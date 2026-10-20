"""flashq — ระบบกลางส่งงานให้ opencode (DeepSeek Flash) ทำแผน แบบมีคิว ใช้ได้ทุกโปรเจกต์

วงจร: Claude Code วางแผน T-xx (push เข้า remote) → `flashq run <แผน> <งาน>` (background)
→ เข้าคิวกลาง (ทีละงานทั้งเครื่อง เพราะทุกโปรเจกต์ใช้บัญชีโมเดลชุดเดียวกัน) → opencode `/flash <แผน> <งาน>`
→ จบ = พิมพ์ `FLASH_RUN=...` → Claude ตรวจต่อ

ที่เก็บ:
- โค้ด = โฟลเดอร์นี้ (repo flashq) · ข้อมูลตอนรัน = `%USERPROFILE%\\.flashq\\` (jobs/ logs/ running*.lock config.json) — ไม่อยู่ใน git ของโปรเจกต์ใด
- ช่องรัน: ช่อง 1 = `running.lock` (ชื่อเดิม · เข้ากันกับ process โค้ดเก่า) · ช่อง n≥2 = `running-<n>.lock` · จำนวนช่อง = `max_parallel` ใน config.json (ค่าเริ่มต้น 1 = ทีละงานแบบเดิม)
- จัดคิว `schedule`: fifo (เดิม · หัวคิวได้ช่องก่อน) | auto (ไล่คิวแล้วเริ่มงานแรกที่ไม่ชนกับงานที่กำลังทำ · ชน = โปรเจกต์เดียวกัน
  และไฟล์ซ้อน/แตะไฟล์ร่วม/ดึงรายการไฟล์ไม่ได้/แผนประกาศ `flashq-parallel: no` · งานที่ชนรอเกิน `starve_min` นาที = ล็อกหัวคิว)
  แผนประกาศชุดไฟล์เองได้ด้วยบรรทัด `flashq-files: <path/glob, ...>` (ใช้แทนการเดาจาก backtick)
- ค่าเฉพาะโปรเจกต์ = `.flash.json` ที่รากโปรเจกต์ (ไม่มี = ค่าเริ่มต้น DEFAULTS)

ใช้:
  python flashq.py run docs\\PLAN_X.md T-01..T-03 [--project <dir>]   ส่งงาน (รอคิวเอง)
  python flashq.py run --message "ตอบแค่คำว่า PONG"                   ทดสอบการเชื่อมต่อ
  python flashq.py verify docs\\PLAN_X.md T-01 [--agent flash-verifier] [--model M]   ส่งผู้ตรวจ (อ่านอย่างเดียว · ไม่ชนงานอื่น)
  python flashq.py run ... --agent <ชื่อ> --title <ชื่อ> --readonly   เลือก agent/ชื่อ session/งานอ่านอย่างเดียวเอง
  python flashq.py [status] | list [--all] | log <id> | cancel <id>
  python flashq.py switch [next|<ชื่อย่อ>]                             สลับบัญชีโมเดล flash-worker
  python flashq.py install [--force]                                    ติดตั้งคำสั่ง /flash + agent แบบ global ให้ opencode
  python flashq.py init [--project <dir>] [--force] [--install] [--commit]       ตั้งค่าโปรเจกต์ใหม่ (ตรวจ branch หลัก/remote เอง → .flash.json)
  python flashq.py prune [--days 30] [--dry]                            ลบงานที่จบแล้ว + log เก่า
  python flashq.py config [max_parallel [<n>]]                          ดู/ตั้งค่า (จำนวนงานที่รันพร้อมกันได้)
  python flashq.py config schedule auto|fifo · config starve_min 120     โหมดจัดคิว · กันอดตาย (นาที)
  python flashq.py runnow <id> [--force]                                ให้งานที่รอคิวได้ช่องพิเศษทันที (คู่ขนาน)
  python flashq.py review start <แผน> [<งาน>] | done <แผน> pass|fail [--note ...] | list   ป้ายให้หน้าออฟฟิศรู้ว่า Claude กำลังตรวจ (/flash-check)
  python flashq.py ui [--port 4097] [--no-open]                         หน้าเว็บ dashboard (127.0.0.1 เท่านั้น)
  python flashq.py goal check|verify|status <GOAL.md> [--reset]          โหมดเป้าหมาย (/flash-goal): ตรวจธง · ตรวจเกณฑ์ + เบรก → GOAL=DONE|CONTINUE|STOP
ผลของ run: บรรทัด `FLASH_RUN=OK|FAIL|QUOTA|TIMEOUT|BUSY|NOSTART|QUEUE_TIMEOUT` · exit 0 = OK · 2 = BUSY (--no-wait) · 3 = รอคิวเกินเวลา · อื่น 1
"""
import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
JOBS, LOGS, LOCK = HOME / "jobs", HOME / "logs", HOME / "running.lock"
REVIEWS = HOME / "reviews"   # ป้าย "Claude กำลังตรวจ" ที่ /flash-check ตั้ง (ให้หน้าออฟฟิศแสดงผู้ตรวจ) — ไม่ใช่งานในคิว
REVIEW_TTL_MIN = 90          # ป้ายที่ค้างเกินนี้ถือว่าถูกทิ้ง (session ตาย/ลืม done)
CONFIG, RUN_NOW = HOME / "config.json", HOME / "run_now"
CONFIG_DEFAULTS = {"max_parallel": 1, "schedule": "fifo", "starve_min": 120}  # ไม่มีไฟล์ config = พฤติกรรมเดิม (ทีละงาน FIFO)
SCHEDULES = ("auto", "fifo")
MAX_SLOTS = 8          # เพดานของ max_parallel
QUEUE_VERSION = 2      # job ที่มี qv>=2 = โค้ดที่รองรับหลายช่อง + สัญญาณ run_now
SLOT_RE = re.compile(r"^running(?:-(\d+))?\.lock$")
OC_CONFIG = Path(os.environ.get("FLASHQ_OPENCODE_CONFIG") or (Path.home() / ".config" / "opencode" / "opencode.json"))
LIVE_URL = os.environ.get("FLASHQ_LIVE_URL") or "http://127.0.0.1:4096"
START_LIMIT_SEC = 180
AGENT_KINDS = {"verify": "flash-verifier", "investigate": "flash-investigator"}  # งานอ่านอย่างเดียวที่ส่ง prompt ตรงให้ agent (ไม่ผ่าน /flash)
SUBAGENT_RE = re.compile(r"is a subagent, not a primary agent|not found\. Falling back to default agent", re.I)
QUOTA_RE = re.compile(r"\b(429|402)\b|rate.?limit|quota|insufficient|balance", re.I)
DEFAULTS = {
    "main_branch": "master",          # branch ที่ opencode ต้องอยู่ + ที่แผนต้องถูก push ไป
    "remote": "origin",
    "require_plan_in_remote": True,   # แผนต้องอยู่ใน <remote>/<main_branch> ก่อนส่ง
    "command": "flash",               # คำสั่ง opencode ที่เรียก (โปรเจกต์มีของตัวเองใน .opencode/command ได้)
    "timeout_min": 480,
    "stall_min": 20,  # log ไม่ขยับเกินนี้ (นาที) = ค้าง → ฆ่าแล้วรายงาน TIMEOUT (0 = ปิด) · งานทำจริง
    "agent_stall_min": 10,  # เหมือน stall_min แต่ผู้ตรวจ/ผู้สืบ
    "stall_floor_min": 8,  # ขั้นต่ำของเกณฑ์ "ค้าง" แบบปรับตามจังหวะงานจริง (เกณฑ์ = max(ค่านี้, 6 × ช่วงเงียบที่นานสุดที่เคยเห็น) แต่ไม่เกิน stall_min)
    "agent_stall_floor_min": 4,
    "agent_timeout_min": 30,  # ผู้ตรวจ/ผู้สืบ (verify/investigate) สั้นกว่างานทำจริง — กัน agent วนจนกินช่องคิว
    "shell_idle_min": 4,  # ตัวเฝ้า shell: คำสั่งที่ทั้งชุดโปรเซส CPU+I/O ไม่ขยับเลยเกินนี้ (นาที) = ค้าง → ฆ่าเฉพาะคำสั่งนั้น (0 = ปิด)
}
SHELL_POLL_SEC = float(os.environ.get("FLASHQ_SHELL_POLL_SEC") or 30)  # ถามสถานะ tool + วัดโปรเซสถี่แค่ไหนตอน log เงียบ
SHELL_NAMES = {"powershell.exe", "pwsh.exe", "cmd.exe", "bash.exe", "sh.exe"}
SHELL_WORDS = {"cmd", "start", "powershell", "pwsh", "bash", "exe", "nologo", "noprofile", "noninteractive", "command", "null", "out-null"}


# ---------- ทั่วไป ----------
def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _proc_info(pid: int) -> tuple[bool, int]:
    """(ยังทำงานอยู่, เวลาเริ่ม process) — เวลาเริ่มใช้กัน pid ถูกนำกลับมาใช้ซ้ำ (Windows ใช้เลขซ้ำบ่อย)"""
    if not pid:
        return False, 0
    if os.name == "nt":
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False, 0
        h = ctypes.c_void_p(h)
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        t = [ctypes.c_ulonglong() for _ in range(4)]
        k32.GetProcessTimes(h, *(ctypes.byref(x) for x in t))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259, t[0].value  # STILL_ACTIVE · creation time
    try:
        os.kill(pid, 0)
        return True, 0
    except OSError:
        return False, 0


def proc_start(pid: int) -> int:
    return _proc_info(pid)[1]


def pid_alive(pid: int, start: int = 0) -> bool:
    alive, st = _proc_info(pid)
    return alive and (not start or not st or st == start)


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}_{threading.get_ident()}.tmp")  # + thread: หน้า ui เขียนไฟล์เดียวกันพร้อมกันได้หลาย thread
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


@contextlib.contextmanager
def file_lock(path: Path, wait_sec: float = 15, stale_sec: float = 60):
    """ล็อกข้าม process แบบไฟล์ O_EXCL · รอได้ wait_sec (เกิน = ทำต่อแบบไม่ล็อก ดีกว่าค้าง) · ไฟล์เก่าเกิน stale_sec = ล็อกที่ process ตายทิ้งไว้"""
    t0, got = time.time(), False
    while time.time() - t0 < wait_sec:
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            got = True
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > stale_sec:
                    path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            time.sleep(0.2)
    try:
        yield got
    finally:
        if got:
            path.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))  # -sig: PowerShell 5.1 / Notepad เก่าเขียน BOM ให้ไฟล์ UTF-8
    except (OSError, ValueError):
        return {}


def opencode_cmd() -> list[str]:
    """FLASHQ_OPENCODE = ทางแทน (ใช้ในเทสต์ · ไฟล์ .py รันด้วย python)"""
    alt = os.environ.get("FLASHQ_OPENCODE")
    if alt:
        return [sys.executable, alt] if alt.endswith(".py") else [alt]
    exe = shutil.which("opencode")
    return [exe] if exe else []


# ---------- โปรเจกต์ ----------
def project_root(start: Path) -> tuple[Path, bool]:
    """รากของ checkout หลัก (worktree → checkout หลัก) · ไม่ใช่ git = โฟลเดอร์นั้นเอง"""
    r = subprocess.run(["git", "-C", str(start), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return start.resolve(), False
    common = Path(r.stdout.strip())
    if common.name != ".git":  # .git แยกที่ (--separate-git-dir / submodule) → parent ของมันไม่ใช่รากโปรเจกต์
        top = subprocess.run(["git", "-C", str(start), "rev-parse", "--path-format=absolute", "--show-toplevel", "--absolute-git-dir"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.splitlines()
        if len(top) >= 2 and top[0].strip() and Path(top[1].strip()) == common:  # ไม่ใช่ linked worktree → toplevel คือราก
            return Path(top[0].strip()), True
    return common.parent, True


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else ""


def detect_remote(root: Path) -> str:
    """origin ถ้ามี · ไม่มี origin แต่มี remote เดียว = remote นั้น · ไม่ใช่ git/ไม่มี remote = origin"""
    remotes = _git(root, "remote").split()
    if not remotes or "origin" in remotes:
        return "origin"
    return remotes[0] if len(remotes) == 1 else "origin"


def detect_main_branch(root: Path, remote: str = "origin") -> str:
    """branch หลักของ repo: remote HEAD → <remote>/main|master ที่มีจริง → branch ปัจจุบัน (checkout หลัก) → master"""
    head = _git(root, "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD")
    if head.startswith(remote + "/"):
        return head[len(remote) + 1:]
    for name in ("main", "master"):
        if _git(root, "rev-parse", "--verify", "-q", f"refs/remotes/{remote}/{name}"):
            return name
    for name in ("main", "master"):  # ยังไม่มี remote → ดู branch ในเครื่อง
        if _git(root, "rev-parse", "--verify", "-q", f"refs/heads/{name}"):
            return name
    cur = _git(root, "branch", "--show-current")
    if cur and not (_git(root, "rev-parse", "--verify", "-q", "HEAD") or cur in ("main", "master")):
        cur = ""  # repo ว่าง (ยังไม่มี commit) และไม่ใช่ชื่อ branch หลักทั่วไป → ไม่เดาว่าเป็น branch หลัก
    return cur or DEFAULTS["main_branch"]


def project_cfg(root: Path) -> dict:
    """DEFAULTS < ตรวจอัตโนมัติ (remote/main_branch เมื่อ .flash.json ไม่ได้ตั้ง) < .flash.json"""
    cfg = dict(DEFAULTS)
    own = read_json(root / ".flash.json")
    if not own and (root / ".flash.json").is_file():
        try:
            json.loads((root / ".flash.json").read_text(encoding="utf-8-sig"))
        except ValueError:
            print(f"คำเตือน: อ่าน {root / '.flash.json'} ไม่ได้ (JSON เสีย?) → ใช้ค่าอัตโนมัติแทน", file=sys.stderr)
    if (root / ".git").exists():
        if "remote" not in own:
            cfg["remote"] = detect_remote(root)
        if "main_branch" not in own:
            cfg["main_branch"] = detect_main_branch(root, own.get("remote") or cfg["remote"])
    cfg.update(own)
    return cfg


def plan_rel(plan: str, root: Path, start: Path) -> str:
    p = Path(plan)
    if p.is_absolute():
        for base in (root, start.resolve()):
            try:
                return p.resolve().relative_to(base.resolve()).as_posix()
            except ValueError:
                pass
        return p.as_posix()
    return plan.replace("\\", "/")


def configured_model() -> str:
    """โมเดลของ flash-worker ใน opencode.json — ไม่ส่ง --model แล้ว opencode run จะใช้ "model" บนสุดของ config แทน"""
    try:
        return read_json(OC_CONFIG)["agent"]["flash-worker"]["model"]
    except (KeyError, TypeError):
        return ""


def agent_model(agent: str) -> str:
    """โมเดลที่ agent นั้นตั้งไว้เองใน opencode.json (agent.<ชื่อ>.model) — ว่างถ้าไม่ได้ตั้ง"""
    try:
        return read_json(OC_CONFIG)["agent"][agent]["model"]
    except (KeyError, TypeError):
        pass
    try:  # ไม่ได้ตั้งใน opencode.json → ใช้ model: ในหัวไฟล์ agent (global) ตามแม่แบบ
        text = (OC_CONFIG.parent / "agent" / f"{agent}.md").read_text(encoding="utf-8-sig")
        m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
        mm = re.search(r"^model:\s*(\S+)\s*$", m.group(1), re.M) if m else None
        return mm.group(1) if mm else ""
    except OSError:
        return ""


def other_providers(model: str, tried: set) -> list[str]:
    """โมเดลเดียวกัน (ชื่อท้ายตรงกัน) ที่ provider อื่นใน opencode.json — เรียงตาม accounts.json ก่อน · ไม่รวมที่ลองแล้ว"""
    tail = model.rsplit("/", 1)[-1]
    provs = read_json(OC_CONFIG).get("provider", {})
    have = [f"{pv}/{name}" for pv, pd in provs.items() for name in (pd.get("models") or {}) if name.rsplit("/", 1)[-1] == tail]
    order = [m for _, m in accounts()[1]]
    have.sort(key=lambda m: order.index(m) if m in order else len(order))
    return [m for m in have if m not in tried]


CITE_RE = re.compile(r"(?<![\w/.\\-])((?:[A-Za-z]:)?[\w./\\-]*[\w-]\.[A-Za-z0-9]{1,6}):(\d+)(?:[-–](\d+))?([^\n]*)")


def check_citations(text: str, root: Path) -> dict:
    """ตรวจ `file:line` ที่ผู้สืบอ้างในรายงาน: ไฟล์มีจริงใต้โปรเจกต์ · เลขบรรทัดไม่เกินไฟล์ · โค้ดที่คัดไว้ใน `...` อยู่ในบรรทัดนั้น (±3)
    ตรวจได้แค่ "อ้างตรงโค้ดจริง" ไม่ได้ตรวจว่าเป็นต้นตอจริง (ยังเป็นหน้าที่ของ Claude)"""
    root = root.resolve()
    tracked: list[str] | None = None
    ok, code, bad, seen = 0, 0, [], set()
    for m in CITE_RE.finditer(text):
        rel, line = m.group(1).replace("\\", "/"), int(m.group(2))
        if (rel, line) in seen:
            continue
        seen.add((rel, line))
        f = (root / rel)
        try:
            inside = f.resolve().is_relative_to(root)
        except OSError:
            inside = False
        if not (inside and f.is_file()):
            if tracked is None:
                tracked = _git(root, "ls-files").splitlines()
            hits = [t for t in tracked if t == rel or t.endswith("/" + rel)]
            f = root / hits[0] if len(hits) == 1 else None
        if f is None or not f.is_file():
            bad.append(f"{rel}:{line} — ไม่พบไฟล์")
            continue
        try:
            lines = f.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            bad.append(f"{rel}:{line} — อ่านไฟล์ไม่ได้")
            continue
        if not 1 <= line <= len(lines):
            bad.append(f"{rel}:{line} — เลขบรรทัดเกินไฟล์ (มี {len(lines)} บรรทัด)")
            continue
        snippets = [x.strip() for x in re.findall(r"`([^`]{4,})`", m.group(4)) if not x.strip().endswith(("()", "/"))]
        window = re.sub(r"\s+", " ", " ".join(lines[max(0, line - 4):line + 3]))
        miss = [x for x in snippets if re.sub(r"\s+", " ", x) not in window]
        if snippets and len(miss) == len(snippets):
            bad.append(f"{rel}:{line} — ข้อความที่คัดไว้ไม่อยู่ในบรรทัดนี้ (±3): `{miss[0][:60]}`")
            continue
        ok += 1
        code += 1 if snippets else 0  # ตรงถึงตัวโค้ด (มีข้อความคัดและตรง) ต่างจากตรงแค่ไฟล์/เลขบรรทัด
    return {"ok": ok, "ok_code": code, "bad": bad}


def dirty_snapshot(root: Path) -> dict | None:
    """ไฟล์ที่ git เห็นว่าเปลี่ยน → (ขนาด, เวลาแก้) · None = ไม่ใช่ git/อ่านไม่ได้ · ใช้ตรวจว่างาน readonly ไม่แตะไฟล์"""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    snap = {}
    for line in r.stdout.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        try:
            st = (root / path).stat()
            snap[path] = (st.st_size, st.st_mtime_ns)
        except OSError:
            snap[path] = None  # ถูกลบ
    return snap


def snapshot_changes(before: dict, after: dict) -> list[str]:
    return sorted({p for p in after if after[p] != before.get(p)} | {p for p in before if p not in after})


# ---------- คิว ----------
def jobs() -> list[dict]:
    out = []
    for f in sorted(JOBS.glob("*.json")):
        j = read_json(f)
        if j:
            out.append(j)
    out.sort(key=lambda j: (j.get("created", ""), j.get("id", "")))
    return out


def save_job(job: dict) -> None:
    write_json(JOBS / f"{job['id']}.json", job)


def live_state(j: dict) -> str:
    s = j.get("status", "?")
    if s in ("queued", "running") and not pid_alive(j.get("pid", 0), j.get("pid_start", 0)):
        return "dead"
    return s


def read_config() -> dict:
    cfg = dict(CONFIG_DEFAULTS)
    cfg.update(read_json(CONFIG))
    return cfg


def max_parallel() -> int:
    try:
        return min(MAX_SLOTS, max(1, int(read_config().get("max_parallel", 1))))
    except (TypeError, ValueError):
        return 1


def set_max_parallel(n: int) -> str:
    """คืนข้อผิดพลาด ("" = สำเร็จ)"""
    if not 1 <= n <= MAX_SLOTS:
        return f"max_parallel ต้องอยู่ระหว่าง 1-{MAX_SLOTS}"
    cfg = read_json(CONFIG)
    cfg["max_parallel"] = n
    write_json(CONFIG, cfg)
    return ""


def schedule_mode() -> str:
    m = str(read_config().get("schedule", "fifo")).lower()
    return m if m in SCHEDULES else "fifo"


def starve_min() -> float:
    try:
        return max(0.1, float(read_config().get("starve_min", 120)))
    except (TypeError, ValueError):
        return 120.0


def set_config(key: str, value) -> tuple[str, str]:
    """ตั้งค่า schedule / starve_min / max_parallel · คืน (ข้อผิดพลาด, ข้อความสำเร็จ)"""
    if key == "max_parallel":
        try:
            err = set_max_parallel(int(value))
        except (TypeError, ValueError):
            err = "max_parallel ต้องเป็นตัวเลข"
        return err, "" if err else f"ตั้งจำนวนงานพร้อมกัน = {max_parallel()} แล้ว"
    cfg = read_json(CONFIG)
    if key == "schedule":
        v = str(value or "").lower()
        if v not in SCHEDULES:
            return f"schedule ต้องเป็น {' | '.join(SCHEDULES)}", ""
        cfg["schedule"] = v
        msg = f"ตั้งโหมดจัดคิว = {v} แล้ว"
        if v == "auto" and int(cfg.get("max_parallel", 1) or 1) < 2:  # auto มีผลเมื่อมี ≥2 ช่อง
            cfg["max_parallel"] = 2
            msg += " (ตั้ง max_parallel = 2 ด้วย — auto ต้องมีอย่างน้อย 2 ช่องถึงจะรันพร้อมกันได้)"
        write_json(CONFIG, cfg)
        return "", msg
    if key == "starve_min":
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "starve_min ต้องเป็นตัวเลข (นาที)", ""
        if not 0.1 <= v <= 7 * 24 * 60:
            return "starve_min ต้องอยู่ระหว่าง 0.1-10080 นาที", ""
        cfg["starve_min"] = v
        write_json(CONFIG, cfg)
        return "", f"ตั้งกันอดตาย = {v:g} นาที แล้ว"
    return f"ไม่รู้จัก '{key}' — ใช้ได้: max_parallel, schedule, starve_min", ""


def slot_path(n: int) -> Path:
    return LOCK if n == 1 else HOME / f"running-{n}.lock"


def slot_files() -> list[tuple[int, Path]]:
    out = []
    for f in HOME.glob("running*.lock"):
        m = SLOT_RE.match(f.name)
        if m:
            out.append((int(m.group(1) or 1), f))
    return sorted(out)


def clear_stale_lock() -> None:
    """ลบช่องที่ process เจ้าของตายแล้ว (ทุกช่อง)"""
    for _, f in slot_files():
        held = read_json(f)
        if held and pid_alive(held.get("pid", 0), held.get("pid_start", 0)):
            continue
        try:
            if not held and time.time() - f.stat().st_mtime < 5:  # เพิ่งสร้าง (O_EXCL แล้วกำลังเขียน) — ยังไม่ใช่ล็อกตาย
                continue
        except OSError:
            continue
        if read_json(f) == held:  # ยังเป็นล็อกเดิมที่ตายแล้ว
            f.unlink(missing_ok=True)


def held_slots() -> list[dict]:
    """ช่องที่ถูกใช้อยู่ (ล้างช่องตายก่อน) · [{id, pid, since, extra, slot}]"""
    clear_stale_lock()
    out = []
    for n, f in slot_files():
        h = read_json(f)
        if h:
            out.append({**h, "slot": n})
    return out


def take_slot(job: dict, extra: bool) -> int:
    """จองช่องว่างเลขต่ำสุดแบบ O_EXCL · คืนเลขช่อง (0 = ไม่ได้)"""
    for n in range(1, MAX_SLOTS * 4 + 1):
        p = slot_path(n)
        if p.exists():
            continue
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"id": job["id"], "pid": os.getpid(), "pid_start": proc_start(os.getpid()), "since": now(),
                       "extra": extra}, f, ensure_ascii=False)
        return n
    return 0


def acquire(job: dict, wait_min: float, no_wait: bool) -> str:
    """คืน "ok" | "busy" | "timeout" · FIFO ตาม created ของงานที่ยังมีชีวิต
    ได้ช่องเมื่อ ไม่มีงานรอก่อนหน้า + ช่องที่ใช้ < max_parallel · หรือมีสัญญาณ run_now (ช่องพิเศษ เกิน max_parallel ได้)"""
    t0, last = time.time(), None
    key = (job["created"], job["id"])
    flag = RUN_NOW / job["id"]
    while True:
        held = held_slots()
        limit = max_parallel()
        legacy_blocked = LOCK.exists()  # job โค้ดเก่ารอได้แค่ running.lock → ช่อง 1 ไม่ว่าง = ไม่นับว่าขวางคิว
        ahead = [j for j in jobs() if j.get("status") == "queued" and (j["created"], j["id"]) < key
                 and live_state(j) == "queued" and not (legacy_blocked and j.get("qv", 0) < QUEUE_VERSION)]
        boost = flag.exists()
        reason = ""
        if schedule_mode() == "auto":
            sch = schedule(held)
            can = job["id"] in sch["start"]
            reason = sch["reasons"].get(job["id"], "")
        else:
            can = not ahead and len(held) < limit
        if boost or can:
            n = take_slot(job, extra=boost and (bool(ahead) or len(held) >= limit))
            if n:
                flag.unlink(missing_ok=True)
                job["slot"] = n
                return "ok"
            time.sleep(0.5)
            continue
        ids = ", ".join(h.get("id", "?") for h in held) or "-"
        if no_wait:
            print(f"FLASH_RUN=BUSY มีงานอื่นทำอยู่ job={ids} (ช่อง {len(held)}/{limit})", flush=True)
            return "busy"
        pos = len(ahead) + 1
        if (pos, len(held), limit, reason) != last:
            print(f"QUEUED ตำแหน่ง {pos} (กำลังทำ: {ids} · ช่อง {len(held)}/{limit})"
                  + (f" · {reason}" if reason else "") + " — รอคิว…", flush=True)
            last = (pos, len(held), limit, reason)
        if time.time() - t0 > wait_min * 60:
            print(f"FLASH_RUN=QUEUE_TIMEOUT รอคิวเกิน {wait_min:g} นาที", flush=True)
            return "timeout"
        for _ in range(6):  # ~3 วิ แต่ตื่นทันทีเมื่อมีสัญญาณ run_now
            time.sleep(0.5)
            if flag.exists():
                break


def release(job: dict) -> None:
    for _, f in slot_files():
        if read_json(f).get("id") == job["id"]:
            f.unlink(missing_ok=True)
    (RUN_NOW / job["id"]).unlink(missing_ok=True)


def request_run_now(j: dict) -> tuple[bool, str]:
    """ให้งานที่รอคิวได้ช่องพิเศษทันที (เกิน max_parallel ได้ครั้งเดียว)
    · job โค้ดใหม่ (qv>=2) = วางไฟล์สัญญาณ run_now/<id>
    · job โค้ดเก่า (รอได้แค่ running.lock) = ย้ายเจ้าของ running.lock ไปช่องเลขอื่นให้ช่อง 1 ว่าง
      (โค้ดเก่าปล่อยล็อกด้วยการเทียบ id → ไม่ลบช่องของงานอื่น · ช่องที่ย้ายไปถูกล้างเองเมื่อ process เจ้าของจบ)"""
    if live_state(j) != "queued":
        return False, f"รันเลยได้เฉพาะงานที่รอคิว (สถานะ {live_state(j)})"
    if j.get("qv", 0) >= QUEUE_VERSION:
        RUN_NOW.mkdir(parents=True, exist_ok=True)
        (RUN_NOW / j["id"]).write_text(now(), encoding="utf-8")
        return True, f"สั่งรันเลย {j['id']} แล้ว — จะได้ช่องพิเศษภายในไม่กี่วินาที"
    key = (j.get("created", ""), j["id"])
    ahead = [x for x in jobs() if x["id"] != j["id"] and x.get("status") == "queued" and live_state(x) == "queued"
             and (x.get("created", ""), x["id"]) < key]
    if ahead:
        return False, (f"งานนี้ส่งด้วยโค้ดเก่าและยังมีงานรอก่อนหน้า {len(ahead)} งาน (โค้ดเก่าไม่แซงคิว) — "
                       "ยกเลิกแล้วส่งใหม่ หรือรันเลยงานหัวคิวก่อน")
    clear_stale_lock()
    held = read_json(LOCK)
    if not LOCK.exists():
        return True, "ช่อง 1 ว่างอยู่แล้ว — งานจะเริ่มเองภายใน ~3 วิ"
    for n in range(2, MAX_SLOTS * 4 + 1):
        p = slot_path(n)
        if p.exists():
            continue
        try:
            os.link(LOCK, p)  # ล้มเหลวถ้าปลายทางมีอยู่แล้ว (กันทับช่องที่เพิ่งมีคนจอง)
        except FileExistsError:
            continue
        except OSError as e:
            return False, f"ย้ายช่องไม่ได้ ({e})"
        LOCK.unlink(missing_ok=True)
        return True, f"ย้ายงาน {held.get('id', '?')} ไปช่อง {n} แล้ว — งานนี้ (ส่งด้วยโค้ดเก่า) จะได้ช่อง 1 ภายใน ~3 วิ"
    return False, "ไม่มีช่องว่างให้ย้าย"


# ---------- ตรวจไฟล์ซ้อนก่อนรันคู่ขนาน ----------
TASK_MARK_RE = re.compile(r"^\s*(?:[-*]\s*\[[ xX]\]\s*\**\s*|#{2,4}\s+\**)(T-\d+[A-Za-z]*)\b")
SKIP_LABELS = ("ก่อน", "หลัง", "ยืนยัน", "หลักฐาน", "commit")
PATHISH_RE = re.compile(r"^[\w.\-/\\:*~]+$")


def task_matcher(spec: str):
    """"T-01..T-03,T-05,T-02R" → ฟังก์ชันเช็ค id งาน · None = อ่านรูปแบบไม่ได้"""
    rules = []
    for part in (x.strip() for x in (spec or "").split(",")):
        m = re.fullmatch(r"T-(\d+)[A-Za-z]*\s*\.\.\s*T-(\d+)[A-Za-z]*", part, re.I)
        if m:
            rules.append((int(m[1]), int(m[2]), None))
            continue
        m = re.fullmatch(r"T-(\d+)([A-Za-z]*)", part, re.I)
        if m:
            rules.append((int(m[1]), int(m[1]), m[2].upper()))
    if not rules:
        return None

    def ok(tid: str) -> bool:
        m = re.match(r"T-(\d+)([A-Za-z]*)", tid, re.I)
        n, suf = int(m[1]), m[2].upper()
        return any(lo <= n <= hi and (s is None or s == suf) for lo, hi, s in rules)
    return ok


def plan_files(project: str, plan: str, tasks: str) -> list[str] | None:
    """path ไฟล์ที่งาน T-xx ที่สั่งจะแตะ — จาก `backtick` ในบล็อกของงาน (หัวงาน + บรรทัด "ไฟล์" ฯลฯ)
    ข้ามบรรทัด ก่อน/หลัง/ยืนยัน/หลักฐาน/commit และ code block · None = ตรวจไม่ได้ (ไม่มีแผน/อ่านไม่ได้/ไม่เจอหัวงาน)"""
    if not plan:
        return None
    try:
        text = (Path(project) / plan).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = task_matcher(tasks)
    if not match:
        return None
    files, found, cur, fence = set(), False, False, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = TASK_MARK_RE.match(line)
        if m:
            cur = match(m.group(1))
            found = found or cur
        elif line.startswith("## ") or line.strip() == "---":
            cur = False
        if not cur or re.sub(r"^\s*[-*]\s*", "", line).startswith(SKIP_LABELS):
            continue
        for tok in re.findall(r"`([^`\n]+)`", line):
            for t in tok.split():
                t = re.sub(r":\d+(-\d+)?$", "", t.strip("~,;()\"'"))
                base = re.split(r"[/\\]", t.rstrip("/\\"))[-1]
                if not (t and PATHISH_RE.match(t) and not t.startswith(("-", "/", "http:", "https:")) and not t[0].isdigit()
                        and ("/" in t or "\\" in t or re.search(r"\.[A-Za-z]\w{0,5}$", t))
                        and re.search(r"[A-Za-z0-9]", base) and not re.fullmatch(r"\.\w+", base)):
                    continue
                is_dir = t.endswith(("/", "\\"))
                p = Path(t)
                if p.is_absolute():
                    try:
                        t = p.relative_to(Path(project)).as_posix() + ("/" if is_dir else "")
                    except ValueError:
                        pass
                files.add(t.replace("\\", "/"))
    return sorted(files) if found else None


def _pnorm(p: str) -> str:
    p = p.replace("\\", "/").lower()
    return p[2:] if p.startswith("./") else p


def _gnorm(p: str) -> str:
    """glob → โฟลเดอร์ส่วนที่ไม่มีอักขระพิเศษ (เทียบแบบอนุรักษ์) · "" = ทั้งโปรเจกต์"""
    p = _pnorm(p)
    cut = [i for i in (p.find(c) for c in "*?[") if i >= 0]
    if not cut:
        return p
    pre = p[:min(cut)]
    return pre[:pre.rfind("/") + 1]


def paths_overlap(a: str, b: str) -> bool:
    a, b = _gnorm(a), _gnorm(b)
    if a == "" or b == "":  # glob ระดับรากครอบทุกไฟล์
        return True
    if a == b or (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b)):
        return True
    if a.endswith("/") or b.endswith("/"):
        return False
    if "/" not in a or "/" not in b:  # ฝั่งหนึ่งมีแค่ชื่อไฟล์ → เทียบชื่อไฟล์
        return a.rsplit("/", 1)[-1] == b.rsplit("/", 1)[-1]
    return False


# ประกาศในแผน (แนะนำ §0): `flashq-files: Client/Src/A.cpp, Client/Src/UI/*.h` · `flashq-parallel: no`
DECL_RE = re.compile(r"^\s*(?:[-*]\s*)?`?\s*flashq-(files|parallel)\s*:\s*(.*?)\s*$", re.I)
NO_WORDS = ("no", "false", "0", "off", "ไม่")
# โฟลเดอร์ระดับบนที่ทุกโมดูลใช้ร่วม (ค่าเริ่มต้น · เพิ่มต่อโปรเจกต์ได้ด้วย "parallel_shared" ใน .flash.json)
DEFAULT_SHARED = ("common/", "util/", "shared/", "cmake/")


def plan_meta(project: str, plan: str) -> dict:
    """{files: list | None (ไม่ได้ประกาศ), parallel: bool} จากบรรทัด flashq-files / flashq-parallel นอก code block"""
    out = {"files": None, "parallel": True}
    if not plan:
        return out
    try:
        text = (Path(project) / plan).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    files, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        m = None if fence else DECL_RE.match(line)
        if not m:
            continue
        val = m[2].strip().strip("`").strip()
        if m[1].lower() == "parallel":
            if val.lower().split(" ")[0] in NO_WORDS:
                out["parallel"] = False
            continue
        if re.search(r"<[^>]*>", val):  # placeholder ของแม่แบบที่ยังไม่เติม
            continue
        for t in re.split(r"[,\s]+", val):
            t = t.strip("`'\"()")
            if t and not t.startswith("-"):
                files.append(t.replace("\\", "/"))
    if files:
        out["files"] = sorted(set(files))
    return out


def job_info(j: dict) -> dict:
    """ชุดไฟล์ที่งานจะแตะ: ใช้ flashq-files ที่แผนประกาศก่อน · ไม่มี = เดาจาก backtick ของงานที่สั่ง (None = ตรวจไม่ได้)"""
    meta = plan_meta(j.get("project", ""), j.get("plan", ""))
    declared = meta["files"] is not None
    files = meta["files"] if declared else plan_files(j.get("project", ""), j.get("plan", ""), j.get("tasks", ""))
    return {"files": files, "parallel": meta["parallel"], "declared": declared}


def shared_paths(project: str) -> list[str]:
    extra = (project_cfg(Path(project)).get("parallel_shared") or []) if project else []
    return list(DEFAULT_SHARED) + [str(x) for x in extra if isinstance(x, str)]


def shared_hit(p: str, shared: list[str], project: str) -> bool:
    """แตะของที่ทุกโมดูลใช้ร่วม: glob ระดับราก · ไฟล์ระดับรากที่มีอยู่จริง (เช่น CMakeLists.txt) · โฟลเดอร์ร่วม"""
    g = _gnorm(p)
    if g == "":
        return True
    if "/" not in g:
        return bool(project) and (Path(project) / p).is_file()
    return any(g.startswith(_pnorm(s).rstrip("/") + "/") for s in shared)


def conflict_reason(a: dict, b: dict, info) -> str:
    """เหตุที่งาน a รันพร้อม b ไม่ได้ ("" = ไม่ชน) · อนุรักษ์: ไม่แน่ใจ = ชน"""
    if _pnorm(a.get("project", "")) != _pnorm(b.get("project", "")):
        return ""
    if a.get("readonly") or b.get("readonly"):  # งานอ่านอย่างเดียว (เช่น ผู้ตรวจ) ไม่แก้ไฟล์ → ไม่ชนใคร
        return ""
    ia, ib = info(a), info(b)
    if not ia["parallel"]:
        return "แผนสั่งให้รอ (flashq-parallel: no)"
    if not ib["parallel"]:
        return "แผนของงานนั้นสั่งห้ามรันคู่ (flashq-parallel: no)"
    if ia["files"] is None:
        return "ดึงรายการไฟล์ของงานนี้ไม่ได้ (ใส่ flashq-files: ในแผน)"
    if ib["files"] is None:
        return "ดึงรายการไฟล์ของงานนั้นไม่ได้"
    over = sorted({x for x in ia["files"] for y in ib["files"] if paths_overlap(x, y)})
    if over:
        return "ไฟล์ " + ", ".join(over[:3]) + (f" (+{len(over) - 3})" if len(over) > 3 else "")
    proj = a.get("project", "")
    sh = shared_paths(proj)
    hit = sorted({x for x in ia["files"] + ib["files"] if shared_hit(x, sh, proj)})
    if hit:
        return "แตะไฟล์ที่ทุกโมดูลใช้ร่วม " + ", ".join(hit[:3]) + (f" (+{len(hit) - 3})" if len(hit) > 3 else "")
    return ""


def schedule(held: list[dict] | None = None) -> dict:
    """จำลองการจัดคิวตอนนี้: {mode, limit, used, start: [id ที่ได้เริ่ม], reasons: {id: เหตุที่ยังรอ}}
    auto = ไล่คิวตามลำดับ เริ่มงานแรกที่ไม่ชนกับงานที่กำลังทำ (+ที่เพิ่งเลือก) · ข้ามงานที่ชน
           แต่งานที่ชนและรอเกิน starve_min นาที = ล็อกหัวคิว (งานหลังจากนั้นห้ามแซง)
    fifo = งานหัวคิวได้ช่องว่างตามลำดับ"""
    held = held_slots() if held is None else held
    limit, mode, starve = max_parallel(), schedule_mode(), starve_min()
    held_ids = {h.get("id") for h in held}
    all_jobs = jobs()
    active = [j for j in all_jobs if live_state(j) == "running"]
    queue = [j for j in all_jobs if j.get("status") == "queued" and live_state(j) == "queued"]
    memo: dict[str, dict] = {}

    def info(j: dict) -> dict:
        if j["id"] not in memo:
            memo[j["id"]] = job_info(j)
        return memo[j["id"]]

    free, start, reasons, barrier = limit - len(held), [], {}, None
    lock_busy = LOCK.exists()
    for q in queue:
        qid = q["id"]
        if qid in held_ids:  # ได้ช่องแล้ว กำลังเปลี่ยนสถานะเป็น running
            active.append(q)
            continue
        if q.get("qv", 0) < QUEUE_VERSION:  # โค้ดรุ่นก่อน: เข้าเองเมื่อ running.lock ว่าง ไม่ฟัง scheduler
            if not lock_busy and free > 0:
                active.append(q)
                free, lock_busy = free - 1, True
                reasons[qid] = "กำลังจะเริ่ม (งานโค้ดรุ่นก่อน)"
            else:
                reasons[qid] = "รอช่อง 1 ว่าง (งานส่งด้วยโค้ดรุ่นก่อน)"
            continue
        if barrier:
            reasons[qid] = f"รอ {barrier} ที่รอนานเกิน {starve:g} นาทีได้เริ่มก่อน (กันอดตาย)"
            continue
        why = ""
        for r in active if mode == "auto" else ():  # ช่องเต็มก็ยังตรวจ เพื่อบอกเหตุชน + นับกันอดตาย
            c = conflict_reason(q, r, info)
            if c:
                why = c if c.startswith("แผนสั่งให้รอ") else f"ชนกับ {r['id']}: {c}"
                break
        if not why:
            if free <= 0:
                reasons[qid] = f"รอช่องว่าง (ช่อง {len(held)}/{limit})"
            else:
                start.append(qid)
                active.append(q)
                free -= 1
            continue
        w = _secs(q.get("created", ""))
        if w is not None and w > starve * 60:
            barrier = qid
            why += f" · รอเกิน {starve:g} นาที → ล็อกหัวคิว"
        reasons[qid] = why
    return {"mode": mode, "limit": limit, "used": len(held), "start": start, "reasons": reasons}


def overlap_report(target: dict) -> dict:
    """เทียบงานที่จะรันเลยกับทุกงานที่กำลังทำ: โปรเจกต์เดียวกันไหม · ไฟล์ซ้อน (None = ตรวจไม่ได้)"""
    mine = job_info(target)["files"]
    items = []
    for j in jobs():
        if j["id"] == target["id"] or live_state(j) != "running":
            continue
        same = _pnorm(j.get("project", "")) == _pnorm(target.get("project", ""))
        theirs = job_info(j)["files"]
        over = None if (mine is None or theirs is None) else (
            sorted({a for a in mine for b in theirs if paths_overlap(a, b)}) if same else [])
        items.append({"id": j["id"], "project_name": Path(j.get("project", "")).name, "plan": j.get("plan", ""),
                      "tasks": j.get("tasks", ""), "message": j.get("message", ""), "model": j.get("model", ""),
                      "same_project": same, "files": theirs, "overlap": over})
    return {"id": target["id"], "files": mine, "running": items,
            "any_overlap": any(i["overlap"] for i in items),
            "unknown": any(i["same_project"] and i["overlap"] is None for i in items),
            "legacy": target.get("qv", 0) < QUEUE_VERSION, "max_parallel": max_parallel(), "used": len(held_slots())}


# ---------- opencode ----------
def ensure_live_server(exe: list[str]) -> bool:
    """เปิด `opencode serve --port 4096` ค้างไว้ (ถ้ายังไม่มี) ให้ desktop ต่อดูสดได้ · cwd กลาง ไม่ผูกโปรเจกต์ (run ส่ง --dir เอง)"""
    import urllib.request

    def up() -> bool:
        try:
            urllib.request.urlopen(LIVE_URL + "/config", timeout=3)
            return True
        except Exception as e:  # 401 ก็แปลว่ามี server อยู่
            return getattr(e, "code", None) is not None
    if up():
        return True
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    sp = subprocess.Popen([*exe, "serve", "--port", "4096", "--hostname", "127.0.0.1"], cwd=str(HOME),
                          stdout=open(HOME / "live_server.log", "ab"), stderr=subprocess.STDOUT, creationflags=flags,
                          env={k: v for k, v in os.environ.items() if k != "OPENCODE_SERVER_PASSWORD"})
    try:  # เก็บ pid ไว้ให้ปิดได้ (taskkill /PID <pid> /T /F) — server นี้เปิดค้างโดยตั้งใจ
        (HOME / "live_server.pid").write_text(str(sp.pid), encoding="utf-8")
    except OSError:
        pass
    for _ in range(30):
        time.sleep(1)
        if up():
            return True
    return False


def wait_session(p: subprocess.Popen, log: Path) -> str | None:
    """รอ sessionID ใน log · "" = process จบก่อน · None = ไม่ขึ้นใน START_LIMIT_SEC (เจอตอน desktop เพิ่งเปิดใหม่)"""
    pos, buf = 0, ""  # อ่านเฉพาะส่วนที่เพิ่มต่อท้าย (ไม่อ่านทั้งไฟล์ซ้ำทุกวินาที)
    for _ in range(START_LIMIT_SEC):
        if p.poll() is not None:
            return ""
        with open(log, "rb") as f:
            f.seek(pos)
            chunk = f.read()
        pos += len(chunk)
        buf = (buf[-200:] + chunk.decode("utf-8", errors="replace"))
        m = re.search(r'"sessionID":"(ses_[^"]+)"', buf)
        if m:
            return m.group(1)
        time.sleep(1)
    return None


def open_in_desktop(sid: str, server: str) -> None:
    node = shutil.which("node")
    if not node:
        return
    r = subprocess.run([node, str(REPO / "oc_desktop_open.mjs"), sid, server or "sidecar"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout.strip() or f"DESKTOP_OPEN=FAIL rc={r.returncode}"), flush=True)


def server_activity(server: str, sid: str, directory: str = "") -> dict | None:
    """ถามเซิร์ฟเวอร์ opencode (เมื่อ attach) ว่า session นี้ + session ลูกหลาน (subagent ที่ /flash ส่งไปทำ T-xx) ขยับล่าสุดเมื่อไร และมี tool ไหนกำลังรันอยู่
    log ของ parent เงียบได้ทั้งที่ subagent กำลังทำงาน → ใช้ตัดสินว่า "ค้างจริง" + บอกสาเหตุ (tool ค้าง vs รอโมเดล) · ถามไม่ได้ = None (ใช้ log อย่างเดียว)
    directory = โฟลเดอร์โปรเจกต์ของ session (server เปิดที่ ~/.flashq · ไม่ส่ง = server หา session ของโปรเจกต์อื่นไม่เจอ)"""
    import urllib.parse
    import urllib.request
    qs = ("?" + urllib.parse.urlencode({"directory": directory})) if directory else ""

    def get(path):
        return json.loads(urllib.request.urlopen(server.rstrip("/") + path + qs, timeout=8).read())
    try:
        updated, running, ids = 0, [], [sid]
        k = 0
        while k < len(ids) and len(ids) < 30:  # ไล่ลูกหลาน (subagent ซ้อน subagent) · จำกัดจำนวนกันวน
            try:
                for c in get(f"/session/{urllib.parse.quote(ids[k])}/children"):
                    if c.get("id") and c["id"] not in ids:
                        ids.append(c["id"])
                        updated = max(updated, (c.get("time") or {}).get("updated", 0))
            except Exception:
                pass
            k += 1
        for i in ids:
            for m in get(f"/session/{urllib.parse.quote(i)}/message")[-2:]:
                updated = max(updated, (m.get("info", {}).get("time") or {}).get("created", 0))
                for p in m.get("parts", []):
                    st = p.get("state") or {}
                    t = st.get("time") or p.get("time") or {}
                    updated = max(updated, t.get("end", 0), t.get("start", 0))
                    if p.get("type") == "tool" and st.get("status") == "running":
                        inp = st.get("input") or {}
                        running.append({"tool": p.get("tool"), "what": str(st.get("title") or inp.get("command") or inp.get("description") or "")[:100],
                                        "since": t.get("start", 0) / 1000, "session": i, "cmd": str(inp.get("command") or "")[:2000]})
        return {"updated": updated / 1000 if updated else 0, "running": running}
    except Exception:
        return None


def proc_table() -> list[dict] | None:
    """โปรเซสทั้งเครื่อง: pid · ppid · name · cmd · created (epoch วินาที) · act (CPU 100ns + ไบต์ I/O สะสม — ตัวนับที่ไม่ขยับ = นิ่งสนิท)
    Windows เท่านั้น (อื่น ๆ = None → ตัวเฝ้า shell ปิด) · เทสต์: FLASHQ_FAKE_PROCS=<ไฟล์ JSON> แทนตารางจริง"""
    fake = os.environ.get("FLASHQ_FAKE_PROCS")
    if fake:
        try:
            return json.loads(Path(fake).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    if os.name != "nt":
        return None
    ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; $e=[datetime]'1970-01-01'; "
          "@(Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{pid=$_.ProcessId; ppid=$_.ParentProcessId; name=$_.Name; cmd=$_.CommandLine; "
          "created=$(if ($_.CreationDate) { ($_.CreationDate.ToUniversalTime() - $e).TotalSeconds } else { 0 }); "
          "act=[double]$_.KernelModeTime + $_.UserModeTime + $_.ReadTransferCount + $_.WriteTransferCount + $_.OtherTransferCount } }) | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rows = json.loads(r.stdout.decode("utf-8", errors="replace") or "[]")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return [{"pid": int(d.get("pid") or 0), "ppid": int(d.get("ppid") or 0), "name": str(d.get("name") or ""), "cmd": str(d.get("cmd") or ""),
             "created": float(d.get("created") or 0), "act": float(d.get("act") or 0)} for d in (rows if isinstance(rows, list) else [rows])]


def shell_kill(pid: int) -> None:
    fake = os.environ.get("FLASHQ_FAKE_PROCS")
    if fake:  # เทสต์: จดว่าฆ่าตัวไหน + เอาออกจากตาราง (ห้ามฆ่า pid จริงของเครื่อง)
        rows = [p for p in json.loads(Path(fake).read_text(encoding="utf-8")) if p["pid"] != pid]
        Path(fake).write_text(json.dumps(rows), encoding="utf-8")
        with open(fake + ".killed", "a", encoding="utf-8") as f:
            f.write(f"{pid}\n")
        return
    kill_tree(pid)


def _cmd_norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'`^]", "", s)).strip().lower()


class ShellWatch:
    """ตัวเฝ้า shell — opencode รันคำสั่งแล้วรอเฉย ๆ ไม่รู้ว่าโปรเซสตายหรือยังทำงาน · ตัวนี้หาโปรเซสของคำสั่ง (shell ที่ command line ตรง + ลูกหลาน)
    แล้ววัด CPU+I/O ทุกรอบ: ขยับ = ปล่อยไป (และกันไม่ให้เกณฑ์ log เงียบฆ่างาน build ยาวที่ทำงานจริง) · นิ่งสนิทเกิน idle_min = ฆ่าเฉพาะคำสั่งนั้น
    · shell จบแล้วแต่โปรเซสลูก (เช่น `start /b`, `&`, server) ยังถือ handle → tool ไม่คืนค่า = ฆ่าลูกนั้นทันทีที่ยืนยันได้ 2 รอบ
    ฆ่าแล้ว tool คืน error → โมเดลทำงานต่อจากจุดเดิม (ไม่ต้องฆ่าทั้งงานแล้วเริ่มใหม่)"""

    def __init__(self, idle_min: float, table=None, killer=None):
        self.idle = idle_min * 60
        self.table = table or proc_table
        self.killer = killer or shell_kill
        self.seen: dict = {}

    def check(self, running: list[dict], now: float | None = None) -> dict | None:
        now = now or time.time()
        bash = [r for r in running if r.get("tool") == "bash" and r.get("cmd")]
        for k in [k for k in self.seen if k not in {(r["session"], r["since"]) for r in bash}]:
            del self.seen[k]  # tool จบแล้ว
        if not bash:
            return None
        tab = self.table()
        if tab is None:
            return None
        by = {p["pid"]: p for p in tab}
        kids: dict = {}
        for p in tab:
            kids.setdefault(p["ppid"], []).append(p)

        def tree(roots):
            out, stack = {}, list(roots)
            while stack and len(out) < 300:
                p = stack.pop()
                if p["pid"] not in out:
                    out[p["pid"]] = p
                    stack += [c for c in kids.get(p["pid"], []) if c["created"] >= p["created"] - 1]  # ppid ของ Windows อาจชี้ pid ที่ถูกใช้ซ้ำ
            return out
        best = None
        for r in bash:
            w = self.seen.setdefault((r["session"], r["since"]), {"pids": {}, "act": None, "chg": now, "gone": 0, "start": now})
            key = _cmd_norm(r["cmd"])[:60]
            shells = [p for p in tab if p["name"].lower() in SHELL_NAMES and r["since"] - 5 <= p["created"] <= r["since"] + 60
                      and key and key in _cmd_norm(p["cmd"])]
            if shells:
                group, w["gone"] = tree(shells), 0
            else:  # shell จบแล้ว: ลูกที่เคยเห็น + ลูกกำพร้า (parent ตาย) ที่เกิดหลัง tool เริ่ม และเป็นลูกของ shell ที่เคยเห็นหรือ command line มีคำจากคำสั่ง
                prev = [by[i] for i, c in w["pids"].items() if i in by and abs(by[i]["created"] - c) < 2]
                toks = [t for t in re.findall(r"[a-z0-9_.-]{3,}", _cmd_norm(r["cmd"])) if t not in SHELL_WORDS]
                orph = [p for p in tab if p["ppid"] not in by and r["since"] - 2 <= p["created"] <= now
                        and (p["ppid"] in w["pids"] or any(t in _cmd_norm(p["cmd"]) for t in toks))]
                group = tree(prev + orph)
                w["gone"] += 1
            for i, p in group.items():
                w["pids"][i] = p["created"]
            act = sum(p["act"] for p in group.values())
            if act != w["act"]:
                w["act"], w["chg"] = act, now
            names = ", ".join(sorted({p["name"] for p in group.values()}))[:80]
            rep = {"cmd": r["what"] or r["cmd"][:100], "session": r["session"], "since": r["since"], "pids": len(group), "names": names,
                   "quiet_sec": round(now - w["chg"]), "run_sec": round(now - r["since"]), "state": "none" if not group else "active", "note": ""}
            if group and not shells and w["gone"] >= 2:
                rep.update(state="killed", note=f"shell จบแล้วแต่โปรเซสลูกยังถือ handle ไว้ ({names}) → tool ไม่คืนค่า")
            elif group and self.idle and now - w["chg"] >= self.idle:
                rep.update(state="killed", note=f"โปรเซสนิ่งสนิท (CPU/I/O ไม่ขยับ) {(now - w['chg']) / 60:.1f} นาที ({names})")
            elif group and now - w["chg"] >= max(SHELL_POLL_SEC * 2, self.idle / 2):
                rep["state"] = "quiet"
            if rep["state"] == "killed":
                for p in group.values():
                    if p["ppid"] not in group:
                        self.killer(p["pid"])
                del self.seen[(r["session"], r["since"])]
            rank = {"killed": 3, "quiet": 2, "active": 1, "none": 0}
            if best is None or rank[rep["state"]] > rank[best["state"]]:
                best = rep
        return best


def run_once(job: dict, cmd: list[str], root: Path, attach: str, timeout_min: int, no_open: bool, attempt: int, stall_min: float = 0, stall_floor: float = 0,
             shell_idle: float = 0) -> dict:
    log = LOGS / f"{job['id']}_{attempt}.jsonl"
    err = LOGS / f"{job['id']}_{attempt}.err"
    job.setdefault("logs", []).append(str(log))
    save_job(job)
    print(f"START {job['id']} รอบ {attempt} title='{job['title']}' model={job.get('model') or '(ค่าเริ่มต้น config)'} "
          f"attach={attach or '-'} log={log}", flush=True)
    t0, status = time.time(), "OK"
    with open(log, "wb") as fo, open(err, "wb") as fe:
        p = subprocess.Popen(cmd, cwd=str(root), stdout=fo, stderr=fe)
        job["child_pid"], job["child_pid_start"] = p.pid, proc_start(p.pid)
        save_job(job)
        sid = wait_session(p, log)
        if sid is None:
            kill_tree(p.pid)
            p.wait()
            rc, status = -1, "NOSTART"
        else:
            if sid:
                job["session"] = sid
                save_job(job)
                if not no_open:
                    open_in_desktop(sid, attach)
            last_poll = 0.0
            last_m, last_chg, maxgap = 0.0, time.time(), 0.0  # จังหวะ log จริง → เกณฑ์ค้างปรับตามงานนี้ (งานที่ปกติขยับทุกครึ่งนาที ไม่ต้องรอ 20 นาทีถึงรู้ว่าค้าง)
            watch = ShellWatch(shell_idle) if shell_idle and attach.startswith("http") and (os.name == "nt" or os.environ.get("FLASHQ_FAKE_PROCS")) else None
            busy_until = 0.0  # ตัวเฝ้า shell เห็นโปรเซสขยับล่าสุด (กันเกณฑ์ log เงียบฆ่างาน build ยาวที่ยังทำงานจริง)
            while True:  # เฝ้า 3 อย่าง: เกินเวลารวม · log เงียบเกิน stall_min (ค้าง) → ฆ่าแล้ว TIMEOUT พร้อมบอกเหตุ · คำสั่ง shell ค้าง → ฆ่าเฉพาะคำสั่ง
                try:
                    rc = p.wait(timeout=max(1, min(15 if stall_min >= 1 and SHELL_POLL_SEC >= 15 else 1, timeout_min * 60 - (time.time() - t0))))
                    break
                except subprocess.TimeoutExpired:
                    why = ""
                    if time.time() - t0 >= timeout_min * 60:
                        why = f"เกินเวลารวม {timeout_min} นาที"
                    else:
                        try:
                            idle = time.time() - os.path.getmtime(log)
                        except OSError:
                            idle = 0
                        try:
                            m = os.path.getmtime(log)
                        except OSError:
                            m = last_m
                        if m != last_m:
                            if job.get("shell_watch"):  # log ขยับ = tool จบแล้ว → ล้างป้ายตัวเฝ้า
                                job["shell_watch"] = None
                                save_job(job)
                            if last_m:
                                maxgap = max(maxgap, time.time() - last_chg)
                            last_m, last_chg = m, time.time()
                        limit = min(stall_min * 60, max(stall_floor * 60, 6 * maxgap)) if stall_min else 0
                        act = None
                        can_ask = attach.startswith("http") and bool(job.get("session"))
                        if can_ask and ((limit and (idle >= limit or (idle >= limit / 2 and time.time() - last_poll >= 20)))
                                        or (watch and idle >= SHELL_POLL_SEC and time.time() - last_poll >= SHELL_POLL_SEC)):
                            # log เงียบแล้ว → ถามเซิร์ฟเวอร์ว่า subagent/tool ยังขยับไหม (ไม่ถามทุกรอบ แต่ถามสดเสมอก่อนตัดสินฆ่า)
                            last_poll = time.time()
                            act = server_activity(attach, job["session"], str(root))
                            if act and act["updated"]:
                                idle = min(idle, time.time() - act["updated"])
                            if act is not None and watch:
                                rep = watch.check(act["running"])
                                job["shell_watch"] = dict(rep, at=now()) if rep else None
                                if rep and rep["state"] == "killed":
                                    job.setdefault("shell_kills", []).append({"at": now(), "cmd": rep["cmd"], "note": rep["note"], "run_sec": rep["run_sec"]})
                                    print(f"SHELL_WATCH: ฆ่าคำสั่งค้าง `{rep['cmd'][:80]}` (รันมา {rep['run_sec'] / 60:.1f} นาที) · {rep['note']} → tool คืน error แล้วงานทำต่อ", flush=True)
                                elif rep and rep["state"] == "active":
                                    busy_until = time.time() - rep["quiet_sec"]
                                save_job(job)
                        if busy_until:
                            idle = min(idle, time.time() - busy_until)
                        if limit and idle >= limit:
                            why = f"STALL: ไม่มีความเคลื่อนไหว {idle / 60:.1f} นาที (เกณฑ์ {limit / 60:.1f} = 6× ช่วงเงียบนานสุดที่เห็น {maxgap / 60:.1f}, ขั้นต่ำ {stall_floor:g}, เพดาน {stall_min:g})"
                            if act is not None:
                                if act["running"]:
                                    r0 = sorted(act["running"], key=lambda r: r["session"] == job["session"])[0]  # tool ของ subagent (ลึกสุด) ก่อน tool `task` ของ parent
                                    why += f" · สาเหตุ: tool `{r0['tool']}` ค้าง ({r0['what']}) รันมา {(time.time() - r0['since']) / 60:.0f} นาทีไม่จบ → คำสั่ง/โปรเซสไม่ตอบ"
                                    if re.search(r"Start-Process|\bstart\s+/b|nohup|Popen|\)\s*&\s*$|&\s*$", r0.get("cmd", ""), re.M | re.I):
                                        why += " · ⚠ คำสั่งเปิดโปรเซสค้าง (เช่นเซิร์ฟเวอร์) ในเบื้องหลัง → bash tool รอ handle ของลูกไม่ยอมคืนค่า: ให้เขียนสคริปต์ที่ เปิด-ทดสอบ-ปิด ในคำสั่งเดียว (try/finally) หรือทดสอบแบบ in-process"
                                else:
                                    why += f" · สาเหตุ: ไม่มี tool ใดรันอยู่ → รอโมเดล/ผู้ให้บริการ ({job.get('model') or 'ค่าเริ่มต้น'}) ตอบไม่ได้"
                            else:
                                why += " · สาเหตุแยกไม่ได้ (ไม่ได้ต่อ server ให้ถามสถานะ tool — ใช้ --attach live)"
                    if why:
                        kill_tree(p.pid)
                        p.wait()
                        rc, status = -1, "TIMEOUT"
                        job["timeout_reason"] = why
                        note = abort_session(job) if attach.startswith("http") else ""  # ฆ่าแค่ `opencode run --attach` → session บน server ยังเดิน (แก้ไฟล์ซ้อนกับรอบลองใหม่/งานถัดไป)
                        if note:
                            print(note, flush=True)
                        break

    session, texts, errors, tools, denied, recent = "", [], [], 0, [], []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        session = session or ev.get("sessionID", "")
        part = ev.get("part") or {}
        if ev.get("type") == "text" and part.get("text"):
            texts.append(part["text"])
        elif ev.get("type") == "tool_use":
            tools += 1
            st = part.get("state") or {}
            inp = st.get("input") or {}
            recent.append(f"{part.get('tool', '?')} {st.get('status', '')} " + str(inp.get("command") or inp.get("filePath") or inp.get("pattern") or "")[:90])
            if "prevents you from using" in str(st.get("error", "")):
                denied.append(str(inp.get("command") or part.get("tool"))[:100])
        elif ev.get("type") == "error" or "error" in ev:
            errors.append(json.dumps(ev.get("error", ev), ensure_ascii=False)[:400])
    errtxt = err.read_text(encoding="utf-8", errors="replace")
    last = texts[-1] if texts else ""
    if status == "OK" and (rc != 0 or errors):
        status = "FAIL"
    if status == "OK" and SUBAGENT_RE.search(errtxt):  # agent เป็น subagent → opencode เงียบ ๆ ไปรัน agent เริ่มต้นแทน
        status = "FAIL"
        errors.append("agent ที่ระบุใช้ไม่ได้ (เป็น subagent หรือหาไม่เจอ → opencode ตกไปใช้ agent เริ่มต้นที่แก้ไฟล์ได้) — ตั้ง mode: all/primary ติดตั้ง agent ให้ครบ หรือใช้ --attach none")
    # ตรวจโควตาจาก error/stderr จริงเท่านั้น — ไม่กวาดข้อความสรุปของ worker (คำว่า balance/quota ในเนื้องานเกมทำให้สลับบัญชีเกินจำเป็น)
    # worker รายงานโควตาเองด้วยบรรทัด "FAIL: quota" (flash.md)
    if (QUOTA_RE.search(" ".join(errors) + errtxt[-2000:]) and (rc != 0 or errors)) or "FAIL: quota" in last:
        status = "QUOTA"
    return {"status": status, "rc": rc, "mins": (time.time() - t0) / 60, "tools": tools,
            "session": session, "errors": errors, "stderr": errtxt.strip()[-600:], "last": last,
            "denied": denied, "recent": recent[-5:]}


# ---------- คำสั่ง ----------
def cmd_run(a) -> int:
    if isinstance(a.message, list):  # investigate รับบรีฟเป็นหลายคำ
        a.message = " ".join(a.message).strip()
    if not a.message and not (a.plan and a.tasks):
        print("ต้องมี <plan> <tasks> หรือ --message")
        return 1
    start = Path(a.project or os.getcwd())
    root, is_git = project_root(start)
    cfg = project_cfg(root)
    for d in (JOBS, LOGS):
        d.mkdir(parents=True, exist_ok=True)

    plan = ""
    if a.plan:
        plan = plan_rel(a.plan, root, start)
        if cfg["require_plan_in_remote"] and is_git:
            ref = f"{cfg['remote']}/{cfg['main_branch']}"
            try:  # จำกัดเวลา + ห้ามถามรหัส (รันแบบ detached จากหน้าเว็บ ไม่มีใครตอบ prompt) · ล้ม = ใช้ ref ในเครื่องที่มีอยู่
                subprocess.run(["git", "-C", str(root), "fetch", "-q", cfg["remote"], cfg["main_branch"]], check=False,
                               stdin=subprocess.DEVNULL, timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            except subprocess.TimeoutExpired:
                print(f"WARN: git fetch {cfg['remote']} เกิน 120 วิ → ตรวจแผนจาก ref ในเครื่องแทน", flush=True)
            if subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{ref}:{plan}"],
                              capture_output=True).returncode != 0:
                print(f"FLASH_RUN=FAIL ไม่พบแผนใน {ref}: {plan} (push แผนก่อน)")
                have = [b for b in ("main", "master")
                        if _git(root, "rev-parse", "--verify", "-q", f"refs/remotes/{cfg['remote']}/{b}")]
                if have and cfg["main_branch"] not in have:
                    print(f"หมายเหตุ: repo นี้มี {cfg['remote']}/{' , '.join(have)} · ถ้า branch หลักไม่ใช่ "
                          f"{cfg['main_branch']} ให้ตั้ง main_branch ใน .flash.json (หรือรัน `flashq init`)")
                elif not _git(root, "remote"):
                    print("หมายเหตุ: repo นี้ยังไม่มี remote · ตั้ง \"require_plan_in_remote\": false ใน .flash.json "
                          "ถ้าไม่ใช้ remote (หรือรัน `flashq init`)")
                return 1
        elif not (root / plan).exists():
            print(f"FLASH_RUN=FAIL ไม่พบไฟล์แผน: {root / plan}")
            return 1
        if is_git:  # /flash หยุดทันทีถ้า checkout ไม่อยู่บน main_branch → บอกสาเหตุจริงตรงนี้ แทนที่จะรอ NOSTART/FAIL
            br = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
            if br != cfg["main_branch"]:
                print(f"FLASH_RUN=FAIL checkout หลัก {root} อยู่บน branch '{br or '(detached)'}' ไม่ใช่ "
                      f"{cfg['main_branch']} → สลับกลับ {cfg['main_branch']} (git switch {cfg['main_branch']}) แล้วสั่งใหม่")
                return 1

    exe = opencode_cmd()
    if not exe:
        print("FLASH_RUN=FAIL ไม่พบคำสั่ง opencode ใน PATH")
        return 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jid = f"{ts}_{os.getpid()}"
    kind = a.kind or ("test" if a.message else "work")  # work = ลงมือตามแผน · verify = ผู้ตรวจ (อ่านอย่างเดียว) · test = --message
    agent = a.agent or AGENT_KINDS.get(kind, "")
    prompt = ""
    if kind == "verify":
        prompt = a.prompt or f"ตรวจแผน {plan} งาน {a.tasks} ตามหน้าที่ของคุณ แล้วรายงานผลสั้น ๆ"
    elif kind == "investigate":
        prompt = a.message
    if a.title:
        title = a.title
    elif kind == "verify":
        title = f"flash-verify {Path(plan).stem} {a.tasks}"
    elif kind == "investigate":
        title = f"flash-investigate {a.message[:40]}"
    else:
        title = f"flash-test {ts}" if a.message else f"flash {Path(plan).stem} {a.tasks}"
    worker_like = agent in ("", "flash-worker")
    # agent อื่น (ผู้ตรวจ/ผู้สำรวจ) ใช้โมเดลที่ตั้งไว้ใน agent นั้นเอง — ไม่ทับด้วยโมเดลของ flash-worker
    model = a.model or (configured_model() if worker_like else agent_model(agent))
    job = {"id": jid, "project": str(root), "plan": plan, "tasks": a.tasks or "", "message": a.message or "",
           "kind": kind, "agent": agent, "prompt": prompt, "readonly": bool(a.readonly or kind in AGENT_KINDS),
           "title": title, "model": model, "status": "queued", "pid": os.getpid(),
           "pid_start": proc_start(os.getpid()), "created": now(), "qv": QUEUE_VERSION}
    save_job(job)

    got = acquire(job, a.wait_min, a.no_wait)
    if got != "ok":
        job.update(status="busy" if got == "busy" else "queue_timeout", finished=now())
        save_job(job)
        return 2 if got == "busy" else 3

    res = {"status": "FAIL", "rc": -1}
    try:
        job.update(status="running", started=now())  # job["slot"] ตั้งโดย acquire
        save_job(job)
        print(f"SLOT ช่อง {job.get('slot', 1)} (max_parallel={max_parallel()})", flush=True)
        attach = LIVE_URL if a.attach == "live" else ("" if a.attach == "none" else a.attach)
        if attach == LIVE_URL and not ensure_live_server(exe):
            print("WARN: เปิด server 4096 ไม่ขึ้น → รันแยก (ดูสดไม่ได้)", flush=True)
            attach = ""
        job["attach"] = attach
        save_job(job)
        timeout_min = a.timeout_min or (cfg["agent_timeout_min"] if kind in AGENT_KINDS else cfg["timeout_min"])
        snap0 = dirty_snapshot(root) if job["readonly"] else None
        switches, nostart_retry, attempt = 0, a.retry_nostart, 0
        stall_retry = 1
        stall_min = cfg["agent_stall_min"] if kind in AGENT_KINDS else cfg["stall_min"]
        stall_floor = cfg["agent_stall_floor_min"] if kind in AGENT_KINDS else cfg["stall_floor_min"]
        tried_models: set = set()
        while True:
            attempt += 1
            cmd = [*exe, "run", "--dir", str(root), "--title", title, "--format", "json"]
            if job["model"]:
                cmd += ["--model", job["model"]]
            if a.variant:
                cmd += ["--variant", a.variant]
            if attach:
                cmd += ["--attach", attach]
            if a.auto:
                cmd += ["--auto"]
            if agent:
                cmd += ["--agent", agent]
            if kind in AGENT_KINDS:
                cmd += ["--", prompt]
            else:
                cmd += ["--", a.message] if a.message else ["--command", cfg["command"], "--", plan, a.tasks]
            res = run_once(job, cmd, root, attach, timeout_min, a.no_open, attempt, stall_min, stall_floor, float(cfg.get("shell_idle_min") or 0))
            if res.get("denied"):
                job["denied"] = (job.get("denied") or []) + res["denied"][:20]
            if res["status"] == "TIMEOUT" and job.get("timeout_reason", "").startswith("STALL") and stall_retry > 0:  # ค้างเพราะ log เงียบ (มักเป็น request ไปโมเดลไม่ตอบ) → ลองใหม่ 1 ครั้ง · งานทำจริง /flash ข้ามงานที่ติ๊ก [x] แล้ว จึงต่อจากที่ค้างได้
                stall_retry -= 1
                if not worker_like and job["model"]:  # ผู้ตรวจ/ผู้สืบ: ค้างที่ผู้ให้บริการนี้ → รอบใหม่ย้ายไปผู้ให้บริการอื่นของโมเดลเดิม (ถ้ามี)
                    tried_models.add(job["model"])
                    alts = other_providers(job["model"], tried_models)
                    if alts:
                        print(f"ย้าย provider {job['model']} → {alts[0]} (โมเดลเดิม) สำหรับรอบใหม่", flush=True)
                        job["model"] = alts[0]
                        save_job(job)
                print(f"TIMEOUT ({job.get('timeout_reason', '')}) → ลองใหม่อัตโนมัติ 1 ครั้ง · ก่อนหน้าทำถึง: " + " | ".join(res.get("recent") or ["(ไม่มี tool)"]), flush=True)
                continue
            if res["status"] == "NOSTART" and nostart_retry > 0:
                nostart_retry -= 1
                print("NOSTART → ลองใหม่อัตโนมัติ 1 ครั้ง", flush=True)
                continue
            if res["status"] == "QUOTA" and not a.model and worker_like and switches < a.switch_on_quota:  # สลับบัญชีเฉพาะ flash-worker
                switches += 1
                with file_lock(HOME / "switch.lock"):  # งานคู่ขนานเจอ QUOTA พร้อมกัน → ตรวจ+สลับทีละงาน (ไม่ข้ามบัญชีทีละสอง)
                    cur = configured_model()
                    new = "" if (cur and job["model"] and cur != job["model"]) else switch_account("next")
                if not new:  # งานอื่นที่รันคู่ขนานสลับไปแล้ว → ใช้ตาม ไม่สลับซ้ำ (กันสลับรัว)
                    if cur and job["model"] and cur != job["model"]:
                        print(f"QUOTA → บัญชีถูกสลับเป็น {cur} แล้ว (โดยงานอื่น) → สั่งงานเดิมซ้ำด้วยบัญชีนั้น (ครั้งที่ {switches})", flush=True)
                        job["model"] = cur
                        continue
                elif new != job["model"]:
                    print(f"QUOTA → สลับบัญชีเป็น {new} แล้วสั่งงานเดิมซ้ำ (ครั้งที่ {switches})", flush=True)
                    job["model"] = new
                    continue
            if res["status"] == "QUOTA" and not worker_like and job["model"] and switches < a.switch_on_quota:
                # ผู้ตรวจ/ผู้สืบ: โควตาหมด → ย้าย provider เป็นโมเดลเดิม (ไม่แตะ opencode.json) แล้วสั่งซ้ำ
                tried_models.add(job["model"])
                alts = other_providers(job["model"], tried_models)
                if alts:
                    switches += 1
                    print(f"QUOTA → ย้าย provider {job['model']} → {alts[0]} (โมเดลเดิม) แล้วสั่งงานเดิมซ้ำ (ครั้งที่ {switches})", flush=True)
                    job["model"] = alts[0]
                    save_job(job)
                    continue
            break
        if snap0 is not None:
            after = dirty_snapshot(root)
            changed = snapshot_changes(snap0, after) if after is not None else []
            if changed:
                others = [j["id"] for j in jobs() if j.get("id") != jid and j.get("project") == str(root) and not j.get("readonly")
                          and live_state(j) == "running"]
                job["modified"] = changed[:50]
                print(f"WARN: งานอ่านอย่างเดียวนี้ไฟล์ในโปรเจกต์เปลี่ยน {len(changed)} ไฟล์: " + ", ".join(changed[:8])
                      + (f" · มีงานอื่นรันในโปรเจกต์เดียวกัน ({', '.join(others)}) อาจเป็นของงานนั้น — ตรวจ git diff ก่อนเชื่อผล" if others
                         else " · ไม่มีงานอื่นในโปรเจกต์นี้ → agent อาจแก้ไฟล์เอง ห้ามเชื่อผล ตรวจ git diff ทันที"), flush=True)
        if kind == "investigate" and res.get("last"):  # ตรวจเลขไฟล์:บรรทัดที่ผู้สืบอ้าง (กลไก · ไม่ใช่การตัดสินว่าเป็นต้นตอจริง)
            cites = check_citations(res["last"], root)
            job["citations"] = cites
            if cites["ok"] or cites["bad"]:
                print(f"CITATIONS: ตรงถึงโค้ด {cites['ok_code']} · ตรงแค่ไฟล์/บรรทัด {cites['ok'] - cites['ok_code']} · ผิด {len(cites['bad'])}" + ("" if not cites["bad"] else " — Claude ต้องไม่เชื่อข้อที่ผิด:"), flush=True)
                for b in cites["bad"][:10]:
                    print("  ✗", b, flush=True)
    finally:
        job.update(status=res["status"].lower(), result=res.get("status"), rc=res.get("rc"),
                   finished=now(), last=(res.get("last") or "")[-1500:])
        save_job(job)
        release(job)

    print(f"FLASH_RUN={res['status']} exit={res['rc']} เวลา={res['mins']:.1f} นาที tool={res['tools']} "
          f"session={res['session']} job={jid}")
    print(f"desktop: โปรเจกต์ {root.name} > session '{title}'")
    if res["status"] == "TIMEOUT":
        print(f"REASON: {job.get('timeout_reason', '')}")
        print("DIAG ก่อนถูกฆ่า (tool ล่าสุด): " + " | ".join(res.get("recent") or ["(ยังไม่เรียก tool เลย → โมเดล/ผู้ให้บริการอาจค้าง)"]))
        print("แนะนำ: เปิด log ดูท้ายไฟล์ · บรีฟกว้างเกิน/ไฟล์ใหญ่เกิน → แบ่งงานให้เล็กลง · ผู้ให้บริการช้า → --model ตัวอื่น แล้วสั่งใหม่")
    if job.get("denied"):
        print(f"DENIED: {len(job['denied'])} คำสั่งถูกสิทธิ์ของ agent บล็อก (ไม่ใช่งานล้มเหลว · agent ต้องใช้ read/grep แทน): " + " | ".join(job["denied"][:5]))
    for e in res["errors"][-3:]:
        print("ERROR:", e)
    if res["stderr"]:
        print("STDERR(ท้าย):", res["stderr"])
    print("---- สรุปท้ายจาก opencode ----")
    print(res["last"][-2500:] if res["last"] else "(ไม่มีข้อความ)")
    return 0 if res["status"] == "OK" else 1


def kind_tag(j: dict) -> str:
    return {"verify": "[ตรวจ] ", "investigate": "[สืบ] "}.get(j.get("kind"), "")


def cmd_list(a) -> int:
    rows = jobs()
    if not a.all:
        rows = [j for j in rows if live_state(j) in ("queued", "running")] or rows[-10:]
    if not rows:
        print("(ยังไม่มีงาน)")
        return 0
    for j in rows:
        what = j.get("message") and "--message" or f"{j.get('plan')} {j.get('tasks')}"
        print(f"{j['id']:24} {live_state(j):13} {Path(j.get('project', '')).name:18} {kind_tag(j)}{what}"
              f"  [{j.get('created', '')}{' → ' + j['finished'] if j.get('finished') else ''}]")
    return 0


def cmd_status(a) -> int:
    held = held_slots()
    q = [j for j in jobs() if live_state(j) == "queued"]
    sch = schedule(held)
    print(f"กำลังทำ: {len(held)} งาน (ช่อง {len(held)}/{max_parallel()} · จัดคิวแบบ {sch['mode']})" + ("" if held else " — ว่าง"))
    for h in held:
        j = next((x for x in jobs() if x["id"] == h.get("id")), {})
        print(f"  ช่อง {h['slot']}{' (พิเศษ)' if h.get('extra') else ''}: {h.get('id', '?')} pid {h.get('pid')} ตั้งแต่ {h.get('since')}"
              + (f" · {Path(j.get('project', '')).name} {kind_tag(j)}{j.get('plan') or '--message'} {j.get('tasks', '')}" if j else ""))
    print(f"รอคิว: {len(q)} งาน")
    for i, j in enumerate(q, 1):
        why = sch["reasons"].get(j["id"]) or ("กำลังจะเริ่ม" if j["id"] in sch["start"] else "")
        print(f"  {i}. {j['id']} {Path(j['project']).name} {kind_tag(j)}{j.get('plan') or '--message'} {j.get('tasks', '')}"
              + (f"\n       ↳ {why}" if why else ""))
    print(f"บัญชี flash-worker: {configured_model() or '(ยังไม่ตั้ง)'}")
    return 0


BG_RE = re.compile(r"Start-Process|\bstart\s+/b|nohup|Popen|&\s*$", re.M | re.I)


def plan_done_tasks(j: dict) -> list[str]:
    """งานในแผนที่ติ๊ก `- [x] **T-xx**` แล้ว (ความจริงของความคืบหน้า — ไม่ต้องเดาจาก log) · รับ `*`/ไม่มีตัวหนา เหมือน TASK_MARK_RE"""
    if not j.get("plan"):
        return []
    try:
        text = (Path(j.get("project", "")) / j["plan"]).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    return re.findall(r"^\s*[-*]\s*\[[xX]\]\s*\**\s*(T-\d+[A-Za-z]*)\b", text, re.M)


def diagnose_job(j: dict) -> dict:
    """งานที่กำลังรันเป็นอย่างไรตอนนี้: log เงียบกี่นาที · subagent/tool ขยับล่าสุด · tool ไหนรันอยู่ → ตัดสิน ok/tool_hang/tool_long/model_wait/unknown"""
    st = live_state(j)
    d = {"id": j.get("id"), "state": st, "log_idle_sec": log_idle_sec(j), "server_idle_sec": None, "running": [], "verdict": "", "text": ""}
    if st != "running":
        d.update(verdict="not_running", text=f"งานไม่ได้รันอยู่ (สถานะ {st})")
        return d
    attach, sid = j.get("attach") or "", j.get("session") or ""
    act = server_activity(attach, sid, j.get("project", "")) if attach.startswith("http") and sid else None
    if act and act["updated"]:
        d["server_idle_sec"] = max(0, int(time.time() - act["updated"]))
    idles = [x for x in (d["log_idle_sec"], d["server_idle_sec"]) if x is not None]
    quiet = min(idles) if idles else None
    d["quiet_sec"] = quiet
    mins = lambda s: f"{s / 60:.0f} นาที" if s is not None else "?"
    base = f"log เงียบ {mins(d['log_idle_sec'])}" + (f" · subagent/tool ขยับล่าสุด {mins(d['server_idle_sec'])} ที่แล้ว" if d["server_idle_sec"] is not None else "")
    if act is None:
        d.update(verdict="unknown", text=base + " · แยกสาเหตุไม่ได้ (ไม่ได้ต่อ server ให้ถามสถานะ tool — งานนี้รัน --attach none หรือ server ไม่ตอบ)")
        return d
    d["running"] = [{"tool": r["tool"], "what": r["what"], "min": round((time.time() - r["since"]) / 60, 1)} for r in act["running"]]
    if quiet is not None and quiet < 180:
        d.update(verdict="ok", text=base + " · ทำงานปกติ")
        return d
    if act["running"]:
        r0 = sorted(act["running"], key=lambda r: r["session"] == sid)[0]
        run_min = (time.time() - r0["since"]) / 60
        bg = bool(BG_RE.search(r0.get("cmd", "")))
        verdict = "tool_hang" if bg or run_min >= 10 else "tool_long"
        d.update(verdict=verdict, text=f"{base} · tool `{r0['tool']}` รันมา {run_min:.0f} นาที: {r0['what']}"
                 + (" · ⚠ คำสั่งเปิดโปรเซสค้างในเบื้องหลัง → tool รอ handle ของลูกไม่คืนค่า (ต้องยกเลิกงาน แล้วให้ทดสอบด้วยสคริปต์ เปิด-ทดสอบ-ปิด)" if bg
                    else (" · นานผิดปกติ น่าจะค้าง" if run_min >= 10 else " · อาจเป็นคำสั่งยาวจริง (build/export) รอต่อได้")))
        return d
    d.update(verdict="model_wait", text=base + f" · ไม่มี tool ใดรันอยู่ → รอโมเดล/ผู้ให้บริการ ({j.get('model') or 'ค่าเริ่มต้น'}) ตอบ — ถ้าเกิน ~10 นาทีควรยกเลิกแล้วสั่งใหม่/ย้ายผู้ให้บริการ")
    return d


def cmd_why(a) -> int:
    """flashq why [id] — งานที่รันอยู่เป็นอย่างไร (ไม่ระบุ id = ทุกงานที่กำลังรัน)"""
    if a.id:
        j = find_job(a.id)
        targets = [j] if j else []
    else:
        targets = [j for j in jobs() if live_state(j) == "running"]
        if not targets:
            print("ไม่มีงานที่กำลังรัน")
    for j in targets:
        d = diagnose_job(j)
        print(f"[{d['verdict'] or d['state']}] {j['id']} {j.get('title', '')}\n   {d['text']}")
    return 0 if targets or not a.id else 1


def find_job(jid: str) -> dict:
    hits = [j for j in jobs() if j["id"].startswith(jid)]
    if len(hits) != 1:
        print(f"หา job '{jid}' ไม่เจอหรือเจอหลายตัว ({len(hits)})")
        return {}
    return hits[0]


def cmd_log(a) -> int:
    j = find_job(a.id)
    if not j:
        return 1
    print(json.dumps({k: v for k, v in j.items() if k != "last"}, ensure_ascii=False, indent=1))
    print("---- ข้อความท้าย ----")
    print(j.get("last") or "(ยังไม่มี)")
    return 0


def abort_session(j: dict) -> str:
    """สั่ง opencode server หยุด session ของงาน (ฆ่า `opencode run --attach` อย่างเดียว session บน server ยังเดินต่อ)
    คืนข้อความผล ("" = ไม่ต้องทำ)"""
    import urllib.parse
    import urllib.request
    server = j.get("attach", LIVE_URL)
    if not j.get("session") or not server:
        return ""
    url = (f"{server.rstrip('/')}/session/{urllib.parse.quote(j['session'])}/abort?"
           + urllib.parse.urlencode({"directory": j.get("project", "")}))
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=b"", method="POST"), timeout=5).read()
        return f"หยุด session {j['session']} บน server แล้ว"
    except Exception as e:
        return f"WARN: หยุด session {j['session']} บน server ไม่ได้ ({e})"


def cancel_job(j: dict) -> tuple[bool, str]:
    """ยกเลิกงานที่รอคิว/กำลังทำ (ใช้ร่วมกับ cmd_cancel และหน้า ui)"""
    st = live_state(j)
    if st not in ("queued", "running"):
        return False, f"job {j['id']} ไม่ได้ทำงานอยู่ (สถานะ {st})"
    note = abort_session(j) if st == "running" else ""
    kill_tree(j["pid"])
    # ลูกถูกฆ่าไปพร้อม /T แล้ว · ฆ่าซ้ำเฉพาะเมื่อยังเป็น process เดิม (pid ของรอบก่อนที่จบไปอาจถูกนำไปใช้ซ้ำโดยโปรแกรมอื่น)
    if j.get("child_pid") and j.get("child_pid_start") and pid_alive(j["child_pid"], j["child_pid_start"]):
        kill_tree(j["child_pid"])
    j.update(status="cancelled", finished=now())
    save_job(j)
    release(j)
    return True, f"ยกเลิก {j['id']} แล้ว" + (f" · {note}" if note else "")


def cmd_cancel(a) -> int:
    j = find_job(a.id)
    if not j:
        return 1
    ok, msg = cancel_job(j)
    print(msg)
    return 0 if ok else 1


def cmd_config(a) -> int:
    if not a.key:
        for k, v in read_config().items():
            print(f"{k} = {v}")
        return 0
    if a.key not in ("max_parallel", "schedule", "starve_min"):
        print(f"ไม่รู้จัก '{a.key}' — ใช้ได้: max_parallel, schedule (auto|fifo), starve_min")
        return 1
    if a.value is None:
        print(f"{a.key} = {read_config().get(a.key)}")
        return 0
    err, msg = set_config(a.key, a.value)
    if err:
        print(err)
        return 1
    print(f"{msg} (งานที่รอคิวใช้ค่าใหม่ภายใน ~3 วิ)")
    return 0


def cmd_runnow(a) -> int:
    j = find_job(a.id)
    if not j:
        return 1
    rep = overlap_report(j)
    for it in rep["running"]:
        over = it["overlap"]
        print(f"เทียบกับ {it['id']} ({it['project_name']}{' · โปรเจกต์เดียวกัน' if it['same_project'] else ''}): "
              + ("ตรวจไฟล์ไม่ได้" if over is None else ("ไฟล์ซ้อน: " + ", ".join(over) if over else "ไม่มีไฟล์ซ้อน")))
    if rep["any_overlap"] and not a.force:
        print("หยุด: มีไฟล์ซ้อนกับงานที่กำลังทำ — ใส่ --force ถ้ายืนยันจะรันคู่ขนาน")
        return 1
    ok, msg = request_run_now(j)
    print(msg)
    return 0 if ok else 1


def accounts() -> tuple[str, list[list[str]]]:
    d = read_json(REPO / "accounts.json")
    return d.get("agent", "flash-worker"), d.get("accounts", [])


def switch_account(arg: str) -> str:
    """สลับบัญชี · คืนโมเดลใหม่ ("" = ล้มเหลว)"""
    agent, accs = accounts()
    cfg = read_json(OC_CONFIG)
    if not cfg:
        print(f"FAIL: อ่าน {OC_CONFIG} ไม่ได้")
        return ""
    current = cfg.get("agent", {}).get(agent, {}).get("model")
    models = [m for _, m in accs]
    if not models:
        print(f"FAIL: ไม่มีรายการบัญชีใน {REPO / 'accounts.json'}")
        return ""
    if arg == "next":
        target = models[(models.index(current) + 1 if current in models else 0) % len(models)]
    else:
        lookup = dict(accs)
        if arg not in lookup:
            print(f"ไม่รู้จัก '{arg}' — ใช้ได้: next, " + ", ".join(lookup))
            return ""
        target = lookup[arg]
    provider, _, name = target.partition("/")
    if name not in cfg.get("provider", {}).get(provider, {}).get("models", {}):
        print(f"FAIL: {target} ไม่มีใน provider ของ {OC_CONFIG}")
        return ""
    shutil.copy2(OC_CONFIG, OC_CONFIG.with_name(OC_CONFIG.name + ".bak-flash-switch"))
    cfg.setdefault("agent", {}).setdefault(agent, {})["model"] = target
    tmp = OC_CONFIG.with_name(OC_CONFIG.name + f".{os.getpid()}.tmp")  # เขียนแล้วสลับไฟล์ — opencode ที่อ่านพร้อมกันไม่เจอไฟล์ครึ่ง ๆ
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, OC_CONFIG)
    print(f"{agent}: {current or '(ยังไม่ตั้ง)'} → {target}")
    return target


def cmd_switch(a) -> int:
    if a.target:
        if not switch_account(a.target):
            return 3
        print("flashq run ใช้บัญชีใหม่ทันที · opencode desktop ต้องรีโหลด/เริ่ม session ใหม่")
        return 0
    agent, accs = accounts()
    cfg = read_json(OC_CONFIG)
    current = cfg.get("agent", {}).get(agent, {}).get("model")
    for short, model in accs:
        provider, _, name = model.partition("/")
        ok = "" if name in cfg.get("provider", {}).get(provider, {}).get("models", {}) else "  (ไม่มีใน provider!)"
        print(f"{'*' if model == current else ' '} {short:7} {model}{ok}")
    print(f"ปัจจุบัน: {current or '(ยังไม่ตั้ง)'} — ดูสถานะอย่างเดียว ไม่ได้เปลี่ยน")
    return 0


def cmd_install(a) -> int:
    """คัดลอก opencode/{command,agent}/*.md ไป ~/.config/opencode/ และ claude/commands/*.md ไป ~/.claude/commands/
    (แทน {{FLASHQ}} ด้วย path repo นี้)"""
    claude_home = Path(os.environ.get("FLASHQ_CLAUDE_HOME") or Path.home() / ".claude")
    pairs = [(REPO / "opencode" / "command", OC_CONFIG.parent / "command"),
             (REPO / "opencode" / "agent", OC_CONFIG.parent / "agent"),
             (REPO / "claude" / "commands", claude_home / "commands")]
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rc = 0
    for src_dir, dst_dir in pairs:
        dst_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(src_dir.glob("*.md")):
            text = src.read_text(encoding="utf-8").replace("{{FLASHQ}}", str(REPO).replace("\\", "/"))
            dst = dst_dir / src.name
            if dst.exists():
                old = dst.read_text(encoding="utf-8")
                if old == text:
                    print(f"เหมือนเดิม  {dst}")
                    continue
                if "flashq:managed" not in old and not a.force:
                    print(f"ข้าม       {dst} (มีไฟล์ที่ไม่ได้มาจาก flashq — ใช้ --force เพื่อสำรองแล้วทับ)")
                    rc = 1
                    continue
                shutil.copy2(dst, dst.with_name(dst.name + f".bak-flashq-{ts}"))
            dst.write_text(text, encoding="utf-8")
            print(f"ติดตั้ง     {dst}")
    return rc


def cmd_init(a) -> int:
    """ตั้งค่าโปรเจกต์ใหม่ให้ใช้ flashq ได้ในคำสั่งเดียว: ตรวจ remote/branch หลัก → .flash.json · .gitignore · แม่แบบแผน
    · เช็ก opencode + คำสั่ง global · ไม่ commit/push ให้ (แจ้งขั้นถัดไปแทน)"""
    start = Path(a.project or os.getcwd())
    root, is_git = project_root(start)
    if not root.is_dir():
        print(f"ไม่พบโฟลเดอร์โปรเจกต์: {root}")
        return 1
    print(f"โปรเจกต์: {root}" + ("" if is_git else "  (ไม่ใช่ git repo)"))
    claude_home = Path(os.environ.get("FLASHQ_CLAUDE_HOME") or Path.home() / ".claude")
    todo: list[str] = []

    # 1) .flash.json — ไม่ทับค่าที่ผู้ใช้ตั้งไว้ (--force = ทับเฉพาะช่องที่ตรวจเจอ)
    path = root / ".flash.json"
    own = read_json(path)
    found: dict = {}
    if is_git:
        remote = detect_remote(root)
        has_remote = bool(_git(root, "remote"))
        found = {"main_branch": detect_main_branch(root, remote), "remote": remote}
        if not has_remote:
            found["require_plan_in_remote"] = False
            todo.append("repo นี้ยังไม่มี remote → ตั้ง require_plan_in_remote=false ไว้ก่อน "
                        "(เพิ่ม remote แล้วลบช่องนี้ออกเพื่อให้แผนต้อง push ก่อนส่ง)")
    else:
        found = {"require_plan_in_remote": False}
    found["plan_dir"] = own.get("plan_dir") or "docs/plans"
    new = dict(own)
    for k, v in found.items():
        if k not in new or a.force:
            new[k] = v
    if new != own or not path.exists():
        write_json(path, new)
        print(f"{'สร้าง' if not own else 'อัปเดต'}  .flash.json: " + json.dumps(new, ensure_ascii=False))
        todo.append("commit + push .flash.json เข้า branch หลัก")
    else:
        print(f"เหมือนเดิม  .flash.json: {json.dumps(own, ensure_ascii=False)}")

    # 2) .gitignore — .tmp/ (ไฟล์ชั่วคราวของ agent)
    gi = root / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    if not any(l.strip().rstrip("/") in (".tmp", "/.tmp") for l in lines):
        gi.write_text("\n".join(lines + [".tmp/"]) + "\n", encoding="utf-8")
        print("เพิ่ม       .gitignore: .tmp/")
        todo.append("commit .gitignore")

    # 3) แม่แบบแผน
    tpl_src = REPO / "templates" / "FLASH_PLAN_TEMPLATE.md"
    tpl_dst = root / new["plan_dir"] / "FLASH_PLAN_TEMPLATE.md"
    if tpl_src.exists() and not tpl_dst.exists():
        tpl_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tpl_src, tpl_dst)
        print(f"คัดลอก     {tpl_dst.relative_to(root).as_posix()} (แม่แบบแผน — ตั้งชื่อแผนจริงเป็น PLAN_FLASH_<เรื่อง>.md)")
        todo.append("commit แม่แบบแผน")

    # 4) เครื่องมือ: opencode + คำสั่ง global
    if opencode_cmd():
        print("พบ         opencode ใน PATH")
    else:
        print("ไม่พบ      opencode ใน PATH — ติดตั้ง opencode ก่อนส่งงาน")
        todo.append("ติดตั้ง opencode ให้อยู่ใน PATH")
    need = [p for p in (OC_CONFIG.parent / "command" / "flash.md", OC_CONFIG.parent / "agent" / "flash-worker.md",
                        claude_home / "commands" / "flash-plan.md", claude_home / "commands" / "flash-check.md")
            if not p.exists()]
    proj_own = [p for p in (root / ".opencode" / "command" / "flash.md", root / ".opencode" / "agent" / "flash-worker.md")
                if p.exists()]
    if need and a.install:
        print("ติดตั้งคำสั่ง global ที่ขาด ...")
        cmd_install(argparse.Namespace(force=False))
    elif need:
        print("ยังไม่ได้ติดตั้งคำสั่ง global: " + ", ".join(p.name for p in need))
        todo.append(f"python {REPO / 'flashq.py'} install  (แล้วรีโหลด opencode desktop)")
    else:
        print("พบ         คำสั่ง /flash /flash-plan /flash-check + agent flash-worker (global)")
    if proj_own:
        print("หมายเหตุ    โปรเจกต์มี flash.md/flash-worker.md ของตัวเอง → opencode ใช้ของโปรเจกต์ก่อน")

    # 5) บัญชีโมเดล
    if not configured_model():
        todo.append(f"ตั้ง agent.flash-worker.model ใน {OC_CONFIG} (หรือส่ง --model ตอน run)")

    # 6) --commit: commit เฉพาะไฟล์ที่ init แตะ (ไม่แตะไฟล์อื่นที่ค้างอยู่) · push เมื่ออยู่ branch หลักและมี remote
    if a.commit and is_git:
        mine = [p for p in (".flash.json", ".gitignore", (root / new["plan_dir"] / "FLASH_PLAN_TEMPLATE.md").relative_to(root).as_posix())
                if (root / p).exists()]
        dirty = _git(root, "status", "--porcelain", "--", *mine)
        if dirty:
            subprocess.run(["git", "-C", str(root), "add", "--", *mine], check=False)
            r = subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "ตั้งค่า flashq สำหรับโปรเจกต์นี้ (.flash.json · .gitignore · แม่แบบแผน)",
                                "--", *mine], capture_output=True, text=True, encoding="utf-8", errors="replace")
            print("commit     " + ("สำเร็จ" if r.returncode == 0 else f"ล้มเหลว: {(r.stderr or r.stdout).strip()}"))
            todo = [t for t in todo if not t.startswith("commit")]
        else:
            print("commit     ไม่มีอะไรต้อง commit")
        branch, remote = _git(root, "branch", "--show-current"), new.get("remote", "origin")
        if _git(root, "remote") and branch == new["main_branch"]:
            r = subprocess.run(["git", "-C", str(root), "push", "-q", remote, f"HEAD:{new['main_branch']}"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            print("push       " + (f"{remote}/{new['main_branch']} สำเร็จ" if r.returncode == 0
                                     else f"ล้มเหลว: {(r.stderr or r.stdout).strip()}"))
        elif _git(root, "remote"):
            todo.append(f"อยู่ branch '{branch}' ไม่ใช่ {new['main_branch']} → merge เข้า {new['main_branch']} แล้ว push เอง")

    print("\nพร้อมใช้ · ทดสอบการเชื่อมต่อ: " + f"python {REPO / 'flashq.py'} run --message \"ตอบแค่คำว่า PONG\" --project \"{root}\"")
    if todo:
        print("ขั้นต่อไป:")
        for i, t in enumerate(todo, 1):
            print(f"  {i}. {t}")
    return 0


# ---------- หน้าเว็บ dashboard (ui) ----------
def _secs(a: str, b: str = "") -> int | None:
    """จำนวนวินาทีจาก a ถึง b (ว่าง = ตอนนี้)"""
    try:
        t0 = datetime.strptime(a, "%Y-%m-%d %H:%M:%S")
        t1 = datetime.strptime(b, "%Y-%m-%d %H:%M:%S") if b else datetime.now()
        return int((t1 - t0).total_seconds())
    except (TypeError, ValueError):
        return None


def log_idle_sec(j: dict) -> int | None:
    """วินาทีนับจากที่ log รอบล่าสุดถูกเขียนครั้งสุดท้าย (ไม่มี/อ่านไม่ได้ = None) — ให้หน้าเว็บเตือน "log เงียบ" ได้แม่นแม้เพิ่งเปิดหน้า"""
    logs = j.get("logs") or []
    try:
        return max(0, int(time.time() - os.path.getmtime(logs[-1]))) if logs else None
    except OSError:
        return None


def _review_rows() -> list[dict]:
    rows = []
    for f in sorted(REVIEWS.glob("rv_*.json")):
        r = read_json(f)
        if r.get("id"):
            r["age_sec"] = _secs(r.get("started", "")) or 0
            r["done_sec"] = _secs(r["finished"]) if r.get("finished") else None
            rows.append(r)
    return rows


def ui_reviews() -> tuple[list[dict], list[dict]]:
    """(กำลังตรวจ · ผลตรวจที่เพิ่งจบ ≤10 นาที) — ป้ายที่เก่าเกิน TTL ไม่นับ"""
    rows = _review_rows()
    act = [r for r in rows if r.get("status") == "reviewing" and r["age_sec"] <= REVIEW_TTL_MIN * 60]
    done = [r for r in rows if r.get("status") in ("pass", "fail") and r["done_sec"] is not None and r["done_sec"] <= 600]
    return act, sorted(done, key=lambda r: r.get("finished", ""), reverse=True)[:10]


def cmd_review(a) -> int:
    """ป้ายสถานะผู้ตรวจ: start = เริ่มตรวจ · done = จบ (pass/fail) · list — ไม่รันอะไรเลย แค่ให้หน้าออฟฟิศแสดงผู้ตรวจ"""
    REVIEWS.mkdir(parents=True, exist_ok=True)
    a.tasks_or_result = " ".join(a.tasks_or_result) if isinstance(a.tasks_or_result, list) else (a.tasks_or_result or "")
    key = (a.plan or "").replace("\\", "/").split("/")[-1]
    if a.action == "list":
        act, done = ui_reviews()
        for r in act + done:
            print(f"{r['id']:34} {r['status']:9} {r.get('plan_name', '')} {r.get('tasks', '')}")
        return 0
    if not key:
        print("ต้องระบุแผน", file=sys.stderr)
        return 1
    if a.action == "start":
        for f in REVIEWS.glob("rv_*.json"):  # ล้างป้ายเก่า > 2 วัน
            try:
                if time.time() - f.stat().st_mtime > 172800:
                    f.unlink()
            except OSError:
                pass
        proj = str(Path(a.project).resolve()) if a.project else str(Path.cwd())
        rid = f"rv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        for r in _review_rows():  # แผนเดียวกันเริ่มใหม่ = ทิ้งป้ายค้างเก่าที่ยังเป็น reviewing
            if r.get("status") == "reviewing" and r.get("plan_name") == key and r.get("project") == proj:
                (REVIEWS / f"{r['id']}.json").unlink(missing_ok=True)
        write_json(REVIEWS / f"{rid}.json", {"id": rid, "project": proj, "project_name": Path(proj).name, "plan_name": key,
                                              "tasks": a.tasks_or_result or "", "status": "reviewing", "started": now()})
        print(f"REVIEW=START id={rid}")
        return 0
    if a.action == "done":
        if a.tasks_or_result not in ("pass", "fail"):
            print("done ต้องตามด้วย pass หรือ fail", file=sys.stderr)
            return 1
        cand = [r for r in _review_rows() if r.get("status") == "reviewing" and r.get("plan_name") == key]
        if not cand:
            print(f"ไม่พบป้ายที่กำลังตรวจของแผน {key} (ข้าม)", file=sys.stderr)
            return 0
        r = max(cand, key=lambda x: x.get("started", ""))
        r.update(status=a.tasks_or_result, finished=now(), note=a.note or "")
        r.pop("age_sec", None), r.pop("done_sec", None)
        write_json(REVIEWS / f"{r['id']}.json", r)
        print(f"REVIEW={a.tasks_or_result.upper()} id={r['id']}")
        return 0
    return 1


def ui_state() -> dict:
    """สถานะทั้งหมดสำหรับ /api/state — อ่านผ่านฟังก์ชันคิวเดิม (ไม่เขียนตรรกะคิวซ้ำ)"""
    held = held_slots()
    sch = schedule(held)
    slot_of = {h.get("id"): h for h in held}
    running, queued, history, dead, kills = [], [], [], [], []
    for j in jobs():
        st = live_state(j)
        kills += [dict(k, job=j["id"], project_name=Path(j.get("project", "")).name, age_sec=_secs(k.get("at", ""))) for k in j.get("shell_kills") or []]
        row = {k: j.get(k, "") for k in ("id", "project", "plan", "tasks", "message", "title", "model",
                                         "kind", "agent", "readonly", "created", "started", "finished", "session", "result", "rc")}
        row.update(state=st, project_name=Path(j.get("project", "")).name, attempts=len(j.get("logs") or []))
        if st == "dead" and j.get("status") in ("queued", "running"):  # ไฟล์ยังบอก queued/running แต่ process flashq ตายแล้ว → ป้ายเตือน
            row.update(was=j.get("status"), pid=j.get("pid"), child_pid=j.get("child_pid") or 0,
                       child_alive=pid_alive(j.get("child_pid") or 0),
                       rerun=(f'python "{REPO / "flashq.py"}" run {j["plan"]} {j.get("tasks", "")} --project "{j.get("project", "")}"'
                              if j.get("plan") else ""))
            dead.append(row)
        if st == "running":
            h = slot_of.get(j["id"], {})
            row.update(elapsed_sec=_secs(j.get("started", "")), slot=h.get("slot") or j.get("slot") or 0, extra=bool(h.get("extra")),
                       log_idle_sec=log_idle_sec(j), plan_done=plan_done_tasks(j), shell_watch=j.get("shell_watch"),
                       shell_kills=len(j.get("shell_kills") or []))
            running.append(row)
        elif st == "queued":
            row.update(wait_sec=_secs(j.get("created", "")), legacy=j.get("qv", 0) < QUEUE_VERSION,
                       run_now=(RUN_NOW / j["id"]).exists(),
                       wait_reason=sch["reasons"].get(j["id"]) or ("กำลังจะเริ่ม" if j["id"] in sch["start"] else ""))
            queued.append(row)
        else:
            row["duration_sec"] = (_secs(j.get("started") or j.get("created", ""), j["finished"])
                                   if j.get("finished") else None)  # งานตายไม่มีเวลาจบ = ไม่รู้ระยะเวลา
            history.append(row)
    for i, row in enumerate(queued, 1):
        row["position"] = i
    agent, accs = accounts()
    cfg = read_json(OC_CONFIG)
    providers = cfg.get("provider", {})
    acc_rows = [{"short": s, "model": m, "available": m.partition("/")[2] in providers.get(m.partition("/")[0], {}).get("models", {})}
                for s, m in accs]
    rows = history + queued + running
    rv_act, rv_done = ui_reviews()
    goals = ui_goals(running)
    return {"now": now(), "lock": held[0] if held else {}, "slots": {"used": len(held), "max": max_parallel(), "held": held},
            "schedule": sch["mode"], "starve_min": starve_min(),
            "running": running[0] if running else None, "running_list": running, "dead": dead, "queued": queued, "history": history[::-1][:300],
            "history_total": len(history), "agent": agent, "current_model": configured_model(), "accounts": acc_rows,
            "projects": sorted({r["project_name"] for r in rows if r["project_name"]}),
            "project_paths": sorted({r["project"] for r in rows if r["project"]}),
            "stats": job_stats(history), "reviews": rv_act, "reviews_done": rv_done,
            "guard": {"idle_min": DEFAULTS["shell_idle_min"], "kills": sorted(kills, key=lambda k: k["at"])[-20:][::-1]},
            "goals": goals}


def job_stats(history: list[dict]) -> dict:
    """สถิติจากงานที่จบแล้ว: ต่อโปรเจกต์ / ต่อบัญชี — จำนวน · ผ่าน · ไม่ผ่าน · เวลาเฉลี่ย (วินาที)"""
    def group(key, only=None) -> list[dict]:
        acc: dict[str, dict] = {}
        for r in history:
            if r["state"] in ("cancelled", "busy", "queue_timeout") or (only and not only(r)):
                continue
            name = key(r) or "-"
            g = acc.setdefault(name, {"name": name, "n": 0, "ok": 0, "secs": []})
            g["n"] += 1
            g["ok"] += r["state"] == "ok"
            if r.get("duration_sec") is not None:
                g["secs"].append(r["duration_sec"])
        out = []
        for g in acc.values():
            secs = g.pop("secs")
            g.update(fail=g["n"] - g["ok"], avg_sec=int(sum(secs) / len(secs)) if secs else None)
            out.append(g)
        return sorted(out, key=lambda g: -g["n"])
    def kind(r) -> str:
        return r.get("kind") or ("test" if r.get("message") else "work")

    def not_verify(r) -> bool:  # งานตรวจ/สืบสั้นกว่ามาก → ไม่ปนสถิติ/เวลาเฉลี่ยของงานทำจริง
        return kind(r) not in AGENT_KINDS
    return {"by_project": group(lambda r: r["project_name"], not_verify), "by_model": group(lambda r: r["model"], not_verify),
            "by_kind": group(kind)}


# ---------- ส่งงาน/สั่งซ้ำ/ล้างประวัติ (ใช้จาก ui) ----------
TASKS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,._-]{0,80}$")
PLAN_SKIP_DIRS = {"node_modules", "venv", "__pycache__", "worktrees", "Temp", "cworking", "cMapeditor", "server_run"}


def list_plans(project: str, limit: int = 400) -> list[str]:
    """ไฟล์แผน flash ในโปรเจกต์ (PLAN_*FLASH*.md) · path แบบ posix สัมพัทธ์ · ข้ามโฟลเดอร์หนัก/ซ่อน/worktree"""
    root = Path(project)
    if not project or not root.is_dir():
        return []
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in PLAN_SKIP_DIRS and not x.startswith((".", "cmake-build"))]
        for f in files:
            up = f.upper()
            if up.startswith("PLAN_") and "FLASH" in up and up.endswith(".MD"):
                out.append((Path(d) / f).relative_to(root).as_posix())
                if len(out) >= limit:
                    return sorted(out)
    return sorted(out)


def build_run_argv(body: dict) -> tuple[list[str], str]:
    """ตรวจค่าจากฟอร์มแล้วสร้าง argv ของ `flashq.py run` (list · ไม่ผ่าน shell) · คืน (argv, "") หรือ ([], ข้อผิดพลาด)"""
    def num(key, lo, hi):
        try:
            v = int(body.get(key) or 0)
        except (TypeError, ValueError):
            raise ValueError(f"{key} ต้องเป็นตัวเลข")
        if not lo <= v <= hi:
            raise ValueError(f"{key} ต้องอยู่ระหว่าง {lo}-{hi}")
        return v
    try:
        project = str(body.get("project") or "").strip().strip('"')
        if not project or not Path(project).is_absolute() or not Path(project).is_dir():
            return [], "โปรเจกต์ต้องเป็น path โฟลเดอร์แบบเต็มที่มีอยู่จริง"
        kind = body.get("kind") if body.get("kind") in AGENT_KINDS else ""
        argv = [sys.executable, str(REPO / "flashq.py"), kind or "run"]
        message = str(body.get("message") or "").strip()
        tail: list[str] = []  # บรีฟของ investigate ต่อท้ายสุดหลัง "--" (ขึ้นต้นด้วย - ก็ไม่ถูกตีเป็นตัวเลือก)
        if kind == "investigate":
            if not message:
                return [], "ต้องระบุบรีฟ (อาการ/สิ่งที่ให้ไปสืบ)"
            if len(message) > 4000:
                return [], "บรีฟยาวเกิน 4000 ตัวอักษร"
            tail = ["--", message]
        elif message and not kind:
            if len(message) > 2000:
                return [], "ข้อความยาวเกิน 2000 ตัวอักษร"
            argv.append(f"--message={message}")  # รูป --x=ค่า กัน argparse ตีความข้อความที่ขึ้นต้นด้วย - เป็นตัวเลือก
        else:
            plan = str(body.get("plan") or "").strip().replace("\\", "/")
            tasks = str(body.get("tasks") or "").strip()
            if not plan or plan.startswith("-"):
                return [], "ต้องระบุไฟล์แผน"
            full = (Path(project) / plan).resolve()
            try:
                full.relative_to(Path(project).resolve())
            except ValueError:
                return [], "ไฟล์แผนต้องอยู่ในโฟลเดอร์โปรเจกต์"
            if not full.is_file():
                return [], f"ไม่พบไฟล์แผน: {plan}"
            if not TASKS_RE.match(tasks):
                return [], "งานต้องเป็นรูปแบบเช่น T-01 หรือ T-01..T-03"
            argv += [plan, tasks]
        argv += ["--project", project, "--switch-on-quota", str(num("switch_on_quota", 0, 10))]
        timeout_min = num("timeout_min", 0, 1440)
        if timeout_min:
            argv += ["--timeout-min", str(timeout_min)]
        attach = str(body.get("attach") or ("none" if kind else "live"))  # agent ใหม่ live server อาจไม่เห็น → ค่าเริ่มต้น none
        if attach not in ("live", "none"):
            return [], "attach ต้องเป็น live หรือ none"
        argv += ["--attach", attach]
        agent = str(body.get("agent") or "").strip()
        if agent:
            if not re.fullmatch(r"[\w.-]{1,64}", agent):
                return [], "ชื่อ agent ใช้ได้แค่ตัวอักษร ตัวเลข _ . -"
            argv.append(f"--agent={agent}")
        if body.get("readonly") and not kind:
            argv.append("--readonly")
        prompt = str(body.get("prompt") or "").strip()
        if prompt and kind == "verify":
            argv.append(f"--prompt={prompt}")
        if body.get("no_open"):
            argv.append("--no-open")
        if body.get("auto"):
            argv.append("--auto")
        return argv + tail, ""
    except ValueError as e:
        return [], str(e)


def spawn_run(argv: list[str], project: str, wait_sec: float = 8) -> dict:
    """รัน `flashq.py run` แบบแยกขาด (detached) ให้ใช้คิวเดิม · รอจนเห็นไฟล์งานใหม่ หรือ process จบก่อน (= ผิดพลาด)"""
    LOGS.mkdir(parents=True, exist_ok=True)
    JOBS.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"submit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.out"
    before = {f.name for f in JOBS.glob("*.json")}
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    with open(out, "wb") as fo:
        p = subprocess.Popen(argv, cwd=project, stdout=fo, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             creationflags=flags, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    t0 = time.time()
    while time.time() - t0 < wait_sec:
        new = sorted(n.removesuffix(".json") for n in {f.name for f in JOBS.glob("*.json")} - before)
        if new:
            return {"ok": True, "job": new[-1], "pid": p.pid, "out": str(out), "message": f"ส่งงานเข้าคิวแล้ว ({new[-1]})"}
        if p.poll() is not None:
            text = out.read_text(encoding="utf-8", errors="replace").strip()
            return {"ok": False, "rc": p.returncode, "out": str(out), "message": text[-1500:] or f"จบทันที rc={p.returncode}"}
        time.sleep(0.2)
    return {"ok": True, "job": "", "pid": p.pid, "out": str(out), "message": "ส่งแล้ว (ยังไม่เห็นไฟล์งาน — ดูในคิวอีกครู่)"}


def prune_jobs(days: float, dry: bool = False) -> dict:
    """ลบงานที่จบแล้วที่เก่ากว่า N วัน (ไฟล์งาน + log + .err) และ submit_*.out เก่า — ไม่แตะงานที่รอคิว/กำลังทำ"""
    cutoff = datetime.now().timestamp() - days * 86400
    n_jobs, files = 0, []
    for j in jobs():
        if live_state(j) in ("queued", "running"):
            continue
        try:
            t = datetime.strptime(j.get("created", ""), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if t >= cutoff:
            continue
        n_jobs += 1
        files.append(JOBS / f"{j['id']}.json")
        for lg in j.get("logs") or []:
            files += [Path(lg), Path(lg).with_suffix(".err")]
    if LOGS.exists():
        files += [f for f in LOGS.glob("submit_*.out") if f.stat().st_mtime < cutoff]
    files = [f for f in files if f.exists()]
    size = sum(f.stat().st_size for f in files)
    if not dry:
        for f in files:
            f.unlink(missing_ok=True)
    return {"jobs": n_jobs, "files": len(files), "bytes": size, "dry": dry}


def cmd_prune(a) -> int:
    r = prune_jobs(a.days, a.dry)
    print(f"{'(ทดลอง) จะลบ' if r['dry'] else 'ลบ'}งาน {r['jobs']} รายการ · ไฟล์ {r['files']} ไฟล์ · "
          f"{r['bytes'] / 1048576:.1f} MB (เก่ากว่า {a.days:g} วัน)")
    return 0


def _fmt_event(line: str) -> str | None:
    """แปลง 1 บรรทัด JSON ของ opencode เป็นข้อความอ่านง่าย · None = ข้าม"""
    try:
        ev = json.loads(line)
    except ValueError:
        return line
    part = ev.get("part") or {}
    t = ev.get("type")
    if t == "text" and part.get("text"):
        return part["text"]
    if t == "tool_use":
        state = part.get("state") or {}
        inp = state.get("input") or {}
        brief = inp.get("command") or inp.get("filePath") or inp.get("pattern") or inp.get("description") or ""
        mark = "❌" if state.get("status") == "error" else "🔧"
        return f"{mark} {part.get('tool', '?')}: {str(brief)[:300]}"
    if t == "error" or "error" in ev:
        return "❌ " + json.dumps(ev.get("error", ev), ensure_ascii=False)[:600]
    return None


def log_tail(j: dict, attempt: int, offset: int, limit: int = 256 * 1024) -> dict:
    """อ่าน log ต่อจาก offset (ไบต์) เฉพาะบรรทัดที่จบแล้ว — ไม่อ่านทั้งไฟล์ซ้ำ"""
    logs = j.get("logs") or []
    out = {"attempts": len(logs), "attempt": 0, "offset": 0, "size": 0, "lines": [], "reset": False,
           "state": live_state(j), "last": j.get("last", "")}
    if not logs:
        return out
    idx = attempt - 1 if 1 <= attempt <= len(logs) else len(logs) - 1
    p = Path(logs[idx])
    size = p.stat().st_size if p.exists() else 0
    if offset > size or offset < 0:  # ไฟล์ถูกเขียนใหม่ → เริ่มต้น
        offset, out["reset"] = 0, True
    data = b""
    if size > offset:
        with open(p, "rb") as f:
            f.seek(offset)
            data = f.read(limit)
        cut = data.rfind(b"\n")
        if cut >= 0:
            data = data[:cut + 1]
        elif len(data) < limit:  # บรรทัดยังเขียนไม่จบ รอรอบหน้า
            data = b""
    lines = [x for x in (_fmt_event(s) for s in data.decode("utf-8", errors="replace").splitlines() if s.strip()) if x]
    out.update(attempt=idx + 1, offset=offset + len(data), size=size, lines=lines)
    return out


def make_ui_server(port: int = 4097):
    """สร้าง server (ยังไม่ serve) · คืน (server, token) — bind 127.0.0.1 เท่านั้น"""
    import secrets
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    token = secrets.token_urlsafe(24)

    class H(BaseHTTPRequestHandler):
        server_version = "flashq-ui"

        def log_message(self, *args):  # เงียบ (poll ทุก 2-3 วิ)
            pass

        def _send(self, code: int, body, ctype: str = "application/json; charset=utf-8") -> None:
            if not isinstance(body, (bytes, str)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _host_ok(self) -> bool:
            """กัน DNS rebinding: Host ต้องเป็น 127.0.0.1/localhost พอร์ตนี้ · Origin (ถ้ามี) ต้องตรงด้วย"""
            p = self.server.server_address[1]
            allowed = {f"127.0.0.1:{p}", f"localhost:{p}"}
            if self.headers.get("Host", "") not in allowed:
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in {f"http://{h}" for h in allowed}

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "host/origin ไม่ได้รับอนุญาต"})
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/":
                html = (REPO / "ui.html").read_text(encoding="utf-8").replace("{{TOKEN}}", token)
                return self._send(200, html, "text/html; charset=utf-8")
            if u.path == "/api/state":
                return self._send(200, ui_state())
            if u.path == "/api/log":
                jid = q.get("id", [""])[0]
                j = next((x for x in jobs() if x.get("id") == jid), None)
                if not j:
                    return self._send(404, {"error": f"ไม่พบงาน {jid}"})
                try:
                    attempt, offset = int(q.get("attempt", ["0"])[0]), int(q.get("offset", ["0"])[0])
                except ValueError:
                    return self._send(400, {"error": "attempt/offset ต้องเป็นตัวเลข"})
                return self._send(200, log_tail(j, attempt, offset))
            if u.path == "/api/why":
                j = next((x for x in jobs() if x.get("id") == q.get("id", [""])[0]), None)
                if not j:
                    return self._send(404, {"error": "ไม่พบงาน"})
                return self._send(200, diagnose_job(j))
            if u.path == "/api/overlap":
                j = next((x for x in jobs() if x.get("id") == q.get("id", [""])[0]), None)
                if not j:
                    return self._send(404, {"error": "ไม่พบงาน"})
                return self._send(200, overlap_report(j))
            if u.path == "/api/plans":
                return self._send(200, {"plans": list_plans(q.get("project", [""])[0])})
            return self._send(404, {"error": "ไม่พบ"})

        def do_POST(self):
            if not self._host_ok() or not secrets.compare_digest(self.headers.get("X-Flashq-Token", ""), token):
                return self._send(403, {"error": "ไม่ได้รับอนุญาต (host/origin/token)"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
            except ValueError:
                return self._send(400, {"error": "body ต้องเป็น JSON"})
            path = urlparse(self.path).path
            if path == "/api/cancel":
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงาน"})
                if live_state(j) != "queued":
                    return self._send(409, {"ok": False, "message": f"ยกเลิกได้เฉพาะงานที่รอคิว (สถานะ {live_state(j)})"})
                ok, msg = cancel_job(j)
                return self._send(200 if ok else 409, {"ok": ok, "message": msg})
            if path == "/api/stop":  # หยุดงานที่กำลังทำ — หน้าเว็บยืนยัน 2 ชั้น + body ต้องมี confirm=id
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงาน"})
                if body.get("confirm") != j["id"]:
                    return self._send(400, {"ok": False, "message": "ต้องยืนยันด้วย id ของงาน"})
                if live_state(j) != "running":
                    return self._send(409, {"ok": False, "message": f"งานนี้ไม่ได้กำลังทำ (สถานะ {live_state(j)})"})
                ok, msg = cancel_job(j)
                return self._send(200 if ok else 409, {"ok": ok, "message": msg})
            if path == "/api/runnow":  # รันเลย (ช่องพิเศษ) — มีไฟล์ซ้อนต้องส่ง ack_overlap=true
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงาน"})
                rep = overlap_report(j)
                if rep["any_overlap"] and body.get("ack_overlap") is not True:
                    return self._send(409, {"ok": False, "message": "มีไฟล์ซ้อนกับงานที่กำลังทำ — ต้องติ๊กยืนยันก่อน", "report": rep})
                ok, msg = request_run_now(j)
                return self._send(200 if ok else 409, {"ok": ok, "message": msg})
            if path == "/api/config":
                keys = [k for k in ("schedule", "max_parallel", "starve_min") if k in body]
                if not keys:
                    return self._send(400, {"ok": False, "message": "ต้องมี max_parallel / schedule / starve_min"})
                msgs = []
                for k in keys:
                    err, msg = set_config(k, body[k])
                    if err:
                        return self._send(400, {"ok": False, "message": err})
                    msgs.append(msg)
                return self._send(200, {"ok": True, "max_parallel": max_parallel(), "schedule": schedule_mode(),
                                        "message": " · ".join(msgs)})
            if path == "/api/dismiss":  # รับทราบงานที่ process ตาย → บันทึกสถานะ dead
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j or live_state(j) != "dead" or j.get("status") not in ("queued", "running"):
                    return self._send(409, {"ok": False, "message": "ไม่ใช่งานที่ process ตายค้างสถานะ"})
                j.update(status="dead", dismissed=now())  # ไม่ใส่ finished: ไม่รู้ว่าตายเมื่อไร
                save_job(j)
                release(j)
                return self._send(200, {"ok": True, "message": f"บันทึก {j['id']} เป็น 'ตาย' แล้ว"})
            if path == "/api/submit":
                argv, err = build_run_argv(body)
                if err:
                    return self._send(400, {"ok": False, "message": err})
                r = spawn_run(argv, str(body["project"]).strip().strip('"'))
                return self._send(200 if r["ok"] else 400, r)
            if path == "/api/retry":  # สั่งงานเดิมซ้ำ (เข้าคิวใหม่) · ตัวเลือกใน body ทับได้
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงาน"})
                if live_state(j) in ("queued", "running"):
                    return self._send(409, {"ok": False, "message": "งานนี้ยังรอคิว/กำลังทำอยู่"})
                spec = {**body, "project": j.get("project", ""), "plan": j.get("plan", ""),
                        "tasks": j.get("tasks", ""), "message": j.get("message", ""), "kind": j.get("kind", ""),
                        "agent": j.get("agent", ""), "readonly": j.get("readonly", False), "prompt": j.get("prompt", "")}
                argv, err = build_run_argv(spec)
                if err:
                    return self._send(400, {"ok": False, "message": err})
                r = spawn_run(argv, spec["project"])
                return self._send(200 if r["ok"] else 400, r)
            if path == "/api/prune":
                try:
                    days = float(body.get("days", 30))
                except (TypeError, ValueError):
                    days = -1
                if days < 1:
                    return self._send(400, {"ok": False, "message": "จำนวนวันต้อง ≥ 1"})
                r = prune_jobs(days, bool(body.get("dry")))
                return self._send(200, {"ok": True, **r, "message": f"{'จะลบ' if r['dry'] else 'ลบ'}งาน {r['jobs']} รายการ · "
                                                                    f"ไฟล์ {r['files']} ไฟล์ ({r['bytes'] / 1048576:.1f} MB)"})
            if path == "/api/open":  # เปิด session ใน opencode desktop (oc_desktop_open.mjs)
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j or not j.get("session"):
                    return self._send(404, {"ok": False, "message": "งานนี้ไม่มี session"})
                import contextlib
                import io
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    open_in_desktop(j["session"], j.get("attach", LIVE_URL))
                out = buf.getvalue().strip() or "ไม่พบ node — เปิดไม่ได้"
                return self._send(200, {"ok": "=OK" in out, "message": out})
            if path == "/api/switch":
                import contextlib
                import io
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    new = switch_account(str(body.get("target") or "next"))
                return self._send(200 if new else 400, {"ok": bool(new), "model": new, "message": buf.getvalue().strip()})
            return self._send(404, {"error": "ไม่พบ"})

    class S(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 128  # ค่าเริ่มต้น 5 → คำขอพร้อมกันเยอะ (เบราว์เซอร์ poll หลายแท็บ/เทสต์) โดน reset บน Windows
        # Windows: SO_REUSEADDR ทำให้เปิด 2 ตัวบนพอร์ตเดียวกันได้ (ตัวที่สองแย่งคำขอ) → ปิด แล้วจองแบบ exclusive
        allow_reuse_address = os.name != "nt"

        def server_bind(self):
            if os.name == "nt":
                import socket
                self.socket.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_EXCLUSIVEADDRUSE", -5), 1)
            super().server_bind()

    return S(("127.0.0.1", port), H), token


def cmd_ui(a) -> int:
    try:
        srv, _ = make_ui_server(a.port)
    except OSError as e:
        import urllib.request
        url = f"http://127.0.0.1:{a.port}/"
        try:  # เปิดค้างอยู่แล้ว (เช่น ดับเบิลคลิก .bat ซ้ำ) → แค่เปิดเบราว์เซอร์
            json.loads(urllib.request.urlopen(url + "api/state", timeout=3).read())
        except Exception:
            print(f"FAIL: เปิดพอร์ต {a.port} ไม่ได้ ({e}) — ลอง --port อื่น")
            return 1
        print(f"UI_URL={url}  (เปิดอยู่แล้ว)", flush=True)
        if not a.no_open:
            import webbrowser
            webbrowser.open(url)
        return 0
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"UI_URL={url}  (Ctrl+C เพื่อปิด)", flush=True)
    if not a.no_open:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


# ---------- โหมดเป้าหมาย (/flash-goal): ตั้งธง → วางแผน → Flash ทำ → ตรวจกับเกณฑ์ → วนจนผ่าน หรือชนเบรก ----------
GOAL_ITEM_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(G-\d+)\s*(.*)$")
GOAL_VAGUE = ("สวย", "ดีขึ้น", "ดีกว่า", "ง่าย", "เร็วขึ้น", "เร็ว", "เหมาะสม", "ถูกต้อง", "สมบูรณ์", "เรียบร้อย", "ใช้งานได้", "ทำงานได้", "ไม่มีบั๊ก",
              "ลื่น", "นิ่ง", "ครบถ้วน", "user-friendly", "nice", "better", "faster", "clean", "properly", "works")
GOAL_TRIVIAL_RE = re.compile(r"^\s*(echo\b|true\s*$|exit\s+0\s*$|rem\b|:\s*$|cd\s*$|dir\s*$|ls\s*$|type\s+nul)", re.I)
GOAL_DEFAULT_ROUNDS, GOAL_ROUNDS_CAP, GOAL_DEFAULT_HOURS = 5, 10, 6


def goal_parse(path: Path) -> dict:
    """อ่านไฟล์ GOAL: เกณฑ์ `- [ ] G-01 <คำอธิบาย> · ตรวจ: `<คำสั่ง>` · ต้องเห็น: `<ข้อความ|re:regex>`` หรือ `· คนตรวจ: <สิ่งที่ user ดู>`
    + บรรทัด `goal-files:` (ขอบเขตที่ Flash แก้ได้) · `goal-locked:` (ห้ามแก้ เช่นเทสต์เกณฑ์) · `goal-max-rounds:` · `goal-max-hours:` · `goal-cmd-timeout-min:`"""
    text = path.read_text(encoding="utf-8", errors="replace")
    items, meta, fence = [], {}, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = re.match(r"^\s*(?:[-*]\s*)?(goal-[a-z-]+)\s*:\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip("`")
            continue
        m = GOAL_ITEM_RE.match(line)
        if not m:
            continue
        rest = m.group(2)
        cmd = re.search(r"ตรวจ\s*:\s*`([^`]+)`", rest)
        exp = re.search(r"ต้องเห็น\s*:\s*`([^`]+)`", rest)
        human = re.search(r"คนตรวจ\s*:\s*(.+)$", rest)
        desc = re.split(r"\s*·\s*(?:ตรวจ|ต้องเห็น|คนตรวจ)\s*:", rest)[0].strip()
        items.append({"id": m.group(1), "desc": desc, "cmd": cmd.group(1).strip() if cmd else "",
                      "expect": exp.group(1) if exp else "", "human": human.group(1).strip() if human and not cmd else ""})
    globs = lambda k: [g.strip().replace("\\", "/") for g in meta.get(k, "").split(",") if g.strip()]  # noqa: E731
    def num(k, d):
        try:
            return float(meta[k])
        except (KeyError, ValueError):
            return d
    sig = json.dumps([[i["id"], i["cmd"], i["expect"], i["human"]] for i in items] + [globs("goal-files"), globs("goal-locked")], ensure_ascii=False)
    return {"items": items, "files": globs("goal-files"), "locked": globs("goal-locked"), "rounds": int(num("goal-max-rounds", GOAL_DEFAULT_ROUNDS)),
            "hours": num("goal-max-hours", GOAL_DEFAULT_HOURS), "cmd_timeout": num("goal-cmd-timeout-min", 10), "has_rounds": "goal-max-rounds" in meta,
            "sig": hashlib.sha1(sig.encode("utf-8")).hexdigest()[:12]}


def goal_lint(g: dict) -> tuple[list[str], list[str]]:
    """ตัวตรวจข้อจำกัดของโหมดเป้าหมาย → (ข้อห้ามที่ต้องแก้ก่อนเริ่ม, คำเตือน)"""
    errs, warns = [], []
    items = g["items"]
    if not items:
        errs.append("ไม่มีเกณฑ์ยอมรับ (บรรทัด `- [ ] G-01 ... · ตรวจ: `คำสั่ง``) → ตัดสินไม่ได้ว่าเสร็จเมื่อไร")
    machine = [i for i in items if i["cmd"]]
    holes = [f"{i['id']}" for i in items if re.search(r"<[^<>\n]+>", i["desc"] + i["cmd"] + i["expect"] + i["human"])]
    holes += [k for k in ("goal-files", "goal-locked") if any("<" in x for x in g["files" if k == "goal-files" else "locked"])]
    if holes:
        errs.append("ยังมีช่องว่างจากแม่แบบ `<...>`: " + ", ".join(holes))
    for i in items:
        low = i["desc"].lower()
        vague = [w for w in GOAL_VAGUE if w in low]
        if not i["cmd"] and not i["human"]:
            errs.append(f"{i['id']}: ไม่มี `ตรวจ:` และไม่มี `คนตรวจ:` → ตรวจด้วยเครื่องไม่ได้ (ธงต้องวัดผลได้)")
        elif i["cmd"] and GOAL_TRIVIAL_RE.match(i["cmd"]):
            errs.append(f"{i['id']}: คำสั่งตรวจ `{i['cmd']}` ผ่านเสมอ ไม่ได้วัดอะไร")
        elif i["cmd"] and vague and not i["expect"]:
            warns.append(f"{i['id']}: คำว่า \"{vague[0]}\" วัดจาก exit 0 อย่างเดียวอาจไม่จริง → เพิ่ม `ต้องเห็น:` หรือแยกเป็น `คนตรวจ:`")
        elif i["cmd"]:
            exe = re.split(r"\s+", i["cmd"].strip())[0].strip("\"'")
            if exe and not (shutil.which(exe) or Path(exe).exists() or exe.lower() in ("cd", "if", "set", "call", "for")):
                warns.append(f"{i['id']}: ไม่พบโปรแกรม `{exe}` ใน PATH (รันจริงอาจล้มทุกรอบ)")
    if items and not machine:
        errs.append("ทุกเกณฑ์เป็น `คนตรวจ:` → วนอัตโนมัติไม่ได้ (ต้องมีเกณฑ์ที่เครื่องตรวจได้อย่างน้อย 1 ข้อ)")
    elif machine and len(machine) * 2 < len(items):
        warns.append(f"เกณฑ์ที่เครื่องตรวจได้มีแค่ {len(machine)}/{len(items)} ข้อ → ผ่านรอบอัตโนมัติแล้วยังต้องให้ user ดูอีกมาก")
    if not g["files"]:
        errs.append("ไม่มี `goal-files:` (ไฟล์/โฟลเดอร์ที่ Flash แก้ได้) → ตรวจไม่ได้ว่างานหลุดขอบเขต")
    if g["rounds"] < 1:
        errs.append("goal-max-rounds ต้อง ≥ 1")
    elif g["rounds"] > GOAL_ROUNDS_CAP:
        warns.append(f"goal-max-rounds {g['rounds']} เกินเพดาน → ใช้ {GOAL_ROUNDS_CAP} (กันกินโควตา Claude ตอนวางแผน/ตรวจ)")
    if not g["has_rounds"]:
        warns.append(f"ไม่ได้ตั้ง goal-max-rounds → ใช้ {GOAL_DEFAULT_ROUNDS}")
    if machine and not g["locked"]:
        warns.append("ไม่มี `goal-locked:` → Flash แก้ไฟล์เทสต์ที่ใช้ตัดสินได้ (ผ่านแบบโกง) · ใส่ path เทสต์เกณฑ์เพื่อล็อก")
    return errs, warns


def _goal_state_path(root: Path, goal: Path) -> Path:
    return root / ".tmp" / "flashq-goal" / (goal.stem + ".json")


def _goal_load(root: Path, goal_arg: str) -> tuple[Path, Path, dict, dict]:
    goal = Path(goal_arg)
    goal = goal if goal.is_absolute() else root / goal
    return goal, _goal_state_path(root, goal), goal_parse(goal), read_json(_goal_state_path(root, goal))


GOALS_DIR = HOME / "goals"  # สำเนาสถานะเป้าหมายทุกโปรเจกต์ ให้ UI เห็น (ต้นฉบับอยู่ใน <project>/.tmp/flashq-goal/)


def goal_publish(root: Path, goal: Path, rel: str, g: dict, st: dict, rounds_max: int) -> None:
    """คัดลอกสถานะเป้าหมายไป ~/.flashq/goals/ (ย่อ: รอบเก่าเก็บแค่ผล · รอบล่าสุดเก็บท้าย output) — พังได้ ไม่ขวางงาน"""
    try:
        title = ""
        for line in goal.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                title = re.sub(r"^#\s*GOAL\s*:\s*", "", line).strip()
                break
        rounds = [{k: r.get(k) for k in ("at", "verdict", "fail", "stop", "human")} for r in st.get("rounds", [])]
        if rounds:
            rounds[-1]["results"] = st["rounds"][-1].get("results", {})
        GOALS_DIR.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(f"{root.resolve()}|{rel}".lower().encode("utf-8")).hexdigest()[:12]
        write_json(GOALS_DIR / f"{key}.json", {
            "id": key, "project": str(root), "goal": rel, "stem": goal.stem, "title": title or goal.stem,
            "items": [{"id": i["id"], "desc": i["desc"], "human": i["human"] if not i["cmd"] else ""} for i in g["items"]],
            "rounds_max": rounds_max, "hours": g["hours"], "started": st.get("started", ""), "updated": now(), "rounds": rounds})
    except Exception:
        pass


def goal_topic(name: str) -> str:
    """ชื่อเรื่องร่วมของ GOAL_<เรื่อง>.md กับ PLAN_FLASH_<เรื่อง>_R<n>.md"""
    s = Path(name).stem
    s = re.sub(r"^(GOAL_|PLAN_FLASH_)", "", s, flags=re.I)
    return re.sub(r"_R\d+$", "", s, flags=re.I).lower()


def ui_goals(running: list[dict]) -> list[dict]:
    """เป้าหมายสำหรับ UI: สถานะ + ผูกงานที่รันอยู่ (แผน _R<n> ในโปรเจกต์เดียวกัน) · ซ่อนที่จบ/หยุดเกิน 3 วัน"""
    out = []
    for f in GOALS_DIR.glob("*.json") if GOALS_DIR.is_dir() else []:
        gl = read_json(f)
        if not gl.get("id"):
            continue
        last = (gl.get("rounds") or [None])[-1]
        verdict = last["verdict"] if last else "START"
        upd = _secs(gl.get("updated", "")) or 0
        if verdict in ("DONE", "DONE_NEEDS_USER", "STOP") and upd > 3 * 86400:
            continue
        proj, topic = os.path.normcase(gl.get("project", "")), goal_topic(gl.get("stem", ""))
        jobs_now = []
        for r in running:
            m = re.search(r"_R(\d+)\.md$", r.get("plan") or "", re.I)
            if m and os.path.normcase(r.get("project", "")) == proj and goal_topic(r["plan"]) == topic:
                jobs_now.append(r["id"])
                r["goal"] = {"id": gl["id"], "round": int(m.group(1)), "rounds_max": gl.get("rounds_max", 0)}
        res = (last or {}).get("results") or {}
        machine = [i for i in gl.get("items", []) if not i.get("human")]
        final = verdict in ("DONE", "DONE_NEEDS_USER", "STOP")
        out.append(dict(gl, verdict=verdict, age_sec=upd,
                        elapsed_sec=_secs(gl.get("started", ""), last["at"]) if final else _secs(gl.get("started", "")),
                        passed=sum(1 for i in machine if res.get(i["id"], {}).get("ok")), machine=len(machine),
                        jobs=jobs_now, project_name=Path(gl.get("project", "")).name))
    return sorted(out, key=lambda x: x.get("updated", ""), reverse=True)[:12]


def _glob_hit(path: str, globs: list[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(path, g) or (g.endswith("/") and path.startswith(g)) or path.startswith(g.rstrip("/") + "/") for g in globs)


def _ts(s: str) -> float:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()
    except (TypeError, ValueError):
        return 0.0


def goal_job_windows(root: Path, stem: str) -> list[tuple[float, float]]:
    """ช่วงเวลาที่งาน Flash ของเป้าหมายนี้รัน (แผน PLAN_FLASH_<เรื่อง>_R<n>.md ในโปรเจกต์เดียวกัน)"""
    proj, topic, out = os.path.normcase(str(root)), goal_topic(stem), []
    for j in jobs():
        plan = j.get("plan") or ""
        if (re.search(r"_R\d+\.md$", plan, re.I) and goal_topic(plan) == topic
                and os.path.normcase(j.get("project", "")) == proj and j.get("started")):
            out.append((_ts(j["started"]), _ts(j.get("finished", "")) or time.time()))
    return out


def goal_changed_files(root: Path, base: str, started: str, windows: list[tuple[float, float]]) -> list[str]:
    """ไฟล์ที่ถูกแก้ระหว่างวนเป้าหมาย — นับเฉพาะ commit (ไม่รวม merge) ที่เกิดระหว่างงาน Flash ของเป้าหมายนี้รัน
    + ไฟล์ค้าง/ยังไม่ track ที่แก้ระหว่างงาน Flash รัน · ไม่มีประวัติงาน = ทุก commit หลัง base + ไฟล์ค้างที่แก้หลังเริ่มเป้าหมาย
    (กัน STOP ผิด: เทสต์เกณฑ์ที่เจ้าของ commit หลัง check · ไฟล์ขยะที่ไม่ track มาก่อน · commit ของ session อื่นในโปรเจกต์เดียวกัน)"""
    out = set()
    if base:
        t = None
        for line in _git(root, "log", "--no-merges", "--format=@@%ct", "--name-only", f"{base}..HEAD").splitlines():
            if line.startswith("@@"):
                t = int(line[2:] or 0)
            elif line.strip() and t is not None and (not windows or any(a - 2 <= t <= b + 5 for a, b in windows)):
                out.add(line.strip())
    dirty = set(_git(root, "diff", "--name-only", "HEAD").splitlines()) | set(_git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    for f in dirty:
        f = f.strip()
        try:
            m = (root / f).stat().st_mtime if f else 0
            if f and (any(a - 2 <= m <= b + 5 for a, b in windows) if windows else m >= _ts(started)):
                out.add(f)
        except OSError:
            out.add(f)  # ถูกลบ = นับว่าแก้
    return sorted(out)


def goal_run_cmd(root: Path, cmd: str, timeout_min: float) -> tuple[int, str]:
    p = subprocess.Popen(cmd, shell=True, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out, _ = p.communicate(timeout=timeout_min * 60)
    except subprocess.TimeoutExpired:
        kill_tree(p.pid)
        out = (p.communicate()[0] or b"") + f"\n[flashq goal: เกิน {timeout_min:g} นาที → ฆ่าแล้ว]".encode("utf-8")
        return 124, out.decode("utf-8", errors="replace")
    return p.returncode, (out or b"").decode("utf-8", errors="replace")


def cmd_goal(a) -> int:
    """check = ตรวจไฟล์เป้าหมายก่อนเริ่ม (ธงวัดได้ไหม · ขอบเขต · งบรอบ) แล้วจด base commit + ลายนิ้วมือเกณฑ์
    verify = รันเกณฑ์ทุกข้อ + ตรวจขอบเขต/ไฟล์ล็อก/เกณฑ์ถูกแก้ + เบรก (รอบ · เวลา · พังซ้ำ) → `GOAL=DONE|DONE_NEEDS_USER|CONTINUE|STOP`
    status = ดูสถานะ (ใช้ต่อหลัง session ปิด)"""
    root, is_git = project_root(Path(a.project or os.getcwd()))
    goal, sp, g, st = _goal_load(root, a.goal)
    if not goal.is_file():
        print(f"GOAL_CHECK=FAIL\nไม่พบไฟล์เป้าหมาย: {goal}")
        return 1
    rel = goal.relative_to(root).as_posix() if goal.is_relative_to(root) else str(goal)
    rounds_max = min(GOAL_ROUNDS_CAP, max(1, g["rounds"]))
    if a.action == "check":
        errs, warns = goal_lint(g)
        if not is_git:
            errs.append("โปรเจกต์ไม่ใช่ git repo → ตรวจขอบเขต/ไฟล์ล็อกไม่ได้")
        for w in warns:
            print(f"เตือน: {w}")
        for e in errs:
            print(f"ต้องแก้: {e}")
        if errs:
            print("GOAL_CHECK=FAIL")
            return 1
        if st and st.get("sig") != g["sig"] and not a.reset:
            print("ต้องแก้: เกณฑ์ต่างจากตอนเริ่ม (ย้ายเสาประตู) → ให้ user ยืนยันเกณฑ์ใหม่แล้วรัน `goal check --reset`")
            print("GOAL_CHECK=FAIL")
            return 1
        if not st or a.reset:
            st = {"goal": rel, "sig": g["sig"], "base": _git(root, "rev-parse", "HEAD"), "started": now(), "rounds": []}
            sp.parent.mkdir(parents=True, exist_ok=True)
            write_json(sp, st)
        goal_publish(root, goal, rel, g, st, rounds_max)
        print(f"GOAL_CHECK=OK เกณฑ์ {len(g['items'])} ข้อ (เครื่องตรวจ {sum(1 for i in g['items'] if i['cmd'])}) · "
              f"งบ {rounds_max} รอบ / {g['hours']:g} ชม. · ใช้ไปแล้ว {len(st['rounds'])} รอบ · base {st['base'][:9]}")
        return 0
    if not st:
        print(f"GOAL=STOP ยังไม่ได้รัน `goal check {rel}` (ต้องตรวจเป้าหมาย + จด base ก่อน)")
        return 1
    if a.action == "status":
        last = st["rounds"][-1] if st["rounds"] else None
        print(f"เป้าหมาย {rel} · เริ่ม {st['started']} (ผ่านไป {(_secs(st['started']) or 0) / 3600:.1f} ชม.) · รอบ {len(st['rounds'])}/{rounds_max} · base {st['base'][:9]}")
        if last:
            print(f"รอบล่าสุด {last['at']}: {last['verdict']} · ไม่ผ่าน {', '.join(last['fail']) or '-'}")
        return 0
    # verify
    stop = []
    if st.get("sig") != g["sig"]:
        stop.append("เกณฑ์/ขอบเขตในไฟล์เป้าหมายถูกแก้หลังเริ่ม (ย้ายเสาประตู) → ให้ user ยืนยัน แล้ว `goal check --reset`")
    results, fail, human = {}, [], []
    for i in g["items"]:
        if not i["cmd"]:
            human.append(f"{i['id']} {i['desc']} → {i['human']}")
            continue
        rc, out = goal_run_cmd(root, i["cmd"], g["cmd_timeout"])
        exp = i["expect"]
        seen = (re.search(exp[3:], out, re.M) is not None) if exp.startswith("re:") else (exp in out) if exp else True
        ok = rc == 0 and seen
        results[i["id"]] = {"ok": ok, "rc": rc, "seen": seen, "tail": out.strip()[-600:]}
        print(f"{'✅' if ok else '❌'} {i['id']} {i['desc']} · exit {rc}{'' if seen else ' · ไม่เห็น `' + exp + '`'}")
        if not ok:
            fail.append(i["id"])
            print("   " + "\n   ".join(out.strip().splitlines()[-8:]))
    changed = goal_changed_files(root, st["base"], st["started"], goal_job_windows(root, goal.stem)) if is_git else []
    cfg = project_cfg(root)
    free = [rel, (cfg.get("plan_dir") or "docs/plans").rstrip("/") + "/", ".flash.json", ".gitignore", ".tmp/"] + g["locked"]
    out_scope = [f for f in changed if not _glob_hit(f, g["files"] + free)]
    locked = [f for f in changed if g["locked"] and _glob_hit(f, g["locked"])]
    if locked:
        stop.append("ไฟล์ล็อก (เกณฑ์/เทสต์ตัดสิน) ถูกแก้: " + ", ".join(locked[:8]))
    if out_scope:
        stop.append("แก้ไฟล์นอกขอบเขต goal-files: " + ", ".join(out_scope[:8]) + (" …" if len(out_scope) > 8 else ""))
    prev = st["rounds"][-1] if st["rounds"] else None
    regress = [k for k, r in results.items() if not r["ok"] and prev and prev["results"].get(k, {}).get("ok")]
    n = len(st["rounds"]) + 1
    hrs = (_secs(st["started"]) or 0) / 3600
    if not stop and not fail:
        verdict = "DONE_NEEDS_USER" if human else "DONE"
    elif stop:
        verdict = "STOP"
    else:
        if prev and prev["fail"] == fail and all(prev["results"].get(k, {}).get("tail") == results[k]["tail"] for k in fail):
            stop.append(f"พังซ้ำเรื่องเดิม 2 รอบติด ({', '.join(fail)} ผลเหมือนเดิมทุกตัวอักษร) → แผนแก้ไม่ถูกจุด ต้องให้ user/สืบต้นตอใหม่")
        if n >= rounds_max:
            stop.append(f"ครบงบ {rounds_max} รอบแล้วยังไม่ผ่าน")
        if hrs >= g["hours"]:
            stop.append(f"เกินงบเวลา {g['hours']:g} ชม. (ผ่านไป {hrs:.1f})")
        verdict = "STOP" if stop else "CONTINUE"
    st["rounds"].append({"at": now(), "verdict": verdict, "fail": fail, "results": results, "out_scope": out_scope, "locked": locked,
                         "stop": stop, "human": human})
    write_json(sp, st)
    goal_publish(root, goal, rel, g, st, rounds_max)
    if regress:
        print(f"ถอยหลัง: {', '.join(regress)} เคยผ่านรอบก่อนแต่รอบนี้ไม่ผ่าน → แผนรอบหน้าต้องแก้ตัวนี้ก่อน")
    for s in stop:
        print(f"เบรก: {s}")
    if human:
        print("ให้ user ตรวจเอง:\n  " + "\n  ".join(human))
    left = rounds_max - n
    print(f"GOAL={verdict} รอบ {n}/{rounds_max} · ไม่ผ่าน {', '.join(fail) or '-'}" + (f" · เหลือ {left} รอบ" if verdict == "CONTINUE" else ""))
    return 0 if verdict in ("DONE", "DONE_NEEDS_USER", "CONTINUE") else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pipe บน Windows = cp874 พังกับไทย/อีโมจิ
    HOME.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser(prog="flashq")
    sp = ap.add_subparsers(dest="cmd")
    r = sp.add_parser("run", help="ส่งงานเข้าคิว")
    r.add_argument("plan", nargs="?")
    r.add_argument("tasks", nargs="?")
    r.add_argument("--message", help="ส่งข้อความตรง (ทดสอบ) แทนคำสั่ง /flash")
    r.set_defaults(kind="", prompt="")
    vf = sp.add_parser("verify", help="ส่งผู้ตรวจ (agent อ่านอย่างเดียว) เข้าคิว · ไม่ชนงานอื่นในตัวจัดคิว")
    vf.add_argument("plan")
    vf.add_argument("tasks")
    vf.add_argument("--prompt", help="ข้อความสั่งผู้ตรวจ (ค่าเริ่มต้น = ตรวจแผน/งานนี้ตามหน้าที่)")
    vf.set_defaults(kind="verify", message="")
    inv = sp.add_parser("investigate", help="ส่งผู้สืบ (agent อ่านอย่างเดียว) ไปไล่หาต้นตอบั๊กตามบรีฟ · ไม่ชนงานอื่น")
    inv.add_argument("message", nargs="+", help="บรีฟ: อาการ + โมดูลที่น่าจะเกี่ยว + สิ่งที่ต้องคืน")
    inv.set_defaults(kind="investigate", plan="", tasks="", prompt="")
    for r in (r, vf, inv):  # ตัวเลือกร่วมของ run/verify/investigate
        r.add_argument("--project", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd · worktree → checkout หลัก)")
        r.add_argument("--agent", default="", help="agent ของ opencode ที่ใช้ (verify = flash-verifier · investigate = flash-investigator)")
        r.add_argument("--title", default="", help="ชื่อ session ใน opencode")
        r.add_argument("--readonly", action="store_true", help="งานอ่านอย่างเดียว ไม่ชนงานอื่นในตัวจัดคิว (verify/investigate เปิดให้เสมอ)")
        r.add_argument("--attach", default="live", help="live (ค่าเริ่มต้นของ run) = server 4096 ให้ desktop ดูสด · none = รันแยก (ค่าเริ่มต้นของ verify/investigate) · หรือ url")
        r.add_argument("--model", help="provider/model (ค่าเริ่มต้น = agent.flash-worker.model · ระบุเอง = ไม่สลับบัญชีอัตโนมัติ)")
        r.add_argument("--variant")
        r.add_argument("--timeout-min", type=int, default=0, help="ค่าเริ่มต้นจาก .flash.json (480)")
        r.add_argument("--wait-min", type=float, default=720, help="รอคิวได้นานสุดกี่นาที")
        r.add_argument("--no-wait", action="store_true", help="คิวไม่ว่าง = จบทันที FLASH_RUN=BUSY")
        r.add_argument("--switch-on-quota", type=int, default=0, help="QUOTA แล้วสลับบัญชีถัดไปและสั่งซ้ำได้กี่ครั้ง")
        r.add_argument("--retry-nostart", type=int, default=1, help="NOSTART แล้วลองใหม่กี่ครั้ง")
        r.add_argument("--auto", action="store_true", help="อนุมัติ permission อัตโนมัติ (ยกเว้นที่ deny)")
        r.add_argument("--no-open", action="store_true", help="ไม่สั่ง desktop เปิด session ให้")
        r.set_defaults(fn=cmd_run)
    vf.set_defaults(attach="none")  # agent ที่เพิ่งติดตั้ง live server 4096 อาจยังไม่เห็น → รันแยกเป็นค่าเริ่มต้น
    inv.set_defaults(attach="none")
    vf.set_defaults(switch_on_quota=2)  # ผู้ตรวจ/ผู้สืบ: โควตาหมดย้าย provider (โมเดลเดิม) ให้เองได้ 2 ครั้ง
    inv.set_defaults(switch_on_quota=2)
    wy = sp.add_parser("why", help="งานที่รันอยู่เป็นอย่างไร: ปกติ/tool ค้าง/รอโมเดล (ไม่ระบุ id = ทุกงานที่รัน)")
    wy.add_argument("id", nargs="?", default="")
    wy.set_defaults(fn=cmd_why)
    sp.add_parser("status", help="งานที่ทำอยู่ + คิว").set_defaults(fn=cmd_status)
    li = sp.add_parser("list", help="รายการงาน")
    li.add_argument("--all", action="store_true")
    li.set_defaults(fn=cmd_list)
    lg = sp.add_parser("log", help="รายละเอียดงาน")
    lg.add_argument("id")
    lg.set_defaults(fn=cmd_log)
    ca = sp.add_parser("cancel", help="ยกเลิกงาน (รอคิวหรือกำลังทำ)")
    ca.add_argument("id")
    ca.set_defaults(fn=cmd_cancel)
    sw = sp.add_parser("switch", help="สลับบัญชีโมเดล flash-worker")
    sw.add_argument("target", nargs="?")
    sw.set_defaults(fn=cmd_switch)
    ins = sp.add_parser("install", help="ติดตั้ง /flash + flash-worker แบบ global")
    ins.add_argument("--force", action="store_true")
    ins.set_defaults(fn=cmd_install)
    ini = sp.add_parser("init", help="ตั้งค่าโปรเจกต์ใหม่ (.flash.json ตรวจ branch หลักเอง · .gitignore · แม่แบบแผน)")
    ini.add_argument("--project", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd)")
    ini.add_argument("--force", action="store_true", help="ทับช่องใน .flash.json ด้วยค่าที่ตรวจเจอ")
    ini.add_argument("--install", action="store_true", help="ติดตั้งคำสั่ง global ที่ขาดให้ด้วย (เหมือน install)")
    ini.add_argument("--commit", action="store_true", help="commit เฉพาะไฟล์ที่ init แตะ + push (ถ้าอยู่ branch หลัก)")
    ini.set_defaults(fn=cmd_init)
    pr = sp.add_parser("prune", help="ลบงานที่จบแล้ว + log ที่เก่ากว่า N วัน")
    pr.add_argument("--days", type=float, default=30)
    pr.add_argument("--dry", action="store_true", help="แค่นับ ไม่ลบ")
    pr.set_defaults(fn=cmd_prune)
    cf = sp.add_parser("config", help="ดู/ตั้งค่า (max_parallel · schedule auto|fifo · starve_min)")
    cf.add_argument("key", nargs="?")
    cf.add_argument("value", nargs="?")
    cf.set_defaults(fn=cmd_config)
    rv = sp.add_parser("review", help="ป้าย Claude กำลังตรวจ (ให้หน้าออฟฟิศแสดงผู้ตรวจ) — start/done/list")
    rv.add_argument("action", choices=["start", "done", "list"])
    rv.add_argument("plan", nargs="?", default="")
    rv.add_argument("tasks_or_result", nargs="*", help="start: งาน (T-01..T-12 หรือ T-01 T-02 ... หลายตัวได้ ใส่เครื่องหมายคำพูดหรือไม่ก็ได้) · done: pass|fail")
    rv.add_argument("--project", default="")
    rv.add_argument("--note", default="")
    rv.set_defaults(fn=cmd_review)
    rn = sp.add_parser("runnow", help="ให้งานที่รอคิวได้ช่องพิเศษทันที (รันคู่ขนาน)")
    rn.add_argument("id")
    rn.add_argument("--force", action="store_true", help="รันแม้ไฟล์ซ้อนกับงานที่กำลังทำ")
    rn.set_defaults(fn=cmd_runnow)
    go = sp.add_parser("goal", help="โหมดเป้าหมาย (/flash-goal): check ไฟล์เป้าหมาย · verify เกณฑ์ + เบรก · status")
    go.add_argument("action", choices=["check", "verify", "status"])
    go.add_argument("goal", help="ไฟล์เป้าหมาย เช่น docs/plans/GOAL_<เรื่อง>.md")
    go.add_argument("--project", default="", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd · worktree → checkout หลัก)")
    go.add_argument("--reset", action="store_true", help="check: เริ่มนับใหม่ (base/รอบ/ลายนิ้วมือเกณฑ์) — ใช้เมื่อ user ยืนยันเกณฑ์ใหม่แล้ว")
    go.set_defaults(fn=cmd_goal)
    ui = sp.add_parser("ui", help="หน้าเว็บ dashboard ในเครื่อง (127.0.0.1)")
    ui.add_argument("--port", type=int, default=4097, help="0 = สุ่มพอร์ตว่าง")
    ui.add_argument("--no-open", action="store_true", help="ไม่เปิดเบราว์เซอร์ให้")
    ui.set_defaults(fn=cmd_ui)
    a = ap.parse_args()
    return a.fn(a) if a.cmd else cmd_status(a)  # ไม่ใส่คำสั่ง = status


if __name__ == "__main__":
    sys.exit(main())

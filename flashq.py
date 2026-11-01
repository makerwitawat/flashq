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
  python flashq.py qa [ชุด...] [--cmd "คำสั่ง"] [--commit SHA] [--retry N] [--no-analyze]   นักทดสอบ: flashq รันชุดทดสอบจาก .flash.json (qa.presets) เอง ตัดสินจาก exit code จริง · ล้ม → Flash อธิบายสาเหตุ (ความเห็น ไม่ใช่คำตัดสิน)
  python flashq.py run ... --agent <ชื่อ> --title <ชื่อ> --readonly   เลือก agent/ชื่อ session/งานอ่านอย่างเดียวเอง
  python flashq.py [status] | list [--all] | log <id> | cancel <id>
  python flashq.py wait <job|แผน> [--timeout-min 480]                  รอจนงานจบแล้วพิมพ์ FLASH_RUN=... (รันใน background ของ Claude · ไม่ต้อง sleep/poll)
  python flashq.py shrink <รูป...> [--max 800]                           ย่อรูปใหญ่เป็น .tmp/shrink/<ชื่อ>.jpg ก่อนให้ Claude อ่าน (รูปใหญ่กิน token ทุก turn)
  python flashq.py switch [next|<ชื่อย่อ>]                             สลับบัญชีโมเดล flash-worker
  python flashq.py install [--force] [--hooks]                          ติดตั้ง /flash + agent (opencode) · /flash-* + flash-checker + hooks (Claude) แบบ global · --hooks = ลงทะเบียน image_guard · inbox_notify · run_guard ใน ~/.claude/settings.json
  python flashq.py init [--project <dir>] [--force] [--install] [--commit]       ตั้งค่าโปรเจกต์ใหม่ (ตรวจ branch หลัก/remote เอง → .flash.json)
  python flashq.py prune [--days 30] [--dry]                            ลบงานที่จบแล้ว + log เก่า
  python flashq.py config [max_parallel [<n>]]                          ดู/ตั้งค่า (จำนวนงานที่รันพร้อมกันได้)
  python flashq.py config schedule auto|fifo · config starve_min 120     โหมดจัดคิว · กันอดตาย (นาที)
  python flashq.py runnow <id> [--force]                                ให้งานที่รอคิวได้ช่องพิเศษทันที (คู่ขนาน)
  python flashq.py review start <แผน> [<งาน>] | done <แผน> pass|fail [--note ...] | list   ป้ายให้หน้าออฟฟิศรู้ว่า Claude กำลังตรวจ (/flash-check)
  python flashq.py ui [--port 4097] [--no-open]                         หน้าเว็บ dashboard (127.0.0.1 เท่านั้น)
  python flashq.py goal check|verify|status <GOAL.md> [--reset]          โหมดเป้าหมาย (/flash-goal): ตรวจธง · ตรวจเกณฑ์ + เบรก → GOAL=DONE|CONTINUE|STOP
  python flashq.py goal cancel <GOAL.md> --reason "เหตุ"                  user สั่งเลิกธง → GOAL=CANCELLED (verify/check ปฏิเสธจนกว่าจะเปิดใหม่)
ผลของ run: บรรทัด `FLASH_RUN=OK|FAIL|DENIED|QUOTA|TIMEOUT|BUSY|NOSTART|QUEUE_TIMEOUT` · exit 0 = OK · 2 = BUSY (--no-wait) · 3 = รอคิวเกินเวลา · อื่น 1
  DENIED = opencode ปฏิเสธสิทธิ์เอง (โหมดไม่โต้ตอบ เช่น อ่านไฟล์นอกโปรเจกต์) งานไม่ได้ทำ → บรรทัด `DENIED:` บอก path + ทางแก้ (`external_dirs` ใน .flash.json หรือ permission ใน opencode.json)
"""
import argparse
import contextlib
import ctypes
import difflib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()  # รันเป็น exe (PyInstaller/Nuitka)
APP_DIR = Path(sys.argv[0]).resolve().parent if FROZEN else Path(__file__).resolve().parent  # โฟลเดอร์ที่วาง exe
REPO = APP_DIR  # ต้นฉบับคำสั่ง/hook/แม่แบบ: ปกติ = checkout · exe = โฟลเดอร์ข้าง exe (claude/ opencode/ hooks/ templates/)
RES = Path(getattr(sys, "_MEIPASS", REPO)) if FROZEN else REPO  # ไฟล์ที่ฝังในตัว exe (ui.html, accounts.json, ไอคอน)
CLI_EXE = "flashq.exe" if os.name == "nt" else "flashq"  # exe แบบ console สำหรับคำสั่ง (flashq-gui.exe เป็นแบบหน้าต่าง พิมพ์ผลออกจอไม่ได้)


def self_argv() -> list[str]:
    """คำสั่งเรียกตัวเองเป็น subprocess (exe = ตัวมันเอง · ปกติ = python flashq.py)"""
    return [str(Path(sys.argv[0]).resolve())] if FROZEN else [sys.executable, str(REPO / "flashq.py")]


def run_cmd(quote: bool = False) -> str:
    """คำสั่งที่พิมพ์ให้ผู้ใช้/AI รัน flashq — ปกติ `python <repo>/flashq.py` · exe = path ของ flashq.exe ข้าง exe (ใส่ "" เสมอ)"""
    if FROZEN:
        return '"' + (APP_DIR / CLI_EXE).as_posix() + '"'
    return f'python "{REPO / "flashq.py"}"' if quote else f"python {REPO / 'flashq.py'}"


HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
JOBS, LOGS, LOCK = HOME / "jobs", HOME / "logs", HOME / "running.lock"
INBOX = HOME / "inbox"  # ผลงานจบรอส่งถึง Claude (hook inbox_notify.py อ่านตอนผู้ใช้พิมพ์ข้อความถัดไป)
INSTALLED = HOME / "installed.json"  # รุ่นที่ `install` ติดตั้งล่าสุด + หัวข้อ CHANGELOG (hook whatsnew.py บอก session ที่เปิดค้างว่ามีของใหม่)
REVIEWS = HOME / "reviews"   # ป้าย "Claude กำลังตรวจ" ที่ /flash-check ตั้ง (ให้หน้าออฟฟิศแสดงผู้ตรวจ) — ไม่ใช่งานในคิว
REVIEW_TTL_MIN = 90          # ป้ายที่ค้างเกินนี้ถือว่าถูกทิ้ง (session ตาย/ลืม done)
CONFIG, RUN_NOW = HOME / "config.json", HOME / "run_now"
CONFIG_DEFAULTS = {"max_parallel": 1, "schedule": "fifo", "starve_min": 120, "dead_clear_hours": 24}  # ไม่มีไฟล์ config = พฤติกรรมเดิม (ทีละงาน FIFO) · dead_clear_hours = ป้าย "process ตาย" หายเองเมื่อพ้นกี่ชั่วโมง (0 = ไม่หายเอง)
SCHEDULES = ("auto", "fifo")
MAX_SLOTS = 8          # เพดานของ max_parallel
VERSION = "0.2.3"      # รุ่นของโปรแกรม — ต้องตรงกับ tag ของ release (แสดงบนแถบชื่อหน้าต่าง/หน้าเว็บ) · แก้ตอนออกรุ่นใหม่
QUEUE_VERSION = 2      # job ที่มี qv>=2 = โค้ดที่รองรับหลายช่อง + สัญญาณ run_now
SLOT_RE = re.compile(r"^running(?:-(\d+))?\.lock$")
STALE_LOCK_HOURS = 24  # ล็อกที่ไม่มี pid_start + เก่ากว่ากี่ชั่วโมง + งานจบแล้ว = ล็อกค้าง เก็บได้
OC_CONFIG = Path(os.environ.get("FLASHQ_OPENCODE_CONFIG") or (Path.home() / ".config" / "opencode" / "opencode.json"))
LIVE_URL = os.environ.get("FLASHQ_LIVE_URL") or "http://127.0.0.1:4096"
# รอ sessionID ใน log นานสุดกี่วิ ก่อนนับเป็น NOSTART (เทสต์ตั้งสั้นได้ — ตั้งแล้วใช้ค่าเดียวทุกรอบ)
# วัดจาก log จริง 180 งาน (2026-10-23): เริ่มได้ใน p50 6 วิ · p90 10 วิ · p99 112 วิ · สูงสุด 145 วิ → รอบแรกรอ 60 วิ แล้วฆ่า-ลองใหม่ดีกว่านั่งรอ 3 นาที (รอบถัดไปมักเริ่มได้ใน 6 วิ) · รอบลองใหม่ให้เวลามากขึ้นเผื่อเครื่องหน่วงจริง
START_LIMIT_FIRST_SEC = int(os.environ.get("FLASHQ_START_LIMIT_SEC") or 60)
START_LIMIT_SEC = int(os.environ.get("FLASHQ_START_LIMIT_SEC") or 120)
AGENT_KINDS = {"verify": "flash-verifier", "investigate": "flash-investigator"}  # งานอ่านอย่างเดียวที่ส่ง prompt ตรงให้ agent (ไม่ผ่าน /flash)
SUBAGENT_RE = re.compile(r"is a subagent, not a primary agent|not found\. Falling back to default agent", re.I)
QUOTA_RE = re.compile(r"\b(429|402)\b|rate.?limit|quota|insufficient|balance", re.I)
# opencode โหมดไม่โต้ตอบ (`opencode run`) ตอบ "ไม่อนุญาต" ให้เองเมื่อกฎเป็น ask → stderr: `permission requested: <ชนิด> (<path>); auto-rejecting`
PERM_REQ_RE = re.compile(r"permission requested:\s*([\w.-]+)\s*\((.*?)\)\s*;\s*auto-reject", re.I)
# tool error ที่ตามมา (subagent ล้มเพราะถูกปฏิเสธ · ข้อความไทย/อังกฤษของ opencode)
PERM_DENY_RE = re.compile(r"rejected permission|ปฏิเสธสิทธิ์|permission (?:was )?denied", re.I)
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
    "model_wait_min": 4,  # server ยืนยันว่าไม่มี tool ใดรันอยู่ (= รอโมเดลตอบอย่างเดียว) แล้ว log เงียบเกินนี้ (นาที) = ตัดสินค้างเลย ไม่รอขั้นต่ำ stall_floor_min · ต้องต่อ server (--attach live) ถึงยืนยันได้ (0 = ปิด)
    "agent_timeout_min": 30,  # ผู้ตรวจ/ผู้สืบ (verify/investigate) สั้นกว่างานทำจริง — กัน agent วนจนกินช่องคิว
    "doc_timeout_min": 30,  # ช่างเอกสาร (flashq doc): เวลาสูงสุดต่อ 1 รัน · ทับรายชุดได้ด้วย timeout_min ใน doc.presets.<ชื่อ>
    "qa_timeout_min": 30,  # นักทดสอบ (flashq qa): เวลาสูงสุดต่อ 1 ชุดทดสอบ · ทับรายชุดได้ด้วย timeout_min ใน qa.presets.<ชื่อ> · เกิน = ฆ่าทั้งต้นแล้วรายงาน TIMEOUT
    "variants": {"investigate": "high", "verify": "low", "qa": "high"},  # ระดับความคิด (opencode --variant) ตามชนิดงาน · ไม่มีชนิดนั้น/ค่าว่าง = ไม่ส่ง (ใช้ค่าเริ่มต้นของ provider) · ทับได้ใน .flash.json / config.json · --variant ใน CLI ชนะทุกอย่าง
    "shell_idle_min": 4,  # ตัวเฝ้า shell: คำสั่งที่ทั้งชุดโปรเซส CPU+I/O ไม่ขยับเลยเกินนี้ (นาที) = ค้าง → ฆ่าเฉพาะคำสั่งนั้น (0 = ปิด)
}
# แยก process ออกจาก console ของผู้เรียก แต่ "ต้องมี console ซ่อนของตัวเอง" (CREATE_NO_WINDOW) · ห้ามใส่ DETACHED_PROCESS: ไม่มี console เลย →
# ลูกที่เป็นโปรแกรม console (git · python · taskkill · opencode) ของ process นั้นแต่ละตัวจะเปิดหน้าต่างดำเด้งขึ้นจอผู้ใช้
HIDDEN_DETACH_FLAGS = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0
GOAL_UI_CMD_TIMEOUT_SEC = 60  # ปุ่ม ✅/❌ และยกเลิกธงบนหน้าเว็บ: คำสั่ง goal ลูกเกินเวลา = ฆ่า + ตอบข้อความกลับ (ไม่ปล่อยให้ handler ล้มเงียบ)
PUSH_TIMEOUT_SEC = float(os.environ.get("FLASHQ_PUSH_TIMEOUT_SEC") or 120)  # git push ของ `flashq init --commit` (ห้ามค้างตลอดไปเมื่อเครือข่าย/credential มีปัญหา)
DESKTOP_OPEN_TIMEOUT_SEC = 30  # สั่ง opencode desktop เปิด session — desktop ไม่ตอบ = ข้าม
SHELL_POLL_SEC = float(os.environ.get("FLASHQ_SHELL_POLL_SEC") or 30)  # ถามสถานะ tool + วัดโปรเซสถี่แค่ไหนตอน log เงียบ
SHELL_CONFIRM = 3  # หา shell ไม่เจอแต่ลูกยังอยู่ ต้องเห็นซ้ำกี่รอบ (รอบละ SHELL_POLL_SEC) ก่อนฆ่า
SHELL_NAMES = {"powershell.exe", "pwsh.exe", "cmd.exe", "bash.exe", "sh.exe"}
SHELL_WORDS = {"cmd", "start", "powershell", "pwsh", "bash", "exe", "nologo", "noprofile", "noninteractive", "command", "null", "out-null",
               "executionpolicy", "bypass", "-file", "file", "-command", "-noprofile", "-executionpolicy"}


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
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            pass
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def run_timeout(cmd: list[str], timeout: float = 60, text: bool = True, env: dict | None = None, cwd: str | None = None) -> subprocess.CompletedProcess:
    """subprocess.run แบบมีเวลาจำกัดและไม่ถามรหัส: เกินเวลา = ฆ่าทั้งต้น (git push/fetch ติดเครือข่ายหรือรอรหัสผ่านจะค้างตลอดไป) แล้วคืน returncode 124
    เปิดโปรแกรมไม่ได้ = returncode 127 · ไม่โยน exception เพื่อให้ผู้เรียกจัดการตามรหัสคืนเหมือน subprocess.run(check=False)"""
    kw = {"encoding": "utf-8", "errors": "replace"} if text else {}
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env, cwd=cwd, **kw)
    except OSError as e:
        return subprocess.CompletedProcess(cmd, 127, "" if text else b"", str(e) if text else str(e).encode("utf-8", "replace"))
    try:
        out, err = p.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd, p.returncode, out, err)
    except subprocess.TimeoutExpired:
        kill_tree(p.pid)
        try:
            out, err = p.communicate(timeout=5)  # ลูกที่สืบทอด pipe ไปค้างอยู่ได้ → ไม่รอเกิน 5 วิ
        except subprocess.TimeoutExpired:
            out, err = "" if text else b"", "" if text else b""
        note = f"หมดเวลา {timeout:g} วิ → ฆ่าแล้ว"
        return subprocess.CompletedProcess(cmd, 124, out, (err or ("" if text else b"")) + (note if text else note.encode("utf-8")))


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}_{threading.get_ident()}.tmp")  # + thread: หน้า ui เขียนไฟล์เดียวกันพร้อมกันได้หลาย thread
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    replace_file(tmp, path)


def replace_file(tmp: Path, path: Path, wait_sec: float = 5) -> None:
    """os.replace ที่ทนผู้อ่านพร้อมกัน — Windows ปฏิเสธ (WinError 5/32) ถ้ามีใครเปิดอ่านปลายทางอยู่ชั่วขณะ (หน้าเว็บ poll · แอนตี้ไวรัส) → ลองใหม่ถี่ ๆ
    ไม่สำเร็จภายใน wait_sec = ลบไฟล์ชั่วคราวแล้วโยน error เดิม"""
    t0, delay = time.time(), 0.005
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if time.time() - t0 >= wait_sec:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.2)


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
        return [sys.executable, alt] if alt.endswith(".py") else [resolve_shim(alt)]
    exe = shutil.which("opencode")
    return [resolve_shim(exe)] if exe else []


SHIM_EXE_RE = re.compile(r'"%~?dp0%?\\?([^"]+?\.exe)"', re.I)


def resolve_shim(exe: str) -> str:
    """ตัวห่อ npm (opencode.CMD) แค่เรียก opencode.exe ต่อ — ข้ามไปเรียก exe ตรง ๆ เพราะ cmd.exe ตัดบรรทัดคำสั่งตรงขึ้นบรรทัดใหม่
    และตีเครื่องหมาย < > & | % เป็นคำสั่งของมัน (เหตุจริง 2026-10-21: บรีฟหลายบรรทัดทำให้ opencode ไม่ได้ข้อความงาน → NOSTART) · หา exe ไม่เจอ = คืนของเดิม"""
    if not exe.lower().endswith((".cmd", ".bat")):
        return exe
    try:
        text = Path(exe).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return exe
    m = SHIM_EXE_RE.search(text)
    real = Path(exe).parent / m.group(1).replace("\\", os.sep) if m else None
    return str(real) if real and real.is_file() else exe


UNSAFE_CMD_CHARS = set('\r\n"<>&|%^!')


def cmd_shim_unsafe(exe: list[str], *texts: str) -> str:
    """ยังต้องผ่าน .cmd/.bat (หา exe จริงไม่เจอ) แล้วข้อความมีอักขระที่ cmd.exe ตีความเอง → คืนอักขระนั้น (ไม่มี = ปลอดภัย)"""
    if os.name != "nt" or not exe or not exe[-1].lower().endswith((".cmd", ".bat")):
        return ""
    bad = sorted({c for t in texts for c in t if c in UNSAFE_CMD_CHARS})
    return " ".join(repr(c) for c in bad)


def one_line(text: str, limit: int) -> str:
    """ชื่อ session ต้องบรรทัดเดียว (ขึ้นบรรทัดใหม่/ช่องว่างซ้อน → ช่องว่างเดียว) แล้วตัดความยาว"""
    return " ".join(str(text).split())[:limit]


# ---------- โปรเจกต์ ----------
def project_root(start: Path) -> tuple[Path, bool]:
    """รากของ checkout หลัก (worktree → checkout หลัก) · ไม่ใช่ git = โฟลเดอร์นั้นเอง"""
    r = run_timeout(["git", "-C", str(start), "rev-parse", "--path-format=absolute", "--git-common-dir"], 30)
    if r.returncode != 0:
        return start.resolve(), False
    common = Path(r.stdout.strip())
    if common.name != ".git":  # .git แยกที่ (--separate-git-dir / submodule) → parent ของมันไม่ใช่รากโปรเจกต์
        top = run_timeout(["git", "-C", str(start), "rev-parse", "--path-format=absolute", "--show-toplevel", "--absolute-git-dir"], 30).stdout.splitlines()
        if len(top) >= 2 and top[0].strip() and Path(top[1].strip()) == common:  # ไม่ใช่ linked worktree → toplevel คือราก
            return Path(top[0].strip()), True
    return common.parent, True


def _git(root: Path, *args: str, timeout: float = 60) -> str:
    r = run_timeout(["git", "-C", str(root), *args], timeout)
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


VARIANT_RE = re.compile(r"^[A-Za-z0-9][\w.-]{0,31}$")


def variant_for(kind: str, cli: str | None, root: Path) -> str:
    """ระดับความคิดของงานชนิดนี้ (work/verify/investigate/test) · ลำดับ: --variant ใน CLI > "variants" ใน .flash.json > config.json > DEFAULTS
    ชนิดที่ไม่มีในตาราง = ไม่ส่ง (provider ใช้ค่าเริ่มต้น) · ใส่ "" หรือ "none" ในชั้นที่สูงกว่า = ปิดค่าของชั้นล่าง · ค่าที่หน้าตาไม่ใช่ชื่อ variant = ข้าม"""
    if cli:
        return cli.strip()
    for src in (read_json(root / ".flash.json"), read_config(), DEFAULTS):
        table = src.get("variants")
        if isinstance(table, dict) and kind in table:
            v = str(table[kind] or "").strip()
            if v.lower() in ("", "none", "default"):
                return ""
            if VARIANT_RE.match(v):
                return v
            print(f"คำเตือน: variants.{kind} = {v!r} ไม่ใช่ชื่อ variant → ข้าม", file=sys.stderr)
    return ""


# ---------- สิทธิ์นอกโปรเจกต์ (opencode permission.external_directory) ----------
def _slash(s: str) -> str:
    return s.replace("\\", "/")


def _native(s: str) -> str:
    """รูปแบบ path ที่ opencode รายงานบนเครื่องนี้ (Windows = \\) — ใช้ในข้อความแนะนำให้วางลง opencode.json ได้ตรงตัว"""
    return s.replace("/", "\\") if os.name == "nt" else s


def external_dirs(cfg: dict) -> list[str]:
    """`external_dirs` ใน .flash.json: โฟลเดอร์นอกโปรเจกต์ที่งานต้องอ่าน/แก้ · ไม่มี * = เติม /* ให้ (opencode ขอสิทธิ์เป็น <โฟลเดอร์>\\*)"""
    out = []
    for d in cfg.get("external_dirs") or []:
        d = _slash(str(d).strip())
        if d:
            out.append(d if "*" in d else d.rstrip("/") + "/*")
    return out


def perm_allows(perm, path: str) -> bool:
    """opencode ตัดสินสิทธิ์: ช่องเป็น "allow"/"ask"/"deny" หรือ {รูปแบบ: การกระทำ} · * = ตัวอักษรใด ๆ (รวมตัวคั่นโฟลเดอร์)
    เลือกกฎที่ตรงและเจาะจงสุด (ยาวสุดเมื่อตัด * ออก · เท่ากัน = อันหลัง) · เทียบโดยไม่สน \\ กับ / (ใส่ได้ทั้งสองแบบ)"""
    if isinstance(perm, str):
        return perm == "allow"
    if not isinstance(perm, dict):
        return False
    best = None  # (ความเจาะจง, ลำดับ, การกระทำ)
    for i, (pat, act) in enumerate(perm.items()):
        rx = "^" + ".*".join(re.escape(p).replace(r"\?", ".") for p in _slash(str(pat)).split("*")) + "$"
        if re.match(rx, _slash(path), re.S):
            key = (len(str(pat).replace("*", "")), i)
            if best is None or key > best[:2]:
                best = (*key, act)
    return bool(best) and best[2] == "allow"


def perm_config_content(dirs: list[str]) -> str:
    """ค่า OPENCODE_CONFIG_CONTENT (opencode รวมเข้ากับ config ของผู้ใช้ตอนเริ่ม · ไม่แตะไฟล์ opencode.json) — ใส่ทั้ง / และ \\ บน Windows กันตีความต่างกัน"""
    rules = {}
    for d in dirs:
        rules[_slash(d)] = "allow"
        if os.name == "nt":
            rules[d.replace("/", "\\")] = "allow"
    return json.dumps({"permission": {"external_directory": rules}}, ensure_ascii=False)


def known_external_dirs(root: Path, extra: list[str] = ()) -> list[str]:
    """external_dirs ของทุกโปรเจกต์ที่เคยส่งงาน + ของโปรเจกต์นี้ — ให้ server สด (เปิดครั้งเดียว ใช้ร่วมทุกโปรเจกต์) รู้สิทธิ์ตั้งแต่เปิด"""
    out = list(extra)
    seen = {str(root)}
    for j in jobs():
        p = j.get("project") or ""
        if p and p not in seen:
            seen.add(p)
            out += external_dirs(read_json(Path(p) / ".flash.json"))
    return list(dict.fromkeys(out))


def server_permission(attach: str, root: Path):
    """ช่อง permission.external_directory ตามที่ server opencode (--attach) ใช้จริง — server โหลด config ตอนเปิด จึงไม่เห็น env ของงาน · None = ถามไม่ได้"""
    import urllib.parse
    import urllib.request
    try:
        raw = urllib.request.urlopen(f"{attach.rstrip('/')}/config?" + urllib.parse.urlencode({"directory": str(root)}), timeout=3).read()
        return (json.loads(raw).get("permission") or {}).get("external_directory")
    except Exception:
        return None


def _perm_pairs(dirs: list[str]) -> str:
    return ", ".join(json.dumps({_native(d): "allow"}, ensure_ascii=False)[1:-1] for d in dirs)


def perm_missing_on_server(dirs: list[str], attach: str, root: Path) -> list[str]:
    """external_dirs ที่ server opencode (--attach) ยังไม่อนุญาต · ถาม server ไม่ได้ = ใช้ opencode.json แทน · ไม่ใช่ server (attach ว่าง) = []"""
    if not dirs or not attach.startswith("http"):
        return []
    perm = (read_json(OC_CONFIG).get("permission") or {})
    file_perm = perm.get("external_directory") if isinstance(perm, dict) else None
    sp = server_permission(attach, root)
    return [d for d in dirs if not perm_allows(sp if sp is not None else file_perm, d)]


def perm_precheck(dirs: list[str], attach: str, root: Path) -> list[str]:
    """ก่อนรัน: opencode.json อ่านได้ไหม · external_dirs ถูกอนุญาตแล้วหรือยัง (ไฟล์ของผู้ใช้ / server สด) → บรรทัดแจ้ง/เตือน"""
    out = []
    oc = read_json(OC_CONFIG)
    if not oc and OC_CONFIG.is_file():
        out.append(f"WARN: อ่าน {OC_CONFIG} ไม่ได้ (JSON เสีย? เช่นลืมคอมมา) → opencode จะเปิดไม่ขึ้นหรือไม่ใช้สิทธิ์ที่ตั้งไว้ — ตรวจด้วย `opencode debug config`")
    if not dirs:
        return out
    file_perm = (oc.get("permission") or {}).get("external_directory") if isinstance(oc.get("permission"), dict) else None
    miss_file = [d for d in dirs if not perm_allows(file_perm, d)]
    if attach.startswith("http"):
        miss = perm_missing_on_server(dirs, attach, root)
        if miss:
            pidf = HOME / "live_server.pid"
            pid = pidf.read_text(encoding="utf-8", errors="replace").strip() if pidf.exists() else "?"
            out.append(f"WARN: server opencode ({attach}) ยังไม่อนุญาต external_dirs: {', '.join(miss)} → งานที่แตะโฟลเดอร์นี้จะถูกปฏิเสธสิทธิ์ (DENIED) "
                       f"· server โหลด config ตอนเปิด ไม่เห็นสิทธิ์ที่ flashq ส่งต่อรอบ · แก้ทางใดทางหนึ่ง: ปิด server แล้วสั่งใหม่ (taskkill /PID {pid} /T /F — flashq เปิดใหม่พร้อมสิทธิ์จาก external_dirs) "
                       f"· เพิ่มใน {OC_CONFIG} ช่อง permission.external_directory: {_perm_pairs(miss)} แล้วรีสตาร์ต server · หรือส่งด้วย --attach none")
        else:
            out.append(f"PERM: server opencode อนุญาต external_dirs แล้ว: {', '.join(dirs)}")
    else:
        out.append(f"PERM: ส่งสิทธิ์ external_dirs ให้ opencode รอบนี้ผ่าน OPENCODE_CONFIG_CONTENT: {', '.join(dirs)}"
                   + (f" · {OC_CONFIG} ยังไม่มี allow ของ {', '.join(miss_file)} (ใส่ถาวรได้ที่ permission.external_directory: {_perm_pairs(miss_file)})" if miss_file else ""))
    return out


def perm_fix_lines(items: list[dict], partial: bool = False) -> list[str]:
    """ข้อความสิทธิ์ที่ opencode ปฏิเสธ + ทางแก้ 2 ทาง (ใช้ร่วม run / wait / หน้าเว็บ) · partial = งานสำเร็จบางส่วน (คง OK แต่เตือน)"""
    n = len(items)
    out = [(f"WARN: opencode ปฏิเสธสิทธิ์ {n} รายการระหว่างทำงาน แต่มีงานสำเร็จบางส่วน (commit/DONE) → ตรวจว่างานไหนขาด:" if partial
            else f"DENIED: opencode ปฏิเสธสิทธิ์ {n} รายการ (รันแบบไม่โต้ตอบ = ตอบ \"ไม่อนุญาต\" ให้เองทันที) — งานไม่ได้ทำ ไม่ต้องไล่หา commit:")]
    out += [f"  - {it.get('kind') or 'tool'}: {it.get('path') or '?'}" for it in items[:8]]
    ext = list(dict.fromkeys(it["path"] for it in items if it.get("kind") == "external_directory" and it.get("path")))
    if ext:
        out.append("ทางแก้ (เลือกทางเดียว แล้วส่งงานใหม่):")
        out.append(f"  1) .flash.json ของโปรเจกต์ เพิ่ม \"external_dirs\": {json.dumps([_slash(p) for p in ext], ensure_ascii=False)} → flashq ส่งสิทธิ์ให้ opencode เองทุกครั้งที่รัน (ย่อให้กว้างขึ้นได้ เช่น \"D:/lib/*\")")
        out.append(f"  2) {OC_CONFIG} ช่อง permission.external_directory เพิ่ม {_perm_pairs(ext)} (ถาวร · ใช้กับ opencode ที่เปิดเองด้วย)")
    else:
        kinds = sorted({it.get("kind") or "tool" for it in items})
        out.append(f"ทางแก้: {OC_CONFIG} ช่อง permission ตั้ง {', '.join(json.dumps({k: 'allow'})[1:-1] for k in kinds)} แล้วส่งงานใหม่ (หรือรันด้วย --auto ถ้ายอมรับความเสี่ยง)")
    return out


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


CITE_RE = re.compile(r"(?<![\w/.\\-])((?:[A-Za-z]:)?[\w./\\-]*[\w-]\.[A-Za-z0-9]{1,6}):(\d+)(?:[-–](\d+))?")
CITE_HOST_RE = re.compile(r"\d+(?:\.\d+){1,3}")  # 127.0.0.1:8219 ไม่ใช่ไฟล์:บรรทัด
CITE_ELLIPSIS_RE = re.compile(r"\.{3}|…")
CITE_CLAUSE_RE = re.compile(r"(?:`|\s|\()?:\d+(?:[-–,]\d+)*|\s·\s|\s→\s")  # ขอบประเด็น: `:585` (เลขบรรทัดของที่อื่น) · " · " · " → "
CITE_CODEISH_RE = re.compile(r"[()\[\]{}=<>/\\.:;'\"+*|]")
CITE_NEAR = 40 # ข้อความที่คัดต้องอยู่ห่างจาก citation ไม่เกินกี่ตัวอักษร (ไกลกว่านี้มักเป็นของอีกประโยค)
CITE_NEG_RE = re.compile(r"ไม่|ขาด|หาย")  # "ไม่มีคีย์ `source`" = อ้างว่าบรรทัดนี้ไม่มีสิ่งนั้น ไม่ใช่การคัดโค้ด


def _cite_file(rel: str, root: Path, tracked: list[str], anchors: list[str]) -> tuple[Path | None, str]:
    """หาไฟล์ที่ citation หมายถึง → (ไฟล์, "") หรือ (None, เหตุผล) · ชื่อย่อ (`viewer.py` = `rig_std_viewer.py`) ใช้ได้เมื่อชี้ไฟล์เดียว
    ไฟล์ชื่อซ้ำหลายที่ → เลือกอันที่อยู่ใต้โฟลเดอร์เดียวกับ citation อื่นที่ระบุ path ครบในรายงาน (anchors) · ยังเลือกไม่ได้ = กำกวม ไม่เดา"""
    f = root / rel
    try:
        if f.resolve().is_relative_to(root) and f.is_file():
            return f, ""
    except OSError:
        pass
    base = rel.rsplit("/", 1)[-1]
    exact = [t for t in tracked if t == rel or t.endswith("/" + rel)]
    loose = [] if "/" in rel else [t for t in tracked if t not in exact and t.rsplit("/", 1)[-1].endswith(("_" + base, "-" + base))]
    near = lambda pool: [t for t in pool if any(t.startswith(a + "/") for a in anchors)]
    near_exact, near_all = near(exact), near(exact + loose)
    if len(near_exact) == 1:
        pick = near_exact
    elif len(near_all) == 1:
        pick = near_all
    elif not near_all and len(exact) == 1:
        pick = exact
    elif not near_all and not exact and len(loose) == 1:
        pick = loose
    else:
        pick = []
    if pick:
        return root / pick[0], ""
    pool = exact + loose
    if not pool:
        return None, "ไม่พบไฟล์"
    return None, f"ชื่อไฟล์กำกวม (ตรง {len(pool)} ไฟล์ เช่น {', '.join(pool[:2])}) — ต้องระบุ path เต็ม"


def _cite_snippet_ok(snippet: str, window: str) -> bool | None:
    """ข้อความที่คัดอยู่ในหน้าต่างบรรทัดหรือไม่ · มี `...`/`…` = ย่อกลางข้อความ → ทุกท่อนที่เหลือต้องอยู่ · ไม่มีท่อนที่ใช้เทียบได้ = None (ไม่นับเป็นข้อความคัด)"""
    parts = [re.sub(r"\s+", " ", p.strip()) for p in CITE_ELLIPSIS_RE.split(snippet)]
    parts = [p for p in parts if len(p) >= 3]
    if not parts:
        return None
    if all(p in window for p in parts):
        return True
    # คัดไม่ตรงตัวแต่ถูกคำ (เช่น `ValueError: ข้อความ` จากโค้ด ValueError('ข้อความ…')) → มีคำ ≥3 ตัวอักษรอย่างน้อย 2 คำและทุกคำต้องอยู่ในหน้าต่าง
    words = [w for p in parts for w in re.split(r"[\s()\[\]{}:;,='\"+*<>|&!?/\\.\-]+", p) if len(w) >= 3]
    return len(words) >= 2 and all(w in window for w in words)  # คำเดียว (เช่น `int z = 5;` → int) หลวมเกินไป ต้องตรงตัวเท่านั้น


def check_citations(text: str, root: Path) -> dict:
    """ตรวจ `file:line` ที่ผู้สืบอ้างในรายงาน: ไฟล์มีจริงใต้โปรเจกต์ · เลขบรรทัดไม่เกินไฟล์ · โค้ดที่คัดไว้ใน `...` หลัง citation (ก่อน citation ถัดไป/จบบรรทัด) อยู่ในบรรทัดนั้น (±3)
    ตรวจได้แค่ "อ้างตรงโค้ดจริง" ไม่ได้ตรวจว่าเป็นต้นตอจริง (ยังเป็นหน้าที่ของ Claude)"""
    root = root.resolve()
    cites = [m for m in CITE_RE.finditer(text) if not CITE_HOST_RE.fullmatch(m.group(1))]
    tracked: list[str] | None = None
    anchors: list[str] = []  # โฟลเดอร์ของไฟล์ที่ citation ระบุ path ถูกตรงๆ → ใช้ตัดสินชื่อย่อที่ซ้ำ
    for m in cites:
        f = root / m.group(1).replace("\\", "/")
        try:
            if f.resolve().is_relative_to(root) and f.is_file():
                d = f.resolve().parent.relative_to(root).as_posix()
                if d != "." and d not in anchors:
                    anchors.append(d)
        except OSError:
            pass
    ok, code, bad, seen = 0, 0, [], set()
    for i, m in enumerate(cites):
        rel, line = m.group(1).replace("\\", "/"), int(m.group(2))
        if (rel, line) in seen:
            continue
        seen.add((rel, line))
        if tracked is None:
            tracked = _git(root, "ls-files").splitlines()
        f, why = _cite_file(rel, root, tracked, anchors)
        if f is None or not f.is_file():
            bad.append(f"{rel}:{line} — {why or 'ไม่พบไฟล์'}")
            continue
        try:
            lines = f.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            bad.append(f"{rel}:{line} — อ่านไฟล์ไม่ได้")
            continue
        if not 1 <= line <= len(lines):
            bad.append(f"{rel}:{line} — เลขบรรทัดเกินไฟล์ (มี {len(lines)} บรรทัด)")
            continue
        eol = text.find("\n", m.end())
        region = text[m.end():min(len(text) if eol < 0 else eol, cites[i + 1].start() if i + 1 < len(cites) else len(text))]
        if m.start() and text[m.start() - 1] == "`" and "`" in region:  # citation อยู่ใน code span → backtick แรกหลังนี้คือตัวปิด (ไม่ใช่ตัวเปิดของข้อความคัด)
            region = region[region.index("`") + 1:]
        last = max(line, int(m.group(3) or 0))  # ช่วง `a.py:48-53` → หน้าต่างครอบถึงบรรทัดท้ายช่วง
        window = re.sub(r"\s+", " ", " ".join(lines[max(0, line - 4):last + 3]))
        cut = CITE_CLAUSE_RE.search(region)  # ข้อความหลัง · / → / `:123` เป็นของประเด็นอื่น ไม่ใช่ของ citation นี้
        region = region[:cut.start()] if cut else region
        verdicts, far = [], []
        for sp in re.finditer(r"`([^`]*)`", region):  # แยกทุก code span (สั้นก็นับ) กันคู่ backtick เหลื่อม
            x = sp.group(1).strip()
            if len(x) < 4 or x.endswith(("()", "/")) or CITE_NEG_RE.search(region[max(0, sp.start() - 14):sp.start()]):
                continue
            if sp.start() > CITE_NEAR:
                if CITE_CODEISH_RE.search(x):  # คำเดี่ยวไกล ๆ (`mesh`) มักเป็นคำพูดถึงของอื่น ไม่ใช่โค้ดที่คัด → เอาเฉพาะที่หน้าตาเป็นโค้ด/path
                    far.append(x)
            else:
                verdicts.append((x, _cite_snippet_ok(x, window)))
        verdicts = [(x, v) for x, v in verdicts if v is not None]
        miss = [x for x, v in verdicts if not v]
        if verdicts and len(miss) == len(verdicts):
            bad.append(f"{rel}:{line} — ข้อความที่คัดไว้ไม่อยู่ในบรรทัดนี้ (±3): `{miss[0][:60]}`")
            continue
        if not verdicts and far:  # ไม่มีข้อความติด citation แต่มีที่ห่างออกไปในประโยคเดียวกัน → เทียบทั้งไฟล์ (เทียบ ±3 ไม่ได้ เพราะอาจเป็นของอีกจุด) · ไม่มีในไฟล์เลย = ผิดแน่
            whole = re.sub(r"\s+", " ", " ".join(lines))
            fv = [(x, v) for x in far for v in [_cite_snippet_ok(x, whole)] if v is not None]
            if fv and not any(v for _, v in fv):
                bad.append(f"{rel}:{line} — ข้อความที่คัดไว้ไม่มีในไฟล์นี้เลย: `{fv[0][0][:60]}`")
                continue
        ok += 1
        code += 1 if verdicts else 0  # ตรงถึงตัวโค้ด (มีข้อความคัดและตรง) ต่างจากตรงแค่ไฟล์/เลขบรรทัด
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
    if key == "dead_clear_hours":
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "dead_clear_hours ต้องเป็นตัวเลข (ชั่วโมง)", ""
        if not 0 <= v <= 24 * 365:
            return "dead_clear_hours ต้องอยู่ระหว่าง 0-8760 ชั่วโมง (0 = ไม่หายเอง)", ""
        cfg["dead_clear_hours"] = v
        write_json(CONFIG, cfg)
        return "", (f"ตั้งป้ายงานตายหายเองเมื่อพ้น {v:g} ชั่วโมง แล้ว" if v else "ปิดการล้างป้ายงานตายอัตโนมัติแล้ว")
    if key == "open_session":
        v = str(value if value is not None else "").lower()
        if v not in ("on", "off", "true", "false", "1", "0", "auto"):
            return "open_session ต้องเป็น on | off | auto", ""
        if v == "auto":  # ล้างค่า → ตามผู้สั่ง (run --detach = ไม่เปิด · อื่น ๆ เปิด)
            cfg.pop("open_session", None)
            write_json(CONFIG, cfg)
            return "", "open_session = auto — งานที่ส่งด้วย run --detach (เช่น จาก opencode) ไม่เปิดหน้าต่าง session · งานอื่นเปิดตามปกติ"
        cfg["open_session"] = v in ("on", "true", "1")
        write_json(CONFIG, cfg)
        return "", ("สั่ง opencode desktop เปิดหน้าต่าง session ตอนงานเริ่มแล้ว" if cfg["open_session"] else "ปิดการเปิดหน้าต่าง session อัตโนมัติแล้ว (งานยังรันตามปกติ ดูได้ที่ flashq ui)")
    return f"ไม่รู้จัก '{key}' — ใช้ได้: max_parallel, schedule, starve_min, dead_clear_hours, open_session", ""


def slot_path(n: int) -> Path:
    return LOCK if n == 1 else HOME / f"running-{n}.lock"


def slot_files() -> list[tuple[int, Path]]:
    out = []
    for f in HOME.glob("running*.lock"):
        m = SLOT_RE.match(f.name)
        if m:
            out.append((int(m.group(1) or 1), f))
    return sorted(out)


def lock_expired(held: dict) -> bool:
    """ล็อกค้าง: ไม่มี pid_start + เก่าเกิน STALE_LOCK_HOURS + งานจบแล้ว (ไม่ใช่ queued/running)"""
    if held.get("pid_start"):
        return False
    age = _secs(held.get("since", ""))
    if age is None or age <= STALE_LOCK_HOURS * 3600:
        return False
    return read_json(JOBS / f"{held.get('id', '')}.json").get("status") not in ("queued", "running")


def clear_stale_lock() -> None:
    """ลบช่องที่ process เจ้าของตายแล้ว (ทุกช่อง)"""
    for _, f in slot_files():
        held = read_json(f)
        if held and pid_alive(held.get("pid", 0), held.get("pid_start", 0)) and not lock_expired(held):
            continue
        try:
            if not held and time.time() - f.stat().st_mtime < 5:  # เพิ่งสร้าง (O_EXCL แล้วกำลังเขียน) — ยังไม่ใช่ล็อกตาย
                continue
        except OSError:
            continue
        if read_json(f) == held:  # ยังเป็นล็อกเดิมที่ตายแล้ว
            if held and held.get("id"):  # เจ้าของตาย → ลูก opencode ที่รอดต้องไม่ถือไฟล์งานต่อ (ไม่งั้นแก้ซ้อนกับงานที่ได้ช่องต่อไป)
                oj = read_json(JOBS / f"{held['id']}.json")
                if oj.get("status") in ("queued", "running"):
                    reap_orphan(oj, abort=oj.get("status") == "running")
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
                       "extra": extra, "project": job.get("project", "")}, f, ensure_ascii=False)
        return n
    return 0


def acquire(job: dict, wait_min: float, no_wait: bool) -> str:
    """คืน "ok" | "busy" | "timeout" · FIFO ตาม created ของงานที่ยังมีชีวิต
    ได้ช่องเมื่อ ไม่มีงานรอก่อนหน้า + ช่องที่ใช้ < max_parallel · หรือมีสัญญาณ run_now (ช่องพิเศษ เกิน max_parallel ได้)"""
    t0, last, queued_hint = time.time(), None, False
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
            if can and job.get("plan"):
                for r in jobs():
                    if live_state(r) != "running" or r["id"] == job["id"] or not r.get("plan"):
                        continue
                    c = conflict_reason(job, r, job_info)
                    if c:
                        can = False
                        reason = f"ชนกับ {r['id']}: {c}"
                        break
        if boost or can:
            forced = boost and not can  # ผู้ใช้สั่งรันเลยข้ามตัวจัดคิว (รวมธง flashq-parallel: no / ไฟล์ซ้อน) → บันทึกไว้แยกจากบั๊กตัวจัดคิว
            n = take_slot(job, extra=forced or (boost and (bool(ahead) or len(held) >= limit)))
            if n:
                flag.unlink(missing_ok=True)
                job["slot"] = n
                if forced:
                    job["forced"] = now()
                return "ok"
            time.sleep(0.5)
            continue
        ids = ", ".join(h.get("id", "?") for h in held) or "-"
        ids_named = ", ".join(h.get("id", "?") + (f" ({Path(h['project']).name})" if h.get("project") else "") for h in held) or "-"
        if no_wait:
            print(f"FLASH_RUN=BUSY มีงานอื่นทำอยู่ job={ids} (ช่อง {len(held)}/{limit})", flush=True)
            return "busy"
        pos = len(ahead) + 1
        if (pos, len(held), limit, reason) != last:
            print(f"QUEUED ตำแหน่ง {pos} (กำลังทำ: {ids_named} · ช่อง {len(held)}/{limit})"
                  + (f" · {reason}" if reason else "") + " — รอคิว…", flush=True)
            last = (pos, len(held), limit, reason)
            if not queued_hint:
                queued_hint = True
                print("หมายเหตุ: คำสั่งนี้เฝ้างานจนจบ — ต้องรันด้วย run_in_background: true ตรง ๆ แล้วรอแจ้งเตือน (ห้ามต่อ & · sleep · head) "
                      "ถ้าเผลอทำไปแล้ว รัน `flashq wait <job>` ใน background ต่อได้", flush=True)
        if time.time() - t0 > wait_min * 60:
            print(f"FLASH_RUN=QUEUE_TIMEOUT รอคิวเกิน {wait_min:g} นาที", flush=True)
            return "timeout"
        for _ in range(6):  # ~3 วิ แต่ตื่นทันทีเมื่อมีสัญญาณ run_now
            time.sleep(0.5)
            if flag.exists():
                break


def _unlink_retry(f: Path, tries: int = 3, gap: float = 0.2) -> bool:
    """ลบไฟล์แบบลองซ้ำ (Windows: ไฟล์ถูกเปิดค้างชั่วคราว → PermissionError) · FileNotFoundError = ถือว่าสำเร็จ"""
    for i in range(tries):
        try:
            f.unlink(missing_ok=True)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if i + 1 < tries:
                time.sleep(gap)
    return False


def _read_lock_retry(f: Path, tries: int = 3, gap: float = 0.2) -> dict:
    """อ่านไฟล์ล็อกแบบลองซ้ำ (Windows: อ่านพลาดชั่วคราวแล้วได้ {}) · ไฟล์หายไปแล้ว = คืนค่าที่อ่านได้"""
    data: dict = {}
    for i in range(tries):
        data = read_json(f)
        if data or not f.exists():
            return data
        if i + 1 < tries:
            time.sleep(gap)
    return data


def release(job: dict) -> None:
    targets = [f for _, f in slot_files() if _read_lock_retry(f).get("id") == job["id"]]
    targets.append(RUN_NOW / job["id"])
    for f in targets:
        if not _unlink_retry(f):
            print(f"WARN: ลบไฟล์ล็อก {f.name} ไม่สำเร็จ (ไฟล์ถูกเปิดค้าง) — คิวจะเคลียร์เองเมื่อ process จบ", flush=True)


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
    if a == b or b.startswith(a.rstrip("/") + "/") or a.startswith(b.rstrip("/") + "/"):
        return True
    if a.endswith("/") or b.endswith("/"):
        return False
    if "/" not in a or "/" not in b:  # ฝั่งหนึ่งมีแค่ชื่อไฟล์ → เทียบชื่อไฟล์
        return a.rsplit("/", 1)[-1] == b.rsplit("/", 1)[-1]
    return False


# ประกาศในแผน (แนะนำ §0): `flashq-files: Client/Src/A.cpp, Client/Src/UI/*.h` · `flashq-parallel: no` · `flashq-exclusive: Build/*, CMakeLists.txt`
DECL_RE = re.compile(r"^\s*(?:[-*]\s*)?`?\s*flashq-(files|parallel|exclusive)\s*:\s*(.*?)\s*$", re.I)
NO_WORDS = ("no", "false", "0", "off", "ไม่")
# โฟลเดอร์ระดับบนที่ทุกโมดูลใช้ร่วม (ค่าเริ่มต้น · เพิ่มต่อโปรเจกต์ได้ด้วย "parallel_shared" ใน .flash.json)
DEFAULT_SHARED = ("common/", "util/", "shared/", "cmake/")


def plan_meta(project: str, plan: str) -> dict:
    """{files: list | None (ไม่ได้ประกาศ), exclusive: list (ไม่ประกาศ = ไม่มีคีย์), parallel: bool}
    จากบรรทัด flashq-files / flashq-exclusive / flashq-parallel นอก code block"""
    out = {"files": None, "parallel": True}
    if not plan:
        return out
    try:
        text = (Path(project) / plan).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    files, excl, fence = [], [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        m = None if fence else DECL_RE.match(line)
        if not m:
            continue
        val = m[2].strip().strip("`").strip()
        kind = m[1].lower()
        if kind == "parallel":
            word = (val.lower().split(None, 1) or [""])[0]
            if word in NO_WORDS:
                out["parallel"] = False
                why = val[len(word):].strip(" \t—–-:;,()")  # `flashq-parallel: no — เหตุผล` (ไม่บังคับ)
                if why:
                    out["why"] = why
            continue
        if re.search(r"<[^>]*>", val):  # placeholder ของแม่แบบที่ยังไม่เติม
            continue
        dest = excl if kind == "exclusive" else files
        for t in re.split(r"[,\s]+", val):
            t = t.strip("`'\"()")
            if t and not t.startswith("-"):
                p = Path(t)
                if p.is_absolute():
                    try:
                        t = p.relative_to(Path(project)).as_posix()
                    except ValueError:
                        pass
                dest.append(t.replace("\\", "/"))
    if files:
        out["files"] = sorted(set(files))
    if excl:
        out["exclusive"] = sorted(set(excl))
    return out


def job_info(j: dict) -> dict:
    """ชุดไฟล์ที่งานจะแตะ: ใช้ flashq-files ที่แผนประกาศก่อน · ไม่มี = เดาจาก backtick ของงานที่สั่ง (None = ตรวจไม่ได้)"""
    meta = plan_meta(j.get("project", ""), j.get("plan", ""))
    declared = meta["files"] is not None
    files = meta["files"] if declared else plan_files(j.get("project", ""), j.get("plan", ""), j.get("tasks", ""))
    return {"files": files, "parallel": meta["parallel"], "declared": declared, "why": meta.get("why", ""),
            "exclusive": meta.get("exclusive")}


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
    qa_a, qa_b = a.get("kind") == "qa", b.get("kind") == "qa"
    if qa_a or qa_b:  # นักทดสอบต้องเห็นโค้ดนิ่ง: ไม่รันคู่กับงานที่แก้ไฟล์ และไม่รันคู่กับนักทดสอบอีกตัว (พอร์ต/ไฟล์ชั่วคราวชนกัน) · ผู้ตรวจ/ผู้สืบอ่านอย่างเดียว รันคู่ได้
        if qa_a and qa_b:
            return "นักทดสอบอีกงานกำลังทดสอบโปรเจกต์นี้อยู่"
        other = b if qa_a else a
        if other.get("readonly"):
            return ""
        return ("มีงานที่แก้ไฟล์กำลังรันในโปรเจกต์เดียวกัน — ต้องรอให้จบก่อนถึงจะทดสอบได้ (ไม่งั้นทดสอบโค้ดที่ยังเปลี่ยนอยู่)" if qa_a
                else "นักทดสอบกำลังทดสอบโปรเจกต์นี้อยู่ — รอให้จบก่อนถึงจะแก้ไฟล์ได้")
    if a.get("readonly") or b.get("readonly"):  # งานอ่านอย่างเดียว (เช่น ผู้ตรวจ) ไม่แก้ไฟล์ → ไม่ชนใคร
        return ""
    if a.get("kind") == "doc" or b.get("kind") == "doc":  # ช่างเอกสารตัดสินจาก "ไฟล์ที่เปลี่ยนในโปรเจกต์" จึงต้องไม่มีใครแก้ไฟล์พร้อมกัน (ไม่งั้นแยกไม่ออกว่าใครแก้)
        return ("ช่างเอกสารกำลังแก้ไฟล์โปรเจกต์นี้อยู่ — รอให้จบก่อน" if b.get("kind") == "doc"
                else "มีงานที่แก้ไฟล์กำลังรันในโปรเจกต์เดียวกัน — ช่างเอกสารต้องรอให้จบก่อน (ไม่งั้นแยกไม่ออกว่าใครแก้ไฟล์ไหน)")
    ia, ib = info(a), info(b)
    if not ia["parallel"] or not ib["parallel"]:
        # แผนที่สั่ง no และประกาศ flashq-exclusive = ห้ามเฉพาะไฟล์ในขอบเขต · ฝั่งที่ไม่ได้ประกาศ = บล็อกทั้งก้อนเหมือนเดิม
        locked = [(mine, ia if mine else ib, ib if mine else ia) for mine in (True, False)
                  if not (ia if mine else ib)["parallel"]]
        if any(not own.get("exclusive") for _mine, own, _other in locked):
            mine = not ia["parallel"]
            head = "แผนสั่งให้รอ (flashq-parallel: no)" if mine else "แผนของงานนั้นสั่งห้ามรันคู่ (flashq-parallel: no)"
            why = (ia if mine else ib).get("why")
            head += f" · เหตุผลจากแผน: {why}" if why else " · แผนไม่ได้เขียนเหตุผลไว้"
            if ia["files"] is not None and ib["files"] is not None:  # บอกด้วยว่าไฟล์ซ้อนกันจริงไหม ผู้ใช้จะตัดสินใจกดรันเลยได้
                over = sorted({x for x in ia["files"] for y in ib["files"] if paths_overlap(x, y)})
                head += (" · ไฟล์ที่ซ้อนกันจริง: " + ", ".join(over[:3]) + (f" (+{len(over) - 3})" if len(over) > 3 else "")) if over else " · ไฟล์ที่ประกาศไม่ซ้อนกัน"
            return head
        for mine, own, other in locked:  # ประกาศขอบเขตไว้ → ชนเฉพาะเมื่ออีกฝ่ายแตะขอบเขตนั้น (ไม่งั้นไหลลงตรวจปกติ)
            if other["files"] is None:
                return "ดึงรายการไฟล์ของงานนั้นไม่ได้"
            over = sorted({y for y in other["files"] for x in own["exclusive"] if paths_overlap(x, y)})
            if over:
                head = "แผนสั่งให้รอ (flashq-parallel: no)" if mine else "แผนของงานนั้นสั่งห้ามรันคู่ (flashq-parallel: no)"
                why = own.get("why")
                head += f" · เหตุผลจากแผน: {why}" if why else " · แผนไม่ได้เขียนเหตุผลไว้"
                head += " · ขอบเขตห้ามรันคู่ซ้อนกับ: " + ", ".join(over[:3]) + (f" (+{len(over) - 3})" if len(over) > 3 else "")
                return head
    if ia["files"] is None:
        return "ดึงรายการไฟล์ของงานนี้ไม่ได้ (ใส่ flashq-files: ในแผน)"
    if ib["files"] is None:
        return "ดึงรายการไฟล์ของงานนั้นไม่ได้"
    if not ia["files"]:
        return "แผนไม่ระบุไฟล์ที่งานนี้จะแตะ (ใส่ `path` บนหัวงานหรือ flashq-files: ในแผน)"
    if not ib["files"]:
        return "แผนของงานนั้นไม่ระบุไฟล์ที่จะแตะ"
    over = sorted({x for x in ia["files"] for y in ib["files"] if paths_overlap(x, y)})
    if over:
        return "ไฟล์ " + ", ".join(over[:3]) + (f" (+{len(over) - 3})" if len(over) > 3 else "")
    proj = a.get("project", "")
    sh = shared_paths(proj)
    ha = {x for x in ia["files"] if shared_hit(x, sh, proj)}  # ไฟล์ร่วมที่ฝั่ง a แตะ
    hb = {x for x in ib["files"] if shared_hit(x, sh, proj)}  # ไฟล์ร่วมที่ฝั่ง b แตะ
    strict = bool(project_cfg(Path(proj)).get("parallel_shared_strict")) if proj else False  # โหมดเข้ม = ฝั่งเดียวแตะก็ชน
    if (ha and hb) or (strict and (ha or hb)):
        hit = sorted(ha | hb)
        return "แตะไฟล์ที่ทุกโมดูลใช้ร่วม " + ", ".join(hit[:3]) + (f" (+{len(hit) - 3})" if len(hit) > 3 else "")
    return ""


def run_stats(all_jobs: list[dict], project: str) -> dict | None:
    """เวลารันที่ผ่านมาของงานแก้โค้ดที่สำเร็จ (นาที): {median, p90, n} · ใช้ของโปรเจกต์เดียวกันถ้ามี ≥5 งาน ไม่งั้นใช้ทุกโปรเจกต์ · None = ข้อมูลไม่พอ"""
    def mins(js):
        out = []
        for x in js:
            if x.get("status") == "ok" and x.get("kind", "work") == "work" and x.get("started") and x.get("finished"):
                d = _secs(x["started"], x["finished"])
                if d is not None and d > 0:
                    out.append(d / 60)
        return sorted(out)
    same = mins([x for x in all_jobs if _pnorm(x.get("project", "")) == _pnorm(project)])
    v = same if len(same) >= 5 else mins(all_jobs)
    if len(v) < 5:
        return None
    return {"median": v[len(v) // 2], "p90": v[min(len(v) - 1, int(len(v) * 0.9))], "n": len(v)}


def running_brief(j: dict, stats: dict | None = None) -> str:
    """อธิบายงานที่กำลังรันให้คนอ่านเข้าใจ: id (โปรเจกต์ · แผน · งานย่อย · รันมานานเท่าไร · คาดว่าจะเสร็จเมื่อไร)"""
    parts = [Path(j.get("project", "")).name, Path(str(j.get("plan") or "").replace("\\", "/")).name, str(j.get("tasks") or "")]
    sec = _secs(j.get("started") or j.get("created") or "")
    if sec is not None and sec >= 0:
        parts.append(f"รันมาแล้ว {sec // 3600} ชม. {sec % 3600 // 60} นาที" if sec >= 3600 else f"รันมาแล้ว {sec // 60} นาที")
        if stats:
            med, p90 = stats["median"], stats["p90"]
            if sec / 60 <= med:
                parts.append(f"ปกติใช้ ~{med:.0f} นาที → น่าจะเสร็จอีก ~{max(1, med - sec / 60):.0f} นาที")
            elif sec / 60 <= p90:
                parts.append(f"เกินเวลาปกติ (~{med:.0f} นาที) แต่ยังไม่เกินที่เคยเห็น 9 ใน 10 งาน ({p90:.0f} นาที)")
            else:
                parts.append(f"นานกว่า 9 ใน 10 งานที่ผ่านมา ({p90:.0f} นาที) — น่าจะติดอะไรอยู่")
        key = "agent_timeout_min" if j.get("kind") in AGENT_KINDS else "timeout_min"
        cap = float(read_config().get(key) or DEFAULTS.get(key) or 0)
        t0 = _secs(j.get("started") or j.get("created") or "")
        if cap and t0 is not None:
            end = datetime.now() + timedelta(minutes=max(0.0, cap - t0 / 60))
            parts.append(f"ช้าสุดตัดเวลา {end:%H:%M}")
    detail = " · ".join(p for p in parts if p)
    return f"{j['id']} ({detail})" if detail else j["id"]


def schedule(held: list[dict] | None = None) -> dict:
    """จำลองการจัดคิวตอนนี้: {mode, limit, used, start: [id ที่ได้เริ่ม], reasons: {id: เหตุที่ยังรอ}}
    auto = ไล่คิวตามลำดับ เริ่มงานแรกที่ไม่ชนกับงานที่กำลังทำ (+ที่เพิ่งเลือก) · ข้ามงานที่ชน
           แต่งานที่ชนและรอเกิน starve_min นาที = ล็อกหัวคิว (งานหลังจากนั้นที่ชนกับมันห้ามแซง)
    fifo = งานหัวคิวได้ช่องว่างตามลำดับ"""
    held = held_slots() if held is None else held
    limit, mode, starve = max_parallel(), schedule_mode(), starve_min()
    held_ids = {h.get("id") for h in held}
    all_jobs = jobs()
    active = [j for j in all_jobs if live_state(j) == "running"]
    queue = [j for j in all_jobs if j.get("status") == "queued" and live_state(j) == "queued"]
    memo: dict[str, dict] = {}
    stats_memo: dict[str, dict] = {}  # สถิติเวลารันรายโปรเจกต์ คำนวณครั้งเดียวต่อรอบ และเฉพาะเมื่อมีงานต้องรอจริง

    def info(j: dict) -> dict:
        if j["id"] not in memo:
            memo[j["id"]] = job_info(j)
        return memo[j["id"]]

    free, start, reasons, barriers = limit - len(held), [], {}, []
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
        blocked = ""
        for b in barriers:  # งานที่อดตาย: ห้ามแซงเฉพาะงานที่ชนกับมัน (งานอื่นไม่ชน = ไหลลงตรวจปกติ)
            c = conflict_reason(q, b, info)
            if c:
                blocked = (f"ชนกับ {b['id']} ที่รอนานเกิน {starve:g} นาที ({c})"
                           f" → รอให้ {b['id']} เริ่มก่อน (กันอดตาย)")
                break
        if blocked:
            reasons[qid] = blocked
            continue
        why = ""
        for r in active if mode == "auto" else ():  # ช่องเต็มก็ยังตรวจ เพื่อบอกเหตุชน + นับกันอดตาย
            c = conflict_reason(q, r, info)
            if c:
                pk = _pnorm(q.get("project", ""))
                if pk not in stats_memo:
                    stats_memo[pk] = run_stats(all_jobs, q.get("project", "")) or {}
                who = running_brief(r, stats_memo[pk] or None)
                why = f"{c} · รอ {who} จบก่อน" if c.startswith("แผนสั่งให้รอ") else f"ชนกับ {who}: {c}"
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
            barriers.append(q)  # ล็อกเฉพาะงานที่ชนกับมัน
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
        block = conflict_reason(target, j, job_info) if same else ""  # เกณฑ์เดียวกับตัวจัดคิว: flashq-parallel: no / ขอบเขต flashq-exclusive / ไฟล์ร่วม
        if block.startswith("ดึงรายการไฟล์"):  # ตรวจไฟล์ไม่ได้ — แสดงผ่านช่อง unknown อยู่แล้ว
            block = ""
        items.append({"id": j["id"], "project_name": Path(j.get("project", "")).name, "plan": j.get("plan", ""),
                      "tasks": j.get("tasks", ""), "message": j.get("message", ""), "model": j.get("model", ""),
                      "same_project": same, "files": theirs, "overlap": over, "block": block})
    return {"id": target["id"], "files": mine, "running": items,
            "any_overlap": any(i["overlap"] or i["block"] for i in items),
            "unknown": any(i["same_project"] and i["overlap"] is None for i in items),
            "legacy": target.get("qv", 0) < QUEUE_VERSION, "max_parallel": max_parallel(), "used": len(held_slots())}


# ---------- opencode ----------
def ensure_live_server(exe: list[str], ext_dirs: list[str] = ()) -> bool:
    """เปิด `opencode serve --port 4096` ค้างไว้ (ถ้ายังไม่มี) ให้ desktop ต่อดูสดได้ · cwd กลาง ไม่ผูกโปรเจกต์ (run ส่ง --dir เอง)
    ext_dirs = external_dirs ของทุกโปรเจกต์ที่รู้จัก → ส่งเป็น OPENCODE_CONFIG_CONTENT ตอนเปิด (server โหลด config ครั้งเดียว)"""
    import urllib.request

    def up() -> bool:
        try:
            urllib.request.urlopen(LIVE_URL + "/config", timeout=3)
            return True
        except Exception as e:  # 401 ก็แปลว่ามี server อยู่
            return getattr(e, "code", None) is not None
    if up():
        return True
    flags = HIDDEN_DETACH_FLAGS
    env = {k: v for k, v in os.environ.items() if k != "OPENCODE_SERVER_PASSWORD"}
    if ext_dirs:
        env["OPENCODE_CONFIG_CONTENT"] = perm_config_content(list(ext_dirs))
    sp = subprocess.Popen([*exe, "serve", "--port", "4096", "--hostname", "127.0.0.1"], cwd=str(HOME),
                          stdout=open(HOME / "live_server.log", "ab"), stderr=subprocess.STDOUT, creationflags=flags, env=env)
    try:  # เก็บ pid ไว้ให้ปิดได้ (taskkill /PID <pid> /T /F) — server นี้เปิดค้างโดยตั้งใจ
        (HOME / "live_server.pid").write_text(str(sp.pid), encoding="utf-8")
    except OSError:
        pass
    for _ in range(30):
        time.sleep(1)
        if up():
            return True
    return False


def wait_session(p: subprocess.Popen, log: Path, limit: int | None = None) -> str | None:
    """รอ sessionID ใน log · "" = process จบก่อน · None = ไม่ขึ้นใน limit วิ (ค่าเริ่มต้น START_LIMIT_SEC · เจอตอน desktop เพิ่งเปิดใหม่)"""
    pos, buf = 0, ""  # อ่านเฉพาะส่วนที่เพิ่มต่อท้าย (ไม่อ่านทั้งไฟล์ซ้ำทุกวินาที)
    for _ in range(limit or START_LIMIT_SEC):
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


OC_LOG = Path(os.environ.get("FLASHQ_OPENCODE_LOG") or (Path.home() / ".local" / "share" / "opencode" / "log" / "opencode.log"))
OC_DB_WARN_GB = 5  # ฐานข้อมูล opencode ใหญ่กว่านี้ = เตือนให้ล้าง (ไม่ใช่ต้นตอค้างที่ init — SQLite busy_timeout 5 วิแล้ว error · ต้นตอจริงคือ stdin ไม่ปิด พิสูจน์ 2026-10-23)
OC_LOG_TAIL_BYTES = 8 << 20
# ขั้นตอนเริ่มระบบของ opencode (เรียงตามลำดับใน log) → ข้อความบอกว่าค้างหลังขั้นไหน
OC_STAGES = (("llm runtime selected", "ส่งคำขอไปผู้ให้บริการโมเดลแล้วไม่ได้คำตอบเลย — ผู้ให้บริการเงียบ (รอบลองใหม่มักผ่าน · เป็นบ่อย = สลับ provider)"),
             ("loop ", "เข้ารอบสนทนาแล้ว กำลังเตรียมเรียกโมเดล (โหลด skill/ไฟล์ช้า)"),
             ("created id=", "สร้าง session แล้วแต่ยังไม่เข้ารอบสนทนา"),
             ("init", "ค้างก่อนสร้าง session — opencode run รออ่าน stdin ที่ไม่ปิด (flashq ปิด stdin ให้แล้ว · ยังเจอ = สาเหตุใหม่ ส่งสืบ)"),
             ("loading path=", "ค้างระหว่างโหลดคอนฟิก"), ("bootstrapping", "ค้างตอนเริ่มโปรเจกต์ (bootstrapping)"), ("creating instance", "ค้างตอนสร้าง instance"))


def nostart_diag(root: Path, since: float, log: Path | None = None, db: Path | None = None) -> str:
    """NOSTART (log ของ `opencode run` ว่างจนหมดเวลา) → อ่านท้าย log กลางของ opencode หารอบที่เปิดโฟลเดอร์โปรเจกต์นี้หลัง `since` แล้วบอกว่าค้างหลังบรรทัดไหน
    ไม่เจอรอบนั้นเลย = process ไม่ทันบูต · ใหญ่เกิน OC_DB_WARN_GB = เตือนเรื่องฐานข้อมูล · พังเองคืน "" (ห้ามกระทบสถานะงาน)"""
    log, db = log or OC_LOG, db or OC_DB
    parts = []
    try:
        with open(log, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - OC_LOG_TAIL_BYTES))
            lines = f.read().decode("utf-8", errors="replace").splitlines()[1 if size > OC_LOG_TAIL_BYTES else 0:]  # ตัดบรรทัดแรกที่อาจขาดครึ่ง (เมื่ออ่านแค่ท้ายไฟล์)
        want = os.path.normcase(os.path.normpath(str(root)))
        runs: dict = {}
        for ln in lines:
            m = re.match(r'timestamp=(\S+)Z level=\w+ run=(\w+) message=(.*)', ln)
            if not m:
                continue
            ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp()
            if ts < since - 5:
                continue
            msg = m.group(3)
            if msg.startswith('"'):  # message="creating instance" directory=... → ตัดเครื่องหมายคำพูดรอบข้อความ
                msg = msg[1:].replace('"', "", 1)
            if msg.startswith("creating instance"):
                d = re.search(r'directory="((?:[^"\\]|\\.)*)"', msg)
                dd = d.group(1).replace("\\\\", "\\") if d else ""
                if os.path.normcase(os.path.normpath(dd)) == want:
                    runs[m.group(2)] = {"start": ts, "msgs": []}
            if m.group(2) in runs and not msg.startswith(("cleanup", "duplicate skill")):  # cleanup = งานเบื้องหลังเรียกหลัง 1 นาที ไม่ใช่ขั้นเริ่มระบบ
                runs[m.group(2)]["msgs"].append((ts, msg))
                if msg.startswith("loop ") and re.search(r"\bstep=[1-9]", msg):  # ถึงรอบ 2 = โมเดลตอบแล้ว log ของรอบนั้นต้องมี sessionID → เป็นของงานอื่นที่เปิดโฟลเดอร์เดียวกันพร้อมกัน
                    runs[m.group(2)]["other"] = True
        mine = {k: v for k, v in runs.items() if not v.get("other")}
        if not runs:
            parts.append("log กลางของ opencode ไม่มีรอบที่เปิดโฟลเดอร์นี้เลย → process ไม่ทันบูต (เครื่องหน่วง/ติดไวรัสสแกน/ไฟล์ opencode เปิดไม่ขึ้น)")
        elif not mine:
            parts.append(f"รอบที่เปิดโฟลเดอร์นี้ {len(runs)} รอบเป็นของงานอื่นที่ทำงานอยู่ทั้งหมด → process ของงานนี้ไม่ทันบูต")
        else:
            for rid, r in sorted(mine.items(), key=lambda kv: kv[1]["start"])[-2:]:
                msgs = [x[1] for x in r["msgs"]]
                stage = next((txt for key, txt in OC_STAGES if any(x.startswith(key) for x in msgs)), "")
                lastts, last = r["msgs"][-1]
                parts.append(f"รอบ run={rid}: บรรทัดสุดท้าย `{last[:90]}` ({lastts - r['start']:.0f} วิหลังเริ่ม) → {stage or 'ไม่ทราบขั้น'}")
    except OSError as e:
        parts.append(f"อ่าน log opencode ไม่ได้ ({e.__class__.__name__})")
    except Exception:
        return ""
    try:
        gb = Path(db).stat().st_size / (1 << 30)
        if gb >= OC_DB_WARN_GB:
            parts.append(f"⚠ ฐานข้อมูล opencode ใหญ่ {gb:.0f} GB (เกณฑ์เตือน {OC_DB_WARN_GB} GB) — ทำให้ opencode ช้า/เปลืองดิสก์ · แนะนำล้าง session เก่า/หมุนไฟล์ (สำรองก่อน)")
    except OSError:
        pass
    return " · ".join(parts)


def _onoff(v):
    """on/off/true/false/1/0 (หรือ bool) → bool · อ่านไม่ออก/ไม่ได้ตั้ง → None"""
    if isinstance(v, bool):
        return v
    t = str(v if v is not None else "").strip().lower()
    return True if t in ("on", "true", "1") else False if t in ("off", "false", "0") else None


def want_open_session(root: Path, job: dict, no_open: bool) -> bool:
    """เปิดหน้าต่าง session ของพนักงานตอนงานเริ่มไหม · --no-open > .flash.json ของโปรเจกต์ > config ของเครื่อง >
    ค่าเริ่มต้นตามผู้สั่ง (ส่งด้วย run --detach = ผู้สั่งไม่ใช่ Claude Code เช่น opencode → ไม่เปิด · อื่น ๆ เปิด)"""
    if no_open:
        return False
    for v in (project_cfg(root).get("open_session"), read_json(CONFIG).get("open_session")):
        b = _onoff(v)
        if b is not None:
            return b
    return job.get("submitter") != "detach"


def open_in_desktop(sid: str, server: str) -> None:
    node = shutil.which("node")
    if not node:
        return
    r = run_timeout([node, str(REPO / "oc_desktop_open.mjs"), sid, server or "sidecar"], DESKTOP_OPEN_TIMEOUT_SEC)  # ไม่ให้งานค้างก่อนเริ่มเฝ้า
    print((r.stdout.strip() or (f"DESKTOP_OPEN=FAIL หมดเวลา {DESKTOP_OPEN_TIMEOUT_SEC:g} วิ" if r.returncode == 124 else f"DESKTOP_OPEN=FAIL rc={r.returncode}")), flush=True)


def server_activity(server: str, sid: str, directory: str = "") -> dict | None:
    """ถามเซิร์ฟเวอร์ opencode (เมื่อ attach) ว่า session นี้ + session ลูกหลาน (subagent ที่ /flash ส่งไปทำ T-xx) ขยับล่าสุดเมื่อไร และมี tool ไหนกำลังรันอยู่
    log ของ parent เงียบได้ทั้งที่ subagent กำลังทำงาน → ใช้ตัดสินว่า "ค้างจริง" + บอกสาเหตุ (tool ค้าง vs รอโมเดล) · ถามไม่ได้ = None (ใช้ log อย่างเดียว)
    directory = โฟลเดอร์โปรเจกต์ของ session (server เปิดที่ ~/.flashq · ไม่ส่ง = server หา session ของโปรเจกต์อื่นไม่เจอ)"""
    import urllib.parse
    import urllib.request
    qs = ("?" + urllib.parse.urlencode({"directory": directory})) if directory else ""

    def get(path, limit=0):
        # ข้อความล่าสุดเท่านั้น (limit) — session หลักยาวมาก server ส่งทั้งประวัติไม่ทัน/ตัดการเชื่อมต่อ ทำให้วินิจฉัยไม่ได้
        q = qs + (("&" if qs else "?") + f"limit={limit}" if limit else "")
        return json.loads(urllib.request.urlopen(server.rstrip("/") + path + q, timeout=8).read())
    try:
        updated, running, ids, titles, cupd = 0, [], [sid], {}, {}
        k = 0
        while k < len(ids) and len(ids) < 30:  # ไล่ลูกหลาน (subagent ซ้อน subagent) · จำกัดจำนวนกันวน
            try:
                for c in get(f"/session/{urllib.parse.quote(ids[k])}/children"):
                    if c.get("id") and c["id"] not in ids:
                        ids.append(c["id"])
                        titles[c["id"]] = str(c.get("title") or "")[:80]
                        cupd[c["id"]] = (c.get("time") or {}).get("updated", 0)
                        updated = max(updated, cupd[c["id"]])
            except Exception:
                pass
            k += 1
        subs = []  # ผู้ช่วยย่อยแต่ละตัว: ชื่องาน · ขยับล่าสุด · tool ล่าสุด (การ์ดหน้าเว็บแสดงแทน "log เงียบ" ของ session หลัก)
        for i in ids:
            su, doing = cupd.get(i, 0), ""
            try:
                msgs = get(f"/session/{urllib.parse.quote(i)}/message", limit=2)[-2:]
            except Exception:
                if i == sid:
                    raise  # session หลักถามไม่ได้ = ไม่มีข้อมูลพอ (None) · ลูกตัวใดตัวหนึ่งพลาดข้ามได้
                msgs = []
            for m in msgs:
                su = max(su, (m.get("info", {}).get("time") or {}).get("created", 0))
                for p in m.get("parts", []):
                    st = p.get("state") or {}
                    t = st.get("time") or p.get("time") or {}
                    su = max(su, t.get("end", 0), t.get("start", 0))
                    if p.get("type") == "tool":
                        inp = st.get("input") or {}
                        what = str(st.get("title") or inp.get("command") or inp.get("description") or inp.get("filePath") or "")[:100]
                        doing = f"{p.get('tool')}: {what}" + ("" if st.get("status") == "running" else " (จบแล้ว)")
                        if st.get("status") == "running":
                            running.append({"tool": p.get("tool"), "what": what, "since": t.get("start", 0) / 1000, "session": i,
                                            "cmd": str(inp.get("command") or "")[:2000]})
            updated = max(updated, su)
            if i != sid:
                subs.append({"session": i, "title": titles.get(i, ""), "updated": su / 1000 if su else 0, "doing": doing[:120]})
        subs.sort(key=lambda s: -s["updated"])
        return {"updated": updated / 1000 if updated else 0, "running": running, "subs": subs}
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


def _cmd_norm(s: str) -> str:  # \" ที่ opencode หนีไว้ใน command line ของ shell ต้องหายไปพร้อมเครื่องหมายคำพูด (ไม่งั้นจับคู่ shell ไม่ได้ → เข้าใจผิดว่า shell จบ)
    return re.sub(r"\s+", " ", re.sub(r"\\*[\"'`^]", "", s)).strip().lower()


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
        self.released: list = []  # สงสัยแล้วแต่ tool จบเอง (ผู้เรียกดึงไปบันทึกแล้วล้าง)

    def check(self, running: list[dict], now: float | None = None) -> dict | None:
        now = now or time.time()
        bash = [r for r in running if r.get("tool") == "bash" and r.get("cmd")]
        for k in [k for k in self.seen if k not in {(r["session"], r["since"]) for r in bash}]:
            if self.seen[k].get("warn"):  # tool จบเองระหว่างที่ยามสงสัย
                self.released.append({"cmd": self.seen[k]["cmd"], "note": self.seen[k]["warn"]})
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
                        and (p["ppid"] in w["pids"] or sum(t in _cmd_norm(p["cmd"]) for t in toks) >= min(2, len(toks)))]  # คำเดียวซ้ำกันบังเอิญได้ (เช่น tools)
                group = tree(prev + orph)
                w["gone"] += 1
            for i, p in group.items():
                w["pids"][i] = p["created"]
            act = sum(p["act"] for p in group.values())
            if act != w["act"]:
                w["act"], w["chg"] = act, now
            names = ", ".join(sorted({p["name"] for p in group.values()}))[:80]
            rep = {"cmd": r["what"] or r["cmd"][:100], "session": r["session"], "since": r["since"], "pids": len(group), "names": names,
                   "quiet_sec": round(now - w["chg"]), "run_sec": round(now - r["since"]), "state": "none" if not group else "active", "note": "",
                   "kill_in": None}
            if group and not shells and w["gone"] >= SHELL_CONFIRM:
                rep.update(state="killed", note=f"shell จบแล้วแต่โปรเซสลูกยังถือ handle ไว้ ({names}) → tool ไม่คืนค่า")
            elif group and not shells:  # ยังไม่แน่ใจ → บอกว่าสงสัยอะไร รออีกกี่วิ · tool จบเองก่อน = ปล่อยไป
                rep.update(state="suspect", note=f"หา shell ของคำสั่งไม่เจอ (อาจจบแล้ว) แต่ยังมีโปรเซสลูก ({names}) — ยืนยัน {w['gone']}/{SHELL_CONFIRM} รอบ",
                           kill_in=round((SHELL_CONFIRM - w["gone"]) * SHELL_POLL_SEC))
            elif group and self.idle and now - w["chg"] >= self.idle:
                rep.update(state="killed", note=f"โปรเซสนิ่งสนิท (CPU/I/O ไม่ขยับ) {(now - w['chg']) / 60:.1f} นาที ({names})")
            elif group and now - w["chg"] >= max(SHELL_POLL_SEC * 2, self.idle / 2):
                rep.update(state="quiet", note=f"โปรเซส ({names}) CPU/I/O ไม่ขยับ", kill_in=round(self.idle - (now - w["chg"])) if self.idle else None)
            w["cmd"], w["warn"] = rep["cmd"], rep["note"] if rep["state"] in ("suspect", "quiet") else ""
            if rep["state"] == "killed":
                rep["victims"] = [{"pid": p["pid"], "name": p["name"], "cmd": p["cmd"][:160]} for p in group.values() if p["ppid"] not in group]
                for v in rep["victims"]:
                    self.killer(v["pid"])
                del self.seen[(r["session"], r["since"])]
            rank = {"killed": 4, "suspect": 3, "quiet": 2, "active": 1, "none": 0}
            if best is None or rank[rep["state"]] > rank[best["state"]]:
                best = rep
        return best


def run_once(*args, **kw) -> dict:
    """รันหนึ่งรอบ — ถ้า `flashq run` เองล้ม/ถูกกด Ctrl+C กลางทาง ต้องไม่ทิ้ง opencode ลูกไว้แก้ไฟล์ต่อเงียบ ๆ"""
    job = args[0]
    try:
        return _run_once(*args, **kw)
    except BaseException:
        note = reap_orphan(job, abort=True)
        if note:
            print(note, flush=True)
        raise


def _run_once(job: dict, cmd: list[str], root: Path, attach: str, timeout_min: int, no_open: bool, attempt: int, stall_min: float = 0, stall_floor: float = 0,
              shell_idle: float = 0, env: dict | None = None, model_wait: float = 0) -> dict:
    log = LOGS / f"{job['id']}_{attempt}.jsonl"
    err = LOGS / f"{job['id']}_{attempt}.err"
    job.setdefault("logs", []).append(str(log))
    save_job(job)
    print(f"START {job['id']} รอบ {attempt} title='{job['title']}' model={job.get('model') or '(ค่าเริ่มต้น config)'} "
          f"{('variant=' + job['variant'] + ' ') if job.get('variant') else ''}attach={attach or '-'} log={log}", flush=True)
    t0, status = time.time(), "OK"
    head0 = _git(root, "rev-parse", "HEAD")  # มี commit ใหม่หลังรัน = งานสำเร็จบางส่วน (ใช้ตัดสิน DENIED กับ OK)
    with open(log, "wb") as fo, open(err, "wb") as fe:
        # stdin=DEVNULL: opencode run อ่าน stdin จนจบก่อนสร้าง session — ถ้าสืบทอดท่อที่ไม่ปิดจากตัวสั่ง จะค้างหลัง log `init` ตลอดไป (NOSTART)
        p = subprocess.Popen(cmd, cwd=str(root), stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, env=env)
        job["child_pid"], job["child_pid_start"] = p.pid, proc_start(p.pid)
        save_job(job)
        sid = wait_session(p, log, START_LIMIT_FIRST_SEC if attempt == 1 else START_LIMIT_SEC)
        if sid is None:
            kill_tree(p.pid)
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                print(f"WARN: ฆ่า opencode pid {p.pid} ไม่สำเร็จใน 30 วิ — ปล่อยไว้แล้วไปต่อ", flush=True)
            rc, status = -1, "NOSTART"
            nostart = nostart_diag(root, t0)
            if nostart:
                job.setdefault("nostart_diag", []).append(nostart)
                save_job(job)
                print(f"NOSTART รอบ {attempt}: {nostart}", flush=True)
        else:
            if sid:
                job["session"] = sid
                save_job(job)
                if want_open_session(root, job, no_open):
                    open_in_desktop(sid, attach)
            last_poll = 0.0
            last_m, last_chg, maxgap = 0.0, time.time(), 0.0  # จังหวะ log จริง → เกณฑ์ค้างปรับตามงานนี้ (งานที่ปกติขยับทุกครึ่งนาที ไม่ต้องรอ 20 นาทีถึงรู้ว่าค้าง)
            watch = ShellWatch(shell_idle) if shell_idle and attach.startswith("http") and (os.name == "nt" or os.environ.get("FLASHQ_FAKE_PROCS")) else None
            warned = False  # เตือนล่วงหน้า "log เงียบ" ครั้งเดียวต่อรอบ
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
                        mw = model_wait * 60 if (model_wait and limit and can_ask) else 0  # เกณฑ์ "รอโมเดล" (ใช้ได้เมื่อถาม server ได้เท่านั้น) · ไม่เกินเกณฑ์ปกติ
                        mw = min(mw, limit) if mw else 0
                        if can_ask and ((limit and (idle >= limit or (idle >= limit / 2 and time.time() - last_poll >= 20)))
                                        or (mw and idle >= mw and time.time() - last_poll >= 20)
                                        or (watch and idle >= SHELL_POLL_SEC and time.time() - last_poll >= SHELL_POLL_SEC)):
                            # log เงียบแล้ว → ถามเซิร์ฟเวอร์ว่า subagent/tool ยังขยับไหม (ไม่ถามทุกรอบ แต่ถามสดเสมอก่อนตัดสินฆ่า)
                            last_poll = time.time()
                            act = server_activity(attach, job["session"], str(root))
                            if act and act["updated"]:
                                idle = min(idle, time.time() - act["updated"])
                            if act is not None:  # หน้าเว็บ: log หลักเงียบเพราะผู้ช่วยย่อยทำงานอยู่ = ไม่ใช่ค้าง
                                job["agent_act"] = {"at": time.time(), "updated": act["updated"], "subs": act.get("subs", [])[:3]}
                                save_job(job)
                            if act is not None and watch:
                                rep = watch.check(act["running"])
                                job["shell_watch"] = dict(rep, at=now()) if rep else None
                                if rep and rep["state"] == "killed":
                                    job.setdefault("shell_kills", []).append({"at": now(), "cmd": rep["cmd"], "note": rep["note"], "run_sec": rep["run_sec"],
                                                                              "victims": rep.get("victims", [])})
                                    print(f"SHELL_WATCH: ฆ่าคำสั่งค้าง `{rep['cmd'][:80]}` (รันมา {rep['run_sec'] / 60:.1f} นาที) · {rep['note']} → tool คืน error แล้วงานทำต่อ", flush=True)
                                elif rep and rep["state"] == "active":
                                    busy_until = time.time() - rep["quiet_sec"]
                                for x in watch.released:  # สงสัยแล้วแต่คำสั่งจบเองก่อนครบเวลา = ปล่อยไป
                                    job.setdefault("shell_released", []).append(dict(x, at=now()))
                                    print(f"SHELL_WATCH: ปล่อยไป `{x['cmd'][:80]}` จบเองก่อนครบเวลา (เคยสงสัย: {x['note']})", flush=True)
                                watch.released.clear()
                                save_job(job)
                        if busy_until:
                            idle = min(idle, time.time() - busy_until)
                        model_wait_hit = bool(mw and act is not None and not act["running"] and idle >= mw)  # ถามสดรอบนี้แล้ว: ไม่มี tool รัน + ไม่มีอะไรขยับเลย = รอโมเดลอย่างเดียว
                        if limit and not warned and idle >= max(60, (mw or limit) / 2):  # เตือนล่วงหน้าครั้งเดียว (idle นับรวมความขยับที่ server เห็นแล้ว)
                            warned = True
                            print(f"WARN: ไม่มีความเคลื่อนไหว {idle / 60:.1f} นาที — ถ้าเงียบถึง {(mw or limit) / 60:.1f} นาที"
                                  + (" และ server ไม่เห็น tool รันอยู่" if mw else "") + " จะถือว่าค้าง ฆ่าแล้วลองใหม่เอง", flush=True)
                        if model_wait_hit and not (idle >= limit):
                            why = (f"STALL: รอโมเดลนาน {idle / 60:.1f} นาที (เกณฑ์รอโมเดล {mw / 60:g} นาที · server ยืนยันว่าไม่มี tool ใดรันอยู่และไม่มีความขยับ) "
                                   f"· สาเหตุ: ผู้ให้บริการ ({job.get('model') or 'ค่าเริ่มต้น'}) ไม่ตอบคำขอ")
                        elif limit and idle >= limit:
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
                        try:
                            p.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            print(f"WARN: ฆ่า opencode pid {p.pid} ไม่สำเร็จใน 30 วิ — ปล่อยไว้แล้วไปต่อ", flush=True)
                        rc, status = -1, "TIMEOUT"
                        job["timeout_reason"] = why
                        note = abort_session(job) if attach.startswith("http") else ""  # ฆ่าแค่ `opencode run --attach` → session บน server ยังเดิน (แก้ไฟล์ซ้อนกับรอบลองใหม่/งานถัดไป)
                        if note:
                            print(note, flush=True)
                        break

    session, texts, errors, tools, denied, recent = "", [], [], 0, [], []
    tool_denied, task_out = [], []  # tool ที่ล้มเพราะ opencode ปฏิเสธสิทธิ์ · ผลที่ subagent (tool task) ส่งกลับ
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
            elif PERM_DENY_RE.search(str(st.get("error", ""))):
                tool_denied.append(f"{part.get('tool', '?')} {str(inp.get('description') or inp.get('command') or inp.get('filePath') or '')[:80]}".strip())
            if part.get("tool") == "task" and isinstance(st.get("output"), str):
                task_out.append(st["output"])
        elif ev.get("type") == "error" or "error" in ev:
            errors.append(json.dumps(ev.get("error", ev), ensure_ascii=False)[:400])
    errtxt = err.read_text(encoding="utf-8", errors="replace")
    last = texts[-1] if texts else ""
    perm = perm_denials(errtxt, tool_denied)
    if status == "OK" and (rc != 0 or errors):
        status = "FAIL"
    if status == "OK" and perm and not job_progressed(root, head0, texts + task_out, job):
        status = "DENIED"  # opencode ตอบ "ไม่อนุญาต" ให้เอง งานจบ exit 0 โดยไม่ได้ทำอะไร — ไม่ใช่ OK
    if status == "OK" and SUBAGENT_RE.search(errtxt):  # agent เป็น subagent → opencode เงียบ ๆ ไปรัน agent เริ่มต้นแทน
        status = "FAIL"
        errors.append("agent ที่ระบุใช้ไม่ได้ (เป็น subagent หรือหาไม่เจอ → opencode ตกไปใช้ agent เริ่มต้นที่แก้ไฟล์ได้) — ตั้ง mode: all/primary ติดตั้ง agent ให้ครบ หรือใช้ --attach none")
    # ตรวจโควตาจาก error/stderr จริงเท่านั้น — ไม่กวาดข้อความสรุปของ worker (คำว่า balance/quota ในเนื้องานเกมทำให้สลับบัญชีเกินจำเป็น)
    # worker รายงานโควตาเองด้วยบรรทัด "FAIL: quota" (flash.md)
    if (QUOTA_RE.search(" ".join(errors) + errtxt[-2000:]) and (rc != 0 or errors)) or "FAIL: quota" in last:
        status = "QUOTA"
    no_progress = status == "OK" and job.get("plan") and not job.get("readonly") and job.get("kind") not in ("verify", "investigate") \
        and not job_progressed(root, head0, texts + task_out, job)  # exit 0 แต่ไม่มี commit/DONE (เช่น worker หยุดถามผู้ใช้) = ยังไม่ได้ทำงาน
    return {"status": status, "rc": rc, "mins": (time.time() - t0) / 60, "tools": tools, "no_progress": no_progress,
            "head0": head0, "head1": _git(root, "rev-parse", "HEAD"), "session": session, "errors": errors, "stderr": errtxt.strip()[-600:], "last": last,
            "denied": denied, "perm_denied": perm, "recent": recent[-5:]}


def perm_denials(errtxt: str, tool_denied: list[str]) -> list[dict]:
    """รายการสิทธิ์ที่ opencode ปฏิเสธเอง: จาก stderr (ชนิด + path) · ไม่มีใน stderr (เช่นถูกปฏิเสธใน subagent) = ใช้ tool error แทน"""
    out = []
    for m in PERM_REQ_RE.finditer(errtxt):
        it = {"kind": m.group(1), "path": m.group(2).strip()}
        if it not in out:
            out.append(it)
    if not out:
        out = [{"kind": "tool", "path": t} for t in dict.fromkeys(tool_denied)]
    return out[:20]


def said_done(text: str) -> bool:
    """มี DONE ที่ไม่ได้ถูกปฏิเสธไหม — "NOT DONE" / "ยังไม่ DONE" / "ไม่ได้ DONE" / "ไม่ DONE" ไม่นับ"""
    for m in re.finditer(r"\bDONE\b", text):
        start = text.rfind("\n", 0, m.start()) + 1
        prev = text[start:m.start()].rstrip(" \t\r\n*_\"'")
        if prev.lower().endswith("not") or prev.endswith(("ยังไม่", "ไม่ได้", "ไม่")):
            continue
        return True
    return False


def job_progressed(root: Path, head0: str, outputs: list[str], job: dict | None = None) -> bool:
    """งานสำเร็จบางส่วนไหม: มี commit ของงานนี้ (ข้อความระบุ T-xx ที่อยู่ในแผน หรือแตะไฟล์แผน) หรือ worker/subagent รายงาน DONE
    (flash.md ให้ worker ตอบ `DONE`/`FAIL`) · commit ของ session อื่นในโปรเจกต์เดียวกันไม่นับ"""
    head1 = _git(root, "rev-parse", "HEAD")
    if head0 and head1 and head0 != head1:
        plan = (job or {}).get("plan")
        if not plan:
            return True
        match = task_matcher((job or {}).get("tasks", ""))
        if match is None:  # อ่านงานในแผนไม่ได้ = ถือว่ามีผลงาน (พฤติกรรมเดิม)
            return True
        for msg in _git(root, "log", "--format=%B%x00", f"{head0}..{head1}").split("\x00"):
            if any(match(t) for t in re.findall(r"T-\d+[A-Za-z]*", msg)):
                return True
        if _git(root, "log", "--format=", "--name-only", f"{head0}..{head1}", "--", plan):
            return True
    return any(said_done(t) for t in outputs)


def unverified_reasons(job: dict, res: dict) -> list[str]:
    """เหตุที่ผล OK ยังไม่ยืนยัน (ไม่มีหลักฐานงาน) — ว่าง = OK จริง"""
    out = []
    if res.get("no_progress"):
        out.append("ไม่มี commit ของงานและไม่มีคำว่า DONE")
    if job.get("readonly") and job.get("modified"):
        out.append("งานอ่านอย่างเดียวแต่ไฟล์ในโปรเจกต์เปลี่ยน")
    if job.get("kind") == "investigate":
        cites = job.get("citations") or {}
        bad = cites.get("bad") or []
        if bad:
            out.append(f"ผู้สืบอ้างเลขไฟล์:บรรทัดผิด {len(bad)} จุด")
        elif not cites.get("ok"):
            out.append("ผู้สืบไม่อ้างเลขไฟล์:บรรทัดเลย")
    return out


# ---------- คำสั่ง ----------
PLAN_SOFT = (300, 100, 30)  # (บรรทัดทั้งแผน, บรรทัดโค้ดใน ``` รวม, บล็อกโค้ดเดียวยาวสุด) เกิน = เตือน
PLAN_HARD = (600, 200, 60)  # เกิน = ปฏิเสธ (แผนใหญ่ = คนวางแผนเขียนโค้ดแทน Flash ไปแล้ว → เปลี่ยนเป็นสเปก/แบ่งแผน · ไม่มีทางลัด)
APPENDIX_RE = re.compile(r"^#{1,6}\s.*(ภาคผนวก|คัดลอกตรงตัว|โค้ดเต็ม|appendix|full code|verbatim)", re.I | re.M)
APPENDIX_CODE_MAX = 20  # หัวข้อภาคผนวกที่มีโค้ดรวมเกินนี้ = Claude เขียนโค้ดให้ Flash วาง → ปฏิเสธ


def plan_blocks(text: str) -> list[tuple[int, int]]:
    """บล็อกโค้ด ``` / ~~~ ในแผน → [(บรรทัดเริ่ม (1-based), จำนวนบรรทัดในบล็อก)] — fence ปิดต้องเป็นตัวเดียวกันและยาวไม่น้อยกว่า"""
    out, fence, start, n = [], "", 0, 0
    for i, ln in enumerate(text.splitlines(), 1):
        m = re.match(r"\s*(`{3,}|~{3,})", ln)
        if not fence and m:
            fence, start, n = m.group(1), i, 0
        elif fence and m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not ln.strip()[len(m.group(1)):].strip():
            out.append((start, n))
            fence = ""
        elif fence:
            n += 1
    if fence:
        out.append((start, n))
    return out


def plan_size(text: str) -> tuple[int, int]:
    """(จำนวนบรรทัดทั้งแผน, จำนวนบรรทัดใน code block รวม)"""
    return len(text.splitlines()), sum(n for _, n in plan_blocks(text))


def plan_lint(text: str) -> tuple[list[str], list[str]]:
    """กติกา "แผน = สเปก ไม่ใช่โค้ด" → (เหตุปฏิเสธ, คำเตือน)
    ปฏิเสธ: แผน > PLAN_HARD บรรทัด · โค้ดรวม > PLAN_HARD · บล็อกเดียว > PLAN_HARD (= โค้ดสำเร็จรูปให้ Flash วาง) ·
    หัวข้อ "ภาคผนวก/คัดลอกตรงตัว/appendix" ที่มีโค้ดรวม > APPENDIX_CODE_MAX บรรทัด · เตือน: เกิน PLAN_SOFT"""
    lines = text.splitlines()
    blocks = plan_blocks(text)
    n, code = len(lines), sum(b for _, b in blocks)
    big = max(blocks, key=lambda b: b[1]) if blocks else (0, 0)
    errs, warns = [], []
    if n > PLAN_HARD[0]:
        errs.append(f"แผน {n} บรรทัด (เพดาน {PLAN_HARD[0]}) → แบ่งเป็นหลายแผน/หลายรอบ")
    if code > PLAN_HARD[1]:
        errs.append(f"โค้ดใน ``` รวม {code} บรรทัด (เพดาน {PLAN_HARD[1]}) → โค้ดใหม่ยาวเขียนเป็นสเปก ให้ Flash เขียนเอง")
    if big[1] > PLAN_HARD[2]:
        errs.append(f"บล็อกโค้ดเดียวยาว {big[1]} บรรทัด (บรรทัด {big[0]} · เพดาน {PLAN_HARD[2]}) = โค้ดสำเร็จรูปให้ Flash วาง → เปลี่ยนเป็นสเปก (จุดเสียบ · ชื่อ/พารามิเตอร์ · พฤติกรรม · เทสต์)")
    heads = [(i, ln) for i, ln in enumerate(lines, 1) if APPENDIX_RE.match(ln)]
    for i, ln in heads:
        level = len(ln) - len(ln.lstrip("#"))
        end = next((j for j, l2 in enumerate(lines[i:], i + 1) if re.match(r"#{1,%d}\s" % level, l2)), n + 1)
        inside = sum(b for s, b in blocks if i < s < end)
        if inside > APPENDIX_CODE_MAX:
            errs.append(f"หัวข้อ `{ln.strip()[:60]}` (บรรทัด {i}) มีโค้ด {inside} บรรทัด → ภาคผนวกโค้ด = Claude ทำงานแทน Flash · ลบออก แล้วใส่สเปกในบล็อก T-xx แทน")
    if not errs and (n > PLAN_SOFT[0] or code > PLAN_SOFT[1] or big[1] > PLAN_SOFT[2]):
        warns.append(f"แผน {n} บรรทัด · โค้ดรวม {code} · บล็อกยาวสุด {big[1]} (แนะนำ ≤{PLAN_SOFT[0]}/{PLAN_SOFT[1]}/{PLAN_SOFT[2]}) — โค้ดยาวควรเป็นสเปกให้ Flash เขียนเอง")
    return errs, warns


def plan_has_history(root: Path, plan: str) -> bool:
    """แผนนี้เคยถูกส่งผ่านคิวนี้แล้วไหม (รอบแก้ T-xxR ของแผนเก่าที่ใหญ่เกินกติกาใหม่ ให้ผ่านพร้อมเตือน)"""
    return any(os.path.normcase(j.get("project", "")) == os.path.normcase(str(root)) and j.get("plan") == plan
               and j.get("kind", "work") == "work" and j.get("status") not in ("queued", "busy", "queue_timeout")
               for j in jobs())


# ---------- ตรวจแผนพิการก่อนส่ง Flash (เชิงกลไก ไม่ใช้โมเดล) ----------
# alias ในตัวของ PowerShell ที่ชื่อชนคำสั่ง/ชื่อที่คนวางแผนมักตั้งใจหมายถึงอย่างอื่น (sc = Set-Content ไม่ใช่ sc.exe · ls -la พัง ฯลฯ)
PS_ALIASES = {"sc": "Set-Content", "r": "Invoke-History", "h": "Get-History", "ls": "Get-ChildItem", "cat": "Get-Content",
              "dir": "Get-ChildItem", "cp": "Copy-Item", "mv": "Move-Item", "rm": "Remove-Item", "rmdir": "Remove-Item",
              "del": "Remove-Item", "ps": "Get-Process", "kill": "Stop-Process", "sort": "Sort-Object", "curl": "Invoke-WebRequest",
              "wget": "Invoke-WebRequest", "diff": "Compare-Object", "man": "help", "where": "Where-Object", "type": "Get-Content",
              "echo": "Write-Output", "gc": "Get-Content", "gi": "Get-Item", "gl": "Get-Location", "gp": "Get-ItemProperty",
              "gm": "Get-Member", "gu": "Get-Unique", "gv": "Get-Variable", "ni": "New-Item", "sl": "Set-Location",
              "sp": "Set-ItemProperty", "sv": "Set-Variable", "si": "Set-Item", "iwr": "Invoke-WebRequest", "irm": "Invoke-RestMethod",
              "iex": "Invoke-Expression", "fc": "Format-Custom", "fl": "Format-List", "ft": "Format-Table", "fw": "Format-Wide",
              "lp": "Out-Printer", "nv": "New-Variable", "ri": "Remove-Item", "rv": "Remove-Variable", "md": "mkdir", "rd": "Remove-Item"}
FILE_EXTS = set("""c cc cpp cxx h hh hpp hxx inl ipp cs vb fs py pyw pyi js mjs cjs ts tsx jsx vue svelte java kt kts go rs rb php pl lua
swift m mm scala sh bash zsh ps1 psm1 psd1 bat cmd md markdown txt rst json jsonc yaml yml toml ini cfg conf xml xsd xaml html htm css scss
less sql csv tsv rc def sln vcxproj filters csproj props targets cmake mk mak gradle lock env gitignore glsl hlsl fx shader nif dds tga png
jpg jpeg gif bmp ico svg wav ogg mp3 dll exe lib pdb proto graphql tf hcl dockerfile log""".split())
LABEL_RE = re.compile(r"(?<![\u0E00-\u0E7F\w])\**(ก่อน|หลัง)\**(?:\s*\([^()\n]*\))?\s*[:：]")
MULTI_OK_RE = re.compile(r"replace_all|ทุกที่|ทั้งหมดที่|หลายที่")  # แผนบอกเองว่าแก้หลายที่ (ไม่ระบุจำนวน)
MULTI_N_RE = re.compile(r"(\d+|สอง|สาม)\s*ที่")  # "มี 2 ที่" / "ต้องเจอ 3 ที่พอดี" / "ทั้งสองที่" → จำนวนที่ต้องเจอ
NEW_AFTER_RE = re.compile(r"^[^`]*?(สร้างใหม่|ไฟล์ใหม่|\(ใหม่\)|ใหม่\b|\bnew\b|ถ้ามี)", re.I)  # ไฟล์ใหม่ / ไม่บังคับ
SCOPE_RE = re.compile(r"ตัวหา|เลือกที่อยู่ใน|ถ้าเจอหลายที่|\(\s*ใน[\s`]")  # anchor มีขอบเขตกำกับ (ใน `ฟังก์ชัน` ...) → เจอหลายที่ = เตือน
NEW_BEFORE_RE = re.compile(r"(สร้างใหม่|ไฟล์ใหม่|ใหม่|new)\s*\**\s*[:：]?\s*\**\s*$", re.I)
NEW_LINE_RE = re.compile(r"สร้าง|เพิ่มไฟล์|ไฟล์ใหม่|\bcreate[sd]?\b|\bnew file\b|\badd(?:s|ed)? (?:a )?(?:new )?file", re.I)  # บรรทัดที่พูดถึงการสร้างไฟล์ → path ที่ยังไม่มีในบรรทัดนั้นถือเป็นไฟล์ใหม่ (ไม่ต้องเขียน "(ใหม่)" ต่อท้ายทุกตัว)


def _plan_path_tok(tok: str, root: Path | None = None) -> str:
    """`token` ที่ดูเป็น path ไฟล์ (มี / หรือ \\ หรือนามสกุลที่รู้จัก) → path แบบ / · ไม่ใช่ = """""
    t = re.sub(r":\d+(-\d+)?$", "", tok.strip().strip("~,;()\"'*"))
    if not t or " " in t or not PATHISH_RE.match(t) or any(c in t for c in "*?<>") or t.startswith(("-", "http:", "https:")):
        return ""
    base = re.split(r"[/\\]", t.rstrip("/\\"))[-1]
    ext = base.rsplit(".", 1)[-1].lower() if "." in base[1:] else ""
    if not (("/" in t or "\\" in t) and re.search(r"[A-Za-z]", base) or ext in FILE_EXTS) or t[0].isdigit():
        return ""
    p = Path(t)
    if p.is_absolute() or re.match(r"[A-Za-z]:", t):
        if not root:
            return ""
        try:
            t = p.relative_to(root).as_posix()
        except ValueError:
            return ""
    t = t.replace("\\", "/")
    return t[2:] if t.startswith("./") else t


def _plan_tasks(text: str):
    """แยกบล็อกงาน T-xx: [(id, checked, [(lineno, line), ...])] — จบบล็อกที่หัวงานถัดไป / ## / ---"""
    out, cur, fence = [], None, ""
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"\s*(`{3,}|~{3,})", line)
        if m and not fence:
            fence = m.group(1)
        elif m and fence and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
            fence = ""
        elif not fence:
            tm = TASK_MARK_RE.match(line)
            if tm:
                cur = (tm.group(1), bool(re.match(r"\s*[-*]\s*\[[xX]\]", line)), [])
                out.append(cur)
            elif line.startswith("## ") or line.strip() == "---":
                cur = None
        if cur:
            cur[2].append((i, line))
    return out


def _snippets(lines):
    """ก่อน/หลัง ในบล็อกงาน → [(label, lineno, ข้อความบรรทัดป้าย, เนื้อโค้ด)] (แบบ `inline` หรือ code block บรรทัดถัดไป)"""
    out, k = [], 0
    while k < len(lines):
        no, line = lines[k]
        m = LABEL_RE.search(line)
        k += 1
        if not m or re.match(r"\s*(`{3,}|~{3,})", line):
            continue
        rest = line[m.end():]
        im = re.match(r"\s*(`+)(.+?)\1", rest)  # ข้อความบรรยายก่อน backtick (เช่น "ก่อน: ไฟล์ปัจจุบัน 132 บรรทัด") = ไม่ใช่ anchor
        if im:
            code = im.group(2).strip()
            if "\\n" in code:  # inline ที่เขียน \n \t แทนขึ้นบรรทัด/tab
                code = code.replace("\\n", "\n").replace("\\t", "\t")
            out.append((m.group(1), no, line, code))
            continue
        if rest.strip():
            continue
        j = k
        while j < len(lines) and not lines[j][1].strip():
            j += 1
        fm = re.match(r"(\s*)(`{3,}|~{3,})", lines[j][1]) if j < len(lines) else None
        if not fm:
            continue
        ind, fence, body = len(fm.group(1)), fm.group(2), []
        j += 1
        while j < len(lines):
            ln = lines[j][1]
            cm = re.match(r"\s*(`{3,}|~{3,})\s*$", ln)
            if cm and cm.group(1)[0] == fence[0] and len(cm.group(1)) >= len(fence):
                break
            body.append(ln[ind:] if ln[:ind].strip() == "" else ln.lstrip())
            j += 1
        out.append((m.group(1), no, line, "\n".join(body)))
        k = j + 1
    return out


def _lenient(s: str) -> str:
    return "\n".join(x.strip() for x in s.replace("\r\n", "\n").split("\n") if x.strip())


class PlanSource:
    """ไฟล์ของโปรเจกต์ ณ rev (git) หรือในโฟลเดอร์ (ไม่ใช่ git) — ให้ตรวจแผนเทียบของจริง"""

    def __init__(self, root: Path, rev: str = ""):
        self.root, self.rev, self.cache = root, rev, {}
        if rev:
            r = run_timeout(["git", "-C", str(root), "ls-tree", "-r", "-z", "--name-only", rev], 60, text=False)
            if r.returncode != 0:
                raise ValueError(f"อ่าน {rev} ไม่ได้" + (" (หมดเวลา)" if r.returncode == 124 else ""))
            files = [x.decode("utf-8", "replace") for x in r.stdout.split(b"\0") if x]
        else:
            files = []
            for dp, dns, fns in os.walk(root):
                dns[:] = [d for d in dns if d not in (".git", "node_modules", ".tmp", "__pycache__", ".venv")]
                files += [Path(dp, f).relative_to(root).as_posix() for f in fns]
                if len(files) > 200_000:
                    break
        self.files = {f.lower(): f for f in files}
        self.dirs = {d.lower() for f in files for d in (f.rsplit("/", n)[0] for n in range(1, f.count("/") + 1))}
        self.bases: dict[str, list[str]] = {}
        for f in files:
            self.bases.setdefault(f.rsplit("/", 1)[-1].lower(), []).append(f)

    def find(self, p: str) -> str:
        return self.files.get(p.lower().rstrip("/"), "") or (p if p.rstrip("/").lower() in self.dirs else "")

    def read(self, p: str) -> str:
        if p not in self.cache:
            if self.rev:
                r = run_timeout(["git", "-C", str(self.root), "show", f"{self.rev}:{p}"], 30, text=False)
                data = r.stdout if r.returncode == 0 else b""
            else:
                try:
                    data = (self.root / p).read_bytes()
                except OSError:
                    data = b""
            self.cache[p] = data.decode("utf-8-sig", "replace").replace("\r\n", "\n")
        return self.cache[p]


SKILL_LINE_RE = re.compile(r"\s*[-*]?\s*\**(?:skills?|สกิล)\**\s*[:：]\s*(.*)", re.I)


def plan_skill_names(line: str) -> list[str]:
    """บรรทัด `skill: a, b` ในบล็อกงาน (ระดับงาน · ใส่เฉพาะชื่อ) → ['a', 'b'] · `-`/ไม่มี/<placeholder> = ว่าง"""
    m = SKILL_LINE_RE.match(line)
    if not m:
        return []
    val = re.sub(r"<[^>\n]*>", " ", m.group(1)).replace("`", " ")
    return [n for n in re.findall(r"[A-Za-z0-9][\w.-]*", val) if n.lower() not in ("none", "no")]


def skill_exists(name: str, src: "PlanSource") -> bool:
    """skill ที่ชื่อตรงโฟลเดอร์ใน skills/ ของโปรเจกต์ (git ของ rev ที่ตรวจ หรือบนดิสก์ เผื่อ junction ที่ไม่ได้ track) หรือส่วนกลางของผู้ใช้"""
    rels = [f"{d}/skills/{name}/SKILL.md" for d in (".opencode", ".claude")]
    if any(src.find(r) or (src.root / r).is_file() for r in rels):
        return True
    home = Path.home()
    return any((home / d / "skills" / name / "SKILL.md").is_file() for d in (".claude", ".config/opencode", ".agents"))


def plan_precheck(text: str, tasks: str, src: PlanSource) -> tuple[list[str], list[str]]:
    """ตรวจงาน T-xx ที่สั่ง (ยังไม่ติ๊ก) → (ข้อผิด, คำเตือน)
    ผิด: path ในหัวงาน/บรรทัด "ไฟล์" ไม่มีจริง (ยกเว้นไฟล์ที่แผนบอกว่าสร้างใหม่) · ข้อความ "ก่อน:" เจอในไฟล์ 0 ครั้ง/หลายครั้ง
    เตือน: คำสั่งใน ยืนยัน/แดง/เขียว ขึ้นต้นด้วย alias ในตัวของ PowerShell · function ในโค้ดของแผนตั้งชื่อชน alias · บรรทัด `skill:` ชื่อไม่ตรง skill ที่มีจริง"""
    match = task_matcher(tasks)
    errs, warns = [], []
    if not match:
        return errs, warns
    blocks = _plan_tasks(text)
    is_file_line = lambda ln: bool(re.match(r"\s*[-*]?\s*\**ไฟล์\**\s*[:：]", ln))
    # ไฟล์ที่ทั้งแผนบอกว่าสร้างใหม่ (งานก่อนหน้าสร้าง งานหลังแก้ต่อได้)
    new_files: set[str] = set()
    task_files: dict[str, list[tuple[int, str, str]]] = {}
    for tid, _, lines in blocks:
        for idx, (no, line) in enumerate(lines):
            if idx and not is_file_line(line):
                continue
            parts = re.split(r"`([^`\n]+)`", line)
            for p in range(1, len(parts), 2):
                tok = parts[p].strip()  # `คำสั่ง ที่มี ช่องว่าง` ไม่ใช่ path
                path = _plan_path_tok(tok, src.root)
                if not path:
                    continue
                task_files.setdefault(tid, []).append((no, tok, path))
                if NEW_AFTER_RE.match(parts[p + 1]) or NEW_BEFORE_RE.search(parts[p - 1]) or (NEW_LINE_RE.search(line) and not src.find(path)):
                    new_files.add(path.lower())
    afters = [(no, _lenient(code)) for _, _, lines in blocks for lab, no, _, code in _snippets(lines) if lab == "หลัง"]

    def resolve(tok_path: str, tid: str) -> str:
        """path ในบรรทัดก่อน: (มักเป็นแค่ชื่อไฟล์) → path จริงใน repo · "" = ไม่รู้ว่าไฟล์ไหน/ไม่มี"""
        if "/" in tok_path:
            return src.find(tok_path)
        mine = [p for _, _, p in task_files.get(tid, []) if p.rsplit("/", 1)[-1].lower() == tok_path.lower()]
        if len(mine) == 1:
            return src.find(mine[0])
        hits = src.bases.get(tok_path.lower(), [])
        return src.find(tok_path) or (hits[0] if len(hits) == 1 else "")

    for tid, checked, lines in blocks:
        if checked or not match(tid):
            continue
        for no, tok, path in task_files.get(tid, []):
            if path.lower() in new_files or src.find(path):
                continue
            if "/" not in path and src.bases.get(path.lower()):
                continue  # ชื่อไฟล์เปล่า ๆ ที่มีอยู่ใน repo
            hint = src.bases.get(path.rsplit("/", 1)[-1].lower(), [])
            hint = f" (หรือหมายถึง {', '.join(hint[:3])}?)" if hint else ""
            errs.append(f"บรรทัด {no} ({tid}): ไม่พบไฟล์ `{tok}`{hint} — ถ้าเป็นไฟล์ใหม่ให้เขียน (ใหม่) ต่อท้าย")
        heads = [p for _, _, p in task_files.get(tid, [])]
        prev = {no: ln for (no, _), (_, ln) in zip(lines[1:], lines)}  # บรรทัดก่อนป้าย (มักมีคำกำกับขอบเขต)
        for lab, no, line, code in _snippets(lines):
            if lab != "ก่อน" or not code.strip() or re.fullmatch(r"<[^>\n]*>", code.strip()):
                continue
            pre = line[:LABEL_RE.search(line).start()]
            cand = [_plan_path_tok(t, src.root) for b in re.findall(r"`([^`\n]+)`", pre) for t in b.split()]
            cand = [c for c in cand if c]
            if cand:
                tokp = cand[-1]
            elif len(heads) == 1:
                tokp = heads[0]
            else:
                continue  # บอกไม่ได้ว่าไฟล์ไหน → ไม่ตัดสิน
            if tokp.lower() in new_files or any(h.lower() in new_files and h.rsplit("/", 1)[-1].lower() == tokp.rsplit("/", 1)[-1].lower() for h in heads):
                continue
            real = resolve(tokp, tid)
            if not real or real.lower() not in src.files:
                continue  # ไฟล์หาไม่เจอ = รายงานในข้อ path แล้ว
            body = src.read(real)
            exact = "\n".join(x.rstrip() for x in code.split("\n")).strip("\n")
            n = "\n".join(x.rstrip() for x in body.split("\n")).count(exact) if exact else 0
            if n == 0:
                n = _lenient(body).count(_lenient(code))
            nm = MULTI_N_RE.search(line)
            want = ({"สอง": 2, "สาม": 3}.get(nm.group(1)) or int(nm.group(1))) if nm else 1
            if n == want or (n > 1 and MULTI_OK_RE.search(line)):
                continue
            if n == 0 and any(ano < no and _lenient(code) in atext for ano, atext in afters):
                continue  # ข้อความนี้มาจาก "หลัง:" ของงานก่อนหน้าในแผนเดียวกัน
            first = exact.split("\n")[0].strip()[:80]
            if n > want and SCOPE_RE.search(line[:LABEL_RE.search(line).end()] + " " + prev.get(no, "")):
                warns.append(f"บรรทัด {no} ({tid}): ข้อความ ก่อน: ใน {real} เจอ {n} ที่ (แผนกำกับขอบเขตไว้ · Flash ต้องเลือกเอง) — `{first}`")
                continue
            why = "ไม่เจอ (anchor เก่า/ผิด · branch หลักเปลี่ยนแล้ว?)" if n == 0 else (f"เจอ {n} ที่ (กำกวม · ขยาย anchor ให้ไม่ซ้ำ หรือเขียน replace_all ถ้าตั้งใจแก้ทุกที่)" if want == 1
                                                       else f"เจอ {n} ที่ แต่แผนบอก {want} ที่")
            errs.append(f"บรรทัด {no} ({tid}): ข้อความ ก่อน: ใน {real} {why} — `{first}`")
        for no, line in lines:
            if not re.match(r"\s*[-*]?\s*\**(ยืนยัน|แดง|เขียว)", line):
                continue
            for cmd in re.findall(r"`([^`\n]+)`", line):
                for seg in re.split(r";|&&|\|\|", cmd):
                    w = seg.strip().split(" ", 1)[0].lower() if seg.strip() else ""
                    if w in PS_ALIASES:
                        warns.append(f"บรรทัด {no} ({tid}): คำสั่ง `{seg.strip()[:60]}` ขึ้นต้นด้วย `{w}` = alias ในตัวของ PowerShell "
                                     f"({PS_ALIASES[w]}) — ใช้ชื่อเต็ม/ชื่อ .exe")
        for no, line in lines:
            for name in plan_skill_names(line):
                if not skill_exists(name, src):
                    warns.append(f"บรรทัด {no} ({tid}): ไม่พบ skill `{name}` (.opencode/skills · .claude/skills ของโปรเจกต์ · skill ส่วนกลาง) "
                                 f"— Flash โหลดไม่ได้ ตรวจชื่อให้ตรงโฟลเดอร์ใน skills/")
    for no, line in enumerate(text.splitlines(), 1):
        fm = re.match(r"\s*function\s+([\w-]+)", line, re.I)
        if fm and fm.group(1).lower() in PS_ALIASES:
            warns.append(f"บรรทัด {no}: function {fm.group(1)} ชื่อชน alias ในตัวของ PowerShell ({PS_ALIASES[fm.group(1).lower()]}) "
                         f"— alias ชนะ function จะไม่ถูกเรียก → ตั้งชื่ออื่น")
    return errs, warns


def cmd_run(a) -> int:
    if isinstance(a.message, list):  # investigate รับบรีฟเป็นหลายคำ
        a.message = " ".join(a.message).strip()
    if isinstance(a.tasks, list):  # run/verify รับ tasks ได้หลาย token: "T-00 T-02" · "T-00..T-02, T-05" → "T-00,T-02" / "T-00..T-02,T-05"
        a.tasks = ",".join(x for x in re.split(r"[,\s]+", " ".join(a.tasks)) if x)
    if not a.message and not (a.plan and a.tasks):
        print("ต้องมี <plan> <tasks> หรือ --message")
        return 1
    start = Path(a.project or os.getcwd())
    if getattr(a, "detach", False):  # ผู้สั่งที่ไม่มี background shell (เช่น opencode) → ส่งแล้วคืนทันที · ผลงานจบอยู่ใน inbox (flashq inbox)
        rest = [x for x in sys.argv[1:] if x != "--detach"] + ["--submitter", "detach"]
        r = spawn_run(([sys.argv[0]] if FROZEN else [sys.executable, sys.argv[0]]) + rest, str(start))
        print(r["message"])
        if r.get("job"):
            print(f"FLASH_RUN=DETACHED job={r['job']} — จบแล้วดูผลด้วย: {run_cmd()} inbox")
        elif r.get("ok"):
            print(f"FLASH_RUN=DETACHED job=? — ดู log ส่งงาน {r['out']} · ผลด้วย: {run_cmd()} inbox")
        return 0 if r.get("ok") else 1
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
            if run_timeout(["git", "-C", str(root), "cat-file", "-e", f"{ref}:{plan}"], 30).returncode != 0:
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
        if (a.kind or "work") == "work":
            try:
                body = ((root / plan).read_text(encoding="utf-8", errors="replace") if (root / plan).exists()
                        else _git(root, "show", f"{cfg['remote']}/{cfg['main_branch']}:{plan}"))
            except OSError:
                body = ""
            errs, warns = plan_lint(body or "")
            n, code = plan_size(body or "")
            why = f"แผน {n} บรรทัด · โค้ดใน ``` {code} บรรทัด"
            if errs:
                fix_round = bool(a.tasks) and all(re.fullmatch(r"T-\d+R\d*", t.strip(), re.I) for t in re.split(r"[,\s]+", a.tasks.strip()) if t)                     and plan_has_history(root, plan)
                if fix_round:  # แผนเก่า (เคยส่งแล้ว) ที่สั่งเฉพาะรอบแก้ T-xxR → ผ่านพร้อมเตือน (ไม่งั้นแผนที่ค้างอยู่ติดหมด)
                    print(f"WARN: แผนใหญ่เกินกติกา ({why}) — ผ่านเพราะเป็นรอบแก้ของแผนที่เคยส่งแล้ว · แผนใหม่ต้องเป็นสเปก: " + " · ".join(errs), flush=True)
                else:
                    print(f"FLASH_RUN=FAIL แผนใหญ่เกิน ({why}) = คนวางแผนเขียนโค้ดแทน Flash ไปแล้ว → แก้แผนก่อนส่ง (/flash-plan §2 · ไม่มีทางลัด):")
                    for e in errs:
                        print(f"  - {e}")
                    return 1
            for w in warns:
                print(f"WARN: แผนใหญ่ ({w})", flush=True)
            if not getattr(a, "skip_precheck", False) and a.tasks:
                rev = (f"{cfg['remote']}/{cfg['main_branch']}" if cfg["require_plan_in_remote"] else "HEAD") if is_git else ""
                try:
                    perrs, pwarns = plan_precheck(body or "", a.tasks, PlanSource(root, rev))
                except (ValueError, OSError) as e:
                    perrs, pwarns = [], [f"ตรวจแผนเทียบโค้ดไม่ได้ ({e}) → ข้าม"]
                for w in pwarns:
                    print(f"WARN: {w}", flush=True)
                if perrs:
                    print(f"FLASH_RUN=FAIL แผนพิการ {len(perrs)} จุด (เทียบ {rev or 'โฟลเดอร์โปรเจกต์'}) — แก้แผนแล้ว push ใหม่ · "
                          f"มั่นใจว่าแผนถูก → ใส่ --skip-precheck")
                    for e in perrs:
                        print(f"  - {e}")
                    return 1
        if is_git:  # /flash หยุดทันทีถ้า checkout ไม่อยู่บน main_branch → บอกสาเหตุจริงตรงนี้ แทนที่จะรอ NOSTART/FAIL
            br = run_timeout(["git", "-C", str(root), "branch", "--show-current"], 30).stdout.strip()
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
        title = f"flash-investigate {one_line(a.message, 40)}"
    else:
        title = f"flash-test {ts}" if a.message else f"flash {Path(plan).stem} {a.tasks}"
    title = one_line(title, 200)
    bad = cmd_shim_unsafe(exe, title, prompt, a.message or "")
    if bad:  # ไม่ปล่อยให้ opencode ได้คำสั่งที่ถูกตัดแล้วเงียบ 3 นาที × 2 รอบถึงรู้ว่า NOSTART
        print(f"FLASH_RUN=FAIL opencode ถูกเรียกผ่าน {exe[-1]} (cmd.exe) แต่บรีฟมีอักขระ {bad} ที่ cmd.exe ตีความเอง → ข้อความงานจะหายหรือเพี้ยน · "
              f"แก้: ตั้ง FLASHQ_OPENCODE เป็นไฟล์ opencode.exe ตัวจริง (npm: <npm>\\node_modules\\opencode-ai\\bin\\opencode.exe) หรือตัดอักขระเหล่านี้ออกจากบรีฟ")
        return 1
    worker_like = agent in ("", "flash-worker")
    # agent อื่น (ผู้ตรวจ/ผู้สำรวจ) ใช้โมเดลที่ตั้งไว้ใน agent นั้นเอง — ไม่ทับด้วยโมเดลของ flash-worker
    model = a.model or (configured_model() if worker_like else agent_model(agent))
    job = {"id": jid, "project": str(root), "plan": plan, "tasks": a.tasks or "", "message": a.message or "",
           "kind": kind, "agent": agent, "prompt": prompt, "readonly": bool(a.readonly or kind in AGENT_KINDS),
           "title": title, "model": model, "status": "queued", "pid": os.getpid(),
           "pid_start": proc_start(os.getpid()), "created": now(), "qv": QUEUE_VERSION,
           "claude_session": os.environ.get("CLAUDE_CODE_SESSION_ID", ""), "claude_host": os.environ.get("CLAUDE_CODE_HOST_SESSION_ID", ""),
           "submitter": getattr(a, "submitter", "") or ""}
    save_job(job)

    got = acquire(job, a.wait_min, a.no_wait)
    if got != "ok":
        job.update(status="busy" if got == "busy" else "queue_timeout", finished=now())
        save_job(job)
        notify_job(job, job["status"].upper())
        return 2 if got == "busy" else 3

    res = {"status": "FAIL", "rc": -1}
    try:
        job.update(status="running", started=now())  # job["slot"] ตั้งโดย acquire
        save_job(job)
        print(f"SLOT ช่อง {job.get('slot', 1)} (max_parallel={max_parallel()})", flush=True)
        attach = LIVE_URL if a.attach == "live" else ("" if a.attach == "none" else a.attach)
        ext_dirs = external_dirs(cfg)
        env = {**os.environ, "OPENCODE_CONFIG_CONTENT": perm_config_content(ext_dirs)} if ext_dirs else None
        if attach == LIVE_URL and not ensure_live_server(exe, known_external_dirs(root, ext_dirs)):
            pidf = HOME / "live_server.pid"
            print(f"WARN: เปิด server 4096 ไม่ขึ้นใน 30 วิ → รันแยก (ดูสดไม่ได้) · log {HOME / 'live_server.log'} · pid "
                  f"{pidf.read_text(encoding='utf-8', errors='replace').strip() if pidf.exists() else '?'} (ค้าง = taskkill /PID <pid> /T /F แล้วสั่งใหม่)", flush=True)
            attach = ""
        if a.attach == "live" and attach == LIVE_URL:  # server เปิดค้างโหลดสิทธิ์ตอนเปิดครั้งเดียว — เห็นโฟลเดอร์ที่เพิ่งเพิ่มใน .flash.json ไม่ได้ → งานจะโดน DENIED หลังรันไปหลายนาที
            miss = perm_missing_on_server(ext_dirs, attach, root)
            if miss:
                print(f"PERM_FALLBACK: server {attach} ยังไม่อนุญาต external_dirs: {', '.join(miss)} (โหลดสิทธิ์ตอนเปิดครั้งเดียว) → รอบนี้รัน opencode แยกที่ได้สิทธิ์จาก .flash.json แทน "
                      f"(ดูสดในแอปไม่ได้) · อยากได้ดูสดรอบหน้า: ปิด server เมื่อไม่มีงานอื่นใช้อยู่ ให้เปิดใหม่เองตอนสั่งงานครั้งหน้า", flush=True)
                attach = ""
        job["attach"] = attach
        variant = variant_for(kind, a.variant, root)
        if variant:
            job["variant"] = variant
        save_job(job)
        for ln in perm_precheck(ext_dirs, attach, root):
            print(ln, flush=True)
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
            if variant:
                cmd += ["--variant", variant]
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
            res = run_once(job, cmd, root, attach, timeout_min, a.no_open, attempt, stall_min, stall_floor, float(cfg.get("shell_idle_min") or 0), env,
                           model_wait=float(cfg.get("model_wait_min") or 0))
            if res.get("head0") and res.get("head1"):  # ช่วง commit ของงานนี้ (ทุกรอบรวมกัน) → flashq scope ใช้หา commit ของ T-xx โดยไม่พึ่งที่โมเดลจดใน §4
                job["head0"] = job.get("head0") or res["head0"]
                job["head1"] = res["head1"]
            if res.get("denied"):
                job["denied"] = (job.get("denied") or []) + res["denied"][:20]
            if res.get("perm_denied"):
                job["perm_denied"] = [x for x in (job.get("perm_denied") or []) + res["perm_denied"] if x][:20]
            if res["status"] == "TIMEOUT" and job.get("timeout_reason", "").startswith("STALL") and stall_retry > 0:  # ค้างเพราะ log เงียบ (มักเป็น request ไปโมเดลไม่ตอบ) → ลองใหม่ 1 ครั้ง · งานทำจริง /flash ข้ามงานที่ติ๊ก [x] แล้ว จึงต่อจากที่ค้างได้
                stall_retry -= 1
                if job["model"] and (not worker_like or not a.model):  # ค้างที่ผู้ให้บริการนี้ → รอบใหม่ย้ายไปผู้ให้บริการอื่นของโมเดลเดิม (ถ้ามี · ไม่แตะ opencode.json) · งานทำจริงที่ผู้ใช้ไม่ได้ระบุ --model เองก็ย้าย (เจอจริง 2026-10-21..23: STALL ซ้ำที่บัญชีเดิม)
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
        verdict = res.get("status")
        reasons = unverified_reasons(job, res) if verdict == "OK" else []
        if reasons:
            job["unverified"] = reasons
            verdict = "OK_UNVERIFIED"
        job.update(status=res["status"].lower(), result=verdict, rc=res.get("rc"),
                   finished=now(), last=(res.get("last") or (f"NOSTART: {job['nostart_diag'][-1]}" if res.get("status") == "NOSTART" and job.get("nostart_diag") else ""))[-1500:])
        save_job(job)
        release(job)
        notify_job(job, verdict, res.get("mins") or 0.0)

    print(f"FLASH_RUN={verdict} exit={res['rc']} เวลา={res['mins']:.1f} นาที tool={res['tools']} "
          f"session={res['session']} job={jid}")
    if job.get("unverified"):
        print("WARN: ผล OK ยังไม่ยืนยัน — " + " · ".join(job["unverified"]))
    print(f"desktop: โปรเจกต์ {root.name} > session '{title}'")
    if res.get("no_progress"):
        print("WARN: สถานะ OK แต่ไม่มี commit ใหม่และ worker ไม่รายงาน DONE → น่าจะหยุดถามหรือยังไม่ได้ทำงาน · อ่านสรุปท้ายแล้วตอบ/สั่งซ้ำ อย่าเชื่อ OK")
    if res["status"] == "NOSTART" and job.get("nostart_diag"):
        print(f"REASON: opencode ไม่เริ่มทำงาน (รอบแรกรอ {START_LIMIT_FIRST_SEC} วิ · รอบลองใหม่ {START_LIMIT_SEC} วิ) ทั้ง {len(job['nostart_diag'])} รอบ · รอบสุดท้าย: {job['nostart_diag'][-1]}")
    if res["status"] == "TIMEOUT":
        print(f"REASON: {job.get('timeout_reason', '')}")
        print("DIAG ก่อนถูกฆ่า (tool ล่าสุด): " + " | ".join(res.get("recent") or ["(ยังไม่เรียก tool เลย → โมเดล/ผู้ให้บริการอาจค้าง)"]))
        print("แนะนำ: เปิด log ดูท้ายไฟล์ · บรีฟกว้างเกิน/ไฟล์ใหญ่เกิน → แบ่งงานให้เล็กลง · ผู้ให้บริการช้า → --model ตัวอื่น แล้วสั่งใหม่")
    if job.get("perm_denied"):
        for ln in perm_fix_lines(job["perm_denied"], partial=res["status"] != "DENIED"):
            print(ln)
    if job.get("denied"):
        print(f"RULE_DENIED: {len(job['denied'])} คำสั่งถูกกฎของ agent บล็อก (ไม่ใช่งานล้มเหลว · agent ต้องใช้ read/grep แทน): " + " | ".join(job["denied"][:5]))
    for e in res["errors"][-3:]:
        print("ERROR:", e)
    if res["stderr"]:
        print("STDERR(ท้าย):", res["stderr"])
    print("---- สรุปท้ายจาก opencode ----")
    print(res["last"][-2500:] if res["last"] else "(ไม่มีข้อความ)")
    return 0 if res["status"] == "OK" else 1


# ---------- นักทดสอบ (flashq qa) ----------
# หลักการ: flashq รันคำสั่งทดสอบเอง (ไม่ผ่านโมเดล) แล้วตัดสินจาก exit code จริง + ข้อความที่ต้องพบ (expect) — โมเดลบอกว่า "ผ่าน" ไม่นับ
# ล้ม → (เลือกได้) ให้ Flash อ่าน log แล้วอธิบายสาเหตุ · คำอธิบายนั้นไม่เปลี่ยนคำตัดสิน
# คำสั่งมาจาก .flash.json (qa.presets) หรือ --cmd ใน CLI เท่านั้น — หน้าเว็บ/โมเดลสั่งคำสั่งเองไม่ได้
QA_NAME_RE = re.compile(r"^[A-Za-z0-9][\w.-]{0,39}$")
QA_MAX_CMD = 2000
QA_LOG_CAP = 100 * 1024 * 1024   # log ของ 1 ชุดเกินนี้ = คำสั่งพ่นข้อความไม่หยุด → ฆ่า (กันดิสก์เต็ม)
QA_READ_CAP = 600 * 1024         # อ่านท้าย log แค่นี้ตอนตรวจ expect/ดึงบรรทัดสำคัญ
QA_ANALYZE_MIN = 10
QA_ADAPT_FLOOR_SEC = float(os.environ.get("FLASHQ_QA_ADAPT_FLOOR_SEC") or 300)  # ชุดที่ไม่ได้ตั้ง idle_min: log เคยขยับเป็นจังหวะแล้วเงียบเกิน max(ค่านี้, 6 × ช่วงเงียบนานสุดที่เห็น) = สงสัยค้าง
QA_FROZEN_SEC = float(os.environ.get("FLASHQ_QA_FROZEN_SEC") or 120)  # สงสัยแล้วต้องเห็นทั้งชุดโปรเซสของคำสั่ง CPU/I/O นิ่งสนิทเกินนี้ถึงฆ่า (ยังขยับ = ทำงานจริง เช่น build เงียบ ๆ ไม่ฆ่า)
QA_ADAPT_POLL_SEC = float(os.environ.get("FLASHQ_QA_ADAPT_POLL_SEC") or 30)
QA_LIVE_POLL_SEC = float(os.environ.get("FLASHQ_QA_LIVE_POLL_SEC") or 20)  # ทุกกี่วินาทีที่วัดชีพจรโปรเซสของชุดทดสอบให้หน้าเว็บ (อ่านตารางโปรเซส ~1-3 วิ)
QA_DEFAULT_RETRY = 1           # ชุดที่ล้มลองซ้ำ 1 รอบ (เหตุชั่วคราว เช่น ConnectionReset) · ผ่านเฉพาะรอบหลัง = FLAKY ไม่ใช่ PASS · ปิดด้วย retry: 0 / --retry 0
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
QA_KEY_RE = re.compile(r"^(?:FAILED|ERROR|FAIL)\b|AssertionError|^E {2,}|^Traceback|\b\d+ (?:passed|failed|errors?|skipped)\b|^Ran \d+ tests?|"
                       r"^(?:OK|FAILED) ?(?:\(|$)|\bnot ok\b|error\[E\d+\]|panicked at|^--- FAIL|BUILD FAILED|✖|✕|\bTests?:\s|\d+ failing|\berror:", re.I)


def qa_standalone_tests(root: Path) -> list[str]:
    """tests/test_*.py ที่เป็นสคริปต์รันตรง (มี `if __name__ == "__main__"` และไม่พึ่ง pytest) → รายชื่อเส้นทางเทียบรากโปรเจกต์ · ไม่มี = []"""
    out = []
    for p in sorted((root / "tests").glob("test_*.py"))[:40]:
        try:
            src = p.read_text(encoding="utf-8-sig", errors="replace")[:200_000]
        except OSError:
            continue
        if re.search(r"^\s*(?:import|from)\s+pytest\b", src, re.M) or not re.search(r"""__name__\s*==\s*["']__main__["']""", src):
            continue
        out.append(p.relative_to(root).as_posix())
    return out


def qa_browser_scripts(root: Path) -> list[str]:
    """tests/ui_*.py ที่ใช้ Playwright (สคริปต์ทดสอบหน้าเว็บแบบ headless รันตรงด้วย python) → เส้นทางเทียบรากโปรเจกต์ · ไม่มี = []"""
    out = []
    for p in sorted((root / "tests").glob("ui_*.py"))[:20]:
        try:
            src = p.read_text(encoding="utf-8-sig", errors="replace")[:200_000]
        except OSError:
            continue
        if re.search(r"^\s*(?:import|from)\s+playwright\b", src, re.M) or "from playwright" in src:
            out.append(p.relative_to(root).as_posix())
    return out


def qa_pytest_missing() -> bool:
    """python ที่อยู่ใน PATH ไม่มี pytest? (ใช้เตือนตอนแนะนำเท่านั้น · ตรวจไม่ได้ = False)"""
    exe = shutil.which("python")
    if not exe:
        return False
    try:
        return subprocess.run([exe, "-c", "import pytest"], capture_output=True, timeout=20).returncode != 0
    except (OSError, subprocess.SubprocessError):
        return False


def qa_detect(root: Path) -> list[dict]:
    """เดาว่าโปรเจกต์นี้ทดสอบด้วยอะไร — ใช้แค่แนะนำให้ผู้ใช้ใส่ใน .flash.json (ไม่รันเอง · คำสั่งที่เดาไม่เคยถูกรันโดยไม่มีคนยืนยัน)"""
    out: list[dict] = []

    def text(name: str) -> str:
        try:
            return (root / name).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return ""
    standalone = qa_standalone_tests(root)
    if (root / "pytest.ini").is_file() or (root / "conftest.py").is_file() or "pytest" in text("pyproject.toml") or "[tool:pytest]" in text("setup.cfg") \
            or ((root / "tests").is_dir() and not standalone):
        out.append({"name": "unit", "cmd": "python -m pytest -q", "expect": r"\d+ passed", "why": "พบ pytest / โฟลเดอร์ tests"})
    elif standalone:
        out.append({"name": "unit", "cmds": [f"python {p}" for p in standalone],
                    "why": f"tests/ มีสคริปต์ standalone {len(standalone)} ไฟล์ (ไม่ใช้ pytest · สำเร็จ/ล้มด้วย exit code) → แยกผลทีละไฟล์ · ถ้าต้องใช้ python ของโปรเจกต์อื่น (เช่น venv) ให้แก้ path ของ python เอง"})
    ui_scripts = qa_browser_scripts(root)
    if ui_scripts:
        out.append({"name": "ui", "cmds": [f"python {p}" for p in ui_scripts], "env_exit": 3,
                    "why": f"tests/ui_*.py ใช้ Playwright {len(ui_scripts)} ไฟล์ → ทดสอบหน้าเว็บด้วย Chrome headless (ไม่มีหน้าต่าง ไม่แย่งเมาส์) · env_exit 3 = ยังไม่ได้ลง playwright/เบราว์เซอร์ (ผล ENV ไม่ใช่โค้ดผิด) · ต้อง pip install playwright"})
    scripts = read_json(root / "package.json").get("scripts")
    if isinstance(scripts, dict) and scripts.get("test") and "no test specified" not in str(scripts["test"]):
        out.append({"name": "unit", "cmd": "npm test", "why": "package.json มี scripts.test"})
    if (root / "Cargo.toml").is_file():
        out.append({"name": "unit", "cmd": "cargo test", "why": "พบ Cargo.toml"})
    if (root / "go.mod").is_file():
        out.append({"name": "unit", "cmd": "go test ./...", "why": "พบ go.mod"})
    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        out.append({"name": "unit", "cmd": "dotnet test", "why": "พบ .sln/.csproj"})
    if re.search(r"^test\s*:", text("Makefile"), re.M):
        out.append({"name": "unit", "cmd": "make test", "why": "Makefile มีเป้าหมาย test"})
    seen, uniq = set(), []
    for x in out:  # ชื่อซ้ำ (เจอหลายระบบ) → ต่อท้ายเลขให้ใช้งานได้ทันที
        n, i = x["name"], 1
        while n in seen:
            i += 1
            n = f"{x['name']}{i}"
        seen.add(n)
        uniq.append(dict(x, name=n))
    return uniq


def qa_suggest_lines(root: Path) -> list[str]:
    found = qa_detect(root)
    if not found:
        return ["ยังเดาไม่ได้ว่าโปรเจกต์นี้ทดสอบด้วยอะไร → ใส่ qa.presets ใน .flash.json เอง หรือสั่งครั้งเดียวด้วย --cmd \"<คำสั่ง>\""]
    presets = {x["name"]: {k: v for k, v in x.items() if k in ("cmd", "cmds", "expect", "env_exit")} for x in found}
    lines = ["ที่เดาได้จากไฟล์ในโปรเจกต์ (ตรวจแล้วค่อยวางใน .flash.json — flashq ไม่รันคำสั่งที่เดาเอง):",
             "  " + json.dumps({"qa": {"presets": presets}}, ensure_ascii=False)] + [f"  - {x['name']}: {x['why']}" for x in found]
    if any("pytest" in str(x.get("cmd")) for x in found) and qa_pytest_missing():
        lines.append("  ⚠️ python ใน PATH ยังไม่มี pytest — ถ้าโปรเจกต์ใช้ python/venv ตัวอื่น ให้ใส่ path ของ python นั้นในคำสั่งแทน `python` (ไม่งั้นจะล้มเพราะไม่มี pytest)")
    return lines


def qa_spec(name: str, v, default_min: float) -> dict | str:
    """ตรวจ 1 ชุดทดสอบ → dict ที่ใช้รันได้ หรือข้อความผิดพลาด (ห้ามปล่อยค่าเพี้ยนไปถึงตอนรัน)"""
    if isinstance(v, str):
        v = {"cmd": v}
    if not isinstance(v, dict):
        return f"ชุดทดสอบ '{name}' ต้องเป็นข้อความคำสั่ง หรือ {{\"cmd\": \"...\"}}"
    cmd = str(v.get("cmd") or "").strip()
    if not cmd:
        return f"ชุดทดสอบ '{name}' ไม่มี cmd"
    if len(cmd) > QA_MAX_CMD or "\x00" in cmd or "\n" in cmd:
        return f"ชุดทดสอบ '{name}': cmd ต้องบรรทัดเดียว ยาวไม่เกิน {QA_MAX_CMD} ตัวอักษร"

    def num(key: str, dflt: float, lo: float, hi: float):
        raw = v.get(key)
        if raw in (None, ""):
            return dflt
        try:
            x = float(raw)
        except (TypeError, ValueError):
            return f"ชุดทดสอบ '{name}': {key} ต้องเป็นตัวเลข"
        return x if lo <= x <= hi else f"ชุดทดสอบ '{name}': {key} ต้องอยู่ระหว่าง {lo:g}-{hi:g}"
    timeout, idle, retry = num("timeout_min", default_min, 0.1, 1440), num("idle_min", 0, 0, 1440), num("retry", QA_DEFAULT_RETRY, 0, 3)
    for x in (timeout, idle, retry):
        if isinstance(x, str):
            return x
    expect = str(v.get("expect") or "")
    if expect:
        try:
            re.compile(expect)
        except re.error as e:
            return f"ชุดทดสอบ '{name}': expect ไม่ใช่ regex ที่ถูกต้อง ({e})"
    env_exit = v.get("env_exit")
    if env_exit in (None, ""):
        env_exit = []
    elif isinstance(env_exit, int) and not isinstance(env_exit, bool):
        env_exit = [env_exit]
    if not (isinstance(env_exit, list) and len(env_exit) <= 8
            and all(isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= 2147483647 for x in env_exit)):
        return f"ชุดทดสอบ '{name}': env_exit ต้องเป็นเลข exit code (1 ขึ้นไป) ไม่เกิน 8 ตัว เช่น [3, 5]"
    return {"name": name, "cmd": cmd, "cwd": str(v.get("cwd") or "."), "timeout_min": timeout, "idle_min": idle,
            "retry": int(retry), "expect": expect, "env_exit": sorted(set(env_exit))}


def qa_expand_cmds(name: str, v: dict, errs: list[str]) -> list[tuple[str, dict]]:
    """preset แบบ {"cmds": [คำสั่ง | {cmd, ...}], ...ตัวเลือกร่วม} → หลายชุดย่อย (ผล ผ่าน/ไม่ผ่านแยกทีละคำสั่ง) · ชื่อชุดย่อย = <ชื่อ>:<ชื่อไฟล์ .py> หรือ <ชื่อ>.<ลำดับ>"""
    items = v.get("cmds")
    if "cmd" in v:
        errs.append(f"ชุดทดสอบ '{name}': ใช้ cmd หรือ cmds อย่างใดอย่างหนึ่ง ไม่ใช่ทั้งสองอย่าง")
        return []
    if not isinstance(items, list) or not items or len(items) > 30:
        errs.append(f"ชุดทดสอบ '{name}': cmds ต้องเป็นรายการคำสั่ง 1-30 รายการ")
        return []
    shared = {k: x for k, x in v.items() if k != "cmds"}
    out, used = [], set()
    for i, it in enumerate(items, 1):
        sub = {**shared, **(it if isinstance(it, dict) else {"cmd": it})}
        cmd = str(sub.get("cmd") or "")
        m = re.findall(r"([\w.-]+)\.py\b", cmd)
        label = f"{name}:{m[-1]}" if m else f"{name}.{i}"
        if label in used:
            label = f"{name}.{i}"
        used.add(label)
        out.append((label, sub))
    return out


def qa_specs(cfg: dict, names: list[str], raw_cmds: list[str], root: Path) -> tuple[list[dict], list[str]]:
    """เลือกชุดทดสอบ: ชื่อจาก qa.presets (ไม่ระบุชื่อและไม่มี --cmd = ทุกชุด) + --cmd เฉพาะกิจ · คืน (ชุด, ข้อผิดพลาด)"""
    qa = cfg.get("qa") if isinstance(cfg.get("qa"), dict) else {}
    presets = qa.get("presets") if isinstance(qa.get("presets"), dict) else {}
    dmin = float(cfg.get("qa_timeout_min") or DEFAULTS["qa_timeout_min"])
    errs, specs = [], []
    want = list(dict.fromkeys(names))
    if not want and not raw_cmds:
        want = list(presets)
    todo = []
    for n in want:
        if n not in presets:
            errs.append(f"ไม่มีชุดทดสอบชื่อ '{n}' ใน .flash.json (qa.presets มี: {', '.join(presets) or 'ไม่มีเลย'})")
        elif not QA_NAME_RE.match(str(n)):
            errs.append(f"ชื่อชุดทดสอบ '{n}' ใช้ได้แค่ตัวอักษร/ตัวเลข _ . - (ยาวไม่เกิน 40)")
        else:
            todo.append((n, presets[n]))
    todo += [("adhoc" if i == 1 else f"adhoc{i}", {"cmd": c}) for i, c in enumerate(raw_cmds, 1)]
    expanded = []
    for n, v in todo:
        if isinstance(v, dict) and "cmds" in v:
            expanded += qa_expand_cmds(n, v, errs)
        else:
            expanded.append((n, v))
    todo = expanded
    for n, v in todo:
        s = qa_spec(n, v, dmin)
        if isinstance(s, str):
            errs.append(s)
        else:
            specs.append(s)
    rroot = root.resolve()
    for s in specs:  # cwd ต้องอยู่ในโปรเจกต์และมีจริง — ไม่ให้ชุดทดสอบเดินออกไปรันนอกโปรเจกต์
        d = (rroot / s["cwd"]).resolve()
        if not d.is_relative_to(rroot):
            errs.append(f"ชุดทดสอบ '{s['name']}': cwd '{s['cwd']}' อยู่นอกโปรเจกต์")
        elif not d.is_dir():
            errs.append(f"ชุดทดสอบ '{s['name']}': ไม่พบโฟลเดอร์ cwd '{s['cwd']}'")
    return specs, errs


def qa_preset_names(project: str) -> list[str]:
    """ชื่อชุดทดสอบที่ตั้งไว้ในโปรเจกต์ (อ่าน .flash.json ตรง ๆ ไม่เรียก git — หน้าเว็บเรียกถี่)"""
    qa = read_json(Path(project) / ".flash.json").get("qa") if project else None
    presets = qa.get("presets") if isinstance(qa, dict) else None
    return [n for n in presets if QA_NAME_RE.match(str(n))] if isinstance(presets, dict) else []


def qa_utf16(data: bytes, offset: int) -> str | None:
    """ข้อความ UTF-16 (PowerShell 5.1 เขียนไฟล์ด้วย `>` เป็น UTF-16 LE) → ข้อความ · ไม่ใช่ UTF-16 = None
    มี BOM = ชัวร์ · ไม่มี BOM (อ่านมาจากกลางไฟล์) = ศูนย์ไบต์ ≥ 5% และเกือบทั้งหมดอยู่ตำแหน่งคู่/คี่ตำแหน่งเดียวกัน
    offset = ตำแหน่งไบต์แรกของ data ในไฟล์ (คี่ = ต้องข้ามไบต์แรกให้ตรงขอบตัวอักษร 2 ไบต์)"""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    n = len(data)
    nul = data.count(b"\x00")
    if n < 4 or nul * 20 < n:
        return None
    even, odd = data[0::2].count(b"\x00"), data[1::2].count(b"\x00")
    if max(even, odd) * 10 < nul * 9:  # ปนกับข้อความธรรมดา = ไม่ใช่ UTF-16 ล้วน
        return None
    chunk = data[1:] if offset % 2 else data
    if offset % 2:
        even, odd = odd, even
    return chunk.decode("utf-16-be" if even > odd else "utf-16-le", "replace")


def qa_text(path: Path, cap: int = QA_READ_CAP) -> str:
    """อ่านท้ายไฟล์ log เป็นข้อความ: UTF-16 (PowerShell `>`) → utf-8 → รหัสหน้าเครื่อง (Windows mbcs) · ตัดสี ANSI · ศูนย์ไบต์ที่ปนมา · บรรทัดที่ถูกเขียนทับด้วย \\r เหลือแค่ข้อความสุดท้าย"""
    try:
        size = path.stat().st_size
        offset = max(0, size - cap)
        with open(path, "rb") as f:
            if offset:
                f.seek(offset)
            data = f.read()
    except OSError:
        return ""
    text = qa_utf16(data, offset)
    if text is None:
        if offset:
            data = data.lstrip(bytes(range(0x80, 0xC0)))  # ตัดไบต์ต่อท้ายตัวอักษรหลายไบต์ที่ถูกหั่นกลาง
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = data.decode("mbcs" if os.name == "nt" else "latin-1", "replace")
            except LookupError:
                text = data.decode("utf-8", "replace")
    text = ANSI_RE.sub("", text.replace("﻿", "").replace("\x00", "").replace("\r\n", "\n"))
    return "\n".join(ln.split("\r")[-1] for ln in text.split("\n"))


def qa_key_lines(text: str, limit: int = 8) -> list[str]:
    """บรรทัดที่บอกผล (สรุปจำนวนผ่าน/ล้ม · ชื่อเทสต์ที่ล้ม · assertion · traceback) ตัดท้าย limit บรรทัด · ไม่ตีความ แค่คัดมา"""
    lines = text.splitlines()
    hits, tb = [], []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if s.startswith("Traceback (most recent call last)"):  # หัว traceback ไม่บอกอะไร → เก็บ "ไฟล์:บรรทัดสุดท้าย + ข้อผิดพลาดจริง" แทน
            frame, j = "", i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j][:1] in " \t"):
                m = re.match(r'\s+File "([^"]+)", line (\d+)', lines[j])
                if m:
                    frame = f'{Path(m.group(1)).name}:{m.group(2)}'
                j += 1
            if j < len(lines) and lines[j].strip():
                tb.append((frame, lines[j].strip()[:200], j))
            continue
        if QA_KEY_RE.search(s):
            hits.append((i, s[:200]))
    own = {j for _, _, j in tb}
    merged = [(i, s) for i, s in hits if i not in own]
    for frame, exc, j in tb:
        merged.append((j, exc + (f"  ({frame})" if frame else "")))
    merged.sort(key=lambda x: x[0])
    return list(dict.fromkeys(s for _, s in merged))[-limit:]


def qa_dirty_counts(root: Path) -> tuple[int, int]:
    """(ไฟล์ที่ติดตามอยู่แล้วและถูกแก้ · รายการไฟล์/โฟลเดอร์ใหม่ที่ยังไม่ติดตาม) — โฟลเดอร์ใหม่นับเป็น 1 รายการ ไม่แตกเป็นรายไฟล์ · ไม่รวม .tmp/"""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return 0, 0
    if r.returncode != 0:
        return 0, 0
    tracked = untracked = 0
    for line in r.stdout.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        if path.startswith((".tmp/", ".tmp\\")):
            continue
        if line.startswith("??"):
            untracked += 1
        else:
            tracked += 1
    return tracked, untracked


def qa_kill(p: subprocess.Popen) -> None:
    if os.name == "nt":
        kill_tree(p.pid)
        return
    try:
        os.killpg(os.getpgid(p.pid), 9)
    except OSError:
        pass


def tree_live(pid: int) -> dict | None:
    """โปรเซส pid และลูกหลานทั้งหมด: {act: CPU+I/O สะสมรวม (ตัวนับที่ไม่ขยับ = นิ่งสนิท), n: จำนวนโปรเซส, names: ชื่อโปรเซสไม่ซ้ำ (ไม่รวม shell/conhost)}
    อ่านตารางโปรเซสไม่ได้/ไม่พบ pid = None (ห้ามใช้ตัดสินฆ่า)"""
    tab = proc_table()
    if tab is None:
        return None
    kids: dict = {}
    for p in tab:
        kids.setdefault(p["ppid"], []).append(p)
    by = {p["pid"]: p for p in tab}
    if pid not in by:
        return None
    seen, stack, total, names = set(), [by[pid]], 0.0, []
    while stack and len(seen) < 300:
        p = stack.pop()
        if p["pid"] in seen:
            continue
        seen.add(p["pid"])
        total += p["act"]
        if p["name"].lower() not in ("cmd.exe", "conhost.exe", "powershell.exe", "pwsh.exe", "") and p["name"] not in names:
            names.append(p["name"])
        stack += [c for c in kids.get(p["pid"], []) if c["created"] >= p["created"] - 1]  # ppid ของ Windows อาจชี้ pid ที่ถูกใช้ซ้ำ
    return {"act": total, "n": len(seen), "names": names[:5]}


def tree_act(pid: int) -> float | None:
    """CPU+I/O สะสมรวมของโปรเซส pid และลูกหลานทั้งหมด (ดู tree_live)"""
    lv = tree_live(pid)
    return None if lv is None else lv["act"]


def qa_live_beat(job: dict, pid: int, stop: threading.Event) -> None:
    """วัดชีพจรโปรเซสของชุดทดสอบทุก QA_LIVE_POLL_SEC → job["qa_live"] = {at, moved (ครั้งล่าสุดที่ CPU/I/O เปลี่ยน), n, names} · หน้าเว็บเอาไปโชว์ (ไม่ใช้ตัดสินฆ่า)"""
    last_act, moved = None, time.time()
    while not stop.is_set():
        lv = tree_live(pid)
        if lv and not stop.is_set():
            now_t = time.time()
            if lv["act"] != last_act:
                last_act, moved = lv["act"], now_t
            job["qa_live"] = {"at": now_t, "moved": moved, "n": lv["n"], "names": lv["names"]}
            try:
                save_job(job)
            except OSError:
                pass
        stop.wait(QA_LIVE_POLL_SEC)


def qa_exec(job: dict, root: Path, spec: dict, log: Path) -> dict:
    """รันคำสั่ง 1 ชุดจนจบ/เกินเวลา/ค้าง/log ใหญ่เกิน · คืน {status: DONE|TIMEOUT|HANG|BIGLOG|ERROR, rc, secs, why}
    ยังไม่ตัดสินผ่าน/ไม่ผ่าน (qa_verdict ทำ) · ฆ่าทั้งต้นเสมอ (ไม่ทิ้งลูกค้างพอร์ต) · flashq ถูกขัดจังหวะ = ฆ่าคำสั่งก่อนออก"""
    t0 = time.time()
    cwd = (root / spec["cwd"]).resolve()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", "CI": "1", "NO_COLOR": "1"}
    kw = {"creationflags": HIDDEN_DETACH_FLAGS} if os.name == "nt" else {"start_new_session": True}
    with open(log, "wb") as fo:
        try:
            p = subprocess.Popen(spec["cmd"], shell=True, cwd=str(cwd), stdout=fo, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env, **kw)
        except OSError as e:
            return {"status": "ERROR", "rc": -1, "secs": 0.0, "why": f"เปิดคำสั่งไม่ได้: {e}"}
        job["child_pid"], job["child_pid_start"] = p.pid, proc_start(p.pid)
        save_job(job)
        status, why, rc = "DONE", "", None
        last_m, last_chg, maxgap, changes = 0.0, time.time(), 0.0, 0  # จังหวะ log จริง → เกณฑ์ค้างปรับตามชุดนี้ (ชุดที่ตั้ง idle_min เองไม่ใช้)
        last_chk, last_act, act_chg = 0.0, None, 0.0
        stop_live = threading.Event()
        if QA_LIVE_POLL_SEC > 0:  # ชีพจรให้หน้าเว็บ: สคริปต์ที่ไม่พิมพ์อะไรก็เห็นว่าโปรเซสยังขยับอยู่ (กลไกล้วน ไม่เรียกโมเดล · thread แยก ไม่รบกวนจังหวะลูปตรวจค้าง)
            threading.Thread(target=qa_live_beat, args=(job, p.pid, stop_live), daemon=True).start()
        try:
            while True:
                try:
                    rc = p.wait(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if time.time() - t0 > spec["timeout_min"] * 60:
                    status, why = "TIMEOUT", f"เกินเวลา {spec['timeout_min']:g} นาที (ฆ่าทั้งต้นแล้ว)"
                else:
                    try:
                        m = os.path.getmtime(log)
                        if os.path.getsize(log) > QA_LOG_CAP:
                            status, why = "BIGLOG", f"log เกิน {QA_LOG_CAP // 1048576} MB (คำสั่งพ่นข้อความไม่หยุด · ฆ่าแล้ว)"
                        elif spec["idle_min"] and time.time() - m > spec["idle_min"] * 60:
                            status, why = "HANG", f"log เงียบเกิน {spec['idle_min']:g} นาที (ตั้ง idle_min ไว้ · ฆ่าแล้ว)"
                        elif not spec["idle_min"]:
                            nowt = time.time()
                            if m != last_m:
                                if last_m:
                                    maxgap, changes = max(maxgap, nowt - last_chg), changes + 1
                                last_m, last_chg, last_act = m, nowt, None
                            limit = max(QA_ADAPT_FLOOR_SEC, 6 * maxgap)
                            if changes >= 5 and nowt - last_chg >= limit and nowt - last_chk >= QA_ADAPT_POLL_SEC:  # เคยพ่นเป็นจังหวะแล้วเงียบผิดปกติ → ดูว่าโปรเซสยังขยับไหม
                                last_chk, act = nowt, tree_act(p.pid)
                                if act is not None and act != last_act:
                                    last_act, act_chg = act, nowt
                                elif act is not None and nowt - act_chg >= QA_FROZEN_SEC:
                                    status, why = "HANG", (f"log เงียบ {(nowt - last_chg) / 60:.1f} นาที (เกณฑ์ปรับตามจังหวะ {limit / 60:.1f} นาที = 6× ช่วงเงียบนานสุด {maxgap / 60:.1f}) "
                                                           f"และโปรเซสทั้งชุด CPU/I/O นิ่งสนิท {(nowt - act_chg) / 60:.1f} นาที → ค้าง · ฆ่าแล้ว")
                    except OSError:
                        pass
                if why:
                    qa_kill(p)
                    try:
                        rc = p.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        rc = -1
                    break
        except BaseException:
            qa_kill(p)
            raise
        finally:
            stop_live.set()
    job.pop("qa_live", None)
    return {"status": status, "rc": rc if rc is not None else -1, "secs": round(time.time() - t0, 1), "why": why}


def qa_verdict(spec: dict, r: dict, text: str) -> str:
    """PASS = exit 0 และ (ไม่ได้ตั้ง expect หรือพบข้อความ expect ใน log) · อย่างอื่นไม่ผ่านหมด (fail-closed)
    NOEXPECT = exit 0 แต่ไม่พบข้อความที่ต้องมี → มักรันเทสต์ไม่ได้สักข้อ (collected 0 / ไม่ได้ build) ห้ามนับผ่าน"""
    if r["status"] != "DONE":
        return {"TIMEOUT": "TIMEOUT", "HANG": "TIMEOUT", "BIGLOG": "FAIL", "ERROR": "ERROR"}.get(r["status"], "FAIL")
    if r["rc"] in spec.get("env_exit", ()) and r["rc"] != 0:
        return "ENV"  # exit code ที่ผู้ใช้ประกาศว่า "สภาพแวดล้อมไม่พร้อม" (เช่น server ไม่ขึ้น) · ยังนับว่าไม่ผ่าน แต่ไม่ใช่ข้อสรุปว่าโค้ดผิด
    if r["rc"] != 0:
        return "FAIL"
    if spec["expect"] and not re.search(spec["expect"], text, re.M):
        return "NOEXPECT"
    return "PASS"


QA_ICON = {"PASS": "✅", "FAIL": "❌", "TIMEOUT": "⏱", "ERROR": "⛔", "NOEXPECT": "⚠️", "FLAKY": "⚠️", "SKIPPED": "⏭", "CHANGED": "⚠️", "ENV": "🔌"}


def qa_summary(q: dict) -> tuple[str, str]:
    """(หัวข้อ 1 บรรทัด, รายละเอียด) ภาษาคน — ผู้ใช้/Claude อ่านบรรทัดแรกก็รู้ผลทันที"""
    specs = q["specs"]
    bad = [s for s in specs if s["verdict"] != "PASS"]
    extra = ([f"แก้ไฟล์ที่ติดตามอยู่แล้วแต่ยังไม่ commit {q['dirty']} ไฟล์"] if q.get("dirty") else []) + \
            ([f"ไฟล์/โฟลเดอร์ใหม่ที่ยังไม่ติดตาม {q['untracked']} รายการ"] if q.get("untracked") else [])
    tested = f"ทดสอบ {q.get('head') or 'โฟลเดอร์ที่ไม่ใช่ git'}" + (f" (+{' · '.join(extra)})" if extra else "")
    if not bad:
        head = f"✅ ผ่านทั้ง {len(specs)} ชุด ({', '.join(s['name'] for s in specs)}) · {tested}"
    else:
        head = f"❌ ไม่ผ่าน {len(bad)}/{len(specs)} ชุด: " + ", ".join(f"{s['name']}={s['verdict']}" for s in bad) + f" · {tested}"
    if q.get("changed"):
        head = f"⚠️ ผลใช้ไม่ได้ — {q['changed']} · " + head
    lines = []
    for s in specs:
        ic = QA_ICON.get(s["verdict"], "?")
        cmd_hint = f" `{one_line(s['cmd'], 70)}`" if s.get("cmd") and (s["name"].startswith("adhoc") or ":" in s["name"] or "." in s["name"]) else ""
        if s["verdict"] == "PASS":
            lines.append(f"{ic} {s['name']}{cmd_hint} — ผ่าน {s['secs']:g} วิ" + (f" · {s['key'][-1]}" if s.get("key") else ""))
            continue
        why = {"FAIL": f"exit {s.get('rc')}", "TIMEOUT": s.get("why") or "เกินเวลา", "ERROR": s.get("why") or "เปิดคำสั่งไม่ได้",
               "NOEXPECT": f"exit 0 แต่ไม่พบข้อความที่ต้องมี /{s.get('expect', '')}/ → อาจไม่ได้รันเทสต์จริง นับว่าไม่ผ่าน",
               "FLAKY": "ล้มรอบแรกแต่ผ่านรอบหลัง = ผลไม่นิ่ง นับว่าไม่ผ่าน", "SKIPPED": "ข้าม (ชุดก่อนหน้าหยุดการทดสอบ)",
               "CHANGED": "โค้ดเปลี่ยนระหว่างทดสอบ",
               "ENV": f"exit {s.get('rc')} = สภาพแวดล้อมไม่พร้อม (ตามที่ env_exit ประกาศ) — ยังไม่ได้ทดสอบโค้ดจริง นับว่าไม่ผ่าน · เตรียมสภาพแวดล้อมแล้วรันใหม่"}.get(s["verdict"], s["verdict"])
        lines.append(f"{ic} {s['name']}{cmd_hint} — {why}" + (f" · {s['secs']:g} วิ" if s["verdict"] != "SKIPPED" else "") + (f" · log {s['log']}" if s.get("log") else ""))
        lines += [f"    {k}" for k in (s.get("key") or [])[-5:]]
    if q.get("test_secs") is not None:
        lines.append(f"เวลา: รันเทสต์ {q['test_secs']:g} วิ" + (f" · Flash วิเคราะห์ {q['analyze_secs']:g} วิ" if q.get("analyze_secs") else ""))
    if q.get("analysis"):
        lines.append("คำอธิบายจากนักทดสอบ (Flash · ความเห็น ไม่ใช่คำตัดสิน — ตรวจกับ log ก่อนเชื่อ): " + one_line(q["analysis"], 700))
    elif q.get("analysis_note"):
        lines.append(f"(ไม่มีคำอธิบายจาก Flash: {q['analysis_note']})")
    return head, "\n".join(lines)


def qa_analyze(job: dict, root: Path, cfg: dict, failing: list[dict], variant: str) -> str:
    """ให้ Flash (flash-tester อ่านอย่างเดียว) อ่าน log ของชุดที่ล้มแล้วอธิบายสาเหตุ · คืนข้อความ · ล้มเหลว = โยน RuntimeError(เหตุผล) ให้ผู้เรียกบันทึก ไม่กระทบคำตัดสิน"""
    exe = opencode_cmd()
    if not exe:
        raise RuntimeError("ไม่พบคำสั่ง opencode")
    parts = "; ".join(f"ชุด {s['name']} (exit {s.get('rc')}) log: {s['log']}" for s in failing[:4])
    prompt = ("ชุดทดสอบต่อไปนี้ไม่ผ่าน อ่านเฉพาะไฟล์ log ที่ระบุ (และโค้ดในโปรเจกต์ที่ log ชี้ถึง) แล้วรายงานตามหน้าที่ของคุณ — "
              "สาเหตุที่น่าจะเป็น พร้อมบรรทัดหลักฐานจาก log ตรงตัว · ห้ามแก้ไฟล์ · ห้ามรันคำสั่งทดสอบซ้ำ. " + parts)
    title = one_line(f"flash-qa-analyze {job['title']}", 200)
    bad = cmd_shim_unsafe(exe, title, prompt)
    if bad:
        raise RuntimeError(f"ข้อความถึงโมเดลมีอักขระ {bad} ที่ cmd.exe ตีความเอง (path ของ log) — ข้ามคำอธิบาย")
    model = agent_model("flash-tester")
    job["model"] = model
    ext = external_dirs(cfg) + [_slash(str(LOGS)).rstrip("/") + "/*"]
    env = {**os.environ, "OPENCODE_CONFIG_CONTENT": perm_config_content(ext)}
    cmd = [*exe, "run", "--dir", str(root), "--title", title, "--format", "json"]
    if model:
        cmd += ["--model", model]
    if variant:
        cmd += ["--variant", variant]
    cmd += ["--agent", "flash-tester", "--", prompt]
    job["attach"], job["variant"] = "", variant
    save_job(job)
    res = run_once(job, cmd, root, "", QA_ANALYZE_MIN, True, len(job.get("logs") or []) + 1, 4, 2, 0, env)
    if res.get("status") != "OK" or not (res.get("last") or "").strip():
        raise RuntimeError(f"Flash ตอบสถานะ {res.get('status')}" + (f" — {res['errors'][-1][:120]}" if res.get("errors") else ""))
    return res["last"].strip()


def cmd_qa(a) -> int:
    start = Path(a.project or os.getcwd())
    root, is_git = project_root(start)
    cfg = project_cfg(root)
    specs, errs = qa_specs(cfg, a.qa_names, a.qa_cmd, root)
    if not specs and not errs:
        errs = ["โปรเจกต์นี้ยังไม่ได้ตั้งชุดทดสอบ (.flash.json → qa.presets) และไม่ได้ระบุ --cmd"]
    if errs and (root / ".flash.json").is_file() and not read_json(root / ".flash.json"):
        errs.insert(0, f"อ่าน {root / '.flash.json'} ไม่ได้ (JSON เสีย/ว่าง) จึงไม่เห็นชุดทดสอบเลย — แก้ไฟล์ก่อน")
    if errs:
        print("FLASH_RUN=FAIL นักทดสอบเริ่มไม่ได้:")
        for e in errs:
            print(f"  - {e}")
        if not specs:
            for ln in qa_suggest_lines(root):
                print(ln)
        return 1
    if a.timeout_min:
        for s in specs:
            s["timeout_min"] = float(a.timeout_min)
    if a.retry is not None:
        for s in specs:
            s["retry"] = max(0, min(3, a.retry))

    def head_now() -> str:
        return _git(root, "rev-parse", "HEAD") if is_git else ""

    def commit_problem() -> str:
        if not a.qa_commit:
            return ""
        if not is_git:
            return "ระบุ --commit แต่โปรเจกต์นี้ไม่ใช่ git"
        want = _git(root, "rev-parse", "--verify", "-q", f"{a.qa_commit}^{{commit}}")
        if not want:
            return f"ไม่พบ commit '{a.qa_commit}' ในโปรเจกต์"
        if want != head_now():
            return (f"ต้องการทดสอบ commit {want[:10]} แต่ checkout ตอนนี้อยู่ที่ {head_now()[:10]} — นักทดสอบทดสอบโค้ดที่อยู่ใน checkout จริง "
                    f"ไม่สลับ commit เอง · สลับให้ตรง (หรือ merge) แล้วสั่งใหม่")
        return ""
    prob = commit_problem()
    if prob:
        print(f"FLASH_RUN=FAIL {prob}")
        return 1
    for d in (JOBS, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jid = f"{ts}_{os.getpid()}"
    names = [s["name"] for s in specs]
    title = one_line(a.title or f"flash-qa {' '.join(names)}", 200)
    q = {"specs": [{"name": s["name"], "cmd": s["cmd"], "verdict": "PENDING", "secs": 0, "expect": s["expect"]} for s in specs],
         "phase": "queued", "head": "", "dirty": 0}
    job = {"id": jid, "project": str(root), "plan": "", "tasks": " ".join(names), "message": "", "kind": "qa", "agent": "flash-tester",
           "prompt": "", "readonly": True, "title": title, "model": "", "status": "queued", "pid": os.getpid(),
           "pid_start": proc_start(os.getpid()), "created": now(), "qv": QUEUE_VERSION,
           "claude_session": os.environ.get("CLAUDE_CODE_SESSION_ID", ""), "claude_host": os.environ.get("CLAUDE_CODE_HOST_SESSION_ID", ""), "qa": q}
    save_job(job)
    got = acquire(job, a.wait_min, a.no_wait)
    if got != "ok":
        job.update(status="busy" if got == "busy" else "queue_timeout", finished=now())
        save_job(job)
        notify_job(job, job["status"].upper())
        return 2 if got == "busy" else 3

    status, rc_out, t_start = "FAIL", 1, time.time()
    try:
        job.update(status="running", started=now())
        save_job(job)
        print(f"SLOT ช่อง {job.get('slot', 1)} (max_parallel={max_parallel()})", flush=True)
        prob = commit_problem()  # รอคิวมานาน HEAD อาจเปลี่ยนไปแล้ว
        head0 = head_now()
        q.update(head=head0[:10], phase="test")
        q["dirty"], q["untracked"] = qa_dirty_counts(root) if is_git else (0, 0)
        save_job(job)
        if prob:
            q["changed"] = prob
            for s in q["specs"]:
                s["verdict"] = "SKIPPED"
        else:
            stop = False
            for spec, row in zip(specs, q["specs"]):
                if stop:
                    row["verdict"] = "SKIPPED"
                    continue
                q["current"] = spec["name"]
                runs = []
                for k in range(spec["retry"] + 1):
                    log = LOGS / f"{jid}_{len(job.get('logs') or []) + 1}.log"
                    job.setdefault("logs", []).append(str(log))
                    row.update(log=str(log), verdict="RUNNING")
                    save_job(job)
                    print(f"QA_START {spec['name']} รอบ {k + 1}/{spec['retry'] + 1} cwd={spec['cwd']} timeout={spec['timeout_min']:g}นาที log={log}", flush=True)
                    r = qa_exec(job, root, spec, log)
                    text = qa_text(log)
                    r["verdict"], r["key"] = qa_verdict(spec, r, text), qa_key_lines(text)
                    runs.append((r, log))
                    print(f"QA_END {spec['name']} → {r['verdict']} exit={r['rc']} {r['secs']:g}วิ" + (f" ({r['why']})" if r["why"] else ""), flush=True)
                    if r["verdict"] in ("PASS", "TIMEOUT", "ERROR", "ENV"):  # ผ่านแล้ว/เกินเวลา/เปิดไม่ได้/สภาพแวดล้อมไม่พร้อม ไม่ลองซ้ำ (ซ้ำก็เสียเวลาเปล่า)
                        break
                r, log = runs[-1]
                verdict = r["verdict"]
                if verdict == "PASS" and len(runs) > 1:
                    verdict = "FLAKY"  # ผ่านเฉพาะรอบหลัง = ผลไม่นิ่ง · เก็บ log ของรอบที่ล้มด้วย
                    log = runs[0][1]
                    r = dict(r, key=runs[0][0]["key"])
                row.update(verdict=verdict, rc=r["rc"], secs=round(sum(x[0]["secs"] for x in runs), 1), why=r["why"], key=r["key"][-8:],
                           log=str(log), runs=len(runs))
                head1 = head_now()
                if head1 != head0:  # โค้ดเปลี่ยนระหว่างทดสอบ (มีใครแตะ checkout) → ผลไม่ใช่ของ commit เดียว ห้ามนับว่าผ่าน
                    row["verdict"] = "CHANGED" if verdict == "PASS" else row["verdict"]
                    q["changed"] = f"HEAD เปลี่ยนจาก {head0[:10]} เป็น {head1[:10]} ระหว่างทดสอบ"
                    stop = True
                elif row["verdict"] != "PASS" and a.fail_fast:
                    stop = True
            q.pop("current", None)
        q["test_secs"] = round(time.time() - t_start, 1)
        bad = [r for r in q["specs"] if r["verdict"] != "PASS"]
        verdicts = {r["verdict"] for r in q["specs"]}
        if verdicts == {"PASS"} and not q.get("changed"):
            status = "OK"
        elif "TIMEOUT" in verdicts and verdicts <= {"PASS", "TIMEOUT"} and not q.get("changed"):
            status = "TIMEOUT"
        else:
            status = "FAIL"  # fail-closed: อะไรที่ไม่ใช่ PASS ล้วน (รวมข้าม/ไม่นิ่ง/โค้ดเปลี่ยน) = ไม่ผ่าน
        failing = [r for r in bad if r.get("log") and r["verdict"] in ("FAIL", "TIMEOUT", "NOEXPECT", "FLAKY")]
        if failing and not a.no_analyze and not q.get("changed"):
            q["phase"] = "analyze"
            save_job(job)
            t_an = time.time()
            try:
                q["analysis"] = qa_analyze(job, root, cfg, failing, variant_for("qa", a.variant, root))
            except Exception as e:  # คำอธิบายเป็นของแถม — พังแค่บันทึกเหตุ ไม่เปลี่ยนคำตัดสิน
                q["analysis_note"] = str(e)[:300]
            q["analyze_secs"] = round(time.time() - t_an, 1)
        q["phase"] = "done"
        rc_out = 0 if status == "OK" else 1
    finally:
        mins = (time.time() - t_start) / 60
        for row in q["specs"]:  # ถูกขัดจังหวะ/พังกลางทาง: ชุดที่ยังไม่ได้ผลต้องไม่ค้างเป็น PENDING/RUNNING (อ่านแล้วเหมือนยังทำอยู่)
            if row["verdict"] in ("PENDING", "RUNNING"):
                row.update(verdict="ERROR", why="ทดสอบไม่จบ (flashq ถูกขัดจังหวะหรือผิดพลาดกลางทาง)")
        q["verdict"] = "PASS" if status == "OK" else status
        head_line, body = qa_summary(q)
        job.update(status=status.lower(), result=status, rc=rc_out, finished=now(), last=(head_line + "\n" + body)[:1500])
        q["phase"] = "done"
        save_job(job)
        release(job)
        notify_job(job, status, mins)
    print(f"FLASH_RUN={status} exit={rc_out} เวลา={mins:.1f} นาที tool=0 session={job.get('session', '')} job={jid}")
    print(f"QA={q['verdict']} {head_line}")
    print("---- สรุปผลทดสอบ ----")
    print(body)
    return rc_out


# ---------- ช่างเอกสาร (flashq doc) — ขั้น 1: ตัวตัดสินด้วยกลไก ----------
# หลักการ: Flash แก้เอกสารได้เฉพาะไฟล์ที่ชุด (doc.presets.<ชื่อ>.paths ใน .flash.json) อนุญาต · flashq ตรวจผลเองจาก git/ไฟล์จริง ไม่ฟังโมเดลว่า "เรียบร้อย"
# ผ่าน = DRAFT (ร่างรอผู้ใช้ดู diff) ไม่ใช่ "ถูกต้อง" · ทุกอย่างที่ไม่ใช่ DRAFT ไม่ผ่านหมด (fail-closed)
DOC_MAX_PATHS = 32
DOC_MAX_BRIEF = 4000
DOC_TEXT_CAP = 1024 * 1024       # ไฟล์เอกสารที่ตรวจเนื้อหาได้ใหญ่สุด · เกินหรือมี NUL = ตรวจไม่ได้ (UNCHECKED)
DOC_WHY_MAX = 8
DOC_PROTECTED_RE = re.compile(r"(?:^|/)(?:\.git(?:/|$)|\.flash\.json$|\.env(?:\.[^/]*)?$|id_(?:rsa|ed25519|ecdsa)[^/]*$|[^/]*\.(?:pem|key|p12|pfx|keystore)$)", re.I)
DOC_GUARD_FILES = (".flash.json", ".env", ".env.local", ".env.production", ".git/config", ".git/HEAD", ".git/hooks")
DOC_SECRET_RES = [re.compile(p) for p in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"\bAKIA[0-9A-Z]{16}\b", r"\bgh[pousr]_[A-Za-z0-9]{30,}", r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bsk-[A-Za-z0-9_-]{20,}", r"\bxox[abpr]-[A-Za-z0-9-]{10,}", r"\bAIza[0-9A-Za-z_-]{35}", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")]
DOC_SECRET_ASSIGN_RE = re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)\b[\"']?\s*[:=]\s*[\"']?([^\s\"'<>`,;]{8,})")
DOC_PLACEHOLDER_RE = re.compile(r"[<>{}$*]|\.\.\.|x{4,}|your|example|changeme|placeholder|redacted|dummy|sample", re.I)
DOC_REF_RE = re.compile(r"`([^`\s]{3,200})`")
DOC_REF_OK_RE = re.compile(r"[\w.@+-]+(?:/[\w.@+-]+)+\.[A-Za-z0-9]{1,6}")
DOC_HOSTPORT_RE = re.compile(r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|dev|local|localhost|test)):\d+")


def doc_norm_path(p: str) -> str:
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def doc_glob_re(pat: str) -> re.Pattern:
    """glob แบบ .gitignore ย่อ: `**/` = กี่โฟลเดอร์ก็ได้ (รวมศูนย์) · `**` = อะไรก็ได้ · `*`/`?` ไม่ข้าม `/` · ตรงทั้งเส้นทาง (ไม่ใช่แค่ท่อนหนึ่ง)"""
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pat[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile(out + r"\Z")


def doc_allowed(rel: str, spec: dict) -> bool:
    """ไฟล์นี้อยู่ใน paths ของชุด และไม่ใช่ไฟล์ต้องห้าม (.git · .flash.json · .env* · กุญแจ)"""
    rel = doc_norm_path(rel)
    return not DOC_PROTECTED_RE.search(rel) and any(doc_glob_re(p).match(rel) for p in spec["paths"])


def doc_spec(name: str, v, default_min: float) -> dict | str:
    """ตรวจ 1 ชุดเอกสาร → dict ที่ใช้รันได้ หรือข้อความผิดพลาด (paths กว้างเกิน/หลุดนอกโปรเจกต์/ครอบไฟล์ต้องห้าม = ปฏิเสธตั้งแต่ตอนอ่านค่า)"""
    if isinstance(v, list):
        v = {"paths": v}
    if not isinstance(v, dict):
        return f"ชุดเอกสาร '{name}' ต้องเป็น {{\"paths\": [...], \"brief\": \"...\"}}"
    paths = v.get("paths")
    if not (isinstance(paths, list) and 1 <= len(paths) <= DOC_MAX_PATHS and all(isinstance(p, str) for p in paths)):
        return f"ชุดเอกสาร '{name}': paths ต้องเป็นรายการข้อความ 1-{DOC_MAX_PATHS} รายการ เช่น [\"docs/**\", \"README.md\"]"
    norm = []
    for raw in paths:
        p = doc_norm_path(raw)
        if not p or len(p) > 200 or "\x00" in p:
            return f"ชุดเอกสาร '{name}': path '{raw[:40]}' ว่าง/ยาวเกิน/มีอักขระต้องห้าม"
        if p.startswith(("/", "~")) or re.match(r"[A-Za-z]:", p) or ".." in p.split("/"):
            return f"ชุดเอกสาร '{name}': path '{raw}' ต้องเป็นเส้นทางสัมพัทธ์ใต้โปรเจกต์ (ห้ามขึ้นต้น / ~ ไดรฟ์ หรือมี ..)"
        if not re.search(r"[\w-]", p):
            return f"ชุดเอกสาร '{name}': path '{raw}' กว้างเกินไป (ต้องมีชื่อโฟลเดอร์หรือนามสกุลระบุ)"
        rx = doc_glob_re(p)
        if p.rstrip("/") in ("**", "*") or any(rx.match(s) for s in (".flash.json", ".env", ".env.local", ".git/config", ".git/hooks/pre-commit", "id_rsa", "server.pem", "secrets.key")):
            return f"ชุดเอกสาร '{name}': path '{raw}' ครอบไฟล์ต้องห้าม (.git · .flash.json · .env* · กุญแจ) หรือกว้างเกินไป"
        norm.append(p)
    brief = v.get("brief") or ""
    if not isinstance(brief, str) or len(brief) > DOC_MAX_BRIEF or "\x00" in brief:
        return f"ชุดเอกสาร '{name}': brief ต้องเป็นข้อความไม่เกิน {DOC_MAX_BRIEF} ตัวอักษร"
    raw_t = v.get("timeout_min")
    try:
        timeout = default_min if raw_t in (None, "") else float(raw_t)
    except (TypeError, ValueError):
        return f"ชุดเอกสาร '{name}': timeout_min ต้องเป็นตัวเลข"
    if not 0.1 <= timeout <= 1440:
        return f"ชุดเอกสาร '{name}': timeout_min ต้องอยู่ระหว่าง 0.1-1440"
    return {"name": name, "paths": list(dict.fromkeys(norm)), "brief": brief.strip(), "timeout_min": timeout}


def doc_guard(root: Path) -> dict:
    """สถานะไฟล์ต้องห้ามที่ git status อาจไม่เห็น (ถูก .gitignore เช่น .env) — เทียบก่อน/หลังรัน"""
    out = {}
    for rel in DOC_GUARD_FILES:
        p = root / rel
        try:
            st = p.stat()
            out[rel] = (st.st_size, st.st_mtime_ns)
        except OSError:
            out[rel] = None
    hooks = root / ".git" / "hooks"
    if hooks.is_dir():
        for f in sorted(hooks.iterdir())[:64]:
            try:
                st = f.stat()
                out[".git/hooks/" + f.name] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
    return out


def doc_changed(before: dict | None, after: dict | None) -> list[str]:
    """ไฟล์ที่เปลี่ยนระหว่างรัน · snapshot_changes มองไม่เห็นการลบไฟล์ที่เดิมสะอาด (ไม่มีในก่อน = None เท่ากับหลังลบ = None) → เทียบเองตรงนี้ ไม่แก้ของเดิมที่ readonly ใช้อยู่"""
    if before is None or after is None:
        return []
    n = lambda v: None if v is None else tuple(v)  # snapshot ที่อ่านกลับจาก JSON เป็น list
    return sorted({doc_norm_path(p) for p in after if p not in before or n(after[p]) != n(before[p])} | {doc_norm_path(p) for p in before if p not in after})


def doc_guarded(guard0: dict, guard1: dict) -> list[str]:
    n = lambda v: None if v is None else tuple(v)  # guard ที่อ่านกลับจาก JSON เป็น list
    return [p for p in guard1 if n(guard1[p]) != n(guard0.get(p))] + [p for p in guard0 if p not in guard1]


def doc_before(root: Path, snap: dict | None) -> dict:
    """ข้อความของไฟล์ที่ "สกปรกอยู่แล้ว" ก่อนรัน — ใช้เป็นฐานเทียบ (ไม่นับการแก้ของผู้ใช้เองเป็นของช่างเอกสาร)"""
    out = {}
    for rel in (snap or {}):
        try:
            if (root / rel).is_file() and (root / rel).stat().st_size <= DOC_TEXT_CAP:
                out[rel] = (root / rel).read_bytes().decode("utf-8", "replace")
        except OSError:
            pass
    return out


def doc_added(root: Path, rel: str, head: str, before_texts: dict) -> tuple[list[str] | None, bool]:
    """บรรทัดที่เพิ่ม/แก้ในไฟล์นี้ (เทียบกับฐานก่อนรัน) → (บรรทัด, ถูกลบหรือไม่) · None = ตรวจเนื้อหาไม่ได้ (ไบนารี/ใหญ่เกิน)"""
    f = root / rel
    if not f.is_file():
        return [], True
    try:
        data = f.read_bytes()
    except OSError:
        return None, False
    if len(data) > DOC_TEXT_CAP or b"\x00" in data:
        return None, False
    if rel in before_texts:
        base = before_texts[rel]
    else:
        r = run_timeout(["git", "-C", str(root), "show", f"{head}:{rel}"], 30, text=False) if head else None
        if r is not None and r.returncode == 0 and (len(r.stdout) > DOC_TEXT_CAP or b"\x00" in r.stdout):
            return None, False
        base = r.stdout.decode("utf-8", "replace") if r is not None and r.returncode == 0 else ""  # ไม่มีใน HEAD = ไฟล์ใหม่
    new = data.decode("utf-8", "replace").splitlines()
    diff = difflib.unified_diff(base.splitlines(), new, n=0, lineterm="")
    return [x[1:] for x in diff if x.startswith("+") and not x.startswith("+++")], False


def doc_secrets(rel: str, lines: list[str]) -> list[str]:
    hits = []
    for n, line in enumerate(lines, 1):
        bad = next((rx.pattern[:24] for rx in DOC_SECRET_RES if rx.search(line)), "")
        if not bad:
            m = DOC_SECRET_ASSIGN_RE.search(line)
            if m and not DOC_PLACEHOLDER_RE.search(m.group(1)):
                bad = "ค่ารหัส/โทเค็นในบรรทัดที่ตั้งค่า"
        if bad:
            hits.append(f"{rel} (บรรทัดที่เพิ่มลำดับ {n}): คล้ายความลับ — {bad}")  # ไม่พิมพ์ค่าจริงซ้ำ
    return hits


def doc_badrefs(root: Path, rel: str, lines: list[str]) -> list[str]:
    """เส้นทางไฟล์ใน `...` และ file:line ที่เอกสารเพิ่งเขียนต้องมีจริง (ตรวจแค่ "มีอยู่จริง" ไม่ได้ตรวจว่าอธิบายถูก)"""
    text = DOC_HOSTPORT_RE.sub("", "\n".join(lines))
    rroot, bad = root.resolve(), []
    cands = []
    for tok in dict.fromkeys(DOC_REF_RE.findall(text)):
        t = doc_norm_path(tok)
        first = t.split("/")[0]
        if not DOC_REF_OK_RE.fullmatch(t) or t.startswith("/") or (first.startswith(("http", "www")) or ("." in first and not first.startswith("."))):
            continue
        cands.append(t)
    missing = []
    for t in cands:
        for base in (rroot, (rroot / rel).parent):
            try:
                if (base / t).resolve().is_relative_to(rroot) and (base / t).is_file():
                    break
            except OSError:
                pass
        else:
            missing.append(t)
    if missing:
        ignored = set()  # ไฟล์ที่ถูก .gitignore (log/ไฟล์ตอนรัน) เอกสารพูดถึงได้แม้ยังไม่มีในเครื่อง
        try:
            p = subprocess.run(["git", "-C", str(root), "check-ignore", "--stdin"], input="\n".join(missing), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
            if p.returncode in (0, 1):
                ignored = set(p.stdout.split("\n"))
        except (OSError, subprocess.SubprocessError):
            pass
        bad += [f"{rel}: อ้างถึง `{t}` แต่ไม่พบไฟล์นี้" for t in missing if t not in ignored]
    bad += [f"{rel}: {b}" for b in check_citations(text, root)["bad"]]
    return bad


def doc_verdict(spec: dict, run: dict, root: Path, before: dict | None, after: dict | None, before_texts: dict,
                guard0: dict, guard1: dict) -> tuple[str, list[str], list[str]]:
    """คำตัดสินช่างเอกสารจากไฟล์จริง → (verdict, เหตุผล, ไฟล์ที่เปลี่ยน) · DRAFT = ผ่านทุกด่านกลไก (ยังต้องให้ผู้ใช้ดู diff) · อย่างอื่นไม่ผ่านหมด
    ลำดับด่าน: รันไม่จบ → HEAD เปลี่ยน → แตะนอกขอบเขต → ไม่มีอะไรเปลี่ยน → ตรวจเนื้อหาไม่ได้ → ลบไฟล์ → ความลับ → อ้างไฟล์ที่ไม่มี"""
    st = run.get("status", "DONE")
    if st != "DONE":
        return {"TIMEOUT": "TIMEOUT", "HANG": "TIMEOUT"}.get(st, "ERROR"), [f"agent จบด้วยสถานะ {st}"], []
    if before is None or after is None:
        return "ERROR", ["อ่านสถานะ git ไม่ได้ จึงตรวจไม่ได้ว่าแก้อะไรไปบ้าง"], []
    head0, head1 = run.get("head0", ""), run.get("head1", "")
    if head0 != head1:
        return "CHANGED", [f"HEAD เปลี่ยนระหว่างรัน ({head0[:8]} → {head1[:8]}) — ช่างเอกสารห้าม commit และห้ามมีใครอื่น commit คั่น"], []
    changed, guarded = doc_changed(before, after), doc_guarded(guard0, guard1)
    outside = [p for p in changed if not doc_allowed(p, spec)] + [p for p in guarded if p not in changed]
    if outside:
        return "OUTSIDE", [f"แตะไฟล์นอกขอบเขตชุด '{spec['name']}': {p}" for p in outside[:DOC_WHY_MAX]] + \
            ([f"(และอีก {len(outside) - DOC_WHY_MAX} ไฟล์)"] if len(outside) > DOC_WHY_MAX else []), changed + [p for p in guarded if p not in changed]
    if not changed:
        return "NOCHANGE", ["ไม่มีไฟล์เปลี่ยนเลย (เอกสารอาจตรงกับโค้ดอยู่แล้ว หรือ agent ไม่ได้ลงมือ)"], []
    added, unchecked, deleted = {}, [], []
    for p in changed:
        lines, gone = doc_added(root, p, head1, before_texts)
        if gone:
            deleted.append(p)
        elif lines is None:
            unchecked.append(p)
        else:
            added[p] = lines
    if unchecked:
        return "UNCHECKED", [f"ตรวจเนื้อหาไม่ได้ (ไบนารี/ใหญ่เกิน {DOC_TEXT_CAP // 1024} KB): {p}" for p in unchecked[:DOC_WHY_MAX]], changed
    if deleted:
        return "DELETED", [f"ลบไฟล์เอกสาร: {p} (ช่างเอกสารไม่ควรลบ — กู้ได้ด้วย git checkout)" for p in deleted[:DOC_WHY_MAX]], changed
    secrets = [h for p, ls in added.items() for h in doc_secrets(p, ls)]
    if secrets:
        return "SECRET", secrets[:DOC_WHY_MAX], changed
    refs = [b for p, ls in added.items() for b in doc_badrefs(root, p, ls)]
    if refs:
        return "BADREF", refs[:DOC_WHY_MAX] + ([f"(และอีก {len(refs) - DOC_WHY_MAX} จุด)"] if len(refs) > DOC_WHY_MAX else []), changed
    return "DRAFT", [f"แก้ {len(changed)} ไฟล์ ผ่านด่านกลไกทั้งหมด — รอผู้ใช้ดู diff"], changed


# ---------- ช่างเอกสาร — ขั้น 2: สั่งงาน · สำรอง/ย้อนกลับ · รับ/ทิ้ง ----------
DOC_AUTO_REVERT = ("OUTSIDE", "SECRET")   # ผลที่อันตราย (แตะนอกขอบเขต/มีความลับ) → ย้อนให้เองทันที · ผลอื่นเก็บไฟล์ไว้ให้ผู้ใช้ดู
DOC_BACKUP_CAP = 20 * 1024 * 1024
DOC_SNAP_CAP = 500
DOC_ICON = {"DRAFT": "📝", "TIMEOUT": "⏱", "ERROR": "⛔", "CHANGED": "⚠️", "OUTSIDE": "🚫", "NOCHANGE": "➖", "UNCHECKED": "⚠️", "DELETED": "🗑",
            "SECRET": "🔑", "BADREF": "🔗", "CANCELLED": "✋"}
DOC_MEANING = {"TIMEOUT": "เกินเวลา", "ERROR": "agent ล้มเหลวหรือ flashq ตรวจไม่ได้", "CHANGED": "HEAD เปลี่ยนระหว่างรัน (ห้าม commit/สลับ branch)",
               "OUTSIDE": "แตะไฟล์นอกขอบเขตของชุด", "NOCHANGE": "ไม่มีไฟล์เปลี่ยน", "UNCHECKED": "ตรวจเนื้อหาไฟล์ไม่ได้ (ไบนารี/ใหญ่เกิน)",
               "DELETED": "ลบไฟล์เอกสาร", "SECRET": "พบข้อความคล้ายความลับ", "BADREF": "อ้างถึงไฟล์/บรรทัดที่ไม่มีจริง", "CANCELLED": "ถูกยกเลิกกลางทาง"}


def doc_sha(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""  # ไม่มีไฟล์


def doc_backup(root: Path, jid: str, snap: dict | None, guard: dict) -> dict:
    """สำรองไฟล์ที่ "สกปรกอยู่แล้ว" ก่อนให้ agent แตะ + ไฟล์ต้องห้ามนอก .git ที่มีอยู่ (.env ฯลฯ) → ใช้ย้อนกลับเฉพาะไฟล์ที่ช่างเอกสารแตะ
    saved = สำรองแล้ว · absent = ก่อนรันไม่มีไฟล์นี้ (ย้อน = ลบ) · skipped = ใหญ่เกินสำรอง (ย้อนเองไม่ได้)"""
    dest = HOME / "docbak" / jid
    saved, absent, skipped = [], [], []
    for rel in dict.fromkeys([doc_norm_path(p) for p in (snap or {})] + [g for g in guard if not g.startswith(".git")]):
        if rel.startswith(".git/") or rel == ".git":
            continue
        p = root / rel
        try:
            if not p.is_file():
                absent.append(rel)
            elif p.stat().st_size > DOC_BACKUP_CAP:
                skipped.append(rel)
            else:
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest / rel)
                saved.append(rel)
        except OSError:
            skipped.append(rel)
    return {"dir": str(dest), "saved": saved, "absent": absent, "skipped": skipped}


def doc_restore(root: Path, bak: dict, rels: list[str], head0: str) -> list[str]:
    """ย้อนไฟล์เหล่านี้ไปสถานะก่อนช่างเอกสารรัน: เคยสกปรก = คืนจากสำรอง · ไม่มีก่อนรัน = ลบ · สะอาดและอยู่ใน HEAD = checkout จาก HEAD เดิม · คืนรายการปัญหา"""
    rroot, problems = root.resolve(), []
    for raw in rels:
        rel = doc_norm_path(raw)
        p = rroot / rel
        try:
            safe = bool(rel) and ".." not in rel.split("/") and not rel.startswith(".git") and p.resolve().is_relative_to(rroot)
        except OSError:
            safe = False
        if not safe:
            problems.append(f"{rel}: path ไม่ปลอดภัย ข้ามไม่ย้อน")
            continue
        try:
            if rel in bak.get("saved", []):
                shutil.copy2(Path(bak["dir"]) / rel, p)
            elif rel in bak.get("skipped", []):
                problems.append(f"{rel}: ใหญ่เกินสำรอง ย้อนเองไม่ได้ (ใช้ git/ที่สำรองของคุณ)")
            elif rel in bak.get("absent", []) or run_timeout(["git", "-C", str(root), "cat-file", "-e", f"{head0}:{rel}"], 30).returncode != 0:
                p.unlink(missing_ok=True)  # ก่อนรันไม่มี / ไม่อยู่ใน HEAD = ไฟล์ใหม่ที่ช่างเอกสารสร้าง
                for d in p.parents:  # เก็บโฟลเดอร์ว่างที่สร้างค้างไว้ (หยุดที่รากโปรเจกต์/โฟลเดอร์ที่ไม่ว่าง)
                    if d == rroot:
                        break
                    try:
                        d.rmdir()
                    except OSError:
                        break
            else:
                r = run_timeout(["git", "-C", str(root), "checkout", head0, "--", rel], 60)
                if r.returncode != 0:
                    problems.append(f"{rel}: git checkout ล้มเหลว ({r.stderr.strip()[:100]})")
        except OSError as e:
            problems.append(f"{rel}: {e}")
    return problems


def doc_prompt(spec: dict, since: str) -> str:
    base = (f"ดูโค้ดที่เปลี่ยนด้วย git log/diff {since}..HEAD (และ git status สำหรับที่ยังไม่ commit)" if since
            else "ดูโค้ดที่เปลี่ยนล่าสุดด้วย git log -20 --stat, git diff และ git status (รวมที่ยังไม่ commit) แล้วตัดสินเองว่าเอกสารส่วนไหนล้าสมัย")
    return "\n".join([
        f"ช่างเอกสาร ชุด '{spec['name']}': อัปเดตเอกสารให้ตรงกับโค้ดตามหน้าที่ของคุณ",
        "ไฟล์ที่แก้ได้เท่านั้น (เทียบจากรากโปรเจกต์): " + ", ".join(spec["paths"]),
        "ห้ามแก้ไฟล์อื่น · ห้าม commit/stage/push/สลับ branch · ห้ามลบไฟล์ · ห้ามใส่ความลับ รหัสผ่าน หรือโทเค็น · "
        "ไฟล์ที่อ้างใน `...` ต้องมีอยู่จริงเท่านั้น (ตรวจก่อนเขียน) · ไม่แน่ใจว่าโค้ดทำงานอย่างไร = ไปอ่านโค้ดก่อน อย่าเดา",
        base,
        *([f"โจทย์เพิ่มเติมของโปรเจกต์นี้: {spec['brief']}"] if spec.get("brief") else []),
        "จบด้วยสรุปสั้น ๆ: แก้ไฟล์ไหน เพราะโค้ดส่วนไหนเปลี่ยน · ถ้าไม่มีอะไรต้องแก้ ให้บอกเหตุผล"])


def doc_summary(d: dict) -> tuple[str, str]:
    """(หัวข้อ 1 บรรทัด, รายละเอียด) ภาษาคน"""
    v, name, ch = d.get("verdict") or "ERROR", d.get("name", ""), d.get("changed") or []
    ic = DOC_ICON.get(v, "?")
    if v == "DRAFT":
        head = f"{ic} ร่างเอกสารชุด '{name}' แก้ {len(ch)} ไฟล์ — ผ่านด่านกลไกแล้ว รอคุณดู diff"
    else:
        head = f"{ic} ช่างเอกสารชุด '{name}' ไม่ผ่าน: {DOC_MEANING.get(v, v)}"
        if d.get("state") == "reverted":
            head += " (ย้อนไฟล์กลับให้แล้ว)"
        elif ch:
            head += f" (ไฟล์ที่แก้ค้างอยู่ {len(ch)} ไฟล์)"
    lines = [f"  • {x}" for x in (d.get("why") or [])[:DOC_WHY_MAX + 1]]
    lines += [f"ไฟล์ที่เปลี่ยน: {', '.join(ch[:10])}" + (f" (+{len(ch) - 10})" if len(ch) > 10 else "")] if ch else []
    if d.get("revert_problems"):
        lines += ["ย้อนบางไฟล์ไม่ได้ — ตรวจเอง:"] + [f"  ✗ {x}" for x in d["revert_problems"][:6]]
    if d.get("state") == "pending":
        jid = d.get("job", "<job>")
        lines.append(f"ดู diff: git -C <โปรเจกต์> diff · " + (f"รับ: flashq doc-review {jid} accept · " if v == "DRAFT" else "") + f"ทิ้ง: flashq doc-review {jid} discard (ยังไม่มีการ commit)")
    if d.get("agent_text"):
        lines.append("สรุปจากช่างเอกสาร (Flash · ความเห็น ไม่ใช่คำตัดสิน): " + one_line(d["agent_text"], 500))
    return head, "\n".join(lines)


def doc_finalize(job: dict, root: Path, d: dict, snap0, guard0, texts, head1: str, run_status: str) -> None:
    """ตรวจผลหลัง agent จบ → เติมผลใน d (verdict/why/changed/state) · ผลอันตรายย้อนไฟล์ให้ทันที"""
    snap1, guard1 = dirty_snapshot(root), doc_guard(root)
    spec = {"name": d["name"], "paths": d["paths"]}
    v, why, changed = doc_verdict(spec, {"status": "DONE" if run_status == "OK" else run_status, "head0": d["head0"], "head1": head1},
                                  root, snap0, snap1, texts, guard0, guard1)
    if v in ("TIMEOUT", "ERROR") and not changed:  # agent ไม่จบ/ตรวจไม่ได้ แต่อาจแก้ไฟล์ค้างไว้ → ต้องรายงาน ไม่ปล่อยเงียบ
        changed = doc_changed(snap0, snap1) + [p for p in doc_guarded(guard0, guard1)]
        if changed:
            why = why + [f"มีไฟล์ถูกแก้ค้างไว้ {len(changed)} ไฟล์ (ดู diff ก่อน — จะทิ้งก็ได้)"]
    d.update(verdict=v, why=why, changed=changed, state="pending" if changed else "none")
    if v in DOC_AUTO_REVERT and changed:
        probs = doc_restore(root, d["backup"], changed, d["head0"])
        d["revert_problems"] = probs
        d["state"] = "reverted" if not probs else "pending"
    d["after_sha"] = {p: doc_sha(root / p) for p in changed} if d["state"] == "pending" else {}


def doc_cancelled(j: dict) -> str:
    """ช่างเอกสารถูกยกเลิก (process ถูกฆ่า ไม่มีโอกาสตรวจผลเอง) → ดูว่า agent แก้อะไรค้างไว้ แล้วบันทึกให้ผู้ใช้ทิ้งได้ · ไม่ย้อนให้เอง (ผู้ใช้เป็นคนกดยกเลิก)"""
    d, root = j["doc"], Path(j["project"])
    d.update(verdict="CANCELLED", why=["ผู้ใช้ยกเลิกกลางทาง — ไม่ได้ตรวจเนื้อหา"], phase="done", name=d.get("name", ""))
    try:
        ch = doc_changed(d.get("snap0"), dirty_snapshot(root)) + doc_guarded(d.get("guard0") or {}, doc_guard(root))
    except Exception:
        ch = []
    d.update(changed=ch, state="pending" if ch else "none", after_sha={p: doc_sha(root / p) for p in ch})
    j["last"] = "\n".join(doc_summary({**d, "job": j["id"]}))[:1500]
    return f"ไฟล์ที่ช่างเอกสารแก้ค้างไว้ {len(ch)} ไฟล์ (ทิ้งได้ด้วย flashq doc-review {j['id'][:12]} discard)" if ch else "ไม่มีไฟล์ถูกแก้"


def doc_since(root: Path, name: str, given: str) -> tuple[str, str]:
    """ฐานเทียบ "โค้ดที่เปลี่ยน": --since (ต้องเป็น commit จริง) · ไม่ระบุ = HEAD ตอนที่ช่างเอกสารชุดนี้ถูกรับ (accepted) ครั้งล่าสุด · ไม่มี = "" · คืน (ref, ข้อผิดพลาด)"""
    def commit(ref: str) -> str:
        return _git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") if re.fullmatch(r"[\w./~^-]{1,100}", ref or "") and not ref.startswith("-") else ""
    if given:
        c = commit(given)
        return (c, "") if c else ("", f"--since '{given}' ไม่ใช่ commit ที่มีในโปรเจกต์นี้")
    done = [j for j in jobs() if j.get("kind") == "doc" and _pnorm(j.get("project", "")) == _pnorm(str(root)) and (j.get("doc") or {}).get("name") == name
            and (j.get("doc") or {}).get("state") == "accepted"]
    done.sort(key=lambda j: j.get("finished", ""))
    return (commit(done[-1]["doc"].get("head0", "")) if done else ""), ""


# ---------- ตรวจขอบเขตไฟล์ของ commit กับแผน (กลไกล้วน ไม่กินโควตาโมเดล) ----------
SCOPE_HEAD_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s*\*\*(T-\d+[A-Za-z]*\d*)\b([^*]*)\*\*(.*)$")  # หัวงาน: **T-01** · **T-01 (RED)** · **T-12 + DoD**
SCOPE_ROW_RE = re.compile(r"^\|\s*(T-\d+[A-Za-z]*\d*)\b[^|]*\|([^|]*)\|([^|]*)\|")  # แถว §4: | T-01 | ผล | hash |
SCOPE_HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
SCOPE_PATH_RE = re.compile(r"`([^`\s]+[/\\.][^`\s]*)`")


def scope_norm(p: str) -> str:
    p = p.replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def scope_parse(text: str) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """อ่านแผน → (path ที่แต่ละงานแก้ได้, hash ใน §4) · path = ทุกตัวใน ` บนบรรทัดหัวงาน + บรรทัด "ไฟล์:"/"แก้ไฟล์:" ใต้หัวงาน"""
    allow: dict[str, set[str]] = {}
    hashes: dict[str, list[str]] = {}
    cur = None
    for line in text.splitlines():
        m = SCOPE_HEAD_RE.match(line)
        if m:
            cur = m.group(1)
            allow.setdefault(cur, set()).update(scope_norm(p) for p in SCOPE_PATH_RE.findall(m.group(2) + " " + m.group(3)))
            continue
        if cur and re.match(r"^\s+-\s*(ไฟล์|แก้ไฟล์)\s*[:：]", line):
            allow[cur].update(scope_norm(p) for p in SCOPE_PATH_RE.findall(line))
        if line.startswith("## "):
            cur = None
        r = SCOPE_ROW_RE.match(line)
        if r:
            hs = SCOPE_HASH_RE.findall(r.group(3))
            if hs:
                hashes[r.group(1)] = hs
    return allow, hashes


SCOPE_BASE_RE = re.compile(r"base commit[^`\n]*`([0-9a-fA-F]{7,40})`")  # หัวแผน: base commit ตอนวางแผน: `<hash>`


def scope_find_commits(root: Path, t: str, plan: Path, text: str) -> tuple[list[str], str]:
    """หา commit ของงาน t เมื่อ §4 ไม่มี hash จริง (worker commit พร้อมแก้แผน → ใส่ hash ของ commit ตัวเองไม่ได้ จึงเหลือ "(HEAD)")
    คืน (hash เต็ม, แหล่ง): "job" = commit ในช่วง head0..head1 ของงานที่ flashq รันเอง (ละเอียดสุด) · "base" = ตั้งแต่ base commit ในหัวแผน (ต้องเจอ commit เดียวเท่านั้น)
    commit ต้องมี T-xx แบบเต็มคำในข้อความ/trailer (T-01 ไม่ชน T-01R, T-010)"""
    rx = re.compile(r"(?<![A-Za-z0-9-])" + re.escape(t) + r"(?![A-Za-z0-9])")
    ranges = [f"{j['head0']}..{j['head1']}" for j in jobs() if j.get("head0") and j.get("head1") and j["head0"] != j["head1"] and not j.get("readonly")
              and _pnorm(j.get("project", "")) == _pnorm(str(root)) and Path(str(j.get("plan") or "").replace("\\", "/")).name == plan.name]
    m = SCOPE_BASE_RE.search(text)
    base = _git(root, "rev-parse", "--verify", "-q", f"{m.group(1)}^{{commit}}") if m else ""
    for src, specs in (("job", ranges), ("base", [f"{base}..HEAD"] if base else [])):
        found: list[str] = []
        for spec in specs:
            r = run_timeout(["git", "-C", str(root), "log", "--reverse", "--format=%H%x00%B%x01", spec], 60)
            if r.returncode != 0:  # ประวัติถูก rebase/amend → hash ในช่วงหาไม่เจอ → ลองแหล่งถัดไป
                continue
            for rec in r.stdout.split("\x01"):
                h, _, msg = rec.strip().partition("\x00")
                if h and rx.search(msg) and h not in found:
                    found.append(h)
        if found:
            return found, src
    return [], ""


def scope_fill(plan: Path, filled: dict[str, list[str]]) -> int:
    """เติม hash จริงลงช่อง commit ของแถว §4 (เฉพาะแถวที่มีอยู่แล้ว) · คงเข้ารหัส/BOM/ปลายบรรทัดเดิม · คืนจำนวนแถวที่แก้"""
    raw = plan.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8-sig").split("\n")
    n = 0
    for i, line in enumerate(lines):
        r = SCOPE_ROW_RE.match(line.rstrip("\r"))
        if r and r.group(1) in filled:
            cr = "\r" if line.endswith("\r") else ""
            body = line.rstrip("\r")
            lines[i] = body[:r.start(3)] + " " + ", ".join(h[:10] for h in filled[r.group(1)]) + " " + body[r.end(3):] + cr
            n += 1
    if n:
        plan.write_bytes((b"\xef\xbb\xbf" if bom else b"") + "\n".join(lines).encode("utf-8"))
    return n


def cmd_scope(a) -> int:
    """flashq scope <แผน> [T-xx...] — ไฟล์ที่ commit ของแต่ละงานแตะ ต้องอยู่ในรายการที่แผนอนุญาต
    ไฟล์แผนเอง (ติ๊ก [x] + เติม §4) ผ่านเสมอ · ไฟล์ที่โปรเจกต์ยกเว้นเพิ่ม → .flash.json scope.always_ok (glob)
    §4 ไม่มี hash จริง → หา commit จากช่วงงานที่ flashq จดไว้/ข้อความ commit ที่มี T-xx (scope_find_commits) · --fill เติม hash ที่หาได้ลงแผน
    exit 0 = PASS · 1 = มีงานแตะเกิน/ไม่มี commit/ไม่ระบุ path · 2 = อ่านแผนไม่ได้"""
    start = Path(a.project or os.getcwd())
    root, is_git = project_root(start)
    plan = Path(a.plan)
    if not plan.is_absolute() and not plan.is_file() and (root / plan).is_file():
        plan = root / plan
    try:
        text = plan.read_text(encoding="utf-8-sig")
    except OSError as e:
        print(f"SCOPE_RESULT=ERROR อ่านแผนไม่ได้: {e}")
        return 2
    if not is_git:
        print("SCOPE_RESULT=ERROR ใช้ได้เฉพาะโปรเจกต์ git")
        return 2
    cfg = project_cfg(root)
    block = cfg.get("scope") if isinstance(cfg.get("scope"), dict) else {}
    always = [scope_norm(str(g)) for g in (block.get("always_ok") or []) if isinstance(g, str)]
    try:
        self_plan = scope_norm(os.path.relpath(os.path.abspath(plan), str(root)))
    except ValueError:  # คนละไดรฟ์
        self_plan = ""
    allow, hashes = scope_parse(text)
    wanted = [t for t in re.split(r"[,\s]+", " ".join(a.tasks)) if t] or sorted(set(allow) | set(hashes))
    bad = 0
    found_by: dict[str, list[str]] = {}  # งานที่ §4 ไม่มี hash แต่หา commit เจอเอง
    for t in wanted:
        if t not in hashes:
            hs, src = scope_find_commits(root, t, plan, text)
            if not hs:
                print(f"SCOPE {t} NOCOMMIT ไม่มี hash ใน §4 และหา commit ที่มี {t} ในข้อความไม่เจอ")
                bad += 1
                continue
            if src == "base" and len(hs) > 1:  # ไม่มีช่วงงานจาก flashq ให้ยืนยัน → เดาจากข้อความอย่างเดียวต้องไม่กำกวม
                print(f"SCOPE {t} NOCOMMIT ไม่มี hash ใน §4 และมี {len(hs)} commit ที่ข้อความมี {t} ({', '.join(h[:8] for h in hs)}) — ใส่ hash ที่ถูกลง §4")
                bad += 1
                continue
            hashes[t], found_by[t] = hs, hs
        if not allow.get(t):
            print(f"SCOPE {t} NOFILES แผนไม่ระบุ path บนหัวงาน — ตรวจเองไม่ได้")
            bad += 1
            continue
        extra: list[str] = []
        for h in hashes[t]:
            r = run_timeout(["git", "-C", str(root), "show", "--name-only", "--format=", h], 60)
            if r.returncode != 0:
                extra.append(f"(hash {h} ไม่พบ)")
                continue
            files = [scope_norm(x) for x in r.stdout.splitlines() if x.strip()]
            extra += [f for f in files if f not in allow[t] and f != self_plan and not (always and _glob_hit(f, always))]
        if extra:
            ex = sorted(set(extra))
            more = f" (+อีก {len(ex) - 8})" if len(ex) > 8 else ""
            print(f"SCOPE {t} EXTRA {len(ex)} ไฟล์: " + ", ".join(ex[:8]) + more)
            bad += 1
        else:
            print(f"SCOPE {t} OK" + (f" (§4 ไม่มี hash — หา commit จากข้อความ {t}: {', '.join(h[:8] for h in found_by[t])})" if t in found_by else ""))
    if getattr(a, "fill", False):  # เติมเฉพาะเมื่อทุกงานผ่าน — ไม่จดหลักฐานของงานที่ยังมีปัญหาลงแผน
        n = scope_fill(plan, found_by) if found_by and not bad else 0
        print(f"FILL เติม hash ลง §4 {n} แถว" if n else ("FILL ไม่เติม — ยังมีงานไม่ผ่าน" if found_by and bad else "FILL ไม่มีแถวต้องเติม"))
    print("SCOPE_RESULT=" + ("FAIL" if bad else "PASS"))
    return 1 if bad else 0


def cmd_doc(a) -> int:
    root, is_git = project_root(Path(a.project or os.getcwd()))
    if not is_git:
        print("FLASH_RUN=FAIL ช่างเอกสารใช้ได้เฉพาะโปรเจกต์ git (ต้องมี diff ให้ตรวจและย้อนกลับ)")
        return 1
    cfg = project_cfg(root)
    block = cfg.get("doc") if isinstance(cfg.get("doc"), dict) else {}
    presets = block.get("presets") if isinstance(block.get("presets"), dict) else {}
    name = a.doc_name or (next(iter(presets)) if len(presets) == 1 else "")
    errs = []
    if not presets:
        errs.append("โปรเจกต์นี้ยังไม่ได้ตั้งชุดเอกสาร (.flash.json → doc.presets เช่น {\"docs\": {\"paths\": [\"docs/**\", \"README.md\"], \"brief\": \"...\"}})")
    elif not name:
        errs.append(f"ต้องระบุชื่อชุด (doc.presets มี: {', '.join(presets)})")
    elif name not in presets:
        errs.append(f"ไม่มีชุดเอกสารชื่อ '{name}' ใน .flash.json (doc.presets มี: {', '.join(presets)})")
    elif not QA_NAME_RE.match(name):
        errs.append(f"ชื่อชุดเอกสาร '{name}' ใช้ได้แค่ตัวอักษร/ตัวเลข _ . - (ยาวไม่เกิน 40)")
    spec = None
    if not errs:
        spec = doc_spec(name, presets[name], float(cfg.get("doc_timeout_min") or DEFAULTS["doc_timeout_min"]))
        if isinstance(spec, str):
            errs.append(spec)
    since, err = doc_since(root, name, a.since) if not errs else ("", "")
    if err:
        errs.append(err)
    exe = opencode_cmd()
    if not errs and not exe:
        errs.append("ไม่พบคำสั่ง opencode ใน PATH")
    if not errs and not _git(root, "rev-parse", "HEAD"):
        errs.append("โปรเจกต์นี้ยังไม่มี commit เลย")
    if errs:
        print("FLASH_RUN=FAIL ช่างเอกสารเริ่มไม่ได้:")
        for e in errs:
            print(f"  - {e}")
        return 1
    if a.timeout_min:
        spec["timeout_min"] = float(a.timeout_min)
    prompt = doc_prompt(spec, since)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jid = f"{ts}_{os.getpid()}"
    title = one_line(a.title or f"flash-doc {name}", 200)
    bad = cmd_shim_unsafe(exe, title, prompt)
    if bad:
        print(f"FLASH_RUN=FAIL opencode ถูกเรียกผ่าน cmd.exe แต่บรีฟมีอักขระ {bad} ที่ cmd.exe ตีความเอง → ตัดอักขระเหล่านี้ออกจาก doc.presets.{name} หรือตั้ง FLASHQ_OPENCODE เป็น opencode.exe ตัวจริง")
        return 1
    for d in (JOBS, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    agent = "flash-writer"
    d = {"name": name, "job": jid, "paths": spec["paths"], "since": since, "head0": "", "phase": "queued", "state": "", "verdict": "", "why": [], "changed": []}
    job = {"id": jid, "project": str(root), "plan": "", "tasks": name, "message": "", "kind": "doc", "agent": agent, "prompt": prompt, "readonly": False,
           "title": title, "model": a.model or agent_model(agent), "status": "queued", "pid": os.getpid(), "pid_start": proc_start(os.getpid()),
           "created": now(), "qv": QUEUE_VERSION, "claude_session": os.environ.get("CLAUDE_CODE_SESSION_ID", ""), "claude_host": os.environ.get("CLAUDE_CODE_HOST_SESSION_ID", ""), "doc": d}
    save_job(job)
    got = acquire(job, a.wait_min, a.no_wait)
    if got != "ok":
        job.update(status="busy" if got == "busy" else "queue_timeout", finished=now())
        save_job(job)
        notify_job(job, job["status"].upper())
        return 2 if got == "busy" else 3

    status, rc_out, t_start, res = "FAIL", 1, time.time(), {"status": "FAIL"}
    snap0 = guard0 = texts = None
    try:
        job.update(status="running", started=now())
        save_job(job)
        print(f"SLOT ช่อง {job.get('slot', 1)} (max_parallel={max_parallel()})", flush=True)
        head0 = _git(root, "rev-parse", "HEAD")
        snap0, guard0 = dirty_snapshot(root), doc_guard(root)
        if snap0 is None or not head0:
            raise RuntimeError("อ่านสถานะ git ไม่ได้ จึงตรวจไม่ได้ว่าช่างเอกสารแก้อะไร — ไม่เริ่ม")
        texts = doc_before(root, snap0)
        if len(snap0) > DOC_SNAP_CAP:
            raise RuntimeError(f"ไฟล์ที่ยังไม่ commit เกิน {DOC_SNAP_CAP} ไฟล์ — commit/เก็บงานเก่าก่อนค่อยใช้ช่างเอกสาร (แยกไม่ออกว่าใครแก้ไฟล์ไหน)")
        d.update(head0=head0, phase="write", backup=doc_backup(root, jid, snap0, guard0), guard0=guard0, snap0=dict(snap0))
        save_job(job)
        print(f"DOC_START ชุด {name} paths={', '.join(spec['paths'])} since={since[:10] or '-'} timeout={spec['timeout_min']:g}นาที", flush=True)
        ext_dirs = external_dirs(cfg)
        env = {**os.environ, "OPENCODE_CONFIG_CONTENT": perm_config_content(ext_dirs)} if ext_dirs else None
        variant = variant_for("doc", a.variant, root)
        job.update(attach="", **({"variant": variant} if variant else {}))
        save_job(job)
        attempt, nostart_retry, stall_retry, switches, tried = 0, 1, 1, 0, set()
        while True:
            attempt += 1
            cmd = [*exe, "run", "--dir", str(root), "--title", title, "--format", "json"]
            if job["model"]:
                cmd += ["--model", job["model"]]
            if variant:
                cmd += ["--variant", variant]
            cmd += ["--agent", agent, "--", prompt]
            res = run_once(job, cmd, root, "", spec["timeout_min"], True, attempt, cfg["agent_stall_min"], cfg["agent_stall_floor_min"], 0, env)
            if res["status"] == "TIMEOUT" and job.get("timeout_reason", "").startswith("STALL") and stall_retry > 0:
                stall_retry -= 1
                print(f"TIMEOUT ({job.get('timeout_reason', '')}) → ลองใหม่อัตโนมัติ 1 ครั้ง (ไฟล์ที่แก้ไว้แล้วคงอยู่ · ช่างเอกสารอ่านต่อจากสถานะปัจจุบัน)", flush=True)
                continue
            if res["status"] == "NOSTART" and nostart_retry > 0:
                nostart_retry -= 1
                print("NOSTART → ลองใหม่อัตโนมัติ 1 ครั้ง", flush=True)
                continue
            if res["status"] == "QUOTA" and job["model"] and switches < a.switch_on_quota:
                tried.add(job["model"])
                alts = other_providers(job["model"], tried)
                if alts:
                    switches += 1
                    print(f"QUOTA → ย้าย provider {job['model']} → {alts[0]} (โมเดลเดิม) แล้วสั่งซ้ำ (ครั้งที่ {switches})", flush=True)
                    job["model"] = alts[0]
                    save_job(job)
                    continue
            break
        d["phase"] = "check"
        save_job(job)
        doc_finalize(job, root, d, snap0, guard0, texts, _git(root, "rev-parse", "HEAD"), res["status"])
        d["agent_text"] = (res.get("last") or "")[-800:]
        status = "OK" if d["verdict"] == "DRAFT" else ("TIMEOUT" if d["verdict"] == "TIMEOUT" else "FAIL")
        rc_out = 0 if status == "OK" else 1
    except Exception as e:
        d.update(verdict="ERROR", why=[f"flashq ผิดพลาดกลางทาง: {e}"])
        if d.get("phase") in ("write", "check") and d.get("backup") and snap0 is not None:  # agent อาจแก้ไฟล์ค้างไว้ → บันทึกไว้ให้ทิ้งได้
            try:
                ch = doc_changed(snap0, dirty_snapshot(root)) + doc_guarded(guard0, doc_guard(root))
                d.update(changed=ch, state="pending" if ch else "none", after_sha={p: doc_sha(root / p) for p in ch})
            except Exception:
                d["state"] = "pending"
        print(f"ERROR: {e}", flush=True)
    finally:
        mins = (time.time() - t_start) / 60
        if not d.get("verdict"):  # ถูกขัดจังหวะ (Ctrl+C ฯลฯ) ก่อนตัดสิน
            d.update(verdict="ERROR", why=["ถูกขัดจังหวะก่อนตรวจผล — ไฟล์ที่แก้ค้างอาจมี (ดู git status)"], state="pending")
        head_line, body = doc_summary(d)
        d["phase"] = "done"
        job.update(status=status.lower(), result=status, rc=rc_out, finished=now(), last=(head_line + "\n" + body)[:1500])
        save_job(job)
        release(job)
        notify_job(job, status, mins)
    print(f"FLASH_RUN={status} exit={rc_out} เวลา={mins:.1f} นาที tool={res.get('tools', 0)} session={job.get('session', '')} job={jid}")
    print(f"DOC={d['verdict']} {head_line}")
    print("---- สรุปผลช่างเอกสาร ----")
    print(body)
    return rc_out


def doc_review(j: dict, action: str, force: bool = False) -> tuple[bool, str]:
    """ผู้ใช้ตัดสินร่างของช่างเอกสาร (ใช้ร่วมกับ CLI และหน้าเว็บ) · accept = เก็บไฟล์ไว้ (ไม่ commit ให้) · discard = ย้อนเฉพาะไฟล์ที่ช่างเอกสารแตะ"""
    d = j.get("doc") if j.get("kind") == "doc" else None
    if not d:
        return False, f"job {j['id']} ไม่ใช่งานช่างเอกสาร"
    if live_state(j) in ("queued", "running"):
        return False, f"job {j['id']} ยังทำงานอยู่ — รอให้จบ (หรือ cancel) ก่อน"
    if d.get("state") != "pending":
        return False, f"job {j['id']} ไม่มีร่างรอตัดสิน (state={d.get('state') or '-'})"
    root = Path(j["project"])
    if action == "accept":
        if d.get("verdict") != "DRAFT":
            return False, f"รับไม่ได้: ผลคือ {d.get('verdict')} ({DOC_MEANING.get(d.get('verdict'), '')}) — ผ่านด่านกลไกไม่ครบ · แก้เองแล้ว commit ก็ได้ หรือสั่ง discard"
        d.update(state="accepted", accepted=now())
        save_job(j)
        return True, f"รับร่างเอกสารแล้ว ({len(d.get('changed') or [])} ไฟล์) — ไฟล์อยู่ใน checkout ยังไม่ได้ commit · ตรวจ diff แล้ว commit เองเมื่อพร้อม"
    head = _git(root, "rev-parse", "HEAD")
    if head != d.get("head0"):
        return False, f"ทิ้งไม่ได้: HEAD เปลี่ยนแล้ว ({(d.get('head0') or '')[:10]} → {head[:10]}) — ย้อนเองด้วย git (ไม่เสี่ยงทับงานที่ commit ไปแล้ว)"
    changed = d.get("changed") or []
    edited = [p for p in changed if d.get("after_sha", {}).get(p) is not None and doc_sha(root / p) != d["after_sha"][p]]
    if edited and not force:
        return False, "ทิ้งไม่ได้: มีไฟล์ที่ถูกแก้ต่อหลังช่างเอกสารจบ (ย้อนแล้วงานของคุณหาย): " + ", ".join(edited[:6]) + " · ยืนยันด้วย --force"
    probs = doc_restore(root, d.get("backup") or {}, changed, d["head0"])
    if probs:
        d["revert_problems"] = probs
        save_job(j)
        return False, "ย้อนไม่ครบ:\n" + "\n".join(f"  ✗ {p}" for p in probs)
    d.update(state="discarded", discarded=now())
    save_job(j)
    return True, f"ทิ้งร่างแล้ว — ย้อน {len(changed)} ไฟล์กลับสถานะก่อนช่างเอกสารรัน"


def cmd_doc_review(a) -> int:
    """flashq doc-review <id> accept|discard"""
    j = find_job(a.id)
    if not j:
        return 1
    ok, msg = doc_review(j, a.action, a.force)
    print(msg)
    return 0 if ok else 1


DOC_DIFF_FILES, DOC_DIFF_CHARS = 20, 200_000


def doc_diff(j: dict) -> dict:
    """diff ที่ช่างเอกสารทำ (เทียบกับสถานะก่อนรัน: ไฟล์ที่เคยสกปรก = เทียบกับที่สำรองไว้ · ไม่งั้นเทียบ HEAD เดิม · ไฟล์ใหม่ = ทั้งไฟล์) — ทำใน Python ไม่เรียก git diff (เห็นไฟล์ใหม่ด้วย)"""
    d = j.get("doc") or {}
    root, head0, bak = Path(j.get("project", "")), d.get("head0", ""), d.get("backup") or {}
    parts, total, rroot = [], 0, root.resolve()
    changed = [doc_norm_path(p) for p in d.get("changed") or []]
    for rel in changed[:DOC_DIFF_FILES]:
        if not rel or ".." in rel.split("/") or rel.startswith(".git"):
            continue
        try:
            if not (rroot / rel).resolve().is_relative_to(rroot):
                continue
            if rel in bak.get("saved", []):
                old = (Path(bak["dir"]) / rel).read_bytes()
            elif rel in bak.get("absent", []) or run_timeout(["git", "-C", str(root), "cat-file", "-e", f"{head0}:{rel}"], 30).returncode != 0:
                old = b""
            else:
                old = subprocess.run(["git", "-C", str(root), "show", f"{head0}:{rel}"], capture_output=True, timeout=30).stdout
            p = rroot / rel
            new = p.read_bytes() if p.is_file() else b""
        except (OSError, subprocess.SubprocessError):
            parts.append(f"--- {rel}\n(อ่านไฟล์ไม่ได้)\n")
            continue
        if b"\x00" in old[:4096] or b"\x00" in new[:4096]:
            parts.append(f"--- {rel}\n(ไฟล์ไบนารี ดู diff ไม่ได้)\n")
            continue
        txt = "".join(difflib.unified_diff(old.decode("utf-8", "replace").splitlines(True), new.decode("utf-8", "replace").splitlines(True),
                                          f"ก่อน/{rel}", f"หลัง/{rel}", n=2)) or f"--- {rel}\n(เนื้อหาเท่าเดิม)\n"
        total += len(txt)
        if total > DOC_DIFF_CHARS:
            parts.append(f"(diff ยาวเกิน {DOC_DIFF_CHARS} ตัวอักษร — ตัดที่ {rel} · ดูส่วนที่เหลือด้วย git diff)\n")
            break
        parts.append(txt if txt.endswith("\n") else txt + "\n")
    if len(changed) > DOC_DIFF_FILES:
        parts.append(f"(และอีก {len(changed) - DOC_DIFF_FILES} ไฟล์ — ดูด้วย git diff)\n")
    return {"id": j.get("id"), "files": changed, "diff": "".join(parts)}


def doc_preset_names(project: str) -> list[str]:
    """ชื่อชุดเอกสารที่ตั้งไว้ในโปรเจกต์ (อ่าน .flash.json ตรง ๆ ไม่เรียก git)"""
    doc = read_json(Path(project) / ".flash.json").get("doc") if project else None
    presets = doc.get("presets") if isinstance(doc, dict) else None
    return [n for n in presets if QA_NAME_RE.match(str(n))] if isinstance(presets, dict) else []


def kind_tag(j: dict) -> str:
    return {"verify": "[ตรวจ] ", "investigate": "[สืบ] ", "qa": "[ทดสอบ] ", "doc": "[เอกสาร] "}.get(j.get("kind"), "")


def plan_label(j: dict) -> str:
    """ชื่องานที่แสดงคู่ kind_tag: แผน · ไม่มีแผน = --message · นักทดสอบ/ช่างเอกสารไม่มีทั้งคู่ (ชื่อชุดอยู่ใน tasks)"""
    return j.get("plan") or ("" if j.get("kind") in ("qa", "doc") else "--message")


def notify_job(job: dict, status: str, mins: float = 0.0) -> None:
    """งานจบ (ทุกสถานะ) → ใส่ inbox ให้ hook inbox_notify.py แทรกเข้า session Claude ตอนผู้ใช้พิมพ์ข้อความถัดไป + toast Windows
    ไม่เรียกโมเดลเลย (ไม่เสีย token ระหว่างรอ) · พังเองไม่กระทบงาน · ปิดทั้งหมด: config.json {"notify": false} · ปิดเฉพาะ toast: {"notify_toast": false}"""
    try:
        cfg = read_config()
        if cfg.get("notify") is False:
            return
        INBOX.mkdir(parents=True, exist_ok=True)
        label = f"{kind_tag(job)}{plan_label(job)} {job.get('tasks', '')}".strip()
        last = job.get("last") or ""
        row = {"job": job["id"], "project": job.get("project", ""), "session": job.get("claude_session", ""),
               "kind": job.get("kind", ""), "plan": job.get("plan", ""), "tasks": job.get("tasks", ""), "status": status,
               "mins": round(mins, 1), "last": last[:600] if job.get("kind") in ("qa", "doc") else last[-600:], "at": time.time()}  # นักทดสอบ/ช่างเอกสาร: หัวข้อผลอยู่บรรทัดแรก
        write_json(INBOX / f"{time.strftime('%Y%m%d-%H%M%S')}-{job['id']}.json", row)
        if os.name == "nt" and status != "CANCELLED" and cfg.get("notify_toast", True) is not False and not os.environ.get("FLASHQ_NO_TOAST"):  # ผู้ใช้กดยกเลิกเอง ไม่ต้องเด้งซ้ำ
            ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;$n.Visible=$true;"
                  "$n.ShowBalloonTip(8000,$env:FQ_T,$env:FQ_B,'Info');Start-Sleep 9;$n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                             env={**os.environ, "FQ_T": f"flashq: {status} ({job.get('id')})", "FQ_B": f"{Path(job.get('project', '')).name} · {label}"[:200]},
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    except Exception:
        pass


def dismiss_dead(j: dict) -> str:
    """รับทราบงานที่ process ตายค้างสถานะ queued/running → เก็บกวาดลูกที่รอด + บันทึกสถานะ dead · คืนข้อความหมายเหตุ ("" = ไม่มี)"""
    note = reap_orphan(j, abort=j.get("status") == "running")  # ลูกที่ยังรอดอยู่ต้องถูกเก็บกวาดด้วย ไม่งั้นแก้ไฟล์ต่อโดยไม่มีใครเห็น
    j.update(status="dead", dismissed=now())  # ไม่ใส่ finished: ไม่รู้ว่าตายเมื่อไร
    save_job(j)
    release(j)
    return note


def dead_clear_hours() -> float:
    try:
        return max(0.0, float(read_config().get("dead_clear_hours", 24)))
    except (TypeError, ValueError):
        return 24.0


def auto_clear_dead() -> int:
    """ป้ายงานตายที่ค้างเกิน dead_clear_hours (นับจากครั้งสุดท้ายที่ไฟล์งานถูกเขียน) → รับทราบให้เอง · ข้ามงานที่ opencode ลูกยังทำงานอยู่ (ต้องให้คนตรวจ) · คืนจำนวนที่ล้าง"""
    hours = dead_clear_hours()
    if not hours:
        return 0
    n = 0
    for j in jobs():
        if live_state(j) != "dead" or j.get("status") not in ("queued", "running"):
            continue
        try:
            if time.time() - (JOBS / f"{j['id']}.json").stat().st_mtime < hours * 3600:
                continue
            if pid_alive(j.get("child_pid") or 0, j.get("child_pid_start") or 0):
                continue
            dismiss_dead(j)
            n += 1
        except Exception:
            pass
    return n


def sweep_dead() -> int:
    """งานที่ process หลักตายกลางคัน (เครื่อง/terminal ปิด) ไม่มีใครเขียน inbox ให้ → ตรวจแล้วแจ้งแทน (ครั้งเดียวต่องาน · ติดธง dead_notified)
    เรียกจาก hook inbox_notify.py ก่อนอ่าน inbox · คืนจำนวนงานที่แจ้ง"""
    n = 0
    for j in jobs():
        if live_state(j) != "dead" or j.get("dead_notified"):
            continue
        try:
            j["dead_notified"] = True
            save_job(j)
            j["last"] = "process ของงานหายไปก่อนจบ (เครื่อง/terminal ปิด?) — " + (j.get("last") or "")
            notify_job(j, "DEAD")
            n += 1
        except Exception:
            pass
    auto_clear_dead()  # แจ้งครบแล้ว ค่อยล้างป้ายที่ค้างเกินเวลาที่ตั้ง
    return n


def cmd_sweep(a) -> int:
    print(f"แจ้งงานที่ process ตายแล้ว {sweep_dead()} งาน")
    return 0


def cmd_inbox(a) -> int:
    """แสดงผลงานที่จบแล้วของโปรเจกต์นี้ (cwd) แล้วย้ายเข้า inbox/done — ทางเดียวกับ hook inbox_notify.py แต่เรียกเองได้ (ผู้สั่งที่ไม่ใช่ Claude Code ไม่มี hook)"""
    import io
    src = REPO / "hooks" / "inbox_notify.py"
    if not src.exists():
        print(f"ไม่พบ {src} — รัน install ใหม่จากที่อยู่จริงของ flashq")
        return 1
    ns: dict = {"__name__": "inbox_notify"}
    exec(compile(fill_template(src.read_text(encoding="utf-8"), True), str(src), "exec"), ns)
    ns["mine"] = lambda row, session, cwd, now: ns["related"](row.get("project", ""), cwd)  # เรียกเอง = ทุกงานของโปรเจกต์นี้ ไม่กรองตาม session ของผู้สั่ง (ผู้สั่งต่างตัวกันได้)
    old_in, old_out = sys.stdin, sys.stdout
    buf = io.BytesIO()  # hook เรียก sys.stdout.reconfigure → ต้องเป็น TextIOWrapper ไม่ใช่ StringIO
    sys.stdin, sys.stdout = io.StringIO(json.dumps({"cwd": os.getcwd(), "session_id": ""})), io.TextIOWrapper(buf, encoding="utf-8")
    try:
        ns["main"]()
        sys.stdout.flush()
        text = buf.getvalue().decode("utf-8").strip()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    print(text or "ไม่มีผลงานใหม่ของโปรเจกต์นี้")
    return 0


def wait_targets(target: str) -> list[dict]:
    """งานที่ตรงกับ target: id (ขึ้นต้น) หรือชื่อแผน/stem · เลือกงานที่ยังไม่จบก่อน ไม่มี = งานล่าสุดของแผนนั้น"""
    rows = jobs()
    hit = [j for j in rows if j["id"].startswith(target)]
    if not hit:
        stem = Path(target).stem.lower()
        hit = [j for j in rows if j.get("plan") and Path(j["plan"]).stem.lower() == stem]
    live = [j for j in hit if live_state(j) in ("queued", "running")]
    return live or hit[-1:]


def cmd_wait(a) -> int:
    """บล็อกจนงานจบ (Claude รันคำสั่งนี้ใน background แล้วรอแจ้งเตือน — ไม่ต้อง sleep/poll เอง) · พิมพ์ FLASH_RUN=... ของทุกงานที่รอ
    exit 0 = OK ทั้งหมด · 1 = มีงานไม่ OK/ไม่พบงาน · 3 = ยังไม่จบในเวลาที่ให้"""
    t0 = time.time()
    targets = wait_targets(a.target)
    if not targets:
        print(f"FLASH_WAIT=NOJOB ไม่พบงานที่ตรงกับ '{a.target}' (ดู: flashq list --all)")
        return 1
    ids = [j["id"] for j in targets]
    print(f"รอ {len(ids)} งาน: {', '.join(ids)} (เพดาน {a.timeout_min:g} นาที · เช็กทุก {a.poll:g} วิ)", flush=True)
    noted = time.time()
    cur = targets
    while True:
        cur = [next((j for j in jobs() if j["id"] == i), {"id": i, "status": "?"}) for i in ids]
        pending = [j for j in cur if live_state(j) in ("queued", "running")]
        if not pending:
            break
        if time.time() - t0 > a.timeout_min * 60:
            print(f"FLASH_WAIT=TIMEOUT ยังไม่จบใน {a.timeout_min:g} นาที: " + ", ".join(f"{j['id']} ({live_state(j)})" for j in pending)
                  + " → สั่ง wait ใหม่ หรือ flashq why")
            return 3
        if time.time() - noted >= 600:  # บรรทัดเดียวทุก 10 นาที พอให้รู้ว่ายังรอ (ไม่ถมผลลัพธ์)
            noted = time.time()
            print(f"  … {(time.time() - t0) / 60:.0f} นาที · " + " · ".join(f"{j['id']} {live_state(j)}" for j in pending), flush=True)
        time.sleep(a.poll)
    rc = 0
    for j in cur:
        st = live_state(j)
        res = "DEAD" if st == "dead" else str(j.get("result") or st).upper()
        mins = ""
        try:
            mins = f" เวลา={(_ts(j['finished']) - _ts(j['started'])) / 60:.1f} นาที" if j.get("finished") and j.get("started") else ""
        except Exception:
            pass
        print(f"FLASH_RUN={res} job={j['id']} {kind_tag(j)}{plan_label(j)} {j.get('tasks', '')}{mins}"
              + (f" session={j['session']}" if j.get("session") else ""))
        if res == "DEAD":
            print("  (process ของงานหายไปก่อนจบ — เครื่อง/terminal ปิด? ดู flashq log แล้วสั่งใหม่)")
        if j.get("perm_denied"):
            for ln in perm_fix_lines(j["perm_denied"], partial=res != "DENIED"):
                print(ln)
        print("---- สรุปท้าย ----")
        print((j.get("last") or "(ไม่มีข้อความ)")[-1500:])
        if res not in ("OK", "OK_UNVERIFIED"):
            rc = 1
    return rc


def shrink_image(src: Path, out_dir: Path, max_px: int, quality: int = 80) -> tuple[Path, str]:
    """ย่อรูปให้ด้านยาวสุด ≤ max_px แล้วบันทึกเป็น jpg (พื้นโปร่ง → ขาว) · คืน (ไฟล์ผล, "WxH→wxh")"""
    from PIL import Image
    im = Image.open(src)
    w, h = im.size
    scale = min(1.0, max_px / max(w, h))
    if scale < 1:
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    if im.mode not in ("RGB", "L"):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        im = bg
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (src.stem + ".jpg")
    im.save(out, "JPEG", quality=quality, optimize=True)
    return out, f"{w}x{h}→{im.size[0]}x{im.size[1]}"


def cmd_shrink(a) -> int:
    """ย่อรูปก่อนให้ Claude อ่าน: รูปใหญ่ 1 รูป ≈ 1–1.6k token และค้างใน context ทุก turn จนจบ session · ผล = .tmp/shrink/<ชื่อ>.jpg"""
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("SHRINK=FAIL ไม่มี Pillow → pip install pillow")
        return 1
    root, _ = project_root(Path(os.getcwd()))
    out_dir = Path(a.out) if a.out else root / ".tmp" / "shrink"
    rc = 0
    for f in a.images:
        src = Path(f)
        if not src.is_file():
            print(f"SHRINK=FAIL ไม่พบไฟล์: {src}")
            rc = 1
            continue
        try:
            out, dims = shrink_image(src, out_dir, a.max, a.quality)
        except Exception as e:
            print(f"SHRINK=FAIL {src}: {e}")
            rc = 1
            continue
        print(f"SHRINK={out} {dims} {out.stat().st_size // 1024}KB (เดิม {src.stat().st_size // 1024}KB) → อ่านไฟล์นี้แทนต้นฉบับ")
    return rc


def cmd_list(a) -> int:
    rows = jobs()
    if not a.all:
        rows = [j for j in rows if live_state(j) in ("queued", "running")] or rows[-10:]
    if not rows:
        print("(ยังไม่มีงาน)")
        return 0
    for j in rows:
        what = j.get("message") and "--message" or f"{j.get('plan') or ''} {j.get('tasks') or ''}".strip()
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
              + (f" · {Path(j.get('project', '')).name} {kind_tag(j)}{plan_label(j)} {j.get('tasks', '')}" if j else "")
              + (" · ผู้ใช้สั่งรันเลยข้ามคิว" if j.get("forced") else ""))
    print(f"รอคิว: {len(q)} งาน")
    for i, j in enumerate(q, 1):
        why = sch["reasons"].get(j["id"]) or ("กำลังจะเริ่ม" if j["id"] in sch["start"] else "")
        print(f"  {i}. {j['id']} {Path(j['project']).name} {kind_tag(j)}{plan_label(j)} {j.get('tasks', '')}"
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
    qa = j.get("qa") if j.get("kind") == "qa" else None
    if qa and qa.get("phase") == "test":  # นักทดสอบรันคำสั่งเอง ไม่มีโมเดล/server ให้ถาม → ดูแค่ log ของคำสั่ง
        cur = next((s for s in qa.get("specs") or [] if s.get("verdict") == "RUNNING"), {})
        quiet = d["log_idle_sec"]
        quiet_txt = f"log เงียบ {quiet / 60:.0f} นาที" if quiet is not None else "ยังไม่มี log"
        d.update(quiet_sec=quiet, verdict="ok" if quiet is None or quiet < 600 else "tool_long",
                 text=f"นักทดสอบกำลังรันชุด '{cur.get('name', '?')}' (คำสั่งจริง ไม่ผ่านโมเดล) · {quiet_txt}"
                      + ("" if quiet is None or quiet < 600 else " · เงียบนาน อาจเป็นเทสต์ยาวจริงหรือค้าง — เกินเวลาของชุดจะถูกฆ่าและรายงาน TIMEOUT เอง"))
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
        d.update(verdict="unknown", text=base + " · แยกสาเหตุไม่ได้ ("
                                      + ("ถาม server ไม่สำเร็จ — server ไม่ตอบ/ตัดการเชื่อมต่อ ลองใหม่อีกครั้ง" if attach.startswith("http") and sid
                                         else "งานนี้ไม่ได้ต่อ server (--attach none) จึงถามสถานะ tool ไม่ได้") + ")")
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
    if j.get("kind") == "qa" and (j.get("qa") or {}).get("verdict"):  # สรุปเต็ม (ใน last ถูกตัดที่ 1500 ตัวอักษร)
        head, body = qa_summary(j["qa"])
        print(head + "\n" + body)
    elif j.get("kind") == "doc" and (j.get("doc") or {}).get("verdict"):
        head, body = doc_summary({**j["doc"], "job": j["id"]})
        print(head + "\n" + body)
    else:
        print(j.get("last") or "(ยังไม่มี)")
    return 0


def reap_orphan(j: dict, abort: bool = False) -> str:
    """ฆ่า `opencode run` ลูกที่ยังรอดหลัง process `flashq run` เจ้าของตาย (ถูกฆ่าตรง ๆ/ไฟดับ/crash — ไม่ได้ฆ่าทั้งต้น) แล้วยังแก้ไฟล์ซ้อนกับงานถัดไป
    ฆ่าเฉพาะเมื่อยังเป็น process เดิม (เทียบเวลาเริ่ม — กัน pid ถูกใช้ซ้ำ) · abort=True = สั่ง server หยุด session ด้วย · คืนข้อความผล ("" = ไม่มีอะไรต้องทำ)"""
    notes = []
    cp, cs = j.get("child_pid") or 0, j.get("child_pid_start") or 0
    if cp and cs and cp != os.getpid() and pid_alive(cp, cs):
        kill_tree(cp)
        notes.append(f"ฆ่า opencode ลูกที่ค้าง (pid {cp}) แล้ว")
    if abort and (notes or j.get("session")) and str(j.get("attach", LIVE_URL)).startswith("http"):
        n = abort_session(j)
        if n:
            notes.append(n)
    return " · ".join(notes)


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
    orphan = st == "dead" and j.get("status") in ("queued", "running")  # process หลักตายแล้วแต่สถานะค้าง — ยังมีลูกรอดอยู่ได้ → ยกเลิกเพื่อเก็บกวาด
    if st not in ("queued", "running") and not orphan:
        return False, f"job {j['id']} ไม่ได้ทำงานอยู่ (สถานะ {st})"
    note = abort_session(j) if st == "running" or (orphan and j.get("status") == "running") else ""
    if not orphan:
        kill_tree(j["pid"])
    # ลูกถูกฆ่าไปพร้อม /T แล้ว · ฆ่าซ้ำเฉพาะเมื่อยังเป็น process เดิม (pid ของรอบก่อนที่จบไปอาจถูกนำไปใช้ซ้ำโดยโปรแกรมอื่น)
    reaped = reap_orphan(j)
    if reaped and orphan:
        note = (note + " · " if note else "") + reaped
    j.update(status="cancelled", finished=now())
    if j.get("kind") == "doc" and isinstance(j.get("doc"), dict) and j["doc"].get("phase") in ("write", "check"):
        note = (note + " · " if note else "") + doc_cancelled(j)  # ช่างเอกสารถูกฆ่ากลางทาง → ไฟล์ที่แก้ค้างต้องถูกบันทึกไว้ให้ทิ้งได้
    save_job(j)
    release(j)
    notify_job(j, "CANCELLED", max(0.0, (_ts(j["finished"]) - _ts(j["started"])) / 60) if j.get("started") else 0.0)  # Claude ที่สั่งงานจะได้รู้ว่าผู้ใช้ยกเลิก ไม่ใช่งานพัง
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
    if a.key not in ("max_parallel", "schedule", "starve_min", "dead_clear_hours", "open_session"):
        print(f"ไม่รู้จัก '{a.key}' — ใช้ได้: max_parallel, schedule (auto|fifo), starve_min, dead_clear_hours, open_session")
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
              + ("ตรวจไฟล์ไม่ได้" if over is None else ("ไฟล์ซ้อน: " + ", ".join(over) if over else "ไม่มีไฟล์ซ้อน"))
              + (f" · แผนห้ามรันคู่: {it['block']}" if it.get("block") else ""))
    if rep["any_overlap"] and not a.force:
        print("หยุด: ไฟล์ซ้อน/แผนห้ามรันคู่กับงานที่กำลังทำ — ใส่ --force ถ้ายืนยันจะรันคู่ขนาน")
        return 1
    ok, msg = request_run_now(j)
    print(msg)
    return 0 if ok else 1


def accounts() -> tuple[str, list[list[str]]]:
    d = read_json(HOME / "accounts.json") or read_json(APP_DIR / "accounts.json") or read_json(RES / "accounts.json")  # ของเครื่องนี้ (flashq models สร้างให้) มาก่อนค่าตั้งต้นใน repo
    return d.get("agent", "flash-worker"), d.get("accounts", [])


def write_machine_accounts(models: list[str]) -> str:
    """สร้าง ~/.flashq/accounts.json ของเครื่องนี้: โมเดลที่ชื่อท้ายตรงกับของผู้ทำ (ผู้ทำเองก่อน · ที่ accounts.json เดิมรู้จักตามมา) · คืนข้อความสรุป ("" = ทำไม่ได้)"""
    worker = agent_model("flash-worker")
    if not worker or (models and worker not in models):
        return ""
    tail = worker.rsplit("/", 1)[-1]
    order = [worker] + [m for _, m in accounts()[1]]
    cand = sorted((m for m in models if m.rsplit("/", 1)[-1] == tail), key=lambda m: order.index(m) if m in order else len(order))
    rows, seen = [], set()
    for m in cand:
        short = m.partition("/")[0]
        n = 2
        while short in seen:
            short, n = f"{m.partition('/')[0]}{n}", n + 1
        seen.add(short)
        rows.append([short, m])
    if not rows:
        return ""
    HOME.mkdir(parents=True, exist_ok=True)
    write_json(HOME / "accounts.json", {"agent": "flash-worker", "_note": "สร้างโดย flashq models — ลำดับสลับบัญชีของเครื่องนี้ (ลบไฟล์นี้ = กลับไปใช้ accounts.json ใน repo)", "accounts": rows})
    return f"{len(rows)} รายการ: " + ", ".join(s for s, _ in rows)


ACC_SHORT_RE = re.compile(r"[\w.\-]{1,16}")
_UI_MODELS_CACHE: dict = {}


def accounts_source() -> str:
    """รายการบัญชีมาจากไหน: machine = ~/.flashq/accounts.json (เครื่องนี้ · แก้ได้จากหน้าเว็บ/flashq models) · repo = ค่าตั้งต้นใน repo"""
    return "machine" if read_json(HOME / "accounts.json") else "repo"


def ui_models(refresh: bool = False) -> tuple[list[str], str]:
    """machine_models() แบบแคช 60 วินาที (เรียก `opencode models` ช้า) · หน้าเว็บใช้เลือกโมเดลของบัญชี/บทบาท"""
    hit = _UI_MODELS_CACHE.get("v")
    if refresh or not hit or time.time() - hit[0] > 60:
        hit = _UI_MODELS_CACHE["v"] = (time.time(), machine_models())
    return hit[1]


def declared_providers() -> set[str]:
    """provider ที่ตั้งไว้ใน opencode.json (provider.<ชื่อ>) — ที่เหลือใน `opencode models` คือที่มากับ opencode/ล็อกอินไว้"""
    pv = read_json(OC_CONFIG).get("provider")
    return set(pv) if isinstance(pv, dict) else set()


def provider_rows(models: list[str]) -> list[dict]:
    """ผู้ให้บริการทั้งหมดที่ใช้ได้บนเครื่องนี้ (ชื่อต้นของ provider/model + ที่ตั้งใน opencode.json แม้ยังไม่ระบุรุ่น) เรียงตั้งไว้ใน opencode.json ก่อน"""
    count: dict[str, int] = {}
    for m in models:
        count[m.partition("/")[0]] = count.get(m.partition("/")[0], 0) + 1
    decl = declared_providers()
    return sorted(({"id": p, "count": count.get(p, 0), "declared": p in decl} for p in set(count) | decl),
                  key=lambda r: (not r["declared"], r["id"].lower()))


def model_usable(model: str) -> bool:
    """โมเดลนี้ opencode ใช้ได้ไหม: ประกาศใน opencode.json หรืออยู่ใน `opencode models` (อันหลังเรียก opencode จึงเช็กเมื่อแบบแรกไม่ผ่านเท่านั้น)"""
    pv, _, name = model.partition("/")
    if name in read_json(OC_CONFIG).get("provider", {}).get(pv, {}).get("models", {}):
        return True
    return model in machine_models()[0]


def edit_accounts(action: str, body: dict) -> tuple[bool, str]:
    """แก้รายการบัญชีสลับโมเดล flash-worker ที่ ~/.flashq/accounts.json ของเครื่องนี้ (ไม่แตะ accounts.json ใน repo)
    action: add (short?, model) · update (short, new_short?, model?) · remove (short) · move (short, dir=up|down) · reset (ลบไฟล์ของเครื่อง → กลับใช้ของ repo)
    โมเดลต้องเป็น provider/ชื่อ และต้องมีในเครื่องนี้ (รายการเดียวกับ flashq models) เมื่ออ่านรายชื่อได้ · คืน (สำเร็จ?, ข้อความ)"""
    agent, accs = accounts()
    rows = [[s, m] for s, m in accs]
    if action == "reset":
        if accounts_source() != "machine":
            return False, "ใช้ค่าตั้งต้นของ repo อยู่แล้ว"
        (HOME / "accounts.json").unlink(missing_ok=True)
        return True, "ลบรายการของเครื่องนี้แล้ว — กลับไปใช้ accounts.json ใน repo"
    short = str(body.get("short") or "").strip()
    model = str(body.get("model") or "").strip()
    models = ui_models()[0] if action in ("add", "update") and model else []

    def bad_model() -> str:
        if not re.fullmatch(r"[\w.\-]+/\S+", model):
            return f"โมเดลต้องเป็นรูป provider/ชื่อ — ได้ '{model}'"
        if models and model not in models:
            return f"เครื่องนี้ไม่มีโมเดล {model} (ดูรายการที่เลือกได้ในช่องโมเดล)"
        if any(m == model and s != short for s, m in rows):
            return f"{model} อยู่ในรายการแล้ว"
        return ""

    idx = next((i for i, (s, _) in enumerate(rows) if s == short), -1)
    if action == "add":
        if not model:
            return False, "ต้องระบุโมเดล"
        if err := bad_model():
            return False, err
        if not short:
            base = model.partition("/")[0]
            short, n = base, 2
            while any(s == short for s, _ in rows):
                short, n = f"{base}{n}", n + 1
        if not ACC_SHORT_RE.fullmatch(short):
            return False, "ชื่อย่อใช้ตัวอักษร ตัวเลข . _ - ได้ไม่เกิน 16 ตัว"
        if idx >= 0:
            return False, f"ชื่อย่อ '{short}' ซ้ำ"
        rows.append([short, model])
        msg = f"เพิ่ม {short} → {model}"
    elif idx < 0:
        return False, f"ไม่พบบัญชี '{short}'"
    elif action == "update":
        new_short = str(body.get("new_short") or short).strip()
        if not ACC_SHORT_RE.fullmatch(new_short):
            return False, "ชื่อย่อใช้ตัวอักษร ตัวเลข . _ - ได้ไม่เกิน 16 ตัว"
        if new_short != short and any(s == new_short for s, _ in rows):
            return False, f"ชื่อย่อ '{new_short}' ซ้ำ"
        if model:
            if err := bad_model():
                return False, err
        rows[idx] = [new_short, model or rows[idx][1]]
        msg = f"แก้ {short} → {rows[idx][0]}: {rows[idx][1]}"
    elif action == "remove":
        if len(rows) <= 1:
            return False, "ลบตัวสุดท้ายไม่ได้ — ต้องเหลืออย่างน้อย 1 บัญชี (ให้สลับบัญชีได้)"
        gone = rows.pop(idx)
        msg = f"ลบ {gone[0]} ({gone[1]})"
    elif action == "move":
        j = idx + (-1 if body.get("dir") == "up" else 1)
        if not 0 <= j < len(rows):
            return False, "ขยับต่อไม่ได้แล้ว"
        rows[idx], rows[j] = rows[j], rows[idx]
        msg = f"ย้าย {short} {'ขึ้น' if j < idx else 'ลง'} (ลำดับ = ลำดับสลับตอนโควตาหมด)"
    else:
        return False, f"ไม่รู้จัก action '{action}'"
    HOME.mkdir(parents=True, exist_ok=True)
    write_json(HOME / "accounts.json", {"agent": agent, "_note": "ลำดับสลับบัญชีของเครื่องนี้ (แก้จากหน้าเว็บ/flashq models) — ลบไฟล์นี้ = กลับไปใช้ accounts.json ใน repo", "accounts": rows})
    return True, msg


def role_rows() -> list[dict]:
    """โมเดลที่แต่ละบทบาท (ผู้ทำ/ผู้ตรวจ/…) ใช้อยู่ — เหมือนตารางของ flashq models"""
    return [{"key": k, "agent": ag, "label": lb, "model": agent_model(ag)} for k, ag, lb in MODEL_ROLES]


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
    if name not in cfg.get("provider", {}).get(provider, {}).get("models", {}) and not model_usable(target):
        print(f"FAIL: {target} ไม่มีใน provider ของ {OC_CONFIG} และไม่อยู่ใน opencode models")
        return ""
    shutil.copy2(OC_CONFIG, OC_CONFIG.with_name(OC_CONFIG.name + ".bak-flash-switch"))
    cfg.setdefault("agent", {}).setdefault(agent, {})["model"] = target
    tmp = OC_CONFIG.with_name(OC_CONFIG.name + f".{os.getpid()}.tmp")  # เขียนแล้วสลับไฟล์ — opencode ที่อ่านพร้อมกันไม่เจอไฟล์ครึ่ง ๆ
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replace_file(tmp, OC_CONFIG)
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
    extra: list[str] | None = None  # `opencode models` เรียกครั้งเดียว เฉพาะเมื่อมีรายการที่ไม่ได้ประกาศใน opencode.json
    for short, model in accs:
        provider, _, name = model.partition("/")
        declared = name in cfg.get("provider", {}).get(provider, {}).get("models", {})
        if not declared and extra is None:
            extra = machine_models()[0]
        ok = "" if declared or model in (extra or []) else "  (ไม่มีใน provider!)"
        print(f"{'*' if model == current else ' '} {short:7} {model}{ok}")
    print(f"ปัจจุบัน: {current or '(ยังไม่ตั้ง)'} — ดูสถานะอย่างเดียว ไม่ได้เปลี่ยน")
    return 0


MODEL_ROLES = [("worker", "flash-worker", "ผู้ทำ (แก้โค้ดตามแผน)"),
               ("verifier", "flash-verifier", "ผู้ตรวจ (อ่านอย่างเดียว)"),
               ("investigator", "flash-investigator", "ผู้สืบ (ไล่หาต้นตอ)"),
               ("tester", "flash-tester", "นักทดสอบ (อธิบายเทสต์ที่ล้ม)"),
               ("writer", "flash-writer", "ช่างเอกสาร")]


def machine_models() -> tuple[list[str], str]:
    """โมเดล provider/model ที่เครื่องนี้มี = `opencode models` + ที่ประกาศใน opencode.json (provider.<p>.models) · คืน (รายการเรียงชื่อ, หมายเหตุเมื่ออ่านจาก opencode ไม่ได้)"""
    found, note = set(), ""
    cmd = opencode_cmd()
    if cmd:
        r = run_timeout(cmd + ["models"], timeout=90)
        if r.returncode == 0:
            found.update(l.strip() for l in r.stdout.splitlines() if re.fullmatch(r"[\w.\-]+/\S+", l.strip()))
        else:
            note = f"`opencode models` ล้มเหลว (exit {r.returncode})"
    else:
        note = "ไม่พบ opencode ใน PATH"
    providers = read_json(OC_CONFIG).get("provider")
    for pv, pd in (providers.items() if isinstance(providers, dict) else []):
        for name in ((pd or {}).get("models") or {}):
            found.add(f"{pv}/{name}")
    return sorted(found), note


def json_agent_model(agent: str) -> str:
    try:
        m = read_json(OC_CONFIG)["agent"][agent]["model"]
    except (KeyError, TypeError):
        return ""
    return m if isinstance(m, str) else ""


def recommended_tail() -> str:
    """ชื่อโมเดลที่แนะนำ (ส่วนท้ายหลัง provider) = รายการแรกของ accounts.json"""
    accs = accounts()[1]
    return accs[0][1].rsplit("/", 1)[-1] if accs else "deepseek-v4.1-flash"


def recommend_model(models: list[str], tail: str) -> str:
    """โมเดลที่ชื่อท้ายตรง tail — provider ที่อยู่ใน accounts.json มาก่อน"""
    order = [m for _, m in accounts()[1]]
    cand = sorted((m for m in models if m.rsplit("/", 1)[-1] == tail), key=lambda m: order.index(m) if m in order else len(order))
    return cand[0] if cand else ""


def with_header_model(text: str, model: str) -> str:
    """แทนบรรทัด model: ในหัวไฟล์ agent (front matter) · ไม่มีบรรทัดนั้น/ไม่มีโมเดล = คืนเดิม"""
    m = re.match(r"(---\s*\n)(.*?)(\n---)", text, re.S)
    if not model or not m or not re.search(r"^model:", m.group(2), re.M):
        return text
    head = re.sub(r"^model:.*$", lambda _: f"model: {model}", m.group(2), count=1, flags=re.M)
    return m.group(1) + head + text[m.end(2):]


def set_agent_model(agent: str, model: str) -> bool:
    """ตั้ง agent.<ชื่อ>.model ใน opencode.json (สำรองครั้งแรก .bak-flash-models · เขียนแล้วสลับไฟล์) + หัวไฟล์ agent ที่ flashq ติดตั้ง"""
    cfg = read_json(OC_CONFIG)
    if OC_CONFIG.exists() and not cfg:
        print(f"FAIL: อ่าน {OC_CONFIG} เป็น JSON ไม่ได้ — ไม่เขียนทับ")
        return False
    OC_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    bak = OC_CONFIG.with_name(OC_CONFIG.name + ".bak-flash-models")
    if OC_CONFIG.exists() and not bak.exists():
        shutil.copy2(OC_CONFIG, bak)
    agents = cfg.setdefault("agent", {})
    if not isinstance(agents.get(agent), dict):
        agents[agent] = {}
    agents[agent]["model"] = model
    tmp = OC_CONFIG.with_name(OC_CONFIG.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    replace_file(tmp, OC_CONFIG)
    md = OC_CONFIG.parent / "agent" / f"{agent}.md"
    try:
        old = md.read_text(encoding="utf-8")
        new = with_header_model(old, model) if "flashq:managed" in old else old
        if new != old:
            md.write_text(new, encoding="utf-8")
    except OSError:
        pass
    return True


def print_model_list(models: list[str], shown: list[str], tail: str, used: dict) -> None:
    """รายการโมเดลจัดกลุ่มตาม provider · เลขลำดับอ้างอิงรายการเต็มเสมอ (กรองแล้วเลขไม่เปลี่ยน)"""
    idx = {m: i for i, m in enumerate(models, 1)}
    last = None
    for m in shown:
        pv, _, name = m.partition("/")
        if pv != last:
            print(f"  [{pv}] {sum(1 for x in models if x.startswith(pv + '/'))} รุ่น")
            last = pv
        tags = ("  (แนะนำ)" if m.rsplit("/", 1)[-1] == tail else "") + (f"  ← ใช้อยู่: {', '.join(used[m])}" if m in used else "")
        print(f"   {idx[m]:>3}. {name}{tags}")


def pick_model(models: list[str], tail: str, used: dict, label: str, default: str = "") -> str:
    """เลือกโมเดล: เลขที่ · ชื่อเต็ม · พิมพ์ส่วนของชื่อเพื่อกรอง · * ทั้งหมด · Enter = ค่าในวงเล็บ · 0 = ข้าม (คืน "")"""
    while True:
        try:
            ans = input(f"{label}{f' [Enter={default}]' if default else ''} — เลขที่/ชื่อ/คำกรอง · * ทั้งหมด · 0 ข้าม: ").strip()
        except EOFError:
            return ""
        if not ans:
            if default:
                return default
            continue
        if ans in ("0", "q"):
            return ""
        if ans == "*":
            print_model_list(models, models, tail, used)
        elif ans.isdigit():
            if 1 <= int(ans) <= len(models):
                return models[int(ans) - 1]
            print(f"เลขต้องอยู่ระหว่าง 1–{len(models)}")
        elif ans in models:
            return ans
        else:
            sub = [m for m in models if ans.lower() in m.lower()]
            if sub:
                print_model_list(models, sub, tail, used)
            else:
                print(f"ไม่พบโมเดลที่มี '{ans}'")


def models_problems(models: list[str]) -> list[str]:
    """agent ที่ยังไม่ตั้งโมเดล หรือตั้งไว้แต่เครื่องนี้ไม่มี"""
    return [ag for _, ag, _ in MODEL_ROLES if not agent_model(ag) or (models and agent_model(ag) not in models)]


def print_role_table(models: list[str]) -> None:
    for key, ag, label in MODEL_ROLES:
        m = agent_model(ag)
        state = "ยังไม่ตั้ง" if not m else ("" if not models else ("ใช้ได้" if m in models else "ไม่มีในเครื่องนี้!"))
        print(f"  {key:12} {ag:19} {m or '-':48} {state}")


def ask_model_changes(models: list[str], tail: str, rec: str, used: dict) -> dict:
    """ถามว่าจะใช้โมเดลอะไรแบบไหน → {agent: โมเดล} (ว่าง = ไม่เปลี่ยน)"""
    bad = models_problems(models)
    default = ("1" if rec else "3") if bad else "0"
    star = lambda k: "  (แนะนำ)" if k == default else ""  # noqa: E731
    print("\nจะให้ใช้โมเดลอะไรแบบไหน?")
    if rec:
        print(f"  1) ใช้ {rec} ทุกบทบาท{star('1')}")
    print(f"  2) เลือกโมเดลเดียวใช้ทุกบทบาท{star('2')}")
    print(f"  3) เลือกแยกรายบทบาท (ผู้ทำ / ผู้ตรวจ / ผู้สืบ / นักทดสอบ / ช่างเอกสาร){star('3')}")
    print(f"  0) ไม่เปลี่ยน{star('0')}")
    try:
        ans = input(f"เลือก [Enter={default}]: ").strip() or default
    except EOFError:
        return {}
    if ans == "1" and rec:
        return {ag: rec for _, ag, _ in MODEL_ROLES}
    if ans == "2":
        m = pick_model(models, tail, used, "โมเดลสำหรับทุกบทบาท")
        return {ag: m for _, ag, _ in MODEL_ROLES} if m else {}
    if ans == "3":
        out = {}
        for key, ag, label in MODEL_ROLES:
            cur = agent_model(ag)
            m = pick_model(models, tail, used, f"{key} {label}", cur if cur in models else rec)
            if m:
                out[ag] = m
        return out
    return {}


def run_models(models: list[str], note: str, *, list_only=False, auto=False, sets=None, all_model="", interactive=False) -> int:
    """แกนของ `flashq models` (install เรียกซ้ำได้) · 0 = เรียบร้อย · 1 = ยังมีบทบาทที่ใช้ไม่ได้ · 2 = ใช้ผิด · 3 = เขียนไม่ได้/โมเดลไม่มีในเครื่อง"""
    tail = recommended_tail()
    rec = recommend_model(models, tail)
    used: dict = {}
    for _, ag, _ in MODEL_ROLES:
        if agent_model(ag):
            used.setdefault(agent_model(ag), []).append(ag)
    print(f"โมเดลที่เครื่องนี้มี: {len(models)} รุ่น" + (f"  (หมายเหตุ: {note})" if note else ""))
    if models and (list_only or interactive):
        print_model_list(models, models, tail, used)
    print("\nโมเดลที่แต่ละบทบาทใช้อยู่:")
    print_role_table(models)
    by_key = {k: ag for k, ag, _ in MODEL_ROLES}
    changes: dict = {}
    if all_model:
        changes.update({ag: all_model for ag in by_key.values()})
    for item in sets or []:
        role, _, m = item.partition("=")
        ag = by_key.get(role.strip()) or (role.strip() if role.strip() in by_key.values() else "")
        if not ag or not m.strip():
            print(f"FAIL: --set ต้องเป็น <บทบาท>=<provider/model> (บทบาท: {', '.join(by_key)}) — ได้ '{item}'")
            return 2
        changes[ag] = m.strip()
    unresolved: list[str] = []
    if auto:
        for _, ag, _ in MODEL_ROLES:
            cur = agent_model(ag)
            if ag in changes or (cur and (cur in models or not models)):
                continue
            if rec:
                changes[ag] = rec
            else:
                unresolved.append(ag)
    if not changes and not unresolved and not list_only and interactive:
        changes = ask_model_changes(models, tail, rec, used)
    if models:
        missing = sorted({m for m in changes.values() if m not in models})
        if missing:
            print("FAIL: ไม่มีในเครื่องนี้ (ดูรายการด้วย flashq models --list): " + ", ".join(missing))
            return 3
    elif changes:
        print(f"เตือน: อ่านรายชื่อโมเดลไม่ได้ ({note}) → ตรวจชื่อที่ตั้งไม่ได้")
    rc = 0
    for ag, m in changes.items():
        old = agent_model(ag)
        if old == m and json_agent_model(ag) == m:
            print(f"เหมือนเดิม  {ag}: {m}")
        elif set_agent_model(ag, m):
            print(f"{ag}: {old or '(ยังไม่ตั้ง)'} → {m}")
        else:
            rc = 3
    if changes:
        print("\nหลังตั้งค่า:")
        print_role_table(models)
        print("flashq run ใช้โมเดลใหม่ทันที · opencode desktop ต้องรีโหลด/เริ่ม session ใหม่")
    if unresolved:
        print(f"หา '{tail}' ในเครื่องนี้ไม่เจอ → ตั้งให้ {', '.join(unresolved)} ไม่ได้ — เลือกเองด้วย flashq models หรือ --set <บทบาท>=<provider/model>")
    acc_missing = [m for _, m in accounts()[1] if models and m not in models]
    if acc_missing and not list_only and (changes or auto or interactive):
        made = write_machine_accounts(models)  # ลำดับสลับบัญชี (โควตาหมด) ที่เครื่องนี้ไม่มีรายการตามนั้น → สร้างของเครื่องนี้แทน
        if made:
            print(f"สลับบัญชีอัตโนมัติ: accounts.json เดิมมี {len(acc_missing)} รายการที่เครื่องนี้ไม่มี → สร้าง {HOME / 'accounts.json'} ใหม่ {made}")
        else:
            print(f"หมายเหตุ: accounts.json (สลับบัญชีอัตโนมัติ) มี {len(acc_missing)} รายการที่เครื่องนี้ไม่มี: {', '.join(acc_missing)} — ตั้งโมเดลผู้ทำให้ใช้ได้ก่อน แล้วรัน flashq models อีกครั้ง")
    elif acc_missing:
        print(f"หมายเหตุ: accounts.json (สลับบัญชีอัตโนมัติ) มี {len(acc_missing)} รายการที่เครื่องนี้ไม่มี: {', '.join(acc_missing)} — รัน flashq models เพื่อสร้างของเครื่องนี้")
    if rc == 0 and not changes and not list_only and models_problems(models):
        print("ยังมีบทบาทที่ใช้ไม่ได้ → flashq models (เลือกเอง) · flashq models --auto (ใช้ตัวแนะนำ) · flashq models --set worker=<provider/model>")
        return 1
    return rc if not unresolved else 1


def cmd_models(a) -> int:
    """แสดงโมเดลทั้งหมดที่เครื่องนี้มี แล้วให้เลือกว่าบทบาทไหนใช้โมเดลอะไร (ไม่มี TTY = แสดงสถานะ/ใช้ flag)"""
    models, note = machine_models()
    given = bool(a.auto or a.set or a.all or a.list)
    return run_models(models, note, list_only=a.list, auto=a.auto, sets=a.set, all_model=a.all or "",
                      interactive=not given and sys.stdin.isatty())


def ensure_models(mode: str) -> None:
    """ท้าย install: ตรวจว่าทุกบทบาทมีโมเดลที่ใช้ได้บนเครื่องนี้ · ขาด → ask ถามเลือก (ต้องมี TTY) · auto ใช้ตัวแนะนำ · ไม่มี TTY บอกวิธีแก้"""
    models, note = machine_models()
    if not models:
        print(f"หมายเหตุ   อ่านรายชื่อโมเดลไม่ได้ ({note}) → ตรวจโมเดลไม่ได้ · พร้อมแล้วรัน flashq models")
        return
    bad = models_problems(models)
    if not bad:
        print("โมเดล       ทุกบทบาทใช้ได้บนเครื่องนี้ (flashq models = ดู/เปลี่ยน)")
    elif mode == "auto":
        run_models(models, note, auto=True)
    elif mode == "ask" and sys.stdin.isatty():
        print(f"\nพบ {len(bad)} บทบาทที่ยังไม่มีโมเดลที่ใช้ได้บนเครื่องนี้ ({', '.join(bad)}) → เลือกโมเดลเลย (ข้ามได้ แล้วรัน flashq models ทีหลัง)")
        run_models(models, note, interactive=True)
    else:
        print(f"หมายเหตุ   {len(bad)} บทบาทยังไม่มีโมเดลที่ใช้ได้บนเครื่องนี้ ({', '.join(bad)}) → flashq models (เลือกเอง) หรือ flashq models --auto")


def register_hook(settings: Path, event: str, matcher: str, command: str, key: str, timeout: int = 10) -> str:
    """ลงทะเบียน hook ใน settings.json ของ Claude Code แบบทำซ้ำได้ (หา hook ที่ command มี key · มีแล้วเหมือนเดิม = ไม่แตะ · ต่างกัน = อัปเดต)"""
    data = read_json(settings) if settings.exists() else {}
    if settings.exists() and not data:  # ไฟล์มีแต่อ่านเป็น JSON ไม่ได้ → ห้ามเขียนทับ
        return f"ข้าม       {settings} อ่าน JSON ไม่ได้ — ลงทะเบียน hook เอง: {event} matcher {matcher!r} → {command}"
    groups = data.setdefault("hooks", {}).setdefault(event, [])
    for grp in groups:
        for h in grp.get("hooks", []):
            if key in h.get("command", ""):
                if h.get("command") == command and grp.get("matcher") == matcher:
                    return f"เหมือนเดิม  hook {event}:{matcher} → {command}"
                h["command"], h["timeout"], grp["matcher"] = command, timeout, matcher
                write_json(settings, data)
                return f"อัปเดต     hook {event}:{matcher} → {command}"
    groups.append({"matcher": matcher, "hooks": [{"type": "command", "command": command, "timeout": timeout}]})
    write_json(settings, data)
    return f"ลงทะเบียน  hook {event}:{matcher} → {command} ใน {settings}"


def fill_template(text: str, py: bool = False) -> str:
    """แทนตัวแปรในแม่แบบที่ติดตั้ง: {{FLASHQ}} = โฟลเดอร์ต้นฉบับ · {{FLASHQ_RUN}} = คำสั่งรัน flashq · {{FLASHQ_EXE}} = path exe (ว่างถ้าไม่ใช่ exe)"""
    run = '"' + (APP_DIR / CLI_EXE).as_posix() + '"' if FROZEN else f"python {REPO.as_posix()}/flashq.py"
    exe = (APP_DIR / CLI_EXE).as_posix() if FROZEN else ""
    if py:  # อยู่ในสตริง "..." ของ hook .py → escape เครื่องหมายคำพูดของ path
        run = run.replace('"', '\\"')
    return text.replace("{{FLASHQ_RUN}}", run).replace("{{FLASHQ_EXE}}", exe).replace("{{FLASHQ}}", str(REPO).replace("\\", "/"))


OC_COMMANDER_NOTE = """
> **ผู้สั่งคือ agent หลักของ opencode (โมเดลไหนก็ได้ เช่น GLM)** — ไฟล์นี้สร้างจากต้นฉบับของ Claude Code ตอน `flashq install` (แก้ที่ `claude/commands/` ไม่ใช่ไฟล์นี้) · อ่านคำในไฟล์ตามนี้:
> - `AskUserQuestion` → question tool · `Agent` / subagent → task tool (เลือก `model:` ไม่ได้ ใช้ agent ที่มี) · `Skill` → skill tool
> - `run_in_background` → ใส่ `--detach` ท้ายคำสั่ง `flashq run …` (ส่งเข้าคิวแล้วคืนทันที) แล้ว**หยุดรอ** ห้าม sleep/poll · จบแล้วผู้ใช้สั่งต่อ หรือรัน `flashq inbox` ดูผลงานที่จบ
> - hook/ยามของ Claude (`run_guard` `inbox_notify` `delegate_guard`) ไม่มีใน opencode → ทำตามกติกาในไฟล์ด้วยตัวเอง · ไม่มี subagent `flash-checker` → ตรวจเองตามขั้นของคำสั่ง
> - `run --detach` ไม่เปิดหน้าต่าง session ของพนักงานให้เองอยู่แล้ว · อยากเปิด/ปิดเอง → `flashq config open_session on|off|auto` (ทั้งเครื่อง) หรือ `"open_session": true|false` ใน `.flash.json` (ต่อโปรเจกต์)
"""


def to_opencode_command(text: str) -> str:
    """แปลงคำสั่งต้นฉบับของ Claude Code เป็นคำสั่ง opencode (ผู้สั่งเป็นโมเดลอะไรก็ได้) — ตัด effort · ใส่ตารางแปลเครื่องมือหลังบรรทัด flashq:managed"""
    text = re.sub(r"^effort:.*\n", "", text, count=1, flags=re.M).replace("(Claude Code · ทุกโปรเจกต์)", "(opencode · ทุกโปรเจกต์)")
    m = re.search(r"^<!-- flashq:managed.*-->\n", text, re.M)
    end = text.find("\n---\n", 3) if text.startswith("---") else -1
    at = m.end() if m else (end + 5 if end >= 0 else 0)
    return text[:at] + OC_COMMANDER_NOTE + text[at:]


def install_items(claude_home: Path):
    """(ปลายทาง, เนื้อหาที่ต้องติดตั้ง) ของทุกไฟล์ที่ install คัดลอก — install กับ install --check ใช้ชุดเดียวกัน"""
    pairs = [(REPO / "opencode" / "command", OC_CONFIG.parent / "command", "*.md"),
             (REPO / "claude" / "commands", OC_CONFIG.parent / "command", "*.md"),
             (REPO / "opencode" / "agent", OC_CONFIG.parent / "agent", "*.md"),
             (REPO / "claude" / "commands", claude_home / "commands", "*.md"),
             (REPO / "claude" / "agents", claude_home / "agents", "*.md"),
             (REPO / "hooks", claude_home / "hooks", "*.py")]
    for src_dir, dst_dir, pat in pairs:
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.glob(pat)):
            text = fill_template(src.read_text(encoding="utf-8"), src.suffix == ".py")
            if src_dir == REPO / "claude" / "commands" and dst_dir == OC_CONFIG.parent / "command":  # ผู้สั่งฝั่ง opencode สร้างจากต้นฉบับเดียวกับ Claude
                text = to_opencode_command(text)
            if src_dir == REPO / "opencode" / "agent":  # โมเดลที่ผู้ใช้เลือกไว้ (flashq models) ไม่ถูกต้นฉบับทับกลับเป็นค่าตั้งต้น
                text = with_header_model(text, json_agent_model(src.stem))
            yield dst_dir / src.name, text


def changelog_news(limit: int = 10) -> list[str]:
    """หัวข้อตัวหนา `- **หัวข้อ**` ของรายการใน CHANGELOG.md ใหม่สุดก่อน"""
    try:
        text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return []
    return [m.group(1).strip() for m in re.finditer(r"^- \*\*(.+?)\*\*", text, re.M)][:limit]


def record_install(claude_home: Path) -> None:
    """บันทึกรุ่นที่ติดตั้ง (hash เนื้อไฟล์ทั้งชุด) ลง installed.json — `at` เปลี่ยนเฉพาะเมื่อเนื้อไฟล์เปลี่ยนจริง · แล้วพิมพ์หัวข้อล่าสุด
    ให้คนที่เห็นผล "เหมือนเดิม" ทั้งชุดรู้ว่าของใหม่คืออะไร (มีคนติดตั้งไปก่อนแล้ว ไม่ใช่ไม่มีของใหม่)"""
    h = hashlib.sha1()
    for dst, text in install_items(claude_home):
        h.update(dst.name.encode("utf-8"))
        h.update(text.encode("utf-8"))
    rev, news = h.hexdigest()[:12], changelog_news()
    cur = read_json(INSTALLED) if INSTALLED.exists() else {}
    if cur.get("rev") != rev:
        cur = {"rev": rev, "at": time.time(), "news": news}
    elif cur.get("news") != news:
        cur["news"] = news
    else:
        cur = None
    if cur is not None:
        HOME.mkdir(parents=True, exist_ok=True)
        write_json(INSTALLED, cur)
    cur = cur or read_json(INSTALLED)
    when = datetime.fromtimestamp(float(cur.get("at") or 0)).strftime("%Y-%m-%d %H:%M")
    print(f"รุ่นที่ติดตั้ง {rev} (เนื้อไฟล์เปลี่ยนล่าสุด {when}) — ถ้าทุกไฟล์ขึ้น \"เหมือนเดิม\" แปลว่าติดตั้งไปก่อนแล้ว ไม่ได้แปลว่าไม่มีของใหม่ · หัวข้อล่าสุดใน CHANGELOG:")
    for t in news[:5]:
        print(f"  - {t[:110]}")


def check_installed(claude_home: Path) -> int:
    """install --check: เทียบไฟล์ที่ติดตั้งไว้กับต้นฉบับ (อ่านอย่างเดียว) · 0 = ตรงครบ · 1 = มีไฟล์ล้าหลัง/ยังไม่ได้ติดตั้ง
    · ไฟล์ของผู้ใช้เอง (ไม่มี flashq:managed) ไม่นับว่าล้าหลัง"""
    ok = 0
    stale: list[Path] = []
    missing: list[Path] = []
    foreign: list[Path] = []
    for dst, text in install_items(claude_home):
        if not dst.exists():
            missing.append(dst)
            continue
        old = dst.read_text(encoding="utf-8", errors="replace")
        if old == text:
            ok += 1
        elif "flashq:managed" not in old:
            foreign.append(dst)
        else:
            stale.append(dst)
    for label, items in (("ล้าหลัง", stale), ("ยังไม่ได้ติดตั้ง", missing), ("ข้าม (ไม่ได้มาจาก flashq)", foreign)):
        for p in items:
            print(f"{label}  {p}")
    if stale or missing:
        print(f"INSTALL=STALE  ตรง {ok} · ล้าหลัง {len(stale)} · ยังไม่ได้ติดตั้ง {len(missing)} → {run_cmd()} install (รันจาก checkout หลัก · ได้ผลใน session ใหม่)")
        return 1
    print(f"INSTALL=OK  ตรงต้นฉบับครบ {ok} ไฟล์" + (f" (ข้าม {len(foreign)} ไฟล์ของผู้ใช้เอง)" if foreign else ""))
    return 0


SETUP_FILE = HOME / "setup.json"  # วิซาร์ดตั้งค่าครั้งแรกในหน้าเว็บ: {"done": true, "at": เวลา} — ไม่มีไฟล์ = ยังไม่เคยทำจนจบ
SETUP_HOOK_KEYS = ("image_guard.py", "inbox_notify.py", "run_guard.py", "delegate_guard.py", "whatsnew.py")


def setup_status() -> dict:
    """สถานะสำหรับวิซาร์ดตั้งค่าครั้งแรก (อ่านอย่างเดียว): opencode · ไฟล์ที่ install ติดตั้ง · hook · โมเดลของบทบาท · เคยทำจนจบหรือยัง"""
    claude_home = Path(os.environ.get("FLASHQ_CLAUDE_HOME") or Path.home() / ".claude")
    ok = stale = missing = foreign = 0
    for dst, text in install_items(claude_home):
        if not dst.exists():
            missing += 1
            continue
        old = dst.read_text(encoding="utf-8", errors="replace")
        if old == text:
            ok += 1
        elif "flashq:managed" not in old:
            foreign += 1
        else:
            stale += 1
    st = claude_home / "settings.json"
    st_text = st.read_text(encoding="utf-8", errors="replace") if st.exists() else ""
    oc = opencode_cmd()
    models, note = ui_models() if oc else ([], "ไม่พบ opencode")
    bad = models_problems(models) if models else []
    py = bool(shutil.which("python") or shutil.which("python3")) or not FROZEN
    install = {"ok": missing == 0 and stale == 0, "same": ok, "stale": stale, "missing": missing, "foreign": foreign}
    done = bool(read_json(SETUP_FILE).get("done"))
    return {"done": done, "opencode": {"ok": bool(oc), "path": oc[-1] if oc else ""},
            "claude_home": {"path": str(claude_home), "exists": claude_home.is_dir()},
            "install": install, "hooks": {k: k in st_text for k in SETUP_HOOK_KEYS}, "python": py,
            "models": {"ok": bool(models) and not bad, "bad": bad, "count": len(models), "note": note},
            "needed": not (bool(oc) and install["ok"] and bool(models) and not bad)}


def setup_capture(fn, ns: argparse.Namespace) -> dict:
    """รัน cmd_* ที่พิมพ์ผลลง stdout แล้วเก็บข้อความกลับให้หน้าเว็บแสดง"""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(ns)
    return {"ok": rc == 0, "rc": rc, "output": buf.getvalue().strip()}


def cmd_install(a) -> int:
    """คัดลอก opencode/{command,agent}/*.md ไป ~/.config/opencode/ · claude/{commands,agents}/*.md + hooks/*.py ไป ~/.claude/
    (แทน {{FLASHQ}} ด้วย path repo นี้) · ไฟล์ที่ flashq ติดตั้งเองทับได้เลย (ต้นฉบับอยู่ใน git ของ flashq ไม่ต้องสำรอง)
    · ไฟล์ของผู้ใช้เอง (ไม่มี flashq:managed) = ข้าม เว้นแต่ --force (สำรอง .bak-flashq-<เวลา> ก่อนทับ) · --hooks = ลงทะเบียน image_guard ใน settings.json
    · --check = แค่เทียบว่าที่ติดตั้งไว้ล้าหลังต้นฉบับไหม ไม่เขียนอะไร"""
    claude_home = Path(os.environ.get("FLASHQ_CLAUDE_HOME") or Path.home() / ".claude")
    if getattr(a, "check", False):
        return check_installed(claude_home)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    rc = 0
    for dst, text in install_items(claude_home):
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            old = dst.read_text(encoding="utf-8")
            if old == text:
                print(f"เหมือนเดิม  {dst}")
                continue
            if "flashq:managed" not in old:
                if not a.force:
                    print(f"ข้าม       {dst} (มีไฟล์ที่ไม่ได้มาจาก flashq — ใช้ --force เพื่อสำรองแล้วทับ)")
                    rc = 1
                    continue
                shutil.copy2(dst, dst.with_name(dst.name + f".bak-flashq-{ts}"))
        dst.write_text(text, encoding="utf-8")
        print(f"ติดตั้ง     {dst}")
    guard = claude_home / "hooks" / "image_guard.py"
    want_hooks = getattr(a, "hooks", False)
    if want_hooks and FROZEN and not shutil.which("python"):  # hook เป็นสคริปต์ .py ที่ settings.json สั่ง `python <hook>.py` → ไม่มี Python = ลงทะเบียนแล้วรันไม่ได้
        print("ข้าม       --hooks: ไม่พบ python ใน PATH (hook ของ Claude Code เป็นสคริปต์ Python) — ติดตั้ง Python 3 แล้วรัน install --hooks ใหม่ · คำสั่ง /flash-* ใช้ได้ตามปกติ")
        want_hooks = False
    if want_hooks:
        if guard.exists():
            print(register_hook(claude_home / "settings.json", "PreToolUse", "Read", f'python "{guard.as_posix()}"', "image_guard.py"))
        else:
            print(f"ข้าม       ไม่พบ {guard} → ลงทะเบียน hook ไม่ได้")
            rc = 1
        inbox_hook = claude_home / "hooks" / "inbox_notify.py"
        if inbox_hook.exists():
            print(register_hook(claude_home / "settings.json", "UserPromptSubmit", "", f'python "{inbox_hook.as_posix()}"', "inbox_notify.py"))
        else:
            print(f"ข้าม       ไม่พบ {inbox_hook} → ลงทะเบียน hook ไม่ได้")
            rc = 1
        run_hook = claude_home / "hooks" / "run_guard.py"
        if run_hook.exists():
            print(register_hook(claude_home / "settings.json", "PreToolUse", "Bash|PowerShell", f'python "{run_hook.as_posix()}"', "run_guard.py"))
        else:
            print(f"ข้าม       ไม่พบ {run_hook} → ลงทะเบียน hook ไม่ได้")
            rc = 1
        deleg_hook = claude_home / "hooks" / "delegate_guard.py"
        if deleg_hook.exists():
            print(register_hook(claude_home / "settings.json", "UserPromptSubmit", "", f'python "{deleg_hook.as_posix()}" prompt', "delegate_guard.py"))
            print(register_hook(claude_home / "settings.json", "PreToolUse", "Read|Grep|Glob|Bash|PowerShell", f'python "{deleg_hook.as_posix()}" pretool', "delegate_guard.py"))
        else:
            print(f"ข้าม       ไม่พบ {deleg_hook} → ลงทะเบียน hook ไม่ได้")
            rc = 1
        news_hook = claude_home / "hooks" / "whatsnew.py"
        if news_hook.exists():
            print(register_hook(claude_home / "settings.json", "UserPromptSubmit", "", f'python "{news_hook.as_posix()}"', "whatsnew.py"))
        else:
            print(f"ข้าม       ไม่พบ {news_hook} → ลงทะเบียน hook ไม่ได้")
            rc = 1
    elif guard.exists():
        st = claude_home / "settings.json"
        if "image_guard.py" not in (st.read_text(encoding="utf-8", errors="replace") if st.exists() else ""):
            print("หมายเหตุ   ยังไม่ได้ลงทะเบียน image_guard (กันอ่านรูปใหญ่/อ่านรูปรัวใน session หลัก) → install --hooks")
        if "run_guard.py" not in (st.read_text(encoding="utf-8", errors="replace") if st.exists() else ""):
            print("หมายเหตุ   ยังไม่ได้ลงทะเบียน run_guard (กันสั่งงานผิดวิธีจนไม่มีใครเฝ้า: & · sleep · ไม่ใส่ run_in_background) → install --hooks")
        if "delegate_guard.py" not in (st.read_text(encoding="utf-8", errors="replace") if st.exists() else ""):
            print("หมายเหตุ   ยังไม่ได้ลงทะเบียน delegate_guard (กัน Claude แย่งไล่โค้ดเองเมื่อผู้ใช้สั่งส่งสืบให้ Flash) → install --hooks")
        if "whatsnew.py" not in (st.read_text(encoding="utf-8", errors="replace") if st.exists() else ""):
            print("หมายเหตุ   ยังไม่ได้ลงทะเบียน whatsnew (บอก session ที่เปิดค้างว่ามีของใหม่ — ไม่เสีย token ถ้าไม่มีอะไรเปลี่ยน) → install --hooks")
    record_install(claude_home)
    if getattr(a, "models", "ask") != "skip":
        ensure_models(getattr(a, "models", "ask"))
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
        tpl_dst.write_text(fill_template(tpl_src.read_text(encoding="utf-8")), encoding="utf-8")
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
        cmd_install(argparse.Namespace(force=False, hooks=False, models="skip"))
    elif need:
        print("ยังไม่ได้ติดตั้งคำสั่ง global: " + ", ".join(p.name for p in need))
        todo.append(f"{run_cmd()} install  (แล้วรีโหลด opencode desktop)")
    else:
        print("พบ         คำสั่ง /flash /flash-plan /flash-check + agent flash-worker (global)")
    if proj_own:
        print("หมายเหตุ    โปรเจกต์มี flash.md/flash-worker.md ของตัวเอง → opencode ใช้ของโปรเจกต์ก่อน")

    # 5) บัญชีโมเดล
    if not configured_model():
        todo.append(f"ตั้งโมเดลของ flash-worker: {run_cmd()} models  (เลือกจากรายการที่เครื่องนี้มี · หรือส่ง --model ตอน run)")

    # 6) --commit: commit เฉพาะไฟล์ที่ init แตะ (ไม่แตะไฟล์อื่นที่ค้างอยู่) · push เมื่ออยู่ branch หลักและมี remote
    if a.commit and is_git:
        mine = [p for p in (".flash.json", ".gitignore", (root / new["plan_dir"] / "FLASH_PLAN_TEMPLATE.md").relative_to(root).as_posix())
                if (root / p).exists()]
        dirty = _git(root, "status", "--porcelain", "--", *mine)
        if dirty:
            run_timeout(["git", "-C", str(root), "add", "--", *mine], 60)
            r = run_timeout(["git", "-C", str(root), "commit", "-q", "-m", "ตั้งค่า flashq สำหรับโปรเจกต์นี้ (.flash.json · .gitignore · แม่แบบแผน)",
                             "--", *mine], 120)
            print("commit     " + ("สำเร็จ" if r.returncode == 0 else f"ล้มเหลว: {(r.stderr or r.stdout).strip()}"))
            todo = [t for t in todo if not t.startswith("commit")]
        else:
            print("commit     ไม่มีอะไรต้อง commit")
        branch, remote = _git(root, "branch", "--show-current"), new.get("remote", "origin")
        if _git(root, "remote") and branch == new["main_branch"]:
            r = run_timeout(["git", "-C", str(root), "push", "-q", remote, f"HEAD:{new['main_branch']}"], PUSH_TIMEOUT_SEC,  # ห้ามถามรหัส + จำกัดเวลา: เครือข่ายค้าง/รอ credential จะไม่ทำให้ init ค้างตลอดไป
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            print("push       " + (f"{remote}/{new['main_branch']} สำเร็จ" if r.returncode == 0
                                     else f"ล้มเหลว: {(r.stderr or r.stdout).strip()}"))
            if r.returncode == 124:
                todo.append(f"push ไม่เสร็จใน {PUSH_TIMEOUT_SEC:g} วิ → ตรวจเครือข่าย/สิทธิ์ แล้ว `git push {remote} HEAD:{new['main_branch']}` เอง")
        elif _git(root, "remote"):
            todo.append(f"อยู่ branch '{branch}' ไม่ใช่ {new['main_branch']} → merge เข้า {new['main_branch']} แล้ว push เอง")

    print("\nพร้อมใช้ · ทดสอบการเชื่อมต่อ: " + f"{run_cmd()} run --message \"ตอบแค่คำว่า PONG\" --project \"{root}\"")
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


def _fresh_shell_watch(j: dict) -> dict | None:
    """ป้ายยามเฝ้า shell ล่าสุด · เก่ากว่า 180 วิ (ยามเฝ้าทุก 30 วิ) = ตัวคุมงานหยุดเฝ้าแล้ว → ไม่แสดง (กันป้ายค้าง)"""
    sw = j.get("shell_watch")
    age = _secs(sw.get("at", "")) if sw else None
    return sw if age is not None and age <= 180 else None


def _agent_act_row(a: dict | None) -> dict | None:
    """ความเคลื่อนไหวของ session + ผู้ช่วยย่อยที่ตัวคุมงานถามจากเซิร์ฟเวอร์ล่าสุด → อายุเป็นวินาที (ข้อมูลเก่าเกิน 5 นาที = ไม่ใช้)"""
    if not a or time.time() - a.get("at", 0) > 300:
        return None
    ago = lambda t: max(0, int(time.time() - t)) if t else None  # noqa: E731
    return {"checked_ago_sec": ago(a["at"]), "idle_sec": ago(a.get("updated")),
            "subs": [{"title": s.get("title", ""), "doing": s.get("doing", ""), "ago_sec": ago(s.get("updated"))} for s in a.get("subs") or []]}


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


def review_name_match(a: str, b: str) -> int:
    """ชื่อแผนของป้ายผู้ตรวจตรงกันไหม: 2 = ตรงทุกตัว (ไม่สนตัวพิมพ์/.md) · 1 = ชื่อสั้นเป็นท้ายของชื่อเต็มที่ขอบ "_"
    (เช่น VIEWFIX2 ↔ PLAN_MAPEDITOR_FLASH_VIEWFIX2) · 0 = ไม่ตรง — start กับ done เรียกคนละแบบก็ปิดป้ายได้"""
    def norm(s: str) -> str:
        s = (s or "").replace("\\", "/").split("/")[-1].strip().lower()
        return s[:-3] if s.endswith(".md") else s
    x, y = norm(a), norm(b)
    if not x or not y:
        return 0
    if x == y:
        return 2
    short, full = sorted((x, y), key=len)
    return 1 if full.endswith("_" + short) else 0


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
            if r.get("status") == "reviewing" and review_name_match(r.get("plan_name", ""), key) and r.get("project") == proj:
                (REVIEWS / f"{r['id']}.json").unlink(missing_ok=True)
        write_json(REVIEWS / f"{rid}.json", {"id": rid, "project": proj, "project_name": Path(proj).name, "plan_name": key,
                                              "tasks": a.tasks_or_result or "", "status": "reviewing", "started": now()})
        print(f"REVIEW=START id={rid}")
        return 0
    if a.action == "done":
        if a.tasks_or_result not in ("pass", "fail"):
            print("done ต้องตามด้วย pass หรือ fail", file=sys.stderr)
            return 1
        cand = [(review_name_match(r.get("plan_name", ""), key), r) for r in _review_rows() if r.get("status") == "reviewing"]
        cand = [(m, r) for m, r in cand if m]
        if a.project:  # ระบุโปรเจกต์มา = ปิดเฉพาะป้ายของโปรเจกต์นั้น
            proj = str(Path(a.project).resolve())
            cand = [(m, r) for m, r in cand if r.get("project") == proj]
        if not cand:
            print(f"ไม่พบป้ายที่กำลังตรวจของแผน {key} (ข้าม)", file=sys.stderr)
            return 0
        r = max(cand, key=lambda x: (x[0], x[1].get("started", "")))[1]  # ชื่อตรงทุกตัวก่อน แล้วเอาที่เริ่มล่าสุด
        r.update(status=a.tasks_or_result, finished=now(), note=a.note or "")
        r.pop("age_sec", None), r.pop("done_sec", None)
        write_json(REVIEWS / f"{r['id']}.json", r)
        print(f"REVIEW={a.tasks_or_result.upper()} id={r['id']}")
        return 0
    return 1


def plan_trail(row: dict, rows: list[dict], reviews: list[dict]) -> dict:
    """เส้นทางของแผนที่งานนี้รัน (ให้การ์ดบอกว่าอยู่ขั้นไหน): ผู้สืบก่อนแผน → แผน → Flash ทำ → ตรวจ → แก้
    runs = งานแผนเดียวกันที่จบแล้ว (ชื่อไฟล์แผนตรงกัน) · checks = งานผู้ตรวจ (verify) ของแผนนี้ · reviews = Claude ตรวจ (/flash-check)
    sleuths = ผู้สืบในโปรเจกต์เดียวกันที่จบก่อนแผนนี้เริ่มรอบแรก ≤6 ชม. (เดาจากเวลา — ผู้สืบไม่ได้ผูกชื่อแผน จึงบอกว่า "อาจเกี่ยวข้อง")"""
    key = Path(str(row.get("plan") or "").replace("\\", "/")).name
    if not key or row.get("message"):
        return {}
    same = [r for r in rows if r is not row and Path(str(r.get("plan") or "").replace("\\", "/")).name == key and r.get("project_name") == row.get("project_name")]
    done = sorted([r for r in same if r.get("finished") and r.get("finished") <= (row.get("created") or "9")], key=lambda r: r["finished"])
    pick = lambda r: {"id": r["id"], "kind": r.get("kind") or "work", "state": r.get("state", ""), "tasks": r.get("tasks", ""), "finished": r.get("finished", "")}
    runs = [pick(r) for r in done if (r.get("kind") or "work") == "work"]
    checks = [pick(r) for r in done if r.get("kind") == "verify"]
    rv = sorted([{"status": r.get("status", ""), "started": r.get("started", ""), "finished": r.get("finished", ""), "tasks": r.get("tasks", "")}
                 for r in reviews if r.get("plan_name") == key and r.get("started", "") <= (row.get("created") or "9")], key=lambda r: r["started"])
    first = min([r.get("created", "") for r in same if r.get("created")] + [row.get("created") or now()])
    t0 = _ts(first)
    sleuths = [pick(r) for r in rows if re.search(r"investigator", r.get("agent") or "", re.I)
               and r.get("project_name") == row.get("project_name") and r.get("finished")
               and 0 <= t0 - _ts(r["finished"]) <= 6 * 3600] if t0 else []
    msg = {r.get("id"): (r.get("message") or "").strip() for r in rows}
    for sl in sleuths:  # หัวข้อที่สืบ = บรรทัดแรกของข้อความ ตัดคำนำ "ผู้สืบ (...) —"
        sl["what"] = re.sub(r"^.*?—\s*", "", (msg.get(sl["id"]) or "").splitlines()[0] if msg.get(sl["id"]) else "")[:60]
    return {"plan": key, "runs": runs[-5:], "n_runs": len(runs), "checks": checks[-3:], "reviews": rv[-3:],
            "sleuths": sleuths[-3:], "n_sleuths": len(sleuths)}


def ui_state() -> dict:
    """สถานะทั้งหมดสำหรับ /api/state — อ่านผ่านฟังก์ชันคิวเดิม (ไม่เขียนตรรกะคิวซ้ำ)"""
    auto_clear_dead()  # ป้ายงานตายที่ค้างเกินเวลาที่ตั้ง → รับทราบให้เอง ก่อนสร้างรายการ
    held = held_slots()
    sch = schedule(held)
    slot_of = {h.get("id"): h for h in held}
    running, queued, history, dead, kills = [], [], [], [], []
    raw = {}
    for j in jobs():
        raw[j.get("id")] = j
        st = live_state(j)
        kills += [dict(k, job=j["id"], project_name=Path(j.get("project", "")).name, age_sec=_secs(k.get("at", ""))) for k in j.get("shell_kills") or []]
        row = {k: j.get(k, "") for k in ("id", "project", "plan", "tasks", "message", "title", "model",
                                         "kind", "agent", "readonly", "created", "started", "finished", "session", "result", "rc")}
        row.update(state=st, project_name=Path(j.get("project", "")).name, attempts=len(j.get("logs") or []), qa=j.get("qa") or None, doc=doc_row(j),
                   perm_denied=[f"{x.get('kind', '')}: {x.get('path', '')}" for x in j.get("perm_denied") or []][:5])
        if st == "dead" and j.get("status") in ("queued", "running"):  # ไฟล์ยังบอก queued/running แต่ process flashq ตายแล้ว → ป้ายเตือน
            row.update(was=j.get("status"), pid=j.get("pid"), child_pid=j.get("child_pid") or 0,
                       child_alive=pid_alive(j.get("child_pid") or 0, j.get("child_pid_start") or 0),
                       rerun=(f'{run_cmd(True)} run {j["plan"]} {j.get("tasks", "")} --project "{j.get("project", "")}"'
                              if j.get("plan") else ""))
            dead.append(row)
        row["claude_session"] = j.get("claude_session") or ""  # session Claude Code ที่สั่งงานนี้ (ผู้ใช้ตามปัญหากลับไปถูก session)
        if st in ("running", "queued", "dead"):  #งานที่จบแล้วไม่ต้องไล่อ่าน transcript ทุกรอบที่หน้าเว็บถาม
            row["claude_title"] = claude_session_title(row["claude_session"])
        row["variant"] = j.get("variant") or ""  # ระดับความคิดที่ส่งให้ opencode จริง (ว่าง = ไม่ส่ง ใช้ค่าปกติของ provider)
        if st == "queued":  # ยังไม่เริ่ม = ยังไม่มีค่าบันทึก → บอกค่าที่จะใช้ (ชนิดเดียวกับที่ cmd_run จะคำนวณ)
            row["variant"] = variant_for(j.get("kind") or ("test" if j.get("message") else "work"), None, Path(j.get("project") or "."))
        if st == "running":
            h = slot_of.get(j["id"], {})
            row.update(elapsed_sec=_secs(j.get("started", "")), slot=h.get("slot") or j.get("slot") or 0, extra=bool(h.get("extra")),
                       log_idle_sec=log_idle_sec(j), plan_done=plan_done_tasks(j),
                       shell_watch=_fresh_shell_watch(j),
                       qa_live=({"n": ql["n"], "names": ql["names"], "age_sec": int(time.time() - ql["at"]), "moved_sec": int(ql["at"] - ql["moved"])}
                                if (ql := j.get("qa_live")) and j.get("kind") == "qa" else None),
                       shell_kills=len(j.get("shell_kills") or []), shell_released=len(j.get("shell_released") or []),
                       agent_act=_agent_act_row(j.get("agent_act")))
            running.append(row)
        elif st == "queued":
            row.update(wait_sec=_secs(j.get("created", "")), legacy=j.get("qv", 0) < QUEUE_VERSION,
                       run_now=(RUN_NOW / j["id"]).exists(),
                       wait_reason=sch["reasons"].get(j["id"]) or ("กำลังจะเริ่ม" if j["id"] in sch["start"] else ""))
            queued.append(row)
        else:
            row["duration_sec"] = (_secs(j.get("started") or j.get("created", ""), j["finished"])
                                   if j.get("finished") else None)  # งานตายไม่มีเวลาจบ = ไม่รู้ระยะเวลา
            row["reason"] = job_reason(j, st)
            history.append(row)
    for i, row in enumerate(queued, 1):
        row["position"] = i
    agent, accs = accounts()
    cfg = read_json(OC_CONFIG)
    providers = cfg.get("provider", {})
    cached = (_UI_MODELS_CACHE.get("v") or (0, ([], "")))[1][0]  # แคชของหน้าเว็บ (ไม่เรียก opencode ตอน poll) · มากับ opencode = ใช้ได้ด้วย
    acc_rows = [{"short": s, "model": m, "available": m.partition("/")[2] in providers.get(m.partition("/")[0], {}).get("models", {}) or m in cached}
                for s, m in accs]
    rows = history + queued + running
    history_total = len(history)
    all_rv = _review_rows()
    for row in running + queued:  # เส้นทางของแผน (ใช้ประวัติทั้งหมดก่อนตัดเหลือ 300)
        row["trail"] = plan_trail(row, rows, all_rv)
        if row["trail"]:
            row["trail"]["usage"] = usage_brief(Path(row["trail"]["plan"]).stem)  # ผลล่าสุดของ flashq usage (ไม่มี = {})
    rv_act, rv_done = ui_reviews()
    history = history[::-1][:300]
    flash_brief_rows(history[:8], raw)
    for row in history[:8]:  # ตาราง "เพิ่งจบ" โชว์ 8 แถวแรก — ใส่ชื่อ session เฉพาะที่โชว์ (ไม่ไล่อ่าน transcript ของ 300 แถว)
        row["claude_title"] = claude_session_title(row["claude_session"])
    goals = ui_goals(running, history, queued)
    return {"now": now(), "lock": held[0] if held else {}, "slots": {"used": len(held), "max": max_parallel(), "held": held},
            "schedule": sch["mode"], "open_session": {True: "on", False: "off"}.get(_onoff(read_json(CONFIG).get("open_session")), "auto"), "starve_min": starve_min(), "dead_clear_hours": dead_clear_hours(),
            "running": running[0] if running else None, "running_list": running, "dead": dead, "queued": queued, "history": history,
            "history_total": history_total, "agent": agent, "current_model": configured_model(), "accounts": acc_rows, "accounts_source": accounts_source(),
            "projects": sorted({r["project_name"] for r in rows if r["project_name"]}),
            "project_paths": sorted({r["project"] for r in rows if r["project"]}),
            "qa_presets": {p: n for p in sorted({r["project"] for r in rows if r["project"]}) if (n := qa_preset_names(p))},  # ชุดทดสอบที่ตั้งไว้ของแต่ละโปรเจกต์ (ให้ฟอร์มส่งงานเลือกได้)
            "doc_presets": {p: n for p in sorted({r["project"] for r in rows if r["project"]}) if (n := doc_preset_names(p))},
            "submit_fails": submit_failures(),
            "stats": job_stats(history), "reviews": rv_act, "reviews_done": rv_done,
            "review_ttl_min": REVIEW_TTL_MIN,
            "guard": {"idle_min": DEFAULTS["shell_idle_min"], "kills": sorted(kills, key=lambda k: k["at"])[-20:][::-1]},
            "goals": goals}


def job_reason(j: dict, state: str) -> str:
    """สาเหตุสั้น ๆ ของงานที่จบไม่ OK สำหรับ tooltip บนป้ายสถานะ (หน้าเว็บ) · ว่าง = ไม่มีข้อมูลสาเหตุ"""
    last = one_line(j.get("last") or "", 400)
    if state == "timeout":
        return one_line(j.get("timeout_reason") or "หมดเวลา (ไม่มีบันทึกสาเหตุ)", 500)
    if state == "nostart":
        diag = j.get("nostart_diag") or []
        return one_line(f"opencode ไม่เริ่มทำงาน (รอ {START_LIMIT_FIRST_SEC}/{START_LIMIT_SEC} วิ ต่อรอบ)" + (f" · รอบสุดท้าย: {diag[-1]}" if diag else ""), 500)
    if state == "denied":
        return one_line("opencode ปฏิเสธสิทธิ์: " + " · ".join(f"{x.get('kind', '')}: {x.get('path', '')}" for x in (j.get("perm_denied") or [])[:5]), 500)
    if state == "quota":
        return last or "โควตาของโมเดลหมด"
    if state == "fail":
        return (f"exit {j.get('rc')} · " if j.get("rc") not in (None, "") else "") + (last or "ไม่มีข้อความท้าย — เปิด log ดู")
    return ""


def flash_brief_rows(rows: list, raw: dict) -> None:
    """ใส่ row["flash"] = token/ค่าจ่ายจริง/ราคาถ้าเป็น Claude ให้งานที่จบแล้วที่หน้าเว็บจะโชว์ (ตาราง "เพิ่งจบ") · อ่านพลาด = ไม่ใส่"""
    todo = [r for r in rows if r.get("finished") and r.get("id")]
    if not todo:
        return
    con, table = oc_open_db(), price_table()
    try:
        for r in todo:
            try:
                b = job_flash_brief(raw.get(r["id"]) or {}, con, table)
            except Exception:
                b = None
            if b:
                r["flash"] = b
    finally:
        if con is not None:
            con.close()


def doc_row(j: dict) -> dict | None:
    """ส่วนของช่างเอกสารที่หน้าเว็บต้องใช้ (ไม่ส่ง backup/snapshot ภายใน)"""
    d = j.get("doc") if j.get("kind") == "doc" else None
    if not d:
        return None
    return {"name": d.get("name", ""), "verdict": d.get("verdict", ""), "state": d.get("state", ""), "phase": d.get("phase", ""),
            "why": (d.get("why") or [])[:DOC_WHY_MAX + 1], "changed": (d.get("changed") or [])[:40], "n_changed": len(d.get("changed") or []),
            "revert_problems": (d.get("revert_problems") or [])[:6], "agent_text": one_line(d.get("agent_text") or "", 500)}


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

    def not_verify(r) -> bool:  # งานตรวจ/สืบ/ทดสอบ/เอกสารต่างจากงานทำตามแผน (และทดสอบไม่ใช้โมเดล) → ไม่ปนสถิติ/เวลาเฉลี่ยของงานทำจริง
        return kind(r) not in AGENT_KINDS and kind(r) not in ("qa", "doc")
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
        if body.get("kind") == "qa":  # นักทดสอบ: เลือกได้เฉพาะ "ชื่อชุด" ที่ตั้งไว้ใน .flash.json — คำสั่งจริงไม่รับจากหน้าเว็บ (กันสั่งรันคำสั่งอะไรก็ได้)
            names = body.get("names") or []
            if not isinstance(names, list) or len(names) > 12 or not all(isinstance(n, str) and QA_NAME_RE.match(n) for n in names):
                return [], "ชื่อชุดทดสอบไม่ถูกต้อง"
            have = qa_preset_names(project)
            if not have:
                return [], "โปรเจกต์นี้ยังไม่ได้ตั้ง qa.presets ใน .flash.json"
            miss = [n for n in names if n not in have]
            if miss:
                return [], f"ไม่มีชุดทดสอบ: {', '.join(miss)} (มี: {', '.join(have)})"
            argv = [*self_argv(), "qa", *names, "--project", project]
            if body.get("no_analyze"):
                argv.append("--no-analyze")
            timeout_min = num("timeout_min", 0, 1440)
            if timeout_min:
                argv += ["--timeout-min", str(timeout_min)]
            return argv, ""
        if body.get("kind") == "doc":  # ช่างเอกสาร: เลือกได้เฉพาะ "ชื่อชุด" ที่ตั้งไว้ใน .flash.json (paths/brief มาจากไฟล์ ไม่รับจากหน้าเว็บ)
            names = body.get("names") or []
            if not isinstance(names, list) or len(names) != 1 or not isinstance(names[0], str) or not QA_NAME_RE.match(names[0]):
                return [], "ต้องเลือกชุดเอกสาร 1 ชุด"
            have = doc_preset_names(project)
            if not have:
                return [], "โปรเจกต์นี้ยังไม่ได้ตั้ง doc.presets ใน .flash.json"
            if names[0] not in have:
                return [], f"ไม่มีชุดเอกสาร: {names[0]} (มี: {', '.join(have)})"
            argv = [*self_argv(), "doc", names[0], "--project", project]
            timeout_min = num("timeout_min", 0, 1440)
            if timeout_min:
                argv += ["--timeout-min", str(timeout_min)]
            return argv, ""
        kind = body.get("kind") if body.get("kind") in AGENT_KINDS else ""
        argv = [*self_argv(), kind or "run"]
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
        if body.get("skip_precheck") and not kind and not message:  # เฉพาะ run ตามแผน (verify/investigate ไม่มีด่านนี้) · ต้องสั่งทุกครั้ง ไม่จำค่า
            argv.append("--skip-precheck")
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


def spawn_run(argv: list[str], project: str, wait_sec: float = 8, body: dict | None = None) -> dict:
    """รัน `flashq.py run` แบบแยกขาด (detached) ให้ใช้คิวเดิม · รอจนเห็นไฟล์งานใหม่ หรือ process จบก่อน (= ผิดพลาด)"""
    LOGS.mkdir(parents=True, exist_ok=True)
    JOBS.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"submit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.out"
    before = {f.name for f in JOBS.glob("*.json")}
    flags = HIDDEN_DETACH_FLAGS
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
    # ด่านตรวจ (git fetch ช้า · แผนใหญ่/พิการ) อาจล้มหลังหน้าต่างนี้ → วางป้ายไว้ให้ ui_state รายงานเมื่อ process จบโดยไม่มีไฟล์งาน (ไม่ให้เงียบ)
    try:
        write_json(Path(str(out) + ".pending"), {"at": now(), "project": project, "pid": p.pid,
                                                  "body": {k: v for k, v in (body or {}).items() if k in SUBMIT_KEYS}})
    except OSError:
        pass
    return {"ok": True, "job": "", "pid": p.pid, "out": str(out), "message": "ส่งแล้ว (ยังไม่เห็นไฟล์งาน — ถ้าด่านตรวจล้ม จะมีป้ายเตือนขึ้นบนหน้านี้)"}


SUBMIT_KEYS = ("project", "plan", "tasks", "kind", "agent", "message", "switch_on_quota", "timeout_min", "attach", "no_open", "auto", "readonly", "prompt", "names", "no_analyze")


def submit_failures() -> list[dict]:
    """คำสั่งส่งงานจากหน้าเว็บที่ process จบแล้วโดยไม่เคยสร้างงาน (ด่านตรวจล้มหลังหน้าต่างรอ 8 วิ) → รายการให้หน้าเว็บเตือน · ป้ายเก่าเกิน 1 วัน/ที่งานเริ่มแล้วถูกล้างทิ้ง"""
    out = []
    if not LOGS.exists():
        return out
    for mark in sorted(LOGS.glob("submit_*.out.pending")):
        log = Path(str(mark)[:-len(".pending")])
        info = read_json(mark)
        try:
            age = time.time() - mark.stat().st_mtime
        except OSError:
            continue
        if age > 86400 or not log.exists():
            mark.unlink(missing_ok=True)
            continue
        if pid_alive(info.get("pid", 0)):
            continue  # ยังทำงานอยู่ (ด่านยังไม่จบ/งานเข้าคิวแล้ว)
        text = log.read_text(encoding="utf-8", errors="replace").strip()
        if re.search(r"^(SLOT |START |QUEUED )", text, re.M):  # งานถูกสร้างและเดินแล้ว = ไม่ใช่ด่านล้ม (ผลงานดูที่คิว/ประวัติ)
            mark.unlink(missing_ok=True)
            continue
        out.append({"id": mark.name[:-len(".out.pending")], "at": info.get("at", ""), "project": info.get("project", ""),
                    "body": info.get("body") or {}, "message": text[-1200:] or "process จบโดยไม่มีข้อความ (อาจ crash)",
                    "can_skip": "แผนพิการ" in text})
    return out


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
        files += [f for f in LOGS.glob("submit_*.out*") if f.stat().st_mtime < cutoff]
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
    """แปลง 1 บรรทัด JSON ของ opencode เป็นข้อความอ่านง่าย · None = ข้าม (บรรทัดที่ไม่ใช่ JSON object เช่น log ของนักทดสอบ = แสดงตามเดิม)"""
    try:
        ev = json.loads(line)
    except ValueError:
        return line
    if not isinstance(ev, dict):  # บรรทัดข้อความล้วนที่บังเอิญเป็น JSON (เช่น "123" "true") ต้องไม่ทำให้หน้า log ล้ม
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
           "state": live_state(j), "last": j.get("last", ""),
           "denied_help": "\n".join(perm_fix_lines(j["perm_denied"], partial=j.get("result") != "DENIED")) if j.get("perm_denied") else "",
           "unverified": j.get("unverified") or []}
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
    boot = secrets.token_hex(6)  # รหัสรอบการเริ่ม server — หน้าเว็บเทียบเพื่อรู้ว่า server รีสตาร์ตแล้ว (token เก่าใช้ไม่ได้)

    class H(BaseHTTPRequestHandler):
        server_version = "flashq-ui"

        def log_message(self, *args):  # เงียบ (poll ทุก 2-3 วิ)
            pass

        def _send(self, code: int, body, ctype: str = "application/json; charset=utf-8") -> None:
            if not isinstance(body, (bytes, str)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass  # เบราว์เซอร์ปิด/รีเฟรช/ยกเลิก request ก่อนรับคำตอบ — เรื่องปกติ ไม่ต้องพ่น traceback

        def _host_ok(self) -> bool:
            """กัน DNS rebinding: Host ต้องเป็น 127.0.0.1/localhost พอร์ตนี้ · Origin (ถ้ามี) ต้องตรงด้วย"""
            p = self.server.server_address[1]
            allowed = {f"127.0.0.1:{p}", f"localhost:{p}"}
            if self.headers.get("Host", "") not in allowed:
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in {f"http://{h}" for h in allowed}

        def _host_denied(self):
            p = self.server.server_address[1]
            return self._send(403, {"error": f"ไม่ได้รับอนุญาต: Host/Origin ไม่ตรง — เปิดหน้านี้ผ่าน http://127.0.0.1:{p} หรือ http://localhost:{p} เท่านั้น "
                                             "(ห้ามผ่าน IP เครื่องอื่น ชื่อเครื่อง proxy หรือ tunnel)", "code": "host"})

        def do_GET(self):
            if not self._host_ok():
                return self._host_denied()
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/":
                html = (RES / "ui.html").read_text(encoding="utf-8").replace("{{TOKEN}}", token).replace("{{VERSION}}", VERSION)
                return self._send(200, html, "text/html; charset=utf-8")
            if u.path == "/api/state":
                return self._send(200, {**ui_state(), "boot": boot})
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
                proj = q.get("project", [""])[0]
                ok = bool(proj) and Path(proj).is_absolute()
                return self._send(200, {"plans": list_plans(proj), "qa_presets": qa_preset_names(proj) if ok else [], "doc_presets": doc_preset_names(proj) if ok else []})
            if u.path == "/api/doc_diff":
                j = next((x for x in jobs() if x.get("id") == q.get("id", [""])[0] and x.get("kind") == "doc"), None)
                if not j:
                    return self._send(404, {"error": "ไม่พบงานช่างเอกสาร"})
                return self._send(200, doc_diff(j))
            if u.path == "/api/models":  # โมเดลที่เครื่องนี้มี (เหมือน flashq models) + โมเดลของแต่ละบทบาท · ให้ตัวแก้บัญชีเลือก
                models, note = ui_models(q.get("refresh", ["0"])[0] == "1")
                return self._send(200, {"models": models, "providers": provider_rows(models), "note": note, "tail": recommended_tail(), "roles": role_rows()})
            if u.path == "/api/setup":  # วิซาร์ดตั้งค่าครั้งแรก — สถานะเครื่อง (อ่านอย่างเดียว)
                return self._send(200, setup_status())
            if u.path == "/api/flash_usage":  # สรุป token/USD ของ Flash + ประมาณการประหยัดเทียบ Claude (อ่านอย่างเดียว · แคช 30 วินาที)
                try:
                    days = min(max(float(q.get("days", ["30"])[0]), 1), 3650)
                except ValueError:
                    return self._send(400, {"error": "days ต้องเป็นตัวเลข"})
                hit = _FLASH_SUM_CACHE.get(days)
                if not hit or time.time() - hit[0] > 30:
                    hit = _FLASH_SUM_CACHE[days] = (time.time(), flash_usage_summary(days))
                return self._send(200, hit[1])
            return self._send(404, {"error": "ไม่พบ"})

        def do_POST(self):
            # อ่าน body ทิ้งก่อนตอบ 403 — ถ้าปิดการเชื่อมต่อทั้งที่ body ยังค้างรับ Windows จะส่ง RST ทำให้ฝั่งเรียกอ่านคำตอบไม่ได้ (ConnectionResetError)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(n, 65536)) if n > 0 else b""
            except (ValueError, OSError):
                n, raw = 0, b""
            if not self._host_ok():
                return self._host_denied()
            if not secrets.compare_digest(self.headers.get("X-Flashq-Token", "").encode("utf-8"), token.encode("utf-8")):
                return self._send(403, {"error": "ไม่ได้รับอนุญาต: token ของหน้านี้หมดอายุ (server รีสตาร์ตหรือเปิดหน้าไว้นานเกินไป) — "
                                                 "รีเฟรชหน้า (Ctrl+F5) แล้วกดอีกครั้ง · ถ้ายังไม่ได้ ตรวจว่าไม่มี flashq ui ซ้อนอยู่หลายพอร์ต", "code": "token"})
            try:
                body = json.loads(raw or b"{}")
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
            if path == "/api/doc_review":  # ปุ่มรับ/ทิ้งร่างของช่างเอกสาร — ทิ้งต้องยืนยัน confirm=id · ทับไฟล์ที่ผู้ใช้แก้ต่อต้องส่ง force=true
                j = next((x for x in jobs() if x.get("id") == body.get("id") and x.get("kind") == "doc"), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงานช่างเอกสาร"})
                if body.get("action") not in ("accept", "discard"):
                    return self._send(400, {"ok": False, "message": "action ต้องเป็น accept หรือ discard"})
                if body["action"] == "discard" and body.get("confirm") != j["id"]:
                    return self._send(400, {"ok": False, "message": "ต้องยืนยันด้วย id ของงาน"})
                ok, msg = doc_review(j, body["action"], body.get("force") is True)
                return self._send(200 if ok else 409, {"ok": ok, "message": msg})
            if path == "/api/runnow":  # รันเลย (ช่องพิเศษ) — มีไฟล์ซ้อนต้องส่ง ack_overlap=true
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงาน"})
                rep = overlap_report(j)
                if rep["any_overlap"] and body.get("ack_overlap") is not True:
                    return self._send(409, {"ok": False, "message": "ไฟล์ซ้อน/แผนห้ามรันคู่กับงานที่กำลังทำ — ต้องติ๊กยืนยันก่อน", "report": rep})
                ok, msg = request_run_now(j)
                return self._send(200 if ok else 409, {"ok": ok, "message": msg})
            if path == "/api/config":
                keys = [k for k in ("schedule", "max_parallel", "starve_min", "dead_clear_hours", "open_session") if k in body]
                if not keys:
                    return self._send(400, {"ok": False, "message": "ต้องมี max_parallel / schedule / starve_min / dead_clear_hours / open_session"})
                msgs = []
                for k in keys:
                    err, msg = set_config(k, body[k])
                    if err:
                        return self._send(400, {"ok": False, "message": err})
                    msgs.append(msg)
                return self._send(200, {"ok": True, "max_parallel": max_parallel(), "schedule": schedule_mode(),
                                        "message": " · ".join(msgs)})
            if path == "/api/dismiss" and body.get("submit"):  # รับทราบป้าย "ส่งงานแล้วล้มหลังหน้าต่างรอ" → ลบป้าย
                name = str(body["submit"])
                if not re.fullmatch(r"submit_[\d_]+", name):
                    return self._send(400, {"ok": False, "message": "ชื่อไม่ถูกต้อง"})
                (LOGS / f"{name}.out.pending").unlink(missing_ok=True)
                return self._send(200, {"ok": True, "message": "รับทราบแล้ว"})
            if path == "/api/dismiss" and body.get("all"):  # รับทราบงานที่ process ตายทั้งหมดในครั้งเดียว (ข้ามงานที่ opencode ลูกยังทำงานอยู่)
                done, skipped = 0, 0
                for x in jobs():
                    if live_state(x) != "dead" or x.get("status") not in ("queued", "running"):
                        continue
                    if pid_alive(x.get("child_pid") or 0, x.get("child_pid_start") or 0):
                        skipped += 1
                        continue
                    dismiss_dead(x)
                    done += 1
                return self._send(200, {"ok": True, "cleared": done, "skipped": skipped,
                                        "message": f"รับทราบแล้ว {done} งาน" + (f" · ข้าม {skipped} งานที่ opencode ยังทำงานอยู่ (ตรวจเองก่อน)" if skipped else "")})
            if path == "/api/dismiss":  # รับทราบงานที่ process ตาย → บันทึกสถานะ dead
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j or live_state(j) != "dead" or j.get("status") not in ("queued", "running"):
                    return self._send(409, {"ok": False, "message": "ไม่ใช่งานที่ process ตายค้างสถานะ"})
                note = dismiss_dead(j)
                return self._send(200, {"ok": True, "message": f"บันทึก {j['id']} เป็น 'ตาย' แล้ว" + (f" · {note}" if note else "")})
            if path == "/api/submit":
                argv, err = build_run_argv(body)
                if err:
                    return self._send(400, {"ok": False, "message": err})
                r = spawn_run(argv, str(body["project"]).strip().strip('"'), body=body)
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
                if j.get("kind") == "doc":
                    spec["names"] = [str(j.get("tasks") or "")]
                if j.get("kind") == "qa":  # สั่งซ้ำ = ชุดเดิมที่เคยรัน (ไม่ใช่ทุกชุด) · ชุดจาก --cmd ไม่มีในไฟล์ตั้งค่า → build_run_argv ปฏิเสธพร้อมบอกชื่อ
                    spec["names"] = str(j.get("tasks") or "").split()
                argv, err = build_run_argv(spec)
                if err:
                    return self._send(400, {"ok": False, "message": err})
                r = spawn_run(argv, spec["project"], body=spec)
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
            if path == "/api/claude_check":  # ปุ่ม "เปิด Claude ตรวจ" บนการ์ดงานที่จบแล้ว
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงาน"})
                code, d = claude_check_action(j, bool(body.get("cli")))
                return self._send(code, d)
            if path == "/api/open_claude":  # ปุ่ม "เปิด session" — เปิด session Claude ที่สั่งงานนี้ในแอป desktop
                j = next((x for x in jobs() if x.get("id") == body.get("id")), None)
                if not j:
                    return self._send(404, {"ok": False, "message": "ไม่พบงาน"})
                code, d = claude_open_session_action(j)
                return self._send(code, d)
            if path == "/api/goal":  # ปุ่มบนการ์ดเป้าหมาย
                code, d = goal_ui_action(str(body.get("id") or ""), str(body.get("action") or ""), body)
                return self._send(code, d)
            if path == "/api/switch":
                import contextlib
                import io
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    new = switch_account(str(body.get("target") or "next"))
                return self._send(200 if new else 400, {"ok": bool(new), "model": new, "message": buf.getvalue().strip()})
            if path == "/api/accounts":  # แก้รายการบัญชีสลับโมเดล (เพิ่ม/แก้/ลบ/ย้าย/คืนค่า repo)
                ok, msg = edit_accounts(str(body.get("action") or ""), body)
                return self._send(200 if ok else 400, {"ok": ok, "message": msg})
            if path == "/api/setup_install":  # วิซาร์ด: ติดตั้งคำสั่ง/agent/hook แบบ global (เหมือน flashq install · ไม่ทับไฟล์ของผู้ใช้เอง)
                res = setup_capture(cmd_install, argparse.Namespace(force=False, hooks=bool(body.get("hooks")), check=False, models="skip"))
                return self._send(200, {**res, "status": setup_status()})
            if path == "/api/setup_init":  # วิซาร์ด: ตั้งค่าโปรเจกต์ (เหมือน flashq init · ไม่ commit/push ให้)
                proj = str(body.get("project") or "").strip()
                if not proj or not Path(proj).is_absolute() or not Path(proj).is_dir():
                    return self._send(400, {"ok": False, "output": "ต้องเป็น path เต็มของโฟลเดอร์ที่มีอยู่จริง"})
                return self._send(200, setup_capture(cmd_init, argparse.Namespace(project=proj, force=False, install=False, commit=False)))
            if path == "/api/setup_done":  # วิซาร์ด: จบแล้ว (ไม่เด้งเองอีก)
                write_json(SETUP_FILE, {"done": bool(body.get("done", True)), "at": time.time()})
                return self._send(200, {"ok": True})
            if path == "/api/role_model":  # ตั้งโมเดลของบทบาท (เหมือน flashq models --set)
                role = next((ag for k, ag, _ in MODEL_ROLES if str(body.get("role") or "") in (k, ag)), "")
                model = str(body.get("model") or "").strip()
                models = ui_models()[0]
                if not role or not model:
                    return self._send(400, {"ok": False, "message": "ต้องระบุบทบาทและโมเดล"})
                if models and model not in models:
                    return self._send(400, {"ok": False, "message": f"เครื่องนี้ไม่มีโมเดล {model}"})
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()):
                    ok = set_agent_model(role, model)
                return self._send(200 if ok else 400, {"ok": ok, "message": f"{role} → {model}" if ok else "เขียน opencode.json ไม่ได้"})
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
                # Windows loopback: ตอบคำขอที่ใหญ่กว่า ~100KB (ui.html ~240KB) ค้างจน client หมดเวลาเป็นครั้งคราว ~3% (http.server เปล่าก็เป็น · วัดแล้ว
                # 1,200 คำขอ SO_SNDBUF=0 ไม่ค้างเลย · ตั้งที่ listening socket แล้ว socket ที่ accept สืบทอดค่า · ค่า 1MB ไม่ช่วย)
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 0)
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
    threading.Thread(target=ui_models, daemon=True).start()  # อุ่นรายการโมเดลของเครื่อง (opencode models ช้า) ให้ตัวแก้บัญชี/สถานะ "ใช้ได้" พร้อมเร็ว
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


def gui_set_icon(title: str) -> None:
    """ใส่ไอคอนให้หน้าต่าง (Windows: WM_SETICON) — exe ใช้ไอคอนที่ฝัง · ไม่ใช่ exe ใช้ assets/flashq.ico"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ico = RES / ("flashq.ico" if FROZEN else "assets/flashq.ico")
        if not ico.is_file():
            return
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, title)
        for flag, size in ((0, 16), (1, 32)):  # ICON_SMALL / ICON_BIG
            h = u.LoadImageW(None, str(ico), 1, size, size, 0x10)  # IMAGE_ICON · LR_LOADFROMFILE
            if hwnd and h:
                u.SendMessageW(hwnd, 0x80, flag, h)  # WM_SETICON
    except Exception:
        pass


def hide_child_consoles() -> None:
    """exe แบบหน้าต่างไม่มี console → process ลูกทุกตัว (git/opencode/node ฯลฯ) เปิดกล่องดำของตัวเองวูบหนึ่ง · ตั้ง CREATE_NO_WINDOW เป็นค่าเริ่มต้น
    (ที่ระบุ creationflags เองอยู่แล้ว เช่น CREATE_NEW_CONSOLE ของการเปิดเทอร์มินัลให้ผู้ใช้ ไม่ถูกแตะ)"""
    if os.name != "nt":
        return
    orig = subprocess.Popen.__init__

    def init(self, *args, **kw):
        if not kw.get("creationflags"):
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        orig(self, *args, **kw)

    subprocess.Popen.__init__ = init


GUI_PORT = 4098


def cmd_gui(a) -> int:
    """หน้าต่างแอป (WebView2 ผ่าน pywebview) แทนการเปิดเบราว์เซอร์ — server เดิมรันในเธรด · pywebview ต้องติดตั้งแยก (ไม่บังคับสำหรับคำสั่งอื่น)"""
    try:
        import webview
    except ImportError:
        print("FAIL: ต้องติดตั้ง pywebview ก่อน (pip install pywebview) หรือใช้ `flashq ui` เปิดผ่านเบราว์เซอร์")
        return 1
    try:
        srv, _ = make_ui_server(a.port)
    except OSError as e:
        if a.port != GUI_PORT:
            print(f"FAIL: เปิดพอร์ต {a.port} ไม่ได้ ({e}) — ลอง --port อื่น")
            return 1
        srv, _ = make_ui_server(0)  # พอร์ตประจำถูกใช้อยู่ (เช่น เปิดแอปซ้อน) → สุ่มพอร์ต ค่าที่ตั้งไว้ในหน้าจอจะไม่ตามมา
    hide_child_consoles()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=ui_models, daemon=True).start()
    win = webview.create_window(f"flashq v{VERSION}", f"http://127.0.0.1:{srv.server_address[1]}/", width=1280, height=840, min_size=(900, 600))

    def on_shown():
        gui_set_icon("flashq")
        last = ""
        while True:  # ชื่อหน้าต่างตาม <title> ของหน้าเว็บ (ui.html เปลี่ยนตามงานที่รัน เช่น "▶ 2:10 · โปรเจกต์ · flashq")
            try:
                t = win.evaluate_js("document.title") or f"flashq v{VERSION}"
                if t != last:
                    win.set_title(t)
                    last = t
            except Exception:
                return  # หน้าต่างปิดแล้ว
            time.sleep(1)

    win.events.shown += lambda: threading.Thread(target=on_shown, daemon=True).start()
    try:  # เก็บ localStorage ลงดิสก์ (ภาษา/ขนาดฟอนต์/ธีม) · origin ต้องคงที่ด้วย (GUI_PORT) ไม่งั้นค่าหาย
        webview.start(debug=False, private_mode=False, storage_path=str(HOME / "webview"))  # ปิดหน้าต่าง = จบโปรแกรม
    except TypeError:  # pywebview รุ่นเก่าไม่มีพารามิเตอร์นี้
        webview.start(debug=False)
    srv.shutdown()
    srv.server_close()
    return 0


# ---------- โหมดเป้าหมาย (/flash-goal): ตั้งธง → วางแผน → Flash ทำ → ตรวจกับเกณฑ์ → วนจนผ่าน หรือชนเบรก ----------
GOAL_ITEM_RE = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s*(G-\d+)\s*(.*)$")
GOAL_VAGUE = ("สวย", "ดีขึ้น", "ดีกว่า", "ง่าย", "เร็วขึ้น", "เร็ว", "เหมาะสม", "ถูกต้อง", "สมบูรณ์", "เรียบร้อย", "ใช้งานได้", "ทำงานได้", "ไม่มีบั๊ก",
              "ลื่น", "นิ่ง", "ครบถ้วน", "user-friendly", "nice", "better", "faster", "clean", "properly", "works")
GOAL_TRIVIAL_RE = re.compile(r"^\s*(echo\b|true\s*$|exit\s+0\s*$|rem\b|:\s*$|cd\s*$|dir\s*$|ls\s*$|type\s+nul)", re.I)
GOAL_DEFAULT_ROUNDS, GOAL_ROUNDS_CAP, GOAL_DEFAULT_HOURS = 5, 10, 6
GOAL_BIG_ITEMS, GOAL_BIG_FILES = 8, 10  # เกณฑ์/รายการ goal-files เกินนี้ = ธงใหญ่ → เตือนให้แบ่งเฟส (ธงจริง 12 เกณฑ์ติด STOP/คนตรวจค้าง)
GOAL_UI_RE = re.compile(r"หน้าตา|หน้าจอ|ใช้ง่าย|ใช้งานง่าย|\bui\b|\bux\b|layout|ปุ่ม|เมนู|หน้าเว็บ", re.I)
GOAL_COUNT_RE = re.compile(r"[≥>]=?\s*\d|อย่างน้อย\s*\d|ครบ\s*\d|\d+\s*(?:จุด|ช่อง|ปุ่ม|รายการ)|นับ|count|ใน\s*dom|querySelector", re.I)


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
    ui_h = [i for i in items if i["human"] and GOAL_UI_RE.search(i["desc"] + " " + i["human"])]
    if ui_h:  # งาน UI: เกณฑ์นับของ (≥12 จุด · มีใน DOM) กันถอยได้แต่ไม่แทน "ใช้ง่าย" · ต้องล็อกแบบจาก mockup R0 ก่อนสร้างจริง
        counts = [i["id"] for i in machine if GOAL_COUNT_RE.search(i["desc"] + " " + i["cmd"] + " " + i["expect"])]
        if counts and len(counts) == len(machine):
            warns.append(f"เกณฑ์ UI ที่เครื่องตรวจเป็นการนับล้วน ({', '.join(counts)}) → ใช้กันถอยได้ แต่ไม่แทน \"ใช้ง่าย\" · คง {', '.join(i['id'] for i in ui_h)} เป็นคนตรวจระหว่างทาง")
        if not any("mockup" in (i["desc"] + i["cmd"] + i["expect"] + i["human"]).lower() for i in items):
            warns.append("งาน UI ยังไม่มีเกณฑ์อ้าง mockup → ทำรอบ R0 mockup 2–3 แบบให้ user เลือก แล้วล็อก \"โครงหน้าตรง mockup_X.html\" ก่อนวนสร้างจริง")
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
    if len(items) > GOAL_BIG_ITEMS or len(g["files"]) > GOAL_BIG_FILES:
        warns.append(f"ธงใหญ่ (เกณฑ์ {len(items)} ข้อ · goal-files {len(g['files'])} รายการ · เกณฑ์เตือน >{GOAL_BIG_ITEMS} ข้อ/>{GOAL_BIG_FILES} รายการ) "
                     "→ แบ่งเป็นเฟส: GOAL_<เรื่อง>_P1, _P2 … เฟสละ ≤8 เกณฑ์ที่เครื่องวัดได้ · เฟสแรกคือแกนที่ทุกอย่างพึ่ง · จบเฟสแล้วค่อยตั้งเฟสถัดไป · ข้อ `คนตรวจ:` รวมไว้เฟสท้ายสุด")
    return errs, warns


def _goal_state_path(root: Path, goal: Path) -> Path:
    return root / ".tmp" / "flashq-goal" / (goal.stem + ".json")


def _goal_load(root: Path, goal_arg: str) -> tuple[Path, Path, dict, dict]:
    goal = Path(goal_arg)
    goal = goal if goal.is_absolute() else root / goal
    sp = _goal_state_path(root, goal)
    st = read_json(sp)
    if not st:  # ต้นฉบับหาย (ลบ .tmp) → กู้จากสำเนาใน ~/.flashq/goal-state/ (รอบ/base เดิม ไม่ใช่เริ่มใหม่)
        rel = goal.relative_to(root).as_posix() if goal.is_relative_to(root) else str(goal)
        st = read_json(GOAL_STATE_BAK / f"{_goal_key(root, rel)}.json")
        if st:
            try:
                sp.parent.mkdir(parents=True, exist_ok=True)
                write_json(sp, st)
            except OSError:
                pass
            print("หมายเหตุ: ไฟล์สถานะธงใน .tmp/flashq-goal หาย → กู้สถานะธงจากสำเนา ~/.flashq/goal-state/ (รอบ/base เดิม)")
    return goal, sp, goal_parse(goal), st


GOALS_DIR = HOME / "goals"  # สำเนาสถานะเป้าหมายทุกโปรเจกต์ ให้ UI เห็น (ต้นฉบับอยู่ใน <project>/.tmp/flashq-goal/)
GOAL_STATE_BAK = HOME / "goal-state"  # สำเนาไฟล์สถานะธง (.tmp ในโปรเจกต์ถูกลบได้)


def _goal_key(root: Path, rel: str) -> str:
    """คีย์เดียวกับการ์ดใน goal_publish (ผูกโปรเจกต์ + path เป้าหมาย)"""
    return hashlib.sha1(f"{root.resolve()}|{rel}".lower().encode("utf-8")).hexdigest()[:12]


_TITLE_CACHE: dict[str, tuple[float, str]] = {}
CLAUDE_PROJECTS = Path(os.environ.get("FLASHQ_CLAUDE_HOME") or Path.home() / ".claude") / "projects"  # transcript ของ Claude Code (<โปรเจกต์>/<session>.jsonl · <session>/subagents/agent-*.jsonl)


CLAUDE_APP_SESSIONS = Path(os.environ.get("FLASHQ_CLAUDE_APP_HOME") or (Path(os.environ.get("APPDATA") or Path.home() / "Library" / "Application Support") / "Claude")) / "claude-code-sessions"
_APP_CACHE: dict[str, dict] = {}  # cli session id → {"host": local_…, "title": ชื่อใน sidebar}
_APP_FILES: dict[str, float] = {}  # ไฟล์ที่อ่านแล้ว → mtime (ไฟล์ไม่เปลี่ยน = ไม่อ่านซ้ำ)
_APP_SCAN = [0.0]


def _scan_app_sessions() -> None:
    """ทำดัชนี cliSessionId → local_… จากทุกไฟล์ <แอป>/claude-code-sessions/*/*/local_*.json (อ่านเฉพาะไฟล์ใหม่/ที่เปลี่ยน)"""
    _APP_SCAN[0] = time.time()
    try:
        files = list(CLAUDE_APP_SESSIONS.glob("*/*/local_*.json"))
    except OSError:
        return
    for f in files:
        try:
            mt = f.stat().st_mtime
            if _APP_FILES.get(str(f)) == mt:
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            _APP_FILES[str(f)] = mt
            if d.get("cliSessionId"):
                _APP_CACHE[str(d["cliSessionId"])] = {"host": str(d.get("sessionId") or f.stem), "title": str(d.get("title") or "")}
        except (OSError, ValueError):
            continue


def claude_app_session(sid: str) -> dict:
    """session ของแอป Claude desktop ที่ตรงกับ session id ของ Claude Code (CLAUDE_CODE_SESSION_ID) → {"host": "local_…", "title": ชื่อใน sidebar}
    หาไม่เจอ (สั่งจาก CLI/ไม่มีแอป/session ใหม่ยังไม่มีไฟล์) = {} · ไล่ไฟล์ใหม่ไม่ถี่กว่า 5 วิ (ชื่อในแอปเปลี่ยนได้ จึงอ่านไฟล์ที่ mtime เปลี่ยนซ้ำ)"""
    if not sid or not re.fullmatch(r"[\w-]+", sid):
        return {}
    if time.time() - _APP_SCAN[0] > 5:
        _scan_app_sessions()
    return _APP_CACHE.get(sid, {})


def claude_session_title(sid: str) -> str:
    """ชื่อ session ใน Claude Code (ชื่อที่เห็นใน sidebar) จากแอป desktop (ไฟล์ claude-code-sessions · ตรงกับที่เห็นจริง) ไม่เจอ = จาก transcript ~/.claude/projects/*/<sid>.jsonl · หาไม่เจอ = ''"""
    return claude_app_session(sid).get("title", "") or _claude_transcript_title(sid)


def claude_open_session_action(j: dict) -> tuple[int, dict]:
    """ปุ่ม "เปิด session" บนการ์ดงาน: เปิด session Claude ที่สั่งงานนี้ในแอป Claude desktop (claude://code/continue?session=local_…)
    host id มาจากงาน (claude_host · งานใหม่) หรือหาจาก session id ของ Claude Code ในโฟลเดอร์ของแอป (งานเก่า) · รับเฉพาะ id ที่ผ่านรูปแบบ local_…"""
    sid = j.get("claude_session") or ""
    if not sid:
        return 404, {"ok": False, "message": "งานนี้ไม่ได้สั่งจาก Claude Code — ไม่มี session ให้เปิด"}
    host = j.get("claude_host") or claude_app_session(sid).get("host", "")
    if not re.fullmatch(r"local_[A-Za-z0-9-]{1,64}", host or ""):
        return 404, {"ok": False, "message": "ไม่พบ session นี้ในแอป Claude desktop (สั่งจาก CLI/session ถูกลบ/เครื่องอื่น) — ค้นชื่อ session ในแอปเอง"}
    url = claude_app_link("continue", {"session": host})
    if not url:
        return 404, {"ok": False, "message": "เครื่องนี้ไม่มีแอป Claude desktop"}
    open_link(url)
    return 200, {"ok": True, "message": "เปิด session นี้ในแอป Claude แล้ว (ถ้า session ถูกเก็บถาวร แอปจะไปหน้ารวม)"}


def _claude_transcript_title(sid: str) -> str:
    if not sid or not re.fullmatch(r"[\w-]+", sid):
        return ""
    try:
        f = next(CLAUDE_PROJECTS.glob(f"*/{sid}.jsonl"), None)
        if not f:
            return ""
        mt = f.stat().st_mtime
        hit = _TITLE_CACHE.get(sid)
        if hit and hit[0] == mt:
            return hit[1]
        with f.open("rb") as fh:
            fh.seek(max(0, mt and f.stat().st_size - 400_000))
            tail = fh.read().decode("utf-8", errors="replace")
        title = ""
        for line in reversed(tail.splitlines()):
            if '"customTitle"' in line or ('"agentName"' in line and not title):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                title = e.get("customTitle") or title or e.get("agentName") or ""
                if e.get("customTitle"):
                    break
        _TITLE_CACHE[sid] = (mt, title)
        return title
    except Exception:
        return ""


_TR_CACHE: dict[str, tuple] = {}


def _tool_desc(name: str, inp: dict) -> str:
    """เครื่องมือที่ Claude เรียกล่าสุด → ข้อความสั้นให้คนอ่าน"""
    name = name.split("__")[-1]
    if name in ("Bash", "PowerShell"):
        d = inp.get("description") or inp.get("command", "")
    elif name in ("Read", "Edit", "Write", "NotebookEdit"):
        d = Path(str(inp.get("file_path", ""))).name
    elif name in ("Grep", "Glob"):
        d = inp.get("pattern", "")
    elif name == "AskUserQuestion":
        d = ((inp.get("questions") or [{}])[0] or {}).get("question", "")
    else:
        d = inp.get("description") or inp.get("title") or ""
    d = " ".join(str(d).split())
    return f"{name}: {d[:100]}" if d else name


def transcript_state(f: Path) -> dict:
    """สถานะล่าสุดของ transcript Claude Code: state = work (กำลังทำ) | ask (รอคุณตอบ/อนุมัติแผน) | end (จบเทิร์นแล้ว)
    doing = เครื่องมือล่าสุดที่เรียก · ago_sec จาก mtime (เขียนทุกครั้งที่มีความเคลื่อนไหว) · cache ตาม mtime+ขนาด"""
    try:
        st = f.stat()
    except OSError:
        return {}
    hit = _TR_CACHE.get(str(f))
    if not hit or hit[0] != (st.st_mtime, st.st_size):
        res = {"state": "work", "doing": ""}
        try:
            with f.open("rb") as fh:
                fh.seek(max(0, st.st_size - 262_144))
                tail = fh.read().decode("utf-8", errors="replace").splitlines()
        except OSError:
            tail = []
        found = False
        for line in reversed(tail):
            if '"assistant"' not in line and '"user"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") not in ("assistant", "user"):
                continue
            m = e.get("message") or {}
            parts = m.get("content") if isinstance(m.get("content"), list) else []
            tools = [p for p in parts if isinstance(p, dict) and p.get("type") == "tool_use"]
            if not found:  # รายการล่าสุด = สถานะตอนนี้
                found = True
                if e["type"] == "assistant":
                    if tools and tools[-1].get("name") in ("AskUserQuestion", "ExitPlanMode"):
                        res["state"] = "ask"
                    elif not tools and m.get("stop_reason") == "end_turn":
                        res["state"] = "end"
            if tools:
                res["doing"] = _tool_desc(tools[-1].get("name", ""), tools[-1].get("input") or {})
                break
        hit = ((st.st_mtime, st.st_size), res)
        _TR_CACHE[str(f)] = hit
    return dict(hit[1], ago_sec=max(0, int(time.time() - st.st_mtime)))


def claude_activity(sid: str) -> dict:
    """ความเคลื่อนไหวของ session Claude Code (รวม subagent ที่ยังทำงาน) — ให้การ์ดบอกว่าไม่ได้ค้าง · หาไม่เจอ = {}"""
    if not sid or not re.fullmatch(r"[\w-]+", sid):
        return {}
    try:
        f = next(CLAUDE_PROJECTS.glob(f"*/{sid}.jsonl"), None)
        if not f:
            return {}
        main = transcript_state(f)
        subs = []
        for sf in (f.parent / sid / "subagents").glob("agent-*.jsonl"):
            s = transcript_state(sf)
            if not s or s["state"] == "end" or s["ago_sec"] > 7200:  # จบแล้ว / เงียบเกิน 2 ชม. = ไม่นับว่าทำงานอยู่
                continue
            meta = read_json(sf.with_suffix(".meta.json"))
            subs.append(dict(s, desc=meta.get("description") or sf.stem))
        subs.sort(key=lambda s: s["ago_sec"])
        return dict(main, subs=subs[:4], ago_sec=min([main["ago_sec"]] + [s["ago_sec"] for s in subs]), main_ago_sec=main["ago_sec"])
    except Exception:
        return {}


# ---------- usage: โทเคน Claude ต่อแผน (อ่าน transcript ของ Claude Code · ไม่โหลดทั้งไฟล์เข้าหน่วยความจำ) ----------
USAGE_DIR = HOME / "usage"  # ผลล่าสุดต่อแผน <stem>.json ให้ UI การ์ดงาน/การ์ดธงแสดง
PRICES_DEFAULT = {  # USD ต่อ 1M token: (in, out, cache_read, cache_write) · ราคา API สาธารณะ ต.ค. 2026 "โดยประมาณ" · ทับได้ใน config.json {"prices": {"<model>": {"in":..,"out":..,"cache_read":..,"cache_write":..}}}
    "claude-fable-5-1": (10, 50, 0.25, 12.5), "claude-fable-5": (10, 50, 1, 12.5), "claude-mythos": (10, 50, 0.25, 12.5),
    "claude-opus-5-5": (4, 20, 0.2, 5), "claude-opus-5": (5, 25, 0.5, 6.25), "claude-opus-4": (5, 25, 0.5, 6.25),
    "claude-sonnet-5-5": (2, 10, 0.2, 2.5), "claude-sonnet-5": (2, 10, 0.2, 2.5), "claude-sonnet-4": (3, 15, 0.3, 3.75),
    "claude-haiku-5-5": (0.1, 0.5, 0.01, 0.125), "claude-haiku-4": (1, 5, 0.1, 1.25),
    "fable": (10, 50, 0.25, 12.5), "opus": (5, 25, 0.5, 6.25), "sonnet": (2, 10, 0.2, 2.5), "haiku": (1, 5, 0.1, 1.25),  # ไม่รู้รุ่นย่อย = ราคาตระกูล
}
USAGE_KEYS = ("in", "out", "cache_read", "cache_write")
USAGE_PHASES = (("plan", "วางแผน"), ("check", "ตรวจ"), ("fix", "รอบแก้"), ("goal", "เป้าหมาย"), ("other", "อื่น ๆ"))
PLAN_STEM_RE = re.compile(r"\bPLAN_[A-Za-z0-9][\w-]*")
FLASH_CMD_RE = re.compile(r"/flash-(plan|check|goal)\b")
FIX_ROUND_RE = re.compile(r"\bT-\d{2,3}R\b")


def claude_project_key(path) -> str:
    """ชื่อโฟลเดอร์ transcript ของ Claude Code สำหรับ cwd นี้ (ทุกตัวที่ไม่ใช่ตัวอักษร/ตัวเลข → '-')"""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def transcript_dirs(paths: list[Path]) -> list[Path]:
    """โฟลเดอร์ transcript ที่ cwd ตรงกับโฟลเดอร์ใดใน paths (รวม worktree ของมัน <key>--claude-worktrees-*)"""
    keys = {claude_project_key(p).lower() for p in paths}
    if not CLAUDE_PROJECTS.is_dir():
        return []
    out = []
    for d in sorted(CLAUDE_PROJECTS.iterdir()):
        n = d.name.lower()
        if d.is_dir() and any(n == k or n.startswith(k + "--claude-worktrees-") for k in keys):
            out.append(d)
    return out


def _blocks_text(content) -> str:
    """ข้อความที่คนเขียน/Claude เขียนใน message (ไม่รวม tool_result ที่เป็นผลลัพธ์ของเครื่องมือ)"""
    if isinstance(content, str):
        return content
    out = []
    for b in content if isinstance(content, list) else []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            out.append(str(b.get("text", "")))
        elif b.get("type") == "tool_use":
            inp = b.get("input") or {}
            if b.get("name") == "Skill":
                out.append("/" + str(inp.get("skill", "")) + " " + str(inp.get("args", "")))
            else:
                out.append(" ".join(str(v) for v in inp.values() if isinstance(v, str))[:2000])
    return "\n".join(out)


def scan_transcript(f: Path) -> dict:
    """รวม usage ของ transcript 1 ไฟล์ (อ่านทีละบรรทัด) → models: {model: {in,out,cache_read,cache_write,calls}} · flags: plan/check/goal/fix · stems: ชื่อแผนที่ถูกอ้าง
    Claude Code เขียน assistant หลายบรรทัดต่อ 1 คำตอบ (block ละบรรทัด usage เท่ากัน) → นับ message.id ซ้ำครั้งเดียว"""
    res = {"models": {}, "flags": set(), "stems": set(), "first": "", "last": "", "calls": 0}
    seen = set()
    try:
        fh = f.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return res
    with fh:
        for line in fh:
            if '"type":"assistant"' in line:  # key type อยู่หลัง message (ท้ายบรรทัด) → ดูทั้งบรรทัดแล้วยืนยันหลัง parse
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") != "assistant":
                    continue
                m = e.get("message") or {}
                u = m.get("usage") or {}
                mid = m.get("id") or e.get("requestId") or e.get("uuid")
                if u and mid not in seen:
                    seen.add(mid)
                    row = res["models"].setdefault(m.get("model") or "?", dict.fromkeys(USAGE_KEYS, 0) | {"calls": 0})
                    row["in"] += int(u.get("input_tokens") or 0)
                    row["out"] += int(u.get("output_tokens") or 0)
                    row["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
                    row["cache_write"] += int(u.get("cache_creation_input_tokens") or 0)
                    row["calls"] += 1
                    res["calls"] += 1
                text = _blocks_text(m.get("content"))
            elif '"type":"user"' in line:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("type") != "user":
                    continue
                text = _blocks_text((e.get("message") or {}).get("content"))
            else:
                continue
            ts = e.get("timestamp") or ""
            if ts:
                res["first"] = min(res["first"] or ts, ts)
                res["last"] = max(res["last"], ts)
            for c in FLASH_CMD_RE.findall(text):
                res["flags"].add(c)
            if FIX_ROUND_RE.search(text):
                res["flags"].add("fix")
            res["stems"].update(PLAN_STEM_RE.findall(text))
    return res


def _merge_usage(dst: dict, src: dict) -> None:
    for model, u in src["models"].items():
        row = dst["models"].setdefault(model, dict.fromkeys(USAGE_KEYS, 0) | {"calls": 0})
        for k in row:
            row[k] += u[k]
    dst["flags"] |= src["flags"]
    dst["stems"] |= src["stems"]
    dst["calls"] += src["calls"]
    if src["first"]:
        dst["first"] = min(dst["first"] or src["first"], src["first"])
        dst["last"] = max(dst["last"], src["last"])


def scan_sessions(dirs: list[Path], since_days: float) -> list[dict]:
    """ทุก session (transcript หลัก + subagent ของมัน) ในโฟลเดอร์ที่ให้ ที่มีความเคลื่อนไหวใน since_days วันล่าสุด"""
    cutoff = time.time() - since_days * 86400
    out = []
    for d in dirs:
        for f in sorted(d.glob("*.jsonl")):
            try:
                if f.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
            s = scan_transcript(f)
            for sf in sorted((d / f.stem / "subagents").glob("agent-*.jsonl")):
                _merge_usage(s, scan_transcript(sf))
            if not s["calls"]:
                continue
            s.update(id=f.stem, dir=d.name, title=claude_session_title(f.stem))
            out.append(s)
    out.sort(key=lambda s: s["first"])
    return out


def session_phase(flags: set) -> str:
    """ขั้นของ session จากคำสั่งที่เรียก: /flash-check (ไม่มี /flash-plan) = ตรวจ · /flash-plan + T-xxR = รอบแก้ · /flash-plan = วางแผน · /flash-goal = เป้าหมาย · T-xxR อย่างเดียว = รอบแก้"""
    if "check" in flags and "plan" not in flags:
        return "check"
    if "plan" in flags:
        return "fix" if "fix" in flags else "plan"
    if "goal" in flags:
        return "goal"
    if "fix" in flags:
        return "fix"
    return "check" if "check" in flags else "other"


def price_table() -> dict:
    t = {k: dict(zip(USAGE_KEYS, v)) for k, v in PRICES_DEFAULT.items()}
    for k, v in (read_json(CONFIG).get("prices") or {}).items():
        if isinstance(v, (list, tuple)):  # รูปย่อ [in, out, cache_read, cache_write]
            v = dict(zip(USAGE_KEYS, v))
        if isinstance(v, dict):
            try:
                t[k] = {**t.get(k, dict.fromkeys(USAGE_KEYS, 0.0)), **{x: float(v[x]) for x in USAGE_KEYS if x in v}}
            except (TypeError, ValueError):
                pass
    return t


def price_for(model: str, table: dict) -> dict | None:
    """ราคาของโมเดล: ตรงตัว/ขึ้นต้น (ยาวสุดชนะ) → ชื่อตระกูลอยู่ในชื่อโมเดล → ไม่รู้ = None"""
    m = (model or "").lower()
    hits = [k for k in table if m.startswith(k.lower())] or [k for k in table if k.lower() in m]
    return table[max(hits, key=len)] if hits else None


def usage_cost(u: dict, model: str, table: dict) -> float | None:
    p = price_for(model, table)
    return None if p is None else sum(u[k] * p[k] for k in USAGE_KEYS) / 1e6


def usage_summary(stem: str, sessions: list[dict], project: str, since_days: float) -> dict:
    """รวม token/USD ของ session ที่อ้างแผน stem แยกตามขั้นและโมเดล (เปอร์เซ็นต์คิดจาก USD · ไม่รู้ราคา = จาก token)"""
    table = price_table()
    rows, by_phase, by_model = [], {}, {}
    total = dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "tokens": 0}
    unknown = set()
    for s in sessions:
        if stem.lower() not in {x.lower() for x in s["stems"]}:
            continue
        ph = session_phase(s["flags"])
        r = dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "id": s["id"], "phase": ph, "flags": sorted(s["flags"]), "title": s["title"],
                                             "first": s["first"], "last": s["last"], "calls": s["calls"], "dir": s["dir"],
                                             "models": sorted(s["models"])}
        for model, u in s["models"].items():
            c = usage_cost(u, model, table)
            if c is None:
                unknown.add(model)
            bm = by_model.setdefault(model, dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "sessions": 0, "calls": 0})
            bm["sessions"] += 1
            bm["calls"] += u["calls"]
            for k in USAGE_KEYS:
                r[k] += u[k]
                bm[k] += u[k]
            r["usd"] += c or 0
            bm["usd"] += c or 0
        r["tokens"] = sum(r[k] for k in USAGE_KEYS)
        bp = by_phase.setdefault(ph, dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "sessions": 0, "tokens": 0})
        bp["sessions"] += 1
        for k in USAGE_KEYS + ("usd", "tokens"):
            bp[k] += r[k]
            total[k] += r[k]
        rows.append(r)
    base = total["usd"] if total["usd"] > 0 else total["tokens"]
    for ph, bp in by_phase.items():
        bp["pct"] = round(100 * (bp["usd"] if total["usd"] > 0 else bp["tokens"]) / base) if base else 0
    return {"stem": stem, "project": project, "at": now(), "since_days": since_days, "sessions": len(rows),
            "total": total, "by_phase": by_phase, "by_model": by_model, "unknown_price": sorted(unknown),
            "pct_by": "usd" if total["usd"] > 0 else "tokens", "session_list": rows}


def fmt_tok(n) -> str:
    n = int(n or 0)
    return f"{n / 1e6:,.1f}M" if n >= 1e6 else f"{n / 1e3:,.0f}k" if n >= 1000 else f"{n:,}"


def usage_brief(stem: str) -> dict:
    """บรรทัดสั้นสำหรับ UI จาก usage/<stem>.json (ไม่มี = {})"""
    u = read_json(USAGE_DIR / f"{stem}.json")
    if not u.get("sessions"):
        return {}
    ph = u.get("by_phase") or {}
    return {"tokens": u["total"]["tokens"], "usd": round(u["total"]["usd"], 2), "sessions": u["sessions"], "at": u.get("at", ""),
            "pct": {k: ph[k]["pct"] for k, _ in USAGE_PHASES if k in ph}, "pct_by": u.get("pct_by", "usd")}


def usage_brief_topic(topic: str) -> dict:
    """รวมทุกแผนของเรื่องเดียวกัน (GOAL_<เรื่อง> ↔ PLAN_FLASH_<เรื่อง>_R<n>) สำหรับการ์ดธง"""
    out, pct, n = {}, {}, 0
    for f in USAGE_DIR.glob("*.json") if USAGE_DIR.is_dir() else []:
        if goal_topic(f.stem) != topic:
            continue
        b = usage_brief(f.stem)
        if not b:
            continue
        n += 1
        out = {"tokens": out.get("tokens", 0) + b["tokens"], "usd": round(out.get("usd", 0) + b["usd"], 2),
               "sessions": out.get("sessions", 0) + b["sessions"], "at": max(out.get("at", ""), b["at"]), "pct_by": b["pct_by"]}
        for k, v in b["pct"].items():
            pct[k] = pct.get(k, 0) + v
    if n:
        out["pct"] = {k: round(v / n) for k, v in pct.items()}
        out["plans"] = n
    return out


def cmd_usage(a) -> int:
    """`flashq usage <แผน|โปรเจกต์> [--since วัน]`: สแกน transcript ของ Claude Code ที่ cwd ตรงกับโปรเจกต์ (รวม worktree)
    → session ที่อ้างชื่อแผน รวม token แยกขั้น/โมเดล + USD โดยประมาณ · บันทึก ~/.flashq/usage/<stem>.json ให้ UI"""
    if a.flash:
        return cmd_usage_flash(a)
    if not a.target:
        print("ต้องระบุไฟล์แผน PLAN_*.md หรือโฟลเดอร์โปรเจกต์ (หรือใช้ --flash เพื่อดู token ฝั่ง Flash)")
        return 1
    target = Path(a.target)
    is_plan = target.suffix.lower() == ".md" or target.name.upper().startswith("PLAN_")
    if is_plan:
        plan = target if target.is_absolute() else Path.cwd() / target
        start = plan.parent if plan.parent.is_dir() else Path.cwd()
        stems = [plan.stem]
    else:
        start = target if target.is_absolute() else Path.cwd() / target
        if not start.is_dir():
            print(f"ไม่พบโฟลเดอร์/ไฟล์แผน '{a.target}' (ให้ path ไฟล์ PLAN_*.md หรือโฟลเดอร์โปรเจกต์)")
            return 1
        stems = []
    if a.project:
        root = Path(a.project).resolve()
    else:
        root, is_git = project_root(start)
        if not is_git and start.resolve().is_relative_to(Path.cwd().resolve()):  # ไม่ใช่ git → รากคือโฟลเดอร์ที่สั่ง (ถ้าแผนอยู่ใต้มัน)
            root = Path.cwd().resolve()
    anc = [start.resolve()] + [p for p in start.resolve().parents]  # cwd ของ Claude อาจลึกกว่า/ตื้นกว่ารากโปรเจกต์ → รับทุกชั้นระหว่างแผนกับราก
    try:
        anc = anc[:anc.index(root.resolve()) + 1]
    except ValueError:
        anc = [start.resolve(), root.resolve()]
    dirs = transcript_dirs(anc)
    if not dirs:
        print(f"ไม่พบโฟลเดอร์ transcript ของ {root} ใน {CLAUDE_PROJECTS} (Claude Code ยังไม่เคยเปิดโปรเจกต์นี้?)")
        print(f"USAGE={stems[0] if stems else root.name} claude_in=0 claude_out=0 cache_read=0 sessions=0")
        return 1
    sessions = scan_sessions(dirs, a.since)
    if not stems:  # โปรเจกต์: ทุกแผน PLAN_* ที่ถูกพูดถึงใน session ช่วงนี้ (ตัวพิมพ์ตามที่เจอครั้งแรก)
        names = {}
        for x in sessions:
            for s in sorted(x["stems"]):
                names.setdefault(s.lower(), s)
        stems = [names[k] for k in sorted(names)]
    print(f"transcript {len(dirs)} โฟลเดอร์ · {len(sessions)} session ใน {a.since:g} วันล่าสุด · โปรเจกต์ {root}")
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    rc, grand, seen_sessions, ph_th = 0, dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0}, set(), dict(USAGE_PHASES)
    for stem in stems:
        u = usage_summary(stem, sessions, str(root), a.since)
        if not u["sessions"]:
            if is_plan:
                print(f"ไม่พบ session ของ Claude ที่อ้างถึง {stem} ใน {a.since:g} วันล่าสุด (ลอง --since มากขึ้น หรือ --project <โฟลเดอร์>)")
                print(f"USAGE={stem} claude_in=0 claude_out=0 cache_read=0 sessions=0")
                rc = 1
            continue
        write_json(USAGE_DIR / f"{stem}.json", u)
        t = u["total"]
        print(f"\n== {stem} · {u['sessions']} session · Claude ใช้ ~{fmt_tok(t['tokens'])} token (~${t['usd']:,.2f} โดยประมาณ)")
        print(f"{'ขั้น':<10}{'session':>8}{'in ใหม่':>10}{'cache เขียน':>12}{'cache อ่าน':>12}{'out':>9}{'~USD':>9}{'%':>5}")
        for k, th in USAGE_PHASES:
            bp = u["by_phase"].get(k)
            if bp:
                print(f"{th:<10}{bp['sessions']:>8}{fmt_tok(bp['in']):>10}{fmt_tok(bp['cache_write']):>12}{fmt_tok(bp['cache_read']):>12}{fmt_tok(bp['out']):>9}{bp['usd']:>9.2f}{bp['pct']:>4}%")
        print(f"{'รวม':<10}{u['sessions']:>8}{fmt_tok(t['in']):>10}{fmt_tok(t['cache_write']):>12}{fmt_tok(t['cache_read']):>12}{fmt_tok(t['out']):>9}{t['usd']:>9.2f}")
        print("โมเดล: " + " · ".join(f"{m} {bm['sessions']} session {bm['calls']} ครั้ง ~${bm['usd']:,.2f}" for m, bm in sorted(u["by_model"].items())))
        if u["unknown_price"]:
            print(f"  (ไม่รู้ราคาของ {', '.join(u['unknown_price'])} → ตั้งใน {CONFIG} ช่อง prices)")
        for r in u["session_list"]:
            print(f"  {r['id'][:8]} {ph_th[r['phase']]:<8} {r['first'][:16].replace('T', ' ')} {fmt_tok(r['tokens']):>7} ~${r['usd']:,.2f} [{' '.join(r['flags']) or '-'}] {r['title'][:50]}")
            if r["id"] not in seen_sessions:
                seen_sessions.add(r["id"])
                for k in USAGE_KEYS + ("usd",):
                    grand[k] += r[k]
        print(f"USAGE={stem} claude_in={t['in'] + t['cache_write']} claude_out={t['out']} cache_read={t['cache_read']} sessions={u['sessions']} usd={t['usd']:.2f}")
    if not is_plan:
        if not stems:
            print("ไม่พบ session ที่พูดถึงแผน PLAN_* ในช่วงนี้")
            rc = 1
        print(f"\nรวมทั้งโปรเจกต์ (session ไม่ซ้ำ {len(seen_sessions)}): in ใหม่ {fmt_tok(grand['in'] + grand['cache_write'])} · cache อ่าน {fmt_tok(grand['cache_read'])} · out {fmt_tok(grand['out'])} · ~${grand['usd']:,.2f}")
    print(f"(ราคาโดยประมาณจากตารางในตัว · ทับได้ที่ {CONFIG} ช่อง prices · บันทึกผลไว้ที่ {USAGE_DIR})")
    return rc


# ---------- usage ฝั่ง Flash: token/USD ที่ opencode รายงานของงานที่รันผ่าน flashq + ประมาณการเทียบ Claude ----------
OC_DB = Path(os.environ.get("FLASHQ_OPENCODE_DB") or (Path.home() / ".local" / "share" / "opencode" / "opencode.db"))  # session ลูก (subagent) ไม่อยู่ใน log หลัก → อ่านจากฐานข้อมูลของ opencode (อ่านอย่างเดียว)
FLASH_COMPARE_DEFAULT = ("claude-sonnet-5-5", "claude-opus-5-5")  # เทียบกับรุ่นเหล่านี้ (ขอบล่าง/ขอบบน) · ทับได้ใน config.json {"flash_compare": ["claude-...", ...]}
_FLASH_SUM_CACHE: dict = {}  # days → (เวลา, ผลสรุป) ของ /api/flash_usage
_FLASH_LOG_CACHE: dict = {}  # path → ((mtime_ns, size), ผลสแกน) — log ของรอบที่จบแล้วไม่เปลี่ยน จึงไม่ต้องอ่านซ้ำทุกครั้งที่หน้าเว็บขอ


def scan_flash_log(f: Path) -> dict:
    """log jsonl ของ opencode 1 รอบ → รวม step_finish: in(input) · out(output+reasoning) · cache_read · cache_write · usd(ตามที่ opencode คิดจากราคาจริง) · steps · sessions"""
    zero = dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "steps": 0, "sessions": []}
    try:
        st = f.stat()
        sig = (st.st_mtime_ns, st.st_size)
        hit = _FLASH_LOG_CACHE.get(str(f))
        if hit and hit[0] == sig:
            return hit[1]
        fh = f.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return zero
    res, sess = dict(zero), set()
    with fh:
        for line in fh:
            if '"step_finish"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            p = e.get("part") or {}
            t = p.get("tokens")
            if e.get("type") != "step_finish" or not isinstance(t, dict):
                continue
            c = t.get("cache") or {}
            res["in"] += int(t.get("input") or 0)
            res["out"] += int(t.get("output") or 0) + int(t.get("reasoning") or 0)  # Claude นับ reasoning รวมใน output
            res["cache_read"] += int(c.get("read") or 0)
            res["cache_write"] += int(c.get("write") or 0)
            res["usd"] += float(p.get("cost") or 0)
            res["steps"] += 1
            if e.get("sessionID"):
                sess.add(e["sessionID"])
    res["sessions"] = sorted(sess)
    _FLASH_LOG_CACHE[str(f)] = (sig, res)
    return res


def oc_open_db():
    """เปิด opencode.db แบบอ่านอย่างเดียว · ไม่มี/เปิดไม่ได้ = None (สรุปจาก log หลักอย่างเดียว)"""
    try:
        if OC_DB.is_file():
            return sqlite3.connect(f"file:{OC_DB.as_posix()}?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        pass
    return None


def oc_child_usage(con, session_ids: list) -> dict:
    """token/USD ของ subagent = session ลูกทุกชั้นของ session_ids (assistant message ใน opencode.db) · อ่านไม่ได้ = ศูนย์"""
    res = dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "steps": 0, "sessions": 0}
    if con is None or not session_ids:
        return res
    try:
        seen, frontier = set(session_ids), list(session_ids)
        kids: list = []
        while frontier:
            nxt = []
            for i in range(0, len(frontier), 400):
                part = frontier[i:i + 400]
                for (sid,) in con.execute(f"select id from session where parent_id in ({','.join('?' * len(part))})", part):
                    if sid not in seen:
                        seen.add(sid)
                        nxt.append(sid)
            kids += nxt
            frontier = nxt
        res["sessions"] = len(kids)
        for i in range(0, len(kids), 400):
            part = kids[i:i + 400]
            for (d,) in con.execute(f"select data from message where session_id in ({','.join('?' * len(part))})", part):
                try:
                    m = json.loads(d)
                except ValueError:
                    continue
                t = m.get("tokens")
                if m.get("role") != "assistant" or not isinstance(t, dict):
                    continue
                c = t.get("cache") or {}
                res["in"] += int(t.get("input") or 0)
                res["out"] += int(t.get("output") or 0) + int(t.get("reasoning") or 0)
                res["cache_read"] += int(c.get("read") or 0)
                res["cache_write"] += int(c.get("write") or 0)
                res["usd"] += float(m.get("cost") or 0)
                res["steps"] += 1
    except sqlite3.Error:
        return dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "steps": 0, "sessions": 0}
    return res


def claude_overhead_usd(since_days: float, project: str) -> dict:
    """USD ของ Claude ที่ยังใช้วางแผน/ตรวจ (จากผล `flashq usage <แผน>` ที่เคยรันไว้ · session ซ้ำข้ามแผนนับครั้งเดียว) — ไม่เคยรัน = 0"""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - since_days * 86400))
    seen, usd = set(), 0.0
    for f in USAGE_DIR.glob("*.json") if USAGE_DIR.is_dir() else []:
        u = read_json(f)
        if project and os.path.normcase(str(u.get("project", ""))) != os.path.normcase(project):
            continue
        for r in u.get("session_list") or []:
            if r.get("id") in seen or (r.get("first") or "") < cutoff:
                continue
            seen.add(r.get("id"))
            usd += float(r.get("usd") or 0)
    return {"usd": round(usd, 4), "sessions": len(seen)}


def job_flash_usage(j: dict, con) -> tuple | None:
    """token + USD ของงาน 1 งาน (log หลัก + subagent) → (row, kid) · ไม่มีข้อมูล token เลย = None"""
    main = dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0, "steps": 0}
    sids: set = set()
    for lp in j.get("logs") or []:
        r = scan_flash_log(Path(lp))
        for k in USAGE_KEYS + ("usd", "steps"):
            main[k] += r[k]
        sids.update(r["sessions"])
    if j.get("session"):
        sids.add(j["session"])
    kid = oc_child_usage(con, sorted(sids))
    if not main["steps"] and not kid["steps"]:
        return None
    row = {k: main[k] + kid[k] for k in USAGE_KEYS + ("usd", "steps")}
    row["tokens"] = sum(row[k] for k in USAGE_KEYS)
    return row, kid


def flash_compare_names() -> list:
    names = read_json(CONFIG).get("flash_compare") or list(FLASH_COMPARE_DEFAULT)
    return [str(n) for n in names] if isinstance(names, list) else []


_JOB_FLASH_CACHE: dict = {}  # job id → ผลของงานที่จบแล้ว (log ไม่เปลี่ยนอีก จึงไม่ต้องเปิด opencode.db ซ้ำทุกรอบ refresh)


def job_flash_brief(j: dict, con, table: dict) -> dict | None:
    """สรุปสั้นของงานที่จบแล้วสำหรับตาราง "เพิ่งจบ": token · ค่าจ่ายจริงที่ opencode คิด · ถ้า Claude ทำ token เท่ากันจะเสียเท่าไร (ต่อรุ่นใน flash_compare)"""
    key = (j.get("id"), j.get("finished"), len(j.get("logs") or []))
    hit = _JOB_FLASH_CACHE.get(key[0])
    if hit and hit[0] == key:
        return hit[1]
    got = job_flash_usage(j, con)
    brief = None
    if got:
        row, kid = got
        brief = {"tokens": row["tokens"], "usd": round(row["usd"], 4), "sub_tokens": sum(kid[k] for k in USAGE_KEYS),
                 "compare": [{"model": n, "usd": round(c, 2)} for n in flash_compare_names()
                             if (c := usage_cost(row, n, table)) is not None]}
    if len(_JOB_FLASH_CACHE) > 600:
        _JOB_FLASH_CACHE.clear()
    _JOB_FLASH_CACHE[key[0]] = (key, brief)
    return brief


def flash_usage_summary(since_days: float = 30, project: str = "") -> dict:
    """token + USD ของ Flash (งานที่รันผ่าน flashq) ใน since_days วันล่าสุด แยกวัน/โปรเจกต์/ชนิดงาน/โมเดล
    + ประมาณการว่าถ้า Claude ทำ token เท่ากันจะเสียเท่าไร (compare) และประหยัดไปเท่าไร (หักค่า Claude ที่ยังใช้วางแผน/ตรวจ)"""
    cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - since_days * 86400))
    want = os.path.normcase(project) if project else ""
    con = oc_open_db()
    total = dict.fromkeys(USAGE_KEYS, 0) | {"usd": 0.0}
    sub = {"sessions": 0, "usd": 0.0, "tokens": 0}
    groups = {"by_day": {}, "by_project": {}, "by_kind": {}, "by_model": {}}
    n_jobs = n_nodata = 0
    try:
        for j in jobs():
            if (j.get("created") or "") < cutoff or (want and os.path.normcase(j.get("project", "")) != want):
                continue
            got = job_flash_usage(j, con)
            if got is None:
                n_nodata += 1
                continue
            row, kid = got
            n_jobs += 1
            for k in USAGE_KEYS + ("usd",):
                total[k] += row[k]
            sub["sessions"] += kid["sessions"]
            sub["usd"] += kid["usd"]
            sub["tokens"] += sum(kid[k] for k in USAGE_KEYS)
            for gk, name in (("by_day", (j.get("created") or "")[:10]), ("by_project", Path(j.get("project", "")).name or "-"),
                             ("by_kind", j.get("kind") or "work"), ("by_model", j.get("model") or "?")):
                g = groups[gk].setdefault(name, {"name": name, "jobs": 0, "tokens": 0, "usd": 0.0})
                g["jobs"] += 1
                g["tokens"] += row["tokens"]
                g["usd"] += row["usd"]
    finally:
        if con is not None:
            con.close()
    total["tokens"] = sum(total[k] for k in USAGE_KEYS)
    over = claude_overhead_usd(since_days, project)
    table = price_table()
    compare = []
    for name in flash_compare_names():
        c = usage_cost(total, name, table)
        if c is None:
            continue
        compare.append({"model": name, "equiv_usd": round(c, 2), "saved_gross": round(c - total["usd"], 2),
                        "saved_net": round(c - total["usd"] - over["usd"], 2),
                        "pct_net": round(100 * (c - total["usd"] - over["usd"]) / c) if c > 0 else 0})
    def rows(gk: str, key=lambda g: -g["usd"]) -> list:
        return [dict(g, usd=round(g["usd"], 4)) for g in sorted(groups[gk].values(), key=key)]
    return {"at": now(), "since_days": since_days, "project": project, "jobs": n_jobs, "jobs_no_data": n_nodata,
            "total": dict(total, usd=round(total["usd"], 4)), "subagent": dict(sub, usd=round(sub["usd"], 4), included=con is not None),
            "claude_overhead": over, "compare": compare,
            "by_day": rows("by_day", key=lambda g: g["name"])[-14:], "by_project": rows("by_project"),
            "by_kind": rows("by_kind"), "by_model": rows("by_model")}


def cmd_usage_flash(a) -> int:
    """`flashq usage --flash [โปรเจกต์] [--since วัน]`: token/USD ของ Flash จาก log ของงานที่รันผ่าน flashq + ประมาณการประหยัดเทียบ Claude"""
    proj = ""
    if a.target or a.project:
        p = Path(a.project or a.target)
        if not p.is_dir():
            print(f"ไม่พบโฟลเดอร์โปรเจกต์ '{p}'")
            return 1
        proj = str(p.resolve())
    s = flash_usage_summary(a.since, proj)
    t, sb = s["total"], s["subagent"]
    print(f"Flash ใน {a.since:g} วันล่าสุด{(' · โปรเจกต์ ' + proj) if proj else ''}: {s['jobs']} งาน"
          + (f" (อีก {s['jobs_no_data']} งานไม่มีข้อมูล token)" if s["jobs_no_data"] else ""))
    print(f"token ~{fmt_tok(t['tokens'])}: in ใหม่ {fmt_tok(t['in'])} · cache เขียน {fmt_tok(t['cache_write'])} · cache อ่าน {fmt_tok(t['cache_read'])} · out {fmt_tok(t['out'])}"
          f" · ค่าใช้จ่ายจริงของ Flash ${t['usd']:,.2f}")
    print(f"  ในนั้นเป็น subagent {sb['sessions']} session ~{fmt_tok(sb['tokens'])} token ${sb['usd']:,.2f}" if sb["included"]
          else f"  (ไม่พบ {OC_DB} → ยังไม่รวม token ของ subagent ตัวเลขจึงต่ำกว่าจริง)")
    for title, key in (("วัน", "by_day"), ("โปรเจกต์", "by_project"), ("ชนิดงาน", "by_kind"), ("โมเดล", "by_model")):
        if s[key]:
            print(f"{title}: " + " · ".join(f"{g['name']} {g['jobs']} งาน {fmt_tok(g['tokens'])} ${g['usd']:,.2f}" for g in s[key]))
    ov = s["claude_overhead"]
    print(f"Claude ที่ยังใช้วางแผน/ตรวจ (จากผล flashq usage ที่เคยรัน {ov['sessions']} session): ~${ov['usd']:,.2f}")
    for c in s["compare"]:
        print(f"  ถ้า {c['model']} ทำเอง ~${c['equiv_usd']:,.2f} → ประหยัด ~${c['saved_net']:,.2f} ({c['pct_net']}%) [ก่อนหักค่า Claude ที่ยังใช้ ~${c['saved_gross']:,.2f}]")
    print("(ประมาณการ: สมมติ Claude ใช้ token เท่ากัน ซึ่งปกติ Claude ใช้น้อยกว่า · ราคาจากตารางในตัว ทับได้ที่ config.json ช่อง prices / flash_compare)")
    best = s["compare"][0] if s["compare"] else {}
    print(f"USAGE_FLASH jobs={s['jobs']} tokens={t['tokens']} usd={t['usd']:.2f} claude_equiv={best.get('equiv_usd', 0):.2f} saved_net={best.get('saved_net', 0):.2f}")
    return 0 if s["jobs"] else 1


def goal_next_plan(gl: dict, n: int) -> dict:
    """แผนรอบ n (PLAN_FLASH_<เรื่อง>_R<n>.md) เขียนเสร็จหรือยัง — ดูโฟลเดอร์แผนของโปรเจกต์ + โฟลเดอร์ของ session ที่ทำ (worktree)"""
    proj = Path(gl.get("project", ""))
    rel_dir = Path(gl.get("goal", "")).parent
    dirs = []
    for base in (proj, Path((gl.get("owner") or {}).get("cwd") or proj)):
        for d in (base / rel_dir, base / (project_cfg(proj).get("plan_dir") or "docs/plans")):
            if d.is_dir() and all(os.path.normcase(str(d.resolve())) != os.path.normcase(str(x.resolve())) for x in dirs):
                dirs.append(d)
    topic = goal_topic(gl.get("stem", ""))
    for d in dirs:
        for p in d.glob("PLAN_FLASH_*.md"):
            m = re.search(r"_R(\d+)\.md$", p.name, re.I)
            if m and int(m.group(1)) == n and goal_topic(p.name) == topic:
                return {"path": str(p), "ago_sec": max(0, int(time.time() - p.stat().st_mtime))}
    return {}


def goal_phase(gl: dict, verdict: str, last: dict | None, busy: dict, runs: list[dict], queued: list[dict],
               last_job: dict, act: dict, unverified: list[int] | None = None) -> dict:
    """ขั้นย่อยตอนนี้ของเป้าหมาย: step = flag · plan · flash · review · verify · result + ข้อความ + เคลื่อนไหวล่าสุดกี่วินาที
    notes = สิ่งที่ session/subagent กำลังทำ (ให้รู้ว่าไม่ได้ค้าง) · warn = นิ่งนาน/รอคุณ
    round = รอบที่กำลังทำ (งานที่รัน/เข้าคิวอยู่ชนะ — เลขรอบตามชื่อแผน _R<n> อาจนำจำนวนรอบที่ verify แล้ว)
    unverified = รอบที่ Flash ทำเสร็จหลัง verify ล่าสุดแต่ยังไม่มีใคร verify → เตือน (ตัวเลขรอบ/ผ่าน/G-xx ยังเป็นของก่อนรอบนั้น)"""
    n_next = len(gl.get("rounds") or []) + 1
    notes = []
    skipped = [n for n in unverified or [] if n not in {(r.get("goal") or {}).get("round") for r in runs + queued}]
    if skipped and (runs or queued):  # ไม่มีงานรัน/คิว = ขั้น "รอตรวจ" บอกอยู่แล้ว
        notes.append({"t": f"⚠ รอบ {', '.join(map(str, skipped))} Flash ทำเสร็จแล้วแต่ยังไม่ได้ goal verify — "
                           "ตัวเลขรอบ/ผ่าน และผล G-xx บนการ์ดจึงยังเป็นของก่อนรอบนั้น", "warn": True})
    if act:
        st = act.get("state")
        main = ("❓ รอคุณตอบคำถาม/อนุมัติใน session นั้น" if st == "ask"
                else "💤 จบเทิร์นแล้ว" + (" — รอ subagent ทำงานเบื้องหลัง" if act.get("subs") else " (รอคุณสั่งต่อ?)") if st == "end"
                else "⚙️ กำลังทำงาน")
        notes.append({"t": f"🧭 session: {main}" + (f" · ล่าสุด {act['doing']}" if act.get("doing") and st != "end" else ""),
                      "ago_sec": act.get("main_ago_sec"), "warn": st == "ask"})
        for s in act.get("subs") or []:
            notes.append({"t": f"🤖 subagent «{s['desc']}» กำลังทำ" + (f" · {s['doing']}" if s.get("doing") else ""), "ago_sec": s["ago_sec"]})
    sess_ago = act.get("ago_sec") if act else None
    sess_warn = bool(act) and (act.get("state") == "ask" or (act.get("state") == "end" and not act.get("subs")) or (sess_ago or 0) > 1800)
    fresh = last_job and last_job.get("finished", "") > ((last or {}).get("at") or gl.get("started", ""))

    def ph(step, label, ago=None, what="เคลื่อนไหวล่าสุด", warn=False, rnd=None, **kw):
        return dict(step=step, label=label, ago_sec=ago, ago_what=what, warn=warn, notes=notes, round=rnd or n_next, **kw)

    if verdict == "CANCELLED":
        return ph("result", "🚫 ยกเลิกโดย user — ไม่วนต่อ" + (" · งาน Flash ของธงนี้ยังรัน/รอคิวอยู่" if runs or queued else ""),
                  _secs((gl.get("cancelled") or {}).get("at", "")), "ยกเลิกมา", bool(runs or queued))
    if busy.get("what") == "verify":
        return ph("verify", "🔍 กำลังรันเกณฑ์ตรวจทุกข้อ (goal verify)", _secs(busy.get("at", "")), "เริ่ม")
    if busy.get("what") == "claude":
        return ph("plan", "🤖 Claude กำลังทำต่อในหน้าต่าง terminal ที่เปิดไว้", _secs(busy.get("at", "")), "เริ่ม")
    if runs:
        idle = min(r.get("log_idle_sec") or 0 for r in runs)
        return ph("flash", f"🧑‍💻 Flash กำลังทำรอบ {', '.join(str(r['goal']['round']) for r in runs)} · ช่อง {', '.join(str(r.get('slot') or '?') for r in runs)}",
                  idle, "log เคลื่อนไหวล่าสุด", idle > 1200, max(r["goal"]["round"] for r in runs), job=runs[0]["id"])
    if queued:
        q = queued[0]
        why = q.get("wait_reason") or ""
        return ph("flash", f"⏳ แผนรอบ {q['goal']['round']} อยู่ในคิว ลำดับ {q.get('position', '?')}" + (f" · {why}" if why else ""),
                  q.get("wait_sec"), "เข้าคิวมา", rnd=q["goal"]["round"])
    if fresh and verdict != "DONE" and last_job.get("state") == "cancelled":  # งานรอบนั้นถูกหยุด ไม่ใช่ทำเสร็จ
        return ph("plan", f"🚫 งาน Flash รอบ {last_job['round']} ถูกยกเลิกก่อนเสร็จ — ต้องส่งแผนรอบนี้เข้าคิวใหม่ (ไม่ต้อง goal verify)",
                  last_job.get("ago_sec"), "ยกเลิกมา", True, rnd=last_job["round"])
    if fresh and verdict != "DONE":
        return ph("review", f"📥 Flash ทำรอบ {last_job['round']} เสร็จแล้ว — รอ Claude ตรวจ (goal verify)",
                  sess_ago if act else last_job.get("ago_sec"), "เคลื่อนไหวล่าสุด" if act else "Flash เสร็จมา", sess_warn or (not act and (last_job.get("ago_sec") or 0) > 1800))
    age = _secs(gl.get("updated", "")) or 0
    if verdict == "DONE":
        return ph("result", "✅ ผ่านครบทุกเกณฑ์", age, "เมื่อ")
    if verdict == "DONE_NEEDS_USER":
        return ph("result", "👀 เครื่องตรวจผ่านหมด — ถึงตาคุณตรวจข้อ 👤", age, "รอมา", age > 1800)
    if verdict == "STOP":
        return ph("result", "⛔ ติดเบรก — รอคุณตัดสินใจ", age, "รอมา", True)
    plan = goal_next_plan(gl, n_next)
    if plan:
        return ph("plan", f"📤 แผนรอบ {n_next} เขียนเสร็จแล้ว ({Path(plan['path']).name}) — รอ Claude ส่งเข้าคิว",
                  sess_ago if act else plan["ago_sec"], "เคลื่อนไหวล่าสุด" if act else "แผนเสร็จมา", sess_warn, plan=plan["path"])
    if not act:
        return ph("plan", f"✍️ ขั้นเขียนแผนรอบ {n_next} — หา session ที่ทำไม่เจอ (ปิดไปแล้ว/ไม่ใช่ Claude Code)", age, "นิ่งมา", age > 1800)
    return ph("plan", f"✍️ Claude กำลังเขียนแผนรอบ {n_next}" if not sess_warn else f"✍️ ขั้นเขียนแผนรอบ {n_next} — session นั้นไม่ได้ทำงานอยู่",
              sess_ago, "เคลื่อนไหวล่าสุด", sess_warn)


def goal_owner() -> dict:
    """session ที่สั่งคำสั่ง goal (Claude Code ใส่ CLAUDE_CODE_SESSION_ID ให้ทุกคำสั่ง shell) → ให้ UI บอกว่าต้องกลับไปที่ไหน"""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not sid:
        return {}
    return {"session": sid, "host": os.environ.get("CLAUDE_CODE_HOST_SESSION_ID", ""), "cwd": os.getcwd(),
            "app": os.environ.get("CLAUDE_CODE_ENTRYPOINT", ""), "title": claude_session_title(sid), "at": now()}


def goal_publish(root: Path, goal: Path, rel: str, g: dict, st: dict, rounds_max: int) -> None:
    """คัดลอกสถานะเป้าหมายไป ~/.flashq/goals/ (ย่อ: รอบเก่าเก็บแค่ผล · รอบล่าสุดเก็บท้าย output) — พังได้ ไม่ขวางงาน"""
    try:
        title = ""
        for line in goal.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("# "):
                title = re.sub(r"^#\s*GOAL\s*:\s*", "", line).strip()
                break
        rounds = [{k: r.get(k) for k in ("at", "verdict", "fail", "stop", "human", "human_res", "flash", "rechecks", "warn", "cancel_hint")} for r in st.get("rounds", [])]
        if rounds:
            rounds[-1]["results"] = st["rounds"][-1].get("results", {})
        GOALS_DIR.mkdir(parents=True, exist_ok=True)
        key = _goal_key(root, rel)
        write_json(GOALS_DIR / f"{key}.json", {
            "id": key, "project": str(root), "goal": rel, "stem": goal.stem, "title": title or goal.stem,
            "items": [{"id": i["id"], "desc": i["desc"], "human": i["human"] if not i["cmd"] else ""} for i in g["items"]],
            "rounds_max": rounds_max, "hours": g["hours"] + float(st.get("extra_hours") or 0), "started": st.get("started", ""), "updated": now(), "rounds": rounds,
            "owner": st.get("owner") or {}, "goal_abs": str(goal), "cancelled": goal_cancelled(goal, st)})
        GOAL_STATE_BAK.mkdir(parents=True, exist_ok=True)
        write_json(GOAL_STATE_BAK / f"{key}.json", st)
    except Exception:
        pass


def goal_topic(name: str) -> str:
    """ชื่อเรื่องร่วมของ GOAL_<เรื่อง>.md กับ PLAN_FLASH_<เรื่อง>_R<n>.md"""
    s = Path(name).stem
    s = re.sub(r"^(GOAL_|PLAN_FLASH_)", "", s, flags=re.I)
    return re.sub(r"_R\d+$", "", s, flags=re.I).lower()


def ui_goals(running: list[dict], history: list[dict] | None = None, queued: list[dict] | None = None) -> list[dict]:
    """เป้าหมายสำหรับ UI: สถานะ + ผูกงานที่รันอยู่ (แผน _R<n> ในโปรเจกต์เดียวกัน) · ซ่อนที่จบ/หยุดเกิน 3 วัน
    ติดป้ายงาน (รันอยู่ + ประวัติ): r["goal"] = รอบของเป้าหมาย · r["fix_round"] = แผนแก้ซ้ำ _R<n> ธรรมดาที่ไม่มีเป้าหมาย (กันสับสนว่าธงหาย)"""
    queued = queued or []
    out, rows = [], running + queued + (history or [])
    rn = {}
    for r in rows:
        m = re.search(r"_R(\d+)\.md$", r.get("plan") or "", re.I)
        if m:
            rn[id(r)] = int(m.group(1))
    for f in GOALS_DIR.glob("*.json") if GOALS_DIR.is_dir() else []:
        if f.name.endswith(".busy.json"):
            continue
        gl = read_json(f)
        if not gl.get("id"):
            continue
        proj, topic = os.path.normcase(gl.get("project", "")), goal_topic(gl.get("stem", ""))
        jobs_now, runs, qs, last_job = [], [], [], {}
        for r in rows:
            if id(r) in rn and os.path.normcase(r.get("project", "")) == proj and goal_topic(r["plan"]) == topic:
                if not r.get("goal") or not gl.get("archived"):  # เรื่องเดียวกันหลายไฟล์ = ไฟล์ที่ไม่ได้เก็บชนะ
                    r["goal"] = {"id": gl["id"], "round": rn[id(r)], "rounds_max": gl.get("rounds_max", 0), "title": gl.get("title", "")}
                if any(r is x for x in running):
                    jobs_now.append(r["id"])
                    runs.append(r)
                elif any(r is x for x in queued):
                    qs.append(r)
                elif r.get("finished") and r["finished"] > last_job.get("finished", ""):  # งาน Flash ล่าสุดที่จบ → การ์ดบอกว่ารอใครอยู่
                    last_job = {"id": r["id"], "state": r.get("state", ""), "finished": r["finished"], "round": r["goal"]["round"]}
        last = (gl.get("rounds") or [None])[-1]
        since = (last or {}).get("at") or gl.get("started", "")
        unv = sorted({r["goal"]["round"] for r in rows if id(r) in rn and (r.get("goal") or {}).get("id") == gl["id"]
                      and r.get("finished", "") > since and r.get("state") not in ("cancelled", "busy", "queue_timeout")
                      and not any(r is x for x in running + queued)})
        if gl.get("archived"):  # กด ✖ เก็บแล้ว (goal check/verify ครั้งใหม่เขียนทับ = กลับมาเอง) — ป้ายงานยังติดให้
            continue
        verdict = last["verdict"] if last else "START"
        if not gl.get("cancelled"):  # user เขียนบรรทัด "สถานะ: ยกเลิก…" ในไฟล์ GOAL เอง (ไม่ได้สั่ง goal cancel) ก็นับ
            note = goal_cancel_note(Path(gl.get("goal_abs") or Path(gl.get("project", "")) / gl.get("goal", "")))
            gl["cancelled"] = {"at": "", "reason": note, "src": "file"} if note else {}
        if gl["cancelled"]:
            verdict = "CANCELLED"
        upd = _secs(gl.get("updated", "")) or 0
        if verdict in ("DONE", "DONE_NEEDS_USER", "STOP", "CANCELLED") and upd > 3 * 86400:
            continue
        res = (last or {}).get("results") or {}
        machine = [i for i in gl.get("items", []) if not i.get("human")]
        final = verdict in ("DONE", "DONE_NEEDS_USER", "STOP", "CANCELLED")
        end = gl["cancelled"].get("at") or (last or {}).get("at", "") if final else ""
        own = dict(gl.get("owner") or {})
        if own.get("session"):
            own["title"] = claude_session_title(own["session"]) or own.get("title", "")
        bz = read_json(GOALS_DIR / f"{gl['id']}.busy.json")
        busy = bz if bz.get("pid") and pid_alive(int(bz["pid"]), int(bz.get("pid_start") or 0)) else {}
        lj = dict(last_job, ago_sec=_secs(last_job["finished"])) if last_job else {}
        phase = goal_phase(gl, verdict, last, busy, runs, qs, lj, claude_activity(own.get("session", "")) if verdict not in ("DONE", "CANCELLED") else {}, unv)
        out.append(dict(gl, owner=own, busy=busy, verdict=verdict, age_sec=upd, usage=usage_brief_topic(topic),
                        elapsed_sec=_secs(gl.get("started", ""), end) if final else _secs(gl.get("started", "")),
                        passed=sum(1 for i in machine if res.get(i["id"], {}).get("ok")), machine=len(machine),
                        jobs=jobs_now, last_job=lj, phase=phase, unverified=unv,
                        project_name=Path(gl.get("project", "")).name))
    for r in rows:
        if id(r) in rn and not r.get("goal"):
            r["fix_round"] = rn[id(r)]
    return sorted(out, key=lambda x: x.get("updated", ""), reverse=True)[:12]


def _glob_hit(path: str, globs: list[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(path, g) or (g.endswith("/") and path.startswith(g)) or path.startswith(g.rstrip("/") + "/") for g in globs)


def _ts(s: str) -> float:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()
    except (TypeError, ValueError):
        return 0.0


def goal_project_jobs(root: Path) -> list[tuple[str, float, float, bool]]:
    """งานที่เคยรันในโปรเจกต์นี้: (เรื่องของแผน, เริ่ม, จบ, เป็นแผน _R<n>) — ใช้แยกว่า commit ในช่วงหนึ่งเป็นของงานไหน"""
    proj, out = os.path.normcase(str(root)), []
    for j in jobs():
        plan = j.get("plan") or ""
        if plan and os.path.normcase(j.get("project", "")) == proj and j.get("started"):
            out.append((goal_topic(plan), _ts(j["started"]), _ts(j.get("finished", "")) or time.time(), bool(re.search(r"_R\d+\.md$", plan, re.I))))
    return out


def goal_job_windows(root: Path, stem: str) -> list[tuple[float, float]]:
    """ช่วงเวลาที่งาน Flash ของเป้าหมายนี้รัน (แผน PLAN_FLASH_<เรื่อง>_R<n>.md ในโปรเจกต์เดียวกัน)"""
    topic = goal_topic(stem)
    return sorted((a, b) for t, a, b, rn in goal_project_jobs(root) if rn and t == topic)


def _other_topic(files: list[str], topic: str) -> bool:
    """commit แตะแผน/เป้าหมายของเรื่องอื่น = งานของ session อื่นที่บังเอิญอยู่ในช่วงเวลาเดียวกัน"""
    return bool(topic) and any(re.match(r"(GOAL_|PLAN_).+\.md$", Path(f).name, re.I) and goal_topic(f) != topic for f in files)


def goal_changed_files(root: Path, base: str, started: str, windows: list[tuple[float, float]], topic: str = "",
                       scope: list[str] | None = None, ack: dict | None = None) -> tuple[list[str], list[str]]:
    """ไฟล์ที่ถูกแก้ระหว่างวนเป้าหมาย → (ของงาน Flash เป้าหมายนี้แน่ ๆ, อาจเป็นของ session อื่น)
    นับเฉพาะ commit (ไม่รวม merge) ที่เกิดระหว่างงาน Flash ของเป้าหมายนี้รัน · ไม่มีประวัติงาน = ทุก commit หลัง base
    ข้าม commit ที่แตะ GOAL_/PLAN_FLASH_ ของเรื่องอื่น · commit ที่ไม่แตะ goal-files/แผนของเรื่องนี้ และ (ไม่มีรหัสงาน `(T-xx)` หรือมีงานแผนอื่นรันซ้อนอยู่)
    = "อาจเป็นของ session อื่น" (เตือน ไม่ STOP) · ไฟล์ค้าง/ยังไม่ track ที่แก้ระหว่างงานรัน ก็เป็น "อาจเป็น" (Flash ต้อง commit ทุกงาน)
    ไม่มีประวัติงาน Flash ของเป้าหมาย = แยกไม่ได้ → ทุกอย่างนับเป็นของเป้าหมาย (รวมไฟล์ค้างที่แก้หลังเริ่ม)
    ack = user รับทราบแล้ว: นับ commit หลัง head ของ ack · ไฟล์ค้างที่แก้หลัง ts"""
    if ack and ack.get("head"):
        base = ack["head"]
    ack_ts, acked = float((ack or {}).get("ts") or 0), set((ack or {}).get("files") or [])
    ours, maybe = set(), set()
    split = scope is not None and bool(windows)  # ไม่มีประวัติงาน Flash = แยกไม่ได้ นับทุกอย่างเป็นของเป้าหมาย (เข้มเหมือนเดิม)
    others = [(a, b) for t, a, b, _ in goal_project_jobs(root) if t != topic] if split else []
    if base:
        commits: list[tuple[int, str, list[str]]] = []
        for line in _git(root, "log", "--no-merges", "--format=@@%ct %s", "--name-only", f"{base}..HEAD").splitlines():
            if line.startswith("@@"):
                t, _, subj = line[2:].partition(" ")
                commits.append((int(t or 0), subj, []))
            elif line.strip() and commits:
                commits[-1][2].append(line.strip())
        for t, subj, files in commits:
            if (windows and not any(a - 2 <= t <= b + 5 for a, b in windows)) or _other_topic(files, topic):
                continue
            mine = any(goal_topic(f) == topic and re.match(r"(GOAL_|PLAN_FLASH_)", Path(f).name, re.I) for f in files) or (
                scope is not None and any(_glob_hit(f, scope) for f in files))
            stranger = split and not mine and (not re.search(r"\(T-\d+", subj) or any(a - 2 <= t <= b + 5 for a, b in others))
            (maybe if stranger else ours).update(files)
    dirty = set(_git(root, "diff", "--name-only", "HEAD").splitlines()) | set(_git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    for f in dirty:
        f = f.strip()
        try:
            m = (root / f).stat().st_mtime if f else 0
            if f and m > ack_ts and (any(a - 2 <= m <= b + 5 for a, b in windows) if windows else m >= _ts(started)):
                (maybe if split else ours).add(f)
        except OSError:
            if f not in acked:
                ours.add(f)  # ถูกลบ = นับว่าแก้ (ยกเว้นที่ ack แล้ว)
    return sorted(ours), sorted(maybe - ours)


def goal_work_fp(root: Path, base: str, free: list[str], windows: list[tuple[float, float]]) -> str:
    """ลายนิ้วมือ "งาน" ตั้งแต่ base: เนื้อหาไฟล์ที่ต่างจาก base (ไม่รวมไฟล์จดบันทึก GOAL/แผน/.tmp) + ไฟล์ใหม่ + จำนวนงาน Flash ของเป้าหมาย
    เท่ากับรอบก่อน = ไม่มีงานใหม่ → verify ซ้ำไม่นับรอบ (กันเสียงบรอบเปล่า)"""
    ex = [f":(exclude){p.rstrip('/')}" for p in free if p and "*" not in p]
    h = hashlib.sha1(_git(root, "diff", "--no-color", "--no-ext-diff", base or "HEAD", "--", ".", *ex).encode("utf-8", "replace"))
    for f in sorted(_git(root, "ls-files", "--others", "--exclude-standard").splitlines()):
        if f.strip() and not _glob_hit(f.strip(), free):
            try:
                s = (root / f.strip()).stat()
                h.update(f"{f}|{s.st_size}|{int(s.st_mtime)}".encode("utf-8", "replace"))
            except OSError:
                pass
    h.update(f"jobs={len(windows)}".encode())
    return h.hexdigest()[:16]


def goal_human(root: Path, goal: Path, rel: str, g: dict, st: dict, sp: Path, rounds_max: int, a) -> int:
    """บันทึกผลข้อ `คนตรวจ:` ของรอบล่าสุด (จากหน้าเว็บหรือ Claude) · ผ่านครบ = DONE · มีข้อไม่ผ่าน = คง DONE_NEEDS_USER รอ Claude แปลงเหตุเป็นเกณฑ์"""
    last = st["rounds"][-1] if st.get("rounds") else None
    if not last or last["verdict"] not in ("DONE_NEEDS_USER", "DONE"):
        print("GOAL_HUMAN=FAIL ตรวจข้อคนตรวจได้เฉพาะเมื่อเครื่องตรวจผ่านครบแล้ว (GOAL=DONE_NEEDS_USER)")
        return 1
    hum = [i["id"] for i in g["items"] if not i["cmd"]]
    if a.item not in hum:
        print(f"GOAL_HUMAN=FAIL {a.item or '(ว่าง)'} ไม่ใช่ข้อคนตรวจ (มี: {', '.join(hum) or '-'})")
        return 1
    if not a.passed and not (a.fail or "").strip():
        print('GOAL_HUMAN=FAIL ต้องระบุ --pass หรือ --fail "เหตุ"')
        return 1
    res = last.setdefault("human_res", {})
    res[a.item] = {"ok": bool(a.passed), "reason": "" if a.passed else a.fail.strip(), "at": now()}
    bad = [k for k in hum if k in res and not res[k]["ok"]]
    last["verdict"] = "DONE" if all(res.get(k, {}).get("ok") for k in hum) else "DONE_NEEDS_USER"
    write_json(sp, st)
    goal_publish(root, goal, rel, g, st, rounds_max)
    if bad:
        print("ไม่ผ่าน: " + " · ".join(f"{k} {res[k]['reason']}" for k in bad) + " → ให้ Claude แปลงเหตุเป็นเกณฑ์ที่วัดได้ แล้ว `goal check --reset` วนต่อ")
        hint = goal_cancel_hint(st)
        if hint:
            print(f"แนะนำ: พิจารณายกเลิกธง (flashq goal cancel {rel} --reason \"…\") — {hint} · ให้ user เลือก วนต่อ / ยกเลิกธง")
    left = [k for k in hum if k not in res]
    print(f"GOAL={last['verdict']} คนตรวจผ่าน {sum(1 for k in hum if res.get(k, {}).get('ok'))}/{len(hum)}" + (f" · ยังไม่ตรวจ {', '.join(left)}" if left else ""))
    return 0


def claude_exe() -> str:
    """claude CLI: ใน PATH ก่อน · ไม่มี → ตัวที่แอป Claude desktop ติดตั้งไว้ (รุ่นใหม่สุด)"""
    w = shutil.which("claude")
    if w:
        return w
    base = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code"
    exes = sorted(base.glob("*/*/claude.exe"), key=lambda x: x.stat().st_mtime, reverse=True) if base.is_dir() else []
    return str(exes[0]) if exes else ""


def claude_app_link(path: str, params: dict) -> str:
    """ลิงก์ claude:// ของแอป Claude desktop (แท็บ Code) · "" = เครื่องนี้ไม่มีแอป (ไม่ได้ลงทะเบียน claude://)
    code/new?q=&folder= = session ใหม่ พิมพ์ข้อความรอไว้ (แอปแปลงโฟลเดอร์ worktree กลับเป็น repo เอง) · code/continue?session=local_… = เปิด session เดิม"""
    import urllib.parse
    if os.name == "nt":
        try:
            import winreg
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\claude"))
        except OSError:
            return ""
    elif not shutil.which("open"):
        return ""
    return f"claude://code/{path}?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def open_link(url: str) -> None:
    if os.name == "nt":
        os.startfile(url)  # noqa: S606 — ลิงก์ claude:// ที่สร้างเองเท่านั้น
    else:
        subprocess.Popen(["open", url])


def claude_check_prompt(j: dict) -> str:
    """ข้อความตั้งต้นของ session Claude ใหม่ที่เปิดจากปุ่มบนการ์ดงานที่จบแล้ว
    OK + มีแผน = /flash-check · ผลสืบ = ตรวจเลขอ้างอิงก่อนเชื่อ · ไม่ OK/ตาย = ดู log หาสาเหตุแล้วรายงาน (ยังไม่สั่งซ้ำเอง)"""
    st = "dead" if live_state(j) == "dead" else str(j.get("result") or j.get("status") or "").lower()
    if st == "ok_unverified":
        st = "ok"
    plan, jid = j.get("plan") or "", j["id"]
    if j.get("kind") == "doc":
        return (f"ช่างเอกสาร flashq job {jid} จบด้วยสถานะ {st.upper()}: อ่านผลด้วย `{run_cmd()} log {jid}` (ผลมาจากการตรวจด้วยกลไกของ flashq ไม่ใช่คำบอกของ AI) "
                f"แล้ว `git diff` ของโปรเจกต์ ตรวจว่าเอกสารที่แก้ตรงกับโค้ดจริง (เปิดไฟล์ที่เอกสารอ้างถึงเทียบเอง) แล้วรายงานผมเป็นภาษาไทย: แก้ไฟล์ไหน · ถูก/ผิดตรงไหน · ควรรับหรือทิ้ง "
                f"(ห้าม commit/รับ/ทิ้งเองจนกว่าผมสั่ง)")
    if j.get("kind") == "qa":
        return (f"นักทดสอบ flashq job {jid} จบด้วยสถานะ {st.upper()}: อ่านผลด้วย `{run_cmd()} log {jid}` "
                f"(ผลมาจาก exit code ของคำสั่งทดสอบจริง ไม่ใช่คำบอกของ AI) แล้วรายงานผมเป็นภาษาไทย: ทดสอบอะไร · ผ่าน/ไม่ผ่านชุดไหน · ถ้าไม่ผ่านสาเหตุคืออะไรจากบรรทัดใน log "
                f"(คำอธิบายของ Flash เป็นแค่ความเห็น ต้องเทียบ log เอง) · ผมต้องทำอะไรต่อ")
    if st == "ok" and j.get("kind") == "investigate":
        return f"ผู้สืบ flashq job {jid} จบแล้ว: อ่านผลด้วย `{run_cmd()} log {jid}` แล้วตรวจเลขไฟล์:บรรทัดที่อ้างก่อนเชื่อ จากนั้นสรุปให้ผม"
    if st == "ok" and plan:
        return f"/flash-check {plan}"
    if st == "ok":
        return f"งาน flashq job {jid} จบแล้ว: อ่าน git diff/log ของโปรเจกต์แล้วตรวจผลก่อนรายงานผม (บอกว่างานนี้ได้ผลงานอะไรแบบไหน)"
    return (f"งาน flashq job {jid} จบด้วยสถานะ {st.upper()}: ดูสาเหตุด้วย `{run_cmd()} log {jid}` "
            f"แล้วบอกผมเป็นภาษาไทยว่าเกิดอะไร และแนะนำทางแก้ (ยังไม่ต้องสั่งงานซ้ำจนกว่าผมจะตอบ)")


def claude_check_action(j: dict, cli: bool = False) -> tuple[int, dict]:
    """ปุ่ม "เปิด Claude ตรวจ" บนการ์ดงาน: แอป Claude desktop = session ใหม่พิมพ์ข้อความรอไว้ (กด Enter เอง) · ไม่มีแอป/cli = หน้าต่าง claude CLI
    รับเฉพาะงานที่จบแล้ว (หรือ process ตาย) · โฟลเดอร์มาจากงานในคิวเท่านั้น ไม่รับ path จากหน้าเว็บ · กดซ้ำภายใน 60 วิ = ปฏิเสธ (กัน session งอกซ้ำ)"""
    if live_state(j) in ("queued", "running"):
        return 409, {"ok": False, "message": "งานยังไม่จบ — รอจบก่อน"}
    cwd = Path(j.get("project") or "")
    if not cwd.is_dir():
        return 404, {"ok": False, "message": f"ไม่พบโฟลเดอร์โปรเจกต์ {cwd}"}
    try:
        if time.time() - float(j.get("claude_opened") or 0) < 60:
            return 409, {"ok": False, "message": "เพิ่งเปิด session ตรวจงานนี้ไปเมื่อสักครู่ — ดูในแอป Claude"}
    except (TypeError, ValueError):
        pass
    prompt = claude_check_prompt(j)
    url = "" if cli else claude_app_link("new", {"q": prompt, "folder": str(cwd)})
    if url:
        open_link(url)
        msg = f"เปิด session ใหม่ในแอป Claude (แท็บ Code) ที่ {cwd} พิมพ์ข้อความตรวจรอไว้แล้ว — กด Enter ในแอปเพื่อเริ่ม"
    else:
        exe = claude_exe()
        if not exe:
            return 404, {"ok": False, "message": "ไม่พบแอป Claude หรือ claude CLI → ใช้ปุ่มคัดลอกคำสั่งแทน", "prompt": prompt}
        subprocess.Popen([exe, prompt], cwd=str(cwd), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        msg = f"เปิดหน้าต่าง Claude Code ที่ {cwd} พร้อมข้อความตรวจแล้ว — ดูและอนุญาตคำสั่งในหน้าต่างนั้น"
    j["claude_opened"] = time.time()
    save_job(j)
    return 200, {"ok": True, "message": msg}


def _goal_sub(argv: list[str], root: Path) -> tuple[int, dict]:
    r = run_timeout(argv, GOAL_UI_CMD_TIMEOUT_SEC, cwd=str(root))
    if r.returncode == 124:
        return 504, {"ok": False, "message": f"คำสั่ง goal ไม่ตอบภายใน {GOAL_UI_CMD_TIMEOUT_SEC:g} วิ → ฆ่าแล้ว (ยังไม่ได้บันทึก) ลองใหม่อีกครั้ง"}
    return (200 if r.returncode == 0 else 400), {"ok": r.returncode == 0, "message": (r.stdout or r.stderr).strip()}


def goal_ui_action(gid: str, action: str, body: dict) -> tuple[int, dict]:
    """ปุ่มบนการ์ดเป้าหมาย: verify (ตรวจใหม่เบื้องหลัง) · human (ผ่าน/ไม่ผ่านข้อคนตรวจ) · open (เปิดไฟล์/โฟลเดอร์)
    claude (ทำต่อ: แอป Claude desktop = session ใหม่พิมพ์ /flash-goal รอไว้ · ไม่มีแอป/body.cli = หน้าต่าง CLI) · session (เปิด session เดิมในแอป) · archive (✖ เก็บการ์ดที่จบแล้ว)
    cancel (ยกเลิกธง + เหตุ = goal cancel) · hide (ซ่อนการ์ดธงที่ยกเลิก = ลบสำเนาใน ~/.flashq/goals)
    path ทุกตัวมาจากสำเนาสถานะใน ~/.flashq/goals เท่านั้น ไม่รับ path จากหน้าเว็บ"""
    if not re.fullmatch(r"[0-9a-f]{12}", gid or ""):
        return 400, {"ok": False, "message": "id ไม่ถูกต้อง"}
    gl = read_json(GOALS_DIR / f"{gid}.json")
    if not gl.get("project"):
        return 404, {"ok": False, "message": "ไม่พบเป้าหมาย"}
    root = Path(gl["project"])
    goal = Path(gl.get("goal_abs") or root / gl["goal"])
    own_cwd = Path((gl.get("owner") or {}).get("cwd") or root)
    cwd = own_cwd if own_cwd.is_dir() else root
    bp = GOALS_DIR / f"{gid}.busy.json"
    bz = read_json(bp)
    busy = bz.get("pid") and pid_alive(int(bz["pid"]), int(bz.get("pid_start") or 0))
    me = [*self_argv(), "goal"]
    if action == "open":
        target = goal if body.get("what") == "goal" else cwd
        if not target.exists():
            return 404, {"ok": False, "message": f"ไม่พบ {target}"}
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(target)] if target.is_file() else ["explorer", str(target)])
        return 200, {"ok": True, "message": f"เปิด {target}"}
    if action == "human":
        return _goal_sub(me + ["human", str(goal), str(body.get("item") or ""), "--project", str(root)]
                         + (["--pass"] if body.get("ok") else ["--fail", str(body.get("reason") or "")]), root)
    if action == "archive":
        last = (gl.get("rounds") or [{}])[-1]
        if last.get("verdict") not in ("DONE", "STOP"):
            return 409, {"ok": False, "message": "เก็บได้เฉพาะเป้าหมายที่ผ่านแล้วหรือหยุดแล้ว"}
        gl["archived"] = now()
        write_json(GOALS_DIR / f"{gid}.json", gl)
        return 200, {"ok": True, "message": "เก็บแล้ว — ไฟล์ GOAL และประวัติยังอยู่ครบ · สั่ง goal check/verify เรื่องนี้ใหม่ = กลับมาแสดงเอง"}
    if action == "cancel":  # ตรรกะเดียวกับ `goal cancel` (บรรทัดสถานะในไฟล์ GOAL · ไฟล์สถานะ · การ์ด)
        if ((gl.get("rounds") or [{}])[-1]).get("verdict") == "DONE":
            return 409, {"ok": False, "message": "ธงนี้ผ่านแล้ว ยกเลิกไม่ได้ (ใช้ ✖ เก็บ)"}
        reason = " ".join(str(body.get("reason") or "").split())
        if not reason:
            return 400, {"ok": False, "message": "ใส่เหตุที่เลิกก่อน"}
        return _goal_sub(me + ["cancel", str(goal), "--reason", reason, "--project", str(root)], root)
    if action == "hide":  # ซ่อนการ์ดธงที่ยกเลิกแล้ว = ลบเฉพาะสำเนาใน ~/.flashq/goals (ไฟล์ GOAL/สถานะในโปรเจกต์อยู่ครบ)
        if not (gl.get("cancelled") or goal_cancel_note(goal)):
            return 409, {"ok": False, "message": "ซ่อนได้เฉพาะธงที่ยกเลิกแล้ว"}
        for f in [GOALS_DIR / f"{gid}.json", bp] + list(GOALS_DIR.glob(f"{gid}.*.log")):
            f.unlink(missing_ok=True)
        return 200, {"ok": True, "message": "ซ่อนการ์ดแล้ว — ไฟล์ GOAL และสถานะในโปรเจกต์ยังอยู่ · ธงที่ยกเลิกไม่สร้างการ์ดใหม่เอง"}
    if action == "session":
        host =(gl.get("owner") or {}).get("host") or ""
        url = claude_app_link("continue", {"session": host}) if re.fullmatch(r"local_[A-Za-z0-9-]{1,64}", host) else ""
        if not url:
            return 404, {"ok": False, "message": "ไม่มี session ของแอป Claude desktop ให้เปิด (สั่งจาก CLI หรือเครื่องไม่มีแอป) → ใช้ปุ่มให้ Claude ทำต่อ"}
        open_link(url)
        return 200, {"ok": True, "message": "เปิด session เดิมในแอป Claude แล้ว (ถ้า session ถูกลบ/เก็บถาวร แอปจะไปหน้ารวม)"}
    if action in ("verify", "claude"):
        if gl.get("cancelled") or goal_cancel_note(goal):
            return 409, {"ok": False, "message": "ธงนี้ยกเลิกแล้ว — ไม่ตรวจ/ไม่วนต่อ (เปิดใหม่: ลบบรรทัดสถานะในไฟล์ GOAL แล้ว goal check --reset)"}
        if busy:
            return 409, {"ok": False, "message": f"กำลัง{'ตรวจใหม่' if bz.get('what') == 'verify' else 'เปิด Claude ทำต่อ'}อยู่แล้ว (เริ่ม {bz.get('at')})"}
        topic, proj = goal_topic(gl.get("stem", "")), os.path.normcase(str(root))
        if any(live_state(j) == "running" and os.path.normcase(j.get("project", "")) == proj and re.search(r"_R\d+\.md$", j.get("plan") or "", re.I)
               and goal_topic(j["plan"]) == topic for j in jobs()):
            return 409, {"ok": False, "message": "Flash กำลังทำรอบของเป้าหมายนี้อยู่ — รอจบก่อน"}
        url = "" if action != "claude" or body.get("cli") else claude_app_link("new", {"q": f"/flash-goal {goal}", "folder": str(cwd)})
        if url:
            open_link(url)
            return 200, {"ok": True, "message": f"เปิด session ใหม่ในแอป Claude (แท็บ Code) ที่ {cwd} พิมพ์ /flash-goal รอไว้แล้ว — กด Enter ในแอปเพื่อเริ่ม"}
        log = GOALS_DIR / f"{gid}.{action}.log"
        if action == "verify":
            with log.open("wb") as fh:
                p = subprocess.Popen(me + ["verify", str(goal), "--project", str(root)], cwd=str(root),
                                     stdout=fh, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            exe = claude_exe()
            if not exe:
                return 404, {"ok": False, "message": "ไม่พบ claude CLI (ไม่มีใน PATH และไม่พบตัวของแอป Claude) → ใช้ปุ่มคัดลอกคำสั่งแทน"}
            p = subprocess.Popen([exe, f"/flash-goal {goal}"], cwd=str(cwd), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        write_json(bp, {"what": action, "pid": p.pid, "pid_start": proc_start(p.pid), "at": now(), "log": str(log) if action == "verify" else ""})
        msg = ("เริ่มตรวจใหม่แล้ว (รันเกณฑ์ทุกข้อ ใช้เวลาหลายนาที) — การ์ดจะอัปเดตเองเมื่อเสร็จ" if action == "verify" else
               f"เปิดหน้าต่าง Claude Code ที่ {cwd} พร้อมคำสั่ง /flash-goal แล้ว — ดูและอนุญาตคำสั่งในหน้าต่างนั้น")
        return 200, {"ok": True, "message": msg}
    return 400, {"ok": False, "message": "action ไม่รู้จัก"}


GOAL_CANCEL_RE = re.compile(r"^\s*>\s*\*\*\s*สถานะ\s*:\s*(ยกเลิก[^*]*)\*\*\s*(?:[—–-]+\s*)?(.*)$")


def goal_cancel_note(goal: Path) -> str:
    """บรรทัด `> **สถานะ: ยกเลิกโดย user (<วันที่>)** — <เหตุ>` ใต้หัวไฟล์ GOAL (ก่อนหัวข้อ `## ` แรก) → "ยกเลิกโดย user (...) — เหตุ" · ไม่มี = ''"""
    try:
        with goal.open(encoding="utf-8", errors="replace") as fh:
            for k, line in enumerate(fh):
                if k > 60 or line.startswith("## "):
                    break
                m = GOAL_CANCEL_RE.match(line)
                if m:
                    return m.group(1).strip() + (f" — {m.group(2).strip()}" if m.group(2).strip() else "")
    except OSError:
        pass
    return ""


def goal_cancelled(goal: Path, st: dict) -> dict:
    """ธงถูกยกเลิกไหม: สถานะที่ goal cancel บันทึก หรือบรรทัด "สถานะ: ยกเลิก…" ในไฟล์ GOAL (เขียนเอง) → {at, reason} · ไม่ได้ยกเลิก = {}"""
    c = dict((st or {}).get("cancelled") or {})
    if not c:
        note = goal_cancel_note(goal)
        c = {"at": "", "reason": note, "src": "file"} if note else {}
    return c


def goal_round_brief(r: dict, prev: dict | None) -> dict:
    """ย่อรอบไว้ข้ามการ check --reset: คนตรวจไม่ผ่าน (None = ยังไม่ตรวจ) · จำนวนเกณฑ์ที่ถอยหลัง"""
    hres = r.get("human_res") or {}
    pres = (prev or {}).get("results") or {}
    return {"at": r.get("at", ""), "verdict": r.get("verdict", ""), "human_bad": any(not v.get("ok") for v in hres.values()) if hres else None,
            "regress": sum(1 for k, v in (r.get("results") or {}).items() if not v.get("ok") and pres.get(k, {}).get("ok"))}


def goal_cancel_hint(st: dict) -> str:
    """เหตุที่ควรพิจารณายกเลิกธง: คนตรวจไม่ผ่าน ≥2 รอบติด · เกณฑ์ถอยหลัง ≥2 รอบ (นับรวมก่อน check --reset) · ไม่มี = ''"""
    rs = st.get("rounds") or []
    seq = list(st.get("past") or []) + [goal_round_brief(r, rs[k - 1] if k else None) for k, r in enumerate(rs)]
    streak = 0
    for b in reversed([b for b in seq if b.get("human_bad") is not None]):
        if not b["human_bad"]:
            break
        streak += 1
    if streak >= 2:
        return f"คนตรวจให้ไม่ผ่าน {streak} รอบติด"
    back = sum(1 for b in seq if b.get("regress"))
    return f"เกณฑ์ถอยหลังแล้ว {back} รอบ (เคยผ่านแล้วกลับไม่ผ่าน)" if back >= 2 else ""


def _log_shas(text: str) -> list[str]:
    """เลข commit ในตารางบันทึกผล (§4 / "บันทึกผล" / "บันทึกรอบ") — มีคอลัมน์ commit = อ่านคอลัมน์นั้น · ไม่มี = คำฐาน 16 ที่มีตัวอักษร"""
    out, on, lvl, fence, cols = [], False, 0, False, None
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        h = None if fence else re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            if on and len(h.group(1)) <= lvl:
                on = False
            t = h.group(2).strip()
            if re.match(r"(§\s*)?4\s*[.)]", t) or "บันทึกผล" in t or "บันทึกรอบ" in t:
                on, lvl = True, len(h.group(1))
            cols = None
            continue
        if not on or fence or not line.lstrip().startswith("|"):
            cols = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cols is None:
            cols = [k for k, c in enumerate(cells) if "commit" in c.lower()]
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
            continue
        pool = " ".join(cells[k] for k in cols if k < len(cells)) if cols else " ".join(cells)
        toks = re.findall(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])", pool)
        out += [t for t in toks if cols or re.search(r"[a-f]", t)]
    return out


def goal_round_commits(root: Path, goal: Path) -> list[dict]:
    """commit ของงานในธงนี้จากบันทึกผลของ GOAL + แผน PLAN_FLASH_<เรื่อง>_R*.md (เฉพาะที่มีจริงใน repo) · ใหม่ → เก่า"""
    topic, dirs = goal_topic(goal.stem), []
    for d in (goal.parent, root / (project_cfg(root).get("plan_dir") or "docs/plans")):
        if d.is_dir() and all(os.path.normcase(str(d.resolve())) != os.path.normcase(str(x.resolve())) for x in dirs):
            dirs.append(d)
    plans = sorted({p for d in dirs for p in d.glob("PLAN_FLASH_*.md") if re.search(r"_R\d+\.md$", p.name, re.I) and goal_topic(p.name) == topic},
                   key=lambda p: int(re.search(r"_R(\d+)\.md$", p.name, re.I).group(1)))
    found: dict[str, str] = {}
    for src in [goal] + plans:
        try:
            for t in _log_shas(src.read_text(encoding="utf-8", errors="replace")):
                found.setdefault(t, src.name)
        except OSError:
            pass
    out, seen = [], set()
    for t, src in found.items():
        info = _git(root, "show", "-s", "--format=%H%x09%h%x09%ct%x09%s", t + "^{commit}", "--")
        parts = info.splitlines()[0].split("\t", 3) if info else []
        if len(parts) == 4 and parts[0] not in seen:
            seen.add(parts[0])
            out.append({"sha": parts[0], "short": parts[1], "ts": int(parts[2]), "subject": parts[3], "src": src})
    return sorted(out, key=lambda c: c["ts"], reverse=True)


def goal_cancel(root: Path, goal: Path, rel: str, g: dict, st: dict, sp: Path, rounds_max: int, a, is_git: bool) -> int:
    """user สั่งเลิกธง: เติมบรรทัดสถานะใต้หัวไฟล์ GOAL · บันทึก cancelled ในไฟล์สถานะ · การ์ดเป็นสถานะยกเลิก (ไม่ลบ)
    · ไม่ commit/ไม่ถอยโค้ดเอง — พิมพ์ commit ของงานในธง + คำสั่ง git revert ให้ user ตัดสิน"""
    reason = " ".join((a.reason or "").split())
    if not reason:
        print('GOAL_CANCEL=FAIL ต้องระบุ --reason "เหตุที่เลิก"')
        return 1
    prev = goal_cancelled(goal, st)
    if not goal_cancel_note(goal):
        raw = goal.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig", errors="replace")
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines(keepends=True)
        mark = f"> **สถานะ: ยกเลิกโดย user ({now()[:10]})** — {reason}{nl}"
        i = next((k for k, x in enumerate(lines) if x.startswith("# ")), -1)
        if i < 0:
            lines[:0] = [mark, nl]
        else:
            if not lines[i].endswith(("\n", "\r")):
                lines[i] += nl
            lines[i + 1:i + 1] = [nl, mark] + ([nl] if i + 1 < len(lines) and lines[i + 1].strip() else [])
        goal.write_bytes((b"\xef\xbb\xbf" if bom else b"") + "".join(lines).encode("utf-8"))
    if not st:
        st = {"goal": rel, "sig": g["sig"], "base": _git(root, "rev-parse", "HEAD") if is_git else "", "started": now(), "rounds": []}
    if not st.get("cancelled"):
        st["cancelled"] = {"at": now(), "reason": reason if not prev else prev.get("reason") or reason, "by": "user", "rounds": len(st.get("rounds") or [])}
    st["owner"] = goal_owner() or st.get("owner") or {}
    sp.parent.mkdir(parents=True, exist_ok=True)
    write_json(sp, st)
    goal_publish(root, goal, rel, g, st, rounds_max)
    c = st["cancelled"]
    print(("ธงนี้ยกเลิกไว้แล้ว" if prev else "ยกเลิกธงแล้ว") + f" ({c['at']}) — {c['reason']} · ใช้ไป {c.get('rounds', 0)}/{rounds_max} รอบ")
    topic, proj = goal_topic(goal.stem), os.path.normcase(str(root))
    live = [j for j in jobs() if live_state(j) in ("running", "queued") and os.path.normcase(j.get("project", "")) == proj
            and re.search(r"_R\d+\.md$", j.get("plan") or "", re.I) and goal_topic(j["plan"]) == topic]
    for j in live:
        print(f"เตือน: งาน Flash ของธงนี้ยัง{'รัน' if live_state(j) == 'running' else 'รอคิว'}อยู่ {j['id']} ({j.get('plan')}) — ไม่หยุดให้เอง · หยุด: `flashq cancel {j['id']}`")
    cs = goal_round_commits(root, goal) if is_git else []
    if cs:
        print("commit ของงานในธงนี้ (จากบันทึกผลของ GOAL/แผน _R*) — ไม่ถอยให้อัตโนมัติ ให้ user ดู diff แล้วตัดสินเอง:")
        for x in cs:
            print(f"  {x['short']}  {datetime.fromtimestamp(x['ts']).strftime('%Y-%m-%d %H:%M')}  {x['subject'][:90]}  ({x['src']})")
        print("ถ้าจะถอยทั้งหมด (ใหม่ → เก่า): git revert --no-edit " + " ".join(x["short"] for x in cs))
    else:
        print("ไม่พบ commit ในบันทึกผลของแผน (§4) — ถ้าจะถอย ดูเองด้วย `git log --oneline " + ((st.get("base") or "")[:9] + "..HEAD`" if st.get("base") else "`"))
    print(f"ต้อง commit ไฟล์ GOAL เอง (flashq ไม่ commit ให้): `git add {rel}` แล้ว `git commit -m \"goal: ยกเลิกธง {goal.stem}\"`")
    print(f"GOAL=CANCELLED {rel}")
    return 0


def goal_stop_hints(stop: list[str], rel: str) -> list[str]:
    """เหตุเบรก → คำสั่งทางออกที่ใช้ได้จริง (สั่งเมื่อ user เลือกแล้วเท่านั้น)"""
    out, has = [], lambda *ks: any(k in s for s in stop for k in ks)  # noqa: E731
    if has("นอกขอบเขต", "ไฟล์ล็อก"):
        out.append(f"ทางออก (ไฟล์นอกขอบเขต/ไฟล์ล็อก): ให้ user ตรวจไฟล์ → ยอมรับ = `goal ack {rel} --reason \"<เหตุของ user>\"` แล้ว `goal verify`"
                   " · ไม่ยอมรับ = git revert แล้ว ack เช่นกัน (ไม่ล้าง base/รอบ)")
    if has("ครบงบ", "เกินงบเวลา"):
        out.append(f"ทางออก (งบหมด): user ต่องบ = `goal check {rel} --extend <รอบ> --extend-hours <ชม.>` แล้ว `goal verify` (เก็บ base/รอบ/ประวัติ)"
                   f" · หรือเริ่มนับใหม่ทั้งหมด = `goal check {rel} --reset`")
    if has("พังซ้ำ"):
        out.append("ทางออก (พังซ้ำ): สืบต้นตอใหม่/แผนคนละทาง → มีงานใหม่แล้วค่อย `goal verify` (ตรวจซ้ำโดยไม่มีงานใหม่ไม่ช่วย)")
    if has("ย้ายเสาประตู"):
        out.append(f"ทางออก (เกณฑ์ถูกแก้): user ยืนยันเกณฑ์ใหม่ → `goal check {rel} --reset`")
    return out


def goal_run_cmd(root: Path, cmd: str, timeout_min: float) -> tuple[int, str]:
    # output ลงไฟล์ชั่วคราว ไม่ใช่ pipe: ลูกที่สืบทอด pipe ไปแล้วค้างเบื้องหลัง (เช่น `start /b server`) จะไม่ทำให้ communicate() รอตามไปจน timeout ไม่ทำงาน
    with tempfile.TemporaryFile() as buf:
        p = subprocess.Popen(cmd, shell=True, cwd=str(root), stdin=subprocess.DEVNULL, stdout=buf, stderr=subprocess.STDOUT)  # คำสั่งที่รอ input ได้ EOF ทันที ไม่ค้าง
        timed_out = False
        try:
            p.wait(timeout=timeout_min * 60)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(p.pid)
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                print(f"เตือน: ฆ่าคำสั่งเกณฑ์ไม่สำเร็จ pid {p.pid} — ไม่รอต่อ", file=sys.stderr)
        buf.seek(0)
        out = buf.read()
    if timed_out:
        return 124, (out + f"\n[flashq goal: เกิน {timeout_min:g} นาที → ฆ่าแล้ว]".encode("utf-8")).decode("utf-8", errors="replace")
    return p.returncode, out.decode("utf-8", errors="replace")


def goal_ack(root: Path, goal: Path, rel: str, g: dict, st: dict, sp: Path, rounds_max: int, a) -> int:
    """user รับทราบไฟล์นอกขอบเขต/ไฟล์ล็อกที่เจอแล้ว → ตรวจเฉพาะ commit หลัง HEAD ตอน ack และไฟล์ที่แก้หลังจากนั้น (ไม่ล้าง base/รอบ/ประวัติ)"""
    reason = (a.reason or "").strip()
    if not reason:
        print('GOAL_ACK=FAIL ต้องระบุ --reason "เหตุที่ user ยอมรับ"')
        return 1
    last = st["rounds"][-1] if st.get("rounds") else {}
    files = sorted(set(last.get("out_scope", []) + last.get("locked", []) + last.get("warn", [])))
    if not files:
        print("GOAL_ACK=FAIL รอบล่าสุดไม่มีไฟล์นอกขอบเขต/ไฟล์ล็อกให้รับทราบ")
        return 1
    st["acks"] = (st.get("acks") or [])[-19:] + [{"at": now(), "ts": time.time(), "head": _git(root, "rev-parse", "HEAD"),
                                                   "reason": reason, "files": files[:50]}]
    write_json(sp, st)
    goal_publish(root, goal, rel, g, st, rounds_max)
    print(f"รับทราบ {len(files)} ไฟล์: " + ", ".join(files[:8]) + (" …" if len(files) > 8 else ""))
    print(f"GOAL_ACK=OK → รัน goal verify {rel} ต่อ (ไม่ล้าง base/รอบ/ประวัติ · commit/ไฟล์ที่แก้หลังจากนี้ยังถูกตรวจตามปกติ)")
    return 0


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
    rounds_max = min(GOAL_ROUNDS_CAP, max(1, g["rounds"])) + int((st or {}).get("extra_rounds") or 0)  # + ที่ user ต่องบ (check --extend)
    if a.action == "cancel":
        return goal_cancel(root, goal, rel, g, st, sp, rounds_max, a, is_git)
    canc = goal_cancelled(goal, st)
    if canc and not (a.action == "check" and a.reset and not goal_cancel_note(goal)):  # ธงที่ยกเลิก = ไม่ตรวจ/ไม่วน/ไม่สร้างการ์ดใหม่
        label = canc.get("reason", "") if canc.get("src") == "file" else f"ยกเลิกโดย user ({canc.get('at', '')}) — {canc.get('reason', '')}"
        print(f"ธงนี้{label} · ไม่ตรวจ/ไม่วนต่อ")
        if a.action != "status":
            print(f"เปิดใหม่: ให้ user ยืนยันก่อน → ลบบรรทัด \"สถานะ: ยกเลิก…\" ใต้หัวไฟล์ GOAL (ถ้ามี) → `goal check {rel} --reset`")
        print(f"GOAL=CANCELLED {rel}")
        return 0 if a.action == "status" else 1
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
        old = st
        if not st or a.reset:
            st = {"goal": rel, "sig": g["sig"], "base": _git(root, "rev-parse", "HEAD"), "started": now(), "rounds": [], "owner": st.get("owner", {}) if st else {}}
            rounds_max = min(GOAL_ROUNDS_CAP, max(1, g["rounds"]))  # state ใหม่ = ไม่มีงบที่ต่อไว้
        if a.reset and old:  # ประวัติย่อข้ามการ reset → ยังรู้ว่าคนตรวจไม่ผ่านซ้ำ/ถอยหลังซ้ำ (เตือนพิจารณายกเลิก)
            ors = old.get("rounds") or []
            st["past"] = (list(old.get("past") or []) + [goal_round_brief(r, ors[k - 1] if k else None) for k, r in enumerate(ors)])[-30:]
        if a.extend or a.extend_hours:  # user ต่องบ: ไม่แตะ base/started/rounds/past
            if a.reset or not old:
                print("ต้องแก้: --extend ใช้กับธงที่เริ่มแล้วเท่านั้น และห้ามใช้คู่ --reset")
                print("GOAL_CHECK=FAIL")
                return 1
            if not (0 <= a.extend <= GOAL_ROUNDS_CAP and 0 <= a.extend_hours <= 24):
                print(f"ต้องแก้: --extend ได้ 0..{GOAL_ROUNDS_CAP} รอบ · --extend-hours ได้ 0..24 ชม. ต่อครั้ง")
                print("GOAL_CHECK=FAIL")
                return 1
            st["extra_rounds"] = int(st.get("extra_rounds") or 0) + a.extend
            st["extra_hours"] = float(st.get("extra_hours") or 0) + a.extend_hours
            rounds_max += a.extend
            print(f"ต่องบ +{a.extend} รอบ / +{a.extend_hours:g} ชม. (ต่อแล้วรวม {st['extra_rounds']} รอบ / {st['extra_hours']:g} ชม.) · base/รอบ/ประวัติเดิมคงไว้")
        st["owner"] = goal_owner() or st.get("owner") or {}
        sp.parent.mkdir(parents=True, exist_ok=True)
        write_json(sp, st)
        goal_publish(root, goal, rel, g, st, rounds_max)
        print(f"GOAL_CHECK=OK เกณฑ์ {len(g['items'])} ข้อ (เครื่องตรวจ {sum(1 for i in g['items'] if i['cmd'])}) · "
              f"งบ {rounds_max} รอบ / {g['hours'] + float(st.get('extra_hours') or 0):g} ชม. · ใช้ไปแล้ว {len(st['rounds'])} รอบ · base {st['base'][:9]}")
        return 0
    if not st:
        print(f"GOAL=STOP ยังไม่ได้รัน `goal check {rel}` (ต้องตรวจเป้าหมาย + จด base ก่อน)")
        return 1
    if a.action == "status":
        last = st["rounds"][-1] if st["rounds"] else None
        print(f"เป้าหมาย {rel} · เริ่ม {st['started']} (ผ่านไป {(_secs(st['started']) or 0) / 3600:.1f} ชม.) · รอบ {len(st['rounds'])}/{rounds_max} · base {st['base'][:9]}")
        if last:
            print(f"รอบล่าสุด {last['at']}: {last['verdict']} · ไม่ผ่าน {', '.join(last['fail']) or '-'}")
            for k, v in (last.get("human_res") or {}).items():
                print(f"คนตรวจ {k}: {'ผ่าน' if v['ok'] else 'ไม่ผ่าน — ' + v.get('reason', '')} ({v['at']})")
        stops = list((last or {}).get("stop") or [])
        if st.get("sig") != g["sig"] and not any("ย้ายเสาประตู" in s for s in stops):
            stops.append("เกณฑ์/ขอบเขตในไฟล์เป้าหมายถูกแก้หลังเริ่ม (ย้ายเสาประตู) → ให้ user ยืนยัน แล้ว `goal check --reset`")
        for s in stops:
            print(f"เบรก: {s}")
        warn = list((last or {}).get("warn") or [])
        if warn:
            print("เตือน: ไฟล์นอกขอบเขตที่อาจเป็นของ session อื่น (ไม่เบรก): " + ", ".join(warn[:8]) + (" …" if len(warn) > 8 else ""))
        for h in goal_stop_hints(stops, rel):
            print(h)
        ack = (st.get("acks") or [None])[-1]
        if ack:
            print(f"รับทราบล่าสุด {ack['at']}: {ack['reason']} ({len(ack.get('files') or [])} ไฟล์)")
        return 0
    if a.action == "human":
        return goal_human(root, goal, rel, g, st, sp, rounds_max, a)
    if a.action == "ack":
        return goal_ack(root, goal, rel, g, st, sp, rounds_max, a)
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
    cfg = project_cfg(root)
    free = [rel, (cfg.get("plan_dir") or "docs/plans").rstrip("/") + "/", ".flash.json", ".gitignore", ".tmp/"] + g["locked"]
    windows = goal_job_windows(root, goal.stem) if is_git else []
    ours, maybe = goal_changed_files(root, st["base"], st["started"], windows, goal_topic(goal.stem), g["files"] + free,
                                     ack=(st.get("acks") or [None])[-1]) if is_git else ([], [])
    out_scope = [f for f in ours if not _glob_hit(f, g["files"] + free)]
    warn = [f for f in maybe if not _glob_hit(f, g["files"] + free)]
    locked = [f for f in ours + maybe if g["locked"] and _glob_hit(f, g["locked"])]
    if locked:
        stop.append("ไฟล์ล็อก (เกณฑ์/เทสต์ตัดสิน) ถูกแก้: " + ", ".join(locked[:8]))
    if out_scope:
        stop.append("แก้ไฟล์นอกขอบเขต goal-files: " + ", ".join(out_scope[:8]) + (" …" if len(out_scope) > 8 else ""))
    fp = goal_work_fp(root, st["base"], free, windows) if is_git else ""
    prev = st["rounds"][-1] if st["rounds"] else None
    # ไม่มีงานใหม่ตั้งแต่รอบก่อน (ไฟล์/งาน Flash เหมือนเดิม · เกณฑ์ไม่ถูกแก้) = ตรวจซ้ำ → แทนผลรอบเดิม ไม่นับรอบใหม่
    recheck = bool(fp and prev and prev.get("fp") == fp and st.get("sig") == g["sig"])
    popped = st["rounds"].pop() if recheck else {}
    if recheck:
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
        hmax = g["hours"] + float(st.get("extra_hours") or 0)
        if hrs >= hmax:
            stop.append(f"เกินงบเวลา {hmax:g} ชม. (ผ่านไป {hrs:.1f})")
        verdict = "STOP" if stop else "CONTINUE"
    since = _ts(prev["at"]) if prev else _ts(st["started"]) - 5
    rnd = {"at": now(), "verdict": verdict, "fail": fail, "results": results, "out_scope": out_scope[:50], "locked": locked[:50],
           "stop": stop, "human": human, "warn": warn[:50], "fp": fp, "flash": sum(1 for a, _ in windows if a >= since),
           "out_scope_n": len(out_scope), "warn_n": len(warn)}  # เก็บแค่ 50 รายการ (เคยบวม 1.3MB เพราะโฟลเดอร์ untracked ทั้งโปรเจกต์)
    if recheck:
        rnd["flash"] = popped.get("flash", 0)
        rnd["rechecks"] = popped.get("rechecks", 0) + 1
        hres = popped.get("human_res") or {}
        if verdict == "DONE_NEEDS_USER" and hres:  # ผลคนตรวจของรอบเดิมยังใช้ได้ (งานไม่เปลี่ยน)
            rnd["human_res"] = hres
            if all(hres.get(i["id"], {}).get("ok") for i in g["items"] if not i["cmd"]):
                rnd["verdict"] = verdict = "DONE"
    st["rounds"].append(rnd)
    hint = goal_cancel_hint(st) if verdict not in ("DONE", "DONE_NEEDS_USER") else ""
    if hint:
        rnd["cancel_hint"] = hint
    st["owner"] = goal_owner() or st.get("owner") or {}
    write_json(sp, st)
    goal_publish(root, goal, rel, g, st, rounds_max)
    if recheck:
        print(f"ไม่มีงานใหม่ตั้งแต่รอบ {n} (ไฟล์และงาน Flash เหมือนเดิม) → ตรวจซ้ำ ไม่นับรอบเพิ่ม")
    if warn:
        print("เตือน: ไฟล์นอกขอบเขตที่อาจเป็นของ session อื่น (ไม่ได้มาจากงาน Flash ของเป้าหมายนี้ชัด ๆ · ไม่เบรก) — ตรวจดูเอง: "
              + ", ".join(warn[:8]) + (" …" if len(warn) > 8 else ""))
    if regress:
        print(f"ถอยหลัง: {', '.join(regress)} เคยผ่านรอบก่อนแต่รอบนี้ไม่ผ่าน → แผนรอบหน้าต้องแก้ตัวนี้ก่อน")
    for s in stop:
        print(f"เบรก: {s}")
    for h in goal_stop_hints(stop, rel):
        print(h)
    if human:
        print("ให้ user ตรวจเอง:\n  " + "\n  ".join(human))
        if recheck and verdict == "DONE_NEEDS_USER":
            print("ข้อคนตรวจ: ให้ user กด ✅/❌ ที่การ์ดในหน้าเว็บ flashq หรือสั่ง `goal human <GOAL> <G-xx> --pass|--fail \"เหตุ\"` (verify ซ้ำไม่ช่วย)")
    if hint:
        print(f"แนะนำ: พิจารณายกเลิกธง (flashq goal cancel {rel} --reason \"…\") — {hint} · ให้ user เลือก วนต่อ / ยกเลิกธง")
    left = rounds_max - n
    print(f"GOAL={verdict} รอบ {n}/{rounds_max} · ไม่ผ่าน {', '.join(fail) or '-'}" + (f" · เหลือ {left} รอบ" if verdict == "CONTINUE" else ""))
    return 0 if verdict in ("DONE", "DONE_NEEDS_USER", "CONTINUE") else 1


def main() -> int:
    for name in ("stdout", "stderr"):  # exe แบบหน้าต่างไม่มี console → stdout/stderr เป็น None · print/log ต้องไม่พัง
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pipe บน Windows = cp874 พังกับไทย/อีโมจิ
    HOME.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser(prog="flashq")
    sp = ap.add_subparsers(dest="cmd")
    r = sp.add_parser("run", help="ส่งงานเข้าคิว")
    r.add_argument("plan", nargs="?")
    r.add_argument("tasks", nargs="*", help="งาน เช่น T-00..T-02 · หลายก้อนเว้นวรรคหรือคั่น , ได้ (T-00 T-02 = T-00,T-02)")
    r.add_argument("--message", help="ส่งข้อความตรง (ทดสอบ) แทนคำสั่ง /flash")
    r.add_argument("--skip-precheck", action="store_true", help="ข้ามด่านตรวจแผนพิการ (path ไม่มีจริง · ข้อความ ก่อน: ไม่เจอ/เจอหลายที่)")
    r.set_defaults(kind="", prompt="")
    vf = sp.add_parser("verify", help="ส่งผู้ตรวจ (agent อ่านอย่างเดียว) เข้าคิว · ไม่ชนงานอื่นในตัวจัดคิว")
    vf.add_argument("plan")
    vf.add_argument("tasks", nargs="+", help="งานที่ตรวจ เช่น T-02 · หลายก้อนเว้นวรรคหรือคั่น , ได้")
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
        r.add_argument("--variant", help="ระดับความคิดของโมเดล (low/medium/high/max ตามที่โมเดลรองรับ) · ชนะค่า variants ใน .flash.json/config.json (ผู้สืบ=high ผู้ตรวจ=low งานทำ=ไม่ส่ง)")
        r.add_argument("--timeout-min", type=int, default=0, help="ค่าเริ่มต้นจาก .flash.json (480)")
        r.add_argument("--wait-min", type=float, default=720, help="รอคิวได้นานสุดกี่นาที")
        r.add_argument("--no-wait", action="store_true", help="คิวไม่ว่าง = จบทันที FLASH_RUN=BUSY")
        r.add_argument("--switch-on-quota", type=int, default=0, help="QUOTA แล้วสลับบัญชีถัดไปและสั่งซ้ำได้กี่ครั้ง")
        r.add_argument("--retry-nostart", type=int, default=2, help="NOSTART แล้วลองใหม่กี่ครั้ง")
        r.add_argument("--auto", action="store_true", help="อนุมัติ permission อัตโนมัติ (ยกเว้นที่ deny)")
        r.add_argument("--no-open", action="store_true", help="ไม่สั่ง desktop เปิด session ให้ (ปิดทั้งเครื่อง: config open_session off)")
        r.add_argument("--submitter", default="", help=argparse.SUPPRESS)  # ภายใน: --detach ใส่ให้ตอนส่งต่อ → ค่าเริ่มต้นไม่เปิดหน้าต่าง session
        r.add_argument("--detach", action="store_true", help="ส่งเข้าคิวแล้วคืนทันที ไม่รอจนงานจบ (สำหรับผู้สั่งที่รัน background ไม่ได้ เช่น opencode) · ผลดูด้วย inbox")
        r.set_defaults(fn=cmd_run)
    vf.set_defaults(attach="none")  # agent ที่เพิ่งติดตั้ง live server 4096 อาจยังไม่เห็น → รันแยกเป็นค่าเริ่มต้น
    inv.set_defaults(attach="none")
    vf.set_defaults(switch_on_quota=2)  # ผู้ตรวจ/ผู้สืบ: โควตาหมดย้าย provider (โมเดลเดิม) ให้เองได้ 2 ครั้ง
    inv.set_defaults(switch_on_quota=2)
    qa = sp.add_parser("qa", help="นักทดสอบ: รันชุดทดสอบของโปรเจกต์ (flashq รันคำสั่งเอง ตัดสินจาก exit code จริง) · ล้ม → Flash ช่วยอธิบายสาเหตุ")
    qa.add_argument("qa_names", nargs="*", metavar="ชุด", help="ชื่อชุดจาก .flash.json qa.presets (ไม่ระบุ = ทุกชุด)")
    qa.add_argument("--cmd", dest="qa_cmd", action="append", default=[], metavar="คำสั่ง", help="คำสั่งทดสอบเฉพาะกิจ (ใช้ซ้ำได้ · ชื่อชุด adhoc, adhoc2…) · ใช้ได้เฉพาะจาก CLI")
    qa.add_argument("--commit", dest="qa_commit", default="", help="ยืนยันว่า checkout อยู่ที่ commit นี้ (ไม่ตรง = ไม่ทดสอบ · ไม่สลับ commit ให้เอง)")
    qa.add_argument("--retry", type=int, default=None, help="ล้มแล้วรันซ้ำกี่ครั้ง (0-3 · ผ่านเฉพาะรอบหลังนับ FLAKY = ไม่ผ่าน) · ค่าเริ่มต้นตาม retry ของชุดนั้น (ไม่ตั้ง = 1) · --retry 0 = ไม่ลองซ้ำ")
    qa.add_argument("--fail-fast", action="store_true", help="ชุดหนึ่งไม่ผ่าน = ไม่รันชุดที่เหลือ")
    qa.add_argument("--no-analyze", action="store_true", help="ล้มแล้วไม่ต้องให้ Flash อ่าน log อธิบาย (ไม่เรียกโมเดลเลย)")
    qa.add_argument("--project", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd · worktree → checkout หลัก)")
    qa.add_argument("--title", default="", help="ชื่องานในคิว")
    qa.add_argument("--timeout-min", type=float, default=0, help="เวลาสูงสุดต่อชุด (ทับค่าในชุด/qa_timeout_min=30)")
    qa.add_argument("--variant", help="ระดับความคิดของ Flash ตอนอธิบาย (ค่าเริ่มต้น qa=high)")
    qa.add_argument("--wait-min", type=float, default=720, help="รอคิวได้นานสุดกี่นาที")
    qa.add_argument("--no-wait", action="store_true", help="คิวไม่ว่าง = จบทันที FLASH_RUN=BUSY")
    qa.set_defaults(fn=cmd_qa)
    sc = sp.add_parser("scope", help="ตรวจขอบเขตไฟล์ (กลไกล้วน): ไฟล์ที่ commit ของงาน T-xx แตะ ต้องอยู่ในรายการที่แผนอนุญาต · ยกเว้นเพิ่มที่ .flash.json scope.always_ok")
    sc.add_argument("plan")
    sc.add_argument("tasks", nargs="*", help="งานที่ตรวจ (ไม่ระบุ = ทุกงานในแผน)")
    sc.add_argument("--project", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd · worktree → checkout หลัก)")
    sc.add_argument("--fill", action="store_true", help="§4 ไม่มี hash จริง (เช่น HEAD) แต่หา commit เจอ และทุกงานผ่าน → เติม hash ลงช่อง commit ของแผน (ไม่ commit ให้)")
    sc.set_defaults(fn=cmd_scope)
    dc = sp.add_parser("doc", help="ช่างเอกสาร: Flash อัปเดตเอกสารให้ตรงกับโค้ดที่เปลี่ยน (แก้ไฟล์จริงเฉพาะ doc.presets.<ชื่อ>.paths · ตัดสินด้วยกลไก · ไม่ commit ให้ · รอคุณรับ/ทิ้ง)")
    dc.add_argument("doc_name", nargs="?", default="", metavar="ชุด", help="ชื่อชุดจาก .flash.json doc.presets (มีชุดเดียว = ไม่ต้องระบุ)")
    dc.add_argument("--since", default="", help="เทียบโค้ดที่เปลี่ยนตั้งแต่ commit/tag นี้ (ไม่ระบุ = ตั้งแต่ครั้งล่าสุดที่รับร่างของชุดนี้ · ไม่เคย = ให้ Flash ดูประวัติล่าสุดเอง)")
    dc.add_argument("--project", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd · worktree → checkout หลัก)")
    dc.add_argument("--title", default="", help="ชื่องานในคิว")
    dc.add_argument("--model", help="โมเดล (ค่าเริ่มต้นตาม agent flash-writer)")
    dc.add_argument("--timeout-min", type=float, default=0, help="เวลาสูงสุด (ทับค่าในชุด/doc_timeout_min=30)")
    dc.add_argument("--variant", help="ระดับความคิดของ Flash")
    dc.add_argument("--wait-min", type=float, default=720, help="รอคิวได้นานสุดกี่นาที")
    dc.add_argument("--no-wait", action="store_true", help="คิวไม่ว่าง = จบทันที FLASH_RUN=BUSY")
    dc.set_defaults(fn=cmd_doc, switch_on_quota=2)
    dr = sp.add_parser("doc-review", help="ตัดสินร่างของช่างเอกสาร: accept = เก็บไฟล์ไว้ (ไม่ commit ให้) · discard = ย้อนเฉพาะไฟล์ที่ช่างเอกสารแตะ")
    dr.add_argument("id")
    dr.add_argument("action", choices=["accept", "discard"])
    dr.add_argument("--force", action="store_true", help="discard ทั้งที่มีไฟล์ถูกแก้ต่อหลังช่างเอกสารจบ (งานแก้ต่อนั้นจะหาย)")
    dr.set_defaults(fn=cmd_doc_review)
    wy =sp.add_parser("why", help="งานที่รันอยู่เป็นอย่างไร: ปกติ/tool ค้าง/รอโมเดล (ไม่ระบุ id = ทุกงานที่รัน)")
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
    wt = sp.add_parser("wait", help="รอจนงานจบแล้วพิมพ์ FLASH_RUN=... (Claude รันใน background · ไม่ต้อง sleep/poll)")
    wt.add_argument("target", help="job id (ขึ้นต้น) หรือชื่อแผน/ไฟล์แผน (= ทุกงานของแผนนั้นที่ยังไม่จบ)")
    wt.add_argument("--timeout-min", type=float, default=480, help="รอได้นานสุด (นาที) · เกิน = FLASH_WAIT=TIMEOUT exit 3")
    wt.add_argument("--poll", type=float, default=15, help="เช็กทุกกี่วินาที")
    wt.set_defaults(fn=cmd_wait)
    ib = sp.add_parser("inbox", help="แสดงผลงานที่จบแล้วของโปรเจกต์นี้ (cwd) แล้วย้ายเข้า done — แทน hook สำหรับผู้สั่งที่ไม่ใช่ Claude Code")
    ib.set_defaults(fn=cmd_inbox)
    sw = sp.add_parser("sweep", help="แจ้ง (inbox/toast) งานที่ process ตายกลางคัน — hook inbox_notify เรียกให้เอง")
    sw.set_defaults(fn=cmd_sweep)
    sh = sp.add_parser("shrink", help="ย่อรูปใหญ่เป็น .tmp/shrink/<ชื่อ>.jpg ก่อนให้ Claude อ่าน (ประหยัด context)")
    sh.add_argument("images", nargs="+")
    sh.add_argument("--max", type=int, default=800, help="ด้านยาวสุด (px)")
    sh.add_argument("--quality", type=int, default=80)
    sh.add_argument("--out", default="", help="โฟลเดอร์ผล (ค่าเริ่มต้น <โปรเจกต์>/.tmp/shrink)")
    sh.set_defaults(fn=cmd_shrink)
    sw = sp.add_parser("switch", help="สลับบัญชีโมเดล flash-worker")
    sw.add_argument("target", nargs="?")
    sw.set_defaults(fn=cmd_switch)
    ins = sp.add_parser("install", help="ติดตั้ง /flash + agent (opencode) และ /flash-* + flash-checker + hooks (Claude) แบบ global")
    ins.add_argument("--force", action="store_true", help="ทับไฟล์ของผู้ใช้ที่ชื่อซ้ำ (สำรอง .bak-flashq ก่อน)")
    ins.add_argument("--hooks", action="store_true", help="ลงทะเบียน image_guard (PreToolUse Read) · inbox_notify (UserPromptSubmit) · run_guard (PreToolUse Bash|PowerShell) ใน ~/.claude/settings.json")
    ins.add_argument("--models", choices=["ask", "auto", "skip"], default="ask",
                     help="ตรวจโมเดลของทุกบทบาทบนเครื่องนี้: ask = ถามเลือกเมื่อขาด (ต้องมี TTY · ไม่มี = แค่บอกวิธีแก้) · auto = ใช้ตัวแนะนำ · skip = ไม่ตรวจ")
    ins.add_argument("--check", action="store_true", help="แค่เทียบว่าไฟล์ที่ติดตั้งไว้ล้าหลังต้นฉบับไหม (ไม่เขียนอะไร · exit 1 = ล้าหลัง/ยังไม่ติดตั้ง)")
    ins.set_defaults(fn=cmd_install)
    mo = sp.add_parser("models", help="แสดงโมเดลทั้งหมดที่เครื่องนี้มี แล้วเลือกว่าบทบาทไหน (ผู้ทำ/ผู้ตรวจ/ผู้สืบ/นักทดสอบ/ช่างเอกสาร) ใช้โมเดลอะไร")
    mo.add_argument("--list", action="store_true", help="แสดงรายการโมเดล + สถานะ ไม่เปลี่ยนอะไร")
    mo.add_argument("--auto", action="store_true", help="บทบาทที่ยังไม่ตั้ง/ใช้ไม่ได้ → ตั้งเป็นตัวแนะนำ (ที่ใช้ได้อยู่แล้วไม่แตะ)")
    mo.add_argument("--set", action="append", metavar="บทบาท=provider/model", help="ตั้งรายบทบาท (worker|verifier|investigator|tester|writer) ใส่ซ้ำได้")
    mo.add_argument("--all", metavar="provider/model", help="ตั้งทุกบทบาทเป็นโมเดลเดียว")
    mo.set_defaults(fn=cmd_models)
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
    cf = sp.add_parser("config", help="ดู/ตั้งค่า (max_parallel · schedule auto|fifo · starve_min · dead_clear_hours · open_session on|off|auto)")
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
    go = sp.add_parser("goal", help="โหมดเป้าหมาย (/flash-goal): check ไฟล์เป้าหมาย · verify เกณฑ์ + เบรก · status · cancel (user สั่งเลิกธง)")
    go.add_argument("action", choices=["check", "verify", "status", "human", "cancel", "ack"])
    go.add_argument("goal", help="ไฟล์เป้าหมาย เช่น docs/plans/GOAL_<เรื่อง>.md")
    go.add_argument("item", nargs="?", default="", help="human: ข้อคนตรวจ เช่น G-07")
    go.add_argument("--pass", dest="passed", action="store_true", help="human: ข้อนี้ผ่าน")
    go.add_argument("--fail", default="", help='human: ข้อนี้ไม่ผ่าน + เหตุ')
    go.add_argument("--reason", default="", help="cancel: เหตุที่ user สั่งเลิกธง (เขียนลงบรรทัดสถานะใต้หัวไฟล์ GOAL) · ack: เหตุที่ user ยอมรับไฟล์นอกขอบเขต/ไฟล์ล็อก")
    go.add_argument("--project", default="", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd · worktree → checkout หลัก)")
    go.add_argument("--reset", action="store_true", help="check: เริ่มนับใหม่ (base/รอบ/ลายนิ้วมือเกณฑ์) — ใช้เมื่อ user ยืนยันเกณฑ์ใหม่แล้ว")
    go.add_argument("--extend", type=int, default=0, help="check: ต่องบรอบ +N เก็บ base/รอบ/ประวัติ — ใช้เมื่อ user สั่งหลัง STOP ครบงบ")
    go.add_argument("--extend-hours", dest="extend_hours", type=float, default=0, help="check: ต่องบเวลา +H ชม.")
    go.set_defaults(fn=cmd_goal)
    us = sp.add_parser("usage", help="โทเคน Claude ต่อแผน: สแกน transcript ของ Claude Code (วางแผน · ตรวจ · รอบแก้) + USD โดยประมาณ")
    us.add_argument("target", nargs="?", default="", help="ไฟล์แผน PLAN_*.md หรือโฟลเดอร์โปรเจกต์ (= ทุกแผนที่ถูกพูดถึง) · ใช้กับ --flash = กรองเฉพาะโปรเจกต์นี้")
    us.add_argument("--flash", action="store_true", help="ดู token/USD ฝั่ง Flash (log ของงานที่รันผ่าน flashq + subagent ใน opencode.db) + ประมาณการประหยัดเทียบ Claude")
    us.add_argument("--since", type=float, default=30, help="ย้อนดู transcript กี่วัน (ค่าเริ่มต้น 30)")
    us.add_argument("--project", default="", help="รากโปรเจกต์ (ค่าเริ่มต้น = หาจาก git ของโฟลเดอร์แผน · worktree → checkout หลัก)")
    us.set_defaults(fn=cmd_usage)
    ui = sp.add_parser("ui", help="หน้าเว็บ dashboard ในเครื่อง (127.0.0.1)")
    ui.add_argument("--port", type=int, default=4097, help="0 = สุ่มพอร์ตว่าง")
    ui.add_argument("--no-open", action="store_true", help="ไม่เปิดเบราว์เซอร์ให้")
    ui.set_defaults(fn=cmd_ui)
    gu = sp.add_parser("gui", help="หน้าต่างแอป (ไม่ใช้เบราว์เซอร์ · ต้องมี pywebview)")
    gu.add_argument("--port", type=int, default=GUI_PORT, help=f"พอร์ตประจำของหน้าต่างแอป ({GUI_PORT} · คงที่เพื่อให้จำค่าที่ตั้งไว้ได้ · ถูกใช้อยู่จะสุ่มให้) · 0 = สุ่มพอร์ตว่าง")
    gu.set_defaults(fn=cmd_gui)
    if FROZEN and len(sys.argv) == 1 and Path(sys.argv[0]).stem.endswith("gui"):  # ดับเบิลคลิก flashq-gui.exe = เปิดหน้าต่างแอป
        sys.argv.append("gui")
    a = ap.parse_args()
    return a.fn(a) if a.cmd else cmd_status(a)  # ไม่ใส่คำสั่ง = status


if __name__ == "__main__":
    sys.exit(main())

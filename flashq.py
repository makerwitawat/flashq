"""flashq — ระบบกลางส่งงานให้ opencode (DeepSeek Flash) ทำแผน แบบมีคิว ใช้ได้ทุกโปรเจกต์

วงจร: Claude Code วางแผน T-xx (push เข้า remote) → `flashq run <แผน> <งาน>` (background)
→ เข้าคิวกลาง (ทีละงานทั้งเครื่อง เพราะทุกโปรเจกต์ใช้บัญชีโมเดลชุดเดียวกัน) → opencode `/flash <แผน> <งาน>`
→ จบ = พิมพ์ `FLASH_RUN=...` → Claude ตรวจต่อ

ที่เก็บ:
- โค้ด = โฟลเดอร์นี้ (repo flashq) · ข้อมูลตอนรัน = `%USERPROFILE%\\.flashq\\` (jobs/ logs/ running.lock) — ไม่อยู่ใน git ของโปรเจกต์ใด
- ค่าเฉพาะโปรเจกต์ = `.flash.json` ที่รากโปรเจกต์ (ไม่มี = ค่าเริ่มต้น DEFAULTS)

ใช้:
  python flashq.py run docs\\PLAN_X.md T-01..T-03 [--project <dir>]   ส่งงาน (รอคิวเอง)
  python flashq.py run --message "ตอบแค่คำว่า PONG"                   ทดสอบการเชื่อมต่อ
  python flashq.py [status] | list [--all] | log <id> | cancel <id>
  python flashq.py switch [next|<ชื่อย่อ>]                             สลับบัญชีโมเดล flash-worker
  python flashq.py install [--force]                                    ติดตั้งคำสั่ง /flash + agent แบบ global ให้ opencode
  python flashq.py ui [--port 4097] [--no-open]                         หน้าเว็บ dashboard (127.0.0.1 เท่านั้น)
ผลของ run: บรรทัด `FLASH_RUN=OK|FAIL|QUOTA|TIMEOUT|BUSY|NOSTART|QUEUE_TIMEOUT` · exit 0 = OK · 2 = BUSY (--no-wait) · 3 = รอคิวเกินเวลา · อื่น 1
"""
import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
JOBS, LOGS, LOCK = HOME / "jobs", HOME / "logs", HOME / "running.lock"
OC_CONFIG = Path(os.environ.get("FLASHQ_OPENCODE_CONFIG") or (Path.home() / ".config" / "opencode" / "opencode.json"))
LIVE_URL = "http://127.0.0.1:4096"
START_LIMIT_SEC = 180
QUOTA_RE = re.compile(r"\b(429|402)\b|rate.?limit|quota|insufficient|balance", re.I)
DEFAULTS = {
    "main_branch": "master",          # branch ที่ opencode ต้องอยู่ + ที่แผนต้องถูก push ไป
    "remote": "origin",
    "require_plan_in_remote": True,   # แผนต้องอยู่ใน <remote>/<main_branch> ก่อนส่ง
    "command": "flash",               # คำสั่ง opencode ที่เรียก (โปรเจกต์มีของตัวเองใน .opencode/command ได้)
    "timeout_min": 480,
}


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
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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
                       capture_output=True, text=True)
    if r.returncode != 0:
        return start.resolve(), False
    return Path(r.stdout.strip()).parent, True


def project_cfg(root: Path) -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(read_json(root / ".flash.json"))
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


def clear_stale_lock() -> None:
    if not LOCK.exists():
        return
    held = read_json(LOCK)
    if held and pid_alive(held.get("pid", 0), held.get("pid_start", 0)):
        return
    if read_json(LOCK) == held:  # ยังเป็นล็อกเดิมที่ตายแล้ว
        LOCK.unlink(missing_ok=True)


def acquire(job: dict, wait_min: float, no_wait: bool) -> str:
    """คืน "ok" | "busy" | "timeout" · FIFO ตาม created ของงานที่ยังมีชีวิต"""
    t0, last = time.time(), None
    key = (job["created"], job["id"])
    while True:
        clear_stale_lock()
        ahead = [j for j in jobs() if j.get("status") == "queued" and (j["created"], j["id"]) < key and live_state(j) == "queued"]
        if not ahead and not LOCK.exists():
            try:
                fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"id": job["id"], "pid": os.getpid(), "pid_start": proc_start(os.getpid()), "since": now()}, f, ensure_ascii=False)
                return "ok"
            except FileExistsError:
                pass
        held = read_json(LOCK)
        if no_wait:
            print(f"FLASH_RUN=BUSY มีงานอื่นทำอยู่ job={held.get('id', '?')} pid={held.get('pid', '?')}", flush=True)
            return "busy"
        pos = len(ahead) + (1 if LOCK.exists() else 0)
        if pos != last:
            print(f"QUEUED ตำแหน่ง {pos} (กำลังทำ: {held.get('id', '-')}) — รอคิว…", flush=True)
            last = pos
        if time.time() - t0 > wait_min * 60:
            print(f"FLASH_RUN=QUEUE_TIMEOUT รอคิวเกิน {wait_min:g} นาที", flush=True)
            return "timeout"
        time.sleep(3)


def release(job: dict) -> None:
    if read_json(LOCK).get("id") == job["id"]:
        LOCK.unlink(missing_ok=True)


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
    subprocess.Popen([*exe, "serve", "--port", "4096", "--hostname", "127.0.0.1"], cwd=str(HOME),
                     stdout=open(HOME / "live_server.log", "ab"), stderr=subprocess.STDOUT, creationflags=flags,
                     env={k: v for k, v in os.environ.items() if k != "OPENCODE_SERVER_PASSWORD"})
    for _ in range(30):
        time.sleep(1)
        if up():
            return True
    return False


def wait_session(p: subprocess.Popen, log: Path) -> str | None:
    """รอ sessionID ใน log · "" = process จบก่อน · None = ไม่ขึ้นใน START_LIMIT_SEC (เจอตอน desktop เพิ่งเปิดใหม่)"""
    for _ in range(START_LIMIT_SEC):
        if p.poll() is not None:
            return ""
        m = re.search(r'"sessionID":"(ses_[^"]+)"', log.read_text(encoding="utf-8", errors="replace"))
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


def run_once(job: dict, cmd: list[str], root: Path, attach: str, timeout_min: int, no_open: bool, attempt: int) -> dict:
    log = LOGS / f"{job['id']}_{attempt}.jsonl"
    err = LOGS / f"{job['id']}_{attempt}.err"
    job.setdefault("logs", []).append(str(log))
    save_job(job)
    print(f"START {job['id']} รอบ {attempt} title='{job['title']}' model={job.get('model') or '(ค่าเริ่มต้น config)'} "
          f"attach={attach or '-'} log={log}", flush=True)
    t0, status = time.time(), "OK"
    with open(log, "wb") as fo, open(err, "wb") as fe:
        p = subprocess.Popen(cmd, cwd=str(root), stdout=fo, stderr=fe)
        job["child_pid"] = p.pid
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
            try:
                rc = p.wait(timeout=max(1, timeout_min * 60 - (time.time() - t0)))
            except subprocess.TimeoutExpired:
                kill_tree(p.pid)
                p.wait()
                rc, status = -1, "TIMEOUT"

    session, texts, errors, tools = "", [], [], 0
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
        elif ev.get("type") == "error" or "error" in ev:
            errors.append(json.dumps(ev.get("error", ev), ensure_ascii=False)[:400])
    errtxt = err.read_text(encoding="utf-8", errors="replace")
    last = texts[-1] if texts else ""
    if status == "OK" and (rc != 0 or errors):
        status = "FAIL"
    if QUOTA_RE.search(" ".join(errors) + errtxt[-2000:] + last[-500:]) and (rc != 0 or errors or "FAIL: quota" in last):
        status = "QUOTA"
    return {"status": status, "rc": rc, "mins": (time.time() - t0) / 60, "tools": tools,
            "session": session, "errors": errors, "stderr": errtxt.strip()[-600:], "last": last}


# ---------- คำสั่ง ----------
def cmd_run(a) -> int:
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
            subprocess.run(["git", "-C", str(root), "fetch", "-q", cfg["remote"], cfg["main_branch"]], check=False)
            if subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{ref}:{plan}"],
                              capture_output=True).returncode != 0:
                print(f"FLASH_RUN=FAIL ไม่พบแผนใน {ref}: {plan} (push แผนก่อน)")
                return 1
        elif not (root / plan).exists():
            print(f"FLASH_RUN=FAIL ไม่พบไฟล์แผน: {root / plan}")
            return 1

    exe = opencode_cmd()
    if not exe:
        print("FLASH_RUN=FAIL ไม่พบคำสั่ง opencode ใน PATH")
        return 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jid = f"{ts}_{os.getpid()}"
    title = f"flash-test {ts}" if a.message else f"flash {Path(plan).stem} {a.tasks}"
    model = a.model or configured_model()
    job = {"id": jid, "project": str(root), "plan": plan, "tasks": a.tasks or "", "message": a.message or "",
           "title": title, "model": model, "status": "queued", "pid": os.getpid(),
           "pid_start": proc_start(os.getpid()), "created": now()}
    save_job(job)

    got = acquire(job, a.wait_min, a.no_wait)
    if got != "ok":
        job.update(status="busy" if got == "busy" else "queue_timeout", finished=now())
        save_job(job)
        return 2 if got == "busy" else 3

    res = {"status": "FAIL", "rc": -1}
    try:
        job.update(status="running", started=now())
        save_job(job)
        attach = LIVE_URL if a.attach == "live" else ("" if a.attach == "none" else a.attach)
        if attach == LIVE_URL and not ensure_live_server(exe):
            print("WARN: เปิด server 4096 ไม่ขึ้น → รันแยก (ดูสดไม่ได้)", flush=True)
            attach = ""
        timeout_min = a.timeout_min or cfg["timeout_min"]
        switches, nostart_retry, attempt = 0, a.retry_nostart, 0
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
            cmd += ["--", a.message] if a.message else ["--command", cfg["command"], "--", plan, a.tasks]
            res = run_once(job, cmd, root, attach, timeout_min, a.no_open, attempt)
            if res["status"] == "NOSTART" and nostart_retry > 0:
                nostart_retry -= 1
                print("NOSTART → ลองใหม่อัตโนมัติ 1 ครั้ง", flush=True)
                continue
            if res["status"] == "QUOTA" and not a.model and switches < a.switch_on_quota:
                switches += 1
                new = switch_account("next")
                if new and new != job["model"]:
                    print(f"QUOTA → สลับบัญชีเป็น {new} แล้วสั่งงานเดิมซ้ำ (ครั้งที่ {switches})", flush=True)
                    job["model"] = new
                    continue
            break
    finally:
        job.update(status=res["status"].lower(), result=res.get("status"), rc=res.get("rc"),
                   finished=now(), last=(res.get("last") or "")[-1500:])
        save_job(job)
        release(job)

    print(f"FLASH_RUN={res['status']} exit={res['rc']} เวลา={res['mins']:.1f} นาที tool={res['tools']} "
          f"session={res['session']} job={jid}")
    print(f"desktop: โปรเจกต์ {root.name} > session '{title}'")
    for e in res["errors"][-3:]:
        print("ERROR:", e)
    if res["stderr"]:
        print("STDERR(ท้าย):", res["stderr"])
    print("---- สรุปท้ายจาก opencode ----")
    print(res["last"][-2500:] if res["last"] else "(ไม่มีข้อความ)")
    return 0 if res["status"] == "OK" else 1


def cmd_list(a) -> int:
    rows = jobs()
    if not a.all:
        rows = [j for j in rows if live_state(j) in ("queued", "running")] or rows[-10:]
    if not rows:
        print("(ยังไม่มีงาน)")
        return 0
    for j in rows:
        what = j.get("message") and "--message" or f"{j.get('plan')} {j.get('tasks')}"
        print(f"{j['id']:24} {live_state(j):13} {Path(j.get('project', '')).name:18} {what}"
              f"  [{j.get('created', '')}{' → ' + j['finished'] if j.get('finished') else ''}]")
    return 0


def cmd_status(a) -> int:
    clear_stale_lock()
    held = read_json(LOCK)
    q = [j for j in jobs() if live_state(j) == "queued"]
    print(f"กำลังทำ: {held.get('id', '-')}" + (f" (pid {held['pid']} ตั้งแต่ {held.get('since')})" if held else ""))
    print(f"รอคิว: {len(q)} งาน")
    for i, j in enumerate(q, 1):
        print(f"  {i}. {j['id']} {Path(j['project']).name} {j.get('plan') or '--message'} {j.get('tasks', '')}")
    print(f"บัญชี flash-worker: {configured_model() or '(ยังไม่ตั้ง)'}")
    return 0


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


def cancel_job(j: dict) -> tuple[bool, str]:
    """ยกเลิกงานที่รอคิว/กำลังทำ (ใช้ร่วมกับ cmd_cancel และหน้า ui)"""
    if live_state(j) not in ("queued", "running"):
        return False, f"job {j['id']} ไม่ได้ทำงานอยู่ (สถานะ {live_state(j)})"
    kill_tree(j["pid"])
    if j.get("child_pid"):
        kill_tree(j["child_pid"])
    j.update(status="cancelled", finished=now())
    save_job(j)
    release(j)
    return True, f"ยกเลิก {j['id']} แล้ว"


def cmd_cancel(a) -> int:
    j = find_job(a.id)
    if not j:
        return 1
    ok, msg = cancel_job(j)
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
    OC_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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


# ---------- หน้าเว็บ dashboard (ui) ----------
def _secs(a: str, b: str = "") -> int | None:
    """จำนวนวินาทีจาก a ถึง b (ว่าง = ตอนนี้)"""
    try:
        t0 = datetime.strptime(a, "%Y-%m-%d %H:%M:%S")
        t1 = datetime.strptime(b, "%Y-%m-%d %H:%M:%S") if b else datetime.now()
        return int((t1 - t0).total_seconds())
    except (TypeError, ValueError):
        return None


def ui_state() -> dict:
    """สถานะทั้งหมดสำหรับ /api/state — อ่านผ่านฟังก์ชันคิวเดิม (ไม่เขียนตรรกะคิวซ้ำ)"""
    clear_stale_lock()
    held = read_json(LOCK)
    running, queued, history = None, [], []
    for j in jobs():
        st = live_state(j)
        row = {k: j.get(k, "") for k in ("id", "project", "plan", "tasks", "message", "title", "model",
                                         "created", "started", "finished", "session", "result", "rc")}
        row.update(state=st, project_name=Path(j.get("project", "")).name, attempts=len(j.get("logs") or []))
        if st == "running" and (not held or held.get("id") == j["id"]):
            row["elapsed_sec"] = _secs(j.get("started", ""))
            running = row
        elif st == "queued":
            row["wait_sec"] = _secs(j.get("created", ""))
            queued.append(row)
        else:
            row["duration_sec"] = _secs(j.get("started") or j.get("created", ""), j.get("finished", ""))
            history.append(row)
    for i, row in enumerate(queued, 1):
        row["position"] = i
    agent, accs = accounts()
    cfg = read_json(OC_CONFIG)
    providers = cfg.get("provider", {})
    acc_rows = [{"short": s, "model": m, "available": m.partition("/")[2] in providers.get(m.partition("/")[0], {}).get("models", {})}
                for s, m in accs]
    return {"now": now(), "lock": held, "running": running, "queued": queued, "history": history[::-1][:300],
            "agent": agent, "current_model": configured_model(), "accounts": acc_rows,
            "projects": sorted({r["project_name"] for r in history + queued + ([running] if running else []) if r["project_name"]})}


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
            if path == "/api/switch":
                import contextlib
                import io
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    new = switch_account(str(body.get("target") or "next"))
                return self._send(200 if new else 400, {"ok": bool(new), "model": new, "message": buf.getvalue().strip()})
            return self._send(404, {"error": "ไม่พบ"})

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    return srv, token


def cmd_ui(a) -> int:
    try:
        srv, _ = make_ui_server(a.port)
    except OSError as e:
        print(f"FAIL: เปิดพอร์ต {a.port} ไม่ได้ ({e}) — ลอง --port อื่น")
        return 1
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


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # pipe บน Windows = cp874 พังกับไทย/อีโมจิ
    HOME.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser(prog="flashq")
    sp = ap.add_subparsers(dest="cmd")
    r = sp.add_parser("run", help="ส่งงานเข้าคิว")
    r.add_argument("plan", nargs="?")
    r.add_argument("tasks", nargs="?")
    r.add_argument("--project", help="โฟลเดอร์โปรเจกต์ (ค่าเริ่มต้น = cwd · worktree → checkout หลัก)")
    r.add_argument("--message", help="ส่งข้อความตรง (ทดสอบ) แทนคำสั่ง /flash")
    r.add_argument("--attach", default="live", help="live (ค่าเริ่มต้น) = server 4096 ให้ desktop ดูสด · none = รันแยก · หรือ url")
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
    ui = sp.add_parser("ui", help="หน้าเว็บ dashboard ในเครื่อง (127.0.0.1)")
    ui.add_argument("--port", type=int, default=4097, help="0 = สุ่มพอร์ตว่าง")
    ui.add_argument("--no-open", action="store_true", help="ไม่เปิดเบราว์เซอร์ให้")
    ui.set_defaults(fn=cmd_ui)
    a = ap.parse_args()
    return a.fn(a) if a.cmd else cmd_status(a)  # ไม่ใส่คำสั่ง = status


if __name__ == "__main__":
    sys.exit(main())

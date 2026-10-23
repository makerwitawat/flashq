"""ยามส่งงาน flashq ของ Claude Code — flashq:managed (ติดตั้งโดย `flashq.py install` · ต้นฉบับ {{FLASHQ}}/hooks/)

ทำไม: คำสั่งส่งงาน (`flashq run` · wrapper ของโปรเจกต์เช่น `flash_run.py` · `investigate` · `verify` · `qa` · `doc` · `goal` · `wait`)
ต้องรันด้วย Bash/PowerShell แบบ `run_in_background: true` **ตรง ๆ** — ตอนคำสั่งนั้นจบ ระบบถึงจะปลุก session ให้ไป /flash-check
เคยพลาดจริง (2026-10-23): session สั่ง `flash_run.py … &` แล้วต่อ `sleep 30; head` เพื่อแอบดูบรรทัด QUEUED → background task ที่ระบบเฝ้า
คือ `sleep 30` ซึ่งจบใน 30 วิ · งาน Flash ยังรอคิว/รันต่อโดยไม่มีใครเฝ้า → session นิ่งรอแจ้งเตือนที่ไม่มีวันมา

ลงทะเบียนเป็น PreToolUse (matcher `Bash|PowerShell`) ใน ~/.claude/settings.json ด้วย `flashq.py install --hooks` · บล็อก (exit 2) เมื่อ:
  1. คำสั่งส่งงานแต่ไม่ได้ตั้ง run_in_background: true (ยกเว้น --help · `wait --timeout-min` ≤ 1)
  2. คำสั่งส่งงานมี `&` ท้ายคำสั่ง · nohup · setsid · disown · Start-Process · Start-Job · start /b (หลอกให้ระบบเฝ้าผิดตัว)
  3. คำสั่งส่งงานมี sleep · Start-Sleep · timeout (วนรอ/แอบดูผล) หรือต่อท่อไป head · tail · Select-Object (ตัดผล/ฆ่า process)
ผ่านแล้วแทรกคำเตือนสั้น ๆ ให้ Claude "หยุดนิ่งรอแจ้งเตือน ห้าม poll"
ตั้งค่า: ~/.flashq/config.json  {"run_guard": false} ปิดถาวร · {"run_guard_wrappers": ["flash_run.py", "..."]} ชื่อสคริปต์ wrapper ของโปรเจกต์ (นับเป็น `run`)
ปิดชั่วคราว (60 นาที): สร้างไฟล์ ~/.flashq/run_guard_off
ทุกครั้งที่บล็อกจดลง ~/.flashq/run_guard.log (jsonl: เวลา · เหตุ · คำสั่ง) ไว้ไล่ดูว่าบล็อกผิดไหม
พังเองไม่ว่ากรณีใด = ปล่อยผ่าน (exit 0) ห้ามขวางงานผู้ใช้ · ทดสอบ: python run_guard.py test "<คำสั่ง>" [--bg]
"""
import json
import os
import re
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
FLASHQ = "{{FLASHQ}}"
SUBCMDS = {"run", "wait", "investigate", "verify", "qa", "doc", "goal"}
WRAPPERS = ("flash_run.py",)
OFF_SEC = 3600
DETACH = {"nohup", "setsid", "disown", "start-process", "start-job", "saps"}
POLL = {"sleep", "start-sleep", "timeout"}
CUT = {"head", "tail", "select-object", "select"}
OPS = (";", "&&", "||", "|", "&", "\n")


def config() -> dict:
    try:
        return json.loads((HOME / "config.json").read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def scan(cmd: str) -> list[tuple[str, str]]:
    """แยกคำสั่งเป็น token ที่รู้จักเครื่องหมายคำพูด: ('w', คำ) หรือ ('op', ตัวต่อ)
    · `&` ที่เป็นส่วนของ `2>&1` `>&2` `&>` ไม่นับเป็นตัวต่อ · `&&` `||` แยกจาก `&` `|`"""
    out: list[tuple[str, str]] = []
    word: list[str] = []
    has_word = False
    quote = ""
    heredocs: list[str] = []  # แท็กของ heredoc ที่รอตัดเนื้อหาเมื่อขึ้นบรรทัดใหม่ (เนื้อหา = ข้อความ ไม่ใช่คำสั่ง)
    i, n = 0, len(cmd)

    def flush():
        nonlocal word, has_word
        if has_word:
            out.append(("w", "".join(word)))
        word, has_word = [], False

    while i < n:
        c = cmd[i]
        if quote:
            if c == quote:
                quote = ""
            else:
                word.append(c)
            i += 1
            continue
        if c in "\"'":
            quote, has_word = c, True
            i += 1
            continue
        if c in " \t\r":
            flush()
            i += 1
            continue
        if c == "<" and cmd[i:i + 2] == "<<" and cmd[i:i + 3] != "<<<":
            m = re.match(r"""<<-?[ \t]*(?:'([^']*)'|"([^"]*)"|([A-Za-z_][A-Za-z0-9_]*))""", cmd[i:])
            if m:
                heredocs.append(m.group(1) or m.group(2) or m.group(3) or "")
                i += m.end()
                continue
        if c == "\n" and heredocs:
            flush()
            out.append(("op", "\n"))
            i += 1
            for tag in heredocs:
                while i < n:
                    j = cmd.find("\n", i)
                    line = cmd[i:] if j < 0 else cmd[i:j]
                    i = n if j < 0 else j + 1
                    if line.strip() == tag:
                        break
            heredocs = []
            continue
        two = cmd[i:i + 2]
        if two in ("&&", "||"):
            flush()
            out.append(("op", two))
            i += 2
            continue
        if c in ";\n|":
            flush()
            out.append(("op", c))
            i += 1
            continue
        if c == "&":
            prev = cmd[i - 1] if i else ""
            nxt = cmd[i + 1] if i + 1 < n else ""
            if prev == ">" or nxt == ">":
                word.append(c)
                has_word = True
            else:
                flush()
                out.append(("op", "&"))
            i += 1
            continue
        word.append(c)
        has_word = True
        i += 1
    flush()
    return out


def statements(tokens: list[tuple[str, str]]) -> list[tuple[list[str], str, str]]:
    """แบ่งเป็น (คำในคำสั่ง, ตัวต่อท้าย, ตัวต่อหน้า) · `&` ที่อยู่ต้นคำสั่ง (call operator ของ PowerShell) ไม่นับเป็นตัวต่อ"""
    res: list[tuple[list[str], str, str]] = []
    cur: list[str] = []
    before = ""
    for kind, val in tokens:
        if kind == "w":
            cur.append(val)
        elif val == "&" and not cur:
            continue
        else:
            res.append((cur, val, before))
            cur, before = [], val
    res.append((cur, "", before))
    return res


def base(tok: str) -> str:
    return re.split(r"[\\/]", tok)[-1].lower()


def job_kind(words: list[str], wrappers: tuple[str, ...]) -> str:
    """คำสั่งนี้คือการส่ง/รองาน flashq ไหม → ชื่อคำสั่งย่อย ('run' ฯลฯ) · ไม่ใช่ = ''"""
    for i, w in enumerate(words):
        b = base(w)
        if b in wrappers:
            return "run"
        if b in ("flashq", "flashq.py"):
            for x in words[i + 1:]:
                if not x.startswith("-"):
                    return x if x in SUBCMDS else ""
            return ""
    return ""


def opt_value(words: list[str], name: str) -> float | None:
    for i, w in enumerate(words):
        if w == name and i + 1 < len(words):
            try:
                return float(words[i + 1])
            except ValueError:
                return None
        if w.startswith(name + "="):
            try:
                return float(w.split("=", 1)[1])
            except ValueError:
                return None
    return None


def judge(command: str, background: bool, cfg: dict) -> tuple[str, str]:
    """คืน ('block', เหตุผล) · ('warn', คำเตือนที่แทรกให้ Claude) · ('', '') = ไม่เกี่ยว"""
    wrappers = tuple(w.lower() for w in (cfg.get("run_guard_wrappers") or ())) + WRAPPERS
    stmts = statements(scan(command))
    jobs = [(i, job_kind(s[0], wrappers)) for i, s in enumerate(stmts)]
    jobs = [(i, k) for i, k in jobs if k]
    if not jobs:
        # Start-Process python -ArgumentList 'flashq.py run …' → คำสั่งส่งงานซ่อนอยู่ในเครื่องหมายคำพูดของคำสั่งแยก process
        low = [base(w) for s in stmts for w in s[0]]
        launcher = any(w in DETACH for w in low) or any(s[0] and base(s[0][0]) == "start" for s in stmts)
        names = "|".join(re.escape(w) for w in ("flashq.py", "flashq") + wrappers)
        wrap_names = "|".join(re.escape(w) for w in wrappers)
        if launcher and re.search(rf"(?:{names})\b[^\n]*?\b(?:run|wait|investigate|verify|qa|doc|goal)\b|(?:{wrap_names})", command, re.I):
            return "block", "  ✗ ใช้ nohup / setsid / Start-Process / Start-Job / start ส่งงาน flashq — แยก process ออกจากที่ระบบเฝ้า"
        return "", ""
    if any(w in ("--help", "-h") for i, _ in jobs for w in stmts[i][0]):
        return "", ""
    bad: list[str] = []
    kinds = {k for _, k in jobs}
    words_all = [w for s in stmts for w in s[0]]
    if not background:
        short_wait = kinds == {"wait"} and (opt_value(words_all, "--timeout-min") or 99) <= 1
        if not short_wait:
            bad.append("ไม่ได้ตั้ง run_in_background: true — คำสั่งนี้รอจนงานจบ (นานเกินเพดานเวลาของ tool) และระบบจะไม่ปลุก session ตอนงานจบ")
    if any(op == "&" for _, op, _ in stmts):
        bad.append("มี `&` ท้ายคำสั่ง — ระบบจะเฝ้าแค่ shell ที่จบทันที ไม่ได้เฝ้างาน (ให้ใช้ run_in_background: true อย่างเดียว ไม่ต้องใส่ &)")
    low = [base(w) for w in words_all]
    if any(w in DETACH for w in low) or any(
            s[0] and base(s[0][0]) == "start" for s in stmts):
        bad.append("ใช้ nohup / setsid / disown / Start-Process / Start-Job / start — แยก process ออกจากที่ระบบเฝ้า")
    if any(w in POLL for w in low):
        bad.append("มี sleep / Start-Sleep / timeout — ห้ามวนรอหรือแอบดูผล (คำสั่งจะจบเร็วกว่างาน แล้วระบบแจ้ง \"จบ\" ผิดตัว)")
    for i, (words, op, _) in enumerate(stmts):
        if op == "|" and i + 1 < len(stmts) and stmts[i + 1][0] and base(stmts[i + 1][0][0]) in CUT:
            bad.append("ต่อท่อไป head / tail / Select-Object — ตัดผลกลางคัน (บางที process ตายด้วย) ให้อ่านผลจากไฟล์ output ของ background task แทน")
            break
    if bad:
        return "block", "\n".join(f"  ✗ {b}" for b in bad)
    if kinds - {"wait"}:
        return "warn", ("flashq: งานนี้เดินใน background — ห้าม sleep / poll / `flashq status` วน · หยุดนิ่งรอแจ้งเตือนว่าคำสั่งจบ "
                        "(ได้บรรทัด FLASH_RUN=…) แล้วค่อย /flash-check · ติดคิว (QUEUED) ก็รอต่อ ไม่ต้องส่งซ้ำ")
    return "", ""


def block_text(reason: str) -> str:
    return (f"ยามส่งงาน flashq: คำสั่งนี้เสี่ยงที่จะ \"ไม่มีใครเฝ้างาน\" → บล็อก\n{reason}\n"
            "วิธีที่ถูก: เรียก Bash/PowerShell ด้วย run_in_background: true แล้วใส่คำสั่งตรง ๆ ตัวเดียว เช่น\n"
            "  python " + FLASHQ + "/flashq.py run <แผน> T-01..T-NN --switch-on-quota 4\n"
            "แล้วหยุดนิ่งรอแจ้งเตือนจากระบบ (ไม่ต้องใส่ & ไม่ต้อง sleep ไม่ต้องต่อ head) · อยากรู้ว่าติดคิวไหม = อ่านไฟล์ output ของ background task\n"
            "งานที่ส่งไปแล้วและยังรออยู่: รัน `python " + FLASHQ + "/flashq.py wait <job>` ด้วย run_in_background: true\n"
            "ถ้าคำสั่งนี้ไม่ใช่การส่งงานจริง (บล็อกผิด): บอกผู้ใช้ — ประวัติการบล็อกอยู่ที่ " + str(HOME / "run_guard.log") + " · ลองตัดสินคำสั่งเองได้ด้วย python <hooks>/run_guard.py test \"<คำสั่ง>\" [--bg]\n"
            "ปิดยามชั่วคราว 60 นาที (เฉพาะผู้ใช้สั่ง): สร้างไฟล์ " + str(HOME / "run_guard_off"))


def log_block(command: str, reason: str) -> None:
    """จดทุกครั้งที่บล็อกลง ~/.flashq/run_guard.log (jsonl) — บล็อกผิดจะได้ไล่ดูย้อนหลังได้ · เกิน 100 KB เหลือ 200 บรรทัดท้าย · พังเงียบ ๆ"""
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        path = HOME / "run_guard.log"
        row = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "reason": reason.splitlines()[0][:200] if reason else "", "command": command[:500]}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if path.stat().st_size > 100_000:
            lines = path.read_text(encoding="utf-8").splitlines()[-200:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def disabled(cfg: dict) -> bool:
    if cfg.get("run_guard") is False:
        return True
    off = HOME / "run_guard_off"
    try:
        return off.exists() and time.time() - off.stat().st_mtime < OFF_SEC
    except Exception:
        return False


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "test":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        verdict, text = judge(sys.argv[2], "--bg" in sys.argv[3:], config())
        print(f"{verdict or 'ผ่าน'}\n{text}".rstrip())
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if data.get("tool_name") not in ("Bash", "PowerShell"):
            return 0
        cfg = config()
        if disabled(cfg):
            return 0
        ti = data.get("tool_input") or {}
        verdict, text = judge(str(ti.get("command") or ""), ti.get("run_in_background") is True, cfg)
        if verdict == "block":
            log_block(str(ti.get("command") or ""), text)
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            print(block_text(text), file=sys.stderr)
            return 2
        if verdict == "warn":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}, ensure_ascii=False))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

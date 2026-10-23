"""ยามมอบงานสืบของ Claude Code — flashq:managed (ติดตั้งโดย `flashq.py install` · ต้นฉบับ {{FLASHQ}}/hooks/)

ทำไม: ผู้ใช้สั่ง "ส่งสืบ / ให้ flash สืบ" แต่ Claude แย่งไล่โค้ดเอง (Read/Grep วนหลายสิบครั้ง) กินโควตา Claude ทั้งที่โควตา DeepSeek มากกว่ามาก
กฎใน /flash-investigate เป็นแค่ข้อความ — มีผลเมื่อคำสั่งถูกเรียกเท่านั้น · ยามนี้ทำให้ทำงานระดับเครื่อง ไม่ผูกกับกฎของโปรเจกต์ใด

ลงทะเบียนด้วย `flashq.py install --hooks` สองจุด (ไฟล์เดียว สองโหมด):
  prompt  (UserPromptSubmit) = ข้อความผู้ใช้บอกให้ส่งสืบ → แทรกคำสั่ง "เรียก /flash-investigate ห้ามไล่โค้ดเอง" + ตั้งงบอ่านโค้ด
  pretool (PreToolUse: Read|Grep|Glob|Bash|PowerShell) = ระหว่างที่ตั้งงบไว้ นับการอ่านโค้ด (Read · Grep · Glob · grep/rg/cat/head/tail… ใน Bash)
      เกินงบ = บล็อก (exit 2) บอกให้ส่งผู้สืบ · เห็นคำสั่ง `flashq investigate` = ส่งแล้ว เหลืองบ 2 ครั้งไว้ยืนยันต้นตอหลังผลมา
ข้อความผู้ใช้ถัดไปที่ไม่ได้สั่งส่งสืบ = ปลดงบ (คุยต่อ/ให้แก้โค้ดได้เต็มที่) · งบหมดอายุเองใน 60 นาที
ไม่นับ: ไฟล์กติกา/แผน/บรีฟ (AGENTS.md · CLAUDE.md · .flash.json · docs/plans · .tmp · ~/.flashq · memory) — ใช้เขียนบรีฟได้
ตั้งค่า: ~/.flashq/config.json {"delegate_guard": false} ปิดถาวร · {"delegate_reads": 3} งบอ่านก่อนส่งผู้สืบ (ค่าตั้งต้น 3)
ปิดชั่วคราว (60 นาที): สร้างไฟล์ ~/.flashq/delegate_guard_off · จดทุกครั้งที่บล็อกลง ~/.flashq/delegate_guard.log
พังเองไม่ว่ากรณีใด = ปล่อยผ่าน (exit 0) ห้ามขวางงานผู้ใช้ · ทดสอบ: python delegate_guard.py test "<ข้อความผู้ใช้>"
"""
import json
import os
import re
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
FLASHQ = "{{FLASHQ}}"
STATE_DIR = HOME / "delegate"
TTL_SEC = 3600
DEFAULT_READS = 3
AFTER_SENT_READS = 2

# ผู้ใช้สั่งให้ Flash/DeepSeek/ผู้สืบ ทำงานสืบ (ไม่จับคำว่า "สืบ" เดี่ยว ๆ — กว้างเกินไป)
INTENT_RE = re.compile(
    r"ส่ง\s*(?:ไป)?\s*สืบ|ส่ง\s*(?:ให้\s*)?(?:flash|deepseek|ดีพซีค|ผู้สืบ)|"
    r"(?:ให้|เรียก|ใช้)\s*(?:flash|deepseek|ดีพซีค|ผู้สืบ)[^\n]{0,16}(?:สืบ|ตามหา|ไล่หา|ไล่ดู|investigate)|"
    r"\bflash[- ]?investigat|ผู้สืบ", re.I)
READERS = {"grep", "rg", "cat", "head", "tail", "sed", "awk", "findstr", "select-string", "get-content", "gc", "type", "find", "fd", "less", "more"}
SKIP_PATH_RE = re.compile(r"(?:^|[\\/])(?:AGENTS\.md|CLAUDE\.md|\.flash\.json)$|[\\/](?:docs[\\/]plans|\.tmp|\.flashq|memory|scratchpad|tasks)[\\/]|PLAN_FLASH_", re.I)


def config() -> dict:
    try:
        return json.loads((HOME / "config.json").read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def disabled(cfg: dict) -> bool:
    if cfg.get("delegate_guard") is False:
        return True
    off = HOME / "delegate_guard_off"
    try:
        return off.exists() and time.time() - off.stat().st_mtime < TTL_SEC
    except Exception:
        return False


def state_path(session: str) -> Path:
    return STATE_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", session or "nosession") + ".json")


def load_state(session: str) -> dict:
    try:
        st = json.loads(state_path(session).read_text(encoding="utf-8"))
        return st if time.time() - float(st.get("at") or 0) < TTL_SEC else {}
    except Exception:
        return {}


def save_state(session: str, st: dict | None) -> None:
    p = state_path(session)
    try:
        if not st:
            p.unlink(missing_ok=True)
            return
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(st), encoding="utf-8")
        for old in STATE_DIR.glob("*.json"):  # เก็บกวาดของ session เก่า
            if time.time() - old.stat().st_mtime > 2 * 86400:
                old.unlink(missing_ok=True)
    except Exception:
        pass


def wants_delegate(prompt: str) -> bool:
    return bool(INTENT_RE.search(prompt or ""))


def first_words(cmd: str) -> str:
    """คำแรกของแต่ละคำสั่งย่อยใน Bash/PowerShell (คั่นด้วย ; && || | newline) — ใช้ดูว่าเป็นคำสั่งอ่านไฟล์ไหม"""
    return " ".join((re.split(r"\s+", s.strip(), maxsplit=1)[0] or "").lower() for s in re.split(r";|&&|\|\||\||\n", cmd) if s.strip())


def classify(tool: str, ti: dict) -> str:
    """'sent' = ส่งผู้สืบแล้ว · 'read' = อ่านโค้ดเอง (นับงบ) · '' = ไม่เกี่ยว/ไม่นับ"""
    if tool in ("Bash", "PowerShell"):
        cmd = str(ti.get("command") or "")
        if re.search(r"flashq(?:\.py)?[\"']?\s+(?:--?\S+\s+)*investigate\b", cmd):
            return "sent"
        return "read" if set(first_words(cmd).split()) & READERS else ""
    if tool in ("Read", "Grep", "Glob"):
        target = str(ti.get("file_path") or ti.get("path") or "")
        return "" if target and SKIP_PATH_RE.search(target) else "read"
    return ""


def block_text(left_total: int) -> str:
    return ("ยามมอบงานสืบ: ผู้ใช้สั่งให้ส่งงานสืบให้ Flash — Claude ห้ามไล่โค้ดเอง (Read/Grep/grep ใน Bash เกินงบ " + str(left_total) + " ครั้งแล้ว)\n"
            "ทำตอนนี้: เรียก /flash-investigate (Skill) เขียนบรีฟ 4 ช่องจากสิ่งที่รู้แล้ว แล้วส่งผู้สืบ · ข้อมูลที่ขาด = ใส่ในบรีฟให้ผู้สืบหา ไม่ใช่ Claude เปิดดูเอง\n"
            "ส่งแล้วหยุดนิ่งรอแจ้งเตือน · พอผลมา Claude เปิดโค้ดยืนยันต้นตอหลักได้อีก 2 ครั้ง · ผลไม่พอ = ส่งผู้สืบรอบใหม่\n"
            "ถ้าบล็อกผิด (ผู้ใช้ไม่ได้สั่งส่งสืบ): บอกผู้ใช้ — ประวัติ " + str(HOME / "delegate_guard.log") + " · ปิดชั่วคราว 60 นาที (เฉพาะผู้ใช้สั่ง): สร้างไฟล์ " + str(HOME / "delegate_guard_off"))


def log_block(session: str, tool: str, ti: dict) -> None:
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        path = HOME / "delegate_guard.log"
        row = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "session": session[:12], "tool": tool, "input": json.dumps(ti, ensure_ascii=False)[:300]}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if path.stat().st_size > 100_000:
            lines = path.read_text(encoding="utf-8").splitlines()[-200:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def on_prompt(data: dict, cfg: dict) -> str:
    session = str(data.get("session_id") or "")
    if not wants_delegate(str(data.get("prompt") or "")):
        save_state(session, None)  # ข้อความอื่น = ปลดงบ
        return ""
    budget = cfg.get("delegate_reads")
    budget = budget if isinstance(budget, int) and budget >= 0 else DEFAULT_READS
    save_state(session, {"at": time.time(), "left": budget, "total": budget, "sent": False})
    return ("[flashq] ผู้ใช้สั่งให้ส่งงานสืบให้ Flash — เรียก /flash-investigate ทันที (Skill: flash-investigate) แล้วส่งผู้สืบตามบรีฟ · "
            f"ห้ามไล่โค้ดเอง (Read/Grep/grep ใน Bash) เกิน {budget} ครั้งก่อนส่ง — ยามจะบล็อก · ขาดข้อมูลไหนใส่ในบรีฟให้ผู้สืบหา · "
            "ส่งแล้วหยุดนิ่งรอแจ้งเตือน · ผลมาแล้วเปิดโค้ดยืนยันต้นตอหลักได้ ≤2 Read · ผลไม่พอ = ส่งผู้สืบรอบใหม่ ไม่ใช่ Claude สืบเอง")


def on_pretool(data: dict) -> tuple[int, str]:
    """(exit code, ข้อความ) · 2 = บล็อก"""
    session = str(data.get("session_id") or "")
    st = load_state(session)
    if not st:
        return 0, ""
    tool, ti = str(data.get("tool_name") or ""), data.get("tool_input") or {}
    kind = classify(tool, ti)
    if kind == "sent":
        save_state(session, {**st, "at": time.time(), "left": AFTER_SENT_READS, "total": AFTER_SENT_READS, "sent": True})
        return 0, ""
    if kind != "read":
        return 0, ""
    left = int(st.get("left", 0))
    if left <= 0:
        log_block(session, tool, ti)
        return 2, block_text(int(st.get("total", 0)))
    save_state(session, {**st, "left": left - 1})
    if left - 1 == 0:
        return 0, ("flashq: งบอ่านโค้ดเองหมดแล้ว" + (" (ยืนยันต้นตอหลังผลสืบ)" if st.get("sent") else " — ครั้งต่อไปจะถูกบล็อก ส่งผู้สืบได้เลย (/flash-investigate)"))
    return 0, ""


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "test":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print("ตรง (จะบังคับส่ง Flash)" if wants_delegate(sys.argv[2]) else "ไม่ตรง")
        return 0
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else ""
        cfg = config()
        if disabled(cfg):
            return 0
        data = json.loads(sys.stdin.read() or "{}")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if mode == "prompt":
            text = on_prompt(data, cfg)
            if text:
                print(text)
        elif mode == "pretool":
            code, text = on_pretool(data)
            if code == 2:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
                print(text, file=sys.stderr)
                return 2
            if text:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}}, ensure_ascii=False))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""แจ้งผลงาน flashq ให้ Claude Code — flashq:managed (ติดตั้งโดย `flashq.py install` · ต้นฉบับ {{FLASHQ}}/hooks/)

ทำไม: งานที่ส่งให้ DeepSeek จบ/ล้ม/โดนปฏิเสธสิทธิ์ตอนไม่มีใครรอ → Claude ไม่รู้เลยจนผู้ใช้มาถาม · การนั่งรอใน session ใหญ่แพง (ห้าม sleep/poll)
ทางที่ใช้: flashq.py เขียนผลลง ~/.flashq/inbox/*.json ตอนงานจบ (ไม่เรียกโมเดล · ไม่เสีย token ระหว่างรอ) + toast Windows
hook นี้ (UserPromptSubmit) อ่าน inbox ตอนผู้ใช้พิมพ์ข้อความถัดไป แล้วแทรกผลให้ Claude เห็น → Claude แจ้งผู้ใช้ + ตรวจ/วินิจฉัยต่อ

ส่งถึงใคร: งานที่สั่งจาก session นี้ (session_id ตรง) · งานเก่าไม่มี session ในโปรเจกต์เดียวกัน · งานของ session อื่นในโปรเจกต์เดียวกันที่ค้างเกิน 30 นาที (session เดิมอาจปิดไปแล้ว)
ส่งแล้วย้ายไป inbox/done/ (ลบเมื่อเกิน 7 วัน) · พังเองไม่ว่ากรณีใด = ไม่พิมพ์อะไร (exit 0) ห้ามขวางผู้ใช้
ปิด: ~/.flashq/config.json {"notify": false}
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
FLASHQ = "{{FLASHQ}}"
FQ = "{{FLASHQ_RUN}}"  # คำสั่งเรียก flashq (python flashq.py หรือ flashq.exe)
FLASHQ_EXE = "{{FLASHQ_EXE}}"  # ไม่ว่าง = ติดตั้งจาก exe
STALE_SEC = 1800
KEEP_DONE_SEC = 7 * 86400
MAX_SHOW = 8


def norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p)).rstrip("\\/") if p else ""


def related(project: str, cwd: str) -> bool:
    """cwd อยู่ในโปรเจกต์ หรือโปรเจกต์อยู่ใน cwd (worktree ใต้ .claude/worktrees/ ของโปรเจกต์ก็นับ)"""
    a, b = norm(project), norm(cwd)
    if not a or not b:
        return False
    return a == b or b.startswith(a + os.sep) or a.startswith(b + os.sep)


def mine(row: dict, session: str, cwd: str, now: float) -> bool:
    if session and row.get("session") == session:
        return True
    if not related(row.get("project", ""), cwd):
        return False
    return not row.get("session") or now - float(row.get("at") or 0) > STALE_SEC


def advice(row: dict) -> str:
    st, plan = row.get("status", ""), row.get("plan", "")
    if row.get("kind") == "qa" and st in ("OK", "FAIL", "TIMEOUT"):  # ผลมาจาก exit code จริง ไม่ใช่คำพูดของโมเดล
        return (f"ผลทดสอบ (flashq รันเองและตัดสินจาก exit code) — รายงานทีละชุดว่าผ่าน/ไม่ผ่าน ห้ามเปลี่ยนคำตัดสิน · "
                f"ไม่ผ่านให้ดู {FQ} log {row.get('job', '')} เทียบ log จริงก่อนเชื่อคำอธิบายของ Flash")
    if row.get("kind") == "doc" and st in ("OK", "FAIL", "TIMEOUT"):  # ผลมาจากด่านกลไกของ flashq (git diff/ไฟล์จริง) ไม่ใช่คำพูดของโมเดล
        job = row.get("job", "")
        if st == "OK":
            return (f"ร่างเอกสารผ่านด่านกลไกแล้ว แต่ยังไม่ถูกรับและไม่ได้ commit — ตรวจ git diff ของโปรเจกต์ เทียบกับโค้ดจริง (เปิดไฟล์ที่เอกสารอ้างถึงดูเอง) แล้วรายงานผู้ใช้ว่าถูก/ผิดตรงไหน · "
                    f"ห้ามรับ/ทิ้ง/commit เองจนกว่าผู้ใช้สั่ง (รับ: {FQ} doc-review {job} accept · ทิ้ง: ... discard)")
        return (f"ช่างเอกสารไม่ผ่านด่านกลไก (สาเหตุอยู่ต้นข้อความท้าย · ดูเต็มด้วย {FQ} log {job}) — บอกผู้ใช้สาเหตุเป็นภาษาคน · "
                f"ถ้ามีไฟล์ค้าง (ไม่ได้ย้อนให้) ให้ดู git diff แล้วเสนอ discard · ห้ามสั่งซ้ำเองจนกว่าผู้ใช้สั่ง")
    if st == "OK_UNVERIFIED":
        return ("ผล OK ยังไม่ยืนยัน (ดูบรรทัด WARN ใน log) — ห้ามเชื่อ OK · "
                + (f"ตรวจด้วย /flash-check {plan} โดยดู git log ของงานเอง" if plan else f"อ่าน {FQ} log {row.get('job', '')} ก่อนรายงาน"))
    if st == "OK":
        if row.get("kind") == "investigate":
            return "ผลสืบ — ตรวจเลขไฟล์:บรรทัดที่อ้างก่อนเชื่อ (ดูบรรทัด CITATIONS ใน log)"
        return f"ตรวจด้วย /flash-check {plan}" if plan else "อ่าน git diff/log แล้วตรวจผลก่อนรายงาน"
    if st == "CANCELLED":
        return "ถูกยกเลิกด้วยคำสั่ง cancel/ปุ่มยกเลิก (ไม่ใช่งานพัง) — ห้ามส่งซ้ำเองจนกว่าผู้ใช้สั่ง · ถ้ารันไปแล้วบางส่วนให้ดู git status ว่ามีไฟล์ค้างครึ่งทางไหม"
    if st == "QUEUE_TIMEOUT" or st == "BUSY":
        return "ยังไม่ได้รันเลย (คิวไม่ว่าง) — สั่งใหม่เมื่อคิวว่าง"
    return f"ไม่สำเร็จ — ดูสาเหตุด้วย {FQ} log {row.get('job', '')} ก่อนสั่งซ้ำ แล้วบอกผู้ใช้สาเหตุ"


def main() -> int:
    try:
        cfg = {}
        try:
            cfg = json.loads((HOME / "config.json").read_text(encoding="utf-8-sig"))
        except Exception:
            pass
        if cfg.get("notify") is False:
            return 0
        if (HOME / "jobs").is_dir():  # งานที่ process ตายกลางคันไม่มีใครเขียน inbox → ให้ flashq ตรวจแล้วแจ้งแทน
            try:
                subprocess.run(([FLASHQ_EXE] if FLASHQ_EXE else [sys.executable, str(Path(FLASHQ) / "flashq.py")]) + ["sweep"], timeout=8,
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            except Exception:
                pass
        inbox = HOME / "inbox"
        if not inbox.is_dir():
            return 0
        data = json.loads(sys.stdin.read() or "{}")
        session, cwd = str(data.get("session_id") or ""), str(data.get("cwd") or os.getcwd())
        now = time.time()
        found = []
        for f in sorted(inbox.glob("*.json")):
            try:
                row = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if mine(row, session, cwd, now):
                found.append((f, row))
        if not found:
            return 0
        done = inbox / "done"
        done.mkdir(exist_ok=True)
        lines = ["[flashq] ผลงานที่จบระหว่างที่ผู้ใช้ไม่ได้รอ — แจ้งผู้ใช้เป็นภาษาไทยในคำตอบนี้ แล้วทำตามคำแนะนำของแต่ละงาน (ผลทุกงานต้องตรวจ ห้ามเชื่อ DONE ของ worker ตรง ๆ) · "
                 "รายงานผู้ใช้ให้ครบ: งานนี้คืออะไร · ผลผ่าน/ไม่ผ่าน · ได้ผลงานอะไรแบบไหน (จากที่ตรวจแล้วจริง) · ถ้าล้มสาเหตุเป็นภาษาคน+ทางแก้ · ผู้ใช้ต้องทำอะไรต่อ:"]
        for f, row in found[:MAX_SHOW]:
            when = time.strftime("%H:%M", time.localtime(float(row.get("at") or now)))
            kind = row.get("kind")
            tag = {"verify": "[ตรวจ] ", "investigate": "[สืบ] ", "qa": "[ทดสอบ] ", "doc": "[เอกสาร] "}.get(kind, "")
            name = row.get("plan") or ("" if kind in ("qa", "doc") else "--message")
            what = " ".join(x for x in (name, row.get("tasks", "")) if x)
            lines.append(f"- job {row.get('job')} {tag}{what} → {row.get('status')} "
                         f"({row.get('mins', 0)} นาที · จบ {when}) · {advice(row)}")
            last = (row.get("last") or "").strip().replace("\n", " ")
            if last and (row.get("status") != "OK" or kind == "doc"):
                lines.append(f"    ท้าย: {last[:300] if kind in ('qa', 'doc') else last[-300:]}")  # นักทดสอบ/ช่างเอกสาร: หัวข้อผลอยู่ต้นข้อความ
        if len(found) > MAX_SHOW:
            lines.append(f"- … และอีก {len(found) - MAX_SHOW} งาน (ดู flashq list --all)")
        for f, _ in found:
            try:
                os.replace(f, done / f.name)
            except Exception:
                pass
        for old in done.glob("*.json"):
            try:
                if now - old.stat().st_mtime > KEEP_DONE_SEC:
                    old.unlink()
            except Exception:
                pass
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print("\n".join(lines))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

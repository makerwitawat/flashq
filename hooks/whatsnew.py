"""บอก session ที่เปิดค้างว่า flashq ติดตั้งของใหม่แล้ว — flashq:managed (ติดตั้งโดย `flashq.py install` · ต้นฉบับ {{FLASHQ}}/hooks/)

ทำไม: session ที่เปิดไว้นานโหลด /flash-* · agent ตอนเริ่ม ไม่รู้ว่ามีคนรัน `install` ไปแล้ว → ผู้ใช้สั่ง "อัปเดต" แล้ว install ตอบ "เหมือนเดิม" ทุกไฟล์
         (เพราะติดตั้งไปก่อนแล้ว) agent เลยสรุปผิดว่า "ไม่มีอะไรใหม่"
ทางที่ใช้: `flashq install` บันทึกรุ่นที่ติดตั้ง + หัวข้อล่าสุดของ CHANGELOG ลง ~/.flashq/installed.json (ไม่เรียกโมเดล)
hook นี้ (UserPromptSubmit) เทียบรุ่นนั้นกับที่ session นี้เคยเห็น (~/.flashq/seen/<session>.json) → ไม่มีอะไรเปลี่ยน = ไม่พิมพ์อะไร (ไม่เสีย token)
เปลี่ยน = แทรกหัวข้อที่เป็นของใหม่ ไม่เกิน ~8 บรรทัด ครั้งเดียวต่อการติดตั้งหนึ่งครั้ง
session ที่ hook เพิ่งเห็นครั้งแรก: ถ้าติดตั้งหลัง session เริ่ม (เทียบเวลาสร้างไฟล์ transcript) = แจ้ง · ติดตั้งก่อน = บันทึกเงียบ ๆ (session โหลดของใหม่อยู่แล้ว)
พังเองไม่ว่ากรณีใด = ไม่พิมพ์อะไร (exit 0) ห้ามขวางผู้ใช้ · ปิด: ~/.flashq/config.json {"whatsnew": false}
"""
import json
import os
import re
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
FLASHQ = "{{FLASHQ}}"
MAX_SHOW = 6
KEEP_SEC = 30 * 86400


def main() -> int:
    try:
        cfg = {}
        try:
            cfg = json.loads((HOME / "config.json").read_text(encoding="utf-8-sig"))
        except Exception:
            pass
        if cfg.get("whatsnew") is False:
            return 0
        inst = json.loads((HOME / "installed.json").read_text(encoding="utf-8-sig"))
        rev, at = str(inst.get("rev") or ""), float(inst.get("at") or 0)
        news = [str(x) for x in inst.get("news") or []]
        data = json.loads(sys.stdin.read() or "{}")
        sid = str(data.get("session_id") or "")
        if not rev or not sid:
            return 0
        seen_dir = HOME / "seen"
        seen_dir.mkdir(exist_ok=True)
        f = seen_dir / (re.sub(r"[^\w.-]", "_", sid)[:100] + ".json")
        try:
            seen = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            seen = None
        now = time.time()
        if seen is None:
            try:
                start = os.stat(str(data.get("transcript_path") or "")).st_ctime  # เวลาสร้างไฟล์ transcript ≈ เวลาเริ่ม session
            except Exception:
                start = now
            seen = {"rev": rev if at <= start + 5 else "", "titles": news if at <= start + 5 else []}
            for old in seen_dir.glob("*.json"):
                try:
                    if now - old.stat().st_mtime > KEEP_SEC:
                        old.unlink()
                except Exception:
                    pass
        if seen.get("rev") == rev:
            return 0
        fresh = [t for t in news if t not in (seen.get("titles") or [])][:MAX_SHOW]
        f.write_text(json.dumps({"rev": rev, "titles": news}, ensure_ascii=False), encoding="utf-8")
        when = time.strftime("%H:%M", time.localtime(at))
        lines = [f"[flashq] ติดตั้งของใหม่แล้วเมื่อ {when} (หลังจากที่ session นี้เริ่ม/เห็นรุ่นก่อน) — "
                 + ("หัวข้อที่เพิ่ม:" if fresh else "ไม่มีหัวข้อใหม่ใน CHANGELOG (ปรับถ้อยคำคำสั่ง/agent)")]
        lines += [f"- {t[:110]}" for t in fresh]
        lines.append("แจ้งผู้ใช้หนึ่งบรรทัดว่ามีของใหม่ · ถ้าผู้ใช้ถามว่า \"อัปเดต/มีอะไรใหม่\" ให้ตอบจากรายการนี้ — ผล install \"เหมือนเดิม\" แปลว่ามีคนติดตั้งไว้ก่อนแล้ว "
                     "ไม่ได้แปลว่าไม่มีของใหม่ · /flash-* ที่ session นี้โหลดไว้อาจเป็นฉบับเก่า: อ่าน ~/.claude/commands/<ชื่อ>.md ฉบับปัจจุบันก่อนใช้ "
                     f"หรือเปิด session ใหม่ · เต็ม: {FLASHQ}/CHANGELOG.md")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print("\n".join(lines))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

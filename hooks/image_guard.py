"""ยามรูปภาพของ Claude Code — flashq:managed (ติดตั้งโดย `flashq.py install` · ต้นฉบับ {{FLASHQ}}/hooks/)

ทำไม: รูป 1 รูปที่ Claude อ่าน ≈ 1–1.6k token และ **ค้างอยู่ใน context ทุก turn จนจบ session** · session จริงที่อ่านรูป 70–100 รูป
= ~100k token ค้างคูณทุกข้อความที่ส่ง → แผน 100 USD หมดกับรูปที่อ่านไปแล้ว

ลงทะเบียนเป็น PreToolUse (matcher `Read`) ใน ~/.claude/settings.json ด้วย `flashq.py install --hooks`:
  1. รูปด้านยาว > IMAGE_MAX_PX (ค่าเริ่มต้น 1200) → บล็อก ให้ย่อก่อนด้วย `flashq.py shrink <รูป>` แล้วอ่านไฟล์ใน .tmp/shrink/
     (ไฟล์ใน .tmp/shrink/ ไม่ตรวจขนาด)
  2. อ่านรูปเกิน IMAGE_MAX_READS (ค่าเริ่มต้น 12) รูปใน session เดียว → บล็อก ให้ส่ง subagent (Agent tool · model haiku/sonnet)
     ดูรูปแล้วตอบเป็นข้อความ หรือเปิด session ใหม่
ตั้งค่า: ~/.flashq/config.json  {"image_max_px": 1200, "image_max_reads": 12}
ปิดชั่วคราว (60 นาที): สร้างไฟล์ ~/.flashq/image_guard_off   (เช่น `type nul > %USERPROFILE%\\.flashq\\image_guard_off`)
พังเองไม่ว่ากรณีใด = ปล่อยผ่าน (exit 0) ห้ามขวางงานผู้ใช้ · ทดสอบ: python image_guard.py test <รูป>
"""
import json
import os
import struct
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
FLASHQ = "{{FLASHQ}}"
FQ = "{{FLASHQ_RUN}}"  # คำสั่งเรียก flashq (python flashq.py หรือ flashq.exe)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
OFF_SEC = 3600


def config() -> dict:
    try:
        return json.loads((HOME / "config.json").read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def image_size(path: Path) -> tuple[int, int] | None:
    """ขนาดรูปจาก header (PNG/GIF/BMP/JPEG) · ไม่รู้จัก → ลอง PIL · ไม่ได้ = None"""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", head[16:24])
            if head[:6] in (b"GIF87a", b"GIF89a"):
                return struct.unpack("<HH", head[6:10])
            if head[:2] == b"BM":
                return struct.unpack("<ii", head[18:26])
            if head[:2] == b"\xff\xd8":  # JPEG: ไล่ segment หา SOFn
                f.seek(2)
                while True:
                    b = f.read(1)
                    if not b:
                        break
                    if b != b"\xff":
                        continue
                    marker = f.read(1)
                    while marker == b"\xff":
                        marker = f.read(1)
                    if not marker:
                        break
                    m = marker[0]
                    if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
                        continue
                    (ln,) = struct.unpack(">H", f.read(2))
                    if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                        f.read(1)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    f.seek(ln - 2, 1)
    except Exception:
        pass
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def count_read(session: str) -> int:
    """นับรูปที่อ่านต่อ session (ล้างรายการเก่ากว่า 24 ชม.) · คืนจำนวนหลังนับครั้งนี้"""
    st = HOME / "image_guard_state.json"
    try:
        data = json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}
    except Exception:
        data = {}
    now = time.time()
    data = {k: v for k, v in data.items() if now - v.get("at", 0) < 86400}
    row = data.setdefault(session or "?", {"n": 0, "at": now})
    row["n"] = row.get("n", 0) + 1
    row["at"] = now
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        tmp = st.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, st)
    except Exception:
        pass
    return row["n"]


def judge(path: Path, session: str, cfg: dict) -> str:
    """'' = ผ่าน · อื่น = เหตุที่บล็อก"""
    off = HOME / "image_guard_off"
    if off.exists():
        if time.time() - off.stat().st_mtime < OFF_SEC:
            return ""
        off.unlink(missing_ok=True)  # หมดเวลาปิด → เปิดยามกลับเอง
    max_px = int(cfg.get("image_max_px") or 1200)
    max_reads = int(cfg.get("image_max_reads") or 12)
    shrunk = ".tmp/shrink/" in path.as_posix() or "/.tmp/shrink" in path.parent.as_posix()
    if not shrunk:
        size = image_size(path)
        if size and max(size) > max_px:
            return (f"ยามรูปภาพ (flashq): รูป {size[0]}x{size[1]} ใหญ่เกิน {max_px}px — รูปใหญ่กิน context และค้างทุก turn จนจบ session\n"
                    f"→ ย่อก่อน: {FQ} shrink \"{path}\"  แล้ว Read ไฟล์ .tmp/shrink/{path.stem}.jpg แทน\n"
                    f"→ หรือให้ subagent (Agent tool · model haiku/sonnet) ดูรูปแล้วตอบเป็นข้อความสั้น ๆ\n"
                    f"→ จำเป็นต้องดูต้นฉบับจริง ๆ: สร้างไฟล์ {off} (ปิดยาม 60 นาที)")
    n = count_read(session)
    if n > max_reads:
        return (f"ยามรูปภาพ (flashq): session นี้อ่านรูปไปแล้ว {n - 1} รูป (เพดาน {max_reads}) — ทุกรูปยังค้างใน context ทุก turn\n"
                f"→ ให้ subagent (Agent tool · model haiku/sonnet) ดูรูปแล้วตอบเป็นข้อความ หรือเปิด session ใหม่ (fresh) สำหรับงานที่ต้องดูรูปต่อ\n"
                f"→ จำเป็นจริง ๆ: สร้างไฟล์ {off} (ปิดยาม 60 นาที)")
    return ""


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "test":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(judge(Path(sys.argv[2]), "test", config()) or "ผ่าน")
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if data.get("tool_name") != "Read":
            return 0
        fp = str((data.get("tool_input") or {}).get("file_path") or "")
        path = Path(fp)
        if path.suffix.lower() not in IMAGE_EXT or not path.is_file():
            return 0
        why = judge(path, str(data.get("session_id") or ""), config())
        if why:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            print(why, file=sys.stderr)
            return 2
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

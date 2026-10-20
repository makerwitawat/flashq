# AGENTS.md — กติกาสำหรับคน/AI ที่แก้ repo flashq

> ใช้ร่วมกันทั้ง Claude Code (`CLAUDE.md` ชี้มาที่นี่) และ opencode · คู่มือการใช้งาน → [README.md](README.md) · โครงสร้างโค้ด → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## ภาษา
- ข้อความที่ผู้ใช้เห็น (ข้อความ UI · output ของ CLI · commit message · เอกสาร) เป็นภาษาไทย · ศัพท์เทคนิค/ชื่อคำสั่ง/ชื่อไฟล์เป็นอังกฤษได้

## ไฟล์หลัก
| ไฟล์ | หน้าที่ |
|---|---|
| `flashq.py` | ทุกอย่างของ CLI + server หน้าเว็บ (stdlib ล้วน ห้ามเพิ่ม dependency) |
| `ui.html` | หน้าเว็บหน้าเดียว (HTML/CSS/JS ในไฟล์เดียว · ห้ามโหลดอะไรจากเน็ต) |
| `claude/commands/*.md` `claude/agents/*.md` `hooks/*.py` | ต้นฉบับที่ `flashq install` คัดลอกไป `~/.claude/` |
| `opencode/command/*.md` `opencode/agent/*.md` | ต้นฉบับที่ `flashq install` คัดลอกไป `~/.config/opencode/` |
| `templates/*.md` | แม่แบบแผน/เป้าหมายที่ `flashq init` คัดลอกไปโปรเจกต์ |
| `tests/test_flashq.py` | เทสต์ (opencode ปลอม ไม่เรียกโมเดลจริง) |

## หลังแก้ต้องทำอะไร
- แก้ `flashq.py`: เทสต์ที่เกี่ยวข้อง `python -m pytest tests/test_flashq.py -q -x -k "<คำ>"` · ก่อน merge ควรรันทั้งชุด (~6 นาที · ตั้ง timeout ≥ 500 วิ) · ตั้ง `PYTHONIOENCODING=utf-8` เมื่อรันจาก bash
- แก้ `ui.html`: ตรวจ syntax ของ JS — ดึง `<script>` ออกมาเป็นไฟล์ใน `.tmp/` แล้ว `node --check` · ทดสอบหน้าจริงด้วย server แยกพอร์ต (ด้านล่าง)
- แก้ `flashq.py`/`ui.html` แล้วต้อง **รีสตาร์ต `flashq ui`** (พอร์ต 4097) ให้หน้าเว็บใช้โค้ดใหม่ — server รันจาก checkout หลัก `D:\MyCode\flashq` จึงต้อง merge เข้า master ก่อน
- แก้ไฟล์ใน `claude/` `opencode/` `hooks/` ต้องรัน `python flashq.py install` ใหม่ (ไฟล์ที่ติดตั้งแล้วจะใช้ได้ใน session ใหม่)

## ทดสอบหน้าเว็บโดยไม่แตะข้อมูลจริง
```
# คัดลอก jobs goals logs reviews config.json จาก %USERPROFILE%\.flashq ไป .tmp\fh ก่อน
$env:FLASHQ_HOME = "<repo>\.tmp\fh"; python flashq.py ui --no-open --port 4197
```
- เสร็จแล้วปิด process · ลบ `.tmp\fh` · ห้ามทดสอบด้วยการกดปุ่มที่เปลี่ยนสถานะงานจริงบนพอร์ต 4097

## หลาย session ใน repo เดียว
- ตรวจ `git status` / `git log` ก่อนเริ่มและก่อน commit — session อื่นอาจ commit เข้า master ระหว่างทาง (rebase ก่อน merge)
- **stage เฉพาะไฟล์ที่ตัวเองแก้** (`git add -- <ไฟล์>`) ห้าม `git add -A` / `git add .`
- ห้ามแก้/ลบไฟล์หรือ branch ของ session อื่น · ห้าม `git stash` เปล่า (stack ใช้ร่วมกันทุก worktree)
- commit / merge / push เฉพาะเมื่อผู้ใช้สั่ง · ห้าม force push
- ไฟล์ชั่วคราวไว้ที่ `.tmp/` (อยู่ใน `.gitignore`) แล้วลบเมื่อเสร็จ

## ข้อห้าม
- ห้ามแตะข้อมูลจริงใน `%USERPROFILE%\.flashq\` นอกจากอ่าน (ยกเว้นผู้ใช้สั่ง) · ห้ามแก้สถานะเป้าหมายของโปรเจกต์อื่นเอง (เช่น `goal human`) — เป็นการตัดสินของผู้ใช้
- ห้ามยกเลิก/หยุดงานที่ Flash กำลังรันของโปรเจกต์อื่นเพื่อทดสอบ
- ปุ่ม/endpoint ที่เปลี่ยนสถานะต้องผ่านการตรวจ Host/Origin + token เสมอ (กัน CSRF)

## commit message
- ภาษาไทย ขึ้นต้นด้วยส่วนที่แก้ (`ui:` · `flashq:` · `flash-goal:` · `flash-plan:` ฯลฯ) แล้วตามด้วยสิ่งที่ผู้ใช้จะเห็น · เพิ่มบรรทัดใน [CHANGELOG.md](CHANGELOG.md) เมื่อเป็นความสามารถใหม่

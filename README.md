# flashq — คิวกลางส่งงานให้ opencode (DeepSeek Flash) ใช้ได้ทุกโปรเจกต์

Claude Code วางแผน → `flashq run` ส่งงานเข้าคิว → opencode `/flash` ให้ `flash-worker` ลงมือ → Claude ตรวจผล

## ทำไมต้องมีคิวกลาง
- ทุกโปรเจกต์ใช้บัญชีโมเดลชุดเดียวกัน → ถ้ารันซ้อนกันจะชนโควตา · คิวนี้ทำ **ทีละงานทั้งเครื่อง** ตามลำดับที่ส่ง (FIFO)
- ของเดิม (ล็อกรายโปรเจกต์) เจองานซ้อนแล้วตอบ `BUSY` ทิ้ง · ตัวนี้ **รอคิวให้เอง** (`--no-wait` = พฤติกรรมเดิม)

## ที่เก็บ
| ส่วน | ที่ |
|---|---|
| โค้ด (repo นี้) | `D:\MyCode\flashq\` |
| ข้อมูลตอนรัน: งาน `jobs/` · log `logs/` · `running.lock` | `%USERPROFILE%\.flashq\` (ไม่อยู่ใน git) |
| คำสั่ง `/flash` `/flash-switch` `/flash-queue` + agent `flash-worker` แบบ global | `~/.config/opencode/command/` · `agent/` (ติดตั้งด้วย `install`) |
| ค่าเฉพาะโปรเจกต์ | `.flash.json` ที่รากโปรเจกต์ (ไม่มีก็ได้) |

โปรเจกต์ที่มี `.opencode/command/flash.md` หรือ `.opencode/agent/flash-worker.md` ของตัวเอง (เช่น IRIS_CODE_1.2) → opencode ใช้ของโปรเจกต์ก่อน

## ติดตั้งครั้งแรก
```
python D:\MyCode\flashq\flashq.py install
```
แล้วรีโหลด opencode desktop · ไฟล์ที่มีอยู่แล้วแต่ไม่ได้มาจาก flashq จะถูกข้าม (`--force` = สำรอง `.bak-flashq-*` แล้วทับ)

## ใช้
```
python D:\MyCode\flashq\flashq.py run docs\plans\PLAN_X.md T-01..T-03     # ที่โฟลเดอร์โปรเจกต์ (หรือ --project <dir>)
python D:\MyCode\flashq\flashq.py run --message "ตอบแค่คำว่า PONG"         # ทดสอบการเชื่อมต่อ
python D:\MyCode\flashq\flashq.py                                          # สถานะ: กำลังทำอะไร + คิว + บัญชี
python D:\MyCode\flashq\flashq.py list [--all] | log <id> | cancel <id>
python D:\MyCode\flashq\flashq.py switch [next|cc|cc2|go2|go3|inferx]
```
ใน opencode: `/flash-queue` · `/flash-queue list` · `/flash-switch next`

ตัวเลือกที่ใช้บ่อยของ `run`: `--switch-on-quota 4` (โควตาหมด → สลับบัญชีถัดไปแล้วสั่งซ้ำเอง · งานที่ติ๊ก `[x]` แล้วจะถูกข้าม) · `--wait-min 720` (รอคิวได้นานสุด) · `--no-wait` · `--attach none` (ไม่ดูสด) · `--no-open`

ผลลัพธ์: บรรทัด `FLASH_RUN=OK|FAIL|QUOTA|TIMEOUT|NOSTART|BUSY|QUEUE_TIMEOUT` + `job=<id>` · exit 0 = OK · 2 = BUSY · 3 = รอคิวเกินเวลา · อื่น ๆ = 1

## `.flash.json` (ทุกช่องไม่บังคับ)
```json
{
  "main_branch": "master",
  "remote": "origin",
  "require_plan_in_remote": true,
  "command": "flash",
  "timeout_min": 480,
  "rules": "กติกาเพิ่มที่ /flash แบบ global ต้องทำตาม (เช่น คำสั่ง commit ของโปรเจกต์)"
}
```

## ดูสดใน opencode desktop
- ค่าเริ่มต้นรันผ่าน `opencode serve --port 4096` (เปิดค้างให้เองถ้ายังไม่มี · cwd = `~/.flashq` ไม่ผูกโปรเจกต์ · ส่ง `--dir` ของโปรเจกต์ทุกครั้ง)
- desktop ต้องเปิดจาก shortcut ที่มี `--remote-debugging-port=9333` → flashq สั่งเปิด session ให้เอง (`oc_desktop_open.mjs`) · อัปเดตแอปอาจรีเซ็ต shortcut → ได้ `DESKTOP_OPEN=NO_PORT`

## แผนงาน
แม่แบบ → [templates/FLASH_PLAN_TEMPLATE.md](templates/FLASH_PLAN_TEMPLATE.md)

## เทสต์ (ใช้ opencode ปลอม ไม่เรียกโมเดลจริง)
```
python -W ignore tests\test_flashq.py
```

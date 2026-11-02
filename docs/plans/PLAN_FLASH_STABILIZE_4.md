# แผน ทำให้คิวเสถียร 4 (EPIPE ของงานสืบ/ตรวจ แบบอ่านอย่างเดียว ไม่ตีเป็น FAIL) — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-03 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_STABILIZE_4.md T-01 --switch-on-quota 4` · base commit ตอนวางแผน: `88624fb`
> ต่อจากแผนเสถียร 3 (T-01 กรณี EPIPE ต้องมี `DONE`)

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, tests/test_flashq.py, tests/fake_opencode.py
flashq-parallel: yes

1. **1 งาน = 1 commit** (`git add -- flashq.py tests/test_flashq.py tests/fake_opencode.py` + `git commit` ข้อความภาษาไทยขึ้นต้น `flashq:` มี `(T-01)` + trailer `Flash-Task: T-01`) · **ห้าม push** · ห้าม `git add -A` / `git add .` · ห้าม `git stash`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" · ห้าม refactor/จัดรูปแบบ/แก้ comment อื่น/แปลง encoding
3. หาจุดแก้จากข้อความ "ก่อน" ด้วย Grep (เลขบรรทัดอาจเลื่อน) · หาไม่เจอ/เจอหลายที่ → **หยุด ⛔** บันทึกใน §4
4. **ห้ามแตะ** `%USERPROFILE%\.flashq\` ของจริง · `ui.html` · `claude/` `opencode/` `hooks/` · ห้ามเรียกโมเดลจริง (ใช้ `tests/fake_opencode.py`) · ห้ามรัน `flashq run`/`flashq ui` พอร์ต 4097
5. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน" · stdlib ล้วน · ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย
6. ไฟล์ชั่วคราว/log ไว้ที่ `.tmp/` · ห้ามรันเทสต์ทั้งชุด (~12 นาที) รันเฉพาะ `-k` ที่แผนกำหนด
7. **แบบ "เทสต์ก่อน"**: เขียนเทสต์ → รันก่อนแก้โค้ดต้อง FAIL ด้วยเหตุที่แผนบอก (log แดง) → แก้โค้ด → รันซ้ำต้อง PASS (log เขียว) → commit เดียว · ผ่านตั้งแต่ก่อนแก้/ล้มด้วยเหตุอื่น → **⛔ หยุด** · ห้ามลดเงื่อนไขเทสต์
8. คำสั่งมาตรฐาน (PowerShell · timeout ≥ 300 วิ): `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k "คำค้น" > .tmp/T-01.red.log 2>&1`

---

## 1. สาเหตุ/หลักฐาน (Claude ตรวจแล้ว 2026-11-03)
งานสืบ/ตรวจ (`kind` = investigate/verify · แบบอ่านอย่างเดียว) 6 งานวันนี้ออก rc=1 พร้อม stderr EPIPE ล้วน และ log ของงาน (เช็ก 4 งาน) จบด้วย `step_finish` ที่ `part.reason == "stop"` = โมเดลตอบครบแล้วค่อยล้มตอนปิด · งานเหล่านี้ส่งรายงานเป็นข้อความ **ไม่เขียน `DONE`** จึงไม่ผ่านเงื่อนไข `said_done(last)` ที่แผนเสถียร 3 ใส่ไว้ (ค้น `epipe_only(errtxt) and said_done(last)` ใน `_run_once` flashq.py) → ยังตีเป็น FAIL
ในลูปอ่าน log ของ `_run_once` (ค้น `elif ev.get("type") == "error" or "error" in ev:`) event ชนิด `step_finish` มี `part.reason` (`tool-calls` = ยังไม่จบ · `stop` = จบ) แต่ยังไม่ถูกเก็บ

## 2. งาน
- [ ] **T-01** `flashq.py` (`_run_once`) + `tests/fake_opencode.py` + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - fake_opencode: ขยายโหมด `FAKE_MODE=epipe` เดิม — ถ้ามี `FAKE_STEP_REASON` (เช่น `stop` หรือ `tool-calls`) ให้พิมพ์ event `{"type":"step_finish","sessionID":sid,"part":{"reason":<ค่า>}}` หลังข้อความ text ก่อนพิมพ์ stderr · ไม่ตั้ง = พฤติกรรมเดิมทุกอย่าง (เทสต์ EPIPE ของแผน 3 ต้องยังผ่าน)
  - เทสต์ใหม่ 3 ข้อ (ทำตามรูปแบบเทสต์ `test_epipe_*` ที่มีอยู่ · งานสืบ = ส่งด้วยคำสั่ง/พารามิเตอร์ที่ทำให้ `job["kind"]` เป็น `investigate` เหมือนเทสต์สืบเดิมที่มีใน tests/test_flashq.py — Grep `investigate`):
    1. `test_epipe_readonly_stop_not_fail`: งาน investigate · `FAKE_MODE=epipe` · `FAKE_TEXT="รายงานผลสืบ: ต้นตอที่ a.py:1"` (ไม่มี DONE) · `FAKE_STEP_REASON=stop` → ไม่ใช่ `FAIL` (ต้องเป็น `OK_UNVERIFIED` · เหตุผลที่บันทึกมีคำ `EPIPE`) · `rc` ยัง 1
    2. `test_epipe_readonly_midrun_still_fail`: งาน investigate · `FAKE_STEP_REASON=tool-calls` และอีกกรณีไม่ตั้ง FAKE_STEP_REASON (ไม่มี step_finish) → ต้อง `FAIL` ทั้งคู่
    3. `test_epipe_work_job_without_done_still_fail`: งานแก้ (ไม่ readonly · kind ไม่ใช่ verify/investigate) · `FAKE_TEXT="กำลังทำ"` · `FAKE_STEP_REASON=stop` → ยัง `FAIL` (กฎผ่อนเฉพาะงานอ่านอย่างเดียว) · และ investigate ที่มี stderr อื่นปน (`FAKE_ERR_EXTRA="Error: boom"`) + `stop` → `FAIL`
  - แดง: `-k "epipe_readonly"` → `.tmp/T-01.red.log` ข้อ 1 ต้อง FAIL เพราะสถานะเป็น `FAIL` (ไม่ใช่ SyntaxError/AttributeError)
  - แก้ (สเปก): ในลูปอ่าน log เก็บ `last_finish` = ค่า `part.reason` ของ event `step_finish` ล่าสุด (ว่างถ้าไม่มี) · ในสาขา EPIPE ที่มีอยู่ (`epipe_only(errtxt)` และ `errors` ว่าง และ rc≠0) ให้ผ่อนได้ 2 ทาง: (เดิม) `said_done(last)` · (ใหม่) งานอ่านอย่างเดียว — `job.get("readonly")` หรือ `job.get("kind") in ("verify","investigate")` — และ `last_finish == "stop"` และ `last` ไม่ว่าง → ตั้ง `epipe_done` เหมือนเดิมด้วยเหตุผลภาษาไทยที่บอกว่า "ล้มด้วย EPIPE หลังโมเดลตอบจบ (step_finish=stop)" · อย่างอื่น = `FAIL` เหมือนเดิม · ห้ามแตะโค้ดโควตา/DENIED/SUBAGENT ถัดลงไป
  - ตรวจ: งานสืบ/ตรวจที่ได้ `OK_UNVERIFIED` ต้องยังแสดงรายงาน (`last`) และผ่านตัวตรวจ CITATIONS ตามปกติ — Grep ผู้ใช้ `epipe_done`/`unverified_reasons` ว่าไม่ทำให้ส่วนนั้นถูกข้าม (ถ้าข้าม ให้ระบุใน §4 แล้วหยุด ⛔ ไม่แก้นอกสเปก)
  - เขียว: คำสั่งเดิม → `.tmp/T-01.green.log` PASS · แล้วรัน `-k "epipe or unverified or investigate or verify"` → `.tmp/T-01.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-01.red.log` มี `FAIL` ที่ `test_epipe_readonly_stop_not_fail` · เขียว `.tmp/T-01.green.log` บรรทัดท้าย `passed` ไม่มี `failed` · `.tmp/T-01.reg.log` `passed`
  - commit: `flashq: EPIPE ของงานสืบ/ตรวจแบบอ่านอย่างเดียวที่โมเดลตอบจบแล้ว (step_finish=stop) เป็น OK_UNVERIFIED ไม่ใช่ FAIL (T-01)`

## 3. นอกแผนนี้
สาเหตุที่ EPIPE เริ่มเกิด · T-09 pid_start ไม่ตรง

## 4. ผล (ผู้ทำเติม · ผู้ตรวจเติมช่องขวา)
| งาน | ผล | commit | หลักฐานชี้ขาด | ตรวจ Claude |
|---|---|---|---|---|
| T-01 | | | | |

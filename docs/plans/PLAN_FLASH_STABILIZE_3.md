# แผน ทำให้คิวเสถียร 3 (opencode ล้มด้วย EPIPE หลังจบงาน ไม่ควรตีเป็น FAIL) — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-02 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_STABILIZE_3.md T-01 --switch-on-quota 4` · base commit ตอนวางแผน: `345843f`

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, tests/test_flashq.py, tests/fake_opencode.py
flashq-parallel: yes

1. **1 งาน = 1 commit** (`git add -- flashq.py tests/test_flashq.py tests/fake_opencode.py` + `git commit` ข้อความภาษาไทยขึ้นต้น `flashq:` มี `(T-01)` + trailer `Flash-Task: T-01`) · **ห้าม push** · ห้าม `git add -A` / `git add .` · ห้าม `git stash`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" · ห้าม refactor/จัดรูปแบบ/แก้ comment อื่น/แปลง encoding
3. หาจุดแก้จากข้อความ "ก่อน" ด้วย Grep (เลขบรรทัดอาจเลื่อน) · หาไม่เจอ/เจอหลายที่ → **หยุด ⛔** บันทึกใน §4
4. **ห้ามแตะ** `%USERPROFILE%\.flashq\` ของจริง (เทสต์ใช้ `FLASHQ_HOME` ชั่วคราวผ่าน helper เดิม) · `ui.html` · `claude/` `opencode/` `hooks/` · ห้ามเรียกโมเดลจริง (ใช้ `tests/fake_opencode.py` เท่านั้น) · ห้ามรัน `flashq run`/`flashq ui` พอร์ต 4097
5. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน" · stdlib ล้วน · ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย
6. ไฟล์ชั่วคราว/log ไว้ที่ `.tmp/` · ห้ามรันเทสต์ทั้งชุด (~6 นาที) รันเฉพาะ `-k` ที่แผนกำหนด
7. **แบบ "เทสต์ก่อน"**: เขียนเทสต์ → รันก่อนแก้โค้ดต้อง FAIL ด้วยเหตุที่แผนบอก (log แดง) → แก้โค้ด → รันซ้ำต้อง PASS (log เขียว) → commit เดียว · ผ่านตั้งแต่ก่อนแก้/ล้มด้วยเหตุอื่น → **⛔ หยุด** · ห้ามลดเงื่อนไขเทสต์
8. คำสั่งมาตรฐาน (PowerShell · timeout ≥ 300 วิ): `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k "คำค้น" > .tmp/T-01.red.log 2>&1`

---

## 1. สาเหตุ/หลักฐาน (Claude ตรวจแล้ว)
opencode เจอ `EPIPE: broken pipe, write` (Bun/Node stream error) แล้วตายด้วย exit 1 หลัง worker รายงาน `DONE` + commit แล้ว (ตัวอย่าง `~/.flashq/jobs/20261102_101335_53132.json` rc=1 last "DONE — T-03R3 ผ่าน") · `flashq.py` ใน `_run_once` (ค้น `if status == "OK" and (rc != 0 or errors):`) ตีทุก rc≠0 เป็น `FAIL` ทันทีโดยไม่ดูหลักฐาน
stderr จริง (`~/.flashq/logs/*_1.err`) มีบล็อกซ้ำ ๆ: `error: EPIPE: broken pipe, write` + `at emitError (node:events:50:13)` ฯลฯ
**ระวัง**: EPIPE เกิดกลางงานได้ด้วย (log งานสืบ step_finish สุดท้ายเป็น `tool-calls`) → ต้องมีหลักฐานว่าจบจริง (worker รายงาน DONE) จึงจะไม่ตีเป็น FAIL

## 2. งาน
- [x] **T-01** `flashq.py` (`_run_once`, ค้นข้อความ `if status == "OK" and (rc != 0 or errors):`) + `tests/fake_opencode.py` + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - fake_opencode: เพิ่มโหมด `FAKE_MODE=epipe` — พิมพ์ event text (ข้อความจาก `FAKE_TEXT`, ค่าเริ่มต้น `DONE — เสร็จ`) แล้วพิมพ์ลง stderr ข้อความ `error: EPIPE: broken pipe, write` กับบรรทัด `      at emitError (node:events:50:13)` แล้ว `sys.exit(1)` · โหมดอื่นไม่เปลี่ยน
  - เทสต์ใหม่ 3 ข้อ (ใช้ helper เดิมแบบเดียวกับเทสต์ `_run_once`/`cmd_run` ที่มีอยู่ — Grep หาตัวอย่าง `FAKE_MODE` ใน tests/test_flashq.py แล้วทำตามรูปแบบนั้น):
    1. `test_epipe_after_done_not_fail`: `FAKE_MODE=epipe`, `FAKE_TEXT="DONE — ครบ"` → ผลต้องไม่ใช่ `FAIL` (ต้องเป็น `OK_UNVERIFIED` และเหตุผลที่แสดง/บันทึกมีคำ `EPIPE`) · `rc` ที่บันทึกยังเป็น 1
    2. `test_epipe_without_done_still_fail`: `FAKE_MODE=epipe`, `FAKE_TEXT="กำลังทำ"` (ไม่มี DONE) → ยังต้อง `FAIL`
    3. `test_real_error_rc1_still_fail`: `FAKE_MODE=fail` (โหมดเดิมที่ exit 1) และกรณี epipe ที่เพิ่ม stderr บรรทัดอื่นที่ไม่ใช่ EPIPE (เช่น `Error: boom`) + DONE → ต้อง `FAIL` ทั้งคู่
  - แดง: `-k "epipe or real_error_rc1"` → `.tmp/T-01.red.log` ข้อ 1 ต้อง FAIL เพราะสถานะเป็น `FAIL` (ไม่ใช่ SyntaxError/AttributeError)
  - แก้ (สเปก): ในสาขา rc≠0 ให้คงเป็น `FAIL` เหมือนเดิม **ยกเว้น** เมื่อครบทุกข้อ: (ก) `errors` ว่าง (ข) `rc != 0` (ค) stderr (`errtxt`) มี `EPIPE` และเมื่อตัดบรรทัดที่เป็นส่วนของ EPIPE traceback ออก (บรรทัดว่าง · มี `EPIPE` · ขึ้นต้น `at ` · เลขบรรทัดโค้ดแบบ `45 |` · ตัวชี้ `^` · `throw er`) แล้วไม่เหลือข้อความอื่น (ง) `said_done(last)` เป็นจริง → ตั้ง `status = "OK_UNVERIFIED"` พร้อมเหตุผลภาษาไทยเข้าชุดเหตุผลที่ `unverified_reasons` ใช้อยู่แล้ว (เช่น `opencode ล้มด้วย EPIPE หลังรายงาน DONE (rc=1) — ตรวจงานด้วย /flash-check`) และพิมพ์ `WARN:` หนึ่งบรรทัด · ไม่ครบข้อใด = `FAIL` เหมือนเดิม · ทำเป็นฟังก์ชันย่อยเล็ก ๆ เช่น `epipe_only(errtxt) -> bool` ให้ทดสอบได้ · ตรวจให้ `cmd_run`/`cmd_wait`/`claude_check_prompt` ที่รับ `OK_UNVERIFIED` อยู่แล้ว (แผนเสถียร 2) ทำงานกับกรณีนี้ได้ ไม่ต้องแก้เพิ่มถ้ามันรองรับอยู่
  - ห้ามแตะการตรวจโควตา/DENIED/SUBAGENT ที่อยู่ถัดลงไป
  - เขียว: คำสั่งเดิม → `.tmp/T-01.green.log` PASS · แล้วรัน `-k "unverified or quota or denied or subagent"` → `.tmp/T-01.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-01.red.log` มี `FAIL` ที่ `test_epipe_after_done_not_fail` · เขียว `.tmp/T-01.green.log` บรรทัดท้าย `passed` ไม่มี `failed` · `.tmp/T-01.reg.log` `passed`
  - commit: `flashq: opencode ล้มด้วย EPIPE หลังรายงาน DONE ไม่ตีเป็น FAIL แต่เป็น OK_UNVERIFIED (T-01)`

## 3. นอกแผนนี้
สาเหตุที่ EPIPE เริ่มเกิดช่วง 08:55 ยังไม่ทราบ · T-09 pid_start ไม่ตรง ยังไม่ทราบสาเหตุ

## 4. ผล (ผู้ทำเติม · ผู้ตรวจเติมช่องขวา)
| งาน | ผล | commit | หลักฐานชี้ขาด | ตรวจ Claude |
|---|---|---|---|---|
| T-01 | DONE — ใช้กลไก `unverified_reasons` เดิม (res คง status "OK" + เหตุ EPIPE) | 1c46c6f | `.tmp/T-01.red.log`: `FAILED tests/test_flashq.py::FlashqTest::test_epipe_after_done_not_fail` (FLASH_RUN=FAIL exit=1) · `.tmp/T-01.green.log`: `3 passed, 200 deselected in 5.36s` · `.tmp/T-01.reg.log`: `13 passed, 190 deselected in 59.73s` | |

# แผน UI_SPEED — หน้าเว็บ flashq ui ช้า (ย้าย/บันทึก/อัปเดตต้องรอคิว) — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-14 · ส่งงาน: `python D:/MyCode/flashq/flashq.py run docs/plans/PLAN_FLASH_UI_SPEED.md T-01..T-04` · base commit ตอนวางแผน: `7635d9e`
> ที่มา: ผลสืบ job `20261114_121933_14892` + Claude เปิดโค้ดยืนยันและวัดจริง: `jobs()` อ่านไฟล์งาน 2,729 ไฟล์ ใช้ 0.408 วิ/ครั้ง · `/api/state` เรียก 3 ครั้ง · หน้าเว็บยิงทุก 3 วิแบบไม่รอรอบก่อน

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, ui.html, tests/test_flashq.py
flashq-parallel: yes

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- <ไฟล์ของงาน>` + `git commit -m "<ข้อความในงาน>"`) · **ห้าม push** · ห้าม `git add -A` / `git add .`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment/แปลง encoding · ข้อความ/comment ใหม่เป็นภาษาไทย
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "ก่อน"/"จุดเสียบ" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนไว้ตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · **หลักฐานชี้ขาด = path log + บรรทัด/ค่าที่แผนกำหนด ตรงตัว**) — Claude ตรวจจากหลักฐานนี้ ไม่รันซ้ำ
6. **ห้ามแตะ**: `%USERPROFILE%\.flashq\` (ข้อมูลจริง) · server พอร์ต 4097 · ไฟล์อื่นนอก `flashq-files`
7. **งานแบบ "เทสต์ก่อน"**: เขียนเทสต์ → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (เก็บ log แดง) → แก้โค้ด → รันซ้ำต้อง PASS (เก็บ log เขียว) → commit เดียว · ผ่านตั้งแต่ก่อนแก้ / ล้มด้วยเหตุอื่น → **⛔ หยุด** · ห้ามแก้เทสต์ให้ผ่านแทนการแก้โค้ด
8. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน"
9. รันจาก bash ให้ตั้ง `PYTHONIOENCODING=utf-8` · ไฟล์ log ไว้ที่ `.tmp/` (อยู่ใน .gitignore)

### คำสั่งมาตรฐาน
```
PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "<คำ>"
```

---

## 1. กลุ่ม A — ฝั่ง server อ่านไฟล์งานซ้ำเกินจำเป็น
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว): `flashq.py:785` `jobs()` เปิด+parse ทุกไฟล์ใน `JOBS` ทุกครั้ง (วัดจริง 2,729 ไฟล์ = 0.408 วิ) · `ui_state()` (`flashq.py:5718`) เรียกทางอ้อม 3 ครั้ง: `auto_clear_dead()` (`4262`), `schedule(held)` (`1391` `all_jobs = jobs()`), และลูปหลัก `for j in jobs():` · ตัวจัดการ HTTP หางานเดียวด้วย `next((x for x in jobs() if x.get("id") == ...), None)` 14 ที่ (`6210`–`6395`) ทั้งที่ไฟล์งานชื่อ `<id>.json` เสมอ (`flashq.py:796` `write_json(JOBS / f"{job['id']}.json", job)`)

- [x] **T-01** `flashq.py` (`ui_state`, `auto_clear_dead`, `schedule`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - ไฟล์: `flashq.py`, `tests/test_flashq.py`
  - เทสต์: เพิ่ม `test_ui_state_reads_jobs_once` ในคลาสเดียวกับ `test_ui_state_and_cancel` — สร้างงาน 2 ไฟล์ใน `<home>/jobs` (แบบเดียวกับเทสต์เดิมในไฟล์) แล้วรัน subprocess `python -c` ด้วย env ของเทสต์ (`FLASHQ_HOME` = home ทดสอบ) ที่ `import flashq` → ห่อ `flashq.jobs` ด้วยตัวนับ (`n=[0]; o=flashq.jobs; flashq.jobs=lambda: (n.__setitem__(0, n[0]+1), o())[1]`) → เรียก `flashq.ui_state()` → `print("JOBS_CALLS", n[0])` · assert ว่าได้ `JOBS_CALLS 1` และผล `ui_state()` ยังมีงานครบ 2 งาน (ใน running/queued/history รวมกัน)
  - แดง: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k test_ui_state_reads_jobs_once > .tmp/T-01.red.log 2>&1` → FAIL ด้วยค่า `JOBS_CALLS 3` (ค่าเริ่มต้น `dead_clear_hours` = 24 จึง `auto_clear_dead` เรียก `jobs()` ด้วย)
  - แก้ (สเปก):
    - `auto_clear_dead(all_jobs: list[dict] | None = None) -> int` — ถ้าส่ง `all_jobs` มาให้วนรายการนั้นแทน `jobs()` · ไม่ส่ง = พฤติกรรมเดิม
    - `schedule(held=None, all_jobs: list[dict] | None = None)` — แทน `    all_jobs = jobs()` ด้วยใช้ค่าที่ส่งมา ถ้า `None` ค่อยเรียก `jobs()`
    - `ui_state()`: เรียก `snap = jobs()` ครั้งเดียวตอนต้น → `if auto_clear_dead(snap): snap = jobs()` (ล้างงานไปแล้วต้องอ่านใหม่ให้สถานะตรง) → `schedule(held, snap)` → ลูปหลักใช้ `for j in snap:`
    - ก่อน: `    auto_clear_dead()  # ป้ายงานตายที่ค้างเกินเวลาที่ตั้ง → รับทราบให้เอง ก่อนสร้างรายการ`
    - ห้ามเปลี่ยนผู้เรียกอื่นของ `auto_clear_dead()` / `schedule()` (ค่าเริ่มต้นต้องทำงานเหมือนเดิม)
  - เขียว: คำสั่งเดิม `> .tmp/T-01.green.log 2>&1` → PASS · แล้ว `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "ui_state or schedule or dead" > .tmp/T-01.related.log 2>&1` → ผ่านทั้งหมด
  - หลักฐานชี้ขาด: `.tmp/T-01.red.log` มี `JOBS_CALLS 3` (หรือค่า ≥2) · `.tmp/T-01.green.log` บรรทัด `1 passed` · `.tmp/T-01.related.log` บรรทัด `N passed` ไม่มี `failed`
  - commit: `flashq: หน้าเว็บอ่านไฟล์งานครั้งเดียวต่อการรีเฟรช (เดิม 3 รอบ) + เทสต์ (T-01)`

- [x] **T-02** `flashq.py` (ตัวจัดการ HTTP ใน `ui`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - ไฟล์: `flashq.py`, `tests/test_flashq.py`
  - เทสต์: เพิ่ม `test_job_by_id` (subprocess `python -c` แบบ T-01) — สร้าง `<home>/jobs/j1.json` `{"id":"j1"}` และ `<home>/jobs/j2.json` ที่ข้างในมี `"id":"other"` → ต้องได้: `job_by_id("j1")["id"] == "j1"` · `job_by_id("nope") is None` · `job_by_id("j2") is None` (id ในไฟล์ไม่ตรงชื่อ) · `job_by_id("../x") is None` · `job_by_id("") is None` · `job_by_id(None) is None`
  - แดง: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k test_job_by_id > .tmp/T-02.red.log 2>&1` → FAIL ด้วย `AttributeError: module 'flashq' has no attribute 'job_by_id'` (นี่คือเหตุที่คาด ไม่ต้องหยุด)
  - แก้ (สเปก):
    - เพิ่ม `def job_by_id(jid) -> dict | None:` ถัดจาก `def jobs()` — รับเฉพาะ `str` ที่ตรง `^[A-Za-z0-9_.-]+$` และไม่ขึ้นต้นด้วย `.` · อ่าน `read_json(JOBS / f"{jid}.json")` · คืน dict เมื่อ `j.get("id") == jid` นอกนั้นคืน `None`
    - ในฟังก์ชัน `ui` (ตัวจัดการ `do_GET`/`do_POST`) แทนทุกบรรทัดรูป `next((x for x in jobs() if x.get("id") == <นิพจน์>), None)` ด้วย `job_by_id(<นิพจน์>)` — **14 ที่** (ช่วงเดิม `6210`–`6395`) · 2 ที่ที่มีเงื่อนไขเพิ่ม `and x.get("kind") == "doc"` ให้เป็น `job_by_id(<นิพจน์>)` แล้วตามด้วย `j = j if j and j.get("kind") == "doc" else None`
    - **ห้ามแตะ** `for x in jobs():` ที่ `~6327` (วนหลายงาน) และจุดนอกตัวจัดการ HTTP (`~1074`, `~4495`)
    - ยืนยันจำนวน: `grep -c 'for x in jobs() if x.get("id")' flashq.py` ต้องได้ `0`
  - เขียว: คำสั่งเดิม `> .tmp/T-02.green.log 2>&1` → PASS · แล้ว `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "ui_" > .tmp/T-02.related.log 2>&1` → ผ่านทั้งหมด
  - หลักฐานชี้ขาด: `.tmp/T-02.red.log` มี `has no attribute 'job_by_id'` · `.tmp/T-02.green.log` บรรทัด `1 passed` · `.tmp/T-02.related.log` บรรทัด `N passed` ไม่มี `failed` · ผล grep = `0` (จดใน §4)
  - commit: `flashq: หน้าเว็บหางานจากชื่อไฟล์ตรง ๆ ไม่สแกนทุกงานทุกคำขอ + เทสต์ (T-02)`

- [x] **T-03** `flashq.py` ~6247 (endpoint flash_usage) — แคชนานขึ้นและไม่คำนวณซ้อน
  - ไฟล์: `flashq.py`
  - ก่อน: `                if not hit or time.time() - hit[0] > 30:`
  - แก้ (สเปก):
    - เพิ่ม lock ระดับโมดูลถัดจาก `_FLASH_SUM_CACHE: dict = {}` ชื่อ `_FLASH_SUM_LOCK = threading.Lock()` (ถ้า `threading` ยังไม่ถูก import ที่หัวไฟล์ ให้ import ในบรรทัดนั้นแบบ local ไม่ต้องแตะหัวไฟล์)
    - ใน endpoint: อายุแคช 30 → **600 วินาที** · เมื่อแคชหมดอายุ ให้ `with _FLASH_SUM_LOCK:` แล้วเช็กแคชซ้ำอีกครั้งในบล็อก (double-check) ก่อนเรียก `flash_usage_summary(days)` — คำขอที่ซ้อนกันรอผลเดียวกัน ไม่คำนวณซ้ำ
    - แก้ comment ท้ายบรรทัด `if u.path == "/api/flash_usage":` จาก `แคช 30 วินาที` เป็น `แคช 10 นาที`
  - ยืนยัน: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k flash_usage > .tmp/T-03.log 2>&1` → ผ่านทั้งหมด
  - หลักฐานชี้ขาด: `.tmp/T-03.log` บรรทัด `N passed` ไม่มี `failed` · ผล `grep -n "_FLASH_SUM_LOCK" flashq.py` ≥ 2 บรรทัด (จดใน §4)
  - commit: `ui: สรุป token ของ Flash แคช 10 นาที ไม่คำนวณซ้อนกัน (T-03)`

## 2. กลุ่ม B — หน้าเว็บยิงคำขอซ้อน
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว): `ui.html:4020` `setInterval(refresh, 3000);` เรียก `refresh()` (`ui.html:2389`) โดยไม่รอรอบก่อน · ปุ่มต่าง ๆ ก็ `await refresh()` ซ้ำ → ถ้า `/api/state` ช้ากว่า 3 วิ คำขอจะกองซ้อน

- [x] **T-04** `ui.html` ~2389 (`refresh`)
  - ไฟล์: `ui.html`
  - ก่อน: `async function refresh() {`
  - แก้ (สเปก):
    - เปลี่ยนชื่อฟังก์ชันเดิมเป็น `async function refreshOnce() {` (เนื้อในไม่เปลี่ยน)
    - เพิ่มเหนือมัน: ตัวแปร `let refreshing = null, refreshAgain = false;` และ `function refresh()` ที่: ถ้า `refreshing` ไม่ว่าง → ตั้ง `refreshAgain = true` แล้วคืน `refreshing` (ไม่ยิงคำขอใหม่) · ถ้าว่าง → `refreshing = (async () => { do { refreshAgain = false; await refreshOnce(); } while (refreshAgain); })().finally(() => { refreshing = null; });` แล้วคืน `refreshing`
    - ผลที่ต้องได้: ไม่มี `/api/state` ซ้อนกันเกิน 1 คำขอ · ปุ่มที่ `await refresh()` ระหว่างรอบอื่นกำลังรัน ยังได้ข้อมูลสดหลังกด (รอบถัดไปถูกรันต่อท้ายในสัญญาเดียวกัน)
    - ห้ามแตะ `setInterval(refresh, 3000);` และผู้เรียก `refresh()` จุดอื่น
  - ยืนยัน (2 คำสั่ง):
    - `python -c "import re,pathlib;s=pathlib.Path('ui.html').read_text(encoding='utf-8');pathlib.Path('.tmp/ui_check.js').write_text('\n'.join(re.findall(r'<script>(.*?)</script>',s,re.S)),encoding='utf-8')" && node --check .tmp/ui_check.js > .tmp/T-04.node.log 2>&1; echo NODE_RC=$? >> .tmp/T-04.node.log`
    - `PYTHONIOENCODING=utf-8 python tests/ui_smoke.py > .tmp/T-04.smoke.log 2>&1` → มี `UI_SMOKE OK` (ถ้า exit 3 = เครื่องไม่มีเบราว์เซอร์ทดสอบ → จด "ไม่ได้รัน: env" ใน §4 ไม่ถือว่าล้ม)
  - หลักฐานชี้ขาด: `.tmp/T-04.node.log` บรรทัด `NODE_RC=0` · `.tmp/T-04.smoke.log` บรรทัด `UI_SMOKE OK` (หรือ exit 3 ตามข้างบน)
  - commit: `ui: รีเฟรชหน้าเว็บไม่ยิงคำขอซ้อนกัน ปุ่มที่กดระหว่างรอยังได้ข้อมูลสด (T-04)`

## 3. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- working tree หลักมีงานที่ยังไม่ commit ใน `flashq.py` `ui.html` `tests/test_flashq.py` (เรื่อง `ui_models_quick`) — ก่อน merge ผลของแผนนี้ ผู้ใช้ต้อง commit หรือเก็บงานนั้นก่อน

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|
| T-01 | ✅แก้ | 6f13fab | `.tmp/T-01.red.log:28` = `AssertionError: 'JOBS_CALLS 1' not found in 'JOBS_CALLS 3
JOBS_TOTAL 2
'` · `.tmp/T-01.green.log:2` = `1 passed, 226 deselected` · `.tmp/T-01.related.log:2` = `8 passed, 219 deselected` (failed 0) | ✅ผ่าน |
| T-02 | ✅แก้ | 83432dd | `.tmp/T-02.red.log:28` = `AttributeError: module 'flashq' has no attribute 'job_by_id'` · `.tmp/T-02.green.log:2` = `1 passed, 227 deselected` · `.tmp/T-02.related.log:2` = `32 passed, 196 deselected` (failed 0) · `grep -c 'for x in jobs() if x.get("id")' flashq.py` = `0` · หมายเหตุ: ของจริงมี 13 จุด ไม่ใช่ 14 (แผนนับเกิน 1 · ทุกจุดในตัวจัดการ HTTP ถูกแทนครบ) | ✅ผ่าน (ยืนยัน: ก่อนแก้มี 13 จุดจริง) |
| T-03 | ✅แก้ | abb3bbd | `.tmp/T-03.log:2` = `1 passed, 227 deselected` (failed 0) · `grep -n _FLASH_SUM_LOCK flashq.py` = 2 บรรทัด (`6284` with-lock · `7253` นิยาม lock) | ✅ผ่าน |
| T-04 | ✅แก้ | 9ea601e | `.tmp/T-04.node.log` = `NODE_RC=0` · `.tmp/T-04.smoke.log:1` = `UI_SMOKE OK (3 ความกว้าง: 1280, 700, 390px)` | ✅ผ่าน |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- `ui_goals` คำนวณเป้าหมายทุกใบ + glob โฟลเดอร์ session ของ Claude ต่อใบ (`flashq.py` ~7616–7664) — รอบถัดไป
- `/api/models` เรียก `opencode models` แบบบล็อก (timeout 90 วิ) — งานค้างใน working tree กำลังแก้อยู่
- ฉาก office อัปเดตทุก 1 วิ + สร้าง SVG ใหม่ (`ui.html` ~3770) · `replace_file` รอได้ถึง 5 วิ (`flashq.py:210`)

# แผน แก้กฎรอคิวไม่ให้งานที่ไม่ชนต้องรอ — ส่งงานให้ DeepSeek Flash

> แผนของ flashq เอง — Claude วางแผน+ตรวจ · DeepSeek ลงมือ
> สร้าง 2026-10-24 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_QUEUE_RULES.md T-01..T-04 --switch-on-quota 4` · base commit ตอนวางแผน: `81ec839`

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, tests/test_flashq.py, docs/REFERENCE.md, docs/ARCHITECTURE.md, CHANGELOG.md, templates/FLASH_PLAN_TEMPLATE.md, claude/commands/flash-plan.md
flashq-parallel: yes

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- <ไฟล์ของงาน>` + `git commit -m "<ข้อความในงาน>"`) · **ห้าม push** · **ห้าม `git add -A` / `git add .`** — ใน working tree มี `ui.html` ที่ session อื่นแก้ค้างอยู่ ห้ามแตะ/ห้าม stage
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment/แปลง encoding
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "จุดเสียบ" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนไว้ตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · หลักฐานชี้ขาด = path log + บรรทัดที่แผนกำหนดตรงตัว)
6. **ห้ามแตะ**: `ui.html` · `~/.flashq/` (ข้อมูลจริง) · ห้ามแก้เทสต์เดิมให้หลวมลงเพื่อให้ผ่าน — แก้ได้เฉพาะแอสเซิร์ตที่แผนสั่งให้เปลี่ยนเพราะกฎใหม่
7. **งาน "เทสต์ก่อน"**: เขียนเทสต์/แก้แอสเซิร์ต → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (เก็บ log แดง) → แก้โค้ด → รันซ้ำต้อง PASS (log เขียว) → commit เดียว · ผ่านตั้งแต่ก่อนแก้ / ล้มด้วยเหตุอื่น (import error, syntax) → **⛔ หยุด**
8. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน" ตรง ๆ
9. stdlib ล้วน ห้ามเพิ่ม dependency · ข้อความที่ผู้ใช้เห็น/คอมเมนต์/commit เป็นภาษาไทย · commit ขึ้นต้น `flashq:` + สิ่งที่ผู้ใช้จะเห็น
10. สไตล์โค้ด: ตามไฟล์รอบข้าง (คอมเมนต์ไทยสั้น ๆ ท้ายบรรทัดเมื่อจำเป็น)

### คำสั่งมาตรฐาน
```
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k "<คำ>"
```
(log ไว้ที่ `.tmp/` เช่น `... > .tmp/T-01.red.log 2>&1` · เทสต์ที่เปิด process จริงใช้เวลาหลายสิบวินาที ตั้ง timeout ≥ 300 วิ)

---

## 1. งาน
### สาเหตุ/หลักฐาน (Claude ตรวจแล้วที่ `flashq.py:1102-1194`)
กฎชน `conflict_reason` + ตัวจัดคิว `schedule` มีเงื่อนไขกว้างเกิน ทำให้งานที่ไฟล์ไม่ชนกันต้องรอ:
- **ก** งานของแผนที่ประกาศ `flashq-parallel: no` บล็อกทุกงานในโปรเจกต์เดียวกัน ไม่ดูไฟล์เลย (ข้อความยังบอก "ไฟล์ที่ประกาศไม่ซ้อนกัน" ทั้งที่บล็อกอยู่)
- **ข** แตะ "ไฟล์ร่วม" (`Common/` `CMakeLists.txt` ฯลฯ) ฝั่งเดียวก็ชน (ตรวจแบบ union)
- **ค** กันอดตาย (barrier) ล็อก "ทั้งคิว" ไม่ใช่เฉพาะงานที่ชนกับตัวที่อดตาย
- **ง (ไม่อยู่ในแผนนี้)** doc/qa ชนทั้งโปรเจกต์ — Claude ตรวจแล้ว **แก้ด้วยการจำกัดขอบเขตไม่ได้ปลอดภัย** เพราะ `doc_verdict` (`flashq.py:3227-3234`) ตัดสิน OUTSIDE/CHANGED จากไฟล์ที่เปลี่ยนทั้งโปรเจกต์ + HEAD เดียวกันตลอดรัน และ qa (`:2970`) ทิ้งผลถ้า HEAD เปลี่ยนระหว่างทดสอบ → ดู §2

กฎร่วมของทุกงาน: **ไม่แน่ใจ = ชน** (อนุรักษ์) ยังคงเดิม · ค่าเดิมต้องไม่เปลี่ยนพฤติกรรมเมื่อไม่ได้ตั้งตัวเลือกใหม่ (ยกเว้นข้อ ข ที่เปลี่ยนค่าตั้งต้นตามที่ผู้ใช้สั่ง)

### กลุ่ม A — `flashq-parallel: no` ผูกขอบเขตไฟล์ด้วย `flashq-exclusive:`

- [x] **T-01** `flashq.py` (`DECL_RE` · `plan_meta` · `job_info` · `conflict_reason`) + `tests/test_flashq.py` (`test_plan_declarations_and_conflicts`) · แบบ: เทสต์ก่อน
  - แนวคิด: แผนเขียนเพิ่มได้ `flashq-exclusive: <path/glob, ...>` = ขอบเขตที่ห้ามงานอื่นแตะระหว่างที่แผนนี้รัน · ใช้คู่กับ `flashq-parallel: no` · **ไม่มี `flashq-exclusive` = พฤติกรรมเดิมทุกตัวอักษร**
  - จุดเสียบ 1: `DECL_RE = re.compile(` ใน `flashq.py` (ใกล้ `# ประกาศในแผน`) → เพิ่ม `exclusive` ในกลุ่ม `(files|parallel)` และอัปเดตคอมเมนต์ตัวอย่างบรรทัดบน
  - จุดเสียบ 2: ฟังก์ชัน `plan_meta` → parse `flashq-exclusive:` แบบเดียวกับ `flashq-files:` (ข้ามค่าที่มี placeholder `<...>` · แปลง `\` เป็น `/` · ข้ามโค้ดบล็อก) แต่เก็บแยกเป็นลิสต์ · ใส่คีย์ `out["exclusive"]` (sorted, ไม่ซ้ำ) **เฉพาะเมื่อมีค่า** (เหมือนคีย์ `why` — เทสต์เดิมเทียบ dict เต็ม ห้ามทำให้คีย์โผล่เมื่อไม่ได้ประกาศ)
  - จุดเสียบ 3: ฟังก์ชัน `job_info` → คืนเพิ่ม `"exclusive": meta.get("exclusive")` (None = ไม่ประกาศ)
  - จุดเสียบ 4: ใน `conflict_reason` บล็อกที่ขึ้นต้น `if not ia["parallel"] or not ib["parallel"]:` → พฤติกรรมใหม่:
    1. ฝั่งที่สั่ง no (`parallel` เป็น False) **ไม่มี** `exclusive` → ใช้โค้ดเดิมทั้งก้อน (คืนข้อความเดิม) — ถ้าสองฝั่งสั่ง no และฝั่งใดฝั่งหนึ่งไม่มี exclusive ก็ใช้ทางนี้
    2. ทุกฝั่งที่สั่ง no มี `exclusive` → ตรวจทีละฝั่ง X ที่สั่ง no: ไฟล์ของอีกฝั่ง (`info(...)["files"]`) เป็น None → คืน `"ดึงรายการไฟล์ของงานนั้นไม่ได้"` (ข้อความเดียวกับที่ใช้อยู่ด้านล่าง ไม่ใช่ข้อความใหม่) · มีไฟล์ของอีกฝั่งซ้อนกับ `X.exclusive` (ใช้ `paths_overlap`) → คืนหัวข้อความเดิมของฝั่งนั้น (`แผนสั่งให้รอ (flashq-parallel: no)` ถ้า X คือ `a` / `แผนของงานนั้นสั่งห้ามรันคู่ (flashq-parallel: no)` ถ้า X คือ `b` รวม ` · เหตุผลจากแผน: …`) ต่อด้วย ` · ขอบเขตห้ามรันคู่ซ้อนกับ: ` + ไฟล์ **ของอีกงาน** ที่ซ้อน (≤3 ตัว + `(+N)` เหมือนรูปแบบเดิม) · ไม่ซ้อน → **ไม่คืนค่า** ปล่อยไหลลงตรวจปกติด้านล่าง (ไฟล์ซ้อน/ไฟล์ร่วม)
    3. หัวข้อความที่ขึ้นต้น `แผนสั่งให้รอ` ต้องคงไว้ (ฟังก์ชัน `schedule` ใช้ `c.startswith("แผนสั่งให้รอ")` จัดรูปข้อความ)
  - เทสต์ (แก้ `test_plan_declarations_and_conflicts` เพิ่มท้ายส่วนแผนประกาศ · ห้ามลบแอสเซิร์ตเดิม):
    - เพิ่มแผนใน `self.proj`: `I.md` = `flashq-files: MapEditor/b.cpp` + `flashq-parallel: no — แตะ build` + `flashq-exclusive: Build/*, CMakeLists.txt` · `J.md` = `flashq-files: Client/z.cpp` · `K.md` = `flashq-files: Build/x.cmake`
    - `plan_meta(P,"I.md")["exclusive"] == ["Build/*", "CMakeLists.txt"]` · `"exclusive" not in plan_meta(P,"B.md")` · `job_info` ของ I.md มี `exclusive` เท่านั้น
    - `c("I.md","J.md") == ""` และ `c("J.md","I.md") == ""` (ไม่ซ้อน ไม่ชน แม้ I.md สั่ง no)
    - `c("I.md","K.md")` มี `"แผนสั่งให้รอ"` และ `"Build/x.cmake"` · `c("K.md","I.md")` มี `"flashq-parallel"` และ `"Build/x.cmake"`
    - `c("I.md","NOPE.md")` มี `"ดึงรายการไฟล์"` (อีกฝั่งดึงไม่ได้ = ชน)
    - แอสเซิร์ตเดิมของ D.md/H.md (ไม่มี exclusive → บล็อกทุกงานเหมือนเดิม) ต้องยังผ่านโดยไม่แก้
  - แดง (ก่อนแก้โค้ด): `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k plan_declarations_and_conflicts > .tmp/T-01.red.log 2>&1` → ต้อง FAIL ที่ `exclusive` (KeyError หรือ `'' != ...`) ไม่ใช่ error อื่น
  - เขียว: คำสั่งเดิม `> .tmp/T-01.green.log 2>&1` → `1 passed`
  - หลักฐานชี้ขาด: `.tmp/T-01.red.log` บรรทัดมี `FAILED`/`exclusive` · `.tmp/T-01.green.log` บรรทัดมี `1 passed`
  - commit: `flashq: flashq-parallel: no ผูกขอบเขตไฟล์ได้ด้วย flashq-exclusive: — ไม่ซ้อนกันก็รันพร้อมกันได้ (T-01)`

### กลุ่ม B — ไฟล์ร่วม ชนเมื่อทั้งสองฝ่ายแตะ

- [x] **T-02** `flashq.py` (`conflict_reason` ท้ายฟังก์ชัน) + `tests/test_flashq.py` (`test_plan_declarations_and_conflicts`) · แบบ: เทสต์ก่อน
  - จุดเสียบ: ใน `conflict_reason` บรรทัด `hit = sorted({x for x in ia["files"] + ib["files"] if shared_hit(x, sh, proj)})` ตามด้วย `if hit:` ที่คืน `"แตะไฟล์ที่ทุกโมดูลใช้ร่วม "`
  - ต้องเป็น: คำนวณไฟล์ร่วมที่แต่ละฝั่งแตะแยกกัน (ha จาก `ia["files"]`, hb จาก `ib["files"]`) · **ชนเมื่อ ha และ hb ไม่ว่างทั้งคู่** (ฝั่งเดียวแตะไม่ชน) · `hit` ที่ใส่ในข้อความ = ไฟล์ร่วมของสองฝั่งรวมกัน (sorted ไม่ซ้ำ) · ข้อความขึ้นต้น `แตะไฟล์ที่ทุกโมดูลใช้ร่วม ` เดิม
  - โหมดเข้ม (opt-in): `project_cfg(Path(proj)).get("parallel_shared_strict")` เป็นจริง → ชนเมื่อฝั่งใดฝั่งหนึ่งแตะไฟล์ร่วม (พฤติกรรมเดิม) · ค่าตั้งต้น = ไม่เข้ม · ตรวจก่อนว่า `project_cfg` ไม่ cache ข้ามการเปลี่ยนไฟล์ `.flash.json` ในเทสต์ (ถ้า cache ให้ล้าง cache ในเทสต์ ไม่ใช่แก้ตัว cache)
  - เทสต์ (แก้ส่วนแอสเซิร์ตเดิมที่ว่าด้วย E/F/G ใน `test_plan_declarations_and_conflicts` เพราะกฎใหม่ทำให้ค่าที่คาดเปลี่ยน — นี่คือแอสเซิร์ตเดียวที่อนุญาตให้เปลี่ยน):
    - เพิ่ม `E2.md` = `flashq-files: Common/y.h`
    - `c("E.md","B.md") == ""` · `c("F.md","B.md") == ""` · `c("G.md","B.md") == ""` (ฝั่งเดียวแตะไฟล์ร่วม ไม่ชนแล้ว)
    - `c("E.md","E2.md")` มี `"ใช้ร่วม"` (สองฝั่งแตะโฟลเดอร์ร่วม `Common/`) · `c("F.md","G.md")` มีทั้ง `"CMakeLists.txt"` และ `"Proto/p.h"`
    - เขียน `.flash.json` ใหม่เพิ่ม `"parallel_shared_strict": true` (คงคีย์เดิม `require_plan_in_remote` และ `parallel_shared`) → `c("E.md","B.md")` มี `"ใช้ร่วม"` และ `c("F.md","B.md")` มี `"CMakeLists.txt"` แล้ว**คืน `.flash.json` เดิม**ท้ายเทสต์
  - แดง: `... -k plan_declarations_and_conflicts > .tmp/T-02.red.log 2>&1` → FAIL ที่ `c("E.md","B.md") == ""` (ได้ข้อความ "ใช้ร่วม" แทนค่าว่าง)
  - เขียว: `> .tmp/T-02.green.log 2>&1` → `1 passed`
  - หลักฐานชี้ขาด: red log มี `FAILED` และ `ใช้ร่วม` · green log มี `1 passed`
  - commit: `flashq: ไฟล์ร่วมชนเมื่อทั้งสองงานแตะ (เดิมฝั่งเดียวก็ชน) · parallel_shared_strict ใน .flash.json คืนโหมดเดิม (T-02)`

### กลุ่ม C — กันอดตายล็อกเฉพาะงานที่ชนกับตัวที่อดตาย

- [x] **T-03** `flashq.py` (`schedule`) + `tests/test_flashq.py` (`test_auto_starvation_locks_head`) · แบบ: เทสต์ก่อน
  - จุดเสียบ (Grep `barrier` ใน `schedule` — มี 4 จุด): การประกาศ `free, start, reasons, barrier = ...` · บล็อก `if barrier:` ต้นลูป · `barrier = qid` ท้ายลูป · docstring ของ `schedule` ("ล็อกหัวคิว (งานหลังจากนั้นห้ามแซง)")
  - ต้องเป็น: เก็บงานที่อดตายเป็น**ลิสต์ของ dict งาน** (`barriers`) แทน id เดียว · ต้นลูปแต่ละงาน q: วนทุก b ใน barriers เรียก `conflict_reason(q, b, info)` · ชน → `reasons[qid]` = `f"ชนกับ {b['id']} ที่รอนานเกิน {starve:g} นาที ({เหตุ}) → รอให้ {b['id']} เริ่มก่อน (กันอดตาย)"` แล้ว `continue` · ไม่ชนกับ barrier ใด → ไหลลงตรวจปกติ (ชนกับงานที่กำลังรัน/ช่องว่าง) ตามเดิม · ท้ายลูป: งานที่รอเกิน starve เพราะชน → `barriers.append(q)` (ไม่ทับตัวเก่า) และคงข้อความเดิม `รอเกิน … → ล็อกหัวคิว` ต่อท้ายเหตุของงานนั้น
  - อัปเดต docstring/คอมเมนต์ให้ตรงกฎใหม่ ("งานหลังจากนั้นที่ชนกับมันห้ามแซง")
  - เทสต์ (แก้ `test_auto_starvation_locks_head` — เปลี่ยนแอสเซิร์ตที่ขัดกฎใหม่ ที่เหลือคงไว้):
    - ก่อนส่ง T-03 ให้เขียน `PLAN.md` ใหม่เพิ่มบรรทัด `- [ ] **T-04** \`src/a.cpp\`` (T-04 ชน T-01 และ T-02) · ส่ง T-04 หลัง T-03 เริ่มแล้ว
    - T-03 (`src/c.cpp` ไม่ชน T-02) **ต้องเริ่มระหว่างที่ T-01 ยังรัน**: `started` ของ T-03 < `finished` ของ T-01 (ใช้ `wait_for` สถานะ running/ok เหมือนเทสต์ `test_auto_skip_conflict_and_overlap_waits`)
    - `status` ต้องมี `"ล็อกหัวคิว"` และ `"กันอดตาย"` (จาก T-04) · T-04 ยัง `queued` ตอนนั้น · T-04 `started` >= T-01 `finished`
    - ผลทุกตัวต้อง `FLASH_RUN=OK`
  - แดง: `... -k auto_starvation_locks_head > .tmp/T-03.red.log 2>&1` → FAIL ที่ T-03 ไม่เริ่ม/`wait_for` หมดเวลา (ยังถูกล็อกหัวคิวทั้งคิว)
  - เขียว: `> .tmp/T-03.green.log 2>&1` → `1 passed` · แล้วรันคลุมกลุ่มจัดคิว `-k "auto_ or schedule or parallel_two_slots or starvation"` `> .tmp/T-03.group.log 2>&1` → ไม่มี failed
  - หลักฐานชี้ขาด: red log มี `FAILED` · green log มี `1 passed` · group log บรรทัดสรุป `N passed` ไม่มี `failed`
  - commit: `flashq: กันอดตายล็อกเฉพาะงานที่ชนกับงานที่อดตาย — งานที่ไม่ชนแซงได้ (T-03)`

### กลุ่ม D — เอกสาร + แม่แบบ

- [x] **T-04** `docs/REFERENCE.md` · `docs/ARCHITECTURE.md` · `CHANGELOG.md` · `templates/FLASH_PLAN_TEMPLATE.md` · `claude/commands/flash-plan.md`
  - `docs/REFERENCE.md` (Grep `flashq-parallel: no` ย่อหน้า "ชน"): แก้คำอธิบายกฎชนให้ตรงโค้ดใหม่ — `flashq-parallel: no` + `flashq-exclusive:` (ขอบเขตห้ามรันคู่ · ไม่ใส่ = บล็อกทั้งโปรเจกต์เหมือนเดิม) · ไฟล์ร่วมชนเมื่อทั้งสองงานแตะ + `parallel_shared_strict` · กันอดตายล็อกเฉพาะงานที่ชนกับงานที่อดตาย
  - `docs/ARCHITECTURE.md` (แถว `จัดคิวอัตโนมัติ`): เพิ่ม `flashq-exclusive` ในรายการที่ `plan_meta` อ่าน
  - `CHANGELOG.md`: เพิ่มหัวข้อใหม่ด้านบนสุดตามรูปแบบเดิม (ดูหัวข้อบนสุดของไฟล์) ว่ากฎรอคิวแม่นขึ้น 3 ข้อ + วิธีใช้ `flashq-exclusive` + หมายเหตุว่า doc/qa ยังชนทั้งโปรเจกต์โดยตั้งใจ (เหตุผล: ตัดสินจากไฟล์เปลี่ยน/HEAD ทั้งโปรเจกต์)
  - `templates/FLASH_PLAN_TEMPLATE.md` คอมเมนต์ใต้ `## 0.`: เพิ่มบรรทัดแนะนำ `flashq-exclusive: <path/glob ที่ห้ามงานอื่นแตะ>` ใช้คู่ `flashq-parallel: no` (ใส่ได้ ไม่ใส่ก็ได้ · ห้ามเพิ่มบรรทัดประกาศจริงเข้าแม่แบบ เพราะ parser อ่านแม่แบบเป็นแผนได้)
  - `claude/commands/flash-plan.md` §3 (ข้อที่พูดถึง `flashq-parallel: no`): เติมว่าควรเขียน `flashq-exclusive:` ระบุขอบเขตเสมอเมื่อใช้ `no` เพื่อไม่ให้บล็อกงานที่ไม่ชน · ข้อความสั้น 1 ประโยค
  - ยืนยัน: `python -c "import ast,sys;ast.parse(open('flashq.py',encoding='utf-8').read())"` > `.tmp/T-04.syntax.log` ไม่มี error · `git diff --stat` ของงานนี้แตะเฉพาะไฟล์ในรายการ · Grep `flashq-exclusive` เจอใน REFERENCE.md, CHANGELOG.md, template, flash-plan.md ≥ 4 ไฟล์ (บันทึกผล Grep ลง `.tmp/T-04.grep.log`)
  - หลักฐานชี้ขาด: `.tmp/T-04.grep.log` มี `flashq-exclusive` ≥ 4 ไฟล์ · `.tmp/T-04.syntax.log` ว่าง
  - commit: `flashq: เอกสาร + แม่แบบ + คำสั่ง flash-plan — flashq-exclusive และกฎรอคิวใหม่ (T-04)`

## 2. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- **ข้อ 4 ของคำสั่ง (doc/qa ชนตามขอบเขต) ยังไม่ทำ** — ทำให้ปลอดภัยไม่ได้ถ้าไม่แก้กลไกตัดสินผล: `doc_verdict` ล้มด้วย OUTSIDE/CHANGED เมื่อมีใครแก้/commit ในโปรเจกต์ระหว่างรัน และ qa ทิ้งผลเมื่อ HEAD เปลี่ยน (`flashq.py:2970`) · ทางเลือก: (ก) คงชนทั้งโปรเจกต์ (ค่าตอนนี้) (ข) qa opt-in `qa.presets.<ชื่อ>.paths` + ตัดสิน "HEAD เปลี่ยน" เฉพาะเมื่อไฟล์ในขอบเขตเปลี่ยนจริง (ค) ให้ worker รันใน worktree แยก — รอผู้ใช้เลือก

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|
| T-01 | ✅แก้ | 635b3b1 | `.tmp/T-01.red.log` `KeyError: 'exclusive'` + `FAILED` · `.tmp/T-01.green.log` `1 passed` (`.tmp/T-01.extra.log` `7 passed` กันถดถอย) | |
| T-02 | ✅แก้ (จด: worker amend commit ของตัวเองให้รวมไฟล์แผน → hash จริง `fb6e16c` แทน `f5c3aee` ที่ worker จดไว้) | fb6e16c | `.tmp/T-02.red.log:49` `FAILED` + `:44` `'แตะไฟล์ที่ทุกโมดูลใช้ร่วม Common/x.h' != ''` · `.tmp/T-02.green.log:2` `1 passed` | |
| T-03 | ✅แก้ (จด: ปรับ sleep ของ T-01 14→30 วิ + `wait_for` ของ T-03 `sec=10` เพราะ 4 การ submit ทำให้เวลารวมยืด — แอสเซิร์ตตามแผนไม่เปลี่ยน · red log ล้มที่แอสเซิร์ต `T-03 ไม่ได้แซง` ไม่ใช่ข้อความ wait_for timeout ตรงตัว) | 26d94d9 | `.tmp/T-03.red.log:28` `AssertionError: T-03 ไม่ได้แซง (ยังถูกล็อกทั้งคิว)` + `:30` `FAILED` · `.tmp/T-03.green.log:2` `1 passed` · `.tmp/T-03.group.log:2` `7 passed` ไม่มี failed | |
| T-04 | ✅แก้ | aad78fd | `.tmp/T-04.grep.log` `flashq-exclusive` เจอ 4 ไฟล์ (REFERENCE.md, CHANGELOG.md, templates/FLASH_PLAN_TEMPLATE.md, claude/commands/flash-plan.md) · `.tmp/T-04.syntax.log` ว่าง (0 ไบต์) | |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- ข้อเสนอที่ผู้สืบเสนอแต่ Claude ยังไม่ได้ยืนยัน: `paths_overlap` เทียบชื่อไฟล์เปล่ากับ path เต็ม (`:1030-1031`) · `take_slot` ตรวจแล้วจองไม่ใช่ขั้นเดียว · โหมด FIFO ไม่ตรวจไฟล์ · ข้อความ "ช่อง x/y" ในโหมด auto

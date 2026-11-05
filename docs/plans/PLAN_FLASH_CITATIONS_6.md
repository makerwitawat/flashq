# แผน CITATIONS 6 — แยก "ผิดจริง / ตรวจไม่ได้ / เลขเพี้ยน" ให้งานสืบไม่ตกเป็น OK_UNVERIFIED เพราะตรวจไม่ได้

> แม่แบบแผนกลาง (flashq) — Claude วางแผน+ตรวจ · DeepSeek ลงมือ
> สร้าง 2026-11-05 · ส่งงาน: `{{FLASHQ_RUN}} run docs/plans/PLAN_FLASH_CITATIONS_6.md T-01..T-07` · base commit ตอนวางแผน: `18c6c87`

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, tests/test_flashq.py, opencode/agent/flash-investigator.md, claude/agents/*, claude/commands/flash-investigate.md, claude/commands/flash-plan.md, docs/REFERENCE.md, CHANGELOG.md
flashq-parallel: yes

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- <ไฟล์ของงาน>` + `git commit -m "<ข้อความในงาน>"`) · **ห้าม push** · ห้าม `git add -A`/`git add .`/`git stash`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment/แปลง encoding
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "ก่อน" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนไว้ตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · **หลักฐานชี้ขาด = path log + บรรทัด/ค่าที่แผนกำหนด ตรงตัว**) · หลักฐานไม่ครบ = งานไม่จบ
6. **ห้ามแตะ**: `%USERPROFILE%\.flashq\` · `ui.html` · ไฟล์นอก `flashq-files` · ห้ามรัน `python flashq.py install` (เป็นขั้นหลังแผนของ Claude)
7. **งานแบบ "เทสต์ก่อน"**: เขียนเทสต์ → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (log "แดง") → แก้โค้ด → รันซ้ำต้อง PASS (log "เขียว") → commit เดียว · ผ่านตั้งแต่ก่อนแก้/ล้มด้วยเหตุอื่น (SyntaxError, ImportError) → **⛔ หยุด** · ห้ามแก้เทสต์ให้ผ่านแทนการแก้โค้ด — **ยกเว้น** assertion เดิมที่แผนสั่งให้เปลี่ยนค่าตรงตัว (ระบุไว้ในงาน)
8. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน" ตรง ๆ
9. stdlib ล้วน (ห้ามเพิ่ม dependency) · ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย · commit ภาษาไทยขึ้นต้น `flashq:` · ไฟล์ชั่วคราวไว้ `.tmp/`
10. เทสต์ใหม่วางใน class `FlashqTest` ต่อจาก `test_check_citations_short_names_code_spans_and_clauses` · repo จำลองใช้ `tempfile.TemporaryDirectory()` + `git init -q -b main` + `git add -A` แบบเดียวกับเทสต์นั้น (check_citations ใช้ `git ls-files`) · เรียก `unverified_reasons` ตรงผ่าน `self.load_mod("<ชื่อ>")`

### คำสั่งมาตรฐาน (PowerShell · timeout ≥ 300 วิ · ทั้งชุด ≥ 500 วิ)
```
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k "<คำค้น>" > .tmp/T-xx.<red|green|reg>.log 2>&1
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q > .tmp/T-05.full.log 2>&1
```

---

## 1. กลุ่ม A — ตัวตรวจ citation แยก 3 กลุ่ม
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว · ดู `.tmp/cite_evidence.md`): งานสืบ IRIS_CODE_1.2 26 งาน → `citations.bad` 202 จุด = ชื่อกำกวม 48% · ไม่พบไฟล์ (path ย่อ `.../x.js`, token `grid.show:298`, ไฟล์ untracked) 26% · ห่างเกิน ±3 25% · ผิดจริงแค่ 3 จุด
- `flashq.py` `_cite_file` ~562: ชื่อซ้ำเลือกไม่ได้ → `return None, f"ชื่อไฟล์กำกวม (ตรง {len(pool)} ไฟล์ …` (ทิ้งรายชื่อไฟล์ ไม่ลองเทียบข้อความ)
- `check_citations` ~607: ทุกกรณีลง `bad` รวมกัน · `unverified_reasons` ~1985: `if bad:` → OK_UNVERIFIED ทันทีแม้ 1 จุด
- ผู้เรียก `check_citations`: ~2591 (งานสืบ · พิมพ์ `CITATIONS:`) และ ~3531 (ตรวจเอกสาร flash-doc · ใช้แค่ `["bad"]` — ไม่แตะ)

- [x] **T-01** `flashq.py` ~607 (`check_citations`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_check_citations_groups` (repo จำลอง: `src/a.py` 60 บรรทัด โดยบรรทัด 10 = `def target():` บรรทัดอื่น `x_<n> = <n>` · `lib/util.py` 3 บรรทัด) ตรวจว่า dict ที่คืนมี key `ok` `ok_code` `bad` `unresolved` `drift` (list ของข้อความ) และ:
    1. ``"`src/a.py:10` — `def target():`"`` → ok 1, ok_code 1
    2. ``"`src/a.py:20` — `def target():`"`` (ห่าง 10 ≤ 40) → `drift` 1 รายการ มีคำ `บรรทัด 10` · ไม่นับใน ok/bad
    3. ``"`src/a.py:58` — `def target():`"`` (ห่าง 48 > 40) → `bad` 1 · ``"`src/a.py:10` — `def ghost_fn():`"`` → `bad` 1
    4. ``"`.../src/a.py:10` — `def target():`"`` (path ย่อแต่ส่วนท้ายชี้ไฟล์เดียว) → ok_code 1 · ``"`.../nope/zz.js:5` ดู"`` → `unresolved` 1 มีคำ `path ย่อ`
    5. ``"`grid.show:298` ดู"`` และ ``"`path_icon.txt:3` ดู"`` (ชื่อเปล่าไม่มี `/` หาไม่เจอ) → `unresolved` 2 · ``"`src/ghost.py:1` ดู"`` (มี `/` ไม่มีจริง) → `bad` 1 มีคำ `ไม่พบไฟล์`
    6. ``"`src/a.py:999` ดู"`` → `bad` 1 มีคำ `เลขบรรทัดเกินไฟล์`
  - แดง (ก่อนแก้): `-k "check_citations_groups"` → `.tmp/T-01.red.log` ต้องมี `KeyError: 'unresolved'` หรือ `KeyError: 'drift'` (key ใหม่ยังไม่มี)
  - แก้ (สเปก · จุดเสียบ `return {"ok": ok, "ok_code": code, "bad": bad}` และ `f, why = _cite_file(rel, root, tracked, anchors)`):
    - ค่าคงที่ใหม่ `CITE_DRIFT = 40` ข้าง `CITE_NEAR` · คืน `{"ok", "ok_code", "bad", "unresolved", "drift"}` (key เดิมความหมายเดิม)
    - **path ย่อ** (`rel` มี `...`/`…` หรือขึ้นต้น `/` หรือตัวอักษรก่อน match ใน text เป็น `…`): ตัดข้อความตั้งแต่ต้นจนถึง `...`/`…` ตัวสุดท้าย แล้วตัด `/` นำหน้าออก (`.../src/a.py` → `src/a.py` · `D:/.../Tool/x.py` → `Tool/x.py`) → ส่วนท้ายส่งเข้า `_cite_file` ตามปกติ · หาไม่เจอ/กำกวม → `unresolved` ข้อความ `"{rel}:{line} — path ย่อ ตรวจไม่ได้ — ต้องระบุ path เต็มจากรากโปรเจกต์"`
    - **ไม่พบไฟล์**: `rel` มี `/` (และไม่ใช่ path ย่อ) → `bad` (เดิม) · ไม่มี `/` (ชื่อเปล่า/token เช่น `grid.show`) → `unresolved` `"… — ไม่พบในไฟล์ที่ git ติดตาม (อาจไม่ใช่ไฟล์/ไฟล์ untracked)"`
    - **ชื่อกำกวม** (`why` ขึ้นต้น `ชื่อไฟล์กำกวม`) → `unresolved` (ข้อความ `why` เดิม) — T-02 จะทำให้ลองเทียบข้อความก่อน
    - **drift**: เมื่อ verdicts ทุกตัว miss (จุดเดิม `ข้อความที่คัดไว้ไม่อยู่ในบรรทัดนี้ (±3)`) → ไล่บรรทัด n ใน `[line-40, line+40]` (ตัดขอบไฟล์) เรียงจากใกล้ไปไกล หาบรรทัดแรกที่ `_cite_snippet_ok(miss[0], lines[n-1])` (บรรทัดเดียว ไม่ใช้หน้าต่าง — กันได้เลขคลาดไป 1) เป็น True → `drift` ข้อความ `"{rel}:{line} — ข้อความที่คัดอยู่ที่บรรทัด {n} (ห่าง {abs(n-line)} บรรทัด · เลขเพี้ยน): `{miss[0][:60]}`"` · ไม่เจอ → `bad` ข้อความเดิม
    - ทางข้อความไกล (`if not verdicts and far:` → `ไม่มีในไฟล์นี้เลย`) และ `อ่านไฟล์ไม่ได้`/`เลขบรรทัดเกินไฟล์` = คงเดิม (ยังเป็น `bad`)
    - ห้ามแตะ ~3531 (`check_citations(text, root)["bad"]`)
  - เทสต์เดิมที่ต้องเปลี่ยนค่าตรงตัว (ใน `test_check_citations_short_names_code_spans_and_clauses`) — เฉพาะ 2 จุดนี้:
    - ก่อน: `self.assertEqual(len(r["bad"]), 2)` → หลัง: `self.assertEqual((r["bad"], len(r["unresolved"])), ([], 2))` และ 2 บรรทัดถัดไป `r["bad"][0]`/`r["bad"][1]` → `r["unresolved"][0]`/`r["unresolved"][1]` (คำ `กำกวม` และ `ไม่พบ`)
    - ก่อน: `self.assertEqual(len(r["bad"]), 3)` → หลัง: `self.assertEqual((len(r["bad"]), len(r["drift"])), (2, 1))` · บรรทัด assert `r["bad"][1]` (ไม่อยู่ในบรรทัดนี้) → `self.assertIn("บรรทัด 2", r["drift"][0])` · `r["bad"][2]` (เลขบรรทัดเกินไฟล์) → `r["bad"][1]`
    - ข้อ `assertEqual(chk("เปิด `127.0.0.1:8219…"), {...})` ใส่ key ใหม่ `"unresolved": [], "drift": []` ใน dict ที่คาด
  - เขียว: คำสั่งเดิม → `.tmp/T-01.green.log` · reg `-k "cit"` → `.tmp/T-01.reg.log`
  - หลักฐานชี้ขาด: red บรรทัด `KeyError: 'unresolved'` · green/reg บรรทัดท้าย `passed` ไม่มี `failed`
  - commit: `flashq: ตรวจ citation แยก ผิดจริง/ตรวจไม่ได้/เลขเพี้ยน (path ย่อ · ชื่อเปล่า · ห่างไม่เกิน 40 บรรทัดบอกเลขที่ถูก) (T-01)`

- [ ] **T-02** `flashq.py` ~562 (`_cite_file`) + ~607 (`check_citations`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_check_citations_ambiguous_tries_all` (repo จำลอง: `a/app.js` = `["var a = 1;", "function boot() {", "}"]` · `b/app.js` = `["var b = 2;", "x = 0;", "function render(p) {", "}"]` · ไม่มี citation path เต็มอื่นเป็น anchor):
    1. ``"`app.js:3` — `function render(p) {`"`` → ok 1, ok_code 1, unresolved []
    2. ``"`app.js:2` — `function boot() {`"`` → ok_code 1 (ตรงใน a/app.js)
    3. ``"`app.js:1` — `const ghost = 9;`"`` (ไม่ตรงทุกไฟล์) → `bad` 1 มีคำ `ทุกไฟล์ที่ชื่อตรง`
    4. ``"`app.js:1` ดู"`` (ไม่มีข้อความคัด) → `unresolved` 1 มีคำ `กำกวม`
  - แดง: `-k "ambiguous_tries_all"` → `.tmp/T-02.red.log` ต้องมี `AssertionError: 0 != 1` (ข้อ 1: หลัง T-01 ชื่อกำกวมลง unresolved ok = 0)
  - แก้ (สเปก):
    - `_cite_file` คืน 3 ค่า `(Path | None, str, list[str])` — ค่าที่ 3 = รายชื่อไฟล์ผู้สมัคร (`pool`) เมื่อกำกวม · กรณีอื่น `[]` · ผู้เรียกมีแค่ `check_citations` (Grep `_cite_file(` ยืนยัน)
    - กำกวม + มีข้อความคัด (verdicts ไม่ว่าง หลังกรอง None): ตัดสินกับทุกไฟล์ใน pool ด้วยกติกาเดียวกับ T-01 (เลขเกินไฟล์ของไฟล์นั้น = ข้ามไฟล์นั้น) · ≥1 ไฟล์ตรง ±3 → ok + ok_code · ไม่มีตรง แต่ ≥1 ไฟล์ drift → `drift` ข้อความระบุไฟล์ `"{rel}:{line} → {path}:{n} …"` · ไม่ตรงเลย → `bad` `"{rel}:{line} — ข้อความที่คัดไม่อยู่ในทุกไฟล์ที่ชื่อตรง ({len(pool)} ไฟล์): `…`"`
    - กำกวม + ไม่มีข้อความคัด → `unresolved` (ข้อความเดิมของ `why`)
    - แยกส่วน "ตัดสินไฟล์เดียว" เป็น helper ภายในได้ เพื่อใช้ซ้ำกับทุกไฟล์ใน pool (ห้ามเปลี่ยนพฤติกรรมไฟล์เดียว)
  - เขียว: คำสั่งเดิม → `.tmp/T-02.green.log` · reg `-k "cit"` → `.tmp/T-02.reg.log`
  - หลักฐานชี้ขาด: red บรรทัด `AssertionError: 0 != 1` · green/reg บรรทัดท้าย `passed` ไม่มี `failed`
  - commit: `flashq: ชื่อไฟล์กำกวมลองเทียบข้อความกับทุกไฟล์ที่ชื่อตรงก่อนตัดสิน (T-02)`

- [ ] **T-03** `flashq.py` ~1985 (`unverified_reasons`) + ~2593 (พิมพ์ `CITATIONS:`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_unverified_reasons_citation_groups` (ใช้ `self.load_mod("flashq_cite_groups")`) · `c(**kw)` = `{"kind": "investigate", "prompt": "ขอ file:line", "citations": {"ok": 0, "ok_code": 0, "bad": [], "unresolved": [], "drift": [], **kw}}`:
    1. `ok=2, ok_code=2, unresolved=["u"], drift=["d"]` → `[]`
    2. `ok=1, ok_code=1, bad=["b"]` → มีข้อความขึ้นต้น `ผู้สืบอ้างเลขไฟล์:บรรทัดผิด 1 จุด`
    3. `unresolved=["u1","u2","u3"], drift=["d"]` (ok_code 0) → `["ตรวจ citation ไม่ได้เกือบทั้งหมด (ตรวจไม่ได้ 3 จาก 4 จุด)"]`
    4. `ok=1, ok_code=0, unresolved=["u"]` (ไม่เกินครึ่ง) → `[]` · ทุก key ว่าง → `["ผู้สืบไม่อ้างเลขไฟล์:บรรทัดเลย"]` · งานเก่าไม่มี key `unresolved`/`drift` (`{"ok": 1, "ok_code": 1, "bad": []}`) → `[]`
  - แดง: `-k "unverified_reasons_citation_groups"` → `.tmp/T-03.red.log` ต้องมี `AssertionError` ที่ข้อ 3 (`[] != ['ตรวจ citation ไม่ได้เกือบทั้งหมด …']` หรือได้ `['ผู้สืบไม่อ้างเลขไฟล์:บรรทัดเลย']`)
  - แก้ ① `unverified_reasons` (สเปก · จุดเสียบ ก่อน: `out.append(f"ผู้สืบอ้างเลขไฟล์:บรรทัดผิด {len(bad)} จุด")`):
    - อ่าน `unres = cites.get("unresolved") or []` · `drift = cites.get("drift") or []` · `total = (cites.get("ok") or 0) + len(bad) + len(unres) + len(drift)`
    - ลำดับ: `bad` → เดิม · `elif total == 0` + บรีฟขอเลขบรรทัด → `ผู้สืบไม่อ้างเลขไฟล์:บรรทัดเลย` (เดิมเช็ค `not ok` → เปลี่ยนเป็น `total == 0`) · `elif len(unres) * 2 > total and not cites.get("ok_code")` → `f"ตรวจ citation ไม่ได้เกือบทั้งหมด (ตรวจไม่ได้ {len(unres)} จาก {total} จุด)"` · drift ไม่ลดผล
  - แก้ ② พิมพ์ผล (ก่อน: `if cites["ok"] or cites["bad"]:`) → เงื่อนไขรวม `unresolved`/`drift` · บรรทัดหลักคงหัวเดิมแล้วต่อท้าย: `CITATIONS: ตรงถึงโค้ด {ok_code} · ตรงแค่ไฟล์/บรรทัด {ok-ok_code} · ผิด {len(bad)} · ตรวจไม่ได้ {len(unres)} · เลขเพี้ยน {len(drift)}` + (มี bad → ` — Claude ต้องไม่เชื่อข้อที่ผิด (✗):`) · รายการ: `  ✗ ` bad ≤10 · `  ↕ ` drift ≤10 (มีเลขบรรทัดที่ถูก) · `  ? ` unresolved ≤5 + `  ? … อีก N จุด` ถ้าเกิน
  - เทสต์เดิม `test_investigate_checks_citations` — เพิ่ม assert เดียว: `self.assertIn("· ตรวจไม่ได้ 0 · เลขเพี้ยน 0", r.stdout)` (assert `CITATIONS: ตรงถึงโค้ด 1 · ตรงแค่ไฟล์/บรรทัด 1 · ผิด 3` เดิมต้องผ่านโดยไม่แก้)
  - เขียว: คำสั่งเดิม → `.tmp/T-03.green.log` · reg `-k "cit or unverified or brief_gate"` → `.tmp/T-03.reg.log`
  - หลักฐานชี้ขาด: red บรรทัด `AssertionError` ข้อ 3 · green/reg บรรทัดท้าย `passed` ไม่มี `failed` · reg มี `test_investigate_checks_citations`/`brief_gate` ผ่าน
  - commit: `flashq: งานสืบลดผลเฉพาะ citation ผิดจริง · ตรวจไม่ได้/เลขเพี้ยนแสดงแยก ไม่ลดผล (T-03)`

## 1b. กลุ่ม B — ผู้สืบอ้างให้ตรวจได้
- [ ] **T-04** `opencode/agent/flash-investigator.md` ~56 (ข้อ 3)
  - ก่อน: `3. ทุกข้ออ้างต้องมี `file:line` และข้อเท็จจริงที่เห็นตรงตัว (คัดบรรทัดโค้ด) · เดา = ใส่ใน "ยังไม่แน่ใจ"`
  - หลัง (คงข้อเดิม แล้วเติมย่อยท้ายข้อ 3 ไม่เกิน 3 บรรทัด): (ก) `file` = path เต็มจากรากโปรเจกต์ (เช่น `Tools/web/app.js:120`) **ห้ามย่อ** `...`/`…`/`D:/...` (ข) เลขบรรทัดเอาจากผล Grep/Read ที่เห็นจริงเท่านั้น ห้ามนับเอง/กะประมาณ (ค) ชื่อไฟล์ซ้ำในโปรเจกต์ (เช่น `app.js` หลายโฟลเดอร์) ต้องระบุโฟลเดอร์เสมอ · คัดโค้ดใส่ `` `...` `` ติดหลัง citation
  - หมายเหตุ: `claude/agents/` มีแค่ `flash-checker.md` (ไม่มีฉบับคู่ของผู้สืบ) — ไม่ต้องแก้ · templates ไม่มีบรีฟผู้สืบที่ซ้ำกฎนี้
  - ยืนยัน: Grep `path เต็มจากรากโปรเจกต์` ใน `opencode/agent/flash-investigator.md` → 1 ที่ · Grep `ห้ามนับเอง` → 1 ที่ (จดผลใน `.tmp/T-04.grep.txt`)
  - หลักฐานชี้ขาด: `.tmp/T-04.grep.txt` มี 2 บรรทัดที่เจอ (ค่าก่อนแก้ = 0 ที่)
  - commit: `flashq: ผู้สืบต้องอ้าง path เต็ม เลขบรรทัดจาก Grep จริง และระบุโฟลเดอร์เมื่อชื่อซ้ำ (T-04)`

## 1c. กลุ่ม C — เทสต์รวม + เอกสาร
- [ ] **T-05** `tests/test_flashq.py` (เทสต์ปลายทาง + ทั้งชุด)
  - เพิ่ม `test_investigate_unresolved_does_not_downgrade` (ต่อจาก `test_investigate_checks_citations` · ใช้ `self.proj`): `src/a.cpp` 30 บรรทัด (บรรทัด 5 = `int target = 1;`) · FAKE_TEXT 3 บรรทัด: ``src/a.cpp:5 — `int target = 1;` `` · ``src/a.cpp:15 — `int target = 1;` `` · ``.../x.js:7 ดู`` → stdout มี `ผิด 0 · ตรวจไม่ได้ 1 · เลขเพี้ยน 1` และ `บรรทัด 5` · job ล่าสุด: ทุกข้อใน `job.get("unverified") or []` ต้องไม่มีคำ `citation` และ `ไฟล์:บรรทัด` (เหตุอื่นของ fake opencode ไม่เกี่ยว) · `len(job["citations"]["drift"]) == 1`
  - ยืนยัน: `-k "unresolved_does_not_downgrade"` → `.tmp/T-05.green.log` · `-k "cit or unverified"` → `.tmp/T-05.reg.log` · ทั้งชุด → `.tmp/T-05.full.log` (timeout ≥ 500 วิ)
  - หลักฐานชี้ขาด: green มี `passed` · full.log บรรทัดท้าย `N passed` ไม่มี `failed`/`error` (ถ้ามีเทสต์ล้มที่ไม่เกี่ยว citation → จดชื่อใน §4 แล้ว ⛔ ไม่แก้)
  - commit: `flashq: เทสต์งานสืบที่มี citation ตรวจไม่ได้/เลขเพี้ยนยังได้ผล OK (T-05)`

- [ ] **T-06** `docs/REFERENCE.md` + `CHANGELOG.md` + `claude/commands/flash-investigate.md` (+ `claude/commands/flash-plan.md` เป็นงาน T-07 แยก commit เพื่อไม่เกิน 3 ไฟล์)
  - `docs/REFERENCE.md` ก่อน: `` - `CITATIONS:` ของผู้สืบ = "ตรงถึงโค้ด" `` (บรรทัดเดียว) → หลัง: อธิบาย 5 ช่อง ตรงถึงโค้ด · ตรงแค่ไฟล์/บรรทัด · **ผิด** (ลดผลเป็น OK_UNVERIFIED) · **ตรวจไม่ได้** (ชื่อกำกวม/path ย่อ/ไม่ใช่ไฟล์ — ไม่ลดผล เว้นแต่เกินครึ่งและไม่มีข้อที่ตรงถึงโค้ด) · **เลขเพี้ยน** (ข้อความอยู่ห่าง ≤40 บรรทัด บอกเลขที่ถูก — ไม่ลดผล) · คงประโยค "พิสูจน์ได้แค่ว่าโค้ดที่อ้างมีจริง…"
  - `CHANGELOG.md`: เพิ่มหัว `## 2026-11-05` เหนือ `## 2026-11-04` + 1 bullet: **CITATIONS แยก ผิด/ตรวจไม่ได้/เลขเพี้ยน** — งานสืบลดเป็น OK_UNVERIFIED เฉพาะอ้างผิดจริง · ชื่อกำกวมลองทุกไฟล์ที่ชื่อตรง · ผู้สืบต้องอ้าง path เต็ม (T-01..T-07)
  - `claude/commands/flash-investigate.md` ก่อน: `` - บรรทัด `CITATIONS: ตรงถึงโค้ด N · ตรงแค่ไฟล์/บรรทัด K · ผิด M` `` → หลัง: รูปบรรทัดใหม่ 5 ช่อง · ✗ = ห้ามเชื่อ · ↕ = ใช้เลขบรรทัดที่ถูกแทน · ? = ส่งผู้สืบรอบใหม่ให้อ้าง path เต็ม (เฉพาะข้อที่เป็นข้อสรุปหลัก) · ข้อ `6. CITATIONS ไม่มีข้อผิดในข้อสรุปหลัก` → `6. CITATIONS ไม่มี ✗ (ผิด) ในข้อสรุปหลัก · ? ในข้อสรุปหลัก = ขอ path เต็ม`
  - ยืนยัน: Grep `เลขเพี้ยน` ใน 3 ไฟล์ → อย่างน้อย 1 ที่ต่อไฟล์ → `.tmp/T-06.grep.txt`
  - หลักฐานชี้ขาด: `.tmp/T-06.grep.txt` มีครบ 3 ไฟล์ (ค่าก่อนแก้ = 0)
  - commit: `flashq: เอกสาร CITATIONS 3 กลุ่ม (ผิด/ตรวจไม่ได้/เลขเพี้ยน) + CHANGELOG (T-06)`

- [ ] **T-07** `claude/commands/flash-plan.md` ~32 และ ~35
  - ก่อน: `` บรรทัด `CITATIONS ... ผิด` = ข้อนั้นห้ามเชื่อ `` → หลัง: `` บรรทัด `CITATIONS` ข้อ ✗ (ผิด) = ห้ามเชื่อ · ↕ (เลขเพี้ยน) ใช้เลขที่ถูก · ? (ตรวจไม่ได้) ในข้อสรุปหลัก = สืบใหม่ให้อ้าง path เต็ม ``
  - ~35: คำ `CITATIONS ผิด` (2 ที่ในบรรทัด "ผลสืบไม่พอ/กำกวม/CITATIONS ผิด" และ "CITATIONS ไม่ผิด") คงไว้ได้ (ความหมายยังตรง "ผิด" = ✗) — ไม่แก้
  - ยืนยัน: Grep `เลขเพี้ยน` ใน `claude/commands/flash-plan.md` → 1 ที่ → `.tmp/T-07.grep.txt`
  - หลักฐานชี้ขาด: `.tmp/T-07.grep.txt` 1 บรรทัด (ก่อนแก้ 0)
  - commit: `flashq: flash-plan อ่าน CITATIONS 3 กลุ่ม (T-07)`

## 2. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- ตัวตรวจเอกสาร (flash-doc · `flashq.py` ~3531) ใช้แค่ `["bad"]` → หลังแผนนี้ ชื่อเปล่าที่ไม่มีจริง/ชื่อกำกวมในเอกสารจะไม่เป็น BADREF อีก (path เต็มที่ไม่มี/เลขเกินไฟล์ยังเป็น BADREF · `test_bad_refs_missing_files_and_citations` ยังผ่าน) — ค่าเริ่มต้นแผนนี้ = ไม่แตะ · ถ้าอยากให้เอกสารเข้มเท่าเดิม ให้เพิ่ม `unresolved` เข้า ~3531 ในรอบถัดไป

## ขั้นหลังแผน (Claude ทำ ไม่ใช่งานของ Flash)
- ตรวจ `/flash-check` → merge เข้า master → `python flashq.py install` จาก checkout หลัก `D:\MyCode\flashq` (คำสั่ง/agent ที่ติดตั้งใช้ได้ใน session ใหม่) → รีสตาร์ต `flashq ui` (พอร์ต 4097)

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|
| T-01 | ✅แก้ | - | `.tmp/T-01.red.log:28` `KeyError: 'unresolved'` · `.tmp/T-01.green.log` บรรทัดท้าย `1 passed` · `.tmp/T-01.reg.log` บรรทัดท้าย `6 passed` | |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- หน้าเว็บ (`ui.html`) แสดง unresolved/drift แยก — ยังไม่ทำ (เหตุผลลดผลแสดงอยู่แล้วจาก `unverified`)
- `hooks/inbox_notify.py` ข้อความ "ดูบรรทัด CITATIONS ใน log" ยังถูกต้อง ไม่ต้องแก้

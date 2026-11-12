# แผน CITE_FALSE_BAD — ตัวตรวจ citation เลิกฟ้อง "ผิด" แบบ false positive

> แม่แบบแผนกลาง (flashq) — Claude วางแผน+ตรวจ · DeepSeek ลงมือ
> สร้าง 2026-11-12 · ส่งงาน: `python D:/MyCode/flashq/flashq.py run docs/plans/PLAN_FLASH_CITE_FALSE_BAD.md T-01..T-04` · base commit ตอนวางแผน: `6a39565`

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, tests/test_flashq.py, opencode/agent/flash-investigator.md, CHANGELOG.md
flashq-parallel: yes

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- <ไฟล์ของงาน>` + `git commit -m "<ข้อความในงาน>"`) · **ห้าม push** · ห้าม `git add -A` / `git add .` · commit message ภาษาไทย
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment/แปลง encoding · `flashq.py` ใช้ stdlib ล้วน ห้ามเพิ่ม dependency
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "ก่อน" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนไว้ตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · **หลักฐานชี้ขาด = path log + บรรทัดที่แผนกำหนด ตรงตัว**) — Claude ตรวจจากหลักฐานนี้ ไม่รันซ้ำ
6. **ห้ามแตะ**: `%USERPROFILE%\.flashq\` · ไฟล์อื่นนอก flashq-files · ห้ามรัน `flashq.py install`
7. **งานแบบ "เทสต์ก่อน"**: เขียนเทสต์ → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (เก็บ log "แดง") → แก้โค้ด → รันซ้ำต้อง PASS (เก็บ log "เขียว") → commit เดียว · ผ่านตั้งแต่ก่อนแก้ / ล้มด้วยเหตุอื่น (เช่น SyntaxError, ImportError) → **⛔ หยุด** · ห้ามแก้เทสต์ให้ผ่านแทนการแก้โค้ด
8. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน"
9. เทสต์ใหม่ทุกตัวใส่ในคลาสเดียวกับ `test_check_citations_groups` (วางต่อท้าย `test_check_citations_ambiguous_tries_all`) ใช้รูปแบบเดียวกัน: `sys.path.insert(0, str(REPO)); import flashq` · `tempfile.TemporaryDirectory()` · `git init -q -b main` + `git add -A` · เรียก `flashq.check_citations(text, root)`
10. ทุกคำสั่งรันจากราก repo · ตั้ง `PYTHONIOENCODING=utf-8` ก่อนรัน pytest

### คำสั่งมาตรฐาน
```
python -m pytest tests/test_flashq.py -q -k "citation"
```

---

## 1. กลุ่ม A — ตัวตรวจ citation (`check_citations` ใน flashq.py)
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว · ผู้สืบ job 20261112_072102_66248 นับจาก 239 งานสืบ: ผิด 651 ข้อ ในนั้น "ไม่พบไฟล์" 264 · "ไม่อยู่ในบรรทัดนี้" 348 โดย 261 เป็นคำเดี่ยว):
- `flashq.py:720` `elif "/" in rel:` → path ที่มี `/` แต่หาใต้ root ไม่เจอ = ผิดทันที แม้ไฟล์มีจริงนอกโปรเจกต์ (เช่น IRIS อ้าง `Gamebryo-2.6/sdk/...` ที่อยู่ข้างโฟลเดอร์โปรเจกต์ · อ้าง absolute `C:/Users/.../.flashq/jobs/x.json`)
- `flashq.py:613` `_cite_spans` นับทุก backtick ใกล้ citation เป็นโค้ดที่คัด รวม `110-124` (เลขบรรทัดของที่อื่น)
- `flashq.py:629-640` `_cite_judge` คำเดี่ยว (ชื่อฟังก์ชัน/สัญลักษณ์) ไม่อยู่ใน ±3 → ไปจับ occurrence ใกล้สุดเป็น "เลขเพี้ยน" หรือ "ผิด" ทั้งที่ผู้สืบแค่พูดถึงชื่อ

- [x] **T-01** `flashq.py` ~566 (`_cite_file`) + ~720 (`check_citations`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `tests/test_flashq.py` → `test_check_citations_outside_project` · โครง: `base = Path(d).resolve()` · `root = base / "proj"` มี `src/a.py` (3 บรรทัด `a = 1`/`b = 2`/`c = 3`) + git init ที่ `root` · ไฟล์นอกโปรเจกต์ `base / "ext" / "inc" / "x.h"` = `int a = 1;`/`int b = 2;`/`int c = 3;`
    1. `` f"`{(base / 'ext/inc/x.h').as_posix()}:2` — `int b = 2;`" `` (absolute มีจริง) → `bad == []` และ `ok_code == 1`
    2. `` "`ext/inc/x.h:2` — `int b = 2;`" `` (relative ต่อจากโฟลเดอร์แม่ของ root) → `bad == []` และ `ok_code == 1`
    3. `` "`Gamebryo-2.6/sdk/NiSystem.h:106` ดู" `` (โฟลเดอร์แรก `Gamebryo-2.6` ไม่มีใต้ root และไม่มีใต้โฟลเดอร์แม่) → `bad == []` · `len(unresolved) == 1` · `"นอกโปรเจกต์" in unresolved[0]`
    4. `` "`src/ghost.py:1` ดู" `` (โฟลเดอร์ `src` มีใต้ root แต่ไฟล์ไม่มี) → `len(bad) == 1` · `"ไม่พบไฟล์" in bad[0]` (พฤติกรรมเดิม ห้ามเปลี่ยน)
    5. `` f"`{(base / 'ext/inc/x.h').as_posix()}:2` — `int z = 9;`" `` → `len(bad) == 1` · `"ไม่อยู่ในบรรทัดนี้" in bad[0]` (ไฟล์นอกโปรเจกต์ยังตรวจโค้ดที่คัดจริง)
  - แดง (ก่อนแก้โค้ด): `python -m pytest tests/test_flashq.py -q -k "test_check_citations_outside_project" > .tmp/T-01.red.log 2>&1` → ต้อง FAIL ที่ข้อ 1 ด้วย AssertionError ที่มีข้อความ `ไม่พบไฟล์`
  - แก้ (1) `_cite_file` — ก่อน: `            return f, "", []` (บรรทัดแรกของฟังก์ชันที่อยู่ใน `try:` · เจอ 1 ที่) · หลัง: คงบรรทัดนั้นไว้ แล้ว**ต่อจากบล็อก `except OSError: pass`** (ก่อน `base = rel.rsplit("/", 1)[-1]`) เพิ่ม:
    ```
    p = Path(rel)
    if p.is_absolute() and p.is_file():  # ไฟล์นอกโปรเจกต์ที่อ้างด้วย path เต็ม (เช่น log ใน ~/.flashq)
        return p, "", []
    if "/" in rel and not p.is_absolute() and not (root / rel.split("/", 1)[0]).exists() and (root.parent / rel).is_file():
        return root.parent / rel, "", []  # โปรเจกต์ย่อยอ้างไฟล์ข้างโฟลเดอร์ (เช่น IRIS_CODE_1.2 → ../Gamebryo-2.6)
    ```
  - แก้ (2) `check_citations` — ก่อน: `elif "/" in rel:` (เจอ 1 ที่) · หลัง (แทน 2 บรรทัด `elif "/" in rel:` + `bad.append(f"{rel}:{line} — {why or 'ไม่พบไฟล์'}")`):
    ```
    elif "/" in rel and (Path(rel).is_absolute() or (root / rel.split("/", 1)[0]).exists()):
        bad.append(f"{rel}:{line} — {why or 'ไม่พบไฟล์'}")
    elif "/" in rel:
        unresolved.append(f"{rel}:{line} — ไฟล์อยู่นอกโปรเจกต์/หาไม่เจอ — ตรวจไม่ได้ (อ้าง path เต็มแบบ absolute)")
    ```
    (ระดับย่อหน้าให้ตรงกับโค้ดรอบข้าง)
  - เขียว: `python -m pytest tests/test_flashq.py -q -k "citation" > .tmp/T-01.green.log 2>&1` → PASS ทั้งหมด (รวมเทสต์ citation เดิม)
  - หลักฐานชี้ขาด: แดง `.tmp/T-01.red.log` บรรทัดที่มี `ไม่พบไฟล์` และ `1 failed` · เขียว `.tmp/T-01.green.log` บรรทัด `N passed` ไม่มี `failed`
  - commit: `flashq: ตรวจ citation ไฟล์นอกโปรเจกต์ได้ (absolute/โฟลเดอร์ข้างกัน) ไม่ฟ้องผิด + เทสต์ (T-01)`

- [x] **T-02** `flashq.py` ~613 (`_cite_spans`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_check_citations_number_spans` · root มี `src/a.py` 60 บรรทัด `x_{n} = {n}` (n=1..60) และบรรทัด 10 = `def target():` (แบบเดียวกับ `test_check_citations_groups`)
    1. `` "`src/a.py:10` ดูช่วง `110-124`" `` → `bad == []` · `drift == []` · `ok == 1` · `ok_code == 0`
    2. `` "`src/a.py:10` เทียบ `12, 40`" `` → `bad == []` · `ok == 1`
    3. `` "`src/a.py:10` — `def target():`" `` → `ok_code == 1` (พฤติกรรมเดิม)
  - แดง: `python -m pytest tests/test_flashq.py -q -k "test_check_citations_number_spans" > .tmp/T-02.red.log 2>&1` → FAIL ที่ข้อ 1 (`bad` มี 1 รายการ `ไม่อยู่ในบรรทัดนี้` … `110-124`)
  - แก้ — ก่อน: `if len(x) < 4 or x.endswith(("()", "/"))` (เจอ 1 ที่) · หลัง: `if len(x) < 4 or x.endswith(("()", "/")) or re.fullmatch(r"\d+(?:\s*[-–,]\s*\d+)*", x)` (ส่วนท้าย `or CITE_NEG_RE.search(...)` คงไว้ตามเดิม)
  - เขียว: `python -m pytest tests/test_flashq.py -q -k "citation" > .tmp/T-02.green.log 2>&1` → PASS ทั้งหมด
  - หลักฐานชี้ขาด: แดง `.tmp/T-02.red.log` บรรทัดที่มี `110-124` และ `1 failed` · เขียว `.tmp/T-02.green.log` บรรทัด `N passed` ไม่มี `failed`
  - commit: `flashq: ตัวตรวจ citation ไม่นับเลขบรรทัด/ช่วงเลขใน backtick เป็นโค้ดที่คัด + เทสต์ (T-02)`

- [ ] **T-03** `flashq.py` ~629 (`_cite_judge`) + ~558 (ค่าคงที่) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_check_citations_token_mentions` · root เหมือน T-02 (บรรทัด 10 = `def target():`)
    1. `` "`src/a.py:20` — `target`" `` (คำเดี่ยว มีในไฟล์แต่ไม่อยู่ใน ±3) → `drift == []` · `bad == []` · `ok == 1` · `ok_code == 0`
    2. `` "`src/a.py:20` — `ghost_symbol`" `` (คำเดี่ยว ไม่มีในไฟล์เลย) → `len(bad) == 1` · `"ไม่มีในไฟล์นี้เลย" in bad[0]`
    3. `` "`src/a.py:20` — `def target():`" `` (มีช่องว่าง = โค้ดที่คัด) → `len(drift) == 1` · `"บรรทัด 10" in drift[0]` (พฤติกรรมเดิม)
    4. `` "`src/a.py:10` — `target`" `` → `ok_code == 1`
  - แดง: `python -m pytest tests/test_flashq.py -q -k "test_check_citations_token_mentions" > .tmp/T-03.red.log 2>&1` → FAIL ที่ข้อ 1 (`drift` มี 1 รายการ `ข้อความที่คัดอยู่ที่บรรทัด 10`)
  - แก้ (1) ค่าคงที่ — ก่อน: `CITE_DRIFT = 40` (เจอ 1 ที่) · หลัง: คงบรรทัดนั้น แล้วเพิ่มบรรทัดถัดไป `CITE_TOKEN_RE = re.compile(r"[\w:~.]+")  # คำเดี่ยว/ชื่อสัญลักษณ์ (ไม่มีช่องว่าง/วงเล็บ) = พูดถึง ไม่ใช่คัดโค้ดทั้งบรรทัด`
  - แก้ (2) `_cite_judge` — ก่อน: `if verdicts and len(miss) == len(verdicts):` (เจอ 1 ที่) · หลัง: คงบรรทัดนั้น แล้วแทรกก่อน `found = None` (ย่อหน้าเดียวกับ `found = None`):
    ```
    if all(CITE_TOKEN_RE.fullmatch(x) for x in miss):  # ชื่อเดี่ยวโผล่หลายที่ → ไม่เดาเลขเพี้ยนจาก occurrence ใกล้สุด
        whole = " ".join(lines)
        absent = [x for x in miss if x not in whole]
        return ("bad_far", absent[0], None, False) if absent else ("ok", None, None, False)
    ```
  - เขียว: `python -m pytest tests/test_flashq.py -q -k "citation or investigate" > .tmp/T-03.green.log 2>&1` → PASS ทั้งหมด
  - หลักฐานชี้ขาด: แดง `.tmp/T-03.red.log` บรรทัดที่มี `บรรทัด 10` และ `1 failed` · เขียว `.tmp/T-03.green.log` บรรทัด `N passed` ไม่มี `failed`
  - commit: `flashq: ตัวตรวจ citation ไม่ฟ้องเลขเพี้ยน/ผิดเมื่อผู้สืบแค่อ้างชื่อเดี่ยว + เทสต์ (T-03)`

## 2. กลุ่ม B — prompt ผู้สืบ + CHANGELOG

- [ ] **T-04** `opencode/agent/flash-investigator.md` + `CHANGELOG.md` (แก้ข้อความ — สเปก)
  - (ข้อความที่ต้องใส่อยู่ระหว่าง «» — ไม่ต้องใส่ «» ลงไฟล์)
  - จุดเสียบ 1: บรรทัดที่มีคำว่า `คัดโค้ดใส่` (เจอ 1 ที่ · ข้อ 3 ย่อยเรื่อง path เต็ม) → ต่อท้ายบรรทัดเดิมด้วย « · backtick ติดหลัง citation = **โค้ดจากบรรทัดนั้นตรงตัวเท่านั้น** ห้ามใส่เลขบรรทัดอื่น/ช่วงเลข/ค่าจาก log ไว้ใน backtick ติดกัน — ค่า/ข้อสังเกตอื่นให้คั่นด้วย " · " ก่อน · ไฟล์นอกโปรเจกต์ (โฟลเดอร์ข้างกัน, log) อ้างด้วย path absolute เต็ม»
  - จุดเสียบ 2: บรรทัดที่ขึ้นต้นด้วย `หลักฐาน: <file:line>` (เจอ 1 ที่ ในบล็อกรูปแบบรายงาน) → ทั้งบรรทัดเป็น «หลักฐาน: <file:line> — <บรรทัดโค้ดตรงตัว> · <ค่า/ข้อสังเกตอื่น ถ้ามี> (ทุกข้อ)»
  - CHANGELOG.md: เพิ่มหัว «## 2026-11-12» เหนือ `## 2026-11-06` (คั่นบรรทัดว่างแบบเดิม) แล้วใส่บรรทัด «- **แก้: CITATIONS ฟ้อง "ผิด" เกินจริง**: ไฟล์นอกโปรเจกต์ (path absolute / โฟลเดอร์ข้างกัน) ตรวจได้จริง หาไม่เจอ = "ตรวจไม่ได้" ไม่ใช่ "ผิด" · เลขบรรทัด/ช่วงเลขใน backtick ไม่นับเป็นโค้ดที่คัด · อ้างแค่ชื่อเดี่ยวไม่ฟ้องเลขเพี้ยน (มีในไฟล์ = ตรงแค่ไฟล์/บรรทัด) · ผู้สืบแยกโค้ดที่คัดออกจากค่าอื่น (T-01..T-04)»
  - ยืนยัน: `python -m pytest tests/test_flashq.py -q -k "citation or investigate" > .tmp/T-04.log 2>&1` → PASS · และ `git diff HEAD~1 --stat > .tmp/T-04.stat.log` → แตะแค่ 2 ไฟล์นี้
  - หลักฐานชี้ขาด: `.tmp/T-04.log` บรรทัด `N passed` ไม่มี `failed` · `.tmp/T-04.stat.log` มีแค่ `opencode/agent/flash-investigator.md` และ `CHANGELOG.md`
  - commit: `flash-investigate: ผู้สืบแยกโค้ดที่คัดออกจากค่าอื่น + CHANGELOG ตัวตรวจ citation (T-04)`

## 3. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- -

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|
| T-01 | ✅แก้ | 7175d50 | แดง `.tmp/T-01.red.log` บรรทัด 29 `...x.h:2 — ไม่พบไฟล์` + บรรทัด 39 `1 failed, 221 deselected` · เขียว `.tmp/T-01.green.log` `7 passed, 215 deselected` ไม่มี `failed` |  |
| T-02 | ✅แก้ | cac612e | แดง `.tmp/T-02.red.log` บรรทัด 28 `['src/a.py:10 — ข้อความที่คัดไว้ไม่อยู่ในบรรทัดนี้ (±3): \`110-124\`']` + บรรทัด 37 `1 failed, 222 deselected` · เขียว `.tmp/T-02.green.log` บรรทัด 2 `8 passed, 215 deselected` ไม่มี `failed` |  |
| T-03 | ✅แก้ | d206dd9 | แดง `.tmp/T-03.red.log` บรรทัด 32 `['src/a.py:20 — ข้อความที่คัดอยู่ที่บรรทัด 10 (ห่าง 10 บรรทัด · เลขเพี้ยน): ...` + บรรทัด 41 `1 failed, 223 deselected` · เขียว `.tmp/T-03.green.log` บรรทัด 2 `16 passed, 208 deselected` ไม่มี `failed` |  |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- หลังรวมแผน Claude รัน `python flashq.py install` จาก checkout หลัก (ไฟล์ใน `opencode/` เปลี่ยน) + รีสตาร์ต `flashq ui`
- ชื่อไฟล์กำกวม (`check_citations` สาขา `ชื่อไฟล์กำกวม`) ยังนับเฉพาะ `ok` ที่มีโค้ดคัด — คำเดี่ยวหลัง T-03 อาจตกไป "ไม่อยู่ในทุกไฟล์ที่ชื่อตรง" · ดูผลจริงก่อนค่อยแก้
- โค้ดใน code fence หลายบรรทัดยังไม่ถูกตรวจ (`region` จบที่สิ้นบรรทัด) · citation ของไฟล์ที่งานอื่นแก้ระหว่างสืบ (`modified_others`) — ยังไม่มีหลักฐานว่าทำให้ผิดจริง

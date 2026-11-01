# แผน ทำให้คิวเสถียร 2 (ผลซื่อตรง + ใช้ง่าย) — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-01 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_STABILIZE_2.md T-01..T-12 --switch-on-quota 4` · base commit ตอนวางแผน: `824c94a`
> **ต้องรอ `PLAN_FLASH_STABILIZE_1.md` merge เข้า master ก่อนส่ง** — T-01 แก้ `job_progressed` ตัวเดียวกับ T-08 ของแผน 1 (ส่งพร้อมกัน = ชนกัน) · ก่อนส่ง Claude ต้อง Grep "ก่อน:" ทุกงานซ้ำบน master ใหม่ (เลขบรรทัดเลื่อนแน่)

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, tests/test_flashq.py, ui.html, hooks/inbox_notify.py, claude/commands/flash-check.md, claude/commands/flash-investigate.md, claude/commands/flash-qa.md, claude/commands/flash-goal.md, README.md, docs/REFERENCE.md, CHANGELOG.md
flashq-parallel: yes

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- ` ตามด้วยไฟล์ในช่อง "ไฟล์" ของงาน + `git commit` ด้วยข้อความในช่อง commit) · **ห้าม push** · ห้าม `git add -A` / `git add .` · ห้าม `git stash`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment อื่น/แปลง encoding
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "ก่อน" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · หลักฐานชี้ขาด = path log + บรรทัด/ค่าตรงตัว) · หลักฐานไม่ครบ = งานไม่จบ
6. **ห้ามแตะ**: `%USERPROFILE%\.flashq\` ของจริง (เทสต์ใช้ `FLASHQ_HOME` ชั่วคราวผ่าน `load_mod`/`run_q` เดิม) · ห้ามเรียกโมเดลจริง (ใช้ `fake_opencode.py`) · ห้ามรัน `flashq run` / `flashq ui` พอร์ต 4097 / `flashq.py install` (Claude รันเองหลัง merge)
7. **งานแบบ "เทสต์ก่อน"**: เขียนเทสต์ → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (log แดง) → แก้โค้ด → รันซ้ำ PASS (log เขียว) → commit เดียว · ผ่านตั้งแต่ก่อนแก้ / ล้มด้วยเหตุอื่น → **⛔ หยุด** · ห้ามแก้เทสต์ให้ผ่านแทนการแก้โค้ด (ยกเว้นงานที่สั่งแก้เทสต์เดิมตรงตัว)
8. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน"
9. stdlib ล้วน · ข้อความผู้ใช้เห็นเป็นไทย · commit ภาษาไทยขึ้นต้น `flashq:` หรือ `ui:` มี `(T-xx)` + trailer `Flash-Task: T-xx`
10. log ไว้ `.tmp/` · ห้ามรันเทสต์ทั้งชุด — รันเฉพาะ `-k` ที่แผนกำหนด

### คำสั่งมาตรฐาน (PowerShell · timeout ≥ 300 วิ)
```
python -c "import ast; ast.parse(open('flashq.py',encoding='utf-8').read())"
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k "คำค้น" > .tmp/T-xx.red.log 2>&1
```
("คำค้น" = ค่า `-k` ของงาน · ชื่อ log เปลี่ยนตามที่งานระบุ)

---

## 1. กลุ่ม B — ผลต้องซื่อตรง (OK ต้องแปลว่าทำจริง)
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว): `job_progressed` (flashq.py ~1856) นับ `\bDONE\b` ทุกที่ — "NOT DONE"/"ยังไม่ DONE" ก็นับ · งาน no_progress/อ่านอย่างเดียวแก้ไฟล์/ผู้สืบอ้างเลขบรรทัดผิด ยังได้ `FLASH_RUN=OK` และ `result="OK"` (~2451, ~2457) มีแค่ WARN · `qa_verdict` (~2935) ไม่ตั้ง `expect` + "collected 0 items" = PASS · `doc_verdict` (~3402) ลบเนื้อหาเอกสารทิ้งครึ่งไฟล์ก็ได้ DRAFT · `cmd_scope` (~3669) แผนไม่มีงาน T-xx เลย → วนว่าง → `SCOPE_RESULT=PASS`

- [x] **T-01** `flashq.py` ~1856 (`job_progressed`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_said_done_ignores_negation` ใช้ `load_mod`: `mod.job_progressed(self.proj, "", ["NOT DONE"])` False · `["ยังไม่ DONE"]` False · `["งานนี้ไม่ได้ DONE"]` False · `["T-01 DONE แล้ว"]` True · `["สถานะ: DONE"]` True · `["**DONE**"]` True
  - แดง: `-k "said_done"` → `.tmp/T-01.red.log` FAIL ด้วย `True is not false`
  - แก้ (สเปก): ฟังก์ชันใหม่ `said_done(text: str) -> bool` เหนือ `job_progressed` — แต่ละ match ของ `\bDONE\b` ดูข้อความก่อนหน้าในบรรทัดเดียวกัน ตัดช่องว่างและ `*_"'` ท้ายออก ถ้าลงท้ายด้วย `NOT` (ไม่สนตัวพิมพ์) / `ยังไม่` / `ไม่ได้` / `ไม่` → ไม่นับ · มี match ที่นับได้อย่างน้อย 1 = True · ก่อน: `    return any(re.search(r"\bDONE\b", t) for t in outputs)` · หลัง: `    return any(said_done(t) for t in outputs)` · ห้ามบังคับรูปแบบ `สถานะ:` (เทสต์เดิม FAKE_TEXT "T-01 DONE แล้ว · T-02 ถูกปฏิเสธสิทธิ์" ต้องยังนับ)
  - เขียว: คำสั่งเดิม → `.tmp/T-01.green.log` PASS · แล้ว `-k "denied or without_commit or own_commits"` → `.tmp/T-01.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-01.red.log` มี `True is not false` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: คำว่า NOT DONE / ยังไม่ DONE ไม่นับเป็นงานเสร็จ + เทสต์ (T-01)`

- [x] **T-02** `flashq.py` ~2451/~2457/~4115 (`cmd_run` finally · `cmd_wait`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์ (แก้เทสต์เดิมตรงตัว 2 จุด):
    - `test_ok_without_commit_or_done_warns`: เพิ่ม `self.assertIn("FLASH_RUN=OK_UNVERIFIED", r.stdout)` และอ่าน job json ล่าสุดใน `self.home / "jobs"` ต้องได้ `status == "ok"`, `result == "OK_UNVERIFIED"`, `unverified` เป็น list ไม่ว่าง · `r.returncode == 0` (คงเดิม)
    - `test_wait_blocks_until_done_and_reports`: บรรทัด `self.assertIn("FLASH_RUN=OK job=", r.stdout)` → `self.assertIn("FLASH_RUN=OK_UNVERIFIED job=", r.stdout)` และต้องคง `returncode == 0` ของ wait
  - แดง: `-k "without_commit_or_done or wait_blocks"` → `.tmp/T-02.red.log` FAIL ด้วย `'FLASH_RUN=OK_UNVERIFIED' not found`
  - แก้ (สเปก):
    - ฟังก์ชันใหม่ `unverified_reasons(job: dict, res: dict) -> list[str]` (ข้อความไทย): `res.get("no_progress")` → "ไม่มี commit ของงานและไม่มีคำว่า DONE" · `job.get("readonly") and job.get("modified")` → "งานอ่านอย่างเดียวแต่ไฟล์ในโปรเจกต์เปลี่ยน" · `job.get("kind") == "investigate"` และ `job.get("citations")` มี `bad` ไม่ว่าง → "ผู้สืบอ้างเลขไฟล์:บรรทัดผิด N จุด" · investigate ที่ `citations` ไม่มี หรือ `ok` และ `bad` เป็น 0 ทั้งคู่ → "ผู้สืบไม่อ้างเลขไฟล์:บรรทัดเลย"
    - ใน `finally:` ก่อน `job.update(status=res["status"].lower(), result=res.get("status"), ...`: คำนวณ `verdict = res.get("status")` · ถ้าเป็น `"OK"` และ `unverified_reasons` ไม่ว่าง → `job["unverified"] = เหตุ` และ `verdict = "OK_UNVERIFIED"` · `job.update(... result=verdict ...)` · `notify_job(job, verdict, ...)` · **`status` ยัง `"ok"`** (หน้าเว็บ/คิวใช้ค่าเดิม)
    - บรรทัด `print(f"FLASH_RUN={res['status']} ...` → ใช้ `verdict` · มี `job.get("unverified")` → พิมพ์ `WARN: ผล OK ยังไม่ยืนยัน — ` + เหตุคั่น ` · ` · `return 0 if res["status"] == "OK" else 1` คงเดิม (exit 0)
    - `cmd_wait`: ก่อน: `        if res != "OK":` · หลัง: `        if res not in ("OK", "OK_UNVERIFIED"):`
  - เขียว: คำสั่งเดิม → `.tmp/T-02.green.log` PASS · แล้ว `-k "ok_passes or fifo_queue or investigate or citation"` → `.tmp/T-02.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-02.red.log` มี `OK_UNVERIFIED' not found` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: ผล OK ที่ไม่มีหลักฐานงานแสดงเป็น OK_UNVERIFIED พร้อมเหตุ + เทสต์ (T-02)`

- [ ] **T-03** `flashq.py` ~7449 (`claude_check_prompt`) + `hooks/inbox_notify.py` ~59 (`advice`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_unverified_routes_like_ok_with_warning`: `mod.claude_check_prompt({"id": "jobu1", "status": "done", "result": "ok_unverified", "plan": "docs/PLAN.md"})` ต้องขึ้นต้นด้วย `/flash-check docs/PLAN.md` (ทางเดียวกับ result ok · ดูรูปแบบ dict จากเทสต์ที่ใช้ `jobok001`) · โหลด `hooks/inbox_notify.py` ด้วย `importlib.util.spec_from_file_location` แล้ว `advice({"status": "OK_UNVERIFIED", "plan": "P.md"})` ต้องมีคำ `ยังไม่ยืนยัน`
  - แดง: `-k "unverified_routes"` → `.tmp/T-03.red.log` FAIL (AssertionError ข้อแรก)
  - แก้: (1) flashq.py ต่อจากบรรทัด `    st = "dead" if live_state(j) == "dead" else str(j.get("result") or j.get("status") or "").lower()` เพิ่ม `    if st == "ok_unverified":` / `        st = "ok"` · (2) inbox_notify.py ก่อน (2 บรรทัด เยื้อง 4/8): `    if st == "OK":` / `        if row.get("kind") == "investigate":` → แทรกเหนือบรรทัดแรก:
    ```
        if st == "OK_UNVERIFIED":
            return ("ผล OK ยังไม่ยืนยัน (ดูบรรทัด WARN ใน log) — ห้ามเชื่อ OK · "
                    + (f"ตรวจด้วย /flash-check {plan} โดยดู git log ของงานเอง" if plan else f"อ่าน {FQ} log {row.get('job', '')} ก่อนรายงาน"))
    ```
  - เขียว: คำสั่งเดิม → `.tmp/T-03.green.log` PASS · แล้ว `-k "claude_check or inbox"` → `.tmp/T-03.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-03.red.log` มี `AssertionError` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: ปุ่มตรวจงานและแจ้งเตือนรองรับผล OK_UNVERIFIED (T-03)`

- [ ] **T-04** `flashq.py` ~5778 (`log_tail`) + `ui.html` ~2408 · แก้ตรง
  - ก่อน (flashq.py): `           "denied_help": "\n".join(perm_fix_lines(j["perm_denied"], partial=j.get("result") != "DENIED")) if j.get("perm_denied") else ""}` · หลัง: แทน `}` ท้ายบรรทัดด้วย `,` (ต้องเป็น `else "",`) แล้วเพิ่มบรรทัดใหม่ `           "unverified": j.get("unverified") or []}` (เยื้องเท่าบรรทัดเดิม)
  - ก่อน (ui.html): `      if (d.denied_help) add.push("", d.denied_help);` · หลัง: คงบรรทัดเดิม แล้วเพิ่มบรรทัดถัดไป `      if (d.unverified && d.unverified.length) add.push("", "⚠ ผล OK ยังไม่ยืนยัน: " + d.unverified.join(" · "));`
  - ยืนยัน: ast.parse ผ่าน · ดึงเนื้อแท็ก script ของ ui.html ไป `.tmp/ui_check.js` (`python -c "import re;s=open('ui.html',encoding='utf-8').read();open('.tmp/ui_check.js','w',encoding='utf-8').write('\n'.join(re.findall(r'<script>(.*?)</script>',s,re.S)))"`) แล้ว `node --check .tmp/ui_check.js > .tmp/T-04.node.log 2>&1` · แล้ว `-k "log_tail or denied"` → `.tmp/T-04.log` PASS
  - หลักฐานชี้ขาด: `.tmp/T-04.node.log` ว่าง (exit 0) · `.tmp/T-04.log` บรรทัดท้าย `passed`
  - commit: `ui: กล่อง log แสดงเหตุที่ผล OK ยังไม่ยืนยัน (T-04)`

- [ ] **T-05** `flashq.py` ~35 (docstring) + `claude/commands/flash-check.md` ~16 + `claude/commands/flash-investigate.md` ~30 · เอกสาร
  - ก่อน (flashq.py): ``ผลของ run: บรรทัด `FLASH_RUN=OK|FAIL|DENIED|QUOTA|`` (ต้นบรรทัด ~35) · หลัง: แทรก `OK_UNVERIFIED|` หลัง `FLASH_RUN=OK|` และเปลี่ยนท้าย `· exit 0 = OK ·` เป็น `· exit 0 = OK/OK_UNVERIFIED ·` (แก้เฉพาะบรรทัดนี้)
  - ก่อน (flash-check.md): ``- `FLASH_RUN=OK` → ข้อ 1`` · หลัง: ``- `FLASH_RUN=OK` → ข้อ 1 · `FLASH_RUN=OK_UNVERIFIED` → ข้อ 1 เช่นกัน แต่ถือว่ายังไม่มีหลักฐาน (อ่านบรรทัด `WARN:` ก่อน ห้ามติ๊กผ่านจากคำของ worker)``
  - ก่อน (flash-investigate.md): ``- `FLASH_RUN=OK` → อ่านรายงานจากท้ายผลลัพธ์`` (ต้นบรรทัด) · หลัง: เติมท้ายบรรทัดเดิม `` · `FLASH_RUN=OK_UNVERIFIED` = ผู้สืบอ้างผิด/ไม่อ้างเลขบรรทัด → ห้ามเชื่อจนกว่าจะเปิดโค้ดยืนยัน``
  - ยืนยัน: ast.parse ผ่าน · `git diff --stat HEAD` แสดง 3 ไฟล์นี้เท่านั้น → `.tmp/T-05.log`
  - หลักฐานชี้ขาด: `.tmp/T-05.log` มี 3 ไฟล์ · ไม่มีไฟล์อื่น
  - commit: `flashq: เอกสารคำสั่งอธิบายผล OK_UNVERIFIED (T-05)`

- [ ] **T-06** `flashq.py` ~2935 (`qa_verdict`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: ใน `QaTest` เพิ่ม `test_qa_no_tests_ran_is_noexpect` ใช้ `load_mod` แบบเทสต์อื่นในคลาส: `r = {"status": "DONE", "rc": 0}` · `spec = {"expect": ""}` · log `"collected 0 items"` / `"Ran 0 tests in 0.000s"` / `"no tests ran in 0.01s"` → `"NOEXPECT"` · log `"3 passed in 1.2s"` / `"Ran 10 tests"` → `"PASS"`
  - แดง: `-k "no_tests_ran"` → `.tmp/T-06.red.log` FAIL ด้วย `'PASS' != 'NOEXPECT'`
  - แก้: ค่าคงที่ใหม่เหนือ `qa_verdict`: `QA_NO_TESTS_RE = re.compile(r"collected 0 items|no tests ran|(?<![\d.,])\b0 tests\b", re.I)` · ก่อน (2 บรรทัด): `        return "NOEXPECT"` / `    return "PASS"` · หลัง:
    ```
            return "NOEXPECT"
        if not spec["expect"] and QA_NO_TESTS_RE.search(text):
            return "NOEXPECT"  # ไม่ตั้ง expect แต่ log บอกเองว่าไม่มีเทสต์ให้รัน
        return "PASS"
    ```
  - เขียว: คำสั่งเดิม → `.tmp/T-06.green.log` PASS · แล้ว `-k "Qa"` → `.tmp/T-06.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-06.red.log` มี `'PASS' != 'NOEXPECT'` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: นักทดสอบไม่นับผ่านเมื่อ log บอกว่าไม่มีเทสต์ให้รัน + เทสต์ (T-06)`

- [ ] **T-07** `flashq.py` ~3293/~3402/~3244 (`doc_added` · `doc_verdict` · `doc_spec`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: ใน `DocTest` เพิ่ม `test_doc_mass_removal_flagged` (ใช้ helper verdict/`w()`/SPEC เดิม): commit `docs/C.md` 50 บรรทัด แล้วให้ fake เขียนทับเหลือ **3 บรรทัดแรกเดิมตรงตัว** (diff จึงมีบรรทัด `-` 47 บรรทัดพอดี) → verdict `"REMOVED"` และเหตุมีเลข `47` · กรณีคุม SPEC + `"max_removed": 0` → `"DRAFT"` และเหตุมีคำ `ลบ 47 บรรทัด` และยังลงท้าย `รอผู้ใช้ดู diff`
  - แดง: `-k "mass_removal"` → `.tmp/T-07.red.log` FAIL ด้วย `'DRAFT' != 'REMOVED'`
  - แก้ (สเปก):
    - `doc_added` คืน 3 ค่า `(lines, gone, removed)` ทุกทางออก (`removed` = จำนวนบรรทัด diff ที่ขึ้นต้น `-` แต่ไม่ใช่ `---` · ทางที่คืน None/gone ให้ removed = 0) · ก่อน: `    return [x[1:] for x in diff if x.startswith("+") and not x.startswith("+++")], False` · ผู้เรียกที่เดียว `        lines, gone = doc_added(root, p, head1, before_texts)` → รับ 3 ค่า แล้วรวม `removed` ทุกไฟล์
    - ค่าคงที่ `DOC_MAX_REMOVED = 40` · หลังด่าน `BADREF` ก่อน `return "DRAFT"`: `lim = spec.get("max_removed", DOC_MAX_REMOVED)` · `lim` > 0 และ removed > lim → `return "REMOVED", [f"ลบ/แก้ทับเนื้อหาเดิม {removed} บรรทัด (เกิน {lim}) — ตรวจ diff ว่าไม่ได้ลบของจริงทิ้ง"], changed` (ไม่ใส่ใน `DOC_AUTO_REVERT`)
    - DRAFT: ก่อน: `    return "DRAFT", [f"แก้ {len(changed)} ไฟล์ ผ่านด่านกลไกทั้งหมด — รอผู้ใช้ดู diff"], changed` · หลัง: ข้อความเป็น `f"แก้ {len(changed)} ไฟล์ (ลบ {removed} บรรทัด) ผ่านด่านกลไกทั้งหมด — รอผู้ใช้ดู diff"`
    - `doc_spec`: อ่าน `v.get("max_removed")` เป็น int 0-100000 (ผิด → คืนข้อความ error ไทยแบบ `timeout_min`) · ใส่คีย์ `"max_removed"` ใน dict ที่คืน **เฉพาะเมื่อตั้งไว้** (เทสต์เดิมเทียบ dict เต็ม)
    - `DOC_ICON`/`DOC_MEANING` เพิ่มคีย์ `"REMOVED"` (ไอคอน `✂` · ความหมาย "ลบเนื้อหาเดิมมากเกินเกณฑ์ — ไม่ผ่าน ต้องดู diff")
  - เขียว: คำสั่งเดิม → `.tmp/T-07.green.log` PASS · แล้ว `-k "Doc"` → `.tmp/T-07.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-07.red.log` มี `'DRAFT' != 'REMOVED'` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: ช่างเอกสารที่ลบเนื้อหาเดิมเกิน 40 บรรทัดได้ผล REMOVED ไม่ผ่าน + เทสต์ (T-07)`

- [ ] **T-08** `flashq.py` ~3669 (`cmd_scope`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_scope_plan_without_tasks_fails`: `git init` ใน `self.proj` + commit แรก (`git -c user.name=t -c user.email=t@t`) · เขียน `PLAN.md` = `"# plan\n"` · เรียก CLI แบบเทสต์ scope เดิม (~347: `subprocess.run([sys.executable, str(REPO / "flashq.py"), "scope", ...])` ใน tempdir + `env=self.env`) ด้วยอาร์กิวเมนต์ `"scope", "PLAN.md", "--project", d` · ทำใน tempdir แบบเทสต์นั้นแทน `self.proj` ได้ → `returncode == 1` · stdout มี `SCOPE_RESULT=FAIL` และ `NOTASK`
  - แดง: `-k "scope_plan_without_tasks"` → `.tmp/T-08.red.log` FAIL ด้วย `0 != 1` หรือ `SCOPE_RESULT=FAIL' not found`
  - แก้: ต่อจากบรรทัด `    bad = 0` ที่อยู่ใต้ `    wanted = [t for t in re.split(r"[,\s]+", " ".join(a.tasks)) if t] or sorted(set(allow) | set(hashes))` เพิ่ม `    if not wanted:` / `        print("SCOPE NOTASK ไม่พบงาน T-xx ในแผน — ตรวจขอบเขตไม่ได้")` / `        bad += 1`
  - เขียว: คำสั่งเดิม → `.tmp/T-08.green.log` PASS · แล้ว `-k "scope"` → `.tmp/T-08.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-08.red.log` มีข้อความ FAIL ข้างต้น · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: scope ของแผนที่ไม่มีงาน T-xx ได้ FAIL แทน PASS + เทสต์ (T-08)`

## 2. กลุ่ม D — ใช้ง่าย
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว): งานที่ส่งจากหน้าเว็บ (`build_run_argv` ~5555 · ใช้ทั้งส่งใหม่และส่งซ้ำ) ไม่มี `--submitter` → `want_open_session` (~1469) เปิดหน้าต่าง session ทุกงาน · `_run_once` ~1701 เปิดหน้าต่างทุกรอบที่ retry (QUOTA/NOSTART) · README ~77 ให้รัน `run` ตรง ๆ แต่ใน Claude Code ยาม `run_guard.py` บล็อก foreground · flash-goal.md ~25 "ถาม user ครั้งเดียว" ขัดกับ ~16 ที่ให้ถามได้หลายรอบ

- [ ] **T-09** `flashq.py` ~5650 (`build_run_argv`) + ~1469 (`want_open_session`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: ใน `test_config_open_session_auto_and_priority` เพิ่ม: job `{"submitter": "ui"}` ค่าเครื่อง auto → `want_open_session` False · ตั้ง config `open_session` on → True · และ `argv, _ = mod.build_run_argv(body)` (body ขั้นต่ำแบบเดียวกับ `test_skip_precheck`) → มีคู่ `"--submitter", "ui"` ติดกัน
  - แดง: `-k "open_session_auto_and_priority"` → `.tmp/T-09.red.log` FAIL ด้วย `True is not false`
  - แก้: ก่อน (2 บรรทัด): `        if body.get("no_open"):` / `            argv.append("--no-open")` → คงไว้ แล้วต่อด้วย `        argv += ["--submitter", "ui"]` (เยื้องเท่า `if`) · ก่อน: `    return job.get("submitter") != "detach"` · หลัง: `    return job.get("submitter") not in ("detach", "ui")` · **ห้ามใช้ `--detach`** (spawn_run แยก process อยู่แล้ว)
  - เขียว: คำสั่งเดิม → `.tmp/T-09.green.log` PASS · แล้ว `-k "open_session or skip_precheck or submit or retry"` → `.tmp/T-09.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-09.red.log` มี `True is not false` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: งานที่ส่งจากหน้าเว็บไม่เปิดหน้าต่าง session เป็นค่าเริ่มต้น + เทสต์ (T-09)`

- [ ] **T-10** `flashq.py` ~1701 (`_run_once`) · แก้ตรง (เปิดหน้าต่างจริงใช้ node + พอร์ต 9333 — ห้ามทดสอบ)
  - ก่อน (2 บรรทัด): `                if want_open_session(root, job, no_open):` / `                    open_in_desktop(sid, attach)`
  - หลัง:
    ```
                    if want_open_session(root, job, no_open) and not job.get("opened"):
                        open_in_desktop(sid, attach)
                        job["opened"] = now()
                        save_job(job)
    ```
  - ยืนยัน: ast.parse ผ่าน · `-k "stalled or nostart or open_session"` → `.tmp/T-10.log` PASS
  - หลักฐานชี้ขาด: `.tmp/T-10.log` บรรทัดท้าย `passed` · `git show --stat HEAD` แตะ `flashq.py` ไฟล์เดียว
  - commit: `flashq: เปิดหน้าต่าง session ครั้งเดียวต่องาน ไม่เปิดซ้ำทุกรอบลองใหม่ (T-10)`

- [ ] **T-11** `README.md` ~77 + `claude/commands/flash-goal.md` ~25 · เอกสาร
  - ก่อน (README): `python flashq.py run docs/plans/PLAN_X.md T-01..T-03` (ในบล็อกใต้ "### ลองส่งงาน") · หลัง: คงบล็อกเดิม แล้วเพิ่มย่อหน้าใต้บล็อกตามข้อความในบล็อกนี้ตรงตัว:
    ```
    รันจาก terminal ปกติได้ตรง ๆ · ใน Claude Code ต้องรันแบบ background (ยาม `hooks/run_guard.py` บล็อกคำสั่ง run แบบ foreground ที่ส่งผ่าน Claude Code เท่านั้น) — ใช้ `/flash-plan` จะจัดให้เอง
    ```
  - ก่อน (flash-goal.md): `- **ถาม user ครั้งเดียว** (AskUserQuestion): สรุปเกณฑ์ + ขอบเขต + งบ + คำเตือนที่เหลือ` · หลัง: `- **ถามยืนยันก่อนเริ่มวน (ข้อสุดท้ายของขั้นนี้ · หลังเคลียร์ข้อสงสัยตามข้อ "ถามให้ชัด" ครบแล้ว)** (AskUserQuestion): สรุปเกณฑ์ + ขอบเขต + งบ + คำเตือนที่เหลือ` (ส่วนท้ายบรรทัดคงเดิม)
  - ยืนยัน: `git diff --stat HEAD` แสดง 2 ไฟล์นี้เท่านั้น → `.tmp/T-11.log`
  - หลักฐานชี้ขาด: `.tmp/T-11.log` มี 2 ไฟล์
  - commit: `flashq: README บอกวิธีรัน run ใน Claude Code · flash-goal ไม่ขัดกันเรื่องจำนวนครั้งที่ถาม (T-11)`

- [ ] **T-12** `CHANGELOG.md` + `docs/REFERENCE.md` + `claude/commands/flash-qa.md` · เอกสารท้ายแผน
  - CHANGELOG: ใต้หัวข้อ `## 2026-11-01` (บนสุด) เพิ่ม bullet ละบรรทัด: `FLASH_RUN=OK_UNVERIFIED` + เหตุ (T-02..T-04) · NOT DONE ไม่นับ (T-01) · qa ไม่มีเทสต์ให้รัน = NOEXPECT (T-06) · ช่างเอกสาร `REMOVED` + `max_removed` (T-07) · scope แผนไม่มีงาน = FAIL (T-08) · หน้าเว็บไม่เปิดหน้าต่าง session เป็นค่าเริ่มต้น + เปิดครั้งเดียวต่องาน (T-09, T-10) · และกลุ่มแผน 1 (ล็อกค้าง · fifo กันชน · แผนไม่ระบุไฟล์ = ชน) ถ้ายังไม่มีบรรทัดเหล่านี้
  - REFERENCE: บรรทัดที่มี ``(exit 0 = OK · 1 = ไม่ OK · 3 = ยังไม่จบ)`` เติม `· OK_UNVERIFIED นับเป็น exit 0 แต่มีบรรทัด WARN บอกเหตุ` · บรรทัดที่มี ``· `NOEXPECT` (exit 0 แต่ไม่พบข้อความที่ต้องมี)`` เติมในวงเล็บ `หรือไม่ตั้ง expect แต่ log บอกว่าไม่มีเทสต์ให้รัน` · บรรทัดที่ขึ้นต้น ``- **flashq ตัดสินเองจากไฟล์จริง**`` (ช่างเอกสาร) เติมรายการ `REMOVED` = ลบ/แก้ทับเกิน `max_removed` (ค่าเริ่ม 40 · 0 = ปิด) · บรรทัดที่มี ``- `open_session` (true/false`` เติม `· งานที่ส่งจากหน้าเว็บ (submitter ui) ไม่เปิดเหมือน --detach` · หัวข้อ `### ตรวจขอบเขตไฟล์ (scope)` เพิ่ม bullet `แผนไม่มีงาน T-xx = SCOPE NOTASK → FAIL`
  - flash-qa.md: ต่อท้ายบรรทัด ``- fail-closed: exit 0 แต่ไม่พบข้อความที่ต้องมี`` ด้วย `· ไม่ตั้ง expect แต่ log บอกว่าไม่มีเทสต์ (collected 0 items / no tests ran / 0 tests) = NOEXPECT เช่นกัน`
  - ยืนยัน: `git diff --stat HEAD` แสดง 3 ไฟล์นี้เท่านั้น → `.tmp/T-12.log`
  - หลักฐานชี้ขาด: `.tmp/T-12.log` มี 3 ไฟล์
  - commit: `flashq: อัปเดต CHANGELOG/REFERENCE/flash-qa ตามแผนทำให้คิวเสถียร 2 (T-12)`

## 3. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- exit code ของ `OK_UNVERIFIED` — แผนเลือก 0 (เท่า OK) เพื่อไม่ทำลายสคริปต์เดิม · ถ้าผู้ใช้อยากให้เป็น 1 ต้องแก้ `cmd_run`/`cmd_wait` เพิ่ม
- ค่าเริ่ม `DOC_MAX_REMOVED = 40` บรรทัด (T-07)
- หลัง merge: Claude รัน `python flashq.py install` จาก checkout หลัก (T-03 แก้ `hooks/`, T-05/T-11/T-12 แก้ `claude/commands/`) และรีสตาร์ต `flashq ui` (T-04)

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|
| T-01 | ✅แก้ | 154a5e6 | `.tmp/T-01.red.log` → `AssertionError: True is not false : NOT DONE` · `.tmp/T-01.green.log` → `1 passed` · `.tmp/T-01.reg.log` → `4 passed` | |
| T-02 | ✅แก้ (⚠️ ภายหลังพบว่าทำให้ `test_notify_inbox_and_hook` แดง — ไม่อยู่ในชุด reg ที่แผนกำหนด → ต้องออก T-02R) | 03c6e54 | `.tmp/T-02.red.log` → `AssertionError: 'FLASH_RUN=OK_UNVERIFIED' not found` · `.tmp/T-02.green.log` → `2 passed` · `.tmp/T-02.reg.log` → `9 passed` | |
| T-03 | ⛔หยุด (โค้ดแก้แล้ว + green ผ่าน แต่ reg แดงด้วยเทสต์เดิมที่ค้างจาก T-02 → ยังไม่ commit · โค้ดถูก revert เก็บเป็น `.tmp/T-03.patch` — รอ T-02R แล้วรัน T-03 ใหม่) | - | `.tmp/T-03.red.log` → `AssertionError: False is not true : งาน flashq job jobu1` · `.tmp/T-03.green.log` → `1 passed` · `.tmp/T-03.reg.log` → `FAILED ...test_notify_inbox_and_hook` `('OK_UNVERIFIED', 's1', 'PLAN.md') != ('OK', 's1', 'PLAN.md')` (rerun `.tmp/T-03.reg2.log` แดงเหมือนกัน) · รันที่ HEAD `03c6e54` แบบไม่มีไฟล์ที่แก้ (`.tmp/T-03.head.log`) ก็แดงแบบเดียวกัน = เทสต์ค้างจาก T-02 ไม่ใช่ผลของ T-03 | |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- นักทดสอบระดับ 3/4 · worktree แยกต่องาน (รอผู้ใช้ตัดสิน)
- usage ของ `init --commit` ในบรรทัดช่วยเหลือต้นไฟล์ flashq.py ไม่บอกว่า push (REFERENCE บอกแล้ว — เรื่องเล็ก ไม่ทำในรอบนี้)
- `OK_UNVERIFIED` บนป้ายสถานะหน้าเว็บ (`STATUS` ใน ui.html ใช้ `status` ไม่ใช่ `result`) — รอดูการใช้งานก่อน

# แผน ทำให้คิวเสถียร 5 (ผล OK_UNVERIFIED แยกให้เห็น · ลดเตือนผิด · DONE เข้มขึ้น) — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-04 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_STABILIZE_5.md T-01..T-11 --switch-on-quota 4` · base commit ตอนวางแผน: `429029c`
> ต่อจากแผนเสถียร 3–4 (EPIPE → OK_UNVERIFIED) · หลักฐานจากผู้สืบ: ผล OK_UNVERIFIED 40/49 งานมาจาก "งานอ่านอย่างเดียวแต่ไฟล์เปลี่ยน" ขณะมีงานอื่นรันในโปรเจกต์เดียวกัน · `said_done("ห้ามรายงาน DONE")` และ `said_done("จะรายงาน DONE เมื่อเทสต์ผ่าน")` คืน True ผิด

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, ui.html, tests/test_flashq.py, tests/fake_opencode.py, docs/REFERENCE.md, claude/commands/flash-plan.md, claude/commands/flash-goal.md, CHANGELOG.md
flashq-parallel: no — แก้ flashq.py/tests ไฟล์เดียวกันหลายงาน
flashq-exclusive: flashq.py, ui.html, tests/test_flashq.py, tests/fake_opencode.py

1. **ทำทีละงานตามลำดับ T-01 → T-11 · 1 งาน = 1 commit** (`git add -- ` ตามด้วยไฟล์ในช่อง "ไฟล์" ของงานนั้นเท่านั้น + `git commit` ข้อความไทยตามช่อง commit มี `(T-xx)` + บรรทัด trailer `Flash-Task: T-xx`) · **ห้าม push** · ห้าม `git add -A` / `git add .` · ห้าม `git stash`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" · ห้าม refactor/จัดรูปแบบ/แก้ comment อื่น/แปลง encoding · stdlib ล้วน · `ui.html` ห้ามโหลดอะไรจากเน็ต
3. หาจุดแก้จากข้อความหลังคำว่า "ก่อน" ด้วย Grep (เลขบรรทัดอาจเลื่อน) · หาไม่เจอ/เจอหลายที่ (ยกเว้นที่แผนบอกจำนวนไว้) → **หยุด ⛔** บันทึกใน §4
4. **ห้ามแตะ** `%USERPROFILE%\.flashq\` ของจริง · `~/.claude/` · `~/.config/opencode/` · `hooks/` · `opencode/` · ห้ามรัน `flashq install` · ห้ามรัน `flashq run`/`flashq ui` พอร์ต 4097 · ห้ามเรียกโมเดลจริง (เทสต์ใช้ `tests/fake_opencode.py`)
5. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน" · ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย
6. ไฟล์ชั่วคราว/log ไว้ที่ `.tmp/` · **ห้ามรันเทสต์ทั้งชุด ยกเว้น T-11** · งานอื่นรันเฉพาะ `-k` ที่แผนกำหนด
7. **แบบ "เทสต์ก่อน"**: เขียนเทสต์ → รันก่อนแก้โค้ดต้อง FAIL ด้วยข้อความที่แผนบอก (log แดง) → แก้โค้ด → รันซ้ำต้อง PASS (log เขียว) → รัน reg → commit เดียว · ผ่านตั้งแต่ก่อนแก้ / ล้มด้วยเหตุอื่น (AttributeError, ImportError, KeyError, SyntaxError, git/คิวผิดปกติ) → **⛔ หยุด** · ห้ามลดเงื่อนไขเทสต์ · เทสต์เดิมที่แผนไม่ได้สั่งแก้แล้วพัง → ⛔ หยุด (ห้ามแก้เทสต์เดิมเอง)
8. คำสั่งมาตรฐาน (PowerShell · timeout ≥ 300 วิ): `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k "คำค้น" > .tmp/T-xx.red.log 2>&1` (เปลี่ยน `red` เป็น `green` / `reg` ตามขั้น)
9. เทสต์ใหม่ทุกข้อวางใน class `FlashqTest` ต่อจากเทสต์ที่แผนระบุ · ใช้ helper ที่มีอยู่: `self.run_q(...)` · `self.base()` · `self.load_mod("ชื่อ")` · git ในเทสต์ใช้รูปแบบเดียวกับ `test_progress_counts_only_own_commits` (lambda `git` ที่ใส่ `-c user.name=t -c user.email=t@t`)
10. ห้ามเปลี่ยน `job["status"]` และฟังก์ชัน `live_state` — สถานะ `ok_unverified` เป็นแค่สถานะ **สำหรับแสดงผล** ในแถวของหน้าเว็บ (`ui_state`) · เทียบ `job["result"]` แบบไม่สนตัวพิมพ์ (`str(...).upper() == "OK_UNVERIFIED"`)

---

## 1. งาน

- [x] **T-01** `said_done` เข้มขึ้น · ไฟล์: `flashq.py` `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์ใหม่ `test_said_done_strict` ต่อจาก `def test_said_done_ignores_negation` · `mod = self.load_mod("flashq_said_done_strict")` แล้วเรียก `mod.said_done(t)` ตรง ๆ
    - ต้องได้ False (ใส่ `t` เป็นข้อความกำกับ assert): `"ห้ามรายงาน DONE"` · `"จะรายงาน DONE เมื่อเทสต์ผ่าน"` · `"รายงาน DONE เมื่อเทสต์ผ่าน"` · `"ถ้าผ่านให้ตอบ DONE"` · `"| T-01 | DONE | abc123 |"` · `"do not write DONE yet"`
    - ต้องได้ True: `"T-01 DONE แล้ว"` · `"สถานะ: DONE"` · `"**DONE**"` · `"DONE"` · `"ห้ามแตะไฟล์อื่น · T-01 DONE"` · `"ข้อ 1 ถ้าผ่านให้ตอบ\nT-01 DONE"`
  - แดง: `-k "said_done_strict"` → `.tmp/T-01.red.log` ต้องมี `AssertionError: True is not false : ห้ามรายงาน DONE`
  - แก้ (สเปก) ใน `said_done` · `flashq.py` ก่อน: `if prev.lower().endswith("not") or prev.endswith(("ยังไม่", "ไม่ได้", "ไม่")):`
    - คงเงื่อนไขปฏิเสธเดิมไว้ · เพิ่ม (ทุกข้อ = `continue` ไปหา DONE ตัวถัดไป):
    - (ก) บรรทัดที่มี DONE (ตัดช่องว่างหน้า) ขึ้นต้นด้วย `|` = แถวตาราง markdown → ข้าม
    - (ข) `clause` = ข้อความก่อน DONE ในบรรทัดเดียวกัน ตัดเหลือส่วนหลังตัวแบ่งตัวสุดท้ายในชุด `. ! ? · ; — |` · ถ้า `re.search(r"จะ|เมื่อ|ห้าม|ถ้า|ก่อน|หาก|\b(?:will|if|when|before|don'?t|do not)\b", clause, re.I)` → ข้าม
    - (ค) `tail` = ข้อความหลัง DONE ถึงตัวแบ่งตัวแรก (ชุดเดียวกัน + ขึ้นบรรทัด) · ถ้ามี `เมื่อ|ถ้า|หาก|\bif\b|\bwhen\b` → ข้าม
  - เขียว: คำสั่งเดิม → `.tmp/T-01.green.log` PASS · reg: `-k "said_done or epipe or progress or unverified"` → `.tmp/T-01.reg.log` PASS
  - หลักฐานชี้ขาด: `.tmp/T-01.red.log` บรรทัด `AssertionError: True is not false : ห้ามรายงาน DONE` (ค่าก่อนแก้ = True) · green/reg บรรทัดท้าย `passed` ไม่มี `failed`
  - commit: `flashq: คำว่า DONE ในประโยคสั่ง/เงื่อนไข (ห้าม/จะ/เมื่อ/ถ้า/ก่อน) และในแถวตารางไม่นับเป็นงานเสร็จ (T-01)`

- [x] **T-02** `job_progressed` ใช้ `job["head0"]` ข้ามรอบลองใหม่ · ไฟล์: `flashq.py` `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์ใหม่ `test_progress_uses_job_head0` ต่อจาก `test_progress_counts_only_own_commits` (คัดลอกส่วน git init + commit "เริ่ม" ของเทสต์นั้น) → `h0` = HEAD · เขียน `x.txt` แล้ว commit ข้อความ `"งาน (T-01)"` → `h1` = HEAD
    - `self.assertTrue(mod.job_progressed(self.proj, h1, [], {"plan": "PLAN.md", "tasks": "T-01", "head0": h0}))` (รอบลองใหม่ head0 ของรอบนั้น = h1 แต่ commit เกิดในรอบแรก)
    - `self.assertFalse(mod.job_progressed(self.proj, h1, [], {"plan": "PLAN.md", "tasks": "T-01"}))` (ไม่มี head0 ใน job = พฤติกรรมเดิม)
  - แดง: `-k "progress_uses_job_head0"` → `.tmp/T-02.red.log` ต้องมี `AssertionError: False is not true`
  - แก้ (สเปก): บรรทัดแรกในตัวฟังก์ชัน `job_progressed` ให้ `head0 = (job or {}).get("head0") or head0` · `flashq.py` ก่อน: `head1 = _git(root, "rev-parse", "HEAD")` (แทรกบรรทัดใหม่เหนือบรรทัดนี้ · ไม่แตะที่อื่น)
  - เขียว: คำสั่งเดิม → `.tmp/T-02.green.log` · reg `-k "progress or said_done or no_progress or epipe"` → `.tmp/T-02.reg.log`
  - หลักฐานชี้ขาด: red log บรรทัด `AssertionError: False is not true` (ค่าก่อนแก้ = False) · green/reg `passed`
  - commit: `flashq: นับ commit ของงานตั้งแต่รอบแรก (head0 ของ job) ไม่หายเมื่อรอบลองใหม่ (T-02)`

- [x] **T-03** EPIPE หลัง DONE ต้องมีหลักฐานเพิ่ม ไม่งั้น FAIL · ไฟล์: `flashq.py` `tests/fake_opencode.py` `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - fake: เพิ่ม `FAKE_COMMIT=<ข้อความ>` — ต่อจากลูป `FAKE_WRITE` (ต้องมี `--dir`) รัน `git -c user.name=t -c user.email=t@t add -A` แล้ว `git ... commit -q -m <ข้อความ>` ใน `--dir` ด้วย `subprocess.run(..., check=False)` · เพิ่ม `import subprocess` ด้านบน · เพิ่มคำอธิบายใน docstring 1 บรรทัด · `tests/fake_opencode.py` ก่อน: `_f.write(os.environ.get("FAKE_WRITE_TEXT", "x"))`
  - เทสต์เดิม `test_epipe_after_done_not_fail`: เพิ่ม `"FAKE_STEP_REASON": "stop"` ใน env (assert เดิมคงไว้ทั้งหมด) · `tests/test_flashq.py` ก่อน: `r = self.run_q(*self.base(), env={"FAKE_MODE": "epipe", "FAKE_TEXT": "DONE — ครบ"})`
  - เทสต์ใหม่ต่อจากเทสต์นั้น:
    1. `test_epipe_done_without_evidence_fail`: env `{"FAKE_MODE": "epipe", "FAKE_TEXT": "DONE — ครบ"}` (ไม่มี step_finish · ไม่มี commit) → `assertIn("FLASH_RUN=FAIL", r.stdout)` · `assertNotEqual(r.returncode, 0)`
    2. `test_epipe_done_with_commit_ok`: git init + commit "เริ่ม" ใน `self.proj` (รูปแบบ §0 ข้อ 9) · env `{"FAKE_MODE": "epipe", "FAKE_TEXT": "DONE", "FAKE_WRITE": "a.txt", "FAKE_COMMIT": "flashq: งาน (T-01)"}` → `assertIn("FLASH_RUN=OK_UNVERIFIED", r.stdout)` (ข้อนี้ผ่านตั้งแต่ก่อนแก้ได้ = ตัวกันถอย ไม่ใช่ตัวแดง)
  - แดง: `-k "epipe_done"` → `.tmp/T-03.red.log` ข้อ 1 ต้อง FAIL ด้วย `AssertionError: 'FLASH_RUN=FAIL' not found in` (ค่าก่อนแก้ = `FLASH_RUN=OK_UNVERIFIED`) · ข้อ 2 ถ้าล้มเพราะ git/คิว (ไม่ใช่ assert) → ⛔
  - แก้ (สเปก) สาขา EPIPE ใน `_run_once`: เงื่อนไขเดิม `said_done(last)` ต้องมีหลักฐานเพิ่มอย่างน้อย 1 ข้อ: `last_finish == "stop"` **หรือ** `job_progressed(root, head0, [], job)` (ส่ง outputs เป็น list ว่าง = ดูเฉพาะ commit · ห้ามส่ง texts เพราะจะวนกลับไปนับ DONE เดิม) · สาขา elif ของงานอ่านอย่างเดียวคงเดิม · ไม่ผ่านทั้งสอง = FAIL เหมือนเดิม · `flashq.py` ก่อน: `if not errors and rc != 0 and epipe_only(errtxt) and said_done(last):`
  - เขียว: คำสั่งเดิม → `.tmp/T-03.green.log` · reg `-k "epipe or no_progress or real_error"` → `.tmp/T-03.reg.log`
  - หลักฐานชี้ขาด: red log บรรทัด `'FLASH_RUN=FAIL' not found` + มี `FLASH_RUN=OK_UNVERIFIED` · green/reg `passed`
  - commit: `flashq: opencode ล้มด้วย EPIPE หลังตอบ DONE ต้องมี step_finish=stop หรือ commit ของงานด้วย ไม่งั้นเป็น FAIL (T-03)`

- [x] **T-04** งานอ่านอย่างเดียวที่ไฟล์เปลี่ยนเพราะงานอื่น = WARN เท่านั้น · ไฟล์: `flashq.py` `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์ใหม่ต่อจาก `test_readonly_job_warns_when_files_change_and_agent_timeout`:
    1. `test_readonly_modified_by_others_warn_only` (unit): `mod = self.load_mod("flashq_ro_others")` · `self.assertEqual(mod.unverified_reasons({"readonly": True, "modified": ["a.txt"], "modified_others": ["J2"]}, {}), [])` · และ `{"readonly": True, "modified": ["a.txt"]}` ต้องได้ `["งานอ่านอย่างเดียวแต่ไฟล์ในโปรเจกต์เปลี่ยน"]`
    2. `test_readonly_modified_others_recorded` (รวม): `git init` ใน proj (เหมือนเทสต์ต้นแบบ) · รัน `verify PLAN.md T-01 --no-open` หนึ่งครั้งเพื่ออ่าน `job["project"]` จาก JSON ล่าสุด · เขียนไฟล์ `self.home / "jobs" / "J2other.json"` = `{"id": "J2other", "project": <ค่าที่อ่านได้>, "status": "ok", "readonly": False, "kind": "work", "created": "2099-01-01 00:00:00", "started": "2099-01-01 00:00:00", "finished": "2099-01-01 00:00:01"}` · รัน verify อีกครั้งด้วย env `{"FAKE_WRITE": "sneaky3.txt"}` → job ล่าสุด: `self.assertEqual(job.get("modified_others"), ["J2other"])` และ `assertNotIn("งานอ่านอย่างเดียวแต่ไฟล์ในโปรเจกต์เปลี่ยน", job.get("unverified") or [])` · stdout ยังมี `WARN: งานอ่านอย่างเดียวนี้ไฟล์ในโปรเจกต์เปลี่ยน`
  - แดง: `-k "readonly_modified"` → `.tmp/T-04.red.log` ต้องมี `AssertionError: Lists differ: ['งานอ่านอย่างเดียวแต่ไฟล์ในโปรเจกต์เปลี่ยน'] != []`
  - แก้ (สเปก):
    - รายชื่อ `others` ใน snapshot ของงาน readonly: นับงานอื่นที่ไม่ readonly ในโปรเจกต์เดียวกันที่ **กำลังรัน หรือจบหลังงานนี้เริ่ม** → เปลี่ยนเป็น `and (live_state(j) == "running" or (j.get("finished") or "") >= (job.get("started") or "9"))]` · `flashq.py` ก่อน: `and live_state(j) == "running"]`
    - ต่อจากบรรทัดเก็บ modified เพิ่ม `if others: job["modified_others"] = others[:10]` (ข้อความ WARN ที่พิมพ์คงเดิม) · `flashq.py` ก่อน: `job["modified"] = changed[:50]`
    - `unverified_reasons`: เพิ่ม `and not job.get("modified_others")` ท้ายเงื่อนไข · `flashq.py` ก่อน: `if job.get("readonly") and job.get("modified"):`
  - เขียว: คำสั่งเดิม → `.tmp/T-04.green.log` · reg `-k "readonly or unverified or verify"` → `.tmp/T-04.reg.log`
  - หลักฐานชี้ขาด: red log บรรทัด `Lists differ` (ค่าก่อนแก้ = มีเหตุ "งานอ่านอย่างเดียวแต่ไฟล์ในโปรเจกต์เปลี่ยน") · green/reg `passed`
  - commit: `flashq: งานอ่านอย่างเดียวที่ไฟล์เปลี่ยนขณะมีงานอื่นในโปรเจกต์เดียวกัน เตือน WARN อย่างเดียว ไม่ลดผลเป็น OK_UNVERIFIED (T-04)`

- [x] **T-05** ตรวจเลขไฟล์:บรรทัดของผู้สืบจากทุกข้อความ · บังคับอ้างเฉพาะเมื่อบรีฟขอ · ไฟล์: `flashq.py` `tests/fake_opencode.py` `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - fake: ถ้ามี `FAKE_TEXT_PARTS` (คั่นด้วย `||`) ให้พิมพ์ event text ทีละส่วน (รูปแบบเดียวกับบรรทัด text สุดท้าย) **ก่อน** ข้อความ `FAKE_TEXT` สุดท้าย · `tests/fake_opencode.py` ก่อน: `print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": os.environ.get("FAKE_TEXT", "PONG")}}), flush=True)`
  - เทสต์ใหม่ต่อจาก `test_investigate_checks_citations` (คัดลอกวิธีสร้างไฟล์ในโปรเจกต์ + รูปแบบอ้างจากเทสต์นั้น · ตัวอย่างด้านล่างใช้ `a.py` ที่มี 3 บรรทัด):
    1. `test_investigate_cites_all_parts`: `investigate --no-open "สืบ ขอไฟล์:บรรทัด"` env `{"FAKE_TEXT_PARTS": "พบที่ a.py:1", "FAKE_TEXT": "สรุป: ต้นตอตามข้างบน"}` → `assertGreaterEqual(job["citations"]["ok"], 1)` · `assertNotIn("ผู้สืบไม่อ้างเลขไฟล์:บรรทัดเลย", job.get("unverified") or [])`
    2. `test_investigate_brief_gate`: บรีฟ `"สืบ"` + `FAKE_TEXT="ไม่พบปัญหา"` → ไม่มีเหตุ "ผู้สืบไม่อ้างเลขไฟล์:บรรทัดเลย" · บรีฟ `"สืบ ขอเลขบรรทัด"` + ข้อความเดิม → มีเหตุนั้น · บรีฟ `"สืบ"` + `FAKE_TEXT="ต้นตอ a.py:999"` → มีเหตุที่ขึ้นต้น `ผู้สืบอ้างเลขไฟล์:บรรทัดผิด`
  - แดง: `-k "investigate_cites_all_parts or investigate_brief_gate"` → `.tmp/T-05.red.log` ต้องมี `AssertionError: 0 not greater than or equal to 1`
  - แก้ (สเปก):
    - dict ที่ `_run_once` คืน เพิ่ม `"text_all": "\n".join(texts)` · `flashq.py` ก่อน: `"denied": denied, "perm_denied": perm, "recent": recent[-5:], "epipe_done": epipe_done}`
    - ตัวตรวจ citations ใช้ `res.get("text_all") or res["last"]` · `flashq.py` ก่อน: `cites = check_citations(res["last"], root)`
    - `unverified_reasons`: เหตุ "ไม่อ้างเลย" เฉพาะเมื่อ `re.search(r"file:line|ไฟล์:บรรทัด|เลขบรรทัด", job.get("prompt") or "", re.I)` · เหตุ "อ้างผิด" คงเดิมทุกกรณี · `flashq.py` ก่อน: `elif not cites.get("ok"):`
  - เขียว: คำสั่งเดิม → `.tmp/T-05.green.log` · reg `-k "investigate or citation or unverified"` → `.tmp/T-05.reg.log`
  - หลักฐานชี้ขาด: red log บรรทัด `0 not greater than or equal to 1` (ค่าก่อนแก้ citations ok = 0 เพราะตรวจแค่ข้อความสุดท้าย) · green/reg `passed`
  - commit: `flashq: ตรวจเลขไฟล์:บรรทัดของผู้สืบจากทุกข้อความ และเตือน "ไม่อ้างเลย" เฉพาะเมื่อบรีฟขอเลขบรรทัด (T-05)`

- [x] **T-06** `wait` / `log` พิมพ์บรรทัด WARN ของผลยังไม่ยืนยัน · ไฟล์: `flashq.py` `tests/test_flashq.py` `docs/REFERENCE.md` · แบบ: เทสต์ก่อน
  - เทสต์ใหม่ `test_wait_and_log_show_unverified_warn` ต่อจาก `test_wait_blocks_until_done_and_reports`: `self.run_q(*self.base())` (โปรเจกต์ไม่ใช่ git + ข้อความ `PONG` = OK_UNVERIFIED เหตุไม่มี commit) · อ่าน job id จาก JSON ล่าสุดใน `self.home / "jobs"` · `r2 = self.run_q("wait", jid, "--poll", "0.5")` และ `r3 = self.run_q("log", jid)` → ทั้งคู่ `assertIn("WARN: ผล OK ยังไม่ยืนยัน — ไม่มี commit ของงานและไม่มีคำว่า DONE", r.stdout)`
  - แดง: `-k "wait_and_log_show_unverified"` → `.tmp/T-06.red.log` ต้องมี `AssertionError: 'WARN: ผล OK ยังไม่ยืนยัน` … `not found in`
  - แก้ (สเปก): ทั้งสองคำสั่ง ถ้า `str(j.get("result") or "").upper() == "OK_UNVERIFIED"` และมี `j.get("unverified")` → `print("WARN: ผล OK ยังไม่ยืนยัน — " + " · ".join(j["unverified"]))` (รูปแบบเดียวกับที่ `run` พิมพ์)
    - `cmd_wait` วางเหนือบรรทัดนี้ · `flashq.py` ก่อน: `print("---- สรุปท้าย ----")`
    - `cmd_log` วางเหนือบรรทัดนี้ · `flashq.py` ก่อน: `print("---- ข้อความท้าย ----")`
  - เอกสาร (1) `docs/REFERENCE.md` ก่อน: `OK_UNVERIFIED นับเป็น exit 0 แต่มีบรรทัด WARN บอกเหตุ` → ต่อท้ายวลีนี้ด้วยวงเล็บ "(run · wait · log พิมพ์บรรทัด WARN: ผล OK ยังไม่ยืนยัน — …)" (ใส่ backtick รอบชื่อคำสั่งตามสไตล์ไฟล์)
  - เอกสาร (2) `docs/REFERENCE.md` ก่อน: `FLASH_RUN=OK|FAIL|QUOTA|TIMEOUT|NOSTART|BUSY|QUEUE_TIMEOUT` → เปลี่ยนเป็น `FLASH_RUN=OK|OK_UNVERIFIED|FAIL|DENIED|QUOTA|TIMEOUT|NOSTART|BUSY|QUEUE_TIMEOUT`
  - เขียว: คำสั่งเดิม → `.tmp/T-06.green.log` · reg `-k "wait or log or unverified"` → `.tmp/T-06.reg.log`
  - หลักฐานชี้ขาด: red log บรรทัด `not found in` (ค่าก่อนแก้ = ไม่มีบรรทัด WARN ใน wait/log) · green/reg `passed`
  - commit: `flashq: wait/log พิมพ์บรรทัด WARN บอกเหตุของผล OK_UNVERIFIED (T-06)`

- [x] **T-07** คู่มือคำสั่ง Claude รู้จัก OK_UNVERIFIED · ไฟล์: `claude/commands/flash-plan.md` `claude/commands/flash-goal.md` · แบบ: แก้เอกสาร (ไม่มีเทสต์)
  - `claude/commands/flash-plan.md` ก่อน: `ทุกสถานะ: OK · FAIL · DENIED · QUOTA · TIMEOUT · NOSTART · BUSY` → เป็น `ทุกสถานะ: OK · OK_UNVERIFIED · FAIL · DENIED · QUOTA · TIMEOUT · NOSTART · BUSY` และต่อท้ายวงเล็บเดิมของบรรทัดนั้นด้วย ` · OK_UNVERIFIED = จบแต่ยังไม่มีหลักฐาน อ่านบรรทัด `WARN:` แล้ว `/flash-check` ตามปกติ` (ถ้าวางต่อท้ายแล้วประโยคอ่านไม่รู้เรื่อง ให้วางเป็นประโยคใหม่ท้าย bullet เดียวกัน)
  - `claude/commands/flash-goal.md` ก่อน: `` - `FLASH_RUN=QUOTA` (สลับครบแล้ว) / `NOSTART` ซ้ำ / `BUSY` → หยุด รายงาน `` → เพิ่ม bullet ใหม่ใต้บรรทัดนี้: `` - `FLASH_RUN=OK_UNVERIFIED` = Flash จบแต่ยังไม่มีหลักฐาน → อ่านบรรทัด `WARN:` (จาก `wait`/`log`) แล้ว `/flash-check` ก่อน `goal verify` · ห้ามนับว่าผ่านจากคำบอกของ Flash ``
  - ตรวจ: `Select-String -Path claude/commands/flash-plan.md,claude/commands/flash-goal.md -Pattern OK_UNVERIFIED > .tmp/T-07.grep.log` ต้องเจอทั้ง 2 ไฟล์
  - หลักฐานชี้ขาด: `.tmp/T-07.grep.log` มี 2 ไฟล์ (ค่าก่อนแก้ = ไม่เจอเลย) · `git diff --stat` เปลี่ยนเฉพาะ 2 ไฟล์
  - commit: `flash-plan: คู่มือ flash-plan/flash-goal รู้จักผล OK_UNVERIFIED (อ่าน WARN แล้วตรวจก่อนเชื่อ) (T-07)`

- [ ] **T-08** แถวงานบนหน้าเว็บมีสถานะแสดงผล `ok_unverified` + เหตุ + สถิติ · ไฟล์: `flashq.py` `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์ใหม่ `test_ui_rows_show_ok_unverified` ต่อจาก `test_unverified_routes_like_ok_with_warning`:
    - `mod = self.load_mod("flashq_ui_unv")` · บันทึก 2 งานด้วย `mod.save_job(...)`: `{"id": "J1u", "project": str(self.proj), "status": "ok", "result": "OK_UNVERIFIED", "unverified": ["ไม่มี commit ของงานและไม่มีคำว่า DONE"], "created": "2099-01-01 00:00:00", "started": "2099-01-01 00:00:00", "finished": "2099-01-01 00:01:00"}` และ `J2o` แบบเดียวกันแต่ `"result": "OK"` ไม่มี unverified
    - `st = mod.ui_state()` → แถว J1u ใน `st["history"]` มี `state == "ok_unverified"` และ `"ไม่มี commit" in reason` · แถว J2o `state == "ok"` · `mod.job_stats(st["history"])["by_kind"]` กลุ่ม `work` มี `ok == 1`, `unv == 1`, `fail == 0`
    - เขียน assert ให้ค่าจริงอยู่ซ้าย: `self.assertEqual(row["state"], "ok_unverified")` (log แดงจึงขึ้น `'ok' != 'ok_unverified'`)
    - ถ้า `mod.ui_state()` ล้มเพราะสภาพแวดล้อม (ไม่ใช่ assert) → ใช้ `self.start_ui()` + `/api/state` แทน (รูปแบบเทสต์ที่เรียก `self.http(base + "/api/state")`) แล้วอ่าน `history`/`stats` จาก JSON ด้วย assert ชุดเดิม · วิธีนี้ก็ล้ม → ⛔ หยุด บันทึก §4
  - แดง: `-k "ui_rows_show_ok_unverified"` → `.tmp/T-08.red.log` ต้องมี `AssertionError: 'ok' != 'ok_unverified'`
  - แก้ (สเปก):
    - ใน `ui_state` สาขางานที่จบแล้ว: ก่อนคำนวณ reason ให้ `if st == "ok" and str(j.get("result") or "").upper() == "OK_UNVERIFIED": row["state"] = "ok_unverified"; row["unverified"] = j.get("unverified") or []` แล้วเรียก `job_reason(j, row["state"])` (ตัวแปร `st` คงเดิม ไม่เปลี่ยนการแยกกลุ่ม running/queued/history) · `flashq.py` ก่อน: `row["reason"] = job_reason(j, st)`
    - `job_reason`: เพิ่มสาขา `if state == "ok_unverified": return one_line("ผลยังไม่ยืนยัน: " + (" · ".join(j.get("unverified") or []) or "ไม่มีหลักฐานงาน"), 500)` ต่อจากสาขา quota · `flashq.py` ก่อน: `return last or "โควตาของโมเดลหมด"`
    - `job_stats` เพิ่มช่อง `"unv": 0` ใน dict ตั้งต้น · `flashq.py` ก่อน: `g = acc.setdefault(name, {"name": name, "n": 0, "ok": 0, "secs": []})`
    - `job_stats` ใต้บรรทัดนับ ok เพิ่ม `g["unv"] += r["state"] == "ok_unverified"` · `flashq.py` ก่อน: `g["ok"] += r["state"] == "ok"`
    - `job_stats` ให้ `fail` = `g["n"] - g["ok"] - g["unv"]` · `flashq.py` ก่อน: `g.update(fail=g["n"] - g["ok"], avg_sec=`
    - ห้ามแก้ `run_stats` (เวลาเฉลี่ยใช้ status ok ซึ่งรวมงานยังไม่ยืนยันอยู่แล้ว = ถูกต้อง)
    - **แก้เทสต์เดิม (ผู้ตรวจสั่งเพิ่ม · รอบ 1 ล้มเพราะแผนไม่ได้บอก)**: `test_ui_submit_retry_plans` ส่งงาน 2 งานผ่าน fake ที่ตอบ `PONG` ในโปรเจกต์ที่ไม่ใช่ git = ผล `OK_UNVERIFIED` จริง จึงต้องนับเป็น `unv` ไม่ใช่ `ok` · `tests/test_flashq.py` ก่อน (เจอ 1 ที่): `self.assertEqual(st["stats"]["by_project"][0]["ok"], 2)` → หลัง: `self.assertEqual(st["stats"]["by_project"][0]["ok"], 0)` แล้วเพิ่มบรรทัดต่อท้าย `self.assertEqual(st["stats"]["by_project"][0]["unv"], 2)` · ห้ามแก้เทสต์เดิมอื่นนอกจากบรรทัดนี้ · ถ้า reg ล้มที่เทสต์เดิมตัวอื่น = ⛔ หยุด
    - ผู้ทำใช้ `.tmp/T-08.FAIL.patch` (ส่วนโค้ดของรอบแรก ผ่านสเปกแล้ว) อ้างอิงได้ แต่ต้องทำตามสเปกข้างบนเองและรันขั้นแดง→เขียวใหม่ทั้งหมด
  - เขียว: คำสั่งเดิม → `.tmp/T-08.green.log` · reg `-k "ui or stats or unverified or goal"` → `.tmp/T-08.reg.log`
  - หลักฐานชี้ขาด: red log บรรทัด `'ok' != 'ok_unverified'` (ค่าก่อนแก้ = ok) · green/reg `passed`
  - commit: `flashq: หน้าเว็บแยกสถานะ "ยังไม่ยืนยัน" ของงาน OK_UNVERIFIED พร้อมเหตุ และสถิติไม่นับรวมกับผ่านจริง (T-08)`

- [ ] **T-09** การ์ดเป้าหมาย: รอบที่ FAIL ไม่ขึ้น "รอ Claude ตรวจ" · ป้ายรอบยังไม่ยืนยัน · ไฟล์: `flashq.py` `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: เพิ่มใน `test_goal_published_for_ui` ต่อจากบรรทัดนี้ · `tests/test_flashq.py` ก่อน: `self.assertIn("รอบ 1 Flash ทำเสร็จแล้วแต่ยังไม่ได้ goal verify", g["phase"]["notes"][0]["t"])`
    - `g = mod.ui_goals([], [dict(done, state="fail")])[0]` → `assertEqual(g["unverified"], [])` · `assertNotEqual(g["phase"]["step"], "review")` · `assertIn("FAIL", g["phase"]["label"])` (ข้อความขั้นอยู่ในคีย์ `label` ของ `ph(...)`)
    - `g = mod.ui_goals([], [dict(done, state="ok_unverified")])[0]` → `assertEqual((g["unverified"], g["ok_unverified"]), ([1], [1]))` · `assertEqual(g["phase"]["step"], "review")` · `assertIn("ยังไม่ยืนยัน", g["phase"]["label"])`
  - แดง: `-k "goal_published_for_ui"` → `.tmp/T-09.red.log` ต้องมี `AssertionError: Lists differ: [1] != []`
  - แก้ (สเปก):
    - `ui_goals` นับรอบรอตรวจเฉพาะงานที่จบดี: เปลี่ยนเป็น `r.get("state") in ("ok", "ok_unverified")` · `flashq.py` ก่อน: `and r.get("finished", "") > since and r.get("state") not in ("cancelled", "busy", "queue_timeout")`
    - `ui_goals` ส่งเพิ่ม `ok_unverified=` รายการรอบใน `unv` ที่งานของรอบนั้น state = `ok_unverified` (เรียงเลขรอบ) · `flashq.py` ก่อน: `jobs=jobs_now, last_job=lj, phase=phase, unverified=unv,`
    - `goal_phase`: เหนือสาขา "รอ Claude ตรวจ" เพิ่ม `if fresh and verdict != "DONE" and last_job.get("state") not in ("ok", "ok_unverified"):` → `return ph("plan", f"❌ งาน Flash รอบ {last_job['round']} จบด้วย {str(last_job.get('state', '')).upper()} — ดู log แล้วแก้แผน/ส่งใหม่ (ไม่ต้อง goal verify)", last_job.get("ago_sec"), "จบมา", True, rnd=last_job["round"])` (รูปแบบเดียวกับสาขา cancelled) · และในสาขา review ต่อท้ายข้อความด้วย `" · ⚠ ผลยังไม่ยืนยัน"` เมื่อ `last_job.get("state") == "ok_unverified"` · `flashq.py` ก่อน: `if fresh and verdict != "DONE":`
  - เขียว: คำสั่งเดิม → `.tmp/T-09.green.log` · reg `-k "goal"` → `.tmp/T-09.reg.log`
  - หลักฐานชี้ขาด: red log บรรทัด `[1] != []` (ค่าก่อนแก้ = รอบ FAIL นับเป็นรอบรอตรวจ) · green/reg `passed`
  - commit: `flashq: การ์ดเป้าหมายไม่ขึ้น "รอ Claude ตรวจ" เมื่อรอบนั้น Flash จบไม่ผ่าน และบอกรอบที่ผลยังไม่ยืนยัน (T-09)`

- [ ] **T-10** หน้าเว็บแสดงสถานะ "ยังไม่ยืนยัน" · ไฟล์: `ui.html` · แบบ: แก้หน้าเว็บ + ตรวจ syntax (ไม่มี pytest)
  - แก้ (สเปก · ข้อความไทย · สีใช้ตัวแปรที่มีอยู่):
    - CSS เพิ่ม `.s-unv { background: var(--quota); color: #1d2430; }` ต่อท้ายบรรทัด · `ui.html` ก่อน: `.s-ok { background: var(--ok); }`
    - `STATUS` เพิ่ม `ok_unverified: ["ยังไม่ยืนยัน", "s-unv"],` ต่อจาก ok · `ui.html` ก่อน: `const STATUS = { ok: ["OK", "s-ok"], fail: ["FAIL", "s-fail"]`
    - `FINAL` เพิ่ม `"ok_unverified"` · `ui.html` ก่อน: `const FINAL = ["ok", "fail", "denied", "quota", "timeout", "nostart"];`
    - `CELE` เพิ่ม `ok_unverified: { pose: "cheer", mood: "flat", icon: "⚠", text: "เสร็จแต่ยังไม่ยืนยัน", cls: "of-st-quota" }` (ต้องมี ไม่งั้น `CELE[c.state].cls` พัง) · `ui.html` ก่อน: `nostart: { pose: "sit", mood: "sad", icon: "❓", text: "ไม่เริ่มทำงาน (NOSTART)", cls: "of-st-bad" } };`
    - `TRAIL_ICON` เพิ่ม `ok_unverified: "⚠"` · `ui.html` ก่อน: `const TRAIL_ICON = { ok: "✅", fail: "❌"`
    - เสียงจบ: `ok_unverified` ใช้เสียงเดียวกับ ok · `ui.html` ก่อน: `if (st === "ok") beep([[660, 0.14], [880, 0.22]]);`
    - เวลาเฉลี่ย/ประมาณเวลา: นับ `ok_unverified` เหมือน ok · `ui.html` ก่อน: `h.state === "ok" && h.duration_sec >= 5` (2 ที่ — แก้ทั้งสองเป็น `(h.state === "ok" || h.state === "ok_unverified") && h.duration_sec >= 5`)
    - ข้อความ "ยังไม่มี token": ไม่ขึ้นกับ ok_unverified · `ui.html` ก่อน: `if (!f) return j && j.state !== "ok" && j.state !== "cancelled" && j.finished`
    - สรุปวันนี้: เพิ่ม `unvN` = จำนวน `ok_unverified` แสดงเป็น `⚠ ${unvN} ยังไม่ยืนยัน` ระหว่างผ่านกับไม่ผ่าน (แสดงเมื่อ unvN > 0) · `ui.html` ก่อน: `const okN = td.filter((h) => h.state === "ok").length`
    - ตารางสถิติ: ช่อง "ผ่าน" แสดง `${pct}%` ตามเดิม แล้วต่อท้าย ` · ⚠${g.unv}` เมื่อ `g.unv > 0` · `ui.html` ก่อน: `<td>${pct}%</td>`
    - ป้ายสถานะแถวประวัติ: ถ้ามี `j.unverified` ให้ title/tooltip ใช้ `j.reason` (ถ้าโค้ดใช้ `reason` เป็น tooltip อยู่แล้ว ไม่ต้องแก้ — Grep `.reason` ยืนยันแล้วบันทึกใน §4)
  - ตรวจ syntax: `python -c "import re,pathlib; s=pathlib.Path('ui.html').read_text(encoding='utf-8'); pathlib.Path('.tmp/ui_script.js').write_text('\n'.join(re.findall(r'<script[^>]*>(.*?)</script>', s, re.S)), encoding='utf-8')"` แล้ว `node --check .tmp/ui_script.js > .tmp/T-10.node.log 2>&1` ต้อง exit 0
  - ตรวจ: `-k "ui"` → `.tmp/T-10.reg.log` PASS
  - หลักฐานชี้ขาด: `.tmp/T-10.node.log` ว่าง + exit 0 · Grep `ok_unverified` ใน ui.html เจอ ≥ 6 ที่ (ค่าก่อนแก้ = 0) · reg `passed`
  - commit: `ui: แสดงสถานะ "ยังไม่ยืนยัน" (ป้ายสีเหลือง · สรุปวันนี้ · สถิติ · เส้นทางแผน) แยกจากผ่านจริง (T-10)`

- [ ] **T-11** CHANGELOG + รันทั้งชุด · ไฟล์: `CHANGELOG.md` · แบบ: เอกสาร + ตรวจรวม
  - เพิ่มหัวข้อ `## 2026-11-04` เหนือหัวข้อเดิม (ใหม่สุดอยู่บน) · `CHANGELOG.md` ก่อน: `## 2026-11-01`
    - bullet (ไทย · รูปแบบเดียวกับหัวข้อเดิม): (1) หน้าเว็บแยกสถานะ "ยังไม่ยืนยัน" + เหตุ + สถิติ (T-08, T-10) · (2) งานอ่านอย่างเดียวที่ไฟล์เปลี่ยนเพราะงานอื่นในโปรเจกต์ = WARN ไม่ลดผล · เก็บ `modified_others` (T-04) · (3) `wait`/`log` พิมพ์ WARN ของ OK_UNVERIFIED (T-06, T-07) · (4) DONE ในประโยคสั่ง/เงื่อนไข/แถวตารางไม่นับ · EPIPE หลัง DONE ต้องมี step_finish=stop หรือ commit (T-01, T-03) · (5) นับ commit ข้ามรอบลองใหม่ (T-02) · (6) ผู้สืบ: ตรวจเลขบรรทัดจากทุกข้อความ · "ไม่อ้างเลย" เฉพาะบรีฟที่ขอ (T-05) · (7) การ์ดเป้าหมาย: รอบ FAIL ไม่ขึ้นรอตรวจ (T-09)
  - รันทั้งชุด (timeout ≥ 600 วิ): `$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q > .tmp/T-11.full.log 2>&1` ต้อง `passed` ไม่มี `failed` · มีพัง → ⛔ หยุด บันทึกชื่อเทสต์ใน §4 (ห้ามแก้โค้ดในงานนี้)
  - `python tests/ui_smoke.py > .tmp/T-11.smoke.log 2>&1` ต้อง exit 0 + `UI_SMOKE OK` · exit 3 (ไม่มี playwright) = บันทึก "ไม่ได้รัน (ENV)" 🟡 ไม่ใช่ ⛔
  - หลักฐานชี้ขาด: `.tmp/T-11.full.log` บรรทัดท้าย (จำนวน passed) · `.tmp/T-11.smoke.log` บรรทัด `UI_SMOKE OK` หรือ exit 3
  - commit: `flashq: บันทึก CHANGELOG แผนเสถียร 5 (OK_UNVERIFIED แยกสถานะ · ลดเตือนผิด · DONE เข้มขึ้น) (T-11)`

## 2. รอผู้ใช้ตัดสิน (ไม่ขวางการทำงาน · ผู้ทำทำตามสเปกได้เลย)
- T-01 ข้อ (ก): แถวตาราง `| T-01 | DONE |` ไม่นับ — ถ้า worker รายงานผลเป็นตาราง §4 อย่างเดียวโดยไม่มี commit ผลจะเป็น OK_UNVERIFIED/FAIL (งานที่ commit จริงไม่กระทบ)
- T-09: รอบที่ Flash จบไม่ผ่าน การ์ดขึ้นขั้น "plan" + ❌ แทน "รอ Claude ตรวจ" — ถ้าต้องการให้ Claude ยัง goal verify รอบ FAIL ด้วย ให้ตัดสาขานี้ออก

## 3. นอกแผนนี้
สาเหตุที่ EPIPE เกิด · `run_stats` (เวลาเฉลี่ย) · ป้าย `g.unverified` ของการ์ดเป้าหมาย (เป็นคนละความหมาย = รอบที่ยังไม่ goal verify) · `python flashq.py install` / รีสตาร์ต `flashq ui` (ทำโดย session หลักหลัง merge)

## 4. ผล (ผู้ทำเติม · ผู้ตรวจเติมช่องขวา)
| งาน | ผล | commit | หลักฐานชี้ขาด | ตรวจ Claude |
|---|---|---|---|---|
| T-01 | DONE | 91ce8fc | `.tmp/T-01.red.log` บรรทัด `AssertionError: True is not false : ห้ามรายงาน DONE` · `.tmp/T-01.green.log` `1 passed, 206 deselected` · `.tmp/T-01.reg.log` `10 passed, 197 deselected` | ✅ ตรวจ diff + log แดง→เขียวตรงสเปก |
| T-02 | DONE | 80db5d1 | `.tmp/T-02.red.log` บรรทัด `AssertionError: False is not true` · `.tmp/T-02.green.log` `1 passed, 207 deselected` · `.tmp/T-02.reg.log` `10 passed, 198 deselected` | ✅ ตรวจ diff + log แดง→เขียวตรงสเปก |
| T-03 | DONE | 650f159 | `.tmp/T-03.red.log` บรรทัด `AssertionError: 'FLASH_RUN=FAIL' not found` + มี `FLASH_RUN=OK_UNVERIFIED` · `.tmp/T-03.green.log` `2 passed, 208 deselected` · `.tmp/T-03.reg.log` `8 passed, 202 deselected` | ✅ ตรวจ diff + log แดง→เขียวตรงสเปก |
| T-04 | DONE | d142f7a | `.tmp/T-04.red.log` บรรทัด `AssertionError: Lists differ: ['งานอ่านอย่างเดียวแต่ไฟล์ในโปรเจกต์เปลี่ยน'] != []` · `.tmp/T-04.green.log` `2 passed, 210 deselected` · `.tmp/T-04.reg.log` `15 passed, 197 deselected` | ✅ ตรวจ diff + log แดง→เขียวตรงสเปก |
| T-05 | DONE | ba050bb | `.tmp/T-05.red.log` บรรทัด `AssertionError: 0 not greater than or equal to 1` · `.tmp/T-05.green.log` `2 passed, 212 deselected` · `.tmp/T-05.reg.log` `10 passed, 204 deselected` | ✅ ตรวจ diff + log แดง→เขียวตรงสเปก |
| T-06 | DONE | 977abcf | `.tmp/T-06.red.log` บรรทัด `AssertionError: 'WARN: ผล OK ยังไม่ยืนยัน — …' not found in` · `.tmp/T-06.green.log` `1 passed, 214 deselected` · `.tmp/T-06.reg.log` `16 passed, 199 deselected` | ✅ ตรวจ diff + log แดง→เขียวตรงสเปก |
| T-07 | DONE | d41aaf2 | `.tmp/T-07.grep.log` เจอ 2 ไฟล์ (`claude\commands\flash-plan.md:74` · `claude\commands\flash-goal.md:58`) | ✅ ตรวจ diff + log แดง→เขียวตรงสเปก |
| T-08 | ⛔ FAIL (reg) | — | `.tmp/T-08.red.log` ผ่าน `'ok' != 'ok_unverified'` · `.tmp/T-08.green.log` `1 passed` · แต่ `.tmp/T-08.reg.log` `test_ui_submit_retry_plans` ล้ม `AssertionError: 0 != 2` (บรรทัด `test_flashq.py:1774` คาด `by_project[0]["ok"] == 2` แต่ 2 งานนั้นเป็น OK_UNVERIFIED จึงย้ายไป `unv` ตามสเปก) · diff ที่ยังไม่ commit เก็บไว้ `.tmp/T-08.FAIL.patch` แล้ว revert working tree | ❌ แผนผิด (ไม่ได้สั่งแก้เทสต์เดิม `test_ui_submit_retry_plans`) → ส่ง T-08 ซ้ำพร้อมสเปกแก้เทสต์เดิม |
| T-09 | | | | |
| T-10 | | | | |
| T-11 | | | | |

## 5. หลังทำครบ (session หลัก · ไม่ใช่ผู้ทำ)
- `/flash-check docs/plans/PLAN_FLASH_STABILIZE_5.md` → merge เข้า master → `python flashq.py install` จาก checkout หลัก `D:\MyCode\flashq` (T-07 แก้ `claude/commands/`) → รีสตาร์ต `flashq ui` พอร์ต 4097

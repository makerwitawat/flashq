# แผน ออฟฟิศใช้ง่าย (แก้บั๊กมุมมอง 🏢 ออฟฟิศ · ลดศัพท์ · แผงหัวหน้า/ใบสั่งงาน) — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-04 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_OFFICE_UX.md T-01..T-11 --switch-on-quota 4` · base commit ตอนวางแผน: `75e38df`
> หลักฐานจากผู้สืบ 2 ฉบับ (บั๊ก + ความง่าย) — **ผู้สืบอ้างเลขบรรทัดผิดหลายจุด** · ข้อความ "ก่อน" ทุกข้อในแผนนี้ Claude Grep ยืนยันแล้วว่าเจอ 1 ที่พอดีใน `ui.html` ที่ `75e38df`

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: ui.html, CHANGELOG.md, docs/REFERENCE.md
flashq-parallel: yes

1. **ทำทีละงานตามลำดับ T-01 → T-11 · 1 งาน = 1 commit** (`git add -- ` ตามด้วยไฟล์ในช่อง "ไฟล์" ของงานนั้นเท่านั้น + `git commit` ข้อความไทยตามช่อง commit มี `(T-xx)` + บรรทัด trailer `Flash-Task: T-xx`) · **ห้าม push** · ห้าม `git add -A` / `git add .` · ห้าม `git stash`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" · ห้าม refactor/จัดรูปแบบ/แก้ comment อื่น/แปลง encoding · `ui.html` ห้ามโหลดอะไรจากเน็ต · ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย
3. **หาจุดแก้จากข้อความหลังคำว่า "ก่อน"/"จุดเสียบ" ด้วย Grep เท่านั้น — ห้ามเชื่อเลขบรรทัด** (เลขบรรทัดในแผนเป็นแค่คำใบ้ และเลื่อนทุกครั้งที่งานก่อนหน้าแก้ไฟล์) · หาไม่เจอ/เจอหลายที่ → **หยุด ⛔** บันทึกใน §4
4. **ห้ามแตะ** `flashq.py` · `%USERPROFILE%\.flashq\` ของจริง · `~/.claude/` · `~/.config/opencode/` · `hooks/` · `claude/` · `opencode/` · `tests/` · ห้ามรัน `flashq install` · ห้ามรัน `flashq run`/`flashq ui` พอร์ต 4097 · ห้ามกดปุ่มที่เปลี่ยนสถานะงานจริง
5. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน"
6. ไฟล์ชั่วคราว/log ไว้ที่ `.tmp/` · ห้ามรันเทสต์ pytest ทั้งชุด (งานนี้แตะแค่ `ui.html` + เอกสาร)
7. ฟังก์ชันใหม่ทุกตัววางเป็น `const`/`function` ระดับบนสุดของ `<script>` (ไม่ซ้อนใน function อื่น) เพื่อให้ตัวตรวจ (ข้อ 8 ค) เรียกได้ · ต้องไม่ error เมื่อฟิลด์เป็น `null`/`undefined` (ใช้ `|| ""` / `|| []`)

### 8. คำสั่งตรวจมาตรฐาน (PowerShell · ตั้ง timeout ≥ 120 วิ)
- **ก) syntax JS** (ทุกงานที่แก้ `ui.html`):
  `python -c "import re,pathlib; s=pathlib.Path('ui.html').read_text(encoding='utf-8'); pathlib.Path('.tmp/ui_script.js').write_text('\n'.join(re.findall(r'<script[^>]*>(.*?)</script>', s, re.S)), encoding='utf-8')"` แล้ว `node --check .tmp/ui_script.js > .tmp/T-xx.node.log 2>&1` → exit 0 + log ว่าง
- **ข) หน้าจริงไม่มี JS error**: `python tests/ui_smoke.py > .tmp/T-xx.smoke.log 2>&1` → exit 0 + บรรทัด `UI_SMOKE OK` (ใช้สำเนาข้อมูลจริงแบบอ่านอย่างเดียว · พอร์ตว่างที่ระบบเลือก) · exit 3 = สภาพแวดล้อมไม่พร้อม → บันทึก "ไม่ได้รัน (ENV)" 🟡 ไม่ใช่ ⛔
- **ค) ตรวจลอจิกในหน้า** (งานที่มีบรรทัด `ตรวจลอจิก:`): ครั้งแรก (T-01) สร้าง `.tmp/office_eval.py` ตามนี้ (ไม่ commit) แล้วใช้ซ้ำทุกงาน:
```python
import pathlib, sys
from playwright.sync_api import sync_playwright
js = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True); p = b.new_page()
    p.goto(pathlib.Path("ui.html").resolve().as_uri(), wait_until="load")  # เปิดไฟล์ตรง ๆ: fetch ล้มได้ ไม่เป็นไร ฟังก์ชันระดับบนสุดเรียกได้
    r = p.evaluate(js); b.close()
print("EVAL=" + str(r)); sys.exit(0 if r == "OK" else 1)
```
  ไฟล์ `.tmp/T-xx.eval.js` = นิพจน์เดียวแบบ `(() => { ...; return ปัญหา.length ? ปัญหา.join(" | ") : "OK"; })()` ตรวจตามข้อที่งานกำหนด · รัน `$env:PYTHONIOENCODING="utf-8"; python .tmp/office_eval.py .tmp/T-xx.eval.js > .tmp/T-xx.eval.log 2>&1` → ต้องมีบรรทัด `EVAL=OK` · ตั้ง `state = {...}` ในนิพจน์ได้ถ้าฟังก์ชันอ่าน `state`
- **ง) นับข้อความ**: `(Select-String -Path ui.html -SimpleMatch -AllMatches -Pattern "ข้อความที่นับ").Matches.Count` (นับจำนวนครั้ง ไม่ใช่จำนวนบรรทัด · ไฟล์อื่นเปลี่ยน `-Path` · ค่าก่อนแก้ระบุในแต่ละงาน)

---

## 1. งาน

### กลุ่ม A — บั๊ก
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว): `docLine`/`qaLine` (นิยามที่ `const qaLine = (j) =>` / `const docLine = (j) =>`) ถูกเรียกแค่ในแดชบอร์ด 2 ที่ ไม่มีในการ์ด/ตาราง "เพิ่งจบ" ของออฟฟิศ → งานช่างเอกสาร (state `ok` แต่ `doc.state="pending"`) ขึ้น OK เฉย ๆ ไม่มีปุ่ม รับ/ทิ้งร่าง · `ofTD` นับ `td.length` ทั้งที่ `job_stats` ใน `flashq.py` ข้าม `("cancelled", "busy", "queue_timeout")` · การ์ดผู้สืบ: `const plan = …` ให้ `"🕵️ สืบ "` + ชื่อแผนว่าง และ `${esc(r.message ? "" : r.tasks)}` ซ่อนบรีฟ · ตัวตาม log ออฟฟิศ (`async function officePoll`) เมื่อ attempt เปลี่ยน รีเซ็ตตัวนับแต่ไม่รีเซ็ต `L.offset` (ต่อมา `L.offset = d.offset;` ทับอีก) — แดชบอร์ดรีเซ็ต `logOffset = 0` ถูกแล้ว · คลิกปุ่มในแถว `<tr data-oflog>` ของออฟฟิศจะพาไปแดชบอร์ด เพราะตัวจับคลิกยกเว้นแค่ 4 ปุ่ม

- [x] **T-01** เรียก `docLine`/`qaLine` ในการ์ดงาน + ตาราง "เพิ่งจบ" ของออฟฟิศ · ไฟล์: `ui.html`
  - การ์ด — ก่อน: `${fromClaudeHTML(r)}` → หลัง: `${fromClaudeHTML(r)}${qaLine(r)}${docLine(r)}`
  - เพิ่งจบ — ก่อน: `${denyNote(j)}</td><td class="nw">` → หลัง: `${denyNote(j)}${qaLine(j)}${docLine(j)}</td><td class="nw">`
  - ตัวจับคลิก — ก่อน: `if (e.target.closest("button[data-runnow],button[data-cancel],button[data-ofwhy],button[data-openclaude]")) return;` → หลัง: `if (e.target.closest("button:not([data-oflog])")) return;` (ปุ่มทุกตัวในออฟฟิศไม่พาไปดู log ยกเว้นปุ่ม "ดู log สด" ที่มี `data-oflog` เอง · ครอบปุ่ม doc/actBtns ของ T-06 ล่วงหน้า)
  - sig วาดใหม่ — ก่อน: `(state.history || []).slice(0, 8).map((h) => [h.id, h.state])` → หลัง: `(state.history || []).slice(0, 8).map((h) => [h.id, h.state, h.doc && h.doc.state])` · ก่อน: `m.runs.map((r) => [r.id, r.model, r.claude_title])` → หลัง: `m.runs.map((r) => [r.id, r.model, r.claude_title, r.doc && r.doc.phase, r.qa && (r.qa.specs || []).map((x) => x.verdict).join()])`
  - ตรวจลอจิก (8ค): สร้าง `.tmp/office_eval.py` · `.tmp/T-01.eval.js` ตั้ง `state = { history: [{ id: "d1", state: "ok", project_name: "p", kind: "doc", tasks: "docs", doc: { verdict: "DRAFT", state: "pending", changed: ["a.md"], n_changed: 1 } }] }` แล้ว `recentHTML()` ต้องมี `data-docacc="d1"` และ `รอคุณตัดสิน` · `runCardHTML({ id: "q1", kind: "qa", tasks: "unit", project_name: "p", qa: { specs: [{ name: "unit", verdict: "FAIL" }] } }, 0)` ต้องมี `unit FAIL`
  - ยืนยัน: 8ก + 8ข + 8ค · 8ง `docLine(` ก่อน 2 → หลัง 4 · `qaLine(` ก่อน 2 → หลัง 4
  - หลักฐานชี้ขาด: `.tmp/T-01.node.log` ว่าง · `.tmp/T-01.smoke.log` `UI_SMOKE OK` · `.tmp/T-01.eval.log` `EVAL=OK` · นับ `docLine(` = 4
  - commit: `ui: ออฟฟิศแสดงผลช่างเอกสาร (DRAFT · รอคุณตัดสิน · ปุ่มรับ/ทิ้งร่าง) และผลรายชุดของนักทดสอบ (T-01)`

- [x] **T-02** ยอด "วันนี้จบแล้ว" ไม่นับงานยกเลิก/BUSY/รอคิวเกิน · ไฟล์: `ui.html`
  - ต้องมี: `const todayDone = (hist, today) => …` วางก่อน `function recentHTML() {` → คืนแถวของ `hist || []` ที่ `(h.finished || "").startsWith(today)` และ `state` ไม่อยู่ใน `["cancelled", "busy", "queue_timeout"]` (comment สั้น: ตรงกับ job_stats ใน flashq.py)
  - ก่อน: `td = (s.history || []).filter((h) => (h.finished || "").startsWith(today));` → หลัง: `td = todayDone(s.history, today);`
  - ตรวจลอจิก (8ค): `todayDone([ok, cancelled, busy, queue_timeout, fail (finished "2026-11-04 10:00:00" ทุกแถว), ok (finished "2026-11-03 …")], "2026-11-04").length === 2` · `todayDone(null, "2026-11-04").length === 0`
  - ยืนยัน: 8ก + 8ข + 8ค · 8ง `queue_timeout` ก่อน 2 → หลัง ≥ 3
  - หลักฐานชี้ขาด: `.tmp/T-02.node.log` ว่าง · `.tmp/T-02.smoke.log` `UI_SMOKE OK` · `.tmp/T-02.eval.log` `EVAL=OK`
  - commit: `ui: ยอด "วันนี้จบแล้ว" ในออฟฟิศไม่นับงานที่ยกเลิก/BUSY/รอคิวเกิน ให้ตรงกับสถิติ (T-02)`

- [x] **T-03** การ์ดผู้สืบแสดงบรีฟ · ไฟล์: `ui.html` (`function runCardHTML`)
  - ก่อน: `r.message && !isSleuth(r) ? "ทดสอบ --message" : String(r.plan || "").split(/[\\/]/).pop());` → หลัง: `r.message && !isSleuth(r) ? "ทดสอบ --message" : isSleuth(r) && r.message ? trunc(r.message, 60) : String(r.plan || "").split(/[\\/]/).pop());`
  - ตรวจลอจิก (8ค): `runCardHTML({ id: "s1", kind: "investigate", agent: "flash-investigator", message: "หาต้นตอการ์ดว่าง", project_name: "p", tasks: "" }, 0)` ต้องมี `หาต้นตอการ์ดว่าง` · การ์ดงานปกติ `{ id: "w1", plan: "docs/plans/PLAN_X.md", tasks: "T-01", project_name: "p" }` ยังมี `PLAN_X.md`
  - ยืนยัน: 8ก + 8ค
  - หลักฐานชี้ขาด: `.tmp/T-03.node.log` ว่าง · `.tmp/T-03.eval.log` `EVAL=OK`
  - commit: `ui: การ์ดผู้สืบในออฟฟิศแสดงบรีฟ (ไม่ว่างอีก) (T-03)`

- [x] **T-04** ตัวตาม log ออฟฟิศอ่านรอบใหม่ตั้งแต่ต้นเมื่อ attempt เปลี่ยน · ไฟล์: `ui.html` (`async function officePoll`)
  - ก่อน: `if (d.reset || (L.attempt && d.attempt && d.attempt !== L.attempt)) { L.tools = 0; L.errs = 0; L.last = ""; L.mention = ""; L.done = new Set(); }`
  - หลัง (สเปก): แยกเป็น 2 กรณี — (1) `!d.reset && L.attempt && d.attempt && d.attempt !== L.attempt` → รีเซ็ตตัวนับชุดเดิม + `L.offset = 0; L.size = -1; L.attempt = d.attempt;` แล้ว `continue;` (ทิ้งบรรทัดที่อ่านจาก offset เก่า ให้รอบถัดไปของ `for k` อ่านใหม่จาก 0) · (2) `d.reset` → รีเซ็ตตัวนับเหมือนเดิม (ไม่ continue · พฤติกรรมเดิม) · **ห้ามแค่ใส่ `L.offset = 0` ในบล็อกเดิม** (บรรทัด `L.offset = d.offset;` ด้านล่างจะทับจนไม่มีผล)
  - ยืนยัน: 8ก · 8ง `L.offset = 0` ก่อน 0 → หลัง 1 · `continue;` อยู่ในลูป `for (let k = 0; k < 6; k++)` (Grep ‑A ดูให้เห็น)
  - หลักฐานชี้ขาด: `.tmp/T-04.node.log` ว่าง · ผลนับ `L.offset = 0` = 1 · ทดสอบสดไม่ได้ (ต้องมีงาน retry จริง) → เขียนในหลักฐานว่า "ตรวจจากโค้ด"
  - commit: `ui: การ์ดออฟฟิศอ่าน log รอบใหม่ตั้งแต่ต้นเมื่องานลองใหม่ (นับเครื่องมือไม่ขาด) (T-04)`

### กลุ่ม B — ใช้ง่ายขึ้น

- [x] **T-05** "วิธีอ่านภาพ" เหลือ 4 บรรทัดหลัก + พับเป็นค่าเริ่มต้น · ไฟล์: `ui.html`
  - ก่อน: `<section class="panel" id="ofLegendBox" data-panel="oflegend">` → หลัง: `<section class="panel collapsed" id="ofLegendBox" data-panel="oflegend">` (ผู้ที่เคยกางไว้ ค่าที่จำไว้ยังชนะ — กลไกเดิม)
  - จุดเสียบ: `<ul class="of-legend">` ใน `#ofLegendBox` · ใส่ `<li>` ใหม่ 4 บรรทัดนี้เป็นรายการแรก: `🧑‍💻 <b>โต๊ะ</b> = งานที่กำลังทำ (1 โต๊ะ = 1 ช่อง · โต๊ะว่าง = ยังไม่มีงาน)` · `🧍 <b>แถวซ้าย</b> = งานรอคิว (#1 = ถัดไป · ถือป้าย ⏸ = รอเพราะไฟล์ชน)` · `🛋 <b>โซฟา</b> = ผู้ช่วยที่ว่าง (ผู้ตรวจ · ผู้สืบ · ยาม · นักทดสอบ · ช่างเอกสาร)` · `🚩 <b>ธง</b> = เป้าหมาย (ธงสูงตามเกณฑ์ที่ผ่าน · ธงเหลือง 👀 = รอคุณตรวจ)`
  - ปิด `</ul>` หลัง 4 บรรทัดนั้น แล้วย้าย `<li>` เดิมทั้ง 15 บรรทัด (ตั้งแต่ `<li>🧑‍💻 <b>นั่งโต๊ะ</b>` ถึง `<li>⏱ ทุก <b>เวลาที่ประมาณ</b>`) **ไม่แก้ข้อความ** เข้า `<details class="of-legend-more"><summary>ศัพท์ละเอียด (สีเสื้อ · ผู้ตรวจ · ยาม · ท่าทาง ฯลฯ)</summary><ul class="of-legend">…</ul></details>` · `<p class="of-note">คลิกตัวละคร…` อยู่ท้ายเหมือนเดิม
  - ยืนยัน: 8ก + 8ข · 8ง `ศัพท์ละเอียด` ก่อน 0 → หลัง 1 · `<li>🧑‍💻 <b>นั่งโต๊ะ</b>` ยังเป็น 1
  - หลักฐานชี้ขาด: `.tmp/T-05.node.log` ว่าง · `.tmp/T-05.smoke.log` `UI_SMOKE OK` · ผลนับ 2 ค่า
  - commit: `ui: วิธีอ่านภาพออฟฟิศเหลือ 4 บรรทัดหลัก ที่เหลือพับใน "ศัพท์ละเอียด" และพับแผงเป็นค่าเริ่มต้น (T-05)`

- [x] **T-06** ตาราง "เพิ่งจบ" มีปุ่ม + หัวสรุป "รอคุณตรวจ N" · ไฟล์: `ui.html`
  - หัวตาราง — ก่อน: `<tr><th>สถานะ</th><th>โปรเจกต์ · งาน</th><th>ใช้เวลา</th></tr>` → หลัง: `<tr><th>สถานะ</th><th>โปรเจกต์ · งาน</th><th>ใช้เวลา</th><th></th></tr>`
  - ท้ายแถว — ก่อน: `${dur(j.duration_sec)}</td></tr>` → หลัง: `${dur(j.duration_sec)}</td><td class="act">${actBtns(j, { check: true })}</td></tr>` (เหมือนแดชบอร์ด · ตัวจับคลิกเดิมของ `data-cc`/`data-copy`/`data-retry` ระดับ document รองรับแล้ว · T-01 กันไม่ให้พาไป log แล้ว)
  - หัวแผง — ก่อน: `<section class="panel"><div class="ph"><h2>เพิ่งจบ</h2></div><div class="pb" id="ofRecent"></div></section>` → หลัง: `<section class="panel"><div class="ph"><h2>เพิ่งจบ <span class="muted" id="ofRecentHead"></span></h2></div><div class="pb" id="ofRecent"></div></section>`
  - ต้องมี: `const reviewWait = (hist, goals) => …` (วางก่อน `function recentHTML() {`) → จำนวน = แถวใน `(hist || []).slice(0, 8)` ที่ `state === "ok_unverified"` หรือ `doc && doc.state === "pending"` + `(goals || [])` ที่ `verdict === "DONE_NEEDS_USER"` · ใน `function officeUpdate` ต่อจากบรรทัด `setText("ofTDs", …` เพิ่ม `setText("ofRecentHead", n ? `· 👀 รอคุณตรวจ ${n}` : "")` (n = `reviewWait(s.history, m.goals)`)
  - ตรวจลอจิก (8ค): `reviewWait([{state:"ok_unverified"},{state:"ok",doc:{state:"pending"}},{state:"ok"}], [{verdict:"DONE_NEEDS_USER"},{verdict:"DONE"}]) === 3` · `reviewWait(null, null) === 0` · `state = { history: [{ id: "h1", state: "ok", project_name: "p", plan: "x.md" }] }; recentHTML()` มี `data-cc="h1"`
  - ยืนยัน: 8ก + 8ข + 8ค · 8ง `ofRecentHead` ก่อน 0 → หลัง ≥ 2
  - หลักฐานชี้ขาด: `.tmp/T-06.node.log` ว่าง · `.tmp/T-06.smoke.log` `UI_SMOKE OK` · `.tmp/T-06.eval.log` `EVAL=OK`
  - commit: `ui: ตาราง "เพิ่งจบ" ในออฟฟิศมีปุ่มเปิด Claude/คัดลอก/สั่งซ้ำ และหัวสรุป "รอคุณตรวจ" (T-06)`

- [x] **T-07** ป้ายบทบาทที่หัวการ์ดงาน · ไฟล์: `ui.html`
  - ต้องมี: `const roleName = (j) => …` วางต่อจากบรรทัด `const roleTag = (j) =>` → `isDoc` = `"📝 ช่างเอกสาร"` · `isQa` = `"🧪 นักทดสอบ"` · `isSleuth(j) || kindOf(j) === "investigate"` = `"🕵️ ผู้สืบ"` · `isVerify` = `"🔍 ผู้ตรวจ"` · อื่น ๆ = `"🧑‍💻 ช่างโค้ด"` (เช็กตามลำดับนี้)
  - ก่อน: `<b>ช่อง ${r.slot || k + 1}</b>` → หลัง: `<b>ช่อง ${r.slot || k + 1}</b><span class="of-role">${esc(roleName(r))}</span>` · CSS `.of-role` 1 บรรทัด (ชิปเล็ก ขอบบาง ไม่ใช้สีเสื้อ) วางต่อจากบรรทัด `.of-mini { display: none; }`
  - **ไม่แตะ** บรรทัด `const plan = …` (ป้าย roleTag เดิมหน้าแผนของงานตรวจยังอยู่ — ซ้ำได้ ตั้งใจ)
  - ตรวจลอจิก (8ค): `roleName({kind:"doc"})` มี `ช่างเอกสาร` · `roleName({kind:"qa"})` มี `นักทดสอบ` · `roleName({kind:"investigate"})` มี `ผู้สืบ` · `roleName({kind:"verify"})` มี `ผู้ตรวจ` · `roleName({plan:"a.md"})` มี `ช่างโค้ด` · `runCardHTML({id:"w1",plan:"a.md",tasks:"T-01",project_name:"p"},0)` มี `of-role`
  - ยืนยัน: 8ก + 8ข + 8ค · 8ง `ช่างโค้ด` ก่อน 0 → หลัง ≥ 1
  - หลักฐานชี้ขาด: `.tmp/T-07.node.log` ว่าง · `.tmp/T-07.smoke.log` `UI_SMOKE OK` · `.tmp/T-07.eval.log` `EVAL=OK`
  - commit: `ui: การ์ดงานในออฟฟิศบอกบทบาท (ช่างโค้ด · ผู้ตรวจ · ผู้สืบ · นักทดสอบ · ช่างเอกสาร) (T-07)`

- [x] **T-08** ปุ่ม "🏢 กลับออฟฟิศ" ในแถบ log · ไฟล์: `ui.html`
  - ก่อน: `<button id="logClose" title="ปิด log">ปิด</button>` → หลัง: `<button id="logBackOffice" title="กลับไปหน้าออฟฟิศ (log นี้เปิดจากออฟฟิศ)" hidden>🏢 กลับออฟฟิศ</button><button id="logClose" title="ปิด log">ปิด</button>`
  - ก่อน: `function openLog(id) {` → หลัง: `function openLog(id) {` + บรรทัดถัดไป `$("logBackOffice").hidden = true;` (เปิด log จากที่อื่น = ซ่อน)
  - ก่อน: `function openLogFromOffice(id) { setView("dash"); openLog(id); }` → หลัง: `function openLogFromOffice(id) { setView("dash"); openLog(id); $("logBackOffice").hidden = false; }` + บรรทัดถัดไป `$("logBackOffice").onclick = () => { $("logBackOffice").hidden = true; setView("office"); };`
  - ใน `$("logClose").onclick = () => {` ใส่ `$("logBackOffice").hidden = true;` เป็นคำสั่งแรกในบล็อก
  - ตรวจลอจิก (8ค): `openLogFromOffice("x")` แล้ว `$("logBackOffice").hidden === false` · กด `$("logBackOffice").click()` แล้ว `view === "office"` และปุ่ม hidden · `openLog("y")` แล้วปุ่ม hidden (fetch ล้มได้ ไม่เป็นไร · ห่อ try/catch)
  - ยืนยัน: 8ก + 8ข + 8ค · 8ง `logBackOffice` ก่อน 0 → หลัง ≥ 6
  - หลักฐานชี้ขาด: `.tmp/T-08.node.log` ว่าง · `.tmp/T-08.smoke.log` `UI_SMOKE OK` · `.tmp/T-08.eval.log` `EVAL=OK`
  - commit: `ui: เปิด log จากออฟฟิศแล้วมีปุ่ม "🏢 กลับออฟฟิศ" ในแถบ log (T-08)`

- [x] **T-09** รายละเอียดเทคนิคของการ์ดงานพับใน `<details>` · ไฟล์: `ui.html` (`function runCardHTML`)
  - คงไว้นอก details: แถบ `ofCB` · `ofCX` · บรรทัด `ofCP`/`ofCS` · บรรทัด `🛠 ofCT` · บรรทัด `⏱ ofCE`
  - ย้ายเข้า details (**ข้อความ/id เดิมทุกตัว ห้ามเปลี่ยน**): บรรทัด `<div class="of-full">${modelChip(r)}${thinkChip(r)}</div>` · `ofCM${k}` · `ofCA${k}` · `ofCG${k}` · บรรทัดปุ่ม `🔍 ตรวจสาเหตุ` (`ofCW${k}`) — ห่อด้วย `<details class="of-more of-full" data-more="${esc(r.id)}"${ofMoreOpen.has(r.id) ? " open" : ""}><summary class="muted" id="ofCD${k}">รายละเอียดทางเทคนิค</summary>…</details>` (คลาส `of-full` = โหมด ▤ ย่อซ่อนทั้งก้อนตามเดิม)
  - ต้องมี: `const ofMoreOpen = new Set();` ระดับบนสุด (ก่อน `function runCardHTML`) + ตัวจับ `$("ofRuns").addEventListener("toggle", (e) => { const d = e.target; if (d.dataset && d.dataset.more) d.open ? ofMoreOpen.add(d.dataset.more) : ofMoreOpen.delete(d.dataset.more); }, true);` (การ์ดถูกสร้างใหม่ทุกครั้งที่ sig เปลี่ยน → จำว่ากางไว้)
  - เตือนไม่หาย — ก่อน: `const ca = $("ofCA" + k); if (ca) ca.classList.toggle("of-warn", !!quiet);` → หลัง: `const ca = $("ofCA" + k); if (ca) ca.classList.toggle("of-warn", !!quiet); const cd = $("ofCD" + k); if (cd) cd.classList.toggle("of-warn", !!quiet);`
  - ตรวจลอจิก (8ค): `runCardHTML({id:"w1",plan:"a.md",tasks:"T-01",project_name:"p"},0)` มี `<details class="of-more of-full"` และมีครบ `id="ofCA0"` `id="ofCG0"` `id="ofCM0"` `id="ofCW0"` `id="ofCT0"` · `ofCT0` อยู่ก่อน `<details` (indexOf)
  - ยืนยัน: 8ก + 8ข + 8ค · 8ง `of-more` ก่อน 0 → หลัง ≥ 1
  - หลักฐานชี้ขาด: `.tmp/T-09.node.log` ว่าง · `.tmp/T-09.smoke.log` `UI_SMOKE OK` · `.tmp/T-09.eval.log` `EVAL=OK`
  - commit: `ui: การ์ดงานในออฟฟิศพับรายละเอียดทางเทคนิคไว้ (เตือนยังเห็นที่หัวพับ) (T-09)`

### กลุ่ม C — แผงหัวหน้า · ใบสั่งงาน

- [x] **T-10** แผง "👔 หัวหน้า · ใบสั่งงาน" · ไฟล์: `ui.html` (ฟีเจอร์ใหม่ — สเปก)
  - จุดเสียบ HTML: แทรกก่อน `<div class="of-runs-bar" id="ofRunsBar" hidden>` → `<section class="panel" id="ofBossBox" hidden data-panel="ofboss">` หัว `<h2>👔 หัวหน้า · ใบสั่งงาน <span class="muted" id="ofBossN"></span></h2>` + `<span class="sp"></span><button class="ico" data-collapse title="พับ/กาง">▾</button>` (แบบเดียวกับ `#ofGoalBox`) + `<div class="pb" id="ofBoss"></div>`
  - ต้องมี (วางก่อน `function recentHTML() {`):
    - `bossGroups(runs, queue, goals)` → `[{ key, name, items: [{ id, role, what, st }] }]` · งาน: `key = j.claude_session || "solo:" + (j.project_name || "-")` · `role = roleName(j)` (T-07) · `what = shortWhat(j)` · `st` = runs → `"ทำ"` · queue → `"รอ"` · เป้าหมาย (`goals` ที่ `verdict` ไม่ใช่ `DONE`/`STOP`/`CANCELLED`): `key = (g.owner && g.owner.session) || "solo:" + (g.project_name || "-")` · `role = "🚩 เป้าหมาย"` · `what = trunc(g.title || g.goal || "-", 40)` · `st = verdict === "DONE_NEEDS_USER" ? "รอตรวจ" : "ทำ"` · `id` ของเป้าหมาย = `""`
    - `name` ของกลุ่ม = `claude_title` (งาน) หรือ `owner.title` (เป้าหมาย) ตัวแรกที่ไม่ว่าง → `trunc(…, 50)` · ไม่มีเลย = `"ไม่ทราบผู้สั่ง"` (กลุ่ม solo ต่อท้าย ` · ` + ชื่อโปรเจกต์) · ลำดับกลุ่ม = ตามที่เจอครั้งแรก (runs → queue → goals) · ทุกพารามิเตอร์รับ `null` ได้
    - `bossHTML(groups)` → `""` เมื่อว่าง · แต่ละกลุ่ม `<div class="of-boss"><b>👔 ชื่อ</b> <span class="muted">· N งาน</span><ul>` แต่ละรายการ `<li>` = role + what + ป้ายสถานะ (`ทำ`/`รอ`/`รอตรวจ`) · รายการที่มี `id` ใส่ `class="click" data-oflog="id"` (คลิกไปดู log — ตัวจับคลิกเดิมรองรับ) · ทุกข้อความผ่าน `esc` · CSS `.of-boss` ≤ 3 บรรทัดต่อจาก `.of-role`
  - เรนเดอร์: ก่อน: `$("ofRecent").innerHTML = recentHTML();` → หลัง: บรรทัดเดิม + `const bg = bossGroups(m.runs, m.queue, m.goals); $("ofBossBox").hidden = !bg.length; setText("ofBossN", bg.length ? `${bg.length} คนสั่ง` : ""); setHTML("ofBoss", bossHTML(bg));`
  - sig — ก่อน: `state.current_model, (state.accounts || []).length]);` → หลัง: `state.current_model, (state.accounts || []).length, m.runs.concat(m.queue).map((j) => [j.claude_session, j.kind, j.agent]), m.goals.map((x) => [x.id, x.owner && x.owner.session, x.owner && x.owner.title, x.title])]);`
  - ตรวจลอจิก (8ค): `bossGroups(null, null, null).length === 0` และ `bossHTML([]) === ""` · `bossGroups([{id:"a",claude_session:"s1",claude_title:"งานหน้าเว็บ",project_name:"p",plan:"x.md",tasks:"T-01"}], [{id:"b",claude_session:"s1",project_name:"p",kind:"qa",tasks:"ui"},{id:"c",claude_session:null,claude_title:null,project_name:null}], [{id:"g",verdict:"DONE_NEEDS_USER",owner:null,project_name:"p",title:"ธง"}])` → **3 กลุ่มตามลำดับ**: (1) key `s1` name `งานหน้าเว็บ` 2 รายการ st `ทำ`,`รอ` (2) key `solo:-` (งาน c) name มี `ไม่ทราบผู้สั่ง` (3) key `solo:p` (เป้าหมาย g) st `รอตรวจ` · `bossHTML(...)` มี `ไม่ทราบผู้สั่ง` · `รอตรวจ` · `data-oflog="a"` · ไม่ throw
  - ยืนยัน: 8ก + 8ข + 8ค · 8ง `ofBoss` ก่อน 0 → หลัง ≥ 4
  - หลักฐานชี้ขาด: `.tmp/T-10.node.log` ว่าง · `.tmp/T-10.smoke.log` `UI_SMOKE OK` · `.tmp/T-10.eval.log` `EVAL=OK`
  - commit: `ui: ออฟฟิศมีแผง "👔 หัวหน้า · ใบสั่งงาน" จัดกลุ่มงานตาม session ที่สั่ง พร้อมบทบาทและสถานะ (T-10)`

### กลุ่ม D — เอกสาร

- [x] **T-11** เอกสารให้ตรง · ไฟล์: `docs/REFERENCE.md` `CHANGELOG.md`
  - `docs/REFERENCE.md`: ใต้ bullet `**แท็บ 🏢 ออฟฟิศ**` (ส่วนย่อยที่มี `การ์ดต่องาน:` และ `คลิกตัวละคร/การ์ด/แถวคิว`) เพิ่ม/แก้ bullet ย่อยไทยสั้น ๆ: (1) แผง 👔 หัวหน้า · ใบสั่งงาน (จัดกลุ่มตาม session Claude ที่สั่ง · ไม่มี = ไม่ทราบผู้สั่ง · บทบาท+สถานะ ทำ/รอ/รอตรวจ · ไม่มีงาน = ซ่อน) (2) ป้ายบทบาทบนการ์ด + รายละเอียดทางเทคนิคพับไว้ (หัวพับเปลี่ยนสีเมื่อ log เงียบ) (3) "เพิ่งจบ" มีปุ่ม เปิด Claude/คัดลอก/สั่งซ้ำ + ผลช่างเอกสาร/นักทดสอบ + หัวสรุป 👀 รอคุณตรวจ N (4) เปิด log จากออฟฟิศมีปุ่ม 🏢 กลับออฟฟิศ (5) "วันนี้จบแล้ว" ไม่นับยกเลิก/BUSY/รอคิวเกิน (6) วิธีอ่านภาพ 4 บรรทัด + ศัพท์ละเอียดพับไว้ · แก้ bullet `คลิกตัวละคร/การ์ด/แถวคิว` ให้บอกเรื่องปุ่มกลับ
  - `CHANGELOG.md`: เพิ่ม bullet **ใต้หัวข้อ `## 2026-11-04` ที่มีอยู่แล้ว** (ห้ามสร้างหัวข้อซ้ำ · วางเป็น bullet แรก) — `**ออฟฟิศใช้ง่ายขึ้น + แผงหัวหน้า**: …` สรุป T-01..T-10 ในบรรทัดเดียว (รูปแบบเดียวกับ bullet เดิม อ้าง T-xx)
  - ยืนยัน: 8ข (หน้าเว็บยังโหลดได้หลังทุกงาน) · 8ง บน `docs/REFERENCE.md`: `หัวหน้า · ใบสั่งงาน` ก่อน 0 → หลัง ≥ 1 · บน `CHANGELOG.md`: `## 2026-11-04` = 1 และ `ออฟฟิศใช้ง่ายขึ้น` ≥ 1
  - หลักฐานชี้ขาด: `.tmp/T-11.smoke.log` `UI_SMOKE OK` · ผลนับ 3 ค่า
  - commit: `ui: เอกสารออฟฟิศ (แผงหัวหน้า · ป้ายบทบาท · ปุ่มเพิ่งจบ · กลับออฟฟิศ) + CHANGELOG (T-11)`

## 2. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- -

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
| T-01 | ✅แก้ | 9fdf194 | `.tmp/T-01.node.log` ว่าง · `.tmp/T-01.smoke.log` `UI_SMOKE OK` · `.tmp/T-01.eval.log` `EVAL=OK` · นับ `docLine(` = 4 · `qaLine(` = 4 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-02 | ✅แก้ | b190641 | `.tmp/T-02.node.log` ว่าง · `.tmp/T-02.smoke.log` `UI_SMOKE OK` · `.tmp/T-02.eval.log` `EVAL=OK` · นับ `queue_timeout` = 3 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-03 | ✅แก้ | 265b1bb | `.tmp/T-03.node.log` ว่าง · `.tmp/T-03.eval.log` `EVAL=OK` (มี `หาต้นตอการ์ดว่าง` · ยังมี `PLAN_X.md`) |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-04 | ✅แก้ | c7caa90 | `.tmp/T-04.node.log` ว่าง · นับ `L.offset = 0` = 1 · `continue;` อยู่ในลูป `for (let k = 0; k < 6; k++)` — ตรวจจากโค้ด (ทดสอบสดไม่ได้) |  ✅ผ่าน (ตรวจจากโค้ด: รีเซ็ต offset จริง · ทดสอบสดไม่ได้) |
| T-05 | ✅แก้ | 08ae9ec | `.tmp/T-05.node.log` ว่าง · `.tmp/T-05.smoke.log` `UI_SMOKE OK` · นับ `ศัพท์ละเอียด` = 1 · `<li>🧑‍💻 <b>นั่งโต๊ะ</b>` = 1 (หมายเหตุ: `Select-String -SimpleMatch` บน PowerShell 5.1 ให้ `.Matches.Count` = 0 เสมอ — worker นับด้วย regex แทน) |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-06 | ✅แก้ | a8186ab | `.tmp/T-06.node.log` ว่าง · `.tmp/T-06.smoke.log` `UI_SMOKE OK` · `.tmp/T-06.eval.log` `EVAL=OK` · นับ `ofRecentHead` = 2 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-07 | ✅แก้ | ee38d27 | `.tmp/T-07.node.log` ว่าง · `.tmp/T-07.smoke.log` `UI_SMOKE OK` · `.tmp/T-07.eval.log` `EVAL=OK` · นับ `ช่างโค้ด` = 2 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-08 | ✅แก้ | c994259 | `.tmp/T-08.node.log` ว่าง · `.tmp/T-08.smoke.log` `UI_SMOKE OK` · `.tmp/T-08.eval.log` `EVAL=OK` · นับ `logBackOffice` = 6 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-09 | ✅แก้ | 9a06609 | `.tmp/T-09.node.log` ว่าง · `.tmp/T-09.smoke.log` `UI_SMOKE OK` · `.tmp/T-09.eval.log` `EVAL=OK` · นับ `of-more` = 1 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-10 | ✅แก้ | e2a7169 | `.tmp/T-10.node.log` ว่าง · `.tmp/T-10.smoke.log` `UI_SMOKE OK` · `.tmp/T-10.eval.log` `EVAL=OK` · นับ `ofBoss` = 7 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |
| T-11 | ✅แก้ | 90cb282 | `.tmp/T-11.smoke.log` `UI_SMOKE OK` · `docs/REFERENCE.md` `หัวหน้า · ใบสั่งงาน` = 1 · `CHANGELOG.md` `## 2026-11-04` = 1 · `ออฟฟิศใช้ง่ายขึ้น` = 1 |  ✅ผ่าน (ตรวจ commit/ไฟล์ที่แตะ/เวลา log/ข้อความหลักใน diff) |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- ผู้สืบเสนอเพิ่ม: คีย์สีเสื้อ = โปรเจกต์ (`ofProjKey`) · คำอธิบาย "ช่อง/คิว" ใต้ tile + เปลี่ยนชื่อ tile ประหยัด · ปุ่ม "ดูทั้งหมด" ในแผงเพิ่งจบ · ตัวหัวหน้าในฉาก SVG — ยังไม่สั่งรอบนี้
- `FINAL` ไม่มี `cancelled`/`queue_timeout`/`busy` (อาจตั้งใจ · ถ้าเพิ่มต้องเพิ่ม `CELE` ด้วย ไม่งั้น `deskSVG` TypeError) · `role="img"` บน SVG ฉากทำให้ปุ่มข้างในอาจไม่ถูกอ่านโดย screen reader · `officeLog`/`deskOf`/`cele` ไม่ล้าง — ยังไม่ยืนยันว่าเป็นบั๊ก

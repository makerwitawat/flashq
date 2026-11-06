# แผน NO_STICKY_SWITCH — เลิกเขียนทับ opencode.json ตอนสลับบัญชีอัตโนมัติ — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-06 · ส่งงาน: `python D:/MyCode/flashq/flashq.py run docs/plans/PLAN_FLASH_NO_STICKY_SWITCH.md T-01..T-03 --switch-on-quota 4` · base commit ตอนวางแผน: `97198b5`

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, ui.html, tests/test_flashq.py, docs/REFERENCE.md, CHANGELOG.md
flashq-parallel: yes

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- <ไฟล์ของงาน>` + `git commit -m "<ข้อความในงาน>"`) · **ห้าม push** · ห้าม `git add -A` / `git add .`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment/แปลง encoding · ไม่เพิ่ม dependency (stdlib ล้วน)
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "ก่อน" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนไว้ตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด · ตั้ง `PYTHONIOENCODING=utf-8` เมื่อรันจาก bash
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · **หลักฐานชี้ขาด = path log/ไฟล์ผล + บรรทัด/ค่าที่แผนกำหนด ตรงตัว**) · หลักฐานไม่ครบ = งานไม่จบ
6. **ห้ามแตะ**: `%USERPROFILE%\.flashq\` (อ่านอย่างเดียว) · `~/.config/opencode/opencode.json` จริง · `accounts.json` · ไฟล์ใน `claude/` `opencode/` `hooks/`
7. **งานแบบ "เทสต์ก่อน"** (`แบบ: เทสต์ก่อน`): เขียนเทสต์ → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (เก็บ log "แดง") → แก้โค้ด → รันซ้ำต้อง PASS (เก็บ log "เขียว") → commit เดียว · ผ่านตั้งแต่ก่อนแก้/ล้มด้วยเหตุอื่น → **⛔ หยุด** · ห้ามแก้เทสต์ให้ผ่านแทนการแก้โค้ด
8. **ห้ามรายงานด้วยคำเดา** ("น่าจะผ่าน" "ข้ามไปก่อน") = งานยังไม่จบ · ไม่ได้รันจริง = เขียน "ไม่ได้รัน"
9. ไฟล์ชั่วคราวไว้ที่ `.tmp/` เท่านั้น

### คำสั่งมาตรฐาน
```
python -m pytest tests/test_flashq.py -q -x -k "quota or switch"
node --check .tmp/ui_script.js
```

---

## 1. กลุ่ม A — สลับบัญชีอัตโนมัติไม่เขียน opencode.json
**สาเหตุ/หลักฐาน** (ผู้สืบ + Claude เปิดโค้ดยืนยันแล้ว): `flashq.py:2629-2642` เมื่องาน worker เจอ QUOTA เรียก `switch_account("next")` (`flashq.py:4851-4881`) ซึ่งเขียน `agent.flash-worker.model` ลง `opencode.json` ถาวรและไม่มีโค้ดคืนค่าเดิม → โมเดลที่ผู้ใช้ตั้งไว้ถูกแทนที่ตลอดไป (หน้าเว็บเลยเห็น "ใช้อยู่" = go2 ทั้งที่แถวแรกคือ cc)
**ทิศทาง**: ให้ auto-switch เปลี่ยนแค่ `job["model"]` (ส่งเป็น `--model` รอบถัดไป — โค้ดเดิม `flashq.py:2591` ทำอยู่แล้ว) ไม่แตะ `opencode.json` · `flashq switch` / `/api/switch` ที่ผู้ใช้สั่งเองยังเขียนตามเดิม (`switch_account` ห้ามเปลี่ยนพฤติกรรม)

- [x] **T-01** `tests/test_flashq.py` ~684 (`test_quota_switch`) ~2005 (`test_quota_no_double_switch`) + `flashq.py` ~2629-2642 · แบบ: เทสต์ก่อน
  - เทสต์: ปรับ `test_quota_switch` ให้ตรวจพฤติกรรมใหม่: รันด้วย `FAKE_MODE=quota` + `--switch-on-quota 1` แล้ว (ก) stdout ยังมี "FLASH_RUN=QUOTA" และข้อความ "สลับบัญชี" (ข) **`opencode.json` ยังเป็นโมเดลเดิมก่อนรัน ไม่เปลี่ยน** (ค) args ที่ opencode ปลอมได้รับมี 2 รอบ และ `--model` ของรอบที่ 2 เป็นบัญชีถัดไปตามลำดับ `accounts.json` (คือ `commandcode/deepseek/deepseek-v4.1-flash` ตามที่เทสต์เดิมคาด) · `test_quota_no_double_switch` เดิมทดสอบกลไก "งานอื่นสลับไปแล้ว" ซึ่งไม่มีอีกแล้ว → **ลบเทสต์นี้** และแทนด้วยเทสต์ใหม่ `test_quota_switch_does_not_touch_config` ที่ตรวจว่าหลังรันที่มี QUOTA `opencode.json` ไม่ถูกเขียนใหม่เลย (เทียบเนื้อไฟล์ก่อน/หลัง) และไม่เกิดไฟล์ `opencode.json.bak-flash-switch`
  - แดง (ก่อนแก้โค้ด): `python -m pytest tests/test_flashq.py -q -x -k "test_quota_switch" > .tmp/T-01.red.log` → ต้อง FAIL ที่การตรวจว่า config ไม่เปลี่ยน (ค่าใน config กลายเป็น `commandcode/deepseek/deepseek-v4.1-flash` แทนค่าเดิม)
  - แก้ (สเปก) ที่ `flashq.py` บล็อก `if res["status"] == "QUOTA" and not a.model and worker_like and switches < a.switch_on_quota:` (หาด้วย Grep ข้อความนี้):
    - เพิ่มฟังก์ชัน `next_account_model(current: str) -> str` ใกล้ `switch_account` — อ่าน `accounts()` แล้วคืนโมเดลถัดไปต่อจาก `current` (วนรอบ · ไม่เจอ `current` = ตัวแรก) · **ไม่เขียนไฟล์ใด ๆ** · รายการว่าง = คืน ""
    - ในบล็อก QUOTA ของ worker: เลิกใช้ `file_lock`/`configured_model()`/`switch_account("next")` · ใช้ `new = next_account_model(job["model"] or configured_model())` · ถ้า `new` ไม่ว่างและไม่เท่า `job["model"]` → `switches += 1` (ย้ายไปก่อนเรียกก็ได้ แต่ต้องนับ 1 ครั้งต่อการสลับจริง) พิมพ์ `QUOTA → สลับบัญชีเป็น {new} (เฉพาะงานนี้ · ไม่แก้ opencode.json) แล้วสั่งงานเดิมซ้ำ (ครั้งที่ {switches})` · ตั้ง `job["model"] = new` + `save_job(job)` แล้ว `continue`
    - ห้ามเปลี่ยน `switch_account` / `cmd_switch` / `/api/switch` · ห้ามแตะบล็อกของผู้ตรวจ/ผู้สืบ (`worker_like` เท็จ) และ `flashq.py:4073`
    - จุดอื่นที่เคยพึ่ง `import file_lock` เฉพาะบล็อกนี้ถ้าไม่ใช้แล้วให้คงไว้ (อย่าลบ import/ฟังก์ชันที่ใช้ที่อื่น)
  - เขียว: `python -m pytest tests/test_flashq.py -q -x -k "quota or switch" > .tmp/T-01.green.log` → PASS ทั้งหมด (รวมเทสต์ `test_switch_cli` และ `test_switch_account_empty_list_and_file_lock` ที่ต้องไม่พัง)
  - หลักฐานชี้ขาด: `แดง .tmp/T-01.red.log บรรทัด FAILED ... test_quota_switch · เขียว .tmp/T-01.green.log บรรทัด "passed"` ไม่มี "failed"
  - commit: `flashq: สลับบัญชีตอนโควตาหมดเฉพาะงานนั้น ไม่เขียนทับ opencode.json (T-01)`

## 2. กลุ่ม B — หน้าเว็บ

- [x] **T-02** `ui.html` ~522 (`switchNext`) ~2819 (ข้อความ `wz-hint`) ~2912 (`$("switchNext").onclick`) · แบบ: สเปก
  - **ความจริงที่ต้องสื่อ**: "ใช้อยู่" = ค่า `agent.flash-worker.model` ใน `opencode.json` (ไม่ใช่แถวแรกของรายการ) · ลำดับในรายการ = ลำดับสลับตอนโควตาหมด
  - จุดเสียบ: ปุ่ม `<button id="switchNext" class="primary">สลับไปบัญชีถัดไป</button>` ในแถวเดียวกัน · `$("switchNext").onclick = async () => { const d = await post("/api/switch", { target: "next" }); ...` · ข้อความ `· ลำดับ = ลำดับสลับตอนโควตาหมด` ใน `wzRender` · ป้าย `<span class="wz-tag ok">ใช้อยู่</span>`
  - ต้องมี: (1) ปุ่มใหม่ `id="switchFirst"` ข้อความ "ใช้บัญชีแรก" ข้างปุ่มเดิม · กดแล้ว `post("/api/switch", { target: state.accounts[0].short })` (มีรายการแล้วเท่านั้น · ว่าง = แจ้ง toast "ไม่มีรายการบัญชี") แล้ว toast `d.message || d.error || "ผิดพลาด"` + `refresh()` เหมือนปุ่มเดิม · ใช้ `post` ตัวเดิม (token/Origin มีอยู่แล้ว ห้ามเพิ่ม endpoint) (2) ป้าย "ใช้อยู่" ใส่ `title="ค่าใน opencode.json (ไม่ใช่แถวแรกเสมอไป)"` (3) ท้ายข้อความ `wz-hint` เพิ่มสั้น ๆ ว่า " · ป้าย "ใช้อยู่" = ค่าใน opencode.json" (4) ปุ่ม "ใช้บัญชีแรก" ปิดใช้ (disabled) เมื่อบัญชีแรกคือ `state.current_model` อยู่แล้ว — ในหน้าหลักอัปเดตสถานะใน render เดียวกับที่ใส่ `#curModel` (หา `$("curModel").textContent = ` ด้วย Grep)
  - ห้าม: โหลดอะไรจากเน็ต · เปลี่ยน API/โค้ดฝั่ง server · แก้ข้อความอื่น
  - ยืนยัน: ดึง `<script>` ออกเป็น `.tmp/ui_script.js` (สคริปต์เล็กใน `.tmp/` ที่ regex เอาข้อความระหว่าง `<script>` กับ `</script>` ที่ยาวที่สุดจาก ui.html) แล้ว `node --check .tmp/ui_script.js > .tmp/T-02.node.log` → ไม่มี error · แล้ว `python tests/ui_smoke.py > .tmp/T-02.smoke.log` → ต้องมี `UI_SMOKE OK` (exit 3 = ไม่มีเบราว์เซอร์ → จดว่า "ไม่ได้รัน" ไม่ถือว่าผ่าน)
  - หลักฐานชี้ขาด: `.tmp/T-02.node.log` ว่าง (exit 0) · `.tmp/T-02.smoke.log` บรรทัด `UI_SMOKE OK` (หรือ "ไม่ได้รัน เพราะ exit 3") · `git diff --stat` แตะ `ui.html` ไฟล์เดียว
  - commit: `ui: ป้าย "ใช้อยู่" อธิบายชัด + ปุ่ม "ใช้บัญชีแรก" (T-02)`

## 3. กลุ่ม C — เอกสาร

- [x] **T-03** `docs/REFERENCE.md` ~16 + `CHANGELOG.md` บนสุด · แบบ: สเปก
  - จุดเสียบ: บรรทัดใน REFERENCE ที่ขึ้นต้น `- ระหว่างรันหลายงาน \`--switch-on-quota\` จะ **ไม่สลับบัญชีซ้ำ**` · ส่วนหัว `## 2026-11-06` ใน CHANGELOG
  - ต้องมี: (1) แทนบรรทัด REFERENCE นั้นด้วยคำอธิบายใหม่: โควตาหมด → ผู้ทำสลับไปบัญชีถัดไปตาม `accounts.json` **เฉพาะงานนั้น (ส่ง `--model` รอบถัดไป) ไม่แก้ `opencode.json`** · งานถัดไปเริ่มจากโมเดลใน `opencode.json` ตามเดิม (ถ้าบัญชีนั้นโควตาหมดอยู่ก็จะสลับอีกรอบ) · `flashq switch` / ปุ่มในหน้าเว็บยังเขียน `opencode.json` ตามที่ผู้ใช้สั่ง · ปุ่ม "ใช้บัญชีแรก" (2) แก้บรรทัด REFERENCE ~130 ที่พูดว่า "ไม่แก้ `opencode.json` ต่างจากผู้ทำที่สลับบัญชีกลาง" ให้ตรงของใหม่ (ผู้ทำก็ไม่แก้แล้ว) (3) CHANGELOG เพิ่มบูลเล็ต 1 บรรทัดใต้ `## 2026-11-06` ด้านบนสุด ตามรูปแบบเดิม (ตัวหนาหัวข้อ + คำอธิบาย) ว่าแก้บั๊ก: สลับบัญชีอัตโนมัติเคยเขียนทับค่าโมเดลของผู้ใช้ถาวร · ไม่แตะ `README.md` (ไม่มีข้อความที่ขัด)
  - ยืนยัน: `python -c "import pathlib;t=pathlib.Path('docs/REFERENCE.md').read_text(encoding='utf-8');print('ไม่สลับบัญชีซ้ำ' in t)" > .tmp/T-03.log` → `False`
  - หลักฐานชี้ขาด: `.tmp/T-03.log` บรรทัด `False` · `git diff --stat` แตะ `docs/REFERENCE.md` + `CHANGELOG.md` เท่านั้น
  - commit: `flashq: เอกสาร+CHANGELOG — สลับบัญชีอัตโนมัติไม่แก้ opencode.json (T-03)`

## 2. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- ผลข้างเคียงของแผนนี้: งานถัดไปเริ่มที่บัญชีใน `opencode.json` เสมอ ถ้าบัญชีนั้นโควตาหมดอยู่จะเสียหนึ่งรอบสั่งก่อนสลับ (ก่อนหน้านี้ค่าค้างไปบัญชีที่ใช้ได้) — ถ้าอยากให้ "จำบัญชีที่ใช้ได้ล่าสุด" แยกจากค่าที่ผู้ใช้ตั้ง ต้องออกแบบแผนรอบใหม่

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|
| T-01 | ✅แก้ (หมายเหตุ: commit แตะไฟล์แผนเพิ่มด้วยนอกเหนือ tests/flashq.py) | 0a0f88d | แดง `.tmp/T-01.red.log` → `FAILED tests/test_flashq.py::FlashqTest::test_quota_switch` (config กลายเป็น `commandcode/deepseek/deepseek-v4.1-flash`) · เขียว `.tmp/T-01.green.log` → `8 passed, 213 deselected` (ไม่มี failed) | |
| T-02 | ✅แก้ | 8700409 | `.tmp/T-02.node.log` ว่าง (0 ไบต์ · node exit 0) · `.tmp/T-02.smoke.log` → `UI_SMOKE OK` · `git show --stat` = `ui.html | 12 +++++++++---` ไฟล์เดียว | |
| T-03 | ✅แก้ | 578a900 | `.tmp/T-03.log` → `False` · `git diff --stat` ก่อน commit = `CHANGELOG.md \| 1 +` · `docs/REFERENCE.md \| 4 ++--` (เฉพาะ 2 ไฟล์นี้) | |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- **แยก 429 "overloaded" ออกจาก QUOTA** (`QUOTA_RE` ที่ `flashq.py:97`, ตัดสินที่ ~1977) — ตัดออกจากแผนนี้: เมื่อ T-01 ไม่เขียน `opencode.json` แล้ว การนับ 429 เป็น QUOTA ไม่ทำให้ค่าผู้ใช้ถูกเขียนทับอีก (ผู้ตรวจ/ผู้สืบย้าย provider เฉพาะรอบอยู่แล้ว) · การเปลี่ยนจะทำให้ 429 กลายเป็น FAIL ไม่ retry ซึ่งแย่กว่าเดิม · ยังไม่ได้ตรวจโค้ดจุดนั้นเองจึงไม่ยืนยัน
- ใครสั่งเปลี่ยนบทบาท investigator/tester/writer เป็น go2 ตอน 15:34-15:35 และ go2 ตอน 16:04:33 (ไม่พบเส้นอัตโนมัติ — ผ่าน `flashq models` / `/api/role_model` / `/api/switch` ที่มีคนสั่ง) · ยังไม่ทราบตัวผู้สั่ง

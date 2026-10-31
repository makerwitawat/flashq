# แผน แก้ธง (flashq goal) เบรกแล้วค้าง ไปต่อไม่ได้ — ส่งงานให้ DeepSeek Flash

> แผนของ flashq เอง — Claude วางแผน+ตรวจ · DeepSeek ลงมือ
> สร้าง 2026-10-31 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_GOAL_STUCK.md T-01..T-09 --switch-on-quota 4` · base commit ตอนวางแผน: `de0d906`

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, ui.html, tests/test_flashq.py, claude/commands/flash-goal.md, CHANGELOG.md, docs/REFERENCE.md
flashq-parallel: no — ทุกงานแก้ flashq.py ไฟล์เดียวกัน
flashq-exclusive: flashq.py

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- <ไฟล์ของงาน>` + `git commit -m "<ข้อความในงาน>"`) · **ห้าม push** · **ห้าม `git add -A` / `git add .`**
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment/แปลง encoding (flashq.py เป็น CRLF — คงไว้)
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "ก่อน"/"จุดเสียบ" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนไว้ตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · หลักฐานชี้ขาด = path log + บรรทัดที่แผนกำหนดตรงตัว)
6. **ห้ามแตะ**: `%USERPROFILE%\.flashq\` (ข้อมูลจริง — เทสต์ใช้ `FLASHQ_HOME` ปลอมอยู่แล้ว) · ห้ามแก้เทสต์เดิมให้หลวมลง · ห้ามรัน `python flashq.py install` · ห้ามรีสตาร์ต `flashq ui` พอร์ต 4097
7. **งาน "เทสต์ก่อน"**: เขียนเทสต์ → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (log แดง) → แก้โค้ด → รันซ้ำต้อง PASS (log เขียว) → commit เดียว · ผ่านตั้งแต่ก่อนแก้ / ล้มด้วยเหตุอื่น (import error, syntax) → **⛔ หยุด**
8. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน" ตรง ๆ
9. stdlib ล้วน ห้ามเพิ่ม dependency · ข้อความที่ผู้ใช้เห็น/คอมเมนต์/commit เป็นภาษาไทย · commit ขึ้นต้นส่วนที่แก้ (`flashq:` `ui:` `flash-goal:`)
10. เทสต์ใหม่ทุกตัววางในคลาสเดียวกับ `def test_goal_verify_loop_and_brakes` (ใช้ `self.goal_repo(body)` · `self.run_q(...)` · `self.load_mod(...)` แบบเทสต์ goal เดิม) · `py = f'"{sys.executable}"'` · **G01** ด้านล่าง = บรรทัดเกณฑ์ G-01 ตัวแรกของตัวแปร `body` ใน `test_goal_verify_loop_and_brakes` (คัดตรงตัว: เกณฑ์ `ตรวจ:` รัน tests/acc.py + `ต้องเห็น:` VAL=new) **ไม่มี** ข้อ G-02 คนตรวจ

### คำสั่งมาตรฐาน
```
PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "<คำ>"
```
(log ไว้ที่ `.tmp/` เช่น `... > .tmp/T-01.red.log 2>&1` · เทสต์ goal เปิด process จริงหลายตัว ตั้ง timeout ≥ 300 วิ)

---

## 1. งาน
### สาเหตุ/หลักฐาน (Claude ยืนยันที่โค้ดแล้ว)
- **ก** `goal_changed_files` (`flashq.py:7287-7299`) รวมไฟล์ของ **ทุก commit ใน `base..HEAD`** → commit ที่หลุดขอบเขตครั้งเดียว (หรือ revert แล้ว) อยู่ใน out_scope/locked ตลอดไป · `cmd_goal` verify (`:7809-7812`) เช็กเบรกก่อนผลเกณฑ์ = STOP ทุกครั้ง · ทางออกเดียวคือ `check --reset` (ล้าง base/รอบ/เวลา)
- **ข** STOP "ครบงบ"/"เกินงบเวลา" (`:7816-7819`) ไม่มีทางต่องบนอกจาก `--reset`
- **ค** `goal status` (`:7760-7767`) ไม่พิมพ์ `last["stop"]`/warn → session ที่ทำต่อไม่รู้ว่าเบรกเพราะอะไร
- **ง** dialog ปุ่ม 🔄 (`ui.html:3778`) บอก "นับเป็นรอบใหม่ของงบรอบ" ขัดกับ verify จริง (`flashq.py:7841` "ตรวจซ้ำ ไม่นับรอบเพิ่ม")
- **จ** state อยู่ที่ `<project>/.tmp/flashq-goal/` (`:6287`) ลบ `.tmp` = รอบ/base หาย
- **ฉ** `goal_phase` (`:7117`) ถืองาน Flash ที่ถูก cancel เป็น "เสร็จแล้ว รอ Claude ตรวจ" (`last_job` มี `state` อยู่แล้วที่ `:7203`)
- **ช** `goal_run_cmd` (`:7693-7700`) ไม่ตั้ง stdin และ `p.wait()` หลัง kill ไม่มี timeout

### กลุ่ม A — ปลดเบรกโดยไม่ล้างรอบ (flashq.py)

- [x] **T-01** `flashq.py` (`goal_changed_files` · `cmd_goal` · argparse ของ `goal`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - แนวคิด: คำสั่งใหม่ `goal ack <GOAL> --reason "<เหตุของ user>"` = user รับทราบไฟล์นอกขอบเขต/ไฟล์ล็อก **ทั้งหมดจนถึงตอนนี้** · ไม่แตะ `base` `started` `rounds` `past` · หลัง ack ตรวจเฉพาะ commit หลัง HEAD ตอน ack และไฟล์ค้างที่แก้หลังเวลา ack
  - เทสต์: `test_goal_ack_clears_scope_brake_keeps_rounds` · body = G01 + `"goal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 5\n"` · ลำดับ:
    1. `goal check` → `GOAL_CHECK=OK`
    2. `goal ack docs/plans/GOAL_x.md --reason x` (ยังไม่มีรอบ) → stdout มี `GOAL_ACK=FAIL` · returncode 1
    3. เขียน `other.py` แล้ว `git add other.py` + `git commit -qm นอกขอบเขต` · เขียน `scratch.txt` (ไม่ commit) → `goal verify` → มี `GOAL=STOP` · `other.py` · `scratch.txt`
    4. อ่าน state `.tmp/flashq-goal/GOAL_x.json` เก็บ `base` `started` · `len(rounds) == 1`
    5. `goal ack ...` ไม่ใส่ `--reason` → `GOAL_ACK=FAIL` · returncode 1
    6. `goal ack docs/plans/GOAL_x.md --reason "user ยอมรับ"` → มี `GOAL_ACK=OK` `other.py` `scratch.txt` · returncode 0
    7. state: `base`/`started` เท่าเดิม · `len(rounds) == 1` · `st["acks"][-1]["reason"] == "user ยอมรับ"`
    8. เขียน `src/a.txt` = `new\n` → `goal verify` → มี `GOAL=DONE` · ไม่มี `นอกขอบเขต`
    9. เขียน `other2.py` + add + commit → `goal verify` → `assertRegex(r.stdout, r"(?m)goal-files: other2\.py$")` (other.py/scratch.txt ไม่กลับมา)
  - แดง (ก่อนแก้โค้ด): `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "goal_ack" > .tmp/T-01.red.log 2>&1` → FAIL ที่ข้อ 2: `AssertionError: 'GOAL_ACK=FAIL' not found in ''` (argparse ปฏิเสธ `invalid choice: 'ack'`)
  - แก้ (สเปก):
    - ก่อน: `go.add_argument("action", choices=["check", "verify", "status", "human", "cancel"])`
    - หลัง: `go.add_argument("action", choices=["check", "verify", "status", "human", "cancel", "ack"])` · และเติมท้าย help ของ `--reason` ว่า ` · ack: เหตุที่ user ยอมรับไฟล์นอกขอบเขต/ไฟล์ล็อก`
    - ก่อน: `scope: list[str] | None = None) -> tuple[list[str], list[str]]:`
    - หลัง: `scope: list[str] | None = None, ack: dict | None = None) -> tuple[list[str], list[str]]:` · ในตัวฟังก์ชันบรรทัดแรก (ก่อน `ours, maybe = set(), set()`): `if ack and ack.get("head"): base = ack["head"]` และ `ack_ts, acked = float((ack or {}).get("ts") or 0), set((ack or {}).get("files") or [])` · เพิ่ม docstring 1 บรรทัด "ack = user รับทราบแล้ว: นับ commit หลัง head ของ ack · ไฟล์ค้างที่แก้หลัง ts"
    - ก่อน: `if f and (any(a - 2 <= m <= b + 5 for a, b in windows) if windows else m >= _ts(started)):`
    - หลัง: `if f and m > ack_ts and (any(a - 2 <= m <= b + 5 for a, b in windows) if windows else m >= _ts(started)):`
    - ก่อน: `ours.add(f)  # ถูกลบ = นับว่าแก้`
    - หลัง: `if f not in acked: ours.add(f)  # ถูกลบ = นับว่าแก้ (ยกเว้นที่ ack แล้ว)` (แตกเป็น 2 บรรทัด if/บล็อกตามสไตล์ก็ได้)
    - ก่อน: `ours, maybe = goal_changed_files(root, st["base"], st["started"], windows, goal_topic(goal.stem), g["files"] + free) if is_git else ([], [])`
    - หลัง: เหมือนเดิมแต่เพิ่มอาร์กิวเมนต์ท้าย `, ack=(st.get("acks") or [None])[-1]` ก่อน `)` ของ `goal_changed_files(`
    - ฟังก์ชันใหม่ `goal_ack(root, goal, rel, g, st, sp, rounds_max, a) -> int` วางก่อน `def cmd_goal(a) -> int:`: ① `reason = (a.reason or "").strip()` ว่าง → พิมพ์ `GOAL_ACK=FAIL ต้องระบุ --reason "เหตุที่ user ยอมรับ"` คืน 1 ② `last = st["rounds"][-1] if st.get("rounds") else {}` · `files = sorted(set(last.get("out_scope", []) + last.get("locked", []) + last.get("warn", [])))` ว่าง → `GOAL_ACK=FAIL รอบล่าสุดไม่มีไฟล์นอกขอบเขต/ไฟล์ล็อกให้รับทราบ` คืน 1 ③ `st["acks"] = (st.get("acks") or [])[-19:] + [{"at": now(), "ts": time.time(), "head": _git(root, "rev-parse", "HEAD"), "reason": reason, "files": files[:50]}]` ④ `write_json(sp, st)` + `goal_publish(root, goal, rel, g, st, rounds_max)` ⑤ พิมพ์ `รับทราบ {len(files)} ไฟล์: ` + 8 ไฟล์แรก (+ ` …` ถ้าเกิน) แล้วบรรทัด (f-string) `GOAL_ACK=OK → รัน goal verify {rel} ต่อ (ไม่ล้าง base/รอบ/ประวัติ · commit/ไฟล์ที่แก้หลังจากนี้ยังถูกตรวจตามปกติ)` คืน 0
    - จุดเสียบใน `cmd_goal`: ใต้บรรทัด `if a.action == "human":` และ `return goal_human(...)` ของมัน → เพิ่ม `if a.action == "ack":` / `return goal_ack(root, goal, rel, g, st, sp, rounds_max, a)` (อยู่หลังด่าน `if not st:` แล้ว = ยังไม่ check ก็ได้ STOP เดิม)
    - กรณีขอบ: ack ไม่เปลี่ยน verdict ของรอบล่าสุด (ต้อง verify ใหม่) · `check --reset` สร้าง state ใหม่ = `acks` หาย (ถูกต้อง: base ใหม่) · ไม่ต้องตรวจว่า head เป็นบรรพบุรุษของ HEAD
  - เขียว: คำสั่งเดิม `> .tmp/T-01.green.log 2>&1` → PASS · แล้วกันถอย: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "goal_verify_loop or goal_scope_counts" > .tmp/T-01.reg.log 2>&1` → PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-01.red.log` บรรทัด `'GOAL_ACK=FAIL' not found` · เขียว `.tmp/T-01.green.log` บรรทัด `1 passed` · `.tmp/T-01.reg.log` บรรทัด `2 passed`
  - commit: `flashq: goal ack รับทราบไฟล์นอกขอบเขต/ไฟล์ล็อกแล้วตรวจต่อได้ ไม่ต้อง --reset (ไม่ล้าง base/รอบ) + เทสต์ (T-01)`

- [x] **T-02** `flashq.py` (`cmd_goal` check/verify · `goal_publish` · argparse) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - แนวคิด: `goal check <GOAL> --extend N [--extend-hours H]` = user ต่องบหลัง STOP ครบงบ/เกินเวลา · เก็บ base/started/rounds/past ไว้ · ใช้ได้เฉพาะธงที่เริ่มแล้วและไม่คู่ `--reset`
  - เทสต์: `test_goal_extend_budget_keeps_history` · body = G01 + `"goal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 2\n"` · `goal check` → `src/a.txt`=`v1\n` → verify มี `GOAL=CONTINUE รอบ 1/2` → `src/a.txt`=`v2\n` → verify มี `ครบงบ 2 รอบแล้วยังไม่ผ่าน` · เก็บ `base` `started` จาก state · `goal check ... --extend 2 --reset` → มี `GOAL_CHECK=FAIL` · `goal check ... --extend 2 --extend-hours 1` → มี `GOAL_CHECK=OK` `งบ 4 รอบ / 7 ชม.` `ใช้ไปแล้ว 2 รอบ` · state: `base`/`started` เท่าเดิม `len(rounds)==2` `extra_rounds==2` · verify (ไม่มีงานใหม่) → มี `GOAL=CONTINUE รอบ 2/4`
  - แดง: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "goal_extend" > .tmp/T-02.red.log 2>&1` → FAIL `AssertionError: 'GOAL_CHECK=FAIL' not found in ''` (argparse: `unrecognized arguments: --extend`)
  - แก้:
    - จุดเสียบ argparse: ใต้ `go.add_argument("--reset", ...` เพิ่ม `--extend` (`type=int, default=0`, help `check: ต่องบรอบ +N เก็บ base/รอบ/ประวัติ — ใช้เมื่อ user สั่งหลัง STOP ครบงบ`) และ `--extend-hours` (`dest="extend_hours", type=float, default=0`, help `check: ต่องบเวลา +H ชม.`)
    - ก่อน: `rounds_max = min(GOAL_ROUNDS_CAP, max(1, g["rounds"]))`
    - หลัง: `rounds_max = min(GOAL_ROUNDS_CAP, max(1, g["rounds"])) + int((st or {}).get("extra_rounds") or 0)  # + ที่ user ต่องบ (check --extend)`
    - จุดเสียบ check 1: ในบล็อก `if not st or a.reset:` (บรรทัดถัดจาก `st = {"goal": rel, "sig": g["sig"], ...}`) เพิ่ม `rounds_max = min(GOAL_ROUNDS_CAP, max(1, g["rounds"]))  # state ใหม่ = ไม่มีงบที่ต่อไว้` (กันการ์ด/ข้อความ check --reset โชว์งบเก่าที่ต่อไว้)
    - จุดเสียบ check 2: หลังบล็อก `if a.reset and old:` (3 บรรทัด) ก่อน `st["owner"] = goal_owner() or ...` ของ check — เพิ่มบล็อกด้านล่าง
    - ก่อน: `f"งบ {rounds_max} รอบ / {g['hours']:g} ชม. · ใช้ไปแล้ว {len(st['rounds'])} รอบ · base {st['base'][:9]}")`
    - หลัง: แทน `{g['hours']:g}` ด้วย `{g['hours'] + float(st.get('extra_hours') or 0):g}` (ที่เหลือตรงตัว)
    - ก่อน: `if hrs >= g["hours"]:` → หลัง 2 บรรทัด: `hmax = g["hours"] + float(st.get("extra_hours") or 0)` แล้ว `if hrs >= hmax:` (ย่อหน้าเท่าเดิม)
    - ก่อน: `stop.append(f"เกินงบเวลา {g['hours']:g} ชม. (ผ่านไป {hrs:.1f})")` → หลัง: `stop.append(f"เกินงบเวลา {hmax:g} ชม. (ผ่านไป {hrs:.1f})")`
    - ก่อน: `"rounds_max": rounds_max, "hours": g["hours"], "started": st.get("started", ""), "updated": now(), "rounds": rounds,`
    - หลัง: แทน `g["hours"]` ด้วย `g["hours"] + float(st.get("extra_hours") or 0)` (ที่เหลือตรงตัว)
  ```python
        if a.extend or a.extend_hours:  # user ต่องบ: ไม่แตะ base/started/rounds/past
            if a.reset or not old:
                print("ต้องแก้: --extend ใช้กับธงที่เริ่มแล้วเท่านั้น และห้ามใช้คู่ --reset")
                print("GOAL_CHECK=FAIL")
                return 1
            if not (0 <= a.extend <= GOAL_ROUNDS_CAP and 0 <= a.extend_hours <= 24):
                print(f"ต้องแก้: --extend ได้ 0..{GOAL_ROUNDS_CAP} รอบ · --extend-hours ได้ 0..24 ชม. ต่อครั้ง")
                print("GOAL_CHECK=FAIL")
                return 1
            st["extra_rounds"] = int(st.get("extra_rounds") or 0) + a.extend
            st["extra_hours"] = float(st.get("extra_hours") or 0) + a.extend_hours
            rounds_max += a.extend
            print(f"ต่องบ +{a.extend} รอบ / +{a.extend_hours:g} ชม. (ต่อแล้วรวม {st['extra_rounds']} รอบ / {st['extra_hours']:g} ชม.) · base/รอบ/ประวัติเดิมคงไว้")
  ```
  - กรณีขอบ: เกณฑ์ถูกแก้ (sig ไม่ตรง) → ด่านเดิม `ต้องแก้: เกณฑ์ต่างจากตอนเริ่ม` FAIL ก่อนถึงบล็อกนี้ (ถูกต้อง) · verify หลังต่องบโดยไม่มีงานใหม่ = recheck ถอดรอบ STOP ออก → `n` = รอบเดิม < เพดานใหม่ → CONTINUE
  - เขียว: คำสั่งเดิม `> .tmp/T-02.green.log 2>&1` → PASS · กันถอย `-k "goal_verify_loop or goal_published"` `> .tmp/T-02.reg.log 2>&1` → PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-02.red.log` บรรทัด `'GOAL_CHECK=FAIL' not found` · เขียว `.tmp/T-02.green.log` `1 passed` · `.tmp/T-02.reg.log` `2 passed`
  - commit: `flashq: goal check --extend/--extend-hours ต่องบรอบ/เวลาหลัง STOP โดยไม่ล้าง base/รอบ + เทสต์ (T-02)`

- [x] **T-03** `flashq.py` (`goal stop hints` ใหม่ · `cmd_goal` status/verify) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_goal_status_shows_brakes_and_way_out` · body = G01 + `"goal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 3\n"` · `goal check` → เขียน `other.py` (ไม่ commit) → `goal verify` → stdout มี `เบรก: แก้ไฟล์นอกขอบเขต goal-files: other.py` และ `goal ack docs/plans/GOAL_x.md` · `goal status` → มี `เบรก: แก้ไฟล์นอกขอบเขต goal-files: other.py` · `goal ack docs/plans/GOAL_x.md` · `ทางออก`
  - แดง: `... -k "goal_status_shows_brakes" > .tmp/T-03.red.log 2>&1` → FAIL `AssertionError: 'goal ack docs/plans/GOAL_x.md' not found in` (verify ยังไม่มีบรรทัดทางออก)
  - แก้:
    - ฟังก์ชันใหม่วางก่อน `def goal_run_cmd(root: Path, cmd: str, timeout_min: float) -> tuple[int, str]:` (ข้อความตรงตัว):
  ```python
def goal_stop_hints(stop: list[str], rel: str) -> list[str]:
    """เหตุเบรก → คำสั่งทางออกที่ใช้ได้จริง (สั่งเมื่อ user เลือกแล้วเท่านั้น)"""
    out, has = [], lambda *ks: any(k in s for s in stop for k in ks)  # noqa: E731
    if has("นอกขอบเขต", "ไฟล์ล็อก"):
        out.append(f"ทางออก (ไฟล์นอกขอบเขต/ไฟล์ล็อก): ให้ user ตรวจไฟล์ → ยอมรับ = `goal ack {rel} --reason \"<เหตุของ user>\"` แล้ว `goal verify`"
                   " · ไม่ยอมรับ = git revert แล้ว ack เช่นกัน (ไม่ล้าง base/รอบ)")
    if has("ครบงบ", "เกินงบเวลา"):
        out.append(f"ทางออก (งบหมด): user ต่องบ = `goal check {rel} --extend <รอบ> --extend-hours <ชม.>` แล้ว `goal verify` (เก็บ base/รอบ/ประวัติ)"
                   f" · หรือเริ่มนับใหม่ทั้งหมด = `goal check {rel} --reset`")
    if has("พังซ้ำ"):
        out.append("ทางออก (พังซ้ำ): สืบต้นตอใหม่/แผนคนละทาง → มีงานใหม่แล้วค่อย `goal verify` (ตรวจซ้ำโดยไม่มีงานใหม่ไม่ช่วย)")
    if has("ย้ายเสาประตู"):
        out.append(f"ทางออก (เกณฑ์ถูกแก้): user ยืนยันเกณฑ์ใหม่ → `goal check {rel} --reset`")
    return out
  ```
    - จุดเสียบ verify: บรรทัด `for s in stop:` + `print(f"เบรก: {s}")` (มีที่เดียว) → ต่อท้ายด้วย `for h in goal_stop_hints(stop, rel):` / `print(h)` (ย่อหน้าระดับเดียวกับ `for s in stop:`)
    - จุดเสียบ status: หลังลูป `for k, v in (last.get("human_res") or {}).items():` (บรรทัด `print(f"คนตรวจ {k}: ...`) ก่อน `return 0` ของ status — เพิ่มที่ระดับย่อหน้าเดียวกับ `if last:`: ① `stops = list((last or {}).get("stop") or [])` ② ถ้า `st.get("sig") != g["sig"]` และไม่มี "ย้ายเสาประตู" ใน stops → append ข้อความเดียวกับ stop ย้ายเสาประตูของ verify (คัดสตริงตรงตัวจากบรรทัดที่ขึ้นต้น `stop.append("เกณฑ์/ขอบเขตในไฟล์เป้าหมายถูกแก้หลังเริ่ม`) ③ พิมพ์ `เบรก: {s}` ทุกข้อ ④ `(last or {}).get("warn")` มี → `เตือน: ไฟล์นอกขอบเขตที่อาจเป็นของ session อื่น (ไม่เบรก): ` + 8 ไฟล์แรก ⑤ พิมพ์ทุกบรรทัดจาก `goal_stop_hints(stops, rel)` ⑥ `st.get("acks")` มี → `รับทราบล่าสุด {at}: {reason} ({n} ไฟล์)`
  - เขียว: คำสั่งเดิม `> .tmp/T-03.green.log 2>&1` → PASS · กันถอย `-k "goal_verify_loop"` `> .tmp/T-03.reg.log 2>&1` → PASS (ข้อความ `ครบงบ 3 รอบแล้วยังไม่ผ่าน` ต้องคงเดิม)
  - หลักฐานชี้ขาด: แดง `.tmp/T-03.red.log` บรรทัด `'goal ack docs/plans/GOAL_x.md' not found` · เขียว `1 passed` · reg `1 passed`
  - commit: `flashq: goal status/verify พิมพ์เหตุเบรกทุกข้อ + บรรทัดทางออก (ack/extend/reset) + เทสต์ (T-03)`

### กลุ่ม B — หน้าเว็บ + สถานะไม่หาย + ไม่ค้าง

- [x] **T-04** `ui.html` ~3778 (dialog ปุ่ม 🔄 ตรวจใหม่)
  - ก่อน: `• นับเป็นรอบใหม่ของงบรอบ" })) return;`
  - หลัง: `• ไม่มีงานใหม่ตั้งแต่รอบก่อน = ไม่นับรอบ แค่อัปเดตผล" })) return;`
  - (สองวลีนี้มีในพจนานุกรม EN แล้ว: `ไม่มีงานใหม่ตั้งแต่รอบก่อน|…` และ `ไม่นับรอบ แค่อัปเดตผล|…` · **ห้ามแตะ** บรรทัด `นับเป็นรอบใหม่ของงบรอบ|counts as…` ในพจนานุกรม)
  - ยืนยัน 1: ดึงเนื้อหา `<script>` ของ ui.html ไป `.tmp/ui_check.js` แล้ว `node --check .tmp/ui_check.js > .tmp/T-04.node.log 2>&1` → ไฟล์ log ว่าง (node --check ผ่านจะไม่พิมพ์อะไร)
  - ยืนยัน 2: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "ui_english_dictionary" > .tmp/T-04.log 2>&1` → PASS
  - หลักฐานชี้ขาด: `.tmp/T-04.node.log` ขนาด 0 ไบต์ · `.tmp/T-04.log` บรรทัด `1 passed` · `git show --stat HEAD` แตะ `ui.html` ไฟล์เดียว 1 บรรทัด
  - commit: `ui: กล่องยืนยันตรวจใหม่บอกตรงจริง — ไม่มีงานใหม่ = ไม่นับรอบ (T-04)`

- [x] **T-05** `flashq.py` (`_goal_load` · `goal_publish`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - แนวคิด: ต้นฉบับยังอยู่ที่ `.tmp/flashq-goal/` (เทสต์เดิมอ้าง) · เพิ่มสำเนาที่ `HOME / "goal-state" / "<key>.json"` (key เดียวกับการ์ดใน `goal_publish`) · ต้นฉบับหาย → กู้จากสำเนา (ไม่ใช้โฟลเดอร์ `goals/` เพราะเทสต์ `:3492` ตรวจว่าโฟลเดอร์นั้นว่าง)
  - เทสต์: `test_goal_state_recovers_after_tmp_deleted` · body = G01 + `"goal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 3\n"` · check → verify (`GOAL=CONTINUE รอบ 1/3`) → `len(list((self.home / "goal-state").glob("*.json"))) == 1` → `shutil.rmtree(self.proj / ".tmp" / "flashq-goal")` → `goal status` มี `รอบ 1/3` และ `กู้สถานะธงจากสำเนา` · ไม่มี `ยังไม่ได้รัน` → `goal verify` มี `GOAL=CONTINUE รอบ 1/3` · ไฟล์ `.tmp/flashq-goal/GOAL_x.json` มีอยู่
  - แดง: `... -k "goal_state_recovers" > .tmp/T-05.red.log 2>&1` → FAIL `AssertionError: 0 != 1` (ยังไม่มีสำเนา)
  - แก้:
    - จุดเสียบ: ใต้ `GOALS_DIR = HOME / "goals"` เพิ่ม `GOAL_STATE_BAK = HOME / "goal-state"  # สำเนาไฟล์สถานะธง (.tmp ในโปรเจกต์ถูกลบได้)` และฟังก์ชัน `_goal_key(root: Path, rel: str) -> str` คืน `hashlib.sha1(f"{root.resolve()}|{rel}".lower().encode("utf-8")).hexdigest()[:12]` · ใน `goal_publish` เปลี่ยน `key = hashlib.sha1(...)` เป็น `key = _goal_key(root, rel)`
    - ใน `goal_publish` หลัง `write_json(GOALS_DIR / f"{key}.json", {...})` (ยังอยู่ใน try): `GOAL_STATE_BAK.mkdir(parents=True, exist_ok=True)` + `write_json(GOAL_STATE_BAK / f"{key}.json", st)`
    - ก่อน: `return goal, _goal_state_path(root, goal), goal_parse(goal), read_json(_goal_state_path(root, goal))`
    - หลัง (สเปก ~8 บรรทัด): `sp = _goal_state_path(root, goal)` · `st = read_json(sp)` · ถ้า `not st`: `rel = goal.relative_to(root).as_posix() if goal.is_relative_to(root) else str(goal)` · `st = read_json(GOAL_STATE_BAK / f"{_goal_key(root, rel)}.json")` · ได้ค่า → try `sp.parent.mkdir(parents=True, exist_ok=True)` + `write_json(sp, st)` except OSError: pass · `print("หมายเหตุ: ไฟล์สถานะธงใน .tmp/flashq-goal หาย → กู้สถานะธงจากสำเนา ~/.flashq/goal-state/ (รอบ/base เดิม)")` · `return goal, sp, goal_parse(goal), st`
    - แก้คอมเมนต์ท้าย `GOALS_DIR = ...` ไม่ต้อง
  - กรณีขอบ: ไม่มีทั้งสองที่ = `{}` เหมือนเดิม (`ยังไม่ได้รัน goal check`) · ล้างธงจริงต้อง `goal check --reset` (ลบ .tmp ไม่รีเซ็ตแล้ว)
  - เขียว: คำสั่งเดิม `> .tmp/T-05.green.log 2>&1` → PASS · กันถอย `-k "goal_cancel or goal_published or goal_check_rejects"` `> .tmp/T-05.reg.log 2>&1` → PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-05.red.log` บรรทัด `AssertionError: 0 != 1` · เขียว `1 passed` · reg `4 passed`
  - commit: `flashq: สำรองสถานะธงไว้ที่ ~/.flashq/goal-state — ลบ .tmp แล้วรอบ/base ไม่หาย + เทสต์ (T-05)`

- [x] **T-06** `flashq.py` ~7117 (`goal_phase`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_goal_phase_cancelled_job_needs_new_round` · body = G01 + `"goal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 3\n"` · check + verify ด้วย `env={"CLAUDE_CODE_SESSION_ID": ""}` · `mod = self.load_mod("flashq_goalcancelled")` · `mod.GOALS_DIR = self.home / "goals"` · `mod.CLAUDE_PROJECTS = self.home / "cp"` · `g = mod.ui_goals([])[0]` · `job = {"id": "J9", "project": g["project"], "plan": "docs/plans/PLAN_FLASH_x_R2.md", "state": "cancelled", "finished": "2099-01-01 00:00:00"}` · `ph = mod.ui_goals([], [job])[0]["phase"]` → `ph["step"] == "plan"` · `"ถูกยกเลิก" in ph["label"]` · `ph["warn"] is True`
  - แดง: `... -k "goal_phase_cancelled" > .tmp/T-06.red.log 2>&1` → FAIL `AssertionError: 'review' != 'plan'`
  - แก้: ก่อน `if fresh and verdict != "DONE":` (มีที่เดียว) แทรก 3 บรรทัด ย่อหน้าเท่ากัน:
    - `if fresh and verdict != "DONE" and last_job.get("state") == "cancelled":  # งานรอบนั้นถูกหยุด ไม่ใช่ทำเสร็จ`
    - `    return ph("plan", f"🚫 งาน Flash รอบ {last_job['round']} ถูกยกเลิกก่อนเสร็จ — ต้องส่งแผนรอบนี้เข้าคิวใหม่ (ไม่ต้อง goal verify)",`
    - `              last_job.get("ago_sec"), "ยกเลิกมา", True, rnd=last_job["round"])`
  - เขียว: คำสั่งเดิม `> .tmp/T-06.green.log 2>&1` → PASS · กันถอย `-k "goal_published"` `> .tmp/T-06.reg.log 2>&1` → PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-06.red.log` บรรทัด `'review' != 'plan'` · เขียว `1 passed` · reg `1 passed`
  - commit: `flashq: การ์ดธงแยก "งานรอบนี้ถูกยกเลิก — ส่งใหม่" ไม่ค้าง "รอ Claude ตรวจ" + เทสต์ (T-06)`

- [x] **T-07** `flashq.py` ~7693-7700 (`goal_run_cmd`) — แก้ตรง ไม่มีเทสต์แดง (เหตุ: `run_q` ส่ง `stdin=DEVNULL` ให้ flashq อยู่แล้ว ลูกสืบทอด → เทสต์ stdin ผ่านตั้งแต่ก่อนแก้ · kill ไม่สำเร็จจำลองไม่ได้ในเทสต์)
  - ก่อน: `p = subprocess.Popen(cmd, shell=True, cwd=str(root), stdout=buf, stderr=subprocess.STDOUT)`
  - หลัง: `p = subprocess.Popen(cmd, shell=True, cwd=str(root), stdin=subprocess.DEVNULL, stdout=buf, stderr=subprocess.STDOUT)  # คำสั่งที่รอ input ได้ EOF ทันที ไม่ค้าง`
  - จุดเสียบ 2: บรรทัด `p.wait()` ที่อยู่**ถัดจาก `kill_tree(p.pid)` ภายใน `def goal_run_cmd`** (ไม่ใช่ที่ ~1663/~1759) → แทนด้วย `try:` / `p.wait(timeout=15)` / `except subprocess.TimeoutExpired:` / `print(f"เตือน: ฆ่าคำสั่งเกณฑ์ไม่สำเร็จ pid {p.pid} — ไม่รอต่อ", file=sys.stderr)` (ย่อหน้าตามบล็อก except เดิม · สไตล์เดียวกับ `print(..., file=sys.stderr)` ที่มีในไฟล์)
  - ยืนยัน: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "goal_cmd_not_blocked or goal_verify_loop" > .tmp/T-07.log 2>&1` → PASS
  - หลักฐานชี้ขาด: `.tmp/T-07.log` บรรทัด `2 passed` · `git show HEAD` มี `stdin=subprocess.DEVNULL` และ `p.wait(timeout=15)` ใน goal_run_cmd
  - commit: `flashq: goal verify ไม่ค้างเมื่อคำสั่งเกณฑ์รอ input หรือฆ่าไม่ตาย (stdin=DEVNULL + รอหลัง kill ≤15 วิ) (T-07)`

### กลุ่ม C — เอกสาร

- [x] **T-08** `claude/commands/flash-goal.md` (§3 STOP · §5 ทำต่อ) — ข้อความในบล็อก text ด้านล่างคือข้อความตรงตัวที่ต้องใส่ (ไม่มี backslash)
  - จุดเสียบ 1: บรรทัดที่ขึ้นต้น `- มีงาน flashq ค้างอยู่` → ในวงเล็บของบรรทัดนั้น แทน `{{FLASHQ_RUN}}` (ที่ไม่มีคำสั่งย่อย) ด้วยข้อความบรรทัดที่ 1 ของบล็อก (เดิมไม่มีคำสั่งย่อย → ตรวจงานค้างไม่ได้)
  - จุดเสียบ 2: บรรทัดที่ขึ้นต้น `` - `GOAL=STOP` → **หยุดวน** `` → ต่อท้ายบรรทัดด้วยบรรทัดที่ 2 ของบล็อก
  - จุดเสียบ 3: บรรทัดที่มีคำว่า `รายงานเบรกให้ user ก่อน` (ใน §5 ทำต่อ) → แทรกบรรทัดที่ 3 ของบล็อก ต่อจากคำว่า `รายงานเบรกให้ user ก่อน` ทันที
  ```text
{{FLASHQ_RUN}} status
 · บรรทัด `ทางออก:` บอกคำสั่งที่ใช้ได้ (`goal ack <GOAL> --reason "…"` รับทราบไฟล์นอกขอบเขต/ไฟล์ล็อก · `goal check <GOAL> --extend N --extend-hours H` ต่องบ · `goal check --reset` เริ่มใหม่) — สั่งเฉพาะเมื่อ user เลือกทางนั้นแล้ว · `--reason` ใช้คำของ user
 (บรรทัด `เบรก:`/`ทางออก:` จาก `goal status`)
  ```
  - ยืนยัน: `git grep -n -F "FLASHQ_RUN}} status" claude/commands/flash-goal.md > .tmp/T-08.log` แล้ว `PYTHONIOENCODING=utf-8 python -m pytest tests/test_flashq.py -q -x -k "install" >> .tmp/T-08.log 2>&1` → PASS
  - หลักฐานชี้ขาด: `.tmp/T-08.log` มีบรรทัด `flash-goal.md:` ที่มี `FLASHQ_RUN}} status` 1 บรรทัด + บรรทัดสรุป pytest มี `passed` ไม่มี `failed`
  - commit: `flash-goal: ทำต่อตรวจงานค้างด้วย status + STOP บอกทางออก ack/extend/reset (T-08)`

- [x] **T-09** `CHANGELOG.md` + `docs/REFERENCE.md` — ข้อความในบล็อก text = ตรงตัว
  - ก่อน: `## 2026-10-31` (CHANGELOG มีที่เดียว) → หลัง: คงหัวข้อ แล้วแทรกบรรทัดที่ 1 ของบล็อกเป็น bullet แรกใต้หัวข้อ
  - ก่อน: `python D:\MyCode\flashq\flashq.py goal check|verify|status|human|cancel <GOAL>   # โหมดเป้าหมาย` → หลัง: แทน `cancel <GOAL>` ด้วย `cancel|ack <GOAL>` (ที่เหลือตรงตัว)
  - จุดเสียบ REFERENCE: บรรทัดที่ขึ้นต้น `` - `flashq goal status <GOAL>` = ทำต่อหลัง session ปิด `` → แทรกบรรทัดที่ 2 ของบล็อกเป็นบรรทัดใหม่ **ก่อน** บรรทัดนั้น
  ```text
- **แก้: ธง (flashq goal) เบรกแล้วค้าง**: `goal ack <GOAL> --reason "…"` รับทราบไฟล์นอกขอบเขต/ไฟล์ล็อกแล้วตรวจต่อได้ (เดิม STOP ตลอดเพราะ commit เก่าอยู่ใน base..HEAD) · `goal check --extend N --extend-hours H` ต่องบโดยไม่ล้าง base/รอบ · `goal status` พิมพ์เหตุเบรก + ทางออก · สถานะธงสำรองที่ `~/.flashq/goal-state/` (ลบ .tmp ไม่รีเซ็ต) · การ์ดแยกงานรอบที่ถูกยกเลิก · กล่องตรวจใหม่บอกตรงว่าไม่มีงานใหม่ไม่นับรอบ · verify ไม่ค้างเมื่อเกณฑ์รอ input
- **ทางออกเมื่อ STOP** (`goal status`/`verify` พิมพ์บรรทัด `ทางออก:`): ไฟล์นอกขอบเขต/ไฟล์ล็อก → `flashq goal ack <GOAL> --reason "<เหตุ user>"` (ไม่ล้าง base/รอบ · ตรวจเฉพาะที่แก้หลัง ack) · ครบงบรอบ/เวลา → `flashq goal check <GOAL> --extend N --extend-hours H` · เริ่มใหม่ทั้งหมด → `goal check --reset` · สถานะสำรองที่ `~/.flashq/goal-state/` (ต้นฉบับ `.tmp/flashq-goal/` หาย = กู้ให้เอง)
  ```
  - ยืนยัน (ก่อน commit): `git diff --stat > .tmp/T-09.log` → แตะ 2 ไฟล์
  - หลักฐานชี้ขาด: `.tmp/T-09.log` บรรทัด `2 files changed` · `git grep -n "goal ack" CHANGELOG.md docs/REFERENCE.md` ≥ 2 บรรทัด
  - commit: `flashq: เอกสาร goal ack/--extend/สำรองสถานะธง (T-09)`

## 2. งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- `goal ack` ปลดทั้ง "นอกขอบเขต" และ "ไฟล์ล็อก" ด้วยคำสั่งเดียว (ตามที่สั่งมา) — ถ้าอยากให้ไฟล์ล็อก (เทสต์เกณฑ์ กันโกง) ต้องใส่แฟล็กแยก เช่น `--locked` ให้ตัดสินก่อนส่ง
- `--extend` จำกัดต่อครั้ง ≤10 รอบ / ≤24 ชม. แต่ไม่จำกัดยอดรวม (เพดาน 10 รอบเดิมกันโควตา Claude) — ต้องการเพดานรวมไหม
- หลัง merge: รัน `python flashq.py install` จาก checkout หลัก (คำสั่ง `/flash-goal` ใหม่ใช้ได้ใน session ใหม่) + รีสตาร์ต `flashq ui` — งานของผู้ใช้/ผู้สั่ง ไม่ใช่ Flash

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|
| T-01 | ✅แก้ | `80ec2cf` | แดง `.tmp/T-01.red.log` → `AssertionError: 'GOAL_ACK=FAIL' not found in ''` · เขียว `.tmp/T-01.green.log` → `1 passed, 183 deselected in 4.32s` · reg `.tmp/T-01.reg.log` → `2 passed, 182 deselected in 16.91s` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-02 | ✅แก้ | `745da37` | แดง `.tmp/T-02.red.log` → `AssertionError: 'GOAL_CHECK=FAIL' not found in ''` · เขียว `.tmp/T-02.green.log` → `1 passed, 184 deselected in 3.98s` · reg `.tmp/T-02.reg.log` → `2 passed, 183 deselected in 14.97s` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-03 | ✅แก้ | `a015901` | แดง `.tmp/T-03.red.log` → `AssertionError: 'goal ack docs/plans/GOAL_x.md' not found` · เขียว `.tmp/T-03.green.log` → `1 passed, 185 deselected in 1.85s` · reg `.tmp/T-03.reg.log` → `1 passed, 185 deselected in 9.53s` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-04 | ✅แก้ | `f076521` | `.tmp/T-04.node.log` = 0 ไบต์ · `.tmp/T-04.log` → `1 passed, 185 deselected in 0.15s` · `git show --stat HEAD` = `ui.html | 2 +-` 1 ไฟล์ | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-05 | ✅แก้ | `48a8997` | แดง `.tmp/T-05.red.log` → `AssertionError: 0 != 1` · เขียว `.tmp/T-05.green.log` → `1 passed, 186 deselected in 2.67s` · reg `.tmp/T-05.reg.log` → `4 passed, 183 deselected in 21.61s` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-06 | ✅แก้ | `061f7cf` | แดง `.tmp/T-06.red.log` → `AssertionError: 'review' != 'plan'` (`1 failed, 187 deselected`) · เขียว `.tmp/T-06.green.log` → `1 passed, 187 deselected in 2.48s` · reg `.tmp/T-06.reg.log` → `1 passed, 187 deselected in 7.46s` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-07 | ✅แก้ | `b168217` | `.tmp/T-07.log` → `2 passed, 186 deselected in 12.69s` · `git show HEAD` มี `stdin=subprocess.DEVNULL` + `p.wait(timeout=15)` ใน `goal_run_cmd` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-08 | ✅แก้ | `2e33021` | `.tmp/T-08.log` → `claude/commands/flash-goal.md:63:... \`{{FLASHQ_RUN}} status\`` + `5 passed, 183 deselected in 6.86s` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |
| T-09 | ✅แก้ | `5b785d1` | `.tmp/T-09.log` ขึ้น `3 files changed` (ไฟล์งาน 2 + แผนที่ agent หลักติ๊กค้าง) → scoped diff `2 files changed, 3 insertions(+), 1 deletion(-)` · `git grep -n "goal ack"` = `CHANGELOG.md:6` + `docs/REFERENCE.md:112` | ✅ผ่าน (diff ตรงสเปก แตะเฉพาะไฟล์ของงาน · แดง→เขียวตามหลักฐาน) |

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- การ์ด STOP `ui.html:2225` ยังบอก "แก้ต้นเหตุแล้วกด 🔄 ตรวจใหม่" (ไม่พูดถึง ack/extend) — ต้องเพิ่มวลีใหม่ + พจนานุกรม EN · ทำรอบหน้า
- งาน state `busy`/`queue_timeout` (ไม่ใช่ cancelled) ก็ยังทำให้การ์ดขึ้น "รอ Claude ตรวจ" ได้ — ยังไม่มีเคสจริง
- ปุ่ม 🤖 โหมด CLI ล็อกการ์ดตามอายุหน้าต่าง console (`flashq.py:7525`) · `write_json(sp, st)` ใน verify ไม่มี try · verify 2 ตัวพร้อมกันเขียน state ทับกัน · "พังซ้ำ" นับรอบ STOP ก่อนหน้าเป็นหลักฐานด้วย — จากผลสืบ ยังไม่ยืนยัน
- ทางเลือกคำนวณขอบเขตจาก `git diff --name-only base HEAD` (ผลสุทธิ) แทน ack — เปลี่ยนพฤติกรรมเดิมมากกว่า ไม่เลือก

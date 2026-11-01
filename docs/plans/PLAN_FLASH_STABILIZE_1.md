# แผน ทำให้คิวเสถียร 1 (ล็อก/เวลา + กันชน) — ส่งงานให้ DeepSeek Flash

> สร้าง 2026-11-01 · ส่งงาน: `python D:\MyCode\flashq\flashq.py run docs/plans/PLAN_FLASH_STABILIZE_1.md T-01..T-08 --switch-on-quota 4` · base commit ตอนวางแผน: `824c94a`
> แผนคู่: `PLAN_FLASH_STABILIZE_2.md` (ต้องรอแผนนี้ merge ก่อน)

## 0. กติกาผู้ทำ (อ่านก่อนเริ่มทุกงาน)
flashq-files: flashq.py, tests/test_flashq.py
flashq-parallel: yes

1. ทำทีละงานตามลำดับ · **1 งาน = 1 commit** (`git add -- flashq.py tests/test_flashq.py` เฉพาะไฟล์ที่งานนั้นแตะ + `git commit` ด้วยข้อความในช่อง commit ของงาน) · **ห้าม push** · ห้าม `git add -A` / `git add .` · ห้าม `git stash`
2. แก้เฉพาะไฟล์ในช่อง "ไฟล์" ของงานนั้น · ห้าม refactor/จัดรูปแบบ/แก้ comment อื่น/แปลง encoding
3. **เลขบรรทัดอาจเลื่อน** → หาจากข้อความใน "ก่อน" (Grep) · หาไม่เจอ/เจอหลายที่/ไม่ตรง → **หยุด ⛔** บันทึกใน §4
4. รันคำสั่งยืนยันของแต่ละงาน **ครั้งเดียว** ตามที่เขียนตรงตัว · FAIL → rerun 1 ครั้ง · ยังไม่ผ่าน = ⛔ หยุด
5. จบแต่ละงาน → ติ๊ก `[x]` + เติมแถว §4 (ผล · commit · หลักฐานชี้ขาด = path log + บรรทัด/ค่าตรงตัว) · หลักฐานไม่ครบ = งานไม่จบ
6. **ห้ามแตะ**: `%USERPROFILE%\.flashq\` ของจริง (เทสต์ใช้ `FLASHQ_HOME` ชั่วคราวผ่าน helper เดิม `load_mod`/`run_q` อยู่แล้ว) · `ui.html` · `claude/` `opencode/` `hooks/` · ห้ามเรียกโมเดลจริง (เทสต์ใช้ `fake_opencode.py` เท่านั้น) · ห้ามรัน `flashq run`/`flashq ui` พอร์ต 4097
7. **งานแบบ "เทสต์ก่อน"**: เขียนเทสต์ → รัน **ก่อนแก้โค้ด** ต้อง FAIL ด้วยเหตุที่แผนบอก (log แดง) → แก้โค้ด → รันซ้ำต้อง PASS (log เขียว) → commit เดียว · เทสต์ผ่านตั้งแต่ก่อนแก้ / ล้มด้วยเหตุอื่น (SyntaxError, AttributeError ของ helper ที่ไม่มี) → **⛔ หยุด** · ห้ามแก้เทสต์ให้ผ่านแทนการแก้โค้ด (ยกเว้นงานที่สั่งแก้เทสต์เดิมตรงตัว)
8. **ห้ามรายงานด้วยคำเดา** — ไม่ได้รันจริง = เขียนว่า "ไม่ได้รัน"
9. stdlib ล้วน ห้ามเพิ่ม dependency · ข้อความที่ผู้ใช้เห็น (print/WARN/เหตุผลคิว) เป็นภาษาไทย · commit ภาษาไทยขึ้นต้น `flashq:` และมี `(T-xx)` + trailer `Flash-Task: T-xx`
10. ไฟล์ชั่วคราว/ log ไว้ที่ `.tmp/` (อยู่ใน `.gitignore`) · ห้ามรันเทสต์ทั้งชุด (~6 นาที) — รันเฉพาะ `-k` ที่แผนกำหนด

### คำสั่งมาตรฐาน (PowerShell · timeout ≥ 300 วิ)
```
python -c "import ast,sys; ast.parse(open('flashq.py',encoding='utf-8').read())"
$env:PYTHONIOENCODING="utf-8"; python -m pytest tests/test_flashq.py -q -x -k "คำค้น" > .tmp/T-xx.red.log 2>&1
```
("คำค้น" = ค่า `-k` ที่แต่ละงานระบุ · `T-xx.red.log` เปลี่ยนชื่อ log ตามที่งานระบุ)

---

## 1. กลุ่ม A — ล็อก/เวลา (ช่องคิวค้าง · process ค้าง)
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว): `release` (flashq.py:925-929) ลบไฟล์ lock ด้วย `unlink` ครั้งเดียว — Windows ที่ไฟล์ถูกเปิดค้าง (antivirus/อีก process อ่านอยู่) ได้ `PermissionError` หลุดออกจาก `finally` ทำให้ช่องค้าง · `p.wait()` หลัง `kill_tree` (1689-1690, 1785-1786) ไม่มี timeout = ถ้า taskkill ไม่สำเร็จ runner ค้างตลอดไป · `clear_stale_lock` (828) เชื่อ `pid_alive` อย่างเดียว — lock เก่าที่ไม่มี `pid_start` + pid ถูกนำกลับมาใช้ = ช่องค้างถาวร

- [ ] **T-01** `flashq.py` ~925 (`release`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: เพิ่มคลาส/เมธอดใหม่ `test_release_retries_locked_file` (ใต้คลาสที่ใช้ `self.load_mod(...)` ได้): สร้าง `mod = self.load_mod("fq_rel")` · เขียน `mod.LOCK` (`running.lock` ใน `mod.HOME`) เนื้อหา JSON `{"id": "jobrel01", "pid": 1}` · เก็บ `orig = pathlib.Path.unlink` แล้ว `unittest.mock.patch.object(pathlib.Path, "unlink", autospec=True, side_effect=fn)` โดย `fn(self_, *a, **k)` โยน `PermissionError` 2 ครั้งแรกแล้วครั้งต่อไปคืน `orig(self_, *a, **k)` → `mod.release({"id": "jobrel01"})` ต้องไม่ raise และไฟล์ lock หายไป · กรณีที่ 2: side_effect โยน `PermissionError` ทุกครั้ง → `release` ต้องไม่ raise และ stdout (ใช้ `contextlib.redirect_stdout`) มีคำ `WARN`
  - แดง: `-k "release_retries"` → `.tmp/T-01.red.log` ต้อง FAIL ด้วย `PermissionError`
  - แก้ (สเปก): เขียนตัวเนื้อ `release` ใหม่ — ก่อน: `    for _, f in slot_files():` / `        if read_json(f).get("id") == job["id"]:` / `            f.unlink(missing_ok=True)` / `    (RUN_NOW / job["id"]).unlink(missing_ok=True)`
    - ต้องมี: ฟังก์ชันย่อย `_unlink_retry(f: Path, tries: int = 3, gap: float = 0.2) -> bool` ลองลบซ้ำได้ 3 ครั้งห่าง 0.2 วิ · `FileNotFoundError` = ถือว่าสำเร็จ · `OSError` อื่นครบ 3 ครั้ง = คืน False
    - `release` ใช้ `_unlink_retry` ทั้งไฟล์ช่องและ `RUN_NOW / job["id"]` · คืน False → `print(f"WARN: ลบไฟล์ล็อก {f.name} ไม่สำเร็จ (ไฟล์ถูกเปิดค้าง) — คิวจะเคลียร์เองเมื่อ process จบ", flush=True)` · **ห้ามโยน exception ออกจาก release** (ถูกเรียกใน `finally` 3 จุด)
  - เขียว: คำสั่งเดิม → `.tmp/T-01.green.log` PASS · แล้วรัน `-k "stale_lock or fifo_queue"` → `.tmp/T-01.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-01.red.log` มี `PermissionError` · เขียว `.tmp/T-01.green.log` บรรทัดท้าย `passed` ไม่มี `failed` · `.tmp/T-01.reg.log` `passed`
  - commit: `flashq: ลบไฟล์ล็อกซ้ำได้เมื่อไฟล์ถูกเปิดค้าง ไม่ทำให้ช่องคิวค้าง + เทสต์ (T-01)`

- [ ] **T-02** `flashq.py` ~1689 และ ~1785 (`_run_once`) · แก้ตรง (ทดสอบการค้างของ taskkill จริงไม่ได้ในเทสต์)
  - ก่อน (จุด 1 · เยื้อง 12 ช่อง): ค้นหาบรรทัด `            rc, status = -1, "NOSTART"` (เจอที่เดียว) · บรรทัดที่อยู่เหนือมันขึ้นไป 1 บรรทัดคือคำสั่งรอ process (p, จุด, wait, วงเล็บว่าง) เยื้อง 12 ช่อง — ให้แทนที่บรรทัดนั้นบรรทัดเดียว (ห้ามแตะ p.wait ของจุด 2)
  - หลัง (จุด 1):
    ```
                try:
                    p.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    print(f"WARN: ฆ่า opencode pid {p.pid} ไม่สำเร็จใน 30 วิ — ปล่อยไว้แล้วไปต่อ", flush=True)
                rc, status = -1, "NOSTART"
    ```
  - ก่อน (จุด 2 · เยื้อง 24 ช่อง): ค้นหาบรรทัด `                        rc, status = -1, "TIMEOUT"` (ให้ Grep ยืนยันว่าเจอที่เดียวพร้อม kill_tree อยู่เหนือขึ้นไป 2 บรรทัด) · บรรทัดที่อยู่เหนือมันขึ้นไป 1 บรรทัดคือคำสั่งรอ process (p, จุด, wait, วงเล็บว่าง) เยื้อง 24 ช่อง — ให้แทนที่บรรทัดนั้นบรรทัดเดียว
  - หลัง (จุด 2): แบบเดียวกับจุด 1 (try/`p.wait(timeout=30)`/except พร้อม WARN เดียวกัน) เยื้อง 24 ช่อง แล้วตามด้วย `rc, status = -1, "TIMEOUT"` เดิม
  - ยืนยัน: คำสั่ง ast.parse (ต้องไม่มี output) แล้ว `-k "stalled or nostart"` → `.tmp/T-02.log` PASS
  - หลักฐานชี้ขาด: `.tmp/T-02.log` บรรทัดท้าย `passed` ไม่มี `failed` · `git show --stat HEAD` แตะ `flashq.py` ไฟล์เดียว
  - commit: `flashq: รอ process ที่ถูกฆ่าไม่เกิน 30 วิ ไม่ค้างตลอดไปเมื่อ taskkill ไม่สำเร็จ (T-02)`

- [ ] **T-03** `flashq.py` ~828 (`clear_stale_lock`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_ancient_lock_without_pid_start_cleared` (วางใกล้ `test_reused_pid_not_blocking` · ใช้รูปแบบเขียน lock + job json แบบเทสต์นั้น): lock `{"id": "jobold01", "pid": os.getpid(), "since": "2000-01-01 00:00:00"}` (ไม่มี `pid_start`) + `jobs/jobold01.json` status `"ok"` → `run_q` งานใหม่ด้วย `--wait-min 0.2` ต้อง `returncode == 0` · กรณีคุม: lock เดียวกันแต่ job json status `"running"` → ยังต้องได้ `QUEUE_TIMEOUT`/returncode ≠ 0 (ไม่เคลียร์งานที่ยังรัน)
  - แดง: `-k "ancient_lock"` → `.tmp/T-03.red.log` FAIL ด้วย `3 != 0` (exit 3 = รอคิวเกินเวลา)
  - แก้: ก่อน: `        if held and pid_alive(held.get("pid", 0), held.get("pid_start", 0)):` · หลัง: `        if held and pid_alive(held.get("pid", 0), held.get("pid_start", 0)) and not lock_expired(held):`
    - ต้องมี (สเปก): ค่าคงที่ `STALE_LOCK_HOURS = 24` ใกล้ค่าคงที่ตัวอื่น · ฟังก์ชัน `lock_expired(held: dict) -> bool` วางเหนือ `clear_stale_lock` → True เมื่อครบ 3 ข้อ: `not held.get("pid_start")` · `_secs(held.get("since", ""))` ไม่เป็น None และ > `STALE_LOCK_HOURS*3600` · `read_json(JOBS / f"{held.get('id','')}.json").get("status")` ไม่อยู่ใน `("queued", "running")` · ห้ามเทียบ `pid_start` ของ lock กับของ job json (ดู §5)
  - เขียว: คำสั่งเดิม → `.tmp/T-03.green.log` PASS · แล้ว `-k "stale_lock or reused_pid"` → `.tmp/T-03.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-03.red.log` มี `3 != 0` · เขียว `.tmp/T-03.green.log` `passed` · `.tmp/T-03.reg.log` `passed`
  - commit: `flashq: เคลียร์ไฟล์ล็อกเก่าเกิน 24 ชม. ที่ไม่มี pid_start และงานจบแล้ว + เทสต์ (T-03)`

## 2. กลุ่ม C — กันชน (งานที่แตะไฟล์เดียวกันห้ามรันพร้อมกัน)
**สาเหตุ/หลักฐาน** (Claude ตรวจแล้ว): โหมด fifo (ค่าเริ่มต้น) ใน `acquire` บรรทัด 889-890 ดูแค่จำนวนช่อง ไม่เรียก `conflict_reason` เลย → `max_parallel ≥ 2` งานแตะไฟล์เดียวกันรันพร้อมกัน · `conflict_reason` (1184-1187) เช็คแค่ `None` — แผนที่ดึงไฟล์ได้ `[]` ถือว่าไม่ชน (fail-open) · `paths_overlap` (1060) ต้องมี `/` ท้าย ทำให้ `src` กับ `src/a.cpp` ไม่ชน · `plan_meta` (1110) ไม่แปลง path เต็มเป็น relative ต่างจาก `plan_files` (1031-1036) · `job_progressed` (1851-1856) นับ commit ของใครก็ได้ในโปรเจกต์ว่าเป็นผลงาน

- [ ] **T-04** `flashq.py` ~1060 (`paths_overlap`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: เพิ่มแอสเซิร์ตท้าย `test_plan_files_and_overlap`: `paths_overlap("src", "src/a.cpp")` True · `paths_overlap("Client/Src", "Client/Src/a.cpp")` True · `paths_overlap("src/a", "src/ab.cpp")` False · `paths_overlap("src/a.cpp", "lib/a.cpp")` False (เรียกผ่าน mod แบบที่เทสต์นั้นใช้อยู่)
  - แดง: `-k "plan_files_and_overlap"` → `.tmp/T-04.red.log` FAIL ด้วย `False is not true`
  - แก้: ก่อน: `    if a == b or (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b)):` · หลัง: `    if a == b or b.startswith(a.rstrip("/") + "/") or a.startswith(b.rstrip("/") + "/"):`
  - เขียว: คำสั่งเดิม → `.tmp/T-04.green.log` PASS · แล้ว `-k "overlap or conflict or declarations"` → `.tmp/T-04.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-04.red.log` มี `False is not true` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: โฟลเดอร์ที่ไม่มี / ท้ายนับว่าชนกับไฟล์ข้างใน + เทสต์ (T-04)`

- [ ] **T-05** `flashq.py` ~1110 (`plan_meta`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: เพิ่มใน `test_plan_declarations_and_conflicts` (หรือเมธอดใหม่ข้างกัน): แผน `M.md` เนื้อหา `f"# M\nflashq-files: {self.proj.as_posix()}/src/a.cpp\n- [ ] **T-01** แก้\n"` → `mod.plan_meta(str(self.proj), "M.md")["files"] == ["src/a.cpp"]`
  - แดง: `-k "declarations"` → `.tmp/T-05.red.log` FAIL ด้วย list ที่มี path เต็ม `!= ['src/a.cpp']`
  - แก้ (สเปก): ที่ `                dest.append(t.replace("\\", "/"))` — ก่อน append ถ้า `Path(t).is_absolute()` ให้แปลงเป็น `Path(t).relative_to(Path(project)).as_posix()` (ValueError = คงค่าเดิม) แบบเดียวกับ `plan_files` บรรทัด ~1031-1036 · ห้ามแตะ `plan_files`
  - เขียว: คำสั่งเดิม → `.tmp/T-05.green.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-05.red.log` มี `src/a.cpp` ใน AssertionError · เขียว บรรทัดท้าย `passed`
  - commit: `flashq: flashq-files ที่เป็น path เต็มแปลงเป็น path ในโปรเจกต์ก่อนตรวจชน + เทสต์ (T-05)`

- [ ] **T-06** `flashq.py` ~1184 (`conflict_reason`) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: ใน `test_plan_declarations_and_conflicts` เพิ่มแผน `L.md` เนื้อหา `"# L\n- [ ] **T-01** แก้ข้อความ\n"` (ไม่มี backtick ไม่มี flashq-files) → `c("L.md", "B.md")` (ใช้ lambda `c` เดิมของเทสต์) ต้องมีคำ `ไม่ระบุไฟล์`
  - แดง: `-k "declarations"` → `.tmp/T-06.red.log` FAIL ด้วย `'ไม่ระบุไฟล์' not found in ''`
  - แก้: ก่อน (2 บรรทัด): `    if ib["files"] is None:` / `        return "ดึงรายการไฟล์ของงานนั้นไม่ได้"` · หลัง: คง 2 บรรทัดเดิม แล้วต่อท้าย
    ```
        if not ia["files"]:
            return "แผนไม่ระบุไฟล์ที่งานนี้จะแตะ (ใส่ `path` บนหัวงานหรือ flashq-files: ในแผน)"
        if not ib["files"]:
            return "แผนของงานนั้นไม่ระบุไฟล์ที่จะแตะ"
    ```
  - เขียว: คำสั่งเดิม → `.tmp/T-06.green.log` PASS · แล้ว `-k "auto or conflict or overlap"` → `.tmp/T-06.reg.log` PASS (ถ้าเทสต์เดิมตัวไหนล้มเพราะคาดว่าแผนไม่มีไฟล์ = ไม่ชน → ⛔ หยุด บันทึกชื่อเทสต์ ห้ามแก้เทสต์นั้น)
  - หลักฐานชี้ขาด: แดง `.tmp/T-06.red.log` มี `not found in ''` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: แผนที่ไม่ระบุไฟล์ถือว่าชน ต้องรอ ไม่ปล่อยรันพร้อมกัน + เทสต์ (T-06)`

- [ ] **T-07** `flashq.py` ~889 (`acquire` โหมด fifo) + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์ (2 จุด):
    - แก้ `test_parallel_two_slots` ตรงตัว: เปลี่ยนแผนจาก `"# plan\n"` + งาน T-01/T-02 เป็นแผนจาก `self.overlap_plan()` + งาน **T-01 กับ T-03** (ไม่ชน → ยังรันพร้อมกันได้) · ห้ามเปลี่ยนแอสเซิร์ตอื่น
    - เทสต์ใหม่ `test_fifo_conflict_waits`: config `max_parallel: 2` schedule fifo (แบบ `test_parallel_two_slots`) · แผน `overlap_plan()` · ส่ง T-01 (FAKE_SLEEP ให้นานพอแบบเทสต์นั้น) แล้ว T-02 (ชน `src/a.cpp`) → ใช้ `jobs_by_tasks` ตรวจ `started` ของ T-02 ≥ `finished` ของ T-01 และ stdout ของ T-02 มี `ชนกับ`
  - แดง: `-k "fifo_conflict_waits"` → `.tmp/T-07.red.log` FAIL ด้วย `not greater than or equal to` (หรือ `'ชนกับ' not found`)
  - แก้ (สเปก): ในบล็อก `        else:` / `            can = not ahead and len(held) < limit` เพิ่มต่อจากบรรทัด `can = ...`: ถ้า `can` และ `job.get("plan")` → วน `jobs()` ที่ `live_state(r) == "running"` และ `r["id"] != job["id"]` และ `r.get("plan")` · `c = conflict_reason(job, r, job_info)` ไม่ว่าง → `can = False` · `reason = f"ชนกับ {r['id']}: {c}"` · `break` · งานที่ไม่มีแผน (brief/สืบ) คงพฤติกรรมเดิม · ไม่แตะสาขา auto
  - เขียว: คำสั่งเดิม → `.tmp/T-07.green.log` PASS · แล้ว `-k "parallel or fifo or run_now"` → `.tmp/T-07.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-07.red.log` มีข้อความ FAIL ข้างต้น · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: โหมด fifo รอเมื่องานแตะไฟล์ชนกับงานที่กำลังรัน + เทสต์ (T-07)`

- [ ] **T-08** `flashq.py` ~1851 (`job_progressed`) + ผู้เรียก ~1823 + `tests/test_flashq.py` · แบบ: เทสต์ก่อน
  - เทสต์: `test_progress_counts_only_own_commits` ใช้ `load_mod` + git repo ชั่วคราวใน `self.proj` (`git init` + commit แรก ด้วย `git -c user.name=t -c user.email=t@t`) · `head0 = rev-parse HEAD` · job = `{"plan": "PLAN.md", "tasks": "T-01..T-02"}` · (ก) commit ไฟล์ `x.txt` ข้อความ `"งาน B (T-05)"` → `mod.job_progressed(self.proj, head0, [], job)` False · (ข) commit อีกอันข้อความ `"แก้\n\nFlash-Task: T-01"` → True · (ค) จาก head ใหม่ commit แตะ `PLAN.md` ข้อความ `"อัปเดตแผน"` → True · (ง) เรียกแบบเดิมไม่ส่ง job (ข้อ ก) → True (พฤติกรรมเดิม)
  - แดง: `-k "own_commits"` → `.tmp/T-08.red.log` FAIL ด้วย `TypeError: job_progressed() takes 3 positional arguments but 4 were given` (เหตุที่คาดไว้ของงานนี้ — ไม่ใช่เหตุ ⛔ ตามกติกาข้อ 7)
  - แก้ (สเปก): ลายเซ็นใหม่ `def job_progressed(root: Path, head0: str, outputs: list[str], job: dict | None = None) -> bool:` · head เปลี่ยน + `job` มี `plan` → True เฉพาะเมื่อ (1) มี commit ใน `head0..head1` ที่ข้อความมี `T-\d+[A-Za-z]*` ซึ่ง `task_matcher(job.get("tasks",""))` รับ (ใช้ `git log --format=%B%x00 head0..head1`) หรือ (2) `git log --format= --name-only head0..head1 -- {job["plan"]}` (path แผนแบบ relative ต่อ root) ไม่ว่าง · ไม่เข้า 2 ข้อ → ตกไปเช็ค DONE ในบรรทัดท้ายเดิม · `task_matcher` คืน None = ถือว่าเป็นผลงาน (เดิม) · ผู้เรียก: `if status == "OK" and perm and not job_progressed(root, head0, texts + task_out):` → ส่ง `job` เป็นอาร์กิวเมนต์ที่ 4 · ค้นผู้เรียกอื่นด้วย Grep `job_progressed(` แล้วส่ง `job` ให้ทุกจุดใน `_run_once`
  - เขียว: คำสั่งเดิม → `.tmp/T-08.green.log` PASS · แล้ว `-k "without_commit or no_progress or own_commits"` → `.tmp/T-08.reg.log` PASS
  - หลักฐานชี้ขาด: แดง `.tmp/T-08.red.log` มี `TypeError` หรือ `True is not false` · เขียว/reg บรรทัดท้าย `passed`
  - commit: `flashq: นับความคืบหน้าเฉพาะ commit ของงานในแผนนี้ ไม่นับ commit ของ session อื่น + เทสต์ (T-08)`

## 3. ท้ายแผน (ไม่ยืนยัน · ห้ามแก้โค้ด)
- 🟡 **T-09** (ไม่อยู่ในช่วงส่งงาน · Claude ทำเองหลังตรวจ) พิสูจน์ว่า `pid_start` ใน job json ไม่ตรงกับใน lock จริงหรือไม่ — อ่านอย่างเดียว: Grep `pid_start` ใน `flashq.py` แล้วสรุปลง §4 ว่ามีกี่จุดที่เขียน และแต่ละจุดเรียก `proc_start` ด้วย pid ไหน (file:line) · **ห้ามแก้โค้ด ห้าม commit** · หลักฐาน: รายการ file:line ใน §4

## 3.5 งานที่ต้องให้ผู้ใช้ตัดสินใจ (**ห้ามทำเอง**)
- ค่า `STALE_LOCK_HOURS = 24` (T-03) — เลือกไว้กว้างเพื่อไม่ตัดงานยาว (`--timeout-min` ค่าเริ่ม 480 นาที)

---

## 4. บันทึกผล
| งาน | ผล (✅แก้/🟡ไม่ยืนยัน/⛔หยุด) | commit | หลักฐานชี้ขาด | ตรวจ Claude (✅ผ่าน/❌→T-xxR) |
|---|---|---|---|---|

## 5. นอกแผน (อ้างอิงเท่านั้น ห้ามทำ)
- นักทดสอบระดับ 3/4 · worktree แยกต่องาน (รอผู้ใช้ตัดสิน)
- ผู้สืบเรื่อง `pid_start` เพี้ยนใน job json (ต่อจาก T-09)
- สองแผนต่างไฟล์ที่ใช้เลข T-01 พร้อมกัน ยังทำให้ T-08 นับ commit ของอีกแผนได้ (ต้องดู trailer + path แผน — รอบถัดไป)

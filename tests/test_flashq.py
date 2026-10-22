"""เทสต์ flashq ด้วย opencode ปลอม (ไม่เรียกโมเดลจริง) · รัน: python tests\\test_flashq.py"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
FLASHQ = REPO / "flashq.py"
FAKE = Path(__file__).with_name("fake_opencode.py")


class FlashqTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="flashq_test_"))
        self.home = self.tmp / "home"
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        (self.proj / "PLAN.md").write_text("# plan\n", encoding="utf-8")
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False}), encoding="utf-8")
        cfg = {"agent": {"flash-worker": {"model": "p1/m"}},
               "provider": {"commandcode": {"models": {"deepseek/deepseek-v4.1-flash": {}}},
                            "commandcode2": {"models": {"deepseek/deepseek-v4.1-flash": {}}}}}
        self.oc_cfg = self.tmp / "opencode.json"
        self.oc_cfg.write_text(json.dumps(cfg), encoding="utf-8")
        self.args_out = self.tmp / "args.jsonl"
        self.env = {**os.environ, "FLASHQ_HOME": str(self.home), "FLASHQ_OPENCODE": str(FAKE),
                    "FLASHQ_OPENCODE_CONFIG": str(self.oc_cfg), "FAKE_ARGS_OUT": str(self.args_out),
                    "FLASHQ_NO_TOAST": "1"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_q(self, *args, env=None, wait=True):
        cmd = [sys.executable, str(FLASHQ), *args]
        e = {**self.env, **(env or {})}
        if wait:
            return subprocess.run(cmd, cwd=self.proj, env=e, capture_output=True, text=True,
                                  encoding="utf-8", timeout=120)
        return subprocess.Popen(cmd, cwd=self.proj, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8")

    def base(self):
        return ["run", "PLAN.md", "T-01", "--attach", "none", "--no-open"]

    def test_ok_passes_dir_command_model(self):
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=OK", r.stdout)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--dir") + 1], str(self.proj.resolve()))
        self.assertEqual(argv[argv.index("--model") + 1], "p1/m")
        self.assertEqual(argv[argv.index("--command") + 1:], ["flash", "--", "PLAN.md", "T-01"])
        self.assertFalse((self.home / "running.lock").exists())

    def test_ok_without_commit_or_done_warns(self):
        """exit 0 แต่ไม่มี commit ใหม่/DONE (worker หยุดถามผู้ใช้) = ยัง OK แต่ต้องเตือน · ส่งข้อความตรง (ไม่มีแผน) ไม่เตือน"""
        r = self.run_q(*self.base())
        self.assertIn("FLASH_RUN=OK", r.stdout)
        self.assertIn("WARN: สถานะ OK แต่ไม่มี commit ใหม่", r.stdout)
        r = self.run_q("run", "--message", "PONG", "--attach", "none", "--no-open")
        self.assertIn("FLASH_RUN=OK", r.stdout)
        self.assertNotIn("ไม่มี commit ใหม่", r.stdout)

    def test_missing_plan(self):
        r = self.run_q("run", "NOPE.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ไม่พบไฟล์แผน", r.stdout)

    def test_big_plan_warn_and_reject(self):
        """แผนใหญ่ = คนวางแผนเขียนโค้ดแทน Flash: เกินเพดานอ่อน (300/100/30) = เตือนแต่ส่ง · เกินเพดานแข็ง (600/200/60) หรือภาคผนวกโค้ด = ปฏิเสธ
        ไม่มีทางลัด (--big-plan ถูกตัด) · ยกเว้นส่งเฉพาะรอบแก้ T-xxR ของแผนที่เคยรันแล้ว = เตือนผ่าน · นับ fence ~~~~ ด้วย"""
        code = lambda n, f="```": f + "python\n" + "x = 1\n" * n + f + "\n"  # noqa: E731
        (self.proj / "BIG.md").write_text("# แผน\n" + code(250, "~~~~"), encoding="utf-8")
        r = self.run_q("run", "BIG.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("แผนใหญ่เกิน", r.stdout)
        self.assertIn("รวม 250 บรรทัด", r.stdout)
        self.assertIn("บล็อกโค้ดเดียวยาว 250 บรรทัด", r.stdout)
        r = self.run_q("run", "BIG.md", "T-01", "--attach", "none", "--no-open", "--big-plan")
        self.assertNotEqual(r.returncode, 0)  # ทางลัดเดิมไม่มีแล้ว
        self.assertIn("--big-plan", r.stderr)
        # โค้ดรวมไม่เกิน แต่บล็อกเดียวยาวเกิน 60 = ปฏิเสธ · บอกบรรทัดที่บล็อกเริ่ม
        (self.proj / "BLOCK.md").write_text("# แผน\n\nข้อความ\n" + code(61), encoding="utf-8")
        r = self.run_q("run", "BLOCK.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("บล็อกโค้ดเดียวยาว 61 บรรทัด (บรรทัด 4", r.stdout)
        # หัวข้อภาคผนวกที่มีโค้ด >20 บรรทัด = ปฏิเสธ แม้ขนาดรวมไม่เกิน
        (self.proj / "APP.md").write_text("# แผน\n- [ ] T-01 x\n\n## ภาคผนวก A — โค้ดเต็ม\n" + code(25), encoding="utf-8")
        r = self.run_q("run", "APP.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ภาคผนวก", r.stdout)
        (self.proj / "APPEN.md").write_text("# plan\n\n## Appendix: full code\n" + code(25), encoding="utf-8")
        self.assertEqual(self.run_q("run", "APPEN.md", "T-01", "--attach", "none", "--no-open").returncode, 1)
        (self.proj / "APPOK.md").write_text("# แผน\n\n## ภาคผนวก — หมายเหตุ\n" + code(5), encoding="utf-8")  # โค้ดสั้นในภาคผนวก = ผ่าน
        self.assertEqual(self.run_q("run", "APPOK.md", "T-01", "--attach", "none", "--no-open").returncode, 0)
        # เกินเพดานอ่อน = เตือนแต่ส่ง
        (self.proj / "MID.md").write_text("# แผน\n" + "".join(code(25) for _ in range(5)), encoding="utf-8")  # โค้ดรวม 125 บล็อกละ 25
        r = self.run_q("run", "MID.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("WARN: แผนใหญ่", r.stdout)
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "none", "--no-open")
        self.assertNotIn("แผนใหญ่", r.stdout)
        # รอบแก้ T-xxR ของแผนที่เคยรันแล้ว (MID.md มีประวัติ) → แผนโตเกินเพดานแข็งก็เตือนผ่าน · แผนไม่เคยรัน = ปฏิเสธ
        (self.proj / "MID.md").write_text("# แผน\n" + code(250), encoding="utf-8")
        r = self.run_q("run", "MID.md", "T-01R", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("รอบแก้", r.stdout)
        r = self.run_q("run", "MID.md", "T-01R,T-02", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1, r.stdout)
        r = self.run_q("run", "BIG.md", "T-01R", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_wait_blocks_until_done_and_reports(self):
        """wait <job|แผน> บล็อกจนงานจบแล้วพิมพ์ FLASH_RUN=... (exit 0 = OK · 1 = ไม่ OK/ไม่พบ · 3 = ยังไม่จบ)"""
        p1 = self.run_q(*self.base(), env={"FAKE_SLEEP": "5"}, wait=False)
        time.sleep(2.5)
        r = self.run_q("wait", "PLAN.md", "--timeout-min", "0.02", "--poll", "0.5")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("FLASH_WAIT=TIMEOUT", r.stdout)
        r = self.run_q("wait", "PLAN.md", "--poll", "0.5")
        p1.communicate(timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("FLASH_RUN=OK job=", r.stdout)
        self.assertIn("PLAN.md T-01", r.stdout)
        jid = re.search(r"job=(\S+)", r.stdout).group(1)
        r = self.run_q("wait", jid[:10])  # งานจบแล้ว = ตอบทันที
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.run_q("wait", "NOPE.md")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FLASH_WAIT=NOJOB", r.stdout)
        p2 = self.run_q(*self.base(), env={"FAKE_MODE": "fail"})
        self.assertIn("FLASH_RUN=FAIL", p2.stdout)
        r = self.run_q("wait", "PLAN.md")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=FAIL", r.stdout)

    def test_shrink_image(self):
        """shrink ย่อรูปใหญ่เป็น .tmp/shrink/<ชื่อ>.jpg ด้านยาว ≤ --max · พื้นโปร่งเป็นขาว"""
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("ไม่มี Pillow")
        Image.new("RGBA", (2400, 1200), (255, 0, 0, 0)).save(self.proj / "big.png")
        r = self.run_q("shrink", "big.png")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = self.proj / ".tmp" / "shrink" / "big.jpg"
        self.assertTrue(out.exists(), r.stdout)
        self.assertIn("2400x1200→800x400", r.stdout)
        self.assertEqual(Image.open(out).size, (800, 400))
        r = self.run_q("shrink", "missing.png")
        self.assertEqual(r.returncode, 1)
        self.assertIn("SHRINK=FAIL", r.stdout)

    def test_image_guard_hook(self):
        """hook กันอ่านรูป: ใหญ่ >1200px = บล็อก (exit 2 + วิธีย่อ) · รูปเล็กผ่าน · เกิน image_max_reads ต่อ session = บล็อก · ไฟล์ปิดยาม = ผ่าน · ไม่ใช่รูป/พัง = ผ่าน"""
        import struct
        import zlib
        guard = REPO / "hooks" / "image_guard.py"

        def png(path, w, h):  # PNG เล็กสุด (header ถูกต้องพอให้อ่านขนาด)
            def chunk(t, d):
                return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
            raw = zlib.compress(b"".join(b"\x00" + b"\x00" * (w * 3) for _ in range(h)))
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b""))

        def hook(file_path, session="s1"):
            data = json.dumps({"tool_name": "Read", "session_id": session, "tool_input": {"file_path": str(file_path)}})
            return subprocess.run([sys.executable, str(guard)], input=data, capture_output=True, text=True, encoding="utf-8",
                                  env=self.env, timeout=30)
        png(self.proj / "big.png", 1600, 900)
        png(self.proj / "small.png", 640, 480)
        r = hook(self.proj / "big.png")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("1600x900", r.stderr)
        self.assertIn("shrink", r.stderr)
        self.assertEqual(hook(self.proj / "small.png").returncode, 0)
        (self.proj / ".tmp" / "shrink").mkdir(parents=True)
        png(self.proj / ".tmp" / "shrink" / "big.jpg", 1600, 900)  # ไฟล์ที่ย่อแล้ว (ชื่อ .jpg เนื้อ png ก็อ่านได้) ไม่ตรวจขนาด
        self.assertEqual(hook(self.proj / ".tmp" / "shrink" / "big.jpg").returncode, 0)
        self.assertEqual(hook(self.proj / "PLAN.md").returncode, 0)
        self.assertEqual(hook(self.proj / "none.png").returncode, 0)
        (self.home).mkdir(parents=True, exist_ok=True)
        (self.home / "config.json").write_text(json.dumps({"image_max_reads": 3}), encoding="utf-8")
        self.assertEqual(hook(self.proj / "small.png").returncode, 0)  # s1 นับแล้ว 3 (small + shrink + นี้ · รูปที่ถูกบล็อกไม่นับ) → ครั้งถัดไปเกินเพดาน
        r = hook(self.proj / "small.png")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("อ่านรูปไปแล้ว", r.stderr)
        self.assertEqual(hook(self.proj / "small.png", session="s2").returncode, 0)  # session อื่นนับแยก
        (self.home / "image_guard_off").write_text("", encoding="utf-8")
        self.assertEqual(hook(self.proj / "big.png").returncode, 0)  # ปิดยาม
        self.assertEqual(subprocess.run([sys.executable, str(guard)], input="not json", capture_output=True, text=True,
                                        env=self.env, timeout=30).returncode, 0)

    PRECHECK_PLAN = """# แผน
- [ ] **T-01** `src\\a.cpp` (`f`)
  - ก่อน: `int x = 1;`
  - หลัง: `int x = 2;`
  - ยืนยัน: `sc out.txt 1` → ok
- [ ] **T-02** `src\\missing.h` + `src\\new.cpp` (ใหม่)
  - (1) `a.cpp` — ก่อน (ตรงตัว 2 บรรทัด):
    ```cpp
    	return y;
    }
    ```
    หลัง:
    ```cpp
    	return y + 1;
    }
    ```
  - แดง: `ls -la src` → FAIL
- [ ] **T-03** `src\\a.cpp`
  - ก่อน: `old_anchor();`
  - หลัง: `new_anchor();`
- [ ] **T-04** `src\\a.cpp`
  - ก่อน: `int x = 2;`
  - หลัง: `int x = 3;`
  - เขียว: `python -m pytest` → PASS
- [x] **T-05** `src\\gone.cpp`
  - ก่อน: `nothing();`
"""

    def write_precheck_proj(self):
        (self.proj / "src").mkdir()
        (self.proj / "src" / "a.cpp").write_text("int x = 1;\nint f() {\n\treturn y;\n}\nint g() {\n\treturn y;\n}\n", encoding="utf-8")
        (self.proj / "PRE.md").write_text(self.PRECHECK_PLAN, encoding="utf-8")

    def test_plan_precheck_unit(self):
        """ตรวจแผนพิการเชิงกลไก: path ไม่มีจริง (ยกเว้นไฟล์ใหม่) · ก่อน: เจอ 0/หลายครั้ง · alias PowerShell = เตือน"""
        sys.path.insert(0, str(REPO))
        import flashq
        self.write_precheck_proj()
        src = flashq.PlanSource(self.proj)
        text = self.PRECHECK_PLAN
        errs, warns = flashq.plan_precheck(text, "T-01", src)
        self.assertEqual(errs, [])
        self.assertTrue(any("`sc`" in w and "Set-Content" in w for w in warns), warns)
        errs, warns = flashq.plan_precheck(text, "T-02", src)
        self.assertTrue(any("ไม่พบไฟล์ `src\\missing.h`" in e for e in errs), errs)  # ข้อ 1
        self.assertFalse(any("new.cpp" in e for e in errs), errs)  # ไฟล์ที่บอกว่า (ใหม่) ยกเว้น
        self.assertTrue(any("บรรทัด 7 (T-02)" in e and "เจอ 2 ที่ (กำกวม" in e for e in errs), errs)  # ข้อ 2 หลายครั้ง
        self.assertTrue(any("`ls`" in w for w in warns), warns)  # ข้อ 3
        errs, _ = flashq.plan_precheck(text, "T-03", src)
        self.assertTrue(len(errs) == 1 and "ไม่เจอ" in errs[0] and "old_anchor" in errs[0], errs)  # ข้อ 2 ไม่เจอ
        errs, warns = flashq.plan_precheck(text, "T-04", src)  # anchor มาจาก "หลัง:" ของ T-01 → ไม่ถือว่าผิด · pytest ไม่ใช่ alias
        self.assertEqual((errs, warns), ([], []))
        self.assertEqual(flashq.plan_precheck(text, "T-05", src), ([], []))  # งานที่ติ๊กแล้วไม่ตรวจ
        # แผนบอกจำนวนที่เองตรงกับของจริง → ผ่าน
        ok = text.replace("ก่อน (ตรงตัว 2 บรรทัด)", "ก่อน (ต้องเจอ 2 ที่ แก้ทั้งสองที่)").replace("`src\\missing.h` + ", "")
        self.assertEqual(flashq.plan_precheck(ok, "T-02", src)[0], [])

    def test_plan_precheck_blocks_run(self):
        self.write_precheck_proj()
        r = self.run_q("run", "PRE.md", "T-03", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=FAIL แผนพิการ 1 จุด", r.stdout)
        self.assertIn("บรรทัด 19 (T-03)", r.stdout)
        r = self.run_q("run", "PRE.md", "T-03", "--attach", "none", "--no-open", "--skip-precheck")
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.run_q("run", "PRE.md", "T-01", "--attach", "none", "--no-open")  # เตือนอย่างเดียว ยังรัน
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("WARN: บรรทัด 5 (T-01): คำสั่ง `sc out.txt 1`", r.stdout)

    def test_fifo_queue_and_no_wait(self):
        p1 = self.run_q(*self.base(), env={"FAKE_SLEEP": "6"}, wait=False)
        time.sleep(2.5)
        busy = self.run_q(*self.base(), "--no-wait")
        self.assertEqual(busy.returncode, 2, busy.stdout)
        self.assertIn("FLASH_RUN=BUSY", busy.stdout)
        p2 = self.run_q(*self.base(), wait=False)
        time.sleep(2)
        st = self.run_q("status")
        self.assertIn("รอคิว: 1", st.stdout)
        o2 = p2.communicate(timeout=120)[0]
        o1 = p1.communicate(timeout=120)[0]
        self.assertIn("QUEUED", o2)
        self.assertIn("FLASH_RUN=OK", o1)
        self.assertIn("FLASH_RUN=OK", o2)
        jobs = [json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json")]
        done = sorted((j for j in jobs if j["status"] == "ok"), key=lambda j: j["started"])
        self.assertEqual(len(done), 2)
        self.assertLessEqual(done[0]["finished"], done[1]["started"])  # ไม่ซ้อนกัน

    def test_stale_lock_cleared(self):
        self.home.mkdir(parents=True)
        (self.home / "running.lock").write_text(json.dumps({"id": "old", "pid": 999999}), encoding="utf-8")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_reused_pid_not_blocking(self):
        """ล็อก/งานรอคิวที่ pid ยังมีชีวิตแต่เวลาเริ่มไม่ตรง (pid ถูกใช้ซ้ำ) ต้องไม่ขวางคิว"""
        (self.home / "jobs").mkdir(parents=True)
        me = os.getpid()
        (self.home / "running.lock").write_text(json.dumps({"id": "old", "pid": me, "pid_start": 1}), encoding="utf-8")
        (self.home / "jobs" / "0_old.json").write_text(json.dumps(
            {"id": "0_old", "status": "queued", "pid": me, "pid_start": 1, "created": "2000-01-01 00:00:00",
             "project": str(self.proj)}), encoding="utf-8")
        r = self.run_q(*self.base(), "--wait-min", "0.2")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_quota_switch(self):
        r = self.run_q(*self.base(), "--switch-on-quota", "1", env={"FAKE_MODE": "quota"})
        self.assertIn("FLASH_RUN=QUOTA", r.stdout)
        self.assertIn("สลับบัญชี", r.stdout)
        cfg = json.loads(self.oc_cfg.read_text(encoding="utf-8"))
        self.assertEqual(cfg["agent"]["flash-worker"]["model"], "commandcode/deepseek/deepseek-v4.1-flash")
        self.assertEqual(len(self.args_out.read_text(encoding="utf-8").splitlines()), 2)

    def test_quota_ignores_balance_word_in_summary(self):
        """คำว่า balance ในสรุปท้ายของ worker (เนื้องานเกม) ต้องไม่ถูกตีเป็นโควตาหมด"""
        r = self.run_q(*self.base(), env={"FAKE_MODE": "failbalance"})
        self.assertIn("FLASH_RUN=FAIL", r.stdout)
        self.assertNotIn("FLASH_RUN=QUOTA", r.stdout)

    def test_quota_when_worker_reports_fail_quota(self):
        r = self.run_q(*self.base(), env={"FAKE_MODE": "failquota"})
        self.assertIn("FLASH_RUN=QUOTA", r.stdout)

    def test_branch_preflight(self):
        """checkout หลักไม่อยู่บน main_branch → FAIL พร้อมสาเหตุ ไม่ส่งงานให้ opencode · กลับ master แล้วรันได้"""
        git = lambda *a: subprocess.run(["git", "-C", str(self.proj), *a], capture_output=True, text=True)
        git("init", "-q")
        git("symbolic-ref", "HEAD", "refs/heads/feature")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ไม่ใช่ master", r.stdout)
        self.assertFalse(self.args_out.exists())
        git("symbolic-ref", "HEAD", "refs/heads/master")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=OK", r.stdout)

    def test_quota_no_switch_by_default(self):
        r = self.run_q(*self.base(), env={"FAKE_MODE": "quota"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("FLASH_RUN=QUOTA", r.stdout)
        self.assertEqual(len(self.args_out.read_text(encoding="utf-8").splitlines()), 1)

    def test_cancel_queued(self):
        p1 = self.run_q(*self.base(), env={"FAKE_SLEEP": "8"}, wait=False)
        time.sleep(2.5)
        p2 = self.run_q(*self.base(), wait=False)
        time.sleep(2.5)
        queued = [json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json")]
        q = [j for j in queued if j["status"] == "queued"]
        self.assertEqual(len(q), 1)
        c = self.run_q("cancel", q[0]["id"])
        self.assertEqual(c.returncode, 0, c.stdout)
        p2.wait(timeout=30)
        self.assertIn("FLASH_RUN=OK", p1.communicate(timeout=120)[0])

    def test_install_claude_and_opencode(self):
        claude = self.tmp / "claude_home"
        env = {"FLASHQ_CLAUDE_HOME": str(claude)}
        (claude / "commands").mkdir(parents=True)
        (claude / "commands" / "flash-check.md").write_text("ของผู้ใช้เอง\n", encoding="utf-8")
        r = self.run_q("install", env=env)
        self.assertEqual(r.returncode, 1, r.stdout)  # ข้ามไฟล์ที่ไม่ได้มาจาก flashq
        plan = (claude / "commands" / "flash-plan.md").read_text(encoding="utf-8")
        self.assertIn("flashq:managed", plan)
        self.assertNotIn("{{FLASHQ}}", plan)
        self.assertEqual((claude / "commands" / "flash-check.md").read_text(encoding="utf-8"), "ของผู้ใช้เอง\n")
        self.assertTrue((self.tmp / "command" / "flash.md").exists())
        self.assertTrue((claude / "agents" / "flash-checker.md").exists(), r.stdout)
        self.assertTrue((claude / "hooks" / "image_guard.py").exists(), r.stdout)
        self.assertNotIn("{{FLASHQ}}", (claude / "hooks" / "image_guard.py").read_text(encoding="utf-8"))
        self.assertIn("ยังไม่ได้ลงทะเบียน image_guard", r.stdout)
        r = self.run_q("install", "--force", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("flashq:managed", (claude / "commands" / "flash-check.md").read_text(encoding="utf-8"))
        self.assertTrue(list((claude / "commands").glob("flash-check.md.bak-flashq-*")))
        # ไฟล์ที่ flashq ติดตั้งเองเปลี่ยน = ทับเลย ไม่สำรอง (ต้นฉบับอยู่ใน git)
        (claude / "commands" / "flash-plan.md").write_text(plan + "\nแก้ทดลอง\n", encoding="utf-8")
        r = self.run_q("install", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((claude / "commands" / "flash-plan.md").read_text(encoding="utf-8"), plan)
        self.assertFalse(list((claude / "commands").glob("flash-plan.md.bak-flashq-*")))
        # --hooks ลงทะเบียนใน settings.json แบบทำซ้ำได้ · ไม่ทับค่าอื่น
        (claude / "settings.json").write_text(json.dumps({"model": "claude-sonnet-5", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}}), encoding="utf-8")
        r = self.run_q("install", "--hooks", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("ลงทะเบียน", r.stdout)
        st = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(st["model"], "claude-sonnet-5")
        self.assertEqual(len(st["hooks"]["Stop"]), 1)
        pre = st["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertEqual(pre[0]["matcher"], "Read")
        self.assertIn("image_guard.py", pre[0]["hooks"][0]["command"])
        r = self.run_q("install", "--hooks", env=env)
        self.assertIn("เหมือนเดิม  hook", r.stdout)
        self.assertEqual(len(json.loads((claude / "settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]), 1)
        ups = json.loads((claude / "settings.json").read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(ups), 1)
        self.assertIn("inbox_notify.py", ups[0]["hooks"][0]["command"])

    def test_notify_inbox_and_hook(self):
        """งานจบ → inbox · hook UserPromptSubmit แทรกผลให้ session ที่สั่ง (หรือโปรเจกต์เดียวกัน) ครั้งเดียวแล้วย้ายเข้า done · session อื่นไม่ได้ · notify=false = เงียบ"""
        hook = REPO / "hooks" / "inbox_notify.py"

        def run_hook(session, cwd):
            return subprocess.run([sys.executable, str(hook)], input=json.dumps({"session_id": session, "cwd": str(cwd)}),
                                  capture_output=True, text=True, encoding="utf-8", env=self.env, timeout=30)
        self.assertEqual(run_hook("s1", self.proj).stdout, "")  # ไม่มี inbox = เงียบ
        r = self.run_q(*self.base(), env={"CLAUDE_CODE_SESSION_ID": "s1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = list((self.home / "inbox").glob("*.json"))
        self.assertEqual(len(files), 1)
        row = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual((row["status"], row["session"], row["plan"]), ("OK", "s1", "PLAN.md"))
        self.assertEqual(run_hook("s2", self.proj.parent).stdout, "")  # session อื่น คนละโฟลเดอร์ = ไม่ได้
        self.assertEqual(run_hook("s2", self.proj).stdout, "")  # session อื่นในโปรเจกต์เดียวกัน แต่ยังไม่ค้างเกิน 30 นาที = ไม่ได้
        out = run_hook("s1", self.proj).stdout
        self.assertIn(row["job"], out)
        self.assertIn("/flash-check PLAN.md", out)
        self.assertFalse(list((self.home / "inbox").glob("*.json")))
        self.assertTrue(list((self.home / "inbox" / "done").glob("*.json")))
        self.assertEqual(run_hook("s1", self.proj).stdout, "")  # ส่งครั้งเดียว
        # session เดิมหายไปนาน → session อื่นในโปรเจกต์เดียวกันรับแทนได้
        row.update(at=row["at"] - 7200)
        (self.home / "inbox" / "old.json").write_text(json.dumps(row), encoding="utf-8")
        self.assertIn(row["job"], run_hook("s9", self.proj).stdout)
        # งานล้ม → คำแนะนำเป็นการดูสาเหตุ ไม่ใช่ /flash-check
        row.update(status="DENIED", at=time.time(), last="ถูกปฏิเสธ")
        (self.home / "inbox" / "d.json").write_text(json.dumps(row), encoding="utf-8")
        out = run_hook("s1", self.proj).stdout
        self.assertIn("DENIED", out)
        self.assertNotIn("/flash-check", out)
        # ปิดด้วย config
        (self.home / "config.json").write_text(json.dumps({"notify": False}), encoding="utf-8")
        (self.home / "inbox" / "e.json").write_text(json.dumps(row), encoding="utf-8")
        self.assertEqual(run_hook("s1", self.proj).stdout, "")
        for f in (self.home / "inbox").glob("*.json"):
            f.unlink()
        self.run_q(*self.base(), env={"CLAUDE_CODE_SESSION_ID": "s1"})
        self.assertFalse(list((self.home / "inbox").glob("*.json")))  # notify=false → flashq ไม่เขียน inbox

    def test_sweep_dead_job_notifies_once(self):
        """process ของงานตายกลางคัน (ไม่มีใครเขียน inbox) → flashq sweep แจ้ง DEAD ครั้งเดียวต่องาน"""
        (self.home / "jobs").mkdir(parents=True, exist_ok=True)
        job = {"id": "deadjob1", "status": "running", "pid": 99999999, "pid_start": 0, "project": str(self.proj),
               "plan": "PLAN.md", "tasks": "T-01", "claude_session": "s1", "created": "2026-10-22T10:00:00", "last": "ทำไปครึ่งทาง"}
        (self.home / "jobs" / "deadjob1.json").write_text(json.dumps(job), encoding="utf-8")
        r = self.run_q("sweep")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = list((self.home / "inbox").glob("*.json"))
        self.assertEqual(len(files), 1)
        row = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual((row["status"], row["session"], row["job"]), ("DEAD", "s1", "deadjob1"))
        self.run_q("sweep")
        self.assertEqual(len(list((self.home / "inbox").glob("*.json"))), 1)  # แจ้งซ้ำไม่ได้

    def test_claude_check_button_opens_new_session(self):
        """ปุ่ม "เปิด Claude ตรวจ": งานจบ → ลิงก์ session ใหม่พิมพ์ข้อความรอ (OK = /flash-check · ล้ม = ดูสาเหตุ) · งานยังรัน = ปฏิเสธ · กดซ้ำเร็ว ๆ = ปฏิเสธ · ไม่มีแอป+ไม่มี CLI = คืนข้อความให้คัดลอก"""
        mod = self.load_mod("flashq_ccheck")
        opened = []
        mod.open_link = opened.append
        mod.claude_app_link = lambda path, params: f"claude://code/{path}?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        base = {"project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01", "pid": os.getpid(), "pid_start": 0}
        ok = dict(base, id="jobok001", status="done", result="ok")
        bad = dict(base, id="jobbad01", status="done", result="denied")
        run = dict(base, id="jobrun01", status="running", pid=os.getpid(), pid_start=mod.proc_start(os.getpid()))
        for j in (ok, bad, run):
            mod.save_job(j)
        self.assertEqual(mod.claude_check_action(run)[0], 409)  # ยังรันอยู่
        code, r = mod.claude_check_action(ok)
        self.assertEqual(code, 200, r)
        self.assertTrue(opened[-1].startswith("claude://code/new?q=%2Fflash-check%20PLAN.md"), opened)
        self.assertIn("&folder=", opened[-1])
        self.assertEqual(mod.claude_check_action(mod.read_json(mod.JOBS / "jobok001.json"))[0], 409)  # กดซ้ำภายใน 60 วิ
        code, r = mod.claude_check_action(bad)
        self.assertEqual(code, 200, r)
        self.assertIn("DENIED", urllib.parse.unquote(opened[-1]))
        self.assertNotIn("flash-check", urllib.parse.unquote(opened[-1]))
        mod.claude_app_link = lambda path, params: ""
        mod.claude_exe = lambda: ""
        code, r = mod.claude_check_action(dict(base, id="jobok002", status="done", result="ok"))
        self.assertEqual(code, 404)
        self.assertEqual(r["prompt"], "/flash-check PLAN.md")

    def start_ui(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        p = subprocess.Popen([sys.executable, str(FLASHQ), "ui", "--port", str(port), "--no-open"], cwd=self.proj,
                             env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        self.addCleanup(lambda: (p.kill(), p.communicate(timeout=30)))
        line = p.stdout.readline()
        self.assertIn("UI_URL=", line)
        return f"http://127.0.0.1:{port}"

    def http(self, url, data=None, headers=None):
        req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
        for attempt in range(4):  # Windows loopback: คำขอหน้าใหญ่ค้าง/รีเซ็ตเป็นระยะ ~5-9% (http.server มาตรฐานก็เป็น) → timeout สั้น + ลองซ้ำ
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, r.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8")
            except (ConnectionResetError, TimeoutError, urllib.error.URLError):
                if attempt == 3:
                    raise
                time.sleep(0.5)

    def test_ui_office_tab_and_script_syntax(self):
        """ui: หน้าเว็บมีแท็บออฟฟิศ · สคริปต์ในหน้าไม่มี syntax error (ตรวจด้วย node ถ้ามี)"""
        (self.home / "jobs").mkdir(parents=True)
        base = self.start_ui()
        code, html = self.http(base + "/")
        self.assertEqual(code, 200)
        for marker in ('id="officeView"', 'id="dashView"', 'data-view="office"', "function officeUpdate", "function estimate"):
            self.assertIn(marker, html)
        node = shutil.which("node")
        if node:
            script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
            f = self.home / "ui_script.js"
            f.write_text(script, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_review_start_accepts_many_task_args(self):
        """review start รับงานหลายตัวได้ทั้งแบบแยกอาร์กิวเมนต์ (T-01 T-12) และแบบเครื่องหมายคำพูด (เหมือน verify)"""
        for args, want in ((("T-01", "T-12"), "T-01 T-12"), (("T-01 T-02",), "T-01 T-02"), ((), "")):
            r = self.run_q("review", "start", "docs/plans/PLAN_X_FLASH.md", *args)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rows = [json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "reviews").glob("rv_*.json")]
            self.assertEqual([x["tasks"] for x in rows], [want])  # แผนเดียวกันเริ่มใหม่ = ทับป้ายเก่า

    def test_plan_trail(self):
        """การ์ดงานบอกเส้นทางของแผน: ผู้สืบก่อนแผน (≤6 ชม. โปรเจกต์เดียวกัน) · เคยรัน · ผู้ตรวจ · Claude ตรวจ — ไม่นับงานหลังจากนี้/โปรเจกต์อื่น"""
        mod = self.load_mod("flashq_trail")
        P = "docs/PLAN_A.md"
        row = {"id": "J9", "plan": P, "project_name": "p", "created": "2026-10-20 20:00:00"}
        rows = [row,
                {"id": "S1", "agent": "flash-investigator", "message": "ผู้สืบ (อ่านอย่างเดียว) — ภาพย่อซ้อนกัน\nรายละเอียด", "project_name": "p", "state": "ok", "finished": "2026-10-20 19:30:00"},
                {"id": "S2", "agent": "flash-investigator", "message": "x", "project_name": "p", "state": "ok", "finished": "2026-10-20 10:00:00"},  # เก่าเกิน 6 ชม.
                {"id": "S3", "agent": "flash-investigator", "message": "x", "project_name": "q", "state": "ok", "finished": "2026-10-20 19:40:00"},  # โปรเจกต์อื่น
                {"id": "W1", "plan": "D:/x/docs/PLAN_A.md", "kind": "work", "project_name": "p", "state": "ok", "tasks": "T-01", "created": "2026-10-20 19:50:00", "finished": "2026-10-20 19:55:00"},
                {"id": "V1", "plan": P, "kind": "verify", "project_name": "p", "state": "fail", "created": "2026-10-20 19:56:00", "finished": "2026-10-20 19:58:00"},
                {"id": "W2", "plan": P, "kind": "work", "project_name": "q", "state": "ok", "finished": "2026-10-20 19:55:00"},  # ชื่อแผนเดียวกันแต่โปรเจกต์อื่น
                {"id": "W3", "plan": P, "kind": "work", "project_name": "p", "state": "ok", "finished": "2026-10-20 21:00:00"}]  # จบหลังงานนี้เริ่ม
        rv = [{"plan_name": "PLAN_A.md", "status": "fail", "started": "2026-10-20 19:57:00", "finished": "2026-10-20 19:59:00"},
              {"plan_name": "PLAN_B.md", "status": "pass", "started": "2026-10-20 19:57:00"}]
        t = mod.plan_trail(row, rows, rv)
        self.assertEqual(([r["id"] for r in t["runs"]], [r["id"] for r in t["checks"]], [r["status"] for r in t["reviews"]]), (["W1"], ["V1"], ["fail"]))
        self.assertEqual(([s["id"] for s in t["sleuths"]], t["sleuths"][0]["what"]), (["S1"], "ภาพย่อซ้อนกัน"))  # นับจากรอบแรกของแผน (19:50) ย้อน 6 ชม.
        self.assertEqual(mod.plan_trail({"id": "M", "message": "hi", "project_name": "p"}, rows, rv), {})  # ข้อความทดสอบ = ไม่มีแผน

    def test_review_markers_and_log_idle(self):
        """review: start/done ทำป้ายผู้ตรวจที่ /api/state เห็น (reviews → reviews_done) · งานที่รันมี log_idle_sec"""
        sys.path.insert(0, str(REPO))
        import flashq
        r = self.run_q("review", "start", "docs/plans/PLAN_X_FLASH.md", "T-01..T-02")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("REVIEW=START", r.stdout)
        old_home = flashq.HOME
        try:
            flashq.HOME = self.home
            flashq.REVIEWS = self.home / "reviews"
            act, done = flashq.ui_reviews()
            self.assertEqual([(x["plan_name"], x["tasks"]) for x in act], [("PLAN_X_FLASH.md", "T-01..T-02")])
            self.assertEqual(done, [])
            r = self.run_q("review", "done", "PLAN_X_FLASH.md", "pass")
            self.assertIn("REVIEW=PASS", r.stdout)
            act, done = flashq.ui_reviews()
            self.assertEqual((act, [x["status"] for x in done]), ([], ["pass"]))
            self.assertEqual(self.run_q("review", "done", "PLAN_X_FLASH.md", "fail").returncode, 0)  # ไม่มีป้ายค้าง = ข้ามเฉย ๆ
            self.assertNotEqual(self.run_q("review", "done", "PLAN_X_FLASH.md", "maybe").returncode, 0)
            log = self.home / "idle.jsonl"
            log.write_text("x", encoding="utf-8")
            self.assertLess(flashq.log_idle_sec({"logs": [str(log)]}), 5)
            self.assertIsNone(flashq.log_idle_sec({"logs": [str(self.home / "none.jsonl")]}))
            self.assertIsNone(flashq.log_idle_sec({}))
            # ป้ายยามเก่า (ตัวคุมงานหยุดเฝ้าแล้ว) ไม่แสดง · ใหม่แสดง
            self.assertIsNone(flashq._fresh_shell_watch({"shell_watch": {"state": "killed", "at": "2020-01-01 00:00:00"}}))
            self.assertIsNone(flashq._fresh_shell_watch({}))
            self.assertEqual(flashq._fresh_shell_watch({"shell_watch": {"state": "suspect", "at": flashq.now()}})["state"], "suspect")
        finally:
            flashq.HOME = old_home
            flashq.REVIEWS = old_home / "reviews"

    def test_ui_state_and_cancel(self):
        """ui: /api/state เป็น JSON · POST ไม่มี token = 403 · token ถูก = ยกเลิกงานที่รอคิวได้"""
        sys.path.insert(0, str(REPO))
        import flashq
        (self.home / "jobs").mkdir(parents=True)
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait(timeout=30)))
        jid = "20990101_000000_1"
        (self.home / "jobs" / f"{jid}.json").write_text(json.dumps(
            {"id": jid, "status": "queued", "pid": sleeper.pid, "pid_start": flashq.proc_start(sleeper.pid),
             "created": "2099-01-01 00:00:00", "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01"}), encoding="utf-8")
        base = self.start_ui()

        code, body = self.http(base + "/api/state")
        self.assertEqual(code, 200)
        st = json.loads(body)
        self.assertIsNone(st["running"])
        self.assertEqual([j["id"] for j in st["queued"]], [jid])
        self.assertEqual(st["queued"][0]["position"], 1)
        self.assertEqual(st["current_model"], "p1/m")
        self.assertTrue(any(a["short"] == "cc" for a in st["accounts"]))

        code, html = self.http(base + "/")
        self.assertEqual(code, 200)
        token = re.search(r'const TOKEN = "([^"]+)"', html).group(1)
        self.assertNotEqual(token, "{{TOKEN}}")

        payload = json.dumps({"id": jid}).encode()
        hdr = {"Content-Type": "application/json"}
        self.assertEqual(self.http(base + "/api/cancel", payload, hdr)[0], 403)
        self.assertEqual(self.http(base + "/api/cancel", payload, {**hdr, "X-Flashq-Token": "ผิด".encode().hex()})[0], 403)
        self.assertEqual(self.http(base + "/api/cancel", payload,
                                   {**hdr, "X-Flashq-Token": token, "Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.http(base + "/api/state", headers={"Host": "evil.example"})[0], 403)

        code, body = self.http(base + "/api/cancel", payload, {**hdr, "X-Flashq-Token": token})
        self.assertEqual(code, 200, body)
        self.assertTrue(json.loads(body)["ok"])
        sleeper.wait(timeout=30)  # process ของงานถูก kill
        job = json.loads((self.home / "jobs" / f"{jid}.json").read_text(encoding="utf-8"))
        self.assertEqual(job["status"], "cancelled")
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["queued"], [])
        self.assertEqual(st["history"][0]["state"], "cancelled")

        code, body = self.http(base + "/api/switch", json.dumps({"target": "cc2"}).encode(), {**hdr, "X-Flashq-Token": token})
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(self.oc_cfg.read_text(encoding="utf-8"))["agent"]["flash-worker"]["model"],
                         "commandcode2/deepseek/deepseek-v4.1-flash")

    def test_ui_log_tail_offset(self):
        """ui: /api/log อ่านต่อจาก offset เฉพาะบรรทัดที่จบแล้ว"""
        (self.home / "jobs").mkdir(parents=True)
        (self.home / "logs").mkdir(parents=True)
        log = self.home / "logs" / "j_1.jsonl"
        log.write_text(json.dumps({"type": "text", "part": {"text": "สวัสดี"}}) + "\n" + '{"type":"te', encoding="utf-8")
        (self.home / "jobs" / "j.json").write_text(json.dumps(
            {"id": "j", "status": "ok", "created": "2026-01-01 00:00:00", "project": str(self.proj), "logs": [str(log)]}),
            encoding="utf-8")
        base = self.start_ui()
        d = json.loads(self.http(base + "/api/log?id=j&offset=0")[1])
        self.assertEqual(d["lines"], ["สวัสดี"])
        with open(log, "a", encoding="utf-8") as f:
            f.write('xt","part":{"text":"PONG"}}\n')
        d2 = json.loads(self.http(base + f"/api/log?id=j&offset={d['offset']}")[1])
        self.assertEqual(d2["lines"], ["PONG"])
        self.assertEqual(d2["offset"], log.stat().st_size)

    def test_ui_stop_running_and_dead(self):
        """ui: หยุดงานที่กำลังทำ (ต้อง confirm=id · สั่ง abort session บน server) + ป้ายงานที่ process ตาย + รับทราบ"""
        import http.server
        import threading
        sys.path.insert(0, str(REPO))
        import flashq
        hits = []

        class Fake(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "4")
                self.end_headers()
                self.wfile.write(b"true")

            def log_message(self, *a):
                pass
        oc = http.server.HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=oc.serve_forever, daemon=True).start()
        self.addCleanup(oc.shutdown)

        (self.home / "jobs").mkdir(parents=True)
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait(timeout=30)))
        st0 = flashq.proc_start(sleeper.pid)
        run_id, dead_id = "20990101_000000_2", "20980101_000000_3"
        (self.home / "running.lock").write_text(json.dumps({"id": run_id, "pid": sleeper.pid, "pid_start": st0}), encoding="utf-8")
        (self.home / "jobs" / f"{run_id}.json").write_text(json.dumps(
            {"id": run_id, "status": "running", "pid": sleeper.pid, "pid_start": st0, "session": "ses_x",
             "attach": f"http://127.0.0.1:{oc.server_address[1]}", "created": "2099-01-01 00:00:00",
             "started": "2099-01-01 00:00:01", "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01"}), encoding="utf-8")
        (self.home / "jobs" / f"{dead_id}.json").write_text(json.dumps(
            {"id": dead_id, "status": "running", "pid": 999999, "created": "2098-01-01 00:00:00",
             "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-02"}), encoding="utf-8")
        base = self.start_ui()
        token = re.search(r'const TOKEN = "([^"]+)"', self.http(base + "/")[1]).group(1)
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": token}

        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["running"]["id"], run_id)
        self.assertEqual([d["id"] for d in st["dead"]], [dead_id])
        self.assertIn("run PLAN.md T-02 --project", st["dead"][0]["rerun"])

        self.assertEqual(self.http(base + "/api/stop", json.dumps({"id": run_id}).encode(), hdr)[0], 400)
        self.assertEqual(self.http(base + "/api/stop", json.dumps({"id": run_id, "confirm": run_id}).encode(),
                                   {"Content-Type": "application/json"})[0], 403)
        code, body = self.http(base + "/api/stop", json.dumps({"id": run_id, "confirm": run_id}).encode(), hdr)
        self.assertEqual(code, 200, body)
        self.assertIn("หยุด session ses_x", json.loads(body)["message"])
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].startswith("/session/ses_x/abort?directory="), hits)
        sleeper.wait(timeout=30)
        self.assertFalse((self.home / "running.lock").exists())

        code, body = self.http(base + "/api/dismiss", json.dumps({"id": dead_id}).encode(), hdr)
        self.assertEqual(code, 200, body)
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertIsNone(st["running"])
        self.assertEqual(st["dead"], [])
        self.assertEqual({h["id"]: h["state"] for h in st["history"]}, {run_id: "cancelled", dead_id: "dead"})

    def test_ui_second_instance_reuses(self):
        """เปิด ui ซ้ำพอร์ตเดิม → ไม่ bind ซ้อน (Windows SO_REUSEADDR) แต่บอกว่าเปิดอยู่แล้วและจบ 0"""
        base = self.start_ui()
        r = self.run_q("ui", "--port", base.rsplit(":", 1)[1], "--no-open")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("เปิดอยู่แล้ว", r.stdout)

    def ui_token(self, base):
        return re.search(r'const TOKEN = "([^"]+)"', self.http(base + "/")[1]).group(1)

    def wait_job(self, jid, want="ok", sec=90):
        f = self.home / "jobs" / f"{jid}.json"
        t0 = time.time()
        while time.time() - t0 < sec:
            if f.exists():
                st = json.loads(f.read_text(encoding="utf-8")).get("status")
                if st == want:
                    return
            time.sleep(0.3)
        self.fail(f"งาน {jid} ไม่เป็น {want} ภายใน {sec} วิ")

    def test_ui_submit_retry_plans(self):
        """ui: รายการแผน · ส่งงาน (ตรวจค่า · token ผิด = 403) · สั่งซ้ำ — งานวิ่งผ่านคิวจริงด้วย opencode ปลอม"""
        with socket.socket() as s:  # server opencode ที่ไม่มีใคร listen — กันไปแตะ 4096 ของจริง
            s.bind(("127.0.0.1", 0))
            self.env["FLASHQ_LIVE_URL"] = f"http://127.0.0.1:{s.getsockname()[1]}"
        plans = self.proj / "docs" / "plans"
        plans.mkdir(parents=True)
        (plans / "PLAN_A_FLASH.md").write_text("# a\n", encoding="utf-8")
        (self.proj / ".git").mkdir()
        (self.proj / ".git" / "PLAN_HIDDEN_FLASH.md").write_text("x", encoding="utf-8")
        base = self.start_ui()
        token = self.ui_token(base)
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": token}

        d = json.loads(self.http(base + "/api/plans?project=" + urllib.request.quote(str(self.proj)))[1])
        self.assertEqual(d["plans"], ["docs/plans/PLAN_A_FLASH.md"])

        good = {"project": str(self.proj), "plan": "docs/plans/PLAN_A_FLASH.md", "tasks": "T-01..T-02",
                "attach": "none", "no_open": True}
        self.assertEqual(self.http(base + "/api/submit", json.dumps(good).encode(), {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.http(base + "/api/submit", json.dumps(good).encode(), {**hdr, "X-Flashq-Token": "x"})[0], 403)
        for bad in ({"plan": "../outside.md"}, {"plan": "docs/plans/NOPE.md"}, {"tasks": "T-01 & del"},
                    {"project": "relative\\dir"}, {"attach": "evil"}, {"switch_on_quota": 99}):
            code, body = self.http(base + "/api/submit", json.dumps({**good, **bad}).encode(), hdr)
            self.assertEqual(code, 400, (bad, body))
        self.assertFalse((self.home / "jobs").exists() and list((self.home / "jobs").glob("*.json")))

        code, body = self.http(base + "/api/submit", json.dumps(good).encode(), hdr)
        self.assertEqual(code, 200, body)
        jid = json.loads(body)["job"]
        self.assertTrue(jid)
        self.wait_job(jid)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--command") + 1:], ["flash", "--", "docs/plans/PLAN_A_FLASH.md", "T-01..T-02"])

        retry = json.dumps({"id": jid, "attach": "none", "no_open": True}).encode()
        self.assertEqual(self.http(base + "/api/retry", retry, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.http(base + "/api/retry", json.dumps({"id": "ไม่มี"}).encode(), hdr)[0], 404)
        code, body = self.http(base + "/api/retry", retry, hdr)
        self.assertEqual(code, 200, body)
        jid2 = json.loads(body)["job"]
        self.assertNotEqual(jid2, jid)
        self.wait_job(jid2)
        job2 = json.loads((self.home / "jobs" / f"{jid2}.json").read_text(encoding="utf-8"))
        self.assertEqual((job2["plan"], job2["tasks"]), ("docs/plans/PLAN_A_FLASH.md", "T-01..T-02"))
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["stats"]["by_project"][0]["n"], 2)
        self.assertEqual(st["stats"]["by_project"][0]["ok"], 2)
        self.assertIn(str(self.proj), st["project_paths"])

    def test_ui_prune_and_cli(self):
        """ui/CLI: ล้างงานเก่ากว่า N วัน (token ผิด = 403 · dry ไม่ลบ · ไม่แตะงานใหม่)"""
        (self.home / "jobs").mkdir(parents=True)
        (self.home / "logs").mkdir(parents=True)
        old_log = self.home / "logs" / "old_1.jsonl"
        old_log.write_text("{}\n", encoding="utf-8")
        for jid, created, logs in (("old", "2000-01-01 00:00:00", [str(old_log)]),
                                   ("new", time.strftime("%Y-%m-%d %H:%M:%S"), [])):
            (self.home / "jobs" / f"{jid}.json").write_text(json.dumps(
                {"id": jid, "status": "ok", "created": created, "finished": created, "project": str(self.proj),
                 "plan": "PLAN.md", "tasks": "T-01", "logs": logs}), encoding="utf-8")
        r = self.run_q("prune", "--days", "30", "--dry")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("งาน 1 รายการ", r.stdout)
        self.assertTrue(old_log.exists())

        base = self.start_ui()
        token = self.ui_token(base)
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": token}
        body = json.dumps({"days": 30}).encode()
        self.assertEqual(self.http(base + "/api/prune", body, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.http(base + "/api/prune", json.dumps({"days": 0}).encode(), hdr)[0], 400)
        d = json.loads(self.http(base + "/api/prune", json.dumps({"days": 30, "dry": True}).encode(), hdr)[1])
        self.assertEqual((d["jobs"], d["files"], d["dry"]), (1, 2, True))
        self.assertTrue((self.home / "jobs" / "old.json").exists())
        code, out = self.http(base + "/api/prune", body, hdr)
        self.assertEqual(code, 200, out)
        self.assertFalse((self.home / "jobs" / "old.json").exists())
        self.assertFalse(old_log.exists())
        self.assertTrue((self.home / "jobs" / "new.json").exists())

    def jobs_by_tasks(self):
        out = {}
        for f in (self.home / "jobs").glob("*.json"):
            j = json.loads(f.read_text(encoding="utf-8"))
            out[j.get("tasks")] = j
        return out

    def wait_for(self, cond, sec=40, msg="เงื่อนไขไม่เป็นจริง"):
        t0 = time.time()
        while time.time() - t0 < sec:
            v = cond()
            if v:
                return v
            time.sleep(0.3)
        self.fail(msg)

    def test_parallel_two_slots(self):
        """max_parallel=2 (CLI config) → 2 งานรันพร้อมกันคนละช่อง · status แสดงทุกช่อง · ค่าเริ่มต้นยังเป็น 1"""
        self.assertIn("max_parallel = 1", self.run_q("config").stdout)
        r = self.run_q("config", "max_parallel", "9")
        self.assertEqual(r.returncode, 1, r.stdout)
        r = self.run_q("config", "max_parallel", "2")
        self.assertEqual(r.returncode, 0, r.stdout)
        p1 = self.run_q("run", "PLAN.md", "T-01", "--attach", "none", "--no-open", env={"FAKE_SLEEP": "6"}, wait=False)
        time.sleep(1.5)
        p2 = self.run_q("run", "PLAN.md", "T-02", "--attach", "none", "--no-open", env={"FAKE_SLEEP": "6"}, wait=False)
        self.wait_for(lambda: all(j.get("status") == "running" for j in self.jobs_by_tasks().values())
                      and len(self.jobs_by_tasks()) == 2, msg="ไม่ได้รัน 2 งานพร้อมกัน")
        st = self.run_q("status").stdout
        self.assertIn("ช่อง 2/2", st)
        self.assertIn("ช่อง 1", st)
        self.assertTrue((self.home / "running.lock").exists())
        self.assertTrue((self.home / "running-2.lock").exists())
        o1, o2 = p1.communicate(timeout=120)[0], p2.communicate(timeout=120)[0]
        self.assertIn("FLASH_RUN=OK", o1)
        self.assertIn("FLASH_RUN=OK", o2)
        self.assertNotIn("QUEUED", o2)
        j = self.jobs_by_tasks()
        self.assertEqual({j["T-01"]["slot"], j["T-02"]["slot"]}, {1, 2})
        self.assertLess(j["T-02"]["started"], j["T-01"]["finished"])  # ซ้อนกันจริง
        self.assertEqual(sorted(p.name for p in self.home.glob("running*.lock")), [])

    def overlap_plan(self):
        (self.proj / "PLAN.md").write_text(
            "# plan\n## 1. กลุ่ม A\n"
            "- [ ] **T-01** `src/a.cpp` ~10 (`Foo`)\n  - ก่อน: `old/ignored.cpp`\n  - commit: `fix(x): y (T-01)`\n"
            "- [ ] **T-02** `src/a.cpp`\n  - ไฟล์: `include/b.h`\n"
            "- [ ] **T-03** `src/c.cpp`\n"
            "## 4. บันทึกผล\n`src/zzz.cpp`\n", encoding="utf-8")
        self.touch_src()

    def touch_src(self):
        """ไฟล์ที่แผนทดสอบอ้างต้องมีจริง (ด่านแผนพิการของ flashq run)"""
        for f, body in (("src/a.cpp", "old/ignored.cpp\n"), ("src/c.cpp", ""), ("include/b.h", "")):
            (self.proj / f).parent.mkdir(parents=True, exist_ok=True)
            (self.proj / f).write_text(body, encoding="utf-8")

    def test_plan_files_and_overlap(self):
        """ดึง path ไฟล์จากแผนตามงานที่สั่ง (ข้าม ก่อน/commit · ตรวจไม่ได้ = None) + เทียบไฟล์ซ้อน"""
        sys.path.insert(0, str(REPO))
        import flashq
        self.overlap_plan()
        P = str(self.proj)
        self.assertEqual(flashq.plan_files(P, "PLAN.md", "T-01"), ["src/a.cpp"])
        self.assertEqual(flashq.plan_files(P, "PLAN.md", "T-02..T-03"), ["include/b.h", "src/a.cpp", "src/c.cpp"])
        self.assertIsNone(flashq.plan_files(P, "PLAN.md", "T-09"))
        self.assertIsNone(flashq.plan_files(P, "NOPE.md", "T-01"))
        self.assertIsNone(flashq.plan_files(P, "", ""))
        self.assertTrue(flashq.paths_overlap("Src\\A.cpp", "src/a.cpp"))
        self.assertTrue(flashq.paths_overlap("cworking/script/", "cworking/script/x.txt"))
        self.assertTrue(flashq.paths_overlap("a.cpp", "src/a.cpp"))
        self.assertFalse(flashq.paths_overlap("src/a.cpp", "lib/a.cpp"))

    def test_ui_run_now_extra_slot(self):
        """ปุ่มรันเลย: max_parallel=1 งานที่ 2 รอคิว → ตรวจไฟล์ซ้อน (ซ้อน = ต้อง ack) → ได้ช่องพิเศษ รันพร้อมงานแรก"""
        self.overlap_plan()
        p1 = self.run_q("run", "PLAN.md", "T-01", "--attach", "none", "--no-open", env={"FAKE_SLEEP": "40"}, wait=False)  # นานพอให้ server ขึ้นช้าตอนเครื่องโหลด
        self.wait_for(lambda: self.jobs_by_tasks().get("T-01", {}).get("status") == "running")
        p2 = self.run_q("run", "PLAN.md", "T-02", "--attach", "none", "--no-open", env={"FAKE_SLEEP": "1"}, wait=False)
        j2 = self.wait_for(lambda: self.jobs_by_tasks().get("T-02"))
        time.sleep(1.5)
        self.assertEqual(self.jobs_by_tasks()["T-02"]["status"], "queued")
        base = self.start_ui()
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": self.ui_token(base)}
        rep = json.loads(self.http(base + f"/api/overlap?id={j2['id']}")[1])
        self.assertEqual(rep["running"][0]["overlap"], ["src/a.cpp"])
        self.assertTrue(rep["running"][0]["same_project"])
        self.assertTrue(rep["any_overlap"])
        self.assertFalse(rep["legacy"])
        body = json.dumps({"id": j2["id"]}).encode()
        self.assertEqual(self.http(base + "/api/runnow", body, {"Content-Type": "application/json"})[0], 403)
        self.assertEqual(self.http(base + "/api/runnow", body, hdr)[0], 409)  # ไฟล์ซ้อน ยังไม่ ack
        code, out = self.http(base + "/api/runnow", json.dumps({"id": j2["id"], "ack_overlap": True}).encode(), hdr)
        self.assertEqual(code, 200, out)
        o2 = p2.communicate(timeout=60)[0]
        self.assertIn("FLASH_RUN=OK", o2)
        self.assertIsNone(p1.poll())  # งานแรกยังรันอยู่ = ได้ช่องพิเศษจริง
        j = self.jobs_by_tasks()
        self.assertEqual(j["T-02"]["slot"], 2)
        self.assertIn("FLASH_RUN=OK", p1.communicate(timeout=120)[0])
        self.assertFalse((self.home / "run_now" / j2["id"]).exists())
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["slots"]["used"], 0)
        self.assertEqual(st["slots"]["max"], 1)

    def test_ui_config_and_legacy_run_now(self):
        """/api/config ตั้ง max_parallel · รันเลยงานโค้ดเก่า (ไม่มี qv) = ย้ายเจ้าของ running.lock ไปช่องอื่นให้ช่อง 1 ว่าง"""
        sys.path.insert(0, str(REPO))
        import flashq
        (self.home / "jobs").mkdir(parents=True)
        procs = [subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"]) for _ in range(2)]
        for sp in procs:
            self.addCleanup(lambda sp=sp: (sp.kill(), sp.wait(timeout=30)))
        run_id, q_id = "20990101_000000_5", "20990101_000001_6"
        st0, st1 = (flashq.proc_start(sp.pid) for sp in procs)
        lock = {"id": run_id, "pid": procs[0].pid, "pid_start": st0, "since": "2099-01-01 00:00:00"}
        (self.home / "running.lock").write_text(json.dumps(lock), encoding="utf-8")
        for jid, sp, st, status in ((run_id, procs[0], st0, "running"), (q_id, procs[1], st1, "queued")):
            (self.home / "jobs" / f"{jid}.json").write_text(json.dumps(
                {"id": jid, "status": status, "pid": sp.pid, "pid_start": st, "created": f"2099-01-01 00:00:0{jid[-1]}",
                 "started": "2099-01-01 00:00:05", "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01"}),
                encoding="utf-8")
        base = self.start_ui()
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": self.ui_token(base)}
        self.assertEqual(self.http(base + "/api/config", json.dumps({"max_parallel": 0}).encode(), hdr)[0], 400)
        self.assertEqual(self.http(base + "/api/config", json.dumps({"max_parallel": 3}).encode(),
                                   {"Content-Type": "application/json"})[0], 403)
        code, out = self.http(base + "/api/config", json.dumps({"max_parallel": 3}).encode(), hdr)
        self.assertEqual(code, 200, out)
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual((st["slots"]["used"], st["slots"]["max"]), (1, 3))
        self.assertEqual([r["id"] for r in st["running_list"]], [run_id])
        self.assertTrue(st["queued"][0]["legacy"])
        code, out = self.http(base + "/api/runnow", json.dumps({"id": q_id}).encode(), hdr)
        self.assertEqual(code, 200, out)
        self.assertFalse((self.home / "running.lock").exists())
        self.assertEqual(json.loads((self.home / "running-2.lock").read_text(encoding="utf-8"))["id"], run_id)
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["running_list"][0]["slot"], 2)
        # เจ้าของเดิม (โค้ดเก่า) ปล่อยล็อกด้วยการเทียบ id ที่ running.lock → ไม่ลบช่องของคนอื่น · พอ process ตาย ช่องที่ย้ายไปถูกล้างเอง
        procs[0].kill()
        procs[0].wait(timeout=30)
        self.assertEqual(json.loads(self.http(base + "/api/state")[1])["slots"]["used"], 0)
        self.assertFalse((self.home / "running-2.lock").exists())

    def test_quota_no_double_switch(self):
        """รันคู่ขนาน: QUOTA แต่บัญชีถูกงานอื่นสลับไปแล้ว → ใช้บัญชีนั้น ไม่สลับซ้ำ"""
        other = "commandcode2/deepseek/deepseek-v4.1-flash"
        r = self.run_q(*self.base(), "--switch-on-quota", "1", env={"FAKE_MODE": "quota", "FAKE_SET_MODEL": other})
        self.assertIn("โดยงานอื่น", r.stdout)
        self.assertEqual(json.loads(self.oc_cfg.read_text(encoding="utf-8"))["agent"]["flash-worker"]["model"], other)
        calls = [json.loads(x) for x in self.args_out.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([c[c.index("--model") + 1] for c in calls], ["p1/m", other])

    def test_switch_cli(self):
        r = self.run_q("switch", "cc2")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("commandcode2", r.stdout)
        r = self.run_q("switch", "go2")
        self.assertEqual(r.returncode, 3)  # ไม่มี provider


    # ---------- จัดคิวอัตโนมัติ (schedule auto) ----------
    def auto_plan(self):
        (self.proj / "PLAN.md").write_text(
            "# plan\n- [ ] **T-01** `src/a.cpp`\n- [ ] **T-02** `src/a.cpp`\n- [ ] **T-03** `src/c.cpp`\n", encoding="utf-8")
        self.touch_src()

    def by_key(self):
        out = {}
        for f in (self.home / "jobs").glob("*.json"):
            j = json.loads(f.read_text(encoding="utf-8"))
            out[j.get("message") or j.get("tasks")] = j
        return out

    def submit(self, *spec, sleep="6", project=None):
        args = ["run", *spec]
        args += ["--attach", "none", "--no-open"] + (["--project", str(project)] if project else [])
        p = self.run_q(*args, env={"FAKE_SLEEP": sleep}, wait=False)
        self.addCleanup(lambda: (p.kill(), p.wait(timeout=30)) if p.poll() is None else None)
        return p

    def test_verify_runs_agent_readonly(self):
        """verify: ส่ง --agent flash-verifier + prompt (ไม่ใช้ --command) · job kind=verify readonly · title/list บอกว่าตรวจ"""
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--agent") + 1], "flash-verifier")
        self.assertNotIn("--command", argv)
        self.assertIn("PLAN.md", argv[-1])
        self.assertIn("T-01", argv[-1])
        job = next(json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json"))
        self.assertEqual((job["kind"], job["agent"], job["readonly"]), ("verify", "flash-verifier", True))
        self.assertEqual(job["title"], "flash-verify PLAN T-01")
        self.assertEqual(argv[argv.index("--title") + 1], "flash-verify PLAN T-01")
        self.assertIn("[ตรวจ]", self.run_q("list", "--all").stdout)
        # ตัวเลือกเอง: agent/title/prompt/model ระบุได้
        self.args_out.unlink()
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open", "--agent", "my-checker",
                       "--title", "ตรวจ X", "--prompt", "ตรวจให้ที", "--model", "p9/m")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((argv[argv.index("--agent") + 1], argv[argv.index("--title") + 1], argv[-1],
                          argv[argv.index("--model") + 1]), ("my-checker", "ตรวจ X", "ตรวจให้ที", "p9/m"))

    def test_run_agent_and_readonly_options(self):
        r = self.run_q(*self.base(), "--agent", "x-agent", "--readonly")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--agent") + 1], "x-agent")
        self.assertEqual(argv[argv.index("--command") + 1:], ["flash", "--", "PLAN.md", "T-01"])
        job = next(json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json"))
        self.assertEqual((job["kind"], job["readonly"]), ("work", True))

    def test_verify_never_blocked_by_file_conflict(self):
        """auto: งานทำจริงที่แตะ a.cpp กำลังรัน → verify ของ T-02 (ไฟล์ซ้อน) ก็เริ่มได้ทันที (อ่านอย่างเดียว ไม่ชน)"""
        self.auto_plan()
        self.assertEqual(self.run_q("config", "schedule", "auto").returncode, 0)
        p1 = self.submit("PLAN.md", "T-01", sleep="8")
        self.wait_for(lambda: self.by_key().get("T-01", {}).get("status") == "running", msg="T-01 ไม่เริ่ม")
        p2 = self.run_q("verify", "PLAN.md", "T-02", "--attach", "none", "--no-open", env={"FAKE_SLEEP": "3"}, wait=False)
        self.addCleanup(lambda: (p2.kill(), p2.wait(timeout=30)) if p2.poll() is None else None)
        self.wait_for(lambda: self.by_key().get("T-02", {}).get("status") == "running", msg="verify ไม่เริ่มพร้อมกัน")
        self.assertIsNone(p1.poll())  # งานแรกยังรันอยู่ = รันคู่ขนานจริง
        self.assertIn("FLASH_RUN=OK", p2.communicate(timeout=60)[0])
        self.assertIn("FLASH_RUN=OK", p1.communicate(timeout=120)[0])

    def test_verify_uses_agent_own_model_and_subagent_fails(self):
        """agent อื่นใช้โมเดลของตัวเองใน config (ไม่ทับด้วยโมเดล flash-worker) · agent เป็น subagent → FAIL ไม่ใช่ OK"""
        cfg = json.loads(self.oc_cfg.read_text(encoding="utf-8"))
        cfg["agent"]["my-checker"] = {"model": "p9/checker-model"}
        self.oc_cfg.write_text(json.dumps(cfg), encoding="utf-8")
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open", "--agent", "my-checker")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--model") + 1], "p9/checker-model")
        self.args_out.unlink()
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open")  # flash-verifier ไม่มี model ของตัวเอง
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn("--model", argv)
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open", "--switch-on-quota", "2",
                       env={"FAKE_MODE": "subagent"})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=FAIL", r.stdout)
        self.assertIn("subagent", r.stdout)
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open", env={"FAKE_MODE": "agentmissing"})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=FAIL", r.stdout)

    def test_agent_model_from_frontmatter_and_json_wins(self):
        """ไม่ตั้งใน opencode.json → ใช้ model: ในหัวไฟล์ agent (แม่แบบ IRIS) · ตั้งทั้งสองที่ → opencode.json ชนะ"""
        agent_dir = self.oc_cfg.parent / "agent"
        agent_dir.mkdir(exist_ok=True)
        (agent_dir / "fm-checker.md").write_text(chr(10).join(["---", "mode: all", "model: p7/from-file", "---", "ตรวจ", ""]), encoding="utf-8")
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open", "--agent", "fm-checker")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--model") + 1], "p7/from-file")
        cfg = json.loads(self.oc_cfg.read_text(encoding="utf-8"))
        cfg["agent"]["fm-checker"] = {"model": "p8/from-json"}
        self.oc_cfg.write_text(json.dumps(cfg), encoding="utf-8")
        self.args_out.unlink()
        self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open", "--agent", "fm-checker")
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--model") + 1], "p8/from-json")

    def test_verify_quota_moves_provider_same_model(self):
        """ผู้ตรวจโควตาหมด → ย้าย provider เป็นโมเดลเดิม (ชื่อท้ายเหมือนกัน) สั่งซ้ำ · ไม่แตะ opencode.json · หมดตัวเลือกก็จบ QUOTA"""
        before = self.oc_cfg.read_text(encoding="utf-8")
        r = self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open",
                       "--model", "commandcode/deepseek/deepseek-v4.1-flash", env={"FAKE_MODE": "quota"})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=QUOTA", r.stdout)
        self.assertIn("ย้าย provider", r.stdout)
        models = [(a := json.loads(l))[a.index("--model") + 1] for l in self.args_out.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(models, ["commandcode/deepseek/deepseek-v4.1-flash", "commandcode2/deepseek/deepseek-v4.1-flash"])
        self.assertEqual(self.oc_cfg.read_text(encoding="utf-8"), before)
        self.args_out.unlink()  # ปิดสลับ (--switch-on-quota 0) → รันครั้งเดียว
        self.run_q("verify", "PLAN.md", "T-01", "--attach", "none", "--no-open", "--switch-on-quota", "0",
                   "--model", "commandcode/deepseek/deepseek-v4.1-flash", env={"FAKE_MODE": "quota"})
        self.assertEqual(len(self.args_out.read_text(encoding="utf-8").splitlines()), 1)

    def test_investigate_checks_citations(self):
        """รายงานผู้สืบอ้าง file:line → flashq ตรวจว่าไฟล์/บรรทัด/โค้ดที่คัดไว้มีจริง · ผิดต้องถูกชี้"""
        (self.proj / "src").mkdir()
        (self.proj / "src" / "a.cpp").write_text(chr(10).join(["int x = 0;", "void Foo() {", "  y = CalcWorldMinZ(m);", "}", ""]), encoding="utf-8")
        report = chr(10).join([
            "หลักฐาน: src/a.cpp:3 — `y = CalcWorldMinZ(m);` เรียกผิด",
            "หลักฐาน: src/a.cpp:2 — Foo เริ่มตรงนี้",
            "หลักฐาน: src/a.cpp:99 — บรรทัดที่ไม่มี",
            "หลักฐาน: src/ghost.cpp:1 — ไฟล์ที่ไม่มี",
            "หลักฐาน: src/a.cpp:1 — `int z = 5;` คัดผิด",
        ])
        r = self.run_q("investigate", "--no-open", "สืบ", env={"FAKE_TEXT": report})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("CITATIONS: ตรงถึงโค้ด 1 · ตรงแค่ไฟล์/บรรทัด 1 · ผิด 3", r.stdout)
        for needle in ("เลขบรรทัดเกินไฟล์", "ไม่พบไฟล์", "ไม่อยู่ในบรรทัดนี้"):
            self.assertIn(needle, r.stdout)
        job = next(json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json"))
        self.assertEqual((job["citations"]["ok"], len(job["citations"]["bad"])), (2, 3))

    def test_readonly_job_warns_when_files_change_and_agent_timeout(self):
        """งาน readonly แล้วไฟล์ในโปรเจกต์เปลี่ยน → WARN · ไม่เปลี่ยน → เงียบ · ผู้สืบ/ผู้ตรวจ timeout ค่าเริ่มต้นสั้นกว่างานทำจริง"""
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.proj, check=True)
        r = self.run_q("investigate", "--no-open", "สืบ", env={"FAKE_WRITE": "sneaky.txt"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WARN: งานอ่านอย่างเดียวนี้ไฟล์ในโปรเจกต์เปลี่ยน 1 ไฟล์: sneaky.txt", r.stdout)
        self.assertIn("ห้ามเชื่อผล", r.stdout)
        job = max((json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json")), key=lambda j: j["id"])
        self.assertEqual(job["modified"], ["sneaky.txt"])
        r = self.run_q("investigate", "--no-open", "สืบอีกที")  # sneaky.txt ค้างอยู่แล้วแต่ไม่เปลี่ยนรอบนี้
        self.assertNotIn("WARN: งานอ่านอย่างเดียว", r.stdout)
        r = self.run_q("verify", "PLAN.md", "T-01", "--no-open", env={"FAKE_WRITE": "sneaky2.txt"})
        self.assertIn("sneaky2.txt", r.stdout)
        import importlib.util
        spec = importlib.util.spec_from_file_location("flashq_t", FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.DEFAULTS["agent_timeout_min"], 30)

    def test_ui_submit_and_retry_keep_verify_kind(self):
        """ui: ส่งแบบ kind=verify แล้วสั่งซ้ำ → ยังเป็นงานตรวจ (agent เดิม) ไม่กลายเป็นงานทำจริง"""
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.env["FLASHQ_LIVE_URL"] = f"http://127.0.0.1:{s.getsockname()[1]}"
        base = self.start_ui()
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": self.ui_token(base)}
        good = {"project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01", "kind": "verify", "agent": "my-checker",
                "attach": "none", "no_open": True}
        self.assertEqual(self.http(base + "/api/submit", json.dumps({**good, "agent": "bad agent;"}).encode(), hdr)[0], 400)
        code, body = self.http(base + "/api/submit", json.dumps(good).encode(), hdr)
        self.assertEqual(code, 200, body)
        jid = json.loads(body)["job"]
        self.wait_job(jid)
        code, body = self.http(base + "/api/retry", json.dumps({"id": jid, "attach": "none", "no_open": True}).encode(), hdr)
        self.assertEqual(code, 200, body)
        jid2 = json.loads(body)["job"]
        self.wait_job(jid2)
        job2 = json.loads((self.home / "jobs" / f"{jid2}.json").read_text(encoding="utf-8"))
        self.assertEqual((job2["kind"], job2["agent"], job2["readonly"]), ("verify", "my-checker", True))
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(argv[argv.index("--agent") + 1], "my-checker")
        self.assertNotIn("--command", argv)
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertTrue(all(h["kind"] == "verify" for h in st["history"]))
        self.assertEqual(st["stats"]["by_project"], [])  # งานตรวจไม่ปนสถิติงานทำจริง
        self.assertEqual([(g["name"], g["n"]) for g in st["stats"]["by_kind"]], [("verify", 2)])
        html = self.http(base + "/")[1]
        for needle in ("agentField", "isVerify", "checker"):
            self.assertIn(needle, html)

    def test_investigate_runs_agent_readonly_no_plan(self):
        """investigate: ไม่ต้องมีแผน · ส่งบรีฟเป็น prompt ให้ flash-investigator · readonly · attach none เป็นค่าเริ่มต้น · นับชนิดของตัวเอง"""
        r = self.run_q("investigate", "--no-open", "ทำไม", "T-01", "ล้ม", "--", "-x")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--agent") + 1], "flash-investigator")
        self.assertNotIn("--command", argv)
        self.assertNotIn("--attach", argv)  # รันแยก ไม่ต่อ live server
        self.assertEqual(argv[-1], "ทำไม T-01 ล้ม -x")
        job = next(json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json"))
        self.assertEqual((job["kind"], job["agent"], job["readonly"]), ("investigate", "flash-investigator", True))
        self.assertTrue(job["title"].startswith("flash-investigate "))
        self.assertIn("[สืบ]", self.run_q("list", "--all").stdout)

    BRIEF = '## 1. อาการ (ของจริง)\nโปรเจกต์ X · r1 ≤ 0.27 · "ค่า" a<b>c | d & e 100% ^ !\n\n## 2. จุดที่เกี่ยว\n- f.py:10'

    def test_investigate_multiline_brief_title_single_line_prompt_intact(self):
        """เหตุจริง 2026-10-21: บรีฟหลายบรรทัด → title มีขึ้นบรรทัดใหม่ · prompt ต้องถึง opencode ครบตัวอักษร (ไม่เพี้ยน/ไม่ถูกตัด)"""
        r = self.run_q("investigate", "--no-open", self.BRIEF)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        title = argv[argv.index("--title") + 1]
        self.assertNotRegex(title, r"[\r\n]")
        self.assertTrue(title.startswith("flash-investigate ## 1. อาการ"))
        self.assertEqual(argv[-1], self.BRIEF)
        self.assertEqual(argv[-2], "--")
        job = next(json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json"))
        self.assertNotRegex(job["title"], r"[\r\n]")
        r = self.run_q("investigate", "--no-open", "--title", "ชื่อ\nสองบรรทัด", "สั้น ๆ")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(argv[argv.index("--title") + 1], "ชื่อ สองบรรทัด")

    def last_argv(self):
        return json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[-1])

    def variant_of(self, argv):
        return argv[argv.index("--variant") + 1] if "--variant" in argv else None

    def test_variant_defaults_by_kind(self):
        """ค่าเริ่มต้น: ผู้สืบ=high · ผู้ตรวจ=low · งานทำ=ไม่ส่ง --variant (provider ใช้ค่าของมันเอง) · เก็บลงบันทึกงานให้เทียบผลภายหลัง"""
        self.assertEqual(self.run_q("investigate", "--no-open", "สืบ").returncode, 0)
        self.assertEqual(self.variant_of(self.last_argv()), "high")
        self.assertEqual(self.run_q("verify", "PLAN.md", "T-01", "--no-open").returncode, 0)
        self.assertEqual(self.variant_of(self.last_argv()), "low")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIsNone(self.variant_of(self.last_argv()))
        jobs = {j["kind"]: j for j in (json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json"))}
        self.assertEqual((jobs["investigate"].get("variant"), jobs["verify"].get("variant"), jobs["work"].get("variant")), ("high", "low", None))
        self.assertIn("variant=low", self.run_q("verify", "PLAN.md", "T-01", "--no-open").stdout)

    def test_variant_precedence_cli_flash_json_config_default(self):
        """ลำดับ: --variant ใน CLI > variants ใน .flash.json > config.json > ค่าเริ่มต้น · ใส่ "" / none = ปิดชั้นล่าง · ชื่อแปลก = ข้ามพร้อมเตือน"""
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "config.json").write_text(json.dumps({"variants": {"investigate": "max", "work": "medium"}}), encoding="utf-8")
        self.run_q("investigate", "--no-open", "ก")
        self.assertEqual(self.variant_of(self.last_argv()), "max")  # config.json ชนะค่าเริ่มต้น
        self.run_q(*self.base())
        self.assertEqual(self.variant_of(self.last_argv()), "medium")  # ตั้งให้งานทำได้
        self.run_q("verify", "PLAN.md", "T-01", "--no-open")
        self.assertEqual(self.variant_of(self.last_argv()), "low")  # ชนิดที่ config.json ไม่พูดถึง = ค่าเริ่มต้น
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False, "variants": {"investigate": "low", "work": ""}}), encoding="utf-8")
        self.run_q("investigate", "--no-open", "ข")
        self.assertEqual(self.variant_of(self.last_argv()), "low")  # .flash.json ชนะ config.json
        self.run_q(*self.base())
        self.assertIsNone(self.variant_of(self.last_argv()))  # "" = ปิด (ไม่ใช้ medium จาก config.json)
        r = self.run_q("investigate", "--no-open", "ค", "--variant", "max")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.variant_of(self.last_argv()), "max")  # CLI ชนะทุกอย่าง
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False, "variants": {"verify": "none", "investigate": "--bad opt"}}), encoding="utf-8")
        self.run_q("verify", "PLAN.md", "T-01", "--no-open")
        self.assertIsNone(self.variant_of(self.last_argv()))  # none = ปิด ผู้ตรวจไม่ส่ง
        r = self.run_q("investigate", "--no-open", "ง")
        self.assertIn("ไม่ใช่ชื่อ variant", r.stderr)
        self.assertEqual(self.variant_of(self.last_argv()), "max")  # ชื่อแปลก (อาจแอบเป็นออปชัน) ไม่ถูกส่ง · ข้ามไปใช้ชั้นถัดไป (config.json = max)

    def test_opencode_npm_shim_resolves_to_real_exe(self):
        """opencode.CMD (ตัวห่อ npm) → เรียก opencode.exe ใต้ node_modules ตรง ๆ ไม่ผ่าน cmd.exe · ไม่มี exe ให้ชี้ = คืนตัวห่อเดิม"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("flashq_shim", FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        npm = self.tmp / "npm"
        exe = npm / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        shim = npm / "opencode.cmd"
        shim.write_text('@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n'
                        '"%dp0%\\node_modules\\opencode-ai\\bin\\opencode.exe"   %*\r\n', encoding="utf-8")
        self.assertEqual(mod.resolve_shim(str(shim)), str(exe))
        exe.unlink()
        self.assertEqual(mod.resolve_shim(str(shim)), str(shim))
        self.assertEqual(mod.resolve_shim(r"C:\x\opencode.exe"), r"C:\x\opencode.exe")
        self.assertEqual(mod.one_line("a\r\n  b\tc", 40), "a b c")

    @unittest.skipUnless(os.name == "nt", "cmd.exe เฉพาะ Windows")
    def test_cmd_shim_unresolved_refuses_unsafe_brief_but_runs_safe_one(self):
        """ยังต้องผ่าน .cmd (หา exe จริงไม่เจอ): บรีฟที่ cmd.exe จะตัด/เพี้ยน → FAIL ทันทีพร้อมบอกเหตุ (ไม่ใช่ NOSTART เงียบ 6 นาที) · บรีฟปลอดภัยยังรันได้"""
        shim = self.tmp / "opencode.cmd"
        shim.write_text(f'@echo off\r\n"{sys.executable}" "{FAKE}" %*\r\n', encoding="utf-8")
        env = {"FLASHQ_OPENCODE": str(shim)}
        t0 = time.time()
        r = self.run_q("investigate", "--no-open", self.BRIEF, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=FAIL", r.stdout)
        self.assertIn("cmd.exe", r.stdout)
        self.assertLess(time.time() - t0, 30)
        self.assertFalse(self.args_out.exists())  # opencode ไม่ถูกเรียก
        self.assertEqual(list((self.home / "jobs").glob("*.json")) if (self.home / "jobs").exists() else [], [])
        r = self.run_q("investigate", "--no-open", "บรีฟ ปลอดภัย", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[-1], "บรีฟ ปลอดภัย")

    def test_stalled_agent_job_is_killed_retried_once_and_explained(self):
        """log เงียบเกิน agent_stall_min → ฆ่า · TIMEOUT พร้อมเหตุ · ลองใหม่ 1 ครั้งเอง (ทั้งผู้สืบและงานทำจริง)"""
        (self.proj / ".flash.json").write_text(json.dumps({"agent_stall_min": 0.05, "stall_min": 0.05, "require_plan_in_remote": False}), encoding="utf-8")
        r = self.run_q("investigate", "--no-open", "ค้างไหม", env={"FAKE_SLEEP": "60"})
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, out)
        self.assertIn("FLASH_RUN=TIMEOUT", out)
        self.assertIn("STALL", out)
        self.assertIn("ลองใหม่อัตโนมัติ", out)
        self.assertEqual(len(self.args_out.read_text(encoding="utf-8").splitlines()), 2)
        r = self.run_q(*self.base(), env={"FAKE_SLEEP": "60"})  # งานทำจริงก็ลองใหม่หนึ่งครั้ง (ข้ามงานที่ติ๊กแล้ว) แล้วจบ TIMEOUT
        self.assertIn("FLASH_RUN=TIMEOUT", r.stdout)
        self.assertEqual(r.stdout.count("ลองใหม่อัตโนมัติ"), 1)

    def test_stall_limit_adapts_to_floor_not_only_ceiling(self):
        """เพดาน 10 นาที แต่ขั้นต่ำเล็ก → ตัดตั้งแต่ log เงียบเกินขั้นต่ำ (ไม่ต้องรอเพดาน)"""
        (self.proj / ".flash.json").write_text(json.dumps({"stall_min": 10, "stall_floor_min": 0.05, "require_plan_in_remote": False}), encoding="utf-8")
        t0 = time.time()
        r = self.run_q(*self.base(), env={"FAKE_SLEEP": "40"})
        self.assertLess(time.time() - t0, 35)
        self.assertIn("FLASH_RUN=TIMEOUT", r.stdout)
        self.assertIn("ขั้นต่ำ 0.05", r.stdout)

    def test_server_activity_sees_child_session_and_running_tool(self):
        """ถามเซิร์ฟเวอร์: session ลูกขยับเมื่อไร + tool ไหนกำลังรัน (ใช้บอกสาเหตุค้าง และกันฆ่างานที่ subagent ยังทำอยู่)"""
        import http.server
        import importlib.util
        import threading
        now_ms = int(time.time() * 1000)
        routes = {
            "/session/ses_p/children": [{"id": "ses_c", "title": "ทำ T-04", "time": {"updated": now_ms - 5000}}],
            "/session/ses_p/message": [{"info": {"time": {"created": now_ms - 600000}}, "parts": [
                {"type": "tool", "tool": "task", "state": {"status": "running", "input": {"description": "T-04"}, "time": {"start": now_ms - 600000}}}]}],
            "/session/ses_c/message": [{"info": {"time": {"created": now_ms - 300000}}, "parts": [
                {"type": "tool", "tool": "bash", "state": {"status": "running", "input": {"command": "blender --hang"}, "time": {"start": now_ms - 300000}}}]}],
            "/session/ses_c/children": [{"id": "ses_g", "time": {"updated": now_ms - 900000}}],  # subagent ซ้อน subagent
            "/session/ses_g/message": [{"info": {"time": {"created": now_ms - 900000}}, "parts": [
                {"type": "tool", "tool": "grep", "state": {"status": "running", "input": {"pattern": "x"}, "time": {"start": now_ms - 900000}}}]}],
        }
        queries = []

        class Hh(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path, _, query = self.path.partition("?")
                queries.append(query)
                body = json.dumps(routes.get(path, [])).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hh)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            spec = importlib.util.spec_from_file_location("flashq_mod", FLASHQ)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            act = mod.server_activity(f"http://127.0.0.1:{srv.server_address[1]}", "ses_p", "D:/งาน/proj")
        finally:
            srv.shutdown()
        self.assertIsNotNone(act)
        self.assertLess(time.time() - act["updated"], 10)  # ลูกขยับ 5 วิก่อน
        self.assertEqual({r["tool"] for r in act["running"]}, {"task", "bash", "grep"})
        # ผู้ช่วยย่อย: เรียงตัวที่ขยับล่าสุดก่อน · ชื่องาน + tool ล่าสุด → หน้าเว็บบอกว่า log หลักเงียบเพราะงานอยู่ที่ผู้ช่วยย่อย
        self.assertEqual([x["session"] for x in act["subs"]], ["ses_c", "ses_g"])
        self.assertEqual((act["subs"][0]["title"], act["subs"][0]["doing"]), ("ทำ T-04", "bash: blender --hang"))
        row = mod._agent_act_row({"at": time.time(), "updated": act["updated"], "subs": act["subs"]})
        self.assertLess(row["idle_sec"], 10)
        self.assertEqual((row["subs"][0]["title"], row["subs"][1]["ago_sec"] >= 899), ("ทำ T-04", True))
        self.assertIsNone(mod._agent_act_row({"at": time.time() - 400, "updated": 0, "subs": []}))  # ข้อมูลเก่าเกิน = ไม่ใช้
        # server เปิดที่ ~/.flashq → ทุกคำขอต้องบอกโฟลเดอร์โปรเจกต์ ไม่งั้นหา session ไม่เจอ
        self.assertTrue(queries and all(q == urllib.parse.urlencode({"directory": "D:/งาน/proj"}) for q in queries), queries)
        self.assertIsNone(mod.server_activity("http://127.0.0.1:1", "ses_p"))

    def fake_live_server(self, mode: dict):
        """server opencode ปลอม: /config · children/message (ขยับล่าสุดตาม mode["active"]) · บันทึกคำขอ (รวม POST abort)"""
        import http.server
        import threading
        hits = []

        class Hh(http.server.BaseHTTPRequestHandler):
            def _ok(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                hits.append(("GET", self.path))
                path = self.path.partition("?")[0]
                if path.endswith("/children"):
                    return self._ok([])
                if path.endswith("/message"):
                    t = int(time.time() * 1000) if mode["active"] else 1000
                    return self._ok([{"info": {"time": {"created": t}}, "parts": []}])
                return self._ok({})

            def do_POST(self):
                hits.append(("POST", self.path))
                self._ok(True)

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hh)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}", hits

    def test_live_stall_spares_active_subagent_and_aborts_real_stall(self):
        """--attach live: log เงียบแต่ server บอกว่า subagent ยังขยับ = ไม่ฆ่า (ถามสดก่อนตัดสินทุกครั้ง)
        ค้างจริง = ฆ่า + POST abort session บน server (ไม่งั้นรอบลองใหม่แก้ไฟล์ซ้อนกับ session เก่า) · ทุกคำขอส่ง directory"""
        (self.proj / ".flash.json").write_text(json.dumps({"stall_min": 0.1, "stall_floor_min": 0.05, "require_plan_in_remote": False}), encoding="utf-8")
        mode = {"active": True}
        url, hits = self.fake_live_server(mode)
        env = {"FLASHQ_LIVE_URL": url, "FAKE_SLEEP": "25"}
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env=env)
        self.assertIn("FLASH_RUN=OK", r.stdout, r.stdout + r.stderr)  # เกณฑ์ค้าง ~3-6 วิ แต่ server ขยับตลอด → รอจนจบ
        asks = [p for m, p in hits if m == "GET" and "/session/" in p]
        self.assertGreater(len(asks), 3)
        want = urllib.parse.urlencode({"directory": str(self.proj.resolve())})
        self.assertTrue(all(p.endswith("?" + want) for p in asks), asks[:3])
        mode["active"] = False
        hits.clear()
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env={**env, "FAKE_SLEEP": "60"})
        self.assertIn("FLASH_RUN=TIMEOUT", r.stdout)
        self.assertIn("รอโมเดล", r.stdout)
        aborts = [p for m, p in hits if m == "POST"]
        self.assertEqual(len(aborts), 2, hits)  # รอบแรก + รอบลองใหม่
        self.assertTrue(all(re.match(r"/session/ses_fake\d+/abort\?directory=", p) for p in aborts), aborts)
        self.assertIn("หยุด session", r.stdout)

    @unittest.skipUnless(os.name == "nt", "หน้าต่าง console เป็นเรื่องของ Windows")
    def test_detached_spawn_children_do_not_open_console_windows(self):
        """process ที่แยกขาด (spawn_run / server สด) ต้องมี console ซ่อนของตัวเอง (CREATE_NO_WINDOW) ไม่ใช่ DETACHED_PROCESS —
        ไม่งั้นลูกที่เป็นโปรแกรม console (git · python · taskkill) ทุกตัวเปิดหน้าต่างดำเด้งขึ้นจอผู้ใช้ · ลูกหลานต้องไม่มีหน้าต่างที่มองเห็น"""
        mod = self.load_mod("flashq_flags")
        self.assertFalse(mod.HIDDEN_DETACH_FLAGS & subprocess.DETACHED_PROCESS)
        self.assertTrue(mod.HIDDEN_DETACH_FLAGS & subprocess.CREATE_NO_WINDOW)
        gc = self.tmp / "gc.py"
        gc.write_text("import ctypes, sys"+chr(10)+"h = ctypes.windll.kernel32.GetConsoleWindow()"+chr(10)+
                      "open(sys.argv[1], 'w').write('visible' if h and ctypes.windll.user32.IsWindowVisible(h) else 'hidden')"+chr(10), encoding="utf-8")
        ch = self.tmp / "ch.py"
        ch.write_text("import subprocess, sys"+chr(10)+"subprocess.run([sys.executable, sys.argv[1], sys.argv[2]])"+chr(10), encoding="utf-8")
        out = self.tmp / "gc_out.txt"
        subprocess.Popen([sys.executable, str(ch), str(gc), str(out)], creationflags=mod.HIDDEN_DETACH_FLAGS,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).wait(timeout=60)
        self.assertEqual(out.read_text(encoding="utf-8"), "hidden")

    def test_live_server_without_external_dirs_falls_back_to_own_opencode(self):
        """server 4096 เปิดค้างโหลดสิทธิ์ครั้งเดียว: external_dirs ที่เพิ่งเพิ่มใน .flash.json ที่ server ไม่รู้ → ไม่ปล่อยให้โดน DENIED หลังรันหลายนาที
        แต่รันแยก (ได้สิทธิ์ผ่าน OPENCODE_CONFIG_CONTENT) พร้อมบอกเหตุ · server อนุญาตแล้ว = ใช้ server ตามเดิม · ระบุ --attach <url> เอง = ไม่เปลี่ยนให้"""
        (self.proj / ".flash.json").write_text(
            json.dumps({"require_plan_in_remote": False, "external_dirs": ["D:/outside/lib/*"]}), encoding="utf-8")
        import http.server
        import threading
        perm_srv = {"external_directory": {"*": "ask"}}

        class Hh(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                body = json.dumps({"permission": perm_srv}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hh)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        env_out = self.tmp / "env_fb.txt"
        env = {"FLASHQ_LIVE_URL": url, "FAKE_ENV_OUT": str(env_out)}
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env=env)
        self.assertIn("FLASH_RUN=OK", r.stdout, r.stdout + r.stderr)
        self.assertIn("PERM_FALLBACK:", r.stdout)
        self.assertIn("D:/outside/lib/*", r.stdout)
        self.assertNotIn("--attach", self.args_out.read_text(encoding="utf-8").splitlines()[0])  # รันแยก ไม่ต่อ server
        rules = json.loads(env_out.read_text(encoding="utf-8"))["permission"]["external_directory"]
        self.assertEqual(rules.get("D:/outside/lib/*"), "allow")
        job = max((json.loads(f.read_text(encoding="utf-8")) for f in (self.home / "jobs").glob("*.json")), key=lambda j: j["created"])
        self.assertEqual(job["attach"], "")
        # server อนุญาตแล้ว → ไม่ fallback
        perm_srv["external_directory"]["D:/outside/*"] = "allow"
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env=env)
        self.assertIn("FLASH_RUN=OK", r.stdout, r.stdout + r.stderr)
        self.assertNotIn("PERM_FALLBACK", r.stdout)
        self.assertIn("server opencode อนุญาต external_dirs แล้ว", r.stdout)
        # ผู้ใช้ระบุ URL เอง → ไม่ตัดสินใจแทน (คงคำเตือนเดิม)
        perm_srv["external_directory"].pop("D:/outside/*")
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", url, "--no-open", env=env)
        self.assertNotIn("PERM_FALLBACK", r.stdout)
        self.assertIn("WARN: server opencode", r.stdout)

    def load_mod(self, name):
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        with mock.patch.dict(os.environ, {"FLASHQ_HOME": str(self.home), "FLASHQ_NO_TOAST": "1"}):  # HOME อ่านตอน import — ห้ามเขียนลง ~/.flashq จริง
            spec.loader.exec_module(mod)
        for d in ("jobs", "inbox", "logs"):
            (self.home / d).mkdir(parents=True, exist_ok=True)
        return mod

    def test_shell_watch_kills_only_stuck_command(self):
        """ตัวเฝ้า shell: โปรเซสขยับ = ไม่ฆ่า · นิ่งเกิน idle = ฆ่าเฉพาะรากของคำสั่ง · shell จบแต่ลูกกำพร้าถือ handle = ฆ่าเมื่อยืนยัน 2 รอบ
        · โปรเซสอื่นของเครื่อง (กำพร้าเหมือนกันแต่ไม่เกี่ยว) ห้ามโดน · tool จบแล้วล้างสถานะ"""
        mod = self.load_mod("flashq_shellwatch")
        T = 1_000_000.0
        tab = [{"pid": 1, "ppid": 0, "name": "opencode.exe", "cmd": "opencode serve", "created": T - 999, "act": 5},
               {"pid": 10, "ppid": 1, "name": "powershell.exe", "cmd": 'powershell.EXE -NoLogo -Command "npm run build"', "created": T + 1, "act": 1},
               {"pid": 11, "ppid": 10, "name": "node.exe", "cmd": "node build.js", "created": T + 2, "act": 100},
               {"pid": 50, "ppid": 4444, "name": "chrome.exe", "cmd": "chrome.exe --type=renderer", "created": T + 3, "act": 7}]
        killed = []
        w = mod.ShellWatch(4, table=lambda: tab, killer=killed.append)
        run = [{"tool": "bash", "cmd": "npm run build", "what": "npm run build", "since": T, "session": "s1"},
               {"tool": "read", "cmd": "", "what": "x", "since": T, "session": "s1"}]
        rep = w.check(run, now=T + 30)
        self.assertEqual((rep["state"], rep["pids"]), ("active", 2))
        tab[2]["act"] = 200  # ขยับ → นับเวลานิ่งใหม่
        self.assertEqual(w.check(run, now=T + 200)["state"], "active")
        self.assertEqual(w.check(run, now=T + 400)["state"], "quiet")  # นิ่ง 200 วิ ≥ ครึ่งของ idle
        self.assertEqual(killed, [])
        rep = w.check(run, now=T + 200 + 4 * 60)
        self.assertEqual(rep["state"], "killed")
        self.assertIn("นิ่งสนิท", rep["note"])
        self.assertEqual(killed, [10])  # ฆ่าแค่ราก (kill_tree ตามลูกเอง) ไม่แตะ opencode / chrome
        self.assertEqual(w.seen, {})

        # shell ตายทันที (start /b) → ping กำพร้า ถือ pipe ไว้ · chrome กำพร้าที่เกิดเวลาเดียวกันแต่ไม่เกี่ยว ห้ามโดน
        tab[:] = [tab[0], tab[3], {"pid": 20, "ppid": 77, "name": "PING.EXE", "cmd": "ping -n 300 127.0.0.1", "created": T + 1, "act": 3}]
        killed.clear()
        w = mod.ShellWatch(4, table=lambda: tab, killer=killed.append)
        run = [{"tool": "bash", "cmd": "cmd /c start /b ping -n 300 127.0.0.1", "what": "", "since": T, "session": "s2"}]
        rep = w.check(run, now=T + 30)
        self.assertEqual((rep["state"], rep["names"], rep["kill_in"]), ("suspect", "PING.EXE", 2 * mod.SHELL_POLL_SEC))
        self.assertIn("1/3", rep["note"])
        self.assertEqual(w.check(run, now=T + 60)["state"], "suspect")
        rep = w.check(run, now=T + 90)
        self.assertEqual(rep["state"], "killed")
        self.assertIn("ถือ handle", rep["note"])
        self.assertEqual(killed, [20])
        self.assertEqual(rep["victims"][0]["name"], "PING.EXE")
        self.assertEqual(w.released, [])  # ฆ่าแล้วไม่นับเป็นปล่อยไป
        # tool จบ (ไม่อยู่ใน running) → ล้าง · ไม่มี bash = ไม่อ่านตารางโปรเซสเลย
        w.check(run, now=T + 91)
        w.check([], now=T + 92)
        self.assertEqual(w.seen, {})
        # สงสัยแล้วแต่ tool จบเองก่อนครบรอบยืนยัน = ปล่อยไป (ไม่ฆ่า)
        killed.clear()
        w = mod.ShellWatch(4, table=lambda: tab, killer=killed.append)
        w.check(run, now=T + 30)
        w.check([], now=T + 40)
        self.assertEqual((killed, len(w.released)), ([], 1))
        self.assertIn("PING.EXE", w.released[0]["note"])
        # เคสจริง 2026-10-20: opencode หนี \" ใน command line ของ shell → ต้องจับคู่ได้ (เดิมเข้าใจผิดว่า shell จบ แล้วฆ่า python/timeout ของเทสต์ที่ยังทำงาน)
        # + กำพร้าที่ตรงคำเดียวบังเอิญ (tools) ห้ามโดน
        cmd = r'powershell -NoProfile -ExecutionPolicy Bypass -File "D:\o\run-long.ps1" -Command "regression_all.ps1 -Tier quick"'
        tab[:] = [tab[0], {"pid": 30, "ppid": 1, "name": "powershell.exe", "created": T + 1, "act": 1,
                           "cmd": 'powershell.EXE -NoLogo -Command "' + cmd.replace('"', '\\"') + '"'},
                  {"pid": 31, "ppid": 30, "name": "powershell.exe", "cmd": "x", "created": T + 2, "act": 1},
                  {"pid": 40, "ppid": 999, "name": "python.exe", "cmd": r"python tools\other.py quick", "created": T + 5, "act": 1}]
        killed.clear()
        w = mod.ShellWatch(4, table=lambda: tab, killer=killed.append)
        run = [{"tool": "bash", "cmd": cmd, "what": "", "since": T, "session": "s3"}]
        for t in (30, 60, 90):
            tab[2]["act"] += 1
            rep = w.check(run, now=T + t)
        self.assertEqual((rep["state"], rep["pids"], killed), ("active", 2, []))
        w2 = mod.ShellWatch(4, table=lambda: self.fail("ไม่ควรอ่านตาราง"), killer=killed.append)
        self.assertIsNone(w2.check([{"tool": "grep", "cmd": "", "since": T, "session": "s"}], now=T))

    def test_shell_watch_live_kills_stuck_command_and_job_continues(self):
        """--attach live + ตารางโปรเซสปลอม: server บอกว่า bash รันอยู่ · โปรเซสนิ่ง → ตัวเฝ้าฆ่าเฉพาะคำสั่ง (ไม่ฆ่างาน) แล้วงานจบ OK"""
        import http.server
        import threading
        T = time.time()
        procs = self.tmp / "procs.json"
        procs.write_text(json.dumps([{"pid": 900001, "ppid": 1, "name": "powershell.exe", "cmd": "powershell -Command \"ping -n 999 x\"",
                                      "created": T, "act": 1}]), encoding="utf-8")

        class Hh(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.partition("?")[0]
                obj = {}
                if path.endswith("/children"):
                    obj = []
                elif path.endswith("/message"):
                    obj = [{"info": {"time": {"created": 1000}}, "parts": [
                        {"type": "tool", "tool": "bash", "state": {"status": "running", "input": {"command": "ping -n 999 x"},
                                                                   "time": {"start": int(T * 1000)}}}]}]
                body = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.do_GET()

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hh)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        (self.proj / ".flash.json").write_text(json.dumps({"shell_idle_min": 0.05, "require_plan_in_remote": False}), encoding="utf-8")
        env = {"FLASHQ_LIVE_URL": f"http://127.0.0.1:{srv.server_address[1]}", "FAKE_SLEEP": "12",
               "FLASHQ_FAKE_PROCS": str(procs), "FLASHQ_SHELL_POLL_SEC": "1"}
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env=env)
        self.assertIn("FLASH_RUN=OK", r.stdout, r.stdout + r.stderr)
        self.assertIn("SHELL_WATCH: ฆ่าคำสั่งค้าง", r.stdout)
        self.assertEqual(Path(str(procs) + ".killed").read_text(encoding="utf-8").split(), ["900001"])
        job = json.loads(next((self.home / "jobs").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(len(job["shell_kills"]), 1)

    def goal_repo(self, body: str) -> Path:
        g = lambda *a: subprocess.run(["git", "-C", str(self.proj), *a], capture_output=True, check=True)  # noqa: E731
        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        (self.proj / "src").mkdir()
        (self.proj / "src" / "a.txt").write_text("old\n", encoding="utf-8")
        (self.proj / "tests").mkdir()
        (self.proj / "tests" / "acc.py").write_text("import sys\nt = open('src/a.txt').read()\nprint('VAL=' + t.strip())\nsys.exit(0 if 'new' in t else 1)\n", encoding="utf-8")
        goal = self.proj / "docs" / "plans" / "GOAL_x.md"
        goal.parent.mkdir(parents=True)
        goal.write_text(body, encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "base")
        return goal

    def test_goal_check_rejects_unmeasurable_flags(self):
        """ตัวตรวจข้อจำกัด: ไม่มีเกณฑ์ · เกณฑ์ไม่มีทั้งตรวจ/คนตรวจ · คำสั่งที่ผ่านเสมอ · ช่อง <...> · ไม่มีขอบเขต · ทุกข้อคนตรวจ = FAIL
        คำลอยไม่มี ต้องเห็น · ไม่มี goal-locked · ไม่ตั้งรอบ = เตือน"""
        self.goal_repo("# GOAL\n")
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL_CHECK=FAIL", r.stdout)
        self.assertIn("ไม่มีเกณฑ์ยอมรับ", r.stdout)
        bad = ("- [ ] G-01 หน้าเว็บสวยขึ้น\n- [ ] G-02 ผ่าน · ตรวจ: `echo ok`\n- [ ] G-03 x · ตรวจ: `<คำสั่ง>`\n")
        (self.proj / "docs/plans/GOAL_x.md").write_text(bad, encoding="utf-8")
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL_CHECK=FAIL", r.stdout)
        for want in ("G-01: ไม่มี `ตรวจ:`", "G-02: คำสั่งตรวจ `echo ok` ผ่านเสมอ", "ช่องว่างจากแม่แบบ `<...>`: G-03", "ไม่มี `goal-files:`"):
            self.assertIn(want, r.stdout)
        (self.proj / "docs/plans/GOAL_x.md").write_text("- [ ] G-01 สวย · คนตรวจ: ดูหน้าแรก\ngoal-files: src/*\n", encoding="utf-8")
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertIn("ทุกเกณฑ์เป็น `คนตรวจ:`", r.stdout)
        (self.proj / "docs/plans/GOAL_x.md").write_text(f"- [ ] G-01 ทำงานได้ · ตรวจ: `\"{sys.executable}\" tests/acc.py`\ngoal-files: src/*\n", encoding="utf-8")
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL_CHECK=OK", r.stdout, r.stdout)
        for want in ("คำว่า \"ทำงานได้\"", "ไม่มี `goal-locked:`", "ไม่ได้ตั้ง goal-max-rounds"):
            self.assertIn(want, r.stdout)
        self.assertTrue((self.proj / ".tmp" / "flashq-goal" / "GOAL_x.json").is_file())

    def test_goal_verify_loop_and_brakes(self):
        """verify: ไม่ผ่าน = CONTINUE · พังซ้ำเหมือนเดิม 2 รอบ = STOP · ผ่าน + คนตรวจ = DONE_NEEDS_USER · แก้ไฟล์ล็อก/นอกขอบเขต = STOP
        · แก้เกณฑ์หลังเริ่ม = STOP จนกว่า check --reset · ครบงบรอบ = STOP"""
        py = f'"{sys.executable}"'
        body = (f"- [ ] G-01 ค่าเป็น new · ตรวจ: `{py} tests/acc.py` · ต้องเห็น: `VAL=new`\n- [ ] G-02 ข้อความอ่านง่าย · คนตรวจ: เปิด src/a.txt\n"
                "goal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 3\n")
        goal = self.goal_repo(body)
        v = lambda: self.run_q("goal", "verify", "docs/plans/GOAL_x.md")  # noqa: E731
        self.assertIn("ยังไม่ได้รัน `goal check", v().stdout)
        self.assertIn("GOAL_CHECK=OK", self.run_q("goal", "check", "docs/plans/GOAL_x.md").stdout)
        r = v()
        self.assertIn("GOAL=CONTINUE รอบ 1/3 · ไม่ผ่าน G-01", r.stdout, r.stdout)
        self.assertIn("VAL=old", r.stdout)  # ท้าย output ของเกณฑ์ที่ล้ม = หลักฐานให้แผนรอบหน้า
        r = v()  # ไม่มีงานใหม่ = ตรวจซ้ำ ไม่นับรอบ (ไม่เสียงบรอบเปล่า)
        self.assertIn("ไม่มีงานใหม่ตั้งแต่รอบ 1", r.stdout, r.stdout)
        self.assertIn("GOAL=CONTINUE รอบ 1/3", r.stdout)
        (self.proj / "src" / "b.txt").write_text("x\n", encoding="utf-8")  # มีงานแต่ผลเหมือนเดิม
        r = v()
        self.assertIn("GOAL=STOP", r.stdout)
        self.assertIn("พังซ้ำเรื่องเดิม 2 รอบติด", r.stdout)
        self.assertEqual(r.returncode, 1)
        self.assertIn("GOAL_CHECK=OK", self.run_q("goal", "check", "docs/plans/GOAL_x.md", "--reset").stdout)
        (self.proj / "src" / "a.txt").write_text("new\n", encoding="utf-8")
        r = v()
        self.assertIn("GOAL=DONE_NEEDS_USER", r.stdout, r.stdout)
        self.assertIn("G-02 ข้อความอ่านง่าย → เปิด src/a.txt", r.stdout)
        # โกง: แก้เทสต์เกณฑ์ + แตะไฟล์นอกขอบเขต
        (self.proj / "tests" / "acc.py").write_text("print('VAL=new')\n", encoding="utf-8")
        (self.proj / "other.py").write_text("x\n", encoding="utf-8")
        r = v()
        self.assertIn("GOAL=STOP", r.stdout)
        self.assertIn("ไฟล์ล็อก (เกณฑ์/เทสต์ตัดสิน) ถูกแก้: tests/acc.py", r.stdout)
        self.assertIn("แก้ไฟล์นอกขอบเขต goal-files: other.py", r.stdout)
        (self.proj / "other.py").unlink()
        subprocess.run(["git", "-C", str(self.proj), "checkout", "--", "tests/acc.py"], check=True)
        # ย้ายเสาประตู: ผ่อนเกณฑ์หลังเริ่ม
        goal.write_text(body.replace("· ต้องเห็น: `VAL=new`", ""), encoding="utf-8")
        r = v()
        self.assertIn("ย้ายเสาประตู", r.stdout)
        self.assertIn("ต้องแก้: เกณฑ์ต่างจากตอนเริ่ม", self.run_q("goal", "check", "docs/plans/GOAL_x.md").stdout)
        # ครบงบรอบ
        goal.write_text(body, encoding="utf-8")
        self.run_q("goal", "check", "docs/plans/GOAL_x.md", "--reset")
        (self.proj / "src" / "a.txt").write_text("v1\n", encoding="utf-8")
        v()
        (self.proj / "src" / "a.txt").write_text("v2\n", encoding="utf-8")  # ผลต่างกันทุกรอบ = ไม่ใช่พังซ้ำ
        v()
        (self.proj / "src" / "a.txt").write_text("v3\n", encoding="utf-8")
        r = v()
        self.assertIn("ครบงบ 3 รอบแล้วยังไม่ผ่าน", r.stdout, r.stdout)
        self.assertIn("รอบ 3/3", self.run_q("goal", "status", "docs/plans/GOAL_x.md").stdout)

    def test_goal_published_for_ui(self):
        """check/verify คัดลอกสถานะไป ~/.flashq/goals · ui_goals: ผ่านกี่ข้อ · ผูกงานแผน _R<n> · เก็บเหตุเบรกของรอบ"""
        py = f'"{sys.executable}"'
        self.goal_repo(f"# GOAL: ค่าใหม่\n- [ ] G-01 ค่าเป็น new · ตรวจ: `{py} tests/acc.py` · ต้องเห็น: `VAL=new`\n"
                       "- [ ] G-02 อ่านง่าย · คนตรวจ: เปิด src/a.txt\ngoal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 3\n")
        self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        files = list((self.home / "goals").glob("*.json"))
        self.assertEqual(len(files), 1)
        mod = self.load_mod("flashq_goalui")
        mod.GOALS_DIR = self.home / "goals"
        g = mod.ui_goals([])[0]
        self.assertEqual((g["verdict"], g["title"], g["machine"], g["rounds_max"]), ("START", "ค่าใหม่", 1, 3))
        self.assertEqual([i["human"] for i in g["items"]], ["", "เปิด src/a.txt"])
        self.run_q("goal", "verify", "docs/plans/GOAL_x.md", env={"CLAUDE_CODE_SESSION_ID": "sess-test-1", "CLAUDE_CODE_ENTRYPOINT": "cli"})
        own = mod.ui_goals([])[0]["owner"]  # session ที่สั่งล่าสุด → UI บอกว่าต้องกลับไปทำต่อที่ไหน
        self.assertEqual((own["session"], own["app"], Path(own["cwd"]).resolve()), ("sess-test-1", "cli", self.proj.resolve()))
        self.run_q("goal", "status", "docs/plans/GOAL_x.md", env={"CLAUDE_CODE_SESSION_ID": ""})
        self.assertEqual(mod.ui_goals([])[0]["owner"]["session"], "sess-test-1")  # คำสั่งนอก Claude Code ไม่ลบที่มาเดิม
        # ขั้นย่อย: เขียนแผน (อ่านความเคลื่อนไหวของ session เจ้าของ + subagent จาก transcript) → คิว → Flash ทำ → รอตรวจ → ผล
        mod.CLAUDE_PROJECTS = self.home / "cp"
        tr = mod.CLAUDE_PROJECTS / "D--proj" / "sess-test-1.jsonl"
        sub = tr.parent / "sess-test-1" / "subagents" / "agent-a1.jsonl"
        sub.parent.mkdir(parents=True)

        def jl(f, *entries):
            f.write_text("".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in entries), encoding="utf-8")

        def tool(name, inp):
            return {"type": "assistant", "message": {"role": "assistant", "stop_reason": "tool_use", "content": [{"type": "tool_use", "name": name, "input": inp}]}}
        end = {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ส่ง subagent แล้ว"}]}}
        self.assertIn("หา session ที่ทำไม่เจอ", mod.ui_goals([])[0]["phase"]["label"])
        jl(tr, tool("Agent", {"description": "เขียนแผน"}), end)
        jl(sub, tool("Read", {"file_path": "C:/x/plan.md"}))
        (sub.parent / "agent-a1.meta.json").write_text(json.dumps({"description": "เขียนแผน R2"}), encoding="utf-8")
        ph = mod.ui_goals([])[0]["phase"]
        self.assertEqual((ph["step"], ph["round"], ph["warn"]), ("plan", 2, False))
        self.assertIn("กำลังเขียนแผนรอบ 2", ph["label"])
        self.assertIn("รอ subagent", ph["notes"][0]["t"])
        self.assertIn("«เขียนแผน R2» กำลังทำ · Read: plan.md", ph["notes"][1]["t"])
        jl(sub, tool("Read", {"file_path": "C:/x/plan.md"}), end)  # subagent จบ + session จบเทิร์น = ไม่มีใครทำ → เตือน
        ph = mod.ui_goals([])[0]["phase"]
        self.assertEqual((ph["warn"], len(ph["notes"])), (True, 1))
        self.assertIn("ไม่ได้ทำงานอยู่", ph["label"])
        jl(tr, tool("AskUserQuestion", {"questions": [{"question": "เริ่มวนไหม"}]}))
        ph = mod.ui_goals([])[0]["phase"]
        self.assertTrue(ph["notes"][0]["warn"])
        self.assertIn("รอคุณตอบ", ph["notes"][0]["t"])
        self.assertIn("เริ่มวนไหม", ph["notes"][0]["t"])
        jl(tr, tool("Bash", {"command": "x", "description": "รันเทสต์"}))
        plan = self.proj / "docs" / "plans" / "PLAN_FLASH_x_R2.md"
        plan.write_text("# แผน\n", encoding="utf-8")
        ph = mod.ui_goals([])[0]["phase"]
        self.assertEqual(ph["step"], "plan")
        self.assertIn("📤 แผนรอบ 2 เขียนเสร็จแล้ว", ph["label"])
        self.assertIn("กำลังทำงาน · ล่าสุด Bash: รันเทสต์", ph["notes"][0]["t"])
        q = {"id": "Q1", "project": str(self.proj), "plan": "docs/plans/PLAN_FLASH_x_R2.md", "position": 1, "wait_sec": 5}
        ph = mod.ui_goals([], [], [q])[0]["phase"]
        self.assertEqual((ph["step"], q["goal"]["round"]), ("flash", 2))
        self.assertIn("อยู่ในคิว ลำดับ 1", ph["label"])
        plan.unlink()
        run = {"id": "J1", "project": g["project"], "plan": "docs/plans/PLAN_FLASH_x_R2.md"}
        other = {"id": "J2", "project": g["project"], "plan": "docs/plans/PLAN_FLASH_y_R2.md"}
        g = mod.ui_goals([run, other])[0]
        self.assertEqual((g["verdict"], g["passed"], g["jobs"]), ("CONTINUE", 0, ["J1"]))
        self.assertEqual((g["phase"]["step"], g["phase"]["job"]), ("flash", "J1"))
        self.assertEqual(run["goal"], {"id": g["id"], "round": 2, "rounds_max": 3, "title": "ค่าใหม่"})
        self.assertNotIn("goal", other)
        self.assertEqual(other["fix_round"], 2)  # แผน _R<n> ธรรมดาที่ไม่มีเป้าหมาย = ป้าย 🔁 แก้รอบ ไม่ใช่ 🚩
        done = {"id": "J0", "project": g["project"], "plan": "docs/plans/PLAN_FLASH_x_R1.md", "state": "ok", "finished": "2099-01-01 00:00:00"}
        g = mod.ui_goals([], [done])[0]  # งานที่จบแล้วในประวัติก็ติด 🚩 + การ์ดรู้ว่า Flash ทำรอบไหนเสร็จล่าสุด
        self.assertEqual((done["goal"]["round"], g["last_job"]["id"], g["last_job"]["round"]), (1, "J0", 1))
        self.assertEqual(g["rounds"][-1]["flash"], 0)  # รอบนี้ไม่มีงาน Flash = ตรวจอย่างเดียว
        self.assertEqual(g["phase"]["step"], "review")  # Flash จบหลังตรวจล่าสุด = รอ Claude ตรวจ
        self.assertEqual(g["unverified"], [1])
        run3 = {"id": "J3", "project": g["project"], "plan": "docs/plans/PLAN_FLASH_x_R3.md"}
        g = mod.ui_goals([run3], [dict(done)])[0]  # ข้าม verify รอบ 1 แล้วส่งรอบถัดไป → ปุ่มขั้นใช้รอบของงานที่รัน + เตือน
        self.assertEqual((g["phase"]["step"], g["phase"]["round"], g["unverified"]), ("flash", 3, [1]))
        self.assertTrue(g["phase"]["notes"][0]["warn"])
        self.assertIn("รอบ 1 Flash ทำเสร็จแล้วแต่ยังไม่ได้ goal verify", g["phase"]["notes"][0]["t"])
        self.assertIn("VAL=old", g["rounds"][-1]["results"]["G-01"]["tail"])
        (self.proj / "src" / "b.txt").write_text("x\n", encoding="utf-8")
        self.run_q("goal", "verify", "docs/plans/GOAL_x.md")  # มีงานใหม่แต่ผลเดิมซ้ำ = STOP
        g = mod.ui_goals([])[0]
        self.assertEqual(g["verdict"], "STOP")
        self.assertEqual((g["phase"]["step"], g["phase"]["warn"]), ("result", True))
        self.assertIn("พังซ้ำเรื่องเดิม", g["rounds"][-1]["stop"][0])
        self.assertNotIn("results", g["rounds"][0])  # รอบเก่าเก็บแค่ผลย่อ

    def test_goal_human_marks_from_ui(self):
        """ข้อคนตรวจ: goal human --pass/--fail (ปุ่ม ✅/❌ ในหน้าเว็บ) · ผ่านครบ = DONE · ไม่ผ่านเก็บเหตุ · ปุ่มเว็บรับเฉพาะ id ของเป้าหมาย"""
        py = f'"{sys.executable}"'
        self.goal_repo(f"- [ ] G-01 ค่าเป็น new · ตรวจ: `{py} tests/acc.py` · ต้องเห็น: `VAL=new`\n"
                       "- [ ] G-02 อ่านง่าย · คนตรวจ: เปิด src/a.txt\ngoal-files: src/*\ngoal-locked: tests/*\n")
        self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        r = self.run_q("goal", "human", "docs/plans/GOAL_x.md", "G-02", "--pass")
        self.assertIn("GOAL_HUMAN=FAIL", r.stdout)  # ยังไม่มีรอบ / เครื่องยังไม่ผ่าน
        (self.proj / "src" / "a.txt").write_text("new\n", encoding="utf-8")
        self.assertIn("GOAL=DONE_NEEDS_USER", self.run_q("goal", "verify", "docs/plans/GOAL_x.md").stdout)
        self.assertIn("ไม่ใช่ข้อคนตรวจ", self.run_q("goal", "human", "docs/plans/GOAL_x.md", "G-01", "--pass").stdout)
        r = self.run_q("goal", "human", "docs/plans/GOAL_x.md", "G-02", "--fail", "ตัวอักษรเล็กไป")
        self.assertIn("GOAL=DONE_NEEDS_USER", r.stdout, r.stdout)
        mod = self.load_mod("flashq_goalhuman")
        mod.GOALS_DIR = self.home / "goals"
        g = mod.ui_goals([])[0]
        self.assertEqual(g["rounds"][-1]["human_res"]["G-02"]["reason"], "ตัวอักษรเล็กไป")
        self.assertIn("ไม่ผ่าน — ตัวอักษรเล็กไป", self.run_q("goal", "status", "docs/plans/GOAL_x.md").stdout)
        r = self.run_q("goal", "human", "docs/plans/GOAL_x.md", "G-02", "--pass")
        self.assertIn("GOAL=DONE คนตรวจผ่าน 1/1", r.stdout, r.stdout)
        self.assertEqual(mod.ui_goals([])[0]["verdict"], "DONE")
        r = self.run_q("goal", "verify", "docs/plans/GOAL_x.md")  # ตรวจซ้ำโดยไม่มีงานใหม่ = ผลคนตรวจเดิมยังใช้ได้ ไม่นับรอบ
        self.assertIn("GOAL=DONE รอบ 1/", r.stdout, r.stdout)
        g2 = mod.ui_goals([])[0]
        self.assertEqual((len(g2["rounds"]), g2["rounds"][-1]["rechecks"], g2["verdict"]), (1, 1, "DONE"))
        self.assertEqual(mod.goal_ui_action(g["id"], "archive", {})[0], 200)  # ✖ เก็บ = หายจากแผง/เสาธง
        self.assertEqual(mod.ui_goals([]), [])
        self.run_q("goal", "human", "docs/plans/GOAL_x.md", "G-02", "--pass")  # สั่งเรื่องนี้ใหม่ = กลับมาเอง
        self.assertEqual(len(mod.ui_goals([])), 1)
        (mod.GOALS_DIR / f"{g['id']}.busy.json").write_text(json.dumps({"what": "verify", "pid": os.getpid(), "at": "x"}), encoding="utf-8")
        gs = mod.ui_goals([])
        self.assertEqual((len(gs), gs[0]["busy"]["what"]), (1, "verify"))  # ไฟล์ busy ไม่นับเป็นเป้าหมาย · pid ยังอยู่ = กำลังทำ
        self.assertEqual(mod.goal_ui_action("../../x", "open", {})[0], 400)
        self.assertEqual(mod.goal_ui_action("0" * 12, "open", {})[0], 404)
        self.assertEqual(mod.goal_ui_action(g["id"], "verify", {})[0], 409)  # กำลังตรวจอยู่ = ไม่เริ่มซ้ำ
        (mod.GOALS_DIR / f"{g['id']}.busy.json").unlink()
        opened, gp = [], mod.GOALS_DIR / f"{g['id']}.json"
        mod.open_link = opened.append  # ไม่เปิดแอปจริงระหว่างเทสต์
        mod.claude_app_link = lambda path, params: f"claude://code/{path}?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)  # ทำเหมือนเครื่องมีแอป
        code, r = mod.goal_ui_action(g["id"], "claude", {})  # มีแอป Claude desktop = session ใหม่ในแอป พิมพ์ /flash-goal รอไว้
        self.assertEqual(code, 200, r)
        self.assertTrue(opened[-1].startswith("claude://code/new?q=%2Fflash-goal%20"), opened)
        self.assertIn("&folder=", opened[-1])
        self.assertFalse((mod.GOALS_DIR / f"{g['id']}.busy.json").exists())  # แอปไม่มี pid ให้เฝ้า = ไม่ล็อกปุ่ม
        data = json.loads(gp.read_text(encoding="utf-8"))
        data["owner"] = {"session": "s1", "host": "local_abc-1"}
        gp.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(mod.goal_ui_action(g["id"], "session", {})[0], 200)
        self.assertEqual(opened[-1], "claude://code/continue?session=local_abc-1")
        data["owner"] = {"session": "s1", "host": "local_x&y=1"}  # host แปลก = ไม่สร้างลิงก์
        gp.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(mod.goal_ui_action(g["id"], "session", {})[0], 404)
        link = self.load_mod("flashq_goallink").claude_app_link("new", {"q": "a b"})
        self.assertIn(link, ("", "claude://code/new?q=a%20b"))  # "" = เครื่องนี้ไม่มีแอป Claude desktop

    def test_goal_scope_counts_only_flash_windows(self):
        """ไม่ STOP ผิด: เทสต์เกณฑ์ commit หลัง check · ไฟล์ขยะไม่ track ที่มีมาก่อน · มีงาน Flash ของเป้าหมาย = นับเฉพาะที่แก้ระหว่างงานรัน"""
        py = f'"{sys.executable}"'
        self.goal_repo(f"- [ ] G-01 ค่าเป็น new · ตรวจ: `{py} tests/acc.py` · ต้องเห็น: `VAL=new`\ngoal-files: src/*\ngoal-locked: tests/*\n")
        junk = self.proj / "junk.bin"
        junk.write_text("x", encoding="utf-8")
        os.utime(junk, (time.time() - 3600, time.time() - 3600))  # มีมาก่อนเริ่มเป้าหมาย
        self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        (self.proj / "tests" / "acc2.py").write_text("print(1)\n", encoding="utf-8")  # เจ้าของเพิ่มเทสต์เกณฑ์หลัง check
        subprocess.run(["git", "-C", str(self.proj), "add", "tests/acc2.py"], check=True)
        subprocess.run(["git", "-C", str(self.proj), "commit", "-qm", "goal tests"], check=True)
        time.sleep(3)
        proj = json.loads(next((self.home / "goals").glob("*.json")).read_text(encoding="utf-8"))["project"]
        t0 = time.strftime("%Y-%m-%d %H:%M:%S")
        (self.home / "jobs").mkdir(exist_ok=True)
        (self.home / "jobs" / "J1.json").write_text(json.dumps({"id": "J1", "project": proj, "plan": "docs/plans/PLAN_FLASH_x_R1.md",
                                                                "status": "running", "created": t0, "started": t0}), encoding="utf-8")
        (self.proj / "src" / "a.txt").write_text("new\n", encoding="utf-8")
        (self.proj / "docs" / "plans" / "PLAN_FLASH_y_R1.md").write_text("y\n", encoding="utf-8")  # session อื่น (เรื่อง y) commit ช่วงเดียวกัน
        (self.proj / "lib").mkdir()
        (self.proj / "lib" / "y.py").write_text("y\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.proj), "add", "docs/plans/PLAN_FLASH_y_R1.md", "lib/y.py"], check=True)
        subprocess.run(["git", "-C", str(self.proj), "commit", "-qm", "งานเรื่อง y"], check=True)
        r = self.run_q("goal", "verify", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL=DONE", r.stdout, r.stdout)
        (self.proj / "other.py").write_text("x\n", encoding="utf-8")  # ไฟล์ค้าง/commit ไม่มีรหัสงาน = อาจเป็นของ session อื่น → เตือน ไม่ STOP
        (self.proj / "lib" / "z.py").write_text("z\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.proj), "add", "lib/z.py"], check=True)
        subprocess.run(["git", "-C", str(self.proj), "commit", "-qm", "งานอื่น"], check=True)
        r = self.run_q("goal", "verify", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL=DONE", r.stdout, r.stdout)
        self.assertIn("อาจเป็นของ session อื่น", r.stdout)
        self.assertIn("lib/z.py, other.py", r.stdout)
        self.assertNotIn("junk.bin", r.stdout)
        self.assertNotIn("ไฟล์ล็อก", r.stdout)
        (self.proj / "lib" / "w.py").write_text("w\n", encoding="utf-8")  # commit ของงาน Flash (มีรหัสงาน) ที่หลุดขอบเขต = STOP
        subprocess.run(["git", "-C", str(self.proj), "add", "lib/w.py"], check=True)
        subprocess.run(["git", "-C", str(self.proj), "commit", "-qm", "fix(lib): w (T-02)"], check=True)
        r = self.run_q("goal", "verify", "docs/plans/GOAL_x.md")
        self.assertIn("แก้ไฟล์นอกขอบเขต goal-files: lib/w.py", r.stdout, r.stdout)
        self.assertNotIn("other.py", r.stdout.split("เบรก:")[-1])

    def test_cancel_does_not_kill_reused_child_pid(self):
        """child_pid ของรอบก่อนที่ถูกโปรแกรมอื่นนำไปใช้ซ้ำ (เวลาเริ่มไม่ตรง) ต้องไม่ถูกฆ่าตอนยกเลิกงาน"""
        mod = self.load_mod("flashq_cancel")
        mod.JOBS = self.tmp / "jobs"
        mod.JOBS.mkdir()
        mod.HOME, mod.RUN_NOW, mod.LOCK = self.tmp, self.tmp / "run_now", self.tmp / "running.lock"
        owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(lambda: [(p.kill(), p.wait(timeout=30)) for p in (owner, other)])
        j = {"id": "J9", "status": "running", "pid": owner.pid, "pid_start": mod.proc_start(owner.pid),
             "child_pid": other.pid, "child_pid_start": 12345, "created": "2099-01-01 00:00:00"}
        ok, _ = mod.cancel_job(j)
        self.assertTrue(ok)
        owner.wait(timeout=30)
        time.sleep(0.5)
        self.assertIsNone(other.poll())  # ยังมีชีวิต

    def test_write_json_retries_while_reader_holds_file(self):
        """Windows ปฏิเสธ os.replace ถ้ามีคนเปิดอ่านไฟล์ปลายทางอยู่ (หน้าเว็บ poll) → ต้องรอแล้วเขียนสำเร็จ ไม่ crash งานกลางทาง"""
        import threading
        mod = self.load_mod("flashq_wj")
        target = self.tmp / "job.json"
        target.write_text("{}", encoding="utf-8")
        reader = open(target, "rb")
        t = threading.Timer(0.4, reader.close)
        t.start()
        self.addCleanup(lambda: (t.cancel(), reader.close()))
        mod.write_json(target, {"v": 2})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"v": 2})
        self.assertEqual([p.name for p in self.tmp.glob("job.json.*.tmp")], [])
        reader2 = open(target, "rb")  # ถูกถือไว้ตลอด → หมดเวลาแล้วโยน error เดิม และไม่ทิ้งไฟล์ .tmp
        self.addCleanup(reader2.close)
        if os.name == "nt":
            tmp = self.tmp / "x.tmp"
            tmp.write_text("x", encoding="utf-8")
            with self.assertRaises(PermissionError):
                mod.replace_file(tmp, target, wait_sec=0.3)
            self.assertFalse(tmp.exists())

    def test_orphan_child_is_reaped_by_cancel_dismiss_stale_lock_and_crash(self):
        """`flashq run` ตายแต่ opencode ลูกรอด: ยกเลิก/ล้างช่องตาย/run_once ล้ม ต้องฆ่าลูก · pid ที่เวลาเริ่มไม่ตรงห้ามแตะ"""
        mod = self.load_mod("flashq_orphan")
        mod.JOBS = self.tmp / "jobs"
        mod.JOBS.mkdir()
        mod.HOME, mod.RUN_NOW, mod.LOCK = self.tmp, self.tmp / "run_now", self.tmp / "running.lock"
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait(timeout=30)
        kids = []

        def child():
            p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            kids.append(p)
            return p

        self.addCleanup(lambda: [(p.kill(), p.wait(timeout=30)) for p in kids])

        def job(jid, c, **kw):
            return {"id": jid, "status": "running", "pid": dead.pid, "pid_start": 0, "attach": "none",
                    "child_pid": c.pid, "child_pid_start": mod.proc_start(c.pid), "created": "2099-01-01 00:00:00", **kw}

        # 1) reap_orphan ฆ่าเฉพาะ process เดิม
        c = child()
        self.assertIn("ฆ่า", mod.reap_orphan(job("O1", c)))
        c.wait(timeout=30)
        reused = child()
        self.assertEqual(mod.reap_orphan({**job("O1b", reused), "child_pid_start": 12345}), "")
        time.sleep(0.3)
        self.assertIsNone(reused.poll())
        # 2) cancel งานที่ process หลักตายแต่สถานะยังค้าง running → ฆ่าลูกด้วย
        c = child()
        j = job("O2", c)
        mod.save_job(j)
        self.assertEqual(mod.live_state(j), "dead")
        ok, msg = mod.cancel_job(j)
        self.assertTrue(ok, msg)
        c.wait(timeout=30)
        self.assertEqual(mod.read_json(mod.JOBS / "O2.json")["status"], "cancelled")
        # งานที่จบแล้วยังยกเลิกไม่ได้
        self.assertFalse(mod.cancel_job({**j, "status": "done"})[0])
        # 3) ช่องของ process ที่ตาย → ถูกล้าง และลูกของงานนั้นถูกฆ่า
        c = child()
        mod.save_job(job("O3", c))
        mod.LOCK.write_text(json.dumps({"id": "O3", "pid": dead.pid, "pid_start": 0, "since": "x", "extra": False}), encoding="utf-8")
        mod.clear_stale_lock()
        self.assertFalse(mod.LOCK.exists())
        c.wait(timeout=30)
        # 4) run_once ล้มกลางทาง (exception) → ฆ่าลูกก่อนโยนต่อ
        c = child()
        j = job("O4", c, pid=os.getpid())

        def boom(*a, **k):
            raise RuntimeError("boom")

        mod._run_once = boom
        with self.assertRaises(RuntimeError):
            mod.run_once(j, [], self.proj, "none", 1, True, 1)
        c.wait(timeout=30)

    def test_goal_cmd_not_blocked_by_background_child_holding_output(self):
        """เกณฑ์ที่เปิดโปรเซสเบื้องหลัง (start /b · &) ไม่ต้องทำให้ goal verify รอจนโปรเซสนั้นจบ · เกิน timeout ต้องฆ่าแล้วคืน 124"""
        mod = self.load_mod("flashq_gcmd")
        py = f'"{sys.executable}" -c "import time; time.sleep(%d)"'
        bg = ('start /b "" ' if os.name == "nt" else "") + py % 12 + ("" if os.name == "nt" else " &")
        t0 = time.time()
        rc, out = mod.goal_run_cmd(self.proj, "echo hello && " + bg if os.name == "nt" else "echo hello; " + bg, 0.05)
        self.assertLess(time.time() - t0, 8, out)
        self.assertEqual(rc, 0, out)
        self.assertIn("hello", out)
        t0 = time.time()
        rc, out = mod.goal_run_cmd(self.proj, py % 60, 0.03)  # timeout 1.8 วิ
        self.assertLess(time.time() - t0, 15)
        self.assertEqual(rc, 124)
        self.assertIn("ฆ่าแล้ว", out)

    def test_switch_account_empty_list_and_file_lock(self):
        mod = self.load_mod("flashq_switch")
        mod.OC_CONFIG = self.oc_cfg
        import contextlib
        import io
        mod.accounts = lambda: ("flash-worker", [])
        with contextlib.redirect_stdout(io.StringIO()):  # console ของเทสต์เป็น cp874 พิมพ์ → ไม่ได้
            self.assertEqual(mod.switch_account("next"), "")  # เดิม ZeroDivisionError
            mod.accounts = lambda: ("flash-worker", [["cc", "commandcode/deepseek/deepseek-v4.1-flash"]])
            self.assertEqual(mod.switch_account("next"), "commandcode/deepseek/deepseek-v4.1-flash")
        self.assertEqual(json.loads(self.oc_cfg.read_text(encoding="utf-8"))["agent"]["flash-worker"]["model"],
                         "commandcode/deepseek/deepseek-v4.1-flash")
        self.assertEqual([p.name for p in self.tmp.glob("opencode.json.*.tmp")], [])
        lk = self.tmp / "x.lock"
        with mod.file_lock(lk) as got:
            self.assertTrue(got)
            t0 = time.time()
            with mod.file_lock(lk, wait_sec=0.5) as got2:  # ถือล็อกอยู่ → รอแล้วทำต่อแบบไม่ล็อก
                self.assertFalse(got2)
            self.assertGreaterEqual(time.time() - t0, 0.4)
            self.assertTrue(lk.exists())  # ตัวที่ไม่ได้ล็อกต้องไม่ลบล็อกของคนอื่น
        self.assertFalse(lk.exists())
        lk.touch()
        os.utime(lk, (time.time() - 3600, time.time() - 3600))  # ล็อกเก่าที่ process ตายทิ้งไว้
        with mod.file_lock(lk, wait_sec=2) as got:
            self.assertTrue(got)

    def test_why_diagnoses_hung_tool_model_wait_and_plan_progress(self):
        """flashq why: แยก tool ค้าง (มีคำสั่งเปิดโปรเซสเบื้องหลัง) / รอโมเดล / ปกติ / ไม่รู้ และนับ T-xx ที่ติ๊ก [x] ในแผน"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("flashq_mod2", FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        plan = self.proj / "plan.md"
        plan.write_text("- [x] **T-01** a\n- [ ] **T-02** b\n  - [x] **T-02a** sub\n- [X] **T-03** c\n"
                        "* [x] T-04 ไม่มีตัวหนา\n- [x]**T-05**\n- [x] T-066x มีตัวอักษรท้าย\n- [x] งานทั่วไป T-07\n", encoding="utf-8")
        j = {"id": "J1", "project": str(self.proj), "plan": "plan.md", "attach": "http://x", "session": "ses_p"}
        self.assertEqual(mod.plan_done_tasks(j), ["T-01", "T-02a", "T-03", "T-04", "T-05", "T-066x"])
        now = time.time()
        mod.live_state = lambda _j: "running"
        mod.log_idle_sec = lambda _j: 1200
        run = lambda cmd, mins: {"updated": now - 1200, "running": [
            {"tool": "bash", "what": cmd, "since": now - mins * 60, "session": "ses_c", "cmd": cmd}]}
        mod.server_activity = lambda *a: run("Start-Process python srv.py", 3)
        d = mod.diagnose_job(j)
        self.assertEqual(d["verdict"], "tool_hang")
        self.assertIn("Start-Process", d["text"])
        mod.server_activity = lambda *a: run("blender --export", 4)
        self.assertEqual(mod.diagnose_job(j)["verdict"], "tool_long")
        mod.server_activity = lambda *a: run("blender --export", 25)
        self.assertEqual(mod.diagnose_job(j)["verdict"], "tool_hang")
        mod.server_activity = lambda *a: {"updated": now - 1200, "running": []}
        self.assertEqual(mod.diagnose_job(j)["verdict"], "model_wait")
        mod.server_activity = lambda *a: {"updated": now - 5, "running": []}
        self.assertEqual(mod.diagnose_job(j)["verdict"], "ok")
        mod.server_activity = lambda *a: None
        self.assertEqual(mod.diagnose_job(j)["verdict"], "unknown")
        mod.live_state = lambda _j: "done"
        self.assertEqual(mod.diagnose_job(j)["verdict"], "not_running")
        r = self.run_q("why")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ไม่มีงานที่กำลังรัน", r.stdout)

    def test_denied_tool_calls_are_counted_not_failures(self):
        r = self.run_q("investigate", "--no-open", "สืบ", env={"FAKE_DENIED": "1"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RULE_DENIED: 1 คำสั่ง", r.stdout)
        self.assertIn("find . -name x", r.stdout)
        self.assertNotIn("FLASH_RUN=DENIED", r.stdout)  # กฎของ agent บล็อก ≠ opencode ปฏิเสธสิทธิ์

    def test_permission_denied_is_not_ok(self):
        """เหตุจริง 2026-10-20: opencode ปฏิเสธสิทธิ์ external_directory เอง (โหมดไม่โต้ตอบ) งานจบ exit 0 โดยไม่ได้ทำ → ต้องเป็น DENIED ไม่ใช่ OK
        พิมพ์ path ที่ถูกปฏิเสธ + ทางแก้ 2 ทาง · wait คืน 1 · มี DONE (สำเร็จบางส่วน) = คง OK แต่เตือน"""
        r = self.run_q(*self.base(), env={"FAKE_MODE": "denied"})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=DENIED", r.stdout)
        self.assertIn("DENIED: opencode ปฏิเสธสิทธิ์ 1 รายการ", r.stdout)
        self.assertIn("external_directory: D:\\outside\\lib\\*", r.stdout)
        self.assertIn('"external_dirs": ["D:/outside/lib/*"]', r.stdout)
        self.assertIn('permission.external_directory เพิ่ม "D:\\\\outside\\\\lib\\\\*": "allow"', r.stdout)
        j = json.loads(next((self.home / "jobs").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual((j["status"], j["result"]), ("denied", "DENIED"))
        self.assertEqual(j["perm_denied"], [{"kind": "external_directory", "path": "D:\\outside\\lib\\*"}])
        r = self.run_q("wait", "PLAN.md")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=DENIED", r.stdout)
        self.assertIn("D:\\outside\\lib\\*", r.stdout)
        self.assertIn("external_dirs", r.stdout)
        r = self.run_q("list", "--all")
        self.assertIn("denied", r.stdout)
        # worker ตอบ DONE (บางงานสำเร็จ) → คง OK แต่เตือนรายการที่ถูกปฏิเสธ
        r = self.run_q(*self.base(), env={"FAKE_MODE": "denied", "FAKE_TEXT": "T-01 DONE แล้ว · T-02 ถูกปฏิเสธสิทธิ์"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=OK", r.stdout)
        self.assertIn("WARN: opencode ปฏิเสธสิทธิ์ 1 รายการระหว่างทำงาน แต่มีงานสำเร็จบางส่วน", r.stdout)
        self.assertIn("D:\\outside\\lib\\*", r.stdout)
        # ตัดสินจาก log จริงได้ด้วยฟังก์ชันเดียวกัน (stderr ของ opencode มีสี ANSI นำหน้า)
        sys.path.insert(0, str(REPO))
        import flashq
        perm = flashq.perm_denials("\x1b[93m! \x1b[0mpermission requested: external_directory (D:\\a\\b\\*); auto-rejecting\n", ["task T-01"])
        self.assertEqual(perm, [{"kind": "external_directory", "path": "D:\\a\\b\\*"}])
        self.assertEqual(flashq.perm_denials("", ["task T-01", "task T-01"]), [{"kind": "tool", "path": "task T-01"}])  # ไม่มี stderr = ใช้ tool error

    def test_external_dirs_precheck_and_config_content(self):
        """`.flash.json` ช่อง external_dirs → ส่งสิทธิ์ให้ opencode ผ่าน OPENCODE_CONFIG_CONTENT (ไม่แตะ opencode.json) ·
        opencode.json ยังไม่มี allow → บอกบรรทัด JSON ที่ต้องเพิ่ม · มีแล้ว → ไม่เตือน · opencode.json เสีย → เตือน · server สด (--attach) ยังไม่อนุญาต → WARN จะ DENIED"""
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False, "external_dirs": ["D:/outside/lib/*", "D:\\other"]}), encoding="utf-8")
        env_out = self.tmp / "env.txt"
        r = self.run_q(*self.base(), env={"FAKE_ENV_OUT": str(env_out)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PERM: ส่งสิทธิ์ external_dirs ให้ opencode รอบนี้ผ่าน OPENCODE_CONFIG_CONTENT", r.stdout)
        self.assertIn("ยังไม่มี allow ของ D:/outside/lib/*, D:/other/*", r.stdout)
        self.assertIn('"D:\\\\outside\\\\lib\\\\*": "allow"', r.stdout)
        rules = json.loads(env_out.read_text(encoding="utf-8"))["permission"]["external_directory"]
        self.assertEqual(rules.get("D:/outside/lib/*"), "allow")
        self.assertEqual(rules.get("D:/other/*"), "allow")  # ไม่มี * = เติม /* ให้
        self.assertEqual(rules.get("D:\\outside\\lib\\*"), "allow")  # ใส่ทั้งสองแบบบน Windows
        # opencode.json อนุญาตแล้ว (รูปแบบ \\ · กฎเจาะจงทับ "*": "ask") → ไม่เตือน
        cfg = json.loads(self.oc_cfg.read_text(encoding="utf-8"))
        cfg["permission"] = {"external_directory": {"*": "ask", "D:\\outside\\*": "allow", "D:/other/*": "allow"}}
        self.oc_cfg.write_text(json.dumps(cfg), encoding="utf-8")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PERM: ส่งสิทธิ์ external_dirs", r.stdout)
        self.assertNotIn("ยังไม่มี allow", r.stdout)
        self.assertNotIn("WARN: อ่าน", r.stdout)
        # ไม่มี external_dirs = ไม่พิมพ์อะไรเพิ่ม · opencode.json เสีย (ลืมคอมมา) → เตือน
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False}), encoding="utf-8")
        r = self.run_q(*self.base())
        self.assertNotIn("PERM:", r.stdout)
        self.oc_cfg.write_text('{"permission": {"external_directory": {"*": "ask"\n "D:/x/*": "allow"}}}', encoding="utf-8")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WARN: อ่าน", r.stdout)
        self.assertIn("JSON เสีย", r.stdout)
        # server สด: ถาม /config ของ server (โหลด config ตอนเปิด ไม่เห็น env ของงาน)
        import http.server
        import threading
        sys.path.insert(0, str(REPO))
        import flashq
        perm_srv = {"external_directory": {"*": "ask"}}

        class Hh(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                body = json.dumps({"permission": perm_srv, "provider": {"p": {"options": {"apiKey": "x"}}}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hh)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}"
            flashq.OC_CONFIG = self.oc_cfg
            flashq.HOME = self.home
            out = "\n".join(flashq.perm_precheck(["D:/outside/lib/*"], url, self.proj))
            self.assertIn("ยังไม่อนุญาต external_dirs: D:/outside/lib/*", out)
            self.assertIn("(DENIED)", out)
            self.assertIn('"D:\\\\outside\\\\lib\\\\*": "allow"', out)
            self.assertNotIn("apiKey", out)
            perm_srv["external_directory"]["D:/outside/*"] = "allow"
            out = "\n".join(flashq.perm_precheck(["D:/outside/lib/*"], url, self.proj))
            self.assertIn("server opencode อนุญาต external_dirs แล้ว", out)
            self.assertNotIn("WARN: server", out)
        finally:
            srv.shutdown()
        # perm_allows: กฎเจาะจงชนะ "*" · deny เจาะจงชนะ allow กว้าง · ค่าเป็นสตริง
        self.assertTrue(flashq.perm_allows({"*": "ask", "D:\\x\\*": "allow"}, "D:/x/y/*"))
        self.assertFalse(flashq.perm_allows({"*": "allow", "D:/x/*": "deny"}, "D:/x/y/*"))
        self.assertFalse(flashq.perm_allows({"*": "ask"}, "D:/x/*"))
        self.assertTrue(flashq.perm_allows("allow", "D:/x/*"))
        self.assertFalse(flashq.perm_allows(None, "D:/x/*"))
        self.assertEqual(flashq.external_dirs({"external_dirs": ["D:/a", "D:/b/*", " "]}), ["D:/a/*", "D:/b/*"])

    def test_investigate_subagent_fails_and_never_conflicts(self):
        r = self.run_q("investigate", "--no-open", "สืบหน่อย", env={"FAKE_MODE": "subagent"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("FAIL", r.stdout + r.stderr)

    def test_ui_submit_and_retry_keep_investigate_kind(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.env["FLASHQ_LIVE_URL"] = f"http://127.0.0.1:{s.getsockname()[1]}"
        base = self.start_ui()
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": self.ui_token(base)}
        good = {"project": str(self.proj), "kind": "investigate", "message": "-บรีฟขึ้นต้นด้วยขีด", "no_open": True}
        self.assertEqual(self.http(base + "/api/submit", json.dumps({**good, "message": ""}).encode(), hdr)[0], 400)
        code, body = self.http(base + "/api/submit", json.dumps(good).encode(), hdr)
        self.assertEqual(code, 200, body)
        jid = json.loads(body)["job"]
        self.wait_job(jid)
        code, body = self.http(base + "/api/retry", json.dumps({"id": jid, "no_open": True}).encode(), hdr)
        self.assertEqual(code, 200, body)
        jid2 = json.loads(body)["job"]
        self.wait_job(jid2)
        job2 = json.loads((self.home / "jobs" / f"{jid2}.json").read_text(encoding="utf-8"))
        self.assertEqual((job2["kind"], job2["agent"], job2["readonly"], job2["message"]),
                         ("investigate", "flash-investigator", True, "-บรีฟขึ้นต้นด้วยขีด"))
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(argv[-1], "-บรีฟขึ้นต้นด้วยขีด")
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["stats"]["by_project"], [])
        self.assertEqual([(g["name"], g["n"]) for g in st["stats"]["by_kind"]], [("investigate", 2)])
        html = self.http(base + "/")[1]
        for needle in ('value="investigate"', "msgMode"):
            self.assertIn(needle, html)

    def test_auto_skip_conflict_and_overlap_waits(self):
        """auto: งานที่ไฟล์ซ้อนต้องรอ (เหตุผลบอกไฟล์) · งานถัดไปที่ไม่ชนได้เริ่มก่อน (ข้ามงานที่ชน)"""
        self.auto_plan()
        r = self.run_q("config", "schedule", "auto")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("max_parallel = 2", r.stdout)  # auto ตั้ง 2 ช่องให้เอง
        self.assertIn("schedule = auto", self.run_q("config").stdout)
        p1 = self.submit("PLAN.md", "T-01", sleep="8")
        self.wait_for(lambda: self.by_key().get("T-01", {}).get("status") == "running", msg="T-01 ไม่เริ่ม")
        p2 = self.submit("PLAN.md", "T-02", sleep="1")
        time.sleep(1.5)
        p3 = self.submit("PLAN.md", "T-03", sleep="1")
        self.wait_for(lambda: self.by_key().get("T-03", {}).get("status") in ("running", "ok"), msg="T-03 ไม่ได้แซง")
        st = self.run_q("status").stdout
        self.assertIn("จัดคิวแบบ auto", st)
        self.assertIn("ชนกับ", st)
        self.assertIn("src/a.cpp", st)
        o = [p.communicate(timeout=120)[0] for p in (p1, p2, p3)]
        for x in o:
            self.assertIn("FLASH_RUN=OK", x)
        j = self.by_key()
        self.assertLess(j["T-03"]["started"], j["T-01"]["finished"])  # แซงงานที่ชน
        self.assertGreaterEqual(j["T-02"]["started"], j["T-01"]["finished"])  # ไฟล์ซ้อน = รอ
        self.assertIn("ชนกับ", o[1])

    def test_auto_other_project_runs_unknown_files_wait(self):
        """auto: โปรเจกต์ต่างกันรันพร้อมกัน (แม้ไม่รู้ไฟล์) · โปรเจกต์เดียวกันที่ดึงรายการไฟล์ไม่ได้ = รอ"""
        self.auto_plan()
        proj2 = self.tmp / "proj2"
        proj2.mkdir()
        (proj2 / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False}), encoding="utf-8")
        self.assertEqual(self.run_q("config", "schedule", "auto").returncode, 0)
        self.assertEqual(self.run_q("config", "max_parallel", "3").returncode, 0)
        p1 = self.submit("PLAN.md", "T-01", sleep="8")
        self.wait_for(lambda: self.by_key().get("T-01", {}).get("status") == "running", msg="T-01 ไม่เริ่ม")
        p2 = self.submit("--message", "SAME", sleep="1")
        time.sleep(1.5)
        p3 = self.submit("--message", "OTHER", sleep="1", project=proj2)
        self.wait_for(lambda: self.by_key().get("OTHER", {}).get("status") in ("running", "ok"), msg="คนละโปรเจกต์ไม่ได้รันพร้อมกัน")
        self.assertIn("ดึงรายการไฟล์ของงานนี้ไม่ได้", self.run_q("status").stdout)
        for p in (p1, p2, p3):
            self.assertIn("FLASH_RUN=OK", p.communicate(timeout=120)[0])
        j = self.by_key()
        self.assertLess(j["OTHER"]["started"], j["T-01"]["finished"])
        self.assertGreaterEqual(j["SAME"]["started"], j["T-01"]["finished"])

    def test_auto_starvation_locks_head(self):
        """auto: งานที่ชนรอเกิน starve_min → ล็อกหัวคิว งานหลังจากนั้นห้ามแซงแม้ไม่ชน"""
        self.auto_plan()
        self.assertEqual(self.run_q("config", "schedule", "auto").returncode, 0)
        self.assertEqual(self.run_q("config", "starve_min", "0.05").returncode, 1)  # ต่ำกว่าขั้นต่ำ
        self.assertEqual(self.run_q("config", "starve_min", "0.1").returncode, 0)  # 6 วิ
        p1 = self.submit("PLAN.md", "T-01", sleep="14")
        self.wait_for(lambda: self.by_key().get("T-01", {}).get("status") == "running", msg="T-01 ไม่เริ่ม")
        p2 = self.submit("PLAN.md", "T-02", sleep="1")
        time.sleep(7.5)  # T-02 รอเกิน 6 วิ
        p3 = self.submit("PLAN.md", "T-03", sleep="1")
        time.sleep(2)
        st = self.run_q("status").stdout
        self.assertIn("ล็อกหัวคิว", st)
        self.assertIn("กันอดตาย", st)
        self.assertEqual(self.by_key()["T-03"]["status"], "queued")
        for p in (p1, p2, p3):
            self.assertIn("FLASH_RUN=OK", p.communicate(timeout=120)[0])
        j = self.by_key()
        self.assertGreaterEqual(j["T-03"]["started"], j["T-01"]["finished"])

    def test_plan_declarations_and_conflicts(self):
        """flashq-files / flashq-parallel ในแผน · เกณฑ์ชน: คนละโปรเจกต์ · ไฟล์ซ้อน · glob · ไฟล์/โฟลเดอร์ร่วม"""
        sys.path.insert(0, str(REPO))
        import flashq
        P = str(self.proj)
        (self.proj / "CMakeLists.txt").write_text("x", encoding="utf-8")
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False, "parallel_shared": ["Proto/"]}),
                                               encoding="utf-8")
        (self.proj / "A.md").write_text(
            "# A\n## 0.\n- `flashq-files: Client/a.cpp, Client\\UI\\*.h`\n```\nflashq-files: Fake/x.cpp\n```\n"
            "- [ ] **T-01** `Other/zzz.cpp`\n", encoding="utf-8")
        (self.proj / "B.md").write_text("# B\nflashq-files: `MapEditor/b.cpp`\n- [ ] **T-01** x\n", encoding="utf-8")
        (self.proj / "C.md").write_text("# C\nflashq-files: Client/UI/w.h\n", encoding="utf-8")
        (self.proj / "D.md").write_text("# D\nflashq-files: <ไฟล์ที่แตะ>\nflashq-parallel: no\n- [ ] **T-01** `Tools/t.py`\n",
                                        encoding="utf-8")
        (self.proj / "E.md").write_text("# E\nflashq-files: Common/x.h\n", encoding="utf-8")
        (self.proj / "F.md").write_text("# F\nflashq-files: CMakeLists.txt\n", encoding="utf-8")
        (self.proj / "G.md").write_text("# G\nflashq-files: Proto/p.h\n", encoding="utf-8")
        self.assertEqual(flashq.plan_meta(P, "A.md"), {"files": ["Client/UI/*.h", "Client/a.cpp"], "parallel": True})
        self.assertEqual(flashq.plan_meta(P, "D.md"), {"files": None, "parallel": False})  # placeholder ถูกข้าม
        self.assertEqual(flashq.job_info({"project": P, "plan": "D.md", "tasks": "T-01"})["files"], ["Tools/t.py"])
        (self.proj / "H.md").write_text("# H\nflashq-files: MapEditor/b.cpp\nflashq-parallel: no — แตะ build ทั้งโปรเจกต์\n", encoding="utf-8")
        self.assertEqual(flashq.plan_meta(P, "H.md")["why"], "แตะ build ทั้งโปรเจกต์")
        self.assertNotIn("why", flashq.plan_meta(P, "D.md"))
        J = lambda plan, proj=P: {"id": plan, "project": proj, "plan": plan, "tasks": "T-01"}
        c = lambda a, b: flashq.conflict_reason(J(a), J(b), flashq.job_info)
        self.assertEqual(c("A.md", "B.md"), "")  # Client กับ MapEditor ไม่ชน
        self.assertIn("Client/UI/*.h", c("A.md", "C.md"))  # glob ครอบไฟล์
        self.assertIn("แผนสั่งให้รอ", c("D.md", "B.md"))
        self.assertIn("flashq-parallel", c("B.md", "D.md"))
        self.assertIn("แผนไม่ได้เขียนเหตุผล", c("D.md", "B.md"))
        self.assertIn("เหตุผลจากแผน: แตะ build ทั้งโปรเจกต์", c("H.md", "A.md"))
        self.assertIn("ไฟล์ที่ซ้อนกันจริง: MapEditor/b.cpp", c("H.md", "B.md"))
        self.assertIn("ไฟล์ที่ประกาศไม่ซ้อนกัน", c("H.md", "A.md"))
        self.assertIn("ใช้ร่วม", c("E.md", "B.md"))  # Common/ = โฟลเดอร์ร่วมค่าเริ่มต้น
        self.assertIn("CMakeLists.txt", c("F.md", "B.md"))  # ไฟล์ระดับรากที่มีจริง
        self.assertIn("Proto/p.h", c("G.md", "B.md"))  # parallel_shared ของโปรเจกต์
        self.assertIn("ดึงรายการไฟล์", c("NOPE.md", "B.md"))
        self.assertEqual(flashq.conflict_reason(J("E.md"), J("E.md", str(self.tmp)), flashq.job_info), "")  # คนละโปรเจกต์
        self.assertTrue(flashq.paths_overlap("**", "x/y.cpp"))
        self.assertFalse(flashq.paths_overlap("Client/UI/*.h", "Client/a.cpp"))

    def test_ui_schedule_config_and_reason(self):
        """ui: POST /api/config schedule (ผิด = 400) · /api/state บอกโหมด + เหตุผลที่งานรอคิว"""
        self.auto_plan()
        base = self.start_ui()
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": self.ui_token(base)}
        self.assertEqual(self.http(base + "/api/config", json.dumps({"schedule": "lifo"}).encode(), hdr)[0], 400)
        code, out = self.http(base + "/api/config", json.dumps({"schedule": "auto"}).encode(), hdr)
        self.assertEqual(code, 200, out)
        self.assertEqual(json.loads(out)["max_parallel"], 2)
        p1 = self.submit("PLAN.md", "T-01", sleep="6")
        self.wait_for(lambda: self.by_key().get("T-01", {}).get("status") == "running", msg="T-01 ไม่เริ่ม")
        p2 = self.submit("PLAN.md", "T-02", sleep="1")
        st = self.wait_for(lambda: (lambda s: s if s["queued"] else None)(json.loads(self.http(base + "/api/state")[1])),
                           msg="ไม่เห็นงานรอคิว")
        self.assertEqual(st["schedule"], "auto")
        self.assertIn("ชนกับ", st["queued"][0]["wait_reason"])
        for p in (p1, p2):
            self.assertIn("FLASH_RUN=OK", p.communicate(timeout=120)[0])

    def test_goal_cancel_blocks_verify_and_card(self):
        """goal cancel: บรรทัดสถานะใต้หัว GOAL · cancelled ในไฟล์สถานะ · การ์ดสถานะยกเลิก (ไม่ลบ) · รายการ commit จาก §4 ของแผน + git revert
        · verify/check ปฏิเสธ GOAL=CANCELLED ไม่สร้างการ์ดใหม่ · ปุ่มเว็บ ยกเลิก/ซ่อน · เปิดใหม่ = ลบบรรทัด + check --reset"""
        py = f'"{sys.executable}"'
        goal = self.goal_repo(f"# GOAL: ค่าใหม่\n> ไฟล์ธง\n\n## เกณฑ์\n- [ ] G-01 ค่าเป็น new · ตรวจ: `{py} tests/acc.py` · ต้องเห็น: `VAL=new`\n"
                              "goal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 5\n")
        gq = lambda *a: self.run_q("goal", *a)  # noqa: E731
        self.assertIn("GOAL_CHECK=OK", gq("check", "docs/plans/GOAL_x.md").stdout)
        self.assertIn("GOAL=CONTINUE รอบ 1/5", gq("verify", "docs/plans/GOAL_x.md").stdout)
        git = lambda *a: subprocess.run(["git", "-C", str(self.proj), *a], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()  # noqa: E731
        (self.proj / "src" / "a.txt").write_text("worse\n", encoding="utf-8")
        git("commit", "-qam", "งาน Flash (T-01)")
        sha = git("rev-parse", "--short=7", "HEAD")
        (goal.parent / "PLAN_FLASH_x_R1.md").write_text(
            "# แผน\n## 1. งาน\n| a | b |\n|---|---|\n| T-09 | 1234567abc |\n## 4. บันทึกผล\n| งาน | ผล | commit | หลักฐาน |\n|---|---|---|---|\n"
            f"| T-01 | ✅ | {sha} | log deadbeefcafe |\n| T-02 | ⛔ | — | |\n```\n# 4. ในโค้ด\n| x | {sha} |\n```\n", encoding="utf-8")
        r = gq("cancel", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL_CANCEL=FAIL", r.stdout)
        r = gq("cancel", "docs/plans/GOAL_x.md", "--reason", "ทำออกมา  แย่ลง")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GOAL=CANCELLED", r.stdout)
        self.assertIn(f"git revert --no-edit {sha}", r.stdout, r.stdout)
        self.assertNotIn("deadbeef", r.stdout)  # คอลัมน์อื่นในตารางที่มีคอลัมน์ commit ไม่นับ
        self.assertIn("ต้อง commit ไฟล์ GOAL เอง", r.stdout)
        lines = goal.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:4], ["# GOAL: ค่าใหม่", "", f"> **สถานะ: ยกเลิกโดย user ({time.strftime('%Y-%m-%d')})** — ทำออกมา แย่ลง", ""])
        self.assertEqual(lines[4], "> ไฟล์ธง")
        self.assertEqual(git("log", "-1", "--format=%s"), "งาน Flash (T-01)")  # ไม่ commit เอง
        st = json.loads((self.proj / ".tmp" / "flashq-goal" / "GOAL_x.json").read_text(encoding="utf-8"))
        self.assertEqual((st["cancelled"]["reason"], st["cancelled"]["rounds"], len(st["rounds"])), ("ทำออกมา แย่ลง", 1, 1))
        cards = list((self.home / "goals").glob("*.json"))
        self.assertEqual(len(cards), 1)
        self.assertEqual(json.loads(cards[0].read_text(encoding="utf-8"))["cancelled"]["reason"], "ทำออกมา แย่ลง")
        r = gq("cancel", "docs/plans/GOAL_x.md", "--reason", "ซ้ำ")
        self.assertIn("ยกเลิกไว้แล้ว", r.stdout)
        self.assertEqual(goal.read_text(encoding="utf-8").count("สถานะ: ยกเลิก"), 1)
        mod = self.load_mod("flashq_goalcancel")
        mod.GOALS_DIR = self.home / "goals"
        g = mod.ui_goals([])[0]
        self.assertEqual((g["verdict"], g["phase"]["step"], g["cancelled"]["reason"]), ("CANCELLED", "result", "ทำออกมา แย่ลง"))
        self.assertEqual(mod.goal_ui_action(g["id"], "verify", {})[0], 409)
        self.assertEqual(mod.goal_ui_action(g["id"], "claude", {})[0], 409)
        cards[0].unlink()
        for act in ("verify", "check", "human"):
            r = gq(act, "docs/plans/GOAL_x.md", *(["G-01", "--pass"] if act == "human" else []))
            self.assertIn("GOAL=CANCELLED", r.stdout, act)
            self.assertEqual(r.returncode, 1)
        self.assertIn("GOAL=CANCELLED", gq("check", "docs/plans/GOAL_x.md", "--reset").stdout)  # บรรทัดยกเลิกยังอยู่ = ไม่เปิดใหม่
        r = gq("status", "docs/plans/GOAL_x.md")
        self.assertEqual((r.returncode, "GOAL=CANCELLED" in r.stdout), (0, True))
        self.assertEqual(list((self.home / "goals").glob("*.json")), [])  # ธงที่ยกเลิกไม่สร้างการ์ดใหม่
        self.assertEqual(len(json.loads((self.proj / ".tmp" / "flashq-goal" / "GOAL_x.json").read_text(encoding="utf-8"))["rounds"]), 1)
        gq("cancel", "docs/plans/GOAL_x.md", "--reason", "x")  # สั่ง cancel อีก = การ์ดยกเลิกกลับมา → ซ่อนได้
        g = mod.ui_goals([])[0]
        self.assertEqual(mod.goal_ui_action(g["id"], "hide", {})[0], 200)
        self.assertEqual((mod.ui_goals([]), list((self.home / "goals").glob("*"))), ([], []))
        # เปิดใหม่: user ยืนยัน → ลบบรรทัดสถานะ → check --reset
        goal.write_text("\n".join(x for x in goal.read_text(encoding="utf-8").splitlines() if "สถานะ: ยกเลิก" not in x) + "\n", encoding="utf-8")
        self.assertIn("GOAL=CANCELLED", gq("check", "docs/plans/GOAL_x.md").stdout)  # ไม่ --reset = ยังปิดอยู่ (สถานะในไฟล์ .tmp)
        self.assertIn("GOAL_CHECK=OK", gq("check", "docs/plans/GOAL_x.md", "--reset").stdout)
        self.assertIn("GOAL=CONTINUE", gq("verify", "docs/plans/GOAL_x.md").stdout)
        g = mod.ui_goals([])[0]
        self.assertEqual(mod.goal_ui_action(g["id"], "hide", {})[0], 409)  # ธงที่ยังไม่ยกเลิก = ซ่อนไม่ได้
        from unittest import mock
        with mock.patch.dict(os.environ, {"FLASHQ_HOME": str(self.home), "CLAUDE_CODE_SESSION_ID": ""}):  # ปุ่มเว็บเรียก goal cancel ตัวเดียวกัน
            self.assertEqual(mod.goal_ui_action(g["id"], "cancel", {})[0], 400)  # ไม่มีเหตุ
            code, d = mod.goal_ui_action(g["id"], "cancel", {"reason": "จากหน้าเว็บ"})
        self.assertEqual(code, 200, d)
        self.assertIn("GOAL=CANCELLED", d["message"])
        self.assertEqual(mod.ui_goals([])[0]["cancelled"]["reason"], "จากหน้าเว็บ")

    def test_goal_cancel_line_by_hand_and_hint(self):
        """บรรทัด "สถานะ: ยกเลิกโดย user" ที่เขียนเองในไฟล์ GOAL = ยกเลิก (การ์ดเดิมขึ้นยกเลิก · verify ปฏิเสธ)
        · คนตรวจไม่ผ่าน 2 รอบติด (ข้าม check --reset) / ถอยหลังซ้ำ = แนะนำพิจารณายกเลิก"""
        py = f'"{sys.executable}"'
        body = (f"# GOAL: ค่าใหม่\n\n## เกณฑ์\n- [ ] G-01 ค่าเป็น new · ตรวจ: `{py} tests/acc.py` · ต้องเห็น: `VAL=new`\n"
                "- [ ] G-02 อ่านง่าย · คนตรวจ: เปิด src/a.txt\ngoal-files: src/*\ngoal-locked: tests/*\ngoal-max-rounds: 5\n")
        goal = self.goal_repo(body)
        gq = lambda *a: self.run_q("goal", *a)  # noqa: E731
        gq("check", "docs/plans/GOAL_x.md")
        (self.proj / "src" / "a.txt").write_text("new\n", encoding="utf-8")
        self.assertIn("GOAL=DONE_NEEDS_USER", gq("verify", "docs/plans/GOAL_x.md").stdout)
        r = gq("human", "docs/plans/GOAL_x.md", "G-02", "--fail", "อ่านยาก")
        self.assertNotIn("แนะนำ: พิจารณายกเลิกธง", r.stdout)
        gq("check", "docs/plans/GOAL_x.md", "--reset")
        (self.proj / "src" / "a.txt").write_text("new2\n", encoding="utf-8")
        self.assertIn("GOAL=DONE_NEEDS_USER", gq("verify", "docs/plans/GOAL_x.md").stdout)
        r = gq("human", "docs/plans/GOAL_x.md", "G-02", "--fail", "ยังอ่านยาก")
        self.assertIn("แนะนำ: พิจารณายกเลิกธง (flashq goal cancel docs/plans/GOAL_x.md", r.stdout, r.stdout)
        self.assertIn("คนตรวจให้ไม่ผ่าน 2 รอบติด", r.stdout)
        gq("check", "docs/plans/GOAL_x.md", "--reset")
        (self.proj / "src" / "a.txt").write_text("old\n", encoding="utf-8")
        r = gq("verify", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL=CONTINUE", r.stdout)
        self.assertIn("แนะนำ: พิจารณายกเลิกธง", r.stdout, r.stdout)
        mod = self.load_mod("flashq_goalcancel2")
        mod.GOALS_DIR = self.home / "goals"
        self.assertIn("คนตรวจให้ไม่ผ่าน 2 รอบติด", mod.ui_goals([])[0]["rounds"][-1]["cancel_hint"])
        ok, bad = {"G-01": {"ok": True}}, {"G-01": {"ok": False}}
        self.assertIn("ถอยหลังแล้ว 2 รอบ", mod.goal_cancel_hint({"rounds": [{"results": ok}, {"results": bad}, {"results": ok}, {"results": bad}]}))
        self.assertEqual(mod.goal_cancel_hint({"rounds": [{"results": ok}, {"results": bad}]}), "")
        # เขียนบรรทัดเองแบบ D:\AI (มีเหตุยาวหลังขีด) → การ์ดเดิมขึ้นยกเลิก · verify ปฏิเสธ
        goal.write_text(body.replace("# GOAL: ค่าใหม่\n", "# GOAL: ค่าใหม่\n\n> **สถานะ: ยกเลิกโดย user (2026-10-20)** — หยุดวนที่รอบ R2 · ไม่มีแผน R3\n"), encoding="utf-8")
        g = mod.ui_goals([])[0]
        self.assertEqual((g["verdict"], g["cancelled"]["reason"]), ("CANCELLED", "ยกเลิกโดย user (2026-10-20) — หยุดวนที่รอบ R2 · ไม่มีแผน R3"))
        self.assertEqual(mod.goal_ui_action(g["id"], "hide", {})[0], 200)
        r = gq("verify", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL=CANCELLED", r.stdout)
        self.assertIn("หยุดวนที่รอบ R2", r.stdout)
        self.assertEqual(list((self.home / "goals").glob("*.json")), [])
        self.assertEqual(mod.goal_cancel_note(self.proj / "README_none.md"), "")

    def test_usage_sums_claude_tokens_per_plan(self):
        """`flashq usage <แผน>`: สแกน transcript ของ Claude Code เฉพาะโฟลเดอร์ที่ cwd ตรงกับโปรเจกต์ (รวม worktree · ไม่รวมโฟลเดอร์ชื่อคล้าย)
        · นับเฉพาะ session ที่อ้างถึงชื่อแผน · บรรทัดซ้ำ message.id เดียวกันนับครั้งเดียว · รวม subagent · แยกขั้นวางแผน/ตรวจ/รอบแก้
        · --since ตัดตาม mtime · บันทึก usage/<stem>.json ให้ UI · ไม่มี session = exit 1 + USAGE=…sessions=0 · โหมดโปรเจกต์รวมทุกแผน"""
        mod = self.load_mod("flashq_usage")
        claude = self.tmp / "claude"
        key = mod.claude_project_key(self.proj.resolve())
        main = claude / "projects" / key
        wt = claude / "projects" / (key + "--claude-worktrees-w1")
        other = claude / "projects" / (key + "-other")  # ชื่อขึ้นต้นเหมือนกันแต่คนละโปรเจกต์ → ห้ามนับ
        for d in (main, wt, other):
            d.mkdir(parents=True)
        (self.proj / "docs" / "plans").mkdir(parents=True)
        (self.proj / "docs" / "plans" / "PLAN_X.md").write_text("# แผน X\n", encoding="utf-8")

        def jl(f, *entries):
            f.write_text("".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in entries), encoding="utf-8")

        def asst(mid, model, i, o, cr=0, cw=0, text="ok"):  # key "type" อยู่ท้าย object เหมือนไฟล์จริง (message ยาวมาก่อน)
            return {"cwd": str(self.proj), "message": {"id": mid, "model": model, "role": "assistant",
                                                        "content": [{"type": "text", "text": text}],
                                                        "usage": {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw}},
                    "timestamp": "2026-10-20T10:00:00.000Z", "type": "assistant"}

        def user(text):
            return {"cwd": str(self.proj), "message": {"role": "user", "content": [{"type": "text", "text": text}]}, "timestamp": "2026-10-20T09:59:00.000Z", "type": "user"}

        # a = วางแผน (Opus · response เดียวถูกเขียน 2 บรรทัด → นับครั้งเดียว)
        jl(main / "sess-a.jsonl", user("<command-name>/flash-plan</command-name> เขียนแผน docs/plans/PLAN_X.md"),
           asst("m1", "claude-opus-5-5", 100, 50, 1000, 200), asst("m1", "claude-opus-5-5", 100, 50, 1000, 200, text="ซ้ำ"),
           asst("m2", "claude-opus-5-5", 10, 5))
        # b = ตรวจ (Sonnet · เรียกสกิลผ่าน tool Skill)
        jl(main / "sess-b.jsonl", {"type": "user", "message": {"role": "user", "content": "ตรวจงานหน่อย"}},
           {"type": "assistant", "message": {"id": "m3", "model": "claude-sonnet-5", "role": "assistant", "usage": {"input_tokens": 20, "output_tokens": 10, "cache_read_input_tokens": 500},
                                             "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "flash-check", "args": "docs/plans/PLAN_X.md"}}]}})
        # c = รอบแก้ ใน worktree + subagent ของมัน
        jl(wt / "sess-c.jsonl", user("ส่งรอบแก้ T-01R ของ PLAN_X ให้ Flash"), asst("m4", "claude-opus-5-5", 30, 15))
        sub = wt / "sess-c" / "subagents" / "agent-s1.jsonl"
        sub.parent.mkdir(parents=True)
        jl(sub, asst("m5", "claude-haiku-5-5", 5, 5))
        # d = แผนอื่น · e = โฟลเดอร์คนละโปรเจกต์ที่พูดถึง PLAN_X
        jl(main / "sess-d.jsonl", user("/flash-plan PLAN_Y"), asst("m6", "claude-opus-5-5", 7, 7))
        jl(other / "sess-e.jsonl", user("/flash-plan PLAN_X"), asst("m7", "claude-opus-5-5", 999, 999))
        env = {"FLASHQ_CLAUDE_HOME": str(claude)}
        r = self.run_q("usage", "docs/plans/PLAN_X.md", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # in ใหม่ = input + cache เขียน: (110+20+35) + 200 · out = 55+10+20 · cache อ่าน = 1000+500
        self.assertIn("USAGE=PLAN_X claude_in=365 claude_out=85 cache_read=1500 sessions=3", r.stdout)
        self.assertIn("วางแผน", r.stdout)
        self.assertIn("ตรวจ", r.stdout)
        self.assertIn("รอบแก้", r.stdout)
        self.assertNotIn("sess-e", r.stdout)
        u = json.loads((self.home / "usage" / "PLAN_X.json").read_text(encoding="utf-8"))
        self.assertEqual(u["sessions"], 3)
        self.assertEqual({k: v["sessions"] for k, v in u["by_phase"].items()}, {"plan": 1, "check": 1, "fix": 1})
        self.assertEqual({x["id"]: x["phase"] for x in u["session_list"]}, {"sess-a": "plan", "sess-b": "check", "sess-c": "fix"})
        self.assertEqual(u["total"]["tokens"], 365 + 85 + 1500)
        self.assertEqual(sorted(u["by_model"]), ["claude-haiku-5-5", "claude-opus-5-5", "claude-sonnet-5"])
        self.assertGreater(u["total"]["usd"], 0)
        self.assertEqual(sum(v["pct"] for v in u["by_phase"].values()), 100)
        # UI: บรรทัดสั้นบนการ์ดงาน/ธง
        mod.USAGE_DIR = self.home / "usage"
        b = mod.usage_brief("PLAN_X")
        self.assertEqual((b["sessions"], b["tokens"], sorted(b["pct"])), (3, 1950, ["check", "fix", "plan"]))
        self.assertEqual(mod.usage_brief("PLAN_NONE"), {})
        # --since: session เก่ากว่าช่วงถูกตัดออก
        old = time.time() - 40 * 86400
        os.utime(main / "sess-a.jsonl", (old, old))
        r = self.run_q("usage", "docs/plans/PLAN_X.md", "--since", "30", env=env)
        self.assertIn("USAGE=PLAN_X claude_in=55 claude_out=30 cache_read=500 sessions=2", r.stdout)
        r = self.run_q("usage", "docs/plans/PLAN_X.md", "--since", "60", env=env)
        self.assertIn("sessions=3", r.stdout)
        # ไม่มี session ที่อ้างถึงแผน → exit 1 แต่ยังพิมพ์บรรทัด USAGE
        r = self.run_q("usage", "docs/plans/PLAN_Z.md", env=env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("USAGE=PLAN_Z claude_in=0 claude_out=0 cache_read=0 sessions=0", r.stdout)
        self.assertFalse((self.home / "usage" / "PLAN_Z.json").exists())
        # โหมดโปรเจกต์: ทุกแผนที่ถูกพูดถึง
        r = self.run_q("usage", ".", "--since", "60", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("USAGE=PLAN_X ", r.stdout)
        self.assertIn("USAGE=PLAN_Y claude_in=7 claude_out=7 cache_read=0 sessions=1", r.stdout)
        self.assertIn("รวมทั้งโปรเจกต์ (session ไม่ซ้ำ 4)", r.stdout)
        # ไม่เคยเปิดโปรเจกต์ใน Claude Code เลย → exit 1
        r = self.run_q("usage", "docs/plans/PLAN_X.md", env={"FLASHQ_CLAUDE_HOME": str(self.tmp / "empty")})
        self.assertEqual(r.returncode, 1)
        self.assertIn("sessions=0", r.stdout)


class NewProjectTest(unittest.TestCase):
    """โปรเจกต์ใหม่ที่ branch หลักไม่ใช่ master: ตรวจอัตโนมัติ + flashq init"""
    setUp, tearDown, run_q, base = (FlashqTest.setUp, FlashqTest.tearDown, FlashqTest.run_q, FlashqTest.base)

    def load_mod(self, name):
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def git(self, cwd, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def make_repo(self, branch="main", push=True):
        """repo ใหม่ (ไม่มี .flash.json) + bare origin · แผนถูก push เข้า origin/<branch>"""
        shutil.rmtree(self.proj)
        origin = self.tmp / "origin.git"
        self.git(self.tmp, "init", "-q", "--bare", "-b", branch, str(origin))
        self.proj.mkdir()
        self.git(self.proj, "init", "-q", "-b", branch)
        (self.proj / "PLAN.md").write_text("# plan\n", encoding="utf-8")
        self.git(self.proj, "add", "PLAN.md")
        self.git(self.proj, "commit", "-q", "-m", "plan")
        self.git(self.proj, "remote", "add", "origin", str(origin))
        if push:
            self.git(self.proj, "push", "-q", "origin", branch)

    def test_autodetect_main_branch_without_flash_json(self):
        self.make_repo("main")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=OK", r.stdout)

    def test_fail_hint_when_plan_not_pushed(self):
        self.make_repo("main", push=False)
        self.git(self.proj, "push", "-q", "origin", "main")  # มี origin/main แต่ไม่มีแผนนี้
        r = self.run_q("run", "NOPE.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ไม่พบแผนใน origin/main", r.stdout)

    def test_plan_precheck_against_remote(self):
        """ตรวจแผนเทียบ origin/<main> ไม่ใช่ไฟล์ในเครื่อง: ไฟล์/anchor ที่มีแค่ในเครื่อง (ยังไม่ push) = แผนพิการ"""
        self.make_repo("main")
        (self.proj / "a.py").write_text("x = 1\n", encoding="utf-8")
        (self.proj / "PRE.md").write_text("- [ ] **T-01** `a.py`\n  - ก่อน: `x = 1`\n  - หลัง: `x = 2`\n"
                                          "- [ ] **T-02** `a.py`\n  - ก่อน: `y = 1`\n", encoding="utf-8")
        self.git(self.proj, "add", "a.py", "PRE.md")
        self.git(self.proj, "commit", "-q", "-m", "pre")
        self.git(self.proj, "push", "-q", "origin", "main")
        r = self.run_q("run", "PRE.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 0, r.stdout)
        (self.proj / "a.py").write_text("y = 1\n", encoding="utf-8")  # มีในเครื่องแต่ไม่ได้ push
        r = self.run_q("run", "PRE.md", "T-02", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("แผนพิการ 1 จุด (เทียบ origin/main)", r.stdout)
        self.assertIn("บรรทัด 5 (T-02): ข้อความ ก่อน: ใน a.py ไม่เจอ", r.stdout)

    def test_explicit_main_branch_wins(self):
        self.make_repo("main")
        (self.proj / ".flash.json").write_text(json.dumps({"main_branch": "master"}), encoding="utf-8")
        r = self.run_q(*self.base())
        self.assertEqual(r.returncode, 1)
        self.assertIn("origin/master", r.stdout)
        self.assertIn("main_branch", r.stdout)  # คำแนะนำ

    def test_init_creates_config_gitignore_template(self):
        self.make_repo("main")
        r = self.run_q("init")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = json.loads((self.proj / ".flash.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["main_branch"], cfg["remote"], cfg["plan_dir"]), ("main", "origin", "docs/plans"))
        self.assertNotIn("require_plan_in_remote", cfg)
        self.assertIn(".tmp/", (self.proj / ".gitignore").read_text(encoding="utf-8"))
        self.assertTrue((self.proj / "docs" / "plans" / "FLASH_PLAN_TEMPLATE.md").exists())
        self.assertIn("ขั้นต่อไป", r.stdout)
        # รันซ้ำ = ไม่เปลี่ยนอะไร ไม่เพิ่ม .tmp/ ซ้ำ
        r2 = self.run_q("init")
        self.assertEqual(r2.returncode, 0)
        self.assertEqual((self.proj / ".gitignore").read_text(encoding="utf-8").count(".tmp/"), 1)
        self.assertIn("เหมือนเดิม", r2.stdout)

    def test_init_keeps_user_values_unless_force(self):
        self.make_repo("main")
        (self.proj / ".flash.json").write_text(json.dumps({"main_branch": "dev", "rules": "x"}), encoding="utf-8")
        self.run_q("init")
        cfg = json.loads((self.proj / ".flash.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["main_branch"], cfg["rules"]), ("dev", "x"))
        self.run_q("init", "--force")
        cfg = json.loads((self.proj / ".flash.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["main_branch"], cfg["rules"]), ("main", "x"))

    def test_init_commit_pushes_only_own_files(self):
        self.make_repo("main")
        (self.proj / "other.txt").write_text("ค้าง\n", encoding="utf-8")  # ไฟล์ค้างที่ init ต้องไม่แตะ
        r = self.run_q("init", "--commit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("push       origin/main สำเร็จ", r.stdout)
        self.git(self.proj, "fetch", "-q", "origin")
        files = self.git(self.proj, "ls-tree", "-r", "--name-only", "origin/main").split()
        self.assertIn(".flash.json", files)
        self.assertNotIn("other.txt", files)
        self.assertIn("?? other.txt", self.git(self.proj, "status", "--short"))
        r2 = self.run_q("init", "--commit")  # รันซ้ำ = ไม่มีอะไรต้อง commit
        self.assertIn("ไม่มีอะไรต้อง commit", r2.stdout)

    def test_init_commit_push_timeout_does_not_hang(self):
        """remote ที่ไม่ตอบ: init --commit ต้องเลิก push ตามเวลา (ฆ่า git) แล้วบอกให้ push เอง ไม่ค้างตลอดไป"""
        import socket
        self.make_repo("main")
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        self.addCleanup(srv.close)
        self.git(self.proj, "remote", "set-url", "origin", f"http://127.0.0.1:{srv.getsockname()[1]}/x.git")
        t0 = time.time()
        r = self.run_q("init", "--commit", env={"FLASHQ_PUSH_TIMEOUT_SEC": "3"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(time.time() - t0, 60)
        self.assertIn("push       ล้มเหลว", r.stdout)
        self.assertIn("หมดเวลา", r.stdout)
        self.assertIn("push ไม่เสร็จใน 3 วิ", r.stdout)

    def test_run_timeout_kills_hung_command_and_reports(self):
        """run_timeout: คำสั่งที่ค้างถูกฆ่าตามเวลา (124) · คำสั่งปกติได้ output · หาโปรแกรมไม่เจอ = 127 ไม่โยน exception"""
        mod = self.load_mod("flashq_rt")
        t0 = time.time()
        r = mod.run_timeout([sys.executable, "-c", "import time; time.sleep(60)"], 1)
        self.assertEqual(r.returncode, 124)
        self.assertIn("หมดเวลา", r.stderr)
        self.assertLess(time.time() - t0, 20)
        r = mod.run_timeout([sys.executable, "-c", "print('สวัสดี')"], 30)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "สวัสดี"))
        self.assertEqual(mod.run_timeout(["flashq-no-such-program-xyz"], 5).returncode, 127)
        r = mod.run_timeout([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'a\\0b')"], 30, text=False)
        self.assertEqual(r.stdout, b"a\0b")

    def test_open_in_desktop_times_out(self):
        """oc_desktop_open.mjs ค้าง (desktop ไม่ตอบ) → ข้ามตามเวลา ไม่ให้งานค้างก่อนเริ่มเฝ้า"""
        import contextlib
        import io
        mod = self.load_mod("flashq_desk")
        fake = self.tmp / "repo"
        fake.mkdir()
        (fake / "oc_desktop_open.mjs").write_text("import time; time.sleep(60)\n", encoding="utf-8")  # รันด้วย python แทน node
        mod.REPO, mod.DESKTOP_OPEN_TIMEOUT_SEC = fake, 1
        orig_which = mod.shutil.which  # shutil เป็นโมดูลร่วมทั้ง process → คืนค่าเดิมเสมอ
        self.addCleanup(setattr, mod.shutil, "which", orig_which)
        mod.shutil.which = lambda name, *a, **k: sys.executable if name == "node" else orig_which(name, *a, **k)
        buf = io.StringIO()
        t0 = time.time()
        with contextlib.redirect_stdout(buf):
            mod.open_in_desktop("ses_x", "http://127.0.0.1:1")
        self.assertLess(time.time() - t0, 20)
        self.assertIn("DESKTOP_OPEN=FAIL หมดเวลา 1 วิ", buf.getvalue())

    def test_goal_ui_buttons_report_timeout_instead_of_dropping(self):
        """ปุ่ม ✅/❌ และยกเลิกธงบนหน้าเว็บ: คำสั่ง goal ลูกค้าง → ฆ่าแล้วตอบ 504 + ข้อความไทย (ไม่ใช่ exception หลุดจน handler ตัดการเชื่อมต่อ)"""
        mod = self.load_mod("flashq_goaltimeout")
        mod.GOALS_DIR = self.tmp / "goals_t"
        mod.GOALS_DIR.mkdir()
        fake = self.tmp / "repo_t"
        fake.mkdir()
        mark = self.tmp / "child_pid.txt"
        (fake / "flashq.py").write_text(
            f"import os, time\nopen({str(mark)!r}, 'w').write(str(os.getpid()))\ntime.sleep(60)\n", encoding="utf-8")
        proj = self.tmp / "proj_t"
        proj.mkdir()
        gid = "0123456789ab"
        mod.write_json(mod.GOALS_DIR / f"{gid}.json", {"project": str(proj), "goal": "GOAL_x.md", "rounds": [{"verdict": "CONTINUE"}]})
        mod.REPO, mod.GOAL_UI_CMD_TIMEOUT_SEC = fake, 1
        for action, body in (("human", {"item": "G-02", "ok": True}), ("cancel", {"reason": "เลิกแล้ว"})):
            t0 = time.time()
            code, r = mod.goal_ui_action(gid, action, body)
            self.assertLess(time.time() - t0, 20, action)
            self.assertEqual((code, r["ok"]), (504, False), action)
            self.assertIn("ไม่ตอบภายใน 1 วิ", r["message"], action)
            pid = int(mark.read_text(encoding="utf-8"))
            for _ in range(50):  # ลูกต้องถูกฆ่าจริง ไม่ค้างเป็นกำพร้า
                if not mod.pid_alive(pid, 0):
                    break
                time.sleep(0.1)
            self.assertFalse(mod.pid_alive(pid, 0), f"{action}: ลูกยังไม่ตาย")

    def test_skip_precheck_only_from_plan_form_and_submit_failure_is_reported(self):
        """หน้าเว็บ: --skip-precheck ส่งได้เฉพาะ run ตามแผน · ด่านตรวจที่ล้มหลังหน้าต่างรอ 8 วิต้องมีป้ายเตือน (ไม่เงียบ) และหายเมื่อรับทราบ"""
        mod = self.load_mod("flashq_submit")
        home = self.tmp / "h2"
        mod.HOME, mod.JOBS, mod.LOGS = home, home / "jobs", home / "logs"
        base = {"project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01"}
        argv, err = mod.build_run_argv({**base, "skip_precheck": True})
        self.assertEqual(err, "")
        self.assertIn("--skip-precheck", argv)
        self.assertNotIn("--skip-precheck", mod.build_run_argv(base)[0])
        self.assertNotIn("--skip-precheck", mod.build_run_argv({**base, "kind": "verify", "skip_precheck": True})[0])
        self.assertNotIn("--skip-precheck", mod.build_run_argv({"project": str(self.proj), "message": "x", "skip_precheck": True})[0])
        # process ที่ล้มหลังหน้าต่างรอ → spawn_run วางป้าย · process จบแล้วไม่มีงาน → รายงาน
        fail = [sys.executable, "-c", "import time; time.sleep(2); print('FLASH_RUN=FAIL แผนพิการ 1 จุด')"]
        r = mod.spawn_run(fail, str(self.proj), wait_sec=0.5, body={**base, "secret": "x"})
        self.assertTrue(r["ok"] and not r["job"], r)
        self.assertEqual(mod.submit_failures(), [])  # ยังรันอยู่ = ยังไม่ใช่ความล้ม
        deadline = time.time() + 30
        while not mod.submit_failures() and time.time() < deadline:
            time.sleep(0.3)
        fails = mod.submit_failures()
        self.assertEqual(len(fails), 1, fails)
        self.assertTrue(fails[0]["can_skip"])
        self.assertIn("แผนพิการ", fails[0]["message"])
        self.assertEqual(fails[0]["body"], base)  # เก็บเฉพาะฟิลด์ฟอร์ม
        (mod.LOGS / f"{fails[0]['id']}.out.pending").unlink()  # รับทราบ
        self.assertEqual(mod.submit_failures(), [])
        # งานที่เดินแล้ว (มี SLOT) ไม่ใช่ด่านล้ม → ป้ายถูกล้างเงียบ ๆ
        ok = [sys.executable, "-c", "import time; time.sleep(1); print('SLOT ช่อง 1'); print('FLASH_RUN=FAIL x')"]
        mod.spawn_run(ok, str(self.proj), wait_sec=0.3, body=base)
        time.sleep(3)
        self.assertEqual(mod.submit_failures(), [])
        self.assertEqual(list(mod.LOGS.glob("*.pending")), [])

    def test_init_no_remote_disables_plan_in_remote(self):
        shutil.rmtree(self.proj)
        self.proj.mkdir()
        self.git(self.proj, "init", "-q", "-b", "main")
        r = self.run_q("init")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        cfg = json.loads((self.proj / ".flash.json").read_text(encoding="utf-8"))
        self.assertEqual((cfg["main_branch"], cfg["require_plan_in_remote"]), ("main", False))

    def test_thai_path_and_bom_config_and_separate_gitdir(self):
        """โปรเจกต์จริงที่เจอ: path ไทย (git พิมพ์ UTF-8) · .flash.json มี BOM · .git แยกที่ (--separate-git-dir)"""
        self.make_repo("main")
        thai = self.tmp / "โปรเจกต์ ไทย"
        shutil.move(str(self.proj), str(thai))
        self.proj = thai
        (thai / ".flash.json").write_bytes("﻿".encode("utf-8") + json.dumps({"plan_dir": "แผน"}).encode("utf-8"))
        r = self.run_q("init", "--project", str(thai))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertEqual(json.loads((thai / ".flash.json").read_text(encoding="utf-8-sig"))["plan_dir"], "แผน")  # ไม่ทับค่า BOM ที่ผู้ใช้ตั้ง
        sep = self.tmp / "แยก"
        proj2 = self.tmp / "sepgit"
        proj2.mkdir()
        self.git(proj2, "init", "-q", "-b", "main", "--separate-git-dir", str(sep))
        (proj2 / "PLAN.md").write_text("# p\n", encoding="utf-8")
        (proj2 / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False}), encoding="utf-8")
        self.git(proj2, "add", ".")
        self.git(proj2, "commit", "-q", "-m", "i")
        r = subprocess.run([sys.executable, str(FLASHQ), "run", "PLAN.md", "T-01", "--attach", "none", "--no-open"], cwd=proj2,
                           env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertIn("FLASH_RUN=OK", r.stdout + r.stderr)  # root = proj2 ไม่ใช่โฟลเดอร์แม่ของ .git ที่แยกไว้

    def test_init_install_flag_installs_missing_globals(self):
        self.make_repo("main")
        claude_home = self.tmp / "claude_home"
        env = {"FLASHQ_CLAUDE_HOME": str(claude_home)}
        r = self.run_q("init", env=env)
        self.assertIn("ยังไม่ได้ติดตั้งคำสั่ง global", r.stdout)
        r = self.run_q("init", "--install", env=env)
        self.assertTrue((claude_home / "commands" / "flash-plan.md").exists(), r.stdout)
        self.assertTrue((self.oc_cfg.parent / "command" / "flash.md").exists(), r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

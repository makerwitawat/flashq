"""เทสต์ flashq ด้วย opencode ปลอม (ไม่เรียกโมเดลจริง) · รัน: python tests\\test_flashq.py"""
import json
import os
import re
import shutil
import socket
import subprocess
import types
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
                                  encoding="utf-8", timeout=120, stdin=subprocess.DEVNULL)  # ไม่มี TTY → คำสั่งที่ถามเลือกไม่ค้างรอ input
        return subprocess.Popen(cmd, cwd=self.proj, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", stdin=subprocess.DEVNULL)

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

    def test_plan_precheck_warns_on_unknown_skill(self):
        """บรรทัด skill: ในงาน → ชื่อต้องตรงโฟลเดอร์ skills/ (โปรเจกต์ .opencode/.claude หรือส่วนกลาง) · ไม่ตรง = เตือน ไม่บล็อก · placeholder/`-` ไม่นับ"""
        sys.path.insert(0, str(REPO))
        import flashq
        self.write_precheck_proj()
        for d, n in ((".opencode", "proj-build"), (".claude", "proj-docs")):
            (self.proj / d / "skills" / n).mkdir(parents=True)
            (self.proj / d / "skills" / n / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        self.assertEqual(flashq.plan_skill_names("  - skill: `proj-build`, proj-docs"), ["proj-build", "proj-docs"])
        self.assertEqual(flashq.plan_skill_names("  - **สกิล:** x-one"), ["x-one"])
        for empty in ("  - skill: `<ชื่อ skill — ไม่มีลบบรรทัดนี้>`", "  - skill: -", "  - skill: none", "  - ก่อน: `skill: a`"):
            self.assertEqual(flashq.plan_skill_names(empty), [], empty)
        plan = ("## งาน\n"
                "- [ ] **T-01** `src/a.cpp`\n"
                "  - skill: `proj-build`, proj-docs\n"
                "- [ ] **T-02** `src/a.cpp`\n"
                "  - skill: `no-such-skill-zz`\n"
                "- [ ] **T-03** `src/a.cpp`\n"
                "  - skill: `<ชื่อ>`\n")
        src = flashq.PlanSource(self.proj)
        self.assertEqual(flashq.plan_precheck(plan, "T-01", src), ([], []))
        errs, warns = flashq.plan_precheck(plan, "T-02", src)
        self.assertEqual(errs, [])
        self.assertTrue(any("บรรทัด 5 (T-02)" in w and "`no-such-skill-zz`" in w for w in warns), warns)
        self.assertEqual(flashq.plan_precheck(plan, "T-03", src), ([], []))

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

    def test_plan_precheck_new_file_wording_and_multi_task_tokens(self):
        """ไฟล์ใหม่: บรรทัดที่พูดว่า "สร้าง ..." ไม่ต้องต่อท้าย (ใหม่) ก็ผ่าน แต่ path ที่ไม่มีและไม่ได้บอกว่าสร้าง = ยังผิด · tasks หลาย token ต่อเป็นก้อนเดียว"""
        sys.path.insert(0, str(REPO))
        import flashq
        self.write_precheck_proj()
        plan = ("# แผน\n\n## §2 งาน\n"
                "- [ ] **T-01** สร้าง `src/brand_new.cpp` แล้วเรียกจาก `src/a.cpp`\n"
                "  - ไฟล์: `src/a.cpp`\n"
                "- [ ] **T-02** แก้ `src/typo_name.cpp`\n"
                "  - ไฟล์: `src/typo_name.cpp`\n")
        src = flashq.PlanSource(self.proj)
        self.assertEqual(flashq.plan_precheck(plan, "T-01", src)[0], [])
        errs = flashq.plan_precheck(plan, "T-02", src)[0]
        self.assertTrue(any("ไม่พบไฟล์ `src/typo_name.cpp`" in e for e in errs), errs)
        r = self.run_q("run", "PRE.md", "T-03", "T-04", "--attach", "none", "--no-open", "--skip-precheck")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.run_q("run", "PRE.md", "T-03, T-04", "--attach", "none", "--no-open", "--skip-precheck").returncode, 0)
        tasks = [json.loads(f.read_text(encoding="utf-8"))["tasks"] for f in (self.home / "jobs").glob("*.json")]
        self.assertEqual(tasks, ["T-03,T-04", "T-03,T-04"], tasks)  # เว้นวรรค และ "T-03, T-04" ได้ผลเหมือนกัน

    def test_ui_smoke_picks_free_port(self):
        """ui_smoke ไม่ใช้พอร์ตตายตัว: ไม่ตั้งค่า = ระบบเลือกพอร์ตว่าง (ไม่ใช่ 4097) · ตั้ง FLASHQ_SMOKE_PORT = ใช้ค่านั้น"""
        code = "import sys; sys.path.insert(0, 'tests'); import ui_smoke; print(ui_smoke.PORT)"
        env = {k: v for k, v in self.env.items() if k != "FLASHQ_SMOKE_PORT"}
        ports = {int(subprocess.run([sys.executable, "-c", code], cwd=str(REPO), env=env, capture_output=True, text=True, timeout=30).stdout) for _ in range(2)}
        self.assertTrue(all(1024 < p < 65536 and p != 4097 for p in ports), ports)
        r = subprocess.run([sys.executable, "-c", code], cwd=str(REPO), env={**env, "FLASHQ_SMOKE_PORT": "4555"}, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.stdout.strip(), "4555")

    def test_scope_command_checks_commit_files_against_plan(self):
        """flashq scope: commit แตะเฉพาะไฟล์ในแผน = PASS · แตะเกิน = EXTRA · ไม่มี hash = NOCOMMIT · ไฟล์แผนเองผ่านเสมอ · always_ok ใน .flash.json ยกเว้นเพิ่มได้"""
        import tempfile
        plan_rel = "docs/x/PLAN_X.md"
        plan = "- [x] **T-01** `src/a.cpp`\n  - ไฟล์: `src/a.cpp`\n- [ ] **T-02** `src/b.cpp`\n- [x] **T-03** `src/a.cpp`\n\n## §4 ผล\n| งาน | ผล | commit |\n|---|---|---|\n| T-01 | OK | {h1} |\n| T-03 | OK | {h3} |\n"
        with tempfile.TemporaryDirectory(prefix="scope_") as d:
            def git(*args):
                r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", d, *args], capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(r.returncode, 0, r.stderr)
                return r.stdout.strip()

            def put(rel, text):
                p = Path(d, *rel.split("/"))
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8", newline="\n")

            def scope(*tasks):
                r = subprocess.run([sys.executable, str(REPO / "flashq.py"), "scope", plan_rel, *tasks, "--project", d],
                                   capture_output=True, text=True, encoding="utf-8", env=self.env, timeout=60)
                return r.returncode, r.stdout
            git("init", "-q", "-b", "main")
            put("src/a.cpp", "a\n"); put("src/b.cpp", "b\n"); put(plan_rel, plan.format(h1="0000000", h3="0000000"))
            git("add", "-A"); git("commit", "-qm", "base")
            put("src/a.cpp", "a2\n"); put(plan_rel, plan.format(h1="0000000", h3="0000000") + "\nติ๊ก\n")
            git("add", "-A"); git("commit", "-qm", "T-01")
            h1 = git("rev-parse", "--short", "HEAD")
            put("src/a.cpp", "a3\n"); put("docs/other.md", "x\n")
            git("add", "-A"); git("commit", "-qm", "T-03 เกิน")
            h3 = git("rev-parse", "--short", "HEAD")
            put(plan_rel, plan.format(h1=h1, h3=h3))
            git("add", "-A"); git("commit", "-qm", "plan")
            code, out = scope("T-01")
            self.assertEqual(code, 0, out)
            self.assertIn("SCOPE T-01 OK", out)  # แตะ src/a.cpp + ไฟล์แผนเอง (นอก docs/plans/) ไม่นับเกิน
            code, out = scope("T-02")
            self.assertEqual(code, 1, out)
            self.assertIn("NOCOMMIT", out)
            code, out = scope("T-03")
            self.assertEqual(code, 1, out)
            self.assertIn("EXTRA 1 ไฟล์: docs/other.md", out)
            Path(d, ".flash.json").write_text(json.dumps({"scope": {"always_ok": ["docs/*.md"]}}), encoding="utf-8")
            code, out = scope("T-01", "T-03")  # หลายงานเว้นวรรคได้ · always_ok ยกเว้น docs/other.md
            self.assertEqual(code, 0, out)
            self.assertIn("SCOPE_RESULT=PASS", out)
            self.assertEqual(subprocess.run([sys.executable, str(REPO / "flashq.py"), "scope", "nope.md", "--project", d], capture_output=True, text=True, encoding="utf-8", env=self.env, timeout=60).returncode, 2)

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

    def oc_agent_models(self):
        return {k: v.get("model") for k, v in json.loads(self.oc_cfg.read_text(encoding="utf-8"))["agent"].items()}

    def test_models_list_set_auto(self):
        """flashq models: รายการ = opencode models + provider ใน opencode.json · --set ตรวจชื่อก่อนเขียน · --auto ตั้งเฉพาะบทบาทที่ใช้ไม่ได้"""
        env = {"FAKE_MODELS": "opencode-go/deepseek-v4.1-flash|x/other-model"}
        r = self.run_q("models", "--list", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("4 รุ่น", r.stdout)  # fake 2 + provider ใน opencode.json 2
        self.assertIn("[opencode-go]", r.stdout)
        self.assertIn("deepseek/deepseek-v4.1-flash  (แนะนำ)", r.stdout)
        self.assertRegex(r.stdout, r"flash-worker\s+p1/m\s+ไม่มีในเครื่องนี้!")
        # ไม่มี TTY + ไม่ใส่ flag = แสดงสถานะ บอกวิธีแก้ ไม่เขียนอะไร
        r = self.run_q("models", env=env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("flashq models --auto", r.stdout)
        self.assertEqual(self.oc_agent_models(), {"flash-worker": "p1/m"})
        # ชื่อที่ไม่มีในเครื่อง = ปฏิเสธทั้งชุด ไม่เขียนครึ่งเดียว
        r = self.run_q("models", "--set", "verifier=x/other-model", "--set", "worker=no/such", env=env)
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("no/such", r.stdout)
        self.assertEqual(self.oc_agent_models(), {"flash-worker": "p1/m"})
        r = self.run_q("models", "--set", "boss=x/other-model", env=env)
        self.assertEqual(r.returncode, 2, r.stdout)
        r = self.run_q("models", "--set", "verifier=x/other-model", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.oc_agent_models()["flash-verifier"], "x/other-model")
        self.assertTrue(self.oc_cfg.with_name("opencode.json.bak-flash-models").exists())
        # --auto: ผู้ตรวจที่ตั้งไว้แล้วและใช้ได้ไม่แตะ · ที่เหลือใช้ตัวแนะนำ (provider ที่ accounts.json รู้จักมาก่อน)
        r = self.run_q("models", "--auto", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        m = self.oc_agent_models()
        self.assertEqual(m["flash-verifier"], "x/other-model")
        for ag in ("flash-worker", "flash-investigator", "flash-tester", "flash-writer"):
            self.assertEqual(m[ag], "commandcode/deepseek/deepseek-v4.1-flash", ag)
        r = self.run_q("models", "--all", "opencode-go/deepseek-v4.1-flash", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(set(self.oc_agent_models().values()), {"opencode-go/deepseek-v4.1-flash"})
        self.assertEqual(self.run_q("models", env=env).returncode, 0)

    def test_models_auto_without_recommended_model(self):
        """เครื่องที่ไม่มีโมเดลแนะนำเลย: --auto ตั้งให้ไม่ได้ → บอกตรง ๆ exit 1 และไม่แตะ opencode.json"""
        self.oc_cfg.write_text(json.dumps({"agent": {}, "provider": {}}), encoding="utf-8")
        r = self.run_q("models", "--auto", env={"FAKE_MODELS": "x/other-model"})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ไม่เจอ", r.stdout)
        self.assertEqual(json.loads(self.oc_cfg.read_text(encoding="utf-8")), {"agent": {}, "provider": {}})

    def test_models_interactive_and_install_keeps_choice(self):
        """ถามเลือก: เลขที่ · คำกรอง · Enter=ค่าแนะนำ · 0 ข้าม · install ไม่ทับโมเดลที่เลือกด้วยค่าตั้งต้นในต้นฉบับ"""
        sys.path.insert(0, str(REPO))
        import flashq
        models = ["a/deepseek-v4.1-flash", "b/glm-5.3", "c/deepseek-v4.1-flash"]
        keys = lambda *xs: mock.patch("builtins.input", side_effect=list(xs))  # noqa: E731
        with mock.patch.object(flashq, "OC_CONFIG", self.oc_cfg), mock.patch("sys.stdout"):
            with keys("zzz", "glm", "2"):  # ไม่พบ → กรอง → เลือกเลข (เลขอ้างรายการเต็ม)
                self.assertEqual(flashq.pick_model(models, "deepseek-v4.1-flash", {}, "x"), "b/glm-5.3")
            with keys("", "0"):  # ไม่มีค่าตั้งต้น Enter ซ้ำถาม · 0 = ข้าม
                self.assertEqual(flashq.pick_model(models, "deepseek-v4.1-flash", {}, "x"), "")
            with keys("", "c/deepseek-v4.1-flash"):
                self.assertEqual(flashq.pick_model(models, "t", {}, "x", default="a/deepseek-v4.1-flash"), "a/deepseek-v4.1-flash")
            with keys("2", "3"):  # เมนู 2 = โมเดลเดียวทุกบทบาท
                ch = flashq.ask_model_changes(models, "deepseek-v4.1-flash", "a/deepseek-v4.1-flash", {})
            self.assertEqual(set(ch), {ag for _, ag, _ in flashq.MODEL_ROLES})
            self.assertEqual(set(ch.values()), {"c/deepseek-v4.1-flash"})
            with keys("3", "2", "0", "", "", ""):  # แยกบทบาท: ผู้ทำ=เลข 2 · ผู้ตรวจ=ข้าม · ที่เหลือ Enter=ตัวแนะนำ
                ch = flashq.ask_model_changes(models, "deepseek-v4.1-flash", "a/deepseek-v4.1-flash", {})
            self.assertEqual(ch, {"flash-worker": "b/glm-5.3", "flash-investigator": "a/deepseek-v4.1-flash",
                                  "flash-tester": "a/deepseek-v4.1-flash", "flash-writer": "a/deepseek-v4.1-flash"})
            with keys(""):  # ทุกบทบาทตั้งแล้วและใช้ได้ → Enter = ไม่เปลี่ยน
                for _, ag, _ in flashq.MODEL_ROLES:
                    flashq.set_agent_model(ag, "a/deepseek-v4.1-flash")
                self.assertEqual(flashq.ask_model_changes(models, "deepseek-v4.1-flash", "a/deepseek-v4.1-flash", {}), {})
        # install: หัวไฟล์ agent ใช้โมเดลที่เลือก (ไม่ใช่ค่าในต้นฉบับ) และตั้งซ้ำได้
        self.run_q("models", "--set", "verifier=x/other-model", env={"FAKE_MODELS": "x/other-model"})
        r = self.run_q("install", "--models", "skip", env={"FLASHQ_CLAUDE_HOME": str(self.tmp / "claude_home")})
        head = (self.tmp / "agent" / "flash-verifier.md").read_text(encoding="utf-8")
        self.assertIn("model: x/other-model", head)
        self.assertNotIn("model: opencode-go/deepseek-v4.1-flash", head)
        self.assertEqual(self.run_q("install", "--models", "skip", env={"FLASHQ_CLAUDE_HOME": str(self.tmp / "claude_home")}).returncode, 0, r.stdout)

    def test_install_checks_models(self):
        """install ท้ายงานตรวจโมเดล: ขาด + ไม่มี TTY = บอกวิธีแก้ (ไม่ค้างถาม) · --models auto ตั้งให้ · ครบ = บอกว่าใช้ได้"""
        env = {"FLASHQ_CLAUDE_HOME": str(self.tmp / "claude_home"), "FAKE_MODELS": "opencode-go/deepseek-v4.1-flash"}
        r = self.run_q("install", env=env)
        self.assertIn("ยังไม่มีโมเดลที่ใช้ได้บนเครื่องนี้", r.stdout)
        self.assertIn("flashq models --auto", r.stdout)
        self.assertEqual(self.oc_agent_models(), {"flash-worker": "p1/m"})
        r = self.run_q("install", "--models", "auto", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.oc_agent_models()["flash-worker"], "commandcode/deepseek/deepseek-v4.1-flash")
        # accounts.json ใน repo มีรายการที่เครื่องนี้ไม่มี (go2/go3/inferx) → สร้างลำดับสลับบัญชีของเครื่องนี้ที่ ~/.flashq/accounts.json
        acc = json.loads((self.home / "accounts.json").read_text(encoding="utf-8"))["accounts"]
        self.assertEqual(acc, [["commandcode", "commandcode/deepseek/deepseek-v4.1-flash"],
                               ["commandcode2", "commandcode2/deepseek/deepseek-v4.1-flash"],
                               ["opencode-go", "opencode-go/deepseek-v4.1-flash"]])
        r = self.run_q("switch", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("go3", r.stdout)
        self.assertIn("commandcode2", r.stdout)
        r = self.run_q("install", env=env)
        self.assertIn("ทุกบทบาทใช้ได้บนเครื่องนี้", r.stdout)

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
        self.assertEqual(len(pre), 3)
        self.assertEqual(pre[0]["matcher"], "Read")
        self.assertIn("image_guard.py", pre[0]["hooks"][0]["command"])
        self.assertEqual(pre[1]["matcher"], "Bash|PowerShell")
        self.assertIn("run_guard.py", pre[1]["hooks"][0]["command"])
        self.assertEqual(pre[2]["matcher"], "Read|Grep|Glob|Bash|PowerShell")
        self.assertTrue(pre[2]["hooks"][0]["command"].endswith("delegate_guard.py\" pretool"))
        r = self.run_q("install", "--hooks", env=env)
        self.assertIn("เหมือนเดิม  hook", r.stdout)
        self.assertEqual(len(json.loads((claude / "settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]), 3)
        ups = json.loads((claude / "settings.json").read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(ups), 3)
        self.assertIn("inbox_notify.py", ups[0]["hooks"][0]["command"])
        self.assertTrue(ups[1]["hooks"][0]["command"].endswith("delegate_guard.py\" prompt"))
        self.assertIn("whatsnew.py", ups[2]["hooks"][0]["command"])

    def test_whatsnew_hook(self):
        """install บันทึกรุ่น+หัวข้อ CHANGELOG · ติดตั้งซ้ำไม่เปลี่ยนรุ่น/เวลา · hook: session ที่เริ่มก่อนติดตั้งได้รับแจ้งครั้งเดียว · session ใหม่/รุ่นเท่าเดิม = เงียบ · ปิดได้"""
        claude = self.tmp / "claude_home_wn"
        home = self.tmp / "wn_home"
        env = {"FLASHQ_CLAUDE_HOME": str(claude), "FLASHQ_HOME": str(home)}
        r = self.run_q("install", "--hooks", "--models", "skip", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("หัวข้อล่าสุดใน CHANGELOG", r.stdout)
        inst = json.loads((home / "installed.json").read_text(encoding="utf-8"))
        self.assertTrue(inst["rev"] and inst["news"])
        self.run_q("install", "--models", "skip", env=env)
        self.assertEqual(json.loads((home / "installed.json").read_text(encoding="utf-8")), inst, "ติดตั้งซ้ำต้องไม่เปลี่ยนรุ่น/เวลา")
        hook = claude / "hooks" / "whatsnew.py"
        henv = dict(os.environ, FLASHQ_HOME=str(home), PYTHONIOENCODING="utf-8")

        def run(sid, tp):
            return subprocess.run([sys.executable, str(hook)], input=json.dumps({"session_id": sid, "transcript_path": str(tp)}),
                                  capture_output=True, text=True, encoding="utf-8", env=henv, timeout=30).stdout

        old = self.tmp / "old_session.jsonl"
        old.write_text("{}", encoding="utf-8")
        self.assertEqual(run("new1", self.tmp / "no_such.jsonl"), "", "session เกิดหลังติดตั้ง = เงียบ")
        # จำลอง session เก่า: เวลาเริ่ม (ctime) ก่อนติดตั้ง — ctime แก้ผ่าน utime ไม่ได้ จึงเลื่อนเวลาติดตั้งให้ใหม่กว่าแทน
        inst2 = dict(inst, at=time.time() + 600, rev="zzz999", news=["หัวข้อทดสอบใหม่"] + inst["news"])
        (home / "installed.json").write_text(json.dumps(inst2), encoding="utf-8")
        out = run("new1", self.tmp / "no_such.jsonl")
        self.assertIn("หัวข้อทดสอบใหม่", out)
        self.assertIn("เหมือนเดิม", out)
        self.assertEqual(run("new1", self.tmp / "no_such.jsonl"), "", "แจ้งครั้งเดียวต่อรุ่น")
        out = run("old1", old)  # session ที่ไม่เคยเห็นรุ่น และเริ่มก่อนติดตั้ง = แจ้ง
        self.assertIn("ติดตั้งของใหม่", out)
        (home / "config.json").write_text('{"whatsnew": false}', encoding="utf-8")
        (home / "installed.json").write_text(json.dumps(dict(inst2, rev="yyy888", at=time.time() + 900)), encoding="utf-8")
        self.assertEqual(run("new1", self.tmp / "no_such.jsonl"), "", "ปิดในคอนฟิก = เงียบ")

    def test_delegate_guard_hook(self):
        """ยามมอบงานสืบ: ผู้ใช้สั่งส่งสืบ → แทรกคำสั่ง + ตั้งงบอ่าน · อ่านเกินงบ = บล็อก (exit 2) · ไฟล์แผน/กติกาไม่นับ · ส่ง investigate แล้วเหลืองบยืนยัน 2 · ข้อความอื่นปลดงบ · ปิดได้"""
        guard = REPO / "hooks" / "delegate_guard.py"
        env = dict(os.environ, FLASHQ_HOME=str(self.tmp / "dg_home"), PYTHONIOENCODING="utf-8")

        def hook(mode, payload):
            return subprocess.run([sys.executable, str(guard), mode], input=json.dumps(payload), capture_output=True,
                                  text=True, encoding="utf-8", env=env, timeout=30)

        def tool(name, **ti):
            return hook("pretool", {"session_id": "s1", "tool_name": name, "tool_input": ti})

        for txt, want in (("ส่งสืบหน่อย บั๊กนี้", True), ("ให้ flash ตามหาต้นตอ", True), ("ส่ง deepseek ไปดู", True),
                          ("แก้บั๊กนี้ให้หน่อย", False), ("ทำไมไม่อัพเดท", False)):
            r = subprocess.run([sys.executable, str(guard), "test", txt], capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
            self.assertEqual(r.stdout.startswith("ตรง"), want, (txt, r.stdout))
        self.assertEqual(tool("Read", file_path="a.py").stdout, "", "ยังไม่ได้สั่งส่งสืบ = ไม่ยุ่ง")
        r = hook("prompt", {"session_id": "s1", "prompt": "ส่งสืบ บั๊กหน้าเว็บ"})
        self.assertIn("/flash-investigate", r.stdout)
        for _ in range(3):
            self.assertEqual(tool("Grep", pattern="x", path="src/a.py").returncode, 0)
        self.assertEqual(tool("Read", file_path="D:/p/docs/plans/PLAN_FLASH_x.md").returncode, 0)  # ไฟล์แผนไม่นับงบ
        r = tool("Read", file_path="src/b.py")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("flash-investigate", r.stderr)
        self.assertEqual(tool("Bash", command="python D:/MyCode/flashq/flashq.py investigate --project . brief.md").returncode, 0)
        self.assertEqual(tool("Bash", command="cd /p && grep -rn foo .").returncode, 0)  # หลังส่งแล้วเหลืองบยืนยัน 2
        self.assertEqual(tool("Read", file_path="src/a.py").returncode, 0)
        self.assertEqual(tool("Read", file_path="src/a.py").returncode, 2)
        hook("prompt", {"session_id": "s1", "prompt": "ok แก้เลย"})  # ข้อความอื่น = ปลดงบ
        self.assertEqual(tool("Read", file_path="src/a.py").returncode, 0)
        hook("prompt", {"session_id": "s1", "prompt": "ส่งสืบ"})
        (self.tmp / "dg_home" / "config.json").write_text('{"delegate_guard": false}', encoding="utf-8")
        for _ in range(5):
            self.assertEqual(tool("Read", file_path="src/a.py").returncode, 0)  # ปิดถาวรในคอนฟิก

    def test_install_check(self):
        """install --check: ยังไม่ติดตั้ง/ล้าหลัง = INSTALL=STALE exit 1 และไม่เขียนอะไร · ตรงต้นฉบับ = INSTALL=OK · ไฟล์ของผู้ใช้เองไม่นับว่าล้าหลัง"""
        claude = self.tmp / "claude_home"
        env = {"FLASHQ_CLAUDE_HOME": str(claude)}
        r = self.run_q("install", "--check", env=env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("INSTALL=STALE", r.stdout)
        self.assertIn("ยังไม่ได้ติดตั้ง", r.stdout)
        self.assertFalse((claude / "commands").exists(), "--check ต้องไม่เขียนอะไร")
        self.run_q("install", "--models", "skip", env=env)
        r = self.run_q("install", "--check", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("INSTALL=OK", r.stdout)
        plan = claude / "commands" / "flash-plan.md"
        txt = plan.read_text(encoding="utf-8")
        plan.write_text(txt + "\nเก่า\n", encoding="utf-8")
        r = self.run_q("install", "--check", env=env)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("ล้าหลัง", r.stdout)
        self.assertIn("flash-plan.md", r.stdout)
        self.assertEqual(plan.read_text(encoding="utf-8"), txt + "\nเก่า\n", "--check ต้องไม่ทับไฟล์")
        plan.write_text("ของผู้ใช้เอง\n", encoding="utf-8")  # ไม่มี flashq:managed = ไม่ใช่ของ flashq ไม่นับล้าหลัง
        r = self.run_q("install", "--check", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("ข้าม", r.stdout)

    def test_run_guard_hook(self):
        """ยามส่งงาน: คำสั่งส่งงานต้อง run_in_background จริง · `&` · sleep · nohup · Start-Process · ต่อท่อ head/tail = บล็อก (exit 2) · ถูกวิธี = ผ่านพร้อมคำเตือน · คำสั่งอื่น/--help/ปิดยาม = เงียบ"""
        guard = REPO / "hooks" / "run_guard.py"

        def hook(cmd, bg=True, tool="Bash"):
            ti = {"command": cmd}
            if bg is not None:
                ti["run_in_background"] = bg
            data = json.dumps({"tool_name": tool, "session_id": "s1", "tool_input": ti})
            return subprocess.run([sys.executable, str(guard)], input=data, capture_output=True, text=True, encoding="utf-8",
                                  env=self.env, timeout=30)
        run = "python D:/MyCode/flashq/flashq.py run docs/p.md T-01..T-02 --switch-on-quota 4"
        r = hook(run)  # ถูกวิธี: ผ่าน + แทรกคำเตือนให้หยุดนิ่งรอแจ้งเตือน
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("หยุดนิ่งรอแจ้งเตือน", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])
        r = hook(run, bg=False)  # foreground = ไม่มีใครเฝ้า
        self.assertEqual(r.returncode, 2)
        self.assertIn("run_in_background", r.stderr)
        r = hook(run, bg=None)
        self.assertEqual(r.returncode, 2)
        # ท่าที่เคยพลาดจริง: ต่อ & แล้ว sleep + head
        r = hook("cd /d/x; python tools/plans/flash_run.py docs/p.md T-00..T-02 --skip-precheck > Temp/o.txt 2>&1 &\nsleep 30; head -6 Temp/o.txt")
        self.assertEqual(r.returncode, 2)
        self.assertIn("`&`", r.stderr)
        self.assertIn("sleep", r.stderr)
        for bad in (run + " &", "nohup " + run, run + " | tail -5", run + "; sleep 5", "Start-Process python -ArgumentList 'flashq.py run p.md T-01'",
                    "python flashq.py wait 2026_1 ; Start-Sleep 20"):
            self.assertEqual(hook(bad, tool="PowerShell" if "Start-" in bad else "Bash").returncode, 2, bad)
        # wrapper ของโปรเจกต์ (flash_run.py) นับเป็น run · ชื่ออื่นตั้งใน config
        self.assertEqual(hook("python tools/plans/flash_run.py docs/p.md T-01", bg=False).returncode, 2)
        self.assertEqual(hook("python tools/x/my_wrap.py docs/p.md T-01", bg=False).returncode, 0)
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "config.json").write_text(json.dumps({"run_guard_wrappers": ["my_wrap.py"]}), encoding="utf-8")
        self.assertEqual(hook("python tools/x/my_wrap.py docs/p.md T-01", bg=False).returncode, 2)
        (self.home / "config.json").unlink()
        # ผ่าน: อยู่ในเครื่องหมายคำพูด (บรีฟมี & sleep) · redirect 2>&1 · wait สั้น · --help · คำสั่งอื่น · call operator ของ PowerShell
        self.assertEqual(hook('python flashq.py investigate "หา bug & sleep | head" --auto').returncode, 0)
        self.assertEqual(hook(run + " 2>&1").returncode, 0)
        self.assertEqual(hook("python flashq.py wait 2026_1 --timeout-min 1", bg=False).returncode, 0)
        self.assertEqual(hook("python flashq.py wait 2026_1", bg=True).returncode, 0)
        self.assertEqual(hook("python flashq.py wait 2026_1", bg=False).returncode, 2)
        self.assertEqual(hook("python flashq.py run --help", bg=False).returncode, 0)
        self.assertEqual(hook("python flashq.py status", bg=False).returncode, 0)
        self.assertEqual(hook("git status && sleep 1 &", bg=False).returncode, 0)
        # แค่อ่านไฟล์ที่ชื่อเป็น wrapper (head · diff · for … in …) ไม่ใช่การส่งงาน
        self.assertEqual(hook("for f in tools/plans/flash_run.py tools/plans/x.py; do head -12 $f; done", bg=False).returncode, 0)
        self.assertEqual(hook("head -12 tools/plans/flash_run.py | cut -c1-80", bg=False).returncode, 0)
        self.assertEqual(hook("diff tools/plans/flash_run.py /d/other/flash_run.py", bg=False).returncode, 0)
        self.assertEqual(hook("C:/Python312/python.exe tools/plans/flash_run.py docs/p.md T-01", bg=False).returncode, 2)
        # เนื้อหา heredoc (เช่นข้อความ commit ที่เล่าเหตุการณ์ flash_run.py … & sleep) เป็นข้อความ ไม่ใช่คำสั่ง
        msg = "git commit -F - <<'EOF'\nflashq: เคยพลาด flash_run.py x.md T-01 & sleep 30; head -6 o.txt\nEOF\ngit log -1"
        self.assertEqual(hook(msg, bg=False).returncode, 0)
        self.assertEqual(hook(msg + "\npython flashq.py run p.md T-01", bg=False).returncode, 2)  # คำสั่งหลัง heredoc ยังถูกตรวจ
        r = hook("& python tools/plans/flash_run.py docs/p.md T-01", tool="PowerShell")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(hook("ls", tool="Read").returncode, 0)
        rows = [json.loads(x) for x in (self.home / "run_guard.log").read_text(encoding="utf-8").splitlines()]  # ทุกครั้งที่บล็อกถูกจดไว้ไล่ย้อนหลัง
        self.assertTrue(rows and all({"at", "reason", "command"} <= set(x) for x in rows), rows)
        self.assertTrue(any("run_in_background" in x["reason"] for x in rows), rows)
        self.assertIn("run_guard.log", hook(run, bg=False).stderr)  # ข้อความบล็อกบอกที่ดู log
        (self.home / "run_guard_off").write_text("", encoding="utf-8")  # ปิดยามชั่วคราว
        n_rows = len(rows)
        self.assertEqual(hook(run, bg=False).returncode, 0)
        self.assertEqual(len((self.home / "run_guard.log").read_text(encoding="utf-8").splitlines()), n_rows + 1)  # ปิดยาม = ไม่บล็อก ไม่จดเพิ่ม (+1 มาจากบรรทัด assertIn ด้านบน)
        (self.home / "run_guard_off").unlink()
        (self.home / "config.json").write_text(json.dumps({"run_guard": False}), encoding="utf-8")
        self.assertEqual(hook(run, bg=False).returncode, 0)

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

    def test_cancel_job_notifies_claude(self):
        """ยกเลิกงาน (cancel/ปุ่มหน้าเว็บ) → inbox CANCELLED ให้ session ที่สั่ง · hook บอกว่าไม่ใช่งานพังและห้ามส่งซ้ำเอง · งานที่ไม่ได้ทำงานอยู่ = ไม่แจ้ง"""
        (self.home / "jobs").mkdir(parents=True, exist_ok=True)
        job = {"id": "canjob01", "status": "running", "pid": 99999999, "pid_start": 0, "project": str(self.proj),
               "plan": "PLAN.md", "tasks": "T-01", "claude_session": "s1", "created": "2026-10-22T10:00:00", "last": "ทำไปครึ่งทาง"}
        (self.home / "jobs" / "canjob01.json").write_text(json.dumps(job), encoding="utf-8")
        r = self.run_q("cancel", "canjob01")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = list((self.home / "inbox").glob("*.json"))
        self.assertEqual(len(files), 1)
        row = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual((row["status"], row["session"], row["job"]), ("CANCELLED", "s1", "canjob01"))
        out = subprocess.run([sys.executable, str(REPO / "hooks" / "inbox_notify.py")], input=json.dumps({"session_id": "s1", "cwd": str(self.proj)}),
                             capture_output=True, text=True, encoding="utf-8", env=self.env, timeout=30).stdout
        self.assertIn("CANCELLED", out)
        self.assertIn("ไม่ใช่งานพัง", out)
        self.assertNotIn("ก่อนสั่งซ้ำ", out)
        self.assertEqual(self.run_q("cancel", "canjob01").returncode, 1)  # จบไปแล้ว ยกเลิกซ้ำไม่ได้
        self.assertFalse(list((self.home / "inbox").glob("*.json")))  # และไม่แจ้งซ้ำ

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

    @unittest.skipUnless(os.name == "nt", "ปัญหา loopback เฉพาะ Windows")
    def test_ui_server_disables_send_buffer_on_windows(self):
        """Windows: ตอบหน้าใหญ่ (ui.html ~240KB) ค้างเป็นครั้งคราว ~3% จนกว่าจะตั้ง SO_SNDBUF=0 ที่ listening socket (accept แล้วสืบทอด)"""
        mod = self.load_mod("flashq_sndbuf")
        srv, _ = mod.make_ui_server(0)
        self.addCleanup(srv.server_close)
        self.assertEqual(srv.socket.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF), 0)

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

    def test_review_done_matches_plan_name_loosely(self):
        """review done ปิดป้ายได้แม้ชื่อแผนตอน start ต่างแบบ (ตัด .md · ชื่อสั้นเป็นท้ายของชื่อเต็มที่ขอบ "_") — เคยพลาดจริง: start VIEWFIX2 แต่ done PLAN_..._VIEWFIX2 ป้ายเลยค้าง"""
        sys.path.insert(0, str(REPO))
        import flashq
        m = flashq.review_name_match
        self.assertEqual(m("PLAN_X_FLASH.md", "plan_x_flash"), 2)
        self.assertEqual(m("VIEWFIX2", "docs/plans/PLAN_MAPEDITOR_FLASH_VIEWFIX2.md"), 1)
        self.assertEqual(m("PLAN_MAPEDITOR_FLASH_VIEWFIX2", "VIEWFIX2.md"), 1)
        self.assertEqual(m("FIX2", "PLAN_X_VIEWFIX2"), 0)  # ต้องตรงที่ขอบ "_" ไม่ใช่แค่ลงท้ายเหมือนกัน
        self.assertEqual(m("PLAN_A", "PLAN_B"), 0)
        self.assertEqual(m("", "PLAN_A"), 0)
        rdir = self.home / "reviews"

        def rows():
            return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(rdir.glob("rv_*.json"))]
        self.assertEqual(self.run_q("review", "start", "VIEWFIX2", "T-00").returncode, 0)
        r = self.run_q("review", "done", "PLAN_MAPEDITOR_FLASH_VIEWFIX2", "pass")
        self.assertIn("REVIEW=PASS", r.stdout + r.stderr)
        self.assertEqual([x["status"] for x in rows()], ["pass"])
        # start ซ้ำด้วยชื่อเต็ม ทิ้งป้ายค้างที่ชื่อสั้นของโปรเจกต์เดียวกัน
        self.assertEqual(self.run_q("review", "start", "VIEWFIX3", "T-00").returncode, 0)
        self.assertEqual(self.run_q("review", "start", "PLAN_X_FLASH_VIEWFIX3.md", "T-00").returncode, 0)
        self.assertEqual([x["status"] for x in rows() if x["plan_name"].lower().endswith("viewfix3") or x["plan_name"].endswith("VIEWFIX3.md")], ["reviewing"])
        # ชื่อไม่เกี่ยวกัน = ไม่ปิดป้ายของแผนอื่น
        r = self.run_q("review", "done", "PLAN_OTHER.md", "fail")
        self.assertEqual(r.returncode, 0)
        self.assertEqual([x["status"] for x in rows()].count("reviewing"), 1)

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
        # ข้อความ 403 ต้องบอกสาเหตุ+ทางแก้ (token หมดอายุ → รีเฟรช · Host/Origin ผิด → เปิดผ่าน 127.0.0.1/localhost)
        bad = json.loads(self.http(base + "/api/cancel", payload, {**hdr, "X-Flashq-Token": "x"})[1])
        self.assertEqual(bad["code"], "token")
        self.assertIn("รีเฟรช", bad["error"])
        bad = json.loads(self.http(base + "/api/cancel", payload, {**hdr, "X-Flashq-Token": token, "Origin": "http://evil.example"})[1])
        self.assertEqual(bad["code"], "host")
        self.assertIn("127.0.0.1", bad["error"])
        self.assertTrue(st.get("boot"))  # รหัสรอบ server ให้หน้าเว็บรู้ว่ารีสตาร์ตแล้ว

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

    def test_ui_accounts_edit_and_role_model(self):
        """ui: แก้บัญชีสลับโมเดล (เพิ่ม/แก้/ย้าย/ลบ/คืนค่า) เขียน ~/.flashq/accounts.json ของเครื่อง ไม่แตะ repo · โมเดลต้องมีในเครื่อง (รายการเดียวกับ flashq models) · ตั้งโมเดลบทบาทได้"""
        self.env["FAKE_MODELS"] = "x/other-model|y/spare-model"
        base = self.start_ui()
        page = self.http(base + "/")[1]
        token = re.search(r'const TOKEN = "([^"]+)"', page).group(1)
        self.assertIn('id="accDlg"', page)  # ตัวแก้บัญชีเป็น popup wizard
        self.assertNotIn('id="accEdit"', page)
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": token}

        def acc(**kw):
            code, body = self.http(base + "/api/accounts", json.dumps(kw).encode(), hdr)
            return code, json.loads(body)

        def state():
            return json.loads(self.http(base + "/api/state")[1])

        mf = self.home / "accounts.json"
        self.assertEqual(state()["accounts_source"], "repo")
        self.assertFalse(mf.exists())
        code, d = self.http(base + "/api/models")
        info = json.loads(d)
        self.assertIn("x/other-model", info["models"])
        self.assertIn("commandcode/deepseek/deepseek-v4.1-flash", info["models"])  # ที่ประกาศใน opencode.json ด้วย
        self.assertEqual([r["key"] for r in info["roles"]][0], "worker")
        provs = {p["id"]: p for p in info["providers"]}  # ผู้ให้บริการทั้งหมด: ที่ตั้งใน opencode.json + ที่มากับ opencode
        self.assertTrue(provs["commandcode"]["declared"])
        self.assertEqual((provs["x"]["declared"], provs["x"]["count"]), (False, 1))
        self.assertLess([p["id"] for p in info["providers"]].index("commandcode2"), [p["id"] for p in info["providers"]].index("x"))  # ที่ตั้งไว้มาก่อน

        self.assertEqual(self.http(base + "/api/accounts", b"{}", {"Content-Type": "application/json"})[0], 403)  # ไม่มี token
        code, d = acc(action="add", short="xo", model="x/other-model")
        self.assertEqual(code, 200, d)
        self.assertEqual(state()["accounts_source"], "machine")
        self.assertEqual(state()["accounts"][-1]["short"], "xo")
        self.assertTrue(state()["accounts"][-1]["available"])  # โมเดลที่มากับ opencode (ไม่ได้ประกาศใน opencode.json) ก็ใช้ได้
        code, d = self.http(base + "/api/switch", json.dumps({"target": "xo"}).encode(), hdr)
        self.assertEqual(code, 200, d)
        self.assertEqual(self.oc_agent_models()["flash-worker"], "x/other-model")
        self.assertEqual(len(json.loads(mf.read_text(encoding="utf-8"))["accounts"]), 6)  # 5 ของ repo + 1
        self.assertEqual(len(json.loads((REPO / "accounts.json").read_text(encoding="utf-8"))["accounts"]), 5)  # repo ไม่ถูกแตะ
        # ปฏิเสธ: โมเดลที่เครื่องไม่มี · ซ้ำ · ชื่อย่อซ้ำ/ผิดรูป · รูปแบบโมเดลผิด
        self.assertEqual(acc(action="add", short="n1", model="no/such")[0], 400)
        self.assertEqual(acc(action="add", short="n2", model="x/other-model")[0], 400)
        self.assertEqual(acc(action="add", short="xo", model="y/spare-model")[0], 400)
        self.assertEqual(acc(action="add", short="bad name!", model="y/spare-model")[0], 400)
        self.assertEqual(acc(action="add", short="n3", model="noslash")[0], 400)
        # ไม่ใส่ชื่อย่อ = ตั้งจากชื่อ provider
        self.assertEqual(acc(action="add", model="y/spare-model")[0], 200)
        self.assertEqual(state()["accounts"][-1]["short"], "y")
        # แก้ชื่อ/โมเดล · ย้าย · ลบ
        self.assertEqual(acc(action="update", short="xo", new_short="xo2")[0], 200)
        self.assertEqual(acc(action="update", short="xo2", new_short="cc")[0], 400)  # ชื่อชนของเดิม
        self.assertEqual(acc(action="move", short="xo2", dir="up")[0], 200)
        self.assertEqual([a["short"] for a in state()["accounts"]][-3:], ["xo2", "inferx", "y"])
        self.assertEqual(acc(action="move", short="cc", dir="up")[0], 400)  # บนสุดแล้ว
        self.assertEqual(acc(action="remove", short="y")[0], 200)
        self.assertEqual(acc(action="remove", short="ไม่มี")[0], 400)
        self.assertEqual(acc(action="nope")[0], 400)
        # ลบจนเหลือตัวเดียว = ลบตัวสุดท้ายไม่ได้
        for s in [a["short"] for a in state()["accounts"]][1:]:
            self.assertEqual(acc(action="remove", short=s)[0], 200)
        code, d = acc(action="remove", short=state()["accounts"][0]["short"])
        self.assertEqual(code, 400, d)
        self.assertEqual(len(state()["accounts"]), 1)
        # คืนค่า repo
        self.assertEqual(acc(action="reset")[0], 200)
        self.assertFalse(mf.exists())
        self.assertEqual(state()["accounts_source"], "repo")
        self.assertEqual(acc(action="reset")[0], 400)
        # โมเดลของบทบาท (ใช้ set_agent_model เดียวกับ flashq models)
        def role(**kw):
            return self.http(base + "/api/role_model", json.dumps(kw).encode(), hdr)[0]
        self.assertEqual(role(role="verifier", model="x/other-model"), 200)
        self.assertEqual(self.oc_agent_models()["flash-verifier"], "x/other-model")
        self.assertEqual(role(role="verifier", model="no/such"), 400)
        self.assertEqual(role(role="boss", model="x/other-model"), 400)

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

    def test_ui_dismiss_all_and_auto_clear_dead(self):
        """ป้ายงานตาย: รับทราบทั้งหมดในครั้งเดียว · หายเองเมื่อไฟล์งานเก่าเกิน dead_clear_hours (0 = ปิด) · ตั้งค่าผ่าน /api/config"""
        (self.home / "jobs").mkdir(parents=True)
        ids = ["20980101_000000_1", "20980101_000000_2", "20980101_000000_3"]
        for i in ids:
            (self.home / "jobs" / f"{i}.json").write_text(json.dumps(
                {"id": i, "status": "running", "pid": 999999, "created": "2098-01-01 00:00:00",
                 "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01"}), encoding="utf-8")
        old = time.time() - 30 * 3600
        os.utime(self.home / "jobs" / f"{ids[0]}.json", (old, old))  # เก่า 30 ชม.
        base = self.start_ui()
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": self.ui_token(base)}
        page = self.http(base + "/")[1]
        self.assertIn("data-dismiss-all", page)  # ปุ่มในแผงแดชบอร์ด
        self.assertIn("data-ofdead", page)       # เก้าอี้ในหน้า office คลิกรับทราบได้

        # ค่าเริ่มต้น 24 ชม. → งานเก่า 30 ชม. หายเอง อีกสองงานที่เพิ่งเขียนยังอยู่
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["dead_clear_hours"], 24)
        self.assertEqual(sorted(d["id"] for d in st["dead"]), ids[1:])
        status = lambda i: json.loads((self.home / "jobs" / f"{i}.json").read_text(encoding="utf-8"))["status"]
        self.assertEqual([status(i) for i in ids], ["dead", "running", "running"])

        # ปิดการหายเอง (0) → งานเก่าไม่ถูกล้าง
        old2 = time.time() - 90 * 3600
        os.utime(self.home / "jobs" / f"{ids[1]}.json", (old2, old2))
        code, body = self.http(base + "/api/config", json.dumps({"dead_clear_hours": 0}).encode(), hdr)
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(self.http(base + "/api/state")[1])["dead_clear_hours"], 0)
        self.assertEqual(len(json.loads(self.http(base + "/api/state")[1])["dead"]), 2)
        self.assertEqual(self.http(base + "/api/config", json.dumps({"dead_clear_hours": "x"}).encode(), hdr)[0], 400)

        # รับทราบทั้งหมด · ต้องมี token
        self.assertEqual(self.http(base + "/api/dismiss", json.dumps({"all": True}).encode(), {"Content-Type": "application/json"})[0], 403)
        code, body = self.http(base + "/api/dismiss", json.dumps({"all": True}).encode(), hdr)
        self.assertEqual(code, 200, body)
        self.assertEqual(json.loads(body)["cleared"], 2)
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["dead"], [])
        self.assertEqual([status(i) for i in ids], ["dead"] * 3)

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

    def test_ui_flash_usage_endpoint(self):
        """ui: /api/flash_usage สรุป token ของ Flash (อ่านอย่างเดียว) · days ผิด = 400 · หน้าเว็บมีการ์ดสรุป"""
        self.env["FLASHQ_OPENCODE_DB"] = str(self.tmp / "no_such.db")  # กันไปอ่านฐานข้อมูล opencode จริงของผู้ใช้
        (self.home / "jobs").mkdir(parents=True)
        log = self.tmp / "a.jsonl"
        log.write_text(json.dumps({"type": "step_finish", "sessionID": "S", "part": {"cost": 0.5, "tokens": {
            "input": 10, "output": 2, "reasoning": 1, "cache": {"read": 100, "write": 0}}}}) + "\n", encoding="utf-8")
        (self.home / "jobs" / "j1.json").write_text(json.dumps({"id": "j1", "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                                                                "project": str(self.proj), "logs": [str(log)], "kind": "work"}), encoding="utf-8")
        base = self.start_ui()
        code, body = self.http(base + "/api/flash_usage?days=7")
        d = json.loads(body)
        self.assertEqual(code, 200, body)
        self.assertEqual((d["jobs"], d["total"]["tokens"], d["subagent"]["included"]), (1, 113, False))
        self.assertEqual(self.http(base + "/api/flash_usage?days=abc")[0], 400)
        self.assertIn('id="flashUsage"', self.http(base + "/")[1])

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

    def test_check_citations_short_names_code_spans_and_clauses(self):
        """ชื่อไฟล์ย่อ · ชื่อซ้ำ · host:port · backtick เหลื่อม · ช่วงบรรทัด · ... · คำปฏิเสธ · `:123` — ต้องไม่ฟ้องผิด แต่คัดผิดจริงยังต้องถูกชี้"""
        sys.path.insert(0, str(REPO))
        import flashq
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            files = {
                "tool/rig_viewer.py": ["import os", "def rig_summary():", "    return dict(name=n)", "    raise ValueError('ข้อต่อซ้อนกัน: %s' % n)", "", "x = 1"],
                "tool/rig_catalog.py": ["# ภาพย่อ", "def thumb_svg(s):", "    return 1", "def other():", "    return dict(islands_removed=3)", "", "", "", "", "end"],
                "tool/web/index.html": ["<html>", "<script>", "const a = 1;", "</script>"],
                "other/catalog.py": ["def thumb_svg(s): pass"],
                "other/index.html": ["<html>"],
                "lone/extra_helper.py": ["a = 1", "b = 2"],
            }
            for rel, ls in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("\n".join(ls) + "\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)

            def chk(*lines):
                return flashq.check_citations("\n".join(lines), root)

            # ชื่อย่อชี้ไฟล์เดียว → ผ่าน (viewer.py = rig_viewer.py) · ไม่ใช่ "ไม่พบไฟล์"
            r = chk("`viewer.py:2` — `def rig_summary():` ตรง")
            self.assertEqual((r["ok"], r["ok_code"], r["bad"]), (1, 1, []))
            # ชื่อซ้ำ (catalog.py = other/catalog.py หรือ tool/rig_catalog.py) → เลือกอันที่อยู่โฟลเดอร์เดียวกับ citation ที่ระบุ path ครบ
            r = chk("`tool/rig_viewer.py:1` ดู", "`catalog.py:2` — `def thumb_svg(s):` ตรง", "`index.html:3` — `const a = 1;` ตรง")
            self.assertEqual((r["ok"], r["ok_code"], r["bad"]), (3, 2, []))
            # ไม่มี anchor + ซ้ำ → กำกวม ไม่เดา · ชื่อที่ไม่มีเลย → ไม่พบไฟล์
            r = chk("`index.html:1` ดู", "`ghost.py:1` ดู")
            self.assertEqual(len(r["bad"]), 2)
            self.assertIn("กำกวม", r["bad"][0])
            self.assertIn("ไม่พบไฟล์", r["bad"][1])
            # host:port ไม่ใช่ citation
            self.assertEqual(chk("เปิด `127.0.0.1:8219/api/rigs` แล้วดู http://localhost:8219"), {"ok": 0, "ok_code": 0, "bad": []})
            # citation ในโค้ดสแปน + ข้อความคัดสั้น (<4) ไม่ทำให้ backtick จับคู่เหลื่อม
            r = chk("- `tool/rig_viewer.py:3` `n` ใช้ค่า `name=n` ตรง · `tool/rig_catalog.py:1` \"ตัวละคร `h_w`\" + `:261` `ไม่อยู่ในไฟล์เลย`")
            self.assertEqual(r["bad"], [])
            # ช่วงบรรทัด: โค้ดที่ปลายช่วงต้องนับ · ข้อความย่อด้วย ... · คำปฏิเสธ "ไม่มีคีย์ `x`" ไม่ถูกตรวจ
            r = chk("`tool/rig_catalog.py:2-5` — ส่งกลับ `islands_removed` ตรง",
                    "`tool/rig_viewer.py:2` — `def ... rig_summary():` ตรง",
                    "`tool/rig_viewer.py:3` ไม่มีคีย์ `source` ในผลลัพธ์")
            self.assertEqual((r["ok"], r["bad"]), (3, []))
            # คัดไม่ตรงตัวแต่ถูกคำ (ValueError: ข้อความ) ผ่าน · ข้อความหลัง `:123` / · / → เป็นของประเด็นอื่น
            r = chk("`tool/rig_viewer.py:4` — `ValueError: ข้อต่อซ้อนกัน` ตรง",
                    "`tool/rig_viewer.py:1` ดู `:585` `ไม่มีในไฟล์เลย`",
                    "`tool/rig_viewer.py:5` ดู · `ไม่มีในไฟล์เลย`",
                    "`tool/rig_viewer.py:6` ดู → `ไม่มีในไฟล์เลย`")
            self.assertEqual((r["ok"], r["bad"]), (4, []))
            # ข้อความคัดที่ห่างจาก citation (>40 ตัวอักษร ในประโยคเดียวกัน): มีในไฟล์ = ผ่าน (ตรงแค่ไฟล์/บรรทัด) · ไม่มีในไฟล์เลย = ผิด
            gap = "ซึ่งเป็นคำอธิบายยาว ๆ ที่คั่นอยู่ระหว่าง citation กับโค้ดที่คัดมาตรงนี้"
            r = chk(f"`tool/rig_viewer.py:6` {gap} `def rig_summary():`", f"`tool/rig_viewer.py:5` {gap} `def ghost_func():`")
            self.assertEqual((r["ok"], r["ok_code"]), (1, 0))
            self.assertEqual(len(r["bad"]), 1)
            self.assertIn("ไม่มีในไฟล์นี้เลย", r["bad"][0])
            # คัดผิดจริง/อยู่ไกลเกิน ±3 → ยังต้องถูกชี้ (ไม่หย่อนจนตรวจอะไรไม่ได้)
            r = chk("`tool/rig_viewer.py:2` — `def rig_summary():` ตรง",
                    "`tool/rig_catalog.py:9` — `def thumb_svg(s):` ไกลเกิน ±3",
                    "`tool/rig_viewer.py:5` — `raise ValueError('ไม่มีจริง')` ผิด",
                    "`tool/rig_catalog.py:99` — เกินไฟล์")
            self.assertEqual(r["ok"], 1)
            self.assertEqual(len(r["bad"]), 3)
            self.assertIn("ไม่อยู่ในบรรทัดนี้", r["bad"][0])
            self.assertIn("ไม่อยู่ในบรรทัดนี้", r["bad"][1])
            self.assertIn("เลขบรรทัดเกินไฟล์", r["bad"][2])

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

    def test_tree_live_pulse(self):
        """ชีพจรงานทดสอบ: tree_live รวม CPU/I/O + นับโปรเซสลูกหลาน + ชื่อไม่ซ้ำ (ไม่รวม shell) · pid ไม่พบ = None"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("flashq_live", FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        procs = Path(tempfile.mkdtemp()) / "procs_live.json"
        self.addCleanup(shutil.rmtree, str(procs.parent), True)
        t = time.time()
        procs.write_text(json.dumps([
            {"pid": 10, "ppid": 1, "name": "cmd.exe", "cmd": "", "created": t, "act": 5},
            {"pid": 11, "ppid": 10, "name": "powershell.exe", "cmd": "", "created": t + 1, "act": 7},
            {"pid": 12, "ppid": 11, "name": "MapEditor.exe", "cmd": "", "created": t + 2, "act": 100},
            {"pid": 13, "ppid": 11, "name": "MapEditor.exe", "cmd": "", "created": t + 3, "act": 50},
            {"pid": 99, "ppid": 1, "name": "other.exe", "cmd": "", "created": t, "act": 1000}]), encoding="utf-8")
        with mock.patch.dict(os.environ, {"FLASHQ_FAKE_PROCS": str(procs)}):
            lv = mod.tree_live(10)
            self.assertEqual((lv["act"], lv["n"], lv["names"]), (162, 4, ["MapEditor.exe"]))
            self.assertEqual(mod.tree_act(10), 162)
            self.assertIsNone(mod.tree_live(555))

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

    def test_ui_state_shows_variant_of_every_kind(self):
        """ui: /api/state ใส่ variant ให้ทุกแถว — งานที่จบ/รันแล้ว = ค่าที่บันทึกไว้จริง · งานรอคิว = ค่าที่จะส่ง (คำนวณตามชนิดงานจาก .flash.json > config.json > ค่าเริ่มต้น) · งานทำที่ไม่ส่ง = ว่าง"""
        sys.path.insert(0, str(REPO))
        import flashq
        (self.home / "jobs").mkdir(parents=True)
        (self.home / "config.json").write_text(json.dumps({"variants": {"doc": "medium"}}), encoding="utf-8")
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait(timeout=30)))
        base_job = {"status": "queued", "pid": sleeper.pid, "pid_start": flashq.proc_start(sleeper.pid), "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01"}
        for n, extra in enumerate([{"kind": "investigate"}, {"kind": "verify"}, {"kind": "qa"}, {"kind": "doc"}, {}]):
            jid = f"20990101_00000{n}_1"
            (self.home / "jobs" / f"{jid}.json").write_text(json.dumps({**base_job, "id": jid, "created": f"2099-01-01 00:00:0{n}", **extra}), encoding="utf-8")
        (self.home / "jobs" / "20200101_000000_1.json").write_text(json.dumps(
            {"id": "20200101_000000_1", "status": "ok", "kind": "verify", "variant": "max", "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01",
             "created": "2020-01-01 00:00:00", "started": "2020-01-01 00:00:00", "finished": "2020-01-01 00:01:00"}), encoding="utf-8")
        base = self.start_ui()
        st = json.loads(self.http(base + "/api/state")[1])
        got = {j["kind"] or "work": j["variant"] for j in st["queued"]}
        self.assertEqual(got, {"investigate": "high", "verify": "low", "qa": "high", "doc": "medium", "work": ""})
        self.assertEqual([j["variant"] for j in st["history"]], ["max"])  # งานที่จบ = ค่าที่บันทึกไว้ ไม่คำนวณใหม่
        html = self.http(base + "/")[1]
        for needle in ("thinkText", "thinkShort", "thinkChip", "ความคิด"):
            self.assertIn(needle, html)

    def test_ui_state_shows_claude_session_title(self):
        """ui: งานรอคิว/รันอยู่ใส่ claude_session + claude_title (ชื่อที่ผู้ใช้เห็นใน sidebar ของ Claude Code จาก transcript) ให้การ์ดบอกว่างานมาจาก session ไหน ·
        ไม่เจอ transcript = ชื่อว่าง (รหัสยังมี) · งานที่จบแล้ว: ใส่ชื่อเฉพาะ 8 แถวที่ตาราง "เพิ่งจบ" โชว์ · งานที่ไม่มี session = ว่างทั้งคู่"""
        sys.path.insert(0, str(REPO))
        import flashq
        claude = self.tmp / "claude_home"
        proj = claude / "projects" / "D--x"
        proj.mkdir(parents=True)
        (proj / "sess-a.jsonl").write_text("\n".join([
            json.dumps({"type": "agent-name", "agentName": "ชื่อเก่า"}, ensure_ascii=False),
            json.dumps({"type": "custom-title", "customTitle": "ปัญหา terrain build"}, ensure_ascii=False)]) + "\n", encoding="utf-8")
        (self.home / "jobs").mkdir(parents=True)
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(lambda: (sleeper.kill(), sleeper.wait(timeout=30)))
        base_job = {"status": "queued", "pid": sleeper.pid, "pid_start": flashq.proc_start(sleeper.pid), "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01"}
        for n, sess in enumerate(["sess-a", "sess-zzz", ""]):
            jid = f"20990101_00000{n}_1"
            (self.home / "jobs" / f"{jid}.json").write_text(json.dumps({**base_job, "id": jid, "created": f"2099-01-01 00:00:0{n}", "claude_session": sess}), encoding="utf-8")
        (self.home / "jobs" / "20200101_000000_1.json").write_text(json.dumps(
            {"id": "20200101_000000_1", "status": "ok", "claude_session": "sess-a", "project": str(self.proj), "plan": "PLAN.md", "tasks": "T-01",
             "created": "2020-01-01 00:00:00", "started": "2020-01-01 00:00:00", "finished": "2020-01-01 00:01:00"}), encoding="utf-8")
        self.env["FLASHQ_CLAUDE_HOME"] = str(claude)
        self.env["FLASHQ_CLAUDE_APP_HOME"] = str(self.tmp / "no_app")  # ไม่ให้ชื่อจากแอป Claude จริงของเครื่องนี้ปนเข้ามา
        base = self.start_ui()
        st = json.loads(self.http(base + "/api/state")[1])
        got = {j["claude_session"]: j.get("claude_title") for j in st["queued"]}
        self.assertEqual(got, {"sess-a": "ปัญหา terrain build", "sess-zzz": "", "": ""})
        self.assertEqual(st["history"][0]["claude_session"], "sess-a")
        self.assertEqual(st["history"][0]["claude_title"], "ปัญหา terrain build")  # ตาราง "เพิ่งจบ" (8 แถวแรก) โชว์ชื่อด้วย
        self.assertIn("fromClaudeHTML", self.http(base + "/")[1])

    def test_open_claude_session_button(self):
        """ปุ่ม "↩ เปิด session": host id มาจากงาน (claude_host) หรือหาจาก cliSessionId ในโฟลเดอร์ของแอป desktop · ผ่านรูปแบบ local_… เท่านั้น ·
        ไม่มี session/ไม่พบในแอป = 404 ไม่เปิดอะไร · ชื่อ session ใช้ชื่อจากแอปเมื่อ transcript ไม่มี"""
        mod = self.load_mod("flashq_open_claude")
        app = self.tmp / "app_sessions" / "u1" / "u2"
        app.mkdir(parents=True)
        (app / "local_aaa-111.json").write_text(json.dumps({"sessionId": "local_aaa-111", "cliSessionId": "cli-1", "title": "ชื่อในแอป"}, ensure_ascii=False), encoding="utf-8")
        mod.CLAUDE_APP_SESSIONS = self.tmp / "app_sessions"
        mod.CLAUDE_PROJECTS = self.tmp / "no_transcripts"
        opened = []
        mod.open_link = opened.append
        mod.claude_app_link = lambda path, params: f"claude://code/{path}?session={params['session']}"
        self.assertEqual(mod.claude_session_title("cli-1"), "ชื่อในแอป")
        code, d = mod.claude_open_session_action({"claude_session": "cli-1"})  # งานเก่า: หาจากแอป
        self.assertEqual((code, d["ok"], opened), (200, True, ["claude://code/continue?session=local_aaa-111"]))
        opened.clear()
        code, d = mod.claude_open_session_action({"claude_session": "cli-1", "claude_host": "local_bbb"})  # งานใหม่: ใช้ที่บันทึกไว้
        self.assertEqual((code, opened), (200, ["claude://code/continue?session=local_bbb"]))
        opened.clear()
        for bad in ({}, {"claude_session": "cli-zzz"}, {"claude_session": "cli-1", "claude_host": "x;calc"}):
            code, d = mod.claude_open_session_action(bad)
            self.assertEqual((code, d["ok"]), (404, False), bad)
        self.assertEqual(opened, [])

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
        self.assertLess(time.time() - t0, 120)  # ต้องเร็วกว่า NOSTART 180 วิ · เพดานหลวมกันเครื่องโหลดตอนรันทั้งชุด
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

    def oc_log_lines(self, root, run, upto, ts=None, other_dir=False):
        """บรรทัด log กลางของ opencode (เวลา UTC · path ทับ backslash เหมือนของจริง) ของ 1 รอบ: เดินตามลำดับจริงจนถึงขั้น upto"""
        t = ts or time.time()
        d = str(self.tmp / "other" if other_dir else root).replace("\\", "\\\\")
        steps = [("creating instance", f'"creating instance" directory="{d}"'), ("bootstrapping", "bootstrapping"), ("loading", 'loading path="x.json"'),
                 ("all LSPs are disabled", '"all LSPs are disabled"'), ("init", "init"), ("created", "created id=ses_x"), ("loop", "loop step=0")]
        out = []
        for i, (key, msg) in enumerate(steps):
            out.append(f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(t + i))}.000Z level=INFO run={run} message={msg}")
            if key == upto:
                break
        return out

    def test_nostart_diag_names_stage_and_warns_big_db(self):
        """NOSTART: อ่านท้าย log กลางของ opencode บอกว่ารอบของโปรเจกต์นี้ค้างหลังขั้นไหน (ข้าม cleanup เบื้องหลัง · ไม่ปนรอบของโฟลเดอร์อื่น) + เตือนฐานข้อมูลใหญ่"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("flashq_nostart", FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        log, db = self.tmp / "opencode.log", self.tmp / "opencode.db"
        now_ts = time.time()
        # รอบ a = โปรเจกต์นี้ ค้างหลัง init (cleanup เบื้องหลังตามมาเองหลัง 1 นาที) · รอบ b = โฟลเดอร์อื่นที่ไปถึง loop · รอบ c = โปรเจกต์นี้แต่เก่ากว่า since
        lines = self.oc_log_lines(self.proj, "aaaa1111", "init", now_ts - 1)
        lines.append(f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(now_ts + 60))}.000Z level=INFO run=aaaa1111 message=cleanup prune=7.days")
        lines += self.oc_log_lines(self.proj, "bbbb2222", "loop", now_ts, other_dir=True)
        lines += self.oc_log_lines(self.proj, "cccc3333", "loop", now_ts - 3600)
        # รอบ d = งานอื่นในโฟลเดอร์เดียวกันที่เริ่มพร้อมกันและโมเดลตอบแล้ว (ถึง step=1) → ห้ามเอามาปน
        lines += self.oc_log_lines(self.proj, "dddd4444", "loop", now_ts + 1)
        lines.append(f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(now_ts + 20))}.000Z level=INFO run=dddd4444 message=loop session.id=ses_x step=1")
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        db.write_bytes(b"x" * 200)
        mod.OC_DB_WARN_GB = 100 / (1 << 30)  # ตั้งเกณฑ์ให้ไฟล์เล็กในเทสต์ถือว่า "ใหญ่"
        d = mod.nostart_diag(self.proj, now_ts, log, db)
        self.assertIn("run=aaaa1111", d)
        self.assertIn("`init`", d)
        self.assertIn("stdin", d)
        self.assertNotIn("dddd4444", d)
        self.assertNotIn("cleanup", d)  # บรรทัดสุดท้ายต้องเป็น init ไม่ใช่ cleanup เบื้องหลัง
        self.assertNotIn("bbbb2222", d)
        self.assertNotIn("cccc3333", d)
        self.assertIn("ฐานข้อมูล opencode ใหญ่", d)
        mod.OC_DB_WARN_GB = 5
        self.assertNotIn("ใหญ่", mod.nostart_diag(self.proj, now_ts, log, db))
        # ไม่มีรอบของโปรเจกต์นี้เลย → process ไม่ทันบูต · log หาย/ไฟล์ db หาย = ไม่พัง
        self.assertIn("ไม่ทันบูต", mod.nostart_diag(self.tmp / "ไม่มีโปรเจกต์นี้", now_ts, log, self.tmp / "no.db"))
        self.assertIn("อ่าน log opencode ไม่ได้", mod.nostart_diag(self.proj, now_ts, self.tmp / "no.log", self.tmp / "no.db"))
        # มีแต่รอบของงานอื่น → บอกว่าเป็นของงานอื่น · รอบที่ส่งคำขอโมเดลแล้วเงียบ → บอกว่าผู้ให้บริการไม่ตอบ
        other = self.oc_log_lines(self.proj, "dddd4444", "loop", now_ts)
        other.append(f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(now_ts + 20))}.000Z level=INFO run=dddd4444 message=loop session.id=ses_x step=1")
        log.write_text("\n".join(other) + "\n", encoding="utf-8")
        self.assertIn("ของงานอื่น", mod.nostart_diag(self.proj, now_ts, log, self.tmp / "no.db"))
        quiet = self.oc_log_lines(self.proj, "eeee5555", "loop", now_ts)
        quiet.append(f"timestamp={time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(now_ts + 10))}.000Z level=INFO run=eeee5555 message=\"llm runtime selected\" llm.runtime=ai-sdk")
        log.write_text("\n".join(quiet) + "\n", encoding="utf-8")
        self.assertIn("ผู้ให้บริการโมเดลแล้วไม่ได้คำตอบ", mod.nostart_diag(self.proj, now_ts, log, self.tmp / "no.db"))

    def test_nostart_run_prints_reason_and_records_it(self):
        """opencode ไม่ขึ้น sessionID (ปลอมให้นอนเฉย ๆ) → ลองใหม่ 1 ครั้ง · แต่ละรอบพิมพ์ "NOSTART รอบ n: ..." · ท้ายผลมี REASON · ใส่ในงาน (nostart_diag + last)"""
        log = self.tmp / "opencode.log"
        log.write_text("\n".join(self.oc_log_lines(self.proj.resolve(), "dddd4444", "init", time.time())) + "\n", encoding="utf-8")
        t0 = time.time()
        r = self.run_q("investigate", "--no-open", "ไม่เริ่ม", env={"FAKE_MODE": "nostart", "FLASHQ_START_LIMIT_SEC": "3", "FLASHQ_OPENCODE_LOG": str(log)})
        out = r.stdout + r.stderr
        self.assertLess(time.time() - t0, 60)
        self.assertEqual(r.returncode, 1, out)
        self.assertIn("FLASH_RUN=NOSTART", out)
        self.assertIn("NOSTART → ลองใหม่อัตโนมัติ", out)
        self.assertIn("NOSTART รอบ 1:", out)
        self.assertIn("NOSTART รอบ 2:", out)
        self.assertIn("NOSTART รอบ 3:", out)  # ลองใหม่เองได้ 2 ครั้ง (ค่าเริ่มต้น --retry-nostart 2)
        self.assertIn("REASON: opencode ไม่เริ่มทำงาน (รอบแรกรอ 3 วิ · รอบลองใหม่ 3 วิ) ทั้ง 3 รอบ", out)
        self.assertIn("run=dddd4444", out)
        job = json.loads(next((self.home / "jobs").glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(len(job["nostart_diag"]), 3)
        self.assertTrue(job["last"].startswith("NOSTART: "))

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
        d = urllib.parse.urlencode({"directory": "D:/งาน/proj"})
        self.assertTrue(queries and all(q in (d, d + "&limit=2") for q in queries), queries)
        self.assertIn(d + "&limit=2", queries)  # ขอข้อความล่าสุดแค่ 2 — session ยาวมากดึงทั้งประวัติแล้ว server ตัดการเชื่อมต่อ (วินิจฉัยไม่ได้)
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
        self.assertTrue(all(p.endswith("?" + want) or p.endswith("?" + want + "&limit=2") for p in asks), asks[:3])
        mode["active"] = False
        hits.clear()
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env={**env, "FAKE_SLEEP": "60"})
        self.assertIn("FLASH_RUN=TIMEOUT", r.stdout)
        self.assertIn("รอโมเดล", r.stdout)
        aborts = [p for m, p in hits if m == "POST"]
        self.assertEqual(len(aborts), 2, hits)  # รอบแรก + รอบลองใหม่
        self.assertTrue(all(re.match(r"/session/ses_fake\d+/abort\?directory=", p) for p in aborts), aborts)
        self.assertIn("หยุด session", r.stdout)

    def test_live_model_wait_cuts_stall_before_floor(self):
        """server ยืนยันว่าไม่มี tool รันและไม่มีอะไรขยับ = รอโมเดลอย่างเดียว → ตัดที่ model_wait_min ไม่ต้องรอขั้นต่ำ stall_floor_min (5 นาที)
        แต่ถ้า subagent ยังขยับ = ไม่ตัด"""
        (self.proj / ".flash.json").write_text(json.dumps({"stall_min": 10, "stall_floor_min": 5, "model_wait_min": 0.05, "require_plan_in_remote": False}), encoding="utf-8")
        mode = {"active": False}
        url, hits = self.fake_live_server(mode)
        t0 = time.time()
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env={"FLASHQ_LIVE_URL": url, "FAKE_SLEEP": "60"})
        self.assertLess(time.time() - t0, 45, r.stdout)
        self.assertIn("FLASH_RUN=TIMEOUT", r.stdout)
        self.assertIn("เกณฑ์รอโมเดล", r.stdout)
        self.assertIn("ลองใหม่อัตโนมัติ", r.stdout)
        mode["active"] = True
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "live", "--no-open", env={"FLASHQ_LIVE_URL": url, "FAKE_SLEEP": "12"})
        self.assertIn("FLASH_RUN=OK", r.stdout, r.stdout + r.stderr)

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

    def test_goal_check_warns_big_goal_split_phases(self):
        """ธงใหญ่ (เกณฑ์ >8 ข้อ) = เตือนให้แบ่งเฟส ไม่ใช่ error · ธงเล็กไม่เตือน"""
        acc = f"\"{sys.executable}\" tests/acc.py"
        tail = "goal-files: src/*\ngoal-locked: tests/acc.py\ngoal-max-rounds: 5\n"
        self.goal_repo("".join(f"- [ ] G-{n:02d} ค่าเป็น new · ตรวจ: `{acc}`\n" for n in range(1, 10)) + tail)
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL_CHECK=OK", r.stdout, r.stdout)
        self.assertIn("ธงใหญ่", r.stdout)
        self.assertIn("แบ่งเป็นเฟส", r.stdout)
        (self.proj / "docs/plans/GOAL_x.md").write_text(f"- [ ] G-01 ค่าเป็น new · ตรวจ: `{acc}`\n" + tail, encoding="utf-8")
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertNotIn("ธงใหญ่", r.stdout)

    def test_goal_check_warns_ui_counting_only(self):
        """งาน UI (มีคนตรวจเรื่องหน้าตา): เกณฑ์เครื่องเป็นการนับล้วน + ไม่อ้าง mockup = เตือน · อ้าง mockup แล้วเตือนข้อ mockup หาย"""
        acc = f"\"{sys.executable}\" tests/acc.py"
        body = (f"- [ ] G-01 มีคำอธิบาย ≥12 จุด · ตรวจ: `{acc}`\n- [ ] G-02 หน้าตาใช้ง่าย · คนตรวจ: เปิดหน้าแรกลองเลือกค่า\n"
                "goal-files: src/*\ngoal-locked: tests/acc.py\ngoal-max-rounds: 5\n")
        self.goal_repo(body)
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL_CHECK=OK", r.stdout, r.stdout)
        self.assertIn("เป็นการนับล้วน (G-01)", r.stdout)
        self.assertIn("ยังไม่มีเกณฑ์อ้าง mockup", r.stdout)
        (self.proj / "docs/plans/GOAL_x.md").write_text(body + f"- [ ] G-03 โครงหน้าตรง mockup_B.html · ตรวจ: `{acc}`\n", encoding="utf-8")
        r = self.run_q("goal", "check", "docs/plans/GOAL_x.md")
        self.assertNotIn("นับล้วน", r.stdout)
        self.assertNotIn("อ้าง mockup", r.stdout)

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
        (self.proj / "docs" / "other").mkdir(exist_ok=True)
        (self.proj / "docs" / "other" / "PLAN_OTHER_FLASH_q.md").write_text("q\n", encoding="utf-8")  # แผนเรื่องอื่นชื่อ PLAN_<x>_FLASH_ + รหัสงาน (T-xx) ต้องไม่ถูกนับเป็นของธงนี้
        subprocess.run(["git", "-C", str(self.proj), "add", "docs/other/PLAN_OTHER_FLASH_q.md"], check=True)
        subprocess.run(["git", "-C", str(self.proj), "commit", "-qm", "docs: บันทึกผลแผนอื่น (T-01)"], check=True)
        r = self.run_q("goal", "verify", "docs/plans/GOAL_x.md")
        self.assertIn("GOAL=DONE", r.stdout, r.stdout)
        self.assertNotIn("PLAN_OTHER_FLASH_q.md", r.stdout.split("เบรก:")[-1])
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
        """auto: งานที่ชนรอเกิน starve_min → ล็อกเฉพาะงานที่ชนกับมัน · งานที่ไม่ชนแซงได้"""
        self.auto_plan()
        self.assertEqual(self.run_q("config", "schedule", "auto").returncode, 0)
        self.assertEqual(self.run_q("config", "starve_min", "0.05").returncode, 1)  # ต่ำกว่าขั้นต่ำ
        self.assertEqual(self.run_q("config", "starve_min", "0.1").returncode, 0)  # 6 วิ
        p1 = self.submit("PLAN.md", "T-01", sleep="30")
        self.wait_for(lambda: self.by_key().get("T-01", {}).get("status") == "running", msg="T-01 ไม่เริ่ม")
        p2 = self.submit("PLAN.md", "T-02", sleep="1")
        time.sleep(7.5)  # T-02 รอเกิน 6 วิ
        (self.proj / "PLAN.md").write_text(  # เพิ่ม T-04 ที่ชน T-01/T-02 ไว้ก่อนส่ง T-03
            "# plan\n- [ ] **T-01** `src/a.cpp`\n- [ ] **T-02** `src/a.cpp`\n- [ ] **T-03** `src/c.cpp`\n"
            "- [ ] **T-04** `src/a.cpp`\n", encoding="utf-8")
        p3 = self.submit("PLAN.md", "T-03", sleep="1")
        self.wait_for(lambda: self.by_key().get("T-03", {}).get("status") in ("running", "ok"), sec=10,
                      msg="T-03 ไม่ได้แซง (ยังถูกล็อกทั้งคิว)")
        p4 = self.submit("PLAN.md", "T-04", sleep="1")
        time.sleep(2)
        st = self.run_q("status").stdout
        self.assertIn("ล็อกหัวคิว", st)
        self.assertIn("กันอดตาย", st)
        self.assertEqual(self.by_key()["T-04"]["status"], "queued")
        for p in (p1, p2, p3, p4):
            self.assertIn("FLASH_RUN=OK", p.communicate(timeout=120)[0])
        j = self.by_key()
        self.assertLess(j["T-03"]["started"], j["T-01"]["finished"])  # T-03 ไม่ชนกับงานที่อดตาย = แซงได้
        self.assertGreaterEqual(j["T-04"]["started"], j["T-01"]["finished"])  # T-04 ชน = รอ

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
        (self.proj / "E2.md").write_text("# E2\nflashq-files: Common/y.h\n", encoding="utf-8")
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
        self.assertEqual(c("E.md", "B.md"), "")  # ฝั่งเดียวแตะไฟล์ร่วม = ไม่ชนแล้ว
        self.assertEqual(c("F.md", "B.md"), "")
        self.assertEqual(c("G.md", "B.md"), "")
        self.assertIn("ใช้ร่วม", c("E.md", "E2.md"))  # สองฝั่งแตะโฟลเดอร์ร่วม Common/
        self.assertIn("CMakeLists.txt", c("F.md", "G.md"))  # สองฝั่งแตะไฟล์ร่วมคนละแบบ
        self.assertIn("Proto/p.h", c("F.md", "G.md"))
        cfg = {"require_plan_in_remote": False, "parallel_shared": ["Proto/"], "parallel_shared_strict": True}
        (self.proj / ".flash.json").write_text(json.dumps(cfg), encoding="utf-8")
        self.assertIn("ใช้ร่วม", c("E.md", "B.md"))  # โหมดเข้ม: ฝั่งเดียวแตะก็ชน
        self.assertIn("CMakeLists.txt", c("F.md", "B.md"))
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False, "parallel_shared": ["Proto/"]}),
                                               encoding="utf-8")
        self.assertIn("ดึงรายการไฟล์", c("NOPE.md", "B.md"))
        self.assertEqual(flashq.conflict_reason(J("E.md"), J("E.md", str(self.tmp)), flashq.job_info), "")  # คนละโปรเจกต์
        self.assertTrue(flashq.paths_overlap("**", "x/y.cpp"))
        self.assertFalse(flashq.paths_overlap("Client/UI/*.h", "Client/a.cpp"))
        # flashq-exclusive: ขอบเขตที่ห้ามงานอื่นแตะ (ใช้คู่กับ parallel: no) · ไม่ประกาศ = บล็อกทั้งก้อนเหมือนเดิม
        (self.proj / "I.md").write_text("# I\nflashq-files: MapEditor/b.cpp\nflashq-parallel: no — แตะ build\n"
                                       "flashq-exclusive: Build/*, CMakeLists.txt\n", encoding="utf-8")
        (self.proj / "J.md").write_text("# J\nflashq-files: Client/z.cpp\n", encoding="utf-8")
        (self.proj / "K.md").write_text("# K\nflashq-files: Build/x.cmake\n", encoding="utf-8")
        self.assertEqual(flashq.plan_meta(P, "I.md")["exclusive"], ["Build/*", "CMakeLists.txt"])
        self.assertNotIn("exclusive", flashq.plan_meta(P, "B.md"))
        self.assertEqual(flashq.job_info(J("I.md"))["exclusive"], ["Build/*", "CMakeLists.txt"])
        self.assertEqual(c("I.md", "J.md"), "")  # ไม่ซ้อนขอบเขต = รันพร้อมกันได้ แม้ I สั่ง no
        self.assertEqual(c("J.md", "I.md"), "")
        self.assertIn("แผนสั่งให้รอ", c("I.md", "K.md"))
        self.assertIn("Build/x.cmake", c("I.md", "K.md"))
        self.assertIn("flashq-parallel", c("K.md", "I.md"))
        self.assertIn("Build/x.cmake", c("K.md", "I.md"))
        self.assertIn("ดึงรายการไฟล์", c("I.md", "NOPE.md"))

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

    def test_usage_flash_sums_logs_and_subagents(self):
        """`flashq usage --flash`: รวม step_finish ใน log ของงานที่รันผ่าน flashq (out = output+reasoning) + subagent (session ลูกทุกชั้นใน opencode.db ·
        session หลักไม่นับซ้ำ) · --since ตัดตามวันที่สั่งงาน · กรองโปรเจกต์ได้ · ไม่มี DB = สรุปจาก log อย่างเดียว + บอกว่าต่ำกว่าจริง
        · ประมาณการ Claude ทำเอง = token เท่ากันคูณราคาในตาราง หักค่า Claude ที่เคยวัดด้วย flashq usage <แผน> (session ซ้ำนับครั้งเดียว)"""
        import sqlite3
        mod = self.load_mod("flashq_usage_flash")
        (self.home / "jobs").mkdir(parents=True, exist_ok=True)
        (self.home / "usage").mkdir(parents=True, exist_ok=True)
        logs = self.tmp / "oclogs"
        logs.mkdir()

        def fin(sid, i, o, rs, cr, cw, cost):
            return json.dumps({"type": "step_finish", "sessionID": sid, "part": {"type": "step-finish", "cost": cost,
                               "tokens": {"total": i + o + rs + cr + cw, "input": i, "output": o, "reasoning": rs, "cache": {"read": cr, "write": cw}}}})

        (logs / "a.jsonl").write_text("\n".join([json.dumps({"type": "step_start"}), fin("S1", 100, 10, 5, 1000, 20, 0.01),
                                                 json.dumps({"type": "tool_use", "part": {"note": "step_finish อยู่ในข้อความ"}}),
                                                 fin("S1", 50, 5, 0, 500, 0, 0.005)]) + "\n", encoding="utf-8")
        (logs / "old.jsonl").write_text(fin("S9", 1000, 0, 0, 0, 0, 1.0) + "\n", encoding="utf-8")
        mk = lambda jid, created, project, lg, **kw: (self.home / "jobs" / f"{jid}.json").write_text(  # noqa: E731
            json.dumps({"id": jid, "created": created, "project": str(project), "logs": [str(logs / lg)] if lg else [], "kind": "work",
                        "model": "p/m", **kw}), encoding="utf-8")
        recent = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
        mk("j1", recent, self.proj, "a.jsonl", session="S1")
        mk("j2", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 40 * 86400)), self.proj, "old.jsonl")
        mk("j3", recent, self.tmp / "other", "")  # ไม่มี log = นับเป็น "ไม่มีข้อมูล"
        db = self.tmp / "oc.db"
        con = sqlite3.connect(db)
        con.executescript("create table session (id text primary key, parent_id text); create table message (id text, session_id text, data text);")
        con.executemany("insert into session values (?,?)", [("S1", None), ("C1", "S1"), ("C2", "C1"), ("X", None)])
        am = lambda i, o, rs, cr, cw, cost, role="assistant": json.dumps({"role": role, "cost": cost, "tokens": {  # noqa: E731
            "input": i, "output": o, "reasoning": rs, "cache": {"read": cr, "write": cw}}})
        con.executemany("insert into message values (?,?,?)", [
            ("m1", "S1", am(99999, 99999, 0, 0, 0, 99.0)),  # session หลัก: มาจาก log แล้ว → ห้ามนับซ้ำ
            ("m2", "C1", am(10, 2, 1, 100, 0, 0.002)), ("m3", "C1", am(777, 7, 0, 0, 0, 7.0, role="user")),
            ("m4", "C2", am(20, 4, 0, 200, 0, 0.003)), ("m5", "X", am(5555, 0, 0, 0, 0, 5.0))])  # X = ไม่ใช่ลูกของงานใด
        con.commit()
        con.close()
        (self.home / "config.json").write_text(json.dumps({"flash_compare": ["claude-sonnet-5-5", "claude-nope"],
                                                           "prices": {"claude-sonnet-5-5": {"in": 1e6, "out": 1e6, "cache_read": 1e5, "cache_write": 2e6}}}), encoding="utf-8")
        (self.home / "usage" / "PLAN_X.json").write_text(json.dumps({"project": str(self.proj), "session_list": [
            {"id": "s-a", "first": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "usd": 5.0},
            {"id": "s-old", "first": "2020-01-01T00:00:00", "usd": 50.0}]}), encoding="utf-8")
        (self.home / "usage" / "PLAN_Y.json").write_text(json.dumps({"project": str(self.proj), "session_list": [
            {"id": "s-a", "first": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "usd": 5.0}]}), encoding="utf-8")  # session ซ้ำข้ามแผน
        mod.JOBS, mod.USAGE_DIR, mod.CONFIG, mod.OC_DB = self.home / "jobs", self.home / "usage", self.home / "config.json", db
        s = mod.flash_usage_summary(30)
        # in = 100+50 + 10+20 · out = (10+5)+5 + (2+1)+4 · cache อ่าน = 1500 + 300 · cache เขียน = 20
        t = s["total"]
        self.assertEqual((s["jobs"], s["jobs_no_data"]), (1, 1))
        self.assertEqual((t["in"], t["out"], t["cache_read"], t["cache_write"], t["tokens"]), (180, 27, 1800, 20, 2027))
        self.assertAlmostEqual(t["usd"], 0.02, places=6)
        self.assertEqual(s["subagent"], {"sessions": 2, "usd": 0.005, "tokens": 337, "included": True})
        self.assertEqual([c["model"] for c in s["compare"]], ["claude-sonnet-5-5"])  # ไม่รู้ราคา = ข้าม
        c = s["compare"][0]  # 180×1 + 27×1 + 1800×0.1 + 20×2 = 427 (ราคาต่อ token ตามที่ตั้ง)
        self.assertEqual((c["equiv_usd"], c["saved_gross"], c["saved_net"]), (427.0, 426.98, 421.98))
        self.assertEqual(s["claude_overhead"], {"usd": 5.0, "sessions": 1})
        self.assertEqual([g["name"] for g in s["by_project"]], [self.proj.name])
        self.assertEqual(s["by_kind"][0]["name"], "work")
        # ตาราง "เพิ่งจบ": แถวที่จบแล้วได้ row["flash"] (token · USD จริง · ราคาถ้าเป็น Claude) · ไม่มีข้อมูล/ยังไม่จบ = ไม่ใส่
        rows = [{"id": "j1", "finished": "x"}, {"id": "j3", "finished": "x"}, {"id": "j1", "finished": ""}]
        mod.flash_brief_rows(rows, {j["id"]: j for j in mod.jobs()})
        self.assertEqual(rows[0]["flash"], {"tokens": 2027, "usd": 0.02, "sub_tokens": 337,
                                            "compare": [{"model": "claude-sonnet-5-5", "usd": 427.0}]})
        self.assertNotIn("flash", rows[1])
        self.assertNotIn("flash", rows[2])
        # tooltip บนป้ายสถานะ: สาเหตุตามสถานะ · OK ไม่มี
        self.assertIn("STALL: x", mod.job_reason({"timeout_reason": "STALL: x"}, "timeout"))
        self.assertIn("หมดเวลา", mod.job_reason({}, "timeout"))
        self.assertIn("boom", mod.job_reason({"rc": 2, "last": "boom"}, "fail"))
        self.assertIn("exit 2", mod.job_reason({"rc": 2, "last": "boom"}, "fail"))
        self.assertIn("read: C:/x", mod.job_reason({"perm_denied": [{"kind": "read", "path": "C:/x"}]}, "denied"))
        self.assertEqual(mod.job_reason({"last": "ok"}, "ok"), "")
        ui = (FLASHQ.parent / "ui.html").read_text(encoding="utf-8")
        self.assertIn("badge(j.state, j.reason)", ui)
        self.assertIn("ยังไม่มี token", ui)
        s60 =mod.flash_usage_summary(60)
        self.assertEqual((s60["jobs"], s60["total"]["in"]), (2, 180 + 1000))
        self.assertEqual(mod.flash_usage_summary(30, str(self.tmp / "other"))["jobs"], 0)
        # ไม่มี DB → log หลักอย่างเดียว
        mod.OC_DB = self.tmp / "nope.db"
        s = mod.flash_usage_summary(30)
        self.assertEqual((s["total"]["tokens"], s["subagent"]["included"]), (150 + 20 + 1500 + 20, False))
        # CLI
        env = {"FLASHQ_OPENCODE_DB": str(db)}
        r = self.run_q("usage", "--flash", "--since", "30", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 งาน (อีก 1 งานไม่มีข้อมูล token)", r.stdout)
        self.assertIn("USAGE_FLASH jobs=1 tokens=2027 usd=0.02 claude_equiv=427.00 saved_net=421.98", r.stdout)
        r = self.run_q("usage", "--flash", env={"FLASHQ_OPENCODE_DB": str(self.tmp / "nope.db")})
        self.assertIn("ยังไม่รวม token ของ subagent", r.stdout)
        r = self.run_q("usage", "--flash", str(self.tmp / "no_such_dir"), env=env)
        self.assertEqual(r.returncode, 1)
        r = self.run_q("usage", env=env)  # ไม่ใส่อะไรเลย = บอกวิธีใช้ ไม่พัง
        self.assertEqual(r.returncode, 1)
        self.assertIn("--flash", r.stdout)


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


class QaTest(unittest.TestCase):
    """นักทดสอบ (flashq qa): flashq รันคำสั่งทดสอบเองแล้วตัดสินจาก exit code จริง · fail-closed · ไม่เรียกโมเดลถ้าไม่ล้ม"""
    setUp, tearDown, run_q, load_mod = (FlashqTest.setUp, FlashqTest.tearDown, FlashqTest.run_q, FlashqTest.load_mod)
    start_ui, http, ui_token, wait_job = (FlashqTest.start_ui, FlashqTest.http, FlashqTest.ui_token, FlashqTest.wait_job)

    def py(self, name, body):
        (self.proj / name).write_text(body, encoding="utf-8")
        return f'"{sys.executable}" {name}'

    def presets(self, **named):
        cfg = {"require_plan_in_remote": False, "qa": {"presets": named}}
        (self.proj / ".flash.json").write_text(json.dumps(cfg), encoding="utf-8")

    def git(self, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.proj, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def init_git(self):
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "i")

    def job_files(self):
        return [json.loads(f.read_text(encoding="utf-8")) for f in sorted((self.home / "jobs").glob("*.json"))]

    def test_verdicts_come_from_exit_code_and_fail_closed(self):
        """ผ่าน = exit 0 (+ พบ expect) · exit≠0 / ไม่พบ expect / เกินเวลา = ไม่ผ่านทั้งหมด · ผลรวม FAIL ถ้ามีชุดเดียวที่ไม่ใช่ PASS"""
        ok = self.py("ok.py", "print('3 passed')\n")
        bad = self.py("bad.py", "import sys\nprint('E AssertionError: boom')\nsys.exit(2)\n")
        silent = self.py("silent.py", "print('collected 0 items')\n")
        slow = self.py("slow.py", "import time\ntime.sleep(120)\n")
        self.presets(ok={"cmd": ok, "expect": r"\d+ passed"}, bad=bad, silent={"cmd": silent, "expect": r"\d+ passed"},
                     slow={"cmd": slow, "timeout_min": 0.1})
        r = self.run_q("qa", "ok", "--no-analyze")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=OK", r.stdout)
        self.assertIn("QA=PASS", r.stdout)
        j = self.job_files()[0]
        self.assertEqual((j["kind"], j["readonly"], j["status"], j["tasks"]), ("qa", True, "ok", "ok"))
        t0 = time.time()
        r = self.run_q("qa", "--no-analyze")  # ไม่ระบุชื่อ = ทุกชุด
        self.assertLess(time.time() - t0, 60)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=FAIL", r.stdout)
        self.assertIn("QA=FAIL", r.stdout)
        self.assertIn("✅ ok", r.stdout)
        self.assertIn("bad=FAIL", r.stdout)
        self.assertIn("AssertionError: boom", r.stdout)  # บรรทัดสำคัญจาก log
        self.assertIn("silent=NOEXPECT", r.stdout)  # exit 0 แต่ไม่พบ "N passed" ห้ามนับผ่าน
        self.assertIn("slow=TIMEOUT", r.stdout)
        j = [x for x in self.job_files() if x["tasks"] == "ok bad silent slow"][0]
        self.assertEqual((j["status"], j["result"]), ("fail", "FAIL"))
        self.assertEqual([s["verdict"] for s in j["qa"]["specs"]], ["PASS", "FAIL", "NOEXPECT", "TIMEOUT"])
        self.assertTrue(j["last"].startswith("❌"))
        self.assertFalse((self.home / "running.lock").exists())
        self.assertFalse(self.args_out.exists())  # ใช้ --no-analyze = ไม่เรียกโมเดลเลย
        row = json.loads(sorted((self.home / "inbox").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual((row["kind"], row["status"]), ("qa", "FAIL"))
        self.assertTrue(row["last"].startswith("❌"))  # หัวข้อผลอยู่หน้า (ไม่ถูกตัดท้าย)
        r = self.run_q("list", "--all")
        self.assertIn("[ทดสอบ] ok bad silent slow  [", r.stdout)  # ไม่มีช่องว่างซ้อนจากแผนที่ว่าง

    @unittest.skipUnless(os.name == "nt", "ตัวอ่าน CPU/I/O ของโปรเซสใช้ได้บน Windows")
    def test_silent_frozen_suite_is_hang_but_busy_silent_suite_is_spared(self):
        """ชุดที่ไม่ได้ตั้ง idle_min: พ่น log เป็นจังหวะแล้วเงียบ + โปรเซสนิ่งสนิท = ค้าง (ตัดเร็ว ไม่รอ timeout_min) · เงียบแต่ CPU ยังขยับ = ทำงานจริง ไม่ฆ่า"""
        env = {"FLASHQ_QA_ADAPT_FLOOR_SEC": "2", "FLASHQ_QA_FROZEN_SEC": "3", "FLASHQ_QA_ADAPT_POLL_SEC": "1"}
        hang = self.py("hang.py", "import time\nfor i in range(6):\n    print('PASS', i, flush=True)\n    time.sleep(1.2)\ntime.sleep(120)\n")
        busy = self.py("busy.py", "import time\nfor i in range(6):\n    print('PASS', i, flush=True)\n    time.sleep(1.2)\nt = time.time()\nwhile time.time() - t < 20:\n    sum(range(10000))\nprint('PASS=6 FAIL=0', flush=True)\n")
        self.presets(hang={"cmd": hang, "timeout_min": 10, "retry": 0}, busy={"cmd": busy, "timeout_min": 10, "retry": 0})
        t0 = time.time()
        pr = self.run_q("qa", "hang", "--no-analyze", env=env, wait=False)
        try:
            out, _ = pr.communicate(timeout=100)
        except subprocess.TimeoutExpired:
            pr.kill()
            self.fail("ไม่ตัดภายใน 100 วิ: " + pr.communicate()[0])
        r = types.SimpleNamespace(stdout=out)
        self.assertLess(time.time() - t0, 90, r.stdout)
        self.assertIn("FLASH_RUN=TIMEOUT", r.stdout)
        self.assertIn("นิ่งสนิท", r.stdout)
        r = self.run_q("qa", "busy", "--no-analyze", env=env)
        self.assertIn("FLASH_RUN=OK", r.stdout, r.stdout + r.stderr)

    @unittest.skipUnless(os.name == "nt", "ตัวอ่านตารางโปรเซสใช้ได้บน Windows")
    def test_silent_suite_shows_live_pulse_in_state_then_clears(self):
        """ชุดที่ไม่พิมพ์อะไรเลย: ระหว่างรันงานมี qa_live (จำนวนโปรเซส/ชื่อ) ให้หน้าเว็บโชว์ · จบแล้วหายไป"""
        quiet = self.py("quiet.py", "import time\nt = time.time()\nwhile time.time() - t < 12:\n    sum(range(10000))\n")
        self.presets(quiet={"cmd": quiet, "timeout_min": 5, "retry": 0})
        pr = self.run_q("qa", "quiet", "--no-analyze", env={"FLASHQ_QA_LIVE_POLL_SEC": "1"}, wait=False)
        seen = None
        t_end = time.time() + 40
        while time.time() < t_end and pr.poll() is None:
            for j in self.job_files():
                if j.get("qa_live"):
                    seen = j["qa_live"]
            if seen:
                break
            time.sleep(0.5)
        out, _ = pr.communicate(timeout=60)
        self.assertIsNotNone(seen, out)
        self.assertGreaterEqual(seen["n"], 1)
        self.assertTrue(any("python" in n.lower() for n in seen["names"]), seen)
        self.assertIn("FLASH_RUN=OK", out)
        self.assertFalse(any(j.get("qa_live") for j in self.job_files()))

    def test_only_timeouts_is_timeout_status_and_log_shows_summary(self):
        slow = self.py("slow.py", "import time\ntime.sleep(120)\n")
        self.presets(slow={"cmd": slow, "timeout_min": 0.1})
        r = self.run_q("qa", "slow", "--no-analyze")
        self.assertEqual(r.returncode, 1)
        self.assertIn("FLASH_RUN=TIMEOUT", r.stdout)
        jid = re.search(r"job=(\S+)", r.stdout).group(1)
        r = self.run_q("log", jid)
        self.assertIn("slow=TIMEOUT", r.stdout)

    def test_start_errors_never_create_a_job(self):
        """ตั้งค่าเพี้ยน = ปฏิเสธก่อนรันอะไรทั้งนั้น พร้อมบอกว่าแก้ตรงไหน"""
        (self.proj / "tests").mkdir()
        r = self.run_q("qa")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ยังไม่ได้ตั้งชุดทดสอบ", r.stdout)
        self.assertIn("python -m pytest -q", r.stdout)  # เดาให้เป็นคำแนะนำเท่านั้น
        self.assertFalse(list((self.home / "jobs").glob("*.json")) if (self.home / "jobs").exists() else [])
        for label, preset, want in [
                ("หลายบรรทัด", {"cmd": "echo a\necho b"}, "บรรทัดเดียว"), ("ว่าง", {"cmd": " "}, "ไม่มี cmd"),
                ("regex เสีย", {"cmd": "echo x", "expect": "(unclosed"}, "regex"), ("retry เกิน", {"cmd": "echo x", "retry": 9}, "retry"),
                ("เวลาเป็นข้อความ", {"cmd": "echo x", "timeout_min": "ซักพัก"}, "ตัวเลข"), ("เวลาน้อยเกิน", {"cmd": "echo x", "timeout_min": 0}, "timeout_min"),
                ("cwd นอกโปรเจกต์", {"cmd": "echo x", "cwd": ".."}, "อยู่นอกโปรเจกต์"), ("cwd ไม่มี", {"cmd": "echo x", "cwd": "nope"}, "ไม่พบโฟลเดอร์"),
                ("ชนิดผิด", 42, "ต้องเป็นข้อความคำสั่ง")]:
            self.presets(t=preset)
            r = self.run_q("qa", "t", "--no-analyze")
            self.assertEqual(r.returncode, 1, label + r.stdout)
            self.assertIn(want, r.stdout, label)
        self.presets(t="echo x")
        r = self.run_q("qa", "ไม่มีชุดนี้", "--no-analyze")
        self.assertIn("ไม่มีชุดทดสอบชื่อ", r.stdout)
        (self.proj / ".flash.json").write_text("{ไม่ใช่ json", encoding="utf-8")
        r = self.run_q("qa", "--no-analyze")
        self.assertEqual(r.returncode, 1)
        self.assertIn("JSON เสีย", r.stdout)
        self.assertFalse(list((self.home / "jobs").glob("*.json")) if (self.home / "jobs").exists() else [])

    def test_adhoc_cmd_and_cwd_inside_project(self):
        sub = self.proj / "sub"
        sub.mkdir()
        (sub / "here.py").write_text("import os\nprint('cwd=' + os.path.basename(os.getcwd()), '1 passed')\n", encoding="utf-8")
        self.presets(inner={"cmd": f'"{sys.executable}" here.py', "cwd": "sub", "expect": "cwd=sub 1 passed"})
        r = self.run_q("qa", "inner", "--no-analyze")
        self.assertIn("QA=PASS", r.stdout, r.stdout)
        r = self.run_q("qa", "--cmd", f'"{sys.executable}" -c "import sys; sys.exit(3)"', "--no-analyze")
        self.assertEqual(r.returncode, 1)
        self.assertIn("adhoc=FAIL", r.stdout)

    def test_detect_standalone_test_scripts_instead_of_pytest(self):
        """tests/test_*.py ที่รันตรงด้วย python (ไม่มี pytest) → แนะนำ cmds ทีละไฟล์ ไม่ใช่ pytest"""
        t = self.proj / "tests"
        t.mkdir()
        (t / "test_a.py").write_text("def main():\n    pass\n\nif __name__ == '__main__':\n    main()\n", encoding="utf-8")
        (t / "test_b.py").write_text("print('x')\nif __name__ == \"__main__\":\n    pass\n", encoding="utf-8")
        mod = self.load_mod("flashq_qa_detect")
        found = mod.qa_detect(self.proj)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["cmds"], ["python tests/test_a.py", "python tests/test_b.py"])
        self.assertNotIn("cmd", found[0])
        r = self.run_q("qa", "--no-analyze")
        self.assertIn("test_a.py", r.stdout)
        self.assertNotIn("pytest -q", r.stdout)
        (t / "test_c.py").write_text("import pytest\ndef test_x():\n    pass\n", encoding="utf-8")  # ไฟล์ที่พึ่ง pytest ไม่นับเป็น standalone
        self.assertNotIn("tests/test_c.py", json.dumps(mod.qa_detect(self.proj)))
        (self.proj / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")  # ตั้ง pytest ชัด ๆ → ใช้ pytest
        self.assertEqual(mod.qa_detect(self.proj)[0]["cmd"], "python -m pytest -q")

    def test_detect_playwright_ui_scripts_as_separate_ui_preset(self):
        """tests/ui_*.py ที่ import playwright → preset 'ui' แยกจาก unit (cmds + env_exit 3) · ไม่ import playwright = ไม่นับ"""
        t = self.proj / "tests"
        t.mkdir()
        (t / "ui_smoke.py").write_text("from playwright.sync_api import sync_playwright\nif __name__ == '__main__':\n    pass\n", encoding="utf-8")
        (t / "ui_helper.py").write_text("print('no browser')\n", encoding="utf-8")
        (t / "test_a.py").write_text("if __name__ == '__main__':\n    pass\n", encoding="utf-8")
        mod = self.load_mod("flashq_qa_detect")
        found = {x["name"]: x for x in mod.qa_detect(self.proj)}
        self.assertEqual(found["ui"]["cmds"], ["python tests/ui_smoke.py"])
        self.assertEqual(found["ui"]["env_exit"], 3)
        self.assertEqual(found["unit"]["cmds"], ["python tests/test_a.py"])
        r = self.run_q("qa", "--no-analyze")
        self.assertIn('"env_exit": 3', r.stdout)

    def test_cmds_preset_reports_each_command_separately_with_default_retry(self):
        """preset แบบ cmds: แยกผลทีละคำสั่ง (สคริปต์ที่ผ่านไม่ถูกบังด้วยตัวที่ล้ม) · retry เริ่มต้น 1 → ล้มชั่วคราวแล้วผ่าน = FLAKY · retry:0 ปิดได้"""
        for n in ("a", "c"):
            (self.proj / f"test_{n}.py").write_text("print('ok')\n", encoding="utf-8")
        (self.proj / "test_b.py").write_text("import os, sys\nif os.path.exists('b.mark'):\n    sys.exit(0)\nopen('b.mark', 'w').close()\nsys.exit(1)\n", encoding="utf-8")
        py = f'"{sys.executable}"'
        self.presets(unit={"cmds": [f"{py} test_a.py", f"{py} test_b.py", {"cmd": f"{py} test_c.py"}]})
        r = self.run_q("qa", "--no-analyze")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("unit:test_b=FLAKY", r.stdout.split("----")[0])
        j = self.job_files()[-1]
        rows = {s["name"]: s for s in j["qa"]["specs"]}
        self.assertEqual({k: v["verdict"] for k, v in rows.items()}, {"unit:test_a": "PASS", "unit:test_b": "FLAKY", "unit:test_c": "PASS"})
        self.assertEqual(rows["unit:test_a"]["runs"], 1)  # ผ่านรอบแรก = ไม่รันซ้ำ
        self.assertEqual(rows["unit:test_b"]["runs"], 2)
        self.assertIn("เวลา: รันเทสต์", r.stdout)
        (self.proj / "b.mark").unlink()
        self.presets(unit={"cmds": [f"{py} test_b.py"], "retry": 0})
        r = self.run_q("qa", "--no-analyze")
        self.assertIn("unit:test_b=FAIL", r.stdout)
        for bad, want in (({"cmds": []}, "cmds ต้องเป็นรายการ"), ({"cmds": "x"}, "cmds ต้องเป็นรายการ"), ({"cmds": ["echo x"], "cmd": "echo y"}, "อย่างใดอย่างหนึ่ง")):
            self.presets(t=bad)
            r = self.run_q("qa", "t", "--no-analyze")
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn(want, r.stdout)

    def test_key_lines_pick_final_exception_not_traceback_header(self):
        mod = self.load_mod("flashq_qa_keys")
        text = ("running\nTraceback (most recent call last):\n  File \"C:\\x\\tests\\test_v3_http.py\", line 42, in <module>\n    main()\n"
                "  File \"C:\\x\\lib\\http.py\", line 7, in get\n    return s.recv()\nConnectionResetError: [WinError 10054] An existing connection was closed\n")
        keys = mod.qa_key_lines(text)
        self.assertEqual(keys, ["ConnectionResetError: [WinError 10054] An existing connection was closed  (http.py:7)"])
        self.assertFalse(any(k.startswith("Traceback") for k in mod.qa_key_lines("Traceback (most recent call last):\n  File \"a.py\", line 1\nValueError: x\n")))
        self.assertEqual(mod.qa_key_lines("Traceback (most recent call last):\n"), [])  # traceback ถูกตัดกลางทาง = ไม่มีอะไรให้คัด

    def test_dirty_counts_separate_tracked_changes_from_untracked(self):
        (self.proj / "keep.txt").write_text("a", encoding="utf-8")
        self.init_git()
        mod = self.load_mod("flashq_qa_dirty")
        self.assertEqual(mod.qa_dirty_counts(self.proj), (0, 0))
        (self.proj / "keep.txt").write_text("b", encoding="utf-8")
        big = self.proj / "bigdir"
        big.mkdir()
        for i in range(30):
            (big / f"f{i}.txt").write_text("x", encoding="utf-8")
        (self.proj / ".tmp").mkdir()
        (self.proj / ".tmp" / "t.txt").write_text("x", encoding="utf-8")
        self.assertEqual(mod.qa_dirty_counts(self.proj), (1, 1))  # โฟลเดอร์ใหม่ 30 ไฟล์ = 1 รายการ · .tmp ไม่นับ
        head, _ = mod.qa_summary({"specs": [{"name": "u", "verdict": "PASS", "secs": 1}], "head": "abc", "dirty": 1, "untracked": 1})
        self.assertIn("แก้ไฟล์ที่ติดตามอยู่แล้วแต่ยังไม่ commit 1 ไฟล์", head)
        self.assertIn("ไฟล์/โฟลเดอร์ใหม่ที่ยังไม่ติดตาม 1 รายการ", head)

    def test_env_exit_is_env_verdict_not_pass_and_not_retried_or_analyzed(self):
        """exit code ที่ประกาศว่า "สภาพแวดล้อมไม่พร้อม" = ENV (ไม่ผ่านเหมือนกัน แต่บอกชัดว่าไม่ใช่โค้ดผิด · ไม่ลองซ้ำ · ไม่ให้ Flash เดาสาเหตุ)"""
        env3 = self.py("env3.py", "import sys\nprint('server not ready')\nsys.exit(3)\n")
        env7 = self.py("env7.py", "import sys\nsys.exit(7)\n")
        zero = self.py("zero.py", "print('9 passed')\n")
        self.presets(srv={"cmd": env3, "env_exit": [3, 5], "retry": 2}, other={"cmd": env7, "env_exit": [3]},
                     fine={"cmd": zero, "env_exit": 3, "expect": r"\d+ passed"})
        r = self.run_q("qa", "--no-analyze")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=FAIL", r.stdout)
        self.assertIn("srv=ENV", r.stdout)
        self.assertIn("other=FAIL", r.stdout)  # exit 7 ไม่อยู่ในรายการ env_exit = ล้มจริง
        self.assertIn("สภาพแวดล้อมไม่พร้อม", r.stdout)
        self.assertNotIn("fine=", r.stdout.split("----")[0])  # ชุดที่ผ่านไม่อยู่ในหัวข้อ "ไม่ผ่าน"
        j = self.job_files()[0]
        rows = {s["name"]: s for s in j["qa"]["specs"]}
        self.assertEqual((rows["srv"]["verdict"], rows["srv"]["runs"]), ("ENV", 1))  # retry=2 แต่ไม่ลองซ้ำ
        self.assertEqual(rows["fine"]["verdict"], "PASS")
        self.assertFalse(self.args_out.exists())
        # ค่าผิดรูป = ปฏิเสธก่อนสร้างงาน
        for bad in ([0], ["x"], [True], [1] * 9, {"a": 1}):
            self.presets(t={"cmd": "echo x", "env_exit": bad})
            r = self.run_q("qa", "t", "--no-analyze")
            self.assertEqual(r.returncode, 1, repr(bad) + r.stdout)
            self.assertIn("env_exit", r.stdout)
        # ENV ไม่เรียก analyst แม้ไม่ได้ปิดไว้
        self.presets(srv={"cmd": env3, "env_exit": [3]})
        before = len(self.job_files())
        r = self.run_q("qa", "srv")
        self.assertIn("srv=ENV", r.stdout)
        self.assertEqual(len(self.job_files()), before + 1)
        self.assertFalse(self.args_out.exists())

    def test_log_in_utf16_still_matches_expect(self):
        """PowerShell 5.1 เขียนไฟล์ด้วย `>` เป็น UTF-16 → expect ต้องยังหาเจอ (ไม่ใช่ NOEXPECT ผิด ๆ) · ข้อความไทยอ่านออก"""
        w16 = self.py("w16.py", "import sys\nsys.stdout.buffer.write('ผ่านทั้งหมด 12 passed\\r\\n'.encode('utf-16'))\n")
        self.presets(u16={"cmd": w16, "expect": r"12 passed"}, nothing={"cmd": w16, "expect": r"ไม่มีข้อความนี้"})
        r = self.run_q("qa", "--no-analyze")
        self.assertIn("✅ u16", r.stdout)
        self.assertIn("nothing=NOEXPECT", r.stdout)  # ยังเป็น fail-closed เมื่อไม่พบจริง
        mod = self.load_mod("flashq_qa_u16")
        p = self.tmp / "t16.log"
        for label, raw in [("LE+BOM", "ok ทดสอบ 5 passed\n".encode("utf-16")), ("LE ไม่มี BOM", "ok ทดสอบ 5 passed\n".encode("utf-16-le")),
                           ("BE ไม่มี BOM", "ok ทดสอบ 5 passed\n".encode("utf-16-be")),
                           ("ปน UTF-8 นำหน้า", "[build_lock] start\n".encode("utf-8") + "ok 5 passed\n".encode("utf-16-le"))]:
            p.write_bytes(raw)
            self.assertIn("5 passed", mod.qa_text(p), label)
        p.write_bytes("เริ่ม\n5 passed\n".encode("utf-8"))  # UTF-8 ธรรมดาต้องไม่โดนแตะ
        self.assertEqual(mod.qa_text(p), "เริ่ม\n5 passed\n")
        # อ่านเฉพาะท้ายไฟล์ใหญ่ที่เริ่มกลางตัวอักษร 2 ไบต์ (offset คี่) ก็ยังอ่านออก
        big = ("บรรทัด " + "x" * 50 + "\n").encode("utf-16-le") * 40 + "จบ 8 passed\n".encode("utf-16-le")
        p.write_bytes(big)
        self.assertIn("8 passed", mod.qa_text(p, cap=len(big) // 2 + 1))
        self.assertIn("8 passed", mod.qa_text(p, cap=len(big) // 2))

    def test_retry_makes_flaky_not_pass_and_failfast_skips_rest(self):
        flaky = self.py("flaky.py", "import os, sys\nif os.path.exists('flaky.mark'):\n    print('1 passed')\n    sys.exit(0)\nopen('flaky.mark', 'w').close()\nprint('1 failed')\nsys.exit(1)\n")
        bad = self.py("bad.py", "import sys\nsys.exit(1)\n")
        ok = self.py("ok.py", "print('1 passed')\n")
        self.presets(flaky=flaky, bad=bad, ok=ok)
        r = self.run_q("qa", "flaky", "--retry", "1", "--no-analyze")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("flaky=FLAKY", r.stdout)  # ผ่านเฉพาะรอบหลัง = ไม่นิ่ง ห้ามนับผ่าน
        self.assertIn("QA=FAIL", r.stdout)
        j = self.job_files()[-1]
        self.assertEqual(len(j["logs"]), 2)  # เก็บ log ทั้งสองรอบ
        r = self.run_q("qa", "bad", "ok", "--fail-fast", "--no-analyze")
        self.assertIn("ok=SKIPPED", r.stdout)
        self.assertIn("ข้าม", r.stdout)
        r = self.run_q("qa", "bad", "ok", "--no-analyze")
        self.assertIn("✅ ok", r.stdout)  # ไม่มี fail-fast = รันต่อ

    def test_commit_check_and_head_change_mid_run(self):
        """--commit ต้องตรงกับ HEAD ของ checkout จริง (ไม่สลับให้) · HEAD เปลี่ยนระหว่างทดสอบ = ผลใช้ไม่ได้ ห้ามนับผ่าน"""
        mover = self.py("mover.py", "import subprocess\nsubprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--allow-empty', '-q', '-m', 'x'], check=True)\nprint('1 passed')\n")
        ok = self.py("ok.py", "print('1 passed')\n")
        self.presets(mover=mover, ok=ok)
        self.init_git()
        first = self.git("rev-parse", "HEAD")
        r = self.run_q("qa", "ok", "--commit", "deadbeef", "--no-analyze")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ไม่พบ commit", r.stdout)
        r = self.run_q("qa", "ok", "--commit", first[:10], "--no-analyze")
        self.assertIn("QA=PASS", r.stdout, r.stdout)
        self.assertIn(first[:10], r.stdout)  # บอกว่าทดสอบ commit ไหน
        r = self.run_q("qa", "mover", "ok", "--no-analyze")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("mover=CHANGED", r.stdout)
        self.assertIn("HEAD เปลี่ยน", r.stdout)
        self.assertIn("ok=SKIPPED", r.stdout)  # หยุดทันที ไม่ทดสอบต่อบนโค้ดที่เปลี่ยนไปแล้ว
        self.assertIn("⚠️ ผลใช้ไม่ได้", r.stdout)
        r = self.run_q("qa", "ok", "--commit", first[:10], "--no-analyze")  # HEAD ขยับไปแล้ว
        self.assertEqual(r.returncode, 1)
        self.assertIn("checkout ตอนนี้อยู่ที่", r.stdout)

    def test_analyst_runs_only_on_failure_and_is_advisory(self):
        """Flash อธิบายเฉพาะตอนล้ม · คำอธิบายไม่เปลี่ยนคำตัดสิน · Flash พัง = บันทึกเหตุแต่ผลยังเป็น FAIL · ได้สิทธิ์อ่านโฟลเดอร์ log รอบนั้นอย่างเดียว"""
        ok = self.py("ok.py", "print('1 passed')\n")
        bad = self.py("bad.py", "import sys\nprint('E boom')\nsys.exit(1)\n")
        self.presets(ok=ok, bad=bad)
        r = self.run_q("qa", "ok")
        self.assertIn("QA=PASS", r.stdout)
        self.assertFalse(self.args_out.exists())  # ผ่าน = ไม่เรียกโมเดลเลย
        env_out = self.tmp / "env.json"
        r = self.run_q("qa", "bad", env={"FAKE_TEXT": "สาเหตุ: boom ในเทสต์", "FAKE_ENV_OUT": str(env_out)})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("QA=FAIL", r.stdout)
        self.assertIn("คำอธิบายจากนักทดสอบ", r.stdout)
        self.assertIn("สาเหตุ: boom ในเทสต์", r.stdout)
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--agent") + 1], "flash-tester")
        self.assertIn("--format", argv)
        perm = json.loads(env_out.read_text(encoding="utf-8"))
        self.assertIn("logs", json.dumps(perm).replace("\\\\", "/"))  # เปิดอ่านโฟลเดอร์ log เฉพาะรอบนี้
        j = [x for x in self.job_files() if x["tasks"] == "bad"][-1]
        self.assertEqual((j["status"], j["qa"]["verdict"]), ("fail", "FAIL"))
        r = self.run_q("qa", "bad", env={"FAKE_MODE": "fail"})
        self.assertIn("QA=FAIL", r.stdout)
        self.assertIn("ไม่มีคำอธิบายจาก Flash", r.stdout)

    def test_conflict_rules_keep_code_still_while_testing(self):
        mod = self.load_mod("flashq_qa_conflict")
        P, other = str(self.proj), str(self.tmp / "other")
        qa = {"id": "q", "project": P, "kind": "qa", "readonly": True}
        qa2 = {"id": "q2", "project": P, "kind": "qa", "readonly": True}
        writer = {"id": "w", "project": P, "plan": "A.md", "tasks": "T-01"}
        verify = {"id": "v", "project": P, "kind": "verify", "readonly": True, "plan": "A.md"}
        info = lambda j: self.fail("qa ไม่ควรไปแกะแผน")  # noqa: E731
        self.assertIn("นักทดสอบอีกงาน", mod.conflict_reason(qa, qa2, info))
        self.assertIn("ต้องรอให้จบก่อนถึงจะทดสอบได้", mod.conflict_reason(qa, writer, info))
        self.assertIn("รอให้จบก่อนถึงจะแก้ไฟล์ได้", mod.conflict_reason(writer, qa, info))
        self.assertEqual(mod.conflict_reason(qa, verify, info), "")  # ผู้ตรวจอ่านอย่างเดียว รันคู่ได้
        self.assertEqual(mod.conflict_reason(qa, {**qa2, "project": other}, info), "")  # คนละโปรเจกต์

    def test_ui_submit_picks_preset_names_only(self):
        """หน้าเว็บส่งได้แค่ "ชื่อชุด" — คำสั่งจริงมาจาก .flash.json เท่านั้น (ใส่ cmd มาก็ไม่ถูกใช้) · ชื่อแปลก/ไม่มีในไฟล์ = 400"""
        marker = self.proj / "pwned.txt"
        ok = self.py("ok.py", "print('1 passed')\n")
        self.presets(ok={"cmd": ok, "expect": r"\d+ passed"})
        mod = self.load_mod("flashq_qa_argv")
        base = {"project": str(self.proj), "kind": "qa"}
        argv, err = mod.build_run_argv({**base, "names": ["ok"], "no_analyze": True, "cmd": f"echo x > {marker}"})
        self.assertEqual(err, "")
        self.assertEqual(argv[2:], ["qa", "ok", "--project", str(self.proj), "--no-analyze"])
        self.assertNotIn(str(marker), " ".join(argv))
        for names in (["ok; calc"], ["../x"], ["nope"], "ok", [1], ["ok"] * 13):
            self.assertNotEqual(mod.build_run_argv({**base, "names": names})[1], "", names)
        self.assertEqual(mod.build_run_argv({**base})[1], "")  # ไม่ระบุชื่อ = ทุกชุด
        (self.proj / ".flash.json").write_text("{}", encoding="utf-8")
        self.assertIn("ยังไม่ได้ตั้ง qa.presets", mod.build_run_argv({**base, "names": ["ok"]})[1])
        self.assertEqual(mod.qa_preset_names(str(self.proj)), [])
        self.assertEqual(mod.qa_preset_names(str(self.tmp / "ไม่มี")), [])

    def test_ui_end_to_end_submit_state_and_retry(self):
        ok = self.py("ok.py", "print('2 passed')\n")
        bad = self.py("bad.py", "import sys\nsys.exit(1)\n")
        self.presets(ok={"cmd": ok, "expect": r"\d+ passed"}, bad=bad)
        base = self.start_ui()
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": self.ui_token(base)}
        plans = json.loads(self.http(base + "/api/plans?project=" + urllib.parse.quote(str(self.proj)))[1])
        self.assertEqual(plans["qa_presets"], ["ok", "bad"])
        self.assertEqual(json.loads(self.http(base + "/api/plans?project=relative")[1])["qa_presets"], [])
        code, body = self.http(base + "/api/submit", json.dumps({"project": str(self.proj), "kind": "qa", "names": ["ok"], "no_analyze": True}).encode(), hdr)
        self.assertEqual(code, 200, body)
        jid = json.loads(body)["job"]
        self.wait_job(jid, "ok")
        code, body = self.http(base + "/api/submit", json.dumps({"project": str(self.proj), "kind": "qa", "names": ["ok && calc"]}).encode(), hdr)
        self.assertEqual(code, 400, body)
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertEqual(st["qa_presets"][str(self.proj)] if str(self.proj) in st["qa_presets"] else st["qa_presets"][next(iter(st["qa_presets"]))], ["ok", "bad"])
        row = next(x for x in st["history"] if x["id"] == jid)
        self.assertEqual((row["kind"], row["qa"]["verdict"], row["qa"]["specs"][0]["verdict"]), ("qa", "PASS", "PASS"))
        self.assertTrue(any(x["name"] == "qa" for x in st["stats"]["by_kind"]))
        code, body = self.http(base + "/api/retry", json.dumps({"id": jid}).encode(), hdr)  # สั่งซ้ำ = ชุดเดิม ไม่ใช่ทุกชุด
        self.assertEqual(code, 200, body)
        self.wait_job(json.loads(body)["job"], "ok")
        self.assertEqual(sorted(j["tasks"] for j in self.job_files()), ["ok", "ok"])

    def test_cancel_kills_running_test_command(self):
        """ยกเลิกกลางทาง = คำสั่งทดสอบ (ลูก) ต้องตายด้วย ไม่ทิ้งค้างพอร์ต/ไฟล์"""
        mod = self.load_mod("flashq_qa_cancel")
        slow = self.py("slow.py", "import time\ntime.sleep(300)\n")
        self.presets(slow=slow)
        p = self.run_q("qa", "slow", "--no-analyze", wait=False)
        self.addCleanup(lambda: (p.kill(), p.communicate(timeout=30)))
        j, t0 = {}, time.time()
        while time.time() - t0 < 30:
            fs = list((self.home / "jobs").glob("*.json"))
            j = json.loads(fs[0].read_text(encoding="utf-8")) if fs else {}
            if j.get("child_pid"):
                break
            time.sleep(0.3)
        self.assertTrue(j.get("child_pid"), j)
        self.assertTrue(mod.pid_alive(j["child_pid"]))
        r = self.run_q("cancel", j["id"])
        self.assertEqual(r.returncode, 0, r.stdout)
        t0 = time.time()
        while mod.pid_alive(j["child_pid"]) and time.time() - t0 < 15:
            time.sleep(0.3)
        self.assertFalse(mod.pid_alive(j["child_pid"]))
        self.assertFalse((self.home / "running.lock").exists())

    def test_hook_tags_qa_and_never_suggests_flash_check(self):
        hook = REPO / "hooks" / "inbox_notify.py"
        inbox = self.home / "inbox"
        inbox.mkdir(parents=True)
        row = {"job": "J1", "project": str(self.proj), "session": "s1", "kind": "qa", "plan": "", "tasks": "unit lint", "status": "FAIL",
               "mins": 1.2, "last": "❌ ไม่ผ่าน 1/2 ชุด: lint=FAIL\nรายละเอียด", "at": time.time()}
        (inbox / "a.json").write_text(json.dumps(row), encoding="utf-8")
        r = subprocess.run([sys.executable, str(hook)], input=json.dumps({"session_id": "s1", "cwd": str(self.proj)}), capture_output=True,
                           text=True, encoding="utf-8", env=self.env, timeout=30)
        self.assertIn("[ทดสอบ] unit lint", r.stdout)
        self.assertIn("lint=FAIL", r.stdout)  # หัวข้อผล (ต้นข้อความ) ต้องไม่ถูกตัด
        self.assertNotIn("--message", r.stdout)
        self.assertNotIn("/flash-check", r.stdout)
        self.assertIn("exit code", r.stdout)

    def test_log_viewer_survives_non_dict_json_lines(self):
        mod = self.load_mod("flashq_qa_fmt")
        for line in ("123", "[1, 2]", '"text"', "null", "ข้อความธรรมดา"):
            mod._fmt_event(line)  # ต้องไม่พัง


class DocTest(unittest.TestCase):
    """ช่างเอกสาร ขั้น 1: ตัวตัดสินด้วยกลไก (doc_spec / doc_verdict) · fail-closed · ไม่เรียกโมเดล"""
    tearDown, load_mod = FlashqTest.tearDown, FlashqTest.load_mod
    SPEC = {"name": "docs", "paths": ["docs/**", "README.md"], "brief": "", "timeout_min": 5}

    def setUp(self):
        FlashqTest.setUp(self)
        self.mod = self.load_mod("flashq_doc")
        p = self.proj
        (p / "docs").mkdir()
        (p / "src").mkdir()
        (p / "docs" / "A.md").write_text("# A\nเดิม\n", encoding="utf-8")
        (p / "docs" / "B.md").write_text("# B\n", encoding="utf-8")
        (p / "README.md").write_text("# r\nดู `docs/A.md`\n", encoding="utf-8")
        (p / "src" / "a.py").write_text("x = 1\nprint(x)\n", encoding="utf-8")
        (p / ".gitignore").write_text(".env\n.tmp/\n", encoding="utf-8")
        (p / ".env").write_text("K=1\n", encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "i")

    def git(self, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.proj, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def verdict(self, mutate, spec=None, status="DONE", dirty_before=None):
        """snapshot ก่อน → (dirty_before ทำให้สกปรกก่อน) → mutate แก้ไฟล์ → snapshot หลัง → doc_verdict"""
        m, root = self.mod, self.proj
        if dirty_before:
            dirty_before()
        snap0, g0, head0 = m.dirty_snapshot(root), m.doc_guard(root), self.git("rev-parse", "HEAD")
        texts = m.doc_before(root, snap0)
        mutate()
        head1 = self.git("rev-parse", "HEAD")
        return m.doc_verdict(spec or self.SPEC, {"status": status, "head0": head0, "head1": head1}, root, snap0, m.dirty_snapshot(root), texts, g0, m.doc_guard(root))

    def w(self, rel, text, mode="a"):
        with open(self.proj / rel, mode, encoding="utf-8", newline="") as f:
            f.write(text)

    def test_spec_rejects_broad_escaping_or_forbidden_paths(self):
        m = self.mod
        ok = m.doc_spec("d", {"paths": ["docs/**", ".\\README.md"], "brief": " สรุป ", "timeout_min": "2"}, 30)
        self.assertEqual(ok, {"name": "d", "paths": ["docs/**", "README.md"], "brief": "สรุป", "timeout_min": 2.0})
        self.assertEqual(m.doc_spec("d", ["docs/**"], 30)["paths"], ["docs/**"])  # ย่อ: รายการอย่างเดียว
        for bad in (["**"], ["*"], ["**/*"], ["../x.md"], ["docs/../../x"], ["/etc/x"], ["C:\\x\\a.md"], ["~/a.md"], [".env*"], [".git/**"], [".flash.json"],
                    ["**/*.pem"], [""], [], "docs/**", ["docs/**"] * 33, [5]):
            self.assertIsInstance(m.doc_spec("d", {"paths": bad}, 30), str, bad)
        self.assertIsInstance(m.doc_spec("d", {"paths": ["a.md"], "brief": "x" * 4001}, 30), str)
        self.assertIsInstance(m.doc_spec("d", {"paths": ["a.md"], "timeout_min": "ช้า"}, 30), str)
        self.assertIsInstance(m.doc_spec("d", {"paths": ["a.md"], "timeout_min": 0}, 30), str)
        self.assertIsInstance(m.doc_spec("d", 5, 30), str)

    def test_glob_and_protected(self):
        m, s = self.mod, self.SPEC
        self.assertTrue(all(m.doc_allowed(p, s) for p in ("docs/a.md", "docs/x/y.md", "README.md")))
        self.assertFalse(any(m.doc_allowed(p, s) for p in ("docsx/a.md", "src/a.py", "docs", "x/README.md", "readme.md.bak")))
        star = {"paths": ["**/*.md", "*.txt"]}
        self.assertTrue(all(m.doc_allowed(p, star) for p in ("README.md", "docs/a.md", "a/b/c.md", "n.txt")))
        self.assertFalse(m.doc_allowed("docs/n.txt", star))
        self.assertFalse(any(m.doc_allowed(p, {"paths": ["**/*"]}) for p in (".flash.json", ".env", "a/.env.local", ".git/config", "k/id_rsa", "c.pem")))

    def test_pass_only_when_every_gate_passes(self):
        v, why, ch = self.verdict(lambda: self.w("docs/A.md", "เพิ่ม: ดู `docs/B.md` และ `127.0.0.1:4097` · `.tmp/run.log` · `<id>/x.json`\n"))
        self.assertEqual((v, ch), ("DRAFT", ["docs/A.md"]), why)
        v, why, ch = self.verdict(lambda: None)
        self.assertEqual(v, "NOCHANGE")
        v, why, ch = self.verdict(lambda: self.w("docs/new.md", "ไฟล์ใหม่\n", "w"))  # ไฟล์ใหม่ที่ยังไม่ติดตาม ก็ต้องเห็น
        self.assertEqual((v, ch), ("DRAFT", ["docs/new.md"]), why)

    def test_outside_scope_and_guarded_files(self):
        v, why, ch = self.verdict(lambda: (self.w("docs/A.md", "ok\n"), self.w("src/a.py", "y = 2\n")))
        self.assertEqual(v, "OUTSIDE")
        self.assertIn("src/a.py", why[0])
        v, why, _ = self.verdict(lambda: self.w(".env", "K=2\n"))  # .env ถูก .gitignore → git status ไม่เห็น แต่ต้องจับได้
        self.assertEqual(v, "OUTSIDE", why)
        self.assertIn(".env", why[0])
        v, why, _ = self.verdict(lambda: self.w(".flash.json", "{}\n", "w"))
        self.assertEqual(v, "OUTSIDE", why)
        wide = {"name": "w", "paths": ["**/*"], "brief": "", "timeout_min": 5}  # แม้ paths กว้างผิดพลาด ไฟล์ต้องห้ามก็ผ่านไม่ได้
        v, _, _ = self.verdict(lambda: self.w(".env", "K=3\n"), spec=wide)
        self.assertEqual(v, "OUTSIDE")

    def test_head_change_and_incomplete_runs(self):
        v, why, _ = self.verdict(lambda: (self.w("docs/A.md", "x\n"), self.git("commit", "-q", "-am", "agent commit")))
        self.assertEqual(v, "CHANGED", why)
        self.assertEqual(self.verdict(lambda: self.w("docs/A.md", "x\n"), status="TIMEOUT")[0], "TIMEOUT")
        self.assertEqual(self.verdict(lambda: self.w("docs/A.md", "x\n"), status="HANG")[0], "TIMEOUT")
        self.assertEqual(self.verdict(lambda: self.w("docs/A.md", "x\n"), status="ERROR")[0], "ERROR")
        m = self.mod
        self.assertEqual(m.doc_verdict(self.SPEC, {"status": "DONE", "head0": "a", "head1": "a"}, self.proj, None, {}, {}, {}, {})[0], "ERROR")

    def test_secrets_blocked_but_placeholders_allowed(self):
        for line in ("key = AKIAABCDEFGHIJKLMNOP", "-----BEGIN RSA PRIVATE KEY-----", "ghp_" + "a1B2" * 9,
                     "password: hunter2hunter2", 'api_key = "Zq81xJ3mPw0aKd7R"', "sk-" + "a" * 30):
            v, why, _ = self.verdict(lambda: self.w("docs/A.md", line + "\n"))
            self.assertEqual(v, "SECRET", line)
            self.assertNotIn("hunter2", " ".join(why))  # ไม่พิมพ์ค่าลับซ้ำในรายงาน
            self.git("checkout", "-q", "--", ".")
        for line in ("token: <your-token>", "password = $PASSWORD", "api_key: xxxxxxxxxx", "ตั้งค่า token ผ่านตัวแปร"):
            v, why, _ = self.verdict(lambda: self.w("docs/A.md", line + "\n"))
            self.assertEqual(v, "DRAFT", (line, why))
            self.git("checkout", "-q", "--", ".")

    def test_only_added_lines_are_scanned_against_pre_run_baseline(self):
        """ผู้ใช้แก้ค้างไว้เองก่อนรัน (มีข้อความคล้ายความลับ) ไม่ใช่ความผิดของช่างเอกสาร"""
        dirty = lambda: self.w("docs/A.md", "password: hunter2hunter2\nดู `docs/gone.md`\n")
        v, why, _ = self.verdict(lambda: self.w("docs/A.md", "บรรทัดใหม่ปกติ\n"), dirty_before=dirty)
        self.assertEqual(v, "DRAFT", why)
        v, why, _ = self.verdict(lambda: self.w("docs/A.md", "api_key = Zq81xJ3mPw0aKd7R\n"))
        self.assertEqual(v, "SECRET", why)

    def test_bad_refs_missing_files_and_citations(self):
        v, why, _ = self.verdict(lambda: self.w("docs/A.md", "ดู `docs/nope.md` และ `src/a.py`\n"))
        self.assertEqual(v, "BADREF")
        self.assertIn("docs/nope.md", why[0])
        self.git("checkout", "-q", "--", ".")
        v, why, _ = self.verdict(lambda: self.w("docs/A.md", "ดู src/a.py:99 `x = 1`\n"))  # เลขบรรทัดเกินไฟล์
        self.assertEqual(v, "BADREF", why)
        self.git("checkout", "-q", "--", ".")
        v, why, _ = self.verdict(lambda: self.w("docs/A.md", "ดู src/a.py:1 `x = 1` และ B.md ข้างกัน `B.md` เป็นแค่ชื่อ\n"))
        self.assertEqual(v, "DRAFT", why)
        self.git("checkout", "-q", "--", ".")
        v, why, _ = self.verdict(lambda: (self.w("docs/new.md", "ดู `docs/A.md` และ `docs/new.md`\n", "w")))  # อ้างไฟล์ที่เพิ่งสร้างได้
        self.assertEqual(v, "DRAFT", why)

    def test_delete_and_unchecked_files_fail_closed(self):
        v, why, _ = self.verdict(lambda: (self.proj / "docs" / "B.md").unlink())
        self.assertEqual(v, "DELETED", why)
        self.git("checkout", "-q", "--", ".")
        v, why, _ = self.verdict(lambda: (self.proj / "docs" / "img.bin").write_bytes(b"\x00\x01\x02"))
        self.assertEqual(v, "UNCHECKED", why)
        v, why, _ = self.verdict(lambda: self.w("docs/A.md", "ก" * (1024 * 1024 + 10)))
        self.assertEqual(v, "UNCHECKED", why)

    def test_many_issues_are_capped(self):
        v, why, _ = self.verdict(lambda: self.w("docs/A.md", "".join(f"ดู `docs/n{i}.md`\n" for i in range(20))))
        self.assertEqual(v, "BADREF")
        self.assertLessEqual(len(why), 9)
        self.assertIn("อีก", why[-1])


class DocRunTest(unittest.TestCase):
    """ช่างเอกสาร ขั้น 2: `flashq doc` / `doc-review` ทั้งทาง (opencode ปลอมเขียนไฟล์แทน agent) · ตัดสินด้วยกลไก · ไม่ commit ให้"""
    tearDown, run_q, load_mod = FlashqTest.tearDown, FlashqTest.run_q, FlashqTest.load_mod
    git, w = DocTest.git, DocTest.w

    def setUp(self):
        DocTest.setUp(self)
        self.presets()

    def presets(self, **named):
        named = named or {"docs": {"paths": ["docs/**", "README.md"], "brief": "ภาษาไทย"}}
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False, "doc": {"presets": named}}), encoding="utf-8")
        self.git("add", ".flash.json")
        self.git("commit", "-q", "-m", "cfg")

    def doc(self, write, text="# A\nใหม่\n", *extra, env=None):
        return self.run_q("doc", "docs", *extra, env={"FAKE_WRITE": write, "FAKE_WRITE_TEXT": text, **(env or {})})

    def job(self, which=-1):
        return [json.loads(f.read_text(encoding="utf-8")) for f in sorted((self.home / "jobs").glob("*.json"))][which]

    def read(self, rel):
        return (self.proj / rel).read_text(encoding="utf-8")

    def test_draft_waits_for_user_and_is_never_committed(self):
        head = self.git("rev-parse", "HEAD")
        r = self.doc("docs/A.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("FLASH_RUN=OK", r.stdout)
        self.assertIn("DOC=DRAFT", r.stdout)
        j = self.job()
        self.assertEqual((j["kind"], j["readonly"], j["status"], j["agent"]), ("doc", False, "ok", "flash-writer"))
        self.assertEqual((j["doc"]["verdict"], j["doc"]["state"], j["doc"]["changed"]), ("DRAFT", "pending", ["docs/A.md"]))
        self.assertEqual(self.read("docs/A.md"), "# A\nใหม่\n")
        self.assertEqual(self.git("rev-parse", "HEAD"), head)  # ไม่ commit ให้
        self.assertEqual(self.git("status", "--porcelain"), "M docs/A.md")
        argv = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(argv[argv.index("--agent") + 1], "flash-writer")
        prompt = argv[-1]
        self.assertIn("docs/**", prompt)
        self.assertIn("ภาษาไทย", prompt)
        self.assertIn("ห้าม commit", prompt)
        row = json.loads(sorted((self.home / "inbox").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual((row["kind"], row["status"]), ("doc", "OK"))
        self.assertTrue(row["last"].startswith("📝"))
        r = self.run_q("doc-review", j["id"], "accept")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.job()["doc"]["state"], "accepted")
        self.assertEqual(self.read("docs/A.md"), "# A\nใหม่\n")  # รับ = เก็บไฟล์ไว้
        r = self.run_q("doc-review", j["id"], "discard")
        self.assertEqual(r.returncode, 1)  # ตัดสินไปแล้ว ตัดสินซ้ำไม่ได้

    def test_discard_reverts_only_files_the_writer_touched(self):
        self.w("src/a.py", "y = 2\n")  # งานค้างของผู้ใช้เอง ต้องไม่ถูกแตะ
        self.w("docs/B.md", "ผู้ใช้เพิ่ม\n")  # ไฟล์เอกสารที่ผู้ใช้แก้ค้างไว้ก่อน (ช่างเอกสารไม่ได้แตะ)
        r = self.doc("docs/A.md|docs/new/C.md")
        self.assertIn("DOC=DRAFT", r.stdout, r.stdout)
        j = self.job()
        self.assertEqual(j["doc"]["changed"], ["docs/A.md", "docs/new/C.md"])
        r = self.run_q("doc-review", j["id"], "discard")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.read("docs/A.md"), "# A\nเดิม\n")
        self.assertFalse((self.proj / "docs" / "new").exists())  # ไฟล์ใหม่ถูกลบ + โฟลเดอร์ว่างที่สร้างค้าง
        self.assertEqual(self.read("src/a.py"), "x = 1\nprint(x)\ny = 2\n")
        self.assertEqual(self.read("docs/B.md"), "# B\nผู้ใช้เพิ่ม\n")
        self.assertEqual(self.job()["doc"]["state"], "discarded")

    def test_writer_editing_an_already_dirty_file_is_restored_from_backup(self):
        """ไฟล์ที่ผู้ใช้แก้ค้างอยู่แล้ว ช่างเอกสารเขียนทับ → discard คืนเวอร์ชันของผู้ใช้ (ไม่ใช่ HEAD)"""
        self.w("docs/A.md", "ของผู้ใช้\n")
        r = self.doc("docs/A.md")
        self.assertIn("DOC=DRAFT", r.stdout, r.stdout)
        r = self.run_q("doc-review", self.job()["id"], "discard")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.read("docs/A.md"), "# A\nเดิม\nของผู้ใช้\n")

    def test_outside_scope_is_reverted_immediately(self):
        r = self.doc("docs/A.md|src/a.py", "boom\n")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FLASH_RUN=FAIL", r.stdout)
        self.assertIn("DOC=OUTSIDE", r.stdout)
        j = self.job()
        self.assertEqual((j["doc"]["verdict"], j["doc"]["state"]), ("OUTSIDE", "reverted"))
        self.assertEqual(self.git("status", "--porcelain"), "")  # ย้อนทั้งชุดแล้ว รวมไฟล์ในขอบเขต
        self.assertEqual(self.read("src/a.py"), "x = 1\nprint(x)\n")
        r = self.run_q("doc-review", j["id"], "accept")
        self.assertEqual(r.returncode, 1)

    def test_secret_in_added_text_is_reverted_and_failing_draft_cannot_be_accepted(self):
        r = self.doc("docs/A.md", "token ghp_" + "a1B2c3D4" * 5 + "\n")
        self.assertIn("DOC=SECRET", r.stdout, r.stdout)
        self.assertNotIn("ghp_a1B2", r.stdout)  # ไม่พิมพ์ความลับซ้ำ
        self.assertEqual(self.job()["doc"]["state"], "reverted")
        self.assertEqual(self.read("docs/A.md"), "# A\nเดิม\n")
        r = self.doc("docs/A.md", "# A\nดู `docs/missing.md`\n")  # BADREF: เก็บไฟล์ไว้ให้ดู แต่รับไม่ได้
        self.assertIn("DOC=BADREF", r.stdout, r.stdout)
        j = self.job()
        self.assertEqual(j["doc"]["state"], "pending")
        r = self.run_q("doc-review", j["id"], "accept")
        self.assertEqual(r.returncode, 1)
        self.assertIn("รับไม่ได้", r.stdout)
        r = self.run_q("doc-review", j["id"], "discard")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.read("docs/A.md"), "# A\nเดิม\n")

    def test_nochange_and_agent_failure(self):
        r = self.run_q("doc", "docs", env={"FAKE_TEXT": "ไม่มีอะไรต้องแก้"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("DOC=NOCHANGE", r.stdout)
        r = self.run_q("doc", "docs", env={"FAKE_MODE": "fail", "FAKE_WRITE": "docs/A.md", "FAKE_WRITE_TEXT": "ครึ่งทาง\n"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("DOC=ERROR", r.stdout)
        j = self.job()
        self.assertEqual((j["doc"]["state"], j["doc"]["changed"]), ("pending", ["docs/A.md"]))  # แก้ค้างไว้ → ต้องรายงานและทิ้งได้
        self.assertEqual(self.run_q("doc-review", j["id"], "discard").returncode, 0)
        self.assertEqual(self.read("docs/A.md"), "# A\nเดิม\n")

    def test_discard_refuses_when_head_moved_or_file_edited_after(self):
        self.doc("docs/A.md")
        jid = self.job()["id"]
        self.w("docs/A.md", "ผู้ใช้แก้ต่อ\n")
        r = self.run_q("doc-review", jid, "discard")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--force", r.stdout)
        self.assertIn("ผู้ใช้แก้ต่อ", self.read("docs/A.md"))  # ไม่แตะอะไร
        self.git("commit", "-q", "-am", "ผู้ใช้ commit เอง")
        r = self.run_q("doc-review", jid, "discard", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("HEAD เปลี่ยน", r.stdout)
        self.assertIn("ผู้ใช้แก้ต่อ", self.read("docs/A.md"))

    def test_start_errors_never_create_a_job(self):
        def jobs():
            return list((self.home / "jobs").glob("*.json")) if (self.home / "jobs").exists() else []
        self.presets(a={"paths": ["docs/**"]}, b={"paths": ["README.md"]})
        r = self.run_q("doc")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ต้องระบุชื่อชุด", r.stdout)
        r = self.run_q("doc", "ไม่มี")
        self.assertIn("ไม่มีชุดเอกสารชื่อ", r.stdout)
        self.presets(a={"paths": ["**"]})
        r = self.run_q("doc", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("กว้างเกินไป", r.stdout)
        self.presets(a={"paths": ["docs/**"]})
        r = self.run_q("doc", "a", "--since", "ไม่ใช่commit")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--since", r.stdout)
        (self.proj / ".flash.json").write_text(json.dumps({"require_plan_in_remote": False}), encoding="utf-8")
        r = self.run_q("doc")
        self.assertIn("ยังไม่ได้ตั้งชุดเอกสาร", r.stdout)
        self.assertEqual(jobs(), [])
        plain = self.tmp / "plain"
        plain.mkdir()
        r = self.run_q("doc", "--project", str(plain))
        self.assertEqual(r.returncode, 1)
        self.assertIn("โปรเจกต์ git", r.stdout)

    def test_since_defaults_to_last_accepted_head_and_is_in_prompt(self):
        first = self.git("rev-parse", "HEAD")
        self.doc("docs/A.md")
        self.run_q("doc-review", self.job()["id"], "accept")
        self.git("commit", "-q", "-am", "ผู้ใช้ commit ร่างที่รับ")
        self.args_out.unlink()
        self.doc("docs/A.md", "# A\nรอบสอง\n")
        prompt = json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])[-1]
        self.assertIn(f"{first}..HEAD", prompt)  # เทียบตั้งแต่ HEAD ตอนรับร่างครั้งก่อน
        self.args_out.unlink()
        self.run_q("doc", "docs", "--since", "HEAD~1")
        prev = self.git("rev-parse", "HEAD~1")
        self.assertIn(f"{prev}..HEAD", json.loads(self.args_out.read_text(encoding="utf-8").splitlines()[0])[-1])

    def test_queue_never_runs_doc_alongside_other_writers(self):
        m = self.load_mod("flashq_doc_q")
        proj = str(self.proj)
        doc = {"project": proj, "kind": "doc", "readonly": False}
        work = {"project": proj, "kind": "work", "readonly": False}
        ro = {"project": proj, "kind": "verify", "readonly": True}
        qa = {"project": proj, "kind": "qa", "readonly": True}
        info = lambda j: {"parallel": True, "files": []}
        self.assertTrue(m.conflict_reason(doc, work, info))
        self.assertTrue(m.conflict_reason(work, doc, info))
        self.assertTrue(m.conflict_reason(doc, doc, info))
        self.assertTrue(m.conflict_reason(doc, qa, info))
        self.assertTrue(m.conflict_reason(qa, doc, info))
        self.assertEqual(m.conflict_reason(doc, ro, info), "")  # ผู้ตรวจอ่านอย่างเดียว รันคู่ได้
        self.assertEqual(m.conflict_reason(doc, {**work, "project": proj + "x"}, info), "")  # คนละโปรเจกต์

    def test_cancel_records_half_written_files_so_they_can_be_discarded(self):
        p = self.run_q("doc", "docs", env={"FAKE_WRITE": "docs/A.md", "FAKE_WRITE_TEXT": "ครึ่งทาง\n", "FAKE_SLEEP": "60"}, wait=False)
        try:
            for _ in range(100):
                time.sleep(0.2)
                fs = list((self.home / "jobs").glob("*.json")) if (self.home / "jobs").exists() else []
                if fs and (json.loads(fs[0].read_text(encoding="utf-8")).get("doc") or {}).get("phase") == "write" and self.read("docs/A.md") == "ครึ่งทาง\n":
                    break
            else:
                self.fail("ช่างเอกสารไม่เริ่มเขียน")
            jid = self.job()["id"]
            r = self.run_q("cancel", jid)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("แก้ค้างไว้ 1 ไฟล์", r.stdout)
        finally:
            p.kill()
            p.wait(timeout=30)
        j = self.job()
        self.assertEqual((j["status"], j["doc"]["verdict"], j["doc"]["state"], j["doc"]["changed"]), ("cancelled", "CANCELLED", "pending", ["docs/A.md"]))
        row = json.loads(sorted((self.home / "inbox").glob("*.json"))[-1].read_text(encoding="utf-8"))
        self.assertEqual(row["status"], "CANCELLED")
        r = self.run_q("doc-review", jid, "discard")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.read("docs/A.md"), "# A\nเดิม\n")


class DocUiTest(unittest.TestCase):
    """ช่างเอกสาร ขั้น 3: หน้าเว็บ — เลือกได้แค่ชื่อชุด · ดู diff · รับ/ทิ้ง (token + ยืนยัน + force) · ส่งงานผ่านคิวจริงด้วย opencode ปลอม"""
    tearDown, run_q, load_mod = FlashqTest.tearDown, FlashqTest.run_q, FlashqTest.load_mod
    start_ui, http, ui_token, wait_job = FlashqTest.start_ui, FlashqTest.http, FlashqTest.ui_token, FlashqTest.wait_job
    git, w, presets, job, read = DocTest.git, DocTest.w, DocRunTest.presets, DocRunTest.job, DocRunTest.read

    def setUp(self):
        DocTest.setUp(self)
        self.presets()
        with socket.socket() as s:  # server opencode ที่ไม่มีใคร listen — กันไปแตะ 4096 ของจริง
            s.bind(("127.0.0.1", 0))
            self.env["FLASHQ_LIVE_URL"] = f"http://127.0.0.1:{s.getsockname()[1]}"
        self.env.update(FAKE_WRITE="docs/A.md", FAKE_WRITE_TEXT="# A\nใหม่\n")

    def post(self, base, path, body, token=None):
        hdr = {"Content-Type": "application/json", "X-Flashq-Token": token}
        code, text = self.http(base + path, json.dumps(body).encode(), hdr)
        return code, json.loads(text)

    def test_argv_takes_only_a_preset_name(self):
        mod = self.load_mod("flashq_doc_argv")
        marker = self.proj / "pwned.txt"
        base = {"project": str(self.proj), "kind": "doc"}
        argv, err = mod.build_run_argv({**base, "names": ["docs"], "cmd": f"echo x > {marker}", "paths": ["**"]})
        self.assertEqual(err, "")
        self.assertEqual(argv[2:], ["doc", "docs", "--project", str(self.proj)])
        for names in (["docs; calc"], ["../x"], ["nope"], "docs", [1], [], ["docs", "docs"]):
            self.assertNotEqual(mod.build_run_argv({**base, "names": names})[1], "", names)
        self.assertEqual(mod.doc_preset_names(str(self.proj)), ["docs"])
        self.assertEqual(mod.doc_preset_names(str(self.tmp / "ไม่มี")), [])

    def test_ui_submit_diff_discard_force_and_accept(self):
        base = self.start_ui()
        token = self.ui_token(base)
        plans = json.loads(self.http(base + "/api/plans?project=" + urllib.parse.quote(str(self.proj)))[1])
        self.assertEqual(plans["doc_presets"], ["docs"])
        self.assertEqual(json.loads(self.http(base + "/api/plans?project=relative")[1])["doc_presets"], [])
        body = {"project": str(self.proj), "kind": "doc", "names": ["docs"]}
        self.assertEqual(self.post(base, "/api/submit", body, token="x")[0], 403)
        self.assertEqual(self.post(base, "/api/submit", {**body, "names": ["docs && calc"]}, token)[0], 400)
        code, d = self.post(base, "/api/submit", body, token)
        self.assertEqual(code, 200, d)
        jid = d["job"]
        self.wait_job(jid, "ok")
        st = json.loads(self.http(base + "/api/state")[1])
        self.assertIn(["docs"], st["doc_presets"].values())
        row = next(x for x in st["history"] if x["id"] == jid)
        self.assertEqual((row["kind"], row["doc"]["verdict"], row["doc"]["state"], row["doc"]["changed"]), ("doc", "DRAFT", "pending", ["docs/A.md"]))
        self.assertNotIn("backup", row["doc"])
        self.assertTrue(any(x["name"] == "doc" for x in st["stats"]["by_kind"]))
        # ดู diff
        self.assertEqual(self.http(base + "/api/doc_diff?id=nope")[0], 404)
        dd = json.loads(self.http(base + "/api/doc_diff?id=" + jid)[1])
        self.assertEqual(dd["files"], ["docs/A.md"])
        self.assertIn("+ใหม่", dd["diff"])
        # ทิ้ง: ต้องมี token · ต้องยืนยัน id · ไฟล์ที่ถูกแก้ต่อต้อง force
        self.assertEqual(self.post(base, "/api/doc_review", {"id": jid, "action": "discard", "confirm": jid}, token="x")[0], 403)
        self.assertEqual(self.post(base, "/api/doc_review", {"id": jid, "action": "discard"}, token)[0], 400)
        self.assertEqual(self.post(base, "/api/doc_review", {"id": jid, "action": "bogus"}, token)[0], 400)
        self.assertEqual(self.post(base, "/api/doc_review", {"id": "ไม่มี", "action": "accept"}, token)[0], 404)
        self.assertEqual(self.read("docs/A.md"), "# A\nใหม่\n")
        self.w("docs/A.md", "ผู้ใช้แก้ต่อ\n")
        code, d = self.post(base, "/api/doc_review", {"id": jid, "action": "discard", "confirm": jid}, token)
        self.assertEqual(code, 409)
        self.assertIn("--force", d["message"])
        self.assertIn("ผู้ใช้แก้ต่อ", self.read("docs/A.md"))  # ถูกปฏิเสธ = ไฟล์ยังอยู่
        self.assertEqual(self.post(base, "/api/doc_review", {"id": jid, "action": "discard", "confirm": jid, "force": "true"}, token)[0], 409)  # force ต้องเป็น true จริง
        code, d = self.post(base, "/api/doc_review", {"id": jid, "action": "discard", "confirm": jid, "force": True}, token)
        self.assertEqual(code, 200, d)
        self.assertEqual(self.read("docs/A.md"), "# A\nเดิม\n")
        self.assertEqual(self.job()["doc"]["state"], "discarded")
        # สั่งซ้ำ = ชุดเดิม · รับร่าง
        code, d = self.post(base, "/api/retry", {"id": jid}, token)
        self.assertEqual(code, 200, d)
        jid2 = d["job"]
        self.wait_job(jid2, "ok")
        self.assertEqual(self.job()["doc"]["name"], "docs")
        code, d = self.post(base, "/api/doc_review", {"id": jid2, "action": "accept"}, token)
        self.assertEqual(code, 200, d)
        self.assertEqual(self.job()["doc"]["state"], "accepted")
        self.assertEqual(self.read("docs/A.md"), "# A\nใหม่\n")
        self.assertEqual(self.post(base, "/api/doc_review", {"id": jid2, "action": "discard", "confirm": jid2}, token)[0], 409)  # ตัดสินแล้ว ซ้ำไม่ได้

    def test_accept_refused_unless_draft(self):
        self.env.update(FAKE_WRITE="src/a.py", FAKE_WRITE_TEXT="y = 1\n")  # แตะนอกขอบเขต → OUTSIDE (ย้อนให้ทันที)
        base = self.start_ui()
        token = self.ui_token(base)
        code, d = self.post(base, "/api/submit", {"project": str(self.proj), "kind": "doc", "names": ["docs"]}, token)
        self.assertEqual(code, 200, d)
        self.wait_job(d["job"], "fail")
        j = self.job()
        self.assertEqual((j["doc"]["verdict"], j["doc"]["state"]), ("OUTSIDE", "reverted"))
        self.assertEqual(self.read("src/a.py"), "x = 1\nprint(x)\n")
        code, d2 = self.post(base, "/api/doc_review", {"id": j["id"], "action": "accept"}, token)
        self.assertEqual(code, 409, d2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

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
                    "FLASHQ_OPENCODE_CONFIG": str(self.oc_cfg), "FAKE_ARGS_OUT": str(self.args_out)}

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

    def test_missing_plan(self):
        r = self.run_q("run", "NOPE.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ไม่พบไฟล์แผน", r.stdout)

    def test_big_plan_warn_and_reject(self):
        """แผนใหญ่ = คนวางแผนเขียนโค้ดแทน Flash: เกินเพดานอ่อน = เตือนแต่ส่ง · เกินเพดานแข็ง = ปฏิเสธ (เว้นแต่ --big-plan) · นับ fence ~~~~ ด้วย"""
        code = lambda n, f="```": f + "python\n" + "x = 1\n" * n + f + "\n"
        (self.proj / "BIG.md").write_text("# แผน\n" + code(450, "~~~~"), encoding="utf-8")
        r = self.run_q("run", "BIG.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 1)
        self.assertIn("แผนใหญ่เกิน", r.stdout)
        self.assertIn("โค้ดใน ``` 450 บรรทัด", r.stdout)
        r = self.run_q("run", "BIG.md", "T-01", "--attach", "none", "--no-open", "--big-plan")
        self.assertNotIn("แผนใหญ่เกิน", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout)
        (self.proj / "MID.md").write_text("# แผน\n" + code(250), encoding="utf-8")
        r = self.run_q("run", "MID.md", "T-01", "--attach", "none", "--no-open")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("WARN: แผนใหญ่", r.stdout)
        r = self.run_q("run", "PLAN.md", "T-01", "--attach", "none", "--no-open")
        self.assertNotIn("แผนใหญ่", r.stdout)

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
        r = self.run_q("install", "--force", env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("flashq:managed", (claude / "commands" / "flash-check.md").read_text(encoding="utf-8"))
        self.assertTrue(list((claude / "commands").glob("flash-check.md.bak-flashq-*")))

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
        p1 = self.run_q("run", "PLAN.md", "T-01", "--attach", "none", "--no-open", env={"FAKE_SLEEP": "12"}, wait=False)
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

    def load_mod(self, name):
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, FLASHQ)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
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
        self.assertIn("DENIED: 1 คำสั่ง", r.stdout)
        self.assertIn("find . -name x", r.stdout)

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
        J = lambda plan, proj=P: {"id": plan, "project": proj, "plan": plan, "tasks": "T-01"}
        c = lambda a, b: flashq.conflict_reason(J(a), J(b), flashq.job_info)
        self.assertEqual(c("A.md", "B.md"), "")  # Client กับ MapEditor ไม่ชน
        self.assertIn("Client/UI/*.h", c("A.md", "C.md"))  # glob ครอบไฟล์
        self.assertIn("แผนสั่งให้รอ", c("D.md", "B.md"))
        self.assertIn("flashq-parallel", c("B.md", "D.md"))
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


class NewProjectTest(unittest.TestCase):
    """โปรเจกต์ใหม่ที่ branch หลักไม่ใช่ master: ตรวจอัตโนมัติ + flashq init"""
    setUp, tearDown, run_q, base = (FlashqTest.setUp, FlashqTest.tearDown, FlashqTest.run_q, FlashqTest.base)

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

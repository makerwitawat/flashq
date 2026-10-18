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
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

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

    def test_switch_cli(self):
        r = self.run_q("switch", "cc2")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("commandcode2", r.stdout)
        r = self.run_q("switch", "go2")
        self.assertEqual(r.returncode, 3)  # ไม่มี provider


if __name__ == "__main__":
    unittest.main(verbosity=2)

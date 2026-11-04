"""opencode ปลอมสำหรับเทสต์ flashq — พิมพ์ event JSON แบบ `opencode run --format json`

พฤติกรรมตามตัวแปรแวดล้อม:
  FAKE_SLEEP=<วินาที>   หน่วงก่อนจบ (ค่าเริ่มต้น 0)
  FAKE_MODE=ok|quota|nostart|fail|denied|epipe (denied = opencode ปฏิเสธสิทธิ์เองแล้วจบ exit 0 · ใส่ FAKE_TEXT ที่มี DONE = สำเร็จบางส่วน · epipe = รายงานข้อความแล้วตายด้วย EPIPE exit 1)
  FAKE_ARGS_OUT=<path>  เขียน argv ลงไฟล์ (ต่อท้าย)
  FAKE_ENV_OUT=<path>   เขียนค่า OPENCODE_CONFIG_CONTENT ที่ได้รับลงไฟล์ (ว่าง = ไม่ได้รับ)
  FAKE_MODELS=a/b|c/d    รายชื่อที่ `opencode models` ตอบ (คั่นด้วย |)
  FAKE_SET_MODEL=<model> (คู่ FAKE_MODE=quota) เขียนโมเดลนี้ลง FLASHQ_OPENCODE_CONFIG ก่อนตอบ quota
  FAKE_COMMIT=<ข้อความ>  commit ทุกไฟล์ใน --dir ด้วยข้อความนี้ (จำลอง worker ที่ commit งานเอง · ต้องมี --dir)
"""
import json
import os
import subprocess
import sys
import time

if len(sys.argv) > 1 and sys.argv[1] == "models":  # `opencode models` — รายชื่อ provider/model ของเครื่อง (FAKE_MODELS คั่นด้วย | · ไม่บันทึก argv)
    print(os.environ.get("FAKE_MODELS", "opencode/deepseek-v4.1-flash|opencode-go/deepseek-v4.1-flash|opencode-go/glm-5.3").replace("|", "\n"))
    sys.exit(0)

if os.environ.get("FAKE_ARGS_OUT"):
    with open(os.environ["FAKE_ARGS_OUT"], "a", encoding="utf-8") as f:
        f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\n")
if os.environ.get("FAKE_ENV_OUT"):
    with open(os.environ["FAKE_ENV_OUT"], "w", encoding="utf-8") as f:
        f.write(os.environ.get("OPENCODE_CONFIG_CONTENT", ""))
mode = os.environ.get("FAKE_MODE", "ok")
if os.environ.get("FAKE_WRITE") and "--dir" in sys.argv:  # จำลอง agent ที่แก้ไฟล์ในโปรเจกต์ (หลายไฟล์คั่นด้วย | · เนื้อหา = FAKE_WRITE_TEXT)
    for _name in os.environ["FAKE_WRITE"].split("|"):
        _path = os.path.join(sys.argv[sys.argv.index("--dir") + 1], _name)
        os.makedirs(os.path.dirname(_path), exist_ok=True)
        with open(_path, "w", encoding="utf-8") as _f:
            _f.write(os.environ.get("FAKE_WRITE_TEXT", "x"))
if os.environ.get("FAKE_COMMIT") and "--dir" in sys.argv:  # จำลอง worker ที่ commit งานในโปรเจกต์ (ข้อความ = FAKE_COMMIT)
    _cwd = sys.argv[sys.argv.index("--dir") + 1]
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], cwd=_cwd, check=False)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", os.environ["FAKE_COMMIT"]], cwd=_cwd, check=False)
if mode == "nostart":
    time.sleep(600)
    sys.exit(0)
sid = f"ses_fake{os.getpid()}"
print(json.dumps({"type": "step_start", "sessionID": sid}, separators=(",", ":")), flush=True)  # compact เหมือน opencode จริง (wait_session จับด้วย regex)
if os.environ.get("FAKE_DENIED"):  # จำลอง tool ที่ถูกสิทธิ์ agent บล็อก
    print(json.dumps({"type": "tool_use", "sessionID": sid, "part": {"type": "tool", "tool": "bash", "state": {"status": "error", "input": {"command": "find . -name x"}, "error": "The user has specified a rule which prevents you from using this specific tool call."}}}), flush=True)
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
if mode == "quota":
    if os.environ.get("FAKE_SET_MODEL"):  # จำลองงานอื่นที่รันคู่ขนานสลับบัญชีไปก่อน
        cfg_path = os.environ["FLASHQ_OPENCODE_CONFIG"]
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["agent"]["flash-worker"]["model"] = os.environ["FAKE_SET_MODEL"]
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    print(json.dumps({"type": "error", "sessionID": sid, "error": {"message": "429 rate limit"}}), flush=True)
    sys.exit(1)
if mode in ("failbalance", "failquota"):  # สรุปท้ายของ worker พูดถึง balance ในเนื้องาน (ไม่ใช่ error โควตา) / รายงาน FAIL: quota เอง
    txt = "ปรับสมดุล balance ของเกมแล้ว สถานะ: FAIL" if mode == "failbalance" else "FAIL: quota"
    print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": txt}}), flush=True)
    sys.exit(1)
if mode == "agentmissing":  # agent ไม่อยู่ในรายชื่อ (เช่น live server จำรายชื่อเก่า)
    print("agent \"x\" not found. Falling back to default agent", file=sys.stderr, flush=True)
if mode == "subagent":  # opencode เตือนทาง stderr แล้วตกไปรัน agent เริ่มต้น (ยังจบด้วย exit 0)
    print("agent \"x\" is a subagent, not a primary agent. Falling back to default agent", file=sys.stderr, flush=True)
if mode == "epipe":  # รายงานข้อความแล้วสตรีมตายด้วย EPIPE (exit 1) — FAKE_ERR_EXTRA = บรรทัด stderr อื่นที่ปนมา
    print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": os.environ.get("FAKE_TEXT", "DONE — เสร็จ")}}), flush=True)
    if os.environ.get("FAKE_STEP_REASON"):  # จำลอง step_finish ท้ายรอบ (stop = โมเดลตอบจบ · tool-calls = ยังไม่จบ) ก่อนสตรีมตาย
        print(json.dumps({"type": "step_finish", "sessionID": sid, "part": {"reason": os.environ["FAKE_STEP_REASON"]}}), flush=True)
    print("error: EPIPE: broken pipe, write", file=sys.stderr, flush=True)
    print("      at emitError (node:events:50:13)", file=sys.stderr, flush=True)
    if os.environ.get("FAKE_ERR_EXTRA"):
        print(os.environ["FAKE_ERR_EXTRA"], file=sys.stderr, flush=True)
    sys.exit(1)
if mode == "fail":
    print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": "สถานะ: FAIL"}}), flush=True)
    sys.exit(1)
if mode == "denied":  # เหตุจริง 2026-10-20: กฎ external_directory เป็น ask → โหมดไม่โต้ตอบปฏิเสธเอง (stderr) · subagent ล้มเป็น tool error · จบ exit 0
    print("\x1b[93m\x1b[1m! \x1b[0mpermission requested: external_directory (D:\\outside\\lib\\*); auto-rejecting", file=sys.stderr, flush=True)
    print(json.dumps({"type": "tool_use", "sessionID": sid, "part": {"type": "tool", "tool": "task", "state": {
        "status": "error", "input": {"description": "T-01 x", "subagent_type": "flash-worker", "prompt": "ได้ DONE → ติ๊ก"},
        "error": "Subagent failed (task_id: ses_x): The user rejected permission to use this specific tool call."}}}), flush=True)
    print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": os.environ.get("FAKE_TEXT", "ส่งงานให้ flash-worker ไม่ได้ — ผู้ใช้ปฏิเสธสิทธิ์การใช้ tool call นี้")}}), flush=True)
    sys.exit(0)
for _seg in os.environ.get("FAKE_TEXT_PARTS", "").split("||"):  # ข้อความหลายส่วนมาก่อน (คั่นด้วย ||) แล้วปิดท้ายด้วย FAKE_TEXT
    if _seg:
        print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": _seg}}), flush=True)
print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": os.environ.get("FAKE_TEXT", "PONG")}}), flush=True)

"""opencode ปลอมสำหรับเทสต์ flashq — พิมพ์ event JSON แบบ `opencode run --format json`

พฤติกรรมตามตัวแปรแวดล้อม:
  FAKE_SLEEP=<วินาที>   หน่วงก่อนจบ (ค่าเริ่มต้น 0)
  FAKE_MODE=ok|quota|nostart|fail
  FAKE_ARGS_OUT=<path>  เขียน argv ลงไฟล์ (ต่อท้าย)
  FAKE_SET_MODEL=<model> (คู่ FAKE_MODE=quota) เขียนโมเดลนี้ลง FLASHQ_OPENCODE_CONFIG ก่อนตอบ quota
"""
import json
import os
import sys
import time

if os.environ.get("FAKE_ARGS_OUT"):
    with open(os.environ["FAKE_ARGS_OUT"], "a", encoding="utf-8") as f:
        f.write(json.dumps(sys.argv[1:], ensure_ascii=False) + "\n")
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "nostart":
    time.sleep(600)
    sys.exit(0)
sid = f"ses_fake{os.getpid()}"
print(json.dumps({"type": "step_start", "sessionID": sid}), flush=True)
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
if mode == "fail":
    print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": "สถานะ: FAIL"}}), flush=True)
    sys.exit(1)
print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": os.environ.get("FAKE_TEXT", "PONG")}}), flush=True)

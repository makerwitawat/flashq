"""opencode ปลอมสำหรับเทสต์ flashq — พิมพ์ event JSON แบบ `opencode run --format json`

พฤติกรรมตามตัวแปรแวดล้อม:
  FAKE_SLEEP=<วินาที>   หน่วงก่อนจบ (ค่าเริ่มต้น 0)
  FAKE_MODE=ok|quota|nostart|fail
  FAKE_ARGS_OUT=<path>  เขียน argv ลงไฟล์ (ต่อท้าย)
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
    print(json.dumps({"type": "error", "sessionID": sid, "error": {"message": "429 rate limit"}}), flush=True)
    sys.exit(1)
if mode == "fail":
    print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": "สถานะ: FAIL"}}), flush=True)
    sys.exit(1)
print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": "PONG"}}), flush=True)

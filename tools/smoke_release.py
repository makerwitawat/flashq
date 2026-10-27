"""ทดสอบ smoke ของชุดแจกที่ build แล้ว — รันตัว exe/binary จริงในโฟลเดอร์ชุดแจก (ใช้ใน GitHub Actions ทุก OS)

ใช้: python tools/smoke_release.py <โฟลเดอร์ flashq ที่ build แล้ว>
ตรวจ: (1) flashq --help (2) install ลง HOME ชั่วคราว แล้ว install --check ต้องได้ INSTALL=OK (3) ui เปิดเซิร์ฟเวอร์แล้วตอบหน้าเว็บได้
ทุกอย่างทำใน HOME/FLASHQ_HOME ชั่วคราว ไม่แตะข้อมูลจริงของเครื่อง
"""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PORT = 4199


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    folder = Path(sys.argv[1]).resolve()
    exe = folder / ("flashq.exe" if sys.platform == "win32" else "flashq")
    tmp = Path(tempfile.mkdtemp(prefix="flashq-smoke-"))
    env = dict(os.environ, HOME=str(tmp), USERPROFILE=str(tmp), FLASHQ_HOME=str(tmp / ".flashq"), PYTHONIOENCODING="utf-8")
    ok = True

    def run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run([str(exe), *args], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  — {detail[:300]}" if detail and not passed else ""))

    r = run("--help")
    check("flashq --help", r.returncode == 0 and "usage" in r.stdout.lower(), r.stdout + r.stderr)

    r = run("install")
    check("flashq install (HOME ชั่วคราว)", r.returncode == 0, r.stdout + r.stderr)
    r = run("install", "--check")
    check("flashq install --check = INSTALL=OK", "INSTALL=OK" in r.stdout, r.stdout + r.stderr)

    srv = subprocess.Popen([str(exe), "ui", "--no-open", "--port", str(PORT)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        body, err = "", ""
        for _ in range(40):
            time.sleep(0.5)
            if srv.poll() is not None:
                err = (srv.stdout.read() or b"").decode("utf-8", "replace")
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=3) as resp:
                    body = resp.read().decode("utf-8", "replace")
                break
            except OSError as e:
                err = str(e)
        check("flashq ui ตอบหน้าเว็บ", "<html" in body.lower(), err or body[:200])
    finally:
        srv.kill()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

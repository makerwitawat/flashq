"""ทดสอบหน้าเว็บ flashq แบบเงียบ: Chrome headless (Playwright) กับ server แยกพอร์ต 4197 + FLASHQ_HOME ชั่วคราว

- ไม่มีหน้าต่าง ไม่ขยับเมาส์/คีย์บอร์ดจริง (Playwright สั่งผ่าน CDP) · ไม่แตะข้อมูลจริงใน ~/.flashq และไม่ใช้พอร์ต 4097
- ต้องมี: pip install playwright  (+ playwright install chromium-headless-shell ถ้ายังไม่มีเบราว์เซอร์)
- รัน: python tests/ui_smoke.py  → ผ่านเมื่อ exit 0 และพิมพ์ UI_SMOKE OK · ไม่มี playwright = exit 3 (สภาพแวดล้อมไม่พร้อม ไม่ใช่โค้ดผิด)
- ตั้งไว้ใน .flash.json: {"qa": {"presets": {"ui": {"cmd": "python tests/ui_smoke.py", "expect": "UI_SMOKE OK", "env_exit": 3}}}}
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("FLASHQ_SMOKE_PORT") or 4197)
ENV_EXIT = 3
WIDTHS = (1280, 700, 390)  # กว้าง · กลาง · มือถือ — ต้องไม่มี JS error และไม่มีแถบเลื่อนแนวนอนของทั้งหน้า


def fail(msg: str, code: int = 1) -> None:
    print(f"UI_SMOKE FAIL: {msg}", flush=True)
    sys.exit(code)


def wait_port(proc: subprocess.Popen, timeout: float = 30) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            fail(f"server จบก่อนพร้อม (exit {proc.returncode})", ENV_EXIT)
        try:
            socket.create_connection(("127.0.0.1", PORT), timeout=1).close()
            return
        except OSError:
            time.sleep(0.3)
    fail(f"server ไม่ขึ้นที่พอร์ต {PORT} ใน {timeout:g} วิ", ENV_EXIT)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright, Error as PwError
    except ImportError:
        print("UI_SMOKE ENV: ยังไม่ได้ติดตั้ง playwright → pip install playwright", flush=True)
        return ENV_EXIT
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=1).close()
        print(f"UI_SMOKE ENV: พอร์ต {PORT} ถูกใช้อยู่แล้ว (ตั้ง FLASHQ_SMOKE_PORT เป็นพอร์ตอื่น)", flush=True)
        return ENV_EXIT
    except OSError:
        pass

    tmp = Path(tempfile.mkdtemp(prefix="fh_smoke_", dir=str((REPO / ".tmp").resolve() if (REPO / ".tmp").is_dir() else tempfile.gettempdir())))
    real = Path(os.environ.get("FLASHQ_HOME") or (Path.home() / ".flashq"))
    for name in ("jobs", "goals", "logs", "reviews", "config.json"):  # สำเนาอ่านอย่างเดียวให้หน้าเว็บมีข้อมูลจริงให้วาด
        src = real / name
        try:
            if src.is_dir():
                shutil.copytree(src, tmp / name, dirs_exist_ok=True)
            elif src.is_file():
                shutil.copy2(src, tmp / name)
        except OSError:
            pass
    env = {**os.environ, "FLASHQ_HOME": str(tmp), "PYTHONIOENCODING": "utf-8"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    srv = subprocess.Popen([sys.executable, str(REPO / "flashq.py"), "ui", "--no-open", "--port", str(PORT)], cwd=str(REPO), env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=flags)
    errors: list[str] = []
    try:
        wait_port(srv)
        url = f"http://127.0.0.1:{PORT}/"
        for i in range(10):  # อุ่นเครื่อง: หน้าแรกต้องตอบ 200 ติดกัน 3 ครั้งก่อนปล่อยเบราว์เซอร์เข้า (กัน reset ช่วงเพิ่งขึ้น)
            ok = 0
            for path in ("api/state", "", ""):
                try:
                    ok += urllib.request.urlopen(url + path, timeout=10).status == 200
                except OSError:
                    break
            if ok == 3:
                break
            time.sleep(1)
        else:
            fail("server ตอบไม่นิ่ง (อุ่นเครื่อง 10 รอบไม่ผ่าน)", ENV_EXIT)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                try:
                    for w in WIDTHS:
                        for attempt in range(5):  # server UI ตอบหน้าแรกไม่ทัน/หลุดเป็นครั้งคราว (ราว 3-8% ที่วัดได้ · ERR_CONNECTION_RESET หรือค้างเกิน 10 วิ) → ลองใหม่สูงสุด 5 รอบ
                            page = browser.new_page(viewport={"width": w, "height": 900})
                            page.on("pageerror", lambda e, w=w: errors.append(f"[{w}px] JS error: {e}"))
                            page.on("console", lambda m, w=w: m.type == "error" and "ERR_CONNECTION" not in m.text and errors.append(f"[{w}px] console.error: {m.text}"))
                            try:
                                page.goto(url, wait_until="load", timeout=10000)
                                break
                            except PwError as e:
                                page.close()
                                if attempt == 4 or not ("ERR_CONNECTION" in str(e) or "Timeout" in str(e)):
                                    raise
                                time.sleep(1)
                        if "flashq" not in page.title():
                            errors.append(f"[{w}px] ชื่อหน้าไม่ใช่ flashq: {page.title()!r}")
                        if not page.locator("h1").first.is_visible():
                            errors.append(f"[{w}px] ไม่เห็น h1")
                        page.wait_for_selector("#officeView", state="attached", timeout=15000)
                        over = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                        if over > 2:
                            errors.append(f"[{w}px] หน้าล้นแนวนอน {over}px")
                        if w == WIDTHS[0] and os.environ.get("FLASHQ_SMOKE_SHOT"):
                            page.screenshot(path=os.environ["FLASHQ_SMOKE_SHOT"], full_page=True)
                        page.close()
                finally:
                    browser.close()
        except PwError as e:
            if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                print("UI_SMOKE ENV: ไม่มีเบราว์เซอร์ → playwright install chromium-headless-shell", flush=True)
                return ENV_EXIT
            raise
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    if errors:
        for e in errors:
            print(" -", e)
        fail(f"{len(errors)} ข้อ")
    print(f"UI_SMOKE OK ({len(WIDTHS)} ความกว้าง: {', '.join(map(str, WIDTHS))}px)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

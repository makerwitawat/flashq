"""build ชุดแจก flashq ข้าม OS (Windows / macOS / Linux) ด้วย PyInstaller แล้วบีบเป็นไฟล์เดียวพร้อมแนบ release

ใช้: python tools/build_release.py <tag> [--out <โฟลเดอร์>]
ได้: <out>/flashq-<tag>-<win|macos|linux>.<zip|tar.gz>  (Windows = zip · อื่น ๆ = tar.gz เก็บสิทธิ์ execute)
GitHub Actions เรียกสคริปต์นี้ในแต่ละ OS (.github/workflows/release.yml) · Windows ในเครื่องใช้ tools/build_exe.ps1 ก็ได้เหมือนเดิม
"""
import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIN = sys.platform == "win32"
OS_NAME = "win" if WIN else "macos" if sys.platform == "darwin" else "linux"
SIDE_DIRS = ("claude", "opencode", "hooks", "templates")
SIDE_FILES = ("accounts.json", "oc_desktop_open.mjs", "README.md", "CHANGELOG.md")


def build_one(name: str, windowed: bool, dist: Path, work: Path) -> None:
    sep = ";" if WIN else ":"
    ico = ROOT / "assets" / "flashq.ico"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", name,
           "--distpath", str(dist), "--workpath", str(work / f"build-{name}"), "--specpath", str(work),
           "--hidden-import", "webview", "--add-data", f"{ico}{sep}.",
           "--add-data", f"{ROOT / 'ui.html'}{sep}.", "--add-data", f"{ROOT / 'accounts.json'}{sep}."]
    if WIN:
        cmd += ["--icon", str(ico)]
        if windowed:
            cmd.append("--windowed")  # macOS/Linux ไม่ใช้ --windowed: onefile + .app ใช้ไม่ได้ จึงเปิดหน้าต่างจาก terminal/ไฟล์ตรง ๆ
    cmd.append(str(ROOT / "flashq.py"))
    subprocess.run(cmd, check=True, cwd=ROOT)


def pack(folder: Path, archive: Path) -> None:
    top = "flashq"
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:  # zipfile ใส่ชื่อไฟล์ไทยเป็น UTF-8 ให้เอง
            for p in sorted(folder.rglob("*")):
                if p.is_file():
                    z.write(p, Path(top) / p.relative_to(folder))
    else:
        with tarfile.open(archive, "w:gz") as t:
            t.add(folder, arcname=top)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--out", default=str(ROOT / ".tmp" / "release"))
    a = ap.parse_args()
    out = Path(a.out).resolve()
    work = ROOT / ".tmp" / "pyi"
    folder = out / "flashq"
    for p in (folder, work):
        shutil.rmtree(p, ignore_errors=True)
    folder.mkdir(parents=True)
    build_one("flashq-gui", True, folder, work)  # ชื่อลงท้าย gui = ดับเบิลคลิกแล้วเปิดหน้าต่างแอป
    build_one("flashq", False, folder, work)     # console: คำสั่งและ hook ที่ติดตั้งเรียกตัวนี้
    for d in SIDE_DIRS:
        shutil.copytree(ROOT / d, folder / d, ignore=shutil.ignore_patterns("__pycache__"))
    for f in SIDE_FILES:
        shutil.copy2(ROOT / f, folder / f)
    shutil.copy2(ROOT / "tools" / "dist_readme.txt", folder / "อ่านก่อน.txt")
    shutil.copy2(ROOT / "docs" / "INSTALL_EXE.md", folder / "คู่มือติดตั้ง.md")
    archive = out / f"flashq-{a.tag}-{OS_NAME}.{'zip' if WIN else 'tar.gz'}"
    pack(folder, archive)
    print(f"เสร็จ: {archive} ({archive.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    os.chdir(ROOT)
    main()

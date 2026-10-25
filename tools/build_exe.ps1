# build flashq เป็น exe ไฟล์เดียวแบบหน้าต่างแอป (ดับเบิลคลิก = เปิด GUI)
# ใช้: powershell -File tools\build_exe.ps1 [-Engine pyinstaller|nuitka]
#  pyinstaller = เร็ว ไม่ต้องมี C compiler แต่แกะโค้ดคืนง่าย · nuitka = compile เป็น native แกะยากกว่า (ต้องมี C compiler/MinGW)
# ไม่ใช้ UPX: ได้ขนาดเล็กลงนิดเดียว (onefile บีบอยู่แล้ว) แต่เปิดช้าลงและ Defender ฟ้องผิดบ่อยขึ้น · ถอด upx -d ได้ในคำสั่งเดียว จึงไม่ช่วยกันแกะ
param([ValidateSet("pyinstaller", "nuitka")][string]$Engine = "pyinstaller", [string]$Icon = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$out = Join-Path $root ".tmp\dist"
$ico = Join-Path $root "assets\flashq.ico"
if (-not $Icon) { $Icon = $ico }
$data = @("ui.html", "accounts.json")
if ($Engine -eq "pyinstaller") {
    $pa = @("-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--name", "flashq-gui",
            "--distpath", $out, "--workpath", ".tmp\build", "--specpath", ".tmp", "--hidden-import", "webview",
            "--icon", $Icon, "--add-data", "$ico;.")
    foreach ($d in $data) { $pa += @("--add-data", "$root\$d;.") }
    python @pa flashq.py
} else {
    $pa = @("-m", "nuitka", "--onefile", "--windows-console-mode=disable", "--enable-plugin=pywebview",
            "--output-dir=$out", "--output-filename=flashq-gui.exe", "--assume-yes-for-downloads",
            "--windows-icon-from-ico=$Icon", "--include-data-files=$ico=flashq.ico")
    foreach ($d in $data) { $pa += "--include-data-files=$root\$d=$d" }
    python @pa flashq.py
}
if ($LASTEXITCODE -ne 0) { throw "build ไม่สำเร็จ (exit $LASTEXITCODE)" }
# ไฟล์ที่วางข้าง exe (accounts.json แก้ได้โดยไม่ต้อง build ใหม่ — ใช้ก่อนของที่แนบในตัว)
foreach ($f in @("accounts.json", "README.md", "CHANGELOG.md")) { Copy-Item (Join-Path $root $f) $out -Force }
Write-Host "เสร็จ: $out\flashq-gui.exe"

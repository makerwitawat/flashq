# build flashq เป็นชุดแจก dist\: flashq-gui.exe (หน้าต่างแอป ดับเบิลคลิก) + flashq.exe (console สำหรับคำสั่ง/hook) + ไฟล์ข้าง exe
# ใช้: powershell -File tools\build_exe.ps1 [-Engine pyinstaller|nuitka]
#  pyinstaller = เร็ว ไม่ต้องมี C compiler แต่แกะโค้ดคืนง่าย · nuitka = compile เป็น native แกะยากกว่า (ต้องมี C compiler/MinGW)
# ไม่ใช้ UPX: ได้ขนาดเล็กลงนิดเดียว (onefile บีบอยู่แล้ว) แต่เปิดช้าลงและ Defender ฟ้องผิดบ่อยขึ้น · ถอด upx -d ได้ในคำสั่งเดียว จึงไม่ช่วยกันแกะ
param([ValidateSet("pyinstaller", "nuitka")][string]$Engine = "pyinstaller", [string]$Icon = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$out = Join-Path $root "dist"
$ico = Join-Path $root "assets\flashq.ico"
if (-not $Icon) { $Icon = $ico }
$data = @("ui.html", "accounts.json")

function Build-One([string]$name, [bool]$windowed) {
    if ($Engine -eq "pyinstaller") {
        $pa = @("-m", "PyInstaller", "--noconfirm", "--onefile", "--name", $name,
                "--distpath", $out, "--workpath", ".tmp\build-$name", "--specpath", ".tmp", "--hidden-import", "webview",
                "--icon", $Icon, "--add-data", "$ico;.")
        if ($windowed) { $pa += "--windowed" }
        foreach ($d in $data) { $pa += @("--add-data", "$root\$d;.") }
    } else {
        $mode = if ($windowed) { "disable" } else { "force" }
        $pa = @("-m", "nuitka", "--onefile", "--windows-console-mode=$mode", "--enable-plugin=pywebview",
                "--output-dir=$out", "--output-filename=$name.exe", "--assume-yes-for-downloads",
                "--windows-icon-from-ico=$Icon", "--include-data-files=$ico=flashq.ico")
        foreach ($d in $data) { $pa += "--include-data-files=$root\$d=$d" }
    }
    python @pa flashq.py
    if ($LASTEXITCODE -ne 0) { throw "build $name ไม่สำเร็จ (exit $LASTEXITCODE)" }
}

Build-One "flashq-gui" $true   # ชื่อลงท้าย gui = ดับเบิลคลิกแล้วเปิดหน้าต่างแอป
Build-One "flashq" $false      # console: flashq.exe install / run / log ... (คำสั่งและ hook ที่ติดตั้งเรียกตัวนี้)

# ไฟล์ข้าง exe: ต้นฉบับที่ `flashq.exe install` / `init` คัดลอกไปใช้ (เปลี่ยนโดยไม่ต้อง build ใหม่ได้ · accounts.json ใช้ก่อนของที่ฝังในตัว)
foreach ($d in @("claude", "opencode", "hooks", "templates")) {
    $dst = Join-Path $out $d
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Copy-Item (Join-Path $root $d) $dst -Recurse -Force
}
Get-ChildItem (Join-Path $out "hooks") -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
foreach ($f in @("accounts.json", "oc_desktop_open.mjs", "README.md", "CHANGELOG.md")) { Copy-Item (Join-Path $root $f) $out -Force }
Copy-Item (Join-Path $root "tools\dist_readme.txt") (Join-Path $out "อ่านก่อน.txt") -Force
Copy-Item (Join-Path $root "docs\INSTALL_EXE.md") (Join-Path $out "คู่มือติดตั้ง.md") -Force
Write-Host "เสร็จ: $out"

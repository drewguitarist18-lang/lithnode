# Builds dist\LithnodeSetup.exe:
#   1. the engine and Claude Pet (Python, bundled with PyInstaller)  -> dist\Lithnode
#   2. the app window, Lithnode.exe (Electron, installer\app)        -> dist\Lithnode-win32-x64
#   3. the installer (Inno Setup, installer\setup.iss)                -> dist\LithnodeSetup.exe
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
# One-time: py -m venv installer\.venv-build; installer\.venv-build\Scripts\pip install pyinstaller
#           winget install JRSoftware.InnoSetup;  Node.js (for Electron)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = Split-Path $here
$dist = Join-Path $root "dist"
$py = Join-Path $here ".venv-build\Scripts\python.exe"
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not (Test-Path $py)) { throw "Missing build environment: see the one-time steps at the top of this file." }
if (-not $iscc) { throw "Inno Setup isn't installed: winget install JRSoftware.InnoSetup" }

& $py (Join-Path $here "make_icon.py")

# 1. the engine
& $py -m PyInstaller --noconfirm --clean --log-level WARN --distpath $dist --workpath (Join-Path $root "build") (Join-Path $here "lithnode.spec")
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# 2. the app window, English only to keep the download small
$appDir = Join-Path $here "app"
Copy-Item (Join-Path $here "lithnode.ico") (Join-Path $appDir "lithnode.ico") -Force
Push-Location $appDir
try {
    if (-not (Test-Path node_modules)) { npm ci --no-fund --no-audit; if ($LASTEXITCODE) { throw "npm ci failed" } }
    npx --no-install electron-packager . Lithnode --platform=win32 --arch=x64 "--out=$dist" --overwrite --asar `
        --icon=lithnode.ico --app-copyright=Lithnode --win32metadata.ProductName=Lithnode --win32metadata.FileDescription=Lithnode `
        "--ignore=^/node_modules" "--ignore=^/package-lock.json"
    if ($LASTEXITCODE) { throw "Electron packaging failed" }
} finally { Pop-Location }
Get-ChildItem (Join-Path $dist "Lithnode-win32-x64\locales") -Filter *.pak | Where-Object { $_.Name -ne "en-US.pak" } |
    ForEach-Object { [IO.File]::Delete($_.FullName) }
# Lithnode's UI needs no WebGPU shader compilers or software 3D (SwiftShader); dropping them keeps the
# installer under the site's 100 MB per-file limit
foreach ($n in "dxcompiler.dll", "dxil.dll", "vk_swiftshader.dll", "vk_swiftshader_icd.json") {
    $f = Join-Path $dist "Lithnode-win32-x64\$n"; if (Test-Path $f) { [IO.File]::Delete($f) }
}

# 3. the installer
& $iscc /Q (Join-Path $here "setup.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-Item (Join-Path $dist "LithnodeSetup.exe") | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }

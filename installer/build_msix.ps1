# Builds dist\Lithnode.msix for the Microsoft Store from what build.ps1 already built
# (dist\Lithnode-win32-x64 = the window, dist\Lithnode = the engine). The Store signs it, so Store installs
# don't get the "Windows protected your PC" warning.
#
#   powershell -ExecutionPolicy Bypass -File installer\build_msix.ps1
#
# The package identity must match the Store listing (Partner Center > Product identity). Set these once known:
#   LITHNODE_MSIX_NAME        e.g. 12345Lithnode.Lithnode
#   LITHNODE_MSIX_PUBLISHER   e.g. CN=1A2B3C4D-...
#   LITHNODE_MSIX_PUBLISHER_NAME   your publisher display name
# Without them it builds a local test package (identity Lithnode.Lithnode, publisher CN=Lithnode).
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$root = Split-Path $here
$dist = Join-Path $root "dist"

$version = [regex]::Match((Get-Content (Join-Path $root "version.py") -Raw), 'VERSION = "([^"]+)"').Groups[1].Value
if (-not $version) { throw "No VERSION in version.py" }
$msixVersion = "$version.0"   # the Store wants four parts, the last one 0

$name = if ($env:LITHNODE_MSIX_NAME) { $env:LITHNODE_MSIX_NAME } else { "Lithnode.Lithnode" }
$publisher = if ($env:LITHNODE_MSIX_PUBLISHER) { $env:LITHNODE_MSIX_PUBLISHER } else { "CN=Lithnode" }
$publisherName = if ($env:LITHNODE_MSIX_PUBLISHER_NAME) { $env:LITHNODE_MSIX_PUBLISHER_NAME } else { "Lithnode" }

$window = Join-Path $dist "Lithnode-win32-x64"
$engine = Join-Path $dist "Lithnode"
foreach ($p in $window, $engine) { if (-not (Test-Path $p)) { throw "$p is missing: run installer\build.ps1 first" } }

$makeappx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter makeappx.exe -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $makeappx) { throw "makeappx.exe not found: install the Windows SDK" }

# the package's files: the window at the top, the engine and Claude Pet in server\ (same layout as LithnodeSetup.exe)
$stage = Join-Path $dist "msix"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory $stage | Out-Null
Copy-Item "$window\*" $stage -Recurse
Copy-Item $engine (Join-Path $stage "server") -Recurse

# tile and taskbar icons: the pixel crab from make_icon.py, on the app's dark plate
$assets = Join-Path $stage "Assets"
New-Item -ItemType Directory $assets | Out-Null
python -c @"
import sys
sys.path.insert(0, sys.argv[1])
from make_icon import Canvas, icon_png
out = sys.argv[2]
def tile(w, h, frac, name):
    c = Canvas(w, h, (20, 20, 20), 255)
    cell = max(1, round(min(w, h) * frac / 16))
    c.logo((w - 16 * cell) // 2, (h - 13 * cell) // 2, cell)
    open(out + '/' + name, 'wb').write(c.png())
open(out + '/StoreLogo.png', 'wb').write(icon_png(50))
open(out + '/Square44x44Logo.png', 'wb').write(icon_png(44))
tile(150, 150, 0.6, 'Square150x150Logo.png')
tile(310, 150, 0.45, 'Wide310x150Logo.png')
"@ $here $assets
if ($LASTEXITCODE) { throw "making the icons failed" }

@"
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:uap3="http://schemas.microsoft.com/appx/manifest/uap/windows10/3"
         xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap uap3 desktop rescap">
  <Identity Name="$name" Publisher="$publisher" Version="$msixVersion" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>Lithnode</DisplayName>
    <PublisherDisplayName>$publisherName</PublisherDisplayName>
    <Logo>Assets\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources><Resource Language="en-us" /></Resources>
  <Applications>
    <Application Id="Lithnode" Executable="Lithnode.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="Lithnode" Description="Draw teams of Claude Code agents and run them"
                          BackgroundColor="transparent" Square150x150Logo="Assets\Square150x150Logo.png"
                          Square44x44Logo="Assets\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\Wide310x150Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <!-- lithnode-cli on PATH for every program, so Claude Code's hooks can reach Claude Pet inside the package -->
        <uap3:Extension Category="windows.appExecutionAlias" Executable="server\lithnode-cli.exe" EntryPoint="Windows.FullTrustApplication">
          <uap3:AppExecutionAlias><desktop:ExecutionAlias Alias="lithnode-cli.exe" /></uap3:AppExecutionAlias>
        </uap3:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <Capability Name="internetClient" />
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"@ | Set-Content (Join-Path $stage "AppxManifest.xml") -Encoding UTF8

$out = Join-Path $dist "Lithnode.msix"
& $makeappx.FullName pack /o /d $stage /p $out | Select-Object -Last 2
if ($LASTEXITCODE) { throw "makeappx failed" }
Get-Item $out | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }

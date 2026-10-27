<#
.SYNOPSIS
  Installs (copies) or uninstalls the claude_bridge CSP Lua app into <AC>\apps\lua\claude_bridge.
.DESCRIPTION
  The Assetto Corsa folder is taken from -AcRoot, else the AC_ROOT environment variable, else detected from Steam
  (registry SteamPath + steamapps\libraryfolders.vdf).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install_lua_app.ps1
  powershell -ExecutionPolicy Bypass -File scripts\install_lua_app.ps1 -Uninstall
#>
param(
  [string]$AcRoot = $env:AC_ROOT,
  [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'

function Find-AcRoot {
  $steams = @()
  foreach ($k in @(@('HKCU:\Software\Valve\Steam', 'SteamPath'), @('HKLM:\SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'), @('HKLM:\SOFTWARE\Valve\Steam', 'InstallPath'))) {
    try { $v = (Get-ItemProperty -Path $k[0] -Name $k[1] -ErrorAction Stop).($k[1]); if ($v) { $steams += $v } } catch {}
  }
  foreach ($s in $steams) {
    $libs = @($s)
    $vdf = Join-Path $s 'steamapps\libraryfolders.vdf'
    if (Test-Path $vdf) {
      $libs += (Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' -AllMatches).Matches | ForEach-Object { $_.Groups[1].Value -replace '\\', '\' }
    }
    foreach ($l in $libs) {
      $c = Join-Path $l 'steamapps\common\assettocorsa'
      if (Test-Path (Join-Path $c 'acs.exe')) { return $c }
    }
  }
  return $null
}

if (-not $AcRoot) { $AcRoot = Find-AcRoot }
if (-not $AcRoot -or -not (Test-Path (Join-Path $AcRoot 'acs.exe'))) { throw "Assetto Corsa not found. Pass -AcRoot or set AC_ROOT." }
$src = Join-Path $PSScriptRoot '..\lua\claude_bridge'
$dst = Join-Path $AcRoot 'apps\lua\claude_bridge'
if ($Uninstall) {
  if (Test-Path $dst) { Remove-Item -Recurse -Force $dst; Write-Output "Removed $dst" } else { Write-Output "Not installed: $dst" }
  $chan = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Assetto Corsa\claude_bridge'
  Write-Output "Channel folder (delete by hand if no longer wanted): $chan"
  exit 0
}
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item -Force (Join-Path $src '*') $dst
Get-ChildItem $dst | ForEach-Object { Write-Output "Installed $($_.FullName)" }

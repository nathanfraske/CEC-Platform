# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# route.ps1 -- Windows launcher for the automated router (scripts/cec_router.py).
#
# Solves the #1 Windows gotcha: on Windows the `pcbnew` module is ONLY importable from
# KiCad's OWN bundled python.exe (not a system/Microsoft-Store python). This script finds
# KiCad's python, puts KiCad's bin on PATH (so kicad-cli resolves), and runs the router
# with it. No xvfb is needed on Windows -- Java uses the native Win32 display (run this in
# an interactive desktop session; see docs/self-hosted-router.md).
#
# Usage:
#   .\scripts\route.ps1 -Board eps-8pin -Seeds 0,1,2,3 -Passes 12 -OptTime 30 -Render
#   (override the interpreter with $env:KICAD_PYTHON if KiCad is in a nonstandard place)
[CmdletBinding()]
param(
  [string]$Board    = "eps-8pin",
  [string]$Seeds    = "0,1,2,3",
  [int]   $Passes   = 10,
  [int]   $OptTime  = 20,
  [int]   $Threads  = 1,
  [int]   $Kmax       = 2,
  [int]   $MaxIters   = 4,
  [int]   $MaxWorkers = 0,
  [int]   $OptSpread  = 0,
  [string]$Out        = "build/route",
  [switch]$Render
)
# Continue, NOT Stop: native tools (java, python, Freerouting) legitimately write to stderr,
# and under "Stop" Windows PowerShell turns ANY native-command stderr into a terminating
# NativeCommandError (this killed an earlier run on `java -version`). Real failures are caught
# explicitly via `throw` + $LASTEXITCODE checks below.
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot     # scripts\ -> repo root

function Find-KiCadPython {
  # 1) explicit override
  if ($env:KICAD_PYTHON -and (Test-Path $env:KICAD_PYTHON)) { return $env:KICAD_PYTHON }
  # 2) kicad-cli already on PATH -> python.exe sits in the same bin
  $kc = Get-Command kicad-cli -ErrorAction SilentlyContinue
  if ($kc) { $p = Join-Path (Split-Path -Parent $kc.Source) "python.exe"; if (Test-Path $p) { return $p } }
  # 3) registry: KiCad's uninstall InstallLocation (finds it on ANY drive / custom path)
  $ukeys = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
             "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
             "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")
  foreach ($k in $ukeys) {
    foreach ($app in (Get-ItemProperty $k -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "KiCad*" })) {
      if ($app.InstallLocation) {
        $p = Join-Path $app.InstallLocation "bin\python.exe"
        if (Test-Path $p) { return $p }
      }
    }
  }
  # 4) KiCad roots on EVERY fixed drive (Program Files\KiCad\<ver>\bin or <drive>\KiCad\<ver>\bin), newest first
  $roots = @("${env:ProgramFiles(x86)}\KiCad")
  foreach ($drv in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue).Root) {
    $roots += (Join-Path $drv "Program Files\KiCad"); $roots += (Join-Path $drv "KiCad")
  }
  foreach ($root in ($roots | Select-Object -Unique)) {
    if (Test-Path $root) {
      foreach ($d in (Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending)) {
        $p = Join-Path $d.FullName "bin\python.exe"; if (Test-Path $p) { return $p }
      }
      $p = Join-Path $root "bin\python.exe"; if (Test-Path $p) { return $p }   # no version subdir
    }
  }
  # 5) a 'python' already on PATH that can import pcbnew
  $onpath = (Get-Command python -ErrorAction SilentlyContinue)
  if ($onpath) { & $onpath.Source -c "import pcbnew" 2>$null; if ($LASTEXITCODE -eq 0) { return $onpath.Source } }
  return $null
}

$py = Find-KiCadPython
if (-not $py) {
  throw "Could not find a python with the KiCad 'pcbnew' module. Install KiCad 10, or set " +
        "`$env:KICAD_PYTHON to KiCad's python.exe (e.g. 'C:\Program Files\KiCad\10.0\bin\python.exe')."
}
Write-Host "Using KiCad python: $py"

# Put KiCad's bin on PATH so kicad-cli.exe resolves for the router's DRC/render subprocesses.
$kibin = Split-Path -Parent $py
$env:PATH = "$kibin;$env:PATH"

# Ensure `java` resolves WITHOUT the user configuring PATH: if it isn't already on PATH,
# discover a JRE in the usual install roots (Adoptium/Temurin, Oracle, Microsoft, Zulu)
# and prepend its bin. cec_fr invokes plain `java`, so it just needs to be on PATH here.
function Ensure-Java {
  if (Get-Command java -ErrorAction SilentlyContinue) { return }
  if ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME "bin\java.exe"))) {
    $env:PATH = "$(Join-Path $env:JAVA_HOME 'bin');$env:PATH"; return
  }
  $roots = @("$env:ProgramFiles\Eclipse Adoptium", "$env:ProgramFiles\Java",
             "$env:ProgramFiles\Microsoft\jdk*", "$env:ProgramFiles\Zulu",
             "${env:ProgramFiles(x86)}\Java")
  foreach ($r in $roots) {
    foreach ($j in (Get-ChildItem -Path $r -Recurse -Filter java.exe -ErrorAction SilentlyContinue |
                    Sort-Object FullName -Descending)) {
      $env:PATH = "$(Split-Path -Parent $j.FullName);$env:PATH"; return
    }
  }
}
Ensure-Java

# Sanity: pcbnew must import with this interpreter, and java must now resolve.
& $py -c "import pcbnew; print('pcbnew', pcbnew.GetBuildVersion())"
if ($LASTEXITCODE -ne 0) { throw "pcbnew failed to import with $py" }
if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
  throw "java not found. Install a JRE 21 (e.g. Adoptium Temurin) -- or set `$env:JAVA_HOME."
}
# capture java's banner via cmd so its stderr never becomes a PowerShell error record
$jv = (cmd /c "java -version 2>&1") | Select-Object -First 1
Write-Host "java: $jv"

$cliArgs = @(
  (Join-Path $repo "scripts\cec_router.py"),
  "--board", $Board, "--seeds", $Seeds,
  "--passes", $Passes, "--opt-time", $OptTime, "--threads", $Threads,
  "--kmax", $Kmax, "--max-iters", $MaxIters, "--max-workers", $MaxWorkers,
  "--opt-spread", $OptSpread, "--out", $Out
)
if ($Render) { $cliArgs += "--render" }

& $py @cliArgs
exit $LASTEXITCODE

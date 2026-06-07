# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# synth.ps1 -- Windows launcher for the synthesis pipeline (scripts/cec_synth_pipeline.py).
#
# Same Windows plumbing as route.ps1 (the `pcbnew` module is ONLY importable from KiCad's own
# bundled python.exe; kicad-cli must be on PATH; java is needed only when --route runs the swarm).
# Mirrors route.ps1's discovery verbatim so this needs NO manual PATH config. Run in an interactive
# desktop session (no xvfb on Windows). See docs/self-hosted-router.md.
#
# Usage:
#   .\scripts\synth.ps1 -Mode run   -Board eps-8pin -RoutedBoard build\route\eps-8pin\eps-8pin-routed.kicad_pcb
#   .\scripts\synth.ps1 -Mode run   -Board eps-8pin -Route          # route the board first, then run the pipeline
#   .\scripts\synth.ps1 -Mode sweep -Board eps-8pin -Sizes auto -Seeds 0,1,2,3 -MaxWorkers 0
[CmdletBinding()]
param(
  [ValidateSet("run", "sweep")][string]$Mode = "run",
  [string]$Board       = "eps-8pin",
  [switch]$Route,                                   # run mode: route via the swarm before physics/cascade
  [string]$RoutedBoard = "",                        # run mode: a routed .kicad_pcb to run on
  [string]$Sizes       = "auto",                    # sweep mode: 'auto' or 'WxH,WxH'
  [string]$Seeds       = "0,1,2,3",
  [string]$Strategies  = "dataflow,thermal_separated,compact",
  [int]   $MaxWorkers  = 0,
  [string]$Out         = ""
)
# Continue, NOT Stop: native tools legitimately write to stderr; under Stop, Windows PowerShell
# turns any native-command stderr into a terminating error. Real failures are caught via $LASTEXITCODE.
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot

function Find-KiCadPython {
  if ($env:KICAD_PYTHON -and (Test-Path $env:KICAD_PYTHON)) { return $env:KICAD_PYTHON }
  $kc = Get-Command kicad-cli -ErrorAction SilentlyContinue
  if ($kc) { $p = Join-Path (Split-Path -Parent $kc.Source) "python.exe"; if (Test-Path $p) { return $p } }
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
  $roots = @("${env:ProgramFiles(x86)}\KiCad")
  foreach ($drv in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue).Root) {
    $roots += (Join-Path $drv "Program Files\KiCad"); $roots += (Join-Path $drv "KiCad")
  }
  foreach ($root in ($roots | Select-Object -Unique)) {
    if (Test-Path $root) {
      foreach ($d in (Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending)) {
        $p = Join-Path $d.FullName "bin\python.exe"; if (Test-Path $p) { return $p }
      }
      $p = Join-Path $root "bin\python.exe"; if (Test-Path $p) { return $p }
    }
  }
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
$kibin = Split-Path -Parent $py
$env:PATH = "$kibin;$env:PATH"

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
if ($Route -or $Mode -eq "sweep") { Ensure-Java }   # java only needed when the swarm/feasibility routes

& $py -c "import pcbnew; print('pcbnew', pcbnew.GetBuildVersion())"
if ($LASTEXITCODE -ne 0) { throw "pcbnew failed to import with $py" }

$script = Join-Path $repo "scripts\cec_synth_pipeline.py"
if ($Mode -eq "sweep") {
  $cliArgs = @($script, "--board", $Board, "--sweep", $Sizes, "--seeds", $Seeds,
               "--strategies", $Strategies, "--max-workers", $MaxWorkers)
  if (-not $Out) { $Out = "build/synth/$Board" }
} else {
  $cliArgs = @($script, "--board", $Board, "--run")
  if ($RoutedBoard) { $cliArgs += @("--routed-board", $RoutedBoard) }
  if ($Route)       { $cliArgs += "--route" }
  if (-not $Out) { $Out = "build/release/$Board" }
}
$cliArgs += @("--out", $Out)

& $py @cliArgs
exit $LASTEXITCODE

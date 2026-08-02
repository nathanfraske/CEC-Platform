# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# dispatch.ps1 -- Windows launcher for the AGENTIC compute tools (scripts/cec_dispatch.py).
#
# The agentic route-to-clean loop calls cec_dispatch as its compute-as-tools surface
# (request-candidates = Freerouting batch + cec_score + DRC types). That compute needs:
#   * KiCad's bundled python.exe   -- `pcbnew` imports ONLY from it
#   * kicad-cli on PATH            -- cec_dispatch shells out to it for the DRC verdict
#   * java on PATH                 -- Freerouting is a JVM jar
#   * the Freerouting jar          -- $CEC_FREEROUTING_JAR or the ~/.cache/cec copy
# This wrapper assembles all four exactly like synth.ps1/route.ps1 so the caller needs NO
# manual PATH config. Everything after the script name is passed straight to cec_dispatch.py.
#
# Usage:
#   .\scripts\dispatch.ps1 request-candidates --board eps-8pin --seeds 0,1 --passes 8 --opt-time 12 --out build\dispatch\eps-8pin
$ErrorActionPreference = "Continue"   # native tools write to stderr legitimately; gate on $LASTEXITCODE

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

$py = Find-KiCadPython
if (-not $py) {
  throw "Could not find a python with the KiCad 'pcbnew' module. Install KiCad 10 or set " +
        "`$env:KICAD_PYTHON to KiCad's python.exe."
}
$env:PATH = "$(Split-Path -Parent $py);$env:PATH"   # kicad-cli sits beside python.exe
Ensure-Java

if (-not $env:CEC_FREEROUTING_JAR) {
  foreach ($c in @((Join-Path $env:USERPROFILE ".cache\cec\freerouting-1.7.0-cec2.jar"),
                   (Join-Path $env:TEMP "fr_1.7.0-cec2.jar"))) {
    if (Test-Path $c) { $env:CEC_FREEROUTING_JAR = $c; break }
  }
}

& $py (Join-Path $PSScriptRoot "cec_dispatch.py") @args
exit $LASTEXITCODE

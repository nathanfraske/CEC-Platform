# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# route-prereqs.ps1 -- Windows prerequisite check for the automated router.
# Mirrors route-prereqs.sh but Windows-appropriate: NO xvfb (Java uses the native Win32
# display), and pcbnew is checked via KiCad's bundled python (route.ps1 finds it).
# Fails fast with an install hint per missing piece. See docs/self-hosted-router.md.
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$fail = $false
function Note($name, $msg) { "{0,-22} {1}" -f $name, $msg | Write-Host }
function Bad($name, $msg)  { Write-Host ("MISSING  {0,-13} {1}" -f $name, $msg) -ForegroundColor Red; $script:fail = $true }

Write-Host "== route prerequisites on $env:COMPUTERNAME (Windows) =="

# --- KiCad python + pcbnew ---
function Find-KiCadPython {
  if ($env:KICAD_PYTHON -and (Test-Path $env:KICAD_PYTHON)) { return $env:KICAD_PYTHON }
  $kc = Get-Command kicad-cli -EA SilentlyContinue
  if ($kc) { $p = Join-Path (Split-Path -Parent $kc.Source) "python.exe"; if (Test-Path $p) { return $p } }
  $ukeys = @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
             "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
             "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*")
  foreach ($k in $ukeys) {
    foreach ($app in (Get-ItemProperty $k -EA SilentlyContinue | Where-Object { $_.DisplayName -like "KiCad*" })) {
      if ($app.InstallLocation) { $p = Join-Path $app.InstallLocation "bin\python.exe"; if (Test-Path $p) { return $p } }
    }
  }
  $roots = @("${env:ProgramFiles(x86)}\KiCad")
  foreach ($drv in (Get-PSDrive -PSProvider FileSystem -EA SilentlyContinue).Root) {
    $roots += (Join-Path $drv "Program Files\KiCad"); $roots += (Join-Path $drv "KiCad")
  }
  foreach ($root in ($roots | Select-Object -Unique)) {
    if (Test-Path $root) {
      foreach ($d in (Get-ChildItem $root -Directory -EA SilentlyContinue | Sort-Object Name -Descending)) {
        $p = Join-Path $d.FullName "bin\python.exe"; if (Test-Path $p) { return $p }
      }
      $p = Join-Path $root "bin\python.exe"; if (Test-Path $p) { return $p }
    }
  }
  return $null
}
$py = Find-KiCadPython
if ($py) {
  & $py -c "import pcbnew" 2>$null
  if ($LASTEXITCODE -eq 0) {
    $v = & $py -c "import pcbnew; print(pcbnew.GetBuildVersion())" 2>$null
    Note "python + pcbnew" "OK ($py, $v)"
  } else {
    Bad "pcbnew" "found $py but 'import pcbnew' failed -- reinstall KiCad 10"
  }
} else {
  Bad "KiCad python" "install KiCad 10 (bundles python.exe + pcbnew), or set `$env:KICAD_PYTHON"
}

# --- kicad-cli (from KiCad bin even if not on PATH) ---
$kicadcli = $null
if ($py) { $c = Join-Path (Split-Path -Parent $py) "kicad-cli.exe"; if (Test-Path $c) { $kicadcli = $c } }
if (-not $kicadcli) { $g = Get-Command kicad-cli -EA SilentlyContinue; if ($g) { $kicadcli = $g.Source } }
if ($kicadcli) { Note "kicad-cli" ("OK (" + ((& $kicadcli version 2>$null) | Select-Object -First 1) + ")") }
else { Bad "kicad-cli" "install KiCad 10 (provides kicad-cli.exe)" }

# --- java (PATH, repository runtime, or common roots) ---
$java = (Get-Command java -EA SilentlyContinue)
if (-not $java -and $env:JAVA_HOME) { $j = Join-Path $env:JAVA_HOME "bin\java.exe"; if (Test-Path $j) { $java = @{ Source = $j } } }
if (-not $java) {
  $localJdkRoot = Join-Path $repo "build\fr-fork\jdk-dist"
  if (Test-Path $localJdkRoot) {
    $hit = Get-ChildItem -Path $localJdkRoot -Recurse -Filter java.exe -EA SilentlyContinue |
           Where-Object { (Split-Path -Leaf (Split-Path -Parent $_.FullName)) -eq "bin" } |
           Sort-Object FullName -Descending | Select-Object -First 1
    if ($hit) { $java = @{ Source = $hit.FullName } }
  }
}
if (-not $java) {
  foreach ($r in @("$env:ProgramFiles\Eclipse Adoptium","$env:ProgramFiles\Java","$env:ProgramFiles\Microsoft")) {
    $hit = Get-ChildItem -Path $r -Recurse -Filter java.exe -EA SilentlyContinue | Select-Object -First 1
    if ($hit) { $java = @{ Source = $hit.FullName }; break }
  }
}
if ($java) {
  $line = (& $java.Source -version 2>&1) | Select-Object -First 1
  $maj  = [regex]::Match($line, 'version "(\d+)').Groups[1].Value
  if ([int]("0$maj") -ge 17) { Note "java" "OK ($line)" }
  else { Bad "java" "found $line; Freerouting needs java 17+" }
} else {
  Bad "java" "install a JRE 17+ (Adoptium Temurin) and/or set `$env:JAVA_HOME"
}

# --- xvfb: NOT needed on Windows ---
Note "xvfb" "n/a on Windows (Java uses the native display; run the runner in an interactive desktop session)"

# --- Freerouting pinned jar (required; conventional paths are hash-verified) ---
if ($py) {
  $jarProbe = "import os,sys; sys.path.insert(0, os.path.join(r'$repo','scripts')); import cec_fr; print(cec_fr.ensure_jar())"
  $jarPath = (& $py -c $jarProbe 2>$null | Select-Object -Last 1)
  if ($LASTEXITCODE -eq 0 -and $jarPath -and (Test-Path $jarPath)) {
    $mode = if ($env:CEC_FREEROUTING_JAR) { "explicit override" } else { "hash verified" }
    Note "freerouting jar" "OK ($mode, $jarPath)"
  } else {
    Bad "freerouting jar" "missing or hash mismatch; rebuild cec3 using scripts/build-freerouting-cec3.sh in WSL"
  }
} else {
  Bad "freerouting jar" "cannot verify without KiCad python"
}

Write-Host ""
if ($fail) {
  Write-Error "PREREQS FAILED -- see the hints above (docs/self-hosted-router.md has full setup)."
  exit 1
}
Write-Host "All routing prerequisites present."

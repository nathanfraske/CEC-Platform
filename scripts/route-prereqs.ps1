# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# route-prereqs.ps1 -- Windows prerequisite check for the automated router.
# Mirrors route-prereqs.sh but Windows-appropriate: NO xvfb (Java uses the native Win32
# display), and pcbnew is checked via KiCad's bundled python (route.ps1 finds it).
# Fails fast with an install hint per missing piece. See docs/self-hosted-router.md.
$ErrorActionPreference = "Continue"
$fail = $false
function Note($name, $msg) { "{0,-22} {1}" -f $name, $msg | Write-Host }
function Bad($name, $msg)  { Write-Host ("MISSING  {0,-13} {1}" -f $name, $msg) -ForegroundColor Red; $script:fail = $true }

Write-Host "== route prerequisites on $env:COMPUTERNAME (Windows) =="

# --- KiCad python + pcbnew ---
function Find-KiCadPython {
  if ($env:KICAD_PYTHON -and (Test-Path $env:KICAD_PYTHON)) { return $env:KICAD_PYTHON }
  foreach ($root in @("$env:ProgramFiles\KiCad", "${env:ProgramFiles(x86)}\KiCad")) {
    if (Test-Path $root) {
      foreach ($d in (Get-ChildItem $root -Directory -EA SilentlyContinue | Sort-Object Name -Descending)) {
        $p = Join-Path $d.FullName "bin\python.exe"; if (Test-Path $p) { return $p }
      }
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

# --- java (PATH or common roots) ---
$java = (Get-Command java -EA SilentlyContinue)
if (-not $java -and $env:JAVA_HOME) { $j = Join-Path $env:JAVA_HOME "bin\java.exe"; if (Test-Path $j) { $java = @{ Source = $j } } }
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
  else { Bad "java" "found $line -- Freerouting needs java 17+ (21 recommended)" }
} else {
  Bad "java" "install a JRE 21 (Adoptium Temurin) and/or set `$env:JAVA_HOME"
}

# --- xvfb: NOT needed on Windows ---
Note "xvfb" "n/a on Windows (Java uses the native display; run the runner in an interactive desktop session)"

# --- Freerouting jar (informational) ---
$jar = $env:CEC_FREEROUTING_JAR
if ($jar -and (Test-Path $jar)) { Note "freerouting jar" "OK (`$env:CEC_FREEROUTING_JAR)" }
elseif (Test-Path (Join-Path $env:USERPROFILE ".cache\cec\freerouting-1.7.0.jar")) { Note "freerouting jar" "OK (cached)" }
else { Note "freerouting jar" "not cached -- cec_fr.ensure_jar() downloads the pinned v1.7.0 on first route" }

Write-Host ""
if ($fail) {
  Write-Error "PREREQS FAILED -- see the hints above (docs/self-hosted-router.md has full setup)."
  exit 1
}
Write-Host "All routing prerequisites present."

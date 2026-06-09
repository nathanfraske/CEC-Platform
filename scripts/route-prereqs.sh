#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# route-prereqs.sh -- verify a (self-hosted) runner has everything the automated
# routing system needs to run the CPU-heavy compute plane natively on this machine:
#
#   * python3 with the KiCad pcbnew bindings  (DSN/SES round-trip, board measure)
#   * kicad-cli                                (DRC + render)
#   * java 17+ (21 recommended)                (Freerouting)
#   * xvfb-run on HEADLESS LINUX only          (Freerouting under a virtual X server)
#   * the Freerouting jar                      (cec_fr.ensure_jar downloads it if absent)
#
# Fails fast with an install hint per missing piece, so a misprovisioned runner gives
# a clear error instead of a deep stack trace mid-route. See docs/self-hosted-router.md.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0

note() { printf '  %-22s %s\n' "$1" "$2"; }
bad()  { printf '  \033[31mMISSING\033[0m  %-13s %s\n' "$1" "$2"; fail=1; }

echo "== route prerequisites on $(hostname) =="

# --- python3 + pcbnew ---
if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import pcbnew' >/dev/null 2>&1; then
    ver="$(python3 -c 'import pcbnew; print(pcbnew.GetBuildVersion())' 2>/dev/null)"
    note "python3 + pcbnew" "OK (${ver:-unknown})"
  else
    bad "pcbnew" "python3 present but 'import pcbnew' failed -- install KiCad 10 with the python bindings"
    note "" "  Ubuntu: apt install kicad  (or the kicad/kicad:10.0 image's python)"
  fi
else
  bad "python3" "install python3"
fi

# --- kicad-cli ---
if command -v kicad-cli >/dev/null 2>&1; then
  note "kicad-cli" "OK ($(kicad-cli version 2>/dev/null | head -1))"
else
  bad "kicad-cli" "install KiCad 10 (provides kicad-cli) and put it on PATH"
fi

# --- java ---
if command -v java >/dev/null 2>&1; then
  jver="$(java -version 2>&1 | head -1)"
  jmaj="$(java -version 2>&1 | sed -nE 's/.*version "([0-9]+).*/\1/p' | head -1)"
  if [ "${jmaj:-0}" -ge 17 ] 2>/dev/null; then
    note "java" "OK ($jver)"
  else
    bad "java" "found $jver -- Freerouting 1.7.0 needs java 17+ (21 recommended)"
  fi
else
  bad "java" "install a JRE 21 (e.g. apt install openjdk-21-jre-headless)"
fi

# --- xvfb-run ---
# Only HEADLESS LINUX needs it: cec_fr._fr_command wraps Freerouting in xvfb-run only on
# Linux with no $DISPLAY. macOS and display-attached Linux run java on the native display,
# so its absence there is informational, not a failure (punchlist R-06).
if command -v xvfb-run >/dev/null 2>&1; then
  note "xvfb-run" "OK"
elif [ "$(uname -s)" = "Linux" ] && [ -z "${DISPLAY:-}" ]; then
  bad "xvfb-run" "install xvfb (apt install xvfb) -- on headless Linux, Freerouting runs under a virtual X server"
else
  note "xvfb-run" "absent, but not needed here (only headless Linux wraps Freerouting in xvfb-run)"
fi

# --- Freerouting jar (informational: cec_fr.ensure_jar downloads it if absent) ---
jar="${CEC_FREEROUTING_JAR:-}"
if [ -n "$jar" ] && [ -f "$jar" ]; then
  note "freerouting jar" "OK (\$CEC_FREEROUTING_JAR=$jar)"
elif [ -f /tmp/fr_1.7.0.jar ] || [ -f "$HOME/.cache/cec/freerouting-1.7.0.jar" ]; then
  note "freerouting jar" "OK (cached)"
else
  note "freerouting jar" "not cached -- cec_fr.ensure_jar() will download the pinned v1.7.0 on first route"
fi

echo
if [ "$fail" -ne 0 ]; then
  echo "PREREQS FAILED -- see the hints above (docs/self-hosted-router.md has full setup)." >&2
  exit 1
fi
echo "All routing prerequisites present."

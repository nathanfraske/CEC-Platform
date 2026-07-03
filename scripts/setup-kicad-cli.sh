#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Install KiCad (kicad-cli) in an ephemeral "Claude Code on the web" container.
#
# The web container ships no kicad-cli and no Docker daemon, the design files are
# KiCad 10 format (forward-only -- an older KiCad cannot open them), and the
# Ubuntu archive only carries KiCad 7. This pulls the pinned KiCad major
# (versions.env -> KICAD_SERIES, default 10.0) from the KiCad releases PPA so the
# scripts/*.sh wrappers (which prefer a local kicad-cli) work in remote sessions.
#
# Idempotent, root-only, non-interactive, and FAIL-SOFT: it never exits nonzero,
# so a SessionStart hook calling it cannot block the session if the network
# policy changes. Invoked by .claude/hooks/session-start.sh; also fine by hand.
set -uo pipefail

log() { printf '[setup-kicad-cli] %s\n' "$*" >&2; }

# 1. Already have it? (warm-started container snapshot, or a local dev box.)
if command -v kicad-cli >/dev/null 2>&1; then
  log "present: $(kicad-cli version 2>/dev/null || echo kicad-cli) -- nothing to do"
  
# --- render-loop provisioning (schematic-quality charter: cec_sch_render.py) ---------
# pip playwright drives the PREINSTALLED chromium (/opt/pw-browsers) -- never run
# "playwright install" here (env rule); the library alone suffices.
if ! python3 -c "import playwright" 2>/dev/null; then
  log "installing python playwright (render loop)"
  pip install -q playwright 2>>"$aptlog" || log "playwright install failed -- render loop unavailable"
fi
exit 0
fi

# 2. Need root to apt-install. Soft-skip otherwise.
if [ "$(id -u)" != 0 ]; then
  log "not root -- cannot install kicad-cli; skipping"
  exit 0
fi

# 3. Pinned KiCad series (single source of truth: versions.env).
KICAD_SERIES="10.0"
_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
[ -f "$_dir/../versions.env" ] && . "$_dir/../versions.env" 2>/dev/null || true
ppa="kicad-${KICAD_SERIES}-releases"
codename="$(. /etc/os-release 2>/dev/null; echo "${VERSION_CODENAME:-noble}")"
export DEBIAN_FRONTEND=noninteractive
aptlog="$(mktemp 2>/dev/null || echo /tmp/setup-kicad-cli.log)"

# 4. Some network policies block ppa.launchpadcontent.net (the modern PPA pool
#    host) with 403, which makes `apt-get update` hard-fail on every launchpad
#    PPA baked into the image. Park those sources so update stays usable, and
#    reach the KiCad PPA through the legacy host ppa.launchpad.net over plain
#    HTTP, which serves the same InRelease + pool. [trusted=yes] because the
#    signing key isn't fetched (HTTP transport; ephemeral throwaway container).
parked="/var/tmp/cec-disabled-apt-sources"
mkdir -p "$parked" 2>/dev/null || true
grep -rIl 'launchpadcontent\.net' /etc/apt/sources.list.d/ 2>/dev/null | while IFS= read -r f; do
  mv "$f" "$parked/" 2>/dev/null && log "parked blocked PPA source: ${f##*/}"
done
printf 'deb [trusted=yes] http://ppa.launchpad.net/kicad/%s/ubuntu %s main\n' "$ppa" "$codename" \
  > /etc/apt/sources.list.d/kicad-cec.list

# 5. Refresh package lists; tolerate per-source errors (main archive still updates).
apt-get update >"$aptlog" 2>&1 || log "apt-get update reported errors (continuing)"

# 6. Confirm the PPA actually offers the pinned KiCad for this release before
#    committing to an install (guards a changed/tightened network policy).
cand="$(apt-cache policy kicad 2>/dev/null | awk '/Candidate:/{print $2}')"
case "$cand" in
  "${KICAD_SERIES}"* | 10.*) : ;;
  *) log "KiCad ${KICAD_SERIES} not offered (candidate='${cand:-none}'); ppa.launchpad.net may be blocked -- skipping"; exit 0 ;;
esac

# 7. Install. --no-install-recommends skips kicad-libraries / 3D models / docs
#    (multi-GB and unneeded: the project vendors its own libs via ${KIPRJMOD}).
log "installing kicad ${cand} (--no-install-recommends) ..."
if apt-get install -y --no-install-recommends kicad >>"$aptlog" 2>&1 && command -v kicad-cli >/dev/null 2>&1; then
  log "installed: kicad-cli $(kicad-cli version 2>/dev/null)"
else
  log "install failed (see $aptlog) -- skipping; ERC/DRC unavailable this session"
  tail -n 6 "$aptlog" >&2 2>/dev/null || true
fi
exit 0

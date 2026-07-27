#!/bin/bash
# HUB FAB PUSH (owner 2026-07-27: "focus on just the Hub and get that fab ready").
# The hub is routing-hard -- winners historically land at unconn 7-36 and the
# candidate sits at 32 with 5 severity-error track_width. Fab-ready needs ZERO
# unconnected and zero severity-error DRC, so this runs at HIGH effort (passes 40 /
# opt 60 vs the 16/20 default) over many seeds rather than many cheap rounds.
set -u
OUT=build/fresh-wave-hub
mkdir -p build/hub-night "$OUT"
B=hub-standard-rev2
SEED=${SEED:-2000}
ROUNDS=${ROUNDS:-10}
for ROUND in $(seq 1 $ROUNDS); do
  echo "########## HUB ROUND $ROUND (seeds $SEED,$((SEED+1))) $(date '+%H:%M') ##########"
  python3 scripts/cec_fresh_wave.py --boards "$B" --seeds "$SEED,$((SEED+1))" \
      --passes 40 --opt 60 --out "$OUT" --work /tmp/wave-hub 2>&1 \
    | grep -E '\[wave\]|pour termination|force lanes|POUR INCURSION|candidate:'
  W=$(ls -t "$OUT/$B"/*.kicad_pcb 2>/dev/null | head -1)
  if [ -n "$W" ]; then
    echo "----- ROUND $ROUND AUDIT -----"
    # FAB PROFILE CHECK: vendor capability, not our intent rules (see
    # scripts/cec_fab_check.py -- our DRC checks the board against its own
    # .kicad_pro/.kicad_dru, which on these boards set min_clearance 0.0).
    python3 scripts/cec_fab_check.py "$W" --quiet 2>&1 | grep -v Debug:
    python3 scripts/cec_pour_audit.py "$W" --quiet 2>&1 | grep -v Debug:
    # THE FAB GATE: zero unconnected + zero severity-error DRC.
    # The .kicad_dru MUST travel with the board. Measured 2026-07-27: the
    # candidate dir carries no .kicad_dru, so DRC there saw 5 violations while
    # the same board with its rules has 20 -- the 15 extra are 'Power min width'
    # (0.5mm) hits on /USB_VBUS, /PSU_5V, +5VSB, /MAIN_5V_RAW. A gate that
    # cannot see the rules would have called this board fab-ready.
    cp -f "beta/$B/$B.kicad_dru" "${W%.kicad_pcb}.kicad_dru" 2>/dev/null
    if [ ! -f "${W%.kicad_pcb}.kicad_dru" ]; then
      echo "FABGATE ABORT: no .kicad_dru beside $W -- refusing to grade blind"
      continue
    fi
    kicad-cli pcb drc --severity-error --format json -o /tmp/hubgate.json "$W" >/dev/null 2>&1
    python3 - "$W" <<'PY'
import json, sys, collections
d = json.load(open('/tmp/hubgate.json'))
v = d.get("violations") or []
u = d.get("unconnected_items") or []
print("FABGATE %-46s unconnected=%-4d drc_error=%-3d %s"
      % (sys.argv[1].split('/')[-1][:46], len(u), len(v),
         "*** FAB READY ***" if not u and not v else
         "|".join("%s:%d" % kv for kv in
                  collections.Counter(x.get("type") for x in v).most_common(4))))
PY
  fi
  SEED=$((SEED+2))
done
echo "########## HUB CHAIN DONE $(date '+%H:%M') ##########"

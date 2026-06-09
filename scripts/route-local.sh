#!/usr/bin/env bash
# ----------------------------------------------------------------------------------------------
# Gated local-judge route. Spins the vLLM judge UP only when needed, WARMS it, routes in the
# routing container with the local judge, then STOPS it to free GPU VRAM. The judge is profile-
# gated in compose (never auto-started), so it does not hold ~0.85x VRAM except during a route.
#
#   scripts/route-local.sh <board> [extra cec_router args...]   # e.g. --seeds 0,1 --passes 8
#   scripts/route-local.sh eps-8pin --seeds 0,1 --passes 8 --opt-time 10 --max-iters 2
#   scripts/route-local.sh --keep eps-8pin ...                  # leave the judge UP after (batch use)
#
# Run from the HOST (needs docker access). The judge is reached by the routing container as the
# compose service `inference`.
# ----------------------------------------------------------------------------------------------
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

KEEP=0
args=()
for a in "$@"; do
    if [ "$a" = "--keep" ]; then KEEP=1; else args+=("$a"); fi
done
[ "${#args[@]}" -ge 1 ] || { echo "usage: $0 [--keep] <board> [cec_router args...]" >&2; exit 2; }
board="${args[0]}"
rest=("${args[@]:1}")

cleanup() {
    if [ "$KEEP" = "1" ]; then
        echo "[route-local] --keep: leaving the judge UP (run 'python3 scripts/cec_judge_local.py down' to free VRAM)"
    else
        python3 "$ROOT/scripts/cec_judge_local.py" down || true
    fi
}
trap cleanup EXIT

# 1. spin up + warm the judge ONLY if it is not already serving (idempotent gate)
python3 "$ROOT/scripts/cec_judge_local.py" up

# 2. route in the routing container with the local judge (reaches the inference service)
docker exec -e CEC_VLLM_URL=http://inference:8000/v1 -w /workspace docker-routing-1 \
    python3 scripts/cec_router.py --board "$board" --judge local "${rest[@]}"

# 3. the EXIT trap stops the judge -> VRAM freed

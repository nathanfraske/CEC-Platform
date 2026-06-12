# T5 auditor — DeepSeek-V4-Flash eval record (owner 2026-06-12)

The deep local **DeepSeek-V4-Flash** is now the DEFAULT T5 auditor chair (`cec_fullstack.resolve_auditor`);
cloud **Sonnet is one env var away** (`CEC_FS_AUDITOR_MODEL=sonnet`) for a latency-sensitive run. This is
the eval-gate evidence for the seat.

## What was built
- **`resolve_auditor`**: default → `deepseek-v4-flash`; `CEC_FS_AUDITOR_MODEL` / `--auditor` override.
- **`deepseek_audit`**: broker call via `cec_judge_local._chat_json` (json_schema grammar + miner→scribe
  recovery for the deep reasoner); fail-safe (broker error → `repair` verdict, never raises into the loop);
  writes the same findings artifact the Sonnet path does.
- **warm-at-start**: `run()` warms the deep auditor seat up front (V4-Flash ~7 min cold load) so the first
  round's call never loses its race to a cold start. Sonnet (claude CLI) needs no warming.
- **packet-replay eval** (`scripts/cec_auditor_eval.py`): replays a recorded round packet from a real run
  through the auditor and records verdict / failure_class / root-cause-presence / wall, vs the Sonnet
  baseline that ran that round live.
- Host tests `tests/test_auditor_dispatch.py` (8): default = V4-Flash, Sonnet one env var away, dispatch
  routing, broker schema+model targeting, error→repair degrade.

## Packet-replay result

<!-- REPLAY_RESULT: filled from scripts/cec_auditor_eval.py (docs/det-inspection/auditor-v4flash-replay.json) -->
**Status: PENDING the first live V4-Flash run.** On the *current* box V4-Flash (~160 GB) exceeds the 125 GB
WSL2 ceiling and **pages** (the exact constraint `ai-box-upgrade-analysis-2026-06-12.md` calls out: it needs
the 256 GB box to be resident). Run it where V4 is resident:
```bash
docker exec docker-routing-1 python3 /workspace/scripts/cec_auditor_eval.py \
    --run docs/fullstack-run-2026-06-11-validation --rounds 1,2 --model deepseek-v4-flash
```
The full per-round **economics — tokens/s, per-round wall vs the ~17-min Sonnet baseline** — are recorded
from the **first V4-Flash overnight** (owner item 4) and appended here.

## Draft eval_gate record (for the owner to sign into cec-policy.json)

The seat binding is owner-gated (`cec-policy.json`). Drafted block for the `analyst`/auditor role once the
replay lands (do NOT sign to passed until the live replay confirms a competent finding):
```json
"auditor_v4flash": {
  "model": "deepseek-v4-flash",
  "role": "T5 in-loop auditor (default chair); Sonnet one env var away (CEC_FS_AUDITOR_MODEL=sonnet)",
  "eval_gate": {
    "status": "pending",
    "test": "packet-replay on a recorded round -> emits a verdict + bankable root_cause; first-overnight economics",
    "ref": "docs/det-inspection/auditor-v4flash-eval.md + auditor-v4flash-replay.json",
    "residency_caveat": "V4-Flash ~160GB pages at the 125GB WSL ceiling; resident on the 256GB upgrade box"
  }
}
```

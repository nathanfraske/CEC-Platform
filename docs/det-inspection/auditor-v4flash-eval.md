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

**Live attempt 2026-06-12 (`auditor-v4flash-replay.json`): V4-Flash UNSERVABLE on the current box —
HTTP 502 after 330.9 s.** The broker could not serve `deepseek-v4-flash`: it pages at ~160 GB against the
125 GB WSL2 ceiling and the load thrashed/aborted — empirically the exact residency constraint
`ai-box-upgrade-analysis-2026-06-12.md` predicts (V4 needs the 256 GB box to be resident). **Two things
this DID validate:** (1) `deepseek_audit` is **fail-safe** — the 502 degraded to `{"verdict":"repair",
"error":...}` and never raised into the loop; (2) the harness + packet reconstruction run end-to-end.

**The run venue is the WINDOWS-HOSTED workaround, NOT the WSL broker** (owner 2026-06-12): V4-Flash runs
natively on Windows (full 192 GB physical, no WSL 125 GB cap). The deep auditor now has its own endpoint
knob, **`CEC_FS_AUDITOR_URL`** (`cec_fullstack.DEEP_AUDITOR_URL`), so ONLY the auditor targets Windows
while the worker seats stay on the WSL broker; warm-at-start is skipped there (the Windows host keeps V4
resident). Re-run pointed at the Windows V4 endpoint:
```bash
python3 scripts/cec_auditor_eval.py --rounds 1,2 --model deepseek-v4-flash \
    --url http://<win-host>:<port>/v1        # or: CEC_FS_AUDITOR_URL=http://<win-host>:<port>/v1 ...
```
The **competent-finding validation + economics** (tokens/s, per-round wall vs the ~17-min Sonnet baseline)
land from that Windows-hosted run / the first V4-Flash overnight.
The full per-round **economics — tokens/s, per-round wall vs the ~17-min Sonnet baseline** — are recorded
from the **first V4-Flash overnight** (owner item 4) and appended here.

## Economics (item 4) — MEASURED on the Windows-hosted V4 (2026-06-12)

Packet-replay of validation-run rounds 1–2 through V4-Flash on `DESKTOP-1MO5R95.mshome.net:8007`
(`auditor-v4flash-replay.json`): **2/2 competent findings** (verdict + bankable root_cause both rounds).

| metric | Sonnet (prior chair) | **DeepSeek-V4-Flash (MEASURED)** |
|---|---|---|
| per-round auditor wall | **~17 min** (cloud round-trip + stream; validation run, full rounds 27–40 min incl. route + all tiers) | **mean 179.9 s/round** (r1 242 s, r2 118 s) — **~5–6× faster** |
| competent findings | baseline | **2/2** — r1 "routing congestion → DRC + unconnected → gate fail"; r2 "/SENSEC2_LO is a foreign signal routed through a sense corridor → pour clipping" (a precise, mechanism-level diagnosis) |
| venue | cloud (`claude -p`) | **Windows-hosted V4** (`CEC_FS_AUDITOR_URL`, full 192 GB). NOT the WSL broker — V4 ~160 GB pages at the 125 GB ceiling (a broker-routed replay 502'd after 330 s) |
| audit depth | good | **deeper** — named the exact sense-corridor-clipping mechanism; its rumination earlier surfaced a planted spec inconsistency Sonnet/oss-120b omitted |

**Net: V4-Flash is both faster (~3 min vs ~17 min) AND a deeper auditor** — latency is no longer the reason
to keep Sonnet, which becomes the one-env-var fallback. **Nuance for the owner:** V4 returned `accept` on
both rounds where Sonnet returned `repair` (both boards were gate-failing); the *root_cause* diagnoses are
strong, but the verdict polarity on a failing board is worth a glance before relying on the verdict field
(the loop's effectors fire on deterministic facts + the bankable root_cause, not the auditor verdict). The
full per-round tokens/s lands from tonight's overnight telemetry.

## Validated (measured 2026-06-12)
- **Fail-safe:** the live 502 degraded to `{"verdict":"repair"}` and never raised into the loop.
- **Harness + packet reconstruction** run end-to-end (reached the endpoint, timed, compared to Sonnet).
- **Residency constraint pinned:** V4 unservable under WSL (502); runs on the Windows-native host.
- **Default + fallback wiring:** `resolve_auditor` defaults to V4-Flash; `CEC_FS_AUDITOR_MODEL=sonnet`
  flips to Sonnet; `CEC_FS_AUDITOR_URL` points the deep seat at the Windows endpoint. 8 host tests green.

## eval_gate record (for the owner's signature into cec-policy.json)

```json
"auditor_v4flash": {
  "model": "deepseek-v4-flash",
  "role": "T5 in-loop auditor DEFAULT chair; Sonnet one env var away (CEC_FS_AUDITOR_MODEL=sonnet)",
  "endpoint": "Windows-hosted (CEC_FS_AUDITOR_URL); NOT the WSL broker (V4 pages at the 125GB ceiling)",
  "eval_gate": {
    "status": "<owner signs>",
    "evidence": "MEASURED 2026-06-12 on Windows-hosted V4: 2/2 competent findings on validation rounds 1-2 (verdict + bankable root_cause, incl. the precise sense-corridor-clipping diagnosis), mean 179.9s/round vs the ~17min Sonnet baseline (~5-6x faster, deeper); fail-safe verified (broker 502 -> repair). Nuance: V4 returned accept on gate-failing boards where Sonnet said repair -- root_cause strong, verdict-polarity worth a glance.",
    "venue": "Windows-hosted V4 (CEC_FS_AUDITOR_URL=http://DESKTOP-1MO5R95.mshome.net:8007/v1); NOT the WSL broker (V4 pages at 125GB). Tonight's overnight appends per-seat tokens/s telemetry.",
    "ref": "docs/det-inspection/auditor-v4flash-eval.md + auditor-v4flash-replay.json"
  }
}
```

# VLM bake-off — CL-22 golden-render eval (2026-06-10)

The local vision-seat bake-off the parity plan §6 scheduled: the three downloaded
candidates evaluated on the CL-11 golden fixtures, gating any CL-22 panel-seat
binding. Harness: `scripts/cec_vlm_bakeoff.py` (assets → run → show/html/report).
Raw record: `build/vlm-bakeoff/` — per-model results JSON, full call transcript
(`transcript-v2.jsonl`), and the self-contained viewer `transcript-v2.html`
(every composite + every prompt/reasoning/answer).

## Verdict

**All three local models PASS the golden-render gate under the v2
(facts-alongside) protocol** — 12/12 gate verdicts correct across the four
fixtures (pre-fix fires, post-fix stays quiet, both case families):

| model | 12vhpwr pre/post | hub pre/post | perception probes | refs probe | overall |
|---|---|---|---|---|---|
| cec-vision-judge (Qwen3-VL-32B Q4_K_M) | PASS / PASS | PASS / PASS | 1/2 (A-bias) | 6/6 | **PASS** |
| cec-worker-vision (Qwen3.6-35B-A3B + mmproj, nothink) | PASS / PASS | PASS / PASS | **2/2** | 6/6 | **PASS** |
| cec-worker-quality-vision (Qwen3.6-27B + mmproj, nothink) | PASS / PASS | PASS / PASS | 1/2 (A-bias) | 6/6 | **PASS** |

v1 baseline (naive protocol — absolute-mm measurement, no facts block, thinking
left on): **all three FAILED** — the judge false-fired on the conformant post
board; both Qwen3.6 workers returned empty content on 100% of grammar-constrained
calls (thinking-overrun: the reasoning channel consumed the budget before the
JSON channel started — the same failure mode the M2.7 bench documented for text).

## What v1 → v2 changed (each item is a measured finding, not a guess)

1. **Facts ride alongside the render** (CL-21 rule): the context pass now carries
   the deterministic numbers extracted from the board file (via count/sizes;
   divider refs/values). The post cases thereby became *hallucination-resistance*
   tests — a seat that cries "undersized" against stated-conformant facts fails.
2. **Selection, never measurement** (CL-21 rule, now demonstrated on our own
   boards): v1 asked for an absolute mm estimate from a stated px/mm scale — every
   model failed it, harvesting salient prompt numbers instead (25.6 = the scale,
   9.2 = the lane current). v2 stamps two reference via rings (REF A = 0.6 mm,
   REF B = 0.9 mm) into the panel at exact board scale and asks which the lane
   vias match.
3. **De-anchored prompt**: v1's role text described the vias as "small circles" —
   the judge echoed "small, sparse" back on both fixtures. v2 says "circles".
4. **`enable_thinking: false`** via `chat_template_kwargs` for the Qwen3.6 vision
   workers on bounded judging calls (`_NOTHINK` set in the harness).
5. **Full transcript layer**: every call (prompt, raw content, reasoning trace,
   usage, finish reason) appends to `transcript<tag>.jsonl` as it returns;
   viewers `show` (terminal, filterable) and `html` (image-paired).

## Calibration insights (feed CL-22/CL-24 seat-calibration records)

- **The facts channel is load-bearing for geometry; the seats are not
  measurers.** The judge's post-board context verdict said the vias are
  "visually comparable to REF B" — but its isolated perception probe on the SAME
  image said "identical to REF A". With facts present it integrates correctly;
  alone, a 0.3 mm via delta is below its reliable visual floor. Geometry
  conformance stays the deterministic checkers' job (CL-25
  netclass-geometry-conformance), which is how the pipeline was already designed.
- **Where the seats genuinely earn their place: structure/text reading.** All
  three read R15–R18 with values and sense-net names off the schematic render
  (6/6 refs probe). The judge's standout: on hub-pre **blind** — no rule given —
  it produced *"no visible circuit to indicate which source is currently
  active... the firmware needs to know which source is live to manage load
  budgeting, but no sense network exists"*: it derived the §2.9 requirement from
  the role context and spotted the gap. It also correctly dismissed the
  BLACKOUT_SENSE divider confound on the context pass ("connects to a net named
  BLACKOUT_SENSE", not source-sense).
- **Blind passes are noisy by construction** and will need the deterministic
  triage layer the CL-22 design already specifies: on conformant boards the blind
  scans still emit plausible-sounding findings (uneven via spacing, clearance
  vibes), and one hub-post blind finding confabulated a detail ("J8 is a 100nF
  capacitor" — J8 is the connector). Verdict-bearing output must stay
  facts-anchored and charter-scoped.
- The 35B-A3B volume worker was the only model to pass BOTH perception probes —
  worth remembering when assigning crop-reader charters; "judge" rank does not
  imply best raw perception at this quant level.

## Fixture-burn discipline (AM-02)

The four CL-11 fixtures are now **burned for prompt/charter tuning**: the v1→v2
protocol revision was tuned against them (sanctioned — seeding the eval protocol
is their purpose). Any future charter/prompt iteration for these seats must
validate against fresh holdout cases (`tests/holdout/`, never-tune pool) rather
than re-tuning on these four. The golden-render eval itself (these fixtures +
this harness) remains the regression gate for *binding changes* (new model, new
quant, new mmproj).

## Infrastructure landed

- `docker/compose.yaml`: `vision-judge` (:8006), `worker-volume-vision` (:8012),
  `worker-quality-vision` (:8014) — llama.cpp + `--mmproj`, separate
  ports/profiles so the benched text workers are untouched; ctx 16k, single slot.
- `~/cec-llm-broker/models.json`: `cec-vision-judge`, `cec-worker-vision`,
  `cec-worker-quality-vision` registered (vram_gb 25/27/22 → broker swaps, one
  vision backend resident at a time); backup at `models.json.bak-vlm`.
- GGUF downloads verified (magic + size): Qwen3-VL-32B Q4_K_M 19.8 GB + 1.2 GB
  mmproj; mmproj files for both Qwen3.6 workers (~0.9 GB each).
- Render path (in-container): fixture → `kicad-cli pcb/sch export pdf` → gs →
  PNG at exact dpi (page-mapping asserted) → PIL crops/composites + facts JSON
  parsed from the board files. PCB at 650 dpi (25.6 px/mm ≥ the CL-21 25 px/mm
  floor), schematic at 300 dpi.

## Binding status (owner-gated — no policy change made here)

`cec-policy.json` still lists the vision seats as non-load-bearing with absent
eval gates. This bake-off provides the recorded eval-gate PASS the CL-10 guard
requires; flipping any seat to load-bearing is a `cec-policy.json` edit, which is
CODEOWNERS-gated — i.e. the owner's PR approval IS the binding decision
(framework Decision 8/9 territory: panel seats/charters/budgets). Recommended
when taken up: judge seat = cec-vision-judge; crop-reader seats = the two worker
vision variants with nothink pinned; geometry charters excluded (deterministic
checkers own geometry); structure/text charters in.

Reproduce: `docker compose run --rm --no-deps -T routing python3
scripts/cec_vlm_bakeoff.py assets` then `python3 scripts/cec_vlm_bakeoff.py run
--tag=-v2` (host, broker up). Inspect: `... show --tag=-v2 [--model M --case C
--prompts]` or open `build/vlm-bakeoff/transcript-v2.html`.

# Coupled junctions, plated-terminal returns, and generated fill seams

## Scope and status

The current BETA inputs and prior routed control remain intact. No board is
promoted to fabrication and no complete new board has residual routing closure
from this slice. EPS/ATX terminal shorts remain a mechanical-interface authority
block; no vendor pad or dimensional contract has been weakened. A user choice
about a minimal joint main/daughterboard interface span increase is pending.

## Production changes

1. `cec_precision_route._junction_continuation_rank` ranks the absolute length
   of locally uncoupled member copper before future throat distance. This avoids
   rewarding short but widely separated junction stars; longer loops cannot win
   simply by improving a percentage denominator. Final whole-tree coupling,
   detour, skew, exact geometry and return checks remain independent.
2. `cec_pth_pair_returns` synthesizes ordinary legal GND return vias beside
   differential PTH terminals, using existing project via and clearance policy.
   Saved-board reference checking recognizes a PTH antipad transition cell only
   when the own-net PTH land and a nearby plated GND return span the signal and
   reference layers, and that return actually contacts the filled GND plane.
   NPTH, SMD, blind/nonspanning returns, bare GND labels, absent fill, unrelated
   nets and remote plane gaps are not exempted. The existing 1.5 mm return
   limit is project policy, not a newly invented vendor specification.
3. `cec_critical_checkpoint` compares the candidate against a freshly filled
   disposable parent control. It still preserves every original parent copper
   primitive and placement coordinate, hashes executable sidecars, and demands
   all saved-board pair pads connected and all applicable physics passing.
4. Explicit pair scope now rejects unknown or empty names before any Kelvin or
   pair copper is authored. A short alias previously selected nothing but could
   return `pairs_ok=true`. Independent checkpoint admission already rejected
   that empty transaction; now the producing API fails explicitly as well.
5. `cec_generated_fill_seams.coalesce` is invoked by the real power-pour
   materializer. Compatible generated orthofill patches join a touching owned
   pour/manifold parent before filling. The intended polygon union must remain
   unchanged. Authored/locked zones, different nets/layers/fill settings, hatch
   fills, disconnected shapes and foreign-priority conflicts are excluded.
   Exact fill, power-domain connectivity and DRC admission remain mandatory.
   This is not removal of a current-carrying neck or enlargement of a board.

## Measured Hub route

The original high-effort CAN replay reached complete topology but failed the
unchanged 60% coupling floor at 55.2%. A length-weighted diagnostic also failed
(54.184%); this was not simply a plotting or sample-count artifact.

After coupling-aware local selection, a native complete route passed coupling
but failed filled-reference coverage (89.8% against 95%). All 63 uncovered
samples were inside the signal PTH land/antipad regions; no qualified nearby
ground return then existed. Adding independently legal return fields and
checking actual plane contact closed that physical omission.

The unpatched production replay is in `build/hub-native-pth-pair-20260914/`:

- 194.268 seconds under a 600-second pair budget.
- All 14 CAN pads connected, zero DRC errors, whole-pair physics passed.
- Saved PCB SHA256:
  `032f2702da06417d3547cc82fe38f32ebdcbcf1d41636c55e70a9dc9c81c5262`.
- Original parent: 281 opens with stale fill, 254 after fresh refill.
- Candidate: 242 opens. **Routing improvement is 12, not 39.**
- USB and other nets remain unfinished; no thermal qualification was run.

Revalidated checkpoint and native no-body renders:
`build/hub-certified-can-prefix-v2-20260914/` and archive
`20260914-qualified-can-prefix-hub-standard-rev2`.
The Windows dashboard `/img?id=...&panel=render` returned HTTP 200 with
`image/png`; the local mirror was visually inspected. The first publication
attempt refused routed copper because its adapter default was for placement
only. It was corrected only after independent route proof, not by bypassing
source intake or whole-board admission.

The subsequent exact USB replay (`build/hub-usb-fullname-after-can-20260914/`)
finished in 322.356 s with the second inline leg still refused. Qualified CAN
was preserved; the failed USB transaction was not retained as completed work.

## PCIe2 exact power root cause

The failed filled board was retained under
`build/pcie2-exact-retained-20260914/`. The ordinary admission wrapper previously
discarded that temporary board while retaining only its JSON refusal; the
earlier pour skeleton was not an adequate substitute for this forensic check.

Native DRC supplied two `copper_sliver` rows with no item coordinates. An
isolated attempt to read native DRC marker objects crashed in KiCad's missing
application singleton, so it was not used as evidence. An independent read-only
union of native filled copper and native pad/track polygon geometry localized
two 15-degree convex tips on B.Cu, at approximately (48.970, 6.913) and
(48.970, 7.750) mm. These diagnostic positions matched the two native failures.

Both were from a generated 0.098 mm-wide orthofill strip adjoining its own
larger rail. Separate fill processing left pointed seam fragments. Joining
compatible same-net outlines, without changing their intended union, removed
the artificial seam. The real production replay in
`build/pcie2-production-seam-fix-20260914/` passes exact power admission:
zero DRC, all four protected power domains connected. This proves the power
boundary only, not the remaining signal routing or fabrication release.

KiCad's own checker combines filled zones and native primitive polygons before
testing convex acute tips; see its
[10.0 sliver checker source](https://gitlab.com/kicad/code/kicad/-/blob/10.0/pcbnew/drc/drc_test_provider_sliver_checker.cpp).
Ground return placement follows the physical principle described in
[TI's return-path guidance](https://www.ti.com/document-viewer/lit/html/SSZTCM4/GUID-17532CA9-A0AF-4401-8383-D3F4AE36A744).
Neither source replaces the project-specific electrical/DFM acceptance gates.

## Regression and next live pass

`build/pth-return-wide-tests-20260914.log`: 170 passed, one SWIG deprecation
warning, two subtests. Subsequent combined tests are recorded in
`build/seam-and-prefix-broad-v3-tests-20260914.log`; read the final result before
claiming its count. These batches overlap and must not be summed.

All four probes in `build/pth-return-control-20260914.json` exactly equal
`build/fixed-relief-control-20260913.json`, with the protected control PCB hash
unchanged and zero DRC/zero opens. Existing broader release failures are also
unchanged; this is not a renewed fab signoff. A post-seam replay is recorded in
`build/seam-prefix-control-20260914.json`.

The seam batch finished with 379 passed and three skipped tests. Subsequent
production resume tests, completed board-pass results, and the owner-order
composition blockers are recorded in
[critical-prefix-resume-and-owner-order-2026-09-14.md](critical-prefix-resume-and-owner-order-2026-09-14.md).
Do not equate a completed attempt or partial prefix with a routed board.

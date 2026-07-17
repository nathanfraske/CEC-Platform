# Actuation space — deep dive along the pass-form line (owner ask, 2026-07-08)

_Owner: "dig in deep yourself and see what other actuation types along this line of
reasoning would work. Even rewrites of systems or remaking FreeRouting in Rust or
something, whatever." My own analysis, not delegated. The organizing insight is stated
first because every idea below is a corollary of it._

## The organizing insight: pass-form SHRINKS problems until stronger tools apply

Everything the pipeline has struggled with is a symptom of asking one tool to solve one
huge coupled problem (all placement at once; all routing at once). The pass ladder's real
power isn't tidiness — it's that **each locked boundary converts one intractable global
problem into many small, well-posed subproblems**, and small well-posed problems admit
tools we could never aim at the whole board: exact solvers, home-grown routers, learned
templates, even human hands mid-pipeline. Each actuation below names the subproblem the
ladder isolates and the stronger tool that becomes applicable.

## Tier 1 — buildable now on existing machinery (days each)

### A1. STAGED-FR: tier the router we already have
`cec_fr._dsn_exclude_pins` (:536) already strips pins from the DSN (the force-pour-only
and kelvin policies use it in production). Generalize: **run FR more than once, over a
shrinking net set** — pass 1 exports a DSN with ONLY tier-1 nets' pins present (pairs,
sense-adjacent signal), routes them on the empty board, locks + protects; pass 2 the next
tier with tier-1 protected; final pass the residual. FR becomes a subroutine inside the
routing ladder instead of the ladder itself. This is the cheapest possible form of "each
route aware of the others": awareness by SEQUENCE. Composes with S2 (deterministic
precision passes stay first; staged-FR tiers the *remaining* FR work). Risk: more FR wall
time (2-3 shorter runs ≈ one long run — measure); the protect mechanism is already proven.
**Effort: days. Prereq: S2 landed. Evaluation: pinned-seed + blind panel.**

### A2. SNAG→CONSTRAINT COMPILER: close the loop inside one wave
Today a gate failure ranks a candidate low and a human (me) reads reasons between waves.
The reasons are already STRUCTURED (refs, nets, distances, loci). Compile them
mechanically into next-iteration constraints: pin-escape failure on U10 → a spacing ask
around U10's cluster; kelvin-reach fail → the seat's inner_tap directive; courtyard-edge
fail on C50 → a margin bound for its region. The deterministic sibling of the intent seat
(which stays for the judgment-shaped proposals). The pass journal (S1) gives failures a
pass address, so each snag routes to the pass that owns the fix — the escalation ladder
becomes a wiring diagram instead of prose. **Effort: days. Prereq: S1's journal.**

### A3. HAND-CELL EXTRACTOR: blueprints from the boards we already trust
P4 needs cell templates. The best templates exist on shipped copper: the 12vhpwr lane
cell (shunt→RC→INA240, rigid column), the hub's port cell, the eps sense cell. Build the
extractor: given a board + a cell's refs, lift relative placement AND internal routing
into a parameterized template (net-role slots, pitch), stampable by P4 (KiCad-9
multichannel is the GUI-parity precedent). Hand excellence becomes direct pipeline
actuation, and the blind-audit standard ("does it look hand-routed?") is approached by
construction — it IS hand routing, replayed. **Effort: days-week. Prereq: none (P4
consumes it when S3 lands).**

### A4. GUI-PARITY LOCKS: the human as a pass executor
Emit pass state as NATIVE KiCad artifacts: locked flags (already), groups per cell/
cluster, rule areas per region/reservation. Then the owner can open any pass-boundary
board in the GUI, execute or fix a pass by hand (the literature's judgment-heavy passes),
and the pipeline resumes from the result — locks and regions surviving the round trip.
The pass ladder makes human-in-the-middle a FIRST-CLASS actuation instead of a terminal
handoff. Cheap: mostly serialization discipline. **Effort: days.**

## Tier 2 — targeted surgery on the weak tool (the honest "rewrite FR" answer)

### A5. FR MINIMAL PATCH SET (fork the jar, fix three measured wounds)
We pin open-source FreeRouting 1.7.0 (sha-verified jar). A full rewrite (Rust or
otherwise) of a general rip-up detailed router is a decade-class project and the wrong
target. But THREE measured, specific defects are patch-sized in FR's own Java:
1. **No seed control** — measured ±30 unconn noise, R-01's diversity problem, "no -seed
   flag in FR 1.7.0" printed on every run. Threading a PRNG seed through its Monte-Carlo
   choices is a contained patch.
2. **Netclass widths ignored** — measured (routes everything 0.2mm); the DSN carries the
   classes; honoring them is a rules-plumbing patch.
3. **Locked-wire semantics** — we work around fix-vs-protect by rewriting the DSN; native
   respect would remove a fragile hack.
Build our own pinned patched jar (the FR-01 version-parametric machinery already supports
alternate jars + hashes). Each patch lands separately behind an A/B. **Effort: 1-2 weeks
total across the three, Java. Highest value: the seed patch (kills the measurement noise
that costs every ablation run statistical power).**

### A6. RESIDUAL ROUTER, OURS (milestone-gated — the real successor path)
The pass ladder + staged-FR shrink FR's remaining job toward: "connect low-criticality
2-pin nets on a mostly-locked board." That residual problem is 10× smaller than general
routing — and we already own its global half (cec_coord_router, GPU, 8.1×). The missing
half is corridor-constrained DETAILED realization (45° lattice legalization, pad entry,
clearance) — hard, but bounded when each net has a negotiated corridor and locked
surroundings. Gate: build only when (a) staged-FR + precision passes are landed and (b)
an A/B shows FR is the remaining quality/wall-clock bottleneck. Then FR becomes optional
per-net (escalate to it on refusal), then vestigial. Rust vs Python/cupy: the kernels are
grid ops (GPU already); Rust buys determinism + packaging, not algorithmic speed —
decide at build time, not now. **This is the honest version of "remake FreeRouting":
shrink its job until replacing it is small, then replace it from the outside in.**

## Tier 3 — solver-grade subproblems the boundaries create

### A7. PER-REGION EXACT PLACEMENT (ILP/branch-and-bound on small sets)
Post-P4, a region holds ~5-15 free parts with hard bounds and a clean objective
(adjacency + escape + gaps). That is EXACT-SOLVER territory (ILP or even brute
permutation for tiny sets) — provably-optimal micro-placements where today's anneal
guesses. The same shrink argument as A6, applied to placement. Batchable per region, per
candidate, on CPU. **Effort: medium; prereq S1 boundaries. The anneal remains for the
global macro stage only.**

### A8. GPU BATCH ANNEAL over the vectorized cost (the placer-port rung 2, re-aimed)
The legalize/anneal cost is now numpy arrays (12.3× landed). cupy-batching thousands of
anneal chains per REGION (not per board) multiplies P7's search within pass boundaries —
the search-scale lever from the placer-port verdict, made cheap because regions are small.
**Effort: small once A7's region framing exists.**

## Cross-cutting hygiene the ladder exposes

- **A9. kipy/IPC migration for zone ops** — the SWIG footgun class (zone removal
  segfaults, fill-in-fresh-process dances) has a supported successor in KiCad 10's IPC
  API (see memory kicad-integration-landscape: refill_zones). Adopt it for the pour/fill
  passes first; keep SWIG elsewhere. Removes a whole footgun family from the pass code.
- **A10. Per-pass blind-audit hooks** — the blind protocol generalizes below the whole-
  board level: any boundary can emit its artifact pair for a blinded owner call
  (placement-stage blinds next). The owner's eyes found 3 real defects in one session;
  make that a per-pass instrument, sparingly.

## Ranked shortlist (my recommendation)

1. **A5-seed (FR seed patch)** — kills the ±30 measurement noise under EVERY future A/B;
   makes all other evaluations sharper. Do before the next big ablation cycle.
2. **A1 staged-FR** — the biggest coordination win per unit effort; pure existing
   machinery.
3. **A2 snag→constraint compiler** — turns every wave into 2-3 waves' worth of learning.
4. **A3 hand-cell extractor** — feeds P4/S3; converts owned excellence into actuation.
5. **A4 GUI-parity locks** — cheap, unlocks the human pass-executor.
6. A7 → A8 → A6 in that order, each gated on the previous showing the bottleneck moved.

_Registered in docs/pipeline-solver-roadmap.md (the standing place). Nothing here starts
without the owner's go except where an item is already covered by the S1/S2 mandate._

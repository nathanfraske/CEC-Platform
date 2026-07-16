# MCP tool wishlist — from the ENT hub sheet-03/04 capture session (2026-07-16)

Owner ask (2026-07-16, mid-session): a running list of MCP tools worth standing up for
repetitive actions actually hit this session, landed with the sheet-03 commit. This is a
wishlist for triage, not a build order — nothing here has been implemented. Every entry
below is backed by a concrete count/cost from THIS session's real work (captures of
hub-enterprise sheets 04-storage and 03-compute-rails), not a speculative "would be nice."

Format per tool: name, the repetitive action it replaces (with evidence), proposed
input/output contract, which existing script it would wrap/extend, effort class (S/M/L).

---

## 1. `wire_pin_coincidence` — flag every pin sitting on a wire's path, endpoint or not

**Repetitive action + evidence.** Two real, opposite-sense bugs this session both boiled
down to the SAME underlying geometric fact (a pin's coordinate coincides with a drawn wire
segment) but with opposite implications, and both took a multi-step MANUAL investigation to
find:
- 04a's `/RESET` pull-up: a hand-drawn 2-segment wire's INTERIOR passed through R401 pin 1
  (a different net's pin) — an accidental short. Found only by computing pin_abs_rot
  coordinates by hand in a throwaway script, cross-referencing against a dumped wire list,
  three separate `Bash` calls each writing a fresh ad-hoc Python probe.
- 03a's `SW_CORE` bus: the OPPOSITE failure — 4 of 8 same-net pins sat on a bus wire's
  INTERIOR (not at a segment endpoint) and so did NOT connect at all, each reading
  `unconnected-(...)` in the flattened netlist. Found by exporting the netlist, checking
  each pin's net membership one at a time (8 separate lookups), noticing 4 were isolated,
  then re-deriving from scratch why (another fresh probe script computing exact wire
  endpoints vs. pin coordinates).
Between the two, this class of bug cost roughly 8-10 tool calls of manual coordinate math
and netlist grep that a single deterministic checker would have caught in one call.

**Contract.** Input: a `.kicad_sch` leaf path. Output: a list of `{pin: (ref, num), wire:
uuid, kind: "interior-short" | "interior-unconnected" | "endpoint-ok", coincident_net,
declared_net}` — for every pin whose coordinate lies exactly on any drawn wire's path,
report whether it's at a true segment endpoint (connects) or a mid-span interior point
(does NOT connect per kicad-cli's own connectivity rule, verified empirically this
session), and whether the wire's OWN declared net (from a neighboring label/endpoint)
matches the pin's net from the leaf's `nets` dict. A mismatch at an interior point =
accidental short; a match at an interior-only point = the pin will read unconnected.

**Wraps/extends.** `cec_sch_layout.py`'s existing `_extract_wires`/pin-position helpers
(`pin_abs_rot` is already in `cec_sch_layout.py`); would sit naturally next to
`check_overlaps`/`check_sheet_bounds` in `cec_sch_gates.py`.

**Effort.** M — the geometry primitives (wire extraction, pin_abs_rot) already exist; the
new work is the coincidence scan + endpoint-vs-interior classification + net-membership
cross-check.

---

## 2. `root_sheet_box_overlap` — preflight two `(sheet ...)` boxes overlapping on one page

**Repetitive action + evidence.** The single most expensive investigation this session:
04-storage's root-level box (geom `(110,120,70,90)`) overlapped the "08-secio-aux"
placeholder box, and kicad-cli's flattened netlist silently MERGED five unrelated nets
across sheet boundaries — even though the overlapping placeholder box carries ZERO
declared pins. Root-caused only by bisection: exporting 04-storage.kicad_sch standalone
(clean) vs. through the real root (merged), isolating that the ONLY difference was this
box's placement, then confirming by moving it and re-checking. That took roughly 6-8 tool
calls (netlist exports, diffs, a geometry recompute, a second netlist export to confirm
the fix) for something a straight rectangle-intersection test over the root page's own
`(sheet ...)` blocks would answer instantly. This bug class is severe (silent netlist
corruption, not a visible rendering glitch) and is EXPLICITLY flagged in FOLLOWUPS.md as a
standing gotcha for sheets 03/02 to watch for — a preflight tool would retire that whole
class of risk rather than relying on every future agent remembering the warning.

**Contract.** Input: the root `.kicad_sch` path. Output: a list of `{box_a: sheetname,
box_b: sheetname, overlap_rect}` for every pair of `(sheet ...)` boxes (captured OR
placeholder) whose rectangles intersect, regardless of pin count. Exit non-zero on any
finding. No netlist export needed — pure geometry over the root file's own `(sheet ...)`
`(at ...)` / size fields.

**Wraps/extends.** A small new function in `cec_sch_gates.py` (same module as
`check_region_containment`/`check_sheet_bounds`, which already parse sheet/region
rectangles) — the rectangle-overlap primitive (`_rects_overlap`) already exists there for
region-vs-region checks; this just applies it to `(sheet ...)` boxes instead.

**Effort.** S — the geometry helpers already exist in the same file; this is mostly
plumbing a new box-extraction pass through the existing overlap primitive.

---

## 3. `escape_safety_scan` — flag generator-emitted property/text values that would break
the s-expression they're embedded in

**Repetitive action + evidence.** The single most expensive TOOLING investment this
session: a property string (`C308`'s `Description`, containing a literal, unescaped `"`
character around `"50-100pF... reduce noise pick-up"`) silently corrupted an ENTIRE leaf
file from that point onward — `kicad-cli` just reported the opaque "Failed to load
schematic" with no line/column. Root-caused only by writing a from-scratch
delta-debugging minimizer (a ~40-line bisection script, built and run twice) that
progressively removed top-level s-expr blocks until the minimal failing subset (exactly
one symbol instance) was found. That is easily the most expensive single diagnosis this
session (a dedicated custom tool built ad hoc, ~10 tool calls). Once found, fixing the ONE
instance still required a project-wide `grep '\\"'` sweep to catch three MORE
identically-shaped landmines already sitting in the same not-yet-committed file. A
pre-emit or post-emit scanner would have caught this in one call, before ever touching
`kicad-cli`.

**Contract.** Input: either (a) a generator source file (scan every string literal passed
to `add_part(..., props={...})` / `c.note(...)` / `c.caption(...)` for a literal `"`
character that isn't the deliberate outer delimiter), or (b) a generated `.kicad_sch`
(scan every `(property "..." "...")` / `(text "...")` value for an unescaped `"` — i.e. a
quote not immediately preceded by an odd run of backslashes). Output: `{file, line/byte
offset, offending value, context}` for each hit. Prefer (b) — it also catches a
LIBRARY-provenance string that already contains a stray quote before it ever reaches a
generator, not just this project's own new content.

**Wraps/extends.** New, standalone — nothing in the existing toolchain scans for this
today (kicad-cli itself doesn't surface it usefully, hence the opaque failure). Could live
in `cec_sch_gates.py` next to the other structural checks, or as a `cec_sch.py`
helper callable straight from a generator's own emit path before it ever writes bytes to
disk (catch-at-source, not catch-after-the-fact).

**Effort.** S — a single regex pass (`re.search(r'(?<!\\)"(?!\s*\)|\s*\\n)', ...)`-shaped,
tightened against real false positives) per candidate string; no geometry, no pcbnew.

---

## 4. `symbol_pin_table` — dump a vendored symbol's pin map as structured data

**Repetitive action + evidence.** Wrote a fresh ad-hoc Python regex parser to dump a
symbol's pin table (number, name, electrical type, local position) directly from a
`.kicad_sym`/embedded `lib_symbols` block SIX separate times this session (MIC22705YML-TR,
twice — the first regex silently failed and needed a rewrite with proper `carve()`-style
paren tracking; TPS3839DBZ; TPS7A2018PDBVR/TPS7A2050PDBVR; R_Small's local pin geometry
during the 04a short investigation; W25Q256JVFIQ for a cross-check). Every one of these
was written fresh in the moment because the regex needed to handle the `(pin TYPE line
(at X Y ANG) (length L) (name "..." (effects...)) (number "..." (effects...)))` nesting
correctly, and a naive single regex kept failing on the intervening `(effects ...)` block
— the SAME mistake, re-made and re-fixed, multiple times.

**Contract.** Input: library nickname (or raw `.kicad_sym`/`.kicad_sch` path) + symbol
name. Output: `[{number, name, electrical_type, at: (x,y,ang), length}]`, plus the
symbol's own `pin_names`/`pin_numbers` hide/offset settings (relevant to the QFN pin-name-
overlap fix this session also needed). This is pure read-only introspection — genuinely
low-risk to stand up.

**Wraps/extends.** `cec_sch.py` already has `symbol_block`/`pin_table`/`load_symbols` —
`pin_table` almost does this today but returns only `(x,y,angle,length)` keyed by number,
dropping the name/electrical-type/hide fields that mattered for BOTH bugs this session
(the RESET short needed exact positions; the pin-name-overlap fix needed to know
`pin_names` had no `hide` flag). This tool is close to just exposing `pin_table` plus a
small amount of `cec_sch_layout.py`'s already-written `_parse_lib_pin_geometry`-style
logic (used internally by the overlap checker) through one clean interface.

**Effort.** S — the underlying parsing already exists in two different forms across
`cec_sch.py` and `cec_sch_layout.py`; this is consolidating and exposing it, not writing
new parsing logic.

---

## 5. `verify_sheet` — run the full six-gate verification protocol for one board in one call

**Repetitive action + evidence.** Ran the SAME four-command sequence (checker script,
`--check-overlaps` per file, `--sheet-bounds` per file, `cec_sch_lint.py` across the whole
hierarchy) as 4+ SEPARATE tool calls, roughly 5 full times this session (once per real fix
round: SW_CORE bus, pin-name hide, `_unescape` fix, paper-size bump, final confirmation),
each round needing the same ~7-10 line boilerplate re-typed (the file list changes slightly
each time; the git-revert-drift dance in #6 below has to run first or the checker reads
stale committed content). A single wrapper that runs all six protocol items for a named
board and returns one pass/fail summary (with per-gate detail on failure) would collapse
this into one call per verification round instead of 4+.

**Contract.** Input: board directory (e.g. `hubs/hub-enterprise`) + a list of leaf/parent
files just touched. Output: one structured report — `{erc: {classes: [...], unexpected:
[...]}, netlist_assertions: "delegates to the board's own check_*.py — pass/fail + tail of
output", overlaps: {file: count}, sheet_bounds: {file: count}, lint: {file: {errors,
warns, metrics}}}`, plus an overall `ok: bool`. Does NOT replace the board-specific
assertion script (`check_hub_ent_sch.py` etc. stay hand-written and board-aware) — it just
orchestrates running it alongside the four generic gates instead of the caller doing so by
hand every time.

**Wraps/extends.** Pure orchestration over `kicad-cli sch erc`, the board's own
`check_*.py`, `cec_sch_layout.py --check-overlaps`, `cec_sch_gates.py --sheet-bounds`, and
`cec_sch_lint.py` — no new checking logic, just a single entry point.

**Effort.** M — mostly plumbing (subprocess orchestration + report shaping), but has to
stay board-agnostic (discover the board's own `check_*.py` by convention) to be worth
building once rather than per-board.

---

## 6. `revert_unrelated_drift` — restore every file EXCEPT an explicit keep-list to HEAD

**Repetitive action + evidence.** After every one of ~6 regenerations this session, ran
the identical 23-file `git checkout HEAD -- <path> <path> ...` incantation to revert
incidental UUID/format churn on already-committed leaf files the generator touches on
every run but that weren't part of the CURRENT change (a documented, established, and
apparently permanent characteristic of re-running `gen_hub_enterprise.py` — some elements
get fresh random UUIDs on every run regardless of whether their content logically
changed). Retyping (or re-pasting) the same 23-path list six times is exactly the kind of
mechanical, error-prone-under-fatigue action a small tool removes entirely — a single
wrong omission from that list either leaves stray unrelated diffs in the working tree
(caught, but wastes a review cycle) or, worse, accidentally reverts something that SHOULD
have been kept (a real risk if the keep-list itself changes sheet to sheet, as it does:
04's files needed keeping in the 04 session, reverting in the 03 session).

**Contract.** Input: an explicit list of paths to KEEP as-is (the files intentionally
changed this round) + a search root (e.g. `hubs/hub-enterprise/`). Action: `git checkout
HEAD --` every OTHER modified-but-tracked file under that root not in the keep-list.
Output: the list of paths reverted, for the calling agent to sanity-check against its own
intent. Read-only relative to the keep-list (never touches untracked/staged-new files).

**Wraps/extends.** A thin wrapper over `git status --porcelain` + `git checkout HEAD --`
— no schematic-specific logic at all; could live as a tiny standalone script
(`scripts/revert-unrelated-drift.sh <root> <keep-file-1> <keep-file-2> ...`) rather than a
full MCP tool, if that's a cheaper way to ship the same win.

**Effort.** S — almost pure shell; the only real "logic" is safely diffing a keep-list
against `git status`'s own modified-file list.

---

## Lower-priority / noted but not written up in full

- **Standalone single-file load smoke test** ("does this `.kicad_sch` even parse,
  independent of the root hierarchy") — used 3-4 times this session as a fast first
  triage step before reaching for the heavier bisection tool (#3 above). Likely not worth
  a dedicated tool on its own; folding a `--smoke` mode into #3's scanner (or just always
  running `kicad-cli sch export netlist` on the single file as #3's own first step) covers
  it for free.
- **Netlist diff between two generator runs** ("did net X's membership change between the
  broken and fixed version") — used informally a handful of times verifying fixes actually
  worked (e.g. confirming SW_CORE pins 9/10/21/22 rejoined the net after the waypoint fix).
  Real, but lower frequency than the six items above; worth a look once #1 exists, since a
  wire-pin-coincidence report before/after a fix would often answer the same question more
  directly than a raw net diff.

---

## Construction tools — where the building time actually went

Owner follow-up ask (2026-07-16): the six tools above skew toward *detection/debugging* —
catching a mistake after it was made. That's real work, but it's the reactive half. This
section is the affirmative half: while actually BUILDING sheets 04 and 03 (not fixing them),
where did minutes and tool calls go on plain mechanical construction labor — the kind of
thing a direct one-call primitive should just do, instead of a generator author re-deriving
it in Python by hand every time? Same per-tool discipline as above (name, the construction
action collapsed, counted evidence from this session, a small one-job contract, what it
wraps, S/M/L effort) — ranked by construction-time saved, most first. Still a wishlist for
owner triage; nothing here has been implemented.

### C1. `scaffold_leaf` — register a new leaf in one call instead of nine

**Construction action collapsed + evidence.** Adding ONE new leaf to a thin-parent sheet
touches at minimum **nine** separate dict/list sites in `gen_hub_enterprise.py`, confirmed
by grep against the sheet-03 subtree actually added this session: the `leaf03(id_, filename,
sheetname, desc)` registration call itself, `SHEET03_LEAF_IDS`, `leaf_page_03` (a page-
number entry), `LEAF_PAPER_03` (paper-size entry — this one silently defaulted wrong once,
A4 then bumped to A3 after a content-didn't-fit discovery on sheet 04's eMMC land), the
`GLOBAL_NETS_03` entry (only if the leaf carries a project-wide global net), `PARENT_PINS_03`
(with a hand-written `assert` that has to be kept in sync with the leaf's own
`hier_exports`), `BOX_03` (the root-page placement rectangle — see C3 below, its own manual
arithmetic), `leaves_for_parent_03` (the list threaded into `build_thin_parent`), and, if the
leaf exports to root, a `HIER_EXPORTS_03`/`ROOT_EXPORT_NETS_03` entry. Sheet 03 alone added
FOUR leaves this session (03a/03b/03c/03d), so this nine-touch dance ran essentially four
times over, and a single missed or stale site (the `PARENT_PINS_03` assert existing
specifically because a mismatch there silently breaks the parent-pin wiring) is exactly the
class of error that cost real debugging time in tools #1/#2 above.

**Contract.** Input: `register_leaf(sheet_id, leaf_id, filename, sheetname, desc,
hier_exports=None, global_nets=None, size=(w_units, h_units))`. Output: appends/updates every
one of the nine sites above from that single call — derives the page number from sequence
position (not a hand-picked string), derives a non-overlapping `BOX` rectangle by packing
against the other already-registered leaves' boxes for that sheet (see C3), and cross-checks
`hier_exports` against `PARENT_PINS` at call time instead of via a separate `assert` written
by hand later. Raises immediately (not at generation time) if `hier_exports` names collide
with an already-registered net elsewhere in the same sheet without `global_nets` covering it.

**Wraps/extends.** Sits in front of the existing `leaf03`-style per-sheet helper pattern and
`build_thin_parent`/`build_leaf` in `cec_sch_compose.py` — no new placement or netlist logic,
just a single call that fills in the nine call-sites the generator currently hand-maintains
as parallel dicts/lists keyed by the same leaf id.

**Effort.** M — the individual site-writes are trivial, but deriving a correct non-
overlapping box automatically (today done by hand, see C3) is the one piece of real logic.

---

### C2. `net_by_pin_pattern` — wire a symbol's matching pins to a rail in one call

**Construction action collapsed + evidence.** `compose_core_buck` (03a) hand-wrote **nine**
separate `lf.net(...)` calls enumerating which of MIC22705YML-TR's 24 pins belong to which
rail — e.g. `+5V_SYS` needed pins `1, 6, 13, 18, 17` (PVIN×4 + SVIN) picked out by hand from
the datasheet's pin table and copied into a Python tuple; `GND` needed `16, 7, 12, 19, 24, 25`
(PGND×4 + SGND + the exposed pad) similarly hand-picked; `SW_CORE` needed all eight switch
pins `8, 9, 10, 11, 20, 21, 22, 23`. This is exactly the transcription step that later caused
the SW_CORE bus bug (tool #1 above) when four of those eight hand-listed pins didn't land on
an actual wire-segment endpoint. The *reading* half of this already has a natural home (tool
#4, `symbol_pin_table`, dumps the structured pin list) — this is the missing *writing* half:
given that same structured table and a filter, emit the net call directly instead of a human
re-typing filtered pin numbers into a tuple by hand.

**Contract.** Exactly the shape the owner's own ask named:
`net_by_pin_pattern(symbol, pattern, net_name) -> list[(ref, pin_num)]` — pattern matches
against pin NAME (regex, e.g. `r"^PVIN$|^SVIN$"` or `r"^SW\d*$"`), returns (or directly
constructs) the full ball list for `lf.net(net_name, *balls)` in one call, with the option to
pass multiple `(pattern, net_name)` pairs so a single call can dispatch ALL of one symbol's
pins to their respective rails/buses at once (covering PVIN/GND/SW/FB/COMP/EN in one shot for
a part like this).

**Wraps/extends.** Directly composes with tool #4's `symbol_pin_table` (that IS the pin
source this needs) plus `Leaf.net`; no new parsing, just a regex filter + tuple-builder
sitting between the two.

**Effort.** S — thin glue over an already-planned tool (#4) and the existing `net()` call;
the only design question is the multi-pattern-dispatch convenience form.

---

### C3. `pack_root_boxes` / waypoint-list helper — remove hand-computed (x,y)/pitch arithmetic

**Construction action collapsed + evidence.** Two distinct flavors of manual coordinate math
recurred all session: (a) **root-page box placement** — `BOX_03 = {"03a": (16,16,24), "03b":
(110,16,24), "03c": (204,16,24), "03d": (298,16,24)}` is four rectangles hand-spaced 94 units
apart, sized to clear both the leaves' own content AND every OTHER already-committed sheet's
root box (verified disjoint by a hand-written comment enumerating every existing box on that
page — exactly the class of bug tool #2, `root_sheet_box_overlap`, exists to catch *after the
fact*; this tool would prevent it *before* generation by packing automatically); (b) **bus/
wire waypoint lists** — the SW_CORE fix required writing out every intermediate pin's x-
coordinate by hand as an explicit waypoint (`c.wire((87,101),(89,101),(91,101),(93,101),
(115,101),(115,90),(128,90))` and its mirror), because a bus wire only actually connects at
points that coincide with a real pin (the connectivity rule tool #1 exists to detect
violations of). Both are the same underlying labor: a human computing "where does this
rectangle/segment need to sit so it doesn't collide with X, Y, Z which are already placed
here" instead of a packing/routing primitive doing it.

**Contract.** Two small, separable primitives rather than one: `pack_root_boxes(existing:
list[rect], new_sizes: list[(w,h)]) -> list[rect]` (first-fit or shelf-packing against the
already-placed rectangles, returning boxes guaranteed disjoint — feeds directly into C1);
and `bus_waypoints(pins: list[(ref,num)], axis="x"|"y") -> list[(x,y)]` (given a list of pins
that must all land on one bus wire, emit the full Manhattan waypoint list with every pin's
own coordinate as a stop, instead of a human hand-copying each pin's position into the
`c.wire(...)` call and risking a skipped one).

**Wraps/extends.** `pack_root_boxes` sits next to `cec_sch_gates.py`'s existing rectangle-
overlap primitive (`_rects_overlap`, already used by #2) — same geometry, applied
generatively instead of only as a post-hoc check. `bus_waypoints` wraps `cec_sch_layout.py`'s
`pin_abs_rot` (already used for exactly this coordinate math in tool #1's investigation).

**Effort.** M for `pack_root_boxes` (shelf-packing has edge cases once boxes vary a lot in
size — sheet 03's four boxes were uniform, which made hand-spacing tractable, but that won't
always hold); S for `bus_waypoints` (pure coordinate lookup + list-building, no packing
decision).

---

### C4. `leaf_finalize` — collapse the hier_exports/powerflag/io()-column boilerplate

**Construction action collapsed + evidence.** Every non-stub leaf this session ended with
the same three-part pattern, hand-written each time: a `lf.hier_exports = {...}` dict, a
`lf.powerflag_nets = [...]` list, and a matching `c.io(net, side)` call for each exported
net — three separate statements that all have to agree with each other and with the net
name actually used inside the leaf's own `lf.net(...)` calls (03a needed this once for
`+1V0_CORE`, 03d once for `+3V3_MPFS`). It's a small amount of typing per leaf, but it's
pure boilerplate with a real cross-consistency requirement (a typo in any one of the three
either silently drops the export or produces the mismatched-hier-label ERC class this
session's `KNOWN_BENIGN` dict has to keep classifying).

**Contract.** `leaf_finalize(lf, c, exports: dict[net, (ref, pin)], side="left"|"right",
powerflag: list[str] = None)` — writes `hier_exports`, derives `powerflag_nets` (defaulting
to any net whose name starts with `+`/is in a small known-power-prefix set, override-able),
and calls `c.io()` for each exported net in one pass, so the three statements can never drift
from each other because there's only one call site.

**Wraps/extends.** Thin convenience layer directly over `Leaf.hier_exports`/
`Leaf.powerflag_nets`/`_Compose.io` — no new capability, purely collapsing three
already-existing, already-correct primitives that are today invoked separately by hand.

**Effort.** S — no new logic, just bundling three existing calls behind one signature.

---

### C5. Archetype discoverability — `divider_chain` existed and wasn't reached for

**Construction action collapsed + evidence.** 03a's FB feedback divider (R301/R302 + the
mid-tap wire into U301's FB pin) was hand-built from scratch — individual `add_part` calls
for both resistors plus a manual wire from the tap to the FB pin — even though
`cec_sch_archetypes.py` already ships `divider_chain(c, rt, rb, x, y_top, tap=None,
tap_ang=180, ...)` (confirmed by direct read this session: it places exactly two resistors
at a fixed pitch and wires `rt` pin 2 -> tap -> `rb` pin 1, i.e. precisely this pattern) and
is already imported into `gen_hub_enterprise.py` as `arch`. This isn't a missing capability —
it's a **reach-for-it gap**: nothing surfaces "a two-resistor-divider-into-an-IC-pin pattern
already has a one-call archetype" at the moment of hand-building one, short of already
knowing the archetypes file well enough to remember it, or re-reading its full source. The
same gap likely applies to `decoupler_bank` (about to matter directly for sheet 02's MPFS
decoupling per the owner's standing directive) and `protected_rail`.

**Contract.** Not a new checking/building tool so much as a discovery aid:
`suggest_archetype(part_kind, pin_roles) -> list[(archetype_name, one_line_usage)]` — given a
coarse shape ("two passives in series with a mid-tap driving a feedback/reference pin", "N
decoupling caps fanned off one rail pin") return the matching archetype name(s) plus their
exact call signature (so no source-diving is needed to use it correctly), or — cheaper —
just a short indexed docstring/table at the top of `cec_sch_archetypes.py` itself listing
each archetype's one-line shape + call shape, so a generator author scans one table instead
of reading six function bodies.

**Wraps/extends.** Either a tiny new lookup table over the existing archetype functions, or
literally just a documentation reorganization of `cec_sch_archetypes.py` — genuinely the
cheapest item on this list to ship in some form.

**Effort.** S (documentation-table version) to M (a real `suggest_archetype` matcher).

---

### Noted, lower priority

- **Per-part property-block boilerplate** (`Manufacturer`/`MPN`/`LCSC`/`Description` dicts
  repeated across all 45 `add_part(...)` call sites this file makes, 14 of them inside
  `compose_core_buck` alone) is real repeated STRUCTURE, but most of the actual VALUES are
  irreducibly per-part (looked up fresh from a datasheet or BOM-A row each time), so a tool
  here mostly helps only for parts already seen elsewhere in the project (a small
  `props_for_mpn(mpn) -> dict` cache lookup against already-sourced BOM lines) — real, but a
  smaller and more speculative win than C1-C5 above, so noted rather than written up in full.

---

Landed with the sheet-03 (compute-rails) commit, per the owner's 2026-07-16 ask (both the
detection/debugging list above and this construction-tools follow-up). See FOLLOWUPS.md for
the pointer entry.

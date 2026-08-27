# FreeRouting seed fork — `freerouting-1.7.0-cec1` (A5-seed)

A minimal fork of open-source **FreeRouting v1.7.0** (Apache-2.0) that adds a
`-seed <long>` CLI flag giving reproducible, steerable pseudo-randomness to the
autorouter. It closes the R-01 "no diversity axis" gap and removes the
run-to-run noise that contaminated every A/B measurement.

- **Base tag:** `v1.7.0` (upstream commit `ba0b23e89858bbfe7113df38f9de8dab090a0079`).
- **Patch (durable, committed):** `scripts/patches/freerouting-1.7.0-cec-seed.patch`
- **Build product (gitignored, WSL-ephemeral):** `build/fr-fork/freerouting-1.7.0-cec1.jar`
- **Owner ruling:** patch BASE is 1.7.0 (2.2.4 was gate-rejected 2026-06-10 — hangs on
  the 12vhpwr GND net; see `CLAUDE.md` action item -4).

The **patch is the source of truth**; the jar is a rebuildable product (`build/fr-fork`
is gitignored per the WSL-ephemeral-state policy).

---

## What the patch changes (5 files, +44/-2 lines of code)

| File | Change |
|---|---|
| `datastructures/Seed.java` *(new)* | Process-global master-seed holder. `Seed.mix(local)` returns `local` **unchanged** when no seed is set → default behavior is byte-identical to stock. |
| `gui/StartupOptions.java` | Parses `-seed <long>` (decimal or `0x` hex) and calls `Seed.set(...)`. Inserted **before** the `-s` (session-file) branch because `"-seed".startsWith("-s")` — otherwise the flag would be swallowed. |
| `autoroute/BatchAutorouter.java` | **The live diversity axis.** When `-seed` is set, the per-pass net/item routing **order** is shuffled with a seeded PRNG (salted by pass number). Opt-in; no-seed keeps the exact stock (sorted) order. |
| `autoroute/MazeSearchAlgo.java` | The rip-up maze `Random` is seeded via `Seed.mix(ripup_costs)` instead of `ripup_costs` alone. No-seed → identical to stock. |
| `autoroute/BatchOptRouteMT.java` | The `-mt >1` `ItemSelectionStrategy.RANDOM` shuffle (stock: wall-clock-seeded, a genuine nondeterminism source) becomes seed-derived when `-seed` is set; unseeded stock shuffle otherwise. |

### Why net-ORDER is the diversity lever (the key finding)

The obvious target — the maze rip-up `Random` (`MazeSearchAlgo:1180`, gated on
`ctrl.ripup_pass_no >= 4`) — is **dead code in the headless batch path**:
`AutorouteControl.ripup_pass_no` is initialized to `1` (line 120) and **never
reassigned** by `BatchAutorouter` (it sets `ripup_costs` at line 345 but not
`ripup_pass_no`). So `randomize` is always false and that `Random` is never
consumed during a CLI route. Seeding it alone yields **zero** diversity (measured).

Consequently the stock `-mt 1` batch path is **fully deterministic** — every seed
would give the identical route (that is precisely the R-01 "no diversity axis"
problem). The one *live* routing degree of freedom is **net ordering**, so that is
what the seed steers. This mirrors FreeRouting's own `ItemSelectionStrategy.RANDOM`,
which already randomizes item order — but only in the MT optimizer; the patch
extends the same idea, opt-in, to the main batch autoroute pass. The maze-`Random`
seeding is kept anyway (correct, harmless, and becomes live if upstream ever fixes
the `ripup_pass_no` bug).

### Guarantee: unflagged = stock

Every seeded site reduces to the exact stock expression when `-seed` is absent
(`Seed.isSet()==false` / `Seed.mix()` returns its argument). This was verified
byte-for-byte (leg 0b below): **patched, no `-seed`, is byte-identical to the stock
1.7.0 jar.**

---

## Nondeterminism sources found in FR 1.7.0 (audit)

Classified: **(a)** genuinely random / seedable · **(b)** hash-iteration order · **(c)** wall-clock.

| Site | Class | Verdict |
|---|---|---|
| `autoroute/MazeSearchAlgo.java:44,53,1179` — rip-up detour `Random`, seeded from `ripup_costs` | (a) | **Dead** in batch mode (`ripup_pass_no` stuck at 1). Seeded by the patch anyway. |
| `autoroute/BatchOptRouteMT.java:194` — `Collections.shuffle(item_ids)` **unseeded** (wall-clock `Random`) | (a) | Real nondeterminism, but only on `-mt >1` **and** `-is rand`. Seeded by the patch. |
| `datastructures/PlanarDelaunayTriangulation.java:29,56` — shuffle | (a) | Uses a **fixed** seed (`99`); already deterministic. Left stock. |
| `geometry/planar/PolygonShape.java:17,466,485` — `nextInt` | (a) | Uses a **fixed** seed (`99`); already deterministic. Left stock. |
| `datastructures/UndoableObjects.java:20` — item store | (b) | `ConcurrentSkipListMap` (sorted) → deterministic iteration. Not a source. |
| `board/Item.java` — `get_connected_set` / `get_unconnected_set` | (b) | `TreeSet` (sorted). Not a source. |
| `autoroute/BatchAutorouter.java:34` — `already_checked_board_hashes` `HashSet` | (b) | Membership-only, never iterated for decisions. Not a source. |
| `board/BasicBoard.java:165` — `diff_traces` `HashSet` | (b) | Count-only (contains/remove/size). Not a source. |
| `autoroute/BatchOptRouteMT.java:26` — `result_map` `HashMap` + thread completion order | (b)/(c) | MT-only path; thread-order nondeterminism the seed cannot fully fix. Pipeline uses `-mt 1`, so out of scope. |
| Per-connection `TimeLimit` (`BatchAutorouter:373` = `100000·2^(pass-1)` ms) and the pull-tight `TIME_LIMIT_TO_PREVENT_ENDLESS_LOOP = 1000` ms (`opt_changed_area`) | (c) | Wall-clock. **Budget left alone.** Not hit on the small EPS board (deterministic there); *can* feed decisions beyond stopping on large/congested boards — noted, not touched. |

`Math.random()`: none in the tree. `-oit` in 1.7.0 is the optimization-improvement
**threshold** (percent), **not** a time budget; the run is bounded by `-mp`
(max_passes). Neither is wall-clock.

---

## How to rebuild

FR 1.7.0 targets Java 17 and ships a Gradle **7.3** wrapper, which **cannot compile
on Java 21** (the host/container default). Use a local JDK 17 — do **not**
`apt`-install one system-wide.

```bash
cd /home/nathan/CEC-Platform

# 1. Clone the pinned base (gitignored working area)
git clone --depth 1 --branch v1.7.0 \
  https://github.com/freerouting/freerouting.git build/fr-fork
cd build/fr-fork

# 2. Apply the committed patch
git apply ../../scripts/patches/freerouting-1.7.0-cec-seed.patch

# 3. Local JDK 17 (Temurin), extracted under the fork (not system-wide)
curl -sL -o jdk17.tar.gz \
  "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse"
mkdir -p jdk && tar xzf jdk17.tar.gz -C jdk --strip-components=1

# 4. Build the fat executable jar
JAVA_HOME="$PWD/jdk" ./gradlew executableJar --no-daemon --console=plain

# 5. Name the artifact
cp build/libs/freerouting-executable.jar freerouting-1.7.0-cec1.jar
sha256sum freerouting-1.7.0-cec1.jar
```

**Jar reproducibility caveat (matters for hash-pinning):** the compiled bytecode is
fully reproducible — two independent builds from this patch produced **byte-identical
`.class` and resource entries** (3297/3298). The **only** differing jar entry is
`META-INF/MANIFEST.MF`, which bakes in `Build-Time` (build clock), so the jar
**sha256 changes per build**. Pin the specific jar that will actually be
distributed (below), or normalize the manifest for a stable hash.

---

## How to use it (CEC pipeline)

Point `cec_fr` at the jar with the environment variable — **do not edit
`scripts/cec_fr.py`'s `FR_RELEASES`** (another owner wires the registry entry):

```bash
export CEC_FREEROUTING_JAR=/home/nathan/CEC-Platform/build/fr-fork/freerouting-1.7.0-cec1.jar
```

`cec_fr.ensure_jar()` treats an explicit `CEC_FREEROUTING_JAR` as a trusted override
(hash logged, not pin-checked), so it runs the patched jar directly. To actually
*use* the seed, the FR invocation must add `-seed <n>`; `cec_fr.run_freerouting()`
currently only **logs** its `seed=` kwarg (`"no -seed flag in FR 1.7.0"`), so the
registry-wiring change is what threads `-seed` onto the command line. Until then the
patched jar behaves exactly like stock (default = no `-seed`).

Direct invocation (the exact shape `cec_fr._fr_command` builds, plus the new flag):

```bash
xvfb-run -a java -jar freerouting-1.7.0-cec1.jar \
  -de in.dsn -do out.ses -mp 10 -oit 30 -mt 1 -seed 1
```

### For the registry wiring (what the orchestrator needs)

- **Delivered jar:** `build/fr-fork/freerouting-1.7.0-cec1.jar`
  sha256 `375e36b8ee347c57127670c06aeaa650d562a0365b0a4ed6dd3634d215f103b1`
  (built with Temurin JDK 17.0.19; the canonical binary — copy it to a durable path
  and pin THIS sha, since a rebuild changes only the manifest timestamp).
- Base tag `1.7.0`, `min_java: 17`, runs `java -jar` (no app-image needed).
- A suggested `FR_RELEASES` key: `"1.7.0-cec1"`.
- The seed must be threaded onto the FR command line as `-seed <long>` (append to
  `_fr_command`'s arg list) for it to take effect.

---

## Verification (VERBATIM)

Env: `cec/routing:kicad10` container, Java 21, `xvfb-run`. DSN exported **once**
from `tests/golden/eps-8pin/eps8pin-module.kicad_pcb` via `cec_fr.export_dsn`
(`build/fr-fork/dettest/eps.dsn`, sha256 `2cbea65d002a89bf2a83f…`). Every FR run:
`-mp 10 -oit 30 -mt 1`, identical output basename in a separate workdir (so the
session name — which echoes the output filename — is not a spurious diff).

Stock jar sha256 `e6c5db33792a00f99799b1113bb9f5e1576731f885b069da8850520528f7ef8f`
(the pinned baseline). Patched jar sha256
`375e36b8ee347c57127670c06aeaa650d562a0365b0a4ed6dd3634d215f103b1`.

```
sha stock1:9c2819a72527a8bd stock2:9c2819a72527a8bd pdef:9c2819a72527a8bd \
    s1:35238a2ea52e5609 s2:d8199482709908cb s7:641aef9c5bed6ac5

(i)   STOCK run1 vs run2          : IDENTICAL
(0a)  PATCHED no-seed run1 vs run2: IDENTICAL
(0b)  PATCHED no-seed vs STOCK    : IDENTICAL
(ii)  PATCHED -seed 1 run1 vs run2: IDENTICAL
(ii2) PATCHED -seed 2 run1 vs run2: IDENTICAL
(iii) PATCHED -seed 1 vs -seed 2  : DIFFERENT
(iii2)PATCHED -seed 1 vs -seed 7  : DIFFERENT
(iv)  PATCHED -seed 1 vs no-seed  : DIFFERENT
```

Reading the results:

- **(0b) patched-default is byte-identical to the stock jar** — the "keep default
  exactly stock" requirement holds byte-for-byte (all three of stock1/stock2/pdef
  share sha `9c2819a7…`).
- **(ii)/(ii2) same seed → byte-identical** across runs — reproducible.
- **(iii)/(iii2)/(iv) different seeds → different `.ses`** (three distinct shas
  `35238a2e` / `d8199482` / `641aef9c`) — a real, seed-controlled exploration axis.
- **(i) stock run1 vs run2 → IDENTICAL** (honest deviation from the task's
  expectation). On the small EPS board at `-mt 1`, stock FR 1.7.0 is **already
  deterministic** (sorted collections + the dead maze `Random`). The measured
  ±30-unconn noise is a **`-mt >1` / large-congested-board** phenomenon, not a
  `-mt 1` small-board one — but stock nonetheless has **no seed diversity axis**
  (every seed → identical), which is exactly the R-01 gap this patch fills.

---

# cec2 addendum (2026-07-14) — `freerouting-1.7.0-cec2`

Owner GO ("do the surgery ... do the speedups and profile it"). cec2 = cec1 + three
**opt-in** flags; the unflagged-equals-stock guarantee is preserved (every new site
checks a `CecOptions` flag that defaults to stock behavior).

| Flag | File(s) | What it does |
|---|---|---|
| `-noecho` | `designforms/specctra/SpecctraSesFileWriter.java`, `datastructures/CecOptions.java` *(new)* | Skip unmodified user-fixed ("protect") wires in the SES — they were router INPUTS; echoing them creates re-import duplicates (reconcile measured ~130 strips/route). |
| `-maxstall <k>` **(EXPERIMENTAL — do not wire by default)** | `autoroute/BatchAutorouter.java` | Abort the batch route after `k` no-improvement passes. Bench 2026-07-14: the abort fires, but the post-route OPTIMIZER (improvement-bounded, not time-bounded) then thrashes on the incomplete board — the maxstall leg TIMED OUT at 900 s vs a 194 s full run. Completion (skip the optimizer on stall-abort) queued in FOLLOWUPS; the shipping pre-kill is EXTERNAL: watch the `CEC_PASS` lines and kill the JVM on plateau, which dodges the optimizer entirely. |
| `-progress` | `autoroute/BatchAutorouter.java` | One machine-readable line per pass: `CEC_PASS pass=<n> togo=<m> failed=<f> ripped=<r>` — the stage-0 pre-kill contract (replaces log-scraping). |

- **Patch (cumulative over v1.7.0, replaces applying cec1 separately):**
  `scripts/patches/freerouting-1.7.0-cec2.patch`
- **Jar sha256:** `149cebd88169be77f5ddc7e1d50284451204f10c088e5d7380859ab0395b7ce5`
  The cec2 patch removes the upstream build-user and build-clock manifest
  fields, freezes the generated `Constants.java` build date to the reviewed
  binary's date, disables file timestamps, and enables reproducible entry order.
  The reviewed digest is also compiler-platform specific: it is produced by
  Temurin **Windows x64** JDK 17.0.20+8. The corresponding Linux x64 JDK does
  not produce the pinned complete-JAR digest even with identical sources and
  version. `scripts/build-freerouting-cec2.ps1` pins and verifies the Windows
  JDK archive, build patch, and final JAR hash.
  (durable copies: `/mnt/e/toolchain/fr-fork/` + `build/fr-fork/`)
- **cec_fr wiring:** `-noecho` + `-progress` default ON where supported
  (`CEC_FR_NOECHO=0` reverts the echo for A/Bs); `-maxstall` opt-in via
  `CEC_FR_MAXSTALL=<k>`; the seed axis remains opt-in via `CEC_FR_SEED_AXIS=1`.
- Hash-exact rebuild from Windows PowerShell:

  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/build-freerouting-cec2.ps1
  ```

  The default output is
  `build/fr-fork/freerouting-1.7.0-cec2.jar`. The script builds in a disposable
  `%TEMP%` directory, validates both the JDK and JAR hashes, and removes the
  downloaded toolchain and Gradle cache when finished.

# cec3 addendum (2026-08-04) — `freerouting-1.7.0-cec3`

The fully guarded six-layer Hub exports a DSN larger than 512 KiB. Freerouting
1.7.0's generated scanner can refill and grow its buffer, but its hand-written
`next_string()` helper read the initial array directly and crashed at byte
524,288 before routing began. cec3 applies the incremental
`scripts/patches/freerouting-1.7.0-cec3.patch` after the cumulative cec2 patch.
The helper now refills and grows the existing buffer in place, preserving every
scanner position; it does not raise a fixed size ceiling or remove PCB guards.

- Linux/WSL build: `scripts/build-freerouting-cec3.sh`
- OpenJDK build pin: 17
- JAR SHA-256:
  `202136e7e73d5aa3e2a852bab186f71b67289a4068dee0804cb9c7b2efd8c7f7`
- Exact Hub proof: a 549,907-byte DSN completed parser, route, SES import, and
  KiCad board save with the cec3 artifact; cec2 failed at index 524,288.

# Teaching moment: the thermal "neck" that wasn't (2026-06-28)

**TL;DR — I spent a whole session designing a fix (a B.Cu mirror) for a thermal
problem that did not exist. The ~1435 °C "shunt‑funnel necks" were an artifact of
the solver pushing 40 A through 0.2 mm kelvin sense‑tap traces that carry no
current in reality. The owner caught it by demanding an ablation test. The board
is thermally fine (~62 °C). No mirror was ever needed.**

This is a post‑mortem on *how the wrong conclusion survived so long*, written so the
next agent (me included) doesn't repeat it.

---

## What happened (the arc)

1. **Premise (unverified):** `build-routed` "needed a B.Cu mirror" because the
   electro‑thermal solver showed ~1435 °C hot necks where the SENSEC pours funnel
   into the shunt. I had been treating this as the central design problem.

2. **"Show me the pours on the dash."** This kicked off a cascade of *real but
   peripheral* bugs, each of which I chased to ground:
   - The **GPU was never actually used** (`cudaErrorInsufficientDriver` → silent
     CPU fallback). I had earlier claimed it was "soak‑verified." Fixed by
     force‑recreating the routing container.
   - The dashboard was showing a **rejected intermediate board**, and had a
     **focus/board‑mapping bug**.
   - The thermal **render's color scale was crushed** by the hot necks, so the
     pours rendered near‑black ("not on the dash"). I fixed it three ways:
     percentile clip → dim copper‑shape base → cyan pour outlines.

3. **The owner's hypothesis.** "The tiny strips from the pins to the kelvin sense
   taps are carrying the full 40 A when they should carry none — you've fabricated
   the necks. Remove those traces and re‑run, and show me the pour as thermal
   pixels."

4. **The ablation test** (after two false starts — first I forgot to pass the
   currents, then I used a solve that skipped `_prepare_filled` so no current
   flowed, then I chased an `h_eff` red herring). With the *valid* solve:

   | | F.Cu peak |
   |---|---|
   | WITH the thin sense traces | **1067 °C** |
   | WITHOUT them (118 traces, 0.2–0.25 mm) | **62 °C** |

   The owner was right. The thin traces are on the SENSEC net, so the solver routes
   the cable current through them as the lowest‑area path → fake necks, while the
   wide pour sits cool and unused.

5. **Conclusion.** B.Cu mirror retired. The kelvin fix (`w5hxwefr4`) already removes
   these traces. Root cause is a **thermal‑model bug**: the solver injects net
   current through high‑impedance sense‑tap copper that physically carries none.

---

## Why the wrong conclusion survived (the real failure modes)

1. **I built a tall narrative on an unverified foundation.** Necks → mirror →
   cooling models → a multi‑turn render saga — all downstream of one unchecked claim
   ("the necks are real"). When the foundation is wrong, every downstream turn is
   wasted motion that also makes the conclusion *feel* more established.

2. **I ignored a physical impossibility.** Copper melts at 1085 °C. A 1435 °C steady
   state on a powered consumer board is not a hot spot — it's a board that would
   vaporize. That number alone should have screamed *model error*, not *design flaw*.

3. **I fixed messengers and called it progress.** The GPU bug, the wrong‑board bug,
   the color‑scale crush were all real and worth fixing — but they were rabbit holes.
   Making the dashboard "finally show the truth" is worthless when the truth it shows
   is a false model. A better view of a wrong answer is still wrong.

4. **I trusted the output without auditing the input.** I never asked "what current
   path is this solve actually modeling?" The answer — 40 A through a sense tap —
   was the whole bug, and it was one `print` away the entire time.

5. **I treated repeated domain‑expert pushback as something to re‑explain.** The
   owner questioned the *same* conclusion three times (the pours, the necks, the
   thin traces) and was correct every time. Each "are you sure?" I answered with a
   more polished version of the wrong story instead of stopping to test it.

---

## The practices to keep (what "good" looks like)

- **Ablation first, narrative later.** The instant you name a cause ("the necks"),
  prove it by removing it: does the result change? "Delete X, re‑run, compare" is
  the cheapest, most decisive tool there is. Don't design a fix for a cause you
  haven't isolated.
- **Treat physically impossible numbers as model bugs.** Fusing temperatures,
  negative resistances, 99% confidences — audit the model, not the design.
- **Audit a model's inputs before its outputs.** For a solver: what nets carry
  current, where are the sources/sinks, what's the assumed cooling (`h_eff`)?
  Print them. (`h_eff` and `_prepare_filled` both bit me here precisely because I
  didn't.)
- **A repeated challenge from someone who knows the artifact is a stop signal.**
  Not a prompt to re‑explain — a prompt to *test their hypothesis directly*, fast.
- **Don't let a tooling cascade hide the core question.** When peripheral bugs pile
  up, explicitly re‑ask the central question ("is the thing I'm fixing even real?")
  before sinking turns into the periphery.

---

## The technical finding (the actual bug being fixed)

`cec_thermal2d.solve_board_thermal` injects a net's cable current across the entire
current‑carrying net, **including high‑Z kelvin sense‑tap copper** (the INA
current‑sense input pads + any traces to them). The current should flow only along
the force path (connector → pour → shunt → pour → connector); the sense pads are
voltage taps and carry no current.

Fix (in progress, separate agent): exclude the INA current‑sense input pads as
current terminals so the thermal result does not depend on whether sense‑tap traces
happen to exist. Pad set (shared with `cec_score.kelvin_topology_faults`):
INA226/228/238 pads 9/10 (+8 Vbus); INA181/240 pads 3/4.

Gate for the fix: `build-routed` (which *still* has the thin traces) must solve to
~62 °C, not 1067 °C, with the bad traces present — i.e. the model becomes immune to
this routing artifact. Reproducer: `build/traptest.py`.

---

*Filed by the agent, at the owner's request, as a deliberate learning artifact.*

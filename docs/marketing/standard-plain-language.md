# Explaining CEC to someone who knows nothing — and has no reason to care yet

The technical sell sheet (`standard-bundle-sell-technical.html`) sells to someone who
already knows what a shunt and a 12VHPWR connector are. This doc is the opposite end:
**how you explain what CEC does to a normal person, and why they should care**, before
they know any of that. It's the messaging source for consumer copy, box text, a landing
page, or a 30-second pitch. Companion visual: `standard-bundle-plain.html`.

## The core problem to solve

A normal buyer doesn't want "power telemetry." Nobody wakes up wanting telemetry. They
want **their expensive PC not to die**, and they don't want to think about it. So we don't
lead with what CEC *measures* — we lead with what it *protects them from*, using the one
failure they've probably already seen with their own eyes.

## The hook: the melting cable they've already seen

The 16-pin GPU power connector melting on high-end graphics cards (RTX 4090 / 5090) is one
of the most-covered PC stories of the last few years. People who bought a $1,000–$2,000
graphics card have seen the photos of a charred, melted connector. That fear already
exists — we don't have to manufacture it, we just have to name the thing that watches for it.

> **The reason it melts:** one tiny pin quietly ends up carrying more current than the
> others, gets hot, and there is *nothing inside a normal PC watching for it.* CEC watches
> every pin, individually, and sees the imbalance building before it melts.

## The one analogy that does the work

**A smoke detector for your PC's power.** It's the whole pitch in five words:

- It sits quietly in the background.
- You never think about it.
- The one time it speaks up is the one time you needed it to.

(Backup analogy if the room is more car-brained: *"a check-engine light — except it tells
you exactly which cable, not just that something, somewhere, is wrong."* CEC is strictly
better than a check-engine light, so use it as a contrast, not the lead.)

## The tiers of copy

**One sentence (what it is):**
> CEC is a small monitor that watches your PC's power around the clock and warns you before
> a cable, connector, or power supply fails.

**Elevator (10 seconds):**
> You've seen the photos of melted graphics-card cables. It happens because one pin quietly
> carries too much current and nothing is watching. CEC is a little hub plus a few clip-on
> sensors that watch every power connection in your PC — like a smoke detector for your
> power — and warn you before a connector melts, a power supply browns out, or a part dies.

**Why you (the plain benefits — pick 3):**
- **Protects the parts that cost the most.** Your graphics card and power supply are the
  priciest, most failure-prone pieces in the machine. CEC watches exactly the connections
  that kill them.
- **Catches the famous melting-cable problem.** It measures each pin of the high-power GPU
  connector and spots the uneven load that leads to a melt — early, while it's still a warning.
- **No babysitting.** There's no dashboard to stare at. Green means everything's fine. If
  something's wrong, it tells you *what* and *where* — not just "something."
- **Sees trouble coming.** A power supply going bad, a connector heating up, a cable working
  loose — CEC notices the drift before it becomes a dead part or a crash mid-game or mid-render.

**What you actually do:**
> Plug the little hub into your PC, clip the sensors onto your power cables, and forget about
> it. It shows up on your computer like any other USB device — no separate app to install and
> babysit.

**What it physically is (if they ask):**
> A small hub and a few clip-on sensors that sit between your power supply and your
> components — like putting a meter on each pipe, so you know the moment one starts behaving
> wrong.

## The honesty line (keep it — it builds trust)

> CEC can't stop a failure from starting. But it's the difference between a heads-up and a
> dead $2,000 card.

## What to NOT say to this person

- No "rails," "shunts," "INA240," "per-pin current sensing," "CAN bus," "telemetry stream."
- No spec section numbers, no accuracy percentages, no sample rates.
- Don't ask them to read a chart. The average person bounces off a data table. Lead with
  the fear and the relief; the numbers are for the person who already leaned in.

## Who this framing is for vs. not

This is the **cold consumer** — someone who doesn't know they want it. The enthusiast who
already monitors their rig, and the buyer who came in through the melting-cable story
knowing the details, can be handed the technical sheet. This doc is specifically for turning
"why would I need that?" into "oh — I actually want that."

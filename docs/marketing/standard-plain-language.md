# Explaining CEC to someone who knows nothing, and has no reason to care yet

The technical sell sheet (`standard-bundle-sell-technical.html`) is for a buyer who already
knows what a shunt and a 12VHPWR connector are. This doc is the other end: how you explain
what CEC does to a normal person, and why they should care, before they know any of that.
It's the source for consumer copy, box text, a landing page, or a short pitch. Companion
visual: `standard-bundle-plain.html`.

## The purpose, stated plainly

Power is the one major system in a PC that is invisible and close to impossible to diagnose.
It's also what quietly kills expensive parts and causes the instability nobody can explain.
CEC's job is to make power visible, recorded, and diagnosable, so that when your machine
acts up you know the cause instead of guessing at it.

The melting graphics-card cable is the dramatic example everyone has seen. It is not the
whole pitch. The everyday purpose is bigger and less scary: your PC will stop being a black
box the moment something goes wrong with its power.

## The story that does the selling: the instability nightmare

Every enthusiast has lived this or watched a friend live it. The PC reboots at random. It
black-screens under load. It crashes in one game but runs fine in benchmarks. Stable on the
bench, dead in real use. The standard fix is a loop of misery: swap the power supply, reseat
every cable, RMA a part, and hope. Weeks of downtime and hundreds of dollars in guessed
hardware, because the fault is electrical, it happens at the connector, and no software can
see it.

CEC is the recorder that ends the guessing. It watches every power rail and every pin of the
high-power graphics connector the whole time the machine runs, and it keeps the record even
through a crash. When the problem happens, the answer is already written down: at this
moment, under this load, this rail sagged while the GPU pulled this much. You fix the real
thing instead of buying parts on a hunch.

## The analogies that land

- **A flight recorder for your PC's power.** Always recording. When something happens, you
  have the footage, not a mystery.
- **The diagnostic port your PC never had.** Cars have a port that tells the shop exactly
  what went wrong. PCs have nothing like it for power. CEC is that port.

Use the flight recorder as the lead. It carries the whole idea: always on, quietly recording,
and the value shows up the day something breaks.

## Answering the objections head-on

**"Why not just take it to a shop when there's a problem?"** The shop can't see intermittent
power faults either. They don't have your machine under your load for three days, so they
swap parts to fix and hand you a bill. Intermittent power problems are the classic "could not
reproduce, replaced the power supply, still broken." CEC is the recording that makes the
diagnosis exist at all. You bring the data, or the shop reads it, and the guessing stops.
Often you fix it yourself once you know: reseat the right cable, RMA the part that's the
real culprit.

**"Isn't the free software (HWiNFO and the like) the same thing?"** No. Software reads the
motherboard's and power supply's own sensors, which are inaccurate, can't see the graphics
connector pins at all, and die the instant the machine crashes. CEC measures the real current
at the real connector, on its own, and keeps the record through the crash. It's not a nicer
graph of the same numbers. It's the numbers that otherwise don't exist.

**"Why the hub? Why not just the graphics sensor?"** The sensors are dumb meters. The hub is
the brain, the memory, and the single connection to your PC. Only the hub can do the thing
that matters most: line up every rail at the same instant. "The GPU spiked and the 12V sagged
and the CPU rail dipped, all at once" is the answer you're after, and it's only visible if one
brain watches every sensor together. The hub also holds the recording (which survives a crash
that kills software) and runs on standby power, so it watches during boot, sleep, and
shutdown, which is exactly when a whole class of instability shows up.

**"Why the whole bundle instead of one sensor?"** A power fault usually isn't where the
symptom is. A graphics crash is often caused by the CPU rail or the power supply sagging under
total load. One sensor raises an alarm ("this pin is hot"). The full set gives the diagnosis
("this pin is hot because the power supply is sagging under total load"), which is a different
and correct fix. The 24-pin sensor also gives the whole-system view: real wattage, real
efficiency, and whether the power supply is big enough.

## The three things it does, so it's never "does nothing until I break"

1. **Shows health you can see.** Real measured wattage and rail behavior, all the time. People
   check home-energy monitors and fitness trackers for exactly this kind of ongoing readout.
2. **Records everything.** The recorder is always on, so a future problem is diagnosable
   instead of an event you can't reproduce.
3. **Warns early.** The failure-prevention part, including the melting-cable case. This is the
   only one that waits for trouble, and it's the cheapest slice of a $2,000 graphics card.

## The tiers of copy

**One sentence:**
> CEC watches your PC's power and records it, so when something goes wrong you know the cause
> instead of guessing.

**Elevator (about 10 seconds):**
> Random crashes and reboots under load are almost always a power problem, and no software can
> see it, so people swap parts and hope. CEC is a small hub plus a few clip-on sensors that
> record every power rail in your PC, even through a crash. When it acts up, the answer is
> already written down. It also catches the melting graphics-card cable before it melts.

**Why you (pick three):**
- **Stop guessing.** When your PC misbehaves, you get the cause, not a parts-swap loop.
- **Protects the parts that cost the most.** Your graphics card and power supply are the
  priciest and most failure-prone pieces. CEC watches the connections that kill them.
- **Catches the famous cable problem early.** It checks each pin of the high-power graphics
  connector and flags the uneven load that leads to a melt while it's still a warning.
- **No babysitting.** No dashboard to stare at. Green means fine. If something's wrong, it
  tells you what and where.

**What you do:**
> Plug the small hub into your PC, clip the sensors onto your power cables, and leave it. It
> shows up on your computer like any other device. No separate app to install and babysit.

**The honest line (keep it, it builds trust):**
> CEC won't stop a failure from starting. It's the difference between knowing the cause in
> five minutes and losing a weekend and a few guessed parts to find it.

## Who it's for, and who it isn't

It's not for a $600 office PC. Nothing in there is worth this. The value scales with how much
your hardware costs, how hard you push it (gaming, rendering, AI, mining), and how much
downtime hurts (a streamer, a freelancer on deadline, someone whose rig is the investment).
For that person, $250 is a small fraction of the graphics card alone, and one guessed part
swap already costs more.

## What not to say to this person

- No "rails," "shunts," "INA240," "per-pin current sensing," "CAN bus," "telemetry stream."
- No spec section numbers, accuracy percentages, or sample rates.
- Don't ask them to read a chart. Lead with the crash they've had and the guessing they hate.
  The numbers are for the buyer who already leaned in, and they get the technical sheet.

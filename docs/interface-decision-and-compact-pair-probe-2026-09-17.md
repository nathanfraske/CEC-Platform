# Interface decision and compact pair-portal hypothesis

## Required interface direction

The user was asked whether to permit limited growth of **both mating halves**
(and outlines if necessary), or keep the fixed dimensions and investigate
alternative terminals. No answer or growth/replacement authority has been
assumed. Pinouts, qualified land geometry and existing outlines remain unchanged.
Independent work on the other boards can continue while this is pending.

Fresh current-native screening is in
`build/current-interface-decision-basis-20260917.json`. It uses the canonical
hash-bound EPS and ATX inputs from
`build/additive-first-next-inputs-20260917.json`, not old placement candidates:

- EPS: SHA `3af9f2496c44474dc80eee9775596174f9480ace89853f3e463ab7add846aa01`,
  32 native terminal-to-terminal pad-copper report rows.
- ATX: SHA `2e45ff7fc4402a63074253cd65d3f584e8311dbb5b8ae285b9a370d6dc0e280c`,
  40 native terminal-to-terminal pad-copper report rows.

These are repeated native DRC report rows, not unique physical short counts.
The measured daughterboard identities are retained in the report. The separate
conservative zero-clearance projection exceeds the current last-datum limits by
1.5 mm on EPS and 2.4 mm on ATX. This includes conservative same-net/mixed-part
envelopes; it is not an exact mechanical minimum or proof that every imaginable
staggered interface is impossible.

The question cites the earlier **native pair-spacing trials**, which suggested
about 1.4 mm EPS / 2.2 mm ATX extra last-datum travel before additional margin.
Those figures and the projection above are different measurements, not
interchangeable recommended dimensions. Exact paired geometry, the auxiliary
header, edge clearances, stack access and physical sample qualification still
need verification. A screen is not permission to invent a screw-axis/Z transform
or move only one mating half.

## Completed compact-ground frontier

`build/compact-ground-frontier-20260917/report.json` confirms the one-round
placement search completed with **no accepted board change**. It evaluated 16
new poses / 30 legal variants in 171.433 s and retained the Hub's three blockers.
The Hub search history now contains **125 poses**. Source, frozen copper/pairs,
other-family physical gates and historical PCIe2 control remain unchanged.
Core generalization passes; legacy findings remain 23 / 380. Do not repeat that
unchanged search batch or show its unchanged PCB as a new candidate.

## New diagnostic domain, not a production repair

`build/compact-pair-portal-domain-20260917` is a bounded, parallel A/B experiment
on the current PCIe3 and 12VHPWR priority compiler, plus historical control.
It tests the hypothesis that the **ordinary board-minimum-clamped signal portal
land** excludes a usable compact local SMD escape. The existing qualified
filled/capped preferred geometry is substituted only in private worker memory.
No production script, board rule or source CAD is changed.

This is explicitly **unadmitted experimental geometry**. All native copper,
spacing, pair and future-power guards remain active. Retained new compact
signal vias must additionally have a live local-SMD ownership proof; a favorable
route count alone would not justify integration. Complete native DRC and
fabrication signoff would still be needed before any candidate promotion.

The VHP baseline and compact probes have completed with the same result: CAN
segments qualify, USB's second flow-through leg does not. Times are 68.131 s and
68.032 s respectively; no new signal vias survive. This is **no improvement**,
not evidence for lowering global via minima. PCIe3 also completed without a
gain: baseline 143.401 s, compact 144.565 s; USB_D and CAN qualify while CAN_J1
still refuses and the separate Kelvin findings remain. No new signal vias
survive either mode. All six source/hierarchy hashes and the frozen engine are
unchanged; historical PCIe2 board/hash/probe parity passes.

The cohort is finished. **Do not integrate this experimental override or repeat
the same domain.** The existing minimum-clamped production signal-via policy is
unchanged. This result rejects one proposed explanation, not every possible
local-portal implementation. The current input plan and all dashboard candidates
remain unchanged; no new render is appropriate for these identical artifacts.

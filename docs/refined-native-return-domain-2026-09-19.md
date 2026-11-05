# Exact-native return-seat refinement: negative bounded result

Private ablation: `tmp/refined_return_domain_20260919.py`.
Complete six-board/control receipt:
`build/refined-return-domain-20260919/report.json`.

The normal dogbone constructor samples four radii. Its largest sample can be
smaller than the declared 1.5 mm search reach, and the previous boundary probe
used conservative obstacle bounding boxes to generate proposals. This study
checks whether either sampling limitation explains the remaining Hub failures.

For each failed native terminal, the ablation keeps all original successes
and tests a new radial domain only after a legacy refusal. It samples eight
0/45/90-degree rays at 0.025 mm radius increments through the unchanged 1.5 mm
reach. Each of the existing 0.35 mm and 0.30 mm qualified compact geometries
gets one bounded attempt per terminal. The normal native constructor still
checks copper, pad containment, fabrication process, hole spacing, trace
widths, endpoint neckdowns, locality and protected power. No bypass is added.

On the Hub, six domains each test 480 positions: **2,880 positions**, with no
successful ground entry. All six report via-spot obstruction at every sampled
position. Additional pad/stub obstructions remain, but a finer straight-ray
grid does not repair either cell. This is not a proof of geometric
impossibility; it excludes this bounded proposal refinement as a demonstrated
fix. Do not integrate it merely to increase the feature count or replay these
unchanged domains.

All sources and schematic hierarchy hashes are unchanged. Historical PCIe2
PCB hash, regression result and probes match. Production scripts were unchanged
throughout the cohort. PCIe2/PCIe3 physical checks stay passing; VHP retains its
C7 local-interconnect deferral; EPS/ATX remain interface-held. No candidate is
promoted, no source board changes, and no new review image is warranted.

Keep the canonical input plan and the Hub's 158-pose history from
`build/contact-seating-suite-20260919-qualified`. The Hub still has two real
local-return refusals. Further work needs a constructive ownership/ground-access
dependency solution, not denser unchanged via sampling, larger ground-reach
limits, relaxed fabrication checks, or changes to approved high-current buses.

Separately inspected the existing EPS late-intent failure: `p10_intents`
re-ratifies individual loose locks but cannot supersede the persistent supply
cell owned by `p3_critical_seats`. Do not weaken that guard. Any future ordering
repair must be resolved at the owning stage or by an explicitly validated
complete-cell transaction. No production intent change was made in this study.

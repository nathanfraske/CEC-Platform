# Retain the freshly graded route incumbent

## Cause and correction

The canonical route stage previously selected only newly generated candidates.
The failing oracle sort key also omitted copper cost. Consequently, a wave
could select a PCB with the same failures and connectivity but additional vias
and wire, simply because the incoming board was absent from the competition.
The concrete pre-fix witness is
`build/route-incumbent-compare-20260916/report.json`.

The generic coordinator now stages the incoming routed artifact and its rule /
power sidecars, then grades it once with the current route oracle, route
parameters, craft gates, precision and thermal policy. It does not reuse an old
oracle or spend an additional routing seed. Board and sidecar hashes are checked
after read-only grading and again after candidate search. Missing, changed or
incomplete incumbent evidence blocks selection; it does not silently remove
the baseline. Native zero-track placement inputs are explicitly inapplicable.

Candidates may not lose any previously passing incumbent gate, including by
omitting its evidence. Existing safety, critical connectivity, DRC, connectivity
and blocker rankings retain precedence. Only after those terms tie do fewer
vias and shorter measured wire win. Exact ties retain the incumbent rather than
prefer a new seed. Missing, negative and non-finite copper measurements are not
treated as zero. The candidate report records origin, ranking, costs and lost
incumbent gates; the explicit seed budget is unchanged.

The selected incumbent is copied, not edited in place. It still receives the
existing bounded dimension/fabrication finishing stage: blanket skipping would
starve legitimate finishing-only improvements. If finishing changes its artifact
family, protected copper / qualified pairs are checked and the complete read-only
oracle is rerun. A fresh comparison must prefer the finished candidate over the
untouched incumbent; otherwise the original graded family is retained. Finishing
exceptions cannot destroy the incumbent. Independent signoff still owns release.

No board family, reference designator, net or coordinate is special-cased in
these production rules. No load, current, thermal, geometry or fabrication limit
is relaxed.

## Validation and scope

Synthetic and loaded-native tests cover cost ties, genuine connectivity gain,
safety precedence, missing / invalid measurements, lost gate evidence, one- and
multi-seed coordination, zero-track inputs, changed PCB and rule files, concurrent
source mutation, incomplete oracle evidence, failed candidates and finishing
acceptance / rejection / exceptions. Tests use arbitrary signal names and
disposable native KiCad boards.

The first bounded replay correctly omitted the zero-track PCIe3 placement from
route-incumbent selection, but the diagnostic incorrectly required every family
to have routed copper. That diagnostic assertion was corrected; production
behavior was not loosened. Use the v2 replay, not its incomplete predecessor.

Current verification receipts (completion and counts are recorded in the
continuation ledger):

- `build/route-incumbent-final-tests-20260916.log`
- `build/route-incumbent-replay-v2-20260916/report.json`
- `build/route-incumbent-replay-v2-20260916/historical-control.json`

Completed validation: **149 tests pass** in 111.56 seconds. All four applicable
current-family physical reports are identical before/after; all six source and
hierarchy signatures are unchanged. The complete historical PCIe2 control,
probes, regression and generalization payloads remain exactly identical.
`build/route-incumbent-qualified-20260916.json` consolidates the native proof.
The real PCIe2 selection retains 386 vias / 1,654.31 mm over the prior proposal's
387 vias / 1,656.95 mm, at the same 0 DRC / 9 opens and failed gate terms.

The PCIe2 coordinator replay uses the freshly regraded actual last-pass proposal
as the backend result, with a real fresh incumbent grade. It is an explicit
selection replay, **not another router wave**. Other families run native
same-artifact tie controls or the zero-track negative control. EPS and ATX remain
held by unadmitted interface ECOs; they are not counted as routed or physically
admitted. Their current authority and geometry must not be bypassed.

This slice prevents measured regression; it does not close the nine PCIe2 opens,
Hub local-cell blockers, PCIe3 / VHP priority refusals or EPS / ATX interface
conflicts. No new geometry is promoted and no unchanged full cohort is justified.
Retain `build/bound-return-next-inputs-20260916.json` and the existing verified
six-board gallery. The next physical work remains complete priority / power-cell
dependencies and coordinated main/daughterboard fit within user-authorized
constraints.

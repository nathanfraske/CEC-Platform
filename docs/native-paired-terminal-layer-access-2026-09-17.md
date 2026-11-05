# Native plated-terminal access in the coupled router

## Verified defect and generic repair

The coupled portal fallback used one `source_layer` for both ends. Even when
both members of a connector pair were native plated through-hole pads spanning
the selected inner/back signal layer, it generated their fan-in on F.Cu and
required another two signal vias at an arbitrary portal. The existing PTH
dogbone cleanup runs after routing and cannot repair a candidate rejected
before it exists. Multidrop layer assignment already recognizes native PTH
access; that did not cover this separate paired-portal fallback.

Native inspection of the exact current inputs confirms eleven paired plated
ports across all six board families. These are real pad attributes/layer spans,
not an inference from a footprint name, drill drawing or same-net proximity.
Evidence: `build/native-pair-ports-20260917.json` and
`build/native-pair-layer-final-verify-20260917/report.json`.

`cec_precision_route._paired_native_terminal_layers` now resolves each end
independently. Both members must resolve uniquely by actual position/net to
native PTH pads with a nonzero drill and both enabled copper layers. That end
may construct its paired fan-in directly on the chosen signal layer. Its
redundant portal signal-via field is not generated. An SMD end still requires
its ordinary matched signal-via and reference-return qualification.

Wrong-net, shifted, ambiguous, undrilled, unplated, SMD, one-member-only and
unavailable-layer cases retain the original domain. Existing prequalified
surface throats stay on their qualified layer. Portal cache identities include
the selected middle layer and both terminal search layers. No board, package,
refdes or coordinate exception was introduced, and no protected copper is moved.

This does **not** waive plated-terminal return-current requirements. The
existing final `cec_pth_pair_returns.synthesize` and independent plane-contact,
coupling, skew, detour, geometry and whole-board admission remain in place.
The diagnostic projector now preserves bounded per-end layer and native-pad
witnesses, so a single legacy F.Cu label cannot hide a mixed-layer search.

## Tests and current-board outcome

The loaded-native synthetic pair closes entirely on B.Cu with zero added
signal vias when all four terminals are plated, instead of demanding four
redundant transition vias. This proves the routing geometry/dispatch, not
synthetic-board fabrication signoff. Translated/renamed fixtures and native
negative cases cover the same behavior; a rejected mixed PTH/SMD trial leaves
all parent copper unchanged. Tests also verify the SMD end still enters the
matched-via-field guard and that compacted/replayed diagnostics retain the
bounded native witnesses.

**508 tests and two subtests pass**, including pair scheduling, geometry,
return fields, portal feedback/cache lifetime, native PTH returns, precision
flow-through, priority ownership, final residuals and blocker provenance.
Log: `build/native-pair-layer-final-tests-20260917.log`.

Three native priority measurements ran concurrently on private, exact copies:

| Board | Measured priority result | Wall time | Promotion |
| --- | --- | --- | --- |
| PCIe3 | Eight critical refusals remain | 83.516 s | None |
| 12VHPWR | One critical refusal remains | 77.669 s | None |
| Hub | One priority refusal in this diagnostic; three physical/craft holds remain | 136.888 s | None |

These are read-only route-feasibility probes, not newly routed boards. They
did not mutate their source or private measurement board. No metric reduction
or speedup is claimed from unlike previous placement trials. EPS/ATX remain
held before routing for their coupled interface ECOs. Concurrent physical
checks preserve current craft gates and protected copper for all admitted
families. All six source/hierarchy hashes and the historical PCIe2 control's
PCB hash, board-regression and probe payloads match.

Evidence: `build/native-pair-layer-suite-20260917/report.json` and final
`build/native-pair-layer-final-verify-20260917/report.json`. Core generalization
passes; pre-existing physical/runtime debt stays 23 / 380 in
`build/native-pair-layer-generalization-20260917.json`.

## Continuation and next cause to investigate

Keep **`build/additive-first-next-inputs-20260917.json`** authoritative. PCIe2
remains at the reviewed five-open archive. No new board or image is promoted.
All workers finished; approximately 64 GiB remains free. The heartbeat remains
active, and unchanged probes should not be relaunched without a new domain.

The PCIe3 trace now reaches the connector-side native layer access, but the
SMD series station still rejects many possible transition fields. Its foreign
blockers include already-generated copper of the earlier adjacent CAN pair.
Inspect `_future_pair_launch_reservations` and `_shared_split_support_centers`
before changing placement again: broad future boxes are deliberately suppressed
at shared split-series stations because they cover opposite pads. Exact pad
clearance alone does not reserve usable outgoing launch space. A bounded,
direction-aware shared-station portal/launch contract, or a transactional
coupled order portfolio, is the next hypothesis to test—not an instruction to
move specific R11/R12 coordinates or relax the via/coupling gates. Existing
future-pair reservation and scheduling mechanisms must be extended, not
duplicated. This remains a hypothesis for the remaining failure, not proof that
it explains every priority refusal or the Hub's separate craft blockers.

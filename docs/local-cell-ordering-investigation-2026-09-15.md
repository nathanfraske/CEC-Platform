# Next generic slice: coupled local-return and supply ordering

Read-only investigation during the fixed-engine frozen-via cohort. No shared
engine, canonical board, footprint, netclass or power budget was changed.
Nothing here is a fab qualification or promoted candidate.

## Native evidence

Current explicit sources are Hub SHA ce61d1a11de3 and PCIe3 SHA 400ffdd8635e
from `build/locked-reconcile-inputs-20260915.json`. All source/hierarchy and
engine signatures remained unchanged during the following experiments.

1. `build/local-return-profile-probe-20260915.json`: the production return
   generator tries the selected profile's preferred 0.25 mm drill / 0.35 mm
   land at pad centre. PCIe3's failing device has 0.30 mm wide GND pads, so
   that land cannot be fully contained. The **already-declared** process
   minimum 0.20 mm drill / 0.30 mm land passes the same native process, land,
   foreign-copper, frozen-reservation, drill and edge checks on both ground
   pads before the supply cell is laid. This is not permission to shrink
   ordinary high-current vias or bypass project DRC minima.
2. `build/local-return-minimum-counterfactual-20260915/report.json`: a scoped
   in-process substitution of that minimum for the preferred choice **does
   not close** the complete PCIe3 cell. Hub remains five failures and PCIe3
   remains one. Raw pad-seat success is therefore insufficient evidence.
3. The failed PCIe3 native certificate identifies a new **+3V3, 0.50 mm wide
   SIG2 supply track** from (54.583099,22.2895) to (56.163099,22.2895) as the
   blocker of the GND through-via at (54.583099,21.7895). Its UUID belongs to
   that temporary local-cell construction. The supply generator runs first;
   the existing owner-first/capacitor-first retries only reorder the two
   ground returns **after** the obstructing supply has already been laid.
   It labels the temporary supply track as a protected upstream blocker,
   instead of retrying the still-uncommitted cell transaction jointly.
4. `build/local-return-order-counterfactual-20260915/report.json`: after
   materializing the other successful cells in memory, use the declared
   minimum POFV geometry and lay this cell's returns before its supply.
   The existing guarded primitives find a **complete eight-item cell**.
   Hub's four local-access failures still fail; C2's fifth proximity failure
   is also unchanged. Trial objects are discarded; no PCB is published.

The last experiment is a useful existence witness, **not** whole-board DRC,
filled-copper, local-loop-quality or fabrication signoff. It must not become
a refdes-specific override or a manual board edit.

## Implementation boundary to qualify next

- Expose a bounded list of process-qualified via geometries: retain preferred
  settings first, then explicitly allowed alternatives only when they meet
  full-land and topology conditions. Preserve ordinary netclass/current
  geometry and project rules outside that existing POFV exception.
- Solve a local bypass cell as one transaction, with supply-first and
  return-first alternatives. Roll back **all** objects/groups from a failed
  attempt before trying another order. Never rip up inherited locked copper.
- Distinguish inherited authority from tentative items made by this same
  transaction in blocker provenance. A temporary owned item should trigger
  bounded joint replanning, not a misleading permanent-placement diagnosis.
- Keep the same constructor and deterministic alternatives in feasibility
  audit and production. Re-run the full local-loop/proximity gate, frozen
  copper contract, native fill/DRC and historical PCIe2 regression.
- Require renamed/translated synthetic positive and negative regressions,
  including a supply-first success that return-first would block, unknown
  process, insufficient land/drill spacing, inherited-copper conflict,
  no feasible order, and no accumulated trial copper or groups.

Do not edit the implementation while
`build/frozen-via-followup-suite-20260915/suite.json` or its descendants are
live. Hub still needs genuinely different fixed-power-aware consumer seating;
the small-via or ordering experiment is not a solution to its recorded holds.

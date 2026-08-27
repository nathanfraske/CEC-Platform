# Canonical start-to-finish PCB pipeline

`scripts/cec_full_pipeline.py` is the production entry point for current BETA
boards. It is deliberately a coordinator: specialist placement, routing,
electrical, thermal, fabrication, and dashboard engines remain independently
testable and the coordinator records their evidence in one stage ledger.

## Stage contract

1. **Source intake** resolves only `cec_beta_manifest.PROJECTS`, the hierarchy
   root, child sheets, BOM, policy, project/rule files, and current placement.
   The compiled constraint IR, ERC, BOM fields, schematic/PCB reference set,
   value/footprint/pad-net signatures, assembly state, and board-specific
   electrical contracts must admit the source.
2. **Placement** either preserves an explicitly selected current placement or
   performs a fixed-outline route-aware replacement. Pads, courtyards,
   decoupler ownership, stranded parts, and craft gates are checked before
   routing.
3. **Route preflight** performs multiresolution pad-escape, array-fanout,
   critical-route, routed-power reservation, future-congestion, and negotiated
   capacity analysis. CPU/GPU selection uses the persistent route-awareness
   service's measured crossover.
4. **Precision detailed route** uses `route_oracle_grade(precision=True)`:
   pairs and critical controls first; local bypass ground returns and admitted
   GND planes; routed power; residual detailed routing; refusal-certificate
   repair; ground/fab/corner/teardrop finishing; then the complete oracle gate.
5. **Independent signoff** reparses the final board and reruns `cec_score`, the
   ratified constraint release gate, connectivity, KiCad DRC, and the vendor
   fabrication profile/artifact scan. It does not trust the router's verdict.
6. **Release** emits all copper Gerbers, Excellon drill/map/report, position
   data, BOMs, board/project/rules, evidence, a SHA-256 content manifest, and a
   deterministic ZIP only when every signoff term passes and the source is not
   marked `DRAFT`. Otherwise it emits a clearly named review-only package with
   no manufacturing outputs.
7. **Dashboard archive** publishes the exact final candidate and its causal
   blocker report. The canonical user link is
   `http://localhost:8090/?id=<archive-id>`; raw WSL paths are never used as
   image links.

Every stage in `pipeline-state.json` has an input digest and hashes for every
output. `--resume` is safe by construction: changed sources, policy, code,
parameters, or artifacts invalidate the affected stage. A failed or interrupted
stage is never resumed as complete.

## Hub invocation

```bash
python3 scripts/cec_full_pipeline.py \
  --board hub-standard-rev2 \
  --input-board beta/hub-standard-rev2/candidate/hub-standard-rev2-candidate.kicad_pcb \
  --replace-placement \
  --backend auto --passes 16 --opt 30 --route-timeout 1800 \
  --out build/full-pipeline/hub-standard-rev2
```

Omit `--replace-placement` to validate and route an already approved placement.
Use `--no-resume` only for controlled reproducibility trials. A DRAFT board can
reach physical closure and dashboard review, but release remains withheld until
the product owner removes the DRAFT marker through the normal revision process.


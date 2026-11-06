"""Read-only proposed local-bypass poses; not routed/accepted geometry."""
import json
import math
from pathlib import Path
from cec_pipeline.native import _native
p, _ = _native()
import cec_assembly_envelope as assembly
import cec_force_current as force
import cec_constraints as constraints

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).parent
source = WORK / 'c25-reference-repair-v1/candidate/board.kicad_pcb'
cover = ROOT / 'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb'
contract = ROOT / 'beta/assembly/hub-atx-stack.json'
paths = (source, cover, contract)
hashes = [force._hash(path) for path in paths]
board, peer = (p.LoadBoard(str(path)) for path in paths[:2])
cap = board.FindFootprintByReference('C9')
owner = board.FindFootprintByReference('U6').FindPadByNumber('2')
initial = cap.GetPosition()
rows = []
for x, y, angle in [(10.55,48.,270.),(10.91,48.,270.),(11.,48.,270.),
                     (11.1,48.,270.),(11.2,48.,270.),(11.,47.8,270.),
                     (11.,48.6,270.),(11.2,48.6,270.),(11.3,48.6,270.),
                     (10.5,48.6,180.),(10.5,48.5,180.),(10.6,48.5,180.)]:
    cap.SetPosition(p.VECTOR2I_MM(x,y));cap.SetOrientationDegrees(angle)
    poly = assembly.polygon_from_native(cap.GetCourtyard(cap.GetLayer()))
    hits = []
    for other in board.GetFootprints():
        if force._uid(other) == force._uid(cap) or other.GetLayer()!=cap.GetLayer(): continue
        q = other.GetCourtyard(other.GetLayer())
        if q.OutlineCount() and poly.intersection(assembly.polygon_from_native(q)).area > 0:
            hits.append(other.GetReference())
    fit, _ = assembly.evaluate_boards(board, peer, json.loads(contract.read_text()))
    vents = assembly.vent_reservations(board,assembly.facing_vents(fit,json.loads(contract.read_text()),'carrier'))
    with force._thermal_hint('atx-24pin-rev3'):
        bypass = constraints._device_bypass_assignment(board,project_max_mm=3.5)
    rows.append(dict(pose_mm=[x,y,angle],same_face_courtyard_hits=hits,
        paired_failures=[r for r in fit['checks'] if not r['ok']],
        paired_ok=fit['ok'],vent_failures=[v for v in vents if not v['ok']],
        bypass_distance_mm=math.dist(tuple(cap.FindPadByNumber('1').GetPosition()),tuple(owner.GetPosition()))/1e6,
        VBUS_missing=[{k:v for k,v in r.items() if k not in ('pad','return_pad')}
                      for r in bypass['missing'] if r['rail']==owner.GetNetname()]))
report=dict(schema=1,source_files=dict(zip(map(str,paths),hashes)),
    source_unchanged=hashes==[force._hash(path) for path in paths],rows=rows,
    board_saved=False,routes_checked=False,current_qualified=False,release_authority=False)
force._write(WORK/'c9-locality-scout.json',report)
print(json.dumps(rows,indent=2,default=str))

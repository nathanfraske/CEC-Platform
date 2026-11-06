"""Read-only exact saved-parent wired C55 Ground leaf derivation."""
import json
from pathlib import Path
import sys
ROOT = Path('/home/codex/src/CEC-Platform')
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_wired_aggregate_ground_leaf as op

source = ROOT/'experiments/busbars/mux-reconstruction-20261106/output-prefix-v1/candidate/board.kicad_pcb'
study = json.loads((ROOT/'experiments/busbars/reservoir-repack-20261106/geometry-map-derived-seven.json').read_text())
poses = {r:[p[0]/1e6,p[1]/1e6,p[2]] for r,p in study['proposed_poses'].items()}
board = pcbnew.LoadBoard(str(source))
pad = board.FindFootprintByReference('C55').FindPadByNumber('2')
before = op.native.row._source_binding(board)
try:
    proof = op.plan(board,op.native.force._uid(pad),poses,board_hint='atx-24pin-rev3',
        allow_linear_power_stage_reconstruction=True,allow_owned_locked_escapes=True)
    print(json.dumps(dict(ok=True,source=str(source),source_sha256=op.native.force._hash(source),
        tracks=proof['track_uuids'],boundaries=proof['boundary_uuids'],locked=proof['locked_owned_track_uuids'],
        width_nm=proof['width_nm'],source_length_mm=proof['source_length_mm'],
        owner=proof['wired_identity']['source_locality_owner'],no_admission=True),indent=2))
except ValueError as exc:
    print(json.dumps(dict(ok=False,source=str(source),reason=str(exc),no_admission=True)))
assert before == op.native.row._source_binding(board)

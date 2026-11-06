"""Read-only current-contract representation comparison on the exact parent."""
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[3]/'scripts')]
import pcbnew
import cec_force_current as force
import cec_full_current_planar_reflow as full
from scout import SOURCE,SHA

assert force._hash(SOURCE)==SHA
board=pcbnew.LoadBoard(str(SOURCE))
net=next(p.GetNetname()for p in board.FindFootprintByReference('C55').Pads()if p.GetNetname()!='GND')
with force._thermal_hint('atx-24pin-rev3'):
    kind,domain,contract=full._model(board,SOURCE,net,'atx-24pin-rev3')
wire=json.loads(json.dumps(contract,sort_keys=True,allow_nan=False))
differences=[dict(key=k,actual_type=type(contract[k]).__name__,wire_type=type(wire[k]).__name__,
    actual=contract[k],wire=wire[k])for k in contract if contract[k]!=wire[k]]
report=dict(source_sha256=SHA,net=net,kind=kind,
    actual_equals_wire=contract==wire,differences=differences,read_only=True)
target=Path(__file__).with_suffix('.json');assert not target.exists()
target.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
assert force._hash(SOURCE)==SHA

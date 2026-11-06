"""Read-only native seat planning against the compiled exact cut inventory.

Changing transport work intent requires a fresh full compile before use.
These probes never save a construction or claim that cached cuts are owned
for a different option set.
"""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];WORK=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import pcbnew as p
import cec_force_current as force
import cec_cell_macro_requests as macro
import cec_fr as fr
import cec_control_gate_bias_placement as native
from cec_native_items import discard_items

mode=sys.argv[1];dest=WORK/('barrel-frame-'+mode+'.json');assert not dest.exists()
receipt=json.loads((WORK/'compile-paired-refilled-frame-v3.json').read_text());packet=receipt['packet']
source=Path(packet['source']);assert force._hash(source)==packet['source_sha256']
assert force._code_identity()==packet['code_identity']
parent=p.LoadBoard(str(source));source_vias={force._uid(t):t for t in parent.GetTracks()if t.GetClass()=='PCB_VIA'}
options=macro.packet_options(packet)
use={key:options[key]for key in('reuse_ground_barrels','ordinary_via_poses','stationary_ground_barrel_uuids',
    'local_signal_port_offsets','control_shunt_ground_return_axes')if key in options}
if mode=='stationary-ground':
    use['stationary_ground_barrel_uuids']=sorted({*use.get('stationary_ground_barrel_uuids',()),
        *(q['uuid']for q in packet['transport']['source_process_barrel_motion']
            if source_vias[q['uuid']].GetNetname()=='GND')})
else:assert mode=='original'
board,transport=macro._frame(parent,source,packet['source_plan'],timeout_s=6.,**use)
discard_items(board,[t for t in board.GetTracks()if force._uid(t)in packet['retired_track_uuids']])
live={force._uid(t):t for t in board.GetTracks()};rows=[]
ids={q['uuid']for q in receipt['pre_refill_barrels']['refusals']}
for uid in sorted(ids):
    via=live[uid];detail={}
    okay=fr._via_spot_clear(board,via.GetPosition(),via.GetWidth(via.TopLayer()),200000,
        {via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),existing_via_uuid=uid,report=detail)
    pads=[dict(ref=fp.GetReference(),pin=pad.GetNumber(),net=pad.GetNetname(),uuid=force._uid(pad))
        for fp in board.GetFootprints()for pad in fp.Pads()
        if pad.IsOnLayer(via.TopLayer())and pad.GetEffectiveShape(via.TopLayer()).Collide(via.GetEffectiveShape(via.TopLayer()),200000)]
    proof=next((q for q in transport['source_process_barrel_motion']if q['uuid']==uid),None)
    rows.append(dict(uuid=uid,net=via.GetNetname(),source_nm=list(source_vias[uid].GetPosition()),
        at_nm=list(via.GetPosition()),okay=okay,diagnostics=detail,near_pads=pads,owner_proof=proof))
report=dict(mode=mode,source_sha256=force._hash(source),exact_options=use,barrels=rows,
    count_clear=sum(q['okay']for q in rows),count_examined=len(rows),
    provisional_old_cut_inventory_only=True,fresh_source_compilation_required=True,
    no_construction_or_admission=True)
dest.write_text(json.dumps(report,indent=2,default=str)+'\n')
print(json.dumps(report,default=str)[:16000])

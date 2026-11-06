"""Build one private correction with exact original opaque node preservation."""
import json
from pathlib import Path
import time
from repair_port import ROOT,WORK,SOURCE,SOURCE_SHA,VIA,HINT,barrel,force,_native
import cec_additive_route_receiving as syntax
import cec_source_literal_retirement as cut
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw

OUT=WORK/'port-repaired-v1'


def main():
    started=time.monotonic();p,_=_native()
    assert force._hash(SOURCE)==SOURCE_SHA and not (OUT/'construction.json').exists()
    choice=json.loads((WORK/'port-grid-proposals.json').read_text())
    assert choice['source_sha256']==SOURCE_SHA
    trial=next(t for t in choice['trials']if t['complete'])
    board=p.LoadBoard(str(SOURCE))
    proposal=barrel.plan(board,SOURCE,via_uuid=VIA,board_hint=HINT,
        allow_owned_locked=True,repair_source_pad_overlap=True)
    assert {k:v for k,v in proposal.items()if k!='source_binding'}==choice['source_proposal']
    old={force._uid(t)for t in board.GetTracks()}
    barrel.subtract(board,SOURCE,proposal)
    net=board.GetNetcodeFromNetname(proposal['net'])
    via=p.PCB_VIA(board);via.SetPosition(p.VECTOR2I(*trial['at_nm']))
    via.SetViaType(p.VIATYPE_THROUGH);via.SetLayerPair(p.F_Cu,p.B_Cu)
    via.SetWidth(proposal['root_width_by_layer_nm'][str(p.F_Cu)])
    via.SetDrill(proposal['root_drill_nm']);via.SetNetCode(net);via.SetLocked(True);board.Add(via)
    for route in trial['routes']:
        for a,b in zip(route['points_nm'],route['points_nm'][1:]):
            t=p.PCB_TRACK(board);t.SetStart(p.VECTOR2I(*a));t.SetEnd(p.VECTOR2I(*b))
            t.SetWidth(route['width_nm']);t.SetLayer(board.GetLayerID(route['layer']))
            t.SetNetCode(net);t.SetLocked(True);board.Add(t)
    syntax._ground_refill(board)
    OUT.mkdir(exist_ok=True)
    native=OUT/'native-construction.kicad_pcb'
    p.PCB_IO_KICAD_SEXPR().SaveBoard(str(native),board)
    retired=set(proposal['retired_track_uuids'])|{VIA}
    original=raw.raw_text(SOURCE)
    ground=[force._uid(z)for z in board.Zones()if not z.GetIsRuleArea()and z.GetNetname()=='GND']
    text=literal.assemble(cut.subtract(original,retired),raw.raw_text(native),ground_ids=ground)
    candidate=force._copy_family(SOURCE,OUT/'candidate')
    raw.write_raw(candidate,text)
    assert force._hash(SOURCE)==SOURCE_SHA
    record=dict(source=str(SOURCE),source_sha256=SOURCE_SHA,candidate=str(candidate),
        candidate_sha256=force._hash(candidate),source_via_uuid=VIA,new_via_uuid=force._uid(via),
        retired_track_uuids=sorted(retired-{VIA}),
        added_native_uuids=sorted({force._uid(t)for t in board.GetTracks()}-old),
        ordinary_via_dimensions_preserved=True,source_pad_unchanged=True,
        source_pad_overlap_repair=True,trial=trial,elapsed_s=time.monotonic()-started,
        board_saved=True,private_unadmitted=True,release_authority=False)
    (OUT/'construction.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()

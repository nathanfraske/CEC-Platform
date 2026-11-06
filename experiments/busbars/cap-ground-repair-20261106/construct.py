"""One explicit private native via correction; no board promotion."""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_fab_profile as fab
import cec_fr as fr
import cec_additive_route_receiving as additive
import cec_source_literal_retirement as cut
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw

WORK=Path(__file__).resolve().parent
SOURCE=ROOT/'experiments/busbars/coherent-mux-20261106/port-repaired-v1/candidate/board.kicad_pcb'
SHA='d4cf0b22f92526b6bdca0ae7cfa09af02217647db984577064ce91bfc177958a'
VIA='c25714c1-f2d8-4e0e-9711-7d208ce1da97'
PAD='b02322a5-3ab5-4710-8996-cd61b8e81c82'
HINT='atx-24pin-rev3'


def main():
    start=time.monotonic();p,_=_native()
    assert force._hash(SOURCE)==SHA and not (WORK/'construction.json').exists()
    b=p.LoadBoard(str(SOURCE))
    via=next(t for t in b.GetTracks()if force._uid(t)==VIA)
    pad=next(q for f in b.GetFootprints()for q in f.Pads()if force._uid(q)==PAD)
    assert via.GetNetname()==pad.GetNetname()=='GND'
    assert not any(g.ContainsItem(via)for g in b.Groups())
    before_at=list(via.GetPosition());after_at=list(pad.GetPosition())
    assert before_at==[16824990,46765001]and after_at==[16924990,46765001]
    assert via.IsLocked()and via.GetWidth(via.TopLayer())==500000 and via.GetDrillValue()==300000
    assert fab.local_pofv_via_decision(b,via)==(False,'full via land is not contained by the SMD pad')
    # Explicit approved repair of this native source debt. Preserve the same
    # physical padstack/UUID/lock; all other opaque board nodes stay original.
    via.SetPosition(p.VECTOR2I(*after_at))
    assert fab.local_pofv_via_decision(b,via)[0]
    guard={}
    assert fr._via_spot_clear(b,via.GetPosition(),via.GetWidth(via.TopLayer()),200000,
        {via.GetNetCode()},drill_nm=via.GetDrillValue(),net_code=via.GetNetCode(),
        existing_via_uuid=VIA,native_padstack_via=via,report=guard),guard
    additive._ground_refill(b)
    native=WORK/'native-construction.kicad_pcb'
    p.PCB_IO_KICAD_SEXPR().SaveBoard(str(native),b)
    ground=[force._uid(z)for z in b.Zones()if not z.GetIsRuleArea()and z.GetNetname()=='GND']
    original=raw.raw_text(SOURCE)
    text=literal.assemble(cut.subtract(original,{VIA}),raw.raw_text(native),ground_ids=ground)
    candidate=force._copy_family(SOURCE,WORK/'candidate')
    raw.write_raw(candidate,text)
    assert force._hash(SOURCE)==SHA
    old=literal._inventory(original)[0];new=literal._inventory(text)[0]
    assert old.keys()==new.keys()
    changes=[uid for uid in old if old[uid][2]!=new[uid][2]]
    assert VIA in changes and set(changes)<={VIA,*ground}
    report=dict(source=str(SOURCE),source_sha256=SHA,candidate=str(candidate),
        candidate_sha256=force._hash(candidate),via_uuid=VIA,pad_uuid=PAD,
        source_at_nm=before_at,target_at_nm=after_at,barrel_geometry_preserved=True,
        changed_native_node_uuids=sorted(changes),source_guard=guard,
        no_tracks_or_components_changed=True,elapsed_s=time.monotonic()-start,
        private_unadmitted=True,release_authority=False)
    (WORK/'construction.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

"""Single explicit ordinary ILIM reconstruction, private and unadmitted."""
import sys
from pathlib import Path
import signal
import time
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
p,_=_native()
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_additive_route_receiving as syntax
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items

SOURCE=ROOT/'experiments/repack/bar-corridor-20261106/c27-retained-v2/candidate/board.kicad_pcb'
OUT=ROOT/'experiments/repack/bar-corridor-20261106/ilm-corridor-v3'
NET='/5V SOURCE MUX + USB SERVICE INGRESS/U6_ILM'
RETIRE={'260484da-9029-4624-bbe7-634592e0db1f','91e5654b-6559-5f14-b242-20fc9412b04e',
    '94c9e177-7718-547f-ba68-c53389686182','52b91698-cdb7-5b09-9443-0df514bd5415',
    '68d5b9bc-1384-4602-b8e0-8f88943ca98e'}
VIA='19b72a21-fd9a-4eca-8a49-234863e73e00'

def timed(fn):
    def expired(*_):raise TimeoutError('bounded_private_ten_second_lease')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,10)
    try:return fn()
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

def main():
    assert force._hash(SOURCE)=='67c1c32cfd411faab96e998b6be73bf2e065c939da9457dfe51dc75585594885'
    OUT.mkdir(exist_ok=True);assert not(OUT/'construction.json').exists()
    b=p.LoadBoard(str(SOURCE));before={force._uid(t)for t in b.GetTracks()}
    assert NET in ordinary.eligible_nets(b,SOURCE,'atx-24pin-rev3')
    inventory={force._uid(t):t for t in b.GetTracks()}
    proof=ordinary._exclusive_retired_vias(b,{VIA},retired_tracks=RETIRE,nets={NET},
        unlock={VIA},deadline=time.monotonic()+9)
    via=p.PCB_VIA(inventory[VIA]);via.m_Uuid.Clone(p.KIID());via.SetPosition(p.VECTOR2I_MM(12.6,48.25))
    discard_items(b,[inventory[u]for u in RETIRE|{VIA}]);b.Add(via)
    routes=[];cache={}
    for face,a,z in[(p.F_Cu,(12800000,48115000),(12600000,48250000)),
            (b.GetLayerID('SIG2'),(15400000,45400000),(12600000,48250000))]:
        def guard(left,right,half):
            return fr._edge_leg_clear(b,left,right,half)and not force._native_track_rule_hits(
                b,p.SHAPE_SEGMENT(left,right,200000),face,cache=cache)
        legs=timed(lambda:fr._guarded_profiled_lastmile_legs(b,p.VECTOR2I(*a),p.VECTOR2I(*z),
            200000,face,200000,b.GetNetcodeFromNetname(NET),guard,allow_maze=True,
            maze_margin_mm=2,foreign_cache=cache,deadline_monotonic=time.monotonic()+9,
            max_length_nm=9000000,refine_maze=True,refinement_grids_mm=(.2,.1)))
        if not legs:
            force._write(OUT/'refusal.json',dict(net=NET,eligible=True,exclusive_via=proof,
                layer=b.GetLayerName(face),a_nm=a,z_nm=z,reason='no_guarded_path',admitted=False));return
        for leg in legs:
            left,right=leg[:2]
            t=p.PCB_TRACK(b);t.SetStart(left);t.SetEnd(right);t.SetWidth(200000)
            t.SetLayer(face);t.SetNetCode(b.GetNetcodeFromNetname(NET));t.SetLocked(True);b.Add(t)
        routes.append(dict(layer=b.GetLayerName(face),points_nm=[list(legs[0][0])]+[list(leg[1])for leg in legs]))
    timed(lambda:syntax._ground_refill(b))
    native=OUT/'native-save.kicad_pcb';p.PCB_IO_KICAD_SEXPR().SaveBoard(str(native),b)
    _,new=syntax._nodes(native);spans=raw.inventory(raw.raw_text(SOURCE));text=raw.raw_text(SOURCE)
    changed={force._uid(z)for z in b.Zones()if not z.GetIsRuleArea()and z.GetNetname()=='GND'}
    for uid in sorted(RETIRE|{VIA}|changed,key=lambda u:spans[u][0],reverse=True):
        a,z=spans[uid];text=text[:a]+(''if uid in RETIRE|{VIA}else syntax._render(new[uid]))+text[z:]
    added={force._uid(t)for t in b.GetTracks()}-before
    end=text.rfind(')');text=text[:end]+'\n'+'\n'.join(syntax._render(new[u])for u in sorted(added))+'\n'+text[end:]
    candidate=force._copy_family(SOURCE,OUT/'candidate');raw.write_raw(candidate,text)
    force._write(OUT/'construction.json',dict(source=str(SOURCE),source_sha256=force._hash(SOURCE),
        candidate=str(candidate),candidate_sha256=force._hash(candidate),eligible_net=NET,
        exclusive_retired_via_proof=proof,retired_track_uuids=sorted(RETIRE),retired_via_uuids=[VIA],
        added_uuids=sorted(added),new_via_uuid=force._uid(via),new_via_at_mm=[12.6,48.25],
        routes=routes,admitted=False,current_qualified=False))
    print(candidate)

if __name__=='__main__':main()

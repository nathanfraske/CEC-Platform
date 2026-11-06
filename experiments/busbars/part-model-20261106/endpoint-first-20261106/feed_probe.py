"""Bounded RAM-only full-width route feasibility; not a construction receipt."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
p,_=_native()
import cec_force_current as force,cec_fr as fr
S=ROOT/'experiments/repack/bar-corridor-20261106/c9-corrective-v4/candidate/board.kicad_pcb'
assert force._hash(S)=='b118546af6665d77b190a9ac8ce3132cde413d607cdb3d9b28ba620a3857be24'
b=p.LoadBoard(str(S));net='/SENSE12V_HI';width=3230592;face=p.F_Cu
# Counterfactual removal is only the separately source-owned VBUS reflow task.
cut='3a9c7bab-efb6-5496-8d7b-23ded11b3e34'
held=[t for t in b.GetTracks()if force._uid(t)==cut]
assert len(held)==1 and held[0].GetNetname()=='/5V SOURCE MUX + USB SERVICE INGRESS/VBUS'
b.Remove(held[0]);rows=[]
for name,points in [
 ('upper_direct',[(51.685001,34.400099),(71,56.6)]),
 ('upper_source_rated_pad_entry',[(51.685001,35.405895),(71,56.6)]),
 ('upper_source_rated_trunk',[(47.4,38.3582),(71,56.6)]),
 ('upper_source_rated_west',[(43.4,38.5582),(71,56.6)]),
 ('lower_direct',[(18.349999,77.4),(71,82)]),
 ('lower_bottom_channel',[(18.349999,77.4),(18.349999,84.8),(70.8,84.8),(71,84.6),(71,82)])]:
    cache={};legs=[];started=time.monotonic();failed=None;diagnostics={}
    def guard(a,z,half):
        return fr._edge_leg_clear(b,a,z,half) and not force._native_track_rule_hits(b,p.SHAPE_SEGMENT(a,z,width),face,cache=cache)
    for a,z in zip(points,points[1:]):
        result=fr._guarded_profiled_lastmile_legs(b,p.VECTOR2I_MM(*a),p.VECTOR2I_MM(*z),width,face,200000,b.GetNetcodeFromNetname(net),guard,
            allow_maze=True,maze_margin_mm=5.,foreign_cache=cache,deadline_monotonic=time.monotonic()+8.,max_length_nm=150000000,
            refine_maze=True,refinement_grids_mm=(.5,.25),search_diagnostics=diagnostics)
        if not result:failed=[a,z];break
        legs.extend(result)
    rows.append(dict(name=name,found=failed is None,failed_waypoint_segment=failed,elapsed_s=time.monotonic()-started,diagnostics=diagnostics,
        legs=[dict(start_mm=[a.x/1e6,a.y/1e6],end_mm=[z.x/1e6,z.y/1e6],width_nm=w)for a,z,w in legs]))
    print(name,rows[-1],flush=True)
report=dict(source_sha256=force._hash(S),net=net,width_nm=width,ram_counterfactual_vbus_track_removed=cut,results=rows,
    scope='Finite guarded planar routing feasibility only. No saved board, transport/current/Kelvin admission, or exhaustive no-path claim.')
(Path(__file__).parent/'feed-probe.json').write_text(json.dumps(report,indent=2)+'\n')

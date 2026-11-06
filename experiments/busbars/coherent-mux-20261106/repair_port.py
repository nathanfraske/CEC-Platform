"""Source-bound ordinary-port repair, separate from the proposed mux move."""
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
WORK=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from scout import SOURCE,SOURCE_SHA
from cec_pipeline.native import _native
import cec_force_current as force
import cec_ordinary_barrel_reseat as barrel
import cec_fr as fr
import cec_fab_profile as fab

VIA='15a43170-0a45-4792-a73e-963e5c7093da'
HINT='atx-24pin-rev3'


def main():
    start=time.monotonic();p,_=_native()
    assert force._hash(SOURCE)==SOURCE_SHA
    board=p.LoadBoard(str(SOURCE))
    proposal=barrel.plan(board,SOURCE,via_uuid=VIA,board_hint=HINT,
        allow_owned_locked=True,repair_source_pad_overlap=True)
    barrel.subtract(board,SOURCE,proposal)
    net=proposal['net'];code=board.GetNetcodeFromNetname(net)
    gap=max(board.GetDesignSettings().m_MinClearance,200000)
    width=proposal['root_width_by_layer_nm'][str(p.F_Cu)]
    drill=proposal['root_drill_nm'];cache={};trials=[]
    # Explicit geometrical proposals; the source-derived module contains no
    # refdes, coordinates, or net-name exception. All actual faces are tested.
    positions=((13.7,48.115),(13.75,48.25),(13.8,48.0),(13.8,47.8),(13.4,47.4))
    if '--grid'in sys.argv:
        root=proposal['root_nm']
        positions=[((root[0]+ix*100000)/1e6,(root[1]+iy*100000)/1e6)
            for _,ix,iy in sorted((math.hypot(ix,iy),ix,iy)for ix in range(-15,16)
                for iy in range(-15,16)if 0<math.hypot(ix,iy)<=15)]
    for xy in positions:
        at=p.VECTOR2I(*(round(v*1e6)for v in xy));causes={}
        clear=fr._via_spot_clear(board,at,width,gap,{code},drill_nm=drill,
            net_code=code,foreign_cache=cache,refusal_counts=causes)
        trial=dict(at_nm=list(at),via_clear=bool(clear),refusals=causes,routes=[])
        if '--grid'not in sys.argv and not clear:
            blocked,overlaps=fab.via_at_pad_conflicts(board,at,width,drill,code)
            trial['pad_conflicts']=overlaps
        if clear:
            for boundary in proposal['source_points_nm']:
                face=boundary['layer'];w=boundary['width_nm'];foreign={}
                far=p.VECTOR2I(*boundary['far_nm'])
                def guard(a,b,half):
                    return fr._edge_leg_clear(board,a,b,half) and not force._native_track_rule_hits(
                        board,p.SHAPE_SEGMENT(a,b,w),face,cache=foreign)
                legs=fr._guarded_profiled_lastmile_legs(board,at,far,w,face,gap,code,guard,
                    allow_maze=False,foreign_cache=foreign,deadline_monotonic=start+9,
                    max_length_nm=round((proposal['source_path_mm']+4)*1e6))
                trial['routes'].append(dict(layer=board.GetLayerName(face),width_nm=w,
                    points_nm=None if not legs else [list(legs[0][0])]+[list(e[1])for e in legs]))
        trial['complete']=clear and len(trial['routes'])==len(proposal['source_points_nm']) and all(
            r['points_nm']for r in trial['routes'])
        trials.append(trial)
        if trial['complete']:break
        if time.monotonic()-start>8:break
    assert force._hash(SOURCE)==SOURCE_SHA
    result=dict(source=str(SOURCE.relative_to(ROOT)),source_sha256=SOURCE_SHA,
        source_proposal={k:v for k,v in proposal.items()if k!='source_binding'},
        source_binding_omitted_from_diagnostic=True,
        fresh_source_plan_required_for_construction=True,
        trials=trials,board_saved=False,accepted=False,
        elapsed_s=time.monotonic()-start)
    (WORK/('port-grid-proposals.json'if '--grid'in sys.argv else 'port-proposals.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({**result,'trials':trials if '--grid'not in sys.argv else
        [t for t in trials if t['via_clear']],'total_proposals':len(trials)},indent=2))


if __name__=='__main__':main()

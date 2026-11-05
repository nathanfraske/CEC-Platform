"""Exact ordered broad-phase parity and per-plan native snapshot lifetime."""
from dataclasses import asdict
import json
import math
import random
from unittest.mock import patch

import pytest
from cec_hole_index import HoleIndex, ViaHole
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr
from test_bridge_new_hole_pair import fixture


def test_random_queries_never_omit_an_exact_hole_blocker():
    rng=random.Random(71623)
    rows=[ViaHole(rng.randrange(-20_000_000,20_000_000),rng.randrange(-20_000_000,20_000_000),
                  rng.randrange(100000,1400000),str(i),i%3,'net'+str(i%3)) for i in range(500)]
    index=HoleIndex(rows,cell_nm=750000)
    for _ in range(150):
        x,y=rng.randrange(-21000000,21000000),rng.randrange(-21000000,21000000)
        drill,gap=rng.choice([None,200000,300000,900000]),rng.randrange(0,700000)
        selected=index.nearby(x,y,drill,gap)
        def blocks(row):
            return (row.x,row.y)==(x,y) or (drill is not None and
                math.hypot(row.x-x,row.y-y)+1 < (row.drill+drill)/2+gap)
        assert [r.uuid for r in rows if blocks(r)]==[r.uuid for r in selected if blocks(r)]


def test_boundaries_duplicates_and_explicit_replacement_identity():
    rows=[ViaHole(-1000000,0,300000,'z',1,'a'),ViaHole(0,0,300000,'a',1,'a'),
          ViaHole(0,0,400000,'b',2,'b'),ViaHole(9000000,0,200000,'remote',2,'b')]
    index=HoleIndex(rows)
    assert [r.uuid for r in index.nearby(0,0,None,200000)]==['a','b']
    assert 'z' in {r.uuid for r in index.nearby(-500000,0,300000,200000)}
    assert index.nearby(0,0,None,0,include_uuid='remote')[-1].uuid=='remote'
    assert index.nearby(0,0,1000000000,1000000000)==tuple(rows)


@pytest.mark.parametrize('cell',[0,-1,False,1.5])
def test_invalid_grid_rejected(cell):
    with pytest.raises(ValueError):HoleIndex([],cell_nm=cell)


@pytest.mark.parametrize('drill,gap',[(-1,0),(0,-1),(float('nan'),0),(0,float('inf'))])
def test_invalid_query_rejected(drill,gap):
    with pytest.raises(ValueError):HoleIndex([]).nearby(0,0,drill,gap)


def populated_board(tmp_path):
    data=fixture(tmp_path,spacing=5);path=data[0]
    board=pcbnew.LoadBoard(str(path));board.Add(pcbnew.NETINFO_ITEM(board,'FOREIGN'))
    rng=random.Random(41)
    for i in range(40):
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(rng.uniform(10,30),rng.uniform(10,30)))
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetDrill(pcbnew.FromMM(.3 if i%2 else .6));via.SetWidth(pcbnew.FromMM(.9))
        via.SetNet(board.FindNet('FOREIGN' if i%2 else 'RENAMED'));board.Add(via)
    pcbnew.SaveBoard(str(path),board,True)
    return pcbnew.LoadBoard(str(path)),data


def test_loaded_native_guard_matches_exhaustive_reason_and_first_blocker(tmp_path):
    board,_=populated_board(tmp_path);index=cec_fr._via_hole_snapshot(board)
    # Serialization proves the snapshot contains values, not retained SWIG
    # proxies whose lifetime could follow a removed/replaced board item.
    json.dumps([asdict(r) for r in index.rows])
    rng=random.Random(777)
    points=[(r.x,r.y) for r in index.rows]+[(pcbnew.FromMM(rng.uniform(10,30)),
        pcbnew.FromMM(rng.uniform(10,30))) for _ in range(60)]
    for x,y in points:
        at=pcbnew.VECTOR2I(x,y);plain={};fast={}
        args=(board,at,pcbnew.FromMM(.6),pcbnew.FromMM(.2),{board.GetNetcodeFromNetname('RENAMED')})
        kwargs=dict(drill_nm=pcbnew.FromMM(.3),net_code=board.GetNetcodeFromNetname('RENAMED'))
        expected=cec_fr._via_spot_clear(*args,report=plain,**kwargs)
        actual=cec_fr._via_spot_clear(*args,report=fast,_via_holes=index,**kwargs)
        assert (actual,fast)==(expected,plain)


@pytest.mark.parametrize('mode',['same','wrong_origin','wrong_net','missing'])
def test_replacement_verdict_and_evidence_parity(tmp_path,mode):
    board,_=populated_board(tmp_path);index=cec_fr._via_hole_snapshot(board);hole=index.rows[0]
    at=pcbnew.VECTOR2I(hole.x+(10000000 if mode=='wrong_origin' else 0),hole.y)
    kwargs=dict(drill_nm=300000,net_code=hole.net_code+(100 if mode=='wrong_net' else 0),
                existing_via_uuid='missing' if mode=='missing' else hole.uuid)
    a={};b={}
    expected=cec_fr._via_spot_clear(board,at,600000,200000,{hole.net_code},report=a,**kwargs)
    actual=cec_fr._via_spot_clear(board,at,600000,200000,{hole.net_code},report=b,_via_holes=index,**kwargs)
    assert (actual,b)==(expected,a)


def test_next_plan_rebuilds_after_same_count_native_geometry_change(tmp_path):
    data=fixture(tmp_path,spacing=5);board=pcbnew.LoadBoard(str(data[0]))
    _,a,b,side,other,_=data
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(20,30))
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetDrill(300000);via.SetWidth(600000);via.SetNet(board.FindNet('RENAMED'));board.Add(via)
    original=cec_fr._via_hole_snapshot;captured=[]
    def capture(board):
        index=original(board);captured.append(index);return index
    def solve():
        return cec_fr._lastmile_bridge(board,(a.x,a.y),{side},(b.x,b.y),{side},200000,
            board.GetNetcodeFromNetname('RENAMED'),[other],200000,allow_maze=False,
            allow_lattice=False,seat_offsets_mm=())
    with patch.object(cec_fr,'_via_hole_snapshot',side_effect=capture):
        assert solve()
        via.SetPosition(pcbnew.VECTOR2I(a.x+100000,a.y))
        assert solve() is None
    assert len(captured)==2 and captured[0] is not captured[1]
    assert len(captured[0].rows)==len(captured[1].rows)==1
    assert captured[0].rows[0].y!=captured[1].rows[0].y
    # A deliberately stale snapshot misses the moved hole. The production
    # plan never reuses it merely because the board identity/count is equal.
    assert not captured[0].nearby(a.x,a.y,300000,200000)
    assert captured[1].nearby(a.x,a.y,300000,200000)

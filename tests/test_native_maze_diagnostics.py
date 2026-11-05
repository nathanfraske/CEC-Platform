"""Search telemetry must not change routing or grant a no-path/ripup proof."""
import time
import pytest
import cec_swig_guard; cec_swig_guard.pin()
import pcbnew
import cec_fr as fr


def native_board():
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(2)
    net=pcbnew.NETINFO_ITEM(b,'renamed-synthetic-demand');b.Add(net)
    for A,B in [((0,0),(8,0)),((8,0),(8,8)),((8,8),(0,8)),((0,8),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(pcbnew.FromMM(.05))
        edge.SetStart(pcbnew.VECTOR2I_MM(*A));edge.SetEnd(pcbnew.VECTOR2I_MM(*B));b.Add(edge)
    return b,net.GetNetCode()


def search(b,code,*,diagnostics,guard=lambda A,B,R:True):
    return fr._maze_lastmile_legs(b,pcbnew.VECTOR2I_MM(2,2),pcbnew.VECTOR2I_MM(4,2),
        200000,pcbnew.F_Cu,200000,code,guard,grid_mm=.5,margin_mm=2.,
        deadline_monotonic=time.monotonic()+2.,diagnostics=diagnostics)


def shape(legs):
    return [(list(A),list(B),W) for A,B,W in legs]


def assert_no_authority(d):
    assert d['no_path_proof'] is False
    assert d['automatic_ripup_authorized'] is False
    assert d['release_authority'] is False
    assert d['diagnostic_scope']=='bounded_search_telemetry_only'
    assert len(d['blocked_frontier'])<=24


def test_success_matches_telemetry_disabled_native_path():
    b,code=native_board();d={}
    before=[(list(x.GetStart()),list(x.GetEnd())) for x in b.GetDrawings()]
    plain=search(b,code,diagnostics=None);observed=search(b,code,diagnostics=d)
    assert plain and shape(plain)==shape(observed)
    assert d['stop']=='path_found_receiving_required'
    assert d['returned_leg_count']==len(observed)
    assert d['search_counts']['expanded_states']>0
    assert d['nearest_expanded_point']['point_nm']==[4000000,2000000]
    assert d['lattice_constructed'] is True
    assert before==[(list(x.GetStart()),list(x.GetEnd())) for x in b.GetDrawings()]
    assert_no_authority(d)


@pytest.mark.parametrize('stage',['caller_native_guard','native_foreign_shape_guard','frozen_priority_reservation_guard'])
def test_blocked_hops_identify_stage_without_new_authority(monkeypatch,stage):
    b,code=native_board();d={};guard=lambda A,B,R:True
    if stage=='caller_native_guard':
        guard=lambda A,B,R:False
        def forbidden(*args,**kwargs):raise AssertionError('short-circuit changed')
        monkeypatch.setattr(fr,'_snapshot_foreign_clear',forbidden)
    elif stage=='native_foreign_shape_guard':
        monkeypatch.setattr(fr,'_snapshot_foreign_clear',lambda *a,**kw:False)
    else:
        monkeypatch.setattr(fr,'_tap_reservation_hits',lambda *a,**kw:['explicit-synthetic-reservation'])
    assert search(b,code,diagnostics=d,guard=guard) is None
    assert d['stop']=='bounded_lattice_exhausted_not_global_no_path'
    assert d['search_counts']['blocked_hops']>0
    assert {row['refusal_stage'] for row in d['blocked_frontier']}=={stage}
    assert d['nearest_expanded_point']['point_nm']==[2000000,2000000]
    assert_no_authority(d)


@pytest.mark.parametrize('inside',[False,True])
def test_deadline_distinguishes_search_phase_without_renewal(monkeypatch,inside):
    b,code=native_board();d={};calls=[]
    def exhausted(deadline):
        calls.append(deadline);return len(calls)>(1 if inside else 0)
    monkeypatch.setattr(fr._search_budget,'exhausted',exhausted)
    assert search(b,code,diagnostics=d) is None
    assert d['stop']==('search_deadline_inside_lattice' if inside else 'search_deadline_before_lattice')
    assert d['lattice_constructed']==inside
    assert len(set(calls))==1
    assert_no_authority(d)


def test_foreign_endpoint_stops_before_lattice_and_retains_identity_semantics():
    b,code=native_board();d={};other=pcbnew.NETINFO_ITEM(b,'unrelated-native-net');b.Add(other)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('RENAMED_BLOCKER')
    pad=pcbnew.PAD(fp);pad.SetNumber('7');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    pad.SetPosition(pcbnew.VECTOR2I_MM(4,2));pad.SetNetCode(other.GetNetCode());fp.Add(pad);b.Add(fp)
    assert search(b,code,diagnostics=d) is None
    assert d['stop']=='native_endpoint_cap_blocked_before_lattice'
    assert d['lattice_constructed'] is False
    assert d['native_endpoint_caps'][-1]['native_foreign_cap_clear'] is False
    assert d['search_counts']['tested_hops']==0
    assert_no_authority(d)


def test_frontier_storage_is_bounded_and_deterministic(monkeypatch):
    b,code=native_board()
    monkeypatch.setattr(fr,'_snapshot_foreign_clear',
        lambda A,B,W,C,Z,P:max(A.x,B.x)<3000000)
    results=[]
    for _ in range(2):
        d={};assert search(b,code,diagnostics=d) is None
        assert d['search_counts']['blocked_hops']>24
        assert len(d['blocked_frontier'])==24
        assert_no_authority(d);results.append(d['blocked_frontier'])
    assert results[0]==results[1]

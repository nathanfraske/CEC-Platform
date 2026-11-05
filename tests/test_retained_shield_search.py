"""An ordinary legal barrel must not silently cut an unrelated source shield."""
import math
import pcbnew
import pytest
import cec_field_coupling as field
import cec_fr as fr
from cec_field_search import RetainedShieldSearchGuard


def native_shield(tmp_path,turn=0,mirror=False):
    from test_field_coupling import FieldCouplingTest
    path=FieldCouplingTest()._board(str(tmp_path),[
        ('opaque-driver-97','F.Cu',(6.,9.),(24.,9.)),
        ('opaque-input-14','In2.Cu',(6.,13.),(24.,13.))])
    b=pcbnew.LoadBoard(path)
    def point(x,y):
        x,y=x-15,y-10
        if mirror:x=-x
        for _ in range(turn):x,y=-y,x
        return pcbnew.VECTOR2I_MM(x+15,y+10)
    for t in b.GetTracks():
        start,end=t.GetStart(),t.GetEnd()
        t.SetStart(point(start.x/1e6,start.y/1e6));t.SetEnd(point(end.x/1e6,end.y/1e6))
        if t.GetNetname()=='opaque-input-14':t.SetWidth(2000000)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    resolve=lambda name:{'name':{'opaque-driver-97':'SwitchNode','opaque-input-14':'Analog'}.get(name,'Default')}
    return b,path,point,resolve


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_native_clear_barrel_is_pruned_before_it_breaks_measured_source_shield(tmp_path,turn,mirror):
    b,path,point,resolve=native_shield(tmp_path,turn,mirror)
    before=field._field_snapshot_inventory(b)
    source=field.field_coupling_summary(path,board=b,_netclass_resolver=resolve)
    assert source['ok'] and source['interactions'][0]['shield']['shielded']
    guard=RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,netclass_resolver=resolve)
    assert guard.active and guard.report()['relations']==1
    assert not guard(point(15,11),600000,200000)
    assert guard(point(15,17),600000,200000)
    assert field._field_snapshot_inventory(b)==before
    n=pcbnew.NETINFO_ITEM(b,'opaque-control-32');b.Add(n)
    assert fr._via_spot_clear(b,point(15,11),600000,200000,{n.GetNetCode()},drill_nm=300000,net_code=n.GetNetCode())
    v=pcbnew.PCB_VIA(b);v.SetPosition(point(15,11));v.SetWidth(600000);v.SetDrill(300000)
    v.SetNet(n);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(v)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    after=field.field_coupling_summary(path,board=b,_netclass_resolver=resolve)
    assert not after['ok'] and after['blocking_count']==1
    assert not guard.report()['shielding_qualified'] and not guard.report()['release_authority']
    assert not guard.report()['no_path_proof']


def test_unfilled_role_and_ground_barrel_are_not_fictional_shield_authority(tmp_path):
    b,path,point,resolve=native_shield(tmp_path)
    gnd=RetainedShieldSearchGuard(b,'GND',board_path=path,netclass_resolver=resolve)
    assert not gnd.active and gnd(point(15,11),600000,200000)
    for zone in b.Zones():zone.UnFill()
    hint=RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,netclass_resolver=resolve)
    assert not hint.active and hint(point(15,11),600000,200000)
    assert not field.field_coupling_summary(path,board=b,_netclass_resolver=resolve)['ok']
    assert not hint.report()['shielding_qualified']


def test_fresh_snapshot_rebinds_changed_native_geometry(tmp_path):
    b,path,point,resolve=native_shield(tmp_path)
    old=RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,netclass_resolver=resolve)
    assert old.active
    victim=next(t for t in b.GetTracks() if t.GetNetname()=='opaque-input-14')
    b.Delete(victim)
    fresh=RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,netclass_resolver=resolve)
    assert not fresh.active and fresh(point(15,11),600000,200000)


@pytest.mark.parametrize('kwargs',[dict(max_samples=1),dict(max_relations=0),
    dict(max_samples=131073),dict(max_interactions=0),dict(max_interactions=131073),
    dict(max_interactions=True),dict(timeout_s=11.),dict(timeout_s=float('nan'))])
def test_source_search_snapshot_is_explicitly_bounded(tmp_path,kwargs):
    b,path,point,resolve=native_shield(tmp_path)
    with pytest.raises(ValueError):RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,netclass_resolver=resolve,**kwargs)


def test_source_interaction_work_is_not_the_filtered_shield_relation_limit(tmp_path, monkeypatch):
    b,path,point,resolve=native_shield(tmp_path)
    real=field.field_coupling_summary
    def with_extra_source_work(*args,**kwargs):
        work=kwargs['_work']
        for _ in range(3):work.consume('interactions')
        return real(*args,**kwargs)
    monkeypatch.setattr(field,'field_coupling_summary',with_extra_source_work)
    guard=RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,
        netclass_resolver=resolve,max_relations=1,max_interactions=8)
    assert guard.relations==1 and guard.source_interactions==4
    assert not guard(point(15,11),600000,200000)
    with pytest.raises(ValueError,match='interactions_budget'):
        RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,
            netclass_resolver=resolve,max_relations=1,max_interactions=3)


def test_more_inspection_work_does_not_expand_the_actual_shield_relation_budget(tmp_path, monkeypatch):
    b,path,point,resolve=native_shield(tmp_path)
    real=field.field_coupling_summary
    def duplicate_relation(*args,**kwargs):
        summary=real(*args,**kwargs)
        summary['interactions']*=2
        return summary
    monkeypatch.setattr(field,'field_coupling_summary',duplicate_relation)
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError,match='relation_bound'):
        RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,
            netclass_resolver=resolve,max_relations=1,max_interactions=8)
    assert before==field._field_snapshot_inventory(b)


def test_explicit_design_identity_reaches_source_policy_without_replacing_native_source(tmp_path, monkeypatch):
    b,path,point,resolve=native_shield(tmp_path)
    real=field.field_coupling_summary
    seen=[]
    def capture(*args,**kwargs):
        seen.append((args[0],kwargs['board'],kwargs['board_hint']))
        return real(*args,**kwargs)
    monkeypatch.setattr(field,'field_coupling_summary',capture)
    guard=RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,
        netclass_resolver=resolve,board_hint='unclassified-fixture')
    assert seen==[(path,b,'unclassified-fixture')]
    assert guard.report()['board_hint']=='unclassified-fixture'
    assert guard.active and not guard(point(15,11),600000,200000)


@pytest.mark.parametrize('hint', ['', ' ', True, 7])
def test_invalid_explicit_design_identity_is_not_silently_inferred(tmp_path, hint):
    b,path,point,resolve=native_shield(tmp_path)
    with pytest.raises(ValueError,match='identity'):
        RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,
            netclass_resolver=resolve,board_hint=hint)


def test_index_queries_match_complete_reserved_sample_scan(tmp_path):
    b,path,point,resolve=native_shield(tmp_path)
    guard=RetainedShieldSearchGuard(b,'opaque-control-32',board_path=path,netclass_resolver=resolve)
    for i in range(100):
        at=point(3.+i*.24,10.3+(i%5)*.35)
        radius=.3+max(.2,guard.clearance_mm)+1e-8
        expected=not any(math.dist(tuple(v/1e6 for v in at),p)<=radius for p in guard.points)
        assert guard(at,600000,200000) is expected


@pytest.mark.parametrize('turn',range(4))
def test_scoped_native_barrel_guard_wires_all_nested_searches_and_unwinds(tmp_path,turn):
    import time
    from cec_field_search import retained_shield_search
    b,path,point,resolve=native_shield(tmp_path,turn)
    name='opaque-control-32';b.Add(pcbnew.NETINFO_ITEM(b,name))
    code=b.GetNetcodeFromNetname(name)
    guard=RetainedShieldSearchGuard(b,name,board_path=path,netclass_resolver=resolve)
    before=field._field_snapshot_inventory(b)
    def query(at,board=b):
        return fr._via_spot_clear(board,at,600000,200000,{code},drill_nm=300000,net_code=code)
    assert query(point(15,11))
    with retained_shield_search(b,guard,deadline=time.monotonic()+5):
        assert not query(point(15,11))
        assert query(point(15,17))
        # The scope cannot spill into another board, even with a matching net.
        other=pcbnew.BOARD();other.Add(pcbnew.NETINFO_ITEM(other,name))
        assert fr._via_spot_clear(other,point(15,11),600000,200000,
            {other.GetNetcodeFromNetname(name)},drill_nm=300000,net_code=other.GetNetcodeFromNetname(name))
        with pytest.raises(ValueError):
            with retained_shield_search(b,guard,deadline=time.monotonic()+5):pass
    assert query(point(15,11)) and field._field_snapshot_inventory(b)==before


def test_scoped_native_barrel_guard_unwinds_exceptions(tmp_path):
    import time
    from cec_field_search import retained_shield_search,retained_shield_barrel_allowed
    b,path,point,resolve=native_shield(tmp_path)
    name='opaque-control-32';b.Add(pcbnew.NETINFO_ITEM(b,name));code=b.GetNetcodeFromNetname(name)
    guard=RetainedShieldSearchGuard(b,name,board_path=path,netclass_resolver=resolve)
    with pytest.raises(RuntimeError):
        with retained_shield_search(b,guard,deadline=time.monotonic()+5):
            assert not retained_shield_barrel_allowed(b,point(15,11),600000,200000,code)
            raise RuntimeError('private search failed')
    assert retained_shield_barrel_allowed(b,point(15,11),600000,200000,code)

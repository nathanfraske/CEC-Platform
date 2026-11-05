"""A local frozen pocket must not relax any other zone or global work bound."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_native_frozen_zone_access as access
from test_native_frozen_zone_access import fixture


def case(tmp_path,count=34,rotation=0):
    path,net,rotate=fixture(tmp_path,rotation);b=pcbnew.LoadBoard(str(path));root=next(iter(b.Zones()))
    uid=force._uid(root)
    for index in range(count-1):
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.B_Cu);z.SetNet(root.GetNet())
        z.SetLocalClearance(root.GetLocalClearance());z.SetMinThickness(root.GetMinThickness())
        z.Outline().BooleanAdd(root.Outline())
        z.SetFilledPolysList(pcbnew.B_Cu,pcbnew.SHAPE_POLY_SET(root.GetFilledPolysList(pcbnew.F_Cu)))
        z.SetIsFilled(True)
        # Native fill remains literal saved evidence; no refill authority is
        # inferred from the duplicates or their remote/other-face location.
        b.Add(z)
    field._save_field_snapshot(b,path)
    return b,path,net,rotate,uid


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_many_zone_board_can_use_one_exact_local_pocket_without_raising_limit(tmp_path,rotation):
    b,path,net,rotate,uid=case(tmp_path,rotation=rotation);before=path.read_bytes()
    with pytest.raises(ValueError,match='count_bound'):
        with access.frozen(b,path):pass
    start,end=[pcbnew.VECTOR2I_MM(*rotate(p)) for p in ((9,10),(11,10))]
    code=b.GetNetcodeFromNetname(net);cache={}
    assert not fr._tap_foreign_clear(b,start,end,200000,0,200000,{code},foreign_cache=cache)
    with access.frozen(b,path,zone_uuids=[uid]) as proof:
        assert fr._tap_foreign_clear(b,start,end,200000,0,200000,{code},foreign_cache=cache)
        assert proof['reserved_zones']==1 and proof['explicit_frozen_zone_uuids']==[uid]
        selected=next(z for z in b.Zones() if force._uid(z)==uid)
        other=next(z for z in b.Zones() if force._uid(z)!=uid)
        assert access.obstacle(b,other,pcbnew.B_Cu).Format()==other.Outline().Format()
        assert access.obstacle(b,selected,0).Format()==selected.GetFilledPolysList(0).Format()
        assert not proof['release_authority'] and not proof['power_authority']
    assert proof['source_and_zones_unchanged'] and access.cache_token(b) is None
    assert not fr._tap_foreign_clear(b,start,end,200000,0,200000,{code},foreign_cache=cache)
    assert path.read_bytes()==before


@pytest.mark.parametrize('fault',['clearance','fill','outline'])
def test_unselected_zone_mutation_is_not_hidden_by_a_local_scope(tmp_path,fault):
    b,path,net,rotate,uid=case(tmp_path);other=next(z for z in b.Zones() if force._uid(z)!=uid)
    with pytest.raises(ValueError,match='changed_during_search'):
        with access.frozen(b,path,zone_uuids=[uid]):
            if fault=='clearance':other.SetLocalClearance(600000)
            elif fault=='fill':other.UnFill()
            else:other.Outline().Append(9000000,9000000)
    assert access.cache_token(b) is None


def test_unselected_changed_zone_cannot_return_a_guard_obstacle(tmp_path):
    b,path,net,rotate,uid=case(tmp_path);other=next(z for z in b.Zones() if force._uid(z)!=uid)
    with pytest.raises(ValueError,match='reserved_zone_changed'):
        with access.frozen(b,path,zone_uuids=[uid]):
            other.UnFill();access.obstacle(b,other,pcbnew.B_Cu)
    assert access.cache_token(b) is None


@pytest.mark.parametrize('scope',[[],['missing'],['duplicate','duplicate'],[''],[True],False,'not-a-list'])
def test_unbounded_or_unavailable_scope_never_creates_an_implicit_all_fill_mode(tmp_path,scope):
    b,path,net,rotate,uid=case(tmp_path)
    with pytest.raises(ValueError,match='scope'):
        with access.frozen(b,path,zone_uuids=scope):pass
    assert access.cache_token(b) is None


def test_source_binding_still_covers_every_unselected_saved_zone(tmp_path):
    b,path,net,rotate,uid=case(tmp_path);next(z for z in b.Zones() if force._uid(z)!=uid).UnFill()
    with pytest.raises(ValueError,match='differ_from_saved_source'):
        with access.frozen(b,path,zone_uuids=[uid]):pass


def test_scoped_dispatch_keeps_independent_source_and_callback_exception_checks(tmp_path):
    b,path,net,rotate,uid=case(tmp_path)
    result,proof=access.search(b,path,lambda:access.cache_token(b) is not None,zone_uuids=[uid])
    assert result and proof['reserved_zones']==1 and proof['source_and_zones_unchanged']
    with pytest.raises(RuntimeError,match='callback'):
        access.search(b,path,lambda:(_ for _ in ()).throw(RuntimeError('callback')),zone_uuids=[uid])
    assert access.cache_token(b) is None

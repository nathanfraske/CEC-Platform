"""Existing filled pockets are not permission to cut actual power copper."""
import math
import pcbnew
import pytest
import cec_fr as fr
import cec_field_coupling as field
import cec_native_frozen_zone_access as access
from test_lastmile import _board


def fixture(tmp_path,rotation=0,prefix='/renamed/'):
    def rotate(at):
        a=math.radians(rotation);x,y=at[0]-15,at[1]-15
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    bus,signal=prefix+'BUS',prefix+'SCALAR'
    b=_board([(*rotate((6,6)),bus),(*rotate((10,10)),signal)],edge=(0,0,30,30))
    root=next(p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==signal)
    root.SetSize(pcbnew.VECTOR2I_MM(4,4))
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNetCode(b.GetNetcodeFromNetname(bus))
    z.SetLocalClearance(500000);z.SetMinThickness(100000)
    z.Outline().NewOutline()
    for at in ((5,5),(15,5),(15,15),(5,15)):
        z.Outline().Append(pcbnew.VECTOR2I_MM(*rotate(at)))
    b.Add(z);b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    path=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,path)
    return path,signal,rotate


@pytest.mark.parametrize('rotation,prefix',[(0,'/a/'),(90,'/hierarchy/'),(180,'/other/'),(270,'/last/')])
def test_existing_native_clearance_void_only_and_cache_isolation(tmp_path,rotation,prefix):
    path,net,rotate=fixture(tmp_path,rotation,prefix);original=path.read_bytes()
    b=pcbnew.LoadBoard(str(path));code=b.GetNetcodeFromNetname(net);cache={}
    s,t=[pcbnew.VECTOR2I_MM(*rotate(at)) for at in ((9,10),(11,10))]
    assert not fr._tap_foreign_clear(b,s,t,200000,pcbnew.F_Cu,200000,{code},foreign_cache=cache)
    with access.frozen(b,path) as proof:
        assert fr._tap_foreign_clear(b,s,t,200000,pcbnew.F_Cu,200000,{code})
        assert fr._tap_foreign_clear(b,s,t,200000,pcbnew.F_Cu,200000,{code},foreign_cache=cache)
        # Real filled copper still blocks both cached and uncached guards.
        bad_s,bad_t=[pcbnew.VECTOR2I_MM(*rotate(at)) for at in ((12.8,10),(14,10))]
        assert not fr._tap_foreign_clear(b,bad_s,bad_t,200000,pcbnew.F_Cu,200000,{code})
        assert not fr._tap_foreign_clear(b,bad_s,bad_t,200000,pcbnew.F_Cu,200000,{code},foreign_cache=cache)
        assert proof['release_authority'] is False and proof['receiving_still_required'] is True
    assert proof['source_and_zones_unchanged'] is True
    assert not fr._tap_foreign_clear(b,s,t,200000,pcbnew.F_Cu,200000,{code},foreign_cache=cache)
    assert path.read_bytes()==original and access.cache_token(b) is None


def test_unknown_fill_or_changed_source_zone_is_not_a_pocket(tmp_path):
    path,_,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(path));next(iter(b.Zones())).UnFill()
    with pytest.raises(ValueError,match='differ_from_saved_source'):
        with access.frozen(b,path):pass
    field._save_field_snapshot(b,path)
    with pytest.raises(ValueError,match='fill_unknown'):
        with access.frozen(b,path):pass


def test_zone_mutation_during_search_refuses_and_unwinds(tmp_path):
    path,_,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(path));z=next(iter(b.Zones()))
    with pytest.raises(ValueError,match='changed_during_search'):
        with access.frozen(b,path):z.SetLocalClearance(600000)
    assert access.cache_token(b) is None


def test_mutated_zone_cannot_supply_a_new_guard_shape(tmp_path):
    path,_,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(path));z=next(iter(b.Zones()))
    with pytest.raises(ValueError,match='reserved_zone_changed'):
        with access.frozen(b,path):
            z.UnFill();access.obstacle(b,z,pcbnew.F_Cu)
    assert access.cache_token(b) is None


def test_native_clone_not_mutable_context_authority(tmp_path):
    path,_,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(path));z=next(iter(b.Zones()))
    with access.frozen(b,path):
        first=access.obstacle(b,z,pcbnew.F_Cu);identity=first.Format()
        first.RemoveAllContours()
        assert access.obstacle(b,z,pcbnew.F_Cu).Format()==identity
        with pytest.raises(ValueError,match='nested'):
            with access.frozen(b,path):pass


@pytest.mark.parametrize('bounds',[{'timeout_s':0},{'timeout_s':True},{'timeout_s':float('nan')},
    {'max_zones':0},{'max_zones':33},{'max_zones':True}])
def test_invalid_explicit_mode_bounds(tmp_path,bounds):
    with pytest.raises(ValueError,match='bounded_frozen'):
        with access.frozen(None,tmp_path/'absent',**bounds):pass


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_individual_search_dispatch_keeps_default_outline_and_real_bus(tmp_path,rotation):
    path,net,rotate=fixture(tmp_path,rotation)
    b=pcbnew.LoadBoard(str(path));code=b.GetNetcodeFromNetname(net);cache={}
    s,t=[pcbnew.VECTOR2I_MM(*rotate(at)) for at in ((9,10),(11,10))]
    real_s,real_t=[pcbnew.VECTOR2I_MM(*rotate(at)) for at in ((12.8,10),(14,10))]
    def query():
        return (fr._tap_foreign_clear(b,s,t,200000,pcbnew.F_Cu,200000,{code},foreign_cache=cache),
                fr._tap_foreign_clear(b,real_s,real_t,200000,pcbnew.F_Cu,200000,{code},foreign_cache=cache))
    assert query()==(False,False)
    for _ in range(2):
        result,proof=access.search(b,path,query)
        assert result==(True,False) and proof['source_and_zones_unchanged'] is True
        assert proof['release_authority'] is False and proof['power_authority'] is False
        assert query()==(False,False) and access.cache_token(b) is None


def test_search_dispatch_does_not_hide_mutation_or_callback_failure(tmp_path):
    path,_,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(path))
    with pytest.raises(ValueError,match='changed_during_search'):
        access.search(b,path,lambda:next(iter(b.Zones())).UnFill())
    assert access.cache_token(b) is None
    b=pcbnew.LoadBoard(str(path))
    def fail():raise RuntimeError('finite_search_failed')
    with pytest.raises(RuntimeError,match='finite_search_failed'):
        access.search(b,path,fail)
    assert access.cache_token(b) is None
    with pytest.raises(ValueError,match='callback_required'):
        access.search(b,path,None)

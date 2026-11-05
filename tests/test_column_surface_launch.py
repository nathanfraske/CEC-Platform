"""A different middle layer must not fund the same fixed pad-side U-turn."""
import time
import pcbnew
import pytest
import cec_column_surface_launch as launch
import cec_field_coupling as field


def fixture(turn=0,back=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6);n=pcbnew.NETINFO_ITEM(b,'renamed_rail');b.Add(n)
    f=pcbnew.FOOTPRINT(b);f.SetReference('unrelated_terminal');b.Add(f)
    p=pcbnew.PAD(f);p.SetNumber('1');p.SetNet(n);p.SetPosition(pcbnew.VECTOR2I(10000000,10000000))
    p.SetSize(pcbnew.VECTOR2I(700000,700000));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetLayerSet(pcbnew.PAD.SMDMask());f.Add(p)
    old=pcbnew.PCB_TRACK(b);old.SetNet(n);old.SetLayer(pcbnew.F_Cu);old.SetWidth(500000)
    old.SetStart(pcbnew.VECTOR2I(10000050,10000045));old.SetEnd(pcbnew.VECTOR2I(7000000,10000045));b.Add(old)
    endpoints=[]
    for x in (10000000,8000000,12000000):
        marker=pcbnew.PCB_TRACK(b);marker.SetStart(pcbnew.VECTOR2I(x,10000000));marker.SetEnd(marker.GetStart());endpoints.append(marker)
    for item in [f,old,*endpoints]:
        if back:item.Flip(pcbnew.VECTOR2I(10000000,10000000),False)
        if turn:item.Rotate(pcbnew.VECTOR2I(10000000,10000000),pcbnew.EDA_ANGLE(90*turn,pcbnew.DEGREES_T))
    return b,[tuple(t.GetStart())for t in endpoints],int(old.GetLayer())


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_fixed_near_alias_backtrack_refuses_before_any_middle_route(turn,back):
    b,points,layer=fixture(turn,back);before=field._field_snapshot_inventory(b)
    scope=launch.SurfaceLaunch(b,'renamed_rail',deadline=time.monotonic()+2.)
    bad=scope.assess([(points[0],points[1],500000)],layer)
    assert bad['complete']and not bad['ok'],bad
    assert any(i['type']=='covered_backtrack'for i in bad['craft']['issues'])
    assert not bad['release_authority']and not bad['current_authority']
    good=scope.assess([(points[0],points[2],500000)],layer)
    assert good['ok']and good['complete'],good
    assert field._field_snapshot_inventory(b)==before
    again=scope.assess([(points[0],points[1],500000)],layer)
    assert again==bad and scope.report()['exact_same_plan_reuses']==1
    # Returned evidence cannot modify an owned cache entry.
    again['ok']=True;assert not scope.assess([(points[0],points[1],500000)],layer)['ok']


def test_cache_is_exact_geometry_and_plan_local_not_a_rounded_alias_waiver():
    b,points,layer=fixture();scope=launch.SurfaceLaunch(b,'renamed_rail',deadline=time.monotonic()+2.)
    assert scope.assess([(points[0],points[2],500000)],layer)['ok']
    one_nm=(points[0][0]+1,points[0][1])
    scope.assess([(one_nm,points[2],500000)],layer)
    assert scope.report()['exact_same_plan_reuses']==0
    other=launch.SurfaceLaunch(b,'renamed_rail',deadline=time.monotonic()+2.)
    assert other.report()['exact_same_plan_reuses']==0


@pytest.mark.parametrize('fault',['expired','float_coordinate','boolean_width','unknown_layer'])
def test_unknown_or_nonliteral_surface_scope_never_passes(fault):
    b,points,layer=fixture();scope=launch.SurfaceLaunch(b,'renamed_rail',deadline=time.monotonic()+2.)
    legs=[(points[0],points[2],500000)]
    if fault=='expired':scope.deadline=time.monotonic()-1
    elif fault=='float_coordinate':legs=[((10000000.,10000000),points[2],500000)]
    elif fault=='boolean_width':legs=[(points[0],points[2],True)]
    else:layer=9999
    assert not scope.assess(legs,layer)['ok']

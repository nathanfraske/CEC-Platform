"""One connected native keeper may have real, strictly disjoint windows."""
import copy,time
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_multi_keeper_contour as owner
import cec_native_fill_geometry as geometry
import cec_regional_fill as regional
from test_multi_keeper_contour import fixture


def case(tmp_path,face=pcbnew.F_Cu,rotate=False,bank_name=False):
    b,source,t,zones=fixture(tmp_path,face,rotate)
    xy=lambda p:(p[1],p[0]) if rotate else p
    shapes=[[(2.5,5.5),(4.5,5.5),(4.5,7.5),(9.5,7.5),
        (9.5,5.5),(11.5,5.5),(11.5,9.5),(2.5,9.5)],
        [(6.5,5.5),(7.5,5.5),(7.5,6.5),(6.5,6.5)]]
    for z,points in zip(zones,shapes):
        z.Outline().RemoveAllContours();z.Outline().NewOutline()
        for p in points:
            v=pcbnew.VECTOR2I_MM(*xy(p));z.Outline().Append(v.x,v.y)
    if bank_name:zones[0].SetZoneName(owner.bank.ZONE_NAME)
    b.BuildConnectivity();assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    field._save_field_snapshot(b,source)
    return b,source,t,zones


def plan(source,t,bank_name=False):
    return owner.plan(source,[force._uid(t)],allow_locked_source=True,
        fill_policy='source_preserving_regions',allow_compatible_keeper_classes=bank_name,
        clip_native_additions=True,native_addition_inset_nm=4)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,6])
@pytest.mark.parametrize('rotate',[False,True])
@pytest.mark.parametrize('bank_name',[False,True])
def test_strict_signed_window_roundtrips_native_writer_fill_and_whole_saved_replay(tmp_path,face,rotate,bank_name):
    b,source,t,zones=case(tmp_path,face,rotate,bank_name);original=source.read_bytes()
    p=plan(source,t,bank_name);shape=geometry.reconstruct(p['profile'],time.monotonic()+10.)
    assert shape.OutlineCount()==1 and shape.HoleCount(0)==1
    # This native build flags the legitimate closing-edge joint when its
    # polygon has holes. Acceptance instead requires exact signed topology,
    # then all ordinary native/current/field/cut and save/reload gates.
    import cec_exact_outline_topology as topology
    assert topology.require_one_polygon(p['profile'],deadline_monotonic=time.monotonic()+10.)['ok']
    made=owner.construct(b,p);child=force._copy_family(source,tmp_path/'child')
    field._save_field_snapshot(b,child);saved=pcbnew.LoadBoard(str(child));kept=next(iter(saved.Zones()))
    assert kept.Outline().HoleCount(0)==1
    assert geometry.identity(kept.Outline(),time.monotonic()+10.)==geometry.identity(shape,time.monotonic()+10.)
    for row in p['source_zones']:
        assert regional.exact_source_contour_present(kept.GetFilledPolysList(face),
            geometry.reconstruct(row['fill'],time.monotonic()+10.),time.monotonic()+10.)
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['filled_window','shifted_window','extra_window','lost_old_fill'])
def test_real_windows_and_literal_source_fill_are_still_independently_owned(tmp_path,fault):
    b,source,t,zones=case(tmp_path);p=plan(source,t)
    if fault!='lost_old_fill':
        if fault=='filled_window':p['profile'][0]=p['profile'][0][:1]
        elif fault=='shifted_window':p['profile'][0][1][0][0]+=1
        else:p['profile'][0].append(copy.deepcopy(p['profile'][0][1]))
        p.pop('plan_sha256');p['plan_sha256']=owner.owner._digest(p)
        before=field._field_snapshot_inventory(b)
        with pytest.raises(owner.Refused):owner.construct(b,p)
        assert field._field_snapshot_inventory(b)==before
        return
    made=owner.construct(b,p);kept=next(iter(b.Zones()))
    fill=kept.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    fill.RemoveOutline(fill.OutlineCount()-1);kept.SetFilledPolysList(pcbnew.F_Cu,fill)
    child=force._copy_family(source,tmp_path/'bad');field._save_field_snapshot(b,child)
    proof=owner.receive(source,child,[dict(plan=p,materialized=made)],board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors']

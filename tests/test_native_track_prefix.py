"""Only new copper may be shortened by exact full-width source coverage."""
import math

import pcbnew
import pytest

import cec_native_track_prefix as prefix
import cec_force_current as force
import cec_field_coupling as field


def fixture(*, layer=pcbnew.F_Cu, net='/ARBITRARY_RENAMED', source_width=200000):
    source=pcbnew.BOARD();source.SetCopperLayerCount(6)
    rail=pcbnew.NETINFO_ITEM(source,net);source.Add(rail)
    fp=pcbnew.FOOTPRINT(source);source.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(rail);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    ls=pcbnew.LSET();ls.AddLayer(layer);p.SetLayerSet(ls);p.SetPosition(pcbnew.VECTOR2I_MM(5,5));fp.Add(p)
    old=pcbnew.PCB_TRACK(source);old.SetNet(rail);old.SetLayer(layer);old.SetWidth(source_width)
    old.SetStart(pcbnew.VECTOR2I_MM(5,5));old.SetEnd(pcbnew.VECTOR2I_MM(5,6));source.Add(old)
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    childnet=pcbnew.NETINFO_ITEM(board,net);board.Add(childnet)
    return source,board,p,old,childnet,layer


def route(board,net,layer,points,width=200000):
    rows=[]
    for s,t in zip(points,points[1:]):
        item=pcbnew.PCB_TRACK(board);item.SetNet(net);item.SetLayer(layer);item.SetWidth(width)
        item.SetStart(pcbnew.VECTOR2I_MM(*s));item.SetEnd(pcbnew.VECTOR2I_MM(*t));board.Add(item);rows.append(item)
    return rows


@pytest.mark.parametrize('layer,net',[(pcbnew.F_Cu,'/ARBITRARY_ONE'),(pcbnew.B_Cu,'renamed_with_no_power_prefix')])
def test_partial_collinear_prefix_stops_at_exact_source_endpoint(layer,net):
    source,b,p,old,n,l=fixture(layer=layer,net=net)
    tracks=route(b,n,l,[(5,5),(5,7),(6,8)])
    before=field._field_snapshot_inventory(source)
    proof=prefix.clip(source,b,force._uid(p),tracks)
    assert tuple(tracks[0].GetStart())==(5000000,6000000)
    assert proof['trimmed_new_track_uuid']==force._uid(tracks[0])
    assert not proof['removed_new_track_uuids'] and not proof['source_material_removed_or_changed']
    assert before==field._field_snapshot_inventory(source)


def test_fully_covered_first_leg_is_removed_without_changing_original_stub():
    source,b,p,old,n,l=fixture();tracks=route(b,n,l,[(5,5),(5,5.5),(6,5.5)])
    discarded=force._uid(tracks[0]);before=field._field_snapshot_inventory(source)
    proof=prefix.clip(source,b,force._uid(p),tracks)
    assert proof['removed_new_track_uuids']==[discarded] and len(tracks)==len(list(b.GetTracks()))==1
    assert tuple(tracks[0].GetStart())==(5000000,5500000)
    assert before==field._field_snapshot_inventory(source)


@pytest.mark.parametrize('fault',['narrow_source','different_layer','different_direction'])
def test_native_noncoverage_never_becomes_a_prefix_exception(fault):
    source,b,p,old,n,l=fixture(source_width=100000 if fault=='narrow_source' else 200000)
    tracks=route(b,n,pcbnew.B_Cu if fault=='different_layer' else l,
        [(5,5),(6,5)] if fault=='different_direction' else [(5,5),(5,7)])
    before=field._field_snapshot_inventory(b)
    proof=prefix.clip(source,b,force._uid(p),tracks)
    assert not proof['removed_new_track_uuids'] and not proof['trimmed_new_track_uuid']
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['not_rooted','wrong_net','duplicate','old_material','foreign_board'])
def test_source_ownership_and_new_chain_scope_are_reproved_before_mutation(fault):
    source,b,p,old,n,l=fixture();tracks=route(b,n,l,[(5,5),(5,7)])
    if fault=='not_rooted':tracks[0].SetStart(pcbnew.VECTOR2I_MM(5,5.5))
    elif fault=='wrong_net':
        other=pcbnew.NETINFO_ITEM(b,'WRONG_NET');b.Add(other);tracks[0].SetNet(other)
    elif fault=='duplicate':tracks.append(tracks[0])
    elif fault=='foreign_board':
        foreign=pcbnew.BOARD();foreign.SetCopperLayerCount(6)
        other=pcbnew.NETINFO_ITEM(foreign,n.GetNetname());foreign.Add(other)
        tracks=route(foreign,other,l,[(5,5),(5,7)])
    else:tracks=[old]
    before=field._field_snapshot_inventory(b);source_before=field._field_snapshot_inventory(source)
    with pytest.raises(ValueError):prefix.clip(source,b,force._uid(p),tracks)
    assert before==field._field_snapshot_inventory(b) and source_before==field._field_snapshot_inventory(source)


@pytest.mark.parametrize('timeout',[0,True,math.nan,11])
def test_timeout_bounds_cannot_mutate_a_partial_prefix(timeout):
    source,b,p,old,n,l=fixture();tracks=route(b,n,l,[(5,5),(5,7)])
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):prefix.clip(source,b,force._uid(p),tracks,timeout_s=timeout)
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['same_code_different_net_name','unassigned_source','zero_width'])
def test_matching_integer_net_codes_alone_are_not_owned_prefix_authority(fault):
    source,b,p,old,n,l=fixture()
    if fault=='same_code_different_net_name':n.SetNetname('/DIFFERENT_CHILD_NET')
    elif fault=='unassigned_source':p.SetNetCode(0)
    tracks=route(b,n,l,[(5,5),(5,7)],width=0 if fault=='zero_width' else 200000)
    before=field._field_snapshot_inventory(b);source_before=field._field_snapshot_inventory(source)
    with pytest.raises(ValueError):prefix.clip(source,b,force._uid(p),tracks)
    assert before==field._field_snapshot_inventory(b) and source_before==field._field_snapshot_inventory(source)

"""Strict capsule union, not apparent endpoint or approximate area coverage."""
import math
import pcbnew
import pytest

import cec_contained_track_receiving as receiving
import cec_exact_overlap_stage as stage
import cec_field_coupling as field
import cec_force_current as force
import cec_additive_route_receiving as syntax
from cec_native_items import discard_items


def saved(tmp_path, rotation=0, mirror=False, layer=pcbnew.F_Cu, net_name='/USB_VBUS'):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,net_name);b.Add(net)
    c,s=round(math.cos(math.radians(rotation))),round(math.sin(math.radians(rotation)))
    def point(x,y):
        x=-x if mirror else x
        return pcbnew.VECTOR2I(40_000_000+c*x-s*y,40_000_000+s*x+c*y)
    tracks=[]
    for a,z,width in [((0,0),(9_000_000,0),1_000_000),
                      ((200_000,-200_000),(0,0),200_000)]:
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(layer);t.SetWidth(width)
        t.SetStart(point(*a));t.SetEnd(point(*z));t.SetLocked(True);b.Add(t);tracks.append(t)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    return source,[force._uid(t) for t in tracks]


def child(source, tmp_path, ids):
    candidate=force._copy_family(source,tmp_path/'candidate')
    b=pcbnew.LoadBoard(str(candidate));live={force._uid(t):t for t in b.GetTracks()}
    discard_items(b,[live[ids[1]]]);field._save_field_snapshot(b,candidate)
    return candidate


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('net_name',['/USB_VBUS','/UNRELATED/RENAMED_POWER'])
def test_saved_native_copper_union_has_no_orientation_catalog_or_board_special_case(
        tmp_path,rotation,mirror,layer,net_name):
    source,ids=saved(tmp_path,rotation,mirror,layer,net_name);original=source.read_bytes()
    candidate=child(source,tmp_path,ids);before=candidate.read_bytes()
    result=receiving.receive(source,candidate,source_track_uuids=ids)
    assert result['ok'] and result['complete'],result
    assert result['reciprocal_copper_coverage'] and result['every_surviving_source_track_unchanged']
    assert result['proofs'][0]['native_outward_minus_inward_empty']
    assert result['retired_track_uuids']==[ids[1]]
    assert not result['release_authority'] and not result['new_capacity_credited']
    assert source.read_bytes()==original and candidate.read_bytes()==before
    requests=stage.source_requests(source,allow_locked_source=True,normalization='strict_containment')
    assert len(requests['requests'])==1 and requests['requests'][0]['retired_track_uuid']==ids[1]
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['outside_1nm','tangent_only','different_net','different_layer',
    'equal_width','survivor_width','survivor_pose','survivor_lock','survivor_mask',
    'source_group','unscoped_track','unscoped_drawing','additional_track','all_retired',
    'no_retirement','unknown_fabrication'])
def test_visible_coverage_or_a_whole_board_score_cannot_waive_exact_source_ownership(tmp_path,fault):
    source,ids=saved(tmp_path);b=pcbnew.LoadBoard(str(source));tracks={force._uid(t):t for t in b.GetTracks()}
    narrow,wide=tracks[ids[1]],tracks[ids[0]]
    if fault in ('outside_1nm','tangent_only'):
        narrow.SetStart(pcbnew.VECTOR2I(40_200_000,39_600_000-(fault=='outside_1nm')))
    elif fault=='different_layer':narrow.SetLayer(pcbnew.B_Cu)
    elif fault=='equal_width':narrow.SetWidth(wide.GetWidth())
    elif fault=='source_group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(narrow)
    if fault=='unscoped_track':
        extra=pcbnew.PCB_TRACK(b);extra.SetNet(wide.GetNet());extra.SetWidth(200_000)
        extra.SetStart(pcbnew.VECTOR2I(60_000_000,60_000_000));extra.SetEnd(pcbnew.VECTOR2I(61_000_000,60_000_000));b.Add(extra)
    field._save_field_snapshot(b,source)
    candidate=force._copy_family(source,tmp_path/'candidate');b=pcbnew.LoadBoard(str(candidate))
    tracks={force._uid(t):t for t in b.GetTracks()};wide=tracks[ids[0]]
    if fault!='no_retirement':discard_items(b,[tracks[ids[1]]])
    if fault=='all_retired':discard_items(b,[wide])
    elif fault=='survivor_width':wide.SetWidth(wide.GetWidth()-1)
    elif fault=='survivor_pose':wide.SetStart(pcbnew.VECTOR2I(40_000_001,40_000_000))
    elif fault=='survivor_lock':wide.SetLocked(False)
    elif fault=='unscoped_track':next(t for uid,t in tracks.items() if uid not in ids).SetWidth(300_000)
    elif fault=='unscoped_drawing':
        shape=pcbnew.PCB_SHAPE(b);shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(pcbnew.VECTOR2I(1,1));shape.SetEnd(pcbnew.VECTOR2I(1000,1));b.Add(shape)
    elif fault=='additional_track':
        extra=pcbnew.PCB_TRACK(b);extra.SetNet(wide.GetNet());extra.SetWidth(200_000)
        extra.SetStart(pcbnew.VECTOR2I(40_000_000,40_000_000));extra.SetEnd(pcbnew.VECTOR2I(41_000_000,40_000_000));b.Add(extra)
    field._save_field_snapshot(b,candidate)
    if fault=='different_net':
        root,nodes=syntax._nodes(source)
        next(row for row in nodes[ids[1]] if isinstance(row,list) and row[0]=='net')[1]='"/OTHER_SUPPLY"'
        source.write_text(syntax._render(root))
    elif fault=='survivor_mask':
        root,nodes=syntax._nodes(candidate);nodes[ids[0]].append(['solder_mask_margin','0.1'])
        candidate.write_text(syntax._render(root))
    if fault=='unknown_fabrication':
        source.write_text(source.read_text().replace('(width 0.2)','(width 0.2) (future_material yes)',1))
    old,new=source.read_bytes(),candidate.read_bytes()
    result=receiving.receive(source,candidate,source_track_uuids=ids)
    assert not result['ok'] and result['errors'],result
    assert source.read_bytes()==old and candidate.read_bytes()==new


@pytest.mark.parametrize('scope',[[],['unknown'],['same','same'],'text',[{}],[True]])
def test_invalid_scope_is_never_authority(tmp_path,scope):
    source,ids=saved(tmp_path);candidate=child(source,tmp_path,ids)
    if scope==['unknown']:
        assert not receiving.receive(source,candidate,source_track_uuids=scope)['ok']
    else:
        with pytest.raises(ValueError):receiving.receive(source,candidate,source_track_uuids=scope)


@pytest.mark.parametrize('kwargs',[dict(timeout_s=0),dict(max_pairs=1),dict(coverage_margin_nm=1000)])
def test_bounds_and_positive_margins_are_real_not_numeric_waivers(tmp_path,kwargs):
    source,ids=saved(tmp_path);candidate=child(source,tmp_path,ids)
    result=receiving.receive(source,candidate,source_track_uuids=ids,**kwargs)
    assert result['ok']==(kwargs!=dict(timeout_s=0)),result


def test_locked_retirement_requires_explicit_constructor_scope_and_modes_do_not_leak(tmp_path):
    source,ids=saved(tmp_path);original=source.read_bytes()
    assert stage.source_requests(source,normalization='strict_containment')['requests']==[]
    assert stage.source_requests(source,allow_locked_source=True)['requests']==[]
    with pytest.raises(ValueError):stage.source_requests(source,normalization='guess')
    assert source.read_bytes()==original


def test_containment_geometry_refusal_still_precedes_electrical_receiving(tmp_path,monkeypatch):
    source,ids=saved(tmp_path);candidate=child(source,tmp_path,ids)
    monkeypatch.setattr(receiving,'receive',lambda *a,**kw:dict(ok=False,errors=['proof_refused']))
    result=stage.receive_saved(source,candidate,ids,board_hint='synthetic',sense_timeout_s=1,
        normalization='strict_containment')
    assert not result['ok'] and any('exact_source_copper_union_refused' in e for e in result['errors'])
    assert not result['release_authority'] and not result['new_capacity_credited']

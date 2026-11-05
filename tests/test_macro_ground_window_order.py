"""CUT geometry owns filling; UNCUT only owns priority/population checks."""
import time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_macro_ground_barrel_window as window
import cec_macro_priority_preflight as priority
import cec_native_construction_frame as frame
import cec_smd_macro_transport as macro
from cec_native_items import discard_items
from test_macro_ground_barrel_window import native_pair
from test_return_plane_preview import via
from test_field_proposals import track


def fresh_motion(parent,source,quarter=0):
    child=pcbnew.LoadBoard(str(source));owner=child.FindFootprintByReference('RENAMED_ORDINARY_OWNER')
    delta=((1000000,0),(0,-1000000),(-1000000,0),(0,1000000))[quarter]
    owner.Move(pcbnew.VECTOR2I(*delta));transport=macro.apply(parent,child)
    return child,transport


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_stale_Ground_is_prepared_internally_before_foreign_fill_not_net_retagged(tmp_path,monkeypatch,quarter,back):
    source,parent,_,_,ids,_=native_pair(tmp_path,monkeypatch,quarter=quarter,back=back)
    parent.Add(pcbnew.NETINFO_ITEM(parent,'SYNTHETIC_ADDITIONAL_SIGNAL'))
    def xy(point):
        x,y=point[0]-20,point[1]-30
        for _ in range(quarter):x,y=y,-x
        return(20+x,30+y)
    old=via(parent,'SYNTHETIC_ADDITIONAL_SIGNAL',xy((25,34)));uid=force._uid(old)
    additive._ground_refill(parent);field._save_field_snapshot(parent,source)
    parent=pcbnew.LoadBoard(str(source));child,transport=fresh_motion(parent,source,quarter)
    barrel=next(t for t in child.GetTracks()if force._uid(t)==uid)
    barrel.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in xy((25,35)))));before=source.read_bytes()
    # This extra synthetic motion deliberately has no standalone source-cut
    # authority. It exercises native sequencing only, not saved admission.
    with pytest.raises(ValueError,match='changed_saved_identity'):
        field._save_field_snapshot(child,tmp_path/'unfinished.kicad_pcb')
    result=window.apply(parent,child,transport,ids,timeout_s=9.)
    assert result['internal_ordinary_Ground_preparation']['complete']
    assert barrel.GetNetname()=='SYNTHETIC_ADDITIONAL_SIGNAL'
    field._save_field_snapshot(child,tmp_path/'valid-native-snapshot-not-admitted.kicad_pcb')
    assert before==source.read_bytes()and not result['routing_admitted']


def test_priority_independent_foreign_fill_uses_CUT_and_never_rebuilds_crossing_UNCUT(tmp_path,monkeypatch):
    source,parent,_,_,ids,_=native_pair(tmp_path,monkeypatch)
    parent.Add(pcbnew.NETINFO_ITEM(parent,'ORDINARY_OLD_SOURCE_EDGE'))
    old=track(parent,'ORDINARY_OLD_SOURCE_EDGE',(21,29),(21,31),layer=pcbnew.In2_Cu,width=.2)
    track(parent,'ORDINARY_OLD_SOURCE_EDGE',(28,35),(29,35),layer=pcbnew.In2_Cu,width=.2)
    uid=force._uid(old);additive._ground_refill(parent);field._save_field_snapshot(parent,source)
    parent=pcbnew.LoadBoard(str(source));uncut,transport=fresh_motion(parent,source)
    actual,fresh=fresh_motion(parent,source)
    discard_items(actual,[t for t in actual.GetTracks()if force._uid(t)==uid])
    assert transport==fresh
    before=frame.binding(uncut,time.monotonic()+9.)
    proof=window.apply(parent,actual,fresh,ids,timeout_s=9.)
    result=priority.inspect(parent,uncut,transport,board_hint='SYNTHETIC',timeout_s=9.,
        ground_barrel_clearance_window_uuids=ids,actual_ground_barrel_window_board=actual)
    assert result['ok']and proof['complete'],result
    assert frame.binding(uncut,time.monotonic()+9.)==before
    assert not result['current_or_clearance_qualified']and not result['release_authority']


@pytest.mark.parametrize('fault',['ground_fill','foreign_fill','ground_authorship'])
def test_window_requires_original_Source_zones_before_any_internal_Ground_preparation(tmp_path,monkeypatch,fault):
    source,parent,child,transport,ids,zone=native_pair(tmp_path,monkeypatch)
    q=next(z for z in child.Zones()if z.GetNetname()=='GND')if fault!='foreign_fill'else next(z for z in child.Zones()if force._uid(z)==zone)
    if fault=='ground_authorship':q.SetLocalClearance(q.GetLocalClearance()+1)
    else:
        layer=next(iter(q.GetLayerSet().CuStack()));shape=q.GetFilledPolysList(layer).CloneDropTriangulation()
        shape.Move(pcbnew.VECTOR2I(1,0));q.SetFilledPolysList(layer,shape)
    monkeypatch.setattr(window.fill,'compile_selected',lambda *a,**k:pytest.fail('entry fault reached native filling'))
    with pytest.raises(ValueError,match='original_Source_foreign_and_Ground_fills'):
        window.apply(parent,child,transport,ids,timeout_s=9.)


def test_frozen_zone_search_can_construct_tracks_without_changing_snapshot_zones(tmp_path,monkeypatch):
    source,parent,child,transport,ids,_=native_pair(tmp_path,monkeypatch)
    window.apply(parent,child,transport,ids,timeout_s=9.)
    with window.search_geometry(parent,child,transport,ids,timeout_s=9.)as proof:
        track(child,'GND',(28,35),(29,35),width=.2)
    assert proof['source_and_zones_unchanged']

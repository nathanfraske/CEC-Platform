"""Source geometry/width witnesses only; synthetic values are not ratings."""
import copy
import pcbnew
import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union
import cec_terminal_contact_sector as sector
from test_terminal_shadow_keeper_finish import fixture as base_fixture


def fixture(tmp_path,monkeypatch,*,quarter=0,mirror=False,face=pcbnew.F_Cu):
    source,request,body = base_fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face)
    board = pcbnew.LoadBoard(str(source)); zone = next(z for z in board.Zones()
        if sector.base.force._uid(z) == request['zone_uuid'])
    def at(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (round((30+x)*1e6),round((30+y)*1e6))
    branch = Polygon([at(-3.3,0),at(-2.7,0),at(-2.7,3.3),at(-3.3,3.3)])
    profile = unary_union([sector._shape(zone.Outline()),branch])
    zone.UnFill(); zone.Outline().RemoveAllContours();zone.Outline().Append(sector.base.native._poly(sector._points(profile)))
    fp=pcbnew.FOOTPRINT(board);board.Add(fp);fp.SetReference('S900_REAL_POUR_ONLY_PORT')
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNumber('1');pad.SetNet(zone.GetNet())
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetPosition(pcbnew.VECTOR2I(*at(-3,3)));pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    board.BuildConnectivity();assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    sector.base.field._save_field_snapshot(board,source)
    return source,request,body,sector.base.force._uid(pad)


def saved(tmp_path,monkeypatch,**kwargs):
    source,request,body,pad = fixture(tmp_path,monkeypatch,**kwargs)
    q=sector.plan(source,**request);board=sector.construct(source,q)
    child=sector.base.force._copy_family(source,tmp_path/'candidate')
    sector.base.field._save_field_snapshot(board,child)
    return source,child,q,body,pad


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_pour_only_branch_and_actual_source_width_survive_saved_cleanup(tmp_path,monkeypatch,quarter,mirror,face):
    source,child,q,body,pad=saved(tmp_path,monkeypatch,quarter=quarter,mirror=mirror,face=face)
    before=source.read_bytes();proof=sector.receive_literal(source,child,q)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_other_native_items_and_ground_sheets_literal']
    assert proof['every_surviving_native_partition_preserved']
    progress=proof['actual_saved_progress'];floor=progress['actual_native_source_floor_receiving']
    assert floor['every_positive_source_floor_port_partition_preserved']
    assert any(pad in row for row in floor['source_port_partitions'])
    assert progress['every_original_surviving_keeper_contact_material_preserved']
    assert progress['every_retained_source_width_capsule_enclosed']
    assert progress['removed_native_area_mm2'] >= .0025
    assert body in q['retained_track_uuids'] and q['selected_source_sectors']
    assert not proof['current_or_barrel_qualified'] and not proof['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['policy','source','floor','sector','outline','helper'])
def test_rehashed_or_forged_plan_cannot_repurpose_native_sector_or_current_authority(tmp_path,monkeypatch,fault):
    source,child,q,_,_=saved(tmp_path,monkeypatch);bad=copy.deepcopy(q)
    if fault=='policy':bad['policy']='forged'
    elif fault=='source':bad['source_sha256']='0'*64
    elif fault=='floor':bad['full_source_current_width_floor_nm']=1
    elif fault=='sector':bad['selected_source_sectors'][0]['normal']=[1,0]
    elif fault=='outline':bad['points_nm'][0][0]+=1
    else:bad['helper_sha256']={}
    proof=sector.receive_literal(source,child,bad)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('fault',['width','ground','drill','pose','new_track','contact_loss'])
def test_literal_saved_receiver_rejects_unowned_changes_or_missing_native_contact(tmp_path,monkeypatch,fault):
    source,child,q,body,pad=saved(tmp_path,monkeypatch);board=pcbnew.LoadBoard(str(child))
    if fault=='width':next(t for t in board.GetTracks() if sector.base.force._uid(t)==body).SetWidth(599999)
    elif fault=='ground':next(z for z in board.Zones() if z.GetNetname()=='GND').UnFill()
    elif fault=='drill':next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA').SetDrill(310000)
    elif fault=='pose':next(fp for fp in board.GetFootprints() if fp.GetReference()=='S900_REAL_POUR_ONLY_PORT').Move(pcbnew.VECTOR2I(1,0))
    elif fault=='contact_loss':next(z for z in board.Zones() if sector.base.force._uid(z)==q['zone_uuid']).UnFill()
    else:
        track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I_MM(10,10));track.SetEnd(pcbnew.VECTOR2I_MM(11,10));track.SetWidth(200000);board.Add(track)
    sector.base.field._save_field_snapshot(board,child)
    proof=sector.receive_literal(source,child,q)
    assert not proof['ok'] and proof['errors'],proof


def test_unchanged_contact_pixels_do_not_hide_a_newly_underfloor_pour_neck():
    def poly(points):return sector.base.native._poly([[round(x*1e6),round(y*1e6)] for x,y in points])
    old=poly([(0,0),(4,0),(4,1),(0,1)])
    new=poly([(0,0),(1,0),(1,.4),(3,.4),(3,0),(4,0),(4,1),(3,1),(3,.6),(1,.6),(1,1),(0,1)])
    contacts=[('a',poly([(.2,.2),(.8,.2),(.8,.8),(.2,.8)])),
        ('z',poly([(3.2,.2),(3.8,.2),(3.8,.8),(3.2,.8)]))]
    assert sector._floor_receive(old,old,contacts,400000)['ok']
    with pytest.raises(ValueError,match='source_floor_pour_port_partition_lost'):
        sector._floor_receive(old,new,contacts,400000)


def test_half_grid_proposal_is_not_rounded_to_appear_canonical():
    with pytest.raises(ValueError,match='without_rounding'):
        sector._points(Polygon([(0,0),(1,0),(1,.5),(0,1)]))


def test_no_unmodeled_side_port_is_not_permission_to_invent_a_new_branch(tmp_path,monkeypatch):
    source,request,_=base_fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='actual_bounded_pour_only_source_port_required'):
        sector.plan(source,**request)


def test_new_noncanonical_edge_is_not_excused_as_old_native_quantization():
    with pytest.raises(ValueError,match='not_inherited'):
        sector._edges([[0,0],[2,1],[4,0],[0,-2]],[[0,0],[4,0],[4,4],[0,4]])


def test_actual_stronger_native_void_cannot_be_restored_by_a_source_sector(tmp_path,monkeypatch):
    source,request,_,_=fixture(tmp_path,monkeypatch)
    board=pcbnew.LoadBoard(str(source));old=next(z for z in board.Zones()
        if sector.base.force._uid(z)==request['zone_uuid'])
    high=pcbnew.ZONE(board);high.SetNet(old.GetNet());high.SetLayer(pcbnew.F_Cu)
    high.SetAssignedPriority(10);high.SetMinThickness(100000);high.SetLocalClearance(200000)
    high.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    high.Outline().Append(sector.base.native._poly([[24000000,31000000],[27500000,31000000],
        [27500000,32000000],[24000000,32000000]]));board.Add(high)
    filled=sector.base.native._poly([[24000000,31000000],[25000000,31000000],
        [25000000,32000000],[24000000,32000000]])
    high.SetFilledPolysList(pcbnew.F_Cu,filled);high.SetIsFilled(True)
    sector.base.field._save_field_snapshot(board,source)
    q=sector.plan(source,**request)
    with pytest.raises(ValueError,match='intrudes_protected_native_void'):
        sector.construct(source,q)


def test_discovery_is_generic_bounded_and_does_not_construct_or_change_the_source(tmp_path,monkeypatch):
    source,request,_,_=fixture(tmp_path,monkeypatch);before=source.read_bytes()
    found=sector.discover(source,board_hint=request['board_hint'],allow_locked_source=True,maximum_trials=1)
    assert found['ok'] and found['complete'] and len(found['proposals'])==1
    assert found['proposals'][0]['target']['track_uuids']==request['track_uuids']
    assert not found['actual_geometry_constructed'] and not found['current_or_barrel_qualified']
    assert source.read_bytes()==before


def test_source_bounded_chord_closure_does_not_emit_envelope_scallops():
    original=Polygon([(0,0),(10000000,0),(10000000,3000000),(0,3000000)])
    scalloped=Polygon([(0,0),(10000000,0),(10000000,3000000),(7000000,3000000),
        (6500000,2500000),(3500000,2500000),(3000000,3000000),(0,3000000)])
    closed=sector._chord_closure(scalloped,original)
    assert closed.equals(original) and closed.covers(scalloped)


def test_chord_closure_never_covers_an_intentional_original_owner_reservation():
    original=Polygon([(0,0),(10000000,0),(10000000,3000000),(7000000,3000000),
        (7000000,2000000),(3000000,2000000),(3000000,3000000),(0,3000000)])
    closed=sector._chord_closure(original,original)
    assert closed.equals(original)

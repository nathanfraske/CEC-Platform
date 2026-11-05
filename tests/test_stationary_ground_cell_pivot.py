"""Source metal, not package motion, decides whether a GND lead must be cut."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
from cec_native_items import discard_items
from test_complete_cell_connections import native_source


def pivot_source(tmp_path,monkeypatch,*,quarter=0,back=False,fault=None):
    path,parent,unused,prior=native_source(tmp_path,monkeypatch,turn=quarter)
    refs=list(prior['poses']);owner=parent.FindFootprintByReference(refs[0])
    cap=parent.FindFootprintByReference(refs[1]);ground=owner.FindPadByNumber('2')
    if back:
        for fp in parent.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for pad in fp.Pads():
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(layers)
        for item in parent.GetTracks():
            if item.GetClass()=='PCB_TRACK':item.SetLayer(pcbnew.B_Cu)
    if fault=='quarter_rectangle':ground.SetSize(pcbnew.VECTOR2I_MM(.5,.7))
    elif fault=='offset':ground.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='unknown_return':
        discard_items(parent,[t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA'])
    turn=90 if fault=='quarter_rectangle' else 180
    pivot=ground.GetPosition();poses={}
    for fp in (owner,cap):
        detached=pcbnew.FOOTPRINT(fp);detached.Rotate(pivot,pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
        poses[fp.GetReference()]=[detached.GetPosition().x/1e6,detached.GetPosition().y/1e6,
            detached.GetOrientationDegrees()]
    if fault=='one_nm':poses[owner.GetReference()][0]+=.000001
    pcbnew.SaveBoard(str(path),parent);parent=pcbnew.LoadBoard(str(path))
    proposal=escape.prepare(parent,poses,board_hint='opaque',max_shift_mm=12.)
    board=pcbnew.LoadBoard(str(path));escape.apply_private(board,proposal)
    uid=force._uid(ground)
    return path,parent,board,proposal,uid


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_native_pivot_preserves_ground_lead_and_has_zero_emission_choice(tmp_path,monkeypatch,quarter,back):
    path,parent,board,proposal,uid=pivot_source(tmp_path,monkeypatch,quarter=quarter,back=back)
    fixed=proposal['native_stationary_ground_lands'][uid]
    assert fixed['source_return_mm']>.8 and fixed['inherited_return_not_immediate_access_qualification']
    assert not any(q['pad_uuid']==uid for q in proposal['ground_leaves'])
    contacts={r['track_uuid'] for r in proposal['row_plan']['source_incident_boundaries'] if r['pad_uuid']==uid}
    assert contacts and not contacts & set(proposal['retired_track_uuids'])
    request=escape.obligations(parent,board,proposal)['ground:'+uid]
    assert request['retained_stationary_source_return']==fixed
    before=row._source_binding(board)
    packet=escape.menus(board,{'ground:'+uid:request},board_path='opaque',board_hint='opaque')
    assert packet['domains']['ground:'+uid][0]['ops']==[]
    assert len(packet['domains']['ground:'+uid])==1
    detail=packet['diagnostics']['ground:'+uid]
    assert detail['inherited_exact_stationary_source_return_preserved']==fixed
    assert not detail['new_immediate_return_or_process_qualified']
    assert row._source_binding(board)==before


@pytest.mark.parametrize('fault',['one_nm','quarter_rectangle','offset'])
def test_near_centre_or_reoriented_native_metal_does_not_inherit_a_stationary_lead(tmp_path,monkeypatch,fault):
    path,parent,board,proposal,uid=pivot_source(tmp_path,monkeypatch,fault=fault)
    assert uid not in proposal.get('native_stationary_ground_lands',{})
    assert not escape.obligations(parent,board,proposal)['ground:'+uid].get('retained_stationary_source_return')


@pytest.mark.parametrize('fault',['drop','measurement','land_identity','via_identity'])
def test_producer_cannot_forge_or_omit_the_source_derived_stationary_return_scope(tmp_path,monkeypatch,fault):
    path,parent,board,proposal,uid=pivot_source(tmp_path,monkeypatch)
    q=copy.deepcopy(proposal)
    if fault=='drop':q.pop('native_stationary_ground_lands')
    elif fault=='measurement':q['native_stationary_ground_lands'][uid]['source_return_mm']=99.
    elif fault=='land_identity':q['native_stationary_ground_lands'][uid]['source_land_sha256']='not-native'
    else:q['native_stationary_ground_lands'][uid]['source_reference_via_uuid']='not-the-source-via'
    before=row._source_binding(parent)
    with pytest.raises(ValueError,match='stale_or_forged_complete_cell_proposal'):
        escape.apply_private(parent,q)
    assert row._source_binding(parent)==before


@pytest.mark.parametrize('fault',['missing_lead','missing_plane','bad_land_proof'])
def test_private_damage_or_missing_saved_reference_cannot_receive_an_inherited_zero_route(tmp_path,monkeypatch,fault):
    path,parent,board,proposal,uid=pivot_source(tmp_path,monkeypatch)
    request=escape.obligations(parent,board,proposal)['ground:'+uid]
    if fault=='missing_lead':
        ids={r['track_uuid'] for r in proposal['row_plan']['source_incident_boundaries'] if r['pad_uuid']==uid}
        discard_items(board,[t for t in board.GetTracks() if force._uid(t) in ids])
    elif fault=='missing_plane':
        for zone in board.Zones():zone.SetIsFilled(False)
    else:request=copy.deepcopy(request);request['retained_stationary_source_return']['source_land_sha256']='forged'
    before=row._source_binding(board)
    if fault=='bad_land_proof':
        with pytest.raises(ValueError,match='exact_stationary_source_ground_land_required'):
            escape.menus(board,{'ground:'+uid:request},board_path='opaque',board_hint='opaque')
    else:
        packet=escape.menus(board,{'ground:'+uid:request},board_path='opaque',board_hint='opaque')
        assert not packet['diagnostics']['ground:'+uid].get('inherited_exact_stationary_source_return_preserved')
        assert all(q['ops'] for q in packet['domains']['ground:'+uid])
    assert row._source_binding(board)==before


def test_unknown_source_ground_is_retained_as_copper_but_not_a_zero_route_witness(tmp_path,monkeypatch):
    path,parent,board,proposal,uid=pivot_source(tmp_path,monkeypatch,fault='unknown_return')
    assert proposal['native_stationary_ground_lands'][uid]['source_return_mm'] is None
    request=escape.obligations(parent,board,proposal)['ground:'+uid]
    assert not request.get('retained_stationary_source_return')

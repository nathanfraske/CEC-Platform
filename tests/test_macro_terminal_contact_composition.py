"""Generic native terminal contacts compose only into independently owned cuts.

Only synthetic ordinary/current authorities are supplied by these fixtures;
real native pad contacts, endpoint geometry and exact per-face widths are
exercised. No physical board qualification is asserted.
"""
import copy
import time
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_pad_incident_tracks as incident
from test_cell_macro_requests import moved_pair


def fixture(tmp_path, monkeypatch, turn=0, back=False, rated=False):
    board, unused, transport, via = moved_pair(tmp_path, dogbone=True,
        back=back, net_name='not_a_board_specific_name')
    if turn:
        for item in [*board.GetFootprints(), *board.GetTracks()]:
            item.Rotate(pcbnew.VECTOR2I_MM(3, 2), pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T))
    pad = next(p for f in board.GetFootprints() for p in f.Pads())
    leg = next(t for t in board.GetTracks() if t.GetClass() == 'PCB_TRACK')
    uid = force._uid(leg); face = int(leg.GetLayer())
    contact = next(q for q in incident.inspect(board, [pad])['contacts'] if q['track_uuid'] == uid)
    request = dict(kind='source_boundary', net=pad.GetNetname(), width_nm=int(leg.GetWidth()),
        a=dict(pad_uuid=force._uid(pad), at_nm=list(pad.GetPosition()), layers=[face]),
        b=dict(native_uuids=[uid], at_nm=contact['contact_nm'], layers=[face]),
        source_pad_track_contact=copy.deepcopy(contact))
    authority = dict(kind='positive_source_ordinary', native_source_uuid=uid)
    extra = dict(change=dict(uuid=uid, net=leg.GetNetname(),
        source_nm=[list(leg.GetStart()), list(leg.GetEnd())]), authority=authority)
    monkeypatch.setattr(compiler.ordinary, 'eligible_nets', lambda *a: {pad.GetNetname()})
    rail = None
    if rated:
        floor = int(leg.GetWidth())
        widths = {int(layer): floor for layer in board.GetEnabledLayers().CuStack()}
        other = next(layer for layer in widths if layer != face)
        widths[other] = 4*floor
        rail = dict(required_by_layer_nm=widths, current_authority={'synthetic_only': True})
        request.update(width_nm=4*floor, unchanged_full_rail_current_contract=copy.deepcopy(rail))
        authority.update(kind='unchanged_full_current_source_edge', source_plan=dict(
            scope='exact_bounded_whole_current_planar_reflow', retired_track_uuids=[uid],
            net=leg.GetNetname(), layer_id=face, width_nm=floor, full_current_floor_nm=floor))
        monkeypatch.setattr(compiler.cells, '_supply_current_widths', lambda *a: copy.deepcopy(rail))
    return board, pad, leg, request, extra, rail


@pytest.mark.parametrize('turn', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('rated', [False, True])
def test_arbitrary_request_name_keeps_exact_contact_and_whole_current_contract(
        tmp_path, monkeypatch, turn, back, rated):
    board, pad, leg, request, extra, rail = fixture(tmp_path, monkeypatch, turn, back, rated)
    before = row._source_binding(board); original = copy.deepcopy(request)
    pending, proof = compiler._compose_retained_demands(board,
        {'arbitrary_positive_contact': request}, [extra], board_hint='synthetic',
        deadline=time.monotonic()+10.)
    assert not pending and len(proof) == 1
    assert proof[0]['required_replacement_request_id'] == 'macro_boundary:'+force._uid(leg)
    bound = proof[0]['independent_native_terminal_contact_composition']
    assert bound['source_pad_track_contact'] == request['source_pad_track_contact']
    assert bound['literal_source_face_width_floor_nm'] == leg.GetWidth()
    assert proof[0]['original_request'] == original == request
    assert row._source_binding(board) == before
    if rated:
        assert request['width_nm'] > leg.GetWidth()
        assert proof[0]['original_request']['unchanged_full_rail_current_contract'] == rail


@pytest.mark.parametrize('fault', ['forged_contact', 'wrong_pad', 'interior', 'missing_authority',
    'wrong_authority_uuid', 'wrong_net', 'wrong_face', 'wrong_source_edge', 'changed_source_span',
    'ordinary_current_alias', 'too_wide_ordinary'])
def test_invented_or_non_equivalent_terminal_contacts_never_disappear(tmp_path, monkeypatch, fault):
    board, pad, leg, request, extra, rail = fixture(tmp_path, monkeypatch)
    if fault == 'forged_contact': request['source_pad_track_contact']['ref'] = 'fabricated'
    elif fault == 'wrong_pad': request['source_pad_track_contact']['pad_uuid'] = 'not-the-pad'
    elif fault == 'interior': request['b']['at_nm'][0] += 1
    elif fault == 'missing_authority': extra['authority'] = {}
    elif fault == 'wrong_authority_uuid': extra['authority']['native_source_uuid'] = 'another-edge'
    elif fault == 'wrong_net': request['net'] = 'other-net'
    elif fault == 'wrong_face': request['b']['layers'] = [int(pcbnew.B_Cu)]
    elif fault == 'wrong_source_edge': extra['change']['net'] = 'other-net'
    elif fault == 'changed_source_span': extra['change']['source_nm'][0][0] += 1
    elif fault == 'ordinary_current_alias': request['unchanged_full_rail_current_contract'] = {}
    else: request['width_nm'] += 1
    before = row._source_binding(board)
    with pytest.raises(ValueError):
        compiler._compose_retained_demands(board, {'not-a-retained-name': request}, [extra],
            board_hint='synthetic')
    assert row._source_binding(board) == before


@pytest.mark.parametrize('fault', ['changed_contract', 'missing_contract', 'too_thin_source',
    'lowered_request', 'wrong_current_face', 'wrong_current_source_width', 'extra_source_cut',
    'unknown_current', 'missing_context', 'invalid_lease'])
def test_current_contact_composition_cannot_reduce_or_forge_current_scope(tmp_path, monkeypatch, fault):
    board, pad, leg, request, extra, rail = fixture(tmp_path, monkeypatch, rated=True)
    hint = 'synthetic'; deadline = time.monotonic()+10.
    if fault == 'changed_contract': request['unchanged_full_rail_current_contract']['current_authority'] = {}
    elif fault == 'missing_contract': del request['unchanged_full_rail_current_contract']
    elif fault == 'too_thin_source': rail['required_by_layer_nm'][int(leg.GetLayer())] += 1
    elif fault == 'lowered_request': request['width_nm'] = leg.GetWidth()-1
    elif fault == 'wrong_current_face': extra['authority']['source_plan']['layer_id'] = int(pcbnew.B_Cu)
    elif fault == 'wrong_current_source_width': extra['authority']['source_plan']['width_nm'] += 1
    elif fault == 'extra_source_cut': extra['authority']['source_plan']['retired_track_uuids'].append('unowned')
    elif fault == 'unknown_current': monkeypatch.setattr(compiler.cells, '_supply_current_widths', lambda *a: None)
    elif fault == 'missing_context': hint = None
    else: deadline = time.monotonic()-1.
    before = row._source_binding(board)
    with pytest.raises(ValueError):
        compiler._compose_retained_demands(board, {'arbitrary-positive-contact': request}, [extra],
            board_hint=hint, deadline=deadline)
    assert row._source_binding(board) == before


def test_untyped_or_unowned_contact_stays_mandatory(tmp_path, monkeypatch):
    board, pad, leg, request, extra, rail = fixture(tmp_path, monkeypatch)
    untyped = copy.deepcopy(request); del untyped['source_pad_track_contact']
    for raw, extras in ((untyped, [extra]), (request, [])):
        pending, proof = compiler._compose_retained_demands(board, {'unowned': raw}, extras)
        assert pending == {'unowned': raw} and not proof


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_same_exact_contact_can_compose_into_existing_ordinary_base_endpoint_demand(
        tmp_path,monkeypatch,turn,back):
    board,pad,leg,request,extra,unused=fixture(tmp_path,monkeypatch,turn,back)
    uid=force._uid(leg);key='boundary:'+uid
    replacement=dict(kind='source_boundary',net=leg.GetNetname(),width_nm=leg.GetWidth(),
        a=copy.deepcopy(request['a']),b=dict(at_nm=list(leg.GetEnd()),layers=[int(leg.GetLayer())]))
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=row._source_binding(board),poses={pad.GetParentFootprint().GetReference():[1,1,0]},
        retired_track_uuids=[uid])
    old=copy.deepcopy(proposal);before=row._source_binding(board)
    pending,proof=compiler._compose_retained_demands(board,{key:replacement,'exact-contact':request},[],
        board_hint='synthetic',source_proposal=proposal)
    assert pending=={key:replacement}and len(proof)==1
    assert proof[0]['required_replacement_request_id']==key
    assert proof[0]['source_existing_base_endpoint_obligation_composed_not_omitted']
    assert proof[0]['required_replacement_request_ids']==[key]
    assert proposal==old and row._source_binding(board)==before


@pytest.mark.parametrize('fault',['missing_base_demand','wrong_pad','wrong_net','too_narrow',
    'stale_binding','wrong_scope','unselected_owner','supply_alias'])
def test_base_endpoint_composition_cannot_lose_or_invent_an_obligation(tmp_path,monkeypatch,fault):
    board,pad,leg,request,extra,unused=fixture(tmp_path,monkeypatch)
    uid=force._uid(leg);key='boundary:'+uid
    replacement=dict(kind='source_boundary',net=leg.GetNetname(),width_nm=leg.GetWidth(),
        a=copy.deepcopy(request['a']),b=dict(at_nm=list(leg.GetEnd()),layers=[int(leg.GetLayer())]))
    proposal=dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=row._source_binding(board),poses={pad.GetParentFootprint().GetReference():[1,1,0]},
        retired_track_uuids=[uid])
    requests={key:replacement,'exact-contact':request}
    if fault=='missing_base_demand':del requests[key]
    elif fault=='wrong_pad':replacement['a']['pad_uuid']='not-the-source-pad'
    elif fault=='wrong_net':replacement['net']='other-net'
    elif fault=='too_narrow':replacement['width_nm']-=1
    elif fault=='stale_binding':proposal['source_native_binding']='stale'
    elif fault=='wrong_scope':proposal['scope']='arbitrary-cut'
    elif fault=='unselected_owner':proposal['poses']={}
    else:request['unchanged_full_rail_current_contract']={}
    with pytest.raises(ValueError):compiler._compose_retained_demands(board,requests,[],
        board_hint='synthetic',source_proposal=proposal)

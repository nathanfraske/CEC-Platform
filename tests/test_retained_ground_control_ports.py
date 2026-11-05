"""Real public saved-geometry Ground observer regressions.

No observer overlay or ownership monkeypatch is installed. Fresh canonical
Source roles, actual filled reference planes, immediate cap returns, process,
retained control groups/straps and exact request comparison remain active.
"""
import copy
import time

import pytest
import pcbnew
import cec_selected_cap_ground_boundary as draft
from test_selected_cap_ground_boundary import fixture as source_fixture, reconstruct
from cec_native_items import discard_items

import cec_source_ground_boundary_connection as op


def fixture(tmp_path, monkeypatch, quarter=0, reflected=False):
    source, _, _, ids, root = source_fixture(tmp_path, monkeypatch, quarter, reflected)
    properties=source.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal'
    source.SetProperties(properties)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone = pcbnew.ZONE(source); source.Add(zone); zone.SetNet(source.FindNet('GND'))
        zone.SetLayer(face)
        poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
        for x,y in ((0,0),(50000000,0),(50000000,50000000),(0,50000000)):
            poly.Outline(0).Append(x,y)
        zone.Outline().Append(poly); zone.SetFilledPolysList(face, poly); zone.SetIsFilled(True)
    draft.field._save_field_snapshot(source, source.GetFileName())
    source = pcbnew.LoadBoard(source.GetFileName()); child = pcbnew.LoadBoard(source.GetFileName())
    poses = {fp.GetReference():[v/1e6 for v in fp.GetPosition()]+[fp.GetOrientationDegrees()]
        for fp in source.GetFootprints()}
    proposal = draft.escape.prepare(source, poses, board_hint=str(root))
    record = draft.ownership(source, proposal, [ids['edge']], deadline=time.monotonic()+8.)
    authority = record['extras'][0]['authority']
    reconstruct(source, child, ids)
    requests = draft.escape.obligations(source, child, proposal)
    live = draft._items(child)
    def port(uid):
        pad = live[uid]
        return dict(pad_uuid=uid, at_nm=list(pad.GetPosition()), layers=list(map(int,pad.GetLayerSet().CuStack())))
    request = dict(kind='source_boundary', net='GND', a=port(ids['controls'][0]), b=port(ids['cap']),
        width_nm=authority['source_full_class_width_nm'],
        exact_additional_macro_component_source_ownership=[authority],
        every_surviving_source_component_port_mandatory=True)
    requests['test_control_boundary'] = request
    return source, child, proposal, request, requests, ids


def observe(source, child, proposal, request, requests):
    return op.observe(source,child,request,requests,board_hint=proposal['board_hint'],
        source_proposal=proposal,timeout_s=8.)


def test_legacy_typer_does_not_gain_control_ports_without_new_scope(tmp_path,monkeypatch):
    source, child, proposal, request, requests, ids = fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(op.compiler, '_ground_boundary_authority', op.compiler._legacy_ground_boundary_authority)
    assert observe(source,child,proposal,request,requests) is None


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('reflected',[False,True])
def test_real_public_observer_preserves_control_role_and_cap_return(tmp_path,monkeypatch,quarter,reflected):
    source, child, proposal, request, requests, ids = fixture(tmp_path,monkeypatch,quarter,reflected)
    proof = observe(source,child,proposal,request,requests)
    assert proof and proof['all_named_contacts_connected']
    assert proof['actual_native_filled_island_connectivity_proved']
    assert {p['pad_uuid'] for p in proof['fixed_retained_control_ports']} == set(ids['controls'])
    assert all(p['control_remains_control'] and not p['functional_ground_return']
        and not p['root_or_width_or_current_authority'] for p in proof['fixed_retained_control_ports'])
    assert all(set(p['retained_thin_strap_uuids']) == set(ids['thin']) for p in proof['fixed_retained_control_ports'])
    local = proof['independently_received_local_ground_returns']
    assert len(local) == 1 and local[0]['pad_uuid'] == ids['cap']
    assert local[0]['max_return_mm'] == .8 and local[0]['return_mm'] <= .8
    assert local[0]['actual_filled_reference_contacts']
    assert not proof['current_qualified'] and not proof['routing_admitted'] and not proof['release_authority']


@pytest.mark.parametrize('fault',[
    'forged_role','missing_control_port','missing_strap_port','control_ground_root',
    'strap_deleted','strap_width','strap_moved','control_moved','control_size',
    'owner_moved','owner_mpn','owner_group','no_return','no_filled_reference','missing_ground_request',
    'wrong_control_endpoint','wrong_control_layer'])
def test_real_public_observer_refuses_forgery_and_native_losses(tmp_path,monkeypatch,fault):
    source, child, proposal, request, requests, ids = fixture(tmp_path,monkeypatch)
    live = draft._items(child); authority=request['exact_additional_macro_component_source_ownership'][0]
    if fault == 'forged_role':
        next(p for p in authority['exact_retained_ports'] if p.get('role')=='control')['role']='ground'
    elif fault == 'missing_control_port':
        authority['exact_retained_ports']=[p for p in authority['exact_retained_ports'] if p['item']['uuid']!=ids['controls'][0]]
    elif fault == 'missing_strap_port':
        authority['exact_retained_ports']=[p for p in authority['exact_retained_ports'] if p['item']['uuid']!=ids['thin'][0]]
    elif fault == 'control_ground_root':
        authority['source_pad_roots'].append(dict(pad_uuid=ids['controls'][0],role='ground'))
    elif fault == 'strap_deleted': discard_items(child,[live[ids['thin'][0]]])
    elif fault == 'strap_width': live[ids['thin'][0]].SetWidth(200001)
    elif fault == 'strap_moved': live[ids['thin'][0]].Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'control_moved': live[ids['controls'][0]].Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'control_size': live[ids['controls'][0]].SetSize(pcbnew.VECTOR2I(200001,600000))
    elif fault == 'owner_moved': live[ids['controls'][0]].GetParentFootprint().Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'owner_mpn': live[ids['controls'][0]].GetParentFootprint().SetField('MPN','UNQUALIFIED')
    elif fault == 'owner_group':
        group=pcbnew.PCB_GROUP(child);child.Add(group);group.SetName('unexpected');group.AddItem(live[ids['controls'][0]].GetParentFootprint())
    elif fault == 'no_return': discard_items(child,[live[ids['via']]])
    elif fault == 'no_filled_reference':
        for zone in child.Zones(): zone.UnFill()
    elif fault == 'missing_ground_request': del requests['ground:'+ids['cap']]
    elif fault == 'wrong_control_endpoint': request['a']['at_nm'][0]+=1
    elif fault == 'wrong_control_layer': request['a']['layers']=[int(pcbnew.B_Cu)]
    assert observe(source,child,proposal,request,requests) is None


def test_fallback_retains_legacy_outer_refusal_and_fresh_cause(tmp_path,monkeypatch):
    source, child, proposal, request, requests, ids = fixture(tmp_path,monkeypatch)
    # This is a negative Source-current declaration, not supplied authority.
    monkeypatch.setattr(draft.full,'_model',lambda *args:('unknown',{},{}))
    with pytest.raises(ValueError,match='^changed_macro_ground_boundary_has_unowned_land:') as caught:
        op.compiler._ground_boundary_authority(source,draft._items(source)[ids['edge']],
            dict(source_process_barrel_motion=[]),proposal,time.monotonic()+8.)
    assert isinstance(caught.value.__cause__,ValueError)
    assert str(caught.value.__cause__)=='known_unchanged_full_source_rail_current_required'


def test_individual_observer_does_not_annex_other_class_cut_links(tmp_path,monkeypatch):
    source, child, proposal, request, requests, ids = fixture(tmp_path,monkeypatch)
    # This only tests the fixed-CONTROL seam. A WHOLE macro independently owes
    # every other cut port through components.requests/partition receivers.
    # A singleton Source authority may list a neighboring class edge retained,
    # while that same edge belongs to another freshly owned whole-macro cut.
    discard_items(child,[draft._items(child)[ids['trunk']]])
    proof=observe(source,child,proposal,request,requests)
    assert proof and proof['all_named_contacts_connected']
    assert all(set(p['retained_thin_strap_uuids'])==set(ids['thin'])
        for p in proof['fixed_retained_control_ports'])
    assert not proof['routing_admitted'] and not proof['release_authority']

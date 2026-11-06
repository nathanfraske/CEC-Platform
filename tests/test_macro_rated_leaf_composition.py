"""Rated leaf composition retains native terminals and unchanged rail load."""
import copy
import json
import time

import pcbnew
import pytest
import cec_macro_boundary_composition as op
import cec_macro_cut_components as components
import cec_cell_macro_requests as compiler
import cec_measurement_leaf as leaf
import cec_full_current_planar_reflow as full
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items
from test_measurement_leaf import fixture as native_fixture
from test_cell_shared_fork import power_authority
from test_field_proposals import track


def fixture(tmp_path, monkeypatch, *, multilayer=False, work_span=8.):
    board, pad, anchor, edges, xy = native_fixture('arbitrary_rated_rail')
    pad.SetNumber('6')
    edges[0].SetEnd(xy((12,10))); edges[1].SetStart(xy((12,10)))
    edges[1].SetEnd(xy((14,10))); anchor.SetPosition(xy((14,10)))
    if work_span==12.:
        edges[1].SetEnd(xy((22,10))); anchor.SetPosition(xy((22,10)))
    branch = track(board,pad.GetNetname(),(12,10),(12,12),width=.2)
    via = pcbnew.PCB_VIA(board); via.SetNet(pad.GetNet()); via.SetPosition(xy((12,12)))
    via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu); board.Add(via)
    _,rating=power_authority(monkeypatch,pad.GetNetname(),pcbnew.F_Cu)
    if multilayer:
        rating['required_by_layer_nm'].update({10:200000,2:200000})
    source = tmp_path/'rated-leaf.kicad_pcb'; field._save_field_snapshot(board,source)
    q = leaf.plan_rated_supply(board,force._uid(pad),board_hint='synthetic')
    assert q['track_uuids'] == [force._uid(edges[0])]
    proposal = dict(scope='source_typed_complete_cell_escape_proposal',board_hint='synthetic',
        source_native_binding=row._source_binding(board),rated_supply_leaves=[q],
        retired_track_uuids=q['track_uuids'],poses={pad.GetParentFootprint().GetReference():[0,0,0]})
    extras = [dict(change=dict(uuid=force._uid(edge),net=edge.GetNetname(),
        source_nm=[list(edge.GetStart()),list(edge.GetEnd())]),
        authority=dict(kind='unchanged_full_current_source_edge',native_source_uuid=force._uid(edge),
            source_plan=full.plan(board,source,board_hint='synthetic',retired_track_uuids=[force._uid(edge)],
                max_source_track_mm=work_span)))
        for edge in (edges[1],branch)]
    request = dict(kind='source_boundary',net=q['net'],width_nm=q['width_nm'],
        unchanged_full_rail_current_contract=q['unchanged_full_rail_current_contract'],
        a=dict(pad_uuid=q['pad_uuid'],at_nm=list(pad.GetPosition()),layers=[q['layer']]),
        b=dict(native_uuids=q['boundary_uuids'],at_nm=q['points_nm'][-1],layers=[q['layer']]))
    return board,source,proposal,{'rated_supply:'+q['pad_uuid']:request},extras,{force._uid(pad),force._uid(anchor),force._uid(via)}


def invoke(board,source,proposal,requests,extras):
    return op.compose_rated_leaves(board,source,proposal,requests,extras,deadline=time.monotonic()+5.)


def test_actual_rated_leaf_and_connected_extras_preserve_every_native_port(tmp_path,monkeypatch):
    board,source,proposal,requests,extras,terminals = fixture(tmp_path,monkeypatch)
    original = copy.deepcopy((proposal,requests,extras)); binding = row._source_binding(board)
    remaining,extended,records = invoke(board,source,proposal,requests,extras)
    assert not remaining and records
    retired = set(proposal['retired_track_uuids']) | {r['change']['uuid'] for r in extras}
    assert {r['change']['uuid'] for r in extended} == retired
    assert (proposal,requests,extras) == original and row._source_binding(board) == binding
    child = pcbnew.LoadBoard(str(source))
    discard_items(child,[t for t in child.GetTracks() if force._uid(t) in retired])
    transport=dict(source_process_barrel_motion=[],explicit_source_typed_ordinary_barrel_motion=[])
    rebuilt,groups = components.requests(board,child,extended,retired,transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+3.)
    assert rebuilt and len(groups) == 1
    assert {c['source_item_uuid'] for c in groups[0]['surviving_contacts']} == terminals
    assert all(r['every_surviving_source_component_port_mandatory'] for r in rebuilt.values())


@pytest.mark.parametrize('fault',['untyped_peer','thin_peer','contract','forged_leaf','source'])
def test_rated_composition_never_infers_cut_or_rating_authority(tmp_path,monkeypatch,fault):
    board,source,proposal,requests,extras,_ = fixture(tmp_path,monkeypatch)
    if fault == 'untyped_peer': extras[0]['authority']['kind'] = 'positive_source_ordinary'
    elif fault == 'thin_peer':
        uid = extras[0]['change']['uuid']
        next(t for t in board.GetTracks() if force._uid(t)==uid).SetWidth(100000)
        field._save_field_snapshot(board,source); proposal['source_native_binding']=row._source_binding(board)
        # Refresh the still-valid tiny leaf so this is not merely stale-q
        # rejection: the independently rederived peer itself is undersized.
        proposal['rated_supply_leaves']=[leaf.plan_rated_supply(board,
            proposal['rated_supply_leaves'][0]['pad_uuid'],board_hint='synthetic')]
    elif fault == 'contract':
        original = full.plan
        def changed(*a,**kw):
            result=copy.deepcopy(original(*a,**kw));result['contract']['current_authority']['amps']+=1
            return result
        monkeypatch.setattr(full,'plan',changed)
    elif fault == 'forged_leaf': proposal['rated_supply_leaves'][0]['source_length_mm'] += .01
    else: board.FindFootprintByReference('RENAMED_OWNER').SetValue('unknown')
    with pytest.raises(ValueError): invoke(board,source,proposal,requests,extras)


def test_unrelated_and_local_supply_requests_stay_mandatory(tmp_path,monkeypatch):
    board,source,proposal,requests,extras,_ = fixture(tmp_path,monkeypatch)
    request=next(iter(requests.values()))
    unrelated={'other':copy.deepcopy(request),'local_supply:untouched':dict(request,kind='local_supply')}
    remaining,extended,records=invoke(board,source,proposal,unrelated,extras)
    assert remaining==unrelated and extended==extras and records==[]


@pytest.mark.parametrize('fault',[None,'layer_width','current'])
def test_multidigit_native_layer_keys_equal_wire_keys_without_losing_values(tmp_path,monkeypatch,fault):
    board,source,proposal,requests,extras,_=fixture(tmp_path,monkeypatch,multilayer=True)
    native=proposal['rated_supply_leaves'][0]['unchanged_full_rail_current_contract']
    assert 10 in native['required_by_layer_nm'] and 2 in native['required_by_layer_nm']
    proposal,requests,extras=json.loads(json.dumps([proposal,requests,extras]))
    wire=proposal['rated_supply_leaves'][0]['unchanged_full_rail_current_contract']
    assert wire['required_by_layer_nm']['10']==native['required_by_layer_nm'][10]
    assert wire['required_by_layer_nm']['2']==native['required_by_layer_nm'][2]
    if fault:
        if fault=='layer_width':wire['required_by_layer_nm']['10']+=1
        else:wire['current_authority']['amps']+=.01
        next(iter(requests.values()))['unchanged_full_rail_current_contract']=copy.deepcopy(wire)
        with pytest.raises(ValueError):invoke(board,source,proposal,requests,extras)
    else:
        remaining,extended,records=invoke(board,source,proposal,requests,extras)
        assert not remaining and records and len(extended)==3
        assert records[0]['original_rated_leaf']['unchanged_full_rail_current_contract']==wire


def test_approved_twelve_mm_work_bound_replays_actual_over_eight_mm_peer(tmp_path,monkeypatch):
    board,source,proposal,requests,extras,_=fixture(tmp_path,monkeypatch,work_span=12.)
    ids={r['change']['uuid']for r in extras}
    assert any(t.GetLength()>8000000 for t in board.GetTracks() if force._uid(t)in ids)
    assert all(r['authority']['source_plan']['max_source_track_mm']==12. for r in extras)
    remaining,extended,records=invoke(board,source,proposal,requests,extras)
    assert not remaining and len(extended)==3 and records
    assert {r['change']['uuid']for r in extended}==ids|set(proposal['retired_track_uuids'])


@pytest.mark.parametrize('field,value',[('max_source_track_mm',35.),('max_source_track_mm',float('nan')),
    ('max_source_cut_mm',float('nan'))])
def test_invalid_original_work_bounds_never_gain_retirement_or_current_authority(tmp_path,monkeypatch,field,value):
    board,source,proposal,requests,extras,_=fixture(tmp_path,monkeypatch)
    extras[0]['authority']['source_plan'][field]=value
    with pytest.raises(ValueError):invoke(board,source,proposal,requests,extras)

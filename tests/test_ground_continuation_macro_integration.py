"""Distinct Ground roots/continuations retain one actual all-port component."""
import copy
import time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_cell_ground_cut_boundaries as ground_boundaries
import cec_macro_cut_components as components
import cec_macro_obstacle_cuts as obstacles
import cec_source_ground_continuation as continuation
import cec_force_current as force
from cec_native_items import discard_items
from test_source_ground_continuation import fixture, call


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_obstacle_dispatch_and_mixed_ground_component_restore_all_original_contacts(
        tmp_path, monkeypatch, quarter, back):
    parts = fixture(tmp_path, monkeypatch, quarter=quarter, back=back)
    source, parent, private, proposal, ids, roots, tail = parts
    before = row._source_binding(parent); raw = source.read_bytes()
    acquired = obstacles.ownership(parent, private, source, proposal, ids,
        existing_ground_cut_rows=roots, deadline=time.monotonic()+10.)
    assert {q['change']['uuid'] for q in acquired} == set(ids)
    assert all(q['authority']['kind'] == continuation.KIND for q in acquired)
    extra = [*roots, *acquired]; retired = {q['change']['uuid'] for q in extra}
    discard_items(private, [t for t in private.GetTracks() if force._uid(t) in retired])
    demands, observed = components.requests(parent, private, extra, retired,
        dict(changes=[],source_process_barrel_motion=[], explicit_source_typed_ordinary_barrel_motion=[]),
        project_contacts=compiler._project_contacts, deadline=time.monotonic()+10.)
    assert len(observed) == 1 and demands
    assert set(observed[0]['source_extra_edge_uuids']) == retired
    assert {q['source_class'] for q in observed[0]['surviving_contacts']} == {'PAD', 'PCB_TRACK'}
    assert tail in {q['source_item_uuid'] for q in observed[0]['surviving_contacts']}
    expanded=copy.deepcopy(proposal);expanded['retired_track_uuids']=sorted(retired)
    debts=ground_boundaries.requests(parent,private,expanded,
        additional_source_ground_cut_rows=extra,timeout_s=10.)
    assert debts
    assert all(q['kind']=='ground_boundary'and q['net']=='GND'for q in debts.values())
    for demand in demands.values():
        assert demand['net'] == 'GND' and demand['every_surviving_source_component_port_mandatory']
        scope = escape._typed_macro_ground_scope(demand)
        assert scope is not None and scope['not_aggregate_ground_injection_rating']
        assert set(scope['source_track_uuids']) == retired
        assert {q['kind'] for q in demand['exact_additional_macro_component_source_ownership']} == {
            'positive_existing_low_power_ground_boundary', continuation.KIND}
    assert before == row._source_binding(parent) and raw == source.read_bytes()


@pytest.mark.parametrize('fault', ['missing_root', 'changed_root', 'ordinary_root', 'ordinary_continuation',
    'forged_continuation', 'disconnected_root'])
def test_continuation_cannot_be_received_without_same_positive_native_ground_root(
        tmp_path, monkeypatch, fault):
    parts = fixture(tmp_path, monkeypatch)
    source, parent, private, proposal, ids, roots, tail = parts
    acquired = call(parts); extra = copy.deepcopy([*roots, *acquired])
    retired = {q['change']['uuid'] for q in extra}
    if fault == 'missing_root': extra = extra[1:]
    elif fault == 'changed_root': extra[0]['authority']['source_full_class_width_nm'] += 1
    elif fault == 'ordinary_root': extra[0]['authority']['kind'] = 'positive_source_ordinary'
    elif fault == 'ordinary_continuation': extra[1]['authority']['kind'] = 'positive_source_ordinary'
    elif fault == 'forged_continuation': extra[1]['authority']['root_authorities'] = []
    else:
        edge = next(t for t in parent.GetTracks() if force._uid(t) == roots[0]['change']['uuid'])
        edge.Move(pcbnew.VECTOR2I_MM(20, 0))
    discard_items(private, [t for t in private.GetTracks() if force._uid(t) in retired])
    with pytest.raises(ValueError):
        components.requests(parent, private, extra, retired,
            dict(changes=[],source_process_barrel_motion=[], explicit_source_typed_ordinary_barrel_motion=[]),
            project_contacts=compiler._project_contacts, deadline=time.monotonic()+10.)


def test_raw_ground_obstacle_list_remains_insufficient(tmp_path, monkeypatch):
    source, parent, private, proposal, ids, roots, unused = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        obstacles.ownership(parent, private, source, proposal, ids, deadline=time.monotonic()+10.)

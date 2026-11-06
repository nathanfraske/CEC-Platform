"""Construction-only dispatch for distinct positively replayed Ground leaves."""
import copy
import time

import pytest
import cec_additional_aggregate_macro as aggregate
import cec_cell_escape_replan as escape
import cec_wired_aggregate_ground_leaf as wired
from test_wired_aggregate_ground_leaf import fixture


def request_fixture(tmp_path, monkeypatch):
    source, root, board, pad, ids, poses = fixture(tmp_path, monkeypatch)
    selected = aggregate.collect(board, poses, board_hint=str(root),
        allow_linear_power_stage_reconstruction=True)
    proposal = dict(scope='source_typed_complete_cell_escape_proposal', poses=poses,
        board_hint=str(root), source_native_binding=wired.native.row._source_binding(board),
        additional_aggregate_capacitors=selected,
        allow_linear_power_stage_reconstruction=True, allow_owned_locked_escapes=False)
    rows = wired.single_edge_ownerships(board, proposal, ids, deadline=time.monotonic()+8.)
    return dict(kind='source_boundary', net='GND', width_nm=rows[0]['authority']['source_width_nm'],
        every_surviving_source_component_port_mandatory=True,
        exact_additional_macro_component_source_ownership=[r['authority'] for r in rows])


def test_positive_wired_leaf_selects_only_source_class_menu(tmp_path, monkeypatch):
    request = request_fixture(tmp_path, monkeypatch)
    scope = escape._typed_macro_ground_scope(request)
    assert scope and scope['source_width_nm'] == request['width_nm']
    assert scope['whole_original_current_receiving_still_required']
    assert scope['every_original_partition_and_physical_ground_return_still_required']
    assert not scope['current_authority'] and not scope['release_authority']


@pytest.mark.parametrize('fault', ['width', 'kind', 'mandatory', 'duplicate',
    'scope', 'return', 'current', 'supply', 'bypass', 'barrel'])
def test_label_or_changed_leaf_cannot_select_source_class_menu(tmp_path, monkeypatch, fault):
    request = copy.deepcopy(request_fixture(tmp_path, monkeypatch))
    authorities = request['exact_additional_macro_component_source_ownership']
    authority = authorities[0]; leaf = authority['source_wired_aggregate_Ground_leaf']
    if fault == 'width': request['width_nm'] -= 1
    elif fault == 'kind': request['kind'] = 'ordinary'
    elif fault == 'mandatory': request['every_surviving_source_component_port_mandatory'] = False
    elif fault == 'duplicate': authorities.append(copy.deepcopy(authority))
    elif fault == 'scope': leaf['scope'] = wired.native.SCOPE
    elif fault == 'return': leaf['maximum_new_Ground_return_mm'] = 1.35
    elif fault == 'current': authority['current_authority'] = True
    elif fault == 'supply': leaf['supply_trace_retirement_authority'] = True
    elif fault == 'bypass': authority['source_Ground_root']['selected_bypass'] = True
    elif fault == 'barrel': authority['new_barrel_authority'] = True
    assert escape._typed_macro_ground_scope(request) is None

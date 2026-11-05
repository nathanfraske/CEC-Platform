"""Real contact geometry changes, never a new current or inferred sharing."""
import copy
import pcbnew
import pytest
import cec_fab_profile as fab
import cec_force_current as force
import cec_field_coupling as field
import cec_native_current_via_lands as owner
from test_native_layered_via_pad_context import fixture
from test_field_proposals import track


def case(rotation=0, back=False, inner=True):
    board, via, pad = fixture(rotation, back)
    via.Padstack().SetMode(pcbnew.PADSTACK.MODE_NORMAL)
    via.SetWidth(600000)
    board.Add(via)
    at = via.GetPosition()
    x, y = at.x / 1e6, at.y / 1e6
    track(board, '/ordinary', (x, y), (x+2, y),
        layer=pcbnew.In2_Cu if inner else pcbnew.F_Cu if back else pcbnew.B_Cu)
    contract = dict(net='/ordinary', current_authority=dict(amps=.75, geometry_margin=1.25,
        margin_included=False, source='explicit_synthetic_fixture_not_hardware_authority'),
        required_by_layer_mm={fab.COPPER_LAYER_IDS[int(layer)]: .07053861
            if layer in (pcbnew.F_Cu, pcbnew.B_Cu) else .8450747617670971
            for layer in board.GetEnabledLayers().CuStack()},
        routing_layers=[fab.COPPER_LAYER_IDS[int(l)] for l in board.GetEnabledLayers().CuStack()])
    return board, via, contract


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_source_current_web_expands_only_observed_contact_groups(rotation, back):
    board, via, contract = case(rotation, back)
    before = field._field_snapshot_inventory(board)
    authority = copy.deepcopy(contract)
    template, report = owner.propose(board, force._uid(via), contract, clearance_nm=200000)
    assert all(template.GetWidth(l) == (600000 if l in (pcbnew.F_Cu, pcbnew.B_Cu) else 1146000)
        for l in board.GetEnabledLayers().CuStack())
    assert template.GetDrillValue() == via.GetDrillValue() == 300000
    assert template.GetPosition() == via.GetPosition()
    assert report['before']['complete'] and not report['before']['ok']
    assert not report['board_mutated'] and report['supplied_contract_is_not_authority']
    assert not report['barrel_current_qualified'] and not report['routing_admitted']
    assert not report['release_authority']
    assert contract == authority and field._field_snapshot_inventory(board) == before


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('back', [False, True])
def test_outer_to_outer_does_not_invent_unused_thin_layer_load(rotation, back):
    board, via, contract = case(rotation, back, inner=False)
    for name in contract['required_by_layer_mm']:
        if name not in ('F.Cu', 'B.Cu'): contract['required_by_layer_mm'][name] = 8.
    template, report = owner.propose(board, force._uid(via), contract, clearance_nm=200000)
    assert report['before']['ok']
    assert all(template.GetWidth(l) == 600000 for l in board.GetEnabledLayers().CuStack())


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
    pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu])
def test_expansion_does_not_waive_any_actual_foreign_face(layer):
    board, via, contract = case()
    track(board, '/foreign', (9.5, 10), (10.5, 10), layer=layer)
    before = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError, match='native_guard'):
        owner.propose(board, force._uid(via), contract, clearance_nm=200000)
    assert field._field_snapshot_inventory(board) == before


@pytest.mark.parametrize('fault', ['zero_current', 'missing_layer', 'off_net', 'one_face',
    'outside_routing', 'too_large', 'blind', 'bad_timeout', 'bad_clearance', 'unassigned'])
def test_unknown_current_contact_process_or_geometry_refuses(fault):
    board, via, contract = case()
    args = dict(clearance_nm=200000)
    if fault == 'zero_current': contract['current_authority']['amps'] = 0
    elif fault == 'missing_layer': contract['required_by_layer_mm'].pop('In2.Cu')
    elif fault == 'off_net': contract['net'] = '/foreign'
    elif fault == 'one_face':
        for t in list(board.GetTracks()):
            if t.GetClass() == 'PCB_TRACK': board.Remove(t)
    elif fault == 'outside_routing': contract['routing_layers'] = ['F.Cu']
    elif fault == 'too_large': contract['required_by_layer_mm']['In2.Cu'] = 40.
    elif fault == 'blind': via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault == 'bad_timeout': args['timeout_s'] = 11
    elif fault == 'bad_clearance': args['clearance_nm'] = 0
    elif fault == 'unassigned': via.SetNetCode(0)
    with pytest.raises(ValueError): owner.propose(board, force._uid(via), contract, **args)


def test_source_entry_refuses_inherited_barrel_identity_before_current_derivation(tmp_path):
    board, via, contract = case()
    source = tmp_path / 'source' / 'board.kicad_pcb'
    source.parent.mkdir()
    pcbnew.SaveBoard(str(source), board)
    with pytest.raises(ValueError, match='inherited_source_via_land_mutation_not_owned'):
        owner.apply_new_source_barrel(board, source, force._uid(via), board_hint='synthetic', timeout_s=3.)

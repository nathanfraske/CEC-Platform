"""Actual same-net force copper must be an obstacle to a four-wire tap."""
import time
from unittest.mock import patch

import pcbnew
import pytest

import cec_fr as fr
import cec_kelvin_force_separation as separation
from test_kelvin_copper_cut import native_board_fixture, track, zone


def path():
    return [pcbnew.VECTOR2I_MM(90, 75), pcbnew.VECTOR2I_MM(90, 78)]


def audit(values, **kwargs):
    return separation.audit_path(values[0], values[1], path(), width_nm=200000,
        layer=pcbnew.F_Cu, clearance_nm=200000, **kwargs)


def test_contact_only_inside_shunt_pad_is_permitted(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    zone(values[0], [(88, 74.5, 90.05, 75.15)])
    before = [(item.m_Uuid.AsString(), item.GetStart().x, item.GetEnd().y)
              for item in values[0].GetTracks()]
    result = audit(values)
    assert result['ok'] is True, result
    assert result['checked'] >= 2
    assert not result['release_authority']
    assert before == [(item.m_Uuid.AsString(), item.GetStart().x, item.GetEnd().y)
                      for item in values[0].GetTracks()]


def test_same_net_filled_zone_is_not_waived_by_electrical_identity(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    item = zone(values[0], [(89.7, 76.5, 90.3, 78.5)])
    net = values[1].GetNetCode()
    assert fr._tap_foreign_clear(values[0], *path(), 200000, pcbnew.F_Cu, 200000, {net})
    assert fr._tap_candidate_clear(values[0], path(), 200000, pcbnew.F_Cu, 200000, net)
    assert not fr._tap_candidate_clear(values[0], path(), 200000, pcbnew.F_Cu,
        200000, net, source_pad=values[1])
    result = audit(values)
    assert result['ok'] is False and result['complete']
    assert any(h['uuid'] == item.m_Uuid.AsString() for h in result['hits'])
    certificate = fr._tap_path_refusal_certificate(values[0], path(), 200000,
        pcbnew.F_Cu, 200000, {net}, net, path_kind='synthetic', source_pad=values[1])
    assert any(h['kind'] == 'same_net_force_copper' for h in certificate['blocked_legs'])


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_renamed_translated_rotated_native_branch(tmp_path, angle):
    values = native_board_fixture(tmp_path/'source.kicad_pcb', angle=angle)
    p = values[1].GetPosition()
    q = values[2].GetPosition()
    result = separation.audit_path(values[0], values[1], [p, q], width_nm=200000,
        layer=pcbnew.F_Cu, clearance_nm=200000)
    assert result['ok'] is True, result


def test_only_actual_filled_material_and_enabled_layer_block(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    item = zone(values[0], [(85, 74, 86, 75)])
    item.Outline().RemoveAllContours()
    item.Outline().NewOutline()
    for x, y in [(89, 76), (91, 76), (91, 79), (89, 79)]:
        item.Outline().Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    zone(values[0], [(89, 76, 91, 79)], layer=pcbnew.B_Cu)
    assert audit(values)['ok'] is True


def test_unfilled_zone_and_deadline_are_unknown(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    item = zone(values[0], [(89, 76, 91, 79)])
    item.SetIsFilled(False)
    result = audit(values)
    assert result['ok'] is None and result['reason'] == 'native_zone_fill_unavailable'
    result = audit(values, deadline=time.monotonic()-1)
    assert result['ok'] is None and not result['complete']


def test_same_net_wide_trace_and_barrel_are_obstacles(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    wide = track(values[0], (89, 77), (91, 77), width=.8)
    assert audit(values)['ok'] is False
    from cec_native_items import discard_items
    discard_items(values[0], [wide])
    via = pcbnew.PCB_VIA(values[0])
    via.SetPosition(pcbnew.VECTOR2I_MM(90, 77))
    via.SetNet(values[1].GetNet())
    via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    values[0].Add(via)
    assert audit(values)['ok'] is False


def test_thin_retained_sibling_tap_is_not_a_force_obstacle(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    track(values[0], (90, 77), (91.5, 77), width=.2)
    assert audit(values)['ok'] is True


def test_unsupported_source_and_native_failure_cannot_pass(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    values[1].SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    assert audit(values)['ok'] is None
    values[1].SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    with patch.object(separation.cut, '_poly', side_effect=RuntimeError('native failure')):
        assert audit(values)['ok'] is None


def test_synthesizer_uses_guard_and_records_force_zone_uuid(tmp_path):
    from test_kelvin_discipline import _Board
    world = _Board()
    # Net spelling is irrelevant to the new primitive. This fixture's existing
    # native tap synthesizer supplies the authoritative shunt pad itself.
    item = pcbnew.ZONE(world.b)
    item.SetNet(world.hi); item.SetLayer(pcbnew.F_Cu)
    poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
    for x, y in [(10.91, 4), (15, 4), (15, 10.9), (10.91, 10.9)]:
        poly.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    item.Outline().Append(poly); item.SetFilledPolysList(pcbnew.F_Cu, poly)
    item.SetIsFilled(True); world.b.Add(item)
    report = world.synth()
    assert report['refused']
    blockers = [b for row in report['refused_details'] for b in row['blocker_details']]
    assert any(b.get('uuid') == item.m_Uuid.AsString() for b in blockers), report


def test_certified_straight_source_edge_has_no_artificial_force_halo(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    zone(values[0], [(88, 73, 92, 76)])
    result = audit(values)
    assert result['ok'] is True and result['exact_linear_identity_verified'], result
    applied = [row for row in result['exact_linear_refinements'] if row['applied']]
    assert {row['kind'] for row in applied} == {
        'source_interior_core', 'filled_zone_integer_axis_bounds'}


@pytest.mark.parametrize('protrusion_nm', [1, 1000])
def test_native_tiny_force_protrusion_is_not_removed_by_straight_edge_refinement(
        tmp_path, protrusion_nm):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    item = zone(values[0], [(88, 73, 92, 76)])
    actual = pcbnew.SHAPE_POLY_SET()
    actual.NewOutline()
    for x, y in [(88000000, 73000000), (92000000, 73000000),
                 (92000000, 76000000+protrusion_nm),
                 (88000000, 76000000+protrusion_nm)]:
        actual.Append(x, y)
    item.SetFilledPolysList(pcbnew.F_Cu, actual)
    result = audit(values)
    assert result['ok'] is False and result['complete'], result
    assert any(hit['uuid'] == item.m_Uuid.AsString() for hit in result['hits'])


def test_native_linear_epoch_drift_cannot_grant_proposal_clearance(tmp_path):
    values = native_board_fixture(tmp_path/'source.kicad_pcb')
    zone(values[0], [(88, 73, 92, 76)])
    original = separation.cut._validate_linear_epochs
    def changed(work):
        values[1].SetPosition(values[1].GetPosition()+pcbnew.VECTOR2I(1, 0))
        return original(work)
    with patch.object(separation.cut, '_validate_linear_epochs', side_effect=changed):
        result = audit(values)
    assert result['ok'] is None and not result['complete'], result
    assert not result['exact_linear_identity_verified']


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_compiled_hop_guard_is_native_bound_and_preserves_transformed_common_region(tmp_path, angle):
    values=native_board_fixture(tmp_path/'source.kicad_pcb',angle=angle)
    plan=separation.compile_guard(values[0],values[1],width_nm=200000,
        layer=pcbnew.F_Cu,clearance_nm=200000)
    assert plan['guard'](values[1].GetPosition(),values[2].GetPosition(),100000)
    assert plan['unchanged']()
    assert plan['report']['saved_copper_cut_still_required']
    assert not plan['report']['current_authority'] and not plan['report']['release_authority']
    values[1].SetPosition(values[1].GetPosition()+pcbnew.VECTOR2I(1,0))
    assert not plan['unchanged']()


@pytest.mark.parametrize('protrusion_nm', [0, 1, 1000])
def test_compiled_hop_guard_does_not_clip_force_protrusions_outside_actual_source(tmp_path, protrusion_nm):
    values=native_board_fixture(tmp_path/'source.kicad_pcb')
    item=zone(values[0],[(88,73,92,76)])
    actual=pcbnew.SHAPE_POLY_SET();actual.NewOutline()
    for x,y in [(88000000,73000000),(92000000,73000000),
                (92000000,76000000+protrusion_nm),(88000000,76000000+protrusion_nm)]:
        actual.Append(x,y)
    item.SetFilledPolysList(pcbnew.F_Cu,actual)
    plan=separation.compile_guard(values[0],values[1],width_nm=200000,
        layer=pcbnew.F_Cu,clearance_nm=200000)
    assert plan['guard'](*path(),100000) is (protrusion_nm==0)


def test_compiled_force_guard_rejects_unsupported_unfilled_and_unbounded_inputs(tmp_path):
    values=native_board_fixture(tmp_path/'source.kicad_pcb')
    with pytest.raises(ValueError,match='bounded_thin'):
        separation.compile_guard(values[0],values[1],width_nm=200000,
            layer=pcbnew.F_Cu,clearance_nm=200000,deadline=time.monotonic()+11)
    with pytest.raises(separation.cut.Unknown):
        separation.compile_guard(values[0],values[1],width_nm=200000,
            layer=pcbnew.F_Cu,clearance_nm=200000,deadline=time.monotonic()-1)
    item=zone(values[0],[(89,76,91,79)]);item.SetIsFilled(False)
    with pytest.raises(ValueError,match='native_zone_fill_unavailable'):
        separation.compile_guard(values[0],values[1],width_nm=200000,
            layer=pcbnew.F_Cu,clearance_nm=200000)

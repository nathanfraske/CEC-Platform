"""Independent valid poses decline transport, never decline reconstruction."""
import pcbnew
import pytest

import cec_force_current as force
import cec_source_supply_endpoint_cut as supply
from test_isolated_selected_bypass_supply_transport_20261026 import fixture, options


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('turn', [0, 90, 180, 270])
def test_independent_whole_footprints_are_not_rigid_copper_transport(tmp_path, quarter, mirror, back, turn):
    parent, child, path, ids, remote, group = fixture(tmp_path, quarter, mirror, back)
    cap = child.FindFootprintByReference('C_RENAMED')
    cap.Move(pcbnew.VECTOR2I(250000, 0))
    cap.Rotate(cap.GetPosition(), pcbnew.EDA_ANGLE(turn, pcbnew.DEGREES_T))
    before = {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth(), t.IsLocked())
              for t in child.GetTracks()}
    with pytest.raises(ValueError, match='both_selected_supply_owners_require_one_exact_rigid_transform'):
        supply.isolated_components(parent, child, **options(), allow_cardinal_rotations=True)
    assert supply.isolated_components(parent, child, **options(), allow_cardinal_rotations=True,
        defer_independent_endpoint_reconstruction=True) == []
    assert before == {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth(), t.IsLocked())
                      for t in child.GetTracks()}


@pytest.mark.parametrize('fault', ['pad_motion', 'pad_net', 'pad_size', 'pad_rotation',
    'pad_layer', 'pad_attribute', 'missing_pad', 'noncardinal', 'permission', 'policy_type'])
def test_independent_decline_cannot_hide_malformed_footprint_or_policy(tmp_path, fault):
    parent, child, path, ids, remote, group = fixture(tmp_path)
    cap = child.FindFootprintByReference('C_RENAMED'); cap.Move(pcbnew.VECTOR2I(250000, 0))
    pad = cap.FindPadByNumber('1')
    kw = dict(options(), allow_cardinal_rotations=True, defer_independent_endpoint_reconstruction=True)
    if fault == 'pad_motion': pad.Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_net': pad.SetNet(child.FindNet('OTHER'))
    elif fault == 'pad_size': pad.SetSize(pad.GetSize() + pcbnew.VECTOR2I(1, 0))
    elif fault == 'pad_rotation': pad.SetOrientationDegrees(pad.GetOrientationDegrees() + .01)
    elif fault == 'pad_layer':
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.B_Cu); pad.SetLayerSet(layers)
    elif fault == 'pad_attribute': pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault == 'missing_pad': cap.Remove(pad)
    elif fault == 'noncardinal': cap.SetOrientationDegrees(89.99)
    elif fault == 'permission':
        cap.SetOrientationDegrees(90); kw['allow_cardinal_rotations'] = False
    else: kw['defer_independent_endpoint_reconstruction'] = 1
    before = {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd())) for t in child.GetTracks()}
    with pytest.raises(ValueError): supply.isolated_components(parent, child, **kw)
    assert before == {force._uid(t): (tuple(t.GetStart()), tuple(t.GetEnd())) for t in child.GetTracks()}


def test_declining_transport_does_not_exclude_any_edge_from_source_endpoint_cut(tmp_path):
    """No canonical Source input here: a full compiler must still refuse it."""
    parent, child, path, ids, remote, group = fixture(tmp_path)
    child.FindFootprintByReference('C_RENAMED').Move(pcbnew.VECTOR2I(250000, 0))
    assert supply.isolated_components(parent, child, **options(),
        defer_independent_endpoint_reconstruction=True) == []
    # The original Source input/group/whole-current authority is still due.
    # No fake fixed throat or skipped component IDs are supplied by decline.
    with pytest.raises(ValueError): supply.plan(parent, child, **options())

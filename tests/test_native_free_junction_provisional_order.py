import pcbnew
import pytest
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from test_native_pending_joint_cohort import row
from root_free_junction_boundary_envelope_20261013 import expand


@pytest.mark.parametrize('rotation', range(4))
def test_only_exact_pending_strokes_are_removed_from_provisional_obstacle_snapshot(rotation):
    b = _board([(10, 20, 'A'), (20, 10, 'B')])
    a = track(b, 'A', (10, 20), (30, 20))
    pending = track(b, 'B', (10, 17), (10, 23))
    for item in [*b.GetFootprints(), *b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0, 0), pcbnew.EDA_ANGLE(rotation * 90, pcbnew.DEGREES_T))
    before = [(tuple(t.GetStart()), tuple(t.GetEnd())) for t in (a, pending)]
    with pytest.raises(ValueError, match='actual_native_pad'):
        expand(b, [row(a)], clearance_for=lambda n: 200000)
    result, retired = expand(b, [row(a)], clearance_for=lambda n: 200000,
        provisional_reconstruction_track_uuids=[force._uid(pending)])
    assert result[0]['start'] == tuple(a.GetStart())
    assert result[0]['end'] == tuple(a.GetEnd())
    assert not retired and not result[0]['envelope_extension_uuids']
    assert before == [(tuple(t.GetStart()), tuple(t.GetEnd())) for t in (a, pending)]


@pytest.mark.parametrize('kind', ['pad', 'barrel', 'unlisted_stroke'])
def test_actual_foreign_geometry_is_not_exempted_by_pending_stroke_scope(kind):
    b = _board([(10, 20, 'A'), (20, 10, 'B')])
    a = track(b, 'A', (10, 20), (30, 20))
    pending = track(b, 'B', (10, 17), (10, 23))
    if kind == 'pad':
        fp = next(f for f in b.GetFootprints() if any(p.GetNetname() == 'B' for p in f.Pads()))
        fp.Move(pcbnew.VECTOR2I_MM(-10, 10))
    elif kind == 'barrel':
        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I_MM(10, 20))
        v.SetWidth(600000); v.SetDrill(300000); v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(b.FindNet('B')); b.Add(v)
    else:
        track(b, 'B', (10, 18), (10, 22))
    with pytest.raises(ValueError, match='actual_native_pad'):
        expand(b, [row(a)], clearance_for=lambda n: 200000,
            provisional_reconstruction_track_uuids=[force._uid(pending)])


@pytest.mark.parametrize('invalid', ['missing', 'barrel', 'duplicate'])
def test_provisional_scope_requires_existing_unique_native_tracks(invalid):
    b = _board([(10, 20, 'A')]); a = track(b, 'A', (10, 20), (30, 20))
    scope = ['missing']
    if invalid == 'duplicate': scope = [force._uid(a), force._uid(a)]
    if invalid == 'barrel':
        v = pcbnew.PCB_VIA(b); v.SetPosition(pcbnew.VECTOR2I_MM(20, 20))
        v.SetWidth(600000); v.SetDrill(300000); v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(b.FindNet('A')); b.Add(v)
        scope = [force._uid(v)]
    with pytest.raises(ValueError, match='literal_bounded'):
        expand(b, [row(a)], clearance_for=lambda n: 200000,
            provisional_reconstruction_track_uuids=scope)

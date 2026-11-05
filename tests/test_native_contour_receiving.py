"""The immutable parent, not worker geometry or counts, defines the phase."""
import copy
import pcbnew
import pytest
import cec_native_contour_regions as regions
import cec_native_contour_receiving as receiving
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_native_contour_regions import board, proposal, rehash


def saved(tmp_path, separate=False):
    b, tracks = board(separate=separate)
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir()
    pcbnew.SaveBoard(str(source), b)
    b = pcbnew.LoadBoard(str(source)); tracks = list(b.GetTracks())
    plan = proposal(b, tracks)
    emitted = regions.materialize(b, plan); regions.fill(b, plan, emitted['zone_uuids'])
    additive._ground_refill(b)
    candidate = force._copy_family(source, tmp_path/'candidate')
    field._save_field_snapshot(b, candidate)
    return source, candidate, [dict(plan=plan, materialized=emitted)]


@pytest.mark.parametrize('separate', [False, True])
def test_exact_saved_source_replay_receives_holes_and_multiple_zones(tmp_path, separate):
    source, candidate, rows = saved(tmp_path, separate)
    first, last = force._hash(source), force._hash(candidate)
    result = receiving.receive_literal_phase(source, candidate, rows)
    assert result['ok'] and result['complete'], result
    assert result['exact_source_phase_and_ground_refill_received']
    assert not result['new_capacity_credited'] and not result['release_authority']
    assert force._hash(source) == first and force._hash(candidate) == last


@pytest.mark.parametrize('fault', ['other_pad','other_stroke','new_zone','removed_stroke',
    'missing_declared_zone','changed_filled_region','fake_worker_flag','rehashed_bigger_slab',
    'reference_visibility'])
def test_saved_phase_cannot_launder_unrelated_worker_changes(tmp_path, fault):
    source, candidate, rows = saved(tmp_path)
    b = pcbnew.LoadBoard(str(candidate)); zone = next(iter(b.Zones()))
    if fault == 'other_pad':
        p = next(iter(list(b.GetFootprints())[0].Pads()))
        p.SetSize(pcbnew.VECTOR2I_MM(4,4))
    elif fault == 'reference_visibility':
        ref = next(iter(b.GetFootprints())).Reference()
        ref.SetVisible(not ref.IsVisible())
    elif fault == 'other_stroke':
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I_MM(10,10)); t.SetEnd(pcbnew.VECTOR2I_MM(15,10))
        t.SetNet(b.FindNet('/ARBITRARY_POWER')); t.SetLayer(pcbnew.B_Cu); t.SetWidth(200000); b.Add(t)
    elif fault == 'new_zone':
        z = pcbnew.ZONE(b); z.SetNet(b.FindNet('/ARBITRARY_POWER')); z.SetLayer(pcbnew.B_Cu)
        z.Outline().Append(regions.native_poly(rows[0]['plan']['regions_nm'])); b.Add(z)
    elif fault == 'removed_stroke': b.Remove(next(iter(b.GetTracks())))
    elif fault == 'missing_declared_zone': b.Remove(zone)
    elif fault == 'changed_filled_region': zone.UnFill()
    elif fault == 'fake_worker_flag': rows[0]['materialized']['new_capacity_credited'] = True
    elif fault == 'rehashed_bigger_slab':
        rows[0]['plan']['regions_nm'][0]['holes_nm'] = []
        rehash(rows[0]['plan'])
    field._save_field_snapshot(b, candidate)
    result = receiving.receive_literal_phase(source, candidate, rows)
    assert not result['ok'] and not result['complete'], result
    assert not result['release_authority'] and not result['new_capacity_credited']

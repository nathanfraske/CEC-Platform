"""A real barrel reseat must reprove islands, not require old fill hashes."""
import time
from pathlib import Path

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_native_fill_geometry as fill
import cec_ordinary_barrel_reseat as reseat
from test_field_proposals import track
from test_ordinary_barrel_reseat import fixture


def filled_fixture(tmp_path, rotation=0, face=pcbnew.F_Cu):
    source, child, uid = fixture(tmp_path, rotation, 'rotated_' + str(rotation))
    parent = pcbnew.LoadBoard(str(source))
    parent.Add(pcbnew.NETINFO_ITEM(parent, 'GND'))
    zone = pcbnew.ZONE(parent)
    zone.SetLayer(face)
    zone.SetNet(parent.FindNet('GND'))
    zone.SetLocalClearance(200000)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.Outline().Append(fill.reconstruct([[[[1000000, 1000000],
        [24000000, 1000000], [24000000, 24000000], [1000000, 24000000]]]],
        time.monotonic() + 2.))
    parent.Add(zone)
    track(parent, 'GND', (5, 20), (19, 20), layer=face)
    assert pcbnew.ZONE_FILLER(parent).Fill(parent.Zones())
    assert zone.IsFilled() and zone.GetFilledPolysList(face).OutlineCount()
    field._save_field_snapshot(parent, source)
    incoming = pcbnew.LoadBoard(str(child))
    old_ids = {force._uid(t) for t in parent.GetTracks()}
    target = pcbnew.LoadBoard(str(source))
    proposal = reseat.plan(target, source, via_uuid=uid, board_hint='synthetic',
        allow_owned_locked=True)
    reseat.subtract(target, source, proposal)
    for item in incoming.GetTracks():
        if force._uid(item) in old_ids: continue
        copied = item.Duplicate()
        copied.m_Uuid.Clone(item.m_Uuid)
        copied.SetNet(target.FindNet(item.GetNetname()))
        target.Add(copied)
    field._save_field_snapshot(target, child)
    final = Path(additive.finalize_private(source, child, tmp_path / 'native-refilled')['board'])
    return source, final, uid


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_real_native_antipad_refill_is_received_without_source_mutation(tmp_path, rotation, face):
    source, child, uid = filled_fixture(tmp_path, rotation, face)
    before = [p.read_bytes() for p in (source, child)]
    def identity(path):
        board = pcbnew.LoadBoard(str(path))
        zone = next(iter(board.Zones()))
        return fill.identity(zone.GetFilledPolysList(face), time.monotonic() + 2.)[0]
    assert identity(source) != identity(child)
    proof = reseat.receive(source, child, via_uuid=uid, board_hint='synthetic',
        allow_owned_locked=True)
    assert proof['ok'] and proof['complete'], proof
    assert proof['paired_native_partition_preservation']['preserved']
    assert proof['paired_native_partition_preservation']['exact_positive_native_island_overlap']
    assert not proof['paired_native_partition_preservation']['whole_zone_uuid_connectivity_credit']
    assert proof['exact_saved_additions_ground_and_rule_replay']['ok']
    assert not proof['release_authority'] and not proof['current_authority']
    assert before == [p.read_bytes() for p in (source, child)]


@pytest.mark.parametrize('fault', ['split', 'island_lost', 'foreign_net', 'foreign_face'])
def test_refill_identity_rebinding_cannot_hide_actual_source_loss(tmp_path, fault):
    source, child, uid = fixture(tmp_path)
    solid = [[[[3000000, 20000000], [17000000, 20000000],
        [17000000, 24000000], [3000000, 24000000]]]]
    left = [[[3000000, 20000000], [9000000, 20000000],
        [9000000, 24000000], [3000000, 24000000]]]
    right = [[[11000000, 20000000], [17000000, 20000000],
        [17000000, 24000000], [11000000, 24000000]]]
    for path in (source, child):
        b = pcbnew.LoadBoard(str(path))
        b.Add(pcbnew.NETINFO_ITEM(b, 'GND'))
        z = pcbnew.ZONE(b)
        z.m_Uuid.Clone(pcbnew.KIID('00000000-0000-4000-8000-000000000001'))
        z.SetLayer(pcbnew.F_Cu)
        z.SetNet(b.FindNet('GND'))
        z.Outline().Append(fill.reconstruct(solid, time.monotonic() + 2.))
        rings = [left, right] if fault == 'island_lost' else solid
        if path == child:
            if fault == 'split': rings = [left, right]
            elif fault == 'island_lost': rings = [left]
            elif fault == 'foreign_net':
                b.Add(pcbnew.NETINFO_ITEM(b, 'OTHER'))
                z.SetNet(b.FindNet('OTHER'))
            else: z.SetLayer(pcbnew.B_Cu)
        z.SetFilledPolysList(z.GetLayer(), fill.reconstruct(rings, time.monotonic() + 2.))
        z.SetIsFilled(True)
        b.Add(z)
        for index, x in enumerate((5, 15)):
            t = track(b, 'GND', (x, 22), (x + .5, 22))
            t.m_Uuid.Clone(pcbnew.KIID('11111111-1111-4111-8111-' + str(index + 1).zfill(12)))
        field._save_field_snapshot(b, path)
    before = [p.read_bytes() for p in (source, child)]
    proof = reseat.receive(source, child, via_uuid=uid, board_hint='synthetic',
        allow_owned_locked=True)
    assert not proof['ok'] and not proof['complete'] and proof['errors'], proof
    if fault == 'split':
        assert any('lost_surviving_native_partition' in e for e in proof['errors']), proof
        assert not proof['paired_native_partition_preservation']['preserved']
    assert before == [p.read_bytes() for p in (source, child)]


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('changed_value', [False, True])
def test_opaque_unchanged_source_fields_are_not_normalized_by_cut_projection(tmp_path, rotation, changed_value):
    from test_source_literal_retirement import hidden_field_last
    source, child, uid = fixture(tmp_path, rotation)
    for path in (source, child):
        b = pcbnew.LoadBoard(str(path))
        fp = pcbnew.FOOTPRINT(b)
        fp.m_Uuid.Clone(pcbnew.KIID('44444444-4444-4444-8444-444444444444'))
        fp.SetReference('OPAQUE')
        fp.SetValue('unowned changed field' if changed_value and path == child else 'opaque original field')
        for index, item in enumerate(sorted(fp.GetFields(), key=lambda f:f.GetName())):
            item.m_Uuid.Clone(pcbnew.KIID('44444444-4444-4444-8444-' + str(100 + index).zfill(12)))
        fp.SetPosition(pcbnew.VECTOR2I_MM(20, 2))
        b.Add(fp)
        field._save_field_snapshot(b, path)
        hidden_field_last(path)
    before = [p.read_bytes() for p in (source, child)]
    proof = reseat.receive(source, child, via_uuid=uid, board_hint='synthetic',
        allow_owned_locked=True)
    assert proof['ok'] is (not changed_value), (proof['errors'],
        proof.get('exact_saved_additions_ground_and_rule_replay'))
    if not changed_value:
        assert proof['complete']
        assert proof['literal_native_cut_projection']['exact_opaque_source_subtraction']
        assert proof['literal_native_cut_projection']['independent_full_native_inventory_equal']
        assert proof['exact_saved_additions_ground_and_rule_replay']['ok']
    else:
        assert proof['errors'] and not proof['complete']
    assert before == [p.read_bytes() for p in (source, child)]

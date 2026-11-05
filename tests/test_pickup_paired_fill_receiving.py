"""Generated pickup cuts preserve real refill islands, not old fill hashes."""
import time

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_generated_pickup_retirement as pickup
import cec_native_fill_geometry as fill
from test_field_proposals import track
from test_generated_pickup_retirement import fixture, stem_fixture


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def poured_fixture(tmp_path, *, compound=False, angle=0, mirror=False,
                   face=pcbnew.B_Cu):
    factory = stem_fixture if compound else fixture
    source, board, via, trunk, group, *rest = factory(tmp_path, angle, mirror)
    stem, net = rest if compound else (None, rest[0])
    board.Add(pcbnew.NETINFO_ITEM(board, 'GND'))
    zone = pcbnew.ZONE(board)
    zone.SetNet(board.FindNet('GND'))
    zone.SetLayer(face)
    # One valid authored contour, split into two real fill islands by a
    # retained pour-only rule area. Both islands have actual Ground anchors.
    # The changed pickup's opposite-face antipad must vanish on exact refill.
    zone.Outline().Append(fill.reconstruct([
        [rect(2000000, 2000000, 18000000, 18000000)],
    ], time.monotonic()+5.))
    board.Add(zone)
    keepout = pcbnew.ZONE(board)
    keepout.SetIsRuleArea(True)
    keepout.SetLayer(face)
    keepout.SetDoNotAllowZoneFills(True)
    keepout.SetDoNotAllowTracks(False)
    keepout.Outline().Append(fill.reconstruct([
        [rect(13750000, 0, 14250000, 20000000)]
    ], time.monotonic()+5.))
    board.Add(keepout)
    track(board, 'GND', (3, 3), (4, 3), layer=face)
    track(board, 'GND', (16, 16), (17, 16), layer=face)
    additive._ground_refill(board)
    assert zone.IsFilled() and zone.GetFilledPolysList(face).OutlineCount() >= 2
    field._save_field_snapshot(board, source)
    # Serialization canonicalizes net allocator indices; subsequent fixture
    # additions must use the actual saved board, not stale RAM net codes.
    via_id, stem_id, zone_id = (force._uid(via), force._uid(stem) if stem else None,
        force._uid(zone))
    board = pcbnew.LoadBoard(str(source))
    live = {force._uid(t): t for t in board.GetTracks()}
    via, stem = live[via_id], live.get(stem_id)
    zone = next(z for z in board.Zones() if force._uid(z) == zone_id)
    return source, board, via, stem, zone, net


def cut(tmp_path, *, compound=False, angle=0, mirror=False, face=pcbnew.B_Cu):
    source, board, via, stem, zone, net = poured_fixture(
        tmp_path, compound=compound, angle=angle, mirror=mirror, face=face)
    proposal = pickup.plan(board, [force._uid(via)],
        track_uuids=[force._uid(stem)] if compound else [])
    source_bytes = source.read_bytes()
    old_fill = zone.GetFilledPolysList(face).Format()
    pickup.subtract(board, proposal)
    additive._ground_refill(board)
    assert zone.GetFilledPolysList(face).Format() != old_fill
    candidate = force._copy_family(source, tmp_path/'child')
    field._save_field_snapshot(board, candidate)
    assert source.read_bytes() == source_bytes
    return source, candidate, board, proposal


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('compound', [False, True])
@pytest.mark.parametrize('face', [pcbnew.In1_Cu, pcbnew.B_Cu])
def test_actual_multicomponent_ground_refill_is_received_without_rating_credit(
        tmp_path, angle, mirror, compound, face):
    source, candidate, board, proposal = cut(tmp_path, compound=compound,
        angle=angle, mirror=mirror, face=face)
    result = pickup.receive(source, candidate, proposal, board_hint='unclassified-test')
    assert result['ok'] and result['complete'], result
    partitions = result['paired_native_partition_preservation']
    assert partitions['available'] and partitions['preserved']
    assert partitions['overlap_token_count'] >= 2
    assert not partitions['whole_zone_uuid_connectivity_credit']
    assert not result['current_qualified'] and not result['release_authority']
    assert result['exact_generated_membership_cut_and_ground_refill_received']


@pytest.mark.parametrize('fault', [
    'lost_island', 'unfilled', 'zone_net', 'zone_face', 'opaque_source_change',
    'unrelated_track_change', 'surviving_identity_change', 'forged_retirement',
])
def test_paired_fill_identity_does_not_authorize_any_other_saved_change(tmp_path, fault):
    source, candidate, board, proposal = cut(tmp_path, compound=True)
    zone = next(z for z in board.Zones() if not z.GetIsRuleArea())
    if fault == 'lost_island':
        material = fill.reconstruct([[rect(2000000, 2000000, 13000000, 13000000)]],
            time.monotonic()+5.)
        zone.SetFilledPolysList(zone.GetLayer(), material)
    elif fault == 'unfilled':
        zone.UnFill()
    elif fault == 'zone_net':
        zone.SetNetCode(board.GetNetcodeFromNetname('/RENAMED/HARMLESS'))
    elif fault == 'zone_face':
        zone.SetLayer(pcbnew.In1_Cu)
    elif fault == 'opaque_source_change':
        # Source-authored fabrication setting, not a copper-partition fact.
        board.GetDesignSettings().m_SolderPasteMargin += 1000
    elif fault == 'unrelated_track_change':
        list(board.GetTracks())[0].SetWidth(300000)
    elif fault == 'surviving_identity_change':
        list(board.GetTracks())[0].m_Uuid.Clone(pcbnew.KIID())
    else:
        proposal['via_uuids'].append('00000000-0000-4000-8000-000000000000')
    field._save_field_snapshot(board, candidate)
    result = pickup.receive(source, candidate, proposal, board_hint='unclassified-test')
    assert not result['ok'] and not result['complete'] and result['errors'], result


@pytest.mark.parametrize('foreign', ['face', 'net'])
def test_existing_ground_bridge_cannot_be_lost_behind_unchanged_zone_owner(tmp_path, foreign):
    source, board, via, stem, zone, net = poured_fixture(tmp_path)
    bridge = pcbnew.PCB_TRACK(board)
    bridge.SetNet(zone.GetNet())
    bridge.SetStart(pcbnew.VECTOR2I_MM(4, 10))
    bridge.SetEnd(pcbnew.VECTOR2I_MM(16, 10))
    bridge.SetWidth(200000)
    bridge.SetLayer(zone.GetLayer())
    board.Add(bridge)
    field._save_field_snapshot(board, source)
    proposal = pickup.plan(board, [force._uid(via)])
    pickup.subtract(board, proposal)
    # Leave all original conductor identities but break an unrelated native
    # Ground connection. A foreign face/net cannot replace real connectivity.
    if foreign == 'face':
        bridge.SetLayer(pcbnew.In1_Cu)
    else:
        bridge.SetNetCode(board.GetNetcodeFromNetname(net))
    additive._ground_refill(board)
    candidate = force._copy_family(source, tmp_path/'foreign-bridge')
    field._save_field_snapshot(board, candidate)
    result = pickup.receive(source, candidate, proposal, board_hint='unclassified-test')
    assert not result['ok'] and not result['complete'], result

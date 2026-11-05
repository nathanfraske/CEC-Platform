"""No board/refdes/coordinate authority: native feed changes replay exactly."""
import math
import pcbnew
import pytest
import cec_consumer_branch_reanchor as reanchor
import cec_supply_consumer_branch as consumer
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_pass_through_supply_branch import fixture as base_fixture


def fixture(monkeypatch, tmp_path, angle=0, mirrored=False):
    b, root, anchor, owner, cap, old_group_tracks, trunk, group, *_ = base_fixture(monkeypatch, tmp_path)
    old_group_tracks[1].SetEnd(pcbnew.VECTOR2I_MM(12, 8))
    portal = pcbnew.PCB_VIA(b); portal.SetNet(root.GetNet())
    portal.SetPosition(pcbnew.VECTOR2I_MM(12, 8)); portal.SetWidth(900000); portal.SetDrill(500000)
    portal.SetViaType(pcbnew.VIATYPE_THROUGH); portal.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(portal)
    group.SetName(consumer.PREFIX+'|'.join((force._uid(root), force._uid(portal), '')))
    def track(a, z):
        t = pcbnew.PCB_TRACK(b); t.SetNet(root.GetNet()); t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(200000); t.SetStart(pcbnew.VECTOR2I_MM(*a)); t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetLocked(True); b.Add(t); return t
    exclusive = track((12, 8), (15, 8)); obsolete = track((15, 8), (25, 8))
    for item in [*b.GetFootprints(), *b.GetTracks()]:
        if angle: item.Rotate(pcbnew.VECTOR2I_MM(0, 0), pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
        if mirrored: item.Flip(pcbnew.VECTOR2I_MM(0, 0), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source = tmp_path/'board.kicad_pcb'; field._save_field_snapshot(b, source)
    # Fresh synthetic library fields acquire native canonical poses on
    # reload. Freeze that native source before comparing exact primitives.
    canonical = pcbnew.LoadBoard(str(source)); field._save_field_snapshot(canonical, source)
    source_ids = dict(root=force._uid(root), anchor=force._uid(anchor), portal=force._uid(portal),
        exclusive=force._uid(exclusive), obsolete=force._uid(obsolete), group=force._uid(group),
        owner=force._uid(owner), trunk=force._uid(trunk))
    assert consumer.inventory(b, board_hint='arbitrary', timeout_s=10.)['complete']
    candidate = force._copy_family(source, tmp_path/'child')
    c = pcbnew.LoadBoard(str(candidate)); tracks = {force._uid(t): t for t in c.GetTracks()}
    removed = tracks[source_ids['obsolete']]
    # The SWIG accessors borrow their parent's vector storage. Preserve
    # value copies before the source conductor is actually discarded.
    start = pcbnew.VECTOR2I(removed.GetStart().x, removed.GetStart().y)
    end = pcbnew.VECTOR2I(removed.GetEnd().x, removed.GetEnd().y)
    dx, dy = end.x-start.x, end.y-start.y
    offset = pcbnew.VECTOR2I(round(-dy*.6), round(dx*.6))
    points = [start, start+offset, end+offset, end]
    discard_items(c, [removed])
    budget = consumer.contract(c, source_ids['root'], board_hint='arbitrary')
    layer = tracks[source_ids['exclusive']].GetLayer()
    width = math.ceil(budget['required_by_layer_mm'][reanchor.fab.COPPER_LAYER_IDS[layer]]*1e6)
    tracks[source_ids['exclusive']].SetWidth(width)
    target_group = next(g for g in c.Groups() if force._uid(g) == source_ids['group'])
    target_group.SetName(consumer.PREFIX+'|'.join((source_ids['root'], source_ids['anchor'], '')))
    new = []
    for a, z in zip(points, points[1:]):
        t = pcbnew.PCB_TRACK(c); t.SetNet(tracks[source_ids['exclusive']].GetNet()); t.SetLayer(layer)
        t.SetWidth(width); t.SetStart(a); t.SetEnd(z); t.SetLocked(True); c.Add(t); target_group.AddItem(t); new.append(t)
    field._save_field_snapshot(c, candidate)
    return source, candidate, c, source_ids, new


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirrored', [False, True])
def test_source_owned_feed_reanchors_through_retained_terminal_without_new_barrels(
        monkeypatch, tmp_path, angle, mirrored):
    source, candidate, c, ids, new = fixture(monkeypatch, tmp_path, angle, mirrored)
    before = [force._hash(p) for p in (source, candidate)]
    result = reanchor.receive(source, candidate, board_hint='arbitrary', root_pad_uuid=ids['root'],
        retired_track_uuids=[ids['obsolete']], timeout_s=10.)
    assert result['ok'] and result['complete'], result
    assert result['new_barrels'] == 0 and not result['new_barrel_capacity_credited']
    assert result['derived_unchanged_design_budget']['current_authority']['amps'] == 3.0004
    assert result['derived_unchanged_design_budget']['aggregate_current_authority']['amps'] == 20.
    assert {r['uuid'] for r in result['exclusive_exact_floor_widenings']} == {ids['exclusive']}
    assert set(result['incoming_track_uuids']) == set(map(force._uid, new))
    assert result['existing_barrels_parts_pours_interfaces_and_rules_exact']
    assert result['all_surviving_native_partitions_preserved']
    assert result['whole_board_qualification_still_required'] and not result['current_qualified']
    assert not result['release_authority']
    assert [force._hash(p) for p in (source, candidate)] == before


@pytest.mark.parametrize('fault', ['trunk_widen', 'unrelated_track_move', 'part_move', 'wrong_root',
    'wrong_net', 'new_barrel', 'second_tap', 'wrong_floor', 'oversize_incoming',
    'lost_original_member', 'retire_trunk', 'duplicate_cut', 'wrong_anchor', 'long_route'])
def test_unrelated_edits_and_borrowed_current_never_pass_feed_reconstruction(monkeypatch, tmp_path, fault):
    source, candidate, c, ids, new = fixture(monkeypatch, tmp_path)
    tracks = {force._uid(t): t for t in c.GetTracks()}
    group = next(g for g in c.Groups() if force._uid(g) == ids['group'])
    retired = [ids['obsolete']]; root = ids['root']
    if fault == 'trunk_widen': tracks[ids['trunk']].SetWidth(tracks[ids['trunk']].GetWidth()+1000)
    elif fault == 'unrelated_track_move': tracks[ids['trunk']].SetEnd(pcbnew.VECTOR2I_MM(41, 8))
    elif fault == 'part_move':
        fp = next(f for f in c.GetFootprints() if force._uid(f) == ids['owner']); fp.Move(pcbnew.VECTOR2I_MM(1, 0))
    elif fault == 'wrong_root': root = ids['anchor']
    elif fault == 'wrong_net': new[0].SetNet(c.FindNet('OTHER'))
    elif fault == 'new_barrel':
        via = pcbnew.PCB_VIA(c); via.SetNet(new[0].GetNet()); via.SetPosition(new[0].GetStart())
        via.SetWidth(1000000); via.SetDrill(500000); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); c.Add(via)
    elif fault == 'second_tap':
        t = pcbnew.PCB_TRACK(c); t.SetNet(new[2].GetNet()); t.SetLayer(new[2].GetLayer())
        t.SetWidth(new[2].GetWidth()); t.SetStart(new[2].GetStart()); t.SetEnd(pcbnew.VECTOR2I_MM(40, 8))
        c.Add(t); group.AddItem(t)
    elif fault == 'wrong_floor': tracks[ids['exclusive']].SetWidth(tracks[ids['exclusive']].GetWidth()+1)
    elif fault == 'oversize_incoming': new[0].SetWidth(new[0].GetWidth()+1)
    elif fault == 'lost_original_member':
        original = next(t for t in group.GetItems() if force._uid(t) not in set(map(force._uid, new)))
        group.RemoveItem(original)
    elif fault == 'retire_trunk': retired.append(ids['trunk'])
    elif fault == 'duplicate_cut': retired *= 2
    elif fault == 'wrong_anchor': group.SetName(consumer.PREFIX+'|'.join((ids['root'], ids['portal'], '')))
    else: new[0].SetEnd(pcbnew.VECTOR2I_MM(15, 100))
    # Intentionally malformed saved inputs must reach the receiver. The
    # normal production save guard can refuse these first; do not weaken
    # it just to build a negative fixture.
    pcbnew.SaveBoard(str(candidate), c)
    result = reanchor.receive(source, candidate, board_hint='arbitrary', root_pad_uuid=root,
        retired_track_uuids=retired, timeout_s=10.)
    assert not result['ok'] and not result['complete'] and result['errors'], result
    assert not result['release_authority'] and not result['new_barrel_capacity_credited']

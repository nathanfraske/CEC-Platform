"""Generated local land repair: no product, net, pin or coordinate exceptions."""
import json

import pytest
pcbnew = pytest.importorskip('pcbnew')
import cec_fr
import cec_fab_profile as fab
import cec_dimension_repair as repair
import cec_local_via_rebuild as rebuild
from test_local_pofv_ownership import fixture


def board_file(tmp_path, *, angle=0, shift=(0, 0), owner=None, branch_owner=None,
               profile=True, offset=(0.4, 0), size=(0.7, 0.7)):
    b, via = fixture(offset=offset, size=size, diameter=0.6, drill=0.3, angle=angle)
    if not profile:
        props = b.GetProperties()
        props['CEC_FAB_PROFILE'] = ''
        b.SetProperties(props)
    group = pcbnew.PCB_GROUP(b)
    group.SetName(owner or cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    b.Add(group)
    group.AddItem(via)
    via.SetLocked(True)
    if branch_owner:
        tracks = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK']
        g = pcbnew.PCB_GROUP(b)
        g.SetName(branch_owner)
        b.Add(g)
        for track in tracks:
            g.AddItem(track)
            track.SetLocked(True)
    for item in [*b.GetFootprints(), *b.GetTracks()]:
        item.Move(pcbnew.VECTOR2I_MM(*shift))
    path = tmp_path / 'arbitrary-local.kicad_pcb'
    pcbnew.SaveBoard(str(path), b)
    path.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {'classes': [
        {'name': 'Default', 'track_width': 0.25, 'clearance': 0.15,
         'via_diameter': 0.6, 'via_drill': 0.3}]}}))
    return path, repair.uid(via)


@pytest.mark.parametrize('angle,shift', [(0, (0, 0)), (90, (13, -5)), (45, (-8, 11))])
def test_native_rebuild_and_idempotence(tmp_path, angle, shift):
    path, uid = board_file(tmp_path, angle=angle, shift=shift)
    original = repair.family_digest(path)
    report = rebuild.rebuild(path, uid)
    assert report['changed'], report
    b = pcbnew.LoadBoard(str(path))
    via = next(v for v in b.GetTracks() if repair.uid(v) == uid)
    assert via.IsLocked()
    assert fab.local_pofv_via_decision(b, via)[0]
    assert repair._owners(b, via) == [cec_fr.LOCAL_POFV_SIGNAL_VIA_GROUP]
    assert len(report['attempts']) <= 8
    assert not any(blocker.get('uuid') == uid
                   for attempt in report['attempts']
                   for blocker in attempt.get('spot', {}).get('blockers', ()))
    assert all(abs(t.GetStart().x-t.GetEnd().x) == abs(t.GetStart().y-t.GetEnd().y)
               or t.GetStart().x == t.GetEnd().x or t.GetStart().y == t.GetEnd().y
               for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK')
    after = repair.family_digest(path)
    assert original['.kicad_pro'] == after['.kicad_pro']
    assert original['.kicad_dru'] == after['.kicad_dru']
    assert not rebuild.rebuild(path, uid)['changed']
    assert repair.family_digest(path) == after


@pytest.mark.parametrize('kwargs,reason', [
    ({'owner': 'ANOTHER_OWNER'}, 'local_boundary_refused'),
    ({'branch_owner': 'PRECISION_OR_AUTHORED_OWNER'}, 'local_boundary_refused'),
    ({'profile': False}, 'local_pofv_profile_missing'),
    ({'offset': (0, 0), 'size': (2, 2)}, 'no_live_local_via_assembly_failure'),
])
def test_unrelated_or_unneeded_mutations_refused(tmp_path, kwargs, reason):
    path, uid = board_file(tmp_path, **kwargs)
    before = repair.family_digest(path)
    report = rebuild.rebuild(path, uid)
    assert not report['changed']
    assert report['reason'] == reason
    assert repair.family_digest(path) == before


def test_stale_owner_and_profile_refused(tmp_path):
    path, uid = board_file(tmp_path)
    target = rebuild.plan(path, uid)['target']
    b = pcbnew.LoadBoard(str(path))
    next(iter(b.Groups())).SetName('USER_OWNED_NOW')
    pcbnew.SaveBoard(str(path), b)
    before = path.read_bytes()
    assert repair.mutate(path, target, target['seats_nm'][0])['reason'] == 'stale_boundary_or_owner'
    assert path.read_bytes() == before


def test_other_same_net_drill_is_never_exempted(tmp_path):
    path, uid = board_file(tmp_path)
    target = rebuild.plan(path, uid)['target']
    b = pcbnew.LoadBoard(str(path))
    original = next(v for v in b.GetTracks() if repair.uid(v) == uid)
    other = pcbnew.PCB_VIA(b)
    other.SetPosition(pcbnew.VECTOR2I(*target['seats_nm'][0]))
    other.SetWidth(pcbnew.FromMM(0.3))
    other.SetDrill(pcbnew.FromMM(0.2))
    other.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    other.SetViaType(pcbnew.VIATYPE_THROUGH)
    other.SetNetCode(original.GetNetCode())
    b.Add(other)
    pcbnew.SaveBoard(str(path), b, True)
    before = path.read_bytes()
    result = repair.mutate(path, target, target['seats_nm'][0])
    assert not result['changed']
    assert result['reason'] in {'stale_boundary_or_owner', 'candidate_land_blocked'}
    assert path.read_bytes() == before


def test_profile_change_is_not_inherited_from_old_plan(tmp_path):
    path, uid = board_file(tmp_path)
    target = rebuild.plan(path, uid)['target']
    b = pcbnew.LoadBoard(str(path))
    props = b.GetProperties()
    props['CEC_FAB_PROFILE'] = ''
    b.SetProperties(props)
    pcbnew.SaveBoard(str(path), b, True)
    before = path.read_bytes()
    result = repair.mutate(path, target, target['seats_nm'][0])
    assert not result['changed']
    assert result['reason'] == 'local_pofv_profile_missing'
    assert path.read_bytes() == before


@pytest.mark.parametrize('policy', [{'max_seats': 9}, {'max_seats': -1}, {'radius_mm': 2},
                                   {'radius_mm': float('nan')}])
def test_finite_bound_required(policy):
    with pytest.raises(ValueError):
        rebuild.plan('never-loaded', 'unused', **policy)

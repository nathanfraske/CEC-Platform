"""Native Source-owned inward re-landing, without fixed-boundary/API waivers."""
import copy
import json

import pcbnew
import pytest
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_local_branch_access as fixed
import cec_measurement_leaf_relanding as op
import cec_source_literal_additions as literal
import cec_source_literal_retirement as retirement
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items
from test_measurement_terminal_route import fixture as terminal_fixture


def case(tmp_path, monkeypatch, quarter=0, renamed=True):
    board, _, root, target = terminal_fixture(quarter)
    anchor = target.GetParentFootprint()
    if renamed:
        root.GetParentFootprint().SetReference('RELABELED_MEASUREMENT_DEVICE')
        anchor.SetReference('UNCHANGED_ACTUAL_PICKUP')
    domains = {n.GetNetname(): dict(complete=True, authority_refs=[anchor.GetReference()])
        for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    # Current-domain fixture selection only. All copper, roles, topology,
    # native reconstruction, partitions and contact predicates remain real.
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a, **k: copy.deepcopy(domains))
    old = pcbnew.PCB_TRACK(board)
    old.SetStart(root.GetPosition()); old.SetEnd(target.GetPosition())
    old.SetWidth(200000); old.SetLayer(pcbnew.F_Cu); old.SetNet(root.GetNet()); old.SetLocked(True)
    board.Add(old)
    source = tmp_path / 'source' / 'board.kicad_pcb'
    source.parent.mkdir()
    field._save_field_snapshot(board, source)

    def transform(p):
        x, y = p
        for _ in range(quarter):
            x, y = y, 60000000-x
        return [x, y]
    points = list(map(transform, [(10000000,10000000), (12000000,12000000),
        (17200000,12000000), (19200000,10000000), (19800000,10000000)]))
    return source, force._uid(root), force._uid(target), points


def build(source, uid, points, tmp_path):
    child = force._copy_family(source, tmp_path / 'child')
    scope = op.plan(pcbnew.LoadBoard(str(source)), source,
        board_hint='UNRELATED_SOURCE', pad_uuid=uid, timeout_s=9.)
    diagnostic = op._assess(source, scope, points, deadline=op._deadline(9.))
    assert diagnostic['ok'] is True, json.dumps(diagnostic, sort_keys=True)
    result = op.construct_private(source, child, board_hint='UNRELATED_SOURCE',
        pad_uuid=uid, points_nm=points, timeout_s=9.)
    assert result['complete'] is True
    return child


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('renamed', [False, True])
def test_actual_saved_changed_pickup_on_same_inward_land_receives(tmp_path, monkeypatch, quarter, renamed):
    source, uid, target, points = case(tmp_path, monkeypatch, quarter, renamed)
    source_bytes = source.read_bytes()
    candidate = build(source, uid, points, tmp_path)
    saved = candidate.read_bytes()
    proof = op.receive(source, candidate, board_hint='UNRELATED_SOURCE', pad_uuid=uid, timeout_s=9.)
    assert proof['ok'] is True and proof['complete'] is True, proof
    assert target in proof['source_scope']['source_leaf']['boundary_uuids']
    assert target in proof['new_leaf']['boundary_uuids']
    assert proof['source_scope']['source_leaf']['points_nm'][-1] != proof['new_leaf']['points_nm'][-1]
    assert proof['all_original_terminal_and_surviving_conductor_partitions_preserved']
    assert proof['exact_force_copper_barrels_component_poses_and_rules_preserved']
    assert source.read_bytes() == source_bytes and candidate.read_bytes() == saved
    assert not proof['routing_admitted'] and not proof['current_authority']
    assert not proof['kelvin_qualified'] and not proof['release_authority']
    # The old operation's fixed endpoint contract remains strict. No role flag
    # or renamed boundary makes this re-landing pass fixed-boundary receiving.
    unchanged = fixed.receive_measurement_reflow(source, candidate,
        board_hint='UNRELATED_SOURCE', pad_uuid=uid, timeout_s=9.)
    assert unchanged['ok'] is False and unchanged['errors']


@pytest.mark.parametrize('fault', ['force_cut', 'force_width', 'moved_pad', 'thin', 'wrong_net',
    'back_face', 'via', 'orphan', 'new_group', 'changed_sidecar', 'target_dnp'])
def test_saved_relanding_cannot_retire_or_change_any_other_material(tmp_path, monkeypatch, fault):
    source, uid, target, points = case(tmp_path, monkeypatch)
    candidate = build(source, uid, points, tmp_path)
    source_bytes = source.read_bytes()
    b = pcbnew.LoadBoard(str(candidate))
    source_ids = {force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    added = [t for t in b.GetTracks() if force._uid(t) not in source_ids]
    bus = next(t for t in b.GetTracks() if t.GetWidth() == 600000)
    pads = {force._uid(p): p for f in b.GetFootprints() for p in f.Pads()}
    if fault == 'force_cut': discard_items(b, [bus])
    elif fault == 'force_width': bus.SetWidth(650000)
    elif fault == 'moved_pad': pads[target].Move(pcbnew.VECTOR2I_MM(.01, 0))
    elif fault == 'thin': added[0].SetWidth(100000)
    elif fault == 'wrong_net': added[0].SetNet(b.FindNet('FORCE_B'))
    elif fault == 'back_face': added[0].SetLayer(pcbnew.B_Cu)
    elif fault == 'via':
        v = pcbnew.PCB_VIA(b); v.SetPosition(pads[uid].GetPosition()); v.SetNet(pads[uid].GetNet())
        v.SetWidth(600000); v.SetDrill(300000); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v)
    elif fault == 'orphan':
        t = pcbnew.PCB_TRACK(b); t.SetStart(pcbnew.VECTOR2I_MM(42, 25)); t.SetEnd(pcbnew.VECTOR2I_MM(43, 25))
        t.SetWidth(200000); t.SetLayer(pcbnew.F_Cu); t.SetNet(pads[uid].GetNet()); b.Add(t)
    elif fault == 'new_group':
        g = pcbnew.PCB_GROUP(b); g.SetName('unowned'); b.Add(g); g.AddItem(added[0])
    elif fault == 'target_dnp': pads[target].GetParentFootprint().SetDNP(True)
    if fault == 'changed_sidecar':
        candidate.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {'classes': []}}))
    elif fault in ('thin','wrong_net','back_face','via','orphan','new_group'):
        # Exercise the actual new-copper predicates rather than accidentally
        # failing because the native serializer normalized an old field.
        stencil=retirement.subtract(raw.raw_text(candidate), {force._uid(t) for t in added})
        native=tmp_path/'mutated-new-copper.kicad_pcb'
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(native), b)
        raw.write_raw(candidate,literal.assemble(stencil,raw.raw_text(native)))
    else:
        # Deliberately malformed physical/literal input for the receiver, not
        # a producer pass. Opaque preservation must reject a no-op reserialize
        # too if it normalized an original field on this fixture.
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate), b)
    proof = op.receive(source, candidate, board_hint='UNRELATED_SOURCE', pad_uuid=uid, timeout_s=9.)
    assert proof['ok'] is False and proof['errors'], proof
    assert source.read_bytes() == source_bytes


@pytest.mark.parametrize('fault', ['outside_pad', 'outward_side', 'off_angle', 'force_contact',
    'wrong_root', 'zero_edge', 'too_long', 'boolean_coordinate'])
def test_proposal_must_obey_whole_native_width_inward_contact_and_craft(tmp_path, monkeypatch, fault):
    source, uid, target, points = case(tmp_path, monkeypatch)
    if fault == 'outside_pad': points[-1] = [19400000,10000000]
    elif fault == 'outward_side': points = [[10000000,10000000], [10000000,12000000],
        [22000000,12000000], [22000000,10000000], [20200000,10000000]]
    elif fault == 'off_angle': points[1][0] += 1
    elif fault == 'force_contact': points = [[10000000,10000000], [24000000,10000000], [19800000,10000000]]
    elif fault == 'wrong_root': points[0][0] += 1
    elif fault == 'zero_edge': points.insert(1, points[0][:])
    elif fault == 'too_long': points = [[10000000,10000000], [10000000,50000000],
        [19800000,50000000], [19800000,10000000]]
    else: points[0][0] = True
    candidate = force._copy_family(source, tmp_path / 'untouched-rejected')
    before = candidate.read_bytes()
    with pytest.raises(ValueError):
        op.construct_private(source, candidate, board_hint='UNRELATED_SOURCE',
            pad_uuid=uid, points_nm=points, timeout_s=9.)
    assert candidate.read_bytes() == before


@pytest.mark.parametrize('value', [True, False, 0, -1, 11, float('nan'), float('inf')])
def test_invalid_or_unbounded_work_lease_never_becomes_positive(value):
    proof = op.receive('missing-source', 'missing-child', board_hint='other', pad_uuid='not-a-pad', timeout_s=value)
    assert proof['ok'] is False and proof['complete'] is False and proof['errors']


def test_cut_query_cannot_be_represented_as_actual_saved_Source(tmp_path, monkeypatch):
    source, uid, target, points = case(tmp_path, monkeypatch)
    b = pcbnew.LoadBoard(str(source))
    discard_items(b, [t for t in b.GetTracks() if t.GetWidth() == 200000])
    with pytest.raises(ValueError, match='unaltered_saved_Source'):
        op.plan(b, source, board_hint='UNRELATED_SOURCE', pad_uuid=uid)


@pytest.mark.parametrize('fault',['unknown_mpn','wrong_package','dnp','power_role','incomplete_domain','back_surface','isolated_source'])
def test_plan_requires_positive_current_manufacturer_surface_and_existing_leaf(tmp_path,monkeypatch,fault):
    source,uid,target,points=case(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));pads={force._uid(p):p for f in b.GetFootprints()for p in f.Pads()}
    root=pads[uid];owner=root.GetParentFootprint()
    if fault=='unknown_mpn':owner.SetValue('UNRESOLVED_DEVICE')
    elif fault=='wrong_package':owner.SetFPID(pcbnew.LIB_ID('fixture','unknown-package'))
    elif fault=='dnp':owner.SetDNP(True)
    elif fault=='power_role':root.SetNumber('6')
    elif fault=='incomplete_domain':monkeypatch.setattr(topology,'board_current_domains',lambda *a,**k:{})
    elif fault=='back_surface':
        pivot=pcbnew.VECTOR2I_MM(30,30)
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:item.Flip(pivot,True)
    else:discard_items(b,[t for t in b.GetTracks()if t.GetWidth()==200000])
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(pcbnew.LoadBoard(str(source)),source,
        board_hint='UNRELATED_SOURCE',pad_uuid=uid,timeout_s=9.)

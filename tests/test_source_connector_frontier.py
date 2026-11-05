"""Retained sideband access, not an inferred terminal/barrel/current edge."""
import json
import math
import time

import pcbnew
import pytest
import cec_additive_pair_repair as save
import cec_field_coupling as field
import cec_force_current as force
import cec_source_connector_feedthrough as op
from test_source_connector_feedthrough import fixture


def frontier_fixture(tmp_path, monkeypatch, *, quarter=0, back=False, barrel=False,
        source_fault=None, child_fault=None):
    source, root, ids, _ = fixture(tmp_path, monkeypatch, quarter, back)
    b = pcbnew.LoadBoard(str(source))
    first, last = [next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p) == u) for u in ids]
    a, z = first.GetPosition(), last.GetPosition()
    step = pcbnew.VECTOR2I(round((a.x-z.x)/3), round((a.y-z.y)/3))
    track = pcbnew.PCB_TRACK(b); track.SetNet(last.GetNet()); track.SetStart(z); track.SetEnd(z+step)
    face = pcbnew.B_Cu if back else pcbnew.F_Cu
    track.SetLayer(face); track.SetWidth(200000); track.SetLocked(True); b.Add(track)
    if source_fault == 'thin':
        track.SetWidth(100000)
    elif source_fault == 'mask':
        track.SetHasSolderMask(True)
    access = force._uid(track)
    if barrel:
        via = pcbnew.PCB_VIA(b); via.SetNet(last.GetNet()); via.SetPosition(track.GetEnd())
        via.SetWidth(600000); via.SetDrill(300000)
        via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetLocked(True); b.Add(via); access = force._uid(via)
        if source_fault == 'blind':
            via.SetViaType(pcbnew.VIATYPE_BLIND); via.SetLayerPair(pcbnew.F_Cu, 6)
        elif source_fault == 'zero_drill':
            via.SetDrill(0)
        face = pcbnew.F_Cu if back else pcbnew.B_Cu
    field._save_field_snapshot(b, source)
    parent_sha = force._hash(source)
    candidate = force._copy_family(source, tmp_path/'frontier-child')
    child = pcbnew.LoadBoard(str(candidate)); old = {force._uid(t) for t in child.GetTracks()}
    pads = {force._uid(p):p for f in child.GetFootprints() for p in f.Pads()}
    target = next(t for t in child.GetTracks() if force._uid(t) == access)
    point = target.GetPosition() if barrel else target.GetEnd()
    incoming = pcbnew.PCB_TRACK(child); incoming.SetNet(pads[ids[0]].GetNet())
    incoming.SetStart(pads[ids[0]].GetPosition()); incoming.SetEnd(point)
    incoming.SetWidth(200000); incoming.SetLayer(face); child.Add(incoming)
    if child_fault == 'newvia':
        v = pcbnew.PCB_VIA(child); v.SetNet(incoming.GetNet()); v.SetPosition(incoming.GetStart())
        v.SetWidth(600000); v.SetDrill(300000); v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); child.Add(v)
    elif child_fault == 'orphan':
        t = incoming.Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
        t.SetStart(pcbnew.VECTOR2I_MM(3,3)); t.SetEnd(pcbnew.VECTOR2I_MM(4,3)); child.Add(t)
    elif child_fault == 'third_island':
        tap = child.FindFootprintByReference('unreached_tap').FindPadByNumber('1')
        t = incoming.Duplicate(); t.m_Uuid.Clone(pcbnew.KIID()); t.SetStart(point); t.SetEnd(tap.GetPosition()); child.Add(t)
    elif child_fault == 'source_move':
        target.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif child_fault == 'source_cut':
        from cec_native_items import discard_items
        discard_items(child, [target])
    if child_fault:
        field._save_field_snapshot(child, candidate)
    else:
        save.save_native_additions(candidate, child, {}, old, board_hint='synthetic')
    assert force._hash(source) == parent_sha
    return source, root, ids, candidate, [ids[0], access]


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('barrel', [False, True])
def test_actual_retained_frontier_rotations_and_faces(tmp_path, monkeypatch, quarter, back, barrel):
    source, root, ids, candidate, access = frontier_fixture(tmp_path, monkeypatch,
        quarter=quarter, back=back, barrel=barrel)
    tick = time.monotonic()
    result = op.receive_native_frontier(source, candidate, board_hint=str(root),
        pad_uuids=ids, access_uuids=access, timeout_s=8.)
    assert time.monotonic()-tick < 10.
    assert result['ok'] and result['complete'], result['errors']
    assert (result['source_components'], result['candidate_components'], result['unreached_Source_component_count']) == (3,2,1)
    contacts = result['retained_native_frontier_contacts']
    assert contacts['complete'] and len(contacts['actual_contacts']) == 2
    assert contacts['new_barrels'] == 0 and contacts['old_barrel_capacity_credited'] is False
    assert all(row['positive_native_contact_nm2'] > 0 for row in contacts['actual_contacts'])
    assert not any(result[k] for k in ('ordinary_reclassification', 'quiet_reclassification', 'new_current_budget',
        'current_qualified', 'barrel_qualified', 'inherited_footprint_qualified', 'release_authority'))
    legacy = op.receive(source, candidate, board_hint=str(root), pad_uuids=ids, timeout_s=8.)
    assert not legacy['ok'] and any('terminal_contact_required' in e for e in legacy['errors']), legacy


@pytest.mark.parametrize('fault', ['thin', 'mask', 'blind'])
def test_only_actual_full_class_track_or_full_depth_source_barrel_access(tmp_path, monkeypatch, fault):
    source, root, ids, candidate, access = frontier_fixture(tmp_path, monkeypatch,
        barrel=fault in ('blind', 'zero_drill'), source_fault=fault)
    result = op.receive_native_frontier(source, candidate, board_hint=str(root), pad_uuids=ids, access_uuids=access)
    assert not result['ok'] and result['errors'], result


def test_native_zero_drill_cannot_be_offered_as_existing_plated_access(tmp_path, monkeypatch):
    # A zero stored override means "use the inherited drill" in KiCad, not
    # a physical zero bore. Exercise an unknown/nonpositive effective native
    # result explicitly; do not mislabel a normal default as zero geometry.
    source, root, ids, candidate, access = frontier_fixture(tmp_path, monkeypatch, barrel=True)
    parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
    deadline = time.monotonic()+8.
    proof = op._canonical(parent, source.resolve(), str(root), ids, deadline)
    parts = op._parts(parent, proof['net'], deadline)
    roots = [next(part for part in parts if uid in part) for uid in ids]
    old = {force._uid(t) for t in parent.GetTracks()}
    incoming = [t for t in child.GetTracks() if force._uid(t) not in old]
    monkeypatch.setattr(pcbnew.PCB_VIA, 'GetDrillValue', lambda *args:0)
    with pytest.raises(ValueError, match='full_depth_Source_signal_barrel'):
        op._frontier_contacts(parent, incoming, proof, roots, access, deadline)


@pytest.mark.parametrize('fault', ['newvia', 'orphan', 'third_island', 'source_move', 'source_cut'])
def test_frontier_never_licenses_new_barrels_extra_islands_or_source_changes(tmp_path, monkeypatch, fault):
    source, root, ids, candidate, access = frontier_fixture(tmp_path, monkeypatch, child_fault=fault)
    result = op.receive_native_frontier(source, candidate, board_hint=str(root), pad_uuids=ids, access_uuids=access)
    assert not result['ok'] and result['errors'], result


@pytest.mark.parametrize('fault', ['same_island', 'unknown', 'wrong_source_pad', 'wrong_net'])
def test_access_ids_cannot_replace_complete_source_island_membership(tmp_path, monkeypatch, fault):
    source, root, ids, candidate, access = frontier_fixture(tmp_path, monkeypatch)
    b = pcbnew.LoadBoard(str(source))
    if fault == 'same_island':
        access = [ids[1], access[1]]
    elif fault == 'unknown':
        access[1] = 'does-not-exist'
    elif fault == 'wrong_source_pad':
        access[1] = force._uid(b.FindFootprintByReference('unreached_tap').FindPadByNumber('1'))
    else:
        access[1] = force._uid(b.FindFootprintByReference('other_output').FindPadByNumber('1'))
    result = op.receive_native_frontier(source, candidate, board_hint=str(root), pad_uuids=ids, access_uuids=access)
    assert not result['ok'] and result['errors'], result


def test_retained_source_barrel_actual_face_must_be_flashed(tmp_path, monkeypatch):
    source, root, ids, candidate, access = frontier_fixture(tmp_path, monkeypatch, barrel=True)
    monkeypatch.setattr(pcbnew.PCB_VIA, 'FlashLayer', lambda *args:False)
    result = op.receive_native_frontier(source, candidate, board_hint=str(root), pad_uuids=ids, access_uuids=access)
    assert not result['ok'] and any('flashed' in e for e in result['errors']), result


@pytest.mark.parametrize('bad', [None, [], ['a'], ['a', 'a'], ['a', True], True, 'ab'])
def test_frontier_api_requires_explicit_two_identities_not_flag_or_proof(bad):
    with pytest.raises(ValueError):
        op.receive_native_frontier('missing', 'missing', board_hint='synthetic',
            pad_uuids=['first', 'last'], access_uuids=bad)

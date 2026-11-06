"""Actual planar-current peers compose contacts, never caller proof authority."""
import copy
import time

import pcbnew
import pytest
import cec_additional_aggregate_macro as op
from cec_native_items import discard_items
from test_wired_additional_macro_integration import context, leaves
from test_field_proposals import track


def prepared(tmp_path, monkeypatch, *, mid_tee=False, disconnected=False):
    parent, _, proposal, _, ground = context(tmp_path, monkeypatch, with_supply_boundary=True)
    uid = leaves.native.force._uid
    positive = parent.FindFootprintByReference('RENAMED_C').FindPadByNumber('1')
    supply = [t for t in parent.GetTracks() if t.GetClass() == 'PCB_TRACK'
        and t.GetNetCode() == positive.GetNetCode()]
    first, = [t for t in supply if positive.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(), 0)]
    joint = tuple(first.GetEnd())
    second, = [t for t in supply if t is not first and uid(t) != uid(first)
        and (tuple(t.GetStart()) == joint or tuple(t.GetEnd()) == joint)]
    end = tuple(second.GetEnd()) if tuple(second.GetStart()) == joint else tuple(second.GetStart())
    # Two retained branches expose both the internal junction and far terminal.
    tee = tuple((a+b)//2 for a,b in zip(joint,end)) if mid_tee else joint
    branch = track(parent, positive.GetNetname(), tuple(v/1e6 for v in tee),
        (tee[0]/1e6, tee[1]/1e6 + 2), width=.5)
    tail = track(parent, positive.GetNetname(), tuple(v/1e6 for v in end),
        (end[0]/1e6, end[1]/1e6 - 2), width=.5)
    cuts = [uid(first), uid(second)]; terminals = {uid(branch), uid(tail), uid(positive)}
    if disconnected:
        track(parent, positive.GetNetname(), (23,24), (24,24), width=.5)
        remote = track(parent, positive.GetNetname(), (24,24), (25,24), width=.5)
        track(parent, positive.GetNetname(), (25,24), (26,24), width=.5)
        cuts.append(uid(remote))
    source = parent.GetFileName()
    leaves.wired.cap.field._save_field_snapshot(parent, source)
    parent = pcbnew.LoadBoard(source)
    proposal['additional_aggregate_capacitors'] = op.collect(parent, proposal['poses'],
        board_hint=proposal['board_hint'], allow_linear_power_stage_reconstruction=True)
    proposal['source_native_binding'] = leaves.native.row._source_binding(parent)
    proposal['row_plan']['retired_track_uuids'] = cuts
    child = pcbnew.LoadBoard(source)
    cap = child.FindFootprintByReference('RENAMED_C')
    cap.SetPosition(pcbnew.VECTOR2I_MM(*proposal['poses']['RENAMED_C'][:2]))
    discard_items(child, [t for t in child.GetTracks() if uid(t) in set(ground + cuts)])
    return parent, child, proposal, cuts, terminals


def demands(parent, child, proposal, cuts):
    return op.requests(parent, child, proposal, composed_current_cut_uuids=cuts)


def boundaries(rows):
    return [r for k, r in rows.items() if k.startswith('aggregate_incident_cut:')]


def test_native_two_cut_branch_preserves_every_actual_terminal(tmp_path, monkeypatch):
    parent, child, proposal, cuts, terminals = prepared(tmp_path, monkeypatch)
    rows = boundaries(demands(parent, child, proposal, cuts))
    assert rows and all(r['width_nm'] >= 500000 for r in rows)
    assert all(r['every_surviving_source_component_port_mandatory'] for r in rows)
    actual = set()
    for row in rows:
        for port in (row['a'], row['b']):
            actual.update(port.get('native_uuids', []))
            if port.get('pad_uuid'): actual.add(port['pad_uuid'])
    assert terminals <= actual
    for row in rows:
        track(child, row['net'], tuple(v/1e6 for v in row['a']['at_nm']),
            tuple(v/1e6 for v in row['b']['at_nm']), width=.5)
    for row in rows:
        received = leaves.wired.cap.ports.full_width_connection(parent, child,
            parent.GetFileName(), row, proposal['board_hint'], time.monotonic()+2.)
        assert received['all_named_contacts_connected']
        assert received['all_used_strokes_meet_source_and_aggregate_width']


def test_default_does_not_authorize_connected_retired_peer(tmp_path, monkeypatch):
    parent, child, proposal, cuts, _ = prepared(tmp_path, monkeypatch)
    with pytest.raises(ValueError): op.requests(parent, child, proposal)


def test_disconnected_declared_full_current_peer_cannot_expand_cap_cohort(tmp_path, monkeypatch):
    parent, child, proposal, cuts, _ = prepared(tmp_path, monkeypatch, disconnected=True)
    remote = cuts[-1]
    # This really is another eligible full-current edge, not an invalid ID.
    plan = leaves.wired.cap.full.plan(parent, parent.GetFileName(), board_hint=proposal['board_hint'],
        retired_track_uuids=[remote], timeout_s=3.)
    assert plan['retired_track_uuids'] == [remote]
    expected = boundaries(demands(parent, child, proposal, cuts[:2]))
    actual = boundaries(demands(parent, child, proposal, cuts))
    assert actual == expected
    assert remote not in repr(actual)


def test_retained_mid_segment_tee_is_a_mandatory_literal_native_port(tmp_path, monkeypatch):
    parent, child, proposal, cuts, terminals = prepared(tmp_path, monkeypatch, mid_tee=True)
    rows = boundaries(demands(parent, child, proposal, cuts))
    edges = {leaves.native.force._uid(t): t for t in parent.GetTracks()}
    second = edges[cuts[1]]
    tee_uid, = [u for u in terminals if u in edges and edges[u].GetEnd().y > edges[u].GetStart().y]
    ports = [p for row in rows for p in (row['a'],row['b']) if tee_uid in p.get('native_uuids', [])]
    assert ports
    assert all(tuple(p['at_nm']) not in (tuple(second.GetStart()),tuple(second.GetEnd())) for p in ports)
    assert all(second.GetEffectiveShape(second.GetLayer()).Collide(pcbnew.VECTOR2I(*p['at_nm']),0)
        for p in ports)


@pytest.mark.parametrize('fault', ['deadline', 'source_during_plan'])
def test_cohort_rechecks_deadline_and_source_after_real_peer_derivation(tmp_path, monkeypatch, fault):
    import cec_aggregate_current_cut_cohort as cohort
    parent, child, proposal, cuts, _ = prepared(tmp_path, monkeypatch)
    proof = proposal['additional_aggregate_capacitors']['RENAMED_C']
    planner = leaves.wired.cap.full
    incident = planner.plan(parent, parent.GetFileName(), board_hint=proposal['board_hint'],
        retired_track_uuids=[cuts[0]], timeout_s=3.)
    retired = set(proposal['retired_track_uuids']) | set(cuts)
    deadline = time.monotonic()+5.
    if fault == 'deadline': deadline = time.monotonic()-1.
    else:
        original = planner.plan
        def mutate(*a, **kw):
            result = original(*a, **kw)
            if kw.get('retired_track_uuids') == [cuts[1]]:
                parent.FindFootprintByReference('RENAMED_C').SetValue('changed-during-proof')
            return result
        monkeypatch.setattr(planner, 'plan', mutate)
    with pytest.raises(ValueError):
        cohort.requests(parent, child, proposal, proof, [incident], retired, cuts, deadline)


@pytest.mark.parametrize('fault', ['unowned_peer', 'retained_motion', 'omitted_pad', 'source_change',
    'duplicate', 'unknown', 'nonretired', 'wrong_contract'])
def test_explicit_selection_never_waives_native_or_current_identity(tmp_path, monkeypatch, fault):
    parent, child, proposal, cuts, terminals = prepared(tmp_path, monkeypatch)
    selected = list(cuts)
    if fault == 'unowned_peer': selected.pop()
    elif fault == 'retained_motion':
        next(t for t in child.GetTracks() if leaves.native.force._uid(t) in terminals).Move(pcbnew.VECTOR2I(1, 0))
    elif fault == 'omitted_pad':
        child.Remove(child.FindFootprintByReference('RENAMED_C'))
    elif fault == 'source_change':
        parent.FindFootprintByReference('RENAMED_C').SetValue('changed')
    elif fault == 'duplicate': selected.append(selected[0])
    elif fault == 'unknown': selected.append('00000000-0000-0000-0000-000000000000')
    elif fault == 'nonretired': selected.append(next(u for u in terminals if any(
        leaves.native.force._uid(t) == u for t in parent.GetTracks())))
    else:
        planner = leaves.wired.cap.full; original = planner.plan
        def changed(*a, **kw):
            result = copy.deepcopy(original(*a, **kw))
            if kw.get('retired_track_uuids') == [cuts[1]]:
                result['contract']['current_authority']['amps'] += 1
            return result
        monkeypatch.setattr(planner, 'plan', changed)
    with pytest.raises(ValueError): demands(parent, child, proposal, selected)


def test_thin_restoration_cannot_satisfy_composed_full_current_ports(tmp_path, monkeypatch):
    parent, child, proposal, cuts, _ = prepared(tmp_path, monkeypatch)
    rows = boundaries(demands(parent, child, proposal, cuts))
    assert rows
    for row in rows:
        track(child, row['net'], tuple(v/1e6 for v in row['a']['at_nm']),
            tuple(v/1e6 for v in row['b']['at_nm']), width=.2)
    with pytest.raises(ValueError):
        leaves.wired.cap.ports.full_width_connection(parent, child, parent.GetFileName(), rows[0],
            proposal['board_hint'], time.monotonic()+2.)

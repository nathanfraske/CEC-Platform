"""Dispatch/schema controls only, never mocked physical acceptance.

The public ordinary receiver is mocked only to verify exact delegation and
fail-closed result propagation. Small native-shaped doubles test preliminary
scope rejection; saved-board physical proof remains in the existing receiver.
"""
import copy
from pathlib import Path
from types import SimpleNamespace
import time
import pytest
import root_ordinary_barrel_chain_phase_20261027 as adapter

TRACK = '11111111-1111-4111-8111-111111111111'
VIA = '22222222-2222-4222-8222-222222222222'
NEW_TRACK = '33333333-3333-4333-8333-333333333333'
NEW_VIA = '44444444-4444-4444-8444-444444444444'
NET = '/arbitrary-control'


def row_at(tmp_path):
    source = tmp_path/'source.kicad_pcb'; source.write_bytes(b'dispatch Source only\n')
    child = tmp_path/'child.kicad_pcb'; child.write_bytes(b'dispatch child only\n')
    row = dict(kind=adapter.KIND, candidate=str(child), candidate_sha256=adapter.force._hash(child),
        net=NET, retired_track_uuids=[TRACK], retired_via_uuids=[VIA])
    return source, child, row


def registration():
    return (adapter.base.validate_phases, adapter.base.receive_phase,
            adapter.base.annotation_dependencies, adapter.base.KINDS)


class Item:
    def __init__(self, uid, kind='PCB_TRACK', net=NET):
        self.m_Uuid = SimpleNamespace(AsString=lambda: uid)
        self.kind, self.net = kind, net
        self.locked, self.group, self.masked = False, None, False
        self.top, self.bottom = adapter.pcbnew.F_Cu, adapter.pcbnew.B_Cu
        self.via_type = adapter.pcbnew.VIATYPE_THROUGH

    def GetClass(self): return self.kind
    def GetNetname(self): return self.net
    def IsLocked(self): return self.locked
    def GetParentGroup(self): return self.group
    def HasSolderMask(self): return self.masked
    def GetViaType(self): return self.via_type
    def TopLayer(self): return self.top
    def BottomLayer(self): return self.bottom


def native_scope_doubles(monkeypatch, source, child):
    old = [Item(TRACK), Item(VIA, 'PCB_VIA')]
    new = [Item(NEW_TRACK), Item(NEW_VIA, 'PCB_VIA')]
    groups = []
    boards = {source: SimpleNamespace(GetTracks=lambda: old, Groups=lambda: groups),
              child: SimpleNamespace(GetTracks=lambda: new, Groups=lambda: [])}
    monkeypatch.setattr(adapter.pcbnew, 'LoadBoard', lambda path: boards[Path(path)])
    monkeypatch.setattr(adapter.ordinary, 'eligible_nets', lambda *args: {NET})
    return old, new, groups


def test_exact_dispatch_and_fixed_public_limits(tmp_path, monkeypatch):
    source, child, row = row_at(tmp_path)
    native_scope_doubles(monkeypatch, source, child)
    before = registration(); calls = []
    proof = dict(ok=True, complete=True, power_authority=False, release_authority=False)
    def receive(*args, **kwargs): calls.append((args, kwargs)); return proof
    monkeypatch.setattr(adapter.ordinary, 'receive', receive)
    with adapter.installed():
        assert adapter.base.validate_phases([row]) == [adapter.KIND]
        path, result = adapter.base.receive_phase(source, source, row, 'arbitrary-context')
        assert path == child and result is proof
        assert adapter.KIND not in adapter.base.KINDS
    assert registration() == before
    assert len(calls)==1 and calls[0][0]==(source,child)
    assert 0<calls[0][1].pop('timeout_s')<=10.
    assert calls[0][1]==dict(board_hint='arbitrary-context', retired_track_uuids=[TRACK],
        retired_via_uuids=[VIA], max_retired_tracks=32)


@pytest.mark.parametrize('key', ['width', 'diameter', 'drill', 'current', 'margin', 'points_nm',
    'layers', 'timeout_s', 'callback', 'validator', 'allow_locked_track_uuids',
    'allow_locked_via_uuids', 'allow_redundant_cut_only', 'options', 'proposal'])
def test_no_numerical_or_policy_injection(tmp_path, key):
    _, _, row = row_at(tmp_path); row[key] = 1
    with pytest.raises(ValueError): adapter.validate_row(row)


@pytest.mark.parametrize('key', sorted(adapter.FIELDS))
def test_every_exact_field_required(tmp_path, key):
    _, _, row = row_at(tmp_path); del row[key]
    with pytest.raises(ValueError): adapter.validate_row(row)


@pytest.mark.parametrize('fault', ['empty_tracks', 'duplicate_tracks', '33_tracks', 'empty_vias',
    'two_vias', 'overlap', 'tuple_ids', 'malformed_id', 'empty_net', 'boolean_net',
    'bad_hash', 'empty_path'])
def test_malformed_or_overbroad_identity_scope(tmp_path, fault):
    _, _, row = row_at(tmp_path)
    if fault == 'empty_tracks': row['retired_track_uuids'] = []
    elif fault == 'duplicate_tracks': row['retired_track_uuids'] *= 2
    elif fault == '33_tracks': row['retired_track_uuids'] = [f'{i:08x}-1111-4111-8111-111111111111' for i in range(33)]
    elif fault == 'empty_vias': row['retired_via_uuids'] = []
    elif fault == 'two_vias': row['retired_via_uuids'] += [NEW_VIA]
    elif fault == 'overlap': row['retired_via_uuids'] = [TRACK]
    elif fault == 'tuple_ids': row['retired_track_uuids'] = (TRACK,)
    elif fault == 'malformed_id': row['retired_track_uuids'] = ['not-a-uuid']
    elif fault == 'empty_net': row['net'] = ''
    elif fault == 'boolean_net': row['net'] = True
    elif fault == 'bad_hash': row['candidate_sha256'] = 'A'*64
    else: row['candidate'] = ''
    with pytest.raises(ValueError): adapter.validate_row(row)


@pytest.mark.parametrize('fault', ['locked_track', 'locked_via', 'grouped', 'masked_track',
    'wrong_old_net', 'wrong_new_net', 'missing_source_ID', 'extra_source_cut',
    'second_new_via', 'partial_new_via', 'unknown_role'])
def test_scope_refusal_precedes_public_dispatch(tmp_path, monkeypatch, fault):
    source, child, row = row_at(tmp_path)
    old, new, groups = native_scope_doubles(monkeypatch, source, child)
    if fault == 'locked_track': old[0].locked = True
    elif fault == 'locked_via': old[1].locked = True
    elif fault == 'grouped': groups.append(SimpleNamespace(GetItems=lambda: [old[0]]))
    elif fault == 'masked_track': old[0].masked = True
    elif fault == 'wrong_old_net': old[1].net = '/different'
    elif fault == 'wrong_new_net': new[0].net = '/different'
    elif fault == 'missing_source_ID': old.pop(0)
    elif fault == 'extra_source_cut': old.append(Item('55555555-5555-4555-8555-555555555555'))
    elif fault == 'second_new_via': new.append(Item('66666666-6666-4666-8666-666666666666', 'PCB_VIA'))
    elif fault == 'partial_new_via': new[1].bottom = 6
    else: monkeypatch.setattr(adapter.ordinary, 'eligible_nets', lambda *args: set())
    monkeypatch.setattr(adapter.ordinary, 'receive', lambda *args, **kwargs: pytest.fail('invalid scope dispatched'))
    previous = registration()
    with pytest.raises(ValueError):
        with adapter.installed(): adapter.base.receive_phase(source, source, row, 'context')
    assert registration() == previous


@pytest.mark.parametrize('alias', ['same_path', 'symlink', 'hardlink', 'changed_child'])
def test_same_or_unbound_saved_boundary_is_never_dispatched(tmp_path, monkeypatch, alias):
    source, child, row = row_at(tmp_path)
    if alias == 'same_path': row['candidate'] = str(source)
    elif alias == 'changed_child': child.write_bytes(b'changed')
    else:
        child.unlink()
        if alias == 'symlink': child.symlink_to(source)
        else: child.hardlink_to(source)
    if alias != 'changed_child': row['candidate_sha256'] = adapter.force._hash(source)
    monkeypatch.setattr(adapter, '_native_scope', lambda *args: pytest.fail('invalid saved boundary inspected'))
    with pytest.raises(ValueError): adapter.receive_phase(source, source, row, 'context')


@pytest.mark.parametrize('proof', [{}, {'ok': False, 'complete': True}, {'ok': True, 'complete': False},
    {'ok': 1, 'complete': True}, {'ok': True, 'complete': 1}])
def test_public_unknown_or_refusal_cannot_be_relabelled(tmp_path, monkeypatch, proof):
    source, child, row = row_at(tmp_path)
    native_scope_doubles(monkeypatch, source, child)
    monkeypatch.setattr(adapter.ordinary, 'receive', lambda *args, **kwargs: proof)
    previous = registration()
    with pytest.raises(ValueError, match='public_ordinary_barrel_chain_saved_receiver_refused'):
        with adapter.installed(): adapter.base.receive_phase(source, source, row, 'context')
    assert registration() == previous


def test_composed_dispatcher_and_exception_are_restored(tmp_path, monkeypatch):
    source, child, row = row_at(tmp_path)
    native_scope_doubles(monkeypatch, source, child)
    composed = lambda *args, **kwargs: ('original-composed', args, kwargs)
    monkeypatch.setattr(adapter.base, 'receive_phase', composed)
    monkeypatch.setattr(adapter.ordinary, 'receive', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('sentinel')))
    previous = registration()
    with pytest.raises(RuntimeError, match='sentinel'):
        with adapter.installed():
            assert adapter.base.receive_phase(source, source, {'kind': 'unrelated'}, 'context')[0] == 'original-composed'
            adapter.base.receive_phase(source, source, row, 'context')
    assert registration() == previous


def test_actual_dependency_hashes_include_self_and_public_receiver():
    before = registration()
    with adapter.installed():
        dependencies = adapter.base.annotation_dependencies()
        for module in (adapter, adapter.base, adapter.ordinary, adapter.additive):
            path = Path(module.__file__).resolve()
            assert dependencies[str(path)] == adapter.force._hash(path)
    assert registration() == before


def test_duplicate_net_and_original_phase_cap_unchanged(tmp_path):
    _, _, row = row_at(tmp_path); before = registration()
    with adapter.installed():
        peer = dict(kind='ordinary_join', candidate=row['candidate'], candidate_sha256=row['candidate_sha256'], net=NET)
        with pytest.raises(ValueError): adapter.base.validate_phases([row, peer])
        with pytest.raises(ValueError): adapter.base.validate_phases([copy.deepcopy(row)]*(adapter.base.MAX_LOCAL_PHASES+1))
    assert registration() == before


@pytest.mark.parametrize('track_locked',[False,True])
@pytest.mark.parametrize('via_locked',[False,True])
@pytest.mark.parametrize('accepted',[False,True])
def test_distinct_Source_owned_kind_derives_only_actual_requested_locks(
        tmp_path,monkeypatch,track_locked,via_locked,accepted):
    source,child,row=row_at(tmp_path);row['kind']=adapter.SOURCE_OWNED_KIND
    old,new,groups=native_scope_doubles(monkeypatch,source,child)
    old[0].locked=track_locked;old[1].locked=via_locked
    # A retained locked object is never part of the delegated lock scope.
    retained=Item('55555555-5555-4555-8555-555555555555');retained.locked=True
    old.append(retained);new.append(retained)
    calls=[]
    def receive(*args,**kw):
        calls.append((args,kw))
        return dict(ok=accepted,complete=True,release_authority=False)
    monkeypatch.setattr(adapter.ordinary,'receive',receive)
    previous=registration()
    with adapter.installed():
        assert adapter.base.validate_phases([row])==[adapter.SOURCE_OWNED_KIND]
        if accepted:
            path,result=adapter.base.receive_phase(source,source,row,'opaque')
            assert path==child and result['ok']is True
            exact=result['dispatch_Source_lock_inventory']
            assert exact['exact_requested_Source_lock_inventory_derived']is True
            assert not exact['grouped_copper_permission']and not exact['unrelated_locked_copper_permission']
        else:
            with pytest.raises(ValueError,match='public_ordinary_barrel_chain_saved_receiver_refused'):
                adapter.base.receive_phase(source,source,row,'opaque')
    assert previous==registration()and len(calls)==1
    kwargs=calls[0][1]
    assert kwargs['allow_locked_track_uuids']==([TRACK]if track_locked else[])
    assert kwargs['allow_locked_via_uuids']==([VIA]if via_locked else[])
    assert 0<kwargs['timeout_s']<=10.


@pytest.mark.parametrize('fault',['grouped_track','grouped_via','parent_group','wrong_net',
    'extra_cut','caller_track_locks','caller_via_locks'])
def test_Source_owned_kind_never_expands_public_ownership_or_caller_permission(tmp_path,monkeypatch,fault):
    source,child,row=row_at(tmp_path);row['kind']=adapter.SOURCE_OWNED_KIND
    old,new,groups=native_scope_doubles(monkeypatch,source,child)
    old[0].locked=old[1].locked=True
    if fault=='grouped_track':groups.append(SimpleNamespace(GetItems=lambda:[old[0]]))
    elif fault=='grouped_via':groups.append(SimpleNamespace(GetItems=lambda:[old[1]]))
    elif fault=='parent_group':old[1].group=object()
    elif fault=='wrong_net':old[1].net='/unowned'
    elif fault=='extra_cut':old.append(Item('55555555-5555-4555-8555-555555555555'))
    else:row['allow_locked_track_uuids'if fault=='caller_track_locks'else'allow_locked_via_uuids']=[TRACK]
    monkeypatch.setattr(adapter.ordinary,'receive',lambda *a,**k:pytest.fail('unowned scope reached public receiver'))
    previous=registration()
    with pytest.raises(ValueError):
        with adapter.installed():adapter.base.receive_phase(source,source,row,'opaque')
    assert registration()==previous


def test_old_and_Source_owned_kinds_cannot_repeat_one_net_in_a_composed_transaction(tmp_path):
    _,_,row=row_at(tmp_path);new=dict(row,kind=adapter.SOURCE_OWNED_KIND)
    before=registration()
    with adapter.installed():
        with pytest.raises(ValueError):adapter.base.validate_phases([row,new])
    assert registration()==before


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_real_saved_Source_locked_barrel_chain_is_received_only_by_explicit_kind(tmp_path,rotation):
    # Unlike the dispatch doubles above, this exercises the unchanged public
    # ordinary receiver, actual saved shapes, ports and native partitions.
    from test_ordinary_barrel_reseat import fixture
    import cec_field_coupling as field
    source,child,via_uuid=fixture(tmp_path,rotation,'unrelated_'+str(rotation))
    parent,last=[adapter.pcbnew.LoadBoard(str(p))for p in(source,child)]
    child_ids={adapter.force._uid(t)for t in last.GetTracks()}
    cuts=[t for t in parent.GetTracks()if adapter.force._uid(t)not in child_ids]
    tracks=sorted(adapter.force._uid(t)for t in cuts if t.GetClass()=='PCB_TRACK')
    for item in cuts:item.SetLocked(True)
    field._save_field_snapshot(parent,source)
    row=dict(kind=adapter.KIND,candidate=str(child),candidate_sha256=adapter.force._hash(child),
        net=cuts[0].GetNetname(),retired_track_uuids=tracks,retired_via_uuids=[via_uuid])
    frozen=[p.read_bytes()for p in(source,child)];previous=registration()
    with adapter.installed():
        with pytest.raises(ValueError,match='only_exact_unlocked_ungrouped_same_net_Source_copper'):
            adapter.base.receive_phase(source,source,row,'synthetic')
        row['kind']=adapter.SOURCE_OWNED_KIND
        actual,result=adapter.base.receive_phase(source,source,row,'synthetic')
    assert actual==child and result['ok']is True and result['complete']is True,result
    scope=result['dispatch_Source_lock_inventory']
    assert scope['allow_locked_track_uuids']==tracks and scope['allow_locked_via_uuids']==[via_uuid]
    assert result['all_prior_native_terminal_partitions_preserved']is True
    assert not result['release_authority']and not result['power_authority']
    assert previous==registration()and frozen==[p.read_bytes()for p in(source,child)]

"""A removable source stub is not permission to cut loads or shrink power."""
import copy
import math

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_redundant_force_branch as branch
from test_collector_reconstruction import fixture as collector_fixture
from test_field_proposals import track
from cec_native_items import discard_items


def fixture(tmp_path, monkeypatch, angle=0, face='F.Cu'):
    board, net, foreign, pads, at, _, contract = collector_fixture(monkeypatch, angle, face)
    domain = dict(net=net.GetNetname(), amps=20., complete=True,
        source_refs=['RENAMED_BANK'], sink_refs=['RENAMED_SINK'], authority_refs=['RENAMED_BANK', 'RENAMED_SINK'])
    monkeypatch.setattr(topology, 'board_current_domains', lambda *args, **kwargs:{net.GetNetname():copy.deepcopy(domain)})
    def xy(point):
        return [v/1e6 for v in at(*point)]
    layer = board.GetLayerID(face)
    width = math.ceil(contract['required_by_layer_mm'][face]*1e6)/1e6
    body = track(board, net.GetNetname(), xy((20,40)), xy((60,40)), layer=layer, width=width)
    tail = track(board, net.GetNetname(), xy((45,40)), xy((45,50)), layer=layer, width=width)
    tail.SetLocked(True)
    source = tmp_path/'source.kicad_pcb'
    field._save_field_snapshot(board, source)
    board = pcbnew.LoadBoard(str(source))
    by_uid = {force._uid(item):item for item in board.GetTracks()}
    return source, board, by_uid[force._uid(body)], by_uid[force._uid(tail)], net.GetNetname()


def options(tail, net):
    uid = force._uid(tail)
    return dict(track_uuids=[uid], net=net, board_hint='arbitrary-force-test', allow_locked_track_uuids=[uid])


@pytest.mark.parametrize('angle', [0,90,180,270])
@pytest.mark.parametrize('face', ['F.Cu','B.Cu'])
def test_exact_saved_redundant_branch_preserves_copper_partitions_and_rated_connections(
        tmp_path, monkeypatch, angle, face):
    source, board, body, tail, net = fixture(tmp_path, monkeypatch, angle, face)
    raw = source.read_bytes()
    request = options(tail, net)
    packet = branch.plan(board, **request)
    assert packet['redundancy_proved'] is False
    branch.subtract(board, packet)
    child = force._copy_family(source, tmp_path/'candidate')
    additive._ground_refill(board)
    field._save_field_snapshot(board, child)
    proof = branch.receive(source, child, **request)
    assert proof['ok'] and proof['complete'], proof
    assert proof['all_surviving_native_partitions_preserved']
    assert proof['all_existing_trace_and_rated_authority_connections_preserved']
    assert not proof['current_qualified'] and not proof['plated_barrel_rating_qualified']
    assert not proof['release_authority'] and source.read_bytes() == raw


@pytest.mark.parametrize('violation', ['lock','group','wrong_net','duplicate','via'])
def test_unknown_lock_group_net_or_inventory_is_not_cut_authority(tmp_path, monkeypatch, violation):
    source, board, body, tail, net = fixture(tmp_path, monkeypatch)
    request = options(tail, net)
    if violation == 'lock':
        request['allow_locked_track_uuids'] = []
    elif violation == 'group':
        group = pcbnew.PCB_GROUP(board)
        board.Add(group)
        group.AddItem(tail)
    elif violation == 'wrong_net':
        request['net'] = '/ARBITRARY_FOREIGN'
    elif violation == 'duplicate':
        request['track_uuids'] *= 2
    else:
        via = pcbnew.PCB_VIA(board)
        via.SetNetCode(board.GetNetcodeFromNetname(net))
        via.SetPosition(pcbnew.VECTOR2I_MM(45,40))
        via.SetWidth(900000)
        via.SetDrill(500000)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
        request['track_uuids'] = [force._uid(via)]
        request['allow_locked_track_uuids'] = []
    old = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):
        branch.plan(board, **request)
    assert field._field_snapshot_inventory(board) == old


@pytest.mark.parametrize('change', ['stale','forged'])
def test_subtraction_cannot_replay_a_changed_source_or_forged_scope(tmp_path, monkeypatch, change):
    source, board, body, tail, net = fixture(tmp_path, monkeypatch)
    packet = branch.plan(board, **options(tail, net))
    if change == 'stale':
        track(board, '/ARBITRARY_FOREIGN', (70,70), (71,70))
    else:
        packet = copy.deepcopy(packet)
        packet['track_uuids'].append(force._uid(body))
    before = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):
        branch.subtract(board, packet)
    assert field._field_snapshot_inventory(board) == before


def test_saved_cut_of_the_only_real_load_path_is_refused(tmp_path, monkeypatch):
    source, board, body, tail, net = fixture(tmp_path, monkeypatch)
    request = dict(track_uuids=[force._uid(body)], net=net, board_hint='arbitrary-force-test')
    packet = branch.plan(board, **request)
    branch.subtract(board, packet)
    child = force._copy_family(source, tmp_path/'candidate')
    field._save_field_snapshot(board, child)
    proof = branch.receive(source, child, **request)
    assert not proof['ok'] and 'lost_surviving_native_partition' in ' '.join(proof['errors'])


def test_saved_redundant_cut_cannot_change_an_unowned_width(tmp_path, monkeypatch):
    source, board, body, tail, net = fixture(tmp_path, monkeypatch)
    request = options(tail, net)
    branch.subtract(board, branch.plan(board, **request))
    body.SetWidth(body.GetWidth()+10000)
    child = force._copy_family(source, tmp_path/'candidate')
    field._save_field_snapshot(board, child)
    proof = branch.receive(source, child, **request)
    assert not proof['ok']


@pytest.mark.parametrize('budget', [0,11,True,float('inf'),float('nan')])
def test_unbounded_or_nonnumeric_budget_refuses_before_mutation(tmp_path, monkeypatch, budget):
    source, board, body, tail, net = fixture(tmp_path, monkeypatch)
    before = field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):
        branch.plan(board, **options(tail, net), timeout_s=budget)
    assert field._field_snapshot_inventory(board) == before


def test_current_authority_is_required_not_inferred_from_a_net_name(tmp_path, monkeypatch):
    source, board, body, tail, net = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(topology, 'board_current_domains', lambda *args, **kwargs:{})
    with pytest.raises(ValueError, match='complete_source_owned_force_domain_required'):
        branch.plan(board, **options(tail, net))


def test_copper_only_tee_cannot_be_omitted_from_preservation():
    assert branch.preserved_partitions([{'pad','tee'}], [{'pad','tee','new'}])
    assert not branch.preserved_partitions([{'pad','tee'}], [{'pad'},{'tee'}])
    with pytest.raises(ValueError, match='ambiguous'):
        branch.preserved_partitions([{'pad'},{'pad'}], [{'pad'}])


@pytest.mark.parametrize('angle,face',[(0,'F.Cu'),(90,'B.Cu'),(180,'F.Cu'),(270,'B.Cu')])
def test_explicit_complete_segmented_cohort_scope_keeps_defaults_and_native_current_gates(tmp_path,monkeypatch,angle,face):
    source,board,body,tail,net=fixture(tmp_path,monkeypatch,angle,face)
    start,end=tuple(tail.GetStart()),tuple(tail.GetEnd());width=tail.GetWidth()/1e6
    discard_items(board,[tail]);selected=[]
    for k in range(20):
        s=[(start[j]+(end[j]-start[j])*k/20)/1e6 for j in range(2)]
        e=[(start[j]+(end[j]-start[j])*(k+1)/20)/1e6 for j in range(2)]
        t=track(board,net,s,e,layer=board.GetLayerID(face),width=width);t.SetLocked(True)
        selected.append(force._uid(t))
    field._save_field_snapshot(board,source);raw=source.read_bytes()
    request=dict(track_uuids=selected,net=net,board_hint='arbitrary-force-test',allow_locked_track_uuids=selected)
    with pytest.raises(ValueError,match='bounded_exact_force_branch_inventory'):
        branch.plan(board,**request)
    request['max_retired_tracks']=32
    packet=branch.plan(board,**request);branch.subtract(board,packet)
    child=force._copy_family(source,tmp_path/'cohort-candidate');field._save_field_snapshot(board,child)
    proof=branch.receive(source,child,**request)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_surviving_native_partitions_preserved'] and not proof['current_qualified']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('count',[True,0,-1,33,16.5,None,'32'])
def test_force_cohort_scope_remains_finite_and_explicit(tmp_path,monkeypatch,count):
    source,board,body,tail,net=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='bounded_explicit_force_branch_count'):
        branch.plan(board,**options(tail,net),max_retired_tracks=count)

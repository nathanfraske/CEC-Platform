"""Cross-layer construction reuses a proved source leaf, never a guessed budget."""
from unittest import mock
import pcbnew
import pytest

import cec_supply_consumer_branch as consumer
import cec_rated_branch_repair as rated
import cec_rated_branch_layer_chain as worker
import cec_force_current as force
import cec_field_coupling as field
import cec_current_topology as topology
from test_supply_consumer_branch import fixture
from test_pass_through_supply_branch import fixture as passthrough_fixture


def case(monkeypatch, tmp_path, angle=0, mirror=False):
    b, root, _, _, old, trunk, _, _, rail, declaration, _ = fixture(
        monkeypatch, tmp_path, angle=angle, mirror=mirror)
    old.SetWidth(250000)
    points = [tuple(old.GetStart()), tuple(old.GetEnd())]
    for at in points:
        via = pcbnew.PCB_VIA(b); via.SetPosition(pcbnew.VECTOR2I(*at))
        via.SetNet(root.GetNet()); via.SetWidth(600000); via.SetDrill(300000)
        via.SetViaType(pcbnew.VIATYPE_THROUGH); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        b.Add(via)
    source = tmp_path/'source.kicad_pcb'
    loaded = field._save_field_snapshot(b, source)
    field._save_field_snapshot(loaded, source)
    net = str(root.GetNetname()); budget = consumer.contract(b, force._uid(root), board_hint='synthetic')
    raw = dict(net=net, current_authority=rail, profile='jlcpcb_6l_pofv_signal',
        required_by_layer_mm={k:max(.2, v) for k,v in budget['aggregate_required_by_layer_mm'].items()},
        routing_layers=['F.Cu', 'In2.Cu', 'B.Cu'], clearance_mm=.2)
    other = pcbnew.B_Cu if old.GetLayer() == pcbnew.F_Cu else pcbnew.F_Cu
    stages = [dict(layer=pcbnew.LayerName(other), points_nm=[list(p) for p in points])]
    return source, force._uid(old), net, {'contracts':{net:raw}}, stages, declaration, force._uid(trunk)


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
def test_source_proved_leaf_constructs_and_independently_replays_on_other_face(monkeypatch, tmp_path, angle, mirror):
    source, uid, net, catalog, stages, _, _ = case(monkeypatch, tmp_path, angle, mirror)
    saved = source.read_bytes()
    with mock.patch.object(rated.topology, 'distributed_supply_contracts', return_value=catalog):
        with pytest.raises(ValueError):
            worker.construct(source, board_hint='synthetic', retired_track_uuids=[uid], stages=stages)
        board, proposal = worker.construct(source, board_hint='synthetic', retired_track_uuids=[uid],
            stages=stages, use_source_declared_consumer_island=True)
        candidate = force._copy_family(source, tmp_path/'candidate')
        field._save_field_snapshot(board, candidate)
        proof = rated.receive(source, candidate, board_hint='synthetic', retired_track_uuids=[uid],
            allow_rated_layer_bridges=True, use_source_declared_consumer_island=True)
    assert proof['ok'] and proof['complete'], proof
    scope = proposal['source_plan']['source_declared_consumer_scope']
    assert scope['aggregate_contracts'][net]['current_authority']['amps'] == 3.
    assert proposal['source_plan']['contracts'][net]['current_authority']['amps'] == .5
    assert all(row['width_nm'] == 250000 for row in proposal['full_width_native_legs'])
    assert not proposal['new_via_uuids']  # Actual through-barrels already provide both faces.
    assert not proposal['source_current_reduced'] and not proposal['branch_sharing_inferred']
    assert not proposal['routing_admitted'] and not proof['release_authority']
    assert source.read_bytes() == saved


@pytest.mark.parametrize('fault', ['missing_policy', 'unknown_load', 'shared_trunk', 'group', 'boolean'])
def test_flag_cannot_create_source_ownership_or_change_allocation(monkeypatch, tmp_path, fault):
    source, uid, _, catalog, stages, declaration, trunk = case(monkeypatch, tmp_path)
    options = dict(use_source_declared_consumer_island=True)
    if fault == 'missing_policy': declaration['params']['supply_consumer_allocations'] = []
    elif fault == 'boolean': options['use_source_declared_consumer_island'] = 1
    elif fault == 'shared_trunk': uid = trunk
    else:
        board = pcbnew.LoadBoard(str(source))
        if fault == 'group':
            group = pcbnew.PCB_GROUP(board); group.SetName('unrelated owner'); board.Add(group)
            group.AddItem(next(t for t in board.GetTracks() if force._uid(t) == uid))
        else:
            owner = next(fp for fp in board.GetFootprints() if fp.GetReference() == 'NOT_A_U')
            owner.SetField('MPN', 'unqualified part')
        field._save_field_snapshot(board, source)
    saved = source.read_bytes()
    with mock.patch.object(rated.topology, 'distributed_supply_contracts', return_value=catalog):
        with pytest.raises(ValueError):
            worker.construct(source, board_hint='synthetic', retired_track_uuids=[uid], stages=stages, **options)
    assert source.read_bytes() == saved


def aggregate_case(monkeypatch,tmp_path,angle=0,mirror=False):
    board,root,anchor,_,_,tracks,_,group,_,domain,_=passthrough_fixture(monkeypatch,tmp_path,angle,mirror)
    old=tracks[0];group.RemoveItem(old)
    points=[tuple(old.GetStart()),tuple(old.GetEnd())]
    for at in points:
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*at));via.SetNet(root.GetNet())
        via.SetWidth(800000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    source=tmp_path/'aggregate.kicad_pcb'
    loaded=field._save_field_snapshot(board,source);field._save_field_snapshot(loaded,source)
    budget=consumer.contract(board,force._uid(root),board_hint='synthetic')
    net=str(root.GetNetname())
    raw=dict(net=net,current_authority=budget['aggregate_current_authority'],
        profile=budget['copper_profile'],required_by_layer_mm=budget['aggregate_required_by_layer_mm'],
        routing_layers=['F.Cu','In2.Cu','B.Cu'],clearance_mm=.2,authority_refs=tuple(domain['authority_refs']))
    stages=[dict(layer=pcbnew.LayerName(pcbnew.B_Cu if old.GetLayer()==pcbnew.F_Cu else pcbnew.F_Cu),
        points_nm=[list(at) for at in points])]
    return source,force._uid(old),net,raw,stages,domain


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
@pytest.mark.parametrize('mirror', [False, True])
def test_declared_leaf_on_native_aggregate_rail_is_not_a_distributed_supply(monkeypatch, tmp_path, angle, mirror):
    source,uid,net,raw,stages,_=aggregate_case(monkeypatch,tmp_path,angle,mirror)
    monkeypatch.setattr(topology, 'route_width_contracts', lambda *a, **k:{net:raw})
    with mock.patch.object(rated.topology, 'distributed_supply_contracts', return_value={'contracts':{}}):
        board, proposal = worker.construct(source, board_hint='synthetic', retired_track_uuids=[uid],
            stages=stages, use_source_declared_consumer_island=True,
            max_source_width_mm=.5,max_replacement_width_mm=.5)
        candidate = force._copy_family(source, tmp_path/'native-aggregate-child')
        field._save_field_snapshot(board, candidate)
        result = rated.receive(source, candidate, board_hint='synthetic', retired_track_uuids=[uid],
            allow_rated_layer_bridges=True, use_source_declared_consumer_island=True,
            max_source_width_mm=.5,max_replacement_width_mm=.5)
    assert result['ok'] and result['complete'], result
    assert proposal['source_plan']['source_declared_consumer_scope']['source_native_aggregate_domain_nets'] == [net]
    assert proposal['source_plan']['contracts'][net]['current_authority']['amps'] == 3.0004
    assert not result['current_authority'] and not result['release_authority']


@pytest.mark.parametrize('fault', ['missing', 'incomplete', 'refs', 'authority', 'profile'])
def test_missing_distributed_catalog_is_not_permission_to_invent_aggregate_contract(monkeypatch, tmp_path, fault):
    source,uid,net,raw,stages,domain=aggregate_case(monkeypatch,tmp_path)
    if fault == 'incomplete': domain['complete'] = False
    elif fault == 'refs': raw['authority_refs'] = ('fabricated authority',)
    elif fault == 'authority': raw['current_authority'] = dict(raw['current_authority'], amps=2.)
    elif fault == 'profile': raw['profile'] = 'unrelated process'
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a, **k:{net:domain})
    monkeypatch.setattr(topology, 'route_width_contracts', lambda *a, **k:{} if fault=='missing' else {net:raw})
    with mock.patch.object(rated.topology, 'distributed_supply_contracts', return_value={'contracts':{}}):
        with pytest.raises(ValueError):
            worker.construct(source, board_hint='synthetic', retired_track_uuids=[uid],
                stages=stages, use_source_declared_consumer_island=True,
                max_source_width_mm=.5,max_replacement_width_mm=.5)

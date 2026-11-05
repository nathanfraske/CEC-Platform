"""A proved inner consumer span can change faces without acquiring a trunk."""
from unittest import mock
import pcbnew
import pytest
import cec_rated_branch_layer_chain as worker
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
from test_consumer_layer_chain_construction import case


def inner_case(monkeypatch,tmp_path,angle=0,mirror=False):
    source,uid,net,catalog,stages,declaration,trunk=case(monkeypatch,tmp_path,angle,mirror)
    board=pcbnew.LoadBoard(str(source))
    edge=next(t for t in board.GetTracks() if force._uid(t)==uid)
    edge.SetLayer(pcbnew.In2_Cu);edge.SetWidth(500000)
    # The strict rated receiver needs the complete displaced width across
    # each retained annular web, not just nominal through-via connectivity.
    for via in board.GetTracks():
        if via.GetClass()=='PCB_VIA':via.SetWidth(800000)
    field._save_field_snapshot(board,source)
    stages=[dict(layer='B.Cu',points_nm=stages[0]['points_nm'])]
    return source,uid,net,catalog,stages,declaration,trunk


OPTIONS=dict(max_source_width_mm=1.,max_replacement_width_mm=1.,
    use_source_declared_consumer_island=True,allow_rated_source_inner_layers=True)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_proved_inner_leaf_reconstructs_and_replays_at_full_width(monkeypatch,tmp_path,angle,mirror):
    source,uid,net,catalog,stages,_,_=inner_case(monkeypatch,tmp_path,angle,mirror)
    frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
                stages=stages,**dict(OPTIONS,allow_rated_source_inner_layers=False))
        board,proposal=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,**OPTIONS)
        candidate=force._copy_family(source,tmp_path/'child')
        field._save_field_snapshot(board,candidate)
        received=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,**OPTIONS)
    assert received['ok'] and received['complete'],received
    assert proposal['rated_inner_source_scope_explicit']
    assert proposal['source_plan']['source_declared_consumer_scope']['source_native_island_reproved']
    assert proposal['source_plan']['contracts'][net]['current_authority']['amps']==.5
    assert proposal['source_plan']['source_declared_consumer_scope']['aggregate_contracts'][net]['current_authority']['amps']==3.
    assert all(row['width_nm']==500000 for row in proposal['full_width_native_legs'])
    assert not proposal['new_via_uuids']
    assert not proposal['source_current_reduced'] and not proposal['routing_admitted']
    assert source.read_bytes()==frozen


def test_narrow_inherited_barrel_does_not_qualify_a_cross_layer_bridge(monkeypatch,tmp_path):
    source,uid,_,catalog,stages,_,_=inner_case(monkeypatch,tmp_path)
    board=pcbnew.LoadBoard(str(source))
    for via in board.GetTracks():
        if via.GetClass()=='PCB_VIA':via.SetWidth(600000)
    field._save_field_snapshot(board,source);frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        private,_=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,**OPTIONS)
        candidate=force._copy_family(source,tmp_path/'insufficient-web')
        field._save_field_snapshot(private,candidate)
        received=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,**OPTIONS)
    assert not received['ok'] and not received['complete']
    assert any('retired_endpoint_has_no_saved_conductor' in error for error in received['errors'])
    assert source.read_bytes()==frozen


@pytest.mark.parametrize('fault',['boolean','unproved','missing_policy','shared_trunk','group',
    'undersized_inner','ground_plane_source','ground_plane_target','undeclared_target'])
def test_inner_scope_is_not_a_width_ownership_or_layer_waiver(monkeypatch,tmp_path,fault):
    source,uid,net,catalog,stages,declaration,trunk=inner_case(monkeypatch,tmp_path)
    options=dict(OPTIONS)
    if fault=='boolean':options['allow_rated_source_inner_layers']=1
    elif fault=='unproved':options['use_source_declared_consumer_island']=False
    elif fault=='missing_policy':declaration['params']['supply_consumer_allocations']=[]
    elif fault=='shared_trunk':uid=trunk
    elif fault in ('ground_plane_target','undeclared_target'):
        stages[0]['layer']='In1.Cu' if fault=='ground_plane_target' else 'unapproved-face'
    else:
        board=pcbnew.LoadBoard(str(source));edge=next(t for t in board.GetTracks() if force._uid(t)==uid)
        if fault=='group':
            group=pcbnew.PCB_GROUP(board);group.SetName('unrelated owner');board.Add(group);group.AddItem(edge)
        elif fault=='undersized_inner':edge.SetWidth(200000)
        else:edge.SetLayer(pcbnew.In1_Cu)
        field._save_field_snapshot(board,source)
    frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,**options)
    assert source.read_bytes()==frozen

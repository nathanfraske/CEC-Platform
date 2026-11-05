"""The inner-source path also works with two actual full-web layer changes."""
from unittest import mock
import math
import pcbnew
import pytest
import cec_rated_branch_layer_chain as worker
import cec_rated_branch_repair as rated
import cec_force_current as force
import cec_field_coupling as field
from test_consumer_inner_layer_chain_construction import inner_case, OPTIONS


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_two_new_full_web_barrels_replay_complete_inner_source_current(monkeypatch,tmp_path,angle,mirror):
    source,uid,net,catalog,rows,_,_=inner_case(monkeypatch,tmp_path,angle,mirror)
    start,end=rows[0]['points_nm'];dx=end[0]-start[0];dy=end[1]-start[1]
    norm=math.hypot(dx,dy);offset=[round(6000000*dy/norm),round(-6000000*dx/norm)]
    first=[start[i]+offset[i] for i in (0,1)];last=[end[i]+offset[i] for i in (0,1)]
    stages=[dict(layer='In2.Cu',points_nm=[start,first]),dict(layer='B.Cu',points_nm=[first,last]),
        dict(layer='In2.Cu',points_nm=[last,end])]
    frozen=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        board,proposal=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,**OPTIONS)
        candidate=force._copy_family(source,tmp_path/'two-real-layer-changes')
        field._save_field_snapshot(board,candidate)
        received=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,**OPTIONS)
    assert received['ok'] and received['complete'],received
    assert len(proposal['new_via_uuids'])==2 and proposal['derived_new_barrel_sites_nm']==[first,last]
    assert proposal['source_plan']['contracts'][net]['current_authority']['amps']==.5
    assert len(received['independent_saved_consumer_scope']['proofs'])==1
    assert all(row['width_nm']==500000 for row in proposal['full_width_native_legs'])
    vias=[v for v in board.GetTracks() if force._uid(v) in proposal['new_via_uuids']]
    assert all(v.GetWidth(v.TopLayer())-v.GetDrillValue()>=500000 for v in vias)
    assert not proposal['new_barrel_ampacity_credited'] and not received['release_authority']
    assert source.read_bytes()==frozen

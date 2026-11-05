"""A saved stationary Ground hole is not a newly requested power-pour hole."""
import time
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_cell_macro_requests as compiler
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_native_frozen_zone_access as frozen
import cec_retained_ground_barrel_clearance as retained
import cec_stationary_ground_barrel as stationary
from test_retained_ground_barrel_clearance import fixture as source_fixture
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False):
    board,source,via,point=source_fixture(tmp_path,quarter,mirror)
    profile=fab.get_profile(fab.board_profile_name(board))
    for name,role in zip(fab.COPPER_LAYERS,profile['roles']):
        if role!='GND':continue
        zone=pcbnew.ZONE(board);zone.SetLayer(board.GetLayerID(name));zone.SetNet(board.FindNet('GND'))
        zone.SetZoneName('ordinary reference');zone.SetLocalClearance(200000);zone.SetMinThickness(100000)
        zone.Outline().NewOutline()
        for at in ((1,1),(29,1),(29,29),(1,29)):zone.Outline().Append(point(*at))
        board.Add(zone)
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    board=pcbnew.LoadBoard(str(source));via=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    proof=stationary.plan(board,[force._uid(via)],source_path=source,board_hint='opaque')[0]
    other=pcbnew.PCB_VIA(board);other.SetNet(board.FindNet('/RENAMED_POWER'));other.SetPosition(point(24,24))
    other.SetWidth(600000);other.SetDrill(300000);other.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(other)
    additive._ground_refill(board)
    assert frozen._zones(board)!=frozen._zones(pcbnew.LoadBoard(str(source)))
    return board,source,via,proof,point


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_stationary_source_antipad_survives_only_ordinary_ground_refill(tmp_path,quarter,mirror):
    board,source,via,proof,_=fixture(tmp_path,quarter,mirror);raw=source.read_bytes()
    before=field._field_snapshot_inventory(board)
    assert not retained.clear(board,via,200000,deadline=time.monotonic()+10.)
    result=stationary.clearance(board,proof)
    assert result['ok'] and result['source_antipad_not_new_hole_authority']
    packet=dict(scope='source_typed_complete_native_macro_requests',transport=dict(
        source_process_barrel_motion=[],explicit_source_typed_ordinary_barrel_motion=[],
        explicitly_reproved_private_signal_port_reseats=[],explicitly_reproved_private_signal_return_reseats=[],
        explicit_stationary_source_ground_barrels=[proof]))
    screen=compiler.pre_refill_barrel_screen(board,packet)
    assert screen['ok'] and screen['all_carried_barrels_examined']==1
    assert field._field_snapshot_inventory(board)==before and source.read_bytes()==raw
    assert frozen.cache_token(board) is None


@pytest.mark.parametrize('fault',['foreign_fill','foreign_outline','ground_outline','ground_priority',
    'ground_thickness','ground_reserved','moved_root','new_root_identity','changed_profile'])
def test_refill_mode_cannot_hide_changed_authorship_foreign_fill_or_barrel(tmp_path,fault):
    board,source,via,proof,_=fixture(tmp_path)
    ground=next(z for z in board.Zones() if z.GetNetname()=='GND')
    foreign=next(z for z in board.Zones() if z.GetNetname()!='GND')
    if fault=='foreign_fill':foreign.UnFill()
    elif fault=='foreign_outline':foreign.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='ground_outline':ground.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='ground_priority':ground.SetAssignedPriority(ground.GetAssignedPriority()+1)
    elif fault=='ground_thickness':ground.SetMinThickness(ground.GetMinThickness()+1)
    elif fault=='ground_reserved':ground.SetZoneName('CEC_RECTILINEAR_POWER_CONTOUR')
    elif fault=='moved_root':
        key=force._item_key(via);via.Move(pcbnew.VECTOR2I(1,0))
        assert force._item_key(via)==key  # Identity alone does not prove a stationary seat.
    elif fault=='new_root_identity':via.m_Uuid.Clone(pcbnew.KIID())
    else:
        props=board.GetProperties();props['CEC_FAB_PROFILE']='';board.SetProperties(props)
    before=field._field_snapshot_inventory(board);raw=source.read_bytes()
    assert not stationary.clearance(board,proof)['ok']
    assert field._field_snapshot_inventory(board)==before and source.read_bytes()==raw
    assert frozen.cache_token(board) is None


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu,pcbnew.B_Cu])
def test_saved_antipad_never_exempts_live_foreign_tracks_on_any_face(tmp_path,layer):
    board,source,via,proof,_=fixture(tmp_path)
    x,y=[v/1e6 for v in via.GetPosition()]
    track(board,'/RENAMED_POWER',(x-.5,y),(x+.5,y),width=.2,layer=layer)
    before=field._field_snapshot_inventory(board);raw=source.read_bytes()
    assert not stationary.clearance(board,proof)['ok']
    assert field._field_snapshot_inventory(board)==before and source.read_bytes()==raw


def test_saved_candidate_must_use_original_source_not_its_own_new_fill_epoch(tmp_path):
    board,source,via,proof,_=fixture(tmp_path)
    foreign=next(z for z in board.Zones() if z.GetNetname()!='GND')
    foreign.SetLocalClearance(foreign.GetLocalClearance()+1)
    candidate=tmp_path/'candidate.kicad_pcb';field._save_field_snapshot(board,candidate)
    child=pcbnew.LoadBoard(str(candidate))
    assert not stationary.clearance(child,proof)['ok']


@pytest.mark.parametrize('flag',[None,1,'true',[],{}])
def test_ground_refill_permission_is_explicitly_boolean(tmp_path,flag):
    board,source,via,proof,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_frozen'):
        with frozen.frozen(board,source,allow_unreserved_ground_refill=flag):pass

"""A changed rail never earns divided current or an unknown Kelvin waiver."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_force_crossface_receiving as receiver
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,turn=0,net='/arbitrary/RAIL'):
    b=_board([(10,10,net),(20,10,net)],edge=(0,0,30,30))
    old=track(b,net,(10,10),(20,10),width=.6)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),b)
    child=pcbnew.LoadBoard(str(path));cut=force._uid(old)
    child.Remove(next(t for t in child.GetTracks() if force._uid(t)==cut))
    new=track(child,net,(10,10),(20,10),width=.6,layer=pcbnew.B_Cu)
    for board in (b,child):
        for item in [*board.GetTracks(),*board.GetFootprints()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    return b,child,cut,new


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('net',['/renamed/LOAD','/other/POWER'])
def test_native_scope_has_no_board_reference_coordinate_or_orientation_policy(tmp_path,turn,net):
    b,child,cut,new=fixture(tmp_path,turn,net)
    prior=[(force._uid(t),tuple(t.GetStart())) for t in b.GetTracks()]
    result=receiver.native_scope(b,child,[cut])
    assert result[0]==net and [force._uid(t) for t in result[1]]==[cut]
    assert [force._uid(t) for t in result[2]]==[force._uid(new)]
    assert [(force._uid(t),tuple(t.GetStart())) for t in b.GetTracks()]==prior


@pytest.mark.parametrize('bad',['duplicate','missing','stale','other_net','grouped','no_additions','extra_retirement'])
def test_unclear_owned_scope_fails_before_it_can_rebind_cuts(tmp_path,bad):
    b,child,cut,new=fixture(tmp_path)
    request=[cut]
    if bad=='duplicate':request=[cut,cut]
    elif bad=='missing':request=[]
    elif bad=='stale':request=['not_a_native_uuid']
    elif bad=='other_net':new.SetNetCode(0)
    elif bad=='grouped':
        group=pcbnew.PCB_GROUP(b);b.Add(group)
        group.AddItem(next(t for t in b.GetTracks() if force._uid(t)==cut))
    elif bad=='no_additions':child.Remove(new)
    else:track(b,'/arbitrary/RAIL',(11,11),(12,11),width=.6)
    with pytest.raises(ValueError):receiver.native_scope(b,child,request)


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('source_nm,floor,good_width',[(600000,.477369279,600000),(200000,.477369279,477370)])
def test_full_budget_is_not_replaced_by_authored_width_or_divided_across_faces(tmp_path,layer,source_nm,floor,good_width):
    b,child,cut,new=fixture(tmp_path);new.SetLayer(layer);new.SetWidth(good_width)
    contract=dict(net=str(new.GetNetname()),routing_layers=['F.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':floor,'B.Cu':floor})
    prior=copy.deepcopy(contract)
    assert receiver.require_track_floor(b,new,contract,source_nm)==good_width
    new.SetWidth(good_width-1)
    with pytest.raises(ValueError):receiver.require_track_floor(b,new,contract,source_nm)
    assert contract==prior


@pytest.mark.parametrize('bad',['bool','nan','missing','negative','unauthorized','net','source_bool','source_zero'])
def test_invalid_full_width_contract_never_grants_capacity(tmp_path,bad):
    b,child,cut,new=fixture(tmp_path)
    contract=dict(net=str(new.GetNetname()),routing_layers=['F.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':.477,'B.Cu':.477})
    source=600000
    if bad=='bool':contract['required_by_layer_mm']['B.Cu']=True
    elif bad=='nan':contract['required_by_layer_mm']['B.Cu']=float('nan')
    elif bad=='missing':contract['required_by_layer_mm'].pop('B.Cu')
    elif bad=='negative':contract['required_by_layer_mm']['B.Cu']=-1
    elif bad=='unauthorized':contract['routing_layers']=['F.Cu']
    elif bad=='net':contract['net']='WRONG'
    elif bad=='source_bool':source=True
    else:source=0
    with pytest.raises(ValueError):receiver.require_track_floor(b,new,contract,source)


def test_actual_vias_are_track_count_subset_not_an_invented_separate_inventory(tmp_path):
    b,child,cut,new=fixture(tmp_path)
    via=pcbnew.PCB_VIA(child);via.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    via.SetWidth(900000);via.SetDrill(300000);via.SetNetCode(new.GetNetCode())
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);child.Add(via)
    manifest=receiver.count_manifest(str(new.GetNetname()),[cut],[new,via])[0]
    assert set(manifest['added_track_uuids'])=={force._uid(new),force._uid(via)}
    assert manifest['added_via_uuids']==[force._uid(via)]
    assert set(manifest['added_via_uuids'])<=set(manifest['added_track_uuids'])


def test_caller_contract_cannot_make_an_unfilled_factory_reference_plane_routable(tmp_path):
    b,child,cut,new=fixture(tmp_path);new.SetLayer(pcbnew.In1_Cu)
    contract=dict(net=str(new.GetNetname()),routing_layers=['In1.Cu'],required_by_layer_mm={'In1.Cu':.477})
    with pytest.raises(ValueError,match='complete_source_and_authored_force_width'):
        receiver.require_track_floor(b,new,contract,600000)


@pytest.mark.parametrize('turn',[0,90,180,270])
def test_explicit_larger_source_geometry_keeps_default_and_same_exact_scope(tmp_path,turn):
    b,child,cut,new=fixture(tmp_path,turn)
    source=next(t for t in b.GetTracks() if force._uid(t)==cut)
    source.SetEnd(source.GetStart()+pcbnew.VECTOR2I_MM(40,0))
    with pytest.raises(ValueError,match='geometry_work_bound'):
        receiver.native_scope(b,child,[cut])
    net,removed,added,_=receiver.native_scope(b,child,[cut],max_source_leg_mm=64.)
    assert net==str(new.GetNetname()) and [force._uid(t) for t in removed]==[cut]
    assert [force._uid(t) for t in added]==[force._uid(new)]
    # The new geometry bound never substitutes for full-current width proof.
    contract=dict(net=net,routing_layers=['B.Cu'],required_by_layer_mm={'B.Cu':.8})
    with pytest.raises(ValueError,match='complete_source_and_authored_force_width'):
        receiver.require_track_floor(b,new,contract,source.GetWidth())


@pytest.mark.parametrize('bound',[True,False,None,'64',float('nan'),float('inf'),0,-1,128.000001])
def test_invalid_explicit_source_geometry_bound_is_not_a_waiver(tmp_path,bound):
    b,child,cut,_=fixture(tmp_path)
    with pytest.raises(ValueError,match='bounded_explicit_source_leg'):
        receiver.native_scope(b,child,[cut],max_source_leg_mm=bound)


@pytest.mark.parametrize('value',[True,False,None,'60',float('nan'),float('inf'),0,-1,60.000001])
def test_incomplete_proof_cannot_be_accepted_by_invalid_work_budget(value):
    with pytest.raises(ValueError,match='bounded_absolute_force_evidence_budget'):
        receiver.evidence_replay_budget(value)


@pytest.mark.parametrize('value',[.01,10,60])
def test_explicit_proof_budget_is_bounded_without_qualifying_any_evidence(value):
    assert receiver.evidence_replay_budget(value)==float(value)

"""Cooperative local repairs retain explicit full-load, not invented, widths."""
import math
from pathlib import Path
from unittest import mock

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_repair as branch
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,rotation=0,prefix='/a/'):
    net=prefix+'SUPPLY';scalar=prefix+'CONTROL'
    def rotate(at):
        a=math.radians(rotation);x,y=at[0]-15,at[1]-15
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    b=_board([(*rotate(p),n) for p,n in (((5,10),net),((10,10),net),((20,20),scalar),((22,20),scalar))],edge=(0,0,30,30))
    for fp in b.GetFootprints():next(iter(fp.Pads())).SetNumber('1')
    old=track(b,net,rotate((5,10)),rotate((10,10)))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'trial');b=pcbnew.LoadBoard(str(child))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==force._uid(old)])
    for a,z in (((5,10),(5.5,10.5)),((5.5,10.5),(9.5,10.5)),((9.5,10.5),(10,10))):track(b,net,rotate(a),rotate(z))
    track(b,scalar,rotate((20,20)),rotate((22,20)))
    field._save_field_snapshot(b,child)
    final=Path(additive.finalize_private(source,child,tmp_path/'final')['board'])
    # Deliberate synthetic authority: this is a test catalog, not an inferred
    # design load. The real receiver must obtain exactly this kind of explicit
    # existing authority from the immutable source's distributed-load catalog.
    catalog=dict(contracts={net:dict(required_by_layer_mm={'F.Cu':.2,'B.Cu':.2},design_current_A=.1)})
    return source,final,force._uid(old),net,scalar,catalog


@pytest.mark.parametrize('rotation,prefix',[(0,'/a/'),(90,'/renamed/'),(180,'/x/'),(270,'/z/')])
def test_rotated_renamed_full_load_branch_restores_every_source_boundary(tmp_path,rotation,prefix):
    source,child,uid,net,scalar,catalog=fixture(tmp_path,rotation,prefix);before=source.read_bytes()
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog):
        result=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    assert result['ok'] and result['complete'],result
    assert result['all_surviving_native_partitions_preserved']
    assert result['source_proposal']['inferred_branch_load'] is False
    assert not result['current_authority'] and not result['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['narrow','open','extra_power','scalar_via_minimum','scalar_track_minimum','contract_absent','contract_changes','group','budget'])
def test_wrong_electrical_authority_or_incomplete_reconstruction_is_refused(tmp_path,fault):
    source,child,uid,net,scalar,catalog=fixture(tmp_path);b=pcbnew.LoadBoard(str(child))
    if fault=='narrow':next(t for t in b.GetTracks() if t.GetNetname()==net).SetWidth(150000)
    elif fault=='open':next(t for t in b.GetTracks() if t.GetNetname()==net).Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='extra_power':
        # An extra rated branch for another rail is not scalar authority.
        b.Add(pcbnew.NETINFO_ITEM(b,'ZZ_POWER'));track(b,'ZZ_POWER',(25,25),(26,25))
        next(t for t in b.GetTracks() if t.GetNetname()=='ZZ_POWER').SetWidth(1000000)
    elif fault=='scalar_track_minimum':next(t for t in b.GetTracks() if t.GetNetname()==scalar).SetWidth(100000)
    elif fault=='scalar_via_minimum':
        v=pcbnew.PCB_VIA(b);v.SetNetCode(b.GetNetcodeFromNetname(scalar));v.SetPosition(pcbnew.VECTOR2I_MM(21,20))
        v.SetWidth(500000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='group':
        old=pcbnew.LoadBoard(str(source));g=pcbnew.PCB_GROUP(old);g.SetName('PROTECTED');old.Add(g)
        g.AddItem(next(iter(old.GetTracks())));field._save_field_snapshot(old,source)
    field._save_field_snapshot(b,child)
    call=dict(return_value=catalog)
    if fault=='contract_absent':call=dict(return_value={'contracts':{}})
    elif fault=='contract_changes':call=dict(side_effect=[catalog,{'contracts':{net:dict(required_by_layer_mm={'F.Cu':.3,'B.Cu':.3})}}])
    # The extra-power negative also needs a positively typed native supply.
    if fault=='extra_power':
        with mock.patch.object(branch.ordinary,'eligible_nets',return_value={scalar}):
            with mock.patch.object(branch.topology,'distributed_supply_contracts',**call):
                result=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    else:
        with mock.patch.object(branch.topology,'distributed_supply_contracts',**call):
            result=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],timeout_s=0 if fault=='budget' else 10)
    assert not result['ok'] and result['errors'],result


def test_one_phase_chain_is_independently_retyped_and_whole_replayed(tmp_path):
    source,child,uid,net,scalar,catalog=fixture(tmp_path)
    phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid])]
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog):
        result=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert result['ok'] and result['complete'],result
    assert result['retired_track_uuids']==[uid] and not result['retired_via_uuids']
    assert result['whole_original_cut_additions_ground_and_rule_replay']['ok']


def test_a_rated_width_contract_does_not_waive_a_stricter_source_netclass(tmp_path):
    source,child,uid,net,scalar,catalog=fixture(tmp_path)
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog), \
         mock.patch.object(branch.fr,'_project_netclass_resolver',return_value=lambda n:dict(track_width=.3 if n==net else .2)):
        result=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    assert not result['ok'] and 'full_load_planar' in result['errors'][0],result


@pytest.mark.parametrize('fault',['empty','untyped','unknown_key','wrong_final','repeated_phase','budget'])
def test_cut_chain_cannot_replace_independent_scope_with_a_worker_claim(tmp_path,fault):
    source,child,uid,net,scalar,catalog=fixture(tmp_path)
    phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid])]
    if fault=='empty':phases=[]
    elif fault=='untyped':phases[0]['kind']='arbitrary_ripup'
    elif fault=='unknown_key':phases[0]['waive_current']=True
    elif fault=='wrong_final':phases[0]['candidate']=str(source)
    elif fault=='repeated_phase':phases=phases*2
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog):
        result=chain.receive(source,child,board_hint='synthetic',phases=phases,timeout_s=0 if fault=='budget' else 10)
    assert not result['ok'] and result['errors'],result


def bridge_fixture(tmp_path):
    source,child,uid,net,scalar,catalog=fixture(tmp_path)
    parent=pcbnew.LoadBoard(str(source));parent.SetCopperLayerCount(6)
    field._save_field_snapshot(parent,source)
    child=force._copy_family(source,tmp_path/'native-bridge');b=pcbnew.LoadBoard(str(child))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    for a,z,layer in [((5,10),(5,11),pcbnew.F_Cu),((5,11),(10,11),pcbnew.In2_Cu),
                       ((10,11),(10,10),pcbnew.F_Cu)]:
        edge=track(b,net,a,z);edge.SetLayer(layer)
    for xy in ((5,11),(10,11)):
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(*xy));via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetNetCode(b.GetNetcodeFromNetname(net));b.Add(via)
    field._save_field_snapshot(b,child)
    catalog['contracts'][net].update(required_by_layer_mm={'F.Cu':.2,'In2.Cu':.2,'B.Cu':.2},
        routing_layers=['F.Cu','In2.Cu','B.Cu'])
    return source,child,uid,net,scalar,catalog


def test_small_full_load_branch_may_use_an_explicitly_authorized_inner_layer(tmp_path):
    source,child,uid,net,_,catalog=bridge_fixture(tmp_path);saved=source.read_bytes()
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog):
        refused=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
        received=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True)
        assert not refused['ok'] and received['ok'],(refused,received)
        phases=[dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[uid],allow_rated_layer_bridges=True)]
        proof=chain.receive(source,child,board_hint='synthetic',phases=phases)
        assert proof['ok'] and proof['complete'],proof
    assert len(received['rated_replacement_via_uuids'])==2
    assert not received['new_barrel_ampacity_credited'] and not received['current_authority']
    assert received['barrel_and_thermal_qualification_still_required']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('fault',['inner_width','unauthorized_layer','via_diameter','via_drill',
    'foreign_via_contact','blind','extra_barrels','non_boolean'])
def test_rated_bridge_preserves_actual_layer_width_barrel_and_clearance_obligations(tmp_path,fault):
    source,child,uid,net,_,catalog=bridge_fixture(tmp_path);b=pcbnew.LoadBoard(str(child))
    vias=[t for t in b.GetTracks() if t.GetClass()=='PCB_VIA']
    if fault=='inner_width':catalog['contracts'][net]['required_by_layer_mm']['In2.Cu']=.3
    elif fault=='unauthorized_layer':catalog['contracts'][net]['routing_layers']=['F.Cu','B.Cu']
    elif fault=='via_diameter':vias[0].SetWidth(500000)
    elif fault=='via_drill':vias[0].SetDrill(200000)
    elif fault=='blind':vias[0].SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault=='foreign_via_contact':
        original=pcbnew.LoadBoard(str(source));original.Add(pcbnew.NETINFO_ITEM(original,'/FOREIGN'))
        # A real spacing violation, not a physical short that KiCad attempts
        # to relabel while saving. Preserve the same foreign UUID in both
        # families so this reaches the all-layer guard, not the delta gate.
        edge=track(original,'/FOREIGN',(4,11),(4.6,11));edge.SetLayer(pcbnew.In4_Cu)
        foreign_uid=force._uid(edge)
        field._save_field_snapshot(original,source)
        b.Add(pcbnew.NETINFO_ITEM(b,'/FOREIGN'));edge=track(b,'/FOREIGN',(4,11),(4.6,11));edge.SetLayer(pcbnew.In4_Cu)
        edge.m_Uuid.Clone(pcbnew.KIID(foreign_uid))
    elif fault=='extra_barrels':
        for x in (7,8,9):
            via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(x,11));via.SetWidth(600000);via.SetDrill(300000)
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetNetCode(b.GetNetcodeFromNetname(net));b.Add(via)
    field._save_field_snapshot(b,child)
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog):
        proof=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=1 if fault=='non_boolean' else True)
    assert not proof['ok'] and proof['errors'],proof
    if fault=='foreign_via_contact':
        assert any('all_layer_guard' in error for error in proof['errors']),proof


def ground_refill_bridge_fixture(tmp_path,face):
    """Actual native Ground antipads change, but no retained conductor moves."""
    source,_,uid,net,scalar,catalog=bridge_fixture(tmp_path)
    parent=pcbnew.LoadBoard(str(source));parent.Add(pcbnew.NETINFO_ITEM(parent,'GND'))
    for xy in ((3,9),(12,13)):
        via=pcbnew.PCB_VIA(parent);via.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(parent.FindNet('GND'));parent.Add(via)
    zone=pcbnew.ZONE(parent);zone.SetLayer(face);zone.SetNet(parent.FindNet('GND'))
    zone.SetLocalClearance(200000);zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    outline=zone.Outline();outline.NewOutline()
    for x,y in ((2,8),(13,8),(13,14),(2,14)):outline.Append(int(x*1e6),int(y*1e6))
    parent.Add(zone);parent.BuildConnectivity()
    assert pcbnew.ZONE_FILLER(parent).Fill(parent.Zones())
    field._save_field_snapshot(parent,source)
    child=force._copy_family(source,tmp_path/'ground-refill-bridge')
    board=pcbnew.LoadBoard(str(child))
    discard_items(board,[t for t in board.GetTracks()if force._uid(t)==uid])
    for a,z,layer in [((5,10),(5,11),pcbnew.F_Cu),((5,11),(10,11),pcbnew.In2_Cu),
                       ((10,11),(10,10),pcbnew.F_Cu)]:
        edge=track(board,net,a,z);edge.SetLayer(layer)
    for xy in ((5,11),(10,11)):
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(board.FindNet(net));board.Add(via)
    board.BuildConnectivity();assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    field._save_field_snapshot(board,child)
    return source,child,uid,net,scalar,catalog


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_rated_layer_bridge_receives_actual_ground_refill_by_positive_island_overlap(tmp_path,face):
    import time
    source,child,uid,_,_,catalog=ground_refill_bridge_fixture(tmp_path,face)
    parent,board=[pcbnew.LoadBoard(str(p))for p in(source,child)]
    old=branch.ordinary._partition(parent,time.monotonic()+10.,retired_uuids={uid})
    # Reproduce the former receiver bug before testing the complete public API.
    with pytest.raises(ValueError,match='surviving_source_conductor_missing'):
        branch.ordinary._partition(board,time.monotonic()+10.,retained_keys=set().union(*old))
    before=source.read_bytes()
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog):
        received=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True)
    assert received['ok']and received['complete'],received
    paired=received['paired_native_partition_preservation']
    assert paired['available']and paired['preserved']and paired['overlap_token_count']>0
    assert not paired['whole_zone_uuid_connectivity_credit']and not paired['current_capacity_qualified']
    assert received['exact_source_cut_additions_ground_and_rule_replay']['ok']
    assert not received['new_barrel_ampacity_credited']and not received['current_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['split','wrong_face','missing_retained_via'])
def test_rated_ground_refill_does_not_waive_real_split_face_or_conductor_loss(tmp_path,fault):
    import time
    import cec_native_fill_geometry as fill
    source,child,uid,_,_,catalog=ground_refill_bridge_fixture(tmp_path,pcbnew.B_Cu)
    board=pcbnew.LoadBoard(str(child));zone=next(iter(board.Zones()))
    if fault=='split':
        shape=fill.reconstruct(fill.snapshot(zone.GetFilledPolysList(pcbnew.B_Cu),time.monotonic()+5.),
                               time.monotonic()+5.)
        cut=fill.reconstruct([[[[7000000,0],[8000000,0],[8000000,30000000],[7000000,30000000]]]],
                             time.monotonic()+5.)
        shape.BooleanSubtract(cut);zone.SetFilledPolysList(pcbnew.B_Cu,shape)
        zone.SetIsFilled(True);zone.CacheTriangulation(pcbnew.B_Cu)
    elif fault=='wrong_face':zone.SetLayer(pcbnew.F_Cu)
    else:discard_items(board,[next(t for t in board.GetTracks()if str(t.GetNetname())=='GND')])
    if fault=='split':
        # This is deliberately disconnected negative material. Verify the
        # actual serialized two-island board instead of requiring a safe
        # positive construction snapshot for the corrupt test artifact.
        pcbnew.SaveBoard(str(child),board)
        import cec_native_partition_pair as partitions
        split=partitions.compare(pcbnew.LoadBoard(str(source)),pcbnew.LoadBoard(str(child)),
                                 retired_uuids={uid})
        assert split['available']and not split['preserved']
    else:field._save_field_snapshot(board,child)
    with mock.patch.object(branch.topology,'distributed_supply_contracts',return_value=catalog):
        received=branch.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True)
    assert not received['ok']and received['errors'],received
    if fault=='split':
        assert 'rated_reconstruction_lost_surviving_native_partition'in received['errors'][0]

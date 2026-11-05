"""Native loop cuts require source loads, full-width joins and exact replay."""
import copy,math
from unittest import mock
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_distributed_loop_retirement as op
from test_lastmile import _board
from test_field_proposals import track

def fixture(tmp_path,angle=0,mirror=False):
    def xy(p):
        x,y=p[0]-7,p[1]-6
        if mirror:x=-x
        a=math.radians(angle)
        return round(9+x*math.cos(a)-y*math.sin(a),6),round(9+x*math.sin(a)+y*math.cos(a),6)
    net='/RENAMED/SUPPLY';b=_board([(*xy(p),net) for p in ((5,5),(9,5),(9,7))],edge=(0,0,22,22))
    for fp in b.GetFootprints():
        pad=next(iter(fp.Pads()));pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
        mask=pcbnew.LSET(pcbnew.LSET.AllCuMask());mask.AddLayer(pcbnew.F_Mask);mask.AddLayer(pcbnew.B_Mask);pad.SetLayerSet(mask)
    kept=[track(b,net,xy((5,5)),xy((9,5))),track(b,net,xy((9,5)),xy((9,7)))]
    cuts=[track(b,net,xy(a),xy(z),layer=pcbnew.B_Cu) for a,z in
        (((5,5),(5,8)),((5,8),(7,8)),((7,8),(9,8)))]
    tail=track(b,net,xy((9,8)),xy((9,5)),layer=pcbnew.B_Cu)
    bridge=track(b,net,xy((7,8)),xy((7,5)))
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(*xy((7,8))))
    via.SetNetCode(b.GetNetcodeFromNetname(net));via.SetWidth(600000);via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    # Explicit SYNTHETIC catalog fixture, never an invented real-board load.
    catalog=dict(contracts={net:dict(net=net,role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1,geometry_margin=1.25,margin_included=False),
        branch_sharing_assumed=False,routing_layers=['F.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':.2,'B.Cu':.2})})
    trims=[dict(uuid=force._uid(tail),start_nm=[round(v*1e6) for v in xy((9,7))],
        end_nm=[round(v*1e6) for v in xy((9,5))],locked_source_requested=False)]
    request=dict(net=net,board_hint='synthetic',track_uuids=[force._uid(t) for t in cuts],
        via_uuids=[force._uid(via)],retained_shortening_nm=trims)
    return source,b,request,catalog,kept,tail,bridge,via,xy

def saved_cut(tmp_path,b,source,request):
    plan=op.plan(b,source,**request);op.subtract(b,plan)
    child=force._copy_family(source,tmp_path/'child');additive._ground_refill(b);field._save_field_snapshot(b,child)
    return plan,child

@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_rotated_mirrored_native_saved_loop_and_tail_cut(tmp_path,angle,mirror):
    source,b,q,catalog,*_=fixture(tmp_path,angle,mirror);frozen=source.read_bytes()
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        plan,child=saved_cut(tmp_path,b,source,q);proof=op.receive(source,child,plan,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['surviving_native_partitions_preserved'] and proof['source_contract_preserved']
    assert not proof['current_qualified'] and not proof['release_authority']
    assert source.read_bytes()==frozen

@pytest.mark.parametrize('bad',['no_catalog','wrong_role','sharing','missing_margin','group','lock',
    'narrow','inner_cut','wrong_net','foreign_barrel_contact','other_barrel','retained_second_face',
    'duplicate','missing','bad_budget','negative_annulus','wrong_locked_trim','reversed_trim','off_stroke_trim','unshortened_trim'])
def test_source_scope_and_contact_unknowns_refuse_before_cut(tmp_path,bad):
    source,b,q,catalog,kept,tail,bridge,via,xy=fixture(tmp_path)
    cut=next(t for t in b.GetTracks() if force._uid(t)==q['track_uuids'][0])
    net=q['net'];model=catalog['contracts'][net]
    if bad=='no_catalog':catalog['contracts']={}
    elif bad=='wrong_role':model['role']='inferred'
    elif bad=='sharing':model['branch_sharing_assumed']=True
    elif bad=='missing_margin':model['current_authority'].pop('geometry_margin')
    elif bad=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED');b.Add(g);g.AddItem(cut)
    elif bad=='lock':cut.SetLocked(True)
    elif bad=='narrow':cut.SetWidth(100000)
    elif bad=='inner_cut':cut.SetLayer(pcbnew.In1_Cu)
    elif bad=='wrong_net':q['net']='/NOT PRESENT'
    elif bad=='foreign_barrel_contact':track(b,'/OTHER',xy((7,8)),xy((7,9)))
    elif bad=='other_barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(via.GetPosition());v.SetNetCode(via.GetNetCode())
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif bad=='retained_second_face':track(b,net,xy((7,8)),xy((7,9)),layer=pcbnew.B_Cu)
    elif bad=='duplicate':q['track_uuids']*=2
    elif bad=='missing':q['track_uuids'][0]='absent'
    elif bad=='bad_budget':q['timeout_s']=True
    elif bad=='negative_annulus':via.SetDrill(650000)
    elif bad=='wrong_locked_trim':tail.SetLocked(True)
    elif bad=='reversed_trim':
        row=q['retained_shortening_nm'][0];row['start_nm'],row['end_nm']=row['end_nm'],row['start_nm']
    elif bad=='off_stroke_trim':q['retained_shortening_nm'][0]['start_nm'][0]+=1
    elif bad=='unshortened_trim':q['retained_shortening_nm'][0]['start_nm']=list(tail.GetStart())
    frozen=field._field_snapshot_inventory(b)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):op.plan(b,source,**q)
    assert field._field_snapshot_inventory(b)==frozen

@pytest.mark.parametrize('bad',['forged_plan','source_change','candidate_change','needed_loop','full_width_loss','changed_catalog'])
def test_replay_and_current_reachability_are_independent_of_worker_flags(tmp_path,bad):
    source,b,q,catalog,kept,tail,bridge,via,xy=fixture(tmp_path)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        if bad=='needed_loop':
            kept[0].SetEnd(pcbnew.VECTOR2I_MM(*xy((6,5))));field._save_field_snapshot(b,source)
        elif bad=='full_width_loss':
            # The raw F path survives but cannot replace a full-load B join.
            kept[0].SetWidth(100000);field._save_field_snapshot(b,source)
        plan=op.plan(b,source,**q)
        if bad in ('forged_plan','source_change'):
            if bad=='forged_plan':plan['track_uuids'].append(force._uid(kept[0]))
            else:kept[0].SetWidth(250000)
            with pytest.raises(ValueError):op.subtract(b,plan)
            return
        op.subtract(b,plan)
        if bad=='candidate_change':kept[0].SetWidth(250000)
        child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        if bad=='changed_catalog':
            altered=copy.deepcopy(catalog);altered['contracts'][q['net']]['current_authority']['amps']=.2
            with mock.patch.object(op.topology,'distributed_supply_contracts',side_effect=[catalog,altered]):
                proof=op.receive(source,child,plan,board_hint='synthetic')
        else:proof=op.receive(source,child,plan,board_hint='synthetic')
    assert not proof['ok'] and proof['errors'],proof

def test_fully_orphaned_source_barrel_is_proved_from_all_exact_cut_contacts(tmp_path):
    source,b,q,catalog,kept,tail,bridge,via,xy=fixture(tmp_path)
    q['track_uuids'].append(force._uid(bridge))
    field._save_field_snapshot(b,source)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        plan,child=saved_cut(tmp_path,b,source,q)
        assert plan['source_barrels'][0]['all_original_contacts_are_exact_cut']
        assert op.receive(source,child,plan,board_hint='synthetic')['ok']


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_saved_multiface_multisland_ground_does_not_become_one_conductor_or_block_unrelated_supply_cut(tmp_path,angle):
    source,b,q,catalog,*_=fixture(tmp_path,angle)
    b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net)
    for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(b);zone.SetNet(net);zone.SetLayer(face)
        # Two disjoint actual saved islands, not two records incorrectly
        # joined through a common zone identity.
        poly=pcbnew.SHAPE_POLY_SET()
        for x in (1,17):
            index=poly.NewOutline()
            for a,z in ((x,1),(x+2,1),(x+2,3),(x,3)):
                poly.Outline(index).Append(a*1000000,z*1000000)
        outline=pcbnew.SHAPE_POLY_SET();outline.NewOutline()
        for a,z in ((1,1),(19,1),(19,3),(1,3)):outline.Append(a*1000000,z*1000000)
        zone.Outline().Append(outline);zone.SetFilledPolysList(face,poly)
        zone.SetIsFilled(True);b.Add(zone)
    for x in (2,18):
        owner=pcbnew.FOOTPRINT(b);owner.SetReference('GROUND_'+str(x));b.Add(owner)
        pad=pcbnew.PAD(owner);owner.Add(pad)
        pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetNet(net)
        pad.SetLayerSet(pcbnew.LSET.AllCuMask());pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetPosition(pcbnew.VECTOR2I_MM(x,2))
    field._save_field_snapshot(b,source)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        proposal,child=saved_cut(tmp_path,b,source,q)
        proof=op.receive(source,child,proposal,board_hint='synthetic')
    assert proof['ok']and proof['complete'],proof
    paired=proof['paired_native_partition_preservation']
    assert paired['available']and paired['preserved']
    assert not proof['current_qualified']and not proof['release_authority']


@pytest.mark.parametrize('clone_uuid',[False,True])
def test_exact_supply_cut_preserves_incomplete_physical_source_without_claiming_closure(tmp_path,clone_uuid):
    from cec_generated_pickup_retirement import _scoped_terminal_graph,_scoped_terminal_partitions
    source,b,q,catalog,*_=fixture(tmp_path)
    owner=pcbnew.FOOTPRINT(b);owner.SetReference('SEPARATE_UNFINISHED_LOAD');b.Add(owner)
    pad=pcbnew.PAD(owner);owner.Add(pad);pad.SetNumber('renamed-pin');pad.SetNet(b.FindNet(q['net']))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    pad.SetPosition(pcbnew.VECTOR2I_MM(17,17));pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    if clone_uuid:
        prior=next(p for f in b.GetFootprints()for p in f.Pads()if f!=owner)
        pad.m_Uuid.Clone(prior.m_Uuid)
    field._save_field_snapshot(b,source)
    relation=_scoped_terminal_partitions(b,q['net'])
    assert len(relation['actual_terminal_partitions'])==2
    assert len(relation['pad_identities'])==4
    assert relation['all_actual_terminals_definitely_connected']is False
    assert relation['incomplete_terminal_connectivity_not_qualified']
    with pytest.raises(ValueError,match='actual_drilled_terminal_material_disconnected'):
        _scoped_terminal_graph(b,q['net'])
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        proposal,child=saved_cut(tmp_path,b,source,q)
        proof=op.receive(source,child,proposal,board_hint='synthetic')
    assert proof['ok']and proof['complete'],proof
    assert proof['incomplete_source_supply_not_qualified']
    assert not proof['actual_drilled_terminal_graphs']['candidate']['all_actual_terminals_definitely_connected']
    assert not proof['current_qualified']and not proof['release_authority']

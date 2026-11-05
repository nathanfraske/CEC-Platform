"""Whole native forks are neither linear leaves nor whole-net rip-up grants."""
import copy,json,time,math
from pathlib import Path
import pcbnew
import pytest
import cec_cell_shared_fork as fork
import cec_cell_escape_replan as cell
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board
from test_cell_escape_replan import fixture as cell_fixture


def fixture(tmp_path,quarter=0,back=False,renamed=False,power=False):
    b=_board([],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    net='different_reference_alias' if renamed else '/arbitrary/control'
    for name in (net,'GND','RAIL','OUT','INPUT'):b.Add(pcbnew.NETINFO_ITEM(b,name))
    def xy(p):
        x,y=p
        for _ in range(quarter):x,y=30-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    def part(ref,value,entries):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value);fp.SetLayer(face)
        if value=='TLV7011DBVR':fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-5'))
        b.Add(fp)
        for pin,name,point in entries:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetShape(pcbnew.PAD_SHAPE_RECT)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetNet(b.FindNet(name));p.SetPosition(xy(point))
            p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers);fp.Add(p)
        return fp
    number='5' if power else '4'
    owner=part('RENAMED_DEVICE' if renamed else 'UNRELATED_DEVICE','TLV7011DBVR',[
        ('1','OUT',(7,7)),('2','GND',(7,8)),('3','INPUT',(7,9)),
        ('4','INPUT' if power else net,(7,6) if power else (10,10)),
        ('5',net if power else 'RAIL',(10,10) if power else (7,6))])
    root=owner.FindPadByNumber(number)
    left=part('FIXED_ALPHA','passive',[('1',net,(14,9))]).FindPadByNumber('1')
    right=part('FIXED_BETA','passive',[('1',net,(14,11))]).FindPadByNumber('1')
    edges=[]
    for a,z in [((10,10),(11,10)),((11,10),(12,9)),((12,9),(14,9)),((10,10),(10,11)),((10,11),(14,11))]:
        t=track(b,net,list(xy(a)/1e6),list(xy(z)/1e6),layer=face,width=.2);t.SetLocked(True);edges.append(t)
    source=tmp_path/'source.kicad_pcb';b.SetFileName(str(source));field._save_field_snapshot(b,source)
    return b,source,root,left,right,edges,xy


def proposal(b,root,kind='scalar_input',**options):
    # Hostile-source tests still present the actual saved native condition,
    # not an unsaved mutation falsely bound to an older source digest.
    if b.GetFileName() and Path(b.GetFileName()).is_file():
        pcbnew.SaveBoard(b.GetFileName(),b)
    return fork.plan(b,[force._uid(root)],moving_refs=[root.GetParentFootprint().GetReference()],
        kind=kind,board_hint='synthetic',allow_owned_locked=True,**options)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('renamed',[False,True])
def test_complete_scalar_source_fork_captures_all_departures_and_fixed_native_ports(tmp_path,quarter,back,renamed):
    b,source,root,a,z,edges,_=fixture(tmp_path,quarter,back,renamed);before=cell.row._source_binding(b);raw=source.read_bytes()
    with pytest.raises(ValueError):cell.leaf.plan_scalar_input(b,force._uid(root),board_hint='synthetic',allow_owned_locked=True)
    q=proposal(b,root)
    assert set(q['track_uuids'])=={force._uid(t) for t in edges}
    assert {p['native_uuid'] for p in q['retained_native_ports']}=={force._uid(a),force._uid(z)}
    assert q['moving_source_pad_uuids']==[force._uid(root)] and len(q['moving_source_terminal_contracts'])==1
    assert q['source_owned_locked_track_uuids']==q['track_uuids']
    assert not q['current_authority'] and not q['sensitive_role_reclassification'] and not q['release_authority']
    assert json.loads(json.dumps(q))==q and source.read_bytes()==raw and cell.row._source_binding(b)==before


@pytest.mark.parametrize('fault',['unknown_model','missing_pin','duplicate_pin','wrong_pin','DNP','locked_owner','grouped_owner',
    'plated_root','power_pin_type','domain','explicit_current','pair','analog_pair','aggressor','zone',
    'unnamed_source','nonexistent_source','unbounded_inventory','off_lattice_body'])
def test_unknown_protected_or_ambiguous_source_cannot_become_scalar_cut_authority(tmp_path,monkeypatch,fault):
    b,source,root,a,z,edges,xy=fixture(tmp_path);net=str(root.GetNetname())
    if fault=='unknown_model':root.GetParentFootprint().SetValue('UNKNOWN')
    elif fault=='missing_pin':root.GetParentFootprint().Remove(root.GetParentFootprint().FindPadByNumber('1'))
    elif fault=='duplicate_pin':
        copy=root.Duplicate();root.GetParentFootprint().Add(copy)
    elif fault=='wrong_pin':root.SetNumber('1')
    elif fault=='DNP':root.GetParentFootprint().SetDNP(True)
    elif fault=='locked_owner':root.GetParentFootprint().SetLocked(True)
    elif fault=='grouped_owner':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(root.GetParentFootprint())
    elif fault=='plated_root':root.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='power_pin_type':root.SetPinType('power_in')
    elif fault=='domain':monkeypatch.setattr(fork.topology,'board_current_domains',lambda *a,**kw:{net:{'complete':False}})
    elif fault=='explicit_current':monkeypatch.setattr(fork.synth,'spec_net_current_contract',lambda *a,**kw:{'amps':1.})
    elif fault=='pair':monkeypatch.setattr(fork.fr,'coupled_pair_nets',lambda *a,**kw:{net})
    elif fault=='analog_pair':monkeypatch.setattr(fork.semantics,'analog_input_pairs',lambda *a,**kw:[dict(p=net,n='OTHER')])
    elif fault=='aggressor':monkeypatch.setattr(fork.field,'classify_net',lambda *a,**kw:dict(power=False,aggressor=True))
    elif fault=='zone':
        zone=pcbnew.ZONE(b);zone.SetLayer(pcbnew.F_Cu);zone.SetNet(b.FindNet(net));b.Add(zone)
    elif fault=='unnamed_source':b.SetFileName('')
    elif fault=='nonexistent_source':b.SetFileName(str(tmp_path/'not-saved.kicad_pcb'))
    elif fault=='unbounded_inventory':
        # No fixed stop for a nine-edge source continuation.
        discard_items(b,edges);a.SetPosition(xy((20,10)));z.SetPosition(xy((20,11)))
        for i in range(9):track(b,net,(10+i,10),(11+i,10),width=.2)
    else:track(b,net,(10.5,8),(10.5,13),width=.4)
    before=cell.row._source_binding(b)
    with pytest.raises(ValueError):proposal(b,root)
    assert cell.row._source_binding(b)==before


def test_same_face_moving_land_is_a_real_copper_junction_not_an_endpoint_graph(tmp_path):
    b,source,root,a,z,edges,xy=fixture(tmp_path);owner=root.GetParentFootprint()
    # Two fork strokes contact opposite halves of the same actual land but
    # do not touch each other. The land, not a snapped node, joins them.
    root.SetSize(pcbnew.VECTOR2I_MM(1.,1.))
    edges[0].SetStart(xy((10.35,10)));edges[3].SetStart(xy((10,10.35)))
    assert not edges[0].GetEffectiveShape(pcbnew.F_Cu).Collide(edges[3].GetEffectiveShape(pcbnew.F_Cu),0)
    q=proposal(b,root)
    assert set(q['track_uuids'])=={force._uid(t) for t in edges}
    assert len(q['retained_native_ports'])==2


def test_explicit_larger_work_scope_owns_a_longer_source_but_preserves_the_small_default(tmp_path):
    b,source,root,a,z,edges,xy=fixture(tmp_path)
    discard_items(b,edges);a.SetPosition(xy((19,10)))
    strokes=[track(b,root.GetNetname(),(10+i,10),(11+i,10),width=.2) for i in range(9)]
    pcbnew.SaveBoard(str(source),b);before=cell.row._source_binding(b)
    with pytest.raises(ValueError,match='eight_track_scope'):proposal(b,root)
    q=proposal(b,root,max_tracks=16,max_length_mm=16.)
    assert set(q['track_uuids'])=={force._uid(t) for t in strokes}
    assert q['source_work_bounds']==dict(max_tracks=16,max_length_mm=16.)
    assert {p['native_uuid'] for p in q['retained_native_ports']}=={force._uid(a)}
    assert q['source_vias_zones_wide_tracks_and_groups_never_retired']
    assert before==cell.row._source_binding(b) and not q['current_authority']


@pytest.mark.parametrize('fault',['group','wide','mask','locked'])
def test_unowned_root_departures_remain_real_fixed_ports_not_retired_material(tmp_path,fault):
    b,source,root,a,z,edges,_=fixture(tmp_path);item=edges[0]
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(item)
    elif fault=='wide':item.SetWidth(400000)
    elif fault=='mask':item.SetHasSolderMask(True)
    else:
        for t in edges:t.SetLocked(False)
        item.SetLocked(True)
    options={} if fault!='locked' else dict(allow_owned_locked=False)
    before=cell.row._source_binding(b)
    if options:
        pcbnew.SaveBoard(str(source),b)
        q=fork.plan(b,[force._uid(root)],moving_refs=[root.GetParentFootprint().GetReference()],
            kind='scalar_input',board_hint='synthetic',**options)
    else:q=proposal(b,root)
    assert force._uid(item) not in q['track_uuids'] and force._uid(item) in {p['native_uuid'] for p in q['retained_native_ports']}
    assert cell.row._source_binding(b)==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_retained_cross_layer_component_is_not_restored_with_duplicate_parallel_branches(tmp_path,quarter,back):
    b,source,root,a,z,edges,xy=fixture(tmp_path,quarter,back);net=str(root.GetNetname())
    for pad in (a,z):
        via=pcbnew.PCB_VIA(b);via.SetNetCode(pad.GetNetCode());via.SetPosition(pad.GetPosition())
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    other=pcbnew.F_Cu if back else pcbnew.B_Cu
    track(b,net,list(xy((14,9))/1e6),list(xy((14,11))/1e6),layer=other)
    q=proposal(b,root);discard_items(b,[t for t in b.GetTracks() if force._uid(t) in q['track_uuids']])
    before=cell.row._source_binding(b);cohorts=fork.fixed_cohorts(b,q,deadline=time.monotonic()+10.)
    assert len(cohorts)==1 and len(cohorts[0]['ports'])==4
    requests=fork.connections(b,q);assert len(requests)==1
    assert not fork.connections(b,q,mandatory_links=[(force._uid(root),force._uid(a))])
    assert cell.row._source_binding(b)==before


def test_fixed_cohorts_cannot_use_retired_source_edges_missing_ports_or_moving_land_bridges(tmp_path):
    b,source,root,a,z,edges,_=fixture(tmp_path);q=proposal(b,root)
    with pytest.raises(ValueError,match='not_privately_retired'):fork.connections(b,q)
    discard_items(b,edges);before=cell.row._source_binding(b)
    bad=copy.deepcopy(q);bad['retained_native_ports'][0]['at_nm'][0]+=1000000
    with pytest.raises(ValueError,match='port_geometry'):fork.connections(b,bad)
    assert len(fork.fixed_cohorts(b,q,deadline=time.monotonic()+10.))==2
    assert cell.row._source_binding(b)==before


def test_unsaved_worker_native_mutation_cannot_claim_a_different_saved_source_digest(tmp_path):
    b,source,root,a,z,edges,_=fixture(tmp_path);edges[0].SetWidth(210000)
    before=cell.row._source_binding(b);raw=source.read_bytes()
    with pytest.raises(ValueError,match='literal_saved_native_source_fork_snapshot_required'):
        fork.plan(b,[force._uid(root)],moving_refs=[root.GetParentFootprint().GetReference()],
            kind='scalar_input',board_hint='synthetic',allow_owned_locked=True)
    assert cell.row._source_binding(b)==before and source.read_bytes()==raw


@pytest.mark.parametrize('value',[0,-1,True,10.000001,float('nan'),float('inf')])
def test_complete_source_fork_has_one_finite_ten_second_work_lease(tmp_path,value):
    b,source,root,*_=fixture(tmp_path);before=cell.row._source_binding(b)
    with pytest.raises(ValueError):proposal(b,root,timeout_s=value)
    assert cell.row._source_binding(b)==before


def power_authority(monkeypatch,net,face,floor=.2):
    contract=dict(net=net,role='all_terminal_conservative_aggregate',source_sink_inferred=False,branch_sharing_assumed=False,
        required_by_layer_mm={'F.Cu':floor,'B.Cu':floor},routing_layers=['F.Cu','B.Cu'],
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    # Explicit synthetic authority; these numbers are not board budgets.
    monkeypatch.setattr(fork.topology,'board_current_domains',lambda *a,**kw:{})
    monkeypatch.setattr(fork.topology,'distributed_supply_contracts',lambda *a,**kw:dict(contracts={net:contract}))
    rated=dict(required_by_layer_nm={face:round(floor*1e6)},current_authority=contract['current_authority'])
    monkeypatch.setattr(fork.cells,'_supply_current_widths',lambda *a,**kw:rated)
    return contract,rated


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_power_fork_keeps_the_complete_positive_rail_contract_and_exact_source_face(tmp_path,monkeypatch,quarter,back):
    b,source,root,a,z,edges,_=fixture(tmp_path,quarter,back,power=True)
    contract,rated=power_authority(monkeypatch,str(root.GetNetname()),pcbnew.B_Cu if back else pcbnew.F_Cu)
    before=cell.row._source_binding(b);q=proposal(b,root,kind='rated_supply')
    assert q['full_current_source_plan']['contract']==contract
    assert q['unchanged_full_rail_current_contract']==json.loads(json.dumps(rated))
    assert q['width_nm']==200000 and not q['no_per_device_current_or_output_mode_inference'] is False
    assert not q['full_current_source_plan']['current_sharing_inferred']
    assert q['moving_source_terminal_contracts'][0]['role']=='power_input'
    assert cell.row._source_binding(b)==before


@pytest.mark.parametrize('fault',['unknown_budget','higher_floor','incomplete_domain','wrong_kind','boolean_margin'])
def test_power_source_cannot_fall_back_to_signal_width_or_guessed_per_device_current(tmp_path,monkeypatch,fault):
    b,source,root,*_=fixture(tmp_path,power=True);net=str(root.GetNetname())
    contract,rated=power_authority(monkeypatch,net,pcbnew.F_Cu,.3 if fault=='higher_floor' else .2)
    if fault=='unknown_budget':monkeypatch.setattr(fork.topology,'distributed_supply_contracts',lambda *a,**kw:dict(contracts={}))
    elif fault=='incomplete_domain':monkeypatch.setattr(fork.topology,'board_current_domains',lambda *a,**kw:{net:dict(complete=False)})
    elif fault=='wrong_kind':contract['role']='guessed_divided_load'
    elif fault=='boolean_margin':contract['current_authority']['geometry_margin']=True
    before=cell.row._source_binding(b)
    with pytest.raises(ValueError):proposal(b,root,kind='rated_supply')
    assert cell.row._source_binding(b)==before


@pytest.mark.parametrize('fault',['unknown','changed_load','changed_width'])
def test_cell_routing_cannot_drop_a_source_power_contract_after_placement(tmp_path,monkeypatch,fault):
    b,source,root,a,z,edges,_=fixture(tmp_path,power=True);net=str(root.GetNetname())
    contract,rated=power_authority(monkeypatch,net,pcbnew.F_Cu);q=proposal(b,root,kind='rated_supply')
    discard_items(b,edges);request=fork.connections(b,q)[0];changed=copy.deepcopy(rated)
    if fault=='unknown':changed=None
    elif fault=='changed_load':changed['current_authority']['amps']=.1
    else:changed['required_by_layer_nm'][pcbnew.F_Cu]=199999
    monkeypatch.setattr(fork.cells,'_supply_current_widths',lambda *a,**kw:changed)
    before=cell.row._source_binding(b)
    with pytest.raises(ValueError,match='source_current_contract_changed_or_unknown'):
        cell._connection_menu(b,request,board_hint='synthetic',deadline=time.monotonic()+10.,layers=[],append=lambda *a,**kw:None,detail={})
    assert cell.row._source_binding(b)==before


def complete(monkeypatch,tmp_path):
    b,poses,owner,cap=cell_fixture(monkeypatch,prefix='independent_multibranch_cell');root=owner.FindPadByNumber('4');net=str(root.GetNetname())
    fixed=[]
    for ref,point in [('FIXED_SOURCE_A',(16,10)),('FIXED_SOURCE_B',(16,12))]:
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);b.Add(fp);p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(b.FindNet(net))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetPosition(pcbnew.VECTOR2I_MM(*point))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p);fixed.append(p)
    edges=[]
    for a,z in [((11,11),(12,10)),((12,10),(16,10)),((11,11),(12,12)),((12,12),(16,12))]:
        t=track(b,net,a,z);t.SetLocked(True);edges.append(t)
    source=tmp_path/'complete-source.kicad_pcb';b.SetFileName(str(source));field._save_field_snapshot(b,source)
    q=cell.prepare(b,poses,board_hint='synthetic',allow_owned_locked_escapes=True)
    assert len(q['source_owned_shared_scalar_input_forks'])==1
    return b,source,q,root,fixed,edges


@pytest.mark.parametrize('fault',['extra_cut','port','root_role','width','missing_port','source_changed'])
def test_saved_complete_cell_rederives_multiport_ownership_before_any_cut_or_pose(monkeypatch,tmp_path,fault):
    b,source,q,root,fixed,edges=complete(monkeypatch,tmp_path);q=json.loads(json.dumps(q))
    shared=q['source_owned_shared_scalar_input_forks'][0]
    if fault=='extra_cut':q['retired_track_uuids'].append('unowned-source-track')
    elif fault=='port':shared['retained_native_ports'][0]['at_nm'][0]+=1
    elif fault=='root_role':shared['moving_source_terminal_contracts'][0]['role']='power_input'
    elif fault=='width':shared['width_nm']=199999
    elif fault=='missing_port':shared['retained_native_ports'].pop()
    else:edges[0].SetWidth(210000)
    before=cell.row._source_binding(b)
    with pytest.raises(ValueError):cell.apply_private(b,q)
    assert cell.row._source_binding(b)==before


def test_native_multiport_partition_is_restored_after_saved_json_cell_motion(monkeypatch,tmp_path):
    b,source,q,root,fixed,edges=complete(monkeypatch,tmp_path);parent=pcbnew.LoadBoard(str(source))
    oldkeys={force._uid(p):force._item_key(p) for fp in parent.GetFootprints() for p in fp.Pads()}
    before=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=set(q['retired_track_uuids']))
    cell.apply_private(b,json.loads(json.dumps(q)));requests=cell.obligations(parent,b,q)
    shared=[r for k,r in requests.items() if k.startswith('shared_scalar_input:')]
    assert len(shared)==2 and all(r['width_nm']==200000 for r in shared)
    assert not any(k.startswith('boundary:') and k.split(':',1)[1] in {force._uid(t) for t in edges} for k in requests)
    mapping={force._item_key(p):oldkeys[force._uid(p)] for fp in b.GetFootprints() for p in fp.Pads()};retained=set.union(*before)
    def lost():
        after=ordinary._partition(b,time.monotonic()+10.,retained_keys=retained,_identity_rebindings=mapping)
        return sum(not any(p<=q for q in after) for p in before)
    assert lost()==1
    for r in shared:
        path=fork.fr._canonical_45_xy_paths(r['a']['at_nm'],r['b']['at_nm'])[0]
        for a,z in zip(path,path[1:]):track(b,r['net'],[v/1e6 for v in a],[v/1e6 for v in z],width=.2)
    assert lost()==0 and not q['routing_admitted'] and not q['release_authority']

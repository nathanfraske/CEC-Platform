"""Synthetic authority catalogs; native cuts, boundaries and deltas are real."""
import math
from unittest.mock import patch

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as reflow
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, quarter=0, width=1., prefix='/new/', face='F.Cu',span_mm=5.):
    net = prefix+'BUS'
    center=15 if span_mm==5 else 15+span_mm/2
    def pose(at):
        x,y=at[0]-center,at[1]-center
        for _ in range(quarter):x,y=-y,x
        return center+x,center+y
    edge=30 if span_mm==5 else 30+span_mm
    end=5+span_mm
    b=_board([(*pose(p),net) for p in ((5,10),(end,10))],edge=(0,0,edge,edge))
    if face=='In2.Cu':b.SetCopperLayerCount(6)
    old=track(b,net,pose((5,10)),pose((end,10)))
    old.SetWidth(pcbnew.FromMM(width)); old.SetLayer(b.GetLayerID(face)); old.SetLocked(True)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    candidate=force._copy_family(source,tmp_path/'child')
    b=pcbnew.LoadBoard(str(candidate))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==force._uid(old)])
    for a,z in (((5,10),(5.5,10.5)),((5.5,10.5),(end-.5,10.5)),((end-.5,10.5),(end,10))):
        t=track(b,net,pose(a),pose(z));t.SetWidth(pcbnew.FromMM(width));t.SetLayer(b.GetLayerID(face))
    field._save_field_snapshot(b,candidate)
    candidate=additive.finalize_private(source,candidate,tmp_path/'final')['board']
    contract=dict(net=net,required_by_layer_mm={'F.Cu':.2,'B.Cu':.2},
        routing_layers=['F.Cu','B.Cu'],current_authority=dict(
            amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    if face=='In2.Cu':
        contract['required_by_layer_mm']['In2.Cu']=.2
        contract['routing_layers'].append('In2.Cu')
    # Deliberate test-only current authority. Production gets this complete
    # source-owned contract from the real catalog; tests never infer a load.
    domains={net:dict(net=net,complete=True,source_refs=['source'],sink_refs=['sink'])}
    return source,candidate,force._uid(old),net,contract,domains


def receive(source,candidate,uid,net,contract,domains,**kwargs):
    with patch.object(reflow.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(reflow.topology,'board_current_domains',return_value=domains):
        return reflow.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],**kwargs)


@pytest.mark.parametrize('quarter,prefix',[(0,'/a/'),(1,'/renamed/'),(2,'/different/'),(3,'/z/')])
@pytest.mark.parametrize('width',[.2,1.])
def test_exact_full_current_reflow_preserves_boundaries_and_all_unowned_items(tmp_path,quarter,prefix,width):
    source,child,uid,net,contract,domains=fixture(tmp_path,quarter,width,prefix)
    before=source.read_bytes()
    result=receive(source,child,uid,net,contract,domains)
    assert result['ok'] and result['complete'],result
    assert result['source_width_and_current_exact'] and result['all_surviving_native_partitions_preserved']
    assert result['source_proposal']['width_nm']==pcbnew.FromMM(width)
    assert not result['routing_admitted'] and not result['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['narrow','layer','open','pose','via','extra_power','group','authority','incomplete','current_changes'])
def test_reflow_refuses_out_of_scope_or_unrestored_native_changes(tmp_path,fault):
    source,child,uid,net,contract,domains=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(child))
    t=next(iter(b.GetTracks()))
    if fault=='narrow':t.SetWidth(999999)
    elif fault=='layer':t.SetLayer(pcbnew.B_Cu)
    elif fault=='open':
        # Disconnect the whole wide replacement, not one leaf which may
        # still overlap a real large land or the neighboring wide capsule.
        for item in b.GetTracks():item.Move(pcbnew.VECTOR2I_MM(0,6))
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(7,10.5))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='extra_power':
        b.Add(pcbnew.NETINFO_ITEM(b,'OTHER'));track(b,'OTHER',(20,20),(21,20))
    elif fault=='group':
        parent=pcbnew.LoadBoard(str(source));g=pcbnew.PCB_GROUP(parent);parent.Add(g)
        g.AddItem(next(iter(parent.GetTracks())));field._save_field_snapshot(parent,source)
    elif fault=='authority':contract['current_authority']['source']='unverified_guess'
    elif fault=='incomplete':domains[net]['complete']=False
    field._save_field_snapshot(b,child)
    if fault=='current_changes':
        changed=dict(contract,required_by_layer_mm={'F.Cu':.3,'B.Cu':.3})
        with patch.object(reflow.topology,'route_width_contracts',side_effect=[{net:contract},{net:changed}]), \
             patch.object(reflow.topology,'board_current_domains',return_value=domains):
            result=reflow.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    else:result=receive(source,child,uid,net,contract,domains)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('quarter,prefix',[(0,'/long/a/'),(1,'/long/b/'),(2,'/long/c/'),(3,'/long/d/')])
def test_explicit_long_bus_reach_keeps_all_current_geometry_and_replays_chain(tmp_path,quarter,prefix):
    source,child,uid,net,contract,domains=fixture(tmp_path,quarter,prefix=prefix,span_mm=28.)
    before=source.read_bytes()
    assert not receive(source,child,uid,net,contract,domains)['ok']
    bounds=dict(max_source_track_mm=32.,max_source_cut_mm=48.)
    result=receive(source,child,uid,net,contract,domains,**bounds)
    assert result['ok'] and result['complete'],result
    proposal=result['source_proposal']
    assert proposal['contract']==contract and proposal['width_nm']==1000000
    assert {k:proposal[k] for k in bounds}==bounds
    phase=dict(kind='full_current_planar_reflow',candidate=str(child),retired_track_uuids=[uid],**bounds)
    with patch.object(reflow.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(reflow.topology,'board_current_domains',return_value=domains):
        replay=chain.receive(source,child,board_hint='synthetic',phases=[phase],per_phase_leases=True)
    assert replay['ok'] and replay['complete'],replay
    assert source.read_bytes()==before and not replay['release_authority']


@pytest.mark.parametrize('key,value',[(k,v) for k,limit in (('max_source_track_mm',32.),('max_source_cut_mm',48.))
    for v in (True,False,0.,-1.,float('nan'),float('inf'),limit+.1,'32')])
def test_long_bus_scope_refuses_invalid_unbounded_or_boolean_work_limits(tmp_path,key,value):
    source,child,uid,net,contract,domains=fixture(tmp_path,span_mm=28.)
    result=receive(source,child,uid,net,contract,domains,
        **dict(dict(max_source_track_mm=32.,max_source_cut_mm=48.),**{key:value}))
    assert not result['ok'] and result['errors'],result


def test_long_bus_reach_does_not_hide_aggregate_source_cut_or_authorize_unknown_phase_fields(tmp_path):
    source,child,uid,net,contract,domains=fixture(tmp_path,span_mm=28.)
    result=receive(source,child,uid,net,contract,domains,max_source_track_mm=32.,max_source_cut_mm=27.)
    assert not result['ok'] and result['errors'],result
    phase=dict(kind='full_current_planar_reflow',candidate=str(child),retired_track_uuids=[uid],
        max_source_track_mm=32.,max_source_cut_mm=48.,waive_current=True)
    with pytest.raises(ValueError):chain._phases([phase],child)


@pytest.mark.parametrize('fault',['narrow','layer','pose','via'])
def test_long_bus_scope_never_relaxes_saved_native_current_or_unowned_material(tmp_path,fault):
    source,child,uid,net,contract,domains=fixture(tmp_path,span_mm=28.)
    b=pcbnew.LoadBoard(str(child))
    t=next(iter(b.GetTracks()))
    if fault=='narrow':t.SetWidth(999999)
    elif fault=='layer':t.SetLayer(pcbnew.B_Cu)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(20,10.5));v.SetNet(b.FindNet(net))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    field._save_field_snapshot(b,child)
    result=receive(source,child,uid,net,contract,domains,max_source_track_mm=32.,max_source_cut_mm=48.)
    assert not result['ok'] and result['errors'],result


def test_authorized_inner_signal_face_retains_its_own_full_current_width(tmp_path):
    source,child,uid,net,contract,domains=fixture(tmp_path,face='In2.Cu')
    result=receive(source,child,uid,net,contract,domains)
    assert result['ok'] and result['complete'],result
    assert result['source_proposal']['layer_id']==pcbnew.In2_Cu


def test_source_contract_cannot_authorize_a_native_ground_plane_cut(tmp_path):
    source,child,uid,net,contract,domains=fixture(tmp_path,face='In2.Cu')
    parent=pcbnew.LoadBoard(str(source))
    next(iter(parent.GetTracks())).SetLayer(pcbnew.In1_Cu)
    field._save_field_snapshot(parent,source)
    contract['required_by_layer_mm']['In1.Cu']=.2
    contract['routing_layers'].append('In1.Cu')
    result=receive(source,child,uid,net,contract,domains)
    assert not result['ok'] and result['errors'],result


def test_typed_chain_independently_replays_the_exact_whole_current_cut(tmp_path):
    source,child,uid,net,contract,domains=fixture(tmp_path)
    phases=[dict(kind='full_current_planar_reflow',candidate=str(child),retired_track_uuids=[uid])]
    with patch.object(reflow.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(reflow.topology,'board_current_domains',return_value=domains):
        result=chain.receive(source,child,board_hint='synthetic',phases=phases,per_phase_leases=True)
    assert result['ok'] and result['complete'],result
    assert result['retired_track_uuids']==[uid]
    assert not result['current_authority'] and not result['release_authority']


def distributed(contract):
    return dict(contract,role='all_terminal_conservative_aggregate',
        source_sink_inferred=False,branch_sharing_assumed=False)


@pytest.mark.parametrize('quarter,prefix',[(0,'/first/'),(1,'/other/'),(2,'/unrelated/'),(3,'/last/')])
@pytest.mark.parametrize('authority',['board_design_basis','component_power_budget'])
def test_explicit_distributed_current_reflow_keeps_whole_budget_without_source_guessing(tmp_path,quarter,prefix,authority):
    source,child,uid,net,contract,_=fixture(tmp_path,quarter,prefix=prefix)
    contract['current_authority']['source']=authority
    typed=distributed(contract)
    with patch.object(reflow.topology,'board_current_domains',return_value={}), \
         patch.object(reflow.topology,'distributed_supply_contracts',return_value={'contracts':{net:typed}}):
        result=reflow.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    assert result['ok'] and result['complete'],result
    p=result['source_proposal']
    assert p['current_domain_kind']=='explicit_all_terminal_distributed_supply' and p['domain'] is None
    assert p['contract']==typed and not p['source_current_reduced'] and not p['current_sharing_inferred']


@pytest.mark.parametrize('fault',['missing','role','inferred_source','sharing','guessed_current',
    'bool_amps','zero_amps','nan_amps','double_margin','domain_reclassification','budget_changed'])
def test_distributed_reflow_refuses_missing_or_changed_authority(tmp_path,fault):
    source,child,uid,net,contract,_=fixture(tmp_path)
    typed=distributed(contract)
    if fault=='role':typed['role']='signal'
    elif fault=='inferred_source':typed['source_sink_inferred']=True
    elif fault=='sharing':typed['branch_sharing_assumed']=True
    elif fault=='guessed_current':typed['current_authority']['source']='estimate'
    elif fault=='bool_amps':typed['current_authority']['amps']=True
    elif fault=='zero_amps':typed['current_authority']['amps']=0
    elif fault=='nan_amps':typed['current_authority']['amps']=float('nan')
    elif fault=='double_margin':typed['current_authority']['margin_included']=True
    replies=[{'contracts':{} if fault=='missing' else {net:typed}}]*2
    if fault=='budget_changed':
        changed=dict(typed,current_authority=dict(typed['current_authority'],amps=.75))
        replies[1]={'contracts':{net:changed}}
    domains=[{},{}]
    if fault=='domain_reclassification':domains[1]={net:dict(complete=False)}
    with patch.object(reflow.topology,'board_current_domains',side_effect=domains), \
         patch.object(reflow.topology,'distributed_supply_contracts',side_effect=replies):
        result=reflow.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    assert not result['ok'] and result['errors'],result


def test_incomplete_aggregate_domain_never_borrows_distributed_authority(tmp_path):
    source,child,uid,net,contract,domains=fixture(tmp_path)
    domains[net]['complete']=False
    with patch.object(reflow.topology,'board_current_domains',return_value=domains), \
         patch.object(reflow.topology,'distributed_supply_contracts') as unused:
        result=reflow.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    assert not result['ok'] and result['errors'] and unused.call_count==0


def existing_native_domain(contract,domains,net):
    """Synthetic catalog only; use the production existing-domain validator.

    No mock positive replaces its fresh current_contract_for_net derivation.
    Native cuts, contacts, partitions and saved deltas remain real as above.
    """
    contract['current_authority']['source']='current_domain_authority'
    domains[net].update(amps=contract['current_authority']['amps'],
        authority_refs=['source','sink'],source='thermal_source_sink_override')


@pytest.mark.parametrize('quarter,prefix',[(0,'/native/a/'),(1,'/native/b/'),
    (2,'/native/c/'),(3,'/native/d/')])
@pytest.mark.parametrize('width',[.2,1.])
def test_fresh_complete_native_domain_authority_replays_actual_saved_reflow(tmp_path,quarter,prefix,width):
    source,child,uid,net,contract,domains=fixture(tmp_path,quarter,width,prefix)
    existing_native_domain(contract,domains,net)
    before=source.read_bytes()
    result=receive(source,child,uid,net,contract,domains)
    assert result['ok'] and result['complete'],result
    proposal=result['source_proposal']
    assert proposal['current_domain_kind']=='aggregate_source_sink'
    assert proposal['contract']==contract and proposal['domain']==domains[net]
    assert proposal['width_nm']==pcbnew.FromMM(width)
    assert result['source_width_and_current_exact'] and result['all_surviving_native_partitions_preserved']
    assert not proposal['current_sharing_inferred'] and not proposal['source_current_reduced']
    assert not result['current_authority'] and not result['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['incomplete','source_missing','sink_missing',
    'duplicate_source','duplicate_sink','overlapping_roles','blank_ref','owners_missing',
    'owners_string','owners_duplicate','owners_wrong','missing_ref','off_net_ref',
    'bool_amps','zero_amps','nan_amps','mismatched_amps','changed_margin',
    'unknown_authority','static_contract_conflict'])
def test_native_domain_authority_requires_fresh_exact_complete_non_guessed_contract(tmp_path,fault):
    import cec_synth_pipeline as synth
    source,child,uid,net,contract,domains=fixture(tmp_path)
    existing_native_domain(contract,domains,net)
    domain=domains[net];raw=contract['current_authority']
    if fault=='incomplete':domain['complete']=False
    elif fault=='source_missing':domain['source_refs']=[]
    elif fault=='sink_missing':domain['sink_refs']=[]
    elif fault=='duplicate_source':domain['source_refs']*=2
    elif fault=='duplicate_sink':domain['sink_refs']*=2
    elif fault=='overlapping_roles':domain['sink_refs']=['source']
    elif fault=='blank_ref':domain['source_refs']=[' ']
    elif fault=='owners_missing':domain.pop('authority_refs')
    elif fault=='owners_string':domain['authority_refs']='source,sink'
    elif fault=='owners_duplicate':domain['authority_refs'].append('source')
    elif fault=='owners_wrong':domain['authority_refs'].append('other')
    elif fault=='missing_ref':domain['missing_refs']=['missing']
    elif fault=='off_net_ref':domain['binding']={'off_net_required_refs':['sink']}
    elif fault=='bool_amps':domain['amps']=raw['amps']=True
    elif fault=='zero_amps':domain['amps']=raw['amps']=0
    elif fault=='nan_amps':domain['amps']=raw['amps']=float('nan')
    elif fault=='mismatched_amps':raw['amps']=.75
    elif fault=='changed_margin':raw['geometry_margin']=1.5
    elif fault=='unknown_authority':raw['source']='guessed_current'
    with patch.object(synth,'spec_net_current_contract',return_value=(
            dict(raw,source='board_design_basis')if fault=='static_contract_conflict'else None)), \
         patch.object(reflow.topology,'distributed_supply_contracts')as unused:
        result=receive(source,child,uid,net,contract,domains)
    assert not result['ok'] and result['errors'],result
    assert unused.call_count==0


@pytest.mark.parametrize('fault',['amps','roles','width','face','pose'])
def test_native_domain_support_cannot_change_candidate_contract_or_unowned_material(tmp_path,fault):
    import copy
    source,child,uid,net,contract,domains=fixture(tmp_path)
    existing_native_domain(contract,domains,net)
    changed=copy.deepcopy(domains)
    if fault=='amps':changed[net]['amps']=.75
    elif fault=='roles':
        changed[net]['sink_refs']=['different_sink']
        changed[net]['authority_refs']=['source','different_sink']
    else:
        board=pcbnew.LoadBoard(str(child))
        item=next(iter(board.GetTracks()))
        if fault=='width':item.SetWidth(999999)
        elif fault=='face':item.SetLayer(pcbnew.B_Cu)
        elif fault=='pose':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,2))
        field._save_field_snapshot(board,child)
    def fresh_domains(board,board_hint=None):
        return domains if str(board.GetFileName())==str(source)else changed
    with patch.object(reflow.topology,'board_current_domains',side_effect=fresh_domains), \
         patch.object(reflow.topology,'route_width_contracts',return_value={net:contract}):
        result=reflow.receive(source,child,board_hint='synthetic',retired_track_uuids=[uid])
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('quarter,prefix',[(0,'/physical/a/'),(1,'/physical/b/'),(2,'/physical/c/'),(3,'/physical/d/')])
def test_native_planar_chain_requires_exact_retyping_and_fresh_physical_replay(tmp_path,quarter,prefix):
    import cec_current_debt as debt
    source,child,uid,net,contract,domains=fixture(tmp_path,quarter,prefix=prefix)
    phases=[dict(kind='full_current_planar_reflow',candidate=str(child),retired_track_uuids=[uid])]
    # Synthetic catalog/qualification context only. Native source-cut,
    # saved additions, boundaries and conductor partitions are NOT mocked.
    with patch.object(reflow.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(reflow.topology,'board_current_domains',return_value=domains), \
         patch.object(debt,'receive',return_value={'ok':True,'complete':True}):
        result=reflow.receive_force_sense_chain(source,child,board_hint='synthetic',phases=phases)
    assert result['ok'] and result['complete'],result
    assert result['physical_preservation']['same_evidence']
    manifest=result['native_count_manifest'];assert len(manifest)==1
    assert manifest[0]['net']==net and manifest[0]['retired_track_uuids']==[uid]
    assert len(manifest[0]['added_track_uuids'])==3
    assert result['source_current_and_widths_unchanged'] and not result['current_qualified']


@pytest.mark.parametrize('fault',['phase_kind','extra_phase_key','wrong_end','repeated_path',
    'narrow','via','physical_incomplete','physical_changed','current_refused','bad_sense_deadline'])
def test_planar_physical_lineage_cannot_bypass_native_or_absolute_cut_receiving(tmp_path,fault):
    import cec_current_debt as debt
    import cec_force_sense_evidence as sense
    source,child,uid,net,contract,domains=fixture(tmp_path)
    phases=[dict(kind='full_current_planar_reflow',candidate=str(child),retired_track_uuids=[uid])]
    target=child;kwargs={}
    if fault=='phase_kind':phases[0]['kind']='additive'
    elif fault=='extra_phase_key':phases[0]['worker_success']=True
    elif fault=='wrong_end':target=source
    elif fault=='repeated_path':phases.append(dict(phases[0]))
    elif fault=='bad_sense_deadline':kwargs['sense_timeout_s']=float('inf')
    if fault in ('narrow','via'):
        b=pcbnew.LoadBoard(str(child))
        if fault=='narrow':next(iter(b.GetTracks())).SetWidth(999999)
        else:
            v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(7,10.5));v.SetNet(b.FindNet(net))
            v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        field._save_field_snapshot(b,child)
    with patch.object(reflow.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(reflow.topology,'board_current_domains',return_value=domains), \
         patch.object(debt,'receive',return_value={'ok':fault!='current_refused','complete':True}):
        if fault in ('physical_incomplete','physical_changed'):
            with patch.object(sense,'compare_contour_preservation',return_value={
                    'comparison_complete':fault!='physical_incomplete','same_evidence':fault!='physical_changed'}):
                result=reflow.receive_force_sense_chain(source,target,board_hint='synthetic',phases=phases,**kwargs)
        else:
            result=reflow.receive_force_sense_chain(source,target,board_hint='synthetic',phases=phases,**kwargs)
    assert not result['ok'] and result['errors'],result

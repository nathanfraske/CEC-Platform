"""Unqualified routes may survive a proposal without becoming qualified."""
from types import SimpleNamespace
import json

import pytest
import cec_noncontact_placement as local


def fixture(tmp_path, *, back=False, attachment=False, zone_layer=None):
    import cec_swig_guard;cec_swig_guard.pin()
    import pcbnew
    board=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(board,'arbitrary_net');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('movable');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(net)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(1,1));pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad)
    fp.SetPosition(pcbnew.VECTOR2I_MM(3,3))
    if back:fp.Flip(fp.GetPosition(),False)
    t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(pcbnew.B_Cu if back else pcbnew.F_Cu)
    t.SetStart(pcbnew.VECTOR2I_MM(3 if attachment else 10,3))
    t.SetEnd(pcbnew.VECTOR2I_MM(11,3));t.SetWidth(pcbnew.FromMM(.2));board.Add(t)
    if zone_layer is not None:
        z=pcbnew.ZONE(board);z.SetNet(net);z.SetLayer(zone_layer)
        z.Outline().NewOutline()
        for x,y in ((0,0),(15,0),(15,15),(0,15)):z.Outline().Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
        board.Add(z)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    path.with_suffix('.kicad_dru').write_text('(version 1)\n')
    cand=SimpleNamespace(W=15,H=15,P={'movable':local._pose(fp)},back_refs=('movable',) if back else ())
    cand.noncontact_placement_contract=local.bind(path,cand)
    return cand,path,board,fp


@pytest.mark.parametrize('back,rotation', [(False,0),(False,180),(True,0),(True,180),(False,270),(False,-90)])
def test_saved_native_pose_delta_retains_existing_route_without_ownership(tmp_path,back,rotation):
    import pcbnew
    from cec_local_copper_cell import copper_inventory
    cand,path,board,fp=fixture(tmp_path,back=back)
    before=path.read_bytes();inventory=copper_inventory(board)
    cand.P['movable']=(4,4,rotation)
    output=tmp_path/'proposal.kicad_pcb'
    local.materialize(cand,output)
    after=pcbnew.LoadBoard(str(output))
    assert copper_inventory(after)==inventory
    assert local._same_pose(local._pose(after.FindFootprintByReference('movable')),(4,4,rotation))
    assert path.read_bytes()==before
    assert output.with_suffix('.kicad_dru').read_bytes()==path.with_suffix('.kicad_dru').read_bytes()
    assert not cand.noncontact_placement_contract['release_authority']
    assert not cand.noncontact_placement_contract['grants_copper_ownership']


@pytest.mark.parametrize('cause', ['attached','contact','tht','locked','zone','boundary','shape','faces','identity','stale','rules'])
def test_invalid_delta_never_overwrites_output(tmp_path,cause):
    import pcbnew
    cand,path,board,fp=fixture(tmp_path,attachment=cause=='attached',
                              zone_layer=pcbnew.F_Cu if cause=='zone' else None)
    if cause=='tht':
        next(iter(fp.Pads())).SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif cause=='locked':fp.SetLocked(True)
    elif cause=='boundary':
        edge=pcbnew.PCB_SHAPE(fp);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetEnd(pcbnew.VECTOR2I_MM(1,1));fp.Add(edge)
    if cause in ('tht','locked','boundary'):
        pcbnew.SaveBoard(str(path),board);cand.noncontact_placement_contract=local.bind(path,cand)
    cand.P['movable']=(10 if cause=='contact' else 4,3,0)
    if cause=='shape':cand.W=16
    elif cause=='faces':cand.back_refs=('movable',)
    elif cause=='identity':cand.P['unknown']=(1,1,0)
    elif cause=='stale':path.write_text(path.read_text()+'\n')
    elif cause=='rules':path.with_suffix('.kicad_dru').write_text('(version 1)\n\n')
    output=tmp_path/'existing.kicad_pcb';output.write_text('existing output')
    with pytest.raises(ValueError):local.materialize(cand,output)
    assert output.read_text()=='existing output'


def test_unchanged_copy_is_byte_identical_and_inplace_is_refused(tmp_path):
    cand,path,_,_=fixture(tmp_path)
    output=tmp_path/'baseline.kicad_pcb';local.materialize(cand,output)
    assert output.read_bytes()==path.read_bytes()
    with pytest.raises(ValueError,match='distinct'):local.materialize(cand,path)


def test_native_save_side_effect_is_caught_after_reload(tmp_path,monkeypatch):
    import pcbnew
    cand,path,_,_=fixture(tmp_path)
    cand.P['movable']=(4,4,0)
    original=pcbnew.SaveBoard
    def corrupted(path,board):
        next(iter(board.GetTracks())).SetWidth(pcbnew.FromMM(.3))
        return original(path,board)
    monkeypatch.setattr(pcbnew,'SaveBoard',corrupted)
    with pytest.raises(ValueError,match='copper changed'):
        local.materialize(cand,tmp_path/'no-output.kicad_pcb')
    assert not (tmp_path/'no-output.kicad_pcb').exists()


def test_craft_wrapper_binds_nondestructive_scope_but_not_ownership(monkeypatch,tmp_path):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    cand,path,_,_=fixture(tmp_path)
    del cand.noncontact_placement_contract
    cand.rehydration_copper_coverage=dict(ok=False,unpreserved_items=1)
    def repair(cfg,bound,**kwargs):
        assert bound is not cand
        assert bound.noncontact_placement_contract['source_sha256']==local.sha(path)
        assert not bound.noncontact_placement_contract['grants_copper_ownership']
        bound.P=dict(bound.P,movable=(4,4,0))
        synth._materialize_rehydrated_board(bound,cfg,str(tmp_path/'proposal.kicad_pcb'))
        return bound,dict(changed=True)
    monkeypatch.setattr(synth,'repair_placement_craft_epochs',repair)
    _,report=pipeline._repair_craft_with_search_history(
        SimpleNamespace(params={'placement_noncontact_resume':True}),cand,path)
    assert report['materialization_scope']=='noncontact_smd_delta_without_copper_ownership'
    assert report['original_copper_coverage']['unpreserved_items']==1
    assert not hasattr(cand,'noncontact_placement_contract')


@pytest.mark.parametrize('already_touching',[False,True])
def test_direct_pad_contacts_are_not_silently_broken_or_created(tmp_path,already_touching):
    import pcbnew
    cand,path,board,fp=fixture(tmp_path)
    peer=pcbnew.FOOTPRINT(board);peer.SetReference('other')
    pad=pcbnew.PAD(peer);pad.SetNumber('1');pad.SetNet(next(iter(fp.Pads())).GetNet())
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(1,1));pad.SetLayerSet(pcbnew.PAD.SMDMask());peer.Add(pad)
    peer.SetPosition(pcbnew.VECTOR2I_MM(3 if already_touching else 5,3))
    board.Add(peer);pcbnew.SaveBoard(str(path),board)
    cand.P['other']=local._pose(peer);cand.noncontact_placement_contract=local.bind(path,cand)
    cand.P['movable']=(5,3,0)
    expected = 'original copper attachment' if already_touching else 'create copper contact'
    with pytest.raises(ValueError,match=expected):
        local.materialize(cand,tmp_path/'no-output.kicad_pcb')


def test_new_rule_file_invalidates_binding(tmp_path):
    cand,path,_,_=fixture(tmp_path)
    path.with_suffix('.kicad_pro').write_text('{}')
    with pytest.raises(ValueError,match='source/rules changed'):
        local.materialize(cand,tmp_path/'no-output.kicad_pcb')


def test_atomic_proposal_materialization_also_works_without_qualified_prefix(tmp_path,monkeypatch):
    import cec_synth_pipeline as synth
    cand,path,_,_=fixture(tmp_path)
    cand.source_board=str(path);cand.protected_power_prefix={}
    cand.P['movable']=(4,4,0)
    def forbidden(*args):raise AssertionError('native identity normalization would invalidate exact preservation')
    monkeypatch.setattr(synth,'_normalize_materialized_item_ids',forbidden)
    # No qualification is implied by an empty prefix; only independent craft
    # admission outside this low-level materializer may accept this proposal.
    monkeypatch.setattr(synth,'_admit_materialized_power_prefix',lambda *args:None)
    before=path.read_bytes()
    synth.materialize(cand,SimpleNamespace(),str(tmp_path/'output.kicad_pcb'))
    assert path.read_bytes()==before


def test_explicit_optout_keeps_original_reconstruction_path(tmp_path,monkeypatch):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    cand,path,_,_=fixture(tmp_path)
    del cand.noncontact_placement_contract
    cand.rehydration_copper_coverage=dict(ok=False,unpreserved_items=1)
    def repair(cfg,bound,**kwargs):
        assert not hasattr(bound,'noncontact_placement_contract')
        return bound,dict(changed=False)
    monkeypatch.setattr(synth,'repair_placement_craft_epochs',repair)
    _,report=pipeline._repair_craft_with_search_history(
        SimpleNamespace(params={'placement_noncontact_resume':False}),cand,path)
    assert 'materialization_scope' not in report


def test_construction_receipt_is_rebound_only_after_exact_native_preservation(tmp_path):
    cand,path,_,_=fixture(tmp_path)
    report=dict(schema=1,board=path.name,total=0,laid=0,refused=[],
                force_lanes=dict(total=1,laid=1,ok=True,results={}),
                ground_portals=dict(scope='future_not_installed'))
    path.with_suffix('.cellreport.json').write_text(json.dumps(report))
    cand.noncontact_placement_contract=local.bind(path,cand,retain_reports=True)
    cand.P['movable']=(4,4,0)
    target=tmp_path/'renamed.kicad_pcb';local.materialize(cand,target)
    carried=json.loads(target.with_suffix('.cellreport.json').read_text())
    retention=carried.pop('noncontact_retention');carried['board']=path.name
    assert carried==report  # Including failures/observations, not just passes.
    assert retention['source_sha256']==local.sha(path)
    assert retention['output_sha256']==local.sha(target)
    assert retention['source_report_sha256']==local.sha(path.with_suffix('.cellreport.json'))
    assert not retention['release_authority']


@pytest.mark.parametrize('scope',['declared','ref','dictionary_key','preserved_net','force_net'])
def test_report_members_and_explicit_construction_nets_remain_fixed(tmp_path,scope):
    cand,path,_,_=fixture(tmp_path)
    report=dict(schema=1,board=path.name,total=0,laid=0,refused=[])
    if scope=='ref':report['ground_portals']={'ref':'movable'}
    elif scope=='dictionary_key':report['observations']={'movable':{}}
    elif scope=='preserved_net':report['preserved_nets']=['arbitrary_net']
    elif scope=='force_net':report['force_lanes']={'results':{'lane':{'nets':['arbitrary_net']}}}
    path.with_suffix('.cellreport.json').write_text(json.dumps(report))
    cand.noncontact_placement_contract=local.bind(path,cand,retain_reports=True,
        immutable_refs=['movable'] if scope=='declared' else [])
    cand.P['movable']=(4,4,0)
    with pytest.raises(ValueError,match='construction evidence members'):
        local.materialize(cand,tmp_path/'refused.kicad_pcb')


@pytest.mark.parametrize('cause',['identity','counts','unknown_ref','changed'])
def test_invalid_or_changed_construction_report_is_not_reused(tmp_path,cause):
    cand,path,_,_=fixture(tmp_path)
    report=dict(schema=1,board=path.name,total=0,laid=0,refused=[])
    if cause=='identity':report['board']='another.kicad_pcb'
    elif cause=='counts':report['laid']=1
    elif cause=='unknown_ref':report['portal']={'ref':'does-not-exist'}
    report_path=path.with_suffix('.cellreport.json');report_path.write_text(json.dumps(report))
    if cause=='changed':
        cand.noncontact_placement_contract=local.bind(path,cand,retain_reports=True)
        report_path.write_text(json.dumps(dict(report,extra='changed')))
        with pytest.raises(ValueError,match='construction evidence changed'):
            local.materialize(cand,tmp_path/'refused.kicad_pcb')
    else:
        with pytest.raises(ValueError):local.bind(path,cand,retain_reports=True)


@pytest.mark.parametrize('cause',['detached','route','zone','locked','tht','graphic'])
def test_native_search_domain_freezes_unsupported_members_without_route_ownership(tmp_path,cause):
    import pcbnew
    cand,path,board,fp=fixture(tmp_path,attachment=cause=='route',
        zone_layer=pcbnew.F_Cu if cause=='zone' else None)
    if cause=='locked':fp.SetLocked(True)
    elif cause=='tht':next(iter(fp.Pads())).SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif cause=='graphic':
        line=pcbnew.PCB_SHAPE(fp);line.SetLayer(pcbnew.F_Cu)
        line.SetShape(pcbnew.SHAPE_T_SEGMENT);line.SetEnd(pcbnew.VECTOR2I_MM(1,1));fp.Add(line)
    if cause in ('locked','tht','graphic'):pcbnew.SaveBoard(str(path),board)
    before=path.read_bytes()
    contract=local.bind(path,cand,freeze_native_dependencies=True)
    assert path.read_bytes()==before
    assert ('movable' in contract['immutable_refs']) == (cause!='detached')
    assert contract['native_domain']['movable_refs']==(['movable'] if cause=='detached' else [])
    assert not contract['grants_copper_ownership'] and not contract['release_authority']


@pytest.mark.parametrize('enabled',[True,False])
def test_priority_wrapper_uses_exact_noncontact_scope_without_discarding_existing_copper(tmp_path,monkeypatch,enabled):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    cand,path,_,_=fixture(tmp_path)
    del cand.noncontact_placement_contract
    cand.rehydration_copper_coverage=dict(ok=False,unpreserved_items=1)
    cand.route_preflight={};cand.source_board=str(path)
    cfg=SimpleNamespace(params={'placement_route_repair_trials':1,
        'placement_route_repair_rounds':1,'placement_priority_noncontact_resume':enabled})
    original=dict(cfg.params)
    before=path.read_bytes()
    monkeypatch.setattr(synth,'config_with_board_route_authority',lambda *a:(cfg,dict(ok=True,bound=False)))
    monkeypatch.setattr(synth,'placement_candidate_from_board',lambda *a,**k:cand)
    def repair(bound,candidate,**kwargs):
        assert enabled
        assert candidate is not cand and bound is not cfg
        assert candidate.noncontact_placement_contract['native_domain']['movable_refs']==['movable']
        proposal=SimpleNamespace(**candidate.__dict__)
        proposal.P=dict(candidate.P,movable=(4.,4.,180.))
        synth._materialize_rehydrated_board(proposal,bound,str(tmp_path/'proposal.kicad_pcb'))
        return candidate,dict(changed=False,reason='finite_domain_tested')
    monkeypatch.setattr(synth,'repair_route_preflight_iterative',repair)
    report=pipeline._repair_placement_priority_routes_in_process(cfg,path,allow_authored_prefix=True)
    assert not report['changed'] and path.read_bytes()==before and cfg.params==original
    if enabled:
        assert report['materialization_scope']=='noncontact_smd_delta_without_copper_ownership'
        assert report['original_copper_coverage']['unpreserved_items']==1
        assert report['noncontact_domain']['movable_refs']==['movable']
        assert not hasattr(cand,'noncontact_placement_contract')
    else:
        assert report['reason']=='routed_copper_requires_owned_transaction'


@pytest.mark.parametrize('noncontact_enabled', [False,True])
def test_unbound_priority_recovery_reports_unadmitted_local_copper_without_worker_crash(tmp_path,monkeypatch,noncontact_enabled):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    _candidate,path,_board,_fp=fixture(tmp_path)
    state_path=path.with_suffix('.pourfirst-state.json')
    state_path.write_text(json.dumps({'placement_scope':'complete',
        'local_copper_contract':{'schema':1},'exact_admission':{'passed':False}}))
    before={p:p.read_bytes() for p in (path,state_path)}
    cfg=SimpleNamespace(params={'placement_route_repair_trials':1,
        'placement_route_repair_rounds':1,
        'placement_priority_noncontact_resume':noncontact_enabled})
    params=dict(cfg.params)
    monkeypatch.setattr(synth,'config_with_board_route_authority',lambda *a:(cfg,
        dict(ok=False,bound=False,reason='exact_filled_power_admission_failed')))
    def unexpected_repair(*args,**kwargs):
        pytest.fail('a rejected local-copper authority cannot enter route-placement search')
    monkeypatch.setattr(synth,'repair_route_preflight_iterative',unexpected_repair)
    report=pipeline._repair_placement_priority_routes_in_process(cfg,path,
        allow_authored_prefix=True,allow_unbound_power_authority=True)
    assert not report['ok'] and not report['changed'] and report['applicable']
    assert report['reason']=='unadmitted_local_copper_requires_owned_recovery'
    assert report['blocked_stage']=='frozen_power_authority'
    assert report['retry_requires']=='owned_local_copper_transaction_and_fresh_power_qualification'
    assert report['copper_ownership']['grants_copper_ownership'] is False
    assert report['route_authority']['ok'] is False
    assert report['release_authority'] is False
    assert cfg.params==params
    assert {p:p.read_bytes() for p in before}==before


@pytest.mark.parametrize('noncontact_enabled', [False,True])
def test_worker_serializes_unadmitted_local_copper_as_blocked_not_success(tmp_path,monkeypatch,noncontact_enabled):
    import cec_operation_budget as budget
    import cec_power_artifact_worker as worker
    import cec_synth_pipeline as synth
    _candidate,path,_board,_fp=fixture(tmp_path)
    state_path=path.with_suffix('.pourfirst-state.json')
    state_path.write_text(json.dumps({'placement_scope':'complete',
        'local_copper_contract':{'schema':1},'exact_admission':{'passed':False}}))
    before=path.read_bytes(),state_path.read_bytes()
    cfg=SimpleNamespace(params={'placement_route_repair_trials':1,
        'placement_route_repair_rounds':1,
        'placement_priority_noncontact_resume':noncontact_enabled})
    monkeypatch.setattr(synth.Config,'load',lambda *a:cfg)
    monkeypatch.setattr(synth,'config_with_board_route_authority',lambda *a:(cfg,
        dict(ok=False,bound=False,reason='incomplete_route_authority')))
    monkeypatch.setattr(budget,'arm_diagnostics',lambda:None)
    monkeypatch.setattr(budget,'progress',lambda *a,**k:None)
    report_path=tmp_path/'worker-result.json'
    status=worker.main(['priority-repair',str(path),'--board-name','synthetic-fixture',
        '--report',str(report_path),'--allow-authored-prefix','--allow-unbound-power-authority'])
    result=json.loads(report_path.read_text())
    assert status==0  # Successful report delivery, not physical admission.
    assert result['ok'] is False and result['changed'] is False
    assert result['reason']=='unadmitted_local_copper_requires_owned_recovery'
    assert result['blocked_stage']=='frozen_power_authority'
    assert result['release_authority'] is False
    assert (path.read_bytes(),state_path.read_bytes())==before

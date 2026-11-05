"""Known native debt can fund additive work; neither counts nor history suffice."""
from copy import deepcopy
import hashlib
import json
import pytest
import cec_route_debt_resume as debt


def grade(tmp_path,*,opens=41):
    path=tmp_path/'renamed.kicad_pcb';path.write_text('exact native artifact')
    snap=dict(drc=1,drc_types={'track_dangling':1},unconnected=opens,
        unconn_nets=['/ordinary'],structural_drc_identities=[json.dumps(
            ['track_dangling','uuid',['source-copper']])])
    result=dict(routed=str(path),drc=1,unconnected=opens,
        mutation_snapshot=snap,native_structural_violation_count=1)
    result['repair_debt_receipt']=debt.bind(result,family=[{'path':str(path)}],
        params_sha256='policy',code_sha256='epoch')
    return result


def verified(row):
    return debt.verified(row,params_sha256='policy',code_sha256='epoch',artifacts_match=lambda _:True)


def test_known_complete_debt_receipt_is_work_not_release_permission(tmp_path):
    row=grade(tmp_path)
    assert verified(row) and row['repair_debt_receipt']['release_authority'] is False


@pytest.mark.parametrize('fault',['pcb','snapshot','count','missing_identity','fallback',
    'partial_count','duplicate_identity','unhashable_identity','epoch','policy','release','family'])
def test_unknown_or_stale_debt_is_refused(tmp_path,fault):
    row=grade(tmp_path);receipt=row['repair_debt_receipt']
    if fault=='pcb':open(row['routed'],'w').write('new geometry')
    elif fault=='snapshot':row['mutation_snapshot']['unconn_nets']=['different']
    elif fault=='count':row['drc']=2
    elif fault=='missing_identity':row['mutation_snapshot'].pop('structural_drc_identities')
    elif fault=='fallback':row['mutation_snapshot']['structural_drc_identities']=['["track_dangling","fallback",[]]']
    elif fault=='partial_count':row['native_structural_violation_count']=0
    elif fault=='duplicate_identity':row['mutation_snapshot']['structural_drc_identities']*=2
    elif fault=='unhashable_identity':row['mutation_snapshot']['structural_drc_identities']=[{}]
    elif fault=='epoch':receipt['code_sha256']='previous'
    elif fault=='policy':receipt['params_sha256']='different'
    elif fault=='release':receipt['release_authority']=True
    else:receipt['artifacts']=[]
    assert not verified(row)


@pytest.mark.parametrize('fault',['none','new_fault','new_net','opens','incomplete'])
def test_only_strict_open_gain_without_new_fault_identity_is_admitted(tmp_path,fault):
    before=grade(tmp_path);after=deepcopy(before)
    after['unconnected']=40;after['mutation_snapshot']['unconnected']=40
    if fault=='new_fault':after['mutation_snapshot']['structural_drc_identities']=[json.dumps(['track_dangling','uuid',['new-copper']])]
    elif fault=='new_net':after['mutation_snapshot']['unconn_nets']=['/new-open']
    elif fault=='opens':after['unconnected']=41;after['mutation_snapshot']['unconnected']=41
    elif fault=='incomplete':after.pop('mutation_snapshot')
    assert debt.admit(before,after)['accepted'] is (fault=='none')


@pytest.mark.parametrize('fault',['none','same_count','different_fault','gate_loss','retention','plateau','current_debt'])
def test_canonical_resume_funds_verified_debt_and_receives_it_independently(tmp_path,fault):
    from types import SimpleNamespace
    from unittest.mock import patch
    import cec_full_pipeline as pipeline
    import cec_force_current as force
    import cec_residual_breadth as breadth
    import cec_additive_route_receiving as receiving
    import cec_current_debt as current
    import cec_operation_budget as budget
    import cec_synth_pipeline as synth
    before=grade(tmp_path)
    before.update(gate_terms={'pairs_ok':True,'final_residual_consistent':True},gate=False)
    cfg=SimpleNamespace(params={},board_key='source-declared-board')
    family=pipeline._artifact_rows([before['routed']])
    before['repair_debt_receipt']=debt.bind(before,family=family,
        params_sha256=pipeline.digest_value(cfg.params),code_sha256=debt.digest(force._code_identity()))
    child=tmp_path/'child.kicad_pcb';child.write_text('received additions')
    after=deepcopy(before);after.update(routed=str(child),unconnected=40)
    after['mutation_snapshot']['unconnected']=40
    if fault=='same_count':after['unconnected']=41;after['mutation_snapshot']['unconnected']=41
    elif fault=='different_fault':after['mutation_snapshot']['structural_drc_identities']=[json.dumps(['track_dangling','uuid',['foreign-new']])]
    elif fault=='gate_loss':after['gate_terms']['pairs_ok']=False
    with patch.object(budget,'optional_work_admission',return_value={'start':True}), \
        patch.object(breadth,'run',return_value={'changed':fault!='plateau','candidate':str(child),'stop':'bounded'}), \
        patch.object(receiving,'receive',return_value={'ok':fault!='retention','complete':True}), \
        patch.object(current,'receive',return_value={'ok':fault!='current_debt','complete':True}), \
        patch.object(synth,'config_with_board_route_authority',return_value=(cfg,{})), \
        patch.object(pipeline,'_grade_route_incumbent',return_value=after):
        chosen,evidence=pipeline._resume_route_residuals(before,tmp_path/'output',cfg,seed=5,thermal='lazy')
    assert (chosen is not None) is (fault=='none')
    assert not evidence['release_authority']


@pytest.mark.parametrize('fault', ['none', 'plateau', 'retention', 'start_error', 'native_regression', 'current_debt'])
def test_verified_optical_debt_gain_survives_later_refused_route(tmp_path, fault):
    from types import SimpleNamespace
    from unittest.mock import patch
    import cec_full_pipeline as pipeline
    import cec_force_current as force
    import cec_residual_breadth as breadth
    import cec_additive_route_receiving as receiving
    import cec_current_debt as current
    import cec_route_checkpoint as checkpoint
    import cec_operation_budget as budget
    import cec_synth_pipeline as synth
    before = grade(tmp_path)
    before.update(gate_terms={'fiducials_ok': False, 'final_residual_consistent': True}, gate=False)
    cfg = SimpleNamespace(params={}, board_key='renamed-board')
    before['repair_debt_receipt'] = debt.bind(before,
        family=pipeline._artifact_rows([before['routed']]),
        params_sha256=pipeline.digest_value(cfg.params), code_sha256=debt.digest(force._code_identity()))
    optical = tmp_path/'optical.kicad_pcb'; optical.write_text('received optical move')
    after = deepcopy(before)
    after.update(routed=str(optical), drc=0, native_structural_violation_count=0)
    after['mutation_snapshot'].update(drc=0, drc_types={}, structural_drc_identities=[])
    after['gate_terms']['fiducials_ok'] = True
    routed = deepcopy(after); routed['unconnected'] = 40; routed['mutation_snapshot']['unconnected'] = 40
    trial = dict(changed=fault!='plateau', candidate=str(optical), stop='plateau')
    if fault == 'native_regression':
        routed['unconnected']=41; routed['mutation_snapshot']['unconnected']=41
    with patch.object(budget,'optional_work_admission',return_value={'start':True}), \
         patch.object(checkpoint,'assembly_normalize',return_value=(str(optical),{'changed':True})), \
         patch.object(breadth,'run',side_effect=RuntimeError('bounded refusal') if fault=='start_error' else None,
                      return_value=trial), \
         patch.object(receiving,'receive',return_value={'ok':fault!='retention','complete':True}), \
         patch.object(current,'receive',return_value={'ok':fault!='current_debt','complete':True}), \
         patch.object(synth,'config_with_board_route_authority',return_value=(cfg,{})), \
         patch.object(pipeline,'_grade_route_incumbent',side_effect=[after,routed]):
        chosen, evidence = pipeline._resume_route_residuals(before,tmp_path/'output',cfg,seed=5,thermal='lazy')
    assert chosen is not None and chosen['drc']==0
    assert chosen['unconnected'] == (40 if fault=='none' else 41)
    assert evidence['optical_assembly']['accepted'] and evidence['skip_global']
    assert not evidence['release_authority']
    assert (tmp_path/'output'/'residual-resume.json').is_file()

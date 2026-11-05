"""A placement proof is separate from (and cannot weaken) additive continuation."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pcbnew
import pytest
import cec_route_placement_admission as admission
import cec_route_checkpoint as checkpoint
import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
import cec_certificate_repair as repair
import cec_final_residual as residual
import cec_operation_budget as budget
from test_fixed_pofv_mobility import fixture as native_fixture
from test_route_residual_resume import grade


def placement_proof():
    return dict(ok=False, functional_placement_unchanged=False, outline_unchanged=True,
        power_zones_unchanged=True, parent_copper={'ok': True}, qualified_pairs={'ok': True},
        power_obligations={'ok': True}, score_admission={'accepted': True})


@pytest.mark.parametrize('missing', list(placement_proof()))
def test_incomplete_checkpoint_cannot_authorize_handoff(missing):
    proof = placement_proof()
    assert admission.placement_only_failure(proof)
    proof.pop(missing)
    assert not admission.placement_only_failure(proof)


@pytest.mark.parametrize('fault,reason', [
    ('none', 'support_placement_revalidated'),
    ('rules', 'design_rule_authority_changed'),
    ('project', 'design_rule_authority_changed'),
    ('population', 'component_or_pad_definition_changed'),
    ('copper', 'existing_copper_changed'),
    ('fixed', 'immutable_or_out_of_scope_component'),
    ('plan', 'frozen_power_plan_changed'),
    ('physical', 'full_physical_placement_refused'),
    ('exception', 'placement_revalidation_error'),
    ('source_mutation', 'input_family_changed'),
])
def test_native_private_transaction_preserves_each_boundary(tmp_path, monkeypatch, fault, reason):
    board, fp, pad, via = native_fixture()
    other = pcbnew.PAD(fp)
    other.SetNumber('2'); other.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    other.SetShape(pcbnew.PAD_SHAPE_RECT); other.SetSize(pcbnew.VECTOR2I_MM(.6, .4))
    other.SetPosition(fp.GetPosition() - pcbnew.VECTOR2I_MM(.775, 0))
    other.SetLayerSet(pad.GetLayerSet()); other.SetNet(pad.GetNet()); fp.Add(other)
    source = tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    # Stable same-content skeleton shared by the synthetic authority family.
    skeleton = tmp_path/'stock.kicad_pcb'; skeleton.write_bytes(source.read_bytes())
    state = dict(placement_scope='complete', placements={fp.GetReference(): [20,30,0]},
                 frozen_nets=[], skeleton=str(skeleton), unchanged_plan={'amps': 1})
    source.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    if not source.with_suffix('.kicad_pro').exists():
        source.with_suffix('.kicad_pro').write_text('{}')
    candidate = tmp_path/'candidate.kicad_pcb'
    repair._copy_board_family(str(source), str(candidate))
    moved = pcbnew.LoadBoard(str(candidate))
    owner = moved.FindFootprintByReference(fp.GetReference())
    owner.SetPosition(owner.GetPosition()+pcbnew.VECTOR2I_MM(.775,.775))
    owner.SetOrientationDegrees(90)
    if fault == 'population':
        owner.SetValue('changed')
    if fault == 'copper':
        next(iter(moved.GetTracks())).SetWidth(800000)
    pcbnew.SaveBoard(str(candidate), moved)
    # Loading/saving a synthetic project with no schematic can invent a
    # top-level sheet entry. Keep this fixture's explicit source policy;
    # production admission must continue rejecting *any* such policy change.
    candidate.with_suffix('.kicad_pro').write_bytes(source.with_suffix('.kicad_pro').read_bytes())
    if fault == 'rules':
        candidate.with_suffix('.kicad_dru').write_text('(version 2)\n')
    if fault == 'project':
        project = json.loads(candidate.with_suffix('.kicad_pro').read_text())
        project['board']['design_settings']['rules']['min_clearance'] = 0.01
        candidate.with_suffix('.kicad_pro').write_text(json.dumps(project))
    if fault == 'plan':
        changed = json.loads(candidate.with_suffix('.pourfirst-state.json').read_text())
        changed['unchanged_plan']['amps'] = 2
        candidate.with_suffix('.pourfirst-state.json').write_text(json.dumps(changed))
    cfg = SimpleNamespace(params={}, pins={fp.GetReference(): [20,30,0]} if fault=='fixed' else {})
    monkeypatch.setattr(checkpoint, 'preservation', lambda *_: placement_proof())
    monkeypatch.setattr(synth, 'config_with_board_route_authority', lambda c,p: (c, dict(ok=True,bound=True)))
    def physical(*args):
        if fault == 'source_mutation':
            source.write_bytes(source.read_bytes()+b'\n')
        if fault == 'exception':
            raise RuntimeError('synthetic checker failed')
        return dict(ok=fault!='physical', craft_gate={'ok':fault!='physical'})
    monkeypatch.setattr(pipeline, '_measure_placement_physical_in_process', physical)
    before = source.read_bytes(), candidate.read_bytes()
    result = admission._native_prepare(source, candidate, tmp_path/'private', cfg)
    assert result['ok'] is (fault=='none'), result
    assert result['reason'] == reason
    assert not result['release_authority']
    assert json.loads((tmp_path/'private/revalidation.json').read_text())['ok'] == result['ok']
    if fault != 'source_mutation':
        assert (source.read_bytes(),candidate.read_bytes()) == before
        assert result['input_families_unchanged']
    if fault == 'none':
        assert result['additive_checkpoint']['ok'] is False
        assert result['all_parent_copper']['ok']
        assert Path(result['board']).read_bytes() == candidate.read_bytes()


@pytest.mark.parametrize('fault', ['none', 'physical', 'unfunded', 'grade_regression', 'refill_drift'])
def test_normal_coordinator_requires_revalidated_family_and_fresh_grade(tmp_path, monkeypatch, fault):
    source = tmp_path/'source.kicad_pcb'; source.write_text('source')
    proposal = tmp_path/'proposal.kicad_pcb'; proposal.write_text('proposal')
    prepared = tmp_path/'prepared.kicad_pcb'; prepared.write_text('same-board-new-authority')
    cfg = SimpleNamespace(params={'route_residual_resume_rounds':1})
    before = grade(source, opens=4)
    monkeypatch.setattr(residual, 'measure', lambda *a,**k: dict(unconnected_count=4,
        source_board_sha256=pipeline.sha256_file(source)))
    monkeypatch.setattr(residual, 'valid_snapshot', lambda _: True)
    admissions = []
    def funded(*args,**kwargs):
        admissions.append(args[0])
        return dict(start=fault!='unfunded' or len(admissions)==1)
    monkeypatch.setattr(budget, 'optional_work_admission', funded)
    monkeypatch.setattr(synth, '_route_oracle_certificate_repair', lambda *a,**k:
                        (str(proposal), dict(changed=True)))
    monkeypatch.setattr(synth, 'config_with_board_route_authority', lambda c,p: (c,{}))
    proof = placement_proof()
    monkeypatch.setattr(checkpoint, 'preservation', lambda *a: copy.deepcopy(proof))
    with mock.patch.object(admission, 'prepare', return_value=dict(ok=fault not in ('physical','refill_drift'),
            reason='source_refill_drift' if fault=='refill_drift' else 'tested',
            board=str(prepared))) as prepare:
        graded = []
        def qualify(path,*args,**kwargs):
            graded.append(path)
            result = grade(path, opens=3)
            if fault=='grade_regression': result['gate_terms']['pairs_ok'] = False
            return result
        monkeypatch.setattr(pipeline, '_grade_route_incumbent', qualify)
        result, evidence = pipeline._resume_route_residuals(before, tmp_path/'out', cfg,
                                                           seed=1, thermal='lazy')
    assert (result is not None) is (fault=='none')
    assert prepare.call_count == (0 if fault=='unfunded' else 1)
    assert graded == ([str(prepared)] if fault in ('none','grade_regression') else [])
    assert json.loads((tmp_path/'out/residual-resume/round-00/preservation.json').read_text())['ok'] is False
    assert source.read_text() == 'source' and not evidence['release_authority']
    if fault=='refill_drift':
        assert evidence['stop']=='source_refill_drift'
        assert evidence['skip_global'] and evidence['requires_source_revalidation']


@pytest.mark.parametrize('fault', ['none', 'unfunded', 'physical', 'changed_bytes', 'other_origin'])
def test_outer_selector_rechecks_support_transition_instead_of_discarding_it(tmp_path, monkeypatch, fault):
    source=tmp_path/'source.kicad_pcb'; source.write_text('source')
    candidate=tmp_path/'candidate.kicad_pcb'; candidate.write_text('five-open board')
    prepared=tmp_path/'revalidated.kicad_pcb'
    prepared.write_text('changed' if fault=='changed_bytes' else candidate.read_text())
    cfg=SimpleNamespace(board='test',dir=str(tmp_path),pins={},
        params={'automatic_pin_escape_tier':True})
    baseline=grade(source,opens=6)
    baseline['incumbent_identity']=dict(sha256=pipeline.sha256_file(source),
                                       artifacts=pipeline._artifact_rows([source]))
    proposed=grade(candidate,opens=5)
    proposed['candidate_origin']='proposal' if fault=='other_origin' else 'route_residual_resume'
    monkeypatch.setattr(pipeline,'_route_params_for_board',lambda *a:cfg.params)
    monkeypatch.setattr(pipeline,'_grade_route_incumbent',lambda *a,**k:baseline)
    monkeypatch.setattr(pipeline,'_resume_route_residuals',lambda *a,**k:
                        (proposed,dict(skip_global=True)))
    monkeypatch.setattr(pipeline,'_recover_route_checkpoints',lambda *a,**k:([],{}))
    monkeypatch.setattr(checkpoint,'preservation',lambda *a,**k:placement_proof())
    monkeypatch.setattr(budget,'optional_work_admission',lambda *a,**k:dict(start=fault!='unfunded'))
    monkeypatch.setattr(pipeline,'_copy_sidecars',lambda *a,**k:[])
    monkeypatch.setattr(pipeline,'_admit_incumbent_finish',lambda result,*a,**k:
                        (result,dict(admitted=False)))
    monkeypatch.setenv('CEC_DIMENSION_REPAIR','0')
    monkeypatch.setenv('CEC_FAB_REPAIR','0')
    with mock.patch.object(admission,'prepare',return_value=dict(
            ok=fault!='physical',board=str(prepared))) as verify, \
         mock.patch.object(synth,'route_oracle_grade') as global_route:
        result=pipeline._route_stage(source,tmp_path/'out',cfg,passes=1,opt=1,
                                     seed=23,timeout=10,thermal='lazy')
    assert result['unconnected'] == (5 if fault=='none' else 6)
    assert verify.call_count == (0 if fault in ('unfunded','other_origin') else 1)
    global_route.assert_not_called()
    assert source.read_text()=='source'
    assert json.loads(next((tmp_path/'out').glob('*-preservation.json')).read_text())['ok'] is False

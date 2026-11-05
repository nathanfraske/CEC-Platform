import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import cec_synth_pipeline as synth


@pytest.mark.parametrize('net',['ANY_RAIL','/path/renamed_supply'])
def test_located_bridge_exception_survives_without_state_file(net):
    import cec_slab_pour
    from cec_completion_evidence import power_planner_failures
    exc=cec_slab_pour.BridgeSearchRefused(net,{'searches':9},
        dict(required_vias=3,available_vias=1,reason='bounded_field_search'))
    row=synth._priority_power_exception_feedback(exc,[dict(net=net)])
    assert row['refused_nets']==[net]
    assert power_planner_failures(dict(candidates=[dict(compile_failure=row)]))[net][
        'planner_bottleneck']['bottleneck']['required_vias']==3


def test_exception_text_is_never_parsed_or_unknown_net_promoted():
    assert synth._priority_power_exception_feedback(RuntimeError('RAIL failed'),[dict(net='RAIL')])=={}
    exc=RuntimeError('irrelevant');exc.evidence=dict(kind='native',net='UNKNOWN')
    assert synth._priority_power_exception_feedback(exc,[dict(net='RAIL')])=={}


def test_compiler_reorders_after_typed_refusal_then_exactly_admits(tmp_path,monkeypatch):
    import pcbnew,cec_fr,cec_fab_profile,cec_pour_plan,cec_slab_pour
    monkeypatch.setenv('CEC_POURFIRST_STATE','')
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda p:object())
    monkeypatch.setattr(cec_fab_profile,'enabled_copper_layers',lambda b:['F.Cu'])
    monkeypatch.setattr(cec_pour_plan,'power_layer_order',lambda:['F.Cu'])
    monkeypatch.setattr(cec_fr,'settle_generated_power_artifact',lambda *a:{'converged':True})
    monkeypatch.setattr(cec_fr,'copy_project_sidecars',lambda *a:None)
    attempts=[]
    def compile_candidate(source,pours,state_path,out_board_path,**kw):
        order=[p['net'] for p in pours];attempts.append(order)
        if order[0]!='NARROW_LANDING':
            raise cec_slab_pour.BridgeSearchRefused('NARROW_LANDING',{},dict(required_vias=3,available_vias=1))
        Path(out_board_path).write_bytes(b'admitted copper')
        return dict(frozen_nets=order,solver={})
    monkeypatch.setattr(synth,'_compile_post_priority_power_candidate',compile_candidate)
    monkeypatch.setattr(synth,'_admit_priority_power_candidate_isolated',
        lambda *a:dict(passed=True,exact_after=dict(drc=0,unconnected=4)))
    result=synth._compile_post_priority_power_state(str(tmp_path/'source'),
        [dict(net='ROOMY'),dict(net='NARROW_LANDING')],str(tmp_path/'out.json'),str(tmp_path/'out.kicad_pcb'))
    assert attempts==[['ROOMY','NARROW_LANDING'],['NARROW_LANDING','ROOMY']]
    assert result['exact_admission']['passed']
    assert result['candidate_selection']['selected_feedback_round']==1
    assert result['candidate_selection']['candidates'][0]['retry_reason']=='compile_no_path_first'

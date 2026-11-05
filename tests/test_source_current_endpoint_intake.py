from copy import deepcopy
from unittest import mock
import pytest
import pcbnew
import cec_source_current_endpoint_intake as intake
import cec_current_topology as topology
import cec_board_policy as policy
import cec_declared_current_endpoints as endpoints
from test_declared_current_endpoints import fixture


def receive(board, declaration, current, *, existing=None):
    # Native binder remains real. Only source policy/current providers are
    # synthetic: no display value, pad coordinate or connector spelling grants
    # authority. The integration provider follows production conflict semantics.
    declarations=[declaration]
    def domains(_board, board_hint):
        assert board_hint=='SYNTHETIC_POLICY'
        return endpoints.bind(_board,declarations,lambda _net:current,existing=existing)
    with mock.patch.object(policy,'params',return_value={
            'current_endpoint_contracts':declarations}), \
         mock.patch.object(topology,'board_current_domains',side_effect=domains), \
         mock.patch.object(topology,'current_contract_for_net',return_value=current):
        return intake.check(board,'SYNTHETIC_POLICY')


@pytest.mark.parametrize('variant',range(4))
def test_real_native_parts_all_pins_and_existing_budget_bind_without_route_claim(variant):
    b,net,refs,items,d,current=fixture(variant=variant)
    before=deepcopy(d),deepcopy(current)
    result=receive(b,d,current)
    assert result['ok'] and result['bound_nets']==[net]
    assert result['witnesses'][net]['existing_current_contract']==current
    assert result['witnesses'][net]['native_endpoints']['sources'][0]['pins']==['A','B']
    assert not result['current_path_qualified'] and not result['thermal_qualified']
    assert not result['physical_release'] and not result['new_current_or_margin_inferred']
    assert before==(d,current)


@pytest.mark.parametrize('fault', ['selected_mpn','selected_fpid','policy_mpn',
    'policy_fpid','policy_pin','actual_pin','actual_net','declared_net',
    'unknown_budget','zero_budget','margin_relaxation','malformed_policy','conflict'])
def test_changed_part_pin_net_unknown_budget_and_policy_refuse_early(fault):
    b,net,refs,items,d,current=fixture();fp=items[refs[0]];existing=None
    if fault=='selected_mpn':fp.SetField('MPN','OTHER')
    elif fault=='selected_fpid':fp.SetFPID(pcbnew.LIB_ID('Other','source'))
    elif fault=='policy_mpn':d['sources'][0]['mpn']='STALE'
    elif fault=='policy_fpid':d['sources'][0]['footprint']='Other:stale'
    elif fault=='policy_pin':d['sources'][0]['pins']=['A']
    elif fault=='actual_pin':list(fp.Pads())[0].SetNumber('OTHER')
    elif fault=='actual_net':list(fp.Pads())[0].SetNet(b.FindNet('GND'))
    elif fault=='declared_net':d['net']='/MISSING'
    elif fault=='unknown_budget':current=None
    elif fault=='zero_budget':current['amps']=0
    elif fault=='margin_relaxation':current['geometry_margin']=.99
    elif fault=='malformed_policy':d['amps']=99
    elif fault=='conflict':existing={net:dict(complete=True,amps=.75,
        source_refs=('DIFFERENT',),sink_refs=(refs[1],))}
    result=receive(b,d,current,existing=existing)
    assert not result['ok'] and result['reason'] and not result['neutral']
    assert not result['current_path_qualified'] and not result['physical_release']


def test_no_declarations_neutral_without_native_or_current_inspection():
    with mock.patch.object(policy,'params',return_value={}), \
         mock.patch.object(topology,'board_current_domains',side_effect=AssertionError), \
         mock.patch.object(topology,'current_contract_for_net',side_effect=AssertionError), \
         mock.patch.object(endpoints,'bind',side_effect=AssertionError):
        result=intake.check(object(),'UNKNOWN_BUT_UNDECLARED')
    assert result['ok'] and result['neutral'] and result['declaration_count']==0


def test_conflicting_current_policy_environment_refuses_before_native_binding(monkeypatch):
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT','DIFFERENT_POLICY')
    with mock.patch.object(policy,'params',return_value={
            'current_endpoint_contracts':[{'not':'schema admission'}]}), \
         mock.patch.object(policy,'policy_path',side_effect=lambda hint:hint), \
         mock.patch.object(topology,'board_current_domains',side_effect=AssertionError):
        result=intake.check(object(),'ACTUAL_SOURCE_POLICY')
    assert not result['ok'] and result['reason']=='declared_current_endpoint_policy_identity_conflict'


@pytest.mark.parametrize('declaration', [None,{},False,'schema-only'])
def test_invalid_nonempty_or_nonlist_policy_is_not_neutral(declaration):
    with mock.patch.object(policy,'params',return_value={
            'current_endpoint_contracts':declaration}), \
         mock.patch.object(topology,'board_current_domains',return_value={}):
        result=intake.check(object(),'SYNTHETIC_POLICY')
    assert not result['ok'] and not result['neutral']


@pytest.mark.parametrize('endpoint_ok',[False,True])
def test_full_source_intake_preserves_original_gates_and_hoists_endpoint_result(
        tmp_path,monkeypatch,endpoint_ok):
    import importlib.util,pathlib
    import cec_full_pipeline as production
    import cec_constraints,cec_beta_electrical_audit,cec_generalization_gate
    from cec_synth_pipeline import Config
    staged=pathlib.Path(__file__).parents[1]/'scripts/cec_full_pipeline.py'
    spec=importlib.util.spec_from_file_location('staged_endpoint_full_pipeline',staged)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'ROOT',production.ROOT)
    monkeypatch.setattr(module,'_project_rule_authority_delta',lambda *a:{'ok':True})
    old_intake=mock.Mock(return_value={'ok':True})
    monkeypatch.setattr(cec_constraints,'intake_gate',old_intake)
    monkeypatch.setattr(cec_generalization_gate,'audit',lambda *a:{'ok':True})
    monkeypatch.setattr(cec_beta_electrical_audit,'audit',lambda *a:{'findings':[]})
    endpoint=mock.Mock(return_value={'ok':endpoint_ok,'current_path_qualified':False})
    monkeypatch.setattr(intake,'check',endpoint)
    board,_,_,_,_,_=fixture();path=tmp_path/'input.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    result=module._source_intake(Config.load('eps-8pin-rev3'),path,
        tmp_path/'report.json',allow_derived_input=True)
    endpoint.assert_called_once();old_intake.assert_called_once()
    assert result['declared_current_endpoints']['ok'] is endpoint_ok
    assert result['ok'] is endpoint_ok and result['intake']['ok']
    assert result['electrical_source_audit']['ok'] and result['generalization_gate']['ok']
    assert result['route_geometry_deferred']  # Never defers this identity gate.

import json
import pytest
from cec_hardware_qualification import evaluate


def test_fitted_prototype_blocks_release_but_absent_hardware_does_not(tmp_path):
    path = tmp_path / 'status.json'
    path.write_text(json.dumps({'release_status': 'PROTOTYPE_BLOCKED',
                                'gates': {'fit': {'passed': False}}}))
    requirement = {'id': 'test-interface', 'footprints': ['PrototypeConnector'],
                   'status_path': path, 'required_gates': ['fit'],
                   'verify_candidate': lambda: {'ok': True}}
    assert not evaluate(['PrototypeConnector'], [requirement])['ok']
    assert evaluate(['QualifiedResistor'], [requirement])['ok']
    path.write_text(json.dumps({'release_status': 'RELEASED',
                                'gates': {'fit': {'passed': True}}}))
    assert evaluate(['PrototypeConnector'], [requirement])['ok']
    requirement['verify_candidate'] = lambda: {'ok': False, 'reason': 'actual board does not fit'}
    assert not evaluate(['PrototypeConnector'], [requirement])['ok']


def test_missing_qualification_file_is_not_a_pass(tmp_path):
    r = {'id': 'test', 'footprints': ['Prototype'], 'status_path': tmp_path/'absent.json',
         'required_gates': ['fit'], 'verify_candidate': lambda: {'ok': True}}
    assert not evaluate(['Prototype'], [r])['ok']


def test_unqualified_deadbug_pair_withholds_fab_not_unrelated_board():
    from cec_mezz_contract import hardware_release_requirements
    r=hardware_release_requirements('candidate.kicad_pcb','beta/hub-standard-rev2/hub-standard-rev2.kicad_sch')
    assert not evaluate(['PinSocket_2x03_P2.54mm_Vertical'],r)['ok']
    assert hardware_release_requirements('candidate.kicad_pcb','beta/pcie-8pin-2port/pcie.kicad_sch')==[]


def test_pass_flag_without_bound_pair_does_not_release(tmp_path):
    from cec_stack_fit_screen import qualify_stack
    assert not qualify_stack({'fit':{'ok':True,'qualified':True}},['fit'])['release_accepted']

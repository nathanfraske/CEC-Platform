import importlib.util
from pathlib import Path

import pcbnew
import pytest
import cec_fr as fr
from test_local_pofv_ownership import fixture

spec = importlib.util.spec_from_file_location('pofv_metadata',
    Path(__file__).resolve().parents[1]/'ops/cec_reconcile_pofv_membership.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def rule_text():
    return (fr.LOCAL_POFV_SIGNAL_VIA_RULE_BEGIN + '\n# Existing manufacturing rule\n'
        '(rule "CEC local POFV signal via"\n'
        '(condition "A.Type == \'Via\' && A.memberOfGroup(\'%s\')")\n'
        '(constraint via_diameter (min 0.300mm))\n'
        '(constraint hole_size (min 0.200mm))\n'
        '(constraint annular_width (min 0.050mm)))\n' % fr.LOCAL_POFV_SIGNAL_VIA_GROUP
        + fr.LOCAL_POFV_SIGNAL_VIA_RULE_END)


def test_existing_rule_with_comment_is_parsed_without_rewriting():
    assert repair.existing_rule_geometry(rule_text()) == dict(
        via_diameter=.3, hole_size=.2, annular_width=.05)


@pytest.mark.parametrize('fault', ['absent', 'duplicate', 'scope', 'missing_floor', 'unknown_units'])
def test_no_invented_or_broadened_rule(fault):
    text = rule_text()
    if fault == 'absent': text = ''
    elif fault == 'duplicate': text += text
    elif fault == 'scope': text = text.replace(fr.LOCAL_POFV_SIGNAL_VIA_GROUP, 'OTHER_GROUP')
    elif fault == 'missing_floor': text = text.replace('(constraint hole_size (min 0.200mm))', '')
    else: text = text.replace('0.200mm', '0.200')
    with pytest.raises(ValueError): repair.existing_rule_geometry(text)


@pytest.mark.parametrize('fault', [None, 'unlocked', 'floating', 'wrong_layer', 'partial_overlap',
                                  'other_owner', 'not_filled', 'not_capped', 'no_board_fill'])
def test_native_geometry_process_and_existing_ownership_are_mandatory(fault):
    options = dict(offset=(0, 0), connected=False)
    if fault == 'floating': options.update(offset=(1, 0))
    if fault == 'wrong_layer': options.update(offset=(.625, 0), connected=True, layer=pcbnew.B_Cu)
    if fault == 'partial_overlap': options.update(offset=(.4, 0), size=(.7, .7))
    board, via = fixture(**options)
    board.GetDesignSettings().m_FillVias = True
    board.GetDesignSettings().m_CapVias = True
    via.SetLocked(fault != 'unlocked')
    if fault == 'other_owner':
        group = pcbnew.PCB_GROUP(board); group.SetName('OTHER_OWNER'); board.Add(group); group.AddItem(via)
    if fault == 'not_filled': via.SetFillingMode(pcbnew.FILLING_MODE_NOT_FILLED)
    if fault == 'not_capped': via.SetCappingMode(pcbnew.CAPPING_MODE_NOT_CAPPED)
    if fault == 'no_board_fill': board.GetDesignSettings().m_FillVias = False
    ok, _ = repair.eligible(board, via, repair.existing_rule_geometry(rule_text()), {})
    assert ok is (fault is None)


@pytest.mark.parametrize('fault', [None, 'via_geometry', 'setup', 'new_member', 'removed_member', 'unknown_field'])
def test_literal_receiving_allows_only_declared_existing_group_extension(tmp_path, fault):
    source = '(kicad_pcb (version 1) (setup (filling yes)) (via (size 0.35) (uuid "v")) (via (size 0.35) (uuid "old")) (group "local" (uuid "g") (members "old")))'
    candidate = source.replace('(members "old")', '(members "old" "v")')
    if fault == 'via_geometry': candidate = candidate.replace('(size 0.35)', '(size 0.36)', 1)
    elif fault == 'setup': candidate = candidate.replace('(filling yes)', '(filling no)')
    elif fault == 'new_member': candidate = candidate.replace('"old" "v"', '"old" "another"')
    elif fault == 'removed_member': candidate = candidate.replace('"old" "v"', '"v"')
    elif fault == 'unknown_field': candidate = candidate.replace('(size 0.35)', '(size 0.35) (unknown-field yes)', 1)
    a, b = tmp_path/'source.kicad_pcb', tmp_path/'candidate.kicad_pcb'
    a.write_text(source); b.write_text(candidate)
    if fault:
        with pytest.raises(ValueError): repair.literal_group_extension(a, b, 'g', {'v'})
    else:
        result = repair.literal_group_extension(a, b, 'g', {'v'})
        assert result['all_native_geometry_and_fields_literal']
        assert result['unchanged_native_uuid_blocks'] == 2

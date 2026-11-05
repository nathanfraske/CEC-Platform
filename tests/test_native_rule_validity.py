"""A successful CLI job must not disguise rejected custom design rules."""
import os
from pathlib import Path

import pytest

import cec_native_rule_validity as rules
import cec_native_drc_runner as runner


@pytest.mark.parametrize('newline',['\n','\r\n','\r'])
@pytest.mark.parametrize('net',["/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM",'any supply','日本語 supply'])
def test_multiline_condition_repair_preserves_literals_and_every_other_byte(newline,net):
    before='# keep me\n(version 1)\n(rule "arbitrary rule"\n (condition "A.NetClass == \'Power\''+newline+"  && A.NetName != '"+net+"'\")\n (constraint track_width (min 0.5mm)))\n"
    result=rules.normalize_conditions(before)
    expected=before.replace("'Power'"+newline+'  &&',"'Power' &&")
    assert result['text']==expected and result['changed_conditions']==1
    assert result['formatting_only'] and not result['native_parser_validity_proved']
    received=rules.normalize_conditions(result['text'])
    assert received['changed_conditions']==0 and received['semantic_sha256']==result['semantic_sha256']


@pytest.mark.parametrize('condition',[
    "A.memberOfGroup('any group') && A.Type == 'Via'",
    "(A.Pad_Number == 'A4' || A.Pad_Number == 'B12')",
    " A.NetName == 'a   b'  ",
    "A.NetName == 'back\\\\slash'",
])
def test_single_line_conditions_are_byte_identical(condition):
    text='(version 1)\n(rule x (condition "'+condition+'") (constraint hole_size (min 0.2mm)))'
    result=rules.normalize_conditions(text)
    assert result['text']==text and result['changed_conditions']==0


def test_comments_and_quoted_rule_names_are_not_mistaken_for_conditions():
    text='# (condition "not real\n# foo")\n(version 1)\n(rule "condition" (constraint track_width (min 0.2mm)))\n'
    result=rules.normalize_conditions(text)
    assert result['condition_count']==0 and result['text']==text


@pytest.mark.parametrize('text',[
    '(rule "multiline\nrule" (constraint track_width (min 0.2mm)))',
    '(rule x (condition "A.NetName == \'inside\nliteral\'"))',
    '(rule x (condition A.Type))',
    '(rule x (condition "A.Type == \'Via"))',
    '(rule x (condition "A.NetName == \'bad\\x12\'"))',
    '(rule x (condition "unterminated))',
    '(rule x (condition "A.Type == \'Via\'")',
    ')(version 1)',None,True,
])
def test_ambiguous_or_nonformatting_repair_refuses(text):
    with pytest.raises(ValueError):rules.normalize_conditions(text)


def test_rule_file_and_parser_have_explicit_bounds():
    with pytest.raises(ValueError):rules.normalize_conditions('x'*(rules.MAX_RULE_BYTES+1))
    with pytest.raises(ValueError):rules.normalize_conditions('('*257+')'*257)
    with pytest.raises(ValueError):rules.normalize_conditions('() '*(rules.MAX_TOKENS//2+1))


ENGINE='/verified/producer/pcbnew/_pcbnew.kiface'
OBSERVATION='''CEC_NATIVE_THROW
#0 NOTIFICATIONS_MANAGER::Load()
CEC_NATIVE_THROW_END
CEC_NATIVE_RULE_ENGINE_INIT
CEC_NATIVE_RULE_FILE_LOAD
CEC_NATIVE_RULES_REACHED_TESTS
0x00000000 0x000000ff Yes (*) /verified/producer/pcbnew/_pcbnew.kiface
'''


def test_native_probe_ignores_only_a_complete_preinit_startup_exception():
    result=rules.assess_probe(OBSERVATION,engine=ENGINE)
    assert result['ok'] and result['complete'] and result['custom_rules_loaded_and_compiled']
    assert not result['native_rules_fallback'] and not result['native_tests_started']
    assert not result['release_authority'] and not result['source_modified']


@pytest.mark.parametrize('change',[
    lambda s:s.replace('CEC_NATIVE_RULE_FILE_LOAD\n',''),
    lambda s:s.replace('CEC_NATIVE_RULE_ENGINE_INIT\n',''),
    lambda s:s.replace('CEC_NATIVE_RULES_REACHED_TESTS\n',''),
    lambda s:s.replace('CEC_NATIVE_RULE_FILE_LOAD\n','CEC_NATIVE_RULE_FILE_LOAD\n'*2),
    lambda s:s.replace('CEC_NATIVE_RULE_ENGINE_INIT\nCEC_NATIVE_RULE_FILE_LOAD\n','CEC_NATIVE_RULE_FILE_LOAD\nCEC_NATIVE_RULE_ENGINE_INIT\n'),
    lambda s:s.replace('CEC_NATIVE_RULE_FILE_LOAD\n','CEC_NATIVE_RULE_FILE_LOAD\nCEC_NATIVE_THROW\n#0 DRC_RULES_PARSER::Parse()\nCEC_NATIVE_THROW_END\n'),
    lambda s:s.replace('Yes (*)','No'),
    lambda s:s.replace(ENGINE,'/unverified/engine'),
    lambda s:s.replace('CEC_NATIVE_THROW_END\n',''),
])
def test_unobserved_silently_rejected_or_ambiguous_native_rules_refuse(change):
    with pytest.raises(ValueError):rules.assess_probe(change(OBSERVATION),engine=ENGINE)


def test_nonzero_probe_exit_and_output_saturation_refuse():
    with pytest.raises(ValueError):rules.assess_probe(OBSERVATION,engine=ENGINE,returncode=1)
    with pytest.raises(ValueError):rules.assess_probe('x'*(rules.MAX_PROBE_BYTES+1),engine=ENGINE)


def test_malformed_rules_are_rejected_before_a_native_report_is_written(tmp_path):
    source=tmp_path/'generic.kicad_pcb';source.write_text('(kicad_pcb)')
    custom=source.with_suffix('.kicad_dru');custom.write_text('(version 1)\n(rule x (condition "A.Type\n == \'Via\'"))')
    original=custom.read_bytes()
    result=runner.run(source,tmp_path/'report.json')
    assert not result['ok'] and not result['complete'] and result['errors']
    assert custom.read_bytes()==original and not (tmp_path/'report.json').exists()


def _board(tmp_path,rule_text):
    import pcbnew
    import cec_field_coupling as field
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for start,end in [((0,0),(20,0)),((20,0),(20,20)),((20,20),(0,20)),((0,20),(0,0))]:
        shape=pcbnew.PCB_SHAPE(board);shape.SetShape(pcbnew.SHAPE_T_SEGMENT);shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetStart(pcbnew.VECTOR2I_MM(*start));shape.SetEnd(pcbnew.VECTOR2I_MM(*end));board.Add(shape)
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(10,10));via.SetWidth(pcbnew.FromMM(.6));via.SetDrill(pcbnew.FromMM(.3))
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    source=tmp_path/'arbitrary.kicad_pcb';field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_dru').write_text(rule_text)
    return source


def test_stripped_stock_custom_rule_reports_require_an_observable_verified_producer(tmp_path):
    import cec_toolchain as toolchain
    if not toolchain.have_kicad_cli():pytest.skip('native CLI required')
    source=_board(tmp_path,'(version 1)\n(rule x (condition "A.Type == \'Via\'") (constraint via_diameter (min 0.8mm)))')
    result=runner.run(source,tmp_path/'report.json')
    assert not result['ok'] and not result['complete']
    assert any('custom_rule_validation_requires_verified_observable_native_engine' in x for x in result['errors'])
    assert not (tmp_path/'report.json').exists()


@pytest.mark.parametrize('invalid',[False,True])
def test_actual_native_loader_rejects_fallback_and_enforces_valid_custom_rule(tmp_path,invalid):
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('explicit verified native reporting build required')
    text='(version 1)\n(rule x (condition "A.Type == \'Via\'") (constraint '+('invented_constraint' if invalid else 'via_diameter')+' (min 0.8mm)))'
    source=_board(tmp_path,text)
    family={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    result=runner.run(source,tmp_path/'report.json',reporting_build=Path(build))
    if invalid:
        assert not result['ok'] and not result['complete'],result
        assert any('silent_fallback_forbidden' in x for x in result['errors']),result
        assert not (tmp_path/'report.json').exists()
    else:
        import json
        assert result['ok'] and result['complete'] and result['native_rules_validation']['custom_rules_loaded_and_compiled'],result
        report=json.loads((tmp_path/'report.json').read_text())
        assert any(row['type']=='via_diameter' and 'x' in row['description'] for row in report['violations'])
    assert all((tmp_path/name).read_bytes()==content for name,content in family.items())

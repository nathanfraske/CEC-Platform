"""No caller assertion can stand in for complete caption-only input identity."""
import pytest
import cec_root_caption_seating as op
from test_root_caption_seating import fixture


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0,37,90,180])
def test_whole_saved_and_native_query_inputs_equal_except_exact_reviewed_xy(tmp_path,back,angle):
    source,_,args=fixture(tmp_path,back,angle);proposal=op.plan(source,**args)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,proposal)
    before=[p.read_bytes()for p in(source,child)]
    report=op.query_input_identity(source,child,proposal)
    assert all(report[k]is True for k in('ok','complete','comparison_complete','same_material',
        'all_nontranslation_raw_and_native_inputs_equal')),report
    assert report['independent_translation_receiving']['whole_saved_second_native_roundtrip_stable']
    assert not report['mutation_authority']and not report['full_kelvin_qualification']
    assert not report['release_authority']and before==[p.read_bytes()for p in(source,child)]


@pytest.mark.parametrize('fault',['no_scope','incomplete_scope','wrong_text','extra_raw'])
def test_query_identity_is_not_a_bare_material_or_print_waiver(tmp_path,monkeypatch,fault):
    source,_,args=fixture(tmp_path);proposal=op.plan(source,**args)
    child=op.force._copy_family(source,tmp_path/'child');op.write_private(source,child,proposal)
    if fault in('no_scope','incomplete_scope'):
        monkeypatch.setattr(op,'receive',lambda *a:dict(ok=True,complete=fault!='incomplete_scope',
            translation_only=fault!='no_scope',whole_saved_second_native_roundtrip_stable=True,
            exact_reviewed_caption_translation_and_readable_floor_only=fault!='no_scope'))
    elif fault=='wrong_text':proposal['expected_text']='another caption'
    else:
        text=op.raw.raw_text(child);op.raw.write_raw(child,text.replace('(kicad_pcb',
            '(kicad_pcb (property "unowned metadata" "changed")',1))
        # Even a malicious positive producer cannot override the separate
        # complete raw/native query-input comparison.
        monkeypatch.setattr(op,'receive',lambda *a:dict(ok=True,complete=True,translation_only=True,
            whole_saved_second_native_roundtrip_stable=True,
            exact_reviewed_caption_translation_and_readable_floor_only=True))
    assert not op.query_input_identity(source,child,proposal)['ok']

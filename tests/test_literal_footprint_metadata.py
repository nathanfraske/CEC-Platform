"""Literal metadata producer scope and native IO; not board qualification."""
import pytest
import cec_literal_footprint_metadata as op
import cec_component_jumper_metadata as metadata

SOURCE='''(kicad_pcb
 (version 20250101)
 (footprint "arbitrary:one"
  (property "Reference" "Z471" (at 1.00 2))
  (property "MPN" "" (effects (font (size 1 1)) (hide yes)))
  (pad "1" smd rect (at 1.000 2) (layers "F.Cu")))
 (footprint "unrelated:two" (property "Reference" "X42")
   (property "opaque" "a ( quoted ) phrase \\\""))
 (property "unknown root field" " keep  exact ")
)'''


def test_add_metadata_preserves_other_literal_subtrees_and_all_existing_source_tokens():
    after=['jumper_pad_groups',['"1"','"6"'],['"3"','"4"']]
    value=op.splice(SOURCE,{'Z471':[dict(tag='jumper_pad_groups',before=None,after=after)]})
    assert SOURCE[SOURCE.index(' (footprint "unrelated:two"'):] == value[value.index(' (footprint "unrelated:two"'):]
    assert '(at 1.000 2)' in value and '" keep  exact "' in value
    fp=metadata._footprints(metadata._parse(value))['Z471']
    assert metadata._one(fp,'jumper_pad_groups')==after


def test_property_replacement_and_metadata_insert_have_exact_complete_AST():
    fp=metadata._footprints(metadata._parse(SOURCE))['Z471']
    before=op._fields(fp,'property','MPN')[0]
    after=[*before[:2],'"selected-part"',*before[3:]]
    changes=[dict(tag='property',name='MPN',before=before,after=after),
             dict(tag='duplicate_pad_numbers_are_jumpers',before=None,after=['duplicate_pad_numbers_are_jumpers','no'])]
    result=op.splice(SOURCE,{'Z471':changes})
    assert '(pad "1" smd rect (at 1.000 2)' in result
    assert op._fields(metadata._footprints(metadata._parse(result))['Z471'],'property','MPN')[0]==after


def test_semantically_unchanged_requested_field_keeps_its_original_whitespace():
    node=op._fields(metadata._footprints(metadata._parse(SOURCE))['Z471'],'property','MPN')[0]
    assert op.splice(SOURCE,{'Z471':[dict(tag='property',name='MPN',before=node,after=node)]})==SOURCE


@pytest.mark.parametrize('text',[SOURCE[:-1],')'+SOURCE,SOURCE+' stray','',SOURCE.replace('(version','(version "unterminated')])
def test_malformed_or_uncovered_literal_is_refused(text):
    with pytest.raises(ValueError):op.splice(text,{})


@pytest.mark.parametrize('edit',[
    {'missing':[]}, {'Z471':[dict(tag='pad',before=None,after=['pad','"2"'])]},
    {'Z471':[dict(tag='property',name='MPN',before=None,after=['property','"MPN"','"a"'])]},
    {'Z471':[dict(tag='property',name='MPN',before=None,after=['property','"Other"','"a"'])]},
    {'Z471':[dict(tag='jumper_pad_groups',before=None,after=['jumper_pad_groups']),dict(tag='jumper_pad_groups',before=None,after=['jumper_pad_groups'])]},
])
def test_unowned_or_contradictory_field_requests_are_refused(edit):
    with pytest.raises(ValueError):op.splice(SOURCE,edit)


@pytest.mark.parametrize('face',['F','B'])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_real_saved_metadata_producer_keeps_every_unrelated_literal(tmp_path,face,turn):
    from test_component_jumper_metadata import board_fixture, exported
    path=board_fixture(tmp_path,face,turn)
    before=path.read_text()
    def inventory(text):
        root=op._tree(text)
        result={}
        for node in root['children']:
            if node['tag']!='footprint':
                continue
            fp=metadata._parse(text[node['start']:node['end']])
            ref=metadata._text(op._fields(fp,'property','Reference')[0][2])
            result[ref]=(node,text[node['start']:node['end']])
        return result
    old=inventory(before)
    contracts=metadata.from_export(exported())
    assert metadata.apply_saved(path,contracts)==['X72']
    after=path.read_text()
    new=inventory(after)
    assert old.keys()==new.keys()
    assert new['H57'][1]==old['H57'][1]
    # Each original nonmetadata subtree, including pad and field numeric
    # spelling/indentation, remains byte-for-byte, not merely AST-equal.
    for ref,(node,_) in old.items():
        before_fields=[before[s['start']:s['end']]for s in node['children']
                       if s['tag']not in metadata._FIELDS]
        node2=new[ref][0]
        after_fields=[after[s['start']:s['end']]for s in node2['children']
                      if s['tag']not in metadata._FIELDS]
        assert before_fields==after_fields
    assert metadata.apply_saved(path,contracts)==[]
    assert path.read_text()==after

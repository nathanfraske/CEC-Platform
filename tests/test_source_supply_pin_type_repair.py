"""Literal source ERC corrections never grant a routing/current allowance."""
import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import cec_source_supply_pin_type_repair as op


def fixture(mpn='INA181A2IDBVR',hierarchy=False):
    c=op.CONTRACTS[mpn]
    pins='\n'.join('(pin unspecified line (at 1 2 0) (length 2) (name "'+
        (c['name']if str(i)==c['pin']else 'other')+'") (number "'+str(i)+'"))'
        for i in range(1,c['count']+1))
    symbol='(symbol "'+('cec-vendor:'if hierarchy else '')+mpn+'" '+\
        '(property "Value" "'+mpn+'") (property "MPN" "'+mpn+'") '+\
        '(property "Footprint" "'+c['footprints'][0]+'") (symbol "unit_1_1" '+pins+'))'
    return '(kicad_sch (version 20250114) (lib_symbols '+symbol+') (uuid "retained"))'if hierarchy else '(kicad_symbol_lib (version 20250114) '+symbol+')'


@pytest.mark.parametrize('mpn',list(op.CONTRACTS))
@pytest.mark.parametrize('hierarchy',[False,True])
def test_exact_named_manufacturer_source_type_only(mpn,hierarchy):
    before=fixture(mpn,hierarchy);plan=op.plan_text(before)
    assert len(plan['changes'])==1
    assert plan['text'].count('power_in')==1
    assert op.receive_text(before,plan['text'])['all_other_bytes_exact']
    assert op.plan_text(plan['text'])['changes']==[]


@pytest.mark.parametrize('mutation',['mpn','value','package','name','number','duplicate','input','passive','output','inheritance'])
def test_wrong_source_authority_refuses(mutation):
    text=fixture()
    if mutation=='mpn':text=text.replace('(property "MPN" "INA181A2IDBVR")','(property "MPN" "INA181A2IDCKR")')
    elif mutation=='value':text=text.replace('(property "Value" "INA181A2IDBVR")','(property "Value" "INA181")')
    elif mutation=='package':text=text.replace(op.CONTRACTS['INA181A2IDBVR']['footprints'][0],'SOT-363')
    elif mutation=='name':text=text.replace('(name "VS")','(name "IN+")')
    elif mutation=='number':text=text.replace('(number "6")','(number "7")')
    elif mutation=='duplicate':text=text.replace('(number "5")','(number "6")')
    elif mutation in ('input','passive','output'):
        text=text.replace('(pin unspecified line (at 1 2 0) (length 2) (name "VS")',
            '(pin '+mutation+' line (at 1 2 0) (length 2) (name "VS")')
    elif mutation=='inheritance':text=text.replace('(property "Value"','(extends "X") (property "Value"',1)
    with pytest.raises(ValueError):op.plan_text(text)


@pytest.mark.parametrize('mutation',['geometry','uuid','whitespace','otherpin','budget'])
def test_independent_literal_receiver_rejects_other_edits(mutation):
    before=fixture(hierarchy=True);after=op.plan_text(before)['text']
    if mutation=='geometry':after=after.replace('(at 1 2 0)','(at 2 2 0)',1)
    elif mutation=='uuid':after=after.replace('retained','changed')
    elif mutation=='whitespace':after+='\n'
    elif mutation=='otherpin':after=after.replace('(name "other")','(name "renamed")',1)
    elif mutation=='budget':after=after.replace('(uuid "retained")','(uuid "retained") (property "amps" "2")')
    with pytest.raises(ValueError):op.receive_text(before,after)


def exported(mpn='INA181A2IDBVR',suffix=False):
    c=op.CONTRACTS[mpn]
    libpart=['libpart',['lib','cec-vendor'],['part',mpn],['pins',*[
        ['pin',['num',str(i)],['name',c['name']if str(i)==c['pin']else 'other'],['type','unspecified']]
        for i in range(1,c['count']+1)]]]
    node=['node',['ref','RENAMED_OWNER'],['pin',c['pin']],
        ['pinfunction',c['name']+('_'+c['pin']if suffix else '')],['pintype','unspecified']]
    comp=['comp',['ref','RENAMED_OWNER'],['value',mpn],['footprint',c['footprints'][0]],
        ['fields',['field',['name','MPN'],mpn]],['libsource',['lib','cec-vendor'],['part',mpn]]]
    before=['export',['version','E'],['design',['source','same-source'],['date','2026-10-23T07:00:00']],
        ['components',comp],['libparts',libpart],['nets',['net',['code','1'],['name','unchanged-rail'],node]]]
    after=copy.deepcopy(before)
    selected=next(p for p in op.synth._kids(op.synth._first(after[4][1],'pins'),'pin')if op.synth._val(p,'num','')==c['pin'])
    op.synth._first(selected,'type')[1]='power_in'
    op.synth._first(after[5][1][3],'pintype')[1]='power_in'
    after[2][2][1]='2026-10-23T07:00:01'
    return before,after


@pytest.mark.parametrize('mpn',list(op.CONTRACTS))
@pytest.mark.parametrize('suffix',[False,True])
def test_exported_roles_include_each_exact_instance_node_but_no_other_semantic_edit(mpn,suffix):
    a,b=exported(mpn,suffix);saved=copy.deepcopy(b);r=op.receive_netlist_types(a,b)
    assert r['ok'] and len(r['libpart_changes'])==len(r['node_changes'])==1
    assert r['all_other_export_semantics_exact']and b==saved
    assert not r['current_authority']and not r['release_authority']


@pytest.mark.parametrize('fault',['mpn','package','pinfunction','pin','node_type','lib_type','net','node_ref','duplicate','part_value'])
def test_exported_node_annotations_cannot_hide_other_pin_or_connectivity_changes(fault):
    a,b=exported();comp=b[3][1];node=b[5][1][3]
    if fault=='mpn':comp[4][1][-1]='unknown'
    elif fault=='package':comp[3][1]='different-package'
    elif fault=='pinfunction':node[3][1]='VS_5'
    elif fault=='pin':node[2][1]='5'
    elif fault=='node_type':node[4][1]='passive'
    elif fault=='lib_type':b[4][1][3][-1][-1][1]='passive'
    elif fault=='net':b[5][1][2][1]='changed-net'
    elif fault=='node_ref':node[1][1]='other-part'
    elif fault=='duplicate':b[5][1].append(copy.deepcopy(node))
    elif fault=='part_value':comp[2][1]='other-part'
    with pytest.raises(ValueError):op.receive_netlist_types(a,b)

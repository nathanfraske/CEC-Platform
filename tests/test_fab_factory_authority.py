"""Saved owner policy cannot silently waive independent factory checks."""
import hashlib
import json
from unittest import mock

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fab_check as fab


def test_project_warnings_ignores_and_exclusions_are_not_factory_waivers(tmp_path):
    path=tmp_path/'audit.kicad_pro'
    path.write_text(json.dumps({'board':{'design_settings':{
        'rule_severities':{'hole_to_hole':'ignore','silk_overlap':'warning',
                         'clearance':'error','lib_footprint_issues':'warning'},
        'drc_exclusions':['saved exclusion']}}}))
    evidence=fab._factory_project_severities(path)
    actual=json.loads(path.read_text())['board']['design_settings']
    assert actual['rule_severities']['hole_to_hole']=='error'
    assert actual['rule_severities']['silk_overlap']=='error'
    assert actual['rule_severities']['lib_footprint_issues']=='warning'
    assert actual['drc_exclusions']==[]
    assert evidence['source_exclusions_not_applied']==['saved exclusion']


def test_named_owner_exception_is_comment_only_not_factory_acceptance(tmp_path):
    path=tmp_path/'audit.kicad_dru'
    claim=dict(name='fab_qualified_owner_pad',text='''(rule fab_qualified_owner_pad
 (condition "A.memberOfFootprint('ARBITRARY')")
 (constraint hole_clearance (min 0.15mm)))''')
    fab.write_fab_dru(path,fab.profile_rules(fab.PROFILES['jlcpcb'],1.),qualified_rules=[claim])
    active='\n'.join(line for line in path.read_text().splitlines() if not line.startswith('#'))
    assert claim['name'] not in active
    assert '(constraint hole_clearance (min 0.2mm))' in active


def test_scorer_owner_filters_cannot_remove_hole_edge_or_legend_findings():
    rows=[dict(type=t,description=t) for t in
          ('hole_clearance','copper_edge_clearance','silk_overlap','via_diameter')]
    with mock.patch('cec_score.qualify_structural_violations',return_value=[]):
        result=fab.qualify_fab_drc_violations(rows,object())
    assert result==rows[:3]


@pytest.mark.parametrize('kind,count,complete',[
    ('silk_overlap',198,True),('silk_overlap',199,False),
    ('clearance',498,True),('clearance',499,False),
])
def test_native_per_type_caps_are_not_exhaustive(kind,count,complete):
    raw=dict(violations=[dict(type=kind,severity='error')]*count,unconnected_items=[])
    assert fab.native_report_completeness(raw,'10.0.5-ubuntu')['complete'] is complete


def test_unknown_native_version_and_malformed_report_fail_closed():
    empty=dict(violations=[],unconnected_items=[])
    assert not fab.native_report_completeness(empty,'11.0.0')['complete']
    assert not fab.native_report_completeness({},'10.0.5')['complete']
    assert not fab.native_report_completeness(dict(empty,unconnected_items=[{}]*499),'10.0.5')['complete']
    assert fab.blocking_count(dict(schema=2,drc_total=0,complete=False))==1


def test_native_report_version_and_remaining_ignored_checks_are_authoritative():
    empty=dict(violations=[],unconnected_items=[])
    assert not fab.native_report_completeness(dict(empty,kicad_version='11.0.0'),'10.0.5')['complete']
    result=fab.native_report_completeness(dict(empty,ignored_checks=[dict(key='hole_to_hole')]),'10.0.5')
    assert not result['complete'] and result['ignored_factory_checks']==['hole_to_hole']
    assert fab.native_report_completeness(dict(empty,ignored_checks=[dict(key='lib_footprint_issues')]),'10.0.5')['complete']


def fixture(tmp_path):
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    corners=[(0,0),(20,0),(20,20),(0,20),(0,0)]
    for a,c in zip(corners,corners[1:]):
        s=pcbnew.PCB_SHAPE(b);s.SetShape(pcbnew.SHAPE_T_SEGMENT);s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(pcbnew.VECTOR2I_MM(*a));s.SetEnd(pcbnew.VECTOR2I_MM(*c));s.SetWidth(pcbnew.FromMM(.05));b.Add(s)
    text=pcbnew.PCB_TEXT(b);text.SetLayer(pcbnew.F_SilkS);text.SetText('tiny')
    text.SetPosition(pcbnew.VECTOR2I_MM(10,10));text.SetTextSize(pcbnew.VECTOR2I_MM(.8,.8));text.SetTextThickness(pcbnew.FromMM(.12));b.Add(text)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ARBITRARY');b.Add(fp)
    hole=pcbnew.PAD(fp);hole.SetNumber('');hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE);hole.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    hole.SetDrillSize(pcbnew.VECTOR2I_MM(.5,.5));hole.SetPosition(pcbnew.VECTOR2I_MM(5.6651,5));fp.Add(hole)
    land=pcbnew.PAD(fp);land.SetNumber('1');land.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    land.SetShape(pcbnew.PAD_SHAPE_RECT);land.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.F_Mask);land.SetLayerSet(layers)
    land.SetPosition(pcbnew.VECTOR2I_MM(5,5));fp.Add(land)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),b,True)
    path.with_suffix('.kicad_pro').write_text(json.dumps({'board':{'design_settings':{
        'rule_severities':{key:'ignore' for key in fab.FACTORY_DRC_TYPES},
        'rules':{'min_hole_clearance':.15,'min_silk_text_height':.5,'min_silk_text_thickness':.05}}}}))
    path.with_suffix('.kicad_dru').write_text('''(version 1)
(rule fab_qualified_owner_pad
 (condition "A.memberOfFootprint('ARBITRARY') && B.memberOfFootprint('ARBITRARY')")
 (constraint hole_clearance (min 0.15mm)))''')
    return path


def test_fresh_real_cli_reports_hidden_legend_and_unqualified_npth_floor(tmp_path):
    path=fixture(tmp_path)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    evidence={}
    rows,unconnected=fab.run_fab_drc(str(path),fab.profile_rules(fab.PROFILES['jlcpcb'],1.),evidence=evidence)
    assert rows is not None
    kinds={row['type'] for row in rows}
    assert 'hole_clearance' in kinds,evidence
    assert 'text_height' in kinds,evidence
    assert 'text_thickness' in kinds,evidence
    assert evidence['completeness']['complete'],evidence
    assert all(row['severity']=='error' for row in rows if row['type'] in fab.FACTORY_DRC_TYPES)
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}


def test_schema_aggregate_keeps_known_findings_and_unknown_blocking(tmp_path):
    path=fixture(tmp_path)
    def native_check(board,r,*,evidence):
        evidence['completeness']=dict(complete=False,reason='native_report_cap_reached')
        return [],[]
    with mock.patch.object(fab,'run_fab_drc',side_effect=native_check), mock.patch.object(fab,'artifact_scan',return_value={}):
        report=fab.check(str(path),'jlcpcb',1.)
    assert report['schema']==2 and not report['complete']
    assert report['drc']['factory_native_legend_dimension']>=2
    assert report['factory_status']=='blocked'
    assert 'native_report_cap_reached' in report['error']
    assert report['input_identity_unchanged'] is True
    assert fab.blocking_count(report)>report['drc_total']

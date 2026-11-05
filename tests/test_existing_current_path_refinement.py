"""Existing current capacity is not permission to lower a width or a rule."""
import copy,json
import runpy,sys
from pathlib import Path
import pcbnew
import pytest
import cec_existing_current_path_refinement as repair
import cec_force_current as force
import cec_field_coupling as field
import cec_native_drc_runner as native
from test_lastmile import _board
from test_field_proposals import track


def case(tmp_path,monkeypatch,quarter=0,back=False):
    net='/UNFAMILIAR/CURRENT';b=_board([(5,10,net),(10,15,net)],edge=(-25,-25,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    old=[track(b,net,a,z,width=.2) for a,z in [((5,10),(10,10)),((10,10),(10,15))]]
    for t in old:t.SetLocked(True)
    ghosts=[]
    for xy in ((5,10),(9.6,10),(10,10.4),(10,15)):
        q=pcbnew.PCB_TRACK(b);q.SetStart(pcbnew.VECTOR2I_MM(*xy));q.SetEnd(q.GetStart());ghosts.append(q)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*ghosts]:
        if quarter:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    ids=[force._uid(t) for t in old];points=[list(t.GetStart()) for t in ghosts]
    original=[list(q) for q in repair.chains._chain(old)]
    if points[0]!=original[0]:points.reverse()
    contract=dict(net=net,required_by_layer_mm={'F.Cu':.15,'B.Cu':.15},routing_layers=['F.Cu','B.Cu'],
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    domain=dict(net=net,complete=True,source_refs=['source'],sink_refs=['sink'])
    monkeypatch.setattr(repair.full.topology,'route_width_contracts',lambda *a,**k:{net:copy.deepcopy(contract)})
    monkeypatch.setattr(repair.full.topology,'board_current_domains',lambda *a,**k:{net:copy.deepcopy(domain)})
    monkeypatch.setattr(repair.fr,'_project_netclass_resolver',lambda *a,**k:lambda n:dict(track_width=1.,clearance=.2,via_diameter=.6,via_drill=.3))
    return source,dict(board_hint='opaque',retired_track_uuids=ids,points_nm=points,allow_locked_source=True),contract,domain


def make(source,tmp_path,proposal):
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child);return child


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_native_current_path_finishing_keeps_width_budget_and_higher_preference(tmp_path,monkeypatch,quarter,back):
    source,args,contract,domain=case(tmp_path,monkeypatch,quarter,back);raw=source.read_bytes()
    p=repair.plan(source,**args)
    assert p['width_nm']==200000 and p['actual_current_factory_floor_nm']<=200000 and p['unchanged_routing_preference_mm']==1.
    # The original preferred-width owner still refuses this source. Its
    # default contract is not monkeypatched or globally relaxed by this scope.
    b=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError,match='bounded_unchanged_full_current_planar_width'):
        repair.full.plan(b,source,board_hint='opaque',retired_track_uuids=args['retired_track_uuids'])
    p=json.loads(json.dumps(p));child=make(source,tmp_path,p);got=repair.receive(source,child,p,board_hint=args['board_hint'])
    assert got['ok'] and got['complete'],got['errors']
    assert got['source_width_and_actual_current_authority_exact'] and got['source_rules_and_routing_preference_exact']
    assert got['all_preexisting_current_sized_joins_preserved'] and got['all_surviving_native_partitions_preserved']
    assert got['centerline_removed_mm']>.2 and got['full_native_custom_rule_drc_fields_kelvin_pairs_stack_and_release_receiving_still_required']
    assert not got['source_current_reduced'] and not got['new_vias'] and not got['release_authority'] and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['source_too_thin','unproved_budget','incomplete','actual_current_increase','inner_plane',
    'locked','group','raw_diagonal','hard90','moved_port','boolean_permission'])
def test_preference_is_not_a_fallback_for_unknown_or_under_capacity_source(tmp_path,monkeypatch,fault):
    source,args,contract,domain=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    if fault=='source_too_thin':
        for t in b.GetTracks():t.SetWidth(1000)
    elif fault=='unproved_budget':contract['current_authority']['source']='guessed'
    elif fault=='incomplete':domain['complete']=False
    elif fault=='actual_current_increase':contract['required_by_layer_mm']={'F.Cu':.742453,'B.Cu':.742453}
    elif fault=='inner_plane':
        for t in b.GetTracks():t.SetLayer(pcbnew.In1_Cu)
    elif fault=='locked':args['allow_locked_source']=False
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(next(iter(b.GetTracks())))
    elif fault=='raw_diagonal':args['points_nm'][1][1]+=1
    elif fault=='hard90':args['points_nm']=[[5000000,10000000],[10000000,10000000],[10000000,15000000]]
    elif fault=='moved_port':args['points_nm'][0][0]+=1
    elif fault=='boolean_permission':args['allow_locked_source']='true'
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):repair.plan(source,**args)


@pytest.mark.parametrize('fault',['width','face','net','point','lock','extra_copper','via','pose','sidecar','budget','plan_width'])
def test_saved_exact_source_receiving_rejects_every_unowned_change(tmp_path,monkeypatch,fault):
    source,args,contract,domain=case(tmp_path,monkeypatch);p=repair.plan(source,**args);child=make(source,tmp_path,p)
    b=pcbnew.LoadBoard(str(child));t=next(iter(b.GetTracks()))
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='net':
        n=pcbnew.NETINFO_ITEM(b,'OTHER');b.Add(n);t.SetNet(n)
    elif fault=='point':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='lock':t.SetLocked(not t.IsLocked())
    elif fault=='extra_copper':
        q=t.Duplicate();q.m_Uuid.Clone(pcbnew.KIID());b.Add(q)
    elif fault=='via':
        q=pcbnew.PCB_VIA(b);q.SetNet(t.GetNet());q.SetWidth(600000);q.SetDrill(300000)
        q.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);q.SetViaType(pcbnew.VIATYPE_THROUGH);q.SetPosition(t.GetStart());b.Add(q)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='budget':contract['current_authority']['amps']=.4
    elif fault=='plan_width':p['width_nm']-=1
    try:field._save_field_snapshot(b,child)
    except field._ProposalUnknown as exc:
        # The production writer must not let native net propagation launder
        # this deliberate conflicting-net mutant into a valid candidate.
        assert fault=='net' and str(exc)=='native_field_snapshot_changed_saved_identity'
        return
    got=repair.receive(source,child,p,board_hint=args['board_hint'])
    assert not got['ok'] and got['errors']


def test_actual_native_custom_minimum_cannot_be_waived_by_the_same_capacity_scope(tmp_path,monkeypatch):
    source,args,contract,domain=case(tmp_path,monkeypatch)
    source.with_suffix('.kicad_dru').write_text('(version 1)\n(rule "actual wider minimum" '
        '(constraint track_width (min 0.5mm)) (condition "A.NetName == \'/UNFAMILIAR/CURRENT\'"))\n')
    report=tmp_path/'actual-source-native.json';shadow=force._copy_family(source,tmp_path/'native-source-input')
    producer=native.run(shadow,report,reporting_build=Path('/home/codex/.cache/cec/native-drc-10.0.5'),timeout_s=10.)
    assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
    actual=json.loads(report.read_text())
    assert any(v['type']=='track_width' for v in actual['violations'])
    grade=tmp_path/'native-grade.json';force._write(grade,dict(code_identity=force._code_identity(),candidate_sha256=force._hash(source),
        boards=dict(candidate=dict(native_producer=producer))))
    material=tmp_path/'native-material.json';force._write(material,dict(source_sha256=force._hash(source),
        code_identity=force._code_identity(),complete=True,rows=[dict(disposition='visible_or_unproved',request=dict(track_uuids=args['retired_track_uuids']))]))
    out=tmp_path/'finite-source-refinement'
    monkeypatch.setattr(sys,'argv',['root_run_existing_current_path_refinement_20261019.py','--source',str(source),
        '--grade',str(grade),'--material',str(material),'--hint','opaque','--out',str(out)])
    runpy.run_path('build/root_run_existing_current_path_refinement_20261019.py',run_name='__main__')
    result=json.loads((out/'stage.json').read_text())
    assert result['ok'] and result['complete'] and not result['changed'] and not result['release_authority']
    violations=[v for t in result['attempts'] for v in t.get('new_native_faults',[])]
    assert any(v['type']=='track_width' for v in violations)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_new_native_copper_loop_against_retained_same_net_material_is_refused(tmp_path,monkeypatch,quarter,back):
    source,args,contract,domain=case(tmp_path,monkeypatch,quarter,back)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    # Retained overlapping strokes are native metal, not imaginary obstacles.
    # The visually plausible miter now closes a small triangular copper loop.
    for u in args['retired_track_uuids']:
        t=live[u].Duplicate();t.m_Uuid.Clone(pcbnew.KIID());b.Add(t)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='new_enclosed_same_net_copper_void_or_loop_refused'):
        repair.no_new_enclosed_voids(b,[live[u] for u in args['retired_track_uuids']],args['points_nm'])
    # Full planning must also refuse. In this maximally overlapping fixture
    # its earlier boundary-tangent guard can reject before contour analysis.
    with pytest.raises(ValueError):repair.plan(source,**args)

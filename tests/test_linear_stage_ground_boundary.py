"""Distinct Source linear-stage class-Ground boundaries, no low-power alias.

Saved native material, canonical declarations and selected minima execute;
the labelled existing-current/export test catalog is explicitly synthetic.
"""
import copy
import json
from pathlib import Path
import time

import pcbnew
import pytest
import cec_field_coupling as field
import cec_linear_stage_ground_boundary as op
from test_linear_stage_ground_entries import fixture as ground_fixture


def fixture(tmp_path, monkeypatch, kind='control', turn=0, back=False):
    parent, _, q, hint, owner, calls = ground_fixture(tmp_path, monkeypatch, turn, back)
    # This fixture replaces no project current. Three existing non-Ground
    # rail models are labelled synthetic and freshly replayed by the API.
    def existing_current(board, source, net, board_hint):
        return ('aggregate_source_sink', dict(complete=True, source_refs=['fixture-source'],
            sink_refs=[owner]), dict(net=net, current_authority=dict(amps=.125,
            source='SYNTHETIC_EXISTING_TEST_CATALOG_ONLY'), required_by_layer_mm={'F.Cu':.25,'B.Cu':.25}))
    monkeypatch.setattr(op.entries.stage.full,'_model',existing_current)
    # The synthetic exporter closes over this actual mutable native fixture
    # tree. Recover it using the already configured test exporter.
    root = Path(hint)
    tree, _ = op.canonical._export(root,time.monotonic()+8.)
    for comp in op.canonical.synth._kids(op.canonical.synth._first(tree,'components'),'comp'):
        if op.canonical.synth._val(comp,'ref','').startswith('C_min_'):
            comp.extend([['property',['name','MPN'],['value','CL21A106KAYNNNE']],
                         ['property',['name','Manufacturer'],['value','Samsung']]])
    fp = parent.FindFootprintByReference(owner)
    if kind == 'control':
        pad=fp.FindPadByNumber('3'); pad.SetNet(fp.FindPadByNumber('12').GetNet())
        node = None
        for net in op.canonical.synth._kids(op.canonical.synth._first(tree,'nets'),'net'):
            for peer in list(op.canonical.synth._kids(net,'node')):
                if op.canonical.synth._val(peer,'ref','')==owner and op.canonical.synth._val(peer,'pin','')=='3':
                    node=peer;net.remove(peer)
        ground=next(n for n in op.canonical.synth._kids(op.canonical.synth._first(tree,'nets'),'net')
                    if op.canonical.synth._val(n,'name','')=='GND')
        ground.append(node)
    elif kind == 'ground': pad=fp.FindPadByNumber('12')
    else: pad=parent.FindFootprintByReference(next(iter(q['selected_bypasses']))).FindPadByNumber('2')
    face=pad.GetLayerSet().CuStack()[0]; start=pad.GetPosition(); step=-800000 if back else 800000
    end=start+pcbnew.VECTOR2I(step,800000)
    def track(a,b):
        t=pcbnew.PCB_TRACK(parent);parent.Add(t);t.SetNet(pad.GetNet());t.SetLayer(face)
        t.SetStart(a);t.SetEnd(b);t.SetWidth(250000);return t
    edge=track(start,end); branch=track(end,end+pcbnew.VECTOR2I(step,0))
    via=pcbnew.PCB_VIA(parent);parent.Add(via);via.SetPosition(end);via.SetNet(pad.GetNet())
    via.SetWidth(800000);via.SetDrill(400000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    field._save_field_snapshot(parent,Path(parent.GetFileName()))
    q['source_linear_power_stages']=op.entries.stage.collect(parent,q['poses'],board_hint=hint,enabled=True)
    q.update(scope='source_typed_complete_cell_escape_proposal',board_hint=hint,
        source_native_binding=op.row._source_binding(parent),retired_track_uuids=[])
    return parent,q,dict(edge=op.force._uid(edge),branch=op.force._uid(branch),
        via=op.force._uid(via),root=op.force._uid(pad),owner=owner),root,tree


def plan(parent,q,ids):
    return op.ownership(parent,q,[ids['edge']],deadline=time.monotonic()+8.)


@pytest.mark.parametrize('kind',['control','ground','cap'])
@pytest.mark.parametrize('back',[False,True])
def test_distinct_positive_roots_preserve_all_exact_ports(tmp_path,monkeypatch,kind,back):
    parent,q,ids,root,tree=fixture(tmp_path,monkeypatch,kind=kind,back=back)
    before=op.row._source_binding(parent);saved=Path(parent.GetFileName()).read_bytes()
    result=plan(parent,q,ids); authority=result['extras'][0]['authority']
    assert authority['kind']==op.KIND and authority['kind']!=op.native.KIND
    assert authority['source_width_nm']==authority['source_full_class_width_nm']==250000
    assert op.authority_label(authority)
    assert authority['source_owned_barrel_roots']==[] and authority['new_barrel_authority'] is False
    roots=authority['source_pad_roots'];assert any(r['pad_uuid']==ids['root'] for r in roots)
    assert all(op.source_root_label(r) for r in roots)
    if kind=='control':
        witness=next(r for r in roots if r['pad_uuid']==ids['root'])
        assert witness['role']=='control' and witness['control_remains_control'] is True
        assert witness['functional_ground_return'] is False
    ports=authority['exact_retained_ports']
    assert {ids['root'],ids['branch'],ids['via']} <= {p['item']['uuid'] for p in ports}
    assert all(p['every_original_contact_mandatory'] for p in ports)
    assert op.single_edge_ownerships(parent,q,[ids['edge']],deadline=time.monotonic()+8.)==result['extras']
    assert json.loads(json.dumps(result))==result
    assert before==op.row._source_binding(parent) and saved==Path(parent.GetFileName()).read_bytes()


@pytest.mark.parametrize('fault',['disabled','forged_proof','native_unsaved','thin','wide','locked','grouped',
    'trunk','cap_assignment','selected_missing','current_missing','current_unknown','control_Source_type',
    'control_Source_net','native_net','Source_class'])
def test_incomplete_or_reclassified_Source_never_owns_ground(tmp_path,monkeypatch,fault):
    parent,q,ids,root,tree=fixture(tmp_path,monkeypatch)
    edge=op.native._items(parent)[ids['edge']]
    if fault=='disabled':q['allow_linear_power_stage_reconstruction']=False
    elif fault=='forged_proof':q['source_linear_power_stages'][ids['owner']]['current_authority']=True
    elif fault=='native_unsaved':edge.SetEnd(edge.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='native_net':edge.SetNet(parent.FindFootprintByReference(ids['owner']).FindPadByNumber('2').GetNet())
    elif fault in ('thin','wide','locked','grouped'):
        if fault=='thin':edge.SetWidth(200000)
        elif fault=='wide':edge.SetWidth(500000)
        elif fault=='locked':edge.SetLocked(True)
        elif fault=='grouped':
            g=pcbnew.PCB_GROUP(parent);parent.Add(g);g.AddItem(edge)
        field._save_field_snapshot(parent,Path(parent.GetFileName()))
        q['source_native_binding']=op.row._source_binding(parent)
        q['source_linear_power_stages']=op.entries.stage.collect(parent,q['poses'],board_hint=q['board_hint'],enabled=True)
    elif fault=='trunk':ids['edge']=ids['branch']
    elif fault=='cap_assignment':next(iter(q['selected_bypasses'].values()))['pin']='8'
    elif fault=='selected_missing':q['selected_bypasses'].pop(next(iter(q['selected_bypasses'])))
    elif fault=='current_missing':
        def missing(*a,**k):raise ValueError('synthetic_missing_current')
        monkeypatch.setattr(op.entries.stage.full,'_model',missing)
    elif fault=='current_unknown':
        monkeypatch.setattr(op.entries.stage.full,'_model',lambda *a:('unknown',None,{}))
        q['source_linear_power_stages']=op.entries.stage.collect(parent,q['poses'],board_hint=q['board_hint'],enabled=True)
    elif fault in ('control_Source_type','control_Source_net'):
        for net in op.canonical.synth._kids(op.canonical.synth._first(tree,'nets'),'net'):
            for peer in op.canonical.synth._kids(net,'node'):
                if op.canonical.synth._val(peer,'ref','')==ids['owner'] and op.canonical.synth._val(peer,'pin','')=='3':
                    op.canonical.synth._first(peer,'pintype'if fault=='control_Source_type'else'pin')[1]='power_in'if fault=='control_Source_type'else'unknown'
    else:
        project=Path(parent.GetFileName()).with_suffix('.kicad_pro');data=json.loads(project.read_text())
        data['net_settings']['classes'][0]['track_width']=.3;project.write_text(json.dumps(data))
        q['source_linear_power_stages']=op.entries.stage.collect(parent,q['poses'],board_hint=q['board_hint'],enabled=True)
    with pytest.raises(ValueError):plan(parent,q,ids)


@pytest.mark.parametrize('fault',['kind','width','Ground_credit','barrel_right','root_role','control_credit',
    'Source_contact','binding','missing_port'])
def test_structural_labels_cannot_silently_alias_or_promote_control(tmp_path,monkeypatch,fault):
    parent,q,ids,root,tree=fixture(tmp_path,monkeypatch)
    authority=plan(parent,q,ids)['extras'][0]['authority']
    if fault=='kind':authority['kind']=op.native.KIND
    elif fault=='width':authority['source_width_nm']-=1
    elif fault=='Ground_credit':authority['current_authority']=True
    elif fault=='barrel_right':authority['new_barrel_authority']=True
    elif fault=='root_role':authority['source_pad_roots'][0]['role']='ground'
    elif fault=='control_credit':authority['source_pad_roots'][0]['functional_ground_return']=True
    elif fault=='Source_contact':authority['source_linear_stage_ground_boundary']['source_contacts']=[]
    elif fault=='binding':authority['source_linear_stage_ground_boundary']['source_native_binding']='invented'
    else:authority['exact_retained_ports'].pop()
    assert op.authority_label(authority) is False


def test_new_kind_does_not_gain_retained_component_or_continuation_shortcuts(tmp_path,monkeypatch):
    import cec_retained_ground_component as retained
    import cec_source_ground_continuation as continuation
    parent,q,ids,root,tree=fixture(tmp_path,monkeypatch)
    authority=plan(parent,q,ids)['extras'][0]['authority']
    assert continuation.ground_root_authorities(authority) is None
    assert retained._scope(dict(kind='source_boundary',net='GND',width_nm=250000,
        every_surviving_source_component_port_mandatory=True,
        exact_additional_macro_component_source_ownership=[authority])) is None


@pytest.mark.parametrize('deadline',[float('nan'),0.,float('inf')])
def test_inherited_lease_never_resets(deadline):
    with pytest.raises(ValueError,match='bounded_lease'):
        op.single_edge_ownerships(None,{},['fake'],deadline=deadline)


def test_tangent_native_glyph_is_not_positive_cut_ownership(tmp_path,monkeypatch):
    parent,q,ids,root,tree=fixture(tmp_path,monkeypatch)
    live=op.native._items(parent);edge=live[ids['edge']];pad=live[ids['root']]
    p=pad.GetPosition();edge.SetStart(p+pcbnew.VECTOR2I(275000,-500000))
    edge.SetEnd(p+pcbnew.VECTOR2I(275000,500000))
    assert op.native._positive_contact(parent,edge,pad,int(edge.GetLayer()),time.monotonic()+8.)==0
    field._save_field_snapshot(parent,Path(parent.GetFileName()))
    q['source_native_binding']=op.row._source_binding(parent)
    q['source_linear_power_stages']=op.entries.stage.collect(parent,q['poses'],board_hint=q['board_hint'],enabled=True)
    with pytest.raises(ValueError,match='moving_typed_material_root'):plan(parent,q,ids)


@pytest.mark.parametrize('malformed',[None,[],{},dict(kind=op.KIND),dict(kind=op.KIND,source_pad_roots=[None])])
def test_untrusted_labels_fail_closed(malformed):
    assert op.authority_label(malformed) is False
    assert op.source_root_label(malformed) is False

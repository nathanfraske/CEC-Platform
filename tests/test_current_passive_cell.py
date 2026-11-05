"""Composition boundaries, with real native opposite-port connectivity.

The fresh canonical Source planner is independently covered with real CLI
exports in test_detached_current_passive_pose. Here its proof, the routing
portfolio, and the enclosing saved receiver are injected at API boundaries;
native pads, authored current-port graphs and final named joins are real.
"""
import copy
import json
from pathlib import Path
import subprocess

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest

import cec_current_passive_cell as op
import cec_field_coupling as field
import cec_force_current as force


def fixture(tmp_path,monkeypatch):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    nets={}
    for name in('LEFT_RAIL','RIGHT_RAIL'):
        n=pcbnew.NETINFO_ITEM(b,name);b.Add(n);nets[name]=n
    fps={}
    for ref,at,spec in [('ARBITRARY_SERIES',(12,12),[('1','LEFT_RAIL',-1),('2','RIGHT_RAIL',1)]),
        ('EXPLICIT_INGRESS',(3,12),[('1','LEFT_RAIL',0)]),('EXPLICIT_LOAD',(24,12),[('1','RIGHT_RAIL',0)])]:
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(*at));fps[ref]=fp
        for num,net,offset in spec:
            p=pcbnew.PAD(fp);fp.Add(p);p.SetNumber(num);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(1.,1.))
            mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);p.SetLayerSet(mask);p.SetNet(nets[net])
            p.SetPosition(pcbnew.VECTOR2I_MM(at[0]+offset,at[1]))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        dict(name='Default',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5)]}}))
    uid=force._uid(fps['ARBITRARY_SERIES']);authority=dict(source='board_design_basis',amps=.75,geometry_margin=1.25,margin_included=False)
    currents={n:dict(current_authority=authority,required_by_layer_nm={0:500000,2:500000},release_authority=False)for n in nets}
    domains=[]
    for pin,net,src,sink,role in [('1','LEFT_RAIL','EXPLICIT_INGRESS','ARBITRARY_SERIES','sink'),
        ('2','RIGHT_RAIL','ARBITRARY_SERIES','EXPLICIT_LOAD','source')]:
        domains.append(dict(pin=pin,net=net,source_or_sink=role,domain=dict(source_refs=[src],sink_refs=[sink]),
            contract=dict(net=net,current_authority=authority,routing_layers=['F.Cu','B.Cu'],required_by_layer_mm={'F.Cu':.5,'B.Cu':.5})))
    def plan(path,poses,*,board_hint,max_shift_mm=6.,timeout_s=10.):
        return dict(source=str(source),source_sha256=force._hash(source),board_hint=board_hint,
            source_family=force._family(source,board_hint),code_identity=force._code_identity(),
            request=dict(poses=copy.deepcopy(poses),max_shift_mm=max_shift_mm),records=[dict(footprint_uuid=uid,
                ref='ARBITRARY_SERIES',target_pose=poses[0]['target_pose'],current_domains=copy.deepcopy(domains))])
    def apply(board,q):
        fp=board.FindFootprintByReference('ARBITRARY_SERIES');pose=q['request']['poses'][0]['target_pose']
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in pose[:2])));fp.SetOrientationDegrees(pose[2]);return [uid]
    monkeypatch.setattr(op.passive,'plan',plan);monkeypatch.setattr(op.passive,'apply',apply)
    def model(b,path,net,hint):
        d=next(d for d in domains if d['net']==net)
        return 'aggregate_source_sink',copy.deepcopy(d['domain']),copy.deepcopy(d['contract'])
    monkeypatch.setattr(op.ports.full,'_model',model)
    monkeypatch.setattr(op.ports,'_screen',lambda *a:dict(ok=True))
    monkeypatch.setattr(op.cells,'_supply_current_widths',lambda b,n:copy.deepcopy(currents[n]))
    poses=[dict(footprint_uuid=uid,target_pose=[14.,13.,0.])]
    return source,poses,domains


def constructible(tmp_path,monkeypatch,*,drop=None):
    source,poses,_=fixture(tmp_path,monkeypatch)
    board,q=op.compile(source,poses,board_hint='fixture')
    def compile(*a,**k):
        b=pcbnew.LoadBoard(str(source));op.passive.apply(b,q['pose_plan']);return b,copy.deepcopy(q)
    monkeypatch.setattr(op,'compile',compile)
    monkeypatch.setattr(op.escape,'menus',lambda b,r,**kw:dict(domains={k:[{'fixture':True}]for k in r}))
    monkeypatch.setattr(op.escape,'choose',lambda *a,**k:dict(complete=True))
    def construct(b,*args):
        made=[]
        for key,r in q['requests'].items():
            if drop==key:continue
            t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet(r['net']));t.SetWidth(r['width_nm']);t.SetLayer(pcbnew.F_Cu)
            t.SetStart(pcbnew.VECTOR2I(*r['a']['at_nm']));t.SetEnd(pcbnew.VECTOR2I(*r['b']['at_nm']));b.Add(t);made.append(t)
        return made
    monkeypatch.setattr(op.escape,'construct_private',construct)
    monkeypatch.setattr(op.additive,'_ground_refill',lambda b:None)
    monkeypatch.setattr(op.paths,'_receive_paths',lambda *a,**kw:[dict(fixture_path_subproof=True)])
    monkeypatch.setattr(op.ground,'receive',lambda *a,**kw:dict(ok=True,complete=True))
    return source,board,q


def test_both_opposite_aggregate_ports_are_mandatory_and_full_width(tmp_path,monkeypatch):
    source,poses,_=fixture(tmp_path,monkeypatch);literal=source.read_bytes()
    b,q=op.compile(source,poses,board_hint='fixture')
    assert len(q['requests'])==2 and q['every_moved_pin_is_mandatory']and q['no_source_copper_retirement']
    assert {tuple(r['b']['at_nm'])for r in q['requests'].values()}=={(3000000,12000000),(24000000,12000000)}
    assert all(r['width_nm']==500000 and r['unchanged_full_rail_current_contract']['current_authority']['amps']==.75
        for r in q['requests'].values())
    assert source.read_bytes()==literal and not q['routing_admitted']and not q['current_qualified']


@pytest.mark.parametrize('fault',['dual_role','moving_opposite','missing_opposite','current_mismatch'])
def test_source_current_or_endpoint_ambiguity_is_not_routing_authority(tmp_path,monkeypatch,fault):
    source,poses,domains=fixture(tmp_path,monkeypatch)
    if fault=='dual_role':domains[0]['domain']['source_refs']=['ARBITRARY_SERIES']
    elif fault=='moving_opposite':domains[1]['domain']['sink_refs']=['ARBITRARY_SERIES']
    elif fault=='missing_opposite':domains[1]['domain']['sink_refs']=['MISSING']
    else:monkeypatch.setattr(op.cells,'_supply_current_widths',lambda *a:dict(current_authority={'amps':.1}))
    with pytest.raises(ValueError):op.compile(source,poses,board_hint='fixture')


def test_complete_composition_observes_actual_named_native_joins(tmp_path,monkeypatch):
    source,_,q=constructible(tmp_path,monkeypatch);literal=source.read_bytes()
    b,r=op.construct(q)
    assert b is not None and r['complete']and not r['errors']and source.read_bytes()==literal,r
    assert len(r['phases']['complete_joint_selection']['named_endpoints'])==2
    assert r['independent_original_parent_saved_receiving_still_required']and not r['routing_admitted']


@pytest.mark.parametrize('pin',['1','2'])
def test_missing_one_actual_connection_never_emits_a_partial_cell(tmp_path,monkeypatch,pin):
    source,_,q=constructible(tmp_path,monkeypatch)
    key=next(k for k in q['requests']if k.endswith(':'+pin))
    def partial(b,*args):
        made=[]
        for k,r in q['requests'].items():
            if k==key:continue
            t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet(r['net']));t.SetWidth(r['width_nm']);t.SetLayer(0)
            t.SetStart(pcbnew.VECTOR2I(*r['a']['at_nm']));t.SetEnd(pcbnew.VECTOR2I(*r['b']['at_nm']));b.Add(t);made.append(t)
        return made
    monkeypatch.setattr(op.escape,'construct_private',partial)
    b,r=op.construct(q)
    assert b is None and not r['complete']and not r['partial_candidate_emitted']
    assert r['failed_stage']=='complete_joint_selection'and not r['no_path_proof']


@pytest.mark.parametrize('gate',['menu_missing','menu_empty','selection','paths','ground','forged'])
def test_every_mandatory_subproof_can_refuse_the_atomic_private_result(tmp_path,monkeypatch,gate):
    _,_,q=constructible(tmp_path,monkeypatch)
    if gate.startswith('menu'):
        monkeypatch.setattr(op.escape,'menus',lambda *a,**k:dict(domains={}if gate=='menu_missing'else{n:[]for n in q['requests']}))
    elif gate=='selection':monkeypatch.setattr(op.escape,'choose',lambda *a,**k:dict(complete=False))
    elif gate=='paths':
        def refuse(*a,**k):raise ValueError('actual-current-path-refused')
        monkeypatch.setattr(op.paths,'_receive_paths',refuse)
    elif gate=='ground':monkeypatch.setattr(op.ground,'receive',lambda *a,**k:dict(ok=False,complete=True))
    else:q=dict(q,source_sha256='forged')
    b,r=op.construct(q)
    assert b is None and not r['complete']and r['errors']and not r['partial_candidate_emitted']


@pytest.mark.parametrize('bad',[None,{},[],dict(scope='untyped')])
def test_malformed_proposal_fails_with_no_candidate(bad):
    b,r=op.construct(bad)
    assert b is None and not r['complete']and r['failed_stage']=='source_compilation'


@pytest.mark.parametrize('error',[subprocess.TimeoutExpired(['export'],.1),ValueError('Source-refused')])
def test_fresh_source_timeout_is_reported_not_a_partial_or_no_path(monkeypatch,error):
    def refuse(*a,**k):raise error
    monkeypatch.setattr(op,'compile',refuse)
    b,r=op.construct(dict(scope=op.SCOPE,source='/unused',board_hint='fixture',pose_plan={'request':{'poses':[],'max_shift_mm':6.}}))
    assert b is None and r['errors']and r['failed_stage']=='source_compilation'and not r['no_path_proof']


def test_typed_transaction_has_exact_schema_no_budget_role_or_current_overrides():
    import root_receive_local_transaction_20261022 as transaction
    phase=dict(kind='complete_current_passive_cell',candidate='/fixture/child.kicad_pcb',candidate_sha256='a'*64,proposal='/fixture/request.json')
    assert transaction.validate_phases([phase])==['complete_current_passive_cell']
    for key in('amps','width_nm','source_role','timeout_s','receive','allowed_uuids'):
        with pytest.raises(ValueError):transaction.validate_phases([dict(phase,**{key:1})])
    other=dict(kind='ordinary_join',candidate='/fixture/prior.kicad_pcb',candidate_sha256='b'*64,net='/fixture')
    with pytest.raises(ValueError,match='detached_passive_source_pose_must_be_first'):
        transaction.validate_phases([other,phase])


@pytest.mark.parametrize('old_width',[200000,499999,500000,800000])
def test_named_join_cannot_borrow_retained_thin_source_copper(tmp_path,monkeypatch,old_width):
    import time
    source,poses,_=fixture(tmp_path,monkeypatch)
    parent=pcbnew.LoadBoard(str(source))
    old=pcbnew.PCB_TRACK(parent);old.SetNet(parent.FindNet('LEFT_RAIL'));old.SetLayer(0)
    old.SetWidth(old_width);old.SetStart(pcbnew.VECTOR2I_MM(3,12));old.SetEnd(pcbnew.VECTOR2I_MM(8,12));parent.Add(old)
    field._save_field_snapshot(parent,source)
    child,q=op.compile(source,poses,board_hint='fixture')
    request=next(r for r in q['requests'].values()if r['net']=='LEFT_RAIL')
    # Name the actual immutable authority land, not a nearby thin midpoint.
    request['b']=op.ports._port(parent.FindFootprintByReference('EXPLICIT_INGRESS').FindPadByNumber('1'))
    link=pcbnew.PCB_TRACK(child);link.SetNet(child.FindNet('LEFT_RAIL'));link.SetLayer(0);link.SetWidth(500000)
    link.SetStart(pcbnew.VECTOR2I(*request['a']['at_nm']));link.SetEnd(pcbnew.VECTOR2I_MM(8,12));child.Add(link)
    assert op.escape.retained_native_boundary_connection(child,request)['all_named_contacts_connected']
    if old_width<500000:
        with pytest.raises(ValueError,match='relies_on_unqualified_copper'):
            op._full_width_connection(parent,child,source,request,'fixture',time.monotonic()+10.)
    else:
        proof=op._full_width_connection(parent,child,source,request,'fixture',time.monotonic()+10.)
        assert proof['all_named_contacts_connected']and proof['old_thin_copper_and_all_zone_edges_excluded']
        assert not proof['existing_barrel_capacity_qualified']and not proof['current_qualified']


def test_proposal_comparison_cannot_restart_the_initial_constituent_clock(tmp_path,monkeypatch):
    _,_,q=constructible(tmp_path,monkeypatch);clock=[0.];stable=op._stable
    def compile(*a,**k):clock[0]=9.99;return object(),copy.deepcopy(q)
    def compare(value):clock[0]+=.02;return stable(value)
    monkeypatch.setattr(op,'compile',compile);monkeypatch.setattr(op,'_stable',compare)
    monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    b,r=op.construct(q)
    assert b is None and not r['complete']and r['failed_stage']=='source_compilation'
    assert 'current_passive_constituent_deadline'in r['errors'][0]

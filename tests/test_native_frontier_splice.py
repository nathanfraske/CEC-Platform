"""Diagnostic hints are untrusted; positives use real geometry and receivers.

Only refusal tests inject a guard. No scheduling stub constitutes admission.
"""
import copy
import json
import pcbnew
import pytest
import cec_force_current as force
import cec_native_frontier_splice as splice
import cec_ordinary_signal_completion as ordinary
import cec_additive_route_receiving as additive
from test_ordinary_native_portals import fixture,target


def reports_for(board,request,face):
    pads={force._uid(p):p for f in board.GetFootprints()for p in f.Pads()}
    roots=[pads[e['uuid']]for e in request['route_endpoints']]
    a,b=[tuple(p.GetPosition())for p in roots]
    ends=[dict(at_nm=list(point),layers=[face],operations=[],
        retained_native_contact=dict(pad_uuid=force._uid(p)))for p,point in zip(roots,(a,b))]
    reports=[]
    for index,(start,other)in enumerate(((a,b),(b,a))):
        stop=[round(start[j]+(other[j]-start[j])*.4)for j in range(2)]
        op=dict(kind='trk',start_nm=list(start),end_nm=stop,
            width_nm=round(request['width_mm']*1e6),layer=face)
        feedback=dict(complete=True,complete_route=False,ops=[op])
        reports.append(dict(source_local_pad_rule_launches=dict(attempts=[dict(
            local_endpoints=[copy.deepcopy(ends[index]),copy.deepcopy(ends[1-index])],
            diagnostics=dict(middle_searches=[dict(best_reached_prefix=feedback)]))])))
    return reports


def feedback(report):
    return report['source_local_pad_rule_launches']['attempts'][0]['diagnostics']['middle_searches'][0]['best_reached_prefix']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_two_frontiers_join_and_both_saved_receivers(tmp_path,quarter,back):
    source,board,net=fixture(tmp_path,net='/arbitrary/RENAMED_CONTROL',quarter=quarter,back=back)
    q=ordinary.plan(board,source,board_hint='synthetic',net=net);request=target(board,q)
    face=int(pcbnew.B_Cu if back else pcbnew.F_Cu)
    hints=reports_for(board,request,face);raw=source.read_bytes()
    child=force._copy_family(source,tmp_path/'child')
    result=splice.apply(child,request,10.,json.loads(json.dumps(hints)))
    assert result['closed']==1 and result['components_after']<result['components_before'],result
    assert not result['partial_route_published'] and not result['release_authority']
    for module in (ordinary,additive):
        options={'net':net}if module is ordinary else{}
        proof=module.receive(source,child,board_hint='synthetic',timeout_s=10.,**options)
        assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',[
    'width','heading','unknown_root','unproved_prefix','same_root','complete_flag','route_flag',
    'extra_field','wrong_start','unknown_layer','bool_width','too_many_ops',
])
def test_untrusted_hints_cannot_save_partial_or_forged_routes(tmp_path,fault):
    source,board,net=fixture(tmp_path);q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    request=target(board,q);hints=reports_for(board,request,0)
    first=hints[0]['source_local_pad_rule_launches']['attempts'][0]
    op=feedback(hints[0])['ops'][0]
    if fault=='width':op['width_nm']-=1
    elif fault=='heading':op['end_nm'][1]+=1
    elif fault=='unknown_root':first['local_endpoints'][0]['retained_native_contact']['pad_uuid']='forged'
    elif fault=='unproved_prefix':first['local_endpoints'][0]['operations']=[['trk',1,2,3,4,220000,0]]
    elif fault=='same_root':hints[1]=copy.deepcopy(hints[0])
    elif fault=='complete_flag':feedback(hints[0])['complete']=1
    elif fault=='route_flag':feedback(hints[0])['complete_route']=True
    elif fault=='extra_field':op['receiver_ok']=True
    elif fault=='wrong_start':op['start_nm'][0]+=1
    elif fault=='unknown_layer':op['layer']=99
    elif fault=='bool_width':op['width_nm']=True
    elif fault=='too_many_ops':feedback(hints[0])['ops']*=129
    child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    result=splice.apply(child,request,10.,hints)
    assert result['closed']==0 and child.read_bytes()==raw,result
    assert not result['partial_route_published']


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf')])
def test_bounded_work_required(tmp_path,seconds):
    with pytest.raises(ValueError):splice.apply(tmp_path/'missing',{},seconds,[])


def test_unknown_literal_target_root_refuses_before_save(tmp_path):
    source,board,net=fixture(tmp_path);q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    request=target(board,q);hints=reports_for(board,request,0)
    request['route_endpoints'][0]['uuid']='not_actual_source'
    child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    with pytest.raises(ValueError,match='exact_frontier_native_roots'):
        splice.apply(child,request,10.,hints)
    assert child.read_bytes()==raw


def test_real_foreign_copper_barrier_refuses_all_bridges(tmp_path):
    import cec_field_coupling as field
    source,board,net=fixture(tmp_path)
    foreign=pcbnew.NETINFO_ITEM(board,'/FOREIGN');board.Add(foreign)
    track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I_MM(10,0))
    track.SetEnd(pcbnew.VECTOR2I_MM(10,20));track.SetWidth(1000000)
    track.SetLayer(pcbnew.F_Cu);track.SetNet(foreign);board.Add(track)
    field._save_field_snapshot(board,source)
    q=ordinary.plan(board,source,board_hint='synthetic',net=net);request=target(board,q)
    child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    result=splice.apply(child,request,10.,reports_for(board,request,0))
    assert not result['closed'] and child.read_bytes()==raw


def test_full_proposal_guard_refusal_never_saves_even_complete_geometric_join(tmp_path,monkeypatch):
    from cec_route_proposal_guard import RouteProposalGuard
    source,board,net=fixture(tmp_path);q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    request=target(board,q);child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    seen=[]
    def refuse(self,ops):seen.append(ops);return None
    monkeypatch.setattr(RouteProposalGuard,'prepare',refuse)
    result=splice.apply(child,request,10.,reports_for(board,request,0))
    assert seen and not result['closed'] and child.read_bytes()==raw


@pytest.mark.parametrize('alter_prefix',[False,True])
def test_actual_source_rule_frontiers_rederive_prefix_and_receive_saved_geometry(tmp_path,alter_prefix):
    import time
    import cec_field_coupling as field
    import cec_native_component_ports as ports
    import cec_native_portal_geometry as geometry
    from test_existing_local_pofv_pad_rule import case
    board,source,pad=case(tmp_path)
    # Preserve actual authored process/group authority, but make this a
    # two-terminal ordinary fixture rather than borrowing Ground role credit.
    net='/renamed/LOCAL_CONTROL';entry=pcbnew.NETINFO_ITEM(board,net);board.Add(entry)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname()=='GND':p.SetNet(entry);p.SetPinType('input')
    for item in board.GetTracks():
        if item.GetNetname()=='GND':item.SetNet(entry)
    field._save_field_snapshot(board,source)
    project=json.loads(source.with_suffix('.kicad_pro').read_text())
    project['net_settings']={'classes':[dict(name='Default',track_width=.2,
        clearance=.2,via_diameter=.5,via_drill=.3)]}
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    board=pcbnew.LoadBoard(str(source))
    q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    assert q['complete'],q
    request=target(board,q);width=round(request['width_mm']*1e6)
    roots=ordinary._pads(board,q['request']);layers=[int(pcbnew.F_Cu),int(pcbnew.B_Cu)]
    deadline=time.monotonic()+10
    menus=[ports.same_face_track_endpoints(board,net,p,route_layers=layers,
        toward_nm=tuple(other.GetPosition()),minimum_barrel_web_nm=width,deadline=deadline)
        for p,other in((roots[0],roots[1]),(roots[1],roots[0]))]
    work,report=geometry._source_local_pair_menu(board,roots,menus,width=width,
        clearance=round(request['clearance_mm']*1e6),layers=layers,deadline=deadline)
    pair=next(pair for pair in work if all(int(pcbnew.B_Cu)in e['layers']for e in pair))
    hints=[]
    for index in (0,1):
        first,other=copy.deepcopy(pair[index]),copy.deepcopy(pair[1-index])
        if not first.get('operations'):
            first['retained_native_contact']={'pad_uuid':force._uid(roots[index])}
        a,b=first['at_nm'],other['at_nm']
        end=[round(a[0]+(b[0]-a[0])*.4),a[1]]
        op=dict(kind='trk',start_nm=a,end_nm=end,width_nm=width,layer=int(pcbnew.B_Cu))
        hints.append(dict(source_local_pad_rule_launches=dict(attempts=[dict(
            local_endpoints=[first,other],diagnostics=dict(middle_searches=[dict(
                best_reached_prefix=dict(complete=True,complete_route=False,ops=[op]))]))])))
    hints=json.loads(json.dumps(hints))
    if alter_prefix:
        endpoint=next(a['source_local_pad_rule_launches']['attempts'][0]['local_endpoints'][0]
            for a in hints if a['source_local_pad_rule_launches']['attempts'][0]['local_endpoints'][0]['operations'])
        endpoint['operations'][-1][1]+=1
    derived=splice._rows(hints,board,roots,menus,work,width,layers)
    assert len(derived)==(1 if alter_prefix else 2),json.dumps(hints,indent=2)
    child=force._copy_family(source,tmp_path/'child');raw=source.read_bytes()
    child_raw=child.read_bytes()
    result=splice.apply(child,request,10.,json.loads(json.dumps(hints)))
    if alter_prefix:
        assert not result['closed']and child.read_bytes()==child_raw
        return
    assert result['closed']==1,json.dumps(result,indent=2)
    for module in (ordinary,additive):
        options={'net':net}if module is ordinary else{}
        proof=module.receive(source,child,board_hint='synthetic',timeout_s=10.,**options)
        assert proof['ok']and proof['complete'],proof
    assert source.read_bytes()==raw


def test_saved_family_drift_after_complete_guard_refuses_before_materialization(tmp_path,monkeypatch):
    from cec_route_proposal_guard import RouteProposalGuard
    source,board,net=fixture(tmp_path);q=ordinary.plan(board,source,board_hint='synthetic',net=net)
    request=target(board,q);child=force._copy_family(source,tmp_path/'child');raw=child.read_bytes()
    prepare=RouteProposalGuard.prepare
    def change_after_real_preflight(self,ops):
        result=prepare(self,ops)
        if result is not None:
            path=child.with_suffix('.kicad_pro');path.write_bytes(path.read_bytes()+b'\n')
        return result
    monkeypatch.setattr(RouteProposalGuard,'prepare',change_after_real_preflight)
    with pytest.raises(ValueError,match='frontier_source_or_code_epoch_changed'):
        splice.apply(child,request,10.,reports_for(board,request,0))
    assert child.read_bytes()==raw

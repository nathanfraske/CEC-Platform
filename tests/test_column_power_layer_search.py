"""Ordinary-column search keeps Source class roles and physical board bounds."""
import json
import time
import pcbnew
import pytest
import cec_ordinary_power_columns as columns
import cec_field_coupling as field
import cec_fr as fr
import cec_force_current as force
from test_ordinary_power_columns import fixture,track


def source_class(source,name):
    project=source.with_suffix('.kicad_pro')
    data=json.loads(project.read_text())if project.exists()else{}
    data['net_settings']=dict(classes=[dict(name='Default',track_width=.5,clearance=.2,
        via_diameter=.9,via_drill=.5),dict(name='Power',track_width=.5,clearance=.2,
        via_diameter=.9,via_drill=.5)],netclass_assignments={'arbitrary_supply':name})
    project.write_text(json.dumps(data))


@pytest.mark.parametrize('name',['Power','Default'])
def test_actual_project_class_not_width_or_net_spelling_selects_the_power_role(tmp_path,monkeypatch,name):
    b,unused,source,*_=fixture(tmp_path,monkeypatch);source_class(source,name)
    spec=columns._routing_spec(source,'arbitrary_supply',{'width':500000})
    assert spec['name']==name and spec['track_width']==.5
    layers=fr._lastmile_route_layers(b,net_name='arbitrary_supply',spec=spec,exclude_front=False)
    assert (pcbnew.In3_Cu in layers)is(name=='Power')
    assert pcbnew.In1_Cu not in layers and pcbnew.In4_Cu not in layers


@pytest.mark.parametrize('quarter',range(4))
def test_real_plan_construct_receive_can_cross_on_source_authorized_power_role(tmp_path,monkeypatch,quarter):
    b,unused,source,*_=fixture(tmp_path,monkeypatch);source_class(source,'Power')
    wall=pcbnew.NETINFO_ITEM(b,'unrelated_full_height_barriers');b.Add(wall)
    for layer in(pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu):
        track(b,wall,(15,0),(15,15),layer,width=.6)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
        if quarter:item.Rotate(pcbnew.VECTOR2I_MM(15,7.5),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source);before=field._field_snapshot_inventory(b)
    result=columns.plan(b,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.)
    assert result['routing_netclass_name']=='Power'and pcbnew.In3_Cu in result['routing_layers']
    assert result['routing_layers'][0]==pcbnew.In3_Cu
    assert result['complete'],result
    assert any(op[0]=='trk'and op[4]==pcbnew.In3_Cu for op in result['ops'])
    child=pcbnew.LoadBoard(str(source));columns.construct_private(child,result,source=source,board_hint='synthetic')
    proof=columns.receive_native(b,child,source=source,board_hint='synthetic',net='arbitrary_supply')
    assert proof['ok']and proof['complete'],proof
    assert proof['every_single_new_vertical_barrel_loss_preserves_whole_current_path']
    assert field._field_snapshot_inventory(b)==before
    assert not proof['current_qualified']and not proof['release_authority']


@pytest.mark.parametrize('accept',[True,False])
def test_board_envelope_is_a_bounded_proposal_not_a_guard_or_packet_waiver(tmp_path,monkeypatch,accept):
    b,unused,source,*_=fixture(tmp_path,monkeypatch)
    wall=pcbnew.NETINFO_ITEM(b,'unrelated_partial_height_barrier');b.Add(wall)
    track(b,wall,(15,0),(15,10),pcbnew.In3_Cu,width=.6)
    before=field._field_snapshot_inventory(b);calls=[];reports=[];deadline=time.monotonic()+5.
    def actual_guard(a,z,w,layer):
        calls.append((a,z,w,layer));return True
    legs=columns._middle_route(b,(5000000,5000000),(25000000,5000000),
        layer=pcbnew.In3_Cu,width=500000,gap=200000,net='arbitrary_supply',guard=actual_guard,
        deadline=deadline,search_report=reports,power_envelope=True,
        packet_validator=lambda legs:accept)
    assert bool(legs)is accept and calls
    assert reports[0]['scope']=='local'and not reports[0]['found']
    box=b.GetBoardEdgesBoundingBox()
    assert reports[1]['scope']=='actual_board'and reports[1]['margin_mm']==max(box.GetWidth(),box.GetHeight())/1e6
    assert reports[1]['maximum_lease_s']==2.0 and all(not r['no_path_proof']for r in reports)
    assert all(row[2]==500000 and row[3]==pcbnew.In3_Cu for row in calls)
    assert field._field_snapshot_inventory(b)==before
    if legs:assert max(max(a.y,z.y)for a,z,w in legs)>10000000


def test_disabled_board_envelope_does_not_silently_expand_search(tmp_path,monkeypatch):
    b,unused,source,*_=fixture(tmp_path,monkeypatch)
    wall=pcbnew.NETINFO_ITEM(b,'unrelated_partial_height_barrier');b.Add(wall)
    track(b,wall,(15,0),(15,10),pcbnew.In3_Cu,width=.6)
    reports=[]
    legs=columns._middle_route(b,(5000000,5000000),(25000000,5000000),layer=pcbnew.In3_Cu,
        width=500000,gap=200000,net='arbitrary_supply',guard=lambda *args:True,
        deadline=time.monotonic()+2.,search_report=reports,power_envelope=False)
    assert not legs and len(reports)==1 and reports[0]['scope']=='local'


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_fixed_approach_guides_both_trunk_ends_without_waiving_complete_craft(quarter,mirror):
    def p(x,y):
        if mirror:x=-x
        for unused in range(quarter):x,y=-y,x
        return(x,y)
    start=p(0,0);end=p(100,100)
    fixed=[(p(10,10),start,500000),(end,p(110,110),500000)]
    before=list(fixed);guard=columns._fixed_endpoint_turns(fixed,(start,end))
    assert not guard(start,p(0,10),500000)
    assert not guard(p(100,110),end,500000)
    assert guard(start,p(-10,0),500000)
    assert guard(p(90,100),end,500000)
    # Positive-direction exact collinear overlap is normalized as new copper
    # by the ordinary packet producer; this hint must not call it an acute
    # turn, mutate fixed legs, or accept any resulting native craft by itself.
    assert guard(start,p(20,20),500000)
    assert fixed==before


def test_multiway_fixed_junction_keeps_whole_packet_craft_authority():
    legs=[((0,0),(10,10),500000),((0,0),(-10,0),500000)]
    guard=columns._fixed_endpoint_turns(legs,((0,0),(100,100)))
    assert guard((0,0),(0,10),500000)


def test_real_field_timeout_never_completes_until_a_fresh_phase_and_native_cuts(tmp_path,monkeypatch):
    from cec_route_proposal_guard import RouteProposalGuard
    b,unused,source,*_=fixture(tmp_path,monkeypatch);original=RouteProposalGuard.prepare;once=[]
    def timeout_once(self,ops):
        prepared=original(self,ops)
        if prepared is not None and not once:
            once.append(True);self.counts['passed']-=1;self.counts['unknown']+=1
            self.details[-1].update(reason='field_proposal_deadline',field=dict(ok=None,complete=False))
            self._last_attempt=dict(self.details[-1],status='unknown')
            return None
        return prepared
    monkeypatch.setattr(RouteProposalGuard,'prepare',timeout_once)
    before=field._field_snapshot_inventory(b)
    proposal=columns.plan(b,source=source,board_hint='synthetic',net='arbitrary_supply')
    assert not proposal['complete']and proposal['deferred_preflight']is True and not proposal['ops']
    with pytest.raises(ValueError):columns.construct_private(b,proposal,source=source,board_hint='synthetic')
    received=columns.prepare_deferred(b,proposal,source=source,board_hint='synthetic')
    assert received['complete']and received['deferred_preflight_received']
    assert received['fresh_deferred_preflight']['passed']==1 and not proposal['complete']
    child=pcbnew.LoadBoard(str(source));columns.construct_private(child,received,source=source,board_hint='synthetic')
    proof=columns.receive_native(b,child,source=source,board_hint='synthetic',net='arbitrary_supply')
    assert proof['ok']and proof['complete'],proof
    assert proof['every_single_new_vertical_barrel_loss_preserves_whole_current_path']
    assert field._field_snapshot_inventory(b)==before
    assert not received['routing_admitted']and not received['current_qualified']


def test_a_definite_field_refusal_cannot_be_relabelled_as_a_timeout(tmp_path,monkeypatch):
    from cec_route_proposal_guard import RouteProposalGuard
    b,unused,source,*_=fixture(tmp_path,monkeypatch)
    def refuse(self,ops):
        self.details.append(dict(reason='field_refused',craft=dict(ok=True,complete=True),
            field=dict(ok=False,complete=True)));self.counts['refused']+=1;return None
    monkeypatch.setattr(RouteProposalGuard,'prepare',refuse)
    proposal=columns.plan(b,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=2.)
    assert not proposal['complete']and not proposal.get('deferred_preflight',False)


@pytest.mark.parametrize('fault',['source_pose','source_file','not_deferred','already_complete',
    'project_rules_before','custom_rules_before'])
def test_deferred_geometry_is_not_a_worker_success_or_a_stale_source_exception(tmp_path,monkeypatch,fault):
    b,unused,source,*_=fixture(tmp_path,monkeypatch)
    proposal=dict(scope='source_ordinary_redundant_column_proposal',complete=False,
        deferred_preflight=True,board_hint='synthetic',source_binding=columns._source_identity(b),
        deferred_source_family=force._family(source,'synthetic'),
        source_sha256=force._hash(source),net='arbitrary_supply',
        deferred_ops=[('trk',(5000000,5000000),(8000000,5000000),500000,pcbnew.F_Cu)])
    if fault=='source_pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='source_file':proposal['source_sha256']='0'*64
    elif fault=='not_deferred':proposal['deferred_preflight']=False
    elif fault=='already_complete':proposal['complete']=True
    elif fault=='project_rules_before':source.with_suffix('.kicad_pro').write_text('{"changed_rules":true}')
    else:source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    with pytest.raises(ValueError,match='exact_saved_source'):
        columns.prepare_deferred(b,proposal,source=source,board_hint='synthetic')


@pytest.mark.parametrize('suffix',['.kicad_pro','.kicad_dru'])
def test_source_companions_changed_during_fresh_preflight_cannot_escape_epoch_check(tmp_path,monkeypatch,suffix):
    from cec_route_proposal_guard import RouteProposalGuard
    b,unused,source,*_=fixture(tmp_path,monkeypatch)
    proposal=dict(scope='source_ordinary_redundant_column_proposal',complete=False,
        deferred_preflight=True,board_hint='synthetic',source_binding=columns._source_identity(b),
        source_sha256=force._hash(source),deferred_source_family=force._family(source,'synthetic'),
        net='arbitrary_supply',deferred_ops=[('trk',(5000000,5000000),(8000000,5000000),500000,pcbnew.F_Cu)])
    original=RouteProposalGuard.prepare
    def changing(self,ops):
        source.with_suffix(suffix).write_text('{"changed_rules":true}'if suffix=='.kicad_pro'else'(version 1)\n')
        return original(self,ops)
    monkeypatch.setattr(RouteProposalGuard,'prepare',changing)
    with pytest.raises(ValueError,match='source_or_code_changed'):
        columns.prepare_deferred(b,proposal,source=source,board_hint='synthetic')


def test_actual_last_preflight_outcome_survives_capped_historical_diagnostics(tmp_path,monkeypatch):
    from cec_route_proposal_guard import RouteProposalGuard
    b,unused,source,*_=fixture(tmp_path,monkeypatch);guard=RouteProposalGuard(b,'arbitrary_supply')
    for i in range(16):guard._finish(None,dict(reason='earlier_refusal_'+str(i)),'refused')
    guard._finish(None,dict(reason='field_proposal_deadline',craft=dict(ok=True,complete=True),
        field=dict(ok=None,complete=False)),'unknown')
    assert len(guard.report()['details'])==16
    assert guard.report()['details'][-1]['reason']=='earlier_refusal_15'
    last=guard.last_attempt();assert last['reason']=='field_proposal_deadline'and last['status']=='unknown'
    last['field']['complete']=True
    assert guard.last_attempt()['field']['complete']is False

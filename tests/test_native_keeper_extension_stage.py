"""The automatic operator must bind the actual saved family and finite work."""
import json
import types
import pcbnew
import pytest
import cec_force_current as force
import cec_native_keeper_extension_stage as stage
from test_native_keeper_extension_receiving import fixture
from test_native_landing_union import keeper_setup


@pytest.mark.parametrize('fault',['empty_hint','wrong_hash','malformed_hash','missing_native','requests0',
    'requests_bool','requests_unbounded','accepted0','accepted_bool','accepted_unbounded',
    'seconds0','seconds_bool','seconds_nan','seconds_unbounded','existing_output','group_policy_type',
    'material_policy_type','signed_policy_type','unknown_scope','quantum_bool','quantum_bound',
    'screen0','screen_bool','screen_unbounded'])
def test_invalid_or_stale_source_context_never_creates_a_candidate(tmp_path,fault):
    source,_,_,_,_=fixture(tmp_path);out=tmp_path/'stage'
    kwargs=dict(board_hint='synthetic',expected_source_sha256=force._hash(source),reporting_build=tmp_path/'native')
    if fault=='empty_hint':kwargs['board_hint']=''
    elif fault=='wrong_hash':kwargs['expected_source_sha256']='0'*64
    elif fault=='malformed_hash':kwargs['expected_source_sha256']='A'*64
    elif fault=='missing_native':kwargs['reporting_build']=None
    elif fault=='existing_output':out.mkdir()
    elif fault=='group_policy_type':kwargs['retain_existing_keeper_group']=1
    elif fault=='material_policy_type':kwargs['retained_native_track_material']=1
    elif fault=='signed_policy_type':kwargs['allow_signed_native_keeper']=1
    elif fault=='unknown_scope':kwargs['request_scope']='caller-arbitrary'
    elif fault=='quantum_bool':kwargs['source_diagonal_quantum_nm']=True
    elif fault=='quantum_bound':kwargs['source_diagonal_quantum_nm']=2
    else:
        key,value={'requests0':('max_requests',0),'requests_bool':('max_requests',True),
            'requests_unbounded':('max_requests',17),'accepted0':('max_accepted',0),
            'accepted_bool':('max_accepted',True),'accepted_unbounded':('max_accepted',5),
            'seconds0':('sense_timeout_s',0),'seconds_bool':('sense_timeout_s',True),
            'seconds_nan':('sense_timeout_s',float('nan')),'seconds_unbounded':('sense_timeout_s',61),
            'screen0':('max_screen_requests',0),'screen_bool':('max_screen_requests',True),
            'screen_unbounded':('max_screen_requests',257)}[fault]
        kwargs[key]=value
    before=source.read_bytes()
    with pytest.raises(ValueError):stage.run(source,out,**kwargs)
    assert source.read_bytes()==before
    assert not out.exists() or fault=='existing_output' and list(out.iterdir())==[]


@pytest.mark.parametrize('observation',['no_requests_but_findings','truncated','source_open'])
def test_absent_work_or_incomplete_native_observation_never_means_contour_closure(tmp_path,monkeypatch,observation):
    source,_,_,_,_=fixture(tmp_path);out=tmp_path/'stage'
    def native(_source,report,**kwargs):
        # Deliberate test-only producer boundary, not physical DRC evidence.
        report.write_text(json.dumps(dict(violations=[],unconnected_items=[{}] if observation=='source_open' else [])))
        return dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=observation=='truncated'))
    monkeypatch.setattr(stage.native,'run',native)
    monkeypatch.setattr(stage.audit,'component_requests',lambda *a,**kw:dict(complete=True,requests=[]))
    monkeypatch.setattr(stage.audit,'audit_board',lambda *a,**kw:dict(complete=True,finding_count=1))
    before=source.read_bytes()
    result=stage.run(source,out,board_hint='synthetic',expected_source_sha256=force._hash(source),reporting_build=tmp_path/'native')
    assert not result['changed'] and not result['all_power_contours_clean'] and not result['release_authority']
    assert result['candidate']==str(source.resolve()) and source.read_bytes()==before
    if observation=='no_requests_but_findings':assert result['ok'] and result['complete'] and not result['errors']
    else:assert not result['ok'] and not result['complete'] and result['errors']


def test_terminal_request_scope_uses_expanded_audit_even_when_no_terminal_request_is_constructible(tmp_path,monkeypatch):
    source,_,_,_,_=fixture(tmp_path);out=tmp_path/'terminal-stage';observed=[]
    def native(_source,report,**kwargs):
        report.write_text(json.dumps(dict(violations=[],unconnected_items=[])))
        return dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=False))
    def inspect(_board,**kwargs):
        observed.append(('audit',kwargs))
        return dict(complete=True,finding_count=3)
    def requests(_board,**kwargs):
        observed.append(('requests',kwargs))
        return dict(complete=True,requests=[dict(finding_types=['wide_round_elbow'])])
    monkeypatch.setattr(stage.native,'run',native)
    monkeypatch.setattr(stage.audit,'audit_board',inspect)
    monkeypatch.setattr(stage.audit,'finding_requests',requests)
    before=source.read_bytes()
    result=stage.run(source,out,board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=tmp_path/'native',request_scope='terminal_caps')
    assert result['ok'] and result['complete'] and result['terminal_caps_included']
    assert result['source_request_count']==0 and not result['changed'] and not result['all_power_contours_clean']
    assert result['candidate']==str(source.resolve()) and source.read_bytes()==before
    assert all(k['include_terminal_caps'] is True for _,k in observed)
    assert not result['release_authority'] and not result['new_capacity_credited']


def _screen_case(angle=0,mirror=False,layer=pcbnew.F_Cu,renamed=False):
    board,track,zone,_=keeper_setup(angle=angle,mirror=mirror,layer=layer)
    if renamed:
        net=pcbnew.NETINFO_ITEM(board,'/ARBITRARY-CATALOG/OTHER-RAIL');board.Add(net)
        original=str(track.GetNetname())
        for item in [*board.GetTracks(),*board.Zones(),*(p for f in board.GetFootprints() for p in f.Pads())]:
            if str(item.GetNetname())==original:item.SetNet(net)
    requests=[]
    for index in range(20):
        unrelated=pcbnew.PCB_TRACK(board);unrelated.SetNet(track.GetNet());unrelated.SetLayer(layer)
        unrelated.SetWidth(track.GetWidth())
        unrelated.SetStart(pcbnew.VECTOR2I_MM(80+index,80));unrelated.SetEnd(pcbnew.VECTOR2I_MM(80+index,81))
        board.Add(unrelated)
        requests.append(dict(source_tracks=[dict(uuid=force._uid(unrelated))],net=str(track.GetNetname()),layer_id=int(layer)))
    requests.append(dict(source_tracks=[dict(uuid=force._uid(track))],net=str(track.GetNetname()),layer_id=int(layer)))
    return board,track,zone,requests


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('renamed',[False,True])
def test_native_contact_eligible_request_is_not_starved_by_first_sixteen_unowned_scopes(angle,mirror,layer,renamed):
    from cec_local_copper_cell import copper_inventory
    board,track,zone,requests=_screen_case(angle,mirror,layer,renamed);before=copper_inventory(board)
    result=stage.screen_requests(board,requests,max_requests=1)
    assert result['complete'] and result['all_source_requests_examined']
    assert [q['source_request_index'] for q in result['selected']]==[20]
    assert result['screened'][-1]['contacting_keeper_uuids']==[force._uid(zone)]
    assert all(not q['eligible'] for q in result['screened'][:20])
    assert result['stop_reason']=='source_inventory_exhausted' and result['unexamined_source_requests']==0
    assert not result['construction_authority'] and copper_inventory(board)==before
    plan=stage.owner.plan(board,[force._uid(track)],required_width_nm=track.GetWidth())
    assert plan['replacement_source_zone']['configuration']['uuid']==force._uid(zone)


@pytest.mark.parametrize('limit',[1,8,16,20])
def test_screen_bound_reports_unexamined_work_instead_of_calling_it_clean(limit):
    board,_,_,requests=_screen_case()
    result=stage.screen_requests(board,requests,max_requests=1,max_screen_requests=limit)
    assert result['complete'] and not result['all_source_requests_examined'] and not result['selected']
    assert result['unexamined_source_requests']==21-limit and result['stop_reason']=='screen_inventory_budget'
    assert not result['construction_authority']


@pytest.mark.parametrize('count',[1,2,8,16])
def test_constructor_budget_and_source_indices_remain_literal(count):
    board,_,_,requests=_screen_case();requests=[requests[-1]]*(count+1)
    result=stage.screen_requests(board,requests,max_requests=count)
    assert result['complete'] and len(result['selected'])==count
    assert result['unexamined_source_requests']==1 and result['stop_reason']=='construction_request_budget'
    assert [q['source_request_index'] for q in result['selected']]==list(range(count))


@pytest.mark.parametrize('fault',['unfilled','distant','foreign','unregistered','wrong_priority','two_owners'])
def test_prescreen_does_not_substitute_names_outlines_or_ambiguous_owners_for_fill(fault):
    board,track,zone,requests=_screen_case();request=requests[-1]
    if fault=='unfilled':zone.UnFill()
    elif fault=='distant':zone.Move(pcbnew.VECTOR2I_MM(40,0))
    elif fault=='foreign':zone.SetNet(board.FindNet('/RENAMED_FOREIGN'))
    elif fault=='unregistered':zone.SetZoneName('ordinary-unqualified-pour')
    elif fault=='wrong_priority':zone.SetAssignedPriority(1)
    else:
        second=pcbnew.ZONE(board);second.SetNet(zone.GetNet());second.SetLayer(zone.GetLayer())
        second.SetZoneName(zone.GetZoneName());second.SetAssignedPriority(0);second.Outline().NewOutline()
        ring=zone.Outline().Outline(0)
        for i in range(ring.PointCount()):second.Outline().Append(ring.CPoint(i).x,ring.CPoint(i).y)
        second.SetFilledPolysList(zone.GetLayer(),zone.GetFilledPolysList(zone.GetLayer()).CloneDropTriangulation())
        second.SetIsFilled(True);board.Add(second)
    result=stage.screen_requests(board,[request])
    assert result['complete'] and not result['selected'] and result['screened'][0]['refusal']
    assert not result['construction_authority']


@pytest.mark.parametrize('enabled',[False,True])
def test_signed_class_is_only_screened_under_explicit_policy(enabled):
    import cec_native_contour_regions as signed
    board,_,zone,requests=_screen_case();zone.SetZoneName(signed.ZONE_NAME)
    result=stage.screen_requests(board,[requests[-1]],allow_signed_native_keeper=enabled)
    assert bool(result['selected']) is enabled and not result['construction_authority']


def test_contact_prescreen_cannot_waive_constructor_clearance_floor():
    board,track,zone,requests=_screen_case()
    board.GetDesignSettings().m_MinClearance=200000;zone.SetLocalClearance(199999)
    result=stage.screen_requests(board,[requests[-1]])
    assert len(result['selected'])==1 and not result['construction_authority']
    with pytest.raises(ValueError,match='clearance_below_unchanged_board_floor'):
        stage.owner.plan(board,[force._uid(track)],required_width_nm=track.GetWidth())


@pytest.mark.parametrize('kwargs',[
    dict(max_screen_requests=0),dict(max_screen_requests=True),dict(max_screen_requests=257),
    dict(max_requests=True),dict(max_requests=17),dict(timeout_s=0),dict(timeout_s=True),
    dict(timeout_s=float('nan')),dict(timeout_s=11),dict(allow_signed_native_keeper=1)])
def test_invalid_screen_context_is_rejected_before_contact_scan(kwargs):
    with pytest.raises(ValueError,match='bounded_actual_keeper_scheduler_context_required'):
        stage.screen_requests(None,[],**kwargs)


def test_screen_deadline_is_not_reported_as_a_complete_no_path(monkeypatch):
    ticks=iter([0.,11.]);monkeypatch.setattr(stage,'time',types.SimpleNamespace(monotonic=lambda:next(ticks)))
    with pytest.raises(ValueError,match='native_keeper_request_screen_deadline'):
        stage.screen_requests(None,[{}])


def test_automatic_stage_reaches_eligible_scope_after_twenty_unowned_requests(tmp_path,monkeypatch):
    # Scheduling orchestration only: no simulated native verdict is claimed as
    # physical board admission. Real native contact is exercised in the matrix.
    board,_,_,requests=_screen_case()
    import cec_field_coupling as field
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(board,source)
    def native(_source,report,**kwargs):
        report.write_text(json.dumps(dict(violations=[],unconnected_items=[])))
        return dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=False))
    monkeypatch.setattr(stage.native,'run',native)
    monkeypatch.setattr(stage.audit,'component_requests',lambda *a,**kw:dict(complete=True,requests=requests))
    monkeypatch.setattr(stage.audit,'audit_board',lambda *a,**kw:dict(complete=True,finding_count=1))
    def reject(*args,**kwargs):raise ValueError('test_constructor_reached_but_not_admitted')
    monkeypatch.setattr(stage.owner,'plan',reject)
    before=source.read_bytes()
    result=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=tmp_path/'native',max_requests=1)
    assert result['ok'] and result['complete'] and not result['changed']
    assert [q['source_request_index'] for q in result['attempts']]==[20]
    assert 'test_constructor_reached_but_not_admitted' in result['attempts'][0]['refusal']
    assert not result['all_power_contours_clean'] and source.read_bytes()==before

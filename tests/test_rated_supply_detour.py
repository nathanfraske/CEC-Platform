"""A small supply detour needs positive unchanged load authority and replay."""
from contextlib import contextmanager
import math
from unittest import mock

import pcbnew
import pytest

import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_rated_supply_detour as detour
from cec_native_items import discard_items
from test_field_proposals import track
from test_future_pose_clearance import fixture as future_fixture
from test_gpio_series_semantics import fixture as gpio_fixture


@contextmanager
def authority(net,*,amps=.2,domains=None):
    contract=dict(amps=amps,margin_included=True,geometry_margin=1.,source='component_power_budget')
    with mock.patch('cec_synth_pipeline.spec_net_current_contract',side_effect=lambda hint,n:contract if n==net else None), \
            mock.patch.object(topology,'board_current_domains',return_value=domains or {}), \
            mock.patch.object(fr,'_project_netclass_resolver',return_value=lambda n:dict(name='Default',track_width=.2,clearance=.2)):
        yield


def fixture(tmp_path,*,angle=0):
    b,source,poses,_=future_fixture(tmp_path,angle=angle,locked=True)
    discard_items(b,list(b.GetTracks()))
    def rotate(p):
        a=math.radians(angle);x,y=p[0]-15,p[1]-15
        return (15+x*math.cos(a)+y*math.sin(a),15-x*math.sin(a)+y*math.cos(a))
    middle=track(b,'/CONTROL',rotate((8,10)),rotate((12,10)));middle.SetLocked(True)
    track(b,'/CONTROL',rotate((5,10)),rotate((8,10))).SetLocked(True)
    track(b,'/CONTROL',rotate((12,10)),rotate((15,10))).SetLocked(True)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    field._save_field_snapshot(b,source)
    return b,source,poses,force._uid(middle)


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_full_load_planar_prefix_restores_old_connections_before_future_pose(tmp_path,angle):
    b,source,poses,uid=fixture(tmp_path,angle=angle);before=source.read_bytes()
    with authority('/CONTROL'):
        report=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source))
    assert report['ok'],report.get('errors',report.get('receiving',{}).get('errors'))
    assert report['proposal']['retired_track_uuids']==[uid]
    assert report['receiving']['exact_retirement_and_additive_replay']['ok']
    assert report['receiving']['opens']<=report['receiving']['source_opens']
    assert not report['routing_admitted'] and not report['receiving']['force_current_qualified']
    assert source.read_bytes()==before and report['source_and_code_unchanged']
    assert all(t.GetClass()=='PCB_TRACK' and t.GetWidth()==200000 for t in pcbnew.LoadBoard(report['board']).GetTracks())


@pytest.mark.parametrize('fault',['no_contract','unrated','wide','group','force_domain'])
def test_missing_load_or_unowned_force_material_never_enters_small_preclear(tmp_path,fault):
    b,source,poses,uid=fixture(tmp_path)
    selected=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault=='wide':selected.SetWidth(1000000)
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(selected)
    field._save_field_snapshot(b,source)
    before=source.read_bytes()
    context=authority('/absent' if fault=='no_contract' else '/CONTROL',amps=3 if fault=='unrated' else .2,
        domains={'/CONTROL':dict(complete=False)} if fault=='force_domain' else None)
    with context,pytest.raises(ValueError):detour.plan(b,poses,source=source,board_hint='synthetic')
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['narrow','barrel','unrelated','pose','unchosen_retirement','missing_endpoint'])
def test_independent_receiver_rejects_forged_or_unrated_saved_changes(tmp_path,fault):
    b,source,poses,uid=fixture(tmp_path)
    with authority('/CONTROL'):
        result=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source))
        assert result['ok'],result
        child=result['board'];c=pcbnew.LoadBoard(child)
        old={force._uid(t) for t in b.GetTracks()};new=[t for t in c.GetTracks() if force._uid(t) not in old]
        if fault=='narrow':new[0].SetWidth(100000)
        elif fault=='barrel':
            v=pcbnew.PCB_VIA(c);v.SetPosition(pcbnew.VECTOR2I_MM(10,8));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
            v.SetWidth(600000);v.SetDrill(300000);v.SetNetCode(c.GetNetcodeFromNetname('/CONTROL'));c.Add(v)
        elif fault=='unrelated':track(c,'/OTHER_CONTROL',(22,22),(24,22))
        elif fault=='pose':next(iter(c.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
        elif fault=='unchosen_retirement':discard_items(c,[t for t in c.GetTracks() if force._uid(t) in old][:1])
        else:new[0].SetStart(pcbnew.VECTOR2I_MM(8,9.5))
        field._save_field_snapshot(c,child)
        proof=detour.receive(source,child,poses,board_hint='synthetic')
    assert not proof['ok'] and proof['errors'] and not proof['force_current_qualified']


@pytest.mark.parametrize('fault',['noncardinal','long','unknown','specialized','nonisolated','ambiguous_packet'])
def test_launch_lease_requires_a_bounded_isolated_positive_scalar_pin(tmp_path,fault):
    b,gpio,_,net=gpio_fixture();pad=list(gpio.Pads())[0]
    source=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,source)
    at=pad.GetPosition();launch=dict(pad_uuid=force._uid(pad),end_nm=[at.x+1_000_000,at.y])
    if fault=='noncardinal':launch['end_nm'][1]+=100000
    elif fault=='long':launch['end_nm'][0]+=10000000
    elif fault=='unknown':launch['pad_uuid']='missing-native-pad'
    elif fault=='specialized':pad.SetNumber('17')
    elif fault=='nonisolated':track(b,net,(at.x/1e6,at.y/1e6),((at.x+1_000_000)/1e6,at.y/1e6))
    else:launch['authority']=True
    with pytest.raises(ValueError):detour._signal_launch_witness(b,launch,source,'synthetic',10.)


def test_source_internal_bend_is_not_recreated_inside_the_reserved_future_land(tmp_path):
    b,source,poses,uid=fixture(tmp_path)
    selected=next(t for t in b.GetTracks() if force._uid(t)==uid)
    discard_items(b,[selected])
    first=track(b,'/CONTROL',(8,10),(10,10));second=track(b,'/CONTROL',(10,10),(12,10))
    first.SetLocked(True);second.SetLocked(True);field._save_field_snapshot(b,source)
    original=source.read_bytes()
    with authority('/CONTROL'):
        result=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source))
    assert result['ok'],result.get('errors',result.get('receiving',{}).get('errors'))
    assert set(result['proposal']['retired_track_uuids'])=={force._uid(first),force._uid(second)}
    assert len(result['paths'])==1 and result['paths'][0]['external_source_cut']['anchors_nm']==[[8000000,10000000],[12000000,10000000]]
    assert all([10000000,10000000] not in leg for leg in result['paths'][0]['legs_nm'])
    assert result['receiving']['exact_retirement_and_additive_replay']['ok'] and source.read_bytes()==original
    assert not result['receiving']['force_current_qualified'] and not result['routing_admitted']


def test_rated_supply_preclear_opts_into_bounded_refinement_without_neckdown(tmp_path,monkeypatch):
    b,source,poses,_=fixture(tmp_path);original=fr._guarded_profiled_lastmile_legs;calls=[]
    def observe(*args,**kwargs):
        calls.append((args,kwargs));return original(*args,**kwargs)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',observe)
    with authority('/CONTROL'):
        result=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source))
    assert result['ok'],result
    assert calls and all(k['refine_maze'] is True and math.isfinite(k['deadline_monotonic'])
        and a[3]==200000 and a[5]==200000 and k['max_length_nm']<=20_000_000 for a,k in calls)
    assert all('bounded_search_diagnostics' in row for row in result['paths'])


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_full_load_source_cut_can_leave_an_obsolete_internal_bend_but_not_a_terminal(tmp_path,angle):
    b,source,poses,uid=fixture(tmp_path,angle=angle);before=source.read_bytes()
    with authority('/CONTROL'):
        plan=detour.plan(b,poses,source=source,board_hint='synthetic',cut_extension_mm=4.)
        result=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source),cut_extension_mm=4.)
    assert result['ok'],result
    assert len(plan['retired_track_uuids'])==2 and len(plan['source_owned_cut_extensions'])==1
    assert sum(e['source_length_nm'] for e in plan['source_owned_cut_extensions'])<=4e6
    assert plan==result['receiving']['source_proposal'] and source.read_bytes()==before
    assert not result['routing_admitted'] and not result['release_authority']


@pytest.mark.parametrize('bad',[True,-1,4.1,float('nan'),float('inf')])
def test_rated_cut_extension_is_a_finite_explicit_locality_bound(tmp_path,bad):
    b,source,poses,_=fixture(tmp_path)
    with authority('/CONTROL'),pytest.raises(ValueError,match='bounded_rated_source_cut_extension_required'):
        detour.plan(b,poses,source=source,board_hint='synthetic',cut_extension_mm=bad)


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_rated_cut_can_use_exact_existing_component_contacts_with_independent_replay(tmp_path,monkeypatch,angle):
    b,source,poses,uid=fixture(tmp_path,angle=angle)
    with authority('/CONTROL'):
        proposal=detour.plan(b,poses,source=source,board_hint='synthetic')
        original={tuple(p) for p in proposal['boundaries'][0]['anchors_nm']}
        producer=fr._guarded_profiled_lastmile_legs
        def skip_old_internal_contacts(board,a,b,*args,**kwargs):
            if {tuple(a),tuple(b)}==original:return None
            return producer(board,a,b,*args,**kwargs)
        monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',skip_old_internal_contacts)
        report=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source))
    assert report['ok'],report.get('errors',report.get('receiving',{}).get('errors'))
    assert report['receiving']['exact_retirement_and_additive_replay']['ok']
    assert report['proposal']['retired_track_uuids']==[uid]
    selected=report['paths'][0]['selected_existing_component_ports']
    assert {tuple(p['at_nm']) for p in selected}!=original
    assert all(p['native_uuids'] for p in selected)
    assert not report['routing_admitted'] and not report['release_authority']


def test_retained_cut_port_discovery_never_substitutes_a_separate_same_net_island(tmp_path):
    b,source,poses,uid=fixture(tmp_path)
    extra=track(b,'/CONTROL',(7,8),(13,8))
    with authority('/CONTROL'):
        proposal=detour.plan(b,poses,source=source,board_hint='synthetic')
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    import cec_cell_row_rebuild as row
    before=row._source_binding(b)
    import time
    pairs=detour._planar_cut_ports(b,proposal['boundaries'][0],deadline=time.monotonic()+10)
    assert pairs and not any(force._uid(extra) in p['native_uuids'] for pair in pairs for p in pair)
    assert row._source_binding(b)==before


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_preclear_rejects_bad_retained_boundary_joins_during_search_without_mutation(tmp_path,monkeypatch,angle):
    b,source,poses,uid=fixture(tmp_path,angle=angle)
    original=source.read_bytes();producer=fr._guarded_profiled_lastmile_legs
    import cec_cell_row_rebuild as row
    refusals=[]
    def rotate(p):
        a=math.radians(angle);x,y=p[0]-15,p[1]-15
        return pcbnew.VECTOR2I_MM(15+x*math.cos(a)+y*math.sin(a),
                                  15-x*math.sin(a)+y*math.cos(a))
    def inject_bad_first_paths(board,*args,**kwargs):
        callback=kwargs['path_validator'];before=row._source_binding(board)
        # Each path is octilinear. Only the retained neighbor makes its
        # complete endpoint join unacceptable; filtering the graph to new
        # segments alone would miss both the covered launch and acute arrival.
        for points,kind in [([(8,10),(7.5,10),(7.5,8),(12,8),(12,10)],'covered_backtrack'),
                ([(8,10),(8,8),(13,8),(13,9),(12,10)],'acute_backtrack')]:
            legs=[(rotate(x),rotate(y),200000) for x,y in zip(points,points[1:])]
            assert callback(legs) is False
            assert row._source_binding(board)==before
            refusals.append(kind)
        return producer(board,*args,**kwargs)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',inject_bad_first_paths)
    with authority('/CONTROL'):
        result=detour.run(source,tmp_path/'prefix',poses,board_hint='synthetic',source_sha256=force._hash(source))
    assert result['ok'],result
    assert result['proposal']['retired_track_uuids']==[uid]
    reports=[r for trial in result['native_component_port_trials'][0]
        for r in trial['complete_path_craft_trials']]
    assert {'covered_backtrack','acute_backtrack'}<={i['type'] for r in reports for i in r['issues']}
    assert reports[-1]['ok'] and all(not r['board_mutated'] and not r['no_path_proof'] for r in reports)
    assert refusals and result['receiving']['craft']['craft_ok']
    assert result['receiving']['exact_retirement_and_additive_replay']['ok']
    assert source.read_bytes()==original and result['source_and_code_unchanged']

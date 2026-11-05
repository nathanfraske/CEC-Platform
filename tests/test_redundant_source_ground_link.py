"""Two independent Source Ground roots, never an arbitrary Ground mesh cut."""
import copy
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_redundant_source_ground_link as operation
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,*,quarter=0,face=pcbnew.F_Cu,width=.5,pieces=1,short=False):
    board=_board([],edge=(0,0,30,30));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    settings=board.GetDesignSettings();settings.m_TrackMinWidth=127000;settings.m_MinClearance=200000
    for name in ('GND','+3V3'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    board.FindNet('GND').GetNetClassSlow().SetTrackWidth(round(width*1e6))
    def point(x,y):
        for _ in range(quarter):x,y=30-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    roots=[]
    distance=.5 if short else 8.
    for index,(x,y)in enumerate(((8.,10.),(8.+distance,10.))):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('GROUND_ROOT_'+str(index));fp.SetValue('SOURCE_GROUND_TERMINAL')
        fp.SetLayer(face);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('G');pad.SetNet(board.FindNet('GND'))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
        pad.SetSize(pcbnew.VECTOR2I_MM(.3 if short else .8,.3 if short else .8))
        pad.SetPosition(point(x,y));fp.Add(pad);roots.append(pad)
    def edge(net,a,b,track_width=width):
        return track(board,net,[v/1e6 for v in point(*a)],[v/1e6 for v in point(*b)],layer=face,width=track_width)
    left_leg=edge('GND',(8,10),(8,8.6 if short else 9))
    right_leg=edge('GND',(8+distance,10),(8+distance,10.7 if short else 11))
    links=[edge('GND',(8+distance*i/pieces,10),(8+distance*(i+1)/pieces,10))for i in range(pieces)]
    vias=[]
    for x,y in ((8,8.6 if short else 9),(8+distance,10.7 if short else 11)):
        via=pcbnew.PCB_VIA(board);via.SetPosition(point(x,y));via.SetNet(board.FindNet('GND'))
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetWidth(900000);via.SetDrill(500000);board.Add(via);vias.append(via)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(board);zone.SetLayer(layer);zone.SetNet(board.FindNet('GND'))
        zone.SetLocalClearance(200000);zone.SetMinThickness(100000);zone.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):zone.Outline().Append(x*1000000,y*1000000)
        board.Add(zone)
    edge('+3V3',(3,3),(5,3))
    additive._ground_refill(board)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[dict(
        name='Default',track_width=width,clearance=.2,via_diameter=.9,via_drill=.5)]),board=dict(design_settings=dict(rules=dict(
            min_track_width=.127,min_clearance=.2,min_via_diameter=.5,min_through_hole_diameter=.3,
            min_via_annular_width=.1,min_hole_to_hole=.254))))))
    return source,board,dict(board_hint='synthetic',track_uuids=[force._uid(t)for t in links]),dict(
        roots=[force._uid(p)for p in roots],vias=[force._uid(v)for v in vias],
        retained=[force._uid(left_leg),force._uid(right_leg)],point=point)


def saved(tmp_path,**options):
    source,board,args,context=fixture(tmp_path,**options)
    proposal=operation.plan(source,**args)
    written=operation.write_private(proposal,tmp_path/'candidate')
    return source,Path(written['candidate']),args,proposal,context


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('width',[.22,.5])
def test_exact_native_two_root_link_subtraction_in_cardinal_frames(tmp_path,quarter,face,width):
    source,child,args,proposal,context=saved(tmp_path,quarter=quarter,face=face,width=width)
    raw=source.read_bytes()
    assert proposal['schema']==1 and proposal['kind']=='redundant_source_ground_surface_link'
    assert proposal['track_uuids']==sorted(args['track_uuids'])
    assert proposal['source_width_nm']==round(width*1e6)
    assert len(proposal['endpoint_ground_pads'])==2
    received=operation.receive(source,child,**args)
    assert received['ok']and received['complete'],received
    assert not received.get('current_qualified',False)and not received['release_authority']
    before={force._uid(t)for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    after={force._uid(t)for t in pcbnew.LoadBoard(str(child)).GetTracks()}
    assert before-after==set(args['track_uuids'])and not after-before
    assert set(context['vias']+context['retained'])<=after
    assert source.read_bytes()==raw


def test_multiple_literal_degree_two_edges_are_one_bounded_link(tmp_path):
    source,child,args,proposal,context=saved(tmp_path,pieces=3)
    assert len(proposal['track_uuids'])==3
    result=operation.receive(source,child,**args)
    assert result['ok']and result['complete'],result


@pytest.mark.parametrize('fault',['missing_left_entry','missing_right_entry','wrong_via_net','no_second_plane',
    'unfilled_plane','undersized_hole','one_face_barrel','group','lock','mask','power','wrong_width',
    'class_missing','DNP','PTH_root','missing_root','interior_pad','interior_track','interior_via','interior_plane'])
def test_source_eligibility_requires_both_independent_real_roots(tmp_path,fault):
    source,board,args,ctx=fixture(tmp_path)
    live={force._uid(t):t for t in board.GetTracks()};padmap={force._uid(p):p for fp in board.GetFootprints()for p in fp.Pads()}
    seed=live[args['track_uuids'][0]]
    if fault in ('missing_left_entry','missing_right_entry'):
        discard_items(board,[live[ctx['vias'][fault=='missing_right_entry']]])
    elif fault=='wrong_via_net':
        # Keep a genuinely foreign Source barrel, not a contradictory short
        # that native loading legitimately normalizes back to its Ground pad.
        live[ctx['vias'][0]].SetNet(board.FindNet('+3V3'))
        live[ctx['vias'][0]].SetPosition(pcbnew.VECTOR2I_MM(4,3))
        additive._ground_refill(board)
    elif fault=='no_second_plane':discard_items(board,[z for z in board.Zones()if z.GetLayer()==pcbnew.In4_Cu])
    elif fault=='unfilled_plane':next(iter(board.Zones())).UnFill()
    elif fault=='undersized_hole':
        profile=operation.fab.get_profile(operation.fab.board_profile_name(board))
        actual_floor=round(profile['pofv_drill_min_mm']*1e6)
        live[ctx['vias'][0]].SetDrill(actual_floor-1000)
    elif fault=='one_face_barrel':
        live[ctx['vias'][0]].SetViaType(pcbnew.VIATYPE_BLIND)
        live[ctx['vias'][0]].SetLayerPair(pcbnew.F_Cu,pcbnew.In1_Cu)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);group.SetName('PROTECTED_SOURCE_LINK');board.Add(group);group.AddItem(seed)
    elif fault=='lock':seed.SetLocked(True)
    elif fault=='mask':seed.SetHasSolderMask(True)
    elif fault=='power':
        # A real power graph, with matching authored lands/carriers/barrels,
        # is not Ground merely because this operator was asked to cut it.
        for item in [*board.GetTracks(),*padmap.values()]:
            if item.GetNetname()=='GND':item.SetNet(board.FindNet('+3V3'))
        additive._ground_refill(board)
    elif fault=='wrong_width':seed.SetWidth(499999)
    elif fault=='class_missing':source.with_suffix('.kicad_pro').unlink()
    elif fault=='DNP':padmap[ctx['roots'][0]].GetParentFootprint().SetDNP(True)
    elif fault=='PTH_root':
        p=padmap[ctx['roots'][0]];p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2));p.SetLayerSet(pcbnew.PAD.PTHMask())
    elif fault=='missing_root':discard_items(board,[padmap[ctx['roots'][0]].GetParentFootprint()])
    elif fault=='interior_pad':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNOWNED_INTERIOR');board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet('GND'));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4));pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(12,10));fp.Add(pad)
    elif fault=='interior_track':track(board,'GND',(12,10),(12,11),width=.5)
    elif fault=='interior_via':
        via=live[ctx['vias'][0]].Duplicate();via.m_Uuid.Clone(pcbnew.KIID());via.SetPosition(pcbnew.VECTOR2I_MM(12,10));board.Add(via)
    elif fault=='interior_plane':
        zone=next(iter(board.Zones())).Duplicate(False);zone.m_Uuid.Clone(pcbnew.KIID());zone.SetLayer(pcbnew.F_Cu);board.Add(zone)
        additive._ground_refill(board)
    if fault in ('wrong_via_net','power'):
        # Independently check the actual saved net rather than assuming the
        # producer's in-memory mutation survived native reconstruction.
        field._save_field_snapshot(board,source)
        reloaded=pcbnew.LoadBoard(str(source))
        target=ctx['vias'][0]if fault=='wrong_via_net'else args['track_uuids'][0]
        assert next(t for t in reloaded.GetTracks()if force._uid(t)==target).GetNetname()=='+3V3'
    else:field._save_field_snapshot(board,source)
    if fault=='undersized_hole':
        reload=pcbnew.LoadBoard(str(source));via=next(t for t in reload.GetTracks()if force._uid(t)==ctx['vias'][0])
        assert via.GetDrillValue()==actual_floor-1000
    if fault=='one_face_barrel':
        reload=pcbnew.LoadBoard(str(source));via=next(t for t in reload.GetTracks()if force._uid(t)==ctx['vias'][0])
        assert via.GetViaType()==pcbnew.VIATYPE_BLIND and via.BottomLayer()==pcbnew.In1_Cu
    with pytest.raises(ValueError):operation.plan(source,**args)


def test_local_endpoints_do_not_waive_a_shorter_known_source_return(tmp_path):
    source,board,args,ctx=fixture(tmp_path,width=.22,short=True)
    with pytest.raises(ValueError):operation.plan(source,**args)


@pytest.mark.parametrize('bad',[None,False,True,[],[''],['not-present'],['a','a'],['a']*9,'source-track'])
def test_requested_cut_is_literal_bounded_unique_source_identity(tmp_path,bad):
    source,board,args,ctx=fixture(tmp_path)
    with pytest.raises(ValueError):operation.plan(source,board_hint='synthetic',track_uuids=bad)


@pytest.mark.parametrize('limit',[False,True,0,-1,10.001,float('nan'),float('inf')])
def test_plan_cannot_expand_or_disable_native_lease(tmp_path,limit):
    source,board,args,ctx=fixture(tmp_path)
    with pytest.raises(ValueError):operation.plan(source,timeout_s=limit,**args)


@pytest.mark.parametrize('fault',['extra_cut','new_track','part','retained_width','via_drill','zone_outline','sidecar','restore_cut'])
def test_saved_receiving_rederives_exact_source_subtraction_not_worker_claim(tmp_path,fault):
    source,child,args,proposal,ctx=saved(tmp_path)
    board=pcbnew.LoadBoard(str(child));live={force._uid(t):t for t in board.GetTracks()}
    if fault=='extra_cut':discard_items(board,[live[ctx['retained'][0]]])
    elif fault=='new_track':track(board,'GND',(22,22),(23,22),width=.5)
    elif fault=='part':next(iter(board.GetFootprints())).SetValue('NOT_SOURCE_PART')
    elif fault=='retained_width':live[ctx['retained'][0]].SetWidth(499999)
    elif fault=='via_drill':live[ctx['vias'][0]].SetDrill(400000)
    elif fault=='zone_outline':next(iter(board.Zones())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    elif fault=='restore_cut':
        original=pcbnew.LoadBoard(str(source));item=next(t for t in original.GetTracks()if force._uid(t)in args['track_uuids'])
        board.Add(item.Duplicate())
    if fault!='sidecar':field._save_field_snapshot(board,child)
    result=operation.receive(source,child,**args)
    assert not result['ok']and not result['complete']and result['errors'],result


@pytest.mark.parametrize('fault',['tracks','source','code','binding'])
def test_writer_never_trusts_a_stale_or_forged_positive_plan(tmp_path,fault):
    source,board,args,ctx=fixture(tmp_path);proposal=operation.plan(source,**args)
    if fault=='tracks':proposal['track_uuids']=ctx['retained']
    elif fault=='source':proposal['source_sha256']='0'*64
    elif fault=='code':proposal['code_identity']={}
    else:proposal['source_binding']={}
    with pytest.raises(ValueError):operation.write_private(proposal,tmp_path/'forged')


def test_receive_has_no_caller_positive_plan_parameter(tmp_path):
    source,child,args,proposal,ctx=saved(tmp_path)
    with pytest.raises(TypeError):operation.receive(source,child,proposal=proposal,**args)


def test_late_final_code_or_family_observation_cannot_return_success(tmp_path,monkeypatch):
    source,child,args,proposal,ctx=saved(tmp_path)
    now=time.monotonic;offset=[0.];real=operation.force._family;calls=[0]
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:now()+offset[0]))
    def late(*a,**kw):
        value=real(*a,**kw);calls[0]+=1
        # Discover the final check by its completion of actual return proof,
        # not a caller-supplied success or fixed wallclock sleep.
        import inspect
        if any(frame.filename==operation.__file__ and frame.function=='receive'
               and frame.frame.f_locals.get('result',{}).get('all_Source_known_returns')
               for frame in inspect.stack()):offset[0]=11.
        return value
    monkeypatch.setattr(operation.force,'_family',late)
    result=operation.receive(source,child,**args)
    assert offset[0]==11.
    assert not result['ok']and not result['complete']and result['errors'],result


@pytest.mark.parametrize('budgets',[False,True,[],(),(10.,),(10.,10.,10.),(10.,)*5,
    (True,10.,10.,10.),(0.,10.,10.,10.),(-1.,10.,10.,10.),
    (10.001,10.,10.,10.),(float('nan'),10.,10.,10.),(float('inf'),10.,10.,10.)])
def test_optional_receiver_stage_budgets_are_exact_and_never_borrow_authority(budgets):
    with pytest.raises(ValueError):operation._Lease(10.,budgets)


@pytest.mark.parametrize('next_name',[operation.PHASES[0],operation.PHASES[2],operation.PHASES[3],'caller-stage'])
def test_receiver_stage_order_is_fixed(next_name):
    lease=operation._Lease(10.,(10.,)*4)
    with pytest.raises(ValueError):lease.advance(next_name)


def test_all_four_receiving_stages_are_mandatory():
    lease=operation._Lease(10.,(10.,)*4)
    with pytest.raises(ValueError):lease.finish()


def test_four_lease_work_is_not_one_outer_deadline(monkeypatch):
    clock=[0.]
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    lease=operation._Lease(10.,(10.,)*4)
    for index,name in enumerate(operation.PHASES[1:],1):
        clock[0]=8.*index;lease.advance(name)
    clock[0]=32.;lease.finish()
    assert lease.timings==dict.fromkeys(operation.PHASES,8.)


@pytest.mark.parametrize('index',range(4))
def test_a_late_constituent_cannot_reset_into_next_budget(monkeypatch,index):
    clock=[0.]
    monkeypatch.setattr(operation,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    lease=operation._Lease(10.,(10.,)*4)
    for name in operation.PHASES[1:index+1]:lease.advance(name)
    clock[0]=10.
    with pytest.raises(ValueError):
        if index==3:lease.finish()
        else:lease.advance(operation.PHASES[index+1])


def test_explicit_staged_saved_receiving_retains_all_four_native_obligations(tmp_path):
    source,child,args,proposal,ctx=saved(tmp_path,quarter=3,face=pcbnew.B_Cu,width=.22,pieces=2)
    result=operation.receive(source,child,receiving_phase_timeouts_s=(10.,)*4,**args)
    assert result['ok']and result['complete'],result
    assert tuple(result['stage_timings_s'])==operation.PHASES
    assert result['bounded_composition']==dict(constituents=list(operation.PHASES),stage_limits_s=[10.]*4,
        per_constituent_limit_s=10.,aggregate_limit_s=40.)
    assert result['actual_native_partitions']['preserved']
    assert result['all_Source_known_return_witnesses_preserved']
    assert result['every_Source_reference_plane_and_power_fill_byte_unchanged']
    assert result['current_field_Kelvin_fabrication_and_original_parent_receiving_still_required']


@pytest.mark.parametrize('where',['plan','saved_receive'])
@pytest.mark.parametrize('failure',['unknown','failed'])
def test_unknown_or_failed_source_returns_never_become_cut_authority(tmp_path,monkeypatch,where,failure):
    source,child,args,proposal,ctx=saved(tmp_path)
    real=operation.returns.receive;calls=[]
    def refuse(*a,**kw):
        value=real(*a,**kw);calls.append(1)
        if where=='plan'or len(calls)==2:
            value.update(ok=False,complete=failure=='failed',errors=['synthetic_actual_returns_'+failure])
        return value
    monkeypatch.setattr(operation.returns,'receive',refuse)
    if where=='plan':
        with pytest.raises(ValueError,match='worsened_or_could_not_observe_all_Source_known_returns'):
            operation.plan(source,**args)
    else:
        result=operation.receive(source,child,receiving_phase_timeouts_s=(10.,)*4,**args)
        assert len(calls)==2
        assert not result['ok']and not result['complete'],result
        assert any('worsened_or_could_not_observe_all_Source_known_returns'in e for e in result['errors'])


def test_default_none_does_not_silently_request_staged_receiving(tmp_path):
    source,child,args,proposal,ctx=saved(tmp_path)
    result=operation.receive(source,child,receiving_phase_timeouts_s=None,**args)
    assert result['ok']and result['complete'],result
    assert 'stage_timings_s'not in result and 'bounded_composition'not in result


def test_final_code_identity_drift_refuses_after_real_proofs(tmp_path,monkeypatch):
    source,child,args,proposal,ctx=saved(tmp_path)
    real_returns=operation.returns.receive;real_code=operation.force._code_identity;calls=[]
    def observe(*a,**kw):
        value=real_returns(*a,**kw);calls.append(1);return value
    def changed():
        value=real_code()
        return dict(value,in_process_negative_test_only='not_Source_file_mutation')if len(calls)>=2 else value
    monkeypatch.setattr(operation.returns,'receive',observe)
    monkeypatch.setattr(operation.force,'_code_identity',changed)
    result=operation.receive(source,child,receiving_phase_timeouts_s=(10.,)*4,**args)
    assert not result['ok']and not result['complete'],result
    assert any('Source_candidate_or_code_changed'in e for e in result['errors'])


def obtuse_fixture(tmp_path):
    source,board,args,ctx=fixture(tmp_path)
    pads={force._uid(p):p for fp in board.GetFootprints()for p in fp.Pads()}
    pads[ctx['roots'][0]].SetSize(pcbnew.VECTOR2I_MM(.3,.3))
    live={force._uid(t):t for t in board.GetTracks()}
    landing=pcbnew.VECTOR2I_MM(7.25,10.75)
    live[ctx['retained'][0]].SetEnd(landing);live[ctx['vias'][0]].SetPosition(landing)
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    return source,board,args,ctx


def test_actual_obtuse_source_endpoint_stub_is_positive_not_whole_conductor_authority(tmp_path):
    source,board,args,ctx=obtuse_fixture(tmp_path)
    proposal=operation.plan(source,**args)
    assert proposal['retained_endpoint_junctions']
    child=Path(operation.write_private(proposal,tmp_path/'obtuse-child')['candidate'])
    result=operation.receive(source,child,receiving_phase_timeouts_s=(10.,)*4,**args)
    assert result['ok']and result['complete'],result
    assert not result['current_qualified']and not result['release_authority']


@pytest.mark.parametrize('where',['same_conductor','second_contact'])
def test_endpoint_aperture_never_authorizes_a_later_interior_tee(tmp_path,where):
    source,board,args,ctx=obtuse_fixture(tmp_path)
    live={force._uid(t):t for t in board.GetTracks()}
    if where=='same_conductor':
        # The SAME eligible obtuse endpoint edge is also touched by a later
        # part of the selected chain. Owning its one-width endpoint stub must
        # not turn that whole retained object into an acquired interior tee.
        discard_items(board,[live[u]for u in args['track_uuids']])
        root=next(p for fp in board.GetFootprints()for p in fp.Pads()if force._uid(p)==ctx['roots'][1])
        root.SetPosition(pcbnew.VECTOR2I_MM(7.2,11.5));root.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        live[ctx['retained'][1]].SetStart(root.GetPosition())
        live[ctx['retained'][1]].SetEnd(pcbnew.VECTOR2I_MM(7.2,12.5))
        live[ctx['vias'][1]].SetPosition(pcbnew.VECTOR2I_MM(7.2,12.5))
        points=[(8,10),(8.6,10),(8.6,10.8),(7.2,10.8),(7.2,11.5)]
        edges=[track(board,'GND',a,b,width=.5)for a,b in zip(points,points[1:])]
        args['track_uuids']=[force._uid(t)for t in edges]
    else:
        track(board,'GND',(12,10),(12,11),width=.5)
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    with pytest.raises(ValueError,match='interior_contact'):
        operation.plan(source,**args)

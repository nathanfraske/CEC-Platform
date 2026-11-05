"""Renamed, rotated source-typed ground elbows; no board-coordinate policy."""
import copy
import pcbnew
import pytest
import cec_ground_elbow_reflow as op
import cec_field_coupling as field
import cec_force_current as force
import cec_additive_route_receiving as additive
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board
import cec_native_ground_span_reflow as native_span
import cec_native_ground_span_stage as native_span_stage


def fixture(tmp_path,angle=0,mirror=False):
    b=_board([],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    for name in ('GND','+3V3'):
        if name not in b.GetNetsByName():b.Add(pcbnew.NETINFO_ITEM(b,name))
    def point(x,y):
        if mirror:x=20-x
        for _ in range(angle//90):x,y=20-y,x
        return x,y
    def part(ref,value,entries):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetValue(value);b.Add(fp)
        for pin,net,x,y in entries:
            p=pcbnew.PAD(fp);p.SetNumber(pin);p.SetNetCode(b.GetNetcodeFromNetname(net))
            p.SetPosition(pcbnew.VECTOR2I_MM(*point(x,y)));p.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
        return fp
    owner=part('ARBITRARY_SENSOR','INA238',[('6','+3V3',10,9.2),('7','GND',10,10)])
    part('C_ARBITRARY_BYPASS','100nF',[('1','+3V3',11.5,11.3),('2','GND',11.5,12)])
    def edge(a,z):return track(b,'GND',point(*a),point(*z))
    seed=edge((10,10),(10,11.4));second=edge((10,11.2),(10.5,11.2));second.SetLocked(True)
    edge((10.5,11.2),(10.5,12));edge((10.5,12),(11.5,12))
    # Real same-net connection already present, not supplied by the repair.
    track(b,'+3V3',point(10,9.2),point(11.5,11.3))
    uid=force._uid(seed);second_uid=force._uid(second)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    return source,uid,second_uid


def build(source,seed,tmp_path):
    b=pcbnew.LoadBoard(str(source));q=op.plan(b,seed,authorize_source_locked=True)
    op.materialize(b,q);additive._ground_refill(b)
    candidate=force._copy_family(source,tmp_path/'reflowed');field._save_field_snapshot(b,candidate)
    return candidate,q


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_received_real_source_elbow_is_shorter_and_canonical(tmp_path,angle,mirror):
    source,seed,_=fixture(tmp_path,angle,mirror);original=source.read_bytes()
    candidate,q=build(source,seed,tmp_path)
    proof=op.receive(source,candidate,q,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['after_owner_bypass_mm']<proof['before_owner_bypass_mm']
    assert proof['all_surviving_native_partitions_preserved']
    assert not proof['current_qualified'] and not proof['release_authority']
    assert source.read_bytes()==original
    points=q['replacement_points_nm'];a,j,z=points
    assert abs(z[0]-j[0])==abs(z[1]-j[1])


@pytest.mark.parametrize('fault',['no_lock_authority','group','unknown_owner','converter','no_bypass',
    'unselected_bypass','wide','different_width','long_overrun','pad_in_tail','extra_tee',
    'retained_via','source_not_ground','deadline'])
def test_no_arbitrary_ground_or_source_ripup_authority(tmp_path,fault):
    source,seed,other=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    by_id={force._uid(t):t for t in b.GetTracks()};s=by_id[seed]
    owner=b.FindFootprintByReference('ARBITRARY_SENSOR')
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('UNRELATED_PROTECTED_CELL');b.Add(g);g.AddItem(s)
    elif fault=='unknown_owner':owner.SetValue('UNQUALIFIED_DEVICE')
    elif fault=='converter':owner.SetValue('TPS2121RUXR')
    elif fault=='no_bypass':b.Remove(b.FindFootprintByReference('C_ARBITRARY_BYPASS'))
    elif fault=='unselected_bypass':b.FindFootprintByReference('C_ARBITRARY_BYPASS').SetValue('2200uF')
    elif fault=='wide':s.SetWidth(500000)
    elif fault=='different_width':by_id[other].SetWidth(250000)
    elif fault=='long_overrun':s.SetEnd(pcbnew.VECTOR2I_MM(10,11.7))
    elif fault=='pad_in_tail':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('OTHER');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNetCode(b.GetNetcodeFromNetname('GND'))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
        p.SetPosition(pcbnew.VECTOR2I_MM(10,11.4));fp.Add(p)
    elif fault=='extra_tee':track(b,'GND',(10,10.6),(9,10.6))
    elif fault=='retained_via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(10.5,11.2));v.SetWidth(600000)
        v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNetCode(b.GetNetcodeFromNetname('GND'));b.Add(v)
    elif fault=='source_not_ground':s.SetNetCode(b.GetNetcodeFromNetname('+3V3'))
    with pytest.raises(ValueError):op.plan(b,seed,
        authorize_source_locked=fault!='no_lock_authority',timeout_s=0 if fault=='deadline' else 10.)


@pytest.mark.parametrize('fault',['forged_plan','narrow','extra_cut','pose','barrel','different_endpoint',
    'same_source','new_ground_contact'])
def test_independent_saved_receiver_rejects_unowned_changes(tmp_path,fault):
    source,seed,_=fixture(tmp_path);candidate,q=build(source,seed,tmp_path)
    b=pcbnew.LoadBoard(str(candidate));original=pcbnew.LoadBoard(str(source))
    incoming={force._uid(t) for t in b.GetTracks()}-{force._uid(t) for t in original.GetTracks()}
    edge=next(t for t in b.GetTracks() if force._uid(t) in incoming)
    if fault=='forged_plan':q=copy.deepcopy(q);q['retained_endpoint_nm'][0]+=1
    elif fault=='narrow':edge.SetWidth(150000)
    elif fault=='extra_cut':discard_items(b,[next(t for t in b.GetTracks() if t.GetNetname()=='+3V3')])
    elif fault=='pose':b.FindFootprintByReference('ARBITRARY_SENSOR').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(10,10));v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(b.GetNetcodeFromNetname('GND'));b.Add(v)
    elif fault=='different_endpoint':edge.SetEnd(edge.GetEnd()+pcbnew.VECTOR2I(1000,0))
    elif fault=='new_ground_contact':track(b,'GND',(10.25,10.95),(9.8,10.95))
    field._save_field_snapshot(b,candidate)
    proof=op.receive(source,source if fault=='same_source' else candidate,q,board_hint='synthetic')
    assert not proof['ok'] and proof['errors'],proof


def test_constructor_cannot_acquire_a_new_ground_contact_inside_the_cut_corner(tmp_path):
    source,seed,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    track(b,'GND',(10.25,10.95),(10.25,10.90))
    q=op.plan(b,seed,authorize_source_locked=True)
    with pytest.raises(ValueError,match='new_unowned_ground_contact'):op.materialize(b,q)


def test_drc_discovery_is_source_typed_and_deduplicates_reported_items(tmp_path):
    source,seed,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    finding=dict(type='clearance',items=[dict(uuid=seed)])
    r=op.discover_from_drc(b,dict(violations=[finding,finding]),authorize_source_locked=True)
    assert r['complete'] and not r['errors'] and len(r['plans'])==1,r
    assert r['plans'][0]['seed_uuid']==seed and not r['board_mutated']


def test_actual_worker_runs_one_received_atomic_elbow_step_not_later_unrelated_cuts(tmp_path):
    from unittest import mock
    import cec_certificate_repair as repair
    source,seed,_=fixture(tmp_path);child=force._copy_family(source,tmp_path/'worker')
    raw=dict(violations=[dict(type='clearance',items=[dict(uuid=seed)])])
    with mock.patch.object(repair,'_run_drc',return_value=raw) as producer:
        changed,evidence=repair._drc_dangling_cleanup_worker(str(child),max_iterations=8)
    assert changed and producer.call_count==1
    assert evidence['stop']=='single_received_source_ground_elbow_step'
    assert evidence['removed_count']==2 and len(evidence['ground_elbow_proofs'])==1
    proof=evidence['ground_elbow_proofs'][0]['receiving']
    assert proof['ok'] and proof['complete'],proof
    assert evidence['full_board_admission_still_required']


def native_span_fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,planes=True,far_pad=False):
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return (round(x*1e6),round(y*1e6))
    edge=100 if far_pad else 20
    board=_board([(8,8,'GND'),(10,10,'GND')]+([(80,80,'GND')] if far_pad else []),edge=(0,0,edge,edge));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            x,y=tuple(pad.GetPosition());pad.SetPosition(pcbnew.VECTOR2I(*point(x/1e6,y/1e6)))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
            layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
            via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet('GND'));via.SetPosition(pad.GetPosition())
            via.SetWidth(300000);via.SetDrill(200000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    a,b=point(8,8),point(10,10)
    t=track(board,'GND',[v/1e6 for v in a],[v/1e6 for v in b],layer=layer,width=.2)
    if planes:
        for face in (pcbnew.In1_Cu,pcbnew.In4_Cu):
            zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet('GND'));zone.SetLayer(face)
            zone.SetLocalClearance(200000);zone.SetMinThickness(100000);zone.Outline().NewOutline()
            for x,y in ((1,1),(edge-1,1),(edge-1,edge-1),(1,edge-1)):zone.Outline().Append(x*1000000,y*1000000)
            board.Add(zone)
    additive._ground_refill(board);source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    points=[point(x,y) for x,y in ((8,8),(8,8.5),(9.5,10),(10,10))]
    if points[0]>points[-1]:points.reverse()
    return board,source,force._uid(t),[list(p) for p in points]


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_plane_redundant_native_ground_span_reflows_without_moving_ports_or_returns(tmp_path,quarter,mirror,layer):
    board,source,uid,points=native_span_fixture(tmp_path,quarter,mirror,layer)
    old=source.read_bytes();q=native_span.plan(board,[uid],points)
    native_span.materialize(board,q);additive._ground_refill(board)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    proof=native_span.receive(source,child,q,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['source_span_already_redundant_to_retained_native_copper']
    assert proof['every_source_retained_contact_and_proved_ground_return_preserved']
    assert proof['checked_existing_smd_ground_returns']==2
    assert not proof['current_qualified'] and not proof['release_authority'] and source.read_bytes()==old


@pytest.mark.parametrize('fault',['port','diagonal','hard90','backtrack','too_long','locked','group','width','body_tee'])
def test_native_ground_span_has_no_endpoint_process_or_mesh_branch_waiver(tmp_path,fault):
    board,source,uid,points=native_span_fixture(tmp_path)
    t=next(t for t in board.GetTracks() if force._uid(t)==uid)
    if fault=='port':points[0][0]+=1
    elif fault=='diagonal':points[1][0]+=1
    elif fault=='hard90':points=[[8000000,8000000],[8000000,10000000],[10000000,10000000]]
    elif fault=='backtrack':points=[[8000000,8000000],[8000000,8500000],[8000000,8000000],[10000000,10000000]]
    elif fault=='too_long':points=[[8000000,8000000],[8000000,9900000],[8100000,10000000],[10000000,10000000]]
    elif fault=='locked':t.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);group.SetName('EXISTING_OWNER');board.Add(group);group.AddItem(t)
    elif fault=='width':t.SetWidth(500000)
    else:track(board,'GND',(9,9),(10,9),layer=pcbnew.F_Cu,width=.2)
    before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):native_span.plan(board,[uid],points)
    assert field._field_snapshot_inventory(board)==before


def test_a_real_ground_bridge_cannot_be_reclassified_as_an_already_plane_redundant_span(tmp_path):
    board,source,uid,points=native_span_fixture(tmp_path,planes=False)
    q=native_span.plan(board,[uid],points);native_span.materialize(board,q)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    proof=native_span.receive(source,child,q,board_hint='synthetic')
    assert not proof['ok'] and not proof['complete']
    assert any('not_already_native_plane_redundant' in e for e in proof['errors']),proof


@pytest.mark.parametrize('fault',['via','pad','plane','new_ground_contact','process','path'])
def test_native_ground_span_saved_replay_rejects_contact_process_and_plane_changes(tmp_path,fault):
    board,source,uid,points=native_span_fixture(tmp_path)
    if fault=='new_ground_contact':
        track(board,'GND',(7.9,8.5),(8.05,8.5),layer=pcbnew.F_Cu,width=.2)
        field._save_field_snapshot(board,source)
    q=native_span.plan(board,[uid],points);added=native_span.materialize(board,q)
    if fault=='via':next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA').SetDrill(250000)
    elif fault=='pad':next(iter(next(iter(board.GetFootprints())).Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='plane':board.Remove(next(iter(board.Zones())))
    elif fault=='process':next(t for t in board.GetTracks() if force._uid(t) in added).SetLocked(True)
    elif fault=='path':next(t for t in board.GetTracks() if force._uid(t) in added).SetEnd(pcbnew.VECTOR2I_MM(8,8.6))
    additive._ground_refill(board);child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    proof=native_span.receive(source,child,q,board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_native_ground_span_path_portfolio_is_source_derived_finite_and_nonmutating(tmp_path,quarter,mirror):
    board,source,uid,_=native_span_fixture(tmp_path,quarter,mirror)
    before=field._field_snapshot_inventory(board)
    choices=native_span.candidate_paths(board,uid)
    assert 1<=len(choices)<=10
    assert len({repr(q) for q in choices})==len(choices)
    for points in choices:
        q=native_span.plan(board,[uid],points)
        assert q['replacement_length_nm']<=q['source_length_nm']+1000000
        assert q['replacement_points_nm'][0]==q['source_points_nm'][0]
        assert q['replacement_points_nm'][-1]==q['source_points_nm'][-1]
    assert field._field_snapshot_inventory(board)==before


@pytest.mark.parametrize('context',[dict(max_trials=True),dict(max_trials=0),dict(max_trials=33),
                                  dict(board_hint=''),dict(expected_source_sha256=False)])
def test_native_ground_span_stage_requires_bounded_exact_source_context(tmp_path,context):
    board,source,uid,_=native_span_fixture(tmp_path)
    options=dict(board_hint='synthetic',expected_source_sha256=force._hash(source),max_trials=16)
    options.update(context)
    with pytest.raises(ValueError):native_span_stage.run(source,tmp_path/'stage',**options)
    assert not (tmp_path/'stage').exists()


def test_first_native_zero_return_is_the_exact_minimum_without_scanning_distant_barrels(tmp_path):
    from unittest import mock
    import cec_decoupler_cell as cells
    board,source,uid,_=native_span_fixture(tmp_path)
    first=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    pad=next(p for fp in board.GetFootprints() for p in fp.Pads() if p.GetPosition()==first.GetPosition())
    with mock.patch.object(cells,'_query_explicit_track_path_mm',wraps=cells._query_explicit_track_path_mm) as proof:
        result=cells._existing_return(board,pad,16.,allow_native_track_body=True)
    assert result[0]==0.0 and force._uid(result[1])==force._uid(first)
    assert proof.call_count==1


def test_positive_ground_return_still_checks_a_later_strictly_better_witness(tmp_path):
    from unittest import mock
    import cec_decoupler_cell as cells
    board,source,uid,_=native_span_fixture(tmp_path)
    via=[t for t in board.GetTracks() if t.GetClass()=='PCB_VIA']
    pad=next(p for fp in board.GetFootprints() for p in fp.Pads() if p.GetPosition()==via[0].GetPosition())
    # Both mocked costs must remain compatible with actual geometric lower
    # bounds. A hypothetical .5mm path cannot span the old >2mm box gap.
    via[1].SetPosition(pad.GetPosition()+pcbnew.VECTOR2I(200000,0))
    # Isolate explicit-witness ordering. The native body/fill observer now
    # independently compares a shorter real path even after a positive
    # graph answer; that distinct behavior has native transform coverage.
    with mock.patch.object(cells,'_query_explicit_track_path_mm',side_effect=[1.,.5]) as proof, \
            mock.patch.object(cells,'_straight_filled_return_mm',return_value=None):
        result=cells._existing_return(board,pad,16.,allow_native_track_body=True)
    assert result[0]==.5 and force._uid(result[1])==force._uid(via[1])
    assert proof.call_count==2


def test_far_native_ground_return_is_proved_unaffected_only_with_exact_source_fills(tmp_path):
    board,source,uid,points=native_span_fixture(tmp_path,far_pad=True)
    q=native_span.plan(board,[uid],points);native_span.materialize(board,q);additive._ground_refill(board)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    proof=native_span.receive(source,child,q,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['checked_existing_smd_ground_returns']==2
    assert len(proof['analytically_unaffected_ground_land_uuids'])==1
    assert proof['actual_return_comparison_reach_mm']==16.
    assert proof['unchanged_native_zone_fills_required_for_unaffected_scope']


@pytest.mark.parametrize('gap_nm,expected',[(0,False),(16000000,False),(16000001,False),(16000002,True)])
def test_native_return_scope_uses_an_exact_conservative_bound_not_a_distance_tolerance(gap_nm,expected):
    class Box:
        def __init__(self,x):self.x=x
        def GetX(self):return self.x
        def GetRight(self):return self.x+100
        def GetY(self):return 0
        def GetBottom(self):return 100
    class Item:
        def __init__(self,x):self.x=x
        def GetBoundingBox(self):return Box(self.x)
    assert native_span._outside_return_reach(Item(0),[Item(100+gap_nm)]) is expected


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_explicit_ordinary_shortcut_searches_the_requested_outer_bands_without_compact_rules(quarter,mirror):
    import cec_decoupler_cell as cells
    import cec_route_quality as quality
    def point(x,y):
        x,y=x-15,y-15
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return x+15,y+15
    board=_board([(*point(15,15),'GND')],edge=(0,0,30,30));board.SetCopperLayerCount(6)
    foreign=pcbnew.NETINFO_ITEM(board,'/NO_CURRENT_ASSUMPTION');board.Add(foreign)
    track(board,foreign.GetNetname(),point(13,15),point(17,15),layer=pcbnew.In2_Cu,width=4.)
    pad=next(iter(next(iter(board.GetFootprints())).Pads()));before=field._field_snapshot_inventory(board)
    kwargs=dict(diameter=.6,drill=.3,board_limits={},profile_name=None,reach_mm=3.,lock=True,
        diagnostics={},foreign_cache={},pofv_refusal='synthetic_geometry_only')
    prior,error=cells._add_ground_dogbone(board,pad,**kwargs)
    assert prior is None and error and field._field_snapshot_inventory(board)==before
    made,error=cells._add_ground_dogbone(board,pad,**dict(kwargs,diagnostics={},foreign_cache={}),extended_ordinary_reach=True)
    assert made is not None and error is None and 1.5<made['distance_mm']<=3.
    assert made['status']=='ordinary-ground-shortcut' and not made['immediate_return_qualified']
    assert made['diameter_mm']==.6 and made['drill_mm']==.3
    assert not made.get('qualified_process_exception',False)
    traces=[t for t in made['items'] if t.GetClass()=='PCB_TRACK']
    assert traces and all(quality.is_canonical_stroke(t.GetStart(),t.GetEnd(),tolerance_nm=0) for t in traces)
    assert all(field._field_snapshot_inventory(board)[uid]==value for uid,value in before.items())


@pytest.mark.parametrize('flag,reach',[(True,1.5),(True,3.01),(True,float('nan')),(1,3.),(None,3.)])
def test_outer_ground_shortcut_is_explicit_ordinary_bounded_work_not_a_process_waiver(flag,reach):
    import cec_decoupler_cell as cells
    board=_board([(10,10,'GND')],edge=(0,0,30,30));pad=next(iter(next(iter(board.GetFootprints())).Pads()))
    with pytest.raises(ValueError):cells._add_ground_return(board,pad,board_path='',reach_mm=reach,lock=True,extended_ordinary_reach=flag)

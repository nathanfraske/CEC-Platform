"""Native future-seat preclear is source-bound, finite and ordinary-only."""
import math
import json
import time

import pcbnew
import pytest

import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_future_pose_clearance as future
from test_field_proposals import track
from test_lastmile import _board
from cec_native_items import discard_items


def fixture(tmp_path, *, angle=0, back=False, ref='RENAMED_PASSIVE', net='/OTHER_CONTROL',
            blocking_net='/CONTROL', width=.2, locked=False):
    b=_board([(5,10,blocking_net),(15,10,blocking_net),(20,10,blocking_net)],edge=(0,0,30,30))
    b.Add(pcbnew.NETINFO_ITEM(b,net));b.Add(pcbnew.NETINFO_ITEM(b,'/ANCHOR_CONTROL'))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(10,13))
    for number,delta,own in (('1',-.5,'/ANCHOR_CONTROL'),('2',.5,net)):
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.4))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetNet(b.FindNet(own))
        p.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(delta,0));fp.Add(p)
    b.Add(fp)
    if back:
        for item in b.GetFootprints():item.Flip(item.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    edge=track(b,blocking_net,(5,10),(15,10),width=width,
        layer=pcbnew.B_Cu if back else pcbnew.F_Cu);edge.SetLocked(locked)
    # Rotate the entire native fixture and proposal, not just its references.
    if angle:
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    a=math.radians(angle);x,y=10-15,10-15
    at=(15+x*math.cos(a)+y*math.sin(a),15-x*math.sin(a)+y*math.cos(a))
    target_angle=(fp.GetOrientationDegrees())%360
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    board=pcbnew.LoadBoard(str(source))
    return board,source,{ref:[*at,target_angle]},force._uid(edge)


@pytest.mark.parametrize('angle,back,ref,net',[(0,False,'X_RENAMED','/FIRST'),
    (90,False,'SECOND_SUPPORT','/other/'),(180,True,'Q_OTHER','/deep/CONTROL2'),
    (270,True,'HOLDER','/FOURTH')])
def test_readonly_future_native_geometry_finds_foreign_edge_not_only_bbox(tmp_path,angle,back,ref,net):
    board,source,poses,uid=fixture(tmp_path,angle=angle,back=back,ref=ref,net=net)
    before=row._source_binding(board);saved=source.read_bytes()
    plan=future.plan(board,poses,source=source,board_hint='synthetic')
    assert plan['ok'] and plan['retired_track_uuids']==[uid],plan
    assert plan['affected_ordinary_nets']==['/CONTROL']
    assert plan['blockers'][0]['layer']==('B.Cu' if back else 'F.Cu')
    assert row._source_binding(board)==before and source.read_bytes()==saved
    assert plan['board_mutated'] is False and plan['release_authority'] is False


@pytest.mark.parametrize('fault',['locked','group','wide','power','via','arc','tht','fp_locked',
    'long_move','nonfinite','not_quarter','missing','wrong_permission'])
def test_unowned_or_specialized_items_do_not_acquire_retirement_permission(tmp_path,fault):
    b,source,poses,uid=fixture(tmp_path,locked=fault=='locked',
        width=.5 if fault=='wide' else .2,blocking_net='+5V' if fault=='power' else '/CONTROL')
    fp=b.FindFootprintByReference(next(iter(poses)));old=next(iter(b.GetTracks()))
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('protected');b.Add(g);g.AddItem(old)
    if fault in ('via','arc'):
        if fault=='via':
            obj=pcbnew.PCB_VIA(b);obj.SetPosition(pcbnew.VECTOR2I_MM(10.5,10))
            obj.SetWidth(600000);obj.SetDrill(300000);obj.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        else:
            obj=pcbnew.PCB_ARC(b);obj.SetLayer(pcbnew.F_Cu)
            obj.SetStart(pcbnew.VECTOR2I_MM(10,10));obj.SetMid(pcbnew.VECTOR2I_MM(10.5,9.8))
            obj.SetEnd(pcbnew.VECTOR2I_MM(11,10));obj.SetWidth(200000)
        obj.SetNet(old.GetNet());b.Add(obj)
    if fault=='tht':list(fp.Pads())[0].SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    if fault=='fp_locked':fp.SetLocked(True)
    if fault=='long_move':poses[fp.GetReference()][0]+=20
    if fault=='nonfinite':poses[fp.GetReference()][0]=float('nan')
    if fault=='not_quarter':poses[fp.GetReference()][2]=45
    if fault=='missing':poses={'ABSENT':[10,10,0]}
    if fault in ('tht','fp_locked','long_move','nonfinite','not_quarter','missing','wrong_permission'):
        with pytest.raises(ValueError):future.plan(b,poses,source=source,board_hint='synthetic',
            allow_locked_track_uuids=['not-an-actual-blocker'] if fault=='wrong_permission' else [])
    else:
        p=future.plan(b,poses,source=source,board_hint='synthetic')
        assert p['ok'] is False and any(not r['ordinary_retirement_allowed'] for r in p['blockers'])


def test_exact_locked_edge_permission_is_not_a_blanket_unlock(tmp_path):
    b,source,poses,uid=fixture(tmp_path,locked=True)
    p=future.plan(b,poses,source=source,board_hint='synthetic',allow_locked_track_uuids=[uid])
    assert p['ok'] and p['allow_locked_track_uuids']==[uid]
    assert next(iter(b.GetTracks())).IsLocked()


@pytest.mark.parametrize('mutation',['plan','source','pose','permission'])
def test_source_changed_or_tampered_plan_never_constructs(tmp_path,mutation):
    b,source,poses,uid=fixture(tmp_path)
    p=future.plan(b,poses,source=source,board_hint='synthetic')
    if mutation=='plan':p['retired_track_uuids']=[]
    if mutation=='source':next(iter(b.GetTracks())).SetWidth(250000)
    if mutation=='pose':b.FindFootprintByReference(next(iter(poses))).Move(pcbnew.VECTOR2I_MM(0,.1))
    if mutation=='permission':p['allow_locked_track_uuids']=[uid]
    before=row._source_binding(b)
    with pytest.raises(ValueError):future.construct(b,p,source=source)
    assert row._source_binding(b)==before


def test_real_native_preclear_receives_restored_connections_and_future_empty_seat(tmp_path):
    b,source,poses,uid=fixture(tmp_path)
    saved=source.read_bytes()
    result=future.prepare(source,poses,tmp_path/'preclear',board_hint='synthetic')
    assert result['ok'],result
    assert result['independent_ordinary_receiving']['all_prior_native_terminal_partitions_preserved']
    assert result['plan']['retired_track_uuids']==[uid]
    assert not result['future_blockers'] and not result['new_native_faults']
    child=pcbnew.LoadBoard(result['board'])
    assert not any(z.GetZoneName().startswith('TEMP FUTURE LAND ') for z in child.Zones())
    for fp in b.GetFootprints():
        other=child.FindFootprintByReference(fp.GetReference())
        assert tuple(fp.GetPosition())==tuple(other.GetPosition())
        assert fp.GetOrientationDegrees()==other.GetOrientationDegrees()
    assert source.read_bytes()==saved and not result['future_placement_admitted']


def test_persisted_full_plan_roundtrip_is_not_false_source_change(tmp_path):
    b,source,poses,_=fixture(tmp_path)
    p=future.plan(b,poses,source=source,board_hint='synthetic')
    reloaded=json.loads(json.dumps(p))
    result=future.construct(b,reloaded,source=source)
    assert result['closed'] and result['temporary_rule_areas_removed']
    assert not result['release_authority']


def test_redigested_persisted_plan_still_requires_complete_source_rederivation(tmp_path):
    b,source,poses,_=fixture(tmp_path)
    p=json.loads(json.dumps(future.plan(b,poses,source=source,board_hint='synthetic')))
    p['cut_boundaries'][0]['width_nm']+=1
    p.pop('plan_sha256');p['plan_sha256']=future.contour._digest(p)
    before=row._source_binding(b)
    with pytest.raises(ValueError,match='future_pose_source_or_permission_changed'):
        future.construct(b,p,source=source)
    assert before==row._source_binding(b)


def test_keepouts_are_cleaned_even_when_constructor_raises(tmp_path,monkeypatch):
    b,source,poses,uid=fixture(tmp_path)
    p=future.plan(b,poses,source=source,board_hint='synthetic')
    def stop(*args,**kwargs):raise RuntimeError('synthetic construction abort')
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',stop)
    with pytest.raises(RuntimeError):future.construct(b,p,source=source,source_guided_detours=False)
    assert not list(b.Zones())
    assert b.FindFootprintByReference(next(iter(poses))).GetPosition()==pcbnew.VECTOR2I_MM(10,13)


@pytest.mark.parametrize('value',[1,'yes',None])
def test_fine_preclear_search_needs_an_explicit_boolean(tmp_path,value):
    b,source,poses,_=fixture(tmp_path)
    p=future.plan(b,poses,source=source,board_hint='synthetic')
    before=row._source_binding(b)
    with pytest.raises(ValueError,match='explicit_future_pose_maze_refinement_required'):
        future.construct(b,p,source=source,refine_maze=value)
    assert row._source_binding(b)==before
    output=tmp_path/'invalid-refinement'
    with pytest.raises(ValueError,match='explicit_future_pose_maze_refinement_required'):
        future.prepare(source,poses,output,board_hint='synthetic',refine_maze=value)
    assert not output.exists()


def test_fine_preclear_forwards_without_extending_the_planar_lease(tmp_path,monkeypatch):
    b,source,poses,_=fixture(tmp_path)
    p=future.plan(b,poses,source=source,board_hint='synthetic')
    observed=[];original=fr._guarded_profiled_lastmile_legs
    def record(*args,**kwargs):
        observed.append(dict(kwargs))
        return original(*args,**kwargs)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',record)
    started=time.monotonic()
    result=future.construct(b,p,source=source,timeout_s=3.,refine_maze=True,source_guided_detours=False)
    assert result['closed'] and observed
    assert all(r['refine_maze'] is True for r in observed)
    assert all(started<r['deadline_monotonic']<=started+2.5 for r in observed)
    assert not list(b.Zones())


def test_cut_endpoints_not_upstream_tree_contacts_are_restored(tmp_path):
    b,source,poses,uid=fixture(tmp_path)
    discard_items(b,list(b.GetTracks()))
    middle=track(b,'/CONTROL',(8,10),(12,10))
    tails=[track(b,'/CONTROL',(5,10),(8,10)),track(b,'/CONTROL',(12,10),(15,10))]
    field._save_field_snapshot(b,source)
    result=future.prepare(source,poses,tmp_path/'tails-preclear',board_hint='synthetic')
    assert result['ok'],result
    assert result['plan']['retired_track_uuids']==[force._uid(middle)]
    cut=result['construction']['nets'][0]['construction']['restored'][0]['cut']
    assert cut['anchors_nm']==[[8000000,10000000],[12000000,10000000]]
    assert not result['new_native_faults']
    received=pcbnew.LoadBoard(result['board'])
    remaining={force._uid(t) for t in received.GetTracks()}
    assert all(force._uid(t) in remaining for t in tails)


@pytest.mark.parametrize('value',[0,True,10.1,float('inf')])
def test_runtime_budgets_are_not_unbounded(value):
    with pytest.raises(ValueError):future._budget(value)


def reference_fixture(tmp_path, *, angle=0, ref='IC_OTHER', width=.2, locked=False):
    # Use a renamed manufacturer-qualified part and an independently connected
    # true-ground return. REF is deliberately isolated; it is not the ground
    # pin merely because both are assigned the same schematic net.
    from test_local_branch_access import fixture as cell_fixture
    source,_,_=cell_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    owner=board.FindFootprintByReference('U_RENAMED');owner.SetReference(ref)
    # This fixture isolates the ordinary blocker case. The separate protected
    # measurement-path fixtures remain covered by the leaf-access tests.
    discard_items(board,[t for t in board.GetTracks() if t.GetNetname()=='MEASURE_MINUS'])
    board.Add(pcbnew.NETINFO_ITEM(board,'/CONTROL'))
    blocker=track(board,'/CONTROL',(12,11.25),(18,11.25),width=width)
    blocker.SetLocked(locked)
    for index,x in enumerate((12,18)):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('CONTROL_END_'+str(index));board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetPosition(pcbnew.VECTOR2I_MM(x,11.25));p.SetSize(pcbnew.VECTOR2I_MM(.45,.45))
        p.SetNet(blocker.GetNet());fp.Add(p)
    if angle:
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    field._save_field_snapshot(board,source)
    return pcbnew.LoadBoard(str(source)),source,force._uid(owner.FindPadByNumber('5')),force._uid(blocker)


@pytest.mark.parametrize('angle,ref',[(0,'IC_A'),(90,'OTHER_PACKAGE'),(180,'SENSOR'),(270,'DEVICE')])
def test_reference_link_is_source_derived_across_rotations_and_references(tmp_path,angle,ref):
    board,source,ref_uid,blocker=reference_fixture(tmp_path,angle=angle,ref=ref)
    before=row._source_binding(board);saved=source.read_bytes()
    p=future.plan_ground_reference_links(board,[ref_uid],source=source,board_hint='synthetic')
    assert p['ok'] and p['retired_track_uuids']==[blocker],p
    task=p['links'][0]['task']
    assert task['owner']==ref and task['pin']=='5' and task['role']=='ground_reference'
    assert p['links'][0]['points_nm'][0]==task['a_nm']
    assert p['links'][0]['points_nm'][-1]==task['b_nm']
    assert row._source_binding(board)==before and source.read_bytes()==saved
    assert not p['release_authority'] and p['reference_link_not_yet_constructed']


@pytest.mark.parametrize('fault',['wrong_pin','locked','wide','group','via','foreign_pad'])
def test_reference_preclear_never_invents_roles_or_retires_special_copper(tmp_path,fault):
    b,source,target,uid=reference_fixture(tmp_path,width=.5 if fault=='wide' else .2,
        locked=fault=='locked')
    if fault=='wrong_pin':
        with pytest.raises(ValueError,match='source_isolated_ground_reference_link_required'):
            future.plan_ground_reference_links(b,[force._uid(b.FindFootprintByReference('IC_OTHER')
                .FindPadByNumber('2'))],source=source,board_hint='synthetic')
        return
    blocker=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('source-owned');b.Add(g);g.AddItem(blocker)
    if fault=='via':
        item=pcbnew.PCB_VIA(b);item.SetPosition(pcbnew.VECTOR2I_MM(15,11.25))
        item.SetWidth(600000);item.SetDrill(300000);item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        item.SetNet(blocker.GetNet());b.Add(item)
    if fault=='foreign_pad':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('FOREIGN');b.Add(fp)
        item=pcbnew.PAD(fp);item.SetNumber('1');item.SetPosition(pcbnew.VECTOR2I_MM(15,11.25))
        item.SetAttribute(pcbnew.PAD_ATTRIB_SMD);item.SetLayerSet(pcbnew.PAD.SMDMask())
        item.SetSize(pcbnew.VECTOR2I_MM(.5,.5));item.SetShape(pcbnew.PAD_SHAPE_RECT)
        item.SetNet(blocker.GetNet());fp.Add(item)
    p=future.plan_ground_reference_links(b,[target],source=source,board_hint='synthetic')
    assert not p['ok'] and any(not r['ordinary_retirement_allowed'] for r in p['blockers']),p


def test_reference_link_exact_locked_scope_is_source_bound(tmp_path):
    b,source,target,uid=reference_fixture(tmp_path,locked=True)
    p=future.plan_ground_reference_links(b,[target],source=source,board_hint='synthetic',
        allow_locked_track_uuids=[uid])
    assert p['ok'] and p['retired_track_uuids']==[uid]
    p['links'][0]['points_nm'][0][0]+=1
    with pytest.raises(ValueError,match='future_pose_plan_identity_changed'):
        future.construct(b,p,source=source)


def test_source_reference_prefix_is_independently_received_not_reported_as_ground_closure(tmp_path):
    b,source,target,_=reference_fixture(tmp_path)
    result=future.prepare_ground_reference_links(source,[target],tmp_path/'reference-prefix',
        board_hint='synthetic')
    assert result['ok'],result
    assert result['source_opens']==result['opens']
    assert result['independent_ordinary_receiving']['all_prior_native_terminal_partitions_preserved']
    assert not result['future_blockers'] and not result['new_native_faults']
    assert result['plan']['reference_link_not_yet_constructed']
    assert not result['release_authority'] and not result['future_placement_admitted']


def test_reference_prefix_without_a_blocker_cannot_claim_a_terminal_was_connected(tmp_path):
    b,source,target,uid=reference_fixture(tmp_path)
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==uid])
    field._save_field_snapshot(b,source)
    result=future.prepare_ground_reference_links(source,[target],tmp_path/'empty-prefix',board_hint='synthetic')
    assert result['ok'] and result['reason']=='no_ordinary_obstruction'
    assert result['board']==str(source.resolve())
    assert result['plan']['reference_link_not_yet_constructed']
    assert not result['future_placement_admitted'] and not result['release_authority']


def test_source_cut_can_use_native_layers_without_mutating_source_connectivity(tmp_path,monkeypatch):
    b,source,poses,uid=fixture(tmp_path)
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False);z.SetDoNotAllowZoneFills(False)
    z.Outline().NewOutline()
    for p in [(9,0),(12,0),(12,30),(9,30)]:z.Outline().Append(pcbnew.VECTOR2I_MM(*p))
    b.Add(z);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source))
    proposal=future.plan(b,poses,source=source,board_hint='synthetic')
    def forbidden():raise AssertionError('live source connectivity normalization forbidden')
    monkeypatch.setattr(b,'BuildConnectivity',forbidden)
    construction=future.construct(b,proposal,source=source)
    assert construction['closed']==1,construction
    restored=construction['nets'][0]['construction']['restored'][0]
    assert restored['vias']==2 and any(lay!='F.Cu' for lay in restored['layers'])
    assert not any(z.GetZoneName().startswith('TEMP FUTURE LAND ') for z in b.Zones())
    assert next(z for z in b.Zones()).GetIsRuleArea()
    # The actual independent saved-board receiver and CLI, not just the bridge
    # emitter, must accept the alternative. Existing source keepout debt is
    # not permission to create any new copper fault.
    result=future.prepare(source,poses,tmp_path/'native-layer-preclear',board_hint='synthetic')
    assert result['ok'],result
    assert result['independent_ordinary_receiving']['all_prior_native_terminal_partitions_preserved']
    assert not result['new_native_faults']


@pytest.mark.parametrize('fault',['none','locked','branch','via','group','wide','midsegment'])
def test_source_cut_extension_follows_only_bounded_degree_two_ordinary_joints(tmp_path,fault):
    b,source,_,_=fixture(tmp_path)
    discard_items(b,list(b.GetTracks()))
    middle=track(b,'/CONTROL',(8,10),(12,10))
    left=track(b,'/CONTROL',(5,10),(8,10),width=.5 if fault=='wide' else .2)
    right=track(b,'/CONTROL',(12,10),(15,10))
    if fault=='locked':left.SetLocked(True)
    grouped=set()
    if fault=='group':grouped.add(force._uid(left))
    if fault=='branch':track(b,'/CONTROL',(8,10),(8,8))
    if fault=='midsegment':left.SetEnd(pcbnew.VECTOR2I_MM(9,10))
    if fault=='via':
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(8,10))
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetWidth(600000);via.SetDrill(300000)
        via.SetNet(left.GetNet());b.Add(via)
    binding=row._source_binding(b)
    extensions=future._extend_ordinary_cut(b,{force._uid(middle)},{'/CONTROL'},grouped,set(),
        time.monotonic()+2.,6.)
    ids={r['uuid'] for r in extensions}
    assert force._uid(right) in ids
    assert (force._uid(left) in ids)==(fault in ('none','locked'))
    if fault=='locked':
        assert not next(r for r in extensions if r['uuid']==force._uid(left))['ordinary_retirement_allowed']
    assert sum(r['source_length_nm'] for r in extensions)<=6000000
    assert row._source_binding(b)==binding
    assert not future._extend_ordinary_cut(b,{force._uid(middle)},{'/CONTROL'},set(),set(),
        time.monotonic()+2.,2.9)


@pytest.mark.parametrize('limit',[-1,True,10.01,float('nan')])
def test_source_cut_extension_cannot_expand_its_budget(tmp_path,limit):
    b,source,_,uid=fixture(tmp_path)
    with pytest.raises(ValueError,match='finite_source_cut_extension_bound_required'):
        future._extend_ordinary_cut(b,{uid},{'/CONTROL'},set(),set(),time.monotonic()+2.,limit)


def test_native_layer_search_does_not_override_source_pad_prohibition(tmp_path):
    b,source,poses,_=fixture(tmp_path)
    z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True);z.SetDoNotAllowPads(True)
    z.SetDoNotAllowFootprints(False);z.SetDoNotAllowZoneFills(False);z.Outline().NewOutline()
    for p in [(9,0),(12,0),(12,30),(9,30)]:z.Outline().Append(pcbnew.VECTOR2I_MM(*p))
    b.Add(z);before=row._source_binding(b)
    with pytest.raises(ValueError,match='PI_pose_native_pad_keepout'):
        future.plan(b,poses,source=source,board_hint='synthetic')
    assert before==row._source_binding(b)

"""Complete ordinary RC leads only; no power, source-via or package waivers."""
import math
import pcbnew
import pytest
import cec_ordinary_rc_pose as rc
import cec_ordinary_rc_reconstruction as rebuild
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_ordinary_rc_pose import fixture
from test_ordinary_rc_pose import local_rule_fixture
from test_field_proposals import track


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('local_rule',[False,True])
def test_explicit_locks_only_authorize_the_already_typed_complete_ordinary_RC_lead(tmp_path,turn,local_rule):
    b,source,uid,fpuid=(local_rule_fixture(tmp_path,turn) if local_rule else fixture(tmp_path,turn,'LOCKED'))
    original=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK'];cuts=[force._uid(t) for t in original]
    for t in original:t.SetLocked(True)
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source));before=source.read_bytes()
    with pytest.raises(ValueError):rebuild.plan(b,source,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)
    proposal=rebuild.plan(b,source,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts,allow_locked_track_uuids=cuts)
    assert proposal['allow_locked_track_uuids']==sorted(cuts)
    scope=proposal['RC_scope'];angle=math.radians(turn)
    at=[scope['source_pose_nm'][0]+round(2000000*math.sin(angle)),scope['source_pose_nm'][1]+round(2000000*math.cos(angle))]
    for t in list(b.GetTracks()):
        if force._uid(t) in cuts:b.Remove(t)
    cap,via,supply,ground=rc.pose(b,scope,at,scope['source_orientation'])
    owner=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==scope['owner_pad_uuid'])
    track(b,scope['net'],tuple(v/1e6 for v in owner.GetPosition()),tuple(v/1e6 for v in supply.GetPosition()))
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
    assert not rebuild.receive(source,child,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)['ok']
    proof=rebuild.receive(source,child,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts,allow_locked_track_uuids=cuts)
    assert proof['ok'] and proof['complete'],proof
    assert proof['complete_source_ordinary_lead_retired'] and proof['exact_unowned_source_nodes_preserved']
    assert source.read_bytes()==before and not proof['routing_admitted']


@pytest.mark.parametrize('allow',[['not-a-source-object'],[True],True,{'extra':'permission'}])
def test_source_ordinary_RC_lock_scope_is_not_a_general_unlock_or_role_waiver(tmp_path,allow):
    b,source,uid,fpuid=fixture(tmp_path);cuts=[force._uid(t) for t in b.GetTracks() if t.GetClass()=='PCB_TRACK']
    before=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):rebuild.plan(b,source,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts,allow_locked_track_uuids=allow)
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('value',[True,None,float('nan'),float('inf'),-.1,32.01])
def test_extra_work_extent_is_explicit_finite_and_bounded(value):
    with pytest.raises(ValueError):rebuild.additional_path_mm(value)


def test_default_extent_and_explicit_scope_do_not_change_source_class_or_geometry(tmp_path):
    b,source,uid,fpuid=fixture(tmp_path)
    cuts=[force._uid(t) for t in b.GetTracks() if t.GetClass()=='PCB_TRACK']
    before=field._field_snapshot_inventory(b)
    standard=rebuild.plan(b,source,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)
    extra=rebuild.plan(b,source,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts,max_additional_path_mm=24.)
    assert standard['max_additional_path_mm']==16 and extra['max_additional_path_mm']==24
    assert {k:v for k,v in standard.items() if k!='max_additional_path_mm'}=={k:v for k,v in extra.items() if k!='max_additional_path_mm'}
    assert before==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('value',[None,1,'yes',[]])
def test_neighbor_field_reflow_requires_explicit_boolean(tmp_path,value):
    source,target,uid,fpuid,cuts,_=construct(tmp_path)
    result=rebuild.receive(source,target,via_uuid=uid,board_hint='synthetic',
        retired_track_uuids=cuts,reflow_neighbor_fields=value)
    assert not result['ok'] and 'explicit_native_RC_neighbor_field_reflow_mode_required' in str(result['errors'])


def construct_with_cohort(tmp_path,turn=0,suffix=''):
    import cec_support_field_reflow as reflow
    b,source,uid,fpuid=fixture(tmp_path,turn,suffix)
    cap=next(f for f in b.GetFootprints() if force._uid(f)==fpuid)
    for p in cap.Pads():
        layers=p.GetLayerSet();layers.AddLayer(pcbnew.F_Mask);p.SetLayerSet(layers)
    for fp in b.GetFootprints():
        for f in (fp.Reference(),fp.Value()):
            f.SetLayer(pcbnew.F_SilkS);f.SetVisible(True)
            f.SetTextSize(pcbnew.VECTOR2I_MM(.6,.6));f.SetTextThickness(100000)
    # A differently named stationary neighboring owner's printed value is
    # hit by the future capacitor pad. No neighboring part moves.
    peer=pcbnew.FOOTPRINT(b);peer.SetReference('C'+suffix+'307');peer.SetValue('100nF')
    peer.SetPosition(cap.GetPosition()+pcbnew.VECTOR2I_MM(3,2));b.Add(peer)
    pad=pcbnew.PAD(peer);pad.SetNumber('1');pad.SetNet(b.FindNet('GND'))
    pad.SetPosition(peer.GetPosition());pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.F_Mask)
    pad.SetLayerSet(layers);peer.Add(pad)
    for f in (peer.Reference(),peer.Value()):
        f.SetLayer(pcbnew.F_SilkS);f.SetVisible(True)
        f.SetTextSize(pcbnew.VECTOR2I_MM(.6,.6));f.SetTextThickness(100000)
    theta=math.radians(turn)
    at=[cap.GetPosition().x+round(2000000*math.sin(theta)),
        cap.GetPosition().y+round(2000000*math.cos(theta))]
    peer.Value().SetPosition(pcbnew.VECTOR2I(*at))
    field._save_field_snapshot(b,source)
    scope=rc.plan(b,source,uid,hint='synthetic');old=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK']
    cuts=[force._uid(t) for t in old]
    for t in old:b.Remove(t)
    cap,via,supply,ground=rc.pose(b,scope,at,scope['source_orientation'])
    owner=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==scope['owner_pad_uuid'])
    track(b,scope['net'],tuple(x/1e6 for x in owner.GetPosition()),tuple(x/1e6 for x in supply.GetPosition()))
    layout=reflow.construct_collision_cohort(b,[fpuid],include_changed_owners=True)
    assert layout['ok'],layout
    assert force._uid(peer) in layout['impacted_footprint_uuids']
    target=force._copy_family(source,tmp_path/'child');additive._ground_refill(b);field._save_field_snapshot(b,target)
    return source,target,uid,fpuid,cuts,force._uid(peer)


@pytest.mark.parametrize('turn,suffix',[(0,'A'),(90,'RENAME'),(180,'Q'),(270,'Z')])
def test_cohort_replay_rediscovered_from_changed_native_lands(tmp_path,turn,suffix):
    source,target,uid,fpuid,cuts,peer_uid=construct_with_cohort(tmp_path,turn,suffix)
    before=source.read_bytes()
    assert not rebuild.receive(source,target,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)['ok']
    proof=rebuild.receive(source,target,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts,
        reflow_neighbor_fields=True)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert peer_uid in proof['reflowed_native_field_owner_uuids'] and fpuid in proof['reflowed_native_field_owner_uuids']
    assert proof['exact_unowned_source_nodes_preserved'] and source.read_bytes()==before


@pytest.mark.parametrize('fault',['text','size','stroke','hidden','layer','mirror','unrelated_pose','neighbor_pad'])
def test_cohort_cannot_change_identity_style_visibility_or_unrelated_geometry(tmp_path,fault):
    source,target,uid,fpuid,cuts,peer_uid=construct_with_cohort(tmp_path)
    b=pcbnew.LoadBoard(str(target));peer=next(f for f in b.GetFootprints() if force._uid(f)==peer_uid)
    f=peer.Value()
    if fault=='text':peer.SetValue('MALICIOUS')
    elif fault=='size':f.SetTextSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='stroke':f.SetTextThickness(50000)
    elif fault=='hidden':f.SetVisible(False)
    elif fault=='layer':f.SetLayer(pcbnew.F_Fab)
    elif fault=='mirror':f.SetMirrored(not f.IsMirrored())
    elif fault=='unrelated_pose':b.FindFootprintByReference('U71').Reference().Move(pcbnew.VECTOR2I_MM(1,0))
    else:peer.SetPosition(peer.GetPosition()+pcbnew.VECTOR2I_MM(.1,0))
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(target),b)
    proof=rebuild.receive(source,target,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts,
        reflow_neighbor_fields=True)
    assert not proof['ok'] and not proof['complete'] and proof['errors']


def construct(tmp_path,turn=0,suffix='',transitions=False):
    b,source,uid,fpuid=fixture(tmp_path,turn,suffix)
    scope=rc.plan(b,source,uid,hint='synthetic')
    old=[t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK']
    cuts=[force._uid(t) for t in old]
    proposal=rebuild.plan(b,source,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)
    for t in old:b.Remove(t)
    theta=math.radians(turn)
    at=[scope['source_pose_nm'][0]+round(2000000*math.sin(theta)),
        scope['source_pose_nm'][1]+round(2000000*math.cos(theta))]
    cap,via,supply,ground=rc.pose(b,scope,at,scope['source_orientation'])
    rc.preflight(b,scope)
    owner=next(p for f in b.GetFootprints() for p in f.Pads() if force._uid(p)==scope['owner_pad_uuid'])
    if transitions:
        def rotate(x,y):
            return (15+(x-15)*math.cos(theta)+(y-15)*math.sin(theta),
                15-(x-15)*math.sin(theta)+(y-15)*math.cos(theta))
        A=rotate(10,11);B=tuple(x/1e6 for x in supply.GetPosition());mid=rotate(11,12)
        track(b,scope['net'],tuple(x/1e6 for x in owner.GetPosition()),A)
        track(b,scope['net'],A,mid,pcbnew.B_Cu)
        track(b,scope['net'],mid,B,pcbnew.B_Cu)
        for at_v in (A,B):
            v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*at_v));v.SetNetCode(supply.GetNetCode())
            v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    else:
        track(b,scope['net'],tuple(x/1e6 for x in owner.GetPosition()),tuple(x/1e6 for x in supply.GetPosition()))
    target=force._copy_family(source,tmp_path/'child');additive._ground_refill(b);field._save_field_snapshot(b,target)
    return source,target,uid,fpuid,cuts,proposal


@pytest.mark.parametrize('turn,suffix',[(0,''),(90,'A'),(180,'RENAME'),(270,'Q')])
@pytest.mark.parametrize('transitions',[False,True])
def test_renamed_rotated_complete_ordinary_lead_and_actual_owned_ground_return(tmp_path,turn,suffix,transitions):
    source,target,uid,fpuid,cuts,proposal=construct(tmp_path,turn,suffix,transitions)
    before=source.read_bytes()
    assert not rc.receive(source,target,via_uuid=uid,board_hint='synthetic')['ok']
    proof=rebuild.receive(source,target,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['actual_owned_ground_barrel_geometry_preserved'] and proof['all_surviving_source_native_partitions_preserved']
    assert proof['new_standard_transition_count']==(2 if transitions else 0)
    assert source.read_bytes()==before and not proof['release_authority'] and not proof['current_qualified']


@pytest.mark.parametrize('fault',['partial','wrong_net','locked','grouped','third_pad','source_via','narrow',
    'wide','too_long','inner_face','branch','detached_cycle'])
def test_complete_source_lead_authority_is_rederived_not_asserted(tmp_path,fault):
    b,source,uid,fpuid=fixture(tmp_path)
    old=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    cuts=[force._uid(old)]
    if fault=='partial':
        track(b,old.GetNetname(),(12,10),(12.2,10));cuts=[force._uid(old)]
    elif fault=='wrong_net':old.SetNetCode(b.GetNetcodeFromNetname('GND'))
    elif fault=='locked':old.SetLocked(True)
    elif fault=='grouped':
        g=pcbnew.PCB_GROUP(b);g.SetName('protected');b.Add(g);g.AddItem(old)
    elif fault=='third_pad':
        fp=pcbnew.FOOTPRINT(b);p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNetCode(old.GetNetCode())
        p.SetPosition(pcbnew.VECTOR2I_MM(11,10));p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);p.SetLayerSet(layers);fp.Add(p);b.Add(fp)
    elif fault=='source_via':
        v=pcbnew.PCB_VIA(b);v.SetNetCode(old.GetNetCode());v.SetPosition(pcbnew.VECTOR2I_MM(11,10))
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='narrow':old.SetWidth(100000)
    elif fault=='wide':old.SetWidth(500000)
    elif fault=='too_long':old.SetEnd(pcbnew.VECTOR2I_MM(29,10))
    elif fault=='inner_face':old.SetLayer(pcbnew.In2_Cu)
    elif fault=='branch':
        old.SetEnd(pcbnew.VECTOR2I_MM(11,10));track(b,old.GetNetname(),(11,10),(12,10))
        track(b,old.GetNetname(),(11,10),(11,11));cuts=[force._uid(t) for t in b.GetTracks() if t.GetClass()=='PCB_TRACK']
    else:
        for A,B in (((20,20),(22,20)),((22,20),(22,22)),((22,22),(20,22)),((20,22),(20,20))):track(b,old.GetNetname(),A,B)
        cuts=[force._uid(t) for t in b.GetTracks() if t.GetClass()=='PCB_TRACK']
    frozen=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):rebuild.plan(b,source,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)
    assert frozen==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('fault',['package','value','owner','missing_return','ground_diameter','ground_drill',
    'cut_incomplete','source_lead_retained','no_connection','new_power','new_ground','thin_track','inner_track',
    'small_via','small_drill','extra_via','outline','noncardinal'])
def test_saved_reconstruction_cannot_smuggle_contact_copper_or_identity_changes(tmp_path,fault):
    source,target,uid,fpuid,cuts,proposal=construct(tmp_path,transitions=True)
    b=pcbnew.LoadBoard(str(target));cap=next(f for f in b.GetFootprints() if force._uid(f)==fpuid)
    ground=next(t for t in b.GetTracks() if force._uid(t)==uid)
    own_net=proposal['RC_scope']['net']
    routes=[t for t in b.GetTracks() if t.GetNetname()==own_net]
    via=next(t for t in routes if t.GetClass()=='PCB_VIA');t=next(t for t in routes if t.GetClass()=='PCB_TRACK')
    if fault=='package':cap.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(1.2,.8))
    elif fault=='value':cap.SetValue('10uF')
    elif fault=='owner':b.FindFootprintByReference('U71').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='missing_return':b.Remove(ground)
    elif fault=='ground_diameter':ground.SetWidth(550000)
    elif fault=='ground_drill':ground.SetDrill(350000)
    elif fault=='cut_incomplete':cuts=[]
    elif fault=='source_lead_retained':
        parent=pcbnew.LoadBoard(str(source))
        original=next(t for t in parent.GetTracks() if force._uid(t) in cuts)
        retained=pcbnew.Cast_to_PCB_TRACK(pcbnew.Cast_to_BOARD_ITEM(original.Clone()))
        assert force._uid(retained)==cuts[0]
        retained.SetNet(b.FindNet(own_net));b.Add(retained)
    elif fault=='no_connection':t.SetEnd(pcbnew.VECTOR2I_MM(20,20))
    elif fault=='new_power':
        net=pcbnew.NETINFO_ITEM(b,'UNAUTHORISED_POWER');b.Add(net);t.SetNet(net)
    elif fault=='new_ground':t.SetNet(b.FindNet('GND'))
    elif fault=='thin_track':t.SetWidth(100000)
    elif fault=='inner_track':t.SetLayer(pcbnew.In2_Cu)
    elif fault=='small_via':via.SetWidth(500000)
    elif fault=='small_drill':via.SetDrill(250000)
    elif fault=='extra_via':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(own_net));v.SetPosition(pcbnew.VECTOR2I_MM(20,20))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='outline':next(d for d in b.GetDrawings() if d.GetLayer()==pcbnew.Edge_Cuts).Move(pcbnew.VECTOR2I_MM(.1,0))
    else:cap.SetOrientationDegrees(13)
    # Save an intentionally bad fixture with the NON-normalising native IO.
    # Production's identity guard remains mandatory for real constructors.
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(target),b)
    proof=rebuild.receive(source,target,via_uuid=uid,board_hint='synthetic',retired_track_uuids=cuts)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof

"""Local return visibility is not permission for duplicate copper or holes."""
import copy,time
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_access_completion as op
from cec_native_items import discard_items
from test_native_ground_terminal_branch import fixture as base
from test_field_proposals import track


def fixture(tmp_path,*,quarter=0,mirror=False,layer=pcbnew.F_Cu,mode='reuse',observed=False):
    b,source,ids,points,owner,cap,old_via=base(tmp_path,quarter=quarter,mirror=mirror,layer=layer)
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in ids])
    detour=[(8,8),(3,8),(3,18),(18,18),(18,12),(12,12)]
    if observed:detour=[(8,8),(8,10),(10,12),(12,12)]
    for a,z in zip(detour,detour[1:]):
        aa,zz=point(*a),point(*z)
        track(b,'GND',[v/1e6 for v in aa],[v/1e6 for v in zz],layer=layer,width=.2)
    ground=cap.FindPadByNumber('2')
    if mode=='vip':ground.SetSize(pcbnew.VECTOR2I_MM(.9,.9))
    elif mode=='reuse':
        v=pcbnew.PCB_VIA(b);v.SetPosition(point(10.5,8));v.SetNet(b.FindNet('GND'))
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    old=cells._existing_return(b,ground,16.,allow_native_track_body=True)
    assert (old is not None and old[0]>1.5) if observed else old is None
    return b,source,ground,point


def saved(tmp_path,**options):
    b,source,pad,point=fixture(tmp_path,**options)
    args=dict(board_hint='synthetic',pad_uuid=force._uid(pad))
    q=op.plan(source,**args)
    target=Path(op.write_private(q,tmp_path/'candidate')['candidate'])
    return source,target,args,q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('mode',['reuse','vip','dogbone'])
def test_unknown_local_return_gets_real_source_bound_access_in_native_frames(tmp_path,quarter,mirror,layer,mode):
    source,target,args,q=saved(tmp_path,quarter=quarter,mirror=mirror,layer=layer,mode=mode)
    before=source.read_bytes();r=op.receive(source,target,**args)
    assert r['ok'] and r['complete'],r
    assert r['saved_return_witness_mm']<=1.5 and r['every_source_native_partition_identical']
    assert r['new_holes']==(mode!='reuse') and r['source_unobserved_return_not_an_open_or_infinite_length']
    assert r['all_source_known_returns']['ok'] and r['all_source_known_returns']['complete']
    assert not r['current_qualified'] and not r['release_authority'] and source.read_bytes()==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('mode',['reuse','vip','dogbone'])
def test_known_nonlocal_return_is_strictly_shortened_without_losing_any_source_terminal(tmp_path,quarter,mirror,layer,mode):
    source,target,args,q=saved(tmp_path,quarter=quarter,mirror=mirror,layer=layer,mode=mode,observed=True)
    r=op.receive(source,target,**args)
    assert r['ok'] and r['complete'],r
    assert q['source_return_witness_mm']>1.5 and r['saved_return_witness_mm']<=1.5
    assert r['shortened_return_witness_mm']==pytest.approx(q['source_return_witness_mm']-r['saved_return_witness_mm'])
    assert r['all_source_known_returns']['ok'] and not r['release_authority']


def test_larger_netclass_via_geometry_is_not_divided_by_nm_conversion(tmp_path,monkeypatch):
    b,source,pad,point=fixture(tmp_path,mode='dogbone');seen={}
    original=op.cells._netclass;producer=op.cells._add_ground_return
    def spec(board,net):return dict(original(board,net),via_dia=.8,via_drill=.4)
    def capture(*args,**kwargs):
        seen['geometry']=kwargs['pofv_geometry'];return producer(*args,**kwargs)
    monkeypatch.setattr(op.cells,'_netclass',spec);monkeypatch.setattr(op.cells,'_add_ground_return',capture)
    q=op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad))
    assert seen['geometry']==(.8,.4)
    via=next(v for v in q['ops'] if v[0]=='via')
    assert via[2:] == [400000,800000]


@pytest.mark.parametrize('fault',['width','layer','extra','source_part','unlocked','hole','new_root_position'])
def test_source_replay_rejects_every_unowned_saved_change(tmp_path,fault):
    source,target,args,q=saved(tmp_path,mode='vip' if fault in ('hole','new_root_position') else 'reuse')
    b=pcbnew.LoadBoard(str(target));old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    added=next(t for t in b.GetTracks() if force._uid(t) not in old)
    if fault=='width':added.SetWidth(199999)
    elif fault=='layer':added.SetLayer(pcbnew.B_Cu)
    elif fault=='extra':track(b,'GND',(24,24),(25,24),width=.2)
    elif fault=='source_part':next(iter(b.GetFootprints())).SetValue('not-the-source-part')
    elif fault=='unlocked':added.SetLocked(False)
    elif fault=='hole':added.SetDrill(200000)
    else:added.Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,target);r=op.receive(source,target,**args)
    assert not r['ok'] and not r['complete'] and r['errors']


def test_ground_pad_bridge_copper_already_present_is_not_trace_progress(tmp_path):
    b,source,pad,point=fixture(tmp_path);fp=pcbnew.FOOTPRINT(b);fp.SetReference('unrelated_native_ground_bridge');b.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('a');p.SetNet(b.FindNet('GND'));p.SetPosition(point(10.1,8))
    p.SetSize(pcbnew.VECTOR2I_MM(1.8,.8));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(p)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='already_covered_by_source_copper'):
        op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad))


def test_real_footprint_plated_reference_is_not_an_excuse_to_add_a_duplicate_via(tmp_path):
    b,source,pad,point=fixture(tmp_path,mode='vip');p=pcbnew.PAD(pad.GetParentFootprint())
    p.SetNumber(pad.GetNumber());p.SetNet(b.FindNet('GND'));p.SetPosition(pad.GetPosition())
    p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetLayerSet(pcbnew.PAD.PTHMask());pad.GetParentFootprint().Add(p)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='already_contacts_a_plated_reference_pad'):
        op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad))


@pytest.mark.parametrize('fault',['known_return','DNP','not_ground','wrong_identity'])
def test_source_ground_identity_and_unobserved_scope_are_explicit(tmp_path,fault):
    b,source,pad,point=fixture(tmp_path);uid=force._uid(pad)
    if fault=='known_return':track(b,'GND',(9.5,8),(10.5,8),width=.2)
    elif fault=='DNP':pad.GetParentFootprint().SetDNP(True)
    elif fault=='not_ground':pad.SetNet(b.FindNet('+3V3'))
    else:uid='not-a-source-pad'
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',pad_uuid=uid)


@pytest.mark.parametrize('options',[dict(reach_mm=0),dict(reach_mm=1.50001),dict(reach_mm=True),
    dict(timeout_s=0),dict(timeout_s=11),dict(timeout_s=True),dict(board_hint='')])
def test_unbounded_or_untyped_scope_never_becomes_a_constructor_permit(tmp_path,options):
    b,source,pad,point=fixture(tmp_path);args=dict(board_hint='synthetic',pad_uuid=force._uid(pad));args.update(options)
    with pytest.raises(ValueError):op.plan(source,**args)


def test_worker_cannot_forge_a_different_native_addition(tmp_path):
    b,source,pad,point=fixture(tmp_path);q=op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad))
    q=copy.deepcopy(q);q['ops'][0][3]=100000
    with pytest.raises(ValueError,match='stale_or_forged'):op.construct(q)


def test_tiny_diagonal_entirely_inside_retained_via_is_not_emitted(tmp_path):
    b,source,pad,point=fixture(tmp_path)
    near=min((v for v in b.GetTracks() if v.GetClass()=='PCB_VIA'),
        key=lambda v:(v.GetPosition()-pad.GetPosition()).EuclideanNorm())
    near.Move(pcbnew.VECTOR2I(0,25000));additive._ground_refill(b);field._save_field_snapshot(b,source)
    q=op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad))
    assert q['fully_retained_land_covered_finishing_limbs_suppressed']==1
    assert len(q['ops'])==1 and q['ops'][0][1][1]==q['ops'][0][2][1]
    board=op.construct(q);additive._ground_refill(board)
    target=force._copy_family(source,tmp_path/'contained-end');field._save_field_snapshot(board,target)
    r=op.receive(source,target,board_hint='synthetic',pad_uuid=force._uid(pad))
    assert r['ok'] and r['complete'] and r['new_holes']==0


@pytest.mark.parametrize('missing',[1,2])
def test_a_new_ground_hole_cannot_qualify_without_both_actual_saved_references(tmp_path,missing):
    b,source,pad,point=fixture(tmp_path,mode='vip')
    discard_items(b,list(b.Zones())[:missing]);field._save_field_snapshot(b,source)
    q=op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad))
    board=op.construct(q);additive._ground_refill(board)
    target=force._copy_family(source,tmp_path/'missing-reference');field._save_field_snapshot(board,target)
    r=op.receive(source,target,board_hint='synthetic',pad_uuid=force._uid(pad))
    assert not r['ok'] and not r['complete'] and r['errors']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('observed',[False,True])
def test_ground_root_on_literal_source_track_adds_no_surface_loop_in_native_frames(tmp_path,quarter,mirror,layer,observed):
    b,source,pad,point=fixture(tmp_path,quarter=quarter,mirror=mirror,layer=layer,mode='dogbone',observed=observed)
    args=dict(board_hint='synthetic',pad_uuid=force._uid(pad),prefer_source_track_root=True)
    q=op.plan(source,**args)
    assert q['source_track_root'] and len(q['ops'])==1 and q['ops'][0][0]=='via'
    assert q['source_track_root']['only_literal_source_track_centres']
    board=op.construct(q);additive._ground_refill(board)
    target=force._copy_family(source,tmp_path/'source-track-root');field._save_field_snapshot(board,target)
    r=op.receive(source,target,**args)
    assert r['ok'] and r['complete'] and r['new_holes']==1,r
    assert r['all_source_known_returns']['ok'] and r['saved_return_witness_mm']<=1.5
    assert r['every_source_native_partition_identical'] and not r['release_authority']


@pytest.mark.parametrize('face',[pcbnew.B_Cu,pcbnew.In2_Cu,pcbnew.In3_Cu])
def test_source_track_root_checks_foreign_copper_on_other_layers(tmp_path,face):
    b,source,pad,point=fixture(tmp_path,mode='dogbone',observed=True)
    t=track(b,'+3V3',(7,8),(10.5,8),width=3.,layer=face)
    before=len(list(b.GetTracks()))
    root=op._source_track_root(b,pad,(.6,.3),1.5,time.monotonic()+10.)
    assert root is None and len(list(b.GetTracks()))==before


@pytest.mark.parametrize('fault',['grouped','mask','wide','foreign'])
def test_source_track_root_requires_actual_owned_small_ground_carriers(tmp_path,fault):
    b,source,pad,point=fixture(tmp_path,mode='dogbone',observed=True)
    group=pcbnew.PCB_GROUP(b);group.SetName('PROTECTED_NATIVE_COPPER');b.Add(group)
    for t in b.GetTracks():
        if t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND':continue
        if fault=='grouped':group.AddItem(t)
        elif fault=='wide':t.SetWidth(400000)
        elif fault=='mask':t.SetHasSolderMask(True)
        else:t.SetNetCode(b.GetNetcodeFromNetname('+3V3'))
    before=len(list(b.GetTracks()))
    assert op._source_track_root(b,pad,(.6,.3),1.5,time.monotonic()+10.) is None
    assert len(list(b.GetTracks()))==before


@pytest.mark.parametrize('value',[1,None,'yes'])
def test_source_track_root_preference_is_a_literal_policy_not_worker_authority(tmp_path,value):
    b,source,pad,point=fixture(tmp_path)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad),prefer_source_track_root=value)


def test_source_track_root_position_is_exact_not_a_nearby_unowned_drill(tmp_path):
    b,source,pad,point=fixture(tmp_path,mode='dogbone',observed=True)
    q=op.plan(source,board_hint='synthetic',pad_uuid=force._uid(pad),prefer_source_track_root=True)
    assert q['source_track_root'];q=copy.deepcopy(q);q['ops'][0][1][0]+=1
    with pytest.raises(ValueError,match='stale_or_forged'):op.construct(q)


def test_failed_all_terminal_preservation_keeps_the_actual_failure_stack(tmp_path,monkeypatch):
    source,target,args,q=saved(tmp_path)
    failed=dict(ok=False,complete=False,errors=['source-ground-observation-deadline'],elapsed_s=.01)
    monkeypatch.setattr(op.returns,'receive',lambda *args,**kwargs:failed)
    r=op.receive(source,target,**args)
    assert not r['ok'] and r['all_source_known_returns']==failed

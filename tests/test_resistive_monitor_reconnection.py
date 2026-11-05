"""Positive manufacturer roles, not names or historical widths, own a leaf."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_resistive_monitor_reconnection as repair
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
from test_closed_monitor_consumer_loads import fixture as closed_fixture


def case(tmp_path,monkeypatch,*,angle=0,mirrored=False,barrel=False):
    b,root,allocated,trunk,row,selected,tails=closed_fixture(monkeypatch,tmp_path,count=1)
    for t in tails:t.SetWidth(200000)
    top=selected[0][0];pad=top.FindPadByNumber('1')
    for a,z in [((-5,-5),(50,-5)),((50,-5),(50,25)),((50,25),(-5,25)),((-5,25),(-5,-5))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT);edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(edge)
    if barrel:
        for t in tails:t.SetLayer(pcbnew.In2_Cu)
        for p,generated in ((pad,True),(root,False)):
            via=pcbnew.PCB_VIA(b);via.SetPosition(p.GetPosition());via.SetNet(p.GetNet());via.SetWidth(900000)
            via.SetDrill(500000);via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
            if generated:
                g=pcbnew.PCB_GROUP(b);g.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(g);g.AddItem(via)
    ghosts=[]
    for xy in ((3.5,14),(5,12.5),(5,8)):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*xy));t.SetEnd(t.GetStart());ghosts.append(t)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*ghosts]:
        if angle:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirrored:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=Path(b.GetFileName());field._save_field_snapshot(b,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    points=[list(t.GetStart()) for t in ghosts]
    args=dict(board_hint='unfamiliar-monitor-board',pad_uuid=force._uid(pad),target_uuid=force._uid(root),
        points_nm=points,retire_root_pickup=barrel,allow_locked_source=True)
    return source,args,(b,root,top,tails,allocated,row)


def make(source,tmp_path,proposal):
    child=force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(repair.construct(source,proposal),child)
    return child


def test_entire_stage_floor_operator_defers_positive_monitor_instead_of_overbuilding_it(tmp_path,monkeypatch):
    import cec_retained_consumer_floor_repair as floor
    source,args,parts=case(tmp_path,monkeypatch)
    ids=[force._uid(t) for t in parts[3]]
    points=[list(q) for q in floor.chains._chain(parts[3])]
    with pytest.raises(ValueError,match='positively_typed_monitor_requires_monitor_reconnection_owner'):
        floor.plan(source,board_hint=args['board_hint'],retired_track_uuids=ids,
            points_nm=points,allow_locked_source=True)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirrored',[False,True])
@pytest.mark.parametrize('barrel',[False,True])
def test_real_saved_monitor_reconnection_is_pose_reference_and_generation_independent(tmp_path,monkeypatch,angle,mirrored,barrel):
    source,args,parts=case(tmp_path,monkeypatch,angle=angle,mirrored=mirrored,barrel=barrel)
    original=source.read_bytes();proposal=repair.plan(source,**args)
    proposal=json.loads(json.dumps(proposal));child=make(source,tmp_path,proposal)
    got=repair.receive(source,child,proposal,board_hint=args['board_hint'])
    assert got['ok'] and got['complete'] and not got['errors'],got['errors']
    assert got['centerline_removed_mm']>2 and got['source_allocation_group_exact']
    assert got['all_surviving_native_partitions_preserved'] and got['all_preexisting_allocated_full_width_joins_preserved']
    assert len(got['retired_via_uuids'])==int(barrel) and not got['new_vias'] and not got['pads_moved']
    assert proposal['width_nm']==200000
    assert proposal['source_budget']['base_consumer_current_authority']['amps']==3.0004
    assert proposal['source_budget']['aggregate_current_authority']['amps']==20.
    assert not got['source_current_reduced'] and not got['release_authority'] and not got['current_or_terminal_capacity_qualified']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['unknown_resistor','wrong_value','wide_source','locked','extra_load',
    'target_shared_trunk','target_monitor_root','non45','hard90','backtracking','changed_root','bool_permission','leave_root_barrel'])
def test_source_unknowns_do_not_acquire_a_monitor_or_power_budget_waiver(tmp_path,monkeypatch,fault):
    source,args,parts=case(tmp_path,monkeypatch,barrel=fault=='leave_root_barrel')
    b,root,top,tails,allocated,row=parts
    if fault=='unknown_resistor':top.SetField('MPN','unknown')
    elif fault=='wrong_value':top.SetValue('10k')
    elif fault=='wide_source':tails[0].SetWidth(477639)
    elif fault=='locked':
        for t in tails:t.SetLocked(True)
        args['allow_locked_source']=False
    elif fault=='extra_load':
        f=pcbnew.FOOTPRINT(b);b.Add(f);p=pcbnew.PAD(f);f.Add(p);p.SetNet(root.GetNet());p.SetPosition(root.GetPosition())
    elif fault=='target_shared_trunk':args['target_uuid']=force._uid(next(t for t in b.GetTracks() if t.GetWidth()>1000000))
    elif fault=='target_monitor_root':args['target_uuid']=args['pad_uuid']
    elif fault=='non45':args['points_nm'][1][0]+=1
    elif fault=='hard90':args['points_nm']=[[3500000,14000000],[5000000,14000000],[5000000,8000000]]
    elif fault=='backtracking':args['points_nm']=[[3500000,14000000],[3500000,15000000],[3500000,14000000],[5000000,12500000],[5000000,8000000]]
    elif fault=='changed_root':args['points_nm'][0][1]+=1
    elif fault=='bool_permission':args['retire_root_pickup']='true'
    elif fault=='leave_root_barrel':args['retire_root_pickup']=False
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):repair.plan(source,**args)


@pytest.mark.parametrize('fault',['width','face','point','lock','extra_copper','pose','mpn','group','sidecar','restore_pickup'])
def test_saved_exact_receiver_refuses_unowned_changes(tmp_path,monkeypatch,fault):
    source,args,parts=case(tmp_path,monkeypatch,barrel=True)
    proposal=repair.plan(source,**args);child=make(source,tmp_path,proposal);b=pcbnew.LoadBoard(str(child))
    old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    t=next(t for t in b.GetTracks() if force._uid(t) not in old)
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='point':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='lock':t.SetLocked(not t.IsLocked())
    elif fault=='extra_copper':
        q=t.Duplicate();q.m_Uuid.Clone(pcbnew.KIID());b.Add(q)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='mpn':next(iter(b.GetFootprints())).SetField('MPN','unowned')
    elif fault=='group':next(iter(b.Groups())).SetName('unowned')
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='restore_pickup':
        parent=pcbnew.LoadBoard(str(source));via=next(t for t in parent.GetTracks() if force._uid(t) in proposal['retired_via_uuids'])
        b.Add(via.Duplicate())
    field._save_field_snapshot(b,child)
    got=repair.receive(source,child,proposal,board_hint=args['board_hint'])
    assert not got['ok'] and got['errors']


@pytest.mark.parametrize('key',['width_nm','source_sha256','authority_sha256','source_budget','retired_track_uuids'])
def test_caller_cannot_forge_the_source_typed_contract(tmp_path,monkeypatch,key):
    source,args,parts=case(tmp_path,monkeypatch);proposal=repair.plan(source,**args);child=make(source,tmp_path,proposal)
    if key=='width_nm':proposal[key]-=1
    elif key=='source_budget':proposal[key]['current_authority']['amps']=.01
    elif key=='retired_track_uuids':proposal[key]=[]
    else:proposal[key]='0'*64
    got=repair.receive(source,child,proposal,board_hint=args['board_hint'])
    assert not got['ok'] and got['errors']

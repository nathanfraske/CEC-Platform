"""Receive orphan pivots, not translated supply lands or lost old branches."""
import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_support_pivot_receiving as pivot
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, *, angle=0, back=False, name='ANY_SUPPORT'):
    board=_board([(5,10,'/CONTROL'),(8,10,'/CONTROL')],edge=(0,0,30,30))
    board.Add(pcbnew.NETINFO_ITEM(board,'+3V3'))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(name);fp.SetValue('10k')
    fp.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    for number,x,net in (('1',9.5,'+3V3'),('2',10.5,'/CONTROL')):
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.4))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetNet(board.FindNet(net))
        p.SetPosition(pcbnew.VECTOR2I_MM(x,10));fp.Add(p)
    board.Add(fp);track(board,'/CONTROL',(5,10),(8,10))
    for part in board.GetFootprints():
        part.Reference().SetPosition(part.GetPosition()+pcbnew.VECTOR2I_MM(0,2))
        part.Value().SetVisible(False)
    if back:
        # Mirror the complete physical arrangement. Flipping only each body
        # in place would reverse the support while leaving its peer on the
        # wrong side, so the synthetic straight route would cross +3V3.
        for part in [*board.GetFootprints(),*board.GetTracks()]:
            part.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if angle:
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    target=force._copy_family(source,tmp_path/'child');b=pcbnew.LoadBoard(str(target))
    component=b.FindFootprintByReference(name);anchor=pcbnew.VECTOR2I(component.FindPadByNumber('1').GetPosition())
    component.SetOrientationDegrees((component.GetOrientationDegrees()+180)%360)
    component.Move(anchor-component.FindPadByNumber('1').GetPosition())
    pad=component.FindPadByNumber('2')
    # _board's numbered-less pad has an exact native coordinate; no fake
    # connectivity or board-specific geometry is substituted in the test.
    peer=list(b.FindFootprintByReference('X2').Pads())[0]
    edge=pcbnew.PCB_TRACK(b);edge.SetNet(pad.GetNet());edge.SetLayer(component.GetLayer())
    edge.SetStart(pad.GetPosition());edge.SetEnd(peer.GetPosition());edge.SetWidth(200000)
    b.Add(edge);field._save_field_snapshot(b,target)
    return source,target,name


@pytest.mark.parametrize('angle,back,name',[(0,False,'RENAMED_R'),(90,False,'SUPPORT_TWO'),
    (180,True,'X_OTHER'),(270,True,'FOURTH_SUPPORT')])
def test_real_native_pivot_and_original_connections_are_received(tmp_path,angle,back,name):
    source,target,name=fixture(tmp_path,angle=angle,back=back,name=name)
    files=[p.read_bytes() for p in (source,target)]
    result=pivot.receive(source,target,board_hint='synthetic')
    assert result['ok'] and result['complete'],{k:result.get(k) for k in ('errors','source_opens','opens','new_native_faults')}
    assert result['source_opens']==1 and result['opens']==0
    assert result['pivots'][0]['fixed_pad']=='1'
    assert result['original_native_conductor_and_terminal_partitions_preserved']
    assert result['independent_pose_and_additive_replay']['ok']
    assert [p.read_bytes() for p in (source,target)]==files
    assert not result['placement_authority_transferred'] and not result['power_authority']
    assert not additive.receive(source,target)['ok']


@pytest.mark.parametrize('fault',['supply_move','definition','no_pivot','non_quarter','flip',
    'parent_copper','power_addition','orphan_branch','orphan_other_pad','unrelated_text','grouped','locked'])
def test_scope_does_not_widen_to_arbitrary_motion_or_ordinary_net_deletion(tmp_path,fault):
    source,target,name=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(target));fp=b.FindFootprintByReference(name)
    if fault=='supply_move':fp.Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='definition':fp.SetValue('22k')
    elif fault=='no_pivot':
        first=pcbnew.LoadBoard(str(source));orig=first.FindFootprintByReference(name)
        fp.SetOrientationDegrees(orig.GetOrientationDegrees());fp.SetPosition(orig.GetPosition())
    elif fault=='non_quarter':fp.Rotate(fp.FindPadByNumber('1').GetPosition(),pcbnew.EDA_ANGLE(15,pcbnew.DEGREES_T))
    elif fault=='flip':fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault=='parent_copper':
        old=next(t for t in b.GetTracks() if tuple(t.GetStart())==(5000000,10000000))
        old.SetWidth(250000)
    elif fault=='power_addition':track(b,'+3V3',(24,24),(25,24))
    elif fault in ('orphan_branch','orphan_other_pad','grouped','locked'):
        parent=pcbnew.LoadBoard(str(source));owner=parent.FindFootprintByReference(name)
        if fault=='orphan_branch':track(parent,'/CONTROL',(10.5,10),(10.5,12))
        elif fault=='orphan_other_pad':
            other=parent.FindFootprintByReference('X1');other.SetPosition(pcbnew.VECTOR2I_MM(10.5,10))
        elif fault=='grouped':
            g=pcbnew.PCB_GROUP(parent);g.SetName('immutable');parent.Add(g);g.AddItem(owner)
        else:owner.SetLocked(True)
        field._save_field_snapshot(parent,source)
    else:fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1.1,1.1))
    field._save_field_snapshot(b,target)
    result=pivot.receive(source,target,board_hint='synthetic')
    assert not result['ok'] and not result['complete'] and result['errors'],result


def silk_fixture(tmp_path):
    source,target,name=fixture(tmp_path)
    ids=[]
    for path in (source,target):
        b=pcbnew.LoadBoard(str(path))
        for ref in ('X1','X2'):
            fp=b.FindFootprintByReference(ref);fp.Reference().SetLayer(pcbnew.F_SilkS)
            fp.Reference().SetVisible(True);fp.Reference().SetPosition(pcbnew.VECTOR2I_MM(20,20))
            fp.Reference().SetTextSize(pcbnew.VECTOR2I_MM(1,1));fp.Reference().SetTextThickness(150000)
            if path==source:ids.append(force._uid(fp.Reference()))
        field._save_field_snapshot(b,path)
    return source,target,ids


@pytest.mark.parametrize('fault',['none','moved','not_overlap','wrong_type','unknown_uuid'])
def test_inherited_silk_requires_positive_exact_source_collision(tmp_path,fault):
    source,target,ids=silk_fixture(tmp_path)
    parent,child=map(lambda p:pcbnew.LoadBoard(str(p)),(source,target))
    if fault=='moved':
        child.FindFootprintByReference('X1').Reference().Move(pcbnew.VECTOR2I_MM(0,1))
        field._save_field_snapshot(child,target)
    if fault=='not_overlap':
        for b,p in ((parent,source),(child,target)):
            b.FindFootprintByReference('X1').Reference().Move(pcbnew.VECTOR2I_MM(0,5));field._save_field_snapshot(b,p)
    _,old=additive._nodes(source);_,new=additive._nodes(target)
    finding=dict(type='clearance' if fault=='wrong_type' else 'silk_overlap',
        items=[dict(uuid='unknown' if fault=='unknown_uuid' and i==0 else uid) for i,uid in enumerate(ids)])
    proof=pivot._inherited_silk_overlap(parent,child,finding,old,new)
    assert bool(proof) is (fault=='none')
    if proof:assert proof['native_source_collision'] and not proof['inherited_debt_qualified']


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
def test_inherited_pad_mask_collision_has_exact_source_native_witness(tmp_path,angle,back):
    source,target,_=fixture(tmp_path,angle=angle,back=back)
    ids=[]
    for path in (source,target):
        b=pcbnew.LoadBoard(str(path));fp=b.FindFootprintByReference('X1')
        pad=next(iter(fp.Pads()));label=fp.Reference()
        label.SetVisible(True);label.SetPosition(pad.GetPosition())
        label.SetLayer(pcbnew.B_SilkS if back else pcbnew.F_SilkS)
        label.SetTextSize(pcbnew.VECTOR2I_MM(1,1));label.SetTextThickness(150000)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.6,1.6))
        layers=pad.GetLayerSet();layers.AddLayer(pcbnew.B_Mask if back else pcbnew.F_Mask)
        pad.SetLayerSet(layers)
        pad.SetLocalSolderMaskMargin(100000)
        if path==source:ids=[force._uid(label),force._uid(pad)]
        field._save_field_snapshot(b,path)
    parent,child=map(lambda p:pcbnew.LoadBoard(str(p)),(source,target))
    _,old=additive._nodes(source);_,new=additive._nodes(target)
    finding=dict(type='silk_over_copper',items=[dict(uuid=uid) for uid in ids])
    saved=[p.read_bytes() for p in (source,target)]
    proof=pivot._inherited_silk_overlap(parent,child,finding,old,new)
    assert proof and proof['native_source_collision'] and proof['exact_authored_source_geometry']
    assert not proof['inherited_debt_qualified'] and not proof['release_authority']
    assert saved==[p.read_bytes() for p in (source,target)]


@pytest.mark.parametrize('fault',['moved_label','moved_pad','negative_mask',
    'masked_pad','changed_resolved_mask','no_copper_collision','unknown_uuid','wrong_type'])
def test_pad_mask_report_not_a_blanket_inherited_silk_waiver(tmp_path,fault):
    source,target,_=fixture(tmp_path);ids=[]
    for path in (source,target):
        b=pcbnew.LoadBoard(str(path));fp=b.FindFootprintByReference('X1')
        pad=next(iter(fp.Pads()));label=fp.Reference()
        label.SetVisible(True);label.SetPosition(pad.GetPosition())
        label.SetLayer(pcbnew.F_SilkS);label.SetTextSize(pcbnew.VECTOR2I_MM(1,1))
        label.SetTextThickness(150000);pad.SetLocalSolderMaskMargin(100000)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.6,1.6))
        layers=pad.GetLayerSet();layers.AddLayer(pcbnew.F_Mask);pad.SetLayerSet(layers)
        if fault=='negative_mask':pad.SetLocalSolderMaskMargin(-100000)
        if fault=='masked_pad':
            mask=pad.GetLayerSet();mask.RemoveLayer(pcbnew.F_Mask);pad.SetLayerSet(mask)
        if fault=='no_copper_collision':label.Move(pcbnew.VECTOR2I_MM(0,5))
        if path==target and fault=='moved_label':label.Move(pcbnew.VECTOR2I_MM(0,.1))
        if path==target and fault=='moved_pad':pad.Move(pcbnew.VECTOR2I_MM(0,.1))
        if path==source:ids=[force._uid(label),force._uid(pad)]
        field._save_field_snapshot(b,path)
    parent,child=map(lambda p:pcbnew.LoadBoard(str(p)),(source,target))
    if fault=='changed_resolved_mask':
        # A live project setting is not necessarily in the PCB node bytes.
        p=next(iter(child.FindFootprintByReference('X1').Pads()))
        p.SetLocalSolderMaskMargin(200000)
    _,old=additive._nodes(source);_,new=additive._nodes(target)
    finding=dict(type='clearance' if fault=='wrong_type' else 'silk_over_copper',
        items=[dict(uuid='unknown' if fault=='unknown_uuid' and i==0 else uid)
               for i,uid in enumerate(ids)])
    assert pivot._inherited_silk_overlap(parent,child,finding,old,new) is None


@pytest.mark.parametrize('value',[0,True,10.001,float('inf')])
def test_receiving_budget_cannot_expand(value):
    assert not pivot.receive('missing','missing',board_hint='synthetic',timeout_s=value)['ok']


def test_pure_orphan_pivot_can_gain_an_existing_trace_without_new_copper(tmp_path):
    source,target,name=fixture(tmp_path)
    # Move the fixed control peer clear of the future support land, then
    # extend its immutable source trace to the future seat (not the orphan's
    # present seat). These are test source definitions, not admitted repairs.
    parent=pcbnew.LoadBoard(str(source));peer=parent.FindFootprintByReference('X2')
    peer.SetPosition(pcbnew.VECTOR2I_MM(7,10));edge=next(iter(parent.GetTracks()))
    edge.SetEnd(pcbnew.VECTOR2I_MM(7,10));tail=track(parent,'/CONTROL',(7,10),(8.5,10))
    field._save_field_snapshot(parent,source)
    child=pcbnew.LoadBoard(str(source));fp=child.FindFootprintByReference(name)
    anchor=pcbnew.VECTOR2I(fp.FindPadByNumber('1').GetPosition())
    fp.SetOrientationDegrees(180);fp.Move(anchor-fp.FindPadByNumber('1').GetPosition())
    field._save_field_snapshot(child,target)
    proof=pivot.receive(source,target,board_hint='synthetic')
    assert proof['ok'] and proof['cohort_native_orphan_connection_gain']==1,proof['errors']
    assert proof['independent_pose_and_additive_replay']['added_native_uuids']==[]
    assert not proof['power_authority'] and not proof['release_authority']

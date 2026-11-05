"""Complete control-owner motion never substitutes labels for Source proof."""
import time
import pcbnew
import pytest
import cec_control_shunt_placement as op
import cec_device_power_roles as roles
from test_source_device_pinmap import fixture as canonical_fixture


def fixture(tmp_path,monkeypatch,turn=0,back=False):
    board,owner,model,root,tree=canonical_fixture(tmp_path,monkeypatch,turn,back)
    cap=pcbnew.FOOTPRINT(board);board.Add(cap);cap.SetReference('C_renamed_supply')
    cap.SetValue('100nF');cap.SetFPID(pcbnew.LIB_ID('fixture','C_0402_1005Metric'))
    supply=next(p for p in owner.Pads() if p.GetNumber()=='3')
    ground=next(p for p in owner.Pads() if p.GetNumber()=='49')
    cap.SetPosition(supply.GetPosition())
    for num,net,dx in [('1',supply.GetNet(),.4),('2',ground.GetNet(),.9)]:
        p=pcbnew.PAD(cap);p.SetNumber(num);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetNet(net)
        p.SetPosition(supply.GetPosition()+pcbnew.VECTOR2I_MM(dx,0));cap.Add(p)
    if back:cap.Flip(cap.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    poses={owner.GetReference():[owner.GetPosition().x/1e6+1,owner.GetPosition().y/1e6,
             owner.GetOrientationDegrees()+90],cap.GetReference():[cap.GetPosition().x/1e6+1,
             cap.GetPosition().y/1e6,cap.GetOrientationDegrees()+90]}
    return board,owner,cap,root,poses


def compile(board,owner,root,poses):
    return op._complete_owner_motion(board,owner,poses,board_hint=str(root),deadline=time.monotonic()+8)


def posed(board,owner,poses):
    # A real independent native copy, not a reconstructed/fake Source proof.
    child=pcbnew.BOARD()
    for net in board.GetNetsByNetcode().values():
        if net.GetNetCode()>0:child.Add(pcbnew.NETINFO_ITEM(child,net.GetNetname(),net.GetNetCode()))
    for fp in board.GetFootprints():
        clone=pcbnew.FOOTPRINT(fp);child.Add(clone)
        for p in clone.Pads():p.SetNet(child.FindNet(p.GetNetname()))
        target=poses.get(fp.GetReference())
        if target:
            clone.SetPosition(pcbnew.VECTOR2I_MM(*target[:2]));clone.SetOrientationDegrees(target[2])
    return child


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_complete_source_owner_and_selected_bypass_rigid_receiver(tmp_path,monkeypatch,turn,back):
    board,owner,cap,root,poses=fixture(tmp_path,monkeypatch,turn,back)
    item=compile(board,owner,root,poses)
    assert item['selected_followers']==[dict(ref=cap.GetReference(),owner=owner.GetReference(),
        pin='3',rail=owner.FindPadByNumber('3').GetNetname())]
    assert not item['current_authority'] and not item['trace_retirement_authority']
    child=posed(board,owner,poses)
    op._receive_complete_owner_motion(board,child,item,poses,board_hint=str(root),deadline=time.monotonic()+8)


@pytest.mark.parametrize('fault',['missing_cap','missing_pose','wrong_kind','locked','group','dnp',
    'far','noncardinal','source_label','expired'])
def test_motion_requires_full_source_and_bypass_cohort(tmp_path,monkeypatch,fault):
    board,owner,cap,root,poses=fixture(tmp_path,monkeypatch)
    if fault=='missing_cap':board.Remove(cap)
    elif fault=='missing_pose':poses.pop(cap.GetReference())
    elif fault=='wrong_kind':cap.SetValue('10pF')
    elif fault=='locked':owner.SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(board);board.Add(g);g.AddItem(owner)
    elif fault=='dnp':owner.SetDNP(True)
    elif fault=='far':poses[owner.GetReference()][0]+=33
    elif fault=='noncardinal':poses[owner.GetReference()][2]+=1
    elif fault=='source_label':root.write_text(root.read_text().replace('(name "EN")','(name "FAKE")'))
    with pytest.raises(ValueError):
        op._complete_owner_motion(board,owner,poses,board_hint=str(root),
            deadline=time.monotonic()+(-1 if fault=='expired' else 8))


def test_stationary_legacy_scope_does_not_require_complete_motion(tmp_path,monkeypatch):
    board,owner,cap,root,poses=fixture(tmp_path,monkeypatch)
    assert compile(board,owner,root,{}) is None
    assert compile(board,owner,root,{owner.GetReference():[
        owner.GetPosition().x/1e6,owner.GetPosition().y/1e6,owner.GetOrientationDegrees()]}) is None


@pytest.mark.parametrize('fault',['size','shape','net','uuid','face','pose','part','locked','pad_missing'])
def test_receiver_checks_every_actual_rigid_land_and_part(tmp_path,monkeypatch,fault):
    board,owner,cap,root,poses=fixture(tmp_path,monkeypatch)
    item=compile(board,owner,root,poses);child=posed(board,owner,poses)
    moved=child.FindFootprintByReference(owner.GetReference())
    pad=next(p for p in moved.Pads() if p.GetNumber()=='49')
    if fault=='size':pad.SetSize(pcbnew.VECTOR2I_MM(.8,.7))
    elif fault=='shape':pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif fault=='net':pad.SetNet(moved.FindPadByNumber('3').GetNet())
    elif fault=='uuid':pad.m_Uuid.Clone(pcbnew.KIID())
    elif fault=='face':moved.Flip(moved.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault=='pose':moved.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='part':moved.SetValue('WRONG')
    elif fault=='locked':moved.SetLocked(True)
    else:moved.Remove(pad)
    with pytest.raises(ValueError):op._receive_complete_owner_motion(board,child,item,poses,
        board_hint=str(root),deadline=time.monotonic()+8)

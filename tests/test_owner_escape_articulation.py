"""Stationary-support articulation is generic proposal scope, not permission."""
import math

import pytest
pcbnew = pytest.importorskip('pcbnew')

import cec_owner_escape_articulation as articulation
import cec_support_motion as motion


def fixture(*, angle=0, back=False, offset=(0,0), count=12):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_MinClearance = 200000
    board.GetDesignSettings().m_TrackMinWidth = 200000
    nets = []
    for name in ('/renamed_target','/arbitrary_foreign'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets.append(net)
    origin=pcbnew.VECTOR2I_MM(20+offset[0],20+offset[1])
    owner=pcbnew.FOOTPRINT(board);owner.SetReference('RENAMED_IC')
    owner.SetPosition(origin);board.Add(owner)
    support=pcbnew.FOOTPRINT(board);support.SetReference('BYPASS')
    support.SetPosition(origin+pcbnew.VECTOR2I_MM(1,2.275));board.Add(support)
    def pad(fp,number,x,y,size,net):
        p=pcbnew.PAD(fp);p.SetNumber(str(number));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(*size))
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetNet(net)
        p.SetPosition(origin+pcbnew.VECTOR2I_MM(x,y));fp.Add(p);return p
    pin=pad(owner,'signal',.25,1.15,(.2,.6),nets[0])
    for i in range(count-1):
        pad(owner,i,(-.25 if i==0 else .75 if i==1 else (i-5)*.5),
            1.15 if i<2 else -1.15,(.2,.6),nets[1])
    pad(support,'return',.225,2.275,(.9,.95),nets[1])
    pad(support,'supply',1.775,2.275,(.9,.95),nets[1])
    for fp in (owner,support):
        if back:fp.Flip(origin,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle:fp.Rotate(origin,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    target=dict(ref=owner.GetReference(),target_net=nets[0].GetNetname(),
        motion='toward_endpoint',companion_refs=[support.GetReference()])
    return board,owner,support,pin,target


def snapshot(board):
    return [(fp.GetReference(),tuple(fp.GetPosition()),fp.GetOrientationDegrees(),
        [(p.GetNumber(),tuple(p.GetPosition()),p.GetNetCode()) for p in fp.Pads()])
        for fp in board.GetFootprints()]


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('count,offset',[(3,(0,0)),(16,(17,-11))])
def test_gap_alignment_renamed_rotated_and_backside(angle,back,count,offset):
    board,owner,support,pin,target=fixture(angle=angle,back=back,count=count,offset=offset)
    before=snapshot(board)
    rows=articulation.proposals(board,target,
        support_limits=motion.limits(max_owner_copper_pads=16))
    assert rows and snapshot(board)==before
    # The narrow clear channel is centred 0.75 mm tangent to the starting pin.
    assert any(abs(math.hypot(row['dx_mm'],row['dy_mm'])-.75)<2e-6 for row in rows)
    assert all(row['mobility_companion_refs']==[] for row in rows)
    assert all(row['escape_lane']['stationary_companions']==['BYPASS'] for row in rows)
    assert all(row['escape_lane']['qualification_authority'] is False for row in rows)
    assert all(row['escape_lane']['copper_and_reconnect_proof_required'] is True for row in rows)
    assert all(row['escape_lane']['pad_clear_layers']==['B.Cu' if back else 'F.Cu'] for row in rows)


@pytest.mark.parametrize('condition',['default_scope','locked','grouped','tht',
    'no_support','wrong_motion','no_target','immutable','no_obstruction'])
def test_no_scope_expansion_or_unproved_objective(condition):
    board,owner,support,pin,target=fixture()
    limits=motion.limits(max_owner_copper_pads=16)
    if condition=='default_scope':limits=None
    elif condition=='locked':owner.SetLocked(True)
    elif condition=='grouped':
        group=pcbnew.PCB_GROUP(board);group.AddItem(owner);board.Add(group)
    elif condition=='tht':pin.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif condition=='no_support':target['companion_refs']=[]
    elif condition=='wrong_motion':target['motion']='away_from_endpoint'
    elif condition=='no_target':target['target_net']='/absent'
    elif condition=='immutable':limits['immutable_refs']=[owner.GetReference()]
    elif condition=='no_obstruction':support.Move(pcbnew.VECTOR2I_MM(4,0))
    before=snapshot(board)
    assert not articulation.proposals(board,target,support_limits=limits)
    assert snapshot(board)==before


@pytest.mark.parametrize('kwargs',[{'max_candidates':0},{'max_raw':513},
    {'escape_mm':float('nan')},{'escape_mm':0},{'max_candidates':True}])
def test_finite_bounds(kwargs):
    board,owner,support,pin,target=fixture()
    with pytest.raises(ValueError):articulation.proposals(board,target,**kwargs)


def test_nonblocking_support_follows_but_obstructor_stays_put():
    board,owner,support,pin,target=fixture()
    extra=pcbnew.FOOTPRINT(board);extra.SetReference('SECOND_SUPPORT')
    extra.SetPosition(owner.GetPosition()+pcbnew.VECTOR2I_MM(-3,0));board.Add(extra)
    for index in range(2):
        p=pcbnew.PAD(extra);p.SetNumber(str(index));p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        p.SetPosition(extra.GetPosition()+pcbnew.VECTOR2I_MM(index,0));extra.Add(p)
    target['companion_refs'].append(extra.GetReference())
    before=snapshot(board)
    rows=articulation.proposals(board,target,support_limits=motion.limits(max_owner_copper_pads=16))
    assert rows[0]['mobility_companion_refs']==['SECOND_SUPPORT']
    assert rows[0]['escape_lane']['stationary_companions']==['BYPASS']
    assert any(not row['mobility_companion_refs'] for row in rows)
    assert snapshot(board)==before


def test_normal_owner_portfolio_includes_subsets_without_deduping_to_rigid(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    board,owner,support,pin,target=fixture()
    source=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    original=source.read_bytes()
    target=repair.asdict(repair.FootprintRepairTarget(**target,
        endpoint_ref='REMOTE',endpoint_pad='1',endpoint_x_mm=20,endpoint_y_mm=24,
        hit_count=1,distance_mm=3,priority=(0,)))
    monkeypatch.setattr(repair,'_occupancy_relocation_candidates',lambda *a,**k:[])
    monkeypatch.setattr(repair,'_footprint_relocation_candidates',lambda *a,**k:[])
    monkeypatch.setattr(repair,'_target_endpoint_access_candidates_worker',lambda *a,**k:{})
    rows=repair._combined_footprint_relocation_candidates(str(source),target,
        support_limits=motion.limits(max_owner_copper_pads=16))
    assert rows and all(row['generator']=='owner_stationary_support_lane' for row in rows)
    assert source.read_bytes()==original
    pose=dict(dx_mm=.75,dy_mm=0,rotation_delta_deg=0)
    assert repair._footprint_candidate_key('ANY',pose)!=repair._footprint_candidate_key(
        'ANY',dict(pose,mobility_companion_refs=[]))

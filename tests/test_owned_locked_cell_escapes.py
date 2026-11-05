"""An explicit source-owned local lock scope never unlocks a rail or group."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_measurement_leaf as leaf
import cec_force_current as force
from test_cell_escape_replan import fixture as base_fixture
from test_escape_pose_frontier import native_part


def fixture(monkeypatch,quarter=0,back=False,prefix='one'):
    board,poses,owner,cap=base_fixture(monkeypatch,prefix)
    peer=native_part(board,prefix+'_peer','TLV7011DBVR',(10,13),
        [('1',1,-1),('2',-1,0),('3',-1,1),('4',1,1),('5',1,0)],
        'Package_TO_SOT_SMD','SOT-23-5',1.5,1.5)
    for pin,net in [('1','INPUT_N'),('2','GND'),('3','OUT'),('4','INPUT_P'),('5','RAIL')]:
        peer.FindPadByNumber(pin).SetNet(board.FindNet(net))
    follower=native_part(board,prefix+'_follower','100nF',(12,13),
        [('1',-.5,0),('2',.5,0)],'Capacitor_SMD','C_0603_1608Metric',.7,.4)
    follower.FindPadByNumber('1').SetNet(board.FindNet('RAIL'));follower.FindPadByNumber('2').SetNet(board.FindNet('GND'))
    assigned={'one':dict(cap_ref=cap.GetReference(),requirement=dict(ref=owner.GetReference(),pin='5',rail='RAIL',return_rail='GND')),
        'two':dict(cap_ref=follower.GetReference(),requirement=dict(ref=peer.GetReference(),pin='5',rail='RAIL',return_rail='GND'))}
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**kw:dict(assigned=assigned))
    ids=[];points=[(9,9),(8,9),(8,14),(9,14)]
    for a,z in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(board.FindNet('OUT'));t.SetLocked(True);board.Add(t);ids.append(force._uid(t))
    for fp in (peer,follower):poses[fp.GetReference()]=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6+1,fp.GetOrientationDegrees()]
    def point(p):
        x,y=p
        for _ in range(quarter):x,y=y,-x
        return x,y
    for fp in board.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:
            fp.SetLayer(pcbnew.B_Cu)
            for pad in fp.Pads():
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);layers.AddLayer(pcbnew.B_Mask);pad.SetLayerSet(layers)
    for t in board.GetTracks():
        a,z=point(tuple(t.GetStart())),point(tuple(t.GetEnd()))
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        if back:t.SetLayer(pcbnew.B_Cu)
    poses={ref:[*point(pose[:2]),pose[2]+quarter*90] for ref,pose in poses.items()}
    return board,poses,owner,peer,ids


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_explicit_owned_locked_cell_rebuild_keeps_source_roles_and_all_restoration_obligations(monkeypatch,tmp_path,quarter,back):
    b,poses,owner,peer,ids=fixture(monkeypatch,quarter,back,prefix='renamed_'+str(quarter));before=row._source_binding(b)
    old=escape.prepare(b,poses,board_hint='opaque')
    assert not old['scalar_links'] and not set(ids)&set(old['retired_track_uuids'])
    q=escape.prepare(b,poses,board_hint='opaque',allow_owned_locked_escapes=True)
    assert row._source_binding(b)==before and q['allow_owned_locked_escapes']
    assert q['row_plan']['allow_owned_locked'] and len(q['scalar_links'])==1
    link=q['scalar_links'][0]
    assert set(link['track_uuids'])==set(ids)==set(link['source_owned_locked_track_uuids'])
    assert link['allow_owned_locked'] and set(ids)<=set(q['retired_track_uuids'])
    assert link['peer_pad_uuid']==force._uid(peer.FindPadByNumber('3'))
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),b);source=pcbnew.LoadBoard(str(path))
    source_ids={force._uid(t) for t in b.GetTracks()};escape.apply_private(b,q)
    assert source_ids-{force._uid(t) for t in b.GetTracks()}==set(q['retired_track_uuids'])
    requests=escape.obligations(source,b,q);request=requests['scalar_link:'+force._uid(owner.FindPadByNumber('1'))]
    assert request['a']['at_nm']==list(owner.FindPadByNumber('1').GetPosition())
    assert request['b']['at_nm']==list(peer.FindPadByNumber('3').GetPosition())
    assert not q['routing_admitted'] and not q['release_authority']
    assert q['requires_new_placement_power_and_independent_saved_board_receiving']


@pytest.mark.parametrize('flag',[True])
def test_locked_scalar_permission_still_requires_explicit_directed_manufacturer_native_leaf(monkeypatch,flag):
    b,poses,owner,peer,ids=fixture(monkeypatch)
    with pytest.raises(ValueError):leaf.plan_scalar_link(b,force._uid(owner.FindPadByNumber('1')),owner_refs=[owner.GetReference(),peer.GetReference()])
    q=leaf.plan_scalar_link(b,force._uid(owner.FindPadByNumber('1')),owner_refs=[owner.GetReference(),peer.GetReference()],allow_owned_locked=flag)
    assert set(q['track_uuids'])==set(ids) and not q['current_authority'] and not q['release_authority']


@pytest.mark.parametrize('flag',[1,0,None,'yes',[],{}])
def test_untyped_policy_cannot_create_a_source_cut(monkeypatch,flag):
    b,poses,owner,peer,ids=fixture(monkeypatch);before=row._source_binding(b)
    with pytest.raises(ValueError):escape.prepare(b,poses,board_hint='opaque',allow_owned_locked_escapes=flag)
    with pytest.raises(ValueError):leaf.plan_scalar_link(b,force._uid(owner.FindPadByNumber('1')),owner_refs=[owner.GetReference(),peer.GetReference()],allow_owned_locked=flag)
    assert row._source_binding(b)==before


@pytest.mark.parametrize('fault',['drop_flag','false_flag','extra_cut','source_width'])
def test_native_source_policy_or_inventory_forgery_cannot_move_the_cell(monkeypatch,fault):
    b,poses,owner,peer,ids=fixture(monkeypatch);q=escape.prepare(b,poses,board_hint='opaque',allow_owned_locked_escapes=True)
    q=copy.deepcopy(q)
    if fault=='drop_flag':q.pop('allow_owned_locked_escapes')
    elif fault=='false_flag':q['allow_owned_locked_escapes']=False
    elif fault=='extra_cut':q['retired_track_uuids'].append('not-source-owned')
    else:next(t for t in b.GetTracks() if force._uid(t)==ids[1]).SetWidth(210000)
    before=row._source_binding(b)
    with pytest.raises(ValueError):escape.apply_private(b,q)
    assert row._source_binding(b)==before


@pytest.mark.parametrize('protection',['power','pair','group','shared'])
def test_explicit_motion_cannot_steal_power_pairs_grouped_or_shared_middle_copper(monkeypatch,protection):
    b,poses,owner,peer,ids=fixture(monkeypatch)
    if protection=='power':monkeypatch.setattr(escape.topology,'board_current_domains',lambda *a,**kw:{'OUT':{}})
    elif protection=='pair':monkeypatch.setattr(escape.fr,'coupled_pair_nets',lambda *a,**kw:{'OUT'})
    elif protection=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('unrelated protected route');b.Add(group)
        group.AddItem(next(t for t in b.GetTracks() if force._uid(t)==ids[1]))
    else:
        fp=native_part(b,'fixed_shared_land','UNKNOWN',(8,11),[('1',0,0)],'Test','NotAnInput',.3,.3)
        fp.FindPadByNumber('1').SetNet(b.FindNet('OUT'))
    before=row._source_binding(b);q=escape.prepare(b,poses,board_hint='opaque',allow_owned_locked_escapes=True)
    assert ids[1] not in q['retired_track_uuids'] and not q['scalar_links']
    assert row._source_binding(b)==before and not q['release_authority']

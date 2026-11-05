"""Ordinary isolated geometry may move; current/connected terminals may not."""
import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_orphan_support_access as access
import cec_support_pivot_receiving as receiver
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path, quarter=0, back=False, name='OPAQUE_COMPONENT'):
    board=_board([(6,9,'/INPUT'),(6,12,'/OUTPUT')],edge=(0,0,30,30))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(name);fp.SetValue('2.2k')
    board.Add(fp);fp.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    for number,x,net in [('1',9.5,'/INPUT'),('2',10.5,'/OUTPUT')]:
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.4))
        p.SetPosition(pcbnew.VECTOR2I_MM(x,10));p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetNet(board.FindNet(net));fp.Add(p)
    for part in board.GetFootprints():
        part.Reference().SetPosition(part.GetPosition()+pcbnew.VECTOR2I_MM(0,3))
        part.Reference().SetVisible(False)
        part.Value().SetVisible(False)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    child=force._copy_family(source,tmp_path/'child');b=pcbnew.LoadBoard(str(child))
    support=b.FindFootprintByReference(name);support.Move(pcbnew.VECTOR2I_MM(-1,2))
    one,two=[support.FindPadByNumber(str(i)) for i in (1,2)]
    track(b,'/OUTPUT',tuple(v/1e6 for v in two.GetPosition()),(9.5,13.5))
    track(b,'/OUTPUT',(9.5,13.5),(6,13.5))
    track(b,'/OUTPUT',(6,13.5),(6,12))
    track(b,'/INPUT',tuple(v/1e6 for v in one.GetPosition()),(8.5,9))
    track(b,'/INPUT',(8.5,9),(6,9))
    for native,path in [(board,source),(b,child)]:
        if back:
            for item in [*native.GetFootprints(),*native.GetTracks(),*native.GetDrawings()]:
                item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if quarter:
            for item in [*native.GetFootprints(),*native.GetTracks(),*native.GetDrawings()]:
                item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        field._save_field_snapshot(native,path)
    return source,child,name


@pytest.mark.parametrize('quarter,back,name',[(0,False,'NO_REFDES_POLICY'),
    (1,False,'RENAMED'),(2,True,'X_RANDOM'),(3,True,'OTHER')])
def test_fully_isolated_source_ordinary_support_reseat_replays(tmp_path,quarter,back,name):
    source,child,name=fixture(tmp_path,quarter,back,name)
    saved=[p.read_bytes() for p in (source,child)]
    proof=receiver.receive(source,child,board_hint='synthetic',fully_isolated_reseat=True)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['source_opens']==2 and proof['opens']==0
    assert proof['cohort_native_orphan_connection_gain']==2
    assert proof['original_native_conductor_and_terminal_partitions_preserved']
    assert proof['independent_pose_and_additive_replay']['ok']
    assert not proof['power_authority'] and not proof['placement_authority_transferred']
    assert saved==[p.read_bytes() for p in (source,child)]
    # Existing anchor-preserving pivot API remains deliberately narrower.
    assert not receiver.receive(source,child,board_hint='synthetic')['ok']


@pytest.mark.parametrize('fault',['power','contact','group','locked',
    'drill','too_far','raw_angle','definition','extra_text','original_track'])
def test_no_hidden_power_or_source_contact_or_metadata_authority(tmp_path,fault):
    source,child,name=fixture(tmp_path)
    parent=pcbnew.LoadBoard(str(source));last=pcbnew.LoadBoard(str(child))
    owner=parent.FindFootprintByReference(name);target=last.FindFootprintByReference(name)
    if fault=='power':
        for b in (parent,last):
            b.Add(pcbnew.NETINFO_ITEM(b,'+3V3'))
            b.FindFootprintByReference(name).FindPadByNumber('1').SetNet(b.FindNet('+3V3'))
    elif fault=='contact':
        track(parent,'/INPUT',(9.5,10),(9.5,11))
    elif fault=='group':
        group=pcbnew.PCB_GROUP(parent);group.SetName('retained');parent.Add(group);group.AddItem(owner)
    elif fault=='locked':owner.SetLocked(True)
    elif fault=='drill':
        for part in (owner,target):
            p=part.FindPadByNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            p.SetLayerSet(pcbnew.PAD.PTHMask());p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='too_far':target.Move(pcbnew.VECTOR2I_MM(8,0))
    elif fault=='raw_angle':target.Rotate(target.GetPosition(),pcbnew.EDA_ANGLE(13,pcbnew.DEGREES_T))
    elif fault=='definition':target.SetValue('3.3k')
    elif fault=='extra_text':target.Reference().SetTextSize(pcbnew.VECTOR2I_MM(2,2))
    else:
        track(parent,'/INPUT',(4,4),(5,4))
        track(last,'/INPUT',(4,4),(5,4)).SetWidth(250000)
    field._save_field_snapshot(parent,source);field._save_field_snapshot(last,child)
    proof=receiver.receive(source,child,board_hint='synthetic',fully_isolated_reseat=True)
    assert not proof['ok'] and proof['errors'],proof


def test_targets_derive_two_actual_orphans_not_reference_or_net_substrings(tmp_path):
    source,_,name=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    rows=access.targets(board,source,board_hint='synthetic')
    assert {r['ref'] for r in rows}=={name}
    assert {r['target_net'] for r in rows}=={'/INPUT','/OUTPUT'}
    track(board,'/INPUT',(9.5,10),(9.5,11))
    assert not access.targets(board,source,board_hint='synthetic')


def test_foreign_native_source_contact_cannot_be_hidden_by_net_filtered_graph(tmp_path):
    source,_,name=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(source))
    contact=track(board,'/OUTPUT',(9.5,10),(9.5,11))
    saved=(contact.GetNetname(),contact.GetNetCode(),tuple(contact.GetStart()))
    assert not access.targets(board,source,board_hint='synthetic')
    assert saved==(contact.GetNetname(),contact.GetNetCode(),tuple(contact.GetStart()))


@pytest.mark.parametrize('value',[None,0,1,'yes'])
def test_reseat_mode_is_explicit_boolean(value):
    proof=receiver.receive('missing','missing',board_hint='synthetic',fully_isolated_reseat=value)
    assert not proof['ok'] and 'explicit_isolated_reseat_mode_required' in proof['errors'][0]


@pytest.mark.parametrize('quarter,back,name',[(0,False,'RENAMED_NATIVE_SUPPORT'),
    (1,True,'DIFFERENT_COMPONENT')])
def test_automatic_source_derived_constructor_and_saved_receiver_close_fixture(tmp_path,quarter,back,name):
    source,_,name=fixture(tmp_path,quarter,back,name)
    # This operator places a barrel aperture on the moved land. Its fixture
    # must explicitly select the approved POFV process, not silently waive
    # via-in-pad rules on the default, unqualified process.
    b=pcbnew.LoadBoard(str(source));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal'
    b.SetProperties(props);field._save_field_snapshot(b,source)
    saved=source.read_bytes()
    result=access.run(source,tmp_path/'automatic',board_hint='synthetic',
        source_sha256=force._hash(source),max_trials=2,timeout_s=5.)
    assert result['ok'] and result['source_and_code_unchanged'],[
        r['result'].get('reason') for r in result['trials']]
    assert result['opens']<result['source_opens']
    assert source.read_bytes()==saved
    assert result['trials'][-1]['result']['independent_pivot_receiving']['ok']
    assert not result['routing_admitted'] and not result['power_authority']


@pytest.mark.parametrize('kwargs',[dict(max_trials=0),dict(max_trials=9),
    dict(timeout_s=10.001),dict(timeout_s=True),dict(radius_mm=6.001),
    dict(radius_mm=0),dict(radius_mm=float('nan'))])
def test_automatic_search_budget_and_motion_are_finite(kwargs,tmp_path):
    with pytest.raises(ValueError,match='bounded_orphan_access_work_required'):
        access.run('missing',tmp_path/'not-created',board_hint='synthetic',
            source_sha256='missing',**kwargs)
    assert not (tmp_path/'not-created').exists()


@pytest.mark.parametrize('angle,back',[(0,False),(90,False),(180,True),(270,True)])
def test_attached_supply_land_is_source_fixed_not_new_motion_authority(tmp_path,angle,back):
    from test_support_pivot_receiving import fixture as anchored_fixture
    source,_,name=anchored_fixture(tmp_path,name='R52')
    board=pcbnew.LoadBoard(str(source));fp=board.FindFootprintByReference(name)
    board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    peer=board.FindFootprintByReference('X2');peer.SetPosition(pcbnew.VECTOR2I_MM(7,10))
    next(iter(board.GetTracks())).SetEnd(pcbnew.VECTOR2I_MM(7,10))
    # The stationary supply land is connected positively in the source.
    layer=fp.GetLayer();at=fp.FindPadByNumber('1').GetPosition()
    edge=pcbnew.PCB_TRACK(board);edge.SetNet(board.FindNet('+3V3'));edge.SetLayer(layer)
    edge.SetStart(at);edge.SetEnd(at+pcbnew.VECTOR2I_MM(0,2))
    edge.SetWidth(200000);board.Add(edge)
    if back:
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if angle:
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    field._save_field_snapshot(board,source)
    assert access.targets(board,source,board_hint='synthetic')==[]
    rows=access.targets(board,source,board_hint='synthetic',include_anchored_pivots=True)
    assert len(rows)==1 and rows[0]['ref']==name and rows[0]['target_net']=='/CONTROL'
    assert not rows[0]['fully_isolated_reseat'] and rows[0]['fixed_pad_uuid']==force._uid(fp.FindPadByNumber('1'))
    before=[tuple(p.GetPosition()) for fp in board.GetFootprints() for p in fp.Pads()]
    proposals=access.anchored_proposals(board,rows[0],source=source)
    assert proposals and all(p['rotation_delta_deg']==180 for p in proposals)
    assert before==[tuple(p.GetPosition()) for fp in board.GetFootprints() for p in fp.Pads()]
    for candidate in proposals:
        # Independently replay the candidate, checking exact native land
        # geometry instead of assuming that an unchanged centre is enough.
        identity=receiver._fixed_land(fp.FindPadByNumber('1'))
        origin=pcbnew.VECTOR2I(fp.GetPosition());orientation=fp.GetOrientationDegrees()
        fp.SetOrientationDegrees(orientation+candidate['rotation_delta_deg'])
        fp.SetPosition(origin+pcbnew.VECTOR2I_MM(candidate['dx_mm'],candidate['dy_mm']))
        assert receiver._fixed_land(fp.FindPadByNumber('1'))==identity
        fp.SetPosition(origin);fp.SetOrientationDegrees(orientation)
    saved=source.read_bytes()
    result=access.run(source,tmp_path/'automatic-attached',board_hint='synthetic',
        source_sha256=force._hash(source),include_anchored_pivots=True,max_trials=2,timeout_s=5.)
    assert result['ok'] and result['opens']==0,result
    assert source.read_bytes()==saved and not result['power_authority']


@pytest.mark.parametrize('mode',[0,1,None,'true'])
def test_new_anchored_mode_must_be_explicit_not_truthy(tmp_path,mode):
    with pytest.raises(ValueError):
        access.run('missing',tmp_path/'out',board_hint='synthetic',source_sha256='unknown',
            include_anchored_pivots=mode)
    assert not (tmp_path/'out').exists()

"""Source-typed supply lookahead grants neither a rail derating nor a cut waiver."""
import pcbnew
import pytest

import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
import cec_future_pose_clearance as future
import cec_rated_link_preclear as link
from test_field_proposals import track
from test_lastmile import _board
from test_rated_supply_detour import authority


def fixture(tmp_path, *, angle=0, locked=False, blocking_net='/CONTROL', width=.2):
    board=_board([(5,10,blocking_net),(15,10,blocking_net)],edge=(0,0,30,30))
    board.SetCopperLayerCount(6)
    rail=pcbnew.NETINFO_ITEM(board,'+3V3');board.Add(rail)
    roots=[]
    for ref,at in [('RENAME_A',(8,8)),('OTHER_OWNER',(12,12))]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue('INA181A2IDBVR')
        fp.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-6'))
        fp.SetPosition(pcbnew.VECTOR2I_MM(*at));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('6');pad.SetNet(rail)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetPosition(fp.GetPosition())
        pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad);roots.append(force._uid(pad))
    blocker=track(board,blocking_net,(5,10),(15,10),width=width);blocker.SetLocked(locked)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(board,source)
    return pcbnew.LoadBoard(str(source)),source,roots,force._uid(blocker)


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_full_load_link_is_native_source_bound_with_no_refdes_or_coordinate_case(tmp_path,angle):
    board,source,roots,uid=fixture(tmp_path,angle=angle)
    saved=source.read_bytes();binding=row._source_binding(board)
    with authority('+3V3'):
        proposal=link.plan(board,*roots,source=source,board_hint='synthetic')
    assert proposal['ok'] and proposal['retired_track_uuids']==[uid]
    path=proposal['links'][0]
    assert path['width_nm']==200000
    assert path['unchanged_full_rail_contract']['current_authority']['amps']==.2
    assert not path['unchanged_full_rail_contract']['branch_sharing_assumed']
    assert all(p['kind']=='manufacturer_supply' for p in path['terminal_types'])
    assert proposal['source_sha256']==force._hash(source)
    assert proposal['link_not_constructed'] and not proposal['current_authority']
    assert row._source_binding(board)==binding and source.read_bytes()==saved


@pytest.mark.parametrize('fault',['unknown_part','measurement_pin','back','tht',
    'wrong_net','already_joined','no_load','force_domain','too_wide','too_far'])
def test_untyped_or_nonfull_load_source_lands_refuse_without_mutation(tmp_path,fault):
    board,source,roots,_=fixture(tmp_path)
    fp=board.FindFootprintByReference('RENAME_A');pad=list(fp.Pads())[0]
    if fault=='unknown_part':fp.SetValue('UNKNOWN')
    if fault=='measurement_pin':pad.SetNumber('3')
    if fault=='back':fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if fault=='tht':pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    if fault=='wrong_net':pad.SetNet(board.FindNet('/CONTROL'))
    if fault=='already_joined':track(board,'+3V3',(8,8),(12,12))
    if fault=='too_far':fp.Move(pcbnew.VECTOR2I_MM(20,0))
    binding=row._source_binding(board);saved=source.read_bytes()
    with authority('/absent' if fault=='no_load' else '+3V3',
            amps=10 if fault=='too_wide' else .2,
            domains={'+3V3':dict(complete=False)} if fault=='force_domain' else None),pytest.raises(ValueError):
        link.plan(board,*roots,source=source,board_hint='synthetic')
    assert row._source_binding(board)==binding and source.read_bytes()==saved


@pytest.mark.parametrize('fault',['locked','group','power','wide','via'])
def test_lookahead_ablation_never_grants_protected_copper_retirement(tmp_path,fault):
    board,source,roots,uid=fixture(tmp_path,locked=fault=='locked',
        blocking_net='+OTHER_SUPPLY' if fault=='power' else '/CONTROL',
        width=.5 if fault=='wide' else .2)
    item=next(t for t in board.GetTracks() if force._uid(t)==uid)
    if fault=='group':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(item)
    if fault=='via':
        via=pcbnew.PCB_VIA(board);via.SetNet(item.GetNet());via.SetPosition(pcbnew.VECTOR2I_MM(10,10))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    before=row._source_binding(board)
    with authority('+3V3'):
        proposal=link.plan(board,*roots,source=source,board_hint='synthetic')
    assert row._source_binding(board)==before
    # The protected geometry can cause a legal detour, but is never retired.
    if fault=='via':
        assert force._uid(via) not in proposal['retired_track_uuids']
        assert any(force._uid(t)==force._uid(via) for t in board.GetTracks())
    else:
        assert uid not in proposal['retired_track_uuids'] or fault=='locked' and not proposal['ok']
    assert all(r['ordinary_retirement_allowed'] is False for r in proposal['blockers']
        if r['uuid']==uid and fault in ('locked','group','power','wide'))


def test_known_locked_obstruction_needs_exact_permission_and_plan_is_rederived(tmp_path):
    board,source,roots,uid=fixture(tmp_path,locked=True)
    with authority('+3V3'):
        proposal=link.plan(board,*roots,source=source,board_hint='synthetic',allow_locked_track_uuids=[uid])
        assert proposal['ok'] and proposal['allow_locked_track_uuids']==[uid]
        with pytest.raises(ValueError,match='rated_link_cut_or_locked_permission_scope_bound'):
            link.plan(board,*roots,source=source,board_hint='synthetic',allow_locked_track_uuids=['not-a-source-blocker'])
        # Rehashing a forged corridor cannot evade actual source planning.
        proposal['links'][0]['points_nm'][1][0]+=10000
        content=dict(proposal);content.pop('plan_sha256')
        proposal['plan_sha256']=future.contour._digest(content)
        before=row._source_binding(board)
        with pytest.raises(ValueError,match='future_pose_source_or_permission_changed'):
            future.construct(board,proposal,source=source)
        assert row._source_binding(board)==before

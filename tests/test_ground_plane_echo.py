"""Native double-plane coverage, saved cut receiving and refusal boundaries."""
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_ground_plane_echo as echo
import cec_source_cut_chain as chain
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,rotation=0):
    board=_board([(10,10,'GND'),(10,15,'GND'),(20,20,'TEST_SIGNAL'),(22,20,'TEST_SIGNAL')],edge=(0,0,30,30))
    board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    first=track(board,'GND',(10,10),(10,14.5),layer=pcbnew.In2_Cu)
    track(board,'GND',(10,14.5),(10,15),layer=pcbnew.In2_Cu)
    net=board.GetNetsByName()['GND']
    for at in ((10,10),(10,15)):
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(*at));via.SetNet(net)
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(board);zone.SetLayer(layer);zone.SetNet(net);zone.Outline().NewOutline()
        for at in ((1,1),(29,1),(29,29),(1,29)):zone.Outline().Append(pcbnew.VECTOR2I_MM(*at))
        board.Add(zone)
    if rotation:
        at=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(at,angle)
    additive._ground_refill(board)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    return source,force._uid(first)


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_rotated_native_double_plane_echo_is_independently_received(tmp_path,rotation):
    source,uid=fixture(tmp_path,rotation);original=source.read_bytes()
    b=pcbnew.LoadBoard(str(source));proposal=echo.plan(b,uid)
    assert len(proposal['retired_track_uuids'])==2
    assert len({q['layer'] for q in proposal['saved_plane_witnesses']})==2
    child=force._copy_family(source,tmp_path/'cut');echo.subtract(b,proposal)
    field._save_field_snapshot(b,child)
    r=echo.receive(source,child,track_uuid=uid,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['all_surviving_native_partitions_and_short_returns_preserved']
    assert r['all_native_barrels_and_plane_copper_exact']
    assert not r['retired_via_uuids'] and not r['added_native_uuids']
    assert not r['current_authority'] and not r['inductive_return_qualified'] and not r['release_authority']
    assert source.read_bytes()==original
    assert not additive.receive(source,child)['ok']


@pytest.mark.parametrize('fault',['one_plane','unfilled','hole','width','locked','group','surface','fork','pad'])
def test_topological_connectivity_never_waives_missing_coverage_or_unowned_contacts(tmp_path,fault):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    edge=next(t for t in b.GetTracks() if force._uid(t)==uid)
    if fault=='one_plane':b.Remove(next(iter(b.Zones())))
    elif fault=='unfilled':
        for zone in b.Zones():zone.UnFill()
    elif fault=='hole':
        zone=next(iter(b.Zones()));gap=pcbnew.SHAPE_POLY_SET();gap.NewOutline()
        for at in ((9.5,11),(10.5,11),(10.5,12),(9.5,12)):gap.Append(pcbnew.VECTOR2I_MM(*at))
        fill=pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(zone.GetLayer()));fill.BooleanSubtract(gap)
        zone.SetFilledPolysList(zone.GetLayer(),fill);zone.SetIsFilled(True)
    elif fault=='width':edge.SetWidth(400000)
    elif fault=='locked':edge.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('protected');b.Add(group);group.AddItem(edge)
    elif fault=='surface':edge.SetLayer(pcbnew.F_Cu)
    elif fault=='fork':track(b,'GND',(10,12),(13,12),layer=pcbnew.In2_Cu)
    elif fault=='pad':
        owner=pcbnew.FOOTPRINT(b);owner.SetReference('retained_THT');pad=pcbnew.PAD(owner)
        pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetNet(b.GetNetsByName()['GND'])
        pad.SetPosition(pcbnew.VECTOR2I_MM(10,12));pad.SetSize(pcbnew.VECTOR2I_MM(1.2,1.2))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetLayerSet(pcbnew.LSET.AllCuMask());owner.Add(pad);b.Add(owner)
    with pytest.raises(ValueError):echo.plan(b,uid)


def test_a_proposal_cannot_retire_a_changed_plane_or_add_copper(tmp_path):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));p=echo.plan(b,uid)
    next(iter(b.Zones())).SetAssignedPriority(8)
    with pytest.raises(ValueError,match='binding_changed'):echo.subtract(b,p)
    child=force._copy_family(source,tmp_path/'changed');b=pcbnew.LoadBoard(str(source));echo.subtract(b,p)
    next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA').SetWidth(700000)
    field._save_field_snapshot(b,child)
    r=echo.receive(source,child,track_uuid=uid,board_hint='synthetic')
    assert not r['ok'] and 'may_only_subtract' in r['errors'][0],r


def test_cut_chain_retypes_the_saved_ground_echo_not_a_worker_pass(tmp_path):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source));p=echo.plan(b,uid)
    child=force._copy_family(source,tmp_path/'cut');echo.subtract(b,p);field._save_field_snapshot(b,child)
    final=force._copy_family(child,tmp_path/'new-connection');track(b,'TEST_SIGNAL',(20,20),(22,20))
    field._save_field_snapshot(b,final)
    r=chain.receive(source,final,board_hint='synthetic',
        phases=[dict(kind='ground_plane_echo',candidate=str(child),track_uuid=uid),
            dict(kind='additive',candidate=str(final))])
    assert r['ok'] and r['complete'],r
    assert r['retired_track_uuids']==p['retired_track_uuids']
    assert not r['retired_via_uuids'] and not r['current_authority'] and not r['release_authority']


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_subtraction_only_chain_needs_no_token_new_copper(tmp_path,rotation):
    source,uid=fixture(tmp_path,rotation);original=source.read_bytes()
    b=pcbnew.LoadBoard(str(source));p=echo.plan(b,uid)
    child=force._copy_family(source,tmp_path/'pure-cut');echo.subtract(b,p)
    field._save_field_snapshot(b,child)
    phases=[dict(kind='ground_plane_echo',candidate=str(child),track_uuid=uid)]
    r=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert r['ok'] and r['complete'],r
    assert r['independently_received_subtraction_only_ground_echo']
    assert r['retired_track_uuids']==p['retired_track_uuids']
    assert not r['added_native_uuids'] and not r['retired_via_uuids']
    assert r['whole_original_cut_additions_ground_and_rule_replay']['ok']
    assert not r['current_authority'] and not r['release_authority']
    assert source.read_bytes()==original
    cached=chain.receive(source,child,board_hint='synthetic',phases=phases)
    assert cached['ok'] and cached['complete']
    assert cached['independently_received_subtraction_only_ground_echo']


@pytest.mark.parametrize('fault',['no_op','unowned_other_net_cut','barrel_cut','plane_priority'])
def test_subtraction_only_echo_chain_never_authorizes_other_deletions(tmp_path,fault):
    source,uid=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    if fault=='unowned_other_net_cut':
        track(b,'TEST_SIGNAL',(20,20),(22,20))
        field._save_field_snapshot(b,source)
    p=echo.plan(b,uid)
    child=force._copy_family(source,tmp_path/'bad-cut')
    if fault!='no_op':echo.subtract(b,p)
    if fault=='unowned_other_net_cut':
        original=next(t for t in b.GetTracks() if t.GetNetname()=='TEST_SIGNAL')
        b.Remove(original)
    elif fault=='barrel_cut':b.Remove(next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA'))
    elif fault=='plane_priority':next(iter(b.Zones())).SetAssignedPriority(8)
    field._save_field_snapshot(b,child)
    r=chain.receive(source,child,board_hint='synthetic',
        phases=[dict(kind='ground_plane_echo',candidate=str(child),track_uuid=uid)])
    assert not r['ok'] and not r['complete'],r

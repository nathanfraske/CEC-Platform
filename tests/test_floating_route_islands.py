"""Complete source island removal cannot peel a legitimate terminal branch."""
import pcbnew
import pytest
import cec_floating_route_islands as islands
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track, add_net


def fixture(tmp_path):
    source, board = ground_fixture(tmp_path)
    orphan=track(board,'GND',(5,14),(7,14))
    tail=track(board,'GND',(7,14),(9,14))
    field._save_field_snapshot(board,source)
    return source, board, {force._uid(orphan),force._uid(tail)}


def plan(source, board, **kwargs):
    return islands.plan(board,source_path=source,board_hint='unclassified-test',
        include_nets=['GND'],**kwargs)


def test_complete_floating_chain_is_received_without_terminal_or_rule_edits(tmp_path):
    source, board, scope = fixture(tmp_path)
    packet=plan(source,board)
    assert scope<=set(packet['retired_uuids']), packet
    before=source.read_bytes()
    islands.apply(board,packet,source_path=source,board_hint='unclassified-test')
    child=force._copy_family(source,tmp_path/'trial')
    additive._ground_refill(board);field._save_field_snapshot(board,child)
    result=islands.receive(source,child,packet,board_hint='unclassified-test')
    assert result['ok'] and result['complete'], result
    assert source.read_bytes()==before and not result['release_authority']


@pytest.mark.parametrize('pth,layer',[(False,pcbnew.F_Cu),(True,pcbnew.B_Cu)])
def test_any_real_pad_contact_protects_whole_island(tmp_path,pth,layer):
    source, board, scope = fixture(tmp_path)
    if layer!=pcbnew.F_Cu:
        for t in board.GetTracks():
            if force._uid(t) in scope:t.SetLayer(layer)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('OWNER');board.Add(fp)
    p=pcbnew.PAD(fp);fp.Add(p);p.SetNumber('1');p.SetNetCode(board.GetNetcodeFromNetname('GND'))
    p.SetPosition(pcbnew.VECTOR2I_MM(5,14));p.SetSize(pcbnew.VECTOR2I_MM(1,1))
    p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if pth else pcbnew.PAD_ATTRIB_SMD)
    layers=pcbnew.LSET();layers.AddLayer(layer)
    p.SetLayerSet(pcbnew.LSET.AllCuMask() if pth else layers)
    if pth:p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    assert not scope & set(plan(source,board)['retired_uuids'])


def test_group_and_explicit_source_lock_ownership_fail_closed(tmp_path):
    source, board, scope = fixture(tmp_path)
    item=next(t for t in board.GetTracks() if force._uid(t) in scope)
    item.SetLocked(True)
    assert not scope & set(plan(source,board)['retired_uuids'])
    assert scope<=set(plan(source,board,authorize_source_locked=True)['retired_uuids'])
    group=pcbnew.PCB_GROUP(board);group.SetName('owner');board.Add(group);group.AddItem(item)
    assert not scope & set(plan(source,board,authorize_source_locked=True)['retired_uuids'])


def test_retirement_receiver_rejects_unrelated_track_edit(tmp_path):
    source, board, scope = fixture(tmp_path)
    packet=plan(source,board)
    islands.apply(board,packet,source_path=source,board_hint='unclassified-test')
    next(iter(board.GetTracks())).SetLocked(True)
    child=force._copy_family(source,tmp_path/'trial')
    additive._ground_refill(board);field._save_field_snapshot(board,child)
    assert not islands.receive(source,child,packet,board_hint='unclassified-test')['ok']


def test_stale_plan_is_refused_before_deleting(tmp_path):
    source, board, scope = fixture(tmp_path)
    packet=plan(source,board)
    track(board,'/CONTROL',(10,20),(11,20))
    before={force._uid(t) for t in board.GetTracks()}
    with pytest.raises(ValueError,match='stale'):
        islands.apply(board,packet,source_path=source,board_hint='unclassified-test')
    assert before=={force._uid(t) for t in board.GetTracks()}


def test_specialized_supply_cannot_be_reclassified_as_orphan_ordinary(tmp_path):
    source, board, scope = fixture(tmp_path)
    track(board,'+5V_MAIN',(10,20),(11,20))
    # A deliberately incomplete rated-board fixture may fail even earlier
    # while binding its declared endpoints. Unknown is also fail-closed.
    before={force._uid(t) for t in board.GetTracks()}
    with pytest.raises(ValueError):
        islands.plan(board,source_path=source,board_hint='atx-24pin-rev3',include_nets=['+5V_MAIN'])
    assert before=={force._uid(t) for t in board.GetTracks()}

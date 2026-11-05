"""A connected move is atomic; no disconnected prefix or unrelated edit passes."""
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pose_additive_reconstruction as receiving
from test_additive_route_receiving import terminal
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path, *, bridge=True, mutation=None, tht=False):
    source, board = ground_fixture(tmp_path)
    terminal(board, 'X1', (10, 14))
    terminal(board, 'X2', (16, 14))
    fp = board.FindFootprintByReference('X1')
    if tht:
        pad = next(iter(fp.Pads()))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6, .6))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    link = track(board, '/CONTROL', (10, 14), (16, 14))
    field._save_field_snapshot(board, source)
    uid, link_uid = force._uid(fp), force._uid(link)
    target = force._copy_family(source, tmp_path / 'trial')
    board = pcbnew.LoadBoard(str(target)); fp = board.FindFootprintByReference('X1')
    fp.SetPosition(pcbnew.VECTOR2I_MM(10, 16))
    if bridge:
        track(board, '/CONTROL', (10, 16), (10, 14))
    if mutation == 'cut':
        old = next(t for t in board.GetTracks() if force._uid(t) == link_uid)
        board.Remove(old)
    elif mutation == 'pad':
        next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(2, 2))
    elif mutation == 'hidden':
        fp.Reference().SetVisible(not fp.Reference().IsVisible())
    elif mutation == 'peer':
        board.FindFootprintByReference('X2').Move(pcbnew.VECTOR2I_MM(0, 1))
    elif mutation == 'outline':
        next(iter(board.GetDrawings())).Move(pcbnew.VECTOR2I_MM(1, 0))
    additive._ground_refill(board); field._save_field_snapshot(board, target)
    return source, target, uid


@pytest.mark.parametrize('tht', [False, True])
def test_source_connected_pose_requires_real_restoration(tmp_path, tht):
    source, target, uid = fixture(tmp_path, tht=tht)
    original = source.read_bytes()
    result = receiving.receive(source, target, selected_footprint_uuids=[uid], board_hint='arbitrary')
    assert result['ok'] and result['complete'], result
    assert result['all_original_terminal_and_copper_partitions_preserved']
    assert result['paired_native_partition_preservation']['exact_positive_native_island_overlap']
    assert not result['paired_native_partition_preservation']['whole_zone_uuid_connectivity_credit']
    assert source.read_bytes() == original and not result['release_authority']


@pytest.mark.parametrize('tht',[False,True])
def test_paired_source_is_not_the_already_transformed_projection(tmp_path,monkeypatch,tht):
    import cec_native_partition_pair as partitions
    source,target,uid=fixture(tmp_path,tht=tht);before=[p.read_bytes()for p in(source,target)]
    actual=partitions.compare;observations=[]
    def inspect_source(parent,child,**kwargs):
        old=parent.FindFootprintByReference('X1');new=child.FindFootprintByReference('X1')
        assert tuple(old.GetPosition())==(10000000,14000000)
        assert tuple(new.GetPosition())==(10000000,16000000)
        a=next(iter(old.Pads()));b=next(iter(new.Pads()))
        assert kwargs['identity_rebindings'][force._item_key(b)]==force._item_key(a)
        observations.append(True)
        return actual(parent,child,**kwargs)
    monkeypatch.setattr(partitions,'compare',inspect_source)
    r=receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='arbitrary')
    assert r['ok'] and observations==[True],r
    assert before==[p.read_bytes()for p in(source,target)]


def test_pairing_never_waives_existing_source_pose_bound(tmp_path):
    source,target,uid=fixture(tmp_path)
    r=receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='arbitrary',max_shift_mm=1.)
    assert not r['ok'] and any('shift_bound'in e for e in r['errors']),r
    assert 'paired_native_partition_preservation'not in r


def test_disconnected_move_cannot_be_received(tmp_path):
    source, target, uid = fixture(tmp_path, bridge=False)
    result = receiving.receive(source, target, selected_footprint_uuids=[uid], board_hint='arbitrary')
    assert not result['ok'] and 'partition_lost' in result['errors'][0], result


@pytest.mark.parametrize('mutation', ['cut', 'pad', 'hidden', 'peer', 'outline'])
def test_pose_transaction_cannot_smuggle_unrelated_mutations(tmp_path, mutation):
    source, target, uid = fixture(tmp_path, mutation=mutation)
    result = receiving.receive(source, target, selected_footprint_uuids=[uid],
        board_hint='arbitrary', allow_field_reflow=True)
    assert not result['ok'] and result['errors'], result


def test_atomic_pose_composes_only_explicit_independently_qualified_endpoints(tmp_path):
    from test_additive_endpoint_receiving import fixture as endpoint_fixture
    source,target,_,_=endpoint_fixture(tmp_path)
    board=pcbnew.LoadBoard(str(target))
    fp=board.FindFootprintByReference('OTHER_DEVICE_91')
    # The retained source contact stays inside its actual moving SMD land.
    # Other incoming tapers still need independent complete-cell geometry.
    uid=force._uid(fp);fp.Move(pcbnew.VECTOR2I_MM(0,-.2))
    additive._ground_refill(board);field._save_field_snapshot(board,target)
    assert not receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='arbitrary')['ok']
    proof=receiving.receive(source,target,selected_footprint_uuids=[uid],board_hint='arbitrary',
        allow_endpoint_neckdown_additions=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['all_original_terminal_and_copper_partitions_preserved']

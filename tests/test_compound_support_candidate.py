"""Independent two-cell proposals keep one unchanged parent and shared bounds."""
import copy
import hashlib
import pytest
import pcbnew
import cec_compound_support_candidate as compound
import cec_certificate_repair as repair
import cec_support_motion as motion
from test_support_motion import fixture


def cells():
    return [dict(target=repair.asdict(repair.FootprintRepairTarget(
        ref=ref, target_net='/RENAMED', endpoint_ref='FIXED', endpoint_pad='1',
        endpoint_x_mm=30, endpoint_y_mm=20, hit_count=1, distance_mm=2,
        priority=(0,))), candidate=dict(dx_mm=delta, dy_mm=0, rotation_delta_deg=0))
        for ref, delta in [('SUPPORT', -.5), ('PEER', .5)]]


@pytest.mark.parametrize('back,offset', [(False, (0, 0)), (True, (17, -8))])
def test_two_native_cells_move_independently_without_changing_source(tmp_path, back, offset):
    board = fixture(back=back, offset=offset)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    original = source.read_bytes()
    initial = {fp.GetReference(): tuple(fp.GetPosition()) for fp in board.GetFootprints()}
    destination = tmp_path/'private/board.kicad_pcb'
    result = compound.construct(source, destination, cells(), motion.limits())
    assert result['constructed'] and not result['release_authority']
    assert result['input_families_unchanged'] and source.read_bytes() == original
    assert result['source_sha256'] == hashlib.sha256(original).hexdigest()
    staged = pcbnew.LoadBoard(str(destination))
    for ref, dx in [('SUPPORT', -500000), ('PEER', 500000)]:
        at = tuple(staged.FindFootprintByReference(ref).GetPosition())
        assert at == (initial[ref][0]+dx, initial[ref][1])
    assert result['restoration']['affected_nets'] == ['/RENAMED']


@pytest.mark.parametrize('fault', ['overlap', 'count', 'other_net', 'immovable', 'shift'])
def test_whole_compound_domain_refuses_before_native_motion(tmp_path, fault):
    board = fixture(); rows = cells(); policy = motion.limits()
    if fault == 'overlap': rows[1]['target']['ref'] = rows[0]['target']['ref']
    if fault == 'count': policy = motion.limits(max_refs=1)
    if fault == 'other_net': rows[1]['target']['target_net'] = '/OTHER'
    if fault == 'immovable': policy = motion.limits(immutable_refs=['PEER'])
    if fault == 'shift': rows[1]['candidate']['dx_mm'] = 6.01
    original = copy.deepcopy(rows)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    destination = tmp_path/'private/board.kicad_pcb'
    result = compound.construct(source, destination, rows, policy)
    assert not result['constructed'] and not destination.exists()
    assert not result['release_authority'] and result['input_families_unchanged']
    assert rows == original


@pytest.mark.parametrize('failure', ['second_step', 'combined_branch_budget'])
def test_refused_second_step_cannot_publish_partial_compound(tmp_path, monkeypatch, failure):
    board = fixture(); source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    original = source.read_bytes(); count = 0
    def worker(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2 and failure == 'second_step':
            return False, dict(refusal='native_proof_refused')
        return True, dict(removed_track_uuids=[f'{count}-{i}' for i in range(5)])
    monkeypatch.setattr(repair, '_relocate_footprint_worker', worker)
    result = compound.construct(source, tmp_path/'private/board.kicad_pcb', cells(), motion.limits())
    assert count == 2 and not result['constructed'] and 'board' not in result
    assert result['input_families_unchanged'] and source.read_bytes() == original


def test_no_inplace_or_existing_destination(tmp_path):
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), fixture())
    with pytest.raises(ValueError):
        compound.construct(source, source, cells(), motion.limits())
    with pytest.raises(ValueError):
        compound.construct(source, tmp_path/'private/board.kicad_pcb', cells(), motion.limits(), max_branch_tracks=9)


@pytest.mark.parametrize('back,offset',[(False,(0,0)),(True,(17,-8))])
def test_explicit_small_owner_scope_reaches_constructor_unchanged(tmp_path,back,offset):
    board=fixture(back=back,offset=offset)
    fp=board.FindFootprintByReference('SUPPORT')
    original_pad=next(iter(fp.Pads()))
    for number in range(3,13):
        p=pcbnew.PAD(fp);p.SetNumber(str(number));p.SetNet(original_pad.GetNet())
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetLayerSet(original_pad.GetLayerSet());p.SetSize(pcbnew.VECTOR2I_MM(.2,.4))
        p.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM((number-7)*.5,1));fp.Add(p)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    original=source.read_bytes()
    refused=compound.construct(source,tmp_path/'default/board.kicad_pcb',cells(),motion.limits())
    assert not refused['constructed']
    result=compound.construct(source,tmp_path/'explicit/board.kicad_pcb',cells(),
        motion.limits(max_owner_copper_pads=16))
    assert result['constructed'] and not result['release_authority']
    assert source.read_bytes()==original and result['input_families_unchanged']


def test_compound_cannot_expand_to_two_small_ics():
    board=fixture()
    for fp in board.GetFootprints():
        pad=pcbnew.PAD(fp);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2));fp.Add(pad)
    result=compound.validate(board,cells(),motion.limits(max_owner_copper_pads=16))
    assert not result['ok'] and result['reason']=='multiple_endpoint_owners_outside_scope'


def private_partition_fixture(back=False):
    from test_support_cell_topology import fixture as private_fixture
    board, net, endpoint, peer, refs = private_fixture(back=back, prefix='NATIVE_')
    aux = pcbnew.FOOTPRINT(board); aux.SetReference('OBSTACLE_X')
    aux.SetPosition(pcbnew.VECTOR2I_MM(30, 25)); board.Add(aux)
    for number, delta in (('1', -.5), ('2', .5)):
        pad = pcbnew.PAD(aux); pad.SetNumber(number); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetNet(board.FindNet('/ARBITRARY_RAIL')); pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.5,.3))
        pad.SetPosition(aux.GetPosition()+pcbnew.VECTOR2I_MM(delta,0)); aux.Add(pad)
    def target(ref, companions, mode):
        return repair.asdict(repair.FootprintRepairTarget(ref=ref, target_net=net,
            endpoint_ref=peer[0], endpoint_pad=peer[1], endpoint_x_mm=20, endpoint_y_mm=20,
            hit_count=1, distance_mm=4, priority=(), motion=mode, companion_refs=companions))
    rows = [dict(target=target(endpoint[0], refs[2:], 'toward_endpoint'),
                 candidate=dict(dx_mm=.5, dy_mm=0, rotation_delta_deg=0,
                                mobility_companion_refs=[], stationary_companion_refs=refs[2:])),
            dict(target=target('OBSTACLE_X', [], 'away_from_endpoint'),
                 candidate=dict(dx_mm=0, dy_mm=.5, rotation_delta_deg=0))]
    return board, rows, refs[2]


@pytest.mark.parametrize('back', [False, True])
def test_native_private_stationary_partition_constructs_without_moving_companion(tmp_path, back):
    board, rows, stationary = private_partition_fixture(back)
    source = tmp_path/'source.kicad_pcb'; pcbnew.SaveBoard(str(source), board)
    original = source.read_bytes()
    pose = tuple(board.FindFootprintByReference(stationary).GetPosition())
    destination = tmp_path/'private/board.kicad_pcb'
    result = compound.construct(source, destination, rows, motion.limits())
    assert result['constructed'] and result['stationary_companions_unchanged']
    final = pcbnew.LoadBoard(str(destination))
    assert tuple(final.FindFootprintByReference(stationary).GetPosition()) == pose
    assert stationary not in result['moved_refs'] and source.read_bytes() == original


@pytest.mark.parametrize('fault', ['no_receipt', 'wrong_receipt', 'string_receipt',
                                   'mechanical_group', 'moved_elsewhere'])
def test_compound_cannot_silently_drop_a_companion(fault):
    board, rows, stationary = private_partition_fixture()
    if fault == 'no_receipt': rows[0]['candidate'].pop('stationary_companion_refs')
    if fault == 'wrong_receipt': rows[0]['candidate']['stationary_companion_refs'] = ['OTHER']
    if fault == 'string_receipt': rows[0]['candidate']['stationary_companion_refs'] = stationary
    if fault == 'mechanical_group':
        group = pcbnew.PCB_GROUP(board); board.Add(group)
        group.AddItem(board.FindFootprintByReference(stationary))
    if fault == 'moved_elsewhere': rows[1]['target']['ref'] = stationary
    assert not compound.validate(board, rows, motion.limits())['ok']


def articulated_rows(back=False):
    board, rows, companion=private_partition_fixture(back)
    primary=rows[0]['target']['ref']
    first=rows[0]['candidate']
    first.update(stationary_companion_refs=[],independent_companion_refs=[companion])
    third=copy.deepcopy(rows[0])
    third['target'].update(ref=companion,companion_refs=[primary])
    third['candidate'].update(dx_mm=0,dy_mm=.5,independent_companion_refs=[primary])
    rows.append(third)
    return board,rows


@pytest.mark.parametrize('back',[False,True])
def test_independently_moved_companions_have_reciprocal_source_proof(tmp_path,back):
    board,rows=articulated_rows(back)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    before=source.read_bytes()
    result=compound.construct(source,tmp_path/'private/board.kicad_pcb',rows,motion.limits())
    assert result['constructed'] and len(result['moved_refs'])==3
    assert result['domain']['stationary_refs']==[]
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['missing_peer','nonreciprocal','different_owner','wrong_net','stationary_overlap'])
def test_independent_peer_cannot_be_invented_or_silently_frozen(fault):
    board,rows=articulated_rows()
    if fault=='missing_peer':rows.pop()
    if fault=='nonreciprocal':rows[2]['candidate']['independent_companion_refs']=[]
    if fault=='different_owner':rows[2]['target']['endpoint_ref']='OTHER'
    if fault=='wrong_net':rows[2]['target']['target_net']='/OTHER'
    if fault=='stationary_overlap':rows[0]['candidate']['stationary_companion_refs']=rows[0]['target']['companion_refs']
    assert not compound.validate(board,rows,motion.limits())['ok']

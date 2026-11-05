"""Private divider/filter topology is distinct from a shared multi-drop net."""
import hashlib
import pcbnew
import pytest
import cec_certificate_repair as repair
import cec_support_cell_topology as topology


def fixture(*, offset=(0,0), back=False, members=2, prefix=''):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    signal = pcbnew.NETINFO_ITEM(board, '/ARBITRARY_CONTROL'); board.Add(signal)
    other = pcbnew.NETINFO_ITEM(board, '/ARBITRARY_RAIL'); board.Add(other)
    refs = [prefix+'OWNER', *[prefix+'SUPPORT'+str(i) for i in range(members)]]
    for index, ref in enumerate(refs):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(20+(4 if index else 0),20+index*.7)+
                       pcbnew.VECTOR2I_MM(*offset))
        for number in range(1, 9 if index == 0 else 3):
            pad = pcbnew.PAD(fp); pad.SetNumber(str(number))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.5,.3)); pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(signal if number == 1 else other)
            pad.SetPosition(fp.GetPosition()+pcbnew.VECTOR2I_MM(0,.5*(number-1)))
            fp.Add(pad)
        board.Add(fp)
        if back: fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    endpoint, peer = (refs[1], '1'), (refs[0], '1')
    return board, signal.GetNetname(), endpoint, peer, refs


@pytest.mark.parametrize('members', [1,2,3])
@pytest.mark.parametrize('offset,back,prefix', [((0,0),False,''),((11,-7),True,'RENAMED_')])
def test_private_cell_accounts_for_all_native_terminals(members, offset, back, prefix):
    board, net, endpoint, peer, refs = fixture(members=members,offset=offset,back=back,prefix=prefix)
    result = topology.private_cell(board,net,endpoint,peer)
    assert result['ok'] and not result['release_authority']
    assert result['companions'] == refs[2:]
    assert len(result['terminals']) == members+1


@pytest.mark.parametrize('defect', ['remote','locked','grouped','tht','multilead',
    'connector','second_owner_pin','wrong_owner','wrong_support','missing_net','too_many'])
def test_shared_or_out_of_scope_cells_fail_closed(defect):
    board,net,endpoint,peer,refs=fixture(members=4 if defect=='too_many' else 2)
    second=board.FindFootprintByReference(refs[2])
    if defect=='remote': second.Move(pcbnew.VECTOR2I_MM(5,0))
    if defect=='locked': second.SetLocked(True)
    if defect=='grouped':
        group=pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(second)
    if defect=='tht': list(second.Pads())[1].SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    if defect=='multilead':
        pad=pcbnew.PAD(second);pad.SetNumber('3');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());second.Add(pad)
    if defect=='connector':second.SetReference('J_DECLARED_ANCHOR')
    if defect=='second_owner_pin':
        owner=board.FindFootprintByReference(peer[0]);list(owner.Pads())[1].SetNet(board.FindNet(net))
    if defect=='wrong_owner': peer=(peer[0],'2')
    if defect=='wrong_support': endpoint=(endpoint[0],'2')
    if defect=='missing_net':net='/ABSENT'
    result=topology.private_cell(board,net,endpoint,peer)
    assert not result['ok'] and not result['release_authority']


@pytest.mark.parametrize('kwargs',[dict(max_members=4),dict(max_members=True),
    dict(radius_mm=3.0001),dict(radius_mm=float('nan')),dict(radius_mm=True)])
def test_limits_cannot_expand_legacy_local_scope(kwargs):
    board,net,endpoint,peer,refs=fixture()
    with pytest.raises(ValueError):topology.private_cell(board,net,endpoint,peer,**kwargs)


def test_planner_emits_whole_cell_from_native_refusal_without_editing(tmp_path, monkeypatch):
    board,net,endpoint,peer,refs=fixture()
    source=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    ends=[]
    for label,(ref,number) in zip(('a','b'),(peer,endpoint)):
        fp=board.FindFootprintByReference(ref)
        pad=next(p for p in fp.Pads() if p.GetNumber()==number)
        pos=pad.GetPosition()
        ends.append(dict(endpoint=label,kind='pad',ref=ref,pad=number,
                         x_mm=pos.x/1e6,y_mm=pos.y/1e6))
    completion=dict(unconn_nets=[net],final_completion=dict(refused_details=[dict(
        net=net,distance_mm=4,certificate=dict(net=net,endpoints=ends,
            layers=[dict(layer='F.Cu',endpoint_escape=[
                dict(endpoint='a',clear_rays=[]),dict(endpoint='b',clear_rays=['E'])])]))]))
    with monkeypatch.context() as prior:
        prior.setattr(topology,'private_cell',lambda *a,**kw: dict(ok=False,reason='legacy_two_pad_only'))
        old=repair.plan_footprint_repairs(str(source),completion)
        assert not any(row['ref']==endpoint[0] for row in old['targets'])
    plan=repair.plan_footprint_repairs(str(source),completion)
    primary=next((row for row in plan['targets'] if row['ref']==endpoint[0]),None)
    assert primary is not None
    assert primary['motion']=='toward_endpoint' and tuple(primary['companion_refs'])==tuple(refs[2:])
    assert plan['support_cell_evidence'][0]['ok']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('back,prefix', [(False, ''), (True, 'ALTERNATE_')])
def test_private_electrical_companions_can_be_accounted_for_without_rigid_motion(back, prefix):
    board, net, endpoint, peer, refs = fixture(back=back, prefix=prefix)
    target = dict(ref=endpoint[0], target_net=net, endpoint_ref=peer[0], endpoint_pad=peer[1],
                  motion='toward_endpoint', companion_refs=refs[2:])
    original = {fp.GetReference(): tuple(fp.GetPosition()) for fp in board.GetFootprints()}
    proof = topology.stationary_partition(board, target)
    assert proof['ok'] and proof['moving_refs'] == [endpoint[0]]
    assert proof['stationary_refs'] == refs[2:]
    assert proof['restoration_and_pose_proof_required'] and not proof['release_authority']
    assert {fp.GetReference(): tuple(fp.GetPosition()) for fp in board.GetFootprints()} == original


@pytest.mark.parametrize('fault', ['mechanical_group', 'shared_owner', 'remote',
                                   'wrong_declared', 'unaccounted', 'not_endpoint'])
def test_stationary_partition_requires_fresh_complete_private_cell(fault):
    board, net, endpoint, peer, refs = fixture()
    target = dict(ref=endpoint[0], target_net=net, endpoint_ref=peer[0], endpoint_pad=peer[1],
                  motion='toward_endpoint', companion_refs=refs[2:])
    companion = board.FindFootprintByReference(refs[2])
    if fault == 'mechanical_group':
        group = pcbnew.PCB_GROUP(board); board.Add(group); group.AddItem(companion)
    if fault == 'shared_owner':
        list(board.FindFootprintByReference(peer[0]).Pads())[1].SetNet(board.FindNet(net))
    if fault == 'remote': companion.Move(pcbnew.VECTOR2I_MM(5,0))
    if fault == 'wrong_declared': target['companion_refs'] = ['UNRELATED']
    if fault == 'unaccounted': target['companion_refs'] = []
    if fault == 'not_endpoint': target['motion'] = 'away_from_endpoint'
    assert not topology.stationary_partition(board, target)['ok']


@pytest.mark.parametrize('back,prefix', [(False, ''), (True, 'RENAMED_')])
@pytest.mark.parametrize('members', [2, 3])
def test_mobile_primary_selection_keeps_whole_private_cell_authority(back, prefix, members):
    board, net, endpoint, peer, refs = fixture(back=back, prefix=prefix, members=members)
    target = dict(ref=endpoint[0], target_net=net, endpoint_ref=peer[0], endpoint_pad=peer[1],
                  motion='toward_endpoint', companion_refs=refs[2:])
    before = topology.copy.deepcopy(target)
    positions = [(fp.GetReference(), tuple(fp.GetPosition())) for fp in board.GetFootprints()]
    found = topology.articulated_primaries(board, target)
    assert [row['ref'] for row in found] == refs[1:]
    for row in found:
        assert {row['ref'], *row['companion_refs']} == set(refs[1:])
        assert row['target_net'] == net and (row['endpoint_ref'], row['endpoint_pad']) == peer
        assert topology.stationary_partition(board, row)['ok']
    assert target == before
    assert positions == [(fp.GetReference(), tuple(fp.GetPosition())) for fp in board.GetFootprints()]


def test_mobile_primary_selection_cannot_introduce_a_remote_or_undeclared_member():
    board, net, endpoint, peer, refs = fixture()
    target = dict(ref=endpoint[0], target_net=net, endpoint_ref=peer[0], endpoint_pad=peer[1],
                  motion='toward_endpoint', companion_refs=['ABSENT'])
    assert topology.articulated_primaries(board, target) == []
    target['companion_refs'] = refs[2:]
    board.FindFootprintByReference(refs[2]).Move(pcbnew.VECTOR2I_MM(7, 0))
    assert topology.articulated_primaries(board, target) == []

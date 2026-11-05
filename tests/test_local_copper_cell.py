"""Native and pure regressions for route-owned rigid-cell copper motion."""
import pytest

import cec_local_copper_cell as cell


def edge(uid, a, b, *, movable=True, layer=0):
    return dict(uuid=uid, start=(1, layer, a, 0), end=(1, layer, b, 0),
                length_mm=abs(b-a), movable=movable)


def test_degree_two_path_and_bounded_scope():
    edges = [edge('a', 0, 1), edge('b', 1, 2), edge('c', 2, 3)]
    terminals = {edges[0]['start']: 'first', edges[-1]['end']: 'last'}
    assert cell.chains(edges, terminals)[0]['uuids'] == ['a', 'b', 'c']
    assert not cell.chains(edges, terminals, max_items=2)
    assert not cell.chains(edges, terminals, max_length_mm=2.9)
    assert not cell.chains(edges, terminals, blocked_nodes=[edges[1]['start']])
    # An immovable external branch still contributes degree: no false path.
    assert not cell.chains(edges + [edge('branch', 1, 5, movable=False)], terminals)
    edges[1]['movable'] = False
    assert not cell.chains(edges, terminals)


def test_same_xy_on_another_layer_does_not_join_chain():
    edges = [edge('a', 0, 1), edge('b', 1, 2, layer=2)]
    terminals = {edges[0]['start']: 'first', edges[-1]['end']: 'last'}
    assert not cell.chains(edges, terminals)


def test_loop_is_not_two_distinct_terminals():
    edges = [edge('a', 0, 1), edge('b', 1, 2), edge('c', 2, 0)]
    assert not cell.chains(edges, {edges[0]['start']: 'only-terminal'})


def test_exact_inventory_contract():
    before = {'a': [1], 'b': [2], 'c': [3]}
    after = {'a': [5], 'c': [3]}
    assert cell.compare_inventory(before, after, moved=['a'], removed=['b'])['ok']
    assert not cell.compare_inventory(before, after, moved=['a'])['ok']
    after['c'] = [4]
    assert cell.compare_inventory(before, after, moved=['a'], removed=['b'])[
        'unauthorized_uuids'] == ['c']
    assert not cell.compare_inventory(before, before, moved=['unknown'])['ok']
    assert not cell.compare_inventory(before, before, removed=['a'])['ok']
    assert not cell.compare_inventory(before, before, moved=['a'], removed=['a'])['ok']


def native_cell(*, offset=0, names=('A17', 'B92'), net_name='/LOCAL'):
    import pcbnew
    board = pcbnew.CreateEmptyBoard()
    net = pcbnew.NETINFO_ITEM(board, net_name)
    board.Add(net)

    def pad(ref, x, y):
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x+offset, y+offset))
        obj = pcbnew.PAD(fp)
        obj.SetNumber('1')
        obj.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        obj.SetShape(pcbnew.PAD_SHAPE_RECT)
        obj.SetSize(pcbnew.VECTOR2I_MM(.4, .4))
        obj.SetPosition(fp.GetPosition())
        obj.SetLayerSet(pcbnew.PAD.SMDMask())
        obj.SetNet(net)
        fp.Add(obj)
        board.Add(fp)
        return fp

    def track(a, b, layer=pcbnew.F_Cu):
        obj = pcbnew.PCB_TRACK(board)
        obj.SetStart(pcbnew.VECTOR2I_MM(a[0]+offset, a[1]+offset))
        obj.SetEnd(pcbnew.VECTOR2I_MM(b[0]+offset, b[1]+offset))
        obj.SetWidth(pcbnew.FromMM(.15))
        obj.SetLayer(layer)
        obj.SetNet(net)
        board.Add(obj)
        return obj

    fps = [pad(names[0], 5, 5), pad(names[1], 8, 6)]
    internal = [track((5, 5), (6, 5)), track((6, 5), (7, 6)),
                track((7, 6), (8, 6))]
    # The same net is not ownership: a distant route stays byte-exact.
    external = track((20, 20), (25, 20))
    return board, fps, internal, external, pad, track


@pytest.mark.parametrize('offset,names,rotation', [
    (0, ('A17', 'B92'), 0), (37, ('X9', 'Z81'), 90),
    (-11, ('P31', 'P52'), 180)])
def test_native_reseat_keeps_complete_bent_cell(tmp_path, offset, names, rotation):
    import pcbnew
    import cec_certificate_repair as repair
    board, fps, internal, external, _, track = native_cell(offset=offset, names=names)
    stub = track((5, 5), (4, 5))
    stub_id = stub.m_Uuid.AsString()
    internal_ids = {item.m_Uuid.AsString() for item in internal}
    before = cell.copper_inventory(board)
    path = tmp_path/'cell.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    target = repair.FootprintRepairTarget(
        ref=names[0], target_net='/LOCAL', endpoint_ref='REMOTE', endpoint_pad='1',
        endpoint_x_mm=offset+4, endpoint_y_mm=offset+5,
        hit_count=1, distance_mm=1., priority=(0,), companion_refs=(names[1],))
    changed, report = repair._relocate_footprint_worker(str(path), repair.asdict(target),
        dict(dx_mm=.5, dy_mm=-1., rotation_delta_deg=rotation))
    assert changed, report
    assert set(report['moved_internal_track_uuids']) == internal_ids
    assert report['removed_track_uuids'] == [stub_id]
    assert report['copper_ownership']['ok']
    assert report['copper_ownership']['retained_unrelated_items'] == 1
    saved = pcbnew.LoadBoard(str(path))
    after = cell.copper_inventory(saved)
    assert cell.compare_inventory(before, after, moved=internal_ids, removed=[stub_id])['ok']
    assert after[external.m_Uuid.AsString()] == before[external.m_Uuid.AsString()]
    # Read back all native endpoints, not only reported counts.
    for uid in internal_ids:
        original, actual = before[uid], after[uid]
        for index in (3, 5):
            x, y = original[index:index+2]
            dx, dy = repair._rotate_board_vector(
                x-(5+offset)*1e6, y-(5+offset)*1e6, rotation)
            assert actual[index] == round((5.5+offset)*1e6+dx)
            assert actual[index+1] == round((4+offset)*1e6+dy)


@pytest.mark.parametrize('contact,reason', [
    ('foreign_pad', 'foreign_pad_contact'), ('tee', 'external_copper_contact'),
    ('overlap', 'external_copper_contact'), ('via', 'external_copper_contact'),
    ('zone', 'zone_contact')])
def test_native_foreign_contacts_are_not_silent_ownership(contact, reason):
    import pcbnew
    board, fps, internal, _, pad, track = native_cell()
    if contact == 'foreign_pad':
        pad('OUTSIDE', 6.5, 5.5)
    elif contact == 'tee':
        track((6.5, 5.5), (6.5, 8))
    elif contact == 'overlap':
        track((5, 5), (5.5, 5))
    elif contact == 'via':
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(6.5, 5.5))
        via.SetWidth(pcbnew.FromMM(.4))
        via.SetDrill(pcbnew.FromMM(.2))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(internal[0].GetNet())
        board.Add(via)
    else:
        zone = pcbnew.ZONE(board)
        zone.SetLayer(pcbnew.F_Cu)
        zone.SetNet(internal[0].GetNet())
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((6, 5), (7, 5), (7, 6), (6, 6)):
            outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        board.Add(zone)
    result = cell.plan(board, fps)
    assert not result['internal_track_uuids']
    assert result['rejected'][0]['reason'] == reason


def test_locks_groups_protected_net_and_layer_are_boundaries():
    import pcbnew
    board, fps, internal, _, _, track = native_cell()
    assert len(cell.plan(board, fps)['internal_track_uuids']) == 3
    internal[1].SetLocked(True)
    assert not cell.plan(board, fps)['internal_track_uuids']
    assert len(cell.plan(board, fps, generated_locked_uuids=[
        internal[1].m_Uuid.AsString()])['internal_track_uuids']) == 3
    internal[1].SetLocked(False)
    assert not cell.plan(board, fps, protected_nets=['/LOCAL'])['internal_track_uuids']
    internal[1].SetLayer(pcbnew.B_Cu)
    assert not cell.plan(board, fps)['internal_track_uuids']
    internal[1].SetLayer(pcbnew.F_Cu)
    group = pcbnew.PCB_GROUP(board)
    group.SetName('explicit-other-owner')
    group.AddItem(internal[1])
    board.Add(group)
    assert not cell.plan(board, fps)['internal_track_uuids']


def test_coincident_distinct_terminals_are_ambiguous():
    board, fps, _, _, pad, _ = native_cell()
    fps.append(pad('DUPLICATE', 5, 5))
    assert not cell.plan(board, fps)['internal_track_uuids']


def test_move_inventory_failure_never_saves(tmp_path, monkeypatch):
    import pcbnew
    import cec_certificate_repair as repair
    board, fps, _, _, _, _ = native_cell()
    path = tmp_path/'guard.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    before = path.read_bytes()
    target = repair.FootprintRepairTarget(
        ref='A17', target_net='/LOCAL', endpoint_ref='REMOTE', endpoint_pad='1',
        endpoint_x_mm=4., endpoint_y_mm=5., hit_count=1, distance_mm=1.,
        priority=(0,), companion_refs=('B92',))
    monkeypatch.setattr(cell, 'compare_inventory', lambda *args, **kwargs:
        dict(ok=False, unauthorized_uuids=['unrelated']))
    changed, report = repair._relocate_footprint_worker(str(path), repair.asdict(target),
        dict(dx_mm=.5, dy_mm=-1., rotation_delta_deg=0))
    assert not changed and report['refusal'] == 'unowned_local_copper_change'
    assert path.read_bytes() == before

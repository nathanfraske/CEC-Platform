"""Exact capsule contacts: no tolerance, labels, or union credit."""
import pcbnew
import pytest

import cec_native_capsule_contact as capsule


def fixture(source=((0, 0), (2000000, 0)), peer=((250000, 0), (250000, 100000)),
            replacement=((0, 0), (500000, 0)), width=200000, peer_width=200000):
    boards = [pcbnew.BOARD(), pcbnew.BOARD()]
    for board in boards:
        net = pcbnew.NETINFO_ITEM(board, '/renamed/native'); board.Add(net)
    def track(board, points, width, uid=None):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I(*points[0])); item.SetEnd(pcbnew.VECTOR2I(*points[1]))
        item.SetWidth(width); item.SetLayer(pcbnew.F_Cu)
        item.SetNet(board.GetNetInfo().GetNetItem('/renamed/native'))
        if uid: item.m_Uuid.Clone(pcbnew.KIID(uid))
        board.Add(item); return item
    s = track(boards[0], source, width)
    p = track(boards[0], peer, peer_width)
    retained = track(boards[1], peer, peer_width, str(p.m_Uuid.AsString()))
    r = track(boards[1], replacement, width)
    ids = [str(q.m_Uuid.AsString()) for q in (s, p, r)]
    def prove(): return capsule.prove(boards[0], ids[0], ids[1], boards[1], [ids[2]])
    return boards, s, p, retained, r, ids, prove


def transform(point, quarter, mirror):
    x, y = point
    if mirror: x = -x
    for _ in range(quarter): x, y = -y, x
    return x + 30000000, y + 20000000


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', (False, True))
@pytest.mark.parametrize('reverse_source', (False, True))
@pytest.mark.parametrize('reverse_peer', (False, True))
@pytest.mark.parametrize('reverse_replacement', (False, True))
def test_real_diagonal_contact_with_opaque_native_identities(quarter, mirror,
        reverse_source, reverse_peer, reverse_replacement):
    source = [(24670300,15734000), (25415378,16479078)]
    peer = [(24670300,15734000), (24224000,15734000)]
    replacement = [(24670300,15734000), (24890300,15954000)]
    if reverse_source: source.reverse()
    if reverse_peer: peer.reverse()
    if reverse_replacement: replacement.reverse()
    change = lambda pts: tuple(transform(p, quarter, mirror) for p in pts)
    boards, s, p, retained, r, ids, prove = fixture(
        source=change(source), peer=change(peer), replacement=change(replacement),
        width=500000, peer_width=500000)
    result = prove()
    assert result['ok'] and result['complete'], result
    assert result['all_old_contact_points_retained'] and result['no_union_credit']
    assert not any(result[k] for k in ('current_qualified', 'routing_admitted',
                                     'retirement_authorized', 'release_authority'))


@pytest.mark.parametrize('width', (200000, 200001))
@pytest.mark.parametrize('tail', (False, True))
def test_exact_tangent_and_one_nm_outside(width, tail):
    # For odd width the half-nanometre support remains an exact rational.
    # The tail case retains source B rather than source A.
    source = ((0,0),(2000000,0))
    center = 500000 - (width + 1)//2
    peer = ((center,0),(center,1000))
    replacement = ((0,0),(500000,0))
    if tail:
        flip = lambda p: (2000000-p[0],p[1])
        peer = tuple(flip(p) for p in peer)
        replacement = tuple(flip(p) for p in replacement)
    boards, s, p, retained, r, ids, prove = fixture(
        source=source, peer=peer, replacement=replacement, width=100001, peer_width=width)
    assert prove()['ok']
    delta = -1 if tail else 1
    p.Move(pcbnew.VECTOR2I(delta,0)); retained.Move(pcbnew.VECTOR2I(delta,0))
    result = prove()
    assert result['complete'] and not result['ok']


def test_integer_tangent_on_oblique_axis_and_one_nm_projection_change():
    # d=(3M,4M), peer radius=100k: support=500e9 nm2 exactly.
    # New endpoint is (300k,400k), projection=2500e9; peer centers at
    # (240k,320k), projection=2000e9. Moving 1nm along X exceeds tangency.
    boards, s, p, retained, r, ids, prove = fixture(
        source=((0,0),(3000000,4000000)), peer=((240000,320000),(240004,319997)),
        replacement=((0,0),(300000,400000)))
    assert prove()['ok']
    p.Move(pcbnew.VECTOR2I(1,0)); retained.Move(pcbnew.VECTOR2I(1,0))
    assert prove()['complete'] and not prove()['ok']


def test_middle_interval_requires_both_projection_bounds():
    boards, s, p, retained, r, ids, prove = fixture(
        peer=((1000000,0),(1000000,1000)), replacement=((800000,0),(1200000,0)))
    assert prove()['ok']
    p.Move(pcbnew.VECTOR2I(-100001,0)); retained.Move(pcbnew.VECTOR2I(-100001,0))
    assert not prove()['ok']


def test_no_union_credit_for_two_insufficient_intervals():
    boards, s, p, retained, r, ids, prove = fixture(
        peer=((900000,0),(1100000,0)), replacement=((0,0),(1000000,0)))
    extra = pcbnew.PCB_TRACK(boards[1]); extra.SetNet(r.GetNet()); extra.SetLayer(r.GetLayer())
    extra.SetWidth(r.GetWidth()); extra.SetStart(pcbnew.VECTOR2I(1000000,0))
    extra.SetEnd(pcbnew.VECTOR2I(2000000,0)); boards[1].Add(extra)
    result = capsule.prove(boards[0],ids[0],ids[1],boards[1],[ids[2],str(extra.m_Uuid.AsString())])
    assert result['complete'] and not result['ok'] and result['no_union_credit']


@pytest.mark.parametrize('fault', ('source_arc','peer_via','replacement_arc','zero_source',
    'zero_peer','zero_replacement','unassigned','foreign','layer','width',
    'noncollinear','outside_axis','retained_peer_changed','missing_source','missing_peer',
    'missing_replacement','empty','duplicate','source_mutated'))
def test_unknown_or_insufficient_native_geometry_never_grants_authority(fault):
    boards, s, p, retained, r, ids, prove = fixture()
    if fault.endswith('_arc') or fault == 'peer_via':
        board = boards[0] if fault != 'replacement_arc' else boards[1]
        original = s if fault == 'source_arc' else p if fault == 'peer_via' else r
        uid = str(original.m_Uuid.AsString()); board.Delete(original)
        item = pcbnew.PCB_VIA(board) if fault == 'peer_via' else pcbnew.PCB_ARC(board)
        item.m_Uuid.Clone(pcbnew.KIID(uid)); board.Add(item)
    elif fault.startswith('zero_'):
        item = {'zero_source':s,'zero_peer':p,'zero_replacement':r}[fault]
        item.SetEnd(item.GetStart())
    elif fault == 'unassigned': s.SetNetCode(0)
    elif fault == 'foreign':
        net = pcbnew.NETINFO_ITEM(boards[1],'/foreign'); boards[1].Add(net); r.SetNet(net)
    elif fault == 'layer': r.SetLayer(pcbnew.B_Cu)
    elif fault == 'width': r.SetWidth(r.GetWidth()+1)
    elif fault == 'noncollinear': r.SetEnd(pcbnew.VECTOR2I(500000,1))
    elif fault == 'outside_axis': r.SetStart(pcbnew.VECTOR2I(-1,0))
    elif fault == 'retained_peer_changed': retained.Move(pcbnew.VECTOR2I(1,0))
    elif fault == 'missing_source': ids[0] = 'missing'
    elif fault == 'missing_peer': ids[1] = 'missing'
    elif fault == 'missing_replacement': ids[2] = 'missing'
    elif fault in ('empty','duplicate'):
        selected = [] if fault == 'empty' else [ids[2],ids[2]]
        result = capsule.prove(boards[0],ids[0],ids[1],boards[1],selected)
        assert not result['ok'] and not result['complete']; return
    elif fault == 'source_mutated':
        assert prove()['ok']; s.SetWidth(s.GetWidth()+1)
    result = prove()
    assert not result['ok'], result
    assert not any(result[k] for k in ('current_qualified','routing_admitted',
                                     'retirement_authorized','release_authority'))


def test_false_contact_is_not_positive_empty_set_permission():
    boards, s, p, retained, r, ids, prove = fixture(peer=((250000,200001),(250000,300000)))
    result = prove()
    assert result['complete'] and not result['ok']
    assert result['reason'] == 'no_actual_source_peer_contact'


def test_live_source_mutation_recomputes_instead_of_reusing_a_success():
    boards, s, p, retained, r, ids, prove = fixture()
    assert prove()['ok']
    s.SetEnd(pcbnew.VECTOR2I(500000,100000))
    assert not prove()['ok']


def test_unknown_boards_and_extreme_native_envelopes_refuse():
    result = capsule.prove(None, 'source', 'peer', None, ['replacement'])
    assert not result['ok'] and not result['complete']
    boards, s, p, retained, r, ids, prove = fixture()
    s.SetStart(pcbnew.VECTOR2I(1999999999,0))
    assert not prove()['ok'] and not prove()['complete']


def test_live_source_peer_width_mutation_cannot_reuse_an_old_witness():
    boards, s, p, retained, r, ids, prove = fixture()
    assert prove()['ok']
    p.SetWidth(p.GetWidth()+1)
    result = prove()
    assert not result['ok'] and not result['complete']
    assert 'retained_peer_geometry_changed' in result['reason']


def test_helper_is_read_only_and_integer_witnesses_are_recomputed():
    boards, s, p, retained, r, ids, prove = fixture()
    def snapshot():
        return [(str(t.m_Uuid.AsString()),tuple(t.GetStart()),tuple(t.GetEnd()),
                 t.GetWidth(),t.GetLayer(),t.GetNetCode(),t.IsLocked())
                for board in boards for t in board.GetTracks()]
    before = snapshot(); first = prove(); second = prove()
    assert first == second and snapshot() == before
    for witness in first['witnesses']:
        assert type(witness['axis_squared_nm2']) is int
        for side in ('lower','upper'):
            assert type(witness[side]['four_margin_squared']) is int
            assert type(witness[side]['peer_width_squared_times_axis_squared']) is int

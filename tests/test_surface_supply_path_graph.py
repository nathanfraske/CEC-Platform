"""Native physical fixtures, not mocked contact/current/admission receipts."""
import time

import pcbnew
import pytest

import cec_surface_supply_path_graph as graph
import cec_force_current as force
import cec_native_fill_geometry as fill
from cec_native_items import discard_items


def v(x, y):
    return pcbnew.VECTOR2I(round(x*1e6), round(y*1e6))


def mask(face):
    result = pcbnew.LSET(); result.AddLayer(face); return result


def pad(board, net, x, y, *, ref='P', face=pcbnew.F_Cu, size=(1., 1.),
        hole=0., npth=False, angle=0.):
    fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); board.Add(fp)
    p = pcbnew.PAD(fp); p.SetNumber('1'); fp.Add(p)
    p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH if npth else
                   pcbnew.PAD_ATTRIB_PTH if hole else pcbnew.PAD_ATTRIB_SMD)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE if hole else pcbnew.PAD_SHAPE_RECT)
    p.SetSize(v(*size)); p.SetPosition(v(x, y)); p.SetOrientationDegrees(angle)
    p.SetLayerSet(pcbnew.LSET.AllCuMask() if hole else mask(face))
    if hole:
        p.SetDrillSize(v(hole, hole))
    p.SetNet(board.FindNet(net)); return p


def track(board, net, a, b, *, face=pcbnew.F_Cu, width=.2):
    t = pcbnew.PCB_TRACK(board); t.SetNet(board.FindNet(net)); t.SetLayer(face)
    t.SetWidth(round(width*1e6)); t.SetStart(v(*a)); t.SetEnd(v(*b)); board.Add(t)
    return t


def via(board, net, x, y, *, diameter=.9, drill=.4):
    t = pcbnew.PCB_VIA(board); t.SetNet(board.FindNet(net)); t.SetPosition(v(x, y))
    t.SetViaType(pcbnew.VIATYPE_THROUGH); t.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    t.SetWidth(round(diameter*1e6)); t.SetDrill(round(drill*1e6)); board.Add(t)
    return t


def clone(board, tmp_path):
    import cec_field_coupling as field
    path = tmp_path/'clone.kicad_pcb'
    field._save_field_snapshot(board, path)
    return pcbnew.LoadBoard(str(path))


@pytest.fixture
def scope(tmp_path, monkeypatch):
    # Only the external fresh-current/class resolver is stubbed. Every hole,
    # pad, stroke, island and contact operation is real KiCad integer CSG.
    monkeypatch.setattr(graph.full, '_source_width_floor', lambda b, s, c, f: 200000)
    source = tmp_path/'source.kicad_pcb'; source.write_text('external Source binding fixture')
    b = pcbnew.BOARD(); b.SetCopperLayerCount(6)
    for name in ('RAIL', 'FOREIGN'):
        b.Add(pcbnew.NETINFO_ITEM(b, name))
    pad(b, 'RAIL', 0, 0, ref='A'); pad(b, 'RAIL', 4, 0, ref='Z')
    return b, source, [dict(net='RAIL')]


def prove(scope, child, **kwargs):
    b, source, contracts = scope
    return graph.prove(b, child, source, contracts, **kwargs)


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('angle', [0., 90., 180., 270.])
def test_full_native_surface_join_rotated_renamed_no_qualification(scope, tmp_path, face, angle):
    b, _, _ = scope
    for fp in b.GetFootprints():
        fp.SetReference('RENAMED_'+fp.GetReference())
        p = next(iter(fp.Pads())); p.SetLayerSet(mask(face)); p.SetOrientationDegrees(angle)
    c = clone(b, tmp_path); track(c, 'RAIL', (0, 0), (4, 0), face=face)
    before = [force._item_key(p) for fp in c.GetFootprints() for p in fp.Pads()]
    r = prove(scope, c)
    assert r['complete'] and r['all_source_pads_surface_connected']
    assert not any(r[k] for k in ('routing_admitted', 'current_capacity_qualified',
        'barrel_ampacity_qualified', 'pad_contact_capacity_qualified', 'release_authority'))
    assert before == [force._item_key(p) for fp in c.GetFootprints() for p in fp.Pads()]


@pytest.mark.parametrize('kind', ['thin', 'inner', 'foreign', 'zone'])
def test_nonqualifying_dependency_never_connects(scope, tmp_path, kind):
    b, _, _ = scope; c = clone(b, tmp_path)
    if kind == 'zone':
        z = pcbnew.ZONE(c); z.SetNet(c.FindNet('RAIL')); z.SetLayer(pcbnew.F_Cu)
        shape = fill.reconstruct([[[[-1000000, -1000000], [5000000, -1000000],
                                    [5000000, 1000000], [-1000000, 1000000]]]], time.monotonic()+2.)
        z.Outline().Append(shape); z.SetFilledPolysList(pcbnew.F_Cu, shape)
        z.SetIsFilled(True); c.Add(z)
    else:
        track(c, 'FOREIGN' if kind == 'foreign' else 'RAIL', (0, 0), (4, 0),
              face=pcbnew.In1_Cu if kind == 'inner' else pcbnew.F_Cu,
              width=.199999 if kind == 'thin' else .2)
    assert not prove(scope, c)['complete']


@pytest.mark.parametrize('owner', ['foreign_npth', 'own_npth', 'foreign_via', 'own_via', 'slot'])
def test_every_actual_drill_void_cuts_surface_material(scope, tmp_path, owner):
    b, _, _ = scope; c = clone(b, tmp_path)
    track(c, 'RAIL', (0, 0), (4, 0))
    net = 'RAIL' if owner.startswith('own') else 'FOREIGN'
    if owner.endswith('via'):
        # The bore severs the stroke. Its tiny annulus cannot bridge the
        # severed route through the centre or acquire foreign-net credit.
        via(c, net, 2, 0, diameter=.42, drill=.4)
    else:
        p = pad(c, net, 2, 0, ref='HOLE', size=(.4, .4), hole=.4, npth=True)
        if owner == 'slot':
            p.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
            p.SetDrillSize(v(.4, 1.)); p.SetOrientationDegrees(25.)
        if net == 'RAIL':
            # The original Source also contains the actual nonconducting
            # terminal. It cannot be omitted or used as plated access.
            p0 = pad(b, net, 2, 0, ref='HOLE', size=(.4, .4), hole=.4, npth=True)
            p0.m_Uuid.Clone(p.m_Uuid); p0.GetParentFootprint().m_Uuid.Clone(p.GetParentFootprint().m_Uuid)
    if owner == 'own_via':
        # Avoid annular metal as a lateral shortcut: a larger bore crosses
        # an entire terminal-to-terminal .2 stroke inside a thin .01 ring.
        result = prove(scope, c)
        assert not result['complete']
    else:
        assert not prove(scope, c)['complete']


def test_retired_physical_hole_is_truly_absent_not_subtracted_from_parent(scope, tmp_path):
    b, _, _ = scope; via(b, 'FOREIGN', 2, 0, diameter=.6, drill=.4)
    c = clone(b, tmp_path)
    discard_items(c, list(c.GetTracks())); track(c, 'RAIL', (0, 0), (4, 0))
    r = prove(scope, c)
    assert r['complete'] and r['actual_child_drill_count'] == 0


def test_point_or_tangent_contact_is_not_positive_area(scope, tmp_path):
    b, _, _ = scope; c = clone(b, tmp_path)
    # Exact rectangle/rectangle tangency, no round-cap approximation.
    p = next(iter(c.FindFootprintByReference('Z').Pads()))
    p.SetPosition(v(1., 0))
    p0 = next(iter(b.FindFootprintByReference('Z').Pads())); p0.SetPosition(v(1., 0))
    assert not prove(scope, c)['complete']


def test_integer_one_nm_overlap_is_distinct_from_tangency():
    def rect(x):
        return fill.reconstruct([[[[x, 0], [x+100, 0], [x+100, 100], [x, 100]]]],
                                time.monotonic()+2.)
    first = rect(0)
    assert not graph._positive(first, rect(100), time.monotonic()+2.)
    assert graph._positive(first, rect(99), time.monotonic()+2.)


def test_foreign_drill_splits_one_pad_into_distinct_physical_nodes(scope, tmp_path):
    b, _, _ = scope
    first = next(iter(b.FindFootprintByReference('A').Pads()))
    first.SetSize(v(2., 1.))
    c = clone(b, tmp_path)
    # A native slot cuts the pad right through. The right island touches Z,
    # but its UUID must not manufacture connectivity to the left island.
    p = pad(c, 'FOREIGN', 0, 0, ref='SLOT', size=(.4, 2.), hole=.4, npth=True)
    p.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG); p.SetDrillSize(v(.4, 2.))
    track(c, 'RAIL', (.5, 0), (4, 0))
    r = prove(scope, c)
    assert not r['complete']
    assert max(len(p['nodes']) for p in r['nets'][0]['source_pads']) == 2


@pytest.mark.parametrize('fault', ['lost', 'moved', 'size', 'orientation', 'net', 'extra'])
def test_all_original_source_railpads_exact(scope, tmp_path, fault):
    b, _, _ = scope; c = clone(b, tmp_path); fp = c.FindFootprintByReference('Z')
    p = next(iter(fp.Pads()))
    if fault == 'lost': discard_items(c, [fp])
    elif fault == 'moved': p.SetPosition(v(4.000001, 0))
    elif fault == 'size': p.SetSize(v(.99, 1.))
    elif fault == 'orientation': p.SetOrientationDegrees(90.)
    elif fault == 'net': p.SetNet(c.FindNet('FOREIGN'))
    else: pad(c, 'RAIL', 8, 0, ref='EXTRA')
    with pytest.raises(ValueError, match='railpad'):
        prove(scope, c)


@pytest.mark.parametrize('kind', ['via', 'pth', 'npth', 'thin', 'foreign_hole'])
def test_only_full_web_plated_normal_access_joins_faces(scope, tmp_path, kind):
    b, _, _ = scope
    p = next(iter(b.FindFootprintByReference('Z').Pads())); p.SetLayerSet(mask(pcbnew.B_Cu))
    if kind in ('pth', 'npth'):
        pad(b, 'RAIL', 2, 0, ref='ACCESS', size=(.9, .9), hole=.4, npth=kind == 'npth')
    c = clone(b, tmp_path)
    track(c, 'RAIL', (0, 0), (2, 0)); track(c, 'RAIL', (2, 0), (4, 0), face=pcbnew.B_Cu)
    if kind not in ('pth', 'npth'):
        via(c, 'RAIL', 2, 0, diameter=.5 if kind == 'thin' else .9, drill=.4)
    if kind == 'foreign_hole':
        pad(c, 'FOREIGN', 2.35, 0, ref='CUT_RING', size=(.4, .4), hole=.4, npth=True)
    r = prove(scope, c)
    assert r['complete'] is (kind in ('via', 'pth'))


def test_custom_pad_uuid_cannot_bridge_separate_native_islands(scope, tmp_path):
    b, _, _ = scope
    p = next(iter(b.FindFootprintByReference('A').Pads()))
    p.SetShape(pcbnew.PAD_SHAPE_CUSTOM); p.SetAnchorPadShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_RECT)
    p.SetSize(v(.2, .2))
    # Actual disconnected native custom copper under ONE pad UUID.
    p.AddPrimitivePoly(pcbnew.F_Cu, [v(-.5, -.5), v(.5, -.5), v(.5, .5), v(-.5, .5)], 0, True)
    p.AddPrimitivePoly(pcbnew.F_Cu, [v(1.5, -.5), v(2.5, -.5), v(2.5, .5), v(1.5, .5)], 0, True)
    c = clone(b, tmp_path); track(c, 'RAIL', (2, 0), (4, 0))
    r = prove(scope, c)
    assert not r['complete']
    assert len(r['nets'][0]['source_pads'][0]['nodes']) in (1, 2)
    assert max(len(p['nodes']) for p in r['nets'][0]['source_pads']) == 2


@pytest.mark.parametrize('kwargs', [{'timeout_s': True}, {'timeout_s': 11},
    {'max_items': 1}, {'max_nodes': 1}, {'max_vertices': 32}, {'max_checks': 1}])
def test_bounds_refuse_not_positive(scope, tmp_path, kwargs):
    b, _, _ = scope; c = clone(b, tmp_path); track(c, 'RAIL', (0, 0), (4, 0))
    with pytest.raises(ValueError): prove(scope, c, **kwargs)


def test_deadline_and_final_hash_deadline_fail_closed(scope, tmp_path, monkeypatch):
    b, _, _ = scope; c = clone(b, tmp_path); track(c, 'RAIL', (0, 0), (4, 0))
    clock = [0.]
    monkeypatch.setattr(graph.time, 'monotonic', lambda: clock[0])
    original = graph.force._hash; calls = []
    def late_hash(path):
        result = original(path); calls.append(path)
        if len(calls) == 2: clock[0] = 20.
        return result
    monkeypatch.setattr(graph.force, '_hash', late_hash)
    with pytest.raises(ValueError, match='deadline'): prove(scope, c, timeout_s=1.)


def test_expired_inventory_deadline_is_not_a_negative_or_positive_receipt(scope, tmp_path, monkeypatch):
    b, _, _ = scope; c = clone(b, tmp_path)
    calls = iter([0., 20.])
    monkeypatch.setattr(graph.time, 'monotonic', lambda: next(calls, 20.))
    with pytest.raises(ValueError, match='deadline'): prove(scope, c, timeout_s=1.)


def test_changed_source_at_final_hash_refuses(scope, tmp_path, monkeypatch):
    b, _, _ = scope; c = clone(b, tmp_path); track(c, 'RAIL', (0, 0), (4, 0))
    original = graph.force._hash; calls = []
    def changed(path):
        calls.append(path)
        return original(path) if len(calls) == 1 else 'different Source'
    monkeypatch.setattr(graph.force, '_hash', changed)
    with pytest.raises(ValueError, match='source_or_contract_changed'): prove(scope, c)


def test_floor_derived_for_each_actual_face_not_a_default_constant(scope, tmp_path, monkeypatch):
    b, _, _ = scope; c = clone(b, tmp_path)
    p = next(iter(b.FindFootprintByReference('Z').Pads())); p.SetLayerSet(mask(pcbnew.B_Cu))
    p = next(iter(c.FindFootprintByReference('Z').Pads())); p.SetLayerSet(mask(pcbnew.B_Cu))
    calls = []
    def floor(board, source, contract, face):
        calls.append((board, contract['net'], face))
        return 200000 if face == pcbnew.F_Cu else 500000
    monkeypatch.setattr(graph.full, '_source_width_floor', floor)
    track(c, 'RAIL', (0, 0), (2, 0)); track(c, 'RAIL', (2, 0), (4, 0), face=pcbnew.B_Cu, width=.2)
    via(c, 'RAIL', 2, 0)
    r = prove(scope, c)
    assert not r['complete']
    assert calls == [(b, 'RAIL', pcbnew.F_Cu), (b, 'RAIL', pcbnew.B_Cu)]
    assert r['nets'][0]['floors_nm'] == {str(pcbnew.F_Cu): 200000, str(pcbnew.B_Cu): 500000}


def test_global_hole_inventory_obeys_aggregate_vertex_bound(scope, tmp_path):
    b, _, _ = scope; c = clone(b, tmp_path)
    pad(c, 'FOREIGN', 20, 0, ref='DISTANT', size=(.6, .6), hole=.4, npth=True)
    with pytest.raises(ValueError, match='complexity_bound'): prove(scope, c, max_vertices=32)


def test_300_actual_holes_exceed_old_bound_under_unchanged_native_precision(scope, tmp_path):
    b, _, _ = scope
    # All 300 physically present child holes count, even though far from the
    # rail: Source thin own-net vias, foreign vias and foreign NPTH drills.
    # No hole is discarded by a route/ROI/net filter or coarse polygonizer.
    for i in range(300):
        x, y = 20.+(i % 30)*2., 20.+(i // 30)*2.
        if i % 3 == 0:
            via(b, 'RAIL', x, y, diameter=.45, drill=.4)
        elif i % 3 == 1:
            via(b, 'FOREIGN', x, y, diameter=.6, drill=.4)
        else:
            pad(b, 'FOREIGN', x, y, ref='NPTH_'+str(i), size=(.6, .6), hole=.4, npth=True)
    c = clone(b, tmp_path); track(c, 'RAIL', (0, 0), (4, 0))
    holes = [p for fp in c.GetFootprints() for p in fp.Pads() if p.HasHole()]
    holes += [t for t in c.GetTracks() if t.GetClass() == 'PCB_VIA']
    actual = sum(fill.identity(graph._hole(h, time.monotonic()+5.), time.monotonic()+5.)[1]
                 for h in holes)
    assert len(holes) == 300 and actual > 200000
    r = prove(scope, c)
    assert r['complete'] and r['actual_child_drill_count'] == 300
    assert 200000 < actual <= r['vertices'] <= 500000
    assert r['all_child_drills_subtracted']
    for bound in (200000, 32):
        with pytest.raises(ValueError, match='complexity_bound'):
            prove(scope, c, max_vertices=bound)


@pytest.mark.parametrize('bad', [1000001, True, float('nan'), float('inf'), 500000.])
def test_vertex_compute_budget_type_and_hard_limit_are_strict(scope, tmp_path, bad):
    b, _, _ = scope; c = clone(b, tmp_path)
    with pytest.raises(ValueError, match='bounded_surface_supply_path_required'):
        prove(scope, c, max_vertices=bad)


@pytest.mark.parametrize('bad', [float('nan'), float('inf')])
def test_nonfinite_lease_is_never_a_compute_escape(scope, tmp_path, bad):
    b, _, _ = scope; c = clone(b, tmp_path)
    with pytest.raises(ValueError, match='bounded_surface_supply_path_required'):
        prove(scope, c, timeout_s=bad)


@pytest.mark.parametrize('bad', [[], [{'net': ''}], [{'net': 'RAIL'}, {'net': 'RAIL'}], [True]])
def test_no_guessed_or_ambiguous_contract(scope, tmp_path, bad):
    b, source, _ = scope; c = clone(b, tmp_path)
    with pytest.raises(ValueError, match='contracts'):
        graph.prove(b, c, source, bad)

"""Bounded, drill-subtracted outer-surface metal connectivity, NOT admission.

Contracts are freshly compiled by the caller. This checker derives their
unchanged Source/class face floors, but supplies no current, barrel ampacity,
thermal, clearance, fabrication, ownership, or release qualification. Native
parent/source-file identity and the complete saved transaction remain caller
obligations. No zone, inner stroke, thin stroke, or shared UUID is a bridge.
"""
import hashlib
import math
from pathlib import Path
import time

import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_native_fill_geometry as fill


FACES = (pcbnew.F_Cu, pcbnew.B_Cu)


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('surface_supply_path_deadline')


def _digest(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()


def _area2(shape, deadline):
    total = 0
    if not shape.OutlineCount():
        return 0
    for polygon in fill.snapshot(shape, deadline):
        for index, ring in enumerate(polygon):
            _tick(deadline)
            area = abs(sum(a[0]*b[1]-b[0]*a[1]
                           for a, b in zip(ring, ring[1:]+ring[:1])))
            total += area if index == 0 else -area
    if total < 0:
        raise ValueError('surface_supply_ambiguous_native_area')
    return total


def _positive(a, b, deadline):
    _tick(deadline)
    if not a.BBox().Intersects(b.BBox()):
        return False
    overlap = a.CloneDropTriangulation()
    overlap.BooleanIntersection(b)
    _tick(deadline)
    return _area2(overlap, deadline) > 0


def _shape(item, face, deadline):
    _tick(deadline)
    result = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(result, face, 0, 1, pcbnew.ERROR_INSIDE)
    _tick(deadline)
    return result


def _polygons(shape, deadline):
    if not shape.OutlineCount():
        return []
    rows = fill.snapshot(shape, deadline)
    # A zero-width native fracture bridge is not physical connectivity.
    if any(len(set(map(tuple, ring))) != len(ring)
           for polygon in rows for ring in polygon):
        shape, _ = fill.decode_exact_hole_boundaries(shape, deadline)
        rows = fill.snapshot(shape, deadline)
    return rows


def _pad_key(pad):
    fp = pad.GetParentFootprint()
    return (force._uid(fp), force._uid(pad), str(pad.GetNumber()))


def _pad_signature(pad, deadline):
    fp = pad.GetParentFootprint()
    return (str(fp.GetReference()), str(fp.GetValue()), str(fp.GetFPIDAsString()),
        tuple(fp.GetPosition()), float(fp.GetOrientationDegrees()), bool(fp.IsFlipped()),
        str(pad.GetNetname()), tuple(pad.GetPosition()), float(pad.GetOrientationDegrees()),
        int(pad.GetAttribute()), int(pad.GetShape()), tuple(pad.GetSize()),
        tuple(pad.GetOffset()), tuple(pad.GetDrillSize()), int(pad.GetDrillShape()),
        tuple(map(int, pad.GetLayerSet().Seq())),
        tuple((int(face), fill.identity(_shape(pad, face, deadline), deadline)[0])
              for face in FACES if pad.IsOnLayer(face)))


def _items(board, maximum, deadline):
    pads = []
    for fp in board.GetFootprints():
        _tick(deadline)
        for pad in fp.Pads():
            pads.append(pad)
            if len(pads) > maximum:
                raise ValueError('surface_supply_item_bound')
    tracks = list(board.GetTracks())
    if len(pads)+len(tracks)+len(list(board.Zones())) > maximum:
        raise ValueError('surface_supply_item_bound')
    _tick(deadline)
    return pads, tracks


def _hole(item, deadline):
    _tick(deadline)
    result = pcbnew.SHAPE_POLY_SET()
    item.GetEffectiveHoleShape().TransformToPolygon(result, 1, pcbnew.ERROR_OUTSIDE)
    if not result.OutlineCount() or _area2(result, deadline) <= 0:
        raise ValueError('surface_supply_unknown_physical_drill')
    return result


def _barrel(item, floors):
    """Conservative normal circular geometry only; never an ampacity model."""
    if item.GetClass() == 'PCB_VIA':
        return (item.GetViaType() == pcbnew.VIATYPE_THROUGH
            and item.TopLayer() == pcbnew.F_Cu and item.BottomLayer() == pcbnew.B_Cu
            and item.GetDrillValue() > 0
            and all(item.GetWidth(face)-item.GetDrillValue() >= max(floors.values())
                    for face in FACES))
    return (item.GetClass() == 'PAD' and item.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        and item.HasHole() and item.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
        and item.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_CIRCLE
        and tuple(item.GetOffset()) == (0, 0)
        and item.GetSize().x == item.GetSize().y
        and 0 < item.GetDrillSize().x == item.GetDrillSize().y
        and item.GetSize().x-item.GetDrillSize().x >= max(floors.values())
        and all(item.IsOnLayer(face) for face in FACES))


def prove(parent, child, source, contracts, *, timeout_s=10., max_items=16384,
          max_nodes=4096, max_vertices=500000, max_checks=2000000):
    """Prove ALL Source rail-pad islands join through full-floor F/B metal.

    ``parent``/``child`` are actual native boards, ``source`` the unchanged
    Source path used by the full-current floor resolver, and ``contracts`` a
    nonempty list/tuple of externally compiled full-model dictionaries with
    distinct literal nets. False connectivity is a negative result; missing
    identity, unsupported/unknown geometry, bounds and deadlines raise.
    Returned evidence cannot authorize a route, cut, pose or barrel change.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10
            or any(type(v) is not int or not lo <= v <= hi for v, lo, hi in (
                (max_items, 1, 16384), (max_nodes, 1, 4096),
                (max_vertices, 32, 1000000), (max_checks, 1, 2000000)))):
        raise ValueError('bounded_surface_supply_path_required')
    deadline = time.monotonic()+timeout_s
    if (type(contracts) not in (list, tuple) or not 1 <= len(contracts) <= 8
            or any(type(c) is not dict or type(c.get('net')) is not str
                   or not c['net'] for c in contracts)
            or len({c['net'] for c in contracts}) != len(contracts)):
        raise ValueError('explicit_unique_surface_supply_contracts_required')
    source = Path(source).resolve(strict=True)
    source_sha = force._hash(source)
    contract_binding = _digest(contracts)
    oldpads, _ = _items(parent, max_items, deadline)
    pads, tracks = _items(child, max_items, deadline)
    holes = []
    checks = vertices = node_count = 0
    for item in [*pads, *tracks]:
        _tick(deadline)
        if item.GetClass() == 'PAD':
            if any(item.IsBackdrilledOrPostMachined(face)
                   for face in item.GetLayerSet().CuStack()):
                raise ValueError('surface_supply_unsupported_postmachined_drill')
            drilled = item.HasHole()
        else:
            drilled = item.GetClass() == 'PCB_VIA'
        if drilled:
            hole = _hole(item, deadline)
            vertices += fill.identity(hole, deadline)[1]
            if vertices > max_vertices:
                raise ValueError('surface_supply_native_complexity_bound')
            holes.append((item, hole))
    # All child holes, including foreign-net and NPTH/slot holes, are removed
    # from EVERY considered surface. Buried holes are conservatively removed
    # too; no inaccessible drill void can produce a false positive.
    rows = []
    def spend():
        nonlocal checks
        checks += 1
        _tick(deadline)
        if checks > max_checks:
            raise ValueError('surface_supply_work_bound')
    for contract in contracts:
        _tick(deadline)
        net = contract['net']
        floors = {int(face): full._source_width_floor(parent, source, contract, face)
                  for face in FACES}
        if any(type(v) is not int or v <= 0 for v in floors.values()):
            raise ValueError('surface_supply_positive_source_face_floors_required')
        before = [p for p in oldpads if str(p.GetNetname()) == net]
        after = [p for p in pads if str(p.GetNetname()) == net]
        old = {_pad_key(p): p for p in before}
        new = {_pad_key(p): p for p in after}
        if (not before or len(old) != len(before) or len(new) != len(after)
                or old.keys() != new.keys()):
            raise ValueError('surface_supply_exact_source_railpads_required')
        source_pad_binding = []
        for key, pad in old.items():
            signature = _pad_signature(pad, deadline)
            if signature != _pad_signature(new[key], deadline):
                raise ValueError('surface_supply_source_railpad_moved_or_changed')
            source_pad_binding.append((key, signature))
        nodes = []
        owned = {}
        eligible = [p for p in after if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
        eligible += [t for t in tracks if str(t.GetNetname()) == net
            and (t.GetClass() == 'PCB_VIA' and _barrel(t, floors) or t.GetClass() == 'PCB_TRACK'
                 and int(t.GetLayer()) in FACES and t.GetWidth() >= floors[int(t.GetLayer())])]
        seen = set()
        for item in eligible:
            _tick(deadline)
            key = ('pad', *_pad_key(item)) if item.GetClass() == 'PAD' else ('copper', force._uid(item))
            if key in seen:
                raise ValueError('surface_supply_ambiguous_material_identity')
            seen.add(key)
            by_face = {}
            intact = True
            for face in FACES:
                if not item.IsOnLayer(face):
                    continue
                material = _shape(item, face, deadline)
                # Retain a separate own-bore annulus for the through-face
                # check. A foreign drill biting that ring invalidates access.
                own = material.CloneDropTriangulation()
                if item.GetClass() == 'PCB_VIA' or item.GetClass() == 'PAD' and item.HasHole():
                    own.BooleanSubtract(_hole(item, deadline))
                for _, hole in holes:
                    spend()
                    if material.BBox().Intersects(hole.BBox()):
                        material.BooleanSubtract(hole)
                loss = own.CloneDropTriangulation()
                loss.BooleanSubtract(material)
                if _area2(loss, deadline) > 0:
                    intact = False
                indices = []
                for polygon in _polygons(material, deadline):
                    vertices += sum(len(ring) for ring in polygon)
                    node_count += 1
                    if vertices > max_vertices or node_count > max_nodes:
                        raise ValueError('surface_supply_native_complexity_bound')
                    shape = fill.reconstruct([polygon], deadline)
                    if _area2(shape, deadline) <= 0:
                        continue
                    indices.append(len(nodes))
                    nodes.append(dict(key=key, face=int(face), shape=shape))
                by_face[int(face)] = indices
            owned[key] = dict(faces=by_face, bridge=intact and _barrel(item, floors))
        adjacency = [set() for _ in nodes]
        for i, a in enumerate(nodes):
            for j in range(i):
                b = nodes[j]
                if a['face'] != b['face']:
                    continue
                spend()
                if _positive(a['shape'], b['shape'], deadline):
                    adjacency[i].add(j); adjacency[j].add(i)
        barrel_edges = []
        for key, item in owned.items():
            if not item['bridge'] or any(len(item['faces'].get(int(face), [])) != 1 for face in FACES):
                continue
            a, b = (item['faces'][int(face)][0] for face in FACES)
            # No same UUID or island-index pairing: prove the SAME intact
            # annular material exists on both surfaces before access credit.
            spend()
            if _positive(nodes[a]['shape'], nodes[b]['shape'], deadline):
                adjacency[a].add(b); adjacency[b].add(a)
                barrel_edges.append(list(key))
        terminal_nodes = []
        terminal_rows = []
        for key in sorted(old):
            actual = owned.get(('pad', *key), {}).get('faces', {})
            indices = [i for face in FACES for i in actual.get(int(face), [])]
            terminal_rows.append(dict(source_pad_key=list(key), nodes=indices))
            terminal_nodes.extend(indices)
        reached = set()
        if terminal_nodes:
            pending = [terminal_nodes[0]]
            while pending:
                _tick(deadline)
                i = pending.pop()
                if i in reached:
                    continue
                reached.add(i); pending.extend(adjacency[i]-reached)
        connected = (bool(terminal_nodes) and all(r['nodes'] for r in terminal_rows)
                     and set(terminal_nodes) <= reached)
        rows.append(dict(net=net, connected=connected, source_pad_count=len(old),
            source_pad_binding_sha256=_digest(sorted(source_pad_binding)),
            floors_nm={str(k): v for k, v in floors.items()},
            source_pads=terminal_rows, material_node_count=len(nodes),
            reached_nodes=sorted(reached), barrel_access_keys=barrel_edges,
            nodes=[dict(index=i, owner=list(n['key']), face=n['face'],
                        shape_sha256=fill.identity(n['shape'], deadline)[0])
                   for i, n in enumerate(nodes)]))
    if force._hash(source) != source_sha or _digest(contracts) != contract_binding:
        raise ValueError('surface_supply_source_or_contract_changed')
    result = dict(scope='drill_subtracted_full_floor_surface_supply_path',
        complete=all(r['connected'] for r in rows),
        all_source_pads_surface_connected=all(r['connected'] for r in rows),
        source=str(source), source_sha256=source_sha, contracts_sha256=contract_binding,
        nets=rows, actual_child_drill_count=len(holes), work_checks=checks,
        node_count=node_count, vertices=vertices, all_child_drills_subtracted=True,
        whole_uuid_connectivity_credit=False, zone_or_inner_connectivity_credit=False,
        parent_source_binding_external_required=True, saved_receiving_required=True,
        routing_admitted=False, current_capacity_qualified=False,
        barrel_ampacity_qualified=False, pad_contact_capacity_qualified=False,
        fabrication_qualified=False, release_authority=False)
    _tick(deadline)
    return result

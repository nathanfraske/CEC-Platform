"""Finite contact-event refinement of jointly proposed support placements.

Independent aperture menus do not imply that their Cartesian product fits.
Measure all proposed poses together, then generate separating translations
from native courtyard and foreign-pad bounds. These conservative envelopes
are ordering/proposal hints, never physical, electrical or release authority.
Every result must be reconstructed from the original source and requalified.
"""
import copy
import heapq
import itertools
import math

import pcbnew
import cec_fr as fr
import cec_compound_support_candidate as compound
import cec_support_motion as motion
from cec_endpoint_via_access import separation_events


def _box(native):
    return (native.GetLeft(), native.GetTop(), native.GetRight(), native.GetBottom())


def _body(fp):
    courtyard = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
    return _box(courtyard.BBox() if courtyard.OutlineCount() else fp.GetBoundingBox(False, False))


def _signature(cells):
    return tuple((cell['target']['ref'], *(round(float(cell['candidate'].get(k, 0)), 6)
                 for k in ('dx_mm', 'dy_mm', 'rotation_delta_deg'))) for cell in cells)


def refine(board, seeds, policy, *, limit=12, max_expansions=128,
           max_depth=2, max_adjust_mm=1., margin_mm=.05, board_path=''):
    """Return a bounded, deterministic joint frontier; leave the board intact.

    Motion is always measured against the original source, not the preceding
    search node. No rotation, companion authority or branch budget is added.
    The adjustment cap is cumulative from each seed, not per search step.
    Native DRC remains mandatory even for a zero-envelope-conflict proposal.
    """
    if (not isinstance(seeds, (list, tuple)) or not 1 <= len(seeds) <= 128
            or type(limit) is not int or not 1 <= limit <= 32
            or type(max_expansions) is not int or not 1 <= max_expansions <= 512
            or type(max_depth) is not int or not 0 <= max_depth <= 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in (max_adjust_mm, margin_mm))
            or not 0 < max_adjust_mm <= 1. or not 0 <= margin_mm <= .25):
        raise ValueError('finite joint refinement bounds required')
    policy = motion.limits(**policy)
    import cec_protected_neck_pose as neck
    resolver = fr._project_netclass_resolver(board_path) if board_path else lambda _net: {}
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    originals = {ref: (pcbnew.VECTOR2I(fp.GetPosition()), fp.GetOrientationDegrees())
                 for ref, fp in footprints.items()}
    baseline = [(fp.GetReference(), tuple(fp.GetPosition()), fp.GetOrientationDegrees(), fp.IsFlipped())
                for fp in board.GetFootprints()]
    accepted, rejected = [], []
    for index, cells in enumerate(seeds):
        proof = compound.validate(board, cells, policy)
        if proof['ok']:
            contacts = [neck.capture(board, c['target'], resolver) for c in proof['cells']]
            if not all(neck.preserves(anchor, cell['candidate']) for anchor, cell in zip(contacts, cells)):
                rejected.append(dict(index=index, reason='protected_neck_owner_contact_lost')); continue
            domains = [motion.capture(board, c['target'], policy) for c in proof['cells']]
            for domain, anchors in zip(domains, contacts): domain['protected_neck_contacts'] = anchors
            accepted.append((index, copy.deepcopy(cells), proof['cells'], domains))
        else:
            rejected.append(dict(index=index, reason=proof['reason']))
    body_margin = round(margin_mm*1e6)
    pad_margin = max(body_margin, board.GetDesignSettings().m_MinClearance)
    resolve = fr._foreign_clearance_resolver(board)
    # Saved copper is an obstacle even when unlocked. A later independently
    # proved branch removal can make this conservative hint overrestrictive,
    # but attachment or a same-cell label is not permission to ignore copper.
    copper = [(str(item.m_Uuid.AsString()), item.GetNetCode(), _box(item.GetBoundingBox()),
               {layer: (item.GetEffectiveShape(layer), max(pad_margin, resolve(item, layer)))
                for layer in item.GetLayerSet().CuStack()}) for item in board.GetTracks()]

    def measure(cells, effective):
        ownership = {}
        try:
            for index, (cell, scoped) in enumerate(zip(cells, effective)):
                candidate = cell['candidate']
                angle = float(candidate.get('rotation_delta_deg', 0))
                cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                root = originals[scoped['target']['ref']][0]
                delta = pcbnew.VECTOR2I_MM(candidate.get('dx_mm', 0), candidate.get('dy_mm', 0))
                for ref in [scoped['target']['ref'], *(scoped['target'].get('companion_refs') or ())]:
                    fp = footprints[ref]; origin, orientation = originals[ref]
                    x, y = origin.x-root.x, origin.y-root.y
                    fp.SetPosition(root+delta+pcbnew.VECTOR2I(round(cosine*x+sine*y), round(-sine*x+cosine*y)))
                    fp.SetOrientationDegrees(orientation+angle)
                    ownership[ref] = index
            bodies, pads, moving_pads = [], [], []
            for ref, fp in footprints.items():
                owner = ownership.get(ref)
                bodies.append((ref, owner, fp.IsFlipped(), _body(fp)))
                for pad in fp.Pads():
                    if pad.IsOnCopperLayer():
                        pads.append((ref, owner, frozenset(pad.GetLayerSet().CuStack()),
                                     pad.GetNetCode(), _box(pad.GetBoundingBox())))
                        if owner is not None: moving_pads.append((ref, owner, pad))
            conflicts = []
            def add(a, b, gap, kind):
                if a[0] == b[0] or (a[1] is None and b[1] is None) or (a[1] is not None and a[1] == b[1]):
                    return
                left, top, right, bottom = b[-1]
                expanded = (left-gap, top-gap, right+gap, bottom+gap)
                events = separation_events(a[-1], expanded, 1000)
                if events:
                    area = (max(0, min(a[-1][2], expanded[2])-max(a[-1][0], expanded[0]))*
                            max(0, min(a[-1][3], expanded[3])-max(a[-1][1], expanded[1])))
                    conflicts.append(dict(kind=kind, refs=(a[0], b[0]), cells=(a[1], b[1]),
                                          area_nm2=area, events=events))
            for a, b in itertools.combinations(bodies, 2):
                if a[2] == b[2]: add(a, b, body_margin, 'courtyard_envelope')
            for a, b in itertools.combinations(pads, 2):
                if a[2] & b[2] and not (a[3] > 0 and a[3] == b[3]):
                    add(a, b, pad_margin, 'foreign_pad_envelope')
            for ref, owner, pad in moving_pads:
                bounds, net = _box(pad.GetBoundingBox()), pad.GetNetCode()
                shapes = {layer: (pad.GetEffectiveShape(layer), max(pad_margin, resolve(pad, layer)))
                          for layer in pad.GetLayerSet().CuStack()}
                for uid, other_net, other_box, layers in copper:
                    if net > 0 and net == other_net: continue
                    for layer, (shape, gap) in shapes.items():
                        if layer not in layers: continue
                        other_shape, other_gap = layers[layer]; clearance = max(gap, other_gap)
                        if (bounds[2]+clearance < other_box[0] or other_box[2]+clearance < bounds[0]
                                or bounds[3]+clearance < other_box[1] or other_box[3]+clearance < bounds[1]):
                            continue
                        if shape.Collide(other_shape, clearance):
                            add((ref, owner, bounds), (uid, None, other_box),
                                clearance, 'saved_copper_envelope')
                            break
            conflicts.sort(key=lambda c: (-c['area_nm2'], c['refs'], c['kind']))
            return conflicts
        finally:
            for ref in ownership:
                origin, orientation = originals[ref]
                footprints[ref].SetPosition(origin)
                footprints[ref].SetOrientationDegrees(orientation)

    queue, visited, measured = [], set(), []
    serial = itertools.count()
    def enqueue(seed_index, cells, effective, domains, seed, depth):
        signature = _signature(cells)
        if signature in visited: return
        visited.add(signature)
        faults = measure(cells, effective)
        displacement = sum(math.hypot(float(c['candidate'].get('dx_mm', 0)),
                                      float(c['candidate'].get('dy_mm', 0))) for c in cells)
        rank = (len(faults), sum(f['area_nm2'] for f in faults), displacement, signature)
        row = dict(cells=cells, seed_index=seed_index, depth=depth,
                   advisory_conflicts=len(faults),
                   advisory_kinds=sorted({fault['kind'] for fault in faults}),
                   release_authority=False)
        measured.append((rank, row))
        heapq.heappush(queue, (rank, next(serial), row, effective, domains, seed, faults))
    for index, cells, effective, domains in accepted:
        enqueue(index, cells, effective, domains, cells, 0)
    expanded = 0
    while queue and expanded < max_expansions:
        _rank, _serial, row, effective, domains, seed, faults = heapq.heappop(queue)
        if not faults or row['depth'] >= max_depth: continue
        expanded += 1
        # Contact events from the largest current conflicts, not an unbounded
        # finer grid. Both movers get a chance; stationary objects never move.
        for fault in faults[:4]:
            for side, index in enumerate(fault['cells']):
                if index is None: continue
                for x, y in fault['events']:
                    if len(measured) >= len(accepted)+max_expansions: break
                    x, y = ((-x, -y) if side else (x, y))
                    cells = copy.deepcopy(row['cells']); candidate = cells[index]['candidate']
                    candidate['dx_mm'] = round(float(candidate.get('dx_mm', 0))+x/1e6, 6)
                    candidate['dy_mm'] = round(float(candidate.get('dy_mm', 0))+y/1e6, 6)
                    origin = seed[index]['candidate']
                    if (math.hypot(candidate['dx_mm']-float(origin.get('dx_mm', 0)),
                                   candidate['dy_mm']-float(origin.get('dy_mm', 0))) > max_adjust_mm
                            or not motion.evaluate(domains[index], candidate)['ok']):
                        continue
                    if not neck.preserves(domains[index]['protected_neck_contacts'], candidate): continue
                    # A measured aperture belongs to its old pose. Do not let
                    # stale coordinates masquerade as a new native witness.
                    for key in ('endpoint_via_aperture', 'native_copper', 'stationary_partition'):
                        candidate.pop(key, None)
                    candidate['joint_pose_refinement'] = dict(kind=fault['kind'], refs=list(fault['refs']),
                        remaining_native_qualification_required=True, release_authority=False)
                    enqueue(row['seed_index'], cells, effective, domains, seed, row['depth']+1)
    assert baseline == [(fp.GetReference(), tuple(fp.GetPosition()), fp.GetOrientationDegrees(), fp.IsFlipped())
                        for fp in board.GetFootprints()]
    measured.sort(key=lambda item: item[0])
    return dict(schema=1, proposals=[row for _rank, row in measured[:limit]],
                measured=len(measured), expanded=expanded, refused_seeds=rejected,
                input_board_unchanged=True, release_authority=False,
                native_placement_and_route_admission_required=True)

"""Deterministic native zone fill, without a copper-loss tolerance.

KiCad 10.0.5's initial dependency graph tests actual outline collision, but
its different-net knockout collection tests bounding boxes. A disjoint,
higher-priority zone can therefore finish early enough to trigger a second
minimum-width prune, or finish too late. Even unchanged rounded corners can
then differ. Native priority-ordered settling makes those inputs consistent.

The first full-board fill establishes whole-board island connectivity. Two
bounded ordered passes must agree exactly before returning. Every polygon
still comes from ZONE_FILLER; no contours, rules, priorities or saved fill are
patched. Callers must still prove protected copper, clearance and connectivity.
"""
import functools
import hashlib
import time

ALGORITHM = 'native-priority-settle-v1'


class NativeFillFailed(RuntimeError):
    """The native filler returned failure, distinct from budget/identity faults."""


def _assert_unowned_refill_safe(board, *, timeout_s=2.):
    """Never silently union away explicitly preserved positive fill records.

    Normal native island polygons have disjoint interiors. Overlapping
    positive records can encode an exact source-preserving construction.
    A global unowned refill lacks the immutable source/region declaration
    needed to reconstruct those records. Refuse BEFORE any UnFill. The
    caller must use the declared native owner and independent receiving.
    This is a geometric ownership boundary, not a board/name special case.
    """
    import math
    import cec_rectilinear_copper as native
    from cec_native_fill_geometry import identity
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<=timeout_s<=10):
        raise ValueError('invalid_unowned_native_refill_deadline')
    deadline=time.monotonic()+timeout_s
    native._check_deadline(deadline)
    zones=list(board.Zones())
    if len(zones)>8192:raise RuntimeError('unowned_native_refill_zone_inventory_bound')
    vertices=0;trials=0
    for zone in zones:
        native._check_deadline(deadline)
        if zone.GetIsRuleArea() or not zone.IsFilled():continue
        for layer in zone.GetLayerSet().CuStack():
            if not zone.HasFilledPolysForLayer(layer):continue
            shape=zone.GetFilledPolysList(layer)
            if shape.OutlineCount()<2:continue
            _,n=identity(shape,deadline,max_vertices=200000-vertices);vertices+=n
            bounds=[shape.Outline(i).BBox() for i in range(shape.OutlineCount())]
            for i in range(shape.OutlineCount()):
                for j in range(i):
                    native._check_deadline(deadline)
                    trials+=1
                    if trials>131072:raise RuntimeError('unowned_native_refill_component_pair_bound')
                    if not bounds[i].Intersects(bounds[j]):continue
                    left=shape.CloneDropTriangulation();right=shape.CloneDropTriangulation()
                    for k in reversed(range(shape.OutlineCount())):
                        if k!=i:left.RemoveOutline(k)
                        if k!=j:right.RemoveOutline(k)
                    left.BooleanIntersection(right)
                    if left.OutlineCount():
                        raise RuntimeError('overlapping_native_fill_requires_declared_source_preserving_owner:'
                            +zone.m_Uuid.AsString())


def _ordered(zones):
    def compare(a, b):
        # Native ordering includes teardrops and UUID tie-breaking. Do not
        # substitute net names, board names or insertion/address order.
        if a.HigherPriority(b):
            return -1
        if b.HigherPriority(a):
            return 1
        return 0
    return sorted(zones, key=functools.cmp_to_key(compare))


def _fingerprint(zones):
    digest = hashlib.sha256()
    for zone in sorted(zones, key=lambda z: z.m_Uuid.AsString()):
        digest.update((zone.m_Uuid.AsString()+':'+str(zone.IsFilled())).encode())
        for layer in zone.GetLayerSet().Seq():
            digest.update((':'+str(layer)+':').encode())
            digest.update(zone.GetFilledPolysList(layer).Format().encode())
    return digest.hexdigest()


def _authored_nets(board, tick):
    """Literal native net identities; a filler is not net-repair authority."""
    rows={}
    def add(kind,item):
        tick();key=(kind,str(item.m_Uuid.AsString()))
        if len(rows)>=32768:raise RuntimeError('native_fill_authored_net_inventory_bound')
        if key in rows:raise RuntimeError('native_fill_ambiguous_authored_net_identity')
        rows[key]=str(item.GetNetname())
    for item in board.GetTracks():add('track',item)
    for fp in board.GetFootprints():
        for pad in fp.Pads():add('pad',pad)
    for zone in board.Zones():add('zone',zone)
    return rows


def _check_authored_nets(board, expected, tick):
    actual=_authored_nets(board,tick)
    for key in sorted(expected.keys()|actual.keys()):
        if expected.get(key)!=actual.get(key):
            raise RuntimeError('selected_native_fill_changed_authored_net_identity:'
                +':'.join(key)+':'+str(expected.get(key))+'->'+str(actual.get(key)))


def compile_selected(board, selected, *, timeout_s=10., initialize_selected=False):
    """Deterministic local native compilation, NEVER source/release receiving.

    Explicit private-zone owners need local compilation without a global
    UnFill of immutable neighboring conductors. They must subsequently prove
    their source/region/fabrication/physical contracts on the saved result.
    This low-level construction step is not permission to erase a source fill
    or save/publish a candidate without those independent proofs.

    A caller that has cleared several mutually connected planes may request
    one initial native batch for ONLY this subset. This establishes their
    shared island connectivity before the same two exact ordered passes;
    it does not refill, clear or authorize changes to neighboring zones.
    """
    import math
    import pcbnew
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<=timeout_s<=10):raise ValueError('invalid_selected_native_fill_deadline')
    if type(initialize_selected) is not bool:
        raise ValueError('invalid_selected_native_fill_initialization')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise RuntimeError('selected_native_fill_deadline')
    tick();zones=list(selected)
    if len(zones)>256:raise RuntimeError('selected_native_fill_inventory_bound')
    by_id={z.m_Uuid.AsString():z for z in board.Zones()}
    ids=[z.m_Uuid.AsString() for z in zones]
    if (len(set(ids))!=len(ids) or any(uid not in by_id for uid in ids)
            or any(z.GetIsRuleArea() or z.GetNumCorners()<3 for z in zones)):
        raise RuntimeError('explicit_actual_native_zone_subset_required')
    zones=[by_id[uid] for uid in ids]
    if not zones:return dict(stable=True,compiled_zone_count=0,initialized_selected=False,
        native_copper_received=False,release_authority=False)
    authored=_authored_nets(board,tick)
    if initialize_selected:
        tick();batch=pcbnew.ZONES()
        for zone in zones:batch.append(zone)
        if not pcbnew.ZONE_FILLER(board).Fill(batch):
            raise NativeFillFailed('selected native initial zone fill failed')
        _check_authored_nets(board,authored,tick)
    ordered=_ordered(zones);previous=None
    for _ in range(2):
        for zone in ordered:
            tick();batch=pcbnew.ZONES();batch.append(zone)
            if not pcbnew.ZONE_FILLER(board).Fill(batch):
                raise NativeFillFailed('selected native zone fill failed:'+zone.m_Uuid.AsString())
            _check_authored_nets(board,authored,tick)
        board.BuildConnectivity();_check_authored_nets(board,authored,tick)
        current=_fingerprint(zones)
        stable=previous==current;previous=current
    if not stable:raise RuntimeError('selected native zone fill did not converge in two passes')
    return dict(algorithm=ALGORITHM,stable=True,ordered_passes=2,compiled_zone_count=len(zones),
        initialized_selected=initialize_selected,fingerprint=current,
        native_copper_received=False,release_authority=False)


def fill_with_report(board):
    """Fill in memory or raise; never save an incomplete/nonconverged result."""
    import pcbnew
    started = time.monotonic()
    _assert_unowned_refill_safe(board)
    zones = [z for z in board.Zones()
             if not z.GetIsRuleArea() and z.GetNumCorners() > 2]
    result = dict(algorithm=ALGORITHM, native_version=pcbnew.Version(),
                  zone_count=len(zones), ordered_passes=0,
                  stable=False, tolerance_nm=0, pass_fingerprints=[])
    if not zones:
        result.update(stable=True, wall_s=0.)
        return result
    # Preserve native global island/connectivity semantics before settling.
    # Fill itself clears the selected zones. Explicitly unfill all board zones
    # also prevents stale polygons on a newly degenerate/rule-area zone.
    for zone in board.Zones():
        zone.UnFill()
    if not pcbnew.ZONE_FILLER(board).Fill(board.Zones()):
        raise RuntimeError('native full-board zone fill failed')
    ordered = _ordered(zones)
    previous = None
    for index in range(2):
        for zone in ordered:
            batch = pcbnew.ZONES()
            batch.append(zone)
            if not pcbnew.ZONE_FILLER(board).Fill(batch):
                raise RuntimeError('native priority zone fill failed: '+zone.m_Uuid.AsString())
        board.BuildConnectivity()
        current = _fingerprint(zones)
        result['ordered_passes'] = index+1
        result['pass_fingerprints'].append(current)
        result['stable'] = previous == current
        previous = current
    if not result['stable']:
        raise RuntimeError('native priority zone fill did not converge in two passes: '
                           + ' -> '.join(result['pass_fingerprints']))
    result.update(fingerprint=current, wall_s=round(time.monotonic()-started, 6))
    return result


def fill(board):
    """Boolean-compatible replacement for native Fill(board.Zones())."""
    fill_with_report(board)
    return True

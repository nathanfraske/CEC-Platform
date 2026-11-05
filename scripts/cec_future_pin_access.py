"""Preserve non-pair terminal access while routing a priority pair.

A pair owns its signal corridor, not every via column under its packages.
Reserve only a native-legal, fully contained POFV at a scarce, still-isolated
non-pair SMD terminal. This is a prospective placement/routing contract, not
new copper, ampacity qualification, or proof that all alternative paths fail.
"""
import math
import time

import pcbnew
import cec_fab_profile as fab
import cec_fr as fr


def _attached_escape(board, pad, *, cache=None):
    """A same-net native copper path needs no hypothetical new via.

    Do not call BuildConnectivity here: KiCad can propagate a touching pad's
    net onto a wrongly assigned track, mutating the very short under review.
    Walk only same-net exact shape contacts to another pad or a real barrel.
    A dead stub, foreign short or stale connectivity cache is not an escape.
    The cache belongs to one immutable planning/recheck invocation only.
    """
    code=pad.GetNetCode()
    terminal_key=lambda item:(item.GetParentFootprint().GetReference(),str(item.GetNumber()),
                              item.GetPosition().x,item.GetPosition().y)
    cache={} if cache is None else cache
    def shape_row(item):
        return item,{layer:item.GetEffectiveShape(layer) for layer in item.GetLayerSet().CuStack()}
    if code not in cache:
        items=[other for fp in board.GetFootprints() for other in fp.Pads()
               if other.GetNetCode()==code and other.IsOnCopperLayer()
               and other.GetAttribute()!=pcbnew.PAD_ATTRIB_NPTH]
        items.extend(item for item in board.GetTracks() if item.GetNetCode()==code
                     and item.GetClass() in ('PCB_TRACK','PCB_ARC','PCB_VIA'))
        cache[code]=[shape_row(item) for item in items]
    rows=cache[code]; pending=[shape_row(pad)];seen=set()
    for _ in range(4096):
        if not pending:
            break
        _item,shapes=pending.pop()
        for index,(other,other_shapes) in enumerate(rows):
            if index in seen:
                continue
            if other.GetClass()=='PAD' and terminal_key(other)==terminal_key(pad):
                seen.add(index);continue
            layers=shapes.keys() & other_shapes.keys()
            if not any(shapes[layer].BBox().Intersects(other_shapes[layer].BBox())
                       and shapes[layer].Collide(other_shapes[layer],0) for layer in layers):
                continue
            if other.GetClass() in ('PAD','PCB_VIA'):
                return True
            seen.add(index);pending.append((other,other_shapes))
    return False


def plan(board, pair, *, board_path='', excluded_nets=(), escape_mm=1.25,
         max_free_rays=2, max_pads=256, deadline_monotonic=None):
    """Bounded geometry-derived reservations; no package/refdes allowlist.

    Through-hole pads already expose their real layers and are not assigned
    redundant barrels. One-terminal/no-connect nets have no external route
    obligation. Existing copper remains authoritative and is never removed.
    """
    if (type(max_pads) is not int or not 1 <= max_pads <= 4096
            or type(max_free_rays) is not int or not 0 <= max_free_rays <= 8
            or type(escape_mm) not in (int, float)
            or not math.isfinite(escape_mm) or not 0 < escape_mm <= 5
            or (deadline_monotonic is not None and
                (type(deadline_monotonic) not in (int,float)
                 or not math.isfinite(deadline_monotonic)))):
        raise ValueError('future pin-access search must be finite and bounded')
    report = dict(schema=1, complete=True, ports=[], unavailable=[],
        reservations=[], checked=0, skipped_connected=0, release_authority=False,
        no_path_proof=False, scope='isolated-nonpair-pins-on-pair-packages')
    profile_name = fab.board_profile_name(board)
    # Reserve columns that can actually be created on THIS native board.
    # The profile-only menu can be smaller than its hard via/drill/ring floors;
    # rejecting only those sizes falsely reports no future pin access even
    # when the independently clamped board-legal column fits. This remains
    # geometry-only planning, never current, local-rule or fabrication credit.
    geometries = fab.local_pofv_geometry_candidates(fab.PROFILES.get(profile_name),board=board)
    if not geometries:
        report['not_applicable'] = 'no_declared_pofv_process'
        return report
    pair_nets = {pair['p'], pair['n']}
    excluded = pair_nets | set(excluded_nets)
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
            if pad.IsOnCopperLayer() and pad.GetNetCode() > 0]
    terminal_counts = {}
    for pad in pads:
        terminal_counts[pad.GetNetCode()] = terminal_counts.get(pad.GetNetCode(), 0)+1
    members = {fp.GetReference() for fp in board.GetFootprints()
               if pair_nets.issubset({pad.GetNetname() for pad in fp.Pads()})}
    candidates = sorted((pad for pad in pads
        if pad.GetParentFootprint().GetReference() in members
        and pad.GetNetname() not in excluded
        and terminal_counts[pad.GetNetCode()] > 1
        and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not pad.HasHole()),
        key=lambda pad: (pad.GetParentFootprint().GetReference(), str(pad.GetNumber()),
                         pad.GetPosition().x, pad.GetPosition().y, pad.m_Uuid.AsString()))
    resolver = fr._project_netclass_resolver(board_path) if board_path else lambda net: {}
    minimum = int(board.GetDesignSettings().m_TrackMinWidth)
    via_cache, ray_cache, attachment_cache = {}, {}, {}
    holes = fr._via_hole_snapshot(board)
    for pad in candidates:
        if (report['checked'] >= max_pads
                or (deadline_monotonic is not None and time.monotonic() >= deadline_monotonic)):
            report.update(complete=False, stop='future_pin_access_budget_exhausted')
            break
        if _attached_escape(board, pad, cache=attachment_cache):
            report['skipped_connected'] += 1
            continue
        report['checked'] += 1
        pos = pad.GetPosition(); code = pad.GetNetCode()
        identity = dict(ref=pad.GetParentFootprint().GetReference(), pad=str(pad.GetNumber()),
            uuid=pad.m_Uuid.AsString(), net=pad.GetNetname(),
            at_mm=[pos.x/1e6, pos.y/1e6])
        spec = resolver(pad.GetNetname()) or {}
        width = max(minimum, pcbnew.FromMM(float(spec.get('track_width') or .2)))
        clearance = pcbnew.FromMM(max(board.GetDesignSettings().m_MinClearance/1e6,
            float(spec.get('clearance') or .2),
            float(pair.get('clearance') or .2)))
        escape = fr._pad_local_escape(pad, width, clearance, minimum)
        clear_rays = []
        for layer in pad.GetLayerSet().CuStack():
            shapes = fr._foreign_shape_indexes(board, layer, {code}, cache=ray_cache)
            for direction, dx, dy in (('E',1,0),('NE',1,-1),('N',0,-1),('NW',-1,-1),
                                      ('W',-1,0),('SW',-1,1),('S',0,1),('SE',1,1)):
                scale = escape_mm*1e6/math.hypot(dx,dy)
                end = pcbnew.VECTOR2I(pos.x+round(dx*scale),pos.y+round(dy*scale))
                legs = fr._profiled_lastmile_path([pos,end],width,start_escape=escape)
                if legs and all(fr._edge_leg_clear(board,a,b,w//2)
                        and fr._snapshot_foreign_clear(a,b,w,clearance,*shapes)
                        for a,b,w in legs):
                    clear_rays.append(dict(layer=board.GetLayerName(layer),direction=direction))
        if len(clear_rays) > max_free_rays:
            continue
        reasons = {}
        for diameter, drill in geometries:
            radius = pcbnew.FromMM(diameter)//2
            if not fab._pad_contains_circle(pad,pos,radius):
                continue
            if (not fr._edge_leg_clear(board,pos,pos,radius)
                    or not fr._via_spot_clear(board,pos,2*radius,clearance,{code},
                        drill_nm=pcbnew.FromMM(drill),net_code=code,foreign_cache=via_cache,
                        _via_holes=holes,refusal_counts=reasons)):
                continue
            port = dict(identity, diameter_mm=diameter, drill_mm=drill,
                clearance_mm=clearance/1e6, clear_rays=clear_rays,
                basis='native_guarded_contained_pofv_column')
            report['ports'].append(port)
            reach = diameter/2+clearance/1e6
            x,y = identity['at_mm']
            # A through barrel occupies every layer, including future pair
            # portals. Five-field reservations are deliberately stack-wide.
            report['reservations'].append((x-reach,y-reach,x+reach,y+reach,
                'future-pin:%s:%s' % (identity['ref'],identity['pad'])))
            break
        else:
            report['unavailable'].append(dict(identity, clear_rays=clear_rays,
                via_refusal_causes=reasons, conclusion='no_sampled_port_not_no_path'))
    return report


def preserve(board, planned):
    """Independently recheck prospective columns before locking new copper."""
    if not planned.get('complete'):
        return dict(ok=False, reason='incomplete_future_pin_access_plan', losses=[])
    lookup = {(fp.GetReference(),str(pad.GetNumber()),pad.m_Uuid.AsString()):pad
              for fp in board.GetFootprints() for pad in fp.Pads()}
    losses, cache, attachment_cache = [], {}, {}
    holes = fr._via_hole_snapshot(board)
    for port in planned.get('ports', ()):
        pad = lookup.get((port['ref'],port['pad'],port['uuid']))
        if (pad is None or pad.GetNetname()!=port['net']
                or [pad.GetPosition().x/1e6,pad.GetPosition().y/1e6]!=port['at_mm']):
            losses.append(dict(port,reason='future_pin_identity_changed'))
            continue
        if _attached_escape(board,pad,cache=attachment_cache):
            continue
        evidence = {}
        if not fr._via_spot_clear(board,pad.GetPosition(),pcbnew.FromMM(port['diameter_mm']),
                pcbnew.FromMM(port['clearance_mm']),{pad.GetNetCode()},
                drill_nm=pcbnew.FromMM(port['drill_mm']),net_code=pad.GetNetCode(),
                foreign_cache=cache,_via_holes=holes,report=evidence):
            losses.append(dict(port,reason='future_pin_via_column_consumed',blockage=evidence))
    return dict(ok=not losses, losses=losses, checked=len(planned.get('ports', ())),
        release_authority=False, no_path_proof=False)


def replacement_witness(board_path, contract, pair, target_nets, *,
                        max_pair_items=256, deadline_monotonic=None):
    """Native counterfactual offer for one *already qualified* owned pair.

    No caller-provided lost-port report is trusted. Reload the immutable source,
    remove only the closed signal scope in memory, find an actual legal column,
    then reproduce its obstruction against the untouched source. This is not
    replacement authority; an independent transaction must prove the new pair,
    target connectivity, every retained item and all physical/power obligations.
    """
    import cec_priority_dependency as dependency
    from cec_local_copper_cell import copper_inventory
    from cec_native_items import discard_items
    if type(max_pair_items) is not int or not 1 <= max_pair_items <= 4096:
        raise ValueError('pair replacement inventory must be bounded')
    result = dict(ok=False, release_authority=False, no_path_proof=False)
    scope = dependency.pair_scope_plan(contract, {pair['p'], pair['n']}, (), max_pairs=1)
    expected = (pair['name'], pair['p'], pair['n'])
    if (not scope['ok'] or [(p['name'],p['p'],p['n']) for p in scope.get('pairs',())] != [expected]):
        return dict(result, reason='pair_is_not_an_independently_qualified_closed_scope')
    original = pcbnew.LoadBoard(str(board_path))
    board = pcbnew.LoadBoard(str(board_path))
    before = copper_inventory(original)
    selected = [item for item in board.GetTracks() if item.GetNetname() in scope['nets']]
    removed = {item.m_Uuid.AsString() for item in selected}
    if not 1 <= len(removed) <= max_pair_items:
        return dict(result, reason='outside_bounded_complete_pair_inventory')
    discard_items(board, selected)
    del selected
    if copper_inventory(board) != {uid:row for uid,row in before.items() if uid not in removed}:
        raise ValueError('counterfactual changed non-pair copper')
    import cec_precision_route as precision
    excluded = {net for declared in precision.derive_coupled_pairs(str(board_path),board=board)
                for net in (declared['p'],declared['n'])}
    planned = plan(board,pair,board_path=str(board_path),excluded_nets=excluded,
                   deadline_monotonic=deadline_monotonic)
    if not planned['complete']:
        return dict(result, reason='future_pin_access_budget_exhausted', plan=planned)
    planned['ports'] = [p for p in planned['ports'] if p['net'] in set(target_nets)]
    # Reservations in this evidence-only plan are not used by the router; its
    # normal production entry independently replans all pin obligations.
    lost = preserve(original, planned)
    losses = lost['losses']
    blockers = [row for port in losses for row in port.get('blockage',{}).get('blockers',())]
    if (not losses or not blockers
            or any(p.get('reason')!='future_pin_via_column_consumed'
                   or p.get('blockage',{}).get('reason')!='foreign copper excludes via land'
                   for p in losses)
            or any(row.get('uuid') not in removed or row.get('net') not in scope['nets']
                   for row in blockers)):
        return dict(result, reason='no_typed_pair_owned_pin_obstruction', original_replay=lost)
    if copper_inventory(original) != before:
        raise ValueError('pin-access witness mutated native source copper')
    scope['blocking_uuids'] = sorted({row['uuid'] for row in blockers})
    return dict(result, ok=True, reason='native_pair_owned_pin_column_conflict',
        scope=scope, losses=losses, removed_pair_uuids=sorted(removed),
        target_nets=sorted({p['net'] for p in losses}))

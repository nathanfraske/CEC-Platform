"""Bounded full-load reconstruction of an explicitly selected thin inner path.

Use the actual old corridor as a guide, widen every new stroke to its real
layer requirement, and reroute a blocked suffix with the existing guarded
router. No board/refdes/coordinate rule, layer sharing, via, pour or placement
change is permitted. Selection is not admission: saved rated-branch, native,
current, field and Kelvin receivers remain mandatory.
"""
import math
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_native_current_capture as capture
import cec_native_rule_areas as rules
import cec_pair_local_reference_refinement as chain
import cec_rated_branch_repair as rated
import cec_route_quality as quality
from cec_native_items import discard_items


PARAMETERS = dict(allow_rated_layer_bridges=True,
    allow_rated_source_inner_layers=True, repair_undersized_source=True,
    repair_aggregate_current_domain=True, max_source_width_mm=1.,
    max_replacement_width_mm=5., max_source_track_mm=32., max_retired_tracks=32)


def _clean(points):
    import cec_source_guided_ordinary_detour as guides
    points = guides._clean(points)
    guides.length_terms(points)
    return points


def _bevel(legs, clear, deadline):
    """Proposed geometry only; every changed full-width capsule must clear."""
    legs = quality.guarded_corner_shortcuts(legs, clear, deadline_monotonic=deadline)
    points = _clean([list(legs[0][0]), *[list(z) for _, z, _ in legs]])
    width = legs[0][2]; out = [points[0]]
    for a, b, c in zip(points, points[1:], points[2:]):
        if time.monotonic() >= deadline:
            raise ValueError('aggregate_path_proposed_bevel_deadline')
        u = [b[k]-a[k] for k in (0, 1)]; v = [c[k]-b[k] for k in (0, 1)]
        if sum(x*y for x, y in zip(u, v)) != 0:
            out.append(b); continue
        distance = min(max(250000, width), max(map(abs, u))//3, max(map(abs, v))//3)
        if distance < 20000:
            out.append(b); continue
        unit = lambda d: [(x > 0)-(x < 0) for x in d]
        first = [b[k]-distance*unit(u)[k] for k in (0, 1)]
        last = [b[k]+distance*unit(v)[k] for k in (0, 1)]
        trial = [out[-1], first, last, c]
        if all(clear(pcbnew.VECTOR2I(*x), pcbnew.VECTOR2I(*z), width)
                for x, z in zip(trial, trial[1:])):
            out.extend((first, last))
        else:
            out.append(b)
    return _clean([*out, points[-1]])


def construct(board, source, *, board_hint, retired_track_uuids,
              allow_locked_track_uuids=(), timeout_s=10.):
    """Mutate only a caller-owned private board after a complete guarded plan.

    All old cut ports, including any retained side tap, must subsequently
    replay in the independent saved receiver. A blocked/branched/noncanonical
    source or exhausted search refuses instead of inventing a shortcut.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_aggregate_path_search_required')
    ids = rated.ordinary._ids(retired_track_uuids, 'aggregate_path_cut', 32)
    allowed = rated.ordinary._ids(allow_locked_track_uuids, 'aggregate_path_locked_cut', 32)
    if not ids or not allowed <= ids:
        raise ValueError('explicit_nonempty_aggregate_path_scope_required')
    proposal = rated.plan(board, source, board_hint=board_hint,
        retired_track_uuids=sorted(ids), **{k:v for k,v in PARAMETERS.items()
            if k not in ('allow_rated_layer_bridges', 'max_replacement_width_mm')})
    live = {force._uid(t):t for t in board.GetTracks()}; cut = [live[u] for u in sorted(ids)]
    if (len({(str(t.GetNetname()), int(t.GetLayer()), t.GetWidth()) for t in cut}) != 1
            or any(t.IsLocked() and force._uid(t) not in allowed for t in cut)):
        raise ValueError('uniform_exact_source_path_and_explicit_lock_scope_required')
    points = _clean([list(p) for p in chain._chain(cut)])
    if len(set(map(tuple, points))) != len(points):
        raise ValueError('noncyclic_linear_aggregate_source_path_required')
    net = str(cut[0].GetNetname()); layer = int(cut[0].GetLayer()); nc = cut[0].GetNetCode()
    import cec_full_current_planar_reflow as full
    width = max(t.GetWidth() for t in cut)
    width = max(width, full._source_width_floor(board, source, proposal['contracts'][net], layer))
    spec = fr._project_netclass_resolver(str(source), board=board)(net) or {}
    gap = max(board.GetDesignSettings().m_MinClearance, math.ceil(float(spec.get('clearance') or 0)*1e6))
    deadline = time.monotonic()+timeout_s
    zones, other = fr._foreign_shape_indexes(board, layer, {nc})
    forbidden = [r['shape'] for r in rules.areas(board, 'tracks') if layer in r['layers']]
    guard = capture.Guard(board, source, net=net, board_hint=board_hint, timeout_s=timeout_s)

    def clear(a, z, w):
        return bool(time.monotonic() < deadline
            and fr._edge_leg_clear(board, a, z, (w+1)//2)
            and fr._snapshot_foreign_clear(a, z, w, gap, zones, other)
            and not any(p.Collide(pcbnew.SHAPE_SEGMENT(a, z, w), 0) for p in forbidden)
            and guard(tuple(a), tuple(z), w, layer))

    legs = []; diagnostics = {}
    for a, z in zip(points, points[1:]):
        start, end = pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*z)
        if clear(start, end, width):
            legs.append((start, end, width)); continue
        tail = fr._guarded_profiled_lastmile_legs(board, start, pcbnew.VECTOR2I(*points[-1]),
            width, layer, gap, nc, lambda x,y,h: clear(x,y,width), allow_maze=True,
            maze_margin_mm=4., deadline_monotonic=deadline, run_guard=clear,
            refine_maze=True, refinement_grids_mm=(.5, .25, .1),
            endpoint_detail_grid_mm=.2, search_diagnostics=diagnostics, compact_phase_jogs=True)
        if tail is None:
            raise ValueError('bounded_full_width_aggregate_suffix_search_refused')
        legs.extend(tail); break
    if not legs:
        raise ValueError('actual_full_width_aggregate_replacement_required')
    replacement = _bevel(legs, clear, deadline)
    if replacement[0] != points[0] or replacement[-1] != points[-1]:
        raise ValueError('original_aggregate_source_ports_must_stay_fixed')
    if (len(replacement) > 65 or not all(clear(pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*z), width)
            for a,z in zip(replacement,replacement[1:]))):
        raise ValueError('complete_native_full_width_aggregate_path_required')
    rows = [dict(net=net, layer=layer, width_nm=width, start_nm=a, end_nm=z)
            for a,z in zip(replacement,replacement[1:])]
    # Retired strokes are not retained neighbors. Check the constructive
    # join against a separate exact source-minus-cut board, never against
    # the soon-to-be-removed old path or a newly accepted baseline.
    trial = pcbnew.LoadBoard(str(source))
    discard_items(trial, [t for t in trial.GetTracks() if force._uid(t) in ids])
    craft = quality.assess_proposed_route(trial, rows, deadline=deadline, max_proposed=64)
    if not craft['ok'] or not craft['complete']:
        raise ValueError('aggregate_replacement_native_craft_refused')
    incoming = []
    for a,z in zip(replacement,replacement[1:]):
        t = cut[0].Duplicate(); t.m_Uuid.Clone(pcbnew.KIID())
        t.SetStart(pcbnew.VECTOR2I(*a)); t.SetEnd(pcbnew.VECTOR2I(*z)); t.SetWidth(width)
        incoming.append(t)
    original_length_mm = sum(t.GetLength() for t in cut)/1e6
    discard_items(board, cut)
    for t in incoming: board.Add(t)
    return dict(source_proposal=proposal, points_nm=replacement, width_nm=width,
        layer_id=layer, net=net, retired_track_uuids=sorted(ids),
        added_native_uuids=sorted(force._uid(t) for t in incoming),
        source_track_length_mm=original_length_mm,
        replacement_track_length_mm=sum(t.GetLength() for t in incoming)/1e6,
        native_search_diagnostics=diagnostics, new_vias=0, new_holes=0,
        requires_independent_saved_receiving=True, release_authority=False)

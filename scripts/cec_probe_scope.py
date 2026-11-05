"""Comparable critical-route screens across explicitly bounded probe scopes."""


def affected_pairs(pairs, net_refs, moved_refs, refused_names):
    """Include refused pairs plus both sides of any moved series component.

    This is endpoint dependency closure, not proof that unrelated routes cannot
    be obstructed. Complete finalist authority still rechecks every pair.
    """
    moved = set(moved_refs)
    selected = set(refused_names)
    for pair in pairs:
        refs = set(net_refs.get(pair['p'], ())) | set(net_refs.get(pair['n'], ()))
        if moved & refs:
            selected.add(str(pair['name']))
    return tuple(sorted(selected)) or None


def measured_pair_nets(pairs, names):
    selected = None if names is None else set(names)
    return sorted({pair[member] for pair in pairs for member in ('p', 'n')
                   if selected is None or pair['name'] in selected})


def preserve_unmeasured(baseline, measured, *, pair_names, measured_nets=()):
    """Carry unmeasured failures; a missing category is not an improvement.

    Both inputs are compact placement evidence. ``None`` means a full pair
    probe; an empty collection means Kelvin only. Unknown/truncated baseline
    failures remain conservatively counted in partial probes.
    """
    out = dict(measured)
    carried_pairs, carried_quality, carried_edges = 0, 0, 0
    if pair_names is not None:
        names, nets = set(pair_names), set(measured_nets)
        pair_rows = list(baseline.get('critical_pair_refused') or ())
        outside = [row for row in pair_rows if not row.get('name') or row['name'] not in names]
        missing_pairs = max(0, int(baseline.get('critical_pair_refused_count', 0) or 0) - len(pair_rows))
        carried_pairs = len(outside) + missing_pairs
        def edges(row):
            if row.get('remaining_edge_count') is not None:
                return max(0, int(row['remaining_edge_count']))
            return max(1, len(row.get('endpoint_stations') or ()) - 1)
        carried_edges = sum(edges(row) for row in outside) + missing_pairs
        # Preserve aggregate-only legacy edge evidence as well.
        if missing_pairs:
            carried_edges = max(carried_edges,
                int(baseline.get('critical_pair_remaining_edge_count', 0) or 0)
                - sum(edges(row) for row in pair_rows if row not in outside))
        quality_rows = list(baseline.get('critical_route_quality_refused') or ())
        carried_quality = sum(not row.get('net') or row['net'] not in nets for row in quality_rows)
        carried_quality += max(0, int(baseline.get('critical_route_quality_refused_count', 0) or 0)
                               - len(quality_rows))
    out['critical_pair_refused_count'] = int(measured.get('critical_pair_refused_count', 0) or 0) + carried_pairs
    out['critical_pair_remaining_edge_count'] = int(measured.get('critical_pair_remaining_edge_count', 0) or 0) + carried_edges
    out['critical_route_quality_refused_count'] = int(measured.get('critical_route_quality_refused_count', 0) or 0) + carried_quality
    out['critical_route_refused_count'] = int(measured.get('critical_route_refused_count', 0) or 0) + carried_pairs + carried_quality
    out['probe_scope'] = dict(full_pairs=pair_names is None,
        pair_names=None if pair_names is None else sorted(pair_names),
        measured_nets=sorted(measured_nets), carried_pair_refusals=carried_pairs,
        carried_quality_refusals=carried_quality, carried_pair_edges=carried_edges,
        complete_board_authority=False)
    return out

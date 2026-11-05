"""Normalize uncommitted conductors without editing the native incumbent.

Only duplicate centreline coverage and virtual dead-end branches are removed.
Real contacts, layer transitions, widths and terminal-to-terminal paths stay
fixed. This is not current, connectivity, clearance or release qualification.
"""
import math
from collections import defaultdict


def normalize_terminal_paths(plan, *, anchored_at, fixed_points=(), layer_key=str):
    """Return ``[(original_index, segment), ...]`` and a bounded receipt.

The caller owns a single-net proposal, maps aliases to real layer identities,
and supplies native contact tests. Explicit required array/contact points are
split into the graph where they lie on a conductor. Under-anchored components
and closed cycles are kept, never hidden by erasing an unfinished power path.
"""
    from shapely.geometry import LineString, Point
    rows = [tuple(s) for s in plan]
    fixed = [tuple(p) for p in fixed_points]
    if (any(len(s) != 6 or not all(math.isfinite(float(v)) for v in s[:5])
            or s[4] <= 0 for s in rows)
            or any(len(p) != 3 or not all(math.isfinite(float(v)) for v in p[:2])
                   for p in fixed)):
        raise ValueError('invalid conductor proposal')
    receipt = dict(schema=1, input_segments=len(rows), release_authority=False,
                   removed_virtual_length_mm=0., trimmed_segments=0)
    if len(rows) > 512 or len(fixed) > 4096:
        return list(enumerate(rows)), dict(receipt, reason='normalization_size_bound')
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        if math.dist(row[:2], row[2:4]) > 1e-8:
            groups[layer_key(row[5])].append((index, row))
    pieces = {}
    declared = set()
    for layer, group in groups.items():
        points = {p for _, s in group for p in (s[:2], s[2:4])}
        explicit = {p[:2] for p in fixed if layer_key(p[2]) == layer}
        points.update(explicit)
        lines = [LineString((s[:2], s[2:4])) for _, s in group]
        for i, a in enumerate(lines):
            for b in lines[i+1:]:
                cross = a.intersection(b)
                if cross.geom_type == 'Point':
                    points.add((cross.x, cross.y))
        for (index, row), line in zip(group, lines):
            cuts = sorted({p for p in points if line.distance(Point(p)) <= 1e-8},
                          key=lambda p: line.project(Point(p)))
            for a, b in zip(cuts, cuts[1:]):
                a = tuple(round(v, 6) for v in a)
                b = tuple(round(v, 6) for v in b)
                if a == b:
                    continue
                ends = tuple(sorted((a, b)))
                key = (layer, ends)
                # Coincident copper keeps the widest original declaration.
                if key not in pieces or pieces[key][1][4] < row[4]:
                    pieces[key] = (index, (*ends[0], *ends[1], row[4], row[5]))
            declared.update((layer, tuple(round(v, 6) for v in p))
                            for p in explicit if line.distance(Point(p)) <= 1e-8)
    if len(pieces) > 4096:
        return list(enumerate(rows)), dict(receipt, reason='normalization_size_bound')
    adjacency = defaultdict(set)
    layers_at = defaultdict(set)
    for key in pieces:
        layer, ends = key
        for point in ends:
            adjacency[(layer, point)].add(key)
            layers_at[point].add(layer)
    protected = set(declared)
    for (layer, point), edges in adjacency.items():
        tag = pieces[next(iter(edges))][1][5]
        if len(layers_at[point]) > 1 or anchored_at(point, tag):
            protected.add((layer, point))
    active = set(pieces)
    remaining = set(adjacency)
    while remaining:
        component, frontier = set(), {next(iter(remaining))}
        while frontier:
            component.update(frontier)
            neighbors = {(layer, p) for node in frontier for layer, ends in adjacency[node]
                         for p in ends}
            frontier = neighbors - component
        remaining -= component
        # Do not make missing terminals disappear with an unanchored graph.
        if len(component & protected) < 2:
            continue
        queue = [node for node in component if node not in protected
                 and len(adjacency[node] & active) == 1]
        while queue:
            node = queue.pop()
            edges = adjacency[node] & active
            if node in protected or len(edges) != 1:
                continue
            edge = next(iter(edges))
            active.remove(edge)
            layer, ends = edge
            other = (layer, ends[1] if node[1] == ends[0] else ends[0])
            queue.append(other)
    removed = set(pieces) - active
    receipt.update(reason='proposal_only', normalized_segments=len(pieces),
        output_segments=len(active), trimmed_segments=len(removed),
        removed_virtual_length_mm=sum(math.dist(*key[1]) for key in removed),
        protected_vertices=len(protected))
    return [pieces[key] for key in sorted(active)], receipt

"""Finite native-reference-aware proposals for the one-grid endpoint owner.

This adds proposal search, not permission or a tolerance. The original exact
reference-deficit and full saved receiving gates are called without changes.
"""
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_native_grid_projection as grid
import cec_pair_axis_miter as reference


class GridSearchRefusal(ValueError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.grid_search_attempts = attempts


def plan(source, *, board_hint, allow_locked_source=False):
    source = Path(source).resolve()
    proposal = grid.plan(source, board_hint=board_hint, allow_locked_source=allow_locked_source)
    parent, components, _ = grid.inventory(source)
    pairs = reference.owner.precision.derive_coupled_pairs(str(source), board=parent)
    grid.require(len(components) <= 16, 'finite_reference_aware_grid_component_portfolio_required')
    attempts = []
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    for index, record in enumerate(proposal['components']):
        affected = [pair for pair in pairs if record['net'] in (pair['p'], pair['n'])]
        selected = None
        strategies = [(None, None), *[(direction, None) for direction in directions]]
        nearby = {i for edge in record['edges'] if grid.heading(*[record['points_nm'][i] for i in edge])[2] for i in edge}
        for _ in range(2):
            nearby.update(i for edge in record['edges'] if set(edge) & nearby for i in edge)
        selected_vertices = [i for i in sorted(nearby) if i not in record['fixed_vertex_indices']][:6]
        strategies += [(direction, vertex) for vertex in selected_vertices for direction in directions]
        grid.require(len(strategies) <= 57, 'explicit_finite_grid_reference_strategy_bound')
        for direction, vertex in strategies:
            row = dict(component=index, preferred_direction=direction, preferred_vertex=vertex, accepted=False)
            attempts.append(row)
            try:
                points = grid.project(record['edges'], record['points_nm'], record['fixed_vertex_indices'],
                    preferred_direction=direction, preferred_vertex=vertex)
                child = pcbnew.LoadBoard(str(source))
                live = {force._uid(t): t for t in child.GetTracks()}
                for uid, edge in zip(record['track_uuids'], record['edges']):
                    a, z = [points[i] for i in edge]
                    live[uid].SetStart(pcbnew.VECTOR2I(*a)); live[uid].SetEnd(pcbnew.VECTOR2I(*z))
                proofs = []
                for pair in affected:
                    tracks = [[t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK'
                        and t.GetNetname() in (pair['p'], pair['n']) and int(t.GetLayer()) == record['layer']]
                        for b in (parent, child)]
                    proof = reference._reference(parent, child, *tracks, board_hint=board_hint,
                        allow_existing_non_signal_face=True)
                    proofs.append(proof)
                selected = points
                row.update(accepted=True, original_unchanged_reference_proofs=proofs)
                break
            except ValueError as exc:
                row['refusal'] = str(exc)
        if selected is None:
            raise GridSearchRefusal('finite_source_reference_safe_grid_projection_unproved:'+str(index), attempts)
        record['projected_points_nm'] = selected
    return proposal, dict(attempts=attempts, every_source_reference_gate_unchanged=True,
        source_sha256=force._hash(source), authority_sha256=force._hash(Path(__file__)),
        floating_solver_is_proposal_only=True, numeric_or_area_waiver_used=False,
        pair_or_fab_qualified=False, release_authority=False)

"""Bounded source-bound native macro pilot; poses/consents supplied as data.

This is an unadmitted experiment driver, not an automatic source promotion.
Every candidate still requires the full independent saved receiving suite.
"""
import argparse
import json
from pathlib import Path
import time
from materialize_macro import materialize

from cec_pipeline.native import _native
p, _ = _native()
from cec_pipeline import cells, construction
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_additive_route_receiving as additive
import cec_force_current as force
import cec_fr as fr
from native_pair_v13 import soften


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--sha256', required=True)
    ap.add_argument('--board-hint', required=True)
    ap.add_argument('--operation', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--authored-request-routes', type=Path)
    ap.add_argument('--preview', action='store_true')
    args = ap.parse_args()
    source = args.source.resolve(); destination = args.output.resolve()
    if force._hash(source) != args.sha256: raise ValueError('exact_source_hash_required')
    if destination.exists(): raise ValueError('fresh_experiment_directory_required')
    op = json.loads(args.operation.read_text())
    if (op.get('kind') != 'place_cell' or op.get('native_macro') is not True
            or op.get('routes') or op.get('vias')):
        raise ValueError('explicit_native_poses_without_preexisting_route_additions_required')
    destination.mkdir(parents=True)
    def report(name, value):
        (destination / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')
    if args.preview:
        result = cells.preview(source, op, args.board_hint)
        report('preview', result)
        print(json.dumps({k: result.get(k) for k in ('required_locked_cut_uuids',
            'required_locked_transport_uuids', 'ok', 'complete')})); return
    parent = p.LoadBoard(str(source))
    frame, packet, transported = cells.compile_macro(parent, op, args.board_hint)
    report('packet', packet)
    authored = (json.loads(args.authored_request_routes.read_text())
        if args.authored_request_routes else {})
    if not isinstance(authored, dict) or not set(authored) <= set(packet['requests']):
        raise ValueError('authored_routes_must_address_fresh_requests')
    prefill = compiler.pre_refill_barrel_screen(frame, packet, timeout_s=10.)
    additive._ground_refill(frame)
    pose = compiler.native_pose_screen(parent, frame, packet, timeout_s=10., phase_timeouts_s=(10.,)*3)
    report('pre-route-native-pose', dict(prefill=prefill, pose=pose))
    if not prefill['ok'] or not pose['ok']:
        print(json.dumps(dict(native_preflight=False, board_written=False))); return
    routed, unresolved, rejected_paths = [], [], []
    for key, request in sorted(packet['requests'].items(), key=lambda row: (-row[1].get('width_nm', 0), row[0])):
        if request.get('kind') not in ('source_boundary', 'supply_departure'): continue
        retained = escape.retained_native_boundary_connection(frame, request, timeout_s=2.)
        if retained:
            routed.append(dict(request=key, existing_native_path=retained)); continue
        if not all('at_nm' in request.get(port, {}) for port in ('a', 'b')):
            unresolved.append(dict(request=key, reason='explicit_typed_port_required')); continue
        a, z = (tuple(request[port]['at_nm']) for port in ('a', 'b'))
        if a == z: continue
        width, net = request['width_nm'], request['net']; found = None
        allowed = set(request['a']['layers']) & set(request['b']['layers'])
        if key in authored:
            route = authored[key]
            if (route.get('net') != net or route.get('width_nm') != width
                    or frame.GetLayerID(route.get('layer', '')) not in allowed
                    or {tuple(route['points_nm'][0]), tuple(route['points_nm'][-1])} != {a, z}):
                raise ValueError('authored_request_exact_net_width_layer_and_ports_required')
            cells.emit_connections(frame, [route], [], identity='native-request:'+key)
            routed.append(dict(request=key, route=route, agent_authored=True))
            op['routes'].append(route)
            continue
        for face in frame.GetEnabledLayers().CuStack():
            if face not in allowed: continue
            cache = {}
            def guard(left, right, _half):
                return (fr._edge_leg_clear(frame, left, right, (width+1)//2)
                    and not force._native_track_rule_hits(frame,
                        p.SHAPE_SEGMENT(left, right, width), face, cache=cache))
            legs = fr._guarded_profiled_lastmile_legs(frame, p.VECTOR2I(*a), p.VECTOR2I(*z),
                width, face, 200000, frame.GetNetcodeFromNetname(net), guard,
                allow_maze=True, maze_margin_mm=3., foreign_cache=cache,
                deadline_monotonic=time.monotonic()+9., max_length_nm=25000000,
                refine_maze=True, refinement_grids_mm=(.2, .1))
            if not legs: continue
            raw_points = [tuple(legs[0][0])] + [tuple(leg[1]) for leg in legs]
            try:
                route = dict(net=net, layer=frame.GetLayerName(face), width_nm=width,
                    points_nm=soften(raw_points))
                cells.emit_connections(frame, [route], [], identity='native-request:'+key)
            except ValueError as exc:
                rejected_paths.append(dict(request=key, layer=frame.GetLayerName(face),
                    points_nm=raw_points, reason=str(exc)))
                report('rejected-paths', rejected_paths)
                continue
            found = route; break
        if found:
            routed.append(dict(request=key, route=found)); op['routes'].append(found)
        else: unresolved.append(dict(request=key, reason='bounded_native_route_not_found', value=request))
    report('route-plan', dict(source=str(source), sha256=args.sha256, board_hint=args.board_hint,
        transported_source_copper_uuids=transported, routed=routed, unresolved=unresolved,
        rejected_paths=rejected_paths, operation=op))
    if unresolved:
        print(json.dumps(dict(unresolved=len(unresolved), board_written=False))); return
    candidate = materialize(destination)
    print(json.dumps(dict(candidate=str(candidate), sha256=force._hash(candidate), not_received=True)))


if __name__ == '__main__': main()

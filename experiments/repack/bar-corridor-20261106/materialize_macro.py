"""Materialize a saved explicit macro plan without repeating route search.

This only creates a fresh private family. Fresh construction recompiles source
ownership; separate whole-board receiving is still mandatory.
"""
import argparse
import json
from pathlib import Path
from cec_pipeline.native import _native
p, _ = _native()
from cec_pipeline import construction, cells
import cec_force_current as force
import cec_route_quality as craft
import cec_additive_route_receiving as additive


def materialize(folder, output=None, route_overrides=None):
    folder = Path(folder).resolve()
    plan = json.loads((folder / 'route-plan.json').read_text())
    if output is not None:
        folder = Path(output).resolve()
        folder.mkdir(parents=True, exist_ok=False)
    path = folder / 'route-plan.json'
    source = Path(plan['source']).resolve()
    if plan.get('unresolved') or force._hash(source) != plan['sha256']:
        raise ValueError('complete_exact_source_plan_required')
    if plan['operation'].get('native_macro') is not True:
        raise ValueError('explicit_native_macro_required')
    if route_overrides is not None:
        if output is None:
            raise ValueError('route_revision_requires_a_fresh_destination')
        overrides = json.loads(Path(route_overrides).read_text())
        rows = {row['request']: row for row in plan['routed'] if 'route' in row}
        if not isinstance(overrides, dict) or not set(overrides) <= set(rows):
            raise ValueError('only_existing_complete_routes_may_be_revised')
        frame, fresh, _ = cells.compile_macro(p.LoadBoard(str(source)), plan['operation'], plan['board_hint'])
        actual_tracks = {force._uid(t): t for t in frame.GetTracks()}
        endpoint_choices = []
        for key, new in overrides.items():
            old = rows[key]['route']
            if (set(old) != set(new)
                    or any(old[name] != new[name] for name in ('net', 'layer', 'width_nm'))):
                raise ValueError('exact_source_route_net_layer_and_width_required')
            request = fresh['requests'][key]
            for endpoint in (0, -1):
                before, after = old['points_nm'][endpoint], new['points_nm'][endpoint]
                if before == after: continue
                ports = [request[name] for name in ('a','b') if request[name].get('at_nm')==before]
                if len(ports) != 1: raise ValueError('unique_fresh_native_request_port_required')
                contacts = [actual_tracks[uid] for uid in ports[0].get('native_uuids', [])
                    if uid in actual_tracks and actual_tracks[uid].GetClass()=='PCB_TRACK']
                contacts = [t for t in contacts if t.GetNetname()==new['net']
                    and frame.GetLayerName(t.GetLayer())==new['layer']
                    and tuple(after) in (tuple(t.GetStart()),tuple(t.GetEnd()))]
                if not contacts: raise ValueError('exact_named_retained_native_track_endpoint_required')
                endpoint_choices.append(dict(request=key, before_nm=before, after_nm=after,
                    native_uuids=[force._uid(t) for t in contacts], source_current_authority_changed=False))
            matching = [i for i, route in enumerate(plan['operation']['routes']) if route==old]
            if len(matching) != 1:
                raise ValueError('unique_authored_operation_route_required')
            plan['operation']['routes'][matching[0]] = new
            rows[key]['route'] = new
            rows[key]['agent_authored'] = True
        plan['route_revision_source'] = str(Path(route_overrides).resolve())
        plan['source_contact_choices'] = endpoint_choices
        cells.emit_connections(frame, plan['operation']['routes'], [], identity='draft-route-revision')
        additive._ground_refill(frame)
        quality = [craft.analyze_board(b) for b in (p.LoadBoard(str(source)), frame)]
        diagnostic = dict(trace_craft_before_after=[q['issue_count'] for q in quality],
            geometry_checked=True, full_saved_receiving_still_required=True, release_authority=False)
        old_issues = {json.dumps(issue, sort_keys=True) for issue in quality[0]['issues']}
        diagnostic['new_issues'] = [issue for issue in quality[1]['issues']
            if json.dumps(issue, sort_keys=True) not in old_issues]
        (folder/'draft-route-quality.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
        if quality[1]['issue_count'] > quality[0]['issue_count']:
            raise ValueError('draft_trace_craft_regression_before_board_materialization')
    candidate = force._copy_family(source, folder / 'candidate')
    plan['candidate'] = str(candidate)
    path.write_text(json.dumps(plan, indent=2)+'\n')
    result = construction._construct(source, candidate,
        dict(operations=[plan['operation']]), plan['board_hint'])
    (folder/'construction.json').write_text(json.dumps(result, indent=2)+'\n')
    (folder/'packet.json').write_text(json.dumps(
        result['changes'][0]['native_macro_packet'], indent=2)+'\n')
    return candidate


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder')
    parser.add_argument('--output')
    parser.add_argument('--route-overrides')
    args = parser.parse_args()
    print(materialize(args.folder, args.output, args.route_overrides))

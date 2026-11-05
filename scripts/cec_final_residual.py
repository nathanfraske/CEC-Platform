"""Read-only final-PCB endpoint diagnostics, not a claim of route impossibility.

Detailed-router attempts describe intermediate copper. Final residuals must
instead come from the serialized selected board and fresh native DRC. This
bounded geometric survey never adds copper or grants fabrication admission.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import tempfile
import time


def _identity(path):
    path = Path(path)
    files = {}
    for suffix in ('.kicad_pcb', '.kicad_pro', '.kicad_dru', '.pourfirst-state.json'):
        item = path.with_suffix(suffix)
        files[suffix] = hashlib.sha256(item.read_bytes()).hexdigest() if item.is_file() else None
    if files['.kicad_pcb'] is None:
        raise ValueError('final PCB is missing')
    return files


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def valid_snapshot(report):
    if not isinstance(report, dict) or report.get('schema') != 1:
        return False
    try:
        return (report.get('source_unchanged') is True
                and report.get('drc_complete') is True
                and report.get('purpose') == 'final_residual_geometry'
                and bool((report.get('source_identity') or {}).get('.kicad_pcb'))
                and report.get('source_board_sha256') == report['source_identity']['.kicad_pcb']
                and isinstance(report.get('residual_details'), list)
                and isinstance(report.get('unconnected_items'), list)
                and report.get('unconnected_count') == len(report['unconnected_items'])
                and report.get('evidence_sha256') == _digest({k: v for k, v in report.items()
                                                            if k != 'evidence_sha256'}))
    except (TypeError, ValueError, OverflowError):
        return False


def _endpoint(item, objects, board):
    obj = objects.get(str(item.get('uuid') or ''))
    if obj is None:
        raise ValueError('DRC endpoint UUID does not resolve on final PCB')
    pos = item.get('pos') or {}
    point = [float(pos['x']), float(pos['y'])]
    if not all(math.isfinite(v) for v in point):
        raise ValueError('non-finite native endpoint position')
    net = str(obj.GetNetname() or '')
    if not net:
        raise ValueError('native endpoint has no net')
    kind = {'PAD': 'pad', 'PCB_TRACK': 'trk', 'PCB_ARC': 'arc',
            'PCB_VIA': 'via', 'ZONE': 'zone'}.get(obj.GetClass())
    if kind is None:
        raise ValueError('unsupported native endpoint class: '+obj.GetClass())
    row = dict(uuid=str(item['uuid']), kind=kind,
               net=net, native_layer=board.GetLayerName(obj.GetLayer()),
               copper_layers=[board.GetLayerName(layer) for layer in board.GetEnabledLayers().CuStack()
                              if obj.IsOnLayer(layer)])
    if hasattr(obj, 'GetParentFootprint') and obj.GetParentFootprint():
        row.update(ref=obj.GetParentFootprint().GetReference(), pad=obj.GetNumber())
    return obj, point, row


def trace_rows(report):
    """Join current endpoint observations by UUID without inventing origin."""
    if not valid_snapshot(report):
        return []
    rows = []
    for detail in report['residual_details']:
        cert = detail['certificate']
        endpoints = cert.get('endpoints') or []
        rows.append(dict(stage='final_endpoint_geometry', status='observed',
            message='Current open endpoints and sampled surrounding copper; not a route-search or origin proof',
            nets=[cert['net']], refs=sorted({r['ref'] for r in endpoints if r.get('ref')}),
            uuids=sorted({r['uuid'] for r in endpoints if r.get('uuid')}),
            authority='fresh_kicad_connectivity+native_geometry',
            detail=dict(report_ref='completion_report.final_residual',
                        evidence_sha256=report['evidence_sha256'], index=detail['index'],
                        source_board_sha256=report['source_board_sha256'],
                        endpoints=endpoints, dominant_blockers=cert.get('dominant_blockers') or [])))
    return rows


def measure(board_path, *, max_details=32, wall_timeout_s=10.0):
    """Refresh connectivity plus bounded endpoint rays at exact branch rules.

The wall bound governs optional geometry details between endpoints; native
DRC remains an authoritative subprocess owned by the enclosing worker's
deadline. Every open is indexed even when detail work is capped. Ray clearance
on another layer is not proof of a via/plane connection or a routable path.
"""
    if isinstance(max_details, bool) or not isinstance(max_details, int) or max_details < 0:
        raise ValueError('nonnegative integer detail budget required')
    if not math.isfinite(wall_timeout_s) or wall_timeout_s < 0:
        raise ValueError('finite nonnegative geometry time budget required')
    started = time.monotonic()
    report = dict(schema=1, purpose='final_residual_geometry', release_authority=False,
                  drc_complete=False, source_unchanged=False, residual_details=[], errors=[])
    try:
        import pcbnew
        import cec_score
        import cec_fr
        import cec_route_dimensions as dimensions
        import cec_fab_profile as fab
        source = _identity(board_path)
        project = dimensions.project_path(board_path)
        if project is not None and project != Path(board_path).with_suffix('.kicad_pro'):
            # Bind unique sibling projects too; never infer an unbound rule set.
            source['resolved_project'] = hashlib.sha256(project.read_bytes()).hexdigest()
        report['source_identity'] = source
        with tempfile.TemporaryDirectory(prefix='cec-final-residual-') as work:
            drc = cec_score._run_drc(str(board_path), str(Path(work)/'drc.json'))
        if not isinstance(drc.get('unconnected_items'), list):
            raise ValueError('fresh native DRC omitted connectivity results')
        rows = drc['unconnected_items']
        report.update(drc_complete=True, unconnected_count=len(rows),
                      unconnected_items=rows, source_board_sha256=source['.kicad_pcb'])
        board = pcbnew.LoadBoard(str(board_path))
        if board is None:
            raise ValueError('final PCB cannot be loaded')
        objects = {item.m_Uuid.AsString(): item for item in board.GetTracks()}
        objects.update({item.m_Uuid.AsString(): item for item in board.Zones()})
        objects.update({pad.m_Uuid.AsString(): pad for fp in board.GetFootprints() for pad in fp.Pads()})
        resolver = dimensions.project_resolver(str(board_path), board=board)
        layers = [layer for layer in fab.COPPER_LAYER_IDS if board.IsLayerEnabled(layer)]
        geometry_started = time.monotonic()
        for index, row in enumerate(rows):
            if index >= max_details or time.monotonic()-geometry_started >= wall_timeout_s:
                break
            try:
                items = row.get('items') or []
                if len(items) != 2:
                    raise ValueError('expected exactly two native open endpoints')
                a, start, endpoint_a = _endpoint(items[0], objects, board)
                b, end, endpoint_b = _endpoint(items[1], objects, board)
                if a.GetNetCode() != b.GetNetCode():
                    raise ValueError('open endpoints resolve to different nets')
                spec = resolver(endpoint_a['net'])
                width, clearance = float(spec['track_width']), float(spec['clearance'])
                if width <= 0 or clearance < 0 or not all(map(math.isfinite, (width, clearance))):
                    raise ValueError('missing or invalid dimensional authority')
                s, t = (pcbnew.VECTOR2I(round(p[0]*1e6), round(p[1]*1e6)) for p in (start, end))
                certificate = cec_fr._lastmile_refusal_certificate(
                    board, s, t, round(width*1e6), round(clearance*1e6),
                    a.GetNetCode(), layers, endpoint_a=endpoint_a, endpoint_b=endpoint_b,
                    maze_searched=False, attempts_per_pair=0)
                certificate.update(conclusion='sampled_final_geometry_not_route_impossibility',
                    source_board_sha256=source['.kicad_pcb'],
                    search=dict(performed=False, kind='read_only_endpoint_ray_survey',
                                escape_probe_mm=1.25, layer_access_proven=False),
                    width_basis='project_branch_contract_not_owned_trunk_or_pair_routing')
                report['residual_details'].append(dict(index=index, net=endpoint_a['net'],
                    distance_mm=round(math.dist(start, end), 6),
                    reason='fresh_native_unconnected', certificate=certificate))
            except Exception as exc:
                report['errors'].append(dict(index=index, error=str(exc)))
        report['details_complete'] = len(report['residual_details']) == len(rows)
        report['details_missing'] = len(rows)-len(report['residual_details'])
        after = _identity(board_path)
        if project is not None and 'resolved_project' in source:
            after['resolved_project'] = hashlib.sha256(project.read_bytes()).hexdigest()
        report['source_unchanged'] = source == after
        if not report['source_unchanged']:
            report['residual_details'] = []
            report['details_complete'] = False
            report['errors'].append(dict(error='PCB or dimensional authority changed during survey'))
    except Exception as exc:
        report['errors'].append(dict(error=str(exc)))
    report['elapsed_s'] = round(time.monotonic()-started, 6)
    report['evidence_sha256'] = _digest(report)
    return report

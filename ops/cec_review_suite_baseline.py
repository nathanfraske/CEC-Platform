"""Read-only, manifest-complete routing review baseline for an explicit suite.

No latest-file discovery, source normalization, rule edits or promotion. A
blocked or absent PCB remains a visible row and cannot hide another product.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate_plan(plan, projects):
    entries = {entry['board']: entry for entry in projects}
    rows = plan.get('boards')
    if plan.get('schema') != 1 or not isinstance(rows, list):
        raise ValueError('schema-1 explicit suite plan required')
    names = [row.get('board') for row in rows]
    if len(set(names)) != len(names) or set(names) != set(entries):
        raise ValueError('every current manifest product required exactly once')
    omitted = plan.get('out_of_scope', [])
    if (not isinstance(omitted, list) or len(set(omitted)) != len(omitted)
            or not set(omitted) < set(entries)):
        raise ValueError('explicit unique out-of-scope products and a nonempty goal required')
    for row in rows:
        if row.get('path') is None:
            if entries[row['board']]['pcb'] is not None or row.get('sha256') is not None:
                raise ValueError('only a manifest-declared absent PCB may have no input')
        elif (not isinstance(row.get('path'), str)
              or not row['path'].endswith('.kicad_pcb')
              or not isinstance(row.get('sha256'), str)
              or len(row['sha256']) != 64
              or any(c not in '0123456789abcdef' for c in row['sha256'])):
            raise ValueError('explicit PCB path and SHA-256 required')
    return rows


def routing_term(producer, raw, intake, *, route_quality=None):
    """The suite goal includes all native findings and whole saved copper.

    Warnings/exclusions remain separate native categories, but neither is a
    zero-finding goal pass. An ordinary-net jog cannot be erased by an empty
    electrical DRC report. Missing whole-board craft evidence fails closed.
    """
    if not (producer.get('ok') is True and producer.get('complete') is True):
        return False
    return (intake.get('ok') is True
            and not raw.get('unconnected_items')
            and isinstance(raw.get('unconnected_items'), list)
            and isinstance(raw.get('violations'), list) and not raw['violations']
            # KiCad 10 places exclusions in the severity-all findings, not a
            # mandatory top-level excluded_violations array. A diagnostic
            # producer may add that separate inventory; it must be empty.
            and isinstance(raw.get('excluded_violations', []), list) and not raw.get('excluded_violations', [])
            and isinstance(raw.get('ignored_checks', []), list) and not raw.get('ignored_checks', [])
            and type(route_quality) is dict and route_quality.get('craft_ok') is True
            and route_quality.get('power_contour_review_ok') is True)


def run(plan_path, out, reporting_build, *, reuse_suite_source_audits=False):
    import cec_swig_guard
    cec_swig_guard.pin()
    import wx
    quiet = wx.LogNull()
    import cec_beta_manifest as manifest
    import cec_force_current as force
    import cec_full_pipeline as pipeline
    import cec_native_drc_runner as native
    import cec_score as score
    import cec_synth_pipeline as synth
    from cec_suite_source_audit_cache import SuiteSourceAuditCache

    audit_session = SuiteSourceAuditCache(ROOT) if reuse_suite_source_audits else None

    plan_path, out = Path(plan_path).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('fresh baseline directory required')
    plan_hash = force._hash(plan_path)
    plan = json.loads(plan_path.read_text())
    rows = validate_plan(plan, manifest.PROJECTS)
    if manifest.validate(str(ROOT)):
        raise ValueError('current manifest integrity failed')
    epoch = force._code_identity()
    own_hash = force._hash(Path(__file__))
    bindings = {}
    for row in rows:
        if row['path'] is not None:
            path = (ROOT / row['path']).resolve()
            if not path.is_relative_to(ROOT) or force._hash(path) != row['sha256']:
                raise ValueError('selected source outside repository or hash mismatch: '+row['board'])
            cfg = synth.Config.load(row['board'])
            bindings[row['board']] = pipeline._files_signature(pipeline._source_files(cfg, path))
    out.mkdir(parents=True)
    report = dict(schema=1, kind='manifest-complete-routing-review-baseline',
                  started_utc=datetime.now(timezone.utc).isoformat(),
                  plan=dict(path=str(plan_path), sha256=plan_hash), code_identity=epoch,
                  helper_sha256=own_hash, boards={}, release_authority=False, fab_ready=False,
                  source_geometry_or_rules_changed=False, production_selector_changed=False)
    for row in rows:
        name = row['board']
        result = dict(row, routing_review_ready=False,
                      in_goal=name not in plan.get('out_of_scope', []))
        if row['path'] is None:
            result.update(status='no_declared_pcb', opens=None, native_error_count=None,
                          reason='schematic-only product; not a zero-open result')
        else:
            cfg = synth.Config.load(name)
            path = (ROOT / row['path']).resolve()
            dest = out / name
            dest.mkdir(parents=True)
            # These source/hierarchy/BOM checks are mandatory, not inferred
            # from the fact that this explicit candidate once routed well.
            intake = pipeline._source_intake(cfg, path, dest/'source-intake.json',
                                             allow_derived_input=path != Path(cfg.pcb).resolve(),
                                             assembly_instance=row.get('assembly_instance'),
                                             suite_audit_cache=audit_session)
            producer = native.run(path, dest/'native-drc.json',
                                  reporting_build=reporting_build, timeout_s=10., board_hint=name)
            result.update(source_intake_ok=intake['ok'],
                          source_intake_report=str(dest/'source-intake.json'),
                          source_signature=bindings[name], native_producer=producer)
            if producer.get('ok') and producer.get('complete'):
                raw = json.loads(Path(producer['report']).read_text())
                metric = score.score(str(path), score.Rules.from_board(str(path)),
                                     drc_json=str(producer['report']))
                result.update(status='measured', opens=len(raw['unconnected_items']),
                              scored_opens=metric.unconnected, scored_drc=metric.drc,
                              native_error_count=sum(v['severity']=='error' for v in raw['violations']),
                              native_severity_counts=dict(Counter(v['severity'] for v in raw['violations'])),
                              native_error_types=dict(Counter(v['type'] for v in raw['violations'] if v['severity']=='error')),
                              ignored_checks=raw.get('ignored_checks', []),
                              route_quality=metric.detail.get('route_quality'),
                              routing_review_ready=(routing_term(producer, raw, intake,
                                                        route_quality=metric.detail.get('route_quality'))
                                                    and metric.drc == 0 and metric.unconnected == 0))
            else:
                result.update(status='native_measurement_incomplete', opens=None, native_error_count=None)
        report['boards'][name] = result
        force._write(out/'baseline.json', report)
        print(json.dumps({key: result.get(key) for key in (
            'board', 'status', 'opens', 'native_error_count', 'scored_drc',
            'source_intake_ok', 'routing_review_ready')}), flush=True)
    if audit_session is not None:
        report['suite_source_audit_reuse'] = audit_session.evidence()
    report['all_inputs_and_code_unchanged'] = (
        force._hash(plan_path) == plan_hash and force._code_identity() == epoch
        and force._hash(Path(__file__)) == own_hash
        and all(pipeline._files_signature(pipeline._source_files(
            synth.Config.load(row['board']), (ROOT/row['path']).resolve())) == bindings[row['board']]
            for row in rows if row['path'] is not None))
    report['goal_complete'] = (report['all_inputs_and_code_unchanged']
                               and all(r['routing_review_ready'] for r in report['boards'].values()
                                       if r['in_goal']))
    force._write(out/'baseline.json', report)
    if not report['all_inputs_and_code_unchanged']:
        raise ValueError('baseline inputs changed during measurement')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reporting-build', type=Path, required=True)
    parser.add_argument('--reuse-suite-source-audits', action='store_true',
                        help='reuse source-only audits within this exact suite invocation')
    args = parser.parse_args()
    run(args.plan, args.out, args.reporting_build,
        reuse_suite_source_audits=args.reuse_suite_source_audits)

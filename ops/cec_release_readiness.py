"""Bounded, read-only readiness replay of explicitly selected current products.

The input plan is data: no product, reference, coordinate, current or exception
is selected in this driver. Every finding and unknown is retained. This is a
review packet, not an admission or manufacturing-package generator.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import time

import cec_swig_guard
cec_swig_guard.pin()
import wx
_quiet = wx.LogNull()
import pcbnew

import cec_assembly_instance as assembly
import cec_beta_manifest as manifest
import cec_board_geometry as geometry
import cec_constraints as constraints
import cec_fab_check as fab
import cec_fab_native_geometry as native_fab
import cec_fab_profile as profile
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_full_pipeline as pipeline
import cec_native_drc_runner as native
import cec_score as score
import cec_synth_pipeline as synth


ROOT = Path(__file__).resolve().parents[1]


def coverage_term(record):
    """Three-valued coverage: a proved empty obligation is N/A, not failure.

    Missing, unresolved and partially executed evidence cannot acquire that
    exemption merely by reporting zero successful legs.
    """
    keys = ('expected', 'checked', 'passed', 'failed', 'unknown', 'unresolved_inputs')
    if (not isinstance(record, dict)
            or any(type(record.get(key)) is not int or record[key] < 0 for key in keys)):
        return False
    if record.get('status') == 'not_applicable' and all(record[key] == 0 for key in keys):
        return None
    return (record.get('ok') is True and record.get('status') == 'verified' and record['expected'] > 0
            and record['expected'] == record['checked'] == record['passed']
            and not any(record[key] for key in ('failed', 'unknown', 'unresolved_inputs')))


def run(plan_path, out, reporting_build, *, sense_timeout_s=40):
    plan_path, out = Path(plan_path).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('fresh readiness output directory required')
    plan_hash = force._hash(plan_path)
    plan = json.loads(plan_path.read_text())
    if (plan.get('schema') != 1 or not isinstance(plan.get('boards'), list)
            or not 1 <= len(plan['boards']) <= len(manifest.CURRENT_BETA_BOARDS)):
        raise ValueError('bounded explicit current-product readiness plan required')
    names = [row['board'] for row in plan['boards']]
    if len(set(names)) != len(names) or any(name not in manifest.BY_BOARD for name in names):
        raise ValueError('unique current manifest products required')
    errors = manifest.validate(str(ROOT))
    if errors:
        raise ValueError(str(errors))
    epoch = force._code_identity()
    helpers = {str(Path(__file__).resolve()): force._hash(Path(__file__)),
               str(Path(assembly.__file__).resolve()): force._hash(Path(assembly.__file__))}
    # Bind all families before the first board is evaluated. A late peer
    # change cannot leave the earlier half of a two-board report looking valid.
    families, selected = {}, {}
    for row in plan['boards']:
        name = row['board']
        path = (ROOT / row['path']).resolve()
        if force._hash(path) != row['sha256']:
            raise ValueError('selected board hash mismatch: ' + name)
        cfg = synth.Config.load(name)
        selected[name] = path, cfg
        families[name] = force._family(path, name)
        if row.get(assembly.CONTEXT_KEY) is not None:
            assembly.resolve(path, row[assembly.CONTEXT_KEY], ROOT)
    out.mkdir(parents=True)
    report = dict(schema=1, kind='exact-current-product-release-readiness-review',
                  plan=dict(path=str(plan_path), sha256=plan_hash), code_identity=epoch,
                  helper_sha256=helpers, boards={}, release_authority=False, fab_ready=False,
                  review_only=True, physical_geometry_changed=False)
    for row in plan['boards']:
        started = time.monotonic()
        name = row['board']
        path, cfg = selected[name]
        dest = out / name
        dest.mkdir(parents=True)
        working = force._copy_family(path, dest / 'native-source')
        producer = native.run(working, dest / 'native-drc.json',
                              reporting_build=reporting_build, timeout_s=10., board_hint=name)
        if not producer.get('ok') or not producer.get('complete'):
            raise ValueError('complete saved native DRC required: ' + str(producer))
        raw = json.loads(Path(producer['report']).read_text())
        ctx = dict(board_hint=name, sch=str(cfg.sch), **{'_drc_json::'+str(path): raw})
        if assembly.CONTEXT_KEY in row:
            ctx[assembly.CONTEXT_KEY] = copy.deepcopy(row[assembly.CONTEXT_KEY])
        source_files = pipeline._files_signature(pipeline._source_files(cfg, path))
        board = pcbnew.LoadBoard(str(path))
        with force._thermal_hint(name):
            metric = score.score(str(path), score.Rules.from_board(str(path)),
                                 drc_json=str(producer['report']))
            checks = constraints.run(str(path), ctx)
            proof = sense.replay(path, board_hint=name, timeout_s=sense_timeout_s)
        rows = [dict(id=c.id, status=status, severity=c.severity, checkable=c.checkable,
                     ratification=c.status, detail=detail, payload=payload)
                for c, status, detail, payload in checks]
        blocking = constraints.blocking_rows(checks, phase='post_route')
        declared = profile.board_profile_name(board)
        factory_rules = fab.profile_rules(fab.PROFILES['jlcpcb'], fab.board_outer_copper_oz(path),
                                         profile.get_profile(declared) if declared else None)
        factory = dict(holes=native_fab.audit_holes(board, factory_rules, board_path=path),
                       legend=native_fab.audit_legend(board, factory_rules))
        item = dict(path=str(path), sha256=force._hash(path), outline_bbox_mm=geometry.outline_bbox_mm(board),
                    opens=metric.unconnected, scored_drc=metric.drc,
                    raw_native_drc=len(raw['violations']), native_types=dict(Counter(v['type'] for v in raw['violations'])),
                    full50=dict(Counter(value['status'] for value in rows)), checks=rows,
                    constraint_blockers=[dict(id=c.id, status=status, severity=c.severity, detail=detail)
                                         for c, status, detail, _ in blocking],
                    clipped_kelvin={key: proof['clipped_isolation'].get(key) for key in (
                        'expected', 'checked', 'passed', 'failed', 'unknown', 'unresolved_inputs')},
                    native_producer=producer, source_signature=source_files,
                    selected_assembly=ctx.get('assembly_envelope'), independent_factory_geometry=factory,
                    factory_scope='hole and legend audits only; not complete factory signoff',
                    elapsed_s=time.monotonic()-started, fab_ready=False, release_authority=False)
        statuses = {value['id']: value['status'] for value in rows}
        item['readiness_terms'] = dict(
            native_report_complete=producer['complete'], routing_closed=metric.unconnected == 0 and metric.drc == 0,
            current_schematic_parity=statuses.get('sch-pcb-sync') == 'PASS',
            current_bom_field_lint=statuses.get('bom-field-lint') == 'PASS',
            deterministic_constraint_release=not blocking,
            typed_inner_departures=coverage_term(proof['inner_departure']),
            clipped_kelvin_isolation=coverage_term(proof['clipped_isolation']),
            factory_drill_audit_complete=factory['holes'].get('complete') is True,
            factory_drill_clear=not factory['holes']['findings'],
            factory_legend_audit_complete=factory['legend'].get('complete') is True,
            factory_legend_clear=not factory['legend']['findings'])
        item['unpassed_readiness_terms'] = [key for key, value in item['readiness_terms'].items() if value is False]
        item['not_applicable_readiness_terms'] = [key for key, value in item['readiness_terms'].items() if value is None]
        item['not_qualified_by_this_review'] = [
            'complete_factory_native_geometry_and_artifact_signoff',
            'coherent_operating_case_current_and_thermal_qualification',
            'physical_fitted_hardware_contact_and_assembly_qualification',
            'manufacturing_export_and_final_artifact_inspection']
        report['boards'][name] = item
        force._write(dest / 'typed-sense.json', proof)
        force._write(dest / 'readiness.json', item)
        print(json.dumps(dict(board=name, opens=item['opens'], drc=item['scored_drc'],
                              checks=item['full50'], blockers=[q['id'] for q in item['constraint_blockers']],
                              source_sync=next(q['status'] for q in rows if q['id']=='sch-pcb-sync'),
                              elapsed_s=item['elapsed_s'])), flush=True)
    report['all_inputs_and_code_unchanged'] = (
        epoch == force._code_identity() and force._hash(plan_path) == plan_hash
        and all(force._hash(Path(path)) == value for path, value in helpers.items())
        and all(families[name] == force._family(selected[name][0], name) for name in names)
        and all(pipeline._files_signature(pipeline._source_files(selected[name][1], selected[name][0]))
                == report['boards'][name]['source_signature'] for name in names))
    if not report['all_inputs_and_code_unchanged']:
        raise ValueError('review inputs changed; results cannot be selected')
    force._write(out / 'readiness.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reporting-build', type=Path, required=True)
    parser.add_argument('--sense-timeout-s', type=float, default=40.)
    args = parser.parse_args()
    run(args.plan, args.out, args.reporting_build, sense_timeout_s=args.sense_timeout_s)

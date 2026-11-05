"""Construct bounded native-fault reference seating then uniform print context.

Private construction only. The original-parent full transaction receiver is
separate and mandatory; these artifacts do not select or admit a board.
"""
import argparse
import json
from pathlib import Path
import time
import traceback

import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet = wx.LogNull()
import pcbnew
import cec_force_current as force
import cec_native_drc_runner as native
import cec_received_private_stage as stage
import cec_reference_field_seating as seats
import cec_mask_search_reference_mapping as maps
import cec_nonpolar_print_context as printing
import cec_synth_pipeline as synth
import typed_print_runtime as runtime


def discover_native(source,report,build,runtime_directory):
    """Own only this invocation's runtime; never contaminate a print family."""
    return runtime.observe(source,runtime_directory,lambda:native.run(source,report,
        reporting_build=build,timeout_s=10.))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--source-sha256', required=True)
    p.add_argument('--board', required=True)
    p.add_argument('--owner', action='append', required=True)
    p.add_argument('--fpid', action='append', required=True)
    p.add_argument('--optional-body-fpid', action='append', default=[])
    p.add_argument('--reviewed-courtyard-contract', action='append', default=[])
    p.add_argument('--strategy', choices=('reference_fields','reference_map'), default='reference_fields')
    p.add_argument('--peripheral-reverse-seats', action='store_true')
    p.add_argument('--interrupt-projected-body-guides', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert not a.interrupt_projected_body_guides or a.strategy=='reference_map'
    source = a.source.resolve(strict=True)
    assert force._hash(source) == a.source_sha256
    a.out.mkdir(parents=True, exist_ok=False)
    code = force._code_identity()
    dependencies = {str(Path(m.__file__).resolve()): force._hash(Path(m.__file__))
                    for m in (seats, maps, printing, runtime)}
    source_family = force._family(source, a.board)
    r = dict(ok=False, complete=False, admitted=False, source_selected=False,
             release_authority=False, code_identity=code, dependencies=dependencies,
             source=str(source), source_sha256=a.source_sha256, phases=[])
    started = time.monotonic()
    try:
        build = Path('/home/codex/.cache/cec/native-drc-10.0.5')
        # Discovery receives this raw descendant's ACTUAL saved project and
        # library context. It grants no final context/admission authority.
        # The final uniform print phase and original-parent transaction must
        # separately receive the canonical selected-board context.
        producer,preserved = discover_native(source,a.out/'source-discovery-native.json',
            build,a.out/'source-discovery-runtime')
        r['source_discovery_runtime_preserved']=preserved
        stage.require_native_tool(producer, native._describe_build(build))
        grade = a.out/'actual-source-grade.json'
        force._write(grade, dict(code_identity=code,
            kind='fresh_actual_native_reference_field_discovery_not_admission',
            boards=dict(source=dict(path=str(source), sha256=force._hash(source),
                                    native_producer=producer)), release_authority=False))
        operation = seats if a.strategy=='reference_fields' else maps
        options = (dict(timeout_s=10.) if a.strategy=='reference_fields' else
            dict(reverse_ownership='rigid_root_group_per_component',via_ink_policy='native_mask_and_bore',
                 peripheral_reverse_seats=a.peripheral_reverse_seats))
        if a.interrupt_projected_body_guides:options['interrupt_projected_body_guides']=True
        q = operation.plan(source, grade=grade, board_hint=a.board,
            maximum_components=len(a.owner), owner_uuid_scope=a.owner,
            reviewed_courtyard_contract_ids=a.reviewed_courtyard_contract, **options)
        qpath = a.out/'reference-proposal.json'
        force._write(qpath, q)
        child = force._copy_family(source, a.out/'UNADMITTED-reference-fields')
        operation.write_private(source, child, q)
        r['phases'].append(dict(kind=a.strategy, candidate=str(child),
            candidate_sha256=force._hash(child), proposal=str(qpath.resolve())))
        r['reference_seats'] = q['records']
        b = pcbnew.LoadBoard(str(child))
        ids = sorted(force._uid(fp) for fp in b.GetFootprints()
                     if fp.GetFPIDAsString() in a.fpid)
        cfg = synth.Config.load(a.board)
        pq = printing.plan(child, library_table=Path(cfg.dir)/'fp-lib-table',
            footprint_ids=a.fpid, expected_instance_uuids=ids, board_hint=a.board,
            optional_body_footprint_ids=a.optional_body_fpid,timeout_s=10.)
        ppath = a.out/'print-proposal.json'
        force._write(ppath, pq)
        artifact = printing.construct_private(child, pq, a.out/'UNADMITTED-print-context')
        final = Path(artifact['candidate'])
        r['phases'].append(dict(kind='print_context', candidate=str(final),
            candidate_sha256=force._hash(final), proposal=str(ppath.resolve())))
        r['print_instances'] = len(ids)
        r['source_family_live'] = source_family == force._family(source, a.board)
        r['code_dependencies_live'] = code == force._code_identity() and all(
            force._hash(Path(s)) == h for s,h in dependencies.items())
        assert r['source_family_live'] and r['code_dependencies_live']
        r.update(ok=True, complete=True)
    except Exception as exc:
        r.update(error=str(exc), failure_stack=traceback.format_exc())
    r['elapsed_s'] = time.monotonic()-started
    force._write(a.out/'construction.json', r)
    print(json.dumps({k:r.get(k) for k in ('ok','complete','error','elapsed_s',
                                           'reference_seats','print_instances')}), flush=True)
    return 0 if r['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

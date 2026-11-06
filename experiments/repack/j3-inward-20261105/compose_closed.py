"""Compose two independently received, disjoint native deltas, privately."""
from pathlib import Path
import copy
import json
import time

from cec_pipeline.native import _native
from cec_pipeline import outlines
import cec_suite_inspection as inspect
import cec_force_current as force
import cec_additive_route_receiving as syntax
import cec_copper_echo as copper
import cec_native_partition_pair as partition
import cec_assembly_envelope as assembly
import cec_native_drc_runner as drc

BASE = Path('experiments/repack/atx-small-cell-20261105/native-v5/carrier/board.kicad_pcb')
TRIM = Path('experiments/repack/j3-inward-20261105/trim-v2/carrier/board.kicad_pcb')
VENT = Path('experiments/repack/c37-vent-fill-20261105/corrected-rounded/carrier/board.kicad_pcb')
HUB = Path('experiments/repack/hub-kvm-20261105/native-v15/cover/board.kicad_pcb')
CONTRACT = Path('beta/assembly/hub-atx-stack.json')
BOUNDS = {
    BASE: 'dcc749c6d75bac04675ec7260f8709ee78ff798fd6d18a618f9819c56cdd7688',
    TRIM: 'a2fcfe9b147877bf72b5d2badb0cb841e44d7a8f565605dd01b759d2992e0a16',
    VENT: '3f68dd19594ba2817e6989e515786f64163709bd0bd877e88d3fb32115ea37ab',
    HUB: 'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',
    CONTRACT: '0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a',
}
WORK = Path('experiments/repack/paired-closed-v2-20261105')


def globals_only(root, nodes):
    ids = {id(n) for n in nodes.values()}
    return copper._freeze([n for n in root if id(n) not in ids])


def main():
    assert not WORK.exists()
    assert all(inspect.sha(p) == sha for p,sha in BOUNDS.items())
    parsed = [syntax._nodes(p) for p in (BASE, TRIM, VENT)]
    (base, old), (trim, trimmed), (vent, guarded) = parsed
    assert old.keys() == trimmed.keys() == guarded.keys()
    assert globals_only(base,old) == globals_only(trim,trimmed) == globals_only(vent,guarded)
    trim_ids = {k for k in old if old[k] != trimmed[k]}
    vent_ids = {k for k in old if old[k] != guarded[k]}
    assert len(trim_ids) == 7 and vent_ids == {
        'cdb78967-3235-44b9-962b-6ce7aa574142',
        '4298863e-593a-4614-93d4-b005e5fa434e'}
    assert not trim_ids & vent_ids
    assert force._sidecars(BASE) == force._sidecars(TRIM) == force._sidecars(VENT)
    target = force._copy_family(TRIM, WORK/'carrier')
    cover = force._copy_family(HUB, WORK/'cover')
    replacements = {id(trimmed[k]): copy.deepcopy(guarded[k]) for k in vent_ids}
    trim[1:] = [replacements.get(id(n),n) for n in trim[1:]]
    target.write_text(syntax._render(trim)+'\n')
    _, merged = syntax._nodes(target)
    assert all(merged[k] == (guarded[k] if k in vent_ids else trimmed[k]) for k in old)
    pcb, quiet = _native()
    before, board, hub = [pcb.LoadBoard(str(p)) for p in (BASE,target,cover)]
    assert all(p is not None for p in (before,board,hub))
    connectivity = partition.compare(before, board, retired_uuids=(), timeout_s=10.)
    assert connectivity['available'] and connectivity['preserved']
    connectivity = json.loads(json.dumps(connectivity,
        default=lambda value: sorted(value,key=repr) if isinstance(value,set)
        else (_ for _ in ()).throw(TypeError(type(value).__name__))))
    contract = json.loads(CONTRACT.read_text())
    fit, _ = assembly.evaluate_boards(board,hub,contract)
    vents = assembly.facing_vents(fit,contract,'carrier')
    vent_check = assembly.vent_reservations(board,vents)
    guard = next(z for z in board.Zones() if z.m_Uuid.AsString() ==
                 'cdb78967-3235-44b9-962b-6ce7aa574142')
    fill = next(z for z in board.Zones() if z.m_Uuid.AsString() ==
                '4298863e-593a-4614-93d4-b005e5fa434e')
    intersection = fill.GetFilledPolysList(pcb.F_Cu).CloneDropTriangulation()
    intersection.BooleanIntersection(guard.Outline())
    assert intersection.OutlineCount() == 0
    native = drc.run(target,WORK/'native-drc.json',
        reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,
        footprint_table='checkpoints/review-20261105-outline-compaction/boards/atx-24pin-rev3/library/fp-lib-table')
    inspect.write_json(WORK/'native-drc.runner.json',native)
    assert native['ok'] and native['complete']
    raw = json.loads((WORK/'native-drc.json').read_text())
    counts = dict(errors=sum(v['severity']=='error' for v in raw['violations']),
                  opens=len(raw['unconnected_items']),
                  warnings=sum(v['severity']=='warning' for v in raw['violations']))
    assert counts['errors'] == counts['opens'] == 0
    assert fit['ok'] and all(v['ok'] for v in vent_check)
    receipt = dict(schema=1,scope='PRIVATE_DISJOINT_NATIVE_COMPOSITION',
        source_inputs=[dict(path=str(p),sha256=sha) for p,sha in BOUNDS.items()],
        candidate=dict(carrier=dict(path=str(target),sha256=inspect.sha(target)),
                       cover=dict(path=str(cover),sha256=inspect.sha(cover))),
        trim_changed_uuids=sorted(trim_ids),vent_changed_uuids=sorted(vent_ids),
        disjoint_native_owner_changes=True,exact_global_and_project_context_preserved=True,
        outline_mm=[78,87.5],native_counts=counts,original_native_partition=connectivity,
        paired_assembly=dict(ok=fit['ok'],missing=fit['missing'],checks=len(fit['checks']),
            failures=[r for r in fit['checks'] if not r['ok']],
            minimum_reported_margin_mm=min(r['margin_mm'] for r in fit['checks'] if 'margin_mm' in r)),
        current_vent_checks=vent_check,full_c37_guard_native_intersection_empty=True,
        current_qualification=False,assembled_z_qualification=False,release_authority=False,
        cautions=['Three inherited top output power-width failures remain.',
                  'Raw native refill can recreate nm vent penetration; preserve correction receiving.',
                  'No bar is installed; X/Y saving is from the coordinated J3 and placement repack.',
                  'Reviewed incumbents and checkpoint selector are unchanged.'])
    inspect.write_json(WORK/'receipt.json',receipt)
    inspect.write_json('docs/evidence/20261105-bottom-compaction/paired-closed.json',receipt)
    print(json.dumps(dict(candidate=receipt['candidate'],outline_mm=receipt['outline_mm'],
                          native_counts=counts,paired_assembly=receipt['paired_assembly'],
                          native_partition=connectivity['preserved'])))
    assert all(inspect.sha(p) == sha for p,sha in BOUNDS.items())


if __name__ == '__main__':
    main()

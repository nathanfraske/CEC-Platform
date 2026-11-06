"""Private 2 mm bottom-edge trial after the connected J3 repack.

This does not relax the generic outline operator. J3's intentional edge
overhang is proved against the exact pre-repack board; every other native
envelope must fit. Only five perimeter primitives and clipped GND fill change.
No current, complete assembled-height, or production qualification is implied.
"""
from pathlib import Path
import copy
import json
import time

from cec_pipeline.native import _native
from cec_pipeline import outlines, groundplanes, identity
import cec_suite_inspection as inspection
import cec_force_current as force
import cec_additive_route_receiving as syntax
import cec_copper_echo as copper
import cec_field_coupling as field

SOURCE = Path('experiments/repack/atx-small-cell-20261105/native-v5/carrier/board.kicad_pcb')
BASELINE = Path('experiments/repack/bar-corridor-20261105/carrier/board.kicad_pcb')
SOURCE_SHA = 'dcc749c6d75bac04675ec7260f8709ee78ff798fd6d18a618f9819c56cdd7688'
BASELINE_SHA = '496e90672ac0eb24920bccde582661b895ebebb88aaca5bb46ee32db86216749'
WORK = Path('experiments/repack/j3-inward-20261105/trim-v2')
BOTTOM = '6f4ab618-0fcf-40ed-9b87-961ceab9cf33'
NEW_Y = 87_500_000


def main():
    assert inspection.sha(SOURCE) == SOURCE_SHA
    assert inspection.sha(BASELINE) == BASELINE_SHA
    assert not WORK.exists(), 'immutable trial: choose a new target'
    pcb, quiet = _native()
    old, board = [pcb.LoadBoard(str(p)) for p in (BASELINE, SOURCE)]
    edges, bounds = outlines._rounded_edges(board)
    assert bounds == [0, 0, 78_000_000, 89_500_000]
    selected = next(e for e in edges if e.m_Uuid.AsString() == BOTTOM)
    clearance = int(board.GetDesignSettings().m_CopperEdgeClearance)
    assert clearance == 500_000

    # Independently prove the same native connector body, pin positions and
    # courtyard relative to the proposed edge as before this coordinated move.
    before = next(f for f in old.GetFootprints() if f.GetReference() == 'J3')
    after = next(f for f in board.GetFootprints() if f.GetReference() == 'J3')
    assert before.m_Uuid.AsString() == after.m_Uuid.AsString()
    assert before.GetLayer() == after.GetLayer()
    assert before.GetOrientationDegrees() == after.GetOrientationDegrees()
    assert list(after.GetPosition()) == [before.GetPosition().x, before.GetPosition().y-2_000_000]
    oldpads = {p.m_Uuid.AsString(): p for p in before.Pads()}
    newpads = {p.m_Uuid.AsString(): p for p in after.Pads()}
    assert oldpads.keys() == newpads.keys()
    for uid, a in oldpads.items():
        b = newpads[uid]
        assert (a.GetNumber(), a.GetNetname(), a.GetAttribute(), list(a.GetSize()),
                list(a.GetDrillSize()), a.GetShape(), a.GetOrientationDegrees()) == (
                b.GetNumber(), b.GetNetname(), b.GetAttribute(), list(b.GetSize()),
                list(b.GetDrillSize()), b.GetShape(), b.GetOrientationDegrees())
        assert list(b.GetPosition()) == [a.GetPosition().x, a.GetPosition().y-2_000_000]
    for f in (before, after):
        f.BuildCourtyardCaches()
    translated = before.GetCourtyard(before.GetLayer()).CloneDropTriangulation()
    translated.Move(pcb.VECTOR2I(0, -2_000_000))
    deadline = time.monotonic()+8.
    current = after.GetCourtyard(after.GetLayer())
    assert groundplanes._difference(translated, current, deadline).OutlineCount() == 0
    assert groundplanes._difference(current, translated, deadline).OutlineCount() == 0
    assert bounds[3]-before.GetCourtyard(before.GetLayer()).BBox().GetBottom() == NEW_Y-current.BBox().GetBottom()

    rows = []
    def check(box, kind, uid, gap):
        margin = NEW_Y-int(box.GetBottom())
        assert margin > 0 and margin >= gap, (kind, uid, margin, gap)
        rows.append(dict(kind=kind, uuid=uid, edge_margin_nm=margin, required_nm=gap))
    for t in board.GetTracks():
        check(t.GetBoundingBox(), 'conductor_or_barrel', t.m_Uuid.AsString(), clearance)
    for g in board.GetDrawings():
        if pcb.IsCopperLayer(g.GetLayer()):
            check(g.GetBoundingBox(), 'copper_artwork', g.m_Uuid.AsString(), clearance)
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetNetname() == 'GND':
            continue
        for face in z.GetLayerSet().CuStack():
            assert z.IsFilled() and z.HasFilledPolysForLayer(face)
            fill = z.GetFilledPolysList(face)
            if fill.OutlineCount():
                check(fill.BBox(), 'non_ground_fill', z.m_Uuid.AsString(), clearance)
    for f in board.GetFootprints():
        pads = list(f.Pads())
        for p in pads:
            check(p.GetBoundingBox(), 'pad_or_hole', p.m_Uuid.AsString(), clearance)
            drill = p.GetDrillSize()
            radius = (abs(int(drill.x))+abs(int(drill.y))+1)//2
            assert not radius or NEW_Y-int(p.GetPosition().y)-radius > 0
        f.BuildCourtyardCaches()
        occupied = {f.GetLayer()} | {face for p in pads if p.GetAttribute() == pcb.PAD_ATTRIB_SMD
                                     for face in (pcb.F_Cu, pcb.B_Cu) if p.IsOnLayer(face)}
        if pads:
            assert occupied <= {pcb.F_Cu, pcb.B_Cu}
            for face in occupied:
                court = f.GetCourtyard(face)
                assert court.OutlineCount() and not court.IsSelfIntersecting()
                if f != after:
                    check(court.BBox(), 'occupied_courtyard', f.m_Uuid.AsString(), 0)
        for g in f.GraphicalItems():
            if g.GetLayer() in (pcb.F_CrtYd, pcb.B_CrtYd) and f != after:
                check(g.GetBoundingBox(), 'courtyard_stroke', g.m_Uuid.AsString(), 0)
            if pcb.IsCopperLayer(g.GetLayer()):
                check(g.GetBoundingBox(), 'footprint_copper', g.m_Uuid.AsString(), clearance)

    updates, rings = outlines._rounded_updates(board, edges, selected, 1, -1,
                                               NEW_Y, clearance, time.monotonic()+8.)
    record = dict(axis=1, inward=-1, position_nm=NEW_Y, old_position_nm=bounds[3],
                  source_copper_edge_clearance_nm=clearance, source_bounds_nm=bounds,
                  edge_updates=updates, rounded_clip_rings_nm=rings,
                  offset_guard_nm=10000, offset_chord_error_nm=1000)
    outlines._apply_updates(board, updates)
    outlines.clip_ground(board, record)
    target = force._copy_family(SOURCE, WORK/'carrier')
    raw = WORK/'native.kicad_pcb'
    field._save_field_snapshot(board, raw)
    root, original = syntax._nodes(SOURCE)
    _, fresh = syntax._nodes(raw)
    edge_ids = {r['uuid'] for r in updates}
    ground_ids = {z.m_Uuid.AsString() for z in board.Zones()
                  if not z.GetIsRuleArea() and z.GetNetname() == 'GND'}
    replacements = {}
    for uid in edge_ids | ground_ids:
        keys = {'start','mid','end'} if uid in edge_ids else {'filled_polygon'}
        node = copy.deepcopy(original[uid])
        if uid in edge_ids:
            # Native graphic parser requires start/mid/end before style.
            points = {v[0]:v for v in fresh[uid]
                      if isinstance(v,list) and v and v[0] in keys}
            node[:] = [copy.deepcopy(points[v[0]])
                       if isinstance(v,list) and v and v[0] in keys else v for v in node]
        else:
            node[:] = [v for v in node if not (isinstance(v,list) and v and v[0] in keys)]
            node.extend(copy.deepcopy(v) for v in fresh[uid]
                        if isinstance(v,list) and v and v[0] in keys)
        replacements[id(original[uid])] = node
    root[1:] = [replacements.get(id(n), n) for n in root[1:]]
    target.write_text(syntax._render(root)+'\n')
    saved = pcb.LoadBoard(str(target))
    assert field._field_snapshot_inventory(saved) == field._field_snapshot_inventory(board)
    outlines._residue(SOURCE, target, record, ground_ids)
    _, newbounds = outlines._rounded_edges(saved)
    assert newbounds == [0,0,78_000_000,NEW_Y]
    assert force._sidecars(SOURCE) == force._sidecars(target)
    receipt = dict(schema=1, scope='PRIVATE_EXACT_EDGE_PORT_RELATIVE_REPACK_TRIM',
        source=dict(path=str(SOURCE),sha256=SOURCE_SHA),
        edge_port_baseline=dict(path=str(BASELINE),sha256=BASELINE_SHA),
        candidate=dict(path=str(target),sha256=inspection.sha(target)),
        operation=record, native_envelope_count=len(rows),
        minimum_native_copper_margin_nm=min(r['edge_margin_nm'] for r in rows if r['required_nm']),
        j3_relative_courtyard_and_all_pin_geometry_exact_preserved=True,
        j3_existing_overhang_nm=current.BBox().GetBottom()-NEW_Y,
        all_other_native_envelopes_inside=True,
        exact_native_changes='five perimeter primitives and conservative GND fill clipping only',
        outline_before_mm=[78,89.5],outline_after_mm=[78,87.5],
        laminate_area_reduction_mm2=156, code_identity=identity.code_identity(),
        native_drc_pending=True, routing_admitted=False, current_qualified=False,
        complete_assembled_z_qualified=False, assembly_qualified=False, release_authority=False)
    inspection.write_json(WORK/'construction.json', receipt)
    print(json.dumps({k:receipt[k] for k in ('candidate','outline_before_mm',
                     'outline_after_mm','laminate_area_reduction_mm2',
                     'minimum_native_copper_margin_nm','native_drc_pending')}))
    assert inspection.sha(SOURCE) == SOURCE_SHA and inspection.sha(BASELINE) == BASELINE_SHA


if __name__ == '__main__':
    main()

"""Explicit full-width native output detour; no component motion or promotion."""
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
SOURCE = ROOT / 'experiments/busbars/cap-ground-repair-20261106/candidate/board.kicad_pcb'
SHA = '1512d4f046daebaba629ac29db4bc5caf2d53bc6ccf370e44deb903c4259b045'
CUT = '25bba609-ee8a-4547-9df7-c906cfc0979c'
CUTS = [CUT, 'ce87700c-30d7-439e-b3db-eba7d0ab58d1', '57598e07-197c-412f-89d0-b07235644a5b']
HINT = 'atx-24pin-rev3'
# Translate the diagonal 0.10 mm left; adjacent horizontal legs compensate.
# This gives the conditional Ground seat space without adding route length,
# tiny elbows, a new barrel, or an electrical topology change.
POINTS = [(13.208988, 47.), (15.9, 47.), (21.9, 53.), (25.317675, 53.)]


def main():
    import pcbnew as p
    import cec_force_current as force
    import cec_fr as fr
    import cec_full_current_planar_reflow as reflow
    import cec_additive_route_receiving as additive
    import cec_source_literal_retirement as literal_cut
    import cec_source_literal_additions as literal_add
    import cec_source_retaining_ses_import as raw
    from cec_native_items import discard_items
    start = time.monotonic()
    assert force._hash(SOURCE) == SHA
    board = p.LoadBoard(str(SOURCE))
    track = next(t for t in board.GetTracks() if force._uid(t) == CUT)
    proposal = reflow.plan(board, SOURCE, board_hint=HINT, retired_track_uuids=CUTS,
                          timeout_s=10., max_source_track_mm=9.)
    width, layer, code = track.GetWidth(), track.GetLayer(), track.GetNetCode()
    if '--inventory' in sys.argv:
        print(json.dumps([dict(uuid=force._uid(t), start_nm=list(t.GetStart()),
            end_nm=list(t.GetEnd()), width_nm=t.GetWidth()) for t in board.GetTracks()
            if t.GetClass() == 'PCB_TRACK' and t.GetNetCode() == code and t.GetLayer() == layer], indent=2))
        return
    assert width == 477370 and layer == p.B_Cu
    assert tuple(track.GetStart()) == (16000000, 47000000)
    assert tuple(track.GetEnd()) == (22000000, 53000000)
    index = fr._identified_foreign_shape_indexes(board, layer, {code})
    rows = []
    for a, b in zip(POINTS, POINTS[1:]):
        u, v = p.VECTOR2I_MM(*a), p.VECTOR2I_MM(*b)
        rows.append(dict(start_mm=a, end_mm=b,
            foreign_clear=fr._tap_foreign_clear(board, u, v, width, layer, 200000, {code}),
            blockers=fr._snapshot_foreign_blockers(u, v, width, 200000, *index, limit=20),
            edge_clear=fr._edge_leg_clear(board, u, v, (width + 1) // 2),
            rules=force._native_track_rule_hits(board, p.SHAPE_SEGMENT(u, v, width), layer)))
    report = dict(source=str(SOURCE), source_sha256=SHA, proposal=proposal, legs=rows,
                  width_nm=width, old_length_mm=proposal['original_length_nm']/1e6,
                  new_length_mm=sum(math.dist(a,b) for a,b in zip(POINTS,POINTS[1:])),
                  saved=False, accepted=False)
    if '--construct' in sys.argv and all(r['foreign_clear'] and r['edge_clear'] and not r['rules'] for r in rows):
        target = WORK / 'output-prefix-v1'
        assert not target.exists(), 'fresh_candidate_required'
        target.mkdir()
        discard_items(board, [t for t in board.GetTracks() if force._uid(t) in CUTS])
        added = []
        for a, b in zip(POINTS, POINTS[1:]):
            t = p.PCB_TRACK(board)
            t.SetStart(p.VECTOR2I_MM(*a)); t.SetEnd(p.VECTOR2I_MM(*b))
            t.SetWidth(width); t.SetLayer(layer); t.SetNetCode(code); t.SetLocked(True)
            board.Add(t); added.append(force._uid(t))
        additive._ground_refill(board)
        native = target / 'native-construction.kicad_pcb'
        p.PCB_IO_KICAD_SEXPR().SaveBoard(str(native), board)
        ground = [force._uid(z) for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname() == 'GND']
        text = literal_add.assemble(literal_cut.subtract(raw.raw_text(SOURCE), set(CUTS)),
                                    raw.raw_text(native), ground_ids=ground)
        candidate = force._copy_family(SOURCE, target / 'candidate')
        raw.write_raw(candidate, text)
        report.update(saved=True, candidate=str(candidate), candidate_sha256=force._hash(candidate),
                      added_track_uuids=added, retired_track_uuids=CUTS)
    assert force._hash(SOURCE) == SHA
    report['elapsed_s'] = time.monotonic() - start
    (WORK / ('output-prefix-construction.json' if '--construct' in sys.argv else 'output-prefix-probe-v2.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

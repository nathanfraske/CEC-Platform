"""Source-owned full-current VBUS detour for the selected front bar landing.

Does not install a bar or grant assembly/current qualification. Only the named
source chain is retired; the same current authority, width and face remain.
Exact native boundary replay decides whether that cut is legal.
"""
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from cec_pipeline.native import _native
p, _ = _native()
import cec_force_current as force
import cec_full_current_planar_reflow as reflow
import cec_fr as fr
import cec_additive_route_receiving as syntax
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items

SOURCE = ROOT / 'experiments/repack/bar-corridor-20261106/c9-corrective-v4/candidate/board.kicad_pcb'
EXPECTED = 'b118546af6665d77b190a9ac8ce3132cde413d607cdb3d9b28ba620a3857be24'
OUT = Path(__file__).parent / 'vbus-shortcut-v6'
CUT = '3a9c7bab-efb6-5496-8d7b-23ded11b3e34'
CUT_CONTINUATION = '95f87615-b822-460c-b944-e07c223873d7'
CUTS = {CUT, CUT_CONTINUATION, '9fd9a83f-0abb-4262-b709-962889bb3cce',
        '0fd90804-783b-4812-82a6-e13f375d3c5b'}


def bounded(fn):
    def expired(*_):
        raise TimeoutError('ten_second_native_lease')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 10)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def main():
    assert force._hash(SOURCE) == EXPECTED
    assert not (OUT / 'construction.json').exists()
    OUT.mkdir(exist_ok=True)
    b = p.LoadBoard(str(SOURCE))
    proposal = bounded(lambda: reflow.plan(b, SOURCE, board_hint='atx-24pin-rev3',
                                          retired_track_uuids=sorted(CUTS), timeout_s=9.5))
    force._write(OUT / 'proposal.json', proposal)
    old = next(t for t in b.GetTracks() if force._uid(t) == CUT)
    face, net, width = old.GetLayer(), old.GetNetCode(), old.GetWidth()
    a, z = p.VECTOR2I(old.GetStart()), p.VECTOR2I_MM(77.4, 53.2)
    lock = old.IsLocked()
    before = {force._uid(t) for t in b.GetTracks()}
    discard_items(b, [t for t in b.GetTracks() if force._uid(t) in CUTS])
    # Native rectangular enlarged-copper allocation; proposed solder/paste is
    # deliberately not asserted to be approved by the manufacturer/assembler.
    holder = p.FOOTPRINT(b)
    exclusion = p.PAD(holder)
    exclusion.SetShape(p.PAD_SHAPE_RECT)
    exclusion.SetAttribute(p.PAD_ATTRIB_SMD)
    exclusion.SetPosition(p.VECTOR2I_MM(71, 56.6))
    exclusion.SetSize(p.VECTOR2I(3230592, 3230592))
    layers = p.LSET()
    layers.AddLayer(face)
    exclusion.SetLayerSet(layers)
    holder.Add(exclusion)
    cache = {}

    def guard(left, right, half):
        segment = p.SHAPE_SEGMENT(left, right, width)
        return (fr._edge_leg_clear(b, left, right, half)
                and not exclusion.GetEffectiveShape(face).Collide(segment, 200000)
                and not force._native_track_rule_hits(b, segment, face, cache=cache))

    # Receive the complete source dogleg, not a detour which doubles back over
    # its retained neighbor. This shorter path is useful even without a bar.
    points = [a, p.VECTOR2I_MM(73.8,54.2), p.VECTOR2I_MM(74.6,55),
              p.VECTOR2I_MM(76.9,55), p.VECTOR2I_MM(77.4,54.5), z]
    legs = list(zip(points, points[1:]))
    clear = bounded(lambda: all(guard(left, right, width//2)
        and fr._tap_foreign_clear(b, left, right, width, face, 200000, {net}, foreign_cache=cache)
        for left, right in legs))
    if not clear:
        force._write(OUT / 'refusal.json', dict(reason='no_full_current_guarded_detour',
                                               source_sha256=EXPECTED, admitted=False))
        print('REFUSED no guarded route')
        return
    for leg in legs:
        t = p.PCB_TRACK(b)
        t.SetStart(leg[0]); t.SetEnd(leg[1]); t.SetWidth(width)
        t.SetLayer(face); t.SetNetCode(net); t.SetLocked(lock)
        b.Add(t)
    bounded(lambda: syntax._ground_refill(b))
    native = OUT / 'native-construction.kicad_pcb'
    p.PCB_IO_KICAD_SEXPR().SaveBoard(str(native), b)
    _, new = syntax._nodes(native)
    spans = raw.inventory(raw.raw_text(SOURCE))
    text = raw.raw_text(SOURCE)
    changed = {force._uid(q) for q in b.Zones()
               if not q.GetIsRuleArea() and q.GetNetname() == 'GND'}
    for uid in sorted(CUTS | changed, key=lambda uid: spans[uid][0], reverse=True):
        start, end = spans[uid]
        text = text[:start] + ('' if uid in CUTS else syntax._render(new[uid])) + text[end:]
    added = {force._uid(t) for t in b.GetTracks()} - before
    end = text.rfind(')')
    text = text[:end] + '\n' + '\n'.join(syntax._render(new[u]) for u in sorted(added)) + '\n' + text[end:]
    candidate = force._copy_family(SOURCE, OUT / 'candidate')
    raw.write_raw(candidate, text)
    assert force._hash(SOURCE) == EXPECTED
    force._write(OUT / 'construction.json', dict(
        source=str(SOURCE), source_sha256=EXPECTED, candidate=str(candidate),
        candidate_sha256=force._hash(candidate), retired_track_uuids=sorted(CUTS),
        added_track_uuids=sorted(added), source_proposal=proposal,
        path_nm=[list(legs[0][0])] + [list(leg[1]) for leg in legs],
        method='explicit_native_guarded_whole_chain_45_degree_shortcut',
        bar_installed=False, routing_admitted=False, current_qualified=False))
    result = bounded(lambda: reflow.receive(SOURCE, candidate, board_hint='atx-24pin-rev3',
                                            retired_track_uuids=sorted(CUTS), timeout_s=9.5))
    force._write(OUT / 'planar-receiving.json', result)
    print(json.dumps(dict(candidate=str(candidate), sha256=force._hash(candidate),
                          receiving_ok=result['ok'], errors=result['errors'])))


if __name__ == '__main__':
    main()

"""One explicit private path, using the existing independently received owner.

The ordinary drafting API deliberately refuses typed consumer-allocation
rewrites. This experiment uses that allocation's real planar reconstruction
authority. No current, terminal, tap, barrel, width or layer is changed.
Whole-board clearance, placement and stack receiving remain separate.
"""
from pathlib import Path
import argparse
import json
import sys
import uuid

sys.path.insert(0, 'ops')
from cec_pipeline.native import _native
from cec_pipeline import geometry
import cec_planar_consumer_reconstruction as owner
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force

CUT = ['793ec4bb-c61e-43de-9daa-b9e3f9f97811',
       '69e79220-ec09-4c8f-9ed3-3d404d37745a',
       'f9684df9-9180-4722-9968-32b6a2e9bf75']
POINTS = [[29_899_400,65_491_600],[31_184_999,66_777_199],
          [50_222_801,66_777_199],[56_000_000,61_000_000]]


def main(source, expected_sha256, out):
    assert force._hash(source) == expected_sha256
    pcb, quiet = _native()
    board = pcb.LoadBoard(str(source))
    scope = owner.plan(board, source, board_hint='atx-24pin-rev3',
                       retired_track_uuids=CUT, timeout_s=10.)
    live = {t.m_Uuid.AsString(): t for t in board.GetTracks()}
    exemplar = live[CUT[0]].Duplicate()
    points = geometry.path(POINTS, minimum_phase_nm=20_000)
    new = []
    for index, (a, z) in enumerate(zip(points, points[1:])):
        t = exemplar.Duplicate()
        key = str(uuid.uuid5(uuid.NAMESPACE_URL, expected_sha256+':typed-transit:'+str(index)))
        assert key not in live
        t.m_Uuid.Clone(pcb.KIID(key))
        t.SetStart(pcb.VECTOR2I(*a)); t.SetEnd(pcb.VECTOR2I(*z)); new.append(t)
    owner.subtract(board, scope)
    for t in new: board.Add(t)
    owner.assign(board, scope, [force._uid(t) for t in new], [])
    additive._ground_refill(board)
    child = force._copy_family(source, out)
    field._save_field_snapshot(board, child)
    proof = owner.receive(source, child, board_hint='atx-24pin-rev3',
                          retired_track_uuids=CUT, timeout_s=10.)
    result = dict(schema=1, source=str(source), source_sha256=expected_sha256,
                  candidate=str(child), candidate_sha256=force._hash(child),
                  source_scope=scope, replacement_points_nm=points,
                  independently_received=proof, routing_admitted=False,
                  whole_board_qualified=False, release_authority=False)
    force._write(out/'construction.json', result)
    print(json.dumps(dict(candidate=str(child), source_sha256=expected_sha256,
                          candidate_sha256=result['candidate_sha256'],
                          owner_ok=proof['ok'], errors=proof['errors'],
                          routing_admitted=False)))
    assert proof['ok'] and proof['complete'] and not proof['errors']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('expected_sha256')
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    main(args.source, args.expected_sha256, args.out)

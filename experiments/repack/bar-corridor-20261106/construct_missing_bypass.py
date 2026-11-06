"""Explicit missing-bypass pilot; private geometry, not admission authority.

Resolve the real missing Source role and its independently owned supply leaf.
Keep every existing barrel and all unowned copper. Whole saved receiving is
mandatory; this script never promotes a candidate or edits source designs.
"""
import argparse
import copy
import json
from pathlib import Path
import signal
import time

from cec_pipeline.native import _native
p, _ = _native()
from cec_pipeline import cells
import cec_additive_route_receiving as syntax
import cec_decoupler_cell as decoupling
import cec_force_current as force
import cec_fr as fr
import cec_measurement_leaf as leaf
import cec_missing_bypass_repair as repair
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items
from native_pair_v13 import soften


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--intent', type=Path, required=True)
    ap.add_argument('--board-hint', required=True)
    ap.add_argument('--pose', type=float, nargs=3, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--replace-ground-via')
    args = ap.parse_args()
    source = args.source.resolve(strict=True); out = args.output.resolve()
    if out.exists(): raise ValueError('fresh_private_directory_required')
    if args.pose[2] not in (0, 90, 180, 270): raise ValueError('cardinal_pose_required')
    intent = json.loads(args.intent.read_text())
    out.mkdir(parents=True)
    def report(name, value):
        (out/(name+'.json')).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    def timed(call):
        def expired(*unused): raise TimeoutError('bounded_native_pilot_stage_expired')
        previous = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, 10.)
        try: return call()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.)
            signal.signal(signal.SIGALRM, previous)
    role = repair.plan(source, intent, board_hint=args.board_hint)
    report('role', role)
    board = p.LoadBoard(str(source))
    cap = board.FindFootprintByReference(role['capacitor_ref'])
    if any(g.ContainsItem(cap) for g in board.Groups()):
        raise ValueError('grouped_cap_requires_independent_annotation_transport')
    if ((cap.GetPosition().x/1e6-args.pose[0])**2
            +(cap.GetPosition().y/1e6-args.pose[1])**2)**.5 > 6:
        raise ValueError('bounded_local_translation_required')
    supply = next(pad for pad in cap.Pads() if pad.GetNetname()==role['requirement']['rail'])
    ground = next(pad for pad in cap.Pads() if pad.GetNetname()=='GND')
    barrel = None
    if args.replace_ground_via:
        import cec_corrective_bypass_ground_barrel as ground_barrel
        barrel = ground_barrel.plan(source,intent,ground_pad_uuid=force._uid(ground),
            via_uuid=args.replace_ground_via,board_hint=args.board_hint,
            allow_locked_via_uuid=args.replace_ground_via)
        report('source-ground-barrel',barrel)
    owned = leaf.plan_missing_bypass_supply(board, force._uid(supply),
        board_hint=args.board_hint, missing_bypass_intent=intent)
    report('source-supply-leaf', owned)
    retired = set(owned['track_uuids'])
    retired_vias = {args.replace_ground_via} if barrel else set()
    before = {force._uid(t) for t in board.GetTracks()}
    discard_items(board, [t for t in board.GetTracks() if force._uid(t) in retired|retired_vias])
    cap.SetOrientationDegrees(args.pose[2])
    cap.SetPosition(p.VECTOR2I(*(round(v*1e6) for v in args.pose[:2])))
    # Never grant a ground cut merely because no linear source leaf exists.
    # The existing process-aware primitive adds or reuses a local return.
    diagnostics = {}
    result, refusal = timed(lambda: decoupling._add_ground_return(board, ground,
        board_path=str(source), reach_mm=.8, lock=bool(barrel), diagnostics=diagnostics))
    report('ground-construction', dict(result={k:v for k,v in (result or {}).items() if k!='items'},
        refusal=refusal, diagnostics=diagnostics))
    if refusal or not result:
        print(json.dumps(dict(ground_return=False, candidate_written=False, reason=refusal))); return
    a = tuple(supply.GetPosition())
    # Retain the actual last-edge aperture into the shared Source junction.
    # A shortest approach from another angle can acquire the body of a
    # same-net branch even though foreign-net DRC stays clean.
    entry, z = map(tuple,owned['source_boundary_entry_nm'])
    width, face, net = owned['width_nm'], owned['layer'], owned['net']
    cache = {}
    def guard(left, right, half):
        return (fr._edge_leg_clear(board,left,right,half)
            and not force._native_track_rule_hits(board,p.SHAPE_SEGMENT(left,right,width),face,cache=cache))
    legs = timed(lambda: fr._guarded_profiled_lastmile_legs(board,p.VECTOR2I(*a),p.VECTOR2I(*entry),
        width,face,200000,board.GetNetcodeFromNetname(net),guard,allow_maze=True,
        maze_margin_mm=3.,foreign_cache=cache,deadline_monotonic=time.monotonic()+9.,
        max_length_nm=12000000,refine_maze=True,refinement_grids_mm=(.2,.1)))
    if not legs:
        report('route-refusal',dict(a_nm=a,b_nm=z,width_nm=width,layer=board.GetLayerName(face)))
        print(json.dumps(dict(supply_route=False,candidate_written=False))); return
    route = dict(net=net,layer=board.GetLayerName(face),width_nm=width,
        points_nm=soften([tuple(legs[0][0])]+[tuple(leg[1]) for leg in legs]+[z]))
    # The old supply authority stays immutable. Only the geometrical root
    # kernel follows the exact just-performed capacitor pose; the Source
    # junction and every forbidden same-net contact remain unchanged.
    projected_guard = copy.deepcopy(owned)
    projected_guard['points_nm'][0] = list(a)
    path_diagnostics = {}
    clear = timed(lambda: leaf.path_clear(board,projected_guard,route['points_nm'],
        diagnostics=path_diagnostics))
    report('supply-path-guard',dict(**path_diagnostics,route=route))
    if not clear:
        print(json.dumps(dict(supply_route=False,candidate_written=False,reason=path_diagnostics))); return
    cells.emit_connections(board,[route],[],identity='missing-bypass-corrective-pilot:'+intent['capacitor_uuid'])
    timed(lambda: syntax._ground_refill(board))
    # Render only the moved footprint, Ground fills and new copper. All other
    # native source nodes, including every non-Ground pour, remain literal.
    native = out/'native-construction.kicad_pcb'
    p.PCB_IO_KICAD_SEXPR().SaveBoard(str(native), board)
    root, old = syntax._nodes(source); _, new = syntax._nodes(native)
    added = {force._uid(t) for t in board.GetTracks()}-before
    changed = {intent['capacitor_uuid']} | {force._uid(z) for z in board.Zones()
        if z.GetNetname()=='GND' and not z.GetIsRuleArea()}
    inventory = raw.inventory(raw.raw_text(source)); text = raw.raw_text(source)
    for uid in sorted(changed|retired|retired_vias,key=lambda u:inventory[u][0],reverse=True):
        start,end = inventory[uid]
        text = text[:start]+('' if uid in retired|retired_vias else syntax._render(new[uid]))+text[end:]
    end = text.rfind(')')
    text = text[:end]+'\n'+'\n'.join(syntax._render(new[u]) for u in sorted(added))+'\n'+text[end:]
    candidate = force._copy_family(source,out/'candidate')
    raw.write_raw(candidate,text)
    record = dict(source=str(source),source_sha256=intent['source_sha256'],candidate=str(candidate),
        candidate_sha256=force._hash(candidate),intent=intent,board_hint=args.board_hint,
        pose=args.pose,capacitor_ref=role['capacitor_ref'],retired_track_uuids=sorted(retired),
        retired_via_uuids=sorted(retired_vias),ground_replacement_via_uuid=result['via_uuid'] if barrel else None,
        changed_source_uuids=sorted(changed),added_track_uuids=sorted(added),supply_route=route,
        complete_saved_receiving_required=True,admitted=False,release_authority=False)
    report('construction',record)
    print(json.dumps(dict(candidate=str(candidate),sha256=record['candidate_sha256'],not_received=True)))


if __name__=='__main__': main()

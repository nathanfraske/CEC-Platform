"""Bounded via-access re-seating of fully isolated ordinary two-land supports.

Derive eligibility and poses from the immutable native source. A tiny passive
trapped over frozen power copper can use a legal nearby barrel aperture; no
power/sense/pair terminal, connected source land or priority bus may move.
The existing preclear/route constructor and independent pose/delta receiver
remain mandatory. A finite refused menu is not a global no-path proof.
"""
import argparse
import json
import math
from pathlib import Path

import pcbnew
import cec_endpoint_via_access as access
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_support_motion as motion
import cec_support_pivot as pivot
import cec_support_pivot_receiving as receiving
import cec_fab_profile as fab
import cec_pose_copper_score as native_pose


def targets(board, source, *, board_hint, include_anchored_pivots=False):
    if type(include_anchored_pivots) is not bool:raise ValueError('explicit_anchored_pivot_mode_required')
    eligible = ordinary.eligible_nets(board, source, board_hint)
    graph = fr._read_only_route_connectivity(board)
    rows = []
    for fp in board.GetFootprints():
        domain = motion.capture(board, dict(ref=fp.GetReference()), motion.limits())
        pads = list(fp.Pads())
        if (not domain['ok'] or len(pads) != 2
                or len({str(p.GetNumber()) for p in pads}) != 2):
            continue
        isolated=[p for p in pads if receiving.source_land_isolated(board,p,graph)]
        anchored=(include_anchored_pivots and len(isolated)==1 and
            receiving._fixed_land(next(p for p in pads if p not in isolated)) is not None and
            any(i.GetNetCode()==next(p for p in pads if p not in isolated).GetNetCode()
                and force._uid(i)!=force._uid(next(p for p in pads if p not in isolated))
                for i in graph.GetConnectedItems(next(p for p in pads if p not in isolated))))
        if not (len(isolated)==2 and all(str(p.GetNetname()) in eligible for p in pads)) and not anchored:
            continue
        # There must be a real other source terminal, not just a declaration
        # of an unrouted/NC net or a guessed peer coordinate.
        peers = [p for owner in board.GetFootprints() for p in owner.Pads()
            if owner.GetReference() != fp.GetReference()]
        for pad in isolated:
            if str(pad.GetNetname()) not in eligible:continue
            same = [p for p in peers if p.GetNetCode() == pad.GetNetCode()]
            if not same:
                continue
            nearest = min(math.dist(tuple(pad.GetPosition()), tuple(p.GetPosition())) for p in same)
            rows.append(dict(ref=fp.GetReference(), pad_uuid=force._uid(pad),
                target_net=str(pad.GetNetname()), motion='toward_endpoint',
                companion_refs=[], nearest_source_terminal_mm=nearest/1e6,
                source_isolated_pad_uuids=sorted(force._uid(p) for p in isolated),
                fully_isolated_reseat=not anchored,
                fixed_pad_uuid=(force._uid(next(p for p in pads if p not in isolated)) if anchored else None)))
    return sorted(rows, key=lambda r:(r['nearest_source_terminal_mm'], r['ref'], r['pad_uuid']))


def anchored_proposals(board,target,*,source):
    """Actual cardinal pivots around an exact retained native source land.

    These have only three possible poses. An attached supply/ground land is
    never translated, even if an attractive bounding box suggests doing so.
    Exact native land shape, POFV owner, foreign clearance and saved receiving
    remain obligations; the proposal alone owns no copper or ampacity.
    """
    fp=board.FindFootprintByReference(target['ref']);origin=pcbnew.VECTOR2I(fp.GetPosition());angle=fp.GetOrientationDegrees()
    pads={force._uid(p):p for p in fp.Pads()};anchor=pads[target['fixed_pad_uuid']];orphan=pads[target['pad_uuid']]
    fixed_position=pcbnew.VECTOR2I(anchor.GetPosition());fixed_identity=receiving._fixed_land(anchor)
    domain=motion.capture(board,target,motion.limits());scorer=native_pose.NativePoseCopperScore(board,target['ref'],(),generated_locked_uuids=())
    profile=fab.PROFILES.get(fab.board_profile_name(board));preferred=fab.preferred_pofv_geometry(profile)
    geometries=(fab.local_pofv_geometry_candidates(profile) if preferred else [fab.board_legal_through_via_geometry(board,.6,.3)[:2]])
    spec=fr._project_netclass_resolver(str(source))(orphan.GetNetname()) or {}
    gap=max(board.GetDesignSettings().m_MinClearance,pcbnew.FromMM(spec.get('clearance') or .2));results=[]
    stationary=[other.GetBoundingBox(False,False) for other in board.GetFootprints()
        if other.GetReference()!=fp.GetReference() and other.GetLayer()==fp.GetLayer()]
    try:
        for turn in (90.,180.,270.):
            fp.SetPosition(origin);fp.SetOrientationDegrees(angle)
            fp.SetOrientationDegrees(angle+turn);fp.Move(fixed_position-anchor.GetPosition())
            if receiving._fixed_land(anchor)!=fixed_identity:continue
            candidate=dict(dx_mm=(fp.GetPosition().x-origin.x)/1e6,dy_mm=(fp.GetPosition().y-origin.y)/1e6,
                rotation_delta_deg=turn,generator='exact_native_attached_land_pivot')
            if not motion.evaluate(domain,candidate)['ok']:continue
            point=pcbnew.VECTOR2I(orphan.GetPosition());box=fp.GetBoundingBox(False,False)
            overlap=sum(max(0,min(box.GetRight(),other.GetRight())-max(box.GetLeft(),other.GetLeft()))*
                max(0,min(box.GetBottom(),other.GetBottom())-max(box.GetTop(),other.GetTop())) for other in stationary)
            if overlap:continue
            for diameter,drill in geometries:
                if not fr._edge_leg_clear(board,point,point,pcbnew.FromMM(diameter)//2):continue
                blocker,lands=fab.via_at_pad_conflicts(board,point,pcbnew.FromMM(diameter),pcbnew.FromMM(drill),orphan.GetNetCode())
                if blocker is not None or (preferred and not lands):continue
                if not fr._via_spot_clear(board,point,pcbnew.FromMM(diameter),gap,{orphan.GetNetCode()},
                    drill_nm=pcbnew.FromMM(drill),net_code=orphan.GetNetCode(),foreign_cache={}):continue
                candidate['endpoint_via_aperture']=dict(ref=target['ref'],pad=orphan.GetNumber(),
                    via_mm=[point.x/1e6,point.y/1e6],diameter_mm=diameter,drill_mm=drill,
                    approximate_body_overlap_mm2=0.,release_authority=False)
                # Score only after collecting the posed aperture; this helper
                # deliberately restores the immutable original board poses.
                fp.SetPosition(origin);fp.SetOrientationDegrees(angle)
                candidate['native_copper']=scorer.score(candidate)
                results.append(candidate);break
        return results
    finally:fp.SetPosition(origin);fp.SetOrientationDegrees(angle)


def run(source, directory, *, board_hint, source_sha256, max_trials=4, timeout_s=10.,
        radius_mm=6.,include_anchored_pivots=False,allow_support_field_reflow=False):
    if type(include_anchored_pivots) is not bool or type(allow_support_field_reflow) is not bool:
        raise ValueError('explicit_anchored_pivot_and_field_modes_required')
    if (type(max_trials) is not int or not 1 <= max_trials <= 8
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10
            or type(radius_mm) not in (int,float) or not math.isfinite(radius_mm)
            or not 0 < radius_mm <= 6):
        raise ValueError('bounded_orphan_access_work_required')
    source, directory = Path(source).resolve(), Path(directory).resolve()
    if directory.exists() or force._hash(source) != source_sha256:
        raise ValueError('fresh_orphan_access_output_and_exact_source_required')
    family, code = force._family(source, board_hint), force._code_identity()
    directory.mkdir(parents=True)
    board = pcbnew.LoadBoard(str(source))
    report = dict(schema=1, scope='bounded_source_isolated_support_via_access',
        source=str(source), source_sha256=source_sha256, trials=[], targets=[],
        ok=False, routing_admitted=False, release_authority=False,
        power_authority=False, no_path_proof=False, radius_mm=radius_mm)
    seen = set()
    for target in targets(board, source, board_hint=board_hint,include_anchored_pivots=include_anchored_pivots)[:8]:
        # Native endpoint access derives legal through-barrel locations and
        # actual transformed support lands, not an attractive empty bbox.
        before = [tuple(p.GetPosition()) for fp in board.GetFootprints() for p in fp.Pads()]
        poses = (anchored_proposals(board,target,source=source) if target['fixed_pad_uuid'] else
            access.proposals(board, target, board_path=str(source),
                radius_mm=radius_mm, max_sites=128, limit=32, diverse_menu=True,cardinal_rotations=True))
        # This minimum-motion tier has no incident-copper retirement scope.
        # A barrel-sized aperture is insufficient if another source land or
        # the complete passive body is still obstructed. Keep finite legal
        # candidates ahead of expensive route attempts, never relax receiving.
        poses=[p for p in poses if p['native_copper']['new_copper_pairs']==0
            and p['endpoint_via_aperture']['approximate_body_overlap_mm2']==0]
        assert before == [tuple(p.GetPosition()) for fp in board.GetFootprints() for p in fp.Pads()]
        report['targets'].append(dict(target=target, via_access_pose_count=len(poses)))
        fp = board.FindFootprintByReference(target['ref'])
        origin = tuple(fp.GetPosition()); angle = fp.GetOrientationDegrees()
        for proposal in poses:
            key = (target['ref'],proposal['dx_mm'],proposal['dy_mm'],proposal['rotation_delta_deg'])
            if key in seen:
                continue
            seen.add(key)
            if len(report['trials']) >= max_trials:
                break
            pose = [origin[0]/1e6+proposal['dx_mm'], origin[1]/1e6+proposal['dy_mm'],
                (angle+proposal['rotation_delta_deg'])%360]
            recipe = dict(source_sha256=source_sha256, fully_isolated_reseat=target['fully_isolated_reseat'],
                allow_support_field_reflow=allow_support_field_reflow,poses={target['ref']:pose})
            trial_dir = directory/('trial-'+str(len(report['trials'])))
            result = pivot.run(source, recipe, trial_dir, board_hint=board_hint, timeout_s=timeout_s)
            row = dict(target=target, source_derived_pose=proposal, recipe=recipe, result=result)
            report['trials'].append(row)
            if result['ok']:
                report.update(ok=True, board=result['board'], board_sha256=result['board_sha256'],
                    source_opens=result['source_opens'], opens=result['opens'])
            force._write(directory/'receiving.json',report)
            if report['ok']:
                break
        if report['ok'] or len(report['trials']) >= max_trials:
            break
    report['source_and_code_unchanged'] = family == force._family(source,board_hint) and code == force._code_identity()
    if not report['source_and_code_unchanged']:
        report['ok'] = False
    force._write(directory/'receiving.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--source-sha256',required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--hint',required=True)
    parser.add_argument('--max-trials',type=int,default=4)
    parser.add_argument('--seconds',type=float,default=10.)
    parser.add_argument('--radius-mm',type=float,default=6.)
    parser.add_argument('--include-anchored-pivots',action='store_true')
    parser.add_argument('--allow-support-field-reflow',action='store_true')
    args=parser.parse_args()
    result=run(args.source,args.out,board_hint=args.hint,source_sha256=args.source_sha256,
        max_trials=args.max_trials,timeout_s=args.seconds,radius_mm=args.radius_mm,
        include_anchored_pivots=args.include_anchored_pivots,allow_support_field_reflow=args.allow_support_field_reflow)
    print(json.dumps({k:result.get(k) for k in ('ok','source_opens','opens','board','source_and_code_unchanged')}))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())

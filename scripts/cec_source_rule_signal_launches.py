"""Existing-rule local SMD signal launches; no remote small-via authority.

This read-only geometry menu grants no electrical role or routing admission.
Only the literal saved local POFV rule owns these local barrels. The caller
must independently type the net and receive the complete saved transaction.
"""
import math
import time
from pathlib import Path

import pcbnew
import cec_existing_local_pofv_pad_rule as rule
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_pad_face_launch as faces
import cec_native_contained_via_events as contained_events


def _immutable_power_clear(board,start,end,width,layer,gap,net_code):
    segment=pcbnew.SHAPE_SEGMENT(start,end,width)
    resolve=fr._foreign_clearance_resolver(board)
    for zone in board.Zones():
        if (zone.GetIsRuleArea()or zone.GetNetCode()==net_code
                or zone.GetNetname()=='GND'or not zone.IsOnLayer(layer)):continue
        if not zone.IsFilled()or not zone.HasFilledPolysForLayer(layer):return False
        clearance=max(gap,int(zone.GetLocalClearance()),int(resolve(zone,layer)))
        if zone.GetFilledPolysList(layer).Collide(segment,clearance):return False
    return True


def propose(board,pad,*,width_nm,clearance_nm,route_layers,deadline,max_sites=4,
        contained_intervals_only=False):
    """Actual-land face events, not aliases of retained native contacts.

    Every local prefix still needs the full route's field/craft guard and
    saved native/source/current receiving. GND refill is not power-void
    authority: every other foreign filled zone stays an immutable obstacle.
    """
    enabled=set(map(int,board.GetEnabledLayers().CuStack()));layers=tuple(route_layers)
    planes={int(board.GetLayerID(n))for n in fr.plane_layers(board)}
    profile=fab.PROFILES.get(fab.board_profile_name(board))
    if profile:
        planes.update(int(board.GetLayerID(n))for n,role in zip(fab.COPPER_LAYERS,profile['roles'])if role=='GND')
    if (type(width_nm)is not int or width_nm<max(1,board.GetDesignSettings().m_TrackMinWidth)
            or type(clearance_nm)is not int or clearance_nm<=0 or clearance_nm<board.GetDesignSettings().m_MinClearance
            or not 1<=len(layers)<=8 or len(set(layers))!=len(layers)
            or any(type(l)is not int or l not in enabled or l in planes for l in layers)
            or type(deadline)not in(int,float)or not math.isfinite(deadline)
            or deadline>time.monotonic()+10. or type(max_sites)is not int or not 1<=max_sites<=8
            or type(contained_intervals_only)is not bool):
        raise ValueError('bounded_exact_saved_rule_signal_launch_required')
    result=dict(scope='existing_source_rule_local_signal_launch_geometry',choices=[],complete=False,
        proposed_not_retained_native_contacts=True,ordinary_middle_via_floors_unchanged=True,
        electrical_role_qualified=False,current_qualified=False,routing_admitted=False,release_authority=False,
        contained_intervals_only=contained_intervals_only)
    if time.monotonic()>=deadline:result['reason']='source_local_launch_deadline';return result
    context=rule.resolve(board,pad)
    if context is None:result['reason']='no_exact_existing_source_local_pad_rule';return result
    groups=[g for g in board.Groups()if g.GetName()==rule.GROUP]
    saved=pcbnew.LoadBoard(context['source']);original=[g for g in saved.Groups()if g.GetName()==rule.GROUP]
    if (len(groups)!=1 or len(original)!=1 or groups[0].IsLocked()or groups[0].GetParentGroup()
            or force._uid(groups[0])!=force._uid(original[0])
            or original[0].IsLocked()!=groups[0].IsLocked()
            or sorted(force._uid(v)for v in groups[0].GetItems())!=sorted(force._uid(v)for v in original[0].GetItems())):
        result['reason']='unchanged_unlocked_existing_source_local_group_required';return result
    actual=tuple(map(int,pad.GetLayerSet().CuStack()))
    if (len(actual)!=1 or actual[0]not in layers or actual[0]not in(pcbnew.F_Cu,pcbnew.B_Cu)
            or pad.GetParentFootprint().IsDNP()):
        result['reason']='one_populated_authorized_source_surface_required';return result
    source=Path(context['source']);before=force._family(source)
    diameter,drill=rule.geometry(context,(context['minimum_nm']['via_diameter']/1e6,
        context['minimum_nm']['hole_size']/1e6))
    dia,hole=round(diameter*1e6),round(drill*1e6);face=actual[0];net=pad.GetNetCode()
    if width_nm>dia:result['reason']='local_land_narrower_than_authored_signal';return result
    pos=pad.GetPosition();candidates=[dict(start=pos,end=pos,kind='contained_source_pad',normal=(0,0))]
    if not contained_intervals_only:
        candidates.extend(dict(r,kind='bounded_source_dogbone')for r in faces.candidates(
            pad,[(diameter,drill)],reach_mm=fab.LOCAL_POFV_REACH_MM))
        candidates.extend(dict(r,kind='bounded_source_radial_dogbone')for r in faces.radial_candidates(
            pad,[(diameter,drill)],reach_mm=fab.LOCAL_POFV_REACH_MM,
            distances_mm=tuple(fab.LOCAL_POFV_REACH_MM*f for f in(.5,2/3,5/6,1.))))
    # Cover each face before spending the menu on shifted aliases of one face.
    candidates.sort(key=lambda r:(r['kind']!='contained_source_pad',r['start']!=pos,
        math.dist(tuple(r['end']),tuple(pos)),r['normal'],tuple(r['start'])))
    cache={};holes=fr._via_hole_snapshot(board);seen=set();refused={}
    interval_report=None
    def rows():
        nonlocal interval_report
        yield from candidates
        # Default preserves the historical 45-site menu first. An explicit
        # independent contained-only tier avoids a geometrically legal but
        # route-fenced exterior launch starving the entire inset domain.
        # Both use the SAME caller deadline and unchanged native guards.
        if result['choices']or time.monotonic()>=deadline:return
        interval_report=contained_events.candidates(board,pad,dia,clearance_nm,
            deadline=deadline,max_events=24,foreign_cache=cache)
        if not interval_report['complete']:return
        for event in interval_report['events']:
            at=pcbnew.VECTOR2I(*event['at_nm'])
            yield dict(start=at,end=at,kind='contained_source_pad_interval',normal=(0,0))
    for row in rows():
        if time.monotonic()>=deadline:break
        start,at=row['start'],row['end'];key=(tuple(start),tuple(at))
        if key in seen:continue
        seen.add(key);contained=start==at
        # Cheap necessary geometry first. A negative containment/foreign
        # predicate need not reload the literal Source/rule. Positive sites
        # STILL take the unchanged complete native saved-rule inspector.
        if contained:
            if not fab._pad_contains_circle(pad,at,(dia+1)//2,tolerance_nm=0):
                why='source_pad_cannot_fully_contain_local_land';refused[why]=refused.get(why,0)+1;continue
        else:
            blocked,overlaps=fab.via_at_pad_conflicts(board,at,dia,hole,net)
            if blocked is not None or overlaps:
                why='source_local_land_overlaps_native_pad';refused[why]=refused.get(why,0)+1;continue
        if not all(fr._tap_foreign_clear(board,at,at,dia,l,clearance_nm,{net},foreign_cache=cache)for l in enabled):
            why='source_local_native_foreign_copper';refused[why]=refused.get(why,0)+1;continue
        owner=(dict(local_pofv_contained_pad=pad)if row['kind']=='contained_source_pad_interval'else
            dict(local_pofv_pad=pad)if contained else
            dict(local_pofv_dogbone=dict(pad=pad,start=start,layer=face)))
        detail={}
        if not fr._via_spot_clear(board,at,dia,clearance_nm,{net},drill_nm=hole,net_code=net,
                foreign_cache=cache,_via_holes=holes,report=detail,**owner):
            why=detail.get('reason','native_source_local_via_refused');refused[why]=refused.get(why,0)+1;continue
        if not (fr._edge_leg_clear(board,at,at,(dia+1)//2+clearance_nm)
                and fr._edge_leg_clear(board,start,at,(width_nm+1)//2+clearance_nm)
                and fr._tap_foreign_clear(board,start,at,width_nm,face,clearance_nm,{net},foreign_cache=cache)
                and _immutable_power_clear(board,start,at,width_nm,face,clearance_nm,net)
                and all(_immutable_power_clear(board,at,at,dia,l,clearance_nm,net)for l in enabled)):
            why='source_local_lead_edge_or_immutable_power';refused[why]=refused.get(why,0)+1;continue
        operations=[]if contained else[('trk',int(start.x),int(start.y),int(at.x),int(at.y),width_nm,face)]
        operations.append(('via',int(at.x),int(at.y),hole,dia))
        result['choices'].append(dict(at_nm=list(at),layers=list(layers),operations=operations,
            source_pad_uuid=force._uid(pad),kind=row['kind'],source_rule=context,
            actual_native_source_rule_preflight=detail.get('existing_native_local_pad_rule'),
            proposed_not_retained_native_contact=True,release_authority=False))
        if len(result['choices'])>=max_sites:break
    if before!=force._family(source):raise ValueError('source_local_launch_family_changed')
    result.update(complete=time.monotonic()<deadline and(interval_report is None or interval_report['complete']),
        refusals=refused,generated_face_candidates=len(candidates),examined=len(seen),
        contained_interval_discovery=interval_report,source_family_unchanged=True)
    return result

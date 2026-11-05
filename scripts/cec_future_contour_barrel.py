"""Source-derived ordinary-barrel seats that reserve future power contours.

Only an existing ordinary barrel and its independently owned endpoint legs
may move. GND, pairs, Kelvin/power material, pads, groups and undersized holes
remain protected by ordinary-barrel receiving. Reservations are NOT copper,
current authority or permission to manufacture the proposed power profile.
Full native DRC, fields, current, cuts and stack receiving remain mandatory.
"""
import argparse,hashlib,json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_field_coupling as field
import cec_fr as fr
import cec_ordinary_barrel_reseat as barrel
import cec_ordinary_route_receiving as ordinary
import cec_power_contours as audit
import cec_rectilinear_copper as contour
import cec_native_fill_geometry as native


def _search_geometry(radius,grid,source_leg):
    barrel.source_leg_budget_mm(source_leg)
    if (type(radius) not in (int,float) or not math.isfinite(radius) or not .05<=radius<=2.
            or type(grid) not in (int,float) or not math.isfinite(grid) or not .05<=grid<=1.
            or int(radius*1e6)//round(grid*1e6)<1
            or (2*(int(radius*1e6)//round(grid*1e6))+1)**2>4096):
        raise ValueError('finite_literal_future_contour_portal_work_required')


def _profiles(board,deadline):
    requests=audit.finding_requests(board,timeout_s=max(.001,min(10.,deadline-time.monotonic())),
        include_terminal_caps=True)
    if not requests['complete']:raise ValueError('complete_future_contour_inventory_required')
    if len(requests['requests'])>64:raise ValueError('future_contour_demand_bound')
    tracks={force._uid(t):t for t in board.GetTracks()};rows=[]
    for request in requests['requests']:
        contour._check_deadline(deadline)
        ids=[r['uuid'] for r in request['source_tracks']]
        if not 1<=len(ids)<=2 or len(set(ids))!=len(ids):raise ValueError('bounded_actual_contour_strokes_required')
        items=[tracks[u] for u in ids]
        if (any(t.GetClass()!='PCB_TRACK' or t.GetWidth()<1000000 for t in items)
                or len({(str(t.GetNetname()),int(t.GetLayer())) for t in items})!=1):
            raise ValueError('actual_same_face_wide_source_contour_required')
        shape=pcbnew.SHAPE_POLY_SET()
        for t in items:
            shape.BooleanAdd(contour._poly(contour.purposeful_envelope(contour._native_capsule(t),
                style='chamfer45',margin_nm=1000,grid_nm=1000)))
        row=dict(net=str(items[0].GetNetname()),layer_id=int(items[0].GetLayer()),
            source_track_uuids=sorted(ids),clearance_nm=_gap(board,str(items[0].GetNetname())),
            polygons_nm=native.snapshot(shape,deadline,
                max_vertices=4096,max_polygons=4))
        rows.append((row,shape))
    return rows


def _gap(board,net):
    spec=fr._project_netclass_resolver(board.GetFileName())(net) or {}
    return max(200000,int(board.GetDesignSettings().m_MinClearance),round(float(spec.get('clearance') or .2)*1e6))


def plan(source,*,board_hint,via_uuid,allow_owned_locked=False,radius_mm=.6,grid_mm=.1,
         max_source_leg_mm=8.,timeout_s=10.):
    """Finite source-only portal menu; no explicit target coordinates or Cu cut."""
    _search_geometry(radius_mm,grid_mm,max_source_leg_mm)
    deadline=barrel._budget(timeout_s);source=Path(source).resolve()
    epoch=force._code_identity();family=force._family(source,board_hint)
    b=pcbnew.LoadBoard(str(source));profiles=_profiles(b,deadline)
    via=next((t for t in b.GetTracks() if force._uid(t)==via_uuid and t.GetClass()=='PCB_VIA'),None)
    if via is None:raise ValueError('actual_source_future_contour_barrel_required')
    q=barrel.plan(b,source,via_uuid=via_uuid,board_hint=board_hint,
        allow_owned_locked=allow_owned_locked,max_source_leg_mm=max_source_leg_mm,
        timeout_s=max(.001,deadline-time.monotonic()))
    gap=_gap(b,q['net'])
    relevant=[r for r,s in profiles if s.Collide(via.GetEffectiveShape(r['layer_id']),max(gap,r['clearance_nm']))]
    if not relevant:raise ValueError('source_barrel_does_not_block_canonical_contour')
    menu=barrel.portal_candidates(source,via_uuid=via_uuid,board_hint=board_hint,
        allow_owned_locked=allow_owned_locked,radius_mm=radius_mm,grid_mm=grid_mm,
        max_source_leg_mm=max_source_leg_mm,timeout_s=max(.001,deadline-time.monotonic()))
    if not menu['ok'] or not menu['complete']:raise ValueError('complete_private_cut_barrel_menu_required:'+str(menu['errors']))
    probe=via.Duplicate();positions=[]
    for at in menu['portals_nm']:
        contour._check_deadline(deadline);probe.SetPosition(pcbnew.VECTOR2I(*at))
        if all(not s.Collide(probe.GetEffectiveShape(r['layer_id']),max(gap,r['clearance_nm'])) for r,s in profiles):
            positions.append(list(at))
    if not positions:raise ValueError('finite_future_contour_portals_exhausted_not_no_path')
    assert epoch==force._code_identity() and family==force._family(source,board_hint)
    return dict(schema=1,source=str(source),source_sha256=force._hash(source),code_identity=epoch,
        board_hint=board_hint,via_uuid=via_uuid,allow_owned_locked=allow_owned_locked,
        radius_mm=radius_mm,grid_mm=grid_mm,max_source_leg_mm=max_source_leg_mm,
        source_barrel={k:v for k,v in q.items() if k!='source_binding'},
        source_binding_sha256=hashlib.sha256(repr(sorted(q['source_binding'].items())).encode()).hexdigest(),
        future_profiles=[r for r,s in profiles],blocked_profiles=relevant,
        clearance_nm=gap,portal_positions_nm=positions,
        source_and_code_unchanged=True,power_copper_constructed=False,
        current_authority=False,routing_admitted=False,release_authority=False)


def discover(source,*,board_hint,max_barrels=4,allow_owned_locked=False,radius_mm=.6,
             grid_mm=.1,max_source_leg_mm=8.,timeout_s=10.):
    """Automatically identify only ordinary barrels blocking actual profiles."""
    _search_geometry(radius_mm,grid_mm,max_source_leg_mm)
    if type(max_barrels) is not int or not 1<=max_barrels<=8 or type(allow_owned_locked) is not bool:
        raise ValueError('literal_bounded_future_contour_barrel_inventory_required')
    deadline=barrel._budget(timeout_s);source=Path(source).resolve()
    epoch=force._code_identity();family=force._family(source,board_hint);b=pcbnew.LoadBoard(str(source))
    profiles=_profiles(b,deadline);eligible=ordinary.eligible_nets(b,source,board_hint)
    grouped={force._uid(i) for g in b.Groups() for i in g.GetItems()};candidates=[];plans=[];refusals=[]
    for via in b.GetTracks():
        contour._check_deadline(deadline)
        if (via.GetClass()!='PCB_VIA' or via.GetNetname() not in eligible or force._uid(via) in grouped
                or via.IsLocked() and not allow_owned_locked):continue
        gap=_gap(b,str(via.GetNetname()))
        hits=sum(s.Collide(via.GetEffectiveShape(r['layer_id']),max(gap,r['clearance_nm'])) for r,s in profiles)
        if hits:candidates.append((-hits,force._uid(via)))
    for negative_hits,uid in sorted(candidates)[:max_barrels]:
        contour._check_deadline(deadline)
        try:plans.append(plan(source,board_hint=board_hint,via_uuid=uid,allow_owned_locked=allow_owned_locked,
            radius_mm=radius_mm,grid_mm=grid_mm,max_source_leg_mm=max_source_leg_mm,
            timeout_s=max(.001,deadline-time.monotonic())))
        except ValueError as exc:refusals.append(dict(via_uuid=uid,reason=str(exc)))
    assert epoch==force._code_identity() and family==force._family(source,board_hint)
    return dict(ok=True,complete=True,source=str(source),source_sha256=force._hash(source),code_identity=epoch,
        candidate_barrels=len(candidates),unattempted=max(0,len(candidates)-max_barrels),plans=plans,refusals=refusals,
        source_and_code_unchanged=True,power_copper_constructed=False,routing_admitted=False,release_authority=False)


def receive(source,candidate,proposal,*,timeout_s=10.):
    """Existing full-width source restoration plus ALL future-profile clearance."""
    deadline=barrel._budget(timeout_s);r=dict(ok=False,complete=False,errors=[],routing_admitted=False,
        current_authority=False,release_authority=False,full_native_current_fields_cuts_and_stack_still_required=True)
    try:
        epoch=force._code_identity();paths=[Path(p).resolve() for p in (source,candidate)]
        hint=proposal['board_hint'];families=[force._family(p,hint) for p in paths]
        fresh=plan(paths[0],board_hint=hint,via_uuid=proposal['via_uuid'],allow_owned_locked=proposal['allow_owned_locked'],
            radius_mm=proposal['radius_mm'],grid_mm=proposal['grid_mm'],max_source_leg_mm=proposal['max_source_leg_mm'],
            timeout_s=max(.001,deadline-time.monotonic()))
        if contour._digest(proposal)!=contour._digest(fresh):raise ValueError('stale_or_forged_future_contour_barrel_plan')
        core=barrel.receive(*paths,via_uuid=fresh['via_uuid'],board_hint=hint,
            allow_owned_locked=fresh['allow_owned_locked'],max_source_leg_mm=fresh['max_source_leg_mm'],
            max_reseat_mm=fresh['radius_mm'],timeout_s=max(.001,deadline-time.monotonic()))
        r['independent_exact_ordinary_barrel_receiving']=core
        if not core['ok'] or not core['complete']:raise ValueError('ordinary_source_barrel_restoration_refused:'+str(core['errors']))
        board=pcbnew.LoadBoard(str(paths[1]));incoming=set(core['added_native_uuids'])
        vias=[v for v in board.GetTracks() if v.GetClass()=='PCB_VIA' and force._uid(v) in incoming]
        if len(vias)!=1 or list(vias[0].GetPosition()) not in fresh['portal_positions_nm']:
            raise ValueError('replacement_not_in_source_derived_future_portal_menu')
        for demand in fresh['future_profiles']:
            shape=native.reconstruct(demand['polygons_nm'],deadline,max_vertices=4096,max_polygons=4)
            for item in board.GetTracks():
                contour._check_deadline(deadline)
                if (force._uid(item) in incoming and item.IsOnLayer(demand['layer_id'])
                        and shape.Collide(item.GetEffectiveShape(demand['layer_id']),
                            max(fresh['clearance_nm'],demand['clearance_nm']))):
                    raise ValueError('new_ordinary_material_reenters_future_power_profile')
        assert epoch==force._code_identity() and families==[force._family(p,hint) for p in paths]
        r.update(ok=True,complete=True,source_candidate_and_code_unchanged=True,code_identity=epoch,
            all_future_source_power_profiles_clear=True,source_power_and_other_native_material_exact=True)
    except (ValueError,KeyError,TypeError,RuntimeError,OSError,AssertionError) as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def construct(source,outdir,proposal,*,portal_index=0,timeout_s=10.):
    """Build one private exact proposal; no source/selection or release write."""
    import cec_additive_route_receiving as additive
    import cec_future_pose_clearance as future
    from cec_native_items import discard_items
    deadline=barrel._budget(timeout_s);source=Path(source).resolve();outdir=Path(outdir).resolve()
    if outdir.exists() or type(portal_index) is not int or not 0<=portal_index<len(proposal['portal_positions_nm']):
        raise ValueError('fresh_private_future_barrel_output_and_literal_portal_index_required')
    epoch=force._code_identity();hint=proposal['board_hint'];family=force._family(source,hint)
    fresh=plan(source,board_hint=hint,via_uuid=proposal['via_uuid'],allow_owned_locked=proposal['allow_owned_locked'],
        radius_mm=proposal['radius_mm'],grid_mm=proposal['grid_mm'],max_source_leg_mm=proposal['max_source_leg_mm'],
        timeout_s=max(.001,min(10.,deadline-time.monotonic())))
    if contour._digest(fresh)!=contour._digest(proposal):raise ValueError('stale_future_contour_construction_plan')
    board=pcbnew.LoadBoard(str(source));q=barrel.plan(board,source,via_uuid=fresh['via_uuid'],board_hint=hint,
        allow_owned_locked=fresh['allow_owned_locked'],max_source_leg_mm=fresh['max_source_leg_mm'],
        timeout_s=max(.001,deadline-time.monotonic()))
    original=next(t for t in board.GetTracks() if force._uid(t)==fresh['via_uuid'])
    replacement=original.Duplicate();replacement.m_Uuid.Clone(pcbnew.KIID())
    barrel.subtract(board,source,q);temporary=[];land_rows=[]
    for index,row in enumerate(fresh['future_profiles']):
        for region in row['polygons_nm']:
            land_rows.append(dict(ref='source-contour-intent',pad=str(index),net=row['net'],
                uuid=row['source_track_uuids'][0],layer=board.GetLayerName(row['layer_id']),
                clearance_nm=max(fresh['clearance_nm'],row['clearance_nm']),polygons_nm=[region]))
    at=pcbnew.VECTOR2I(*fresh['portal_positions_nm'][portal_index]);code=board.GetNetcodeFromNetname(q['net'])
    try:
        temporary=future._install_reservations(board,dict(lands=land_rows),q['net'],deadline)
        diameter=max(q['root_width_by_layer_nm'].values())
        if not fr._via_spot_clear(board,at,diameter,fresh['clearance_nm'],{code},
                drill_nm=q['root_drill_nm'],net_code=code,foreign_cache={}):
            raise ValueError('future_profile_reserved_barrel_seat_refused')
        replacement.SetPosition(at);replacement.SetLocked(True);board.Add(replacement)
        for point in q['source_points_nm']:
            layer=point['layer'];width=point['width_nm'];start=pcbnew.VECTOR2I(*point['far_nm']);cache={}
            def clear(s,t,half):
                return (half==width//2 and fr._edge_leg_clear(board,s,t,half)
                    and fr._tap_foreign_clear(board,s,t,width,layer,fresh['clearance_nm'],{code},foreign_cache=cache))
            legs=fr._guarded_profiled_lastmile_legs(board,start,at,width,layer,fresh['clearance_nm'],code,clear,
                foreign_cache=cache,deadline_monotonic=deadline,refine_maze=True,allow_maze=True,
                maze_margin_mm=6.,perimeter_channels=True,refinement_grids_mm=(.2,))
            if not legs:raise ValueError('finite_future_reserved_source_lead_reconstruction_refused')
            for a,b,w in legs:
                t=pcbnew.PCB_TRACK(board);t.SetStart(a);t.SetEnd(b);t.SetWidth(w);t.SetLayer(layer)
                t.SetNetCode(code);t.SetLocked(True);board.Add(t)
    finally:
        discard_items(board,temporary)
    contour._check_deadline(deadline)
    child=force._copy_family(source,outdir/'UNADMITTED-future-contour-barrel')
    additive._ground_refill(board);field._save_field_snapshot(board,child)
    assert epoch==force._code_identity() and family==force._family(source,hint)
    result=dict(source=str(source),source_sha256=force._hash(source),candidate=str(child),
        candidate_sha256=force._hash(child),code_identity=epoch,proposal=fresh,portal_index=portal_index,
        errors=[],temporary_reservations_removed=True,source_family_and_code_unchanged=True,
        independent_saved_receiving_required=True,full_native_current_fields_cuts_and_stack_still_required=True,
        power_copper_constructed=False,source_selected=False,routing_admitted=False,fab_ready=False,release_authority=False)
    force._write(outdir/'construction.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--board-hint',required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--max-barrels',type=int,default=4)
    p.add_argument('--max-source-leg-mm',type=float,default=8.)
    p.add_argument('--construct-first',action='store_true',help='Private unadmitted construction; all final gates still required')
    p.add_argument('--allow-owned-locked',action='store_true');a=p.parse_args()
    if a.out.exists():raise ValueError('fresh_future_contour_proposal_output_required')
    result=discover(a.source,board_hint=a.board_hint,max_barrels=a.max_barrels,
        max_source_leg_mm=a.max_source_leg_mm,allow_owned_locked=a.allow_owned_locked)
    force._write(a.out,result)
    if a.construct_first:
        if not result['plans']:raise ValueError('no_source_owned_future_contour_barrel_proposal')
        built=construct(a.source,a.out.with_suffix(''),result['plans'][0])
        print(json.dumps(dict(construction=str(a.out.with_suffix('')/'construction.json'),candidate=built['candidate'],
            source_selected=False,routing_admitted=False,release_authority=False)),flush=True)
    print(json.dumps(dict(receipt=str(a.out),plans=len(result['plans']),candidates=result['candidate_barrels'],
        first=[q['portal_positions_nm'][0] for q in result['plans']],refusals=result['refusals'])),flush=True)


if __name__=='__main__':main()

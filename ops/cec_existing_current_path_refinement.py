"""Same-width finishing of already physically sized, source-owned current paths.

A project routing preference is not a fabricated minimum-width rule. This
separate owner preserves the literal source width, current authority and
interfaces, requires that width to meet the actual-face current/factory
floor, and replays exact source-minus-cut-plus-planar-copper. The original
preferred-width full-current owner is unchanged. Saved native DRC/custom
rules and all whole-board receiving remain independent mandatory gates.
"""
import json,math,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as debt
import cec_distributed_supply as supply
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_pair_local_reference_refinement as chains
import cec_sensitive_scalar_path_reflow as geometry
import cec_native_current_capture as capture
import cec_route_dimensions as dimensions
from cec_generated_pickup_retirement import _scoped_terminal_graph
from cec_native_items import discard_items

POLICY='existing-actual-face-current-capacity-path-refinement-v1'


def require(value,message):
    if not value:raise ValueError(message)


def capacity_floor(board,contract,face):
    canonical=fab.COPPER_LAYER_IDS.get(face)
    actual=contract.get('required_by_layer_mm',{}).get(canonical)
    limits=dimensions.board_limits(board)
    require(face in tuple(board.GetEnabledLayers().CuStack()) and face in (pcbnew.F_Cu,pcbnew.B_Cu)
        and canonical in contract.get('routing_layers',()) and type(actual) in (int,float)
        and math.isfinite(actual) and actual>0,'positive_existing_actual_outer_face_current_floor_required')
    require(type(limits.get('track_width')) in (int,float) and math.isfinite(limits['track_width'])
        and limits['track_width']>0,'positive_actual_current_fabrication_floor_required')
    return max(math.ceil(actual*1e6),board.GetDesignSettings().m_TrackMinWidth,math.ceil(limits['track_width']*1e6))


def no_new_enclosed_voids(board,old,points,*,timeout_s=2.):
    """Reject a shortcut that closes a loop against retained same-net metal.

    This is exact integer-native contour subtraction, not a centerline bend
    score or an area tolerance. Actual existing bores are subtracted equally
    from both sides. No current, plating or thermal authority is inferred.
    """
    deadline=time.monotonic()+timeout_s;first=old[0];face=int(first.GetLayer())
    cut={force._uid(t) for t in old};code=first.GetNetCode()
    tracks=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea() and z.IsOnLayer(face) and z.GetNetCode()==code]
    items=[i for i in pads+tracks if i.IsOnLayer(face) and i.GetNetCode()==code and force._uid(i) not in cut]
    drilled=[i for i in pads+tracks if i.GetClass()=='PCB_VIA' or i.GetClass()=='PAD' and i.HasHole()]
    require(len(items)+len(zones)+len(drilled)<=2048,'bounded_existing_current_contour_inventory_required')
    def tick(): require(time.monotonic()<deadline,'existing_current_contour_deadline')
    def native(item):
        tick()
        if item.GetClass()=='PAD':return item.GetEffectivePolygon(face,pcbnew.ERROR_OUTSIDE).CloneDropTriangulation()
        poly=pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(poly,face,0,1000,pcbnew.ERROR_OUTSIDE,False)
        return poly
    base=pcbnew.SHAPE_POLY_SET()
    for item in items:base.BooleanAdd(native(item));tick()
    for zone in zones:
        tick();require(zone.IsFilled() and zone.HasFilledPolysForLayer(face),'complete_current_contour_fill_required')
        base.BooleanAdd(zone.GetFilledPolysList(face))
    bores=pcbnew.SHAPE_POLY_SET()
    for item in drilled:
        tick();hole=pcbnew.SHAPE_POLY_SET()
        item.GetEffectiveHoleShape().TransformToPolygon(hole,1000,pcbnew.ERROR_OUTSIDE)
        require(hole.OutlineCount()>0,'actual_current_contour_bore_unavailable')
        bores.BooleanAdd(hole)
    before=base.CloneDropTriangulation();after=base.CloneDropTriangulation()
    for item in old:before.BooleanAdd(native(item))
    for a,z in zip(points,points[1:]):
        t=first.Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        after.BooleanAdd(native(t))
    holes=[]
    for material in (before,after):
        tick();material.BooleanSubtract(bores);material.Simplify()
        voids=pcbnew.SHAPE_POLY_SET()
        for i in range(material.OutlineCount()):
            for j in range(material.HoleCount(i)):
                tick();voids.AddOutline(material.Hole(i,j))
        voids.Simplify();holes.append(voids)
    new=holes[1].CloneDropTriangulation();new.BooleanSubtract(holes[0]);tick()
    require(not new.OutlineCount(),'new_enclosed_same_net_copper_void_or_loop_refused')
    return dict(source_enclosed_native_voids=holes[0].OutlineCount(),
        candidate_enclosed_native_voids=holes[1].OutlineCount(),new_enclosed_native_voids=0,
        inspected_actual_bores=len(drilled),integer_native_subtraction=True,
        area_epsilon_or_bend_count_waiver=False,retained_same_net_copper_included=True)


def plan(source,*,board_hint,retired_track_uuids,points_nm,allow_locked_source=False):
    require(type(board_hint) is str and bool(board_hint) and type(allow_locked_source) is bool,
        'explicit_existing_capacity_refinement_context_required')
    source=Path(source).resolve();epoch=force._code_identity();digest=force._hash(Path(__file__).resolve())
    board=pcbnew.LoadBoard(str(source));cut=ordinary._ids(retired_track_uuids,'existing_current_path_cut',8)
    require(2<=len(cut)<=8,'bounded_nonempty_existing_current_path_required')
    live={force._uid(t):t for t in board.GetTracks()};require(cut<=live.keys(),'actual_existing_current_tracks_required')
    old=[live[u] for u in sorted(cut)];grouped={force._uid(t) for g in board.Groups() for t in g.GetItems()}
    require(not cut&grouped and all(t.GetClass()=='PCB_TRACK' and not t.GetParentGroup() and not t.HasSolderMask()
        and (not t.IsLocked() or allow_locked_source) for t in old)
        and len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in old})==1,
        'one_plain_uniform_explicit_source_current_path_required')
    first=old[0];face=int(first.GetLayer());width=first.GetWidth();net=str(first.GetNetname())
    _,nodes=additive._nodes(source);process=chains._process(nodes[force._uid(first)])
    require(all(chains._process(nodes[force._uid(t)])==process for t in old),
        'every_source_track_process_field_must_match')
    kind,domain,contract=full._model(board,source,net,board_hint)
    floor=capacity_floor(board,contract,face)
    require(floor<=width<=1000000 and all(0<t.GetLength()<=16000000 for t in old)
        and sum(t.GetLength() for t in old)<=32000000,'actual_source_path_current_capacity_width_or_span_refused')
    original=[list(p) for p in chains._chain(old)];points=[list(p) for p in geometry._points(points_nm)]
    require(points[0]==original[0] and points[-1]==original[-1], 'literal_fixed_existing_current_path_ports_required')
    old_length=sum(t.GetLength() for t in old);new_length=sum(math.dist(a,z) for a,z in zip(points,points[1:]))
    require(old_length-new_length>=10000,'existing_current_refinement_must_remove_meaningful_path_length')
    spec=fr._project_netclass_resolver(str(source),board=board)(net) or {}
    clearance=max(board.GetDesignSettings().m_MinClearance,math.ceil(float(spec.get('clearance') or .2)*1e6))
    deadline=time.monotonic()+10.;geometry._contacts(board,old,points,deadline)
    boundary=geometry._boundary_turns(board,old,points,deadline)
    for a,z in zip(points,points[1:]):
        require(fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),(width+1)//2+clearance)
            and fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width,face,clearance,{first.GetNetCode()}),
            'existing_current_path_native_edge_hole_rule_area_or_foreign_clearance_refused')
    voids=no_new_enclosed_voids(board,old,points)
    require(epoch==force._code_identity() and digest==force._hash(Path(__file__).resolve()),'existing_current_plan_code_changed')
    return json.loads(json.dumps(dict(policy=POLICY,source_sha256=force._hash(source),authority_sha256=digest,
        board_hint=board_hint,retired_track_uuids=sorted(cut),points_nm=points,source_points_nm=original,
        allow_locked_source=allow_locked_source,layer=face,width_nm=width,actual_current_factory_floor_nm=floor,
        unchanged_routing_preference_mm=spec.get('track_width'),contract=contract,domain=domain,current_domain_kind=kind,
        source_length_nm=old_length,candidate_length_nm=new_length,source_boundaries=boundary,
        enclosed_void_preservation=voids,
        no_rule_preference_or_current_budget_modified=True,new_barrels_or_poses_authorized=False,release_authority=False),allow_nan=False))


def construct(source,proposal):
    board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
    old=[live[u] for u in proposal['retired_track_uuids']];prototype=old[0].Duplicate();discard_items(board,old)
    key=repr((POLICY,proposal['source_sha256'],proposal['retired_track_uuids'],proposal['points_nm']))
    for index,(a,z) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        t=prototype.Duplicate();t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,key+str(index)))))
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));board.Add(t)
    additive._ground_refill(board);return board


def receive(source,candidate,proposal,*,board_hint):
    r=dict(ok=False,complete=False,errors=[],inherited_debt_qualified=False,current_or_barrel_qualified=False,
        source_current_reduced=False,routing_admitted=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in ('retired_track_uuids','points_nm','allow_locked_source')})
        require(fresh==proposal,'stale_or_forged_existing_current_path_plan')
        require(force._sidecars(source)==force._sidecars(candidate),'existing_current_path_rules_or_project_changed')
        _,old=additive._nodes(source);_,got=additive._nodes(candidate)
        cut=set(proposal['retired_track_uuids']);added=got.keys()-old.keys()
        require(old.keys()-got.keys()==cut and len(added)==len(proposal['points_nm'])-1,'exact_existing_current_path_delta_required')
        with tempfile.TemporaryDirectory(prefix='cec-existing-current-path-') as temporary:
            replay=force._copy_family(source,Path(temporary)/'expected');field._save_field_snapshot(construct(source,proposal),replay)
            _,expected=additive._nodes(replay)
            require(got.keys()==expected.keys() and all(syntax._freeze(got[u])==syntax._freeze(expected[u]) for u in got),
                'exact_saved_existing_current_reconstruction_differs')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        kind,domain,contract=full._model(child,candidate,proposal['contract']['net'],board_hint)
        require(json.loads(json.dumps(contract))==proposal['contract'] and json.loads(json.dumps(domain))==proposal['domain']
            and kind==proposal['current_domain_kind'],'existing_current_path_budget_or_domain_changed')
        native={force._uid(t):t for t in child.GetTracks()};new=[native[u] for u in sorted(added)]
        require(all(t.GetClass()=='PCB_TRACK' and (t.GetWidth(),int(t.GetLayer()))==(proposal['width_nm'],proposal['layer'])
            and str(t.GetNetname())==contract['net'] for t in new),'literal_source_width_and_face_required')
        with force._thermal_hint(board_hint):
            guard=capture.Guard(parent,source,net=contract['net'],board_hint=board_hint,timeout_s=10.)
        require(all(guard(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth(),int(t.GetLayer())) for t in new),
            'existing_current_refinement_control_reservation_refused')
        live={force._uid(t):t for t in parent.GetTracks()}
        boundaries=ordinary._boundaries(parent,child,[live[u] for u in sorted(cut)],time.monotonic()+10.)
        first=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=cut)
        last=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*first))
        require(all(any(a<=z for z in last) for a in first),'existing_current_refinement_lost_surviving_partition')
        graphs=[_scoped_terminal_graph(b,contract['net'],timeout_s=10.) for b in (parent,child)]
        require(graphs[0]['pad_uuids']==graphs[1]['pad_uuids'],'actual_drilled_current_terminals_changed')
        rated=[supply._graph(b,contract['net'],contract) for b in (parent,child)]
        require(all(not q['unsupported_terminal_uuids'] and q['planar_full_width_components'] is not None for q in rated)
            and all(any(set(a)<=set(z) for z in rated[1]['planar_full_width_components'])
                for a in rated[0]['planar_full_width_components']),
            'existing_current_refinement_lost_actual_current_sized_terminal_join')
        current=debt.receive(source,candidate,board_hint=board_hint)
        require(current['ok'] and current['complete'],'existing_current_refinement_current_debt_worsened_or_unknown')
        require(epoch==force._code_identity() and proposal['authority_sha256']==force._hash(Path(__file__).resolve())
            and families==[force._family(p,board_hint) for p in (source,candidate)],'existing_current_refinement_epoch_changed')
        r.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            retired_track_uuids=sorted(cut),added_native_uuids=sorted(added),retired_via_uuids=[],
            exact_native_source_reconstruction=True,all_surviving_native_partitions_preserved=True,
            source_width_and_actual_current_authority_exact=True,source_rules_and_routing_preference_exact=True,
            actual_drilled_terminal_graphs=graphs,restored_source_boundaries=boundaries,source_control_capture=guard.report(),
            actual_current_sized_terminal_graphs=rated,all_preexisting_current_sized_joins_preserved=True,
            independent_whole_current_debt=current,centerline_removed_mm=(proposal['source_length_nm']-proposal['candidate_length_nm'])/1e6,
            new_vias=0,pads_moved=0,source_candidate_and_code_unchanged=True,
            full_native_custom_rule_drc_fields_kelvin_pairs_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as e:r['errors'].append(type(e).__name__+':'+str(e))
    return r

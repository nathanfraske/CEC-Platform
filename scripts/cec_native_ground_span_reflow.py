"""Fixed-port reflow of an already plane-redundant small native GND span.

This is not ordinary-net reclassification or mesh/return rip-up authority.
Only ungrouped full-class surface tracks may move. Locked source tracks need
an explicit exact UUID scope and retain their uniform source lock state.
The saved source
minus the exact requested span must ALREADY preserve all surviving native
partitions through unchanged copper. No pad/barrel moves, new current budget,
capacity, thermal, guard/shielding or fabrication qualification is inferred.
"""
from collections import defaultdict
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_copper_echo as syntax
import cec_copper_reuse as copper_reuse
import cec_decoupler_cell as cells
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_route_quality as quality
from cec_native_items import discard_items


def _deadline(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10:
        raise ValueError('bounded_native_ground_span_lease_required')
    return time.monotonic()+seconds


def _chain(rows):
    incidence=defaultdict(list)
    for t in rows:
        for at in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[at].append(t)
    ends=sorted(at for at,edges in incidence.items() if len(edges)==1)
    if len(ends)!=2 or any(len(edges)>2 for edges in incidence.values()):
        raise ValueError('one_exact_endpoint_linear_ground_span_required')
    points=[ends[0]];seen=set()
    while points[-1]!=ends[-1]:
        edges=[t for t in incidence[points[-1]] if force._uid(t) not in seen]
        if len(edges)!=1 or len(seen)>=8:raise ValueError('bounded_contiguous_ground_span_required')
        t=edges[0];seen.add(force._uid(t));a,b=tuple(t.GetStart()),tuple(t.GetEnd())
        points.append(b if points[-1]==a else a)
    if len(seen)!=len(rows):raise ValueError('unlisted_disconnected_ground_span')
    return points


def candidate_paths(board,track_uuid):
    """Finite cardinal-prefix/45-bridge alternatives from actual fixed ports."""
    items=[t for t in board.GetTracks() if force._uid(t)==track_uuid and t.GetClass()=='PCB_TRACK']
    if len(items)!=1:raise ValueError('one_actual_native_span_seed_required')
    a,b=sorted((tuple(items[0].GetStart()),tuple(items[0].GetEnd())))
    delta=[b[i]-a[i] for i in (0,1)];sign=[1 if v>0 else -1 if v<0 else 0 for v in delta]
    rows=[]
    for setback in (100000,250000,500000,750000,1000000):
        for axis in (0,1):
            if abs(delta[axis])<=setback:continue
            first=list(a);first[axis]+=sign[axis]*setback
            remaining=[b[i]-first[i] for i in (0,1)];diagonal=min(map(abs,remaining))
            corner=[first[i]+sign[i]*diagonal for i in (0,1)]
            points=[]
            for p in (list(a),first,corner,list(b)):
                if not points or p!=points[-1]:points.append(p)
            try:plan(board,[track_uuid],points)
            except ValueError:continue
            if points not in rows:rows.append(points)
    return rows


def _simple_reuse_path(points):
    """Exact integer segment predicates, including non-lattice crossings."""
    if len(set(points))!=len(points):raise ValueError('retained_ground_path_must_be_simple')
    def cross(a,b,p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    def on(a,b,p):return cross(a,b,p)==0 and all(min(a[i],b[i])<=p[i]<=max(a[i],b[i]) for i in (0,1))
    for i,(a,b) in enumerate(zip(points,points[1:])):
        for j in range(i+2,len(points)-1):
            c,d=points[j:j+2];ab=[cross(a,b,p) for p in (c,d)];cd=[cross(c,d,p) for p in (a,b)]
            if (ab[0]*ab[1]<0 and cd[0]*cd[1]<0 or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)):
                raise ValueError('retained_ground_path_must_be_simple')


def plan(board,track_uuids,points_nm,*,maximum_extra_nm=1000000,timeout_s=10.,allow_locked_track_uuids=(),
        reuse_retained_source=False,retained_path_only=False,retained_source_pad_portals=False,
        retained_cycle_pruning=False):
    deadline=_deadline(timeout_s)
    if (type(track_uuids) is not list or not 1<=len(track_uuids)<=8
            or len(set(track_uuids))!=len(track_uuids) or any(type(u) is not str or not u for u in track_uuids)
            or type(points_nm) is not list or not 2<=len(points_nm)<=16
            or any(type(p) not in (list,tuple) or len(p)!=2 or any(type(v) is not int
                or abs(v)>2000000000 for v in p) for p in points_nm)
            or type(maximum_extra_nm) is not int or not 0<=maximum_extra_nm<=1000000
            or type(reuse_retained_source) is not bool or type(retained_path_only) is not bool
            or retained_path_only and not reuse_retained_source or type(retained_source_pad_portals) is not bool
            or retained_source_pad_portals and not retained_path_only or type(retained_cycle_pruning) is not bool
            or retained_cycle_pruning and not retained_path_only):
        raise ValueError('bounded_explicit_native_ground_span_context_required')
    tracks=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(tracks)+len(pads)+len(list(board.Zones()))>16384:
        raise ValueError('native_ground_span_inventory_bound')
    live={force._uid(t):t for t in tracks};ids=set(track_uuids)
    if not ids<=live.keys():raise ValueError('actual_native_ground_span_scope_required')
    allowed=ordinary._ids(allow_locked_track_uuids,'native_ground_span_locked_source_scope',8)
    if not allowed<=ids:raise ValueError('ground_span_lock_scope_must_be_inside_exact_cut')
    selected=[live[u] for u in sorted(ids)];face=int(selected[0].GetLayer());width=selected[0].GetWidth()
    floor=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,'GND')['width']))
    if (face not in (pcbnew.F_Cu,pcbnew.B_Cu) or not floor<=width<=350000
            or any(t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND' or int(t.GetLayer())!=face
                or t.GetWidth()!=width or t.IsLocked() and force._uid(t) not in allowed
                or t.GetParentGroup() or t.HasSolderMask()
                or t.GetLength()<=0 for t in selected)
            or any(g.ContainsItem(t) for g in board.Groups() for t in selected)):
        raise ValueError('unlocked_ungrouped_full_class_small_surface_ground_span_required')
    if allowed and (allowed!={force._uid(t) for t in selected if t.IsLocked()}
            or len({bool(t.IsLocked()) for t in selected})!=1):
        raise ValueError('exact_uniform_source_ground_span_lock_process_required')
    source=_chain(selected);points=[tuple(p) for p in points_nm]
    if [points[0],points[-1]]!=[source[0],source[-1]]:
        raise ValueError('exact_unchanged_ground_span_boundary_ports_required')
    if any(a==b or not quality.is_canonical_stroke(a,b,tolerance_nm=0) for a,b in zip(points,points[1:])):
        raise ValueError('exact_nonzero_octilinear_ground_span_required')
    for a,b,c in zip(points,points[1:],points[2:]):
        u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
        dot=sum(x*y for x,y in zip(u,v));cross=u[0]*v[1]-u[1]*v[0]
        if not retained_cycle_pruning and (dot<=0 or abs(cross)>dot):
            raise ValueError('native_ground_span_turns_at_most_45_degrees_required')
    if reuse_retained_source:_simple_reuse_path(points)
    before=sum(t.GetLength() for t in selected);after=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
    if retained_path_only:
        import cec_source_guided_ordinary_detour as exact_lengths
        if retained_cycle_pruning:
            # This is an existing material witness, NOT a new routed shape.
            # Compare its finite scheduling envelope with exact a+b*sqrt(2).
            # Saved receiving still refuses any actual terminal-return loss.
            first,last=[exact_lengths.length_terms(q) for q in (source,points)]
            c=last['cardinal_nm']-first['cardinal_nm']-maximum_extra_nm
            d=last['diagonal_component_nm']-first['diagonal_component_nm']
            lengthened=(c>0 if d==0 else c>=0 or c*c<2*d*d if d>0 else c>0 and c*c>2*d*d)
        else:lengthened=exact_lengths.strictly_shorter(source,points)
    else:lengthened=after>before+maximum_extra_nm
    if before>25000000 or lengthened or points==source:
        raise ValueError('bounded_changed_ground_span_length_required')
    # Native body tees are NOT endpoints and cannot be silently moved with a
    # free junction. A short cap at each fixed port is the only contact lease.
    ports=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*p),width) for p in (source[0],source[-1])]
    contacts=set();port_contacts=[set(),set()];pad_contact_covers=[];pad_material=None
    if retained_source_pad_portals:
        import cec_retained_surface_pad_copper as pad_copper
        pad_material=pad_copper.SourcePads(board,'GND',face,width,ids,deadline)
    for item in [*tracks,*pads]:
        if time.monotonic()>=deadline:raise ValueError('native_ground_span_contact_deadline')
        uid=force._uid(item)
        if uid in ids or not item.IsOnLayer(face):continue
        shape=item.GetEffectiveShape(face)
        if not any(t.GetEffectiveShape(face).Collide(shape,0) for t in selected):continue
        if item.GetNetname()!='GND':raise ValueError('source_ground_span_foreign_contact')
        at=[i for i,p in enumerate(ports) if p.Collide(shape,0)]
        if not at:
            cover=pad_material.contact_cover(selected,item) if pad_material is not None else None
            if cover is None:raise ValueError('source_ground_span_has_unowned_interior_contact')
            pad_contact_covers.append(cover)
        contacts.add(uid)
        for i in at:port_contacts[i].add(uid)
    if not all(port_contacts):raise ValueError('two_actual_retained_ground_span_port_kernels_required')
    result=dict(schema=1,source_binding=binding._source_binding(board),retired_track_uuids=sorted(ids),
        source_points_nm=[list(p) for p in source],replacement_points_nm=[list(p) for p in points],
        source_width_nm=width,source_layer=face,source_length_nm=before,replacement_length_nm=after,
        maximum_extra_nm=maximum_extra_nm,port_contact_uuids=[sorted(q) for q in port_contacts],
        retained_contact_uuids=sorted(contacts),current_qualified=False,release_authority=False)
    if allowed:result['allow_locked_track_uuids']=sorted(allowed)
    if reuse_retained_source:
        # Only literal pre-existing, uncut, same-face full-width straight
        # copper may carry omitted proposal intervals. No fills or barrels
        # stand in for a surface trace, and path length cannot increase.
        retained=copper_reuse.RetainedCopper(r for r in copper_reuse.native_inventory(board) if r['uuid'] not in ids)
        proposed=[dict(net='GND',layer=face,width_nm=width,start_nm=list(a),end_nm=list(b))
            for a,b in zip(points,points[1:])]
        emitted,proof=retained.subtract(proposed)
        pad_witnesses=[]
        if retained_source_pad_portals:
            import cec_retained_surface_pad_copper as pad_copper
            emitted,pad_witnesses=pad_copper.SourcePads(board,'GND',face,width,ids,deadline).credit(emitted)
        material=sum(math.dist(r['start_nm'],r['end_nm']) for r in emitted)
        emitted_count_ok=(len(emitted)==0 if retained_path_only else 1<=len(emitted)<=15)
        if (maximum_extra_nm!=0 and not retained_cycle_pruning or lengthened or before-material<=10000
                or not emitted_count_ok or not proof['reused_native_uuids']):
            raise ValueError('strict_copper_saving_nonlonger_retained_ground_path_required')
        result.update(reuse_retained_source=True,retained_copper_reuse=proof,
            emitted_segments_nm=emitted,emitted_material_length_nm=material,
            saved_trace_length_nm=before-material)
        if retained_path_only:
            result.update(retained_path_only=True,zero_emission_requires_entire_path_in_retained_native_tracks=True)
        if retained_source_pad_portals:
            result.update(retained_source_pad_portals=True,native_solid_smd_pad_copper_witnesses=pad_witnesses,
                retained_source_pad_contact_covers=pad_contact_covers,
                zero_emission_requires_entire_path_in_retained_native_tracks=False,
                exact_native_surface_path_envelope_covered_before_identical_drill_subtraction=True)
        if retained_cycle_pruning:
            result.update(retained_cycle_pruning=True,
                virtual_witness_existing_turns_and_bounded_extra_length_not_new_routing=True,
                actual_saved_ground_return_nonregression_still_mandatory=True)
    return result


def _cut(board,proposal):
    fresh=plan(board,proposal['retired_track_uuids'],proposal['replacement_points_nm'],
        maximum_extra_nm=proposal['maximum_extra_nm'],
        allow_locked_track_uuids=proposal.get('allow_locked_track_uuids',()),
        reuse_retained_source=proposal.get('reuse_retained_source',False),
        retained_path_only=proposal.get('retained_path_only',False),
        retained_source_pad_portals=proposal.get('retained_source_pad_portals',False),
        retained_cycle_pruning=proposal.get('retained_cycle_pruning',False))
    if fresh!=proposal:raise ValueError('native_ground_span_stale_or_forged_source_plan')
    selected=[t for t in board.GetTracks() if force._uid(t) in proposal['retired_track_uuids']]
    exemplar=selected[0].Duplicate();discard_items(board,selected);return exemplar


def materialize(board,proposal):
    exemplar=_cut(board,proposal);gap=max(board.GetDesignSettings().m_MinClearance,
        int(cells._netclass(board,'GND')['clearance']));cache={};added=[]
    for a,b in zip(proposal['replacement_points_nm'],proposal['replacement_points_nm'][1:]):
        a,b=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)
        if (not fr._edge_leg_clear(board,a,b,(proposal['source_width_nm']+1)//2)
                or not fr._tap_foreign_clear(board,a,b,proposal['source_width_nm'],proposal['source_layer'],
                    gap,{exemplar.GetNetCode()},foreign_cache=cache)):
            raise ValueError('native_ground_span_foreign_or_edge_clearance')
    segments=(proposal['emitted_segments_nm'] if proposal.get('reuse_retained_source') else
        [dict(start_nm=a,end_nm=b) for a,b in zip(proposal['replacement_points_nm'],proposal['replacement_points_nm'][1:])])
    for row in segments:
        a,b=pcbnew.VECTOR2I(*row['start_nm']),pcbnew.VECTOR2I(*row['end_nm'])
        item=exemplar.Duplicate();item.m_Uuid.Clone(pcbnew.KIID());item.SetStart(a);item.SetEnd(b);board.Add(item)
        added.append(force._uid(item))
    return added


def _outside_return_reach(pad,tracks,reach_nm=16000001):
    """Exact conservative AABB lower bound, including the observer's 1nm snap.

    A nonnegative XY path of at most 16mm cannot reach material whose entire
    outer native bounding box is farther away. A plated transition changes Z,
    not XY. The pad box overcovers every possible native start node. This may
    refuse to prove a far land, but can never turn a nearby land into one.
    """
    box=pad.GetBoundingBox();bounds=[]
    for track in tracks:
        other=track.GetBoundingBox()
        dx=max(int(box.GetX())-int(other.GetRight()),int(other.GetX())-int(box.GetRight()),0)
        dy=max(int(box.GetY())-int(other.GetBottom()),int(other.GetY())-int(box.GetBottom()),0)
        bounds.append(dx*dx+dy*dy)
    return bool(bounds) and min(bounds)>reach_nm*reach_nm


def _redundant_cut_contract(parent,basis,child,proposal,source_parts,cut_parts,deadline):
    if any(not any(p<=q for q in cut_parts) for p in source_parts):
        raise ValueError('source_ground_span_is_not_already_native_plane_redundant')
    return dict(source_span_already_redundant_to_retained_native_copper=True)


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    """The public redundant-span contract is unchanged and cannot be waived."""
    return _receive_path(source,candidate,proposal,board_hint=board_hint,timeout_s=timeout_s,
        cut_contract=_redundant_cut_contract)


def _receive_path(source,candidate,proposal,*,board_hint,timeout_s,cut_contract):
    """Shared exact path/process/contact replay; typed cut contracts are internal.

    A separate necessary-branch operator supplies its independently retyped
    terminal/partition proof. Neither a manifest field nor a lock permission
    can select that contract through the public redundant-span receiver.
    """
    r=dict(ok=False,complete=False,errors=[],current_qualified=False,release_authority=False,
        full_current_fields_native_DRC_absolute_cuts_and_release_still_required=True)
    try:
        deadline=_deadline(timeout_s);paths=[Path(p).resolve() for p in (source,candidate)]
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in paths]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in paths]
        if plan(parent,proposal['retired_track_uuids'],proposal['replacement_points_nm'],
                maximum_extra_nm=proposal['maximum_extra_nm'],
                allow_locked_track_uuids=proposal.get('allow_locked_track_uuids',()),
                reuse_retained_source=proposal.get('reuse_retained_source',False),
                retained_path_only=proposal.get('retained_path_only',False),
                retained_source_pad_portals=proposal.get('retained_source_pad_portals',False),
                retained_cycle_pruning=proposal.get('retained_cycle_pruning',False))!=proposal:
            raise ValueError('native_ground_span_stale_or_forged_source_plan')
        retired=set(proposal['retired_track_uuids']);_,old=additive._nodes(paths[0]);_,new=additive._nodes(paths[1])
        incoming=new.keys()-old.keys();live={force._uid(t):t for t in child.GetTracks()}
        incoming_count_ok=(len(incoming)==0 if proposal.get('retained_path_only') else 1<=len(incoming)<=15)
        if old.keys()-new.keys()!=retired or not incoming_count_ok or not incoming<=live.keys():
            raise ValueError('exact_native_ground_span_track_only_delta_required')
        if any(u not in new or syntax._freeze(n)!=syntax._freeze(new[u])
                for u,n in old.items() if n[0]=='zone'):
            raise ValueError('every_native_ground_span_source_zone_and_fill_must_be_exact')
        rows=[live[u] for u in incoming]
        source_locked=bool(next(t for t in parent.GetTracks() if force._uid(t) in retired).IsLocked())
        if any(t.GetClass()!='PCB_TRACK' or t.GetNetname()!='GND' or bool(t.IsLocked())!=source_locked or t.GetParentGroup()
                or t.HasSolderMask() or int(t.GetLayer())!=proposal['source_layer']
                or t.GetWidth()!=proposal['source_width_nm'] for t in rows):
            raise ValueError('unchanged_ground_span_face_width_and_process_required')
        if proposal.get('reuse_retained_source'):
            actual=sorted((tuple(t.GetStart()),tuple(t.GetEnd())) for t in rows)
            wanted=sorted((tuple(r['start_nm']),tuple(r['end_nm'])) for r in proposal['emitted_segments_nm'])
            if actual!=wanted:raise ValueError('saved_native_ground_span_retained_copper_emission_differs')
        elif [list(p) for p in _chain(rows)]!=proposal['replacement_points_nm']:
            raise ValueError('saved_native_ground_span_path_differs')
        with tempfile.TemporaryDirectory(prefix='cec-native-ground-span-') as tmp:
            projected=force._copy_family(paths[0],Path(tmp)/'source-minus-span')
            basis=pcbnew.LoadBoard(str(projected));exemplar=_cut(basis,proposal)
            import cec_native_partition_pair as partitions
            comparison=partitions.compare(parent,basis,retired_uuids=retired,
                timeout_s=min(10.,deadline-time.monotonic()))
            source_parts,cut_parts=comparison['source_parts'],comparison['child_parts']
            scoped=cut_contract(parent,basis,child,proposal,source_parts,cut_parts,deadline)
            profile=fab.get_profile(fab.board_profile_name(basis))
            if not profile:raise ValueError('explicit_source_ground_reference_profile_required')
            plane_faces={int(basis.GetLayerID(name)) for name,role in zip(fab.COPPER_LAYERS,profile['roles']) if role=='GND'}
            planes=[(force._uid(z),face) for z in basis.Zones() if not z.GetIsRuleArea()
                and z.GetNetname()=='GND' and z.IsFilled() for face in plane_faces
                if z.IsOnLayer(face) and z.HasFilledPolysForLayer(face)]
            if len({face for uid,face in planes})<2:
                raise ValueError('two_actual_saved_ground_reference_planes_required')
            def process(node):return sorted((syntax._freeze(q) for q in node[1:] if not
                (isinstance(q,list) and q and q[0] in ('uuid','start','end'))),key=repr)
            signature=process(old[proposal['retired_track_uuids'][0]])
            if any(process(nodes[uid])!=signature for nodes,ids in ((old,retired),(new,incoming)) for uid in ids):
                raise ValueError('every_native_ground_span_saved_process_field_required')
            face=proposal['source_layer'];allowed=set(proposal['retained_contact_uuids'])
            contact_shapes=[t.GetEffectiveShape(face) for t in rows]
            if proposal.get('reuse_retained_source'):
                contact_shapes=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),proposal['source_width_nm'])
                    for a,b in zip(proposal['replacement_points_nm'],proposal['replacement_points_nm'][1:])]
            covered_contacts={r['contact_uuid'] for r in proposal.get('retained_source_pad_contact_covers',[])}
            extra_existing_virtual_contacts=[]
            for item in [*basis.GetTracks(),*(p for fp in basis.GetFootprints() for p in fp.Pads())]:
                if time.monotonic()>=deadline:raise ValueError('native_ground_span_saved_contact_deadline')
                if item.GetNetname()!='GND' or not item.IsOnLayer(face):continue
                touching=any(shape.Collide(item.GetEffectiveShape(face),0) for shape in contact_shapes)
                uid=force._uid(item)
                if proposal.get('retained_source_pad_portals'):
                    # There is no incoming copper. A virtual replacement can
                    # encounter extra SOURCE contacts that its retained carrier
                    # already had; that cannot create a new physical junction.
                    # Every OLD contact still needs its exact endpoint kernel
                    # or the independently rederived no-loss land-cover proof.
                    if uid in allowed and not touching and uid not in covered_contacts:
                        raise ValueError('native_ground_span_retained_contact_identity_changed')
                    if touching and uid not in allowed:extra_existing_virtual_contacts.append(uid)
                elif touching != (uid in allowed):
                    raise ValueError('native_ground_span_retained_contact_identity_changed')
            field._save_field_snapshot(basis,projected)
            if proposal.get('retained_path_only'):
                # A zero-emission transaction is not an additive transaction.
                # Reparse and compare the ENTIRE independently projected
                # saved source tree, including unknown nodes and metadata.
                # No cached success flag or empty-delta exception stands in
                # for this exact source-subtraction proof.
                projected_root,_=additive._nodes(projected);candidate_root,_=additive._nodes(paths[1])
                equal=(syntax._freeze(projected_root)==syntax._freeze(candidate_root)
                    and force._sidecars(projected)==force._sidecars(paths[1]))
                if not equal:raise ValueError('zero_emission_saved_source_subtraction_differs')
                exact=dict(ok=True,complete=True,method='entire_native_source_subtraction_saved_tree_and_sidecars_equal',
                    zero_new_tracks_rederived_from_retained_native_copper=True,
                    source_projection_sha256=force._hash(projected),candidate_sha256=force._hash(paths[1]),
                    release_authority=False)
            else:
                exact=additive.receive(projected,paths[1],board_hint=board_hint,timeout_s=max(.001,min(10.,deadline-time.monotonic())))
            r['exact_saved_source_subtract_add_and_ground_refill']=exact
            if not exact['ok'] or not exact['complete']:raise ValueError('native_ground_span_exact_saved_replay_refused')
        pads={force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads()}
        returns=0;unaffected=[]
        original_tracks=[t for t in parent.GetTracks() if force._uid(t) in retired]
        for fp in parent.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname()!='GND' or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:continue
                if time.monotonic()>=deadline:raise ValueError('native_ground_span_saved_return_deadline')
                if _outside_return_reach(pad,original_tracks):
                    unaffected.append(force._uid(pad));continue
                prior=cells._existing_return(parent,pad,16.,allow_native_track_body=True)
                if prior is None:continue
                after=cells._existing_return(child,pads[force._uid(pad)],16.,allow_native_track_body=True)
                if after is None or after[0]>prior[0]+1e-6:raise ValueError('native_ground_span_existing_return_worsened')
                returns+=1
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in paths]:
            raise ValueError('native_ground_span_sources_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(paths[0]),
            candidate_sha256=force._hash(paths[1]),source_candidate_and_code_unchanged=True,
            every_source_retained_contact_and_proved_ground_return_preserved=True,
            checked_existing_smd_ground_returns=returns,analytically_unaffected_ground_land_uuids=unaffected,
            actual_return_comparison_reach_mm=16.,unchanged_native_zone_fills_required_for_unaffected_scope=True,
            retired_track_uuids=sorted(retired),added_track_uuids=sorted(incoming),
            source_length_nm=proposal['source_length_nm'],replacement_length_nm=proposal['replacement_length_nm'],
            **scoped)
        if proposal.get('reuse_retained_source'):
            r.update(retained_copper_reuse=proposal['retained_copper_reuse'],
                emitted_material_length_nm=proposal['emitted_material_length_nm'],
                saved_trace_length_nm=proposal['saved_trace_length_nm'],
                no_return_or_current_authority_from_copper_reuse=True)
        if proposal.get('retained_path_only'):
            r.update(retained_path_only=True,no_new_tracks_or_holes=True,
                every_replacement_capsule_already_in_unchanged_native_surface_tracks=not proposal.get('retained_source_pad_portals',False),
                native_solid_smd_pad_copper_witnesses=proposal.get('native_solid_smd_pad_copper_witnesses',[]))
        if proposal.get('retained_source_pad_portals'):
            r.update(retained_source_pad_contact_covers=proposal['retained_source_pad_contact_covers'],
                extra_virtual_contacts_already_in_unchanged_source_copper=sorted(extra_existing_virtual_contacts),
                no_new_junction_or_current_rights_from_virtual_contacts=True)
        if proposal.get('retained_cycle_pruning'):
            r.update(retained_cycle_pruning=True,
                no_new_route_or_corner_from_virtual_retained_path=True,
                actual_existing_terminal_returns_not_the_virtual_witness_define_nonregression=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r

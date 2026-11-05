"""Fixed-port finishing inside a positively isolated native Kelvin-input island.

No force width, current budget, source land, barrel or part is a variable.
Planning requires a source-bound typed replay and independently re-derives
manufacturer lineage and the actual clipped same-face input island. Saved
receiving repeats native clipping/admission on the literal source and child.
This grants no current, thermal, full-Kelvin or fabrication qualification.
"""
import copy,json,math,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as debt
import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_fr as fr
import cec_kelvin_copper_cut as physical
import cec_ordinary_route_receiving as ordinary
import cec_pair_local_reference_refinement as chains
import cec_sensitive_scalar_path_reflow as geometry
import cec_sense_topology as lineage
import cec_existing_current_path_refinement as contour
import cec_native_fill_geometry as fills
from cec_generated_pickup_retirement import _scoped_terminal_graph
from cec_native_items import discard_items

POLICY='isolated-native-kelvin-input-fixed-port-finishing-v1'
def require(value,message):
    if not value:raise ValueError(message)
def plain(value):return json.loads(json.dumps(value,allow_nan=False))

def source_witness(board,source,evidence_path,board_hint,input_pad_uuid):
    report=json.loads(Path(evidence_path).read_text())
    require(report['complete'] and report['identity_stable'] and report['loaded_board_identity_verified']
        and report['code_before']==report['code_after']==force._code_identity()
        and report['source_family_before']==report['source_family_after']==force._family(source,board_hint),
        'complete_current_source_bound_typed_kelvin_replay_required')
    rows=[r for r in report['inner_departure']['details'] if r.get('sense_terminal',{}).get('uuid')==input_pad_uuid]
    require(len(rows)==1,'one_actual_typed_kelvin_input_terminal_required');row=rows[0]
    clips=[r for r in report['clipped_isolation']['details'] if (r['input_ref'],r['leg'])==(row['input_ref'],row['leg'])]
    require(len(clips)==1 and clips[0]['ok'] is True and clips[0]['native']['complete']
        and clips[0]['native']['ok'] is True and not clips[0]['native']['physical_bypass_proved']
        and row['ok'] is True,'positive_source_clipped_isolation_and_inner_departure_required')
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint)
        fresh=lineage.board_evidence(board,anchor_pairs=fr._board_kelvin_pairs(board),
            anchor_refs={r for d in domains.values() if d.get('complete') is True for r in d.get('authority_refs',())},
            max_hops=sense.MAX_HOPS,max_expansions=sense.MAX_EXPANSIONS)
    derived=[r for r in fresh['details'] if r['ref']==row['input_ref'] and r['ok'] is True]
    cached=[r for r in report['lineage']['details'] if r['ref']==row['input_ref'] and r['ok'] is True]
    require(len(derived)==len(cached)==1 and plain(derived[0]['selected'])==plain(cached[0]['selected'])
        and plain(derived[0]['pins'])==plain(cached[0]['pins']),
        'manufacturer_kelvin_lineage_must_rederive_from_native_parts')
    pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    anchor=pads[row['source_pad']['uuid']];terminal=pads[input_pad_uuid]
    require(sense._pad_identity(anchor)==row['source_pad'] and sense._pad_identity(terminal)==row['sense_terminal']
        and anchor.GetAttribute()==terminal.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
        and not anchor.HasHole() and not terminal.HasHole(), 'literal_unmoved_surface_kelvin_terminals_required')
    return row,anchor,terminal

def input_island(board,anchor,terminal,old,face,*,timeout_s=10.):
    """Every old cut lies in the same actual pad-cut component as this input.

    Use both native envelopes, all saved fills and all actual bores. Every
    selected clipped fragment must contact the input component and no other
    component. Checking fragments, not only a whole item, prevents owning a
    second force-side piece hidden across the removed source land. Component
    assignment uses native integer booleans without polygon healing or an
    area epsilon; independent absolute 3D clipping still owns isolation.
    """
    deadline=time.monotonic()+timeout_s;work=physical._Work(deadline)
    pads,tracks,zones,copper=physical._inventory(board,work)
    items=[i for i in pads+tracks if i.GetNetname()==terminal.GetNetname() and i.IsOnLayer(face)
        and force._uid(i)!=force._uid(anchor)]
    pours=[z for z in zones if z.GetNetname()==terminal.GetNetname() and z.IsOnLayer(face)]
    bores=[i for i in pads+tracks if physical._simple_drill(i,copper)]
    require(len(items)+len(pours)<=512,'bounded_native_kelvin_input_island_required')
    def native(item,upper):
        work.tick();strategy=pcbnew.ERROR_OUTSIDE if upper else pcbnew.ERROR_INSIDE
        if item.GetClass()=='PAD':poly=item.GetEffectivePolygon(face,strategy).CloneDropTriangulation()
        elif item.GetClass()=='ZONE':
            require(item.IsFilled() and item.HasFilledPolysForLayer(face),'saved_kelvin_input_zone_fill_required')
            poly=item.GetFilledPolysList(face).CloneDropTriangulation()
        else:
            poly=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(poly,face,0,1000,strategy,False)
        poly.Inflate(2 if upper else -2,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,1)
        return poly
    results=[]
    for upper in (False,True):
        work.tick();void=pcbnew.SHAPE_POLY_SET()
        for item in bores:
            work.tick();hole=pcbnew.SHAPE_POLY_SET()
            item.GetEffectiveHoleShape().TransformToPolygon(hole,1000,pcbnew.ERROR_INSIDE if upper else pcbnew.ERROR_OUTSIDE)
            hole.Inflate(-2 if upper else 2,pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,1);void.BooleanAdd(hole)
        source_cut=native(anchor,not upper);material=pcbnew.SHAPE_POLY_SET()
        for item in items+pours:
            if not upper and hasattr(item,'FlashLayer') and not item.FlashLayer(face):continue
            material.BooleanAdd(native(item,upper))
        material.BooleanSubtract(void);material.BooleanSubtract(source_cut);material.Simplify()
        target=native(terminal,upper);target.BooleanSubtract(void);target.BooleanSubtract(source_cut)
        parts=[];all_parts=[]
        for i in range(material.OutlineCount()):
            work.tick();part=pcbnew.SHAPE_POLY_SET();part.AddOutline(material.Outline(i))
            for h in range(material.HoleCount(i)):part.AddHole(material.Hole(i,h),0)
            all_parts.append(part)
            overlap=part.CloneDropTriangulation();overlap.BooleanIntersection(target)
            if overlap.OutlineCount():parts.append(part)
        require(len(parts)==1,'one_actual_clipped_kelvin_input_component_required')
        island=parts[0]
        for t in old:
            work.tick();body=native(t,upper);body.BooleanSubtract(void);body.BooleanSubtract(source_cut)
            require(body.OutlineCount(),'selected_kelvin_track_has_no_exposed_input_fragment')
            for i in range(body.OutlineCount()):
                fragment=pcbnew.SHAPE_POLY_SET();fragment.AddOutline(body.Outline(i))
                for h in range(body.HoleCount(i)):fragment.AddHole(body.Hole(i,h),0)
                tested=fragment.CloneDropTriangulation();tested.BooleanIntersection(island)
                require(tested.OutlineCount(),'source_cut_not_exclusively_in_declared_kelvin_input_island:'+
                    ('upper' if upper else 'lower')+':'+force._uid(t))
                for other in all_parts:
                    if other is island:continue
                    contact=fragment.CloneDropTriangulation();contact.BooleanIntersection(other)
                    require(not contact.OutlineCount(),'selected_kelvin_fragment_also_contacts_another_native_component')
        digest,vertices=fills.identity(island,deadline)
        terminals=[]
        for item in items:
            if item.GetClass()!='PAD':continue
            contact=native(item,upper);contact.BooleanIntersection(island)
            if contact.OutlineCount():terminals.append(force._uid(item))
        results.append(dict(bound='upper' if upper else 'lower',component_sha256=digest,native_vertices=vertices,
            component_pad_uuids=sorted(terminals),
            every_selected_track_has_definite_input_contact=not upper,
            every_selected_fragment_contacts_only_declared_input_component=True))
    return dict(bounds=results,actual_bores=len(bores),actual_net_items=len(items)+len(pours),
        source_anchor_uuid=force._uid(anchor),sense_terminal_uuid=force._uid(terminal),force_side_cut_authorized=False,
        exact_integer_native_component_subtraction=True,numeric_healing_or_area_epsilon_used=False)

def plan(source,*,board_hint,sense_evidence,input_pad_uuid,retired_track_uuids,points_nm,allow_locked_source=False):
    require(type(board_hint) is str and bool(board_hint) and type(input_pad_uuid) is str
        and type(allow_locked_source) is bool,'explicit_kelvin_input_finishing_identity_required')
    source=Path(source).resolve();evidence_path=Path(sense_evidence).resolve();epoch=force._code_identity()
    authority=force._hash(Path(__file__));board=pcbnew.LoadBoard(str(source))
    cut=ordinary._ids(retired_track_uuids,'kelvin_input_finishing_cut',8)
    require(2<=len(cut)<=8,'bounded_nonempty_kelvin_input_path_required')
    live={force._uid(t):t for t in board.GetTracks()};require(cut<=live.keys(),'actual_kelvin_input_tracks_required')
    old=[live[u] for u in sorted(cut)];grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    require(not cut&grouped and all(t.GetClass()=='PCB_TRACK' and not t.GetParentGroup() and not t.HasSolderMask()
        and (not t.IsLocked() or allow_locked_source) for t in old)
        and len({(str(t.GetNetname()),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked())) for t in old})==1,
        'one_plain_uniform_source_owned_kelvin_input_path_required')
    row,anchor,terminal=source_witness(board,source,evidence_path,board_hint,input_pad_uuid)
    first=old[0];face=int(first.GetLayer());width=first.GetWidth()
    require(str(first.GetNetname())==row['net'] and face in (pcbnew.F_Cu,pcbnew.B_Cu)
        and anchor.IsOnLayer(face) and terminal.IsOnLayer(face)
        and 0<width<=min(400000,math.floor(row['max_trace_width_mm']*1e6)),
        'positive_same_face_thin_kelvin_branch_scope_required')
    original=[list(p) for p in chains._chain(old)];points=[list(p) for p in geometry._points(points_nm)]
    require(points[0]==original[0] and points[-1]==original[-1],'literal_kelvin_input_boundary_ports_required')
    old_length=sum(t.GetLength() for t in old);new_length=sum(math.dist(a,z) for a,z in zip(points,points[1:]))
    require(old_length<=25000000 and old_length-new_length>=10000,'strictly_shorter_bounded_kelvin_input_path_required')
    _,nodes=additive._nodes(source);process=chains._process(nodes[force._uid(first)])
    require(all(chains._process(nodes[force._uid(t)])==process for t in old),'uniform_kelvin_input_process_fields_required')
    scope=input_island(board,anchor,terminal,old,face)
    geometry._contacts(board,old,points,time.monotonic()+10.)
    boundaries=geometry._boundary_turns(board,old,points,time.monotonic()+10.)
    geometry._clear_path(board,old,points,time.monotonic()+10.,{})
    voids=contour.no_new_enclosed_voids(board,old,points)
    require(epoch==force._code_identity() and authority==force._hash(Path(__file__)),'kelvin_input_finishing_epoch_changed')
    return plain(dict(policy=POLICY,source_sha256=force._hash(source),board_hint=board_hint,
        sense_evidence=str(evidence_path),sense_evidence_sha256=force._hash(evidence_path),authority_sha256=authority,
        input_pad_uuid=input_pad_uuid,source_pad_uuid=force._uid(anchor),typed_input_ref=row['input_ref'],typed_leg=row['leg'],
        net=row['net'],layer=face,width_nm=width,retired_track_uuids=sorted(cut),points_nm=points,source_points_nm=original,
        allow_locked_source=allow_locked_source,source_length_nm=old_length,candidate_length_nm=new_length,
        native_input_island=scope,source_boundaries=boundaries,enclosed_void_preservation=voids,
        current_budget_or_width_reduced=False,new_vias_or_moved_parts_authorized=False,release_authority=False))

def construct(source,proposal):
    board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
    old=[live[u] for u in proposal['retired_track_uuids']];template=old[0].Duplicate();discard_items(board,old)
    key=repr((POLICY,proposal['source_sha256'],proposal['retired_track_uuids'],proposal['points_nm']))
    for n,(a,z) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        t=template.Duplicate();t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,key+str(n)))))
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));board.Add(t)
    additive._ground_refill(board);return board

def receive_owned_departure_observations(before,after,proposal,boards,added):
    """Receive predictable identity/end changes only after exact reconstruction.

    The ordinary contour comparator cannot own a Kelvin departure edit. This
    ledger retains source exits, projections, directions, target sets, counts
    and all other fields. Fresh actual native BFS paths must still reach the
    same real input. Its identity ledger grants no bypass or current waiver.
    """
    normalized=copy.deepcopy(after);old_rows=before['inner_departure']['details']
    rows=normalized['inner_departure']['details'];require(len(rows)==len(old_rows),'owned_departure_input_inventory_changed')
    inventories=[{force._uid(i) for i in [*(p for fp in b.GetFootprints() for p in fp.Pads()),
        *b.GetTracks(),*b.Zones()]} for b in boards]
    tracks=[{force._uid(t):t for t in b.GetTracks()} for b in boards]
    cut=set(proposal['retired_track_uuids']);added=set(added);ledger=[]
    allowed={'uuid','departure_end_mm','input_contact_paths'}
    def signature(row):return plain({k:v for k,v in row.items() if k not in allowed})
    for first,last in zip(old_rows,rows):
        require((first['input_ref'],first['leg'],first['net'])==(last['input_ref'],last['leg'],last['net']),
            'owned_departure_input_row_identity_changed')
        for name in ('departures','non_sense_departures'):
            old=first.get('native',{}).get(name,[]);new=last.get('native',{}).get(name,[])
            owned=[r for r in old if r['uuid'] in cut]
            if not owned:continue
            require(first['net']==proposal['net'] and first['source_pad']['uuid']==proposal['source_pad_uuid']
                and first['source_pad']==last['source_pad'] and first['sense_terminal']==last['sense_terminal']
                and len(old)==len(new),'owned_departure_source_target_or_count_changed')
            used=set()
            for original in owned:
                matches=[(i,r) for i,r in enumerate(new) if r.get('uuid') in added and signature(r)==signature(original)]
                require(len(matches)==1 and matches[0][0] not in used,'owned_departure_exit_heading_projection_or_reach_changed')
                index,current=matches[0];used.add(index)
                require(current.keys()==original.keys(),'owned_departure_record_fields_changed')
                for observation,live in ((original,tracks[0]),(current,tracks[1])):
                    require(observation['uuid'] in live,'owned_departure_is_not_an_actual_native_track')
                    t=live[observation['uuid']]
                    ends={tuple(v/1e6 for v in p) for p in (t.GetStart(),t.GetEnd())}
                    require({tuple(observation['departure_start_mm']),tuple(observation['departure_end_mm'])}==ends,
                        'owned_departure_endpoints_disagree_with_actual_native_track')
                old_paths=original.get('input_contact_paths',{});new_paths=current.get('input_contact_paths',{})
                require(old_paths.keys()==new_paths.keys(),'owned_departure_native_bfs_target_set_changed')
                for target in old_paths:
                    for path,uid,inventory in [(old_paths[target],original['uuid'],inventories[0]),
                            (new_paths[target],current['uuid'],inventories[1])]:
                        require(isinstance(path,list) and 2<=len(path)<=512 and len(path)==len(set(path))
                            and path[0]==uid and path[-1]==target and set(path)<=inventory,
                            'owned_departure_native_bfs_path_not_bound_to_actual_items')
                ledger.append(dict(input_ref=first['input_ref'],leg=first['leg'],observation=name,
                    retired_departure_uuid=original['uuid'],added_departure_uuid=current['uuid'],
                    source_exit_projection_direction_targets_and_all_nonidentity_fields_exact=True,
                    before_end_mm=original['departure_end_mm'],after_end_mm=current['departure_end_mm'],
                    native_bfs_target_pad_uuids=sorted(old_paths)))
                new[index]=copy.deepcopy(original)
    require(bool(ledger),'actual_owned_kelvin_departure_observation_delta_required')
    return normalized,ledger


def receive(source,candidate,proposal,*,board_hint,sense_timeout_s=40.):
    result=dict(ok=False,complete=False,errors=[],current_or_barrel_qualified=False,full_kelvin_qualification=False,
        routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(q).resolve() for q in (source,candidate)];epoch=force._code_identity()
        families=[force._family(q,board_hint) for q in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in
            ('sense_evidence','input_pad_uuid','retired_track_uuids','points_nm','allow_locked_source')})
        require(fresh==proposal,'stale_or_forged_kelvin_input_finishing_plan')
        require(force._sidecars(source)==force._sidecars(candidate),'kelvin_input_finishing_changed_companions_or_rules')
        _,old_nodes=additive._nodes(source);_,got=additive._nodes(candidate)
        cut=set(proposal['retired_track_uuids']);added=got.keys()-old_nodes.keys()
        require(old_nodes.keys()-got.keys()==cut and len(added)==len(proposal['points_nm'])-1,
            'exact_kelvin_input_track_transaction_required')
        with tempfile.TemporaryDirectory(prefix='cec-kelvin-input-finishing-') as work:
            expected=force._copy_family(source,Path(work)/'expected')
            field._save_field_snapshot(construct(source,proposal),expected);_,nodes=additive._nodes(expected)
            require(got.keys()==nodes.keys() and all(syntax._freeze(n)==syntax._freeze(got[u]) for u,n in nodes.items()),
                'unowned_saved_kelvin_input_or_force_change')
        boards=[pcbnew.LoadBoard(str(q)) for q in (source,candidate)]
        source_live={force._uid(t):t for t in boards[0].GetTracks()}
        boundaries=ordinary._boundaries(*boards,[source_live[u] for u in sorted(cut)],time.monotonic()+10.)
        partitions=ordinary._partition(boards[0],time.monotonic()+10.,retired_uuids=cut)
        following=ordinary._partition(boards[1],time.monotonic()+10.,retained_keys=set().union(*partitions))
        require(all(any(a<=z for z in following) for a in partitions),'kelvin_input_surviving_native_component_lost')
        source_pads={force._uid(p):p for fp in boards[1].GetFootprints() for p in fp.Pads()}
        child_live={force._uid(t):t for t in boards[1].GetTracks()}
        child_island=input_island(boards[1],source_pads[proposal['source_pad_uuid']],source_pads[proposal['input_pad_uuid']],
            [child_live[u] for u in sorted(added)],proposal['layer'])
        require([r['component_pad_uuids'] for r in proposal['native_input_island']['bounds']]==
            [r['component_pad_uuids'] for r in child_island['bounds']],'kelvin_input_component_terminal_set_changed')
        current=debt.receive(source,candidate,board_hint=board_hint)
        require(current['ok'] and current['complete'],'kelvin_input_whole_current_debt_regressed_or_unknown')
        graphs=[_scoped_terminal_graph(b,proposal['net'],timeout_s=10.) for b in boards]
        require(graphs[0]['pad_uuids']==graphs[1]['pad_uuids'],'kelvin_input_actual_terminal_inventory_changed')
        with force._thermal_hint(board_hint):
            before,after=[sense.replay(q,board_hint=board_hint,timeout_s=sense_timeout_s) for q in (source,candidate)]
        prior=sense.admit_changed_net(before,before,proposal['net']);actual=sense.admit_changed_net(before,after,proposal['net'])
        require(prior['ok'] and actual['ok'] and prior['expected_legs']==actual['expected_legs']
            and prior['checked']==actual['checked'],'absolute_source_and_candidate_clipped_kelvin_readmission_required')
        transforms=sense.native_copper_transform_inventory(*boards,modified_nets=[proposal['net']])
        cuts=sense.compare_contour_preservation(before,after,modified_nets=[proposal['net']],native_copper_transforms=transforms)
        result.update(fresh_source_and_candidate_clipped_net_admission=actual,raw_whole_parent_clipped_preservation=cuts)
        require(cuts['comparison_complete'] and not cuts['errors'],'whole_parent_kelvin_input_contour_comparison_unknown')
        received,ledger=receive_owned_departure_observations(before,after,proposal,boards,added)
        preserved=sense.compare_contour_preservation(before,received,modified_nets=[proposal['net']],native_copper_transforms=transforms)
        result.update(whole_parent_clipped_preservation=preserved,owned_departure_observation_ledger=ledger,
            candidate_native_input_island=child_island)
        require(preserved['same_evidence'] and preserved['comparison_complete'],'whole_parent_kelvin_input_contour_preservation_refused')
        require(epoch==force._code_identity() and families==[force._family(q,board_hint) for q in (source,candidate)],
            'kelvin_input_finishing_source_or_epoch_changed')
        require(proposal['authority_sha256']==force._hash(Path(__file__))
            and proposal['sense_evidence_sha256']==force._hash(Path(proposal['sense_evidence'])),
            'kelvin_input_finishing_owner_or_source_evidence_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            retired_track_uuids=sorted(cut),added_native_uuids=sorted(added),exact_native_source_reconstruction=True,
            actual_drilled_terminal_graphs=graphs,whole_parent_current_receiving=current,
            restored_source_boundaries=boundaries,all_surviving_native_partitions_preserved=True,
            old_force_copper_parts_widths_budgets_and_source_land_exact=True,
            source_qualified_input_island_independently_rederived=True,new_vias=0,pads_moved=0,
            centerline_removed_mm=(proposal['source_length_nm']-proposal['candidate_length_nm'])/1e6,
            native_custom_rules_fields_pairs_ground_returns_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result

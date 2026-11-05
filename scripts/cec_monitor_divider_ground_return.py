"""Source-compiled full-class return for a fresh monitor-divider land.

Identity-only requests. No caller widths, paths, role callbacks, anchor lists,
new barrels, Source cuts, placements, current ratings or release authority.
Saved receiving is local scope only; whole-board/native admission remains mandatory.
"""
import hashlib,json,math,time,uuid
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_source_divider_ground_span as divider
import cec_source_ground_leaf as fresh
import cec_source_no_connect as source_nc
import cec_synth_pipeline as synth
import cec_device_power_roles as roles
import cec_force_current as force
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_fr as fr
import cec_ground_component_join as join
import cec_ground_return_shortcut as reference
import cec_ground_mesh_entry as mesh
import cec_ground_return_preservation as returns
import cec_native_partition_pair as partitions
import cec_source_literal_additions as literal
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_route_quality as craft
import cec_current_debt as current
import cec_route_dimensions as dimensions


def _need(ok,reason):
    if not ok:raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10,
          'bounded_monitor_ground_lease_required')
    return time.monotonic()+seconds


def _tick(deadline):
    _need(time.monotonic()<deadline,'monitor_ground_deadline')


def _remaining(deadline):
    _tick(deadline);return min(10.,deadline-time.monotonic())


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _epoch():
    modules=(divider,fresh,source_nc,synth,roles,force,row,cells,fab,fr,join,reference,mesh,returns,
        partitions,literal,additive,field,craft,current,dimensions)
    return dict(production_code=force._code_identity(),operator_path=str(Path(__file__).resolve()),
        operator_sha256=force._hash(Path(__file__)),
        module_dependencies={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in modules})


def _source_owner(board,hint,pad_uuid,deadline):
    """Reuse exact selected divider/pin compiler, without its old-span premise.

    No caught refusal grants authority: every canonical predicate preceding
    the existing span owner's old-return prerequisite is re-executed here.
    """
    selected=divider._native_owner(board,pad_uuid,deadline)
    ground,node,uppernode,upperpower,monitor,supply,contract=selected
    root=source_nc._root(board,hint).resolve()
    files,hashes,instances=fresh._hierarchy(root,deadline)
    tree,export=fresh._export(root,deadline);comps,nets,node_net=fresh._tables(tree)
    exporter=Path(export['exporter']).resolve()
    _need(exporter.is_file()and force._hash(exporter)==export['exporter_sha256'],
          'monitor_ground_actual_fresh_exporter_required')
    owners={force._uid(p.GetParentFootprint()):p.GetParentFootprint()for p in(ground,uppernode,monitor)}
    identities={};pins={}
    for uid,fp in owners.items():
        _tick(deadline)
        identity=fresh._identity(board,fp.GetReference(),comps,instances,deadline)
        identities[uid]=identity;pins[uid]=divider._pins(identity)
        for pad in fp.Pads():
            number=str(pad.GetNumber());actual=[p for p in identity[3]['pins']if p['num']==number]
            _need(len(actual)==1 and actual[0]['type']==pins[uid][number][0],
                  'monitor_ground_complete_actual_source_pin_type_required')
            _need(all(not metadata or metadata==expected for metadata,expected in(
                (str(pad.GetPinType()),pins[uid][number][0]),(str(pad.GetPinFunction()),pins[uid][number][1]))),
                'monitor_ground_native_pin_metadata_contradiction')
            _need(node_net.get((fp.GetReference(),number))==str(pad.GetNetname()),
                  'monitor_ground_complete_fresh_membership_required')
    fp=monitor.GetParentFootprint();model=roles.footprint_contract(fp);pinmap=pins[force._uid(fp)]
    _need(model and set(model['pins'])==set(pinmap)
        and pinmap[str(monitor.GetNumber())]==('input',contract['function'])
        and pinmap[str(supply.GetNumber())]==('power_in',{'7':'IN1','2':'IN2'}.get(str(supply.GetNumber()))),
        'monitor_ground_actual_manufacturer_monitor_and_supply_required')
    for passive in(ground.GetParentFootprint(),uppernode.GetParentFootprint()):
        _need(all(p[0]=='passive'for p in pins[force._uid(passive)].values()),
              'monitor_ground_actual_selected_passive_resistors_required')
    for pad in selected[:6]:fresh._pin(identities[force._uid(pad.GetParentFootprint())],str(pad.GetNumber()))
    members={(p.GetParentFootprint().GetReference(),str(p.GetNumber()))for p in(node,uppernode,monitor)}
    _need(nets.get(str(node.GetNetname()))==members,'monitor_ground_fresh_closed_three_land_node_required')
    grounds=[]
    for number,kind in model['pins'].items():
        pad=fp.FindPadByNumber(number)
        if kind=='ground'and pad is not None and pad.GetNetCode()==ground.GetNetCode():
            _need(pinmap[number]==('power_in','GND'),'monitor_ground_actual_device_return_required')
            grounds.append(force._uid(pad))
    _need(grounds,'monitor_ground_actual_manufacturer_ground_required')
    _need(hashes=={str(p):force._hash(p)for p in files}
        and force._hash(exporter)==export['exporter_sha256'],'monitor_ground_canonical_source_changed')
    proof=dict(kind='fresh_closed_manufacturer_monitor_and_selected_ground_resistor',
        canonical_root=str(root),schematic_files_sha256=hashes,
        exporter=dict(path=str(exporter),sha256=export['exporter_sha256']),
        complete_export_membership_sha256=_digest({k:sorted(list(v)for v in vs)for k,vs in sorted(nets.items())}),
        lower_resistor_uuid=force._uid(ground.GetParentFootprint()),ground_pad_uuid=pad_uuid,
        lower_node_pad_uuid=force._uid(node),upper_resistor_uuid=force._uid(uppernode.GetParentFootprint()),
        upper_node_pad_uuid=force._uid(uppernode),upper_power_pad_uuid=force._uid(upperpower),
        monitor_pad_uuid=force._uid(monitor),associated_supply_pad_uuid=force._uid(supply),
        manufacturer_monitor=contract,actual_device_ground_pad_uuids=sorted(grounds),
        closed_node_members=sorted(list(v)for v in members),no_new_current_or_operating_rating=True)
    return ground,proof


def _owner_live(proof):
    return (all(force._hash(Path(p))==h for p,h in proof['schematic_files_sha256'].items())
        and force._hash(Path(proof['exporter']['path']))==proof['exporter']['sha256'])


def _scope(board,hint,pad_uuid,deadline):
    ground,owner=_source_owner(board,hint,pad_uuid,deadline)
    source=Path(board.GetFileName());project=source.with_suffix('.kicad_pro')
    _need(project.is_file()and not project.is_symlink(),'monitor_ground_actual_source_project_required')
    spec=cells._netclass(board,'GND')
    table=dimensions.NetclassTable.from_board_path(source);name=table.resolve_name('GND')
    declared=table.classes.get(name,{})
    _need(type(declared.get('track_width'))in(int,float)and math.isfinite(declared['track_width'])
        and declared['track_width']>0 and round(declared['track_width']*1e6)==int(spec['width']),
        'monitor_ground_positive_saved_class_width_required')
    width=max(int(spec['width']),int(board.GetDesignSettings().m_TrackMinWidth),200000)
    gap=max(int(spec['clearance']),int(board.GetDesignSettings().m_MinClearance),200000)
    face=cells.cec_return_escape.smd_surface_layer(ground)
    _need(face in(pcbnew.F_Cu,pcbnew.B_Cu)and not ground.HasHole()
        and 0<width<=2000000 and fab._pad_contains_circle(ground,ground.GetPosition(),math.ceil(width/2),tolerance_nm=0),
        'monitor_ground_full_class_source_land_required')
    _need(face not in{board.GetLayerID(n)for n in fr.plane_layers(board)},
          'monitor_ground_no_new_reference_face_material')
    context=join._context(board,hint,deadline);key=force._item_key(ground)
    parts=[p for p in context['ground']if key in p]
    _need(len(parts)==1 and parts[0]=={key}and parts[0]!=context['root'],
          'monitor_ground_one_native_singleton_lower_land_required')
    candidates=[];source_tracks={force._uid(t):t for t in board.GetTracks()}
    for uid in context['reference_barrel_uuids']:
        via=source_tracks[uid];contacts=reference._reference_contacts(board,via)
        diameter=via.GetWidth(via.TopLayer())/1e6
        ordinary=fab.board_legal_through_via_geometry(board,diameter,via.GetDrillValue()/1e6)[:2]
        _need(ordinary==(diameter,via.GetDrillValue()/1e6)
            or fab.local_pofv_via_decision(board,via)[0],
            'monitor_ground_existing_root_process_required')
        mesh._reference_envelopes(board,via,contacts,deadline)
        for item_key in context['root']:
            pad=context['live'][item_key]
            if (pad.GetClass()=='PAD'and not pad.HasHole()
                and cells.cec_return_escape.smd_surface_layer(pad)==face
                and tuple(pad.GetPosition())==tuple(via.GetPosition())
                and fab._pad_contains_circle(pad,pad.GetPosition(),math.ceil(width/2),tolerance_nm=0)):
                candidates.append((math.dist(tuple(ground.GetPosition()),tuple(pad.GetPosition())),force._uid(pad),pad,uid,contacts))
    _need(candidates,'monitor_ground_actual_full_land_reference_anchor_required')
    _,_,target,via_uid,contacts=min(candidates,key=lambda v:(v[0],v[1]))
    return dict(ground=ground,target=target,face=int(face),width=width,gap=gap,context=context,
        lower_component=parts[0],owner=owner,anchor=dict(pad_uuid=force._uid(target),via_uuid=via_uid,
            actual_reference_contacts=contacts,source_barrel_unchanged=True,new_capacity_credited=False),
        project_sha256=force._hash(project))


def _paths(board,scope,deadline):
    """Finite proposal boundaries from actual obstructing Source lands only."""
    a=tuple(scope['ground'].GetPosition());z=tuple(scope['target'].GetPosition());w=scope['width'];gap=scope['gap']
    paths=[[a,z]];shape=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),w)
    pads=[p for fp in board.GetFootprints()for p in fp.Pads()if p.IsOnLayer(scope['face'])
        and p.GetNetCode()!=scope['ground'].GetNetCode()and p.GetEffectiveShape(scope['face']).Collide(shape,gap)]
    for pad in sorted(pads,key=lambda p:force._uid(p))[:16]:
        _tick(deadline);box=pad.GetBoundingBox();margin=math.ceil(w/2)+gap+50000
        for sign,x in((1,box.GetX()-margin),(-1,box.GetRight()+margin)):
            if sign*x>=min(sign*a[0],sign*z[0])or abs(z[1]-a[1])<=2*w:continue
            sy=1 if z[1]>a[1]else-1
            paths.append([a,(x+sign*w,a[1]),(x,a[1]+sy*w),(x,z[1]-sy*w),(x+sign*w,z[1]),z])
    seen=set()
    for points in paths:
        points=tuple(points)
        if points in seen:continue
        seen.add(points)
        length=sum(math.dist(s,t)for s,t in zip(points,points[1:]))
        if not 0<length<=12000000:continue
        if any(s==t or not craft.is_canonical_stroke(s,t,tolerance_nm=0)for s,t in zip(points,points[1:])):continue
        yield points


def _rows(scope,points):
    return [dict(net='GND',layer=scope['face'],width_nm=scope['width'],start_nm=list(a),end_nm=list(z))
        for a,z in zip(points,points[1:])]


def _track_ids(source_sha,pad_uuid,rows):
    return [str(uuid.uuid5(uuid.NAMESPACE_URL,source_sha+':source-monitor-divider-ground-v1:'+pad_uuid+':'+str(index)+':'+_digest(r)))
        for index,r in enumerate(rows)]


def _make(board,source_sha,pad_uuid,rows):
    added=[];old={force._uid(t)for t in board.GetTracks()}
    for uid,r in zip(_track_ids(source_sha,pad_uuid,rows),rows):
        _need(uid not in old,'monitor_ground_fresh_native_identity_required')
        t=pcbnew.PCB_TRACK(board);t.SetNetCode(board.GetNetcodeFromNetname('GND'));t.SetLayer(r['layer']);t.SetWidth(r['width_nm'])
        t.SetStart(pcbnew.VECTOR2I(*r['start_nm']));t.SetEnd(pcbnew.VECTOR2I(*r['end_nm']));t.SetLocked(True)
        t.m_Uuid.Clone(pcbnew.KIID(uid));board.Add(t);added.append(uid)
    return added


def _qualify(parent,child,scope,rows,deadline):
    cache={};net=scope['ground'].GetNetCode()
    for r in rows:
        _tick(deadline);a,z=pcbnew.VECTOR2I(*r['start_nm']),pcbnew.VECTOR2I(*r['end_nm'])
        _need(fr._edge_leg_clear(parent,a,z,scope['width']/2+scope['gap'])
            and fr._tap_foreign_clear(parent,a,z,scope['width'],scope['face'],scope['gap'],{net},foreign_cache=cache),
            'monitor_ground_foreign_or_edge_clearance')
        # There is deliberately NO refill lease. Ordinary foreign fills are
        # just as immutable here as protected power collectors; a generic
        # router's potential future antipad cannot clear this literal child.
        shape=pcbnew.SHAPE_SEGMENT(a,z,scope['width']);resolve=fr._foreign_clearance_resolver(parent)
        for zone in parent.Zones():
            _tick(deadline)
            if zone.GetIsRuleArea()or zone.GetNetCode()==net or not zone.IsOnLayer(scope['face']):continue
            _need(zone.IsFilled()and zone.HasFilledPolysForLayer(scope['face']),
                  'monitor_ground_unknown_foreign_fill_refused')
            gap=max(scope['gap'],int(zone.GetLocalClearance()),int(resolve(zone,scope['face'])))
            _need(not zone.GetFilledPolysList(scope['face']).Collide(shape,gap),
                  'monitor_ground_immutable_foreign_fill_refused')
    cq=craft.assess_proposed_route(parent,rows,deadline=deadline)
    _need(cq.get('ok')is True and cq.get('complete')is True,'monitor_ground_craft_refused')
    fq=field.assess_proposed_tracks(parent,rows,board_path=parent.GetFileName(),board_hint=scope['hint'],deadline=deadline)
    _need(fq.get('ok')is True and fq.get('complete')is True,'monitor_ground_field_refused')
    pq=partitions.compare(parent,child,timeout_s=_remaining(deadline))
    _need(pq.get('available')is True and pq.get('preserved')is True,'monitor_ground_retained_partitions_refused')
    rq=returns.receive(parent,child,timeout_s=_remaining(deadline))
    _need(rq.get('ok')is True and rq.get('complete')is True,'monitor_ground_known_returns_refused')
    inv=partitions._inventory(child,deadline,dict(items=16384,polygons=4096,vertices=200000))
    keys=set(scope['context']['live']);lower=scope['lower_component'];root=scope['context']['root']
    key=force._item_key(scope['ground']);merged=inv['components'][inv['component_of'][key]]&keys
    _need(merged==root|lower,'monitor_ground_exact_singleton_to_existing_root_gain_required')
    new_ground=[part for part in inv['components']if all(
        item.GetNetname()=='GND'for item in inv['objects']if force._item_key(item)in part)]
    _need(len(new_ground)==len(scope['context']['ground'])-1,'monitor_ground_strict_one_component_gain_required')
    return dict(native_foreign_and_edge=True,craft=True,field=True,retained_partitions=True,known_returns=True,
        source_ground_components=len(scope['context']['ground']),child_ground_components=len(new_ground),
        exact_lower_and_existing_root_only=True,source_unknown_return_not_qualified=True)


def plan(source,*,board_hint,ground_pad_uuid,timeout_s=10.):
    deadline=_deadline(timeout_s)
    _need(type(board_hint)is str and board_hint and type(ground_pad_uuid)is str and ground_pad_uuid,
          'monitor_ground_identity_only_request_required')
    source=Path(source).resolve(strict=True);epoch=_epoch();sha=force._hash(source);family=force._family(source,board_hint)
    parent=pcbnew.LoadBoard(str(source));binding=row._source_binding(parent);scope=_scope(parent,board_hint,ground_pad_uuid,deadline)
    scope['hint']=board_hint;trials=[]
    for points in _paths(parent,scope,deadline):
        rows=_rows(scope,points);child=pcbnew.LoadBoard(str(source));_make(child,sha,ground_pad_uuid,rows)
        try:proof=_qualify(parent,child,scope,rows,deadline)
        except ValueError as e:
            trials.append(str(e));_tick(deadline);continue
        _need(sha==force._hash(source)and family==force._family(source,board_hint)and epoch==_epoch()
            and binding==row._source_binding(parent)and _owner_live(scope['owner']),
            'monitor_ground_source_family_or_code_changed')
        _tick(deadline)
        return dict(schema=1,scope='source_additive_monitor_divider_ground_return',source=str(source),source_sha256=sha,
            board_hint=board_hint,ground_pad_uuid=ground_pad_uuid,source_binding=binding,source_family=family,code_epoch=epoch,
            owner=scope['owner'],existing_anchor=scope['anchor'],source_project_sha256=scope['project_sha256'],
            rows=rows,preflight=proof,failed_proposal_reasons=trials,new_holes=0,source_cuts=0,
            current_budget_or_capacity_inferred=False,current_qualified=False,release_authority=False,routing_admitted=False)
    raise ValueError('monitor_ground_finite_source_boundary_proposals_refused:'+str(trials))


def _literal_child(source,q):
    board=pcbnew.LoadBoard(str(source));_make(board,q['source_sha256'],q['ground_pad_uuid'],q['rows'])
    writer=pcbnew.STRING_FORMATTER();pcbnew.PCB_IO_KICAD_SEXPR().FormatBoardToFormatter(writer,board)
    return literal.assemble(source.read_text(),writer.GetString(),ground_ids=())


def construct_private(source,proposal,out,*,timeout_s=10.):
    deadline=_deadline(timeout_s);source=Path(source).resolve(strict=True)
    q=plan(source,board_hint=proposal['board_hint'],ground_pad_uuid=proposal['ground_pad_uuid'],timeout_s=_remaining(deadline))
    _need(q==proposal,'monitor_ground_stale_or_forged_proposal')
    text=_literal_child(source,q);_tick(deadline)
    _need(q['code_epoch']==_epoch()and q['source_sha256']==force._hash(source)
        and q['source_family']==force._family(source,q['board_hint']),'monitor_ground_changed_before_private_write')
    candidate=force._copy_family(source,Path(out));candidate.write_text(text)
    _tick(deadline)
    return dict(candidate=str(candidate),candidate_sha256=force._hash(candidate),source_unchanged=True,
        independent_saved_receiving_still_required=True,routing_admitted=False,release_authority=False)


def receive(source,candidate,*,board_hint,ground_pad_uuid,timeout_s=10.):
    """Three explicit, ordered constituents, each <=timeout_s<=10 seconds.

    Aggregate <=3*timeout_s; no expired constituent borrows another's lease.
    Source compilation is fresh once in THIS invocation, never external data.
    Only final current/live receiving can set complete. No whole-board or release authority.
    """
    result=dict(ok=False,complete=False,errors=[],current_qualified=False,
        routing_admitted=False,release_authority=False)
    try:
        first_deadline=_deadline(timeout_s);aggregate_deadline=first_deadline+2*timeout_s
        phase_start=time.monotonic();deadline=first_deadline
        result['bounded_composition']=dict(constituents=['source_inventory','actual_saved_native_material','final_current_and_liveidentity'],
            per_constituent_limit_s=timeout_s,aggregate_limit_s=3*timeout_s,no_borrowed_time=True)
        result['timings_s']={}
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        _need(source!=candidate,'monitor_ground_distinct_saved_boundaries_required')
        epoch=_epoch();families=[force._family(p,board_hint)for p in(source,candidate)];sha=force._hash(source)
        # This receiver independently compiles its OWN pristine Source once.
        # Do not qualify an expected RAM child and then count it as saved
        # evidence: ALL physical guards below inspect the ACTUAL saved child.
        parent=pcbnew.LoadBoard(str(source))
        scope=_scope(parent,board_hint,ground_pad_uuid,deadline);scope['hint']=board_hint
        _tick(deadline);result['timings_s']['source_inventory']=time.monotonic()-phase_start
        phase_start=time.monotonic();deadline=min(aggregate_deadline,phase_start+timeout_s)
        child=pcbnew.LoadBoard(str(candidate))
        old={force._uid(t)for t in parent.GetTracks()};added={force._uid(t):t for t in child.GetTracks()if force._uid(t)not in old}
        _need(1<=len(added)<=16 and all(t.GetClass()=='PCB_TRACK'for t in added.values()),
              'monitor_ground_saved_tracks_only')
        rows=None
        for points in _paths(parent,scope,deadline):
            proposed=_rows(scope,points);ids=_track_ids(sha,ground_pad_uuid,proposed)
            if set(ids)!=set(added):continue
            if all(t.GetNetname()=='GND'and t.GetLayer()==r['layer']and t.GetWidth()==r['width_nm']
                and list(t.GetStart())==r['start_nm']and list(t.GetEnd())==r['end_nm']and t.IsLocked()
                for uid,r in zip(ids,proposed)for t in[added[uid]]):
                rows=proposed;break
        _need(rows is not None,'monitor_ground_exact_source_derived_saved_portfolio_required')
        q=dict(source_sha256=sha,ground_pad_uuid=ground_pad_uuid,rows=rows)
        _need(candidate.read_text()==_literal_child(source,q)and force._sidecars(source)==force._sidecars(candidate),
              'monitor_ground_exact_complete_literal_additions_required')
        delta=additive.receive(source,candidate,board_hint=board_hint,timeout_s=_remaining(deadline))
        _need(delta.get('ok')is True and delta.get('complete')is True,'monitor_ground_public_strict_additive_refused:'+str(delta.get('errors')))
        physical=_qualify(parent,child,scope,rows,deadline)
        _tick(deadline);result['timings_s']['actual_saved_native_material']=time.monotonic()-phase_start
        phase_start=time.monotonic();deadline=min(aggregate_deadline,phase_start+timeout_s)
        debt=current.receive(source,candidate,board_hint=board_hint)
        _need(debt.get('ok')is True and debt.get('complete')is True,'monitor_ground_existing_current_debt_refused:'+str(debt.get('errors')))
        _need(epoch==_epoch()and families==[force._family(p,board_hint)for p in(source,candidate)]and _owner_live(scope['owner']),
              'monitor_ground_saved_source_family_or_code_changed')
        _tick(deadline)
        result['timings_s']['final_current_and_liveidentity']=time.monotonic()-phase_start
        _tick(aggregate_deadline)
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            owner=scope['owner'],existing_anchor=scope['anchor'],physical=physical,
            strict_literal_additive_receiving=delta,current_debt_nonregression=debt,
            native_DRC_and_original_parent_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError)as e:result['errors'].append(type(e).__name__+':'+str(e))
    return result

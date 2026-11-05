"""Complete one Source-declared address tie without moving its device.

An address pin is not a generic supply terminal. This distinct owner requires
the actual manufacturer's address role, a freshly exported same-package
power-input tie and uniquely assigned local bypass. Only a stranded address
land may join that existing power component. Every new conductor retains the
WHOLE unchanged aggregate current; a short pad-local prefix may be below the
preferred class width only after the existing native endpoint geometry proof.
No guessed address load, source cut, placement, barrel or release authority.
"""
from pathlib import Path
import json,math,time
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_constraints as constraints
import cec_device_power_roles as roles
import cec_distributed_supply as supply
import cec_fab_check as factory
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_route_dimensions as dimensions
import cec_route_quality as craft
import cec_route_corner_contacts as copper
import cec_source_ground_leaf as canonical
import cec_source_literal_additions as literal


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _deadline(seconds):
    _require(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10,
        'bounded_stationary_address_supply_lease_required')
    return time.monotonic()+seconds


def _left(deadline):
    left=deadline-time.monotonic()
    _require(left>0,'stationary_address_supply_deadline')
    return min(10.,left)


def _saved_floors(board,source):
    """Read the exact Source project too; a native cached default cannot win."""
    project=dimensions.project_path(source)
    _require(project is not None and project.stat().st_size<=4*1024*1024,
        'bounded_existing_stationary_address_project_required')
    digest=force._hash(project)
    rules=json.loads(project.read_text()).get('board',{}).get('design_settings',{}).get('rules',{})
    _require(type(rules)is dict,'literal_stationary_address_project_rules_required')
    result=dict(track_width_nm=int(board.GetDesignSettings().m_TrackMinWidth),
        clearance_nm=int(board.GetDesignSettings().m_MinClearance))
    for name,key in(('min_track_width','track_width_nm'),('min_clearance','clearance_nm')):
        if name not in rules:continue
        value=rules[name]
        _require(type(value)in(int,float)and math.isfinite(value)and 0<=value<=10,
            'finite_stationary_address_source_process_floor_required')
        result[key]=max(result[key],math.ceil(value*1e6))
    return dict(result,project=str(project.resolve()),project_sha256=digest)


def _canonical_owner(board,owner,cap,hint,deadline,required_owner_pins):
    root=canonical.source_nc._root(board,hint)
    _require(root is not None,'stationary_address_current_schematic_required')
    root=Path(root).resolve(strict=True)
    files,hashes,instances=canonical._hierarchy(root,deadline)
    tree,exporter=canonical._export(root,deadline)
    comps,nets,node_net=canonical._tables(tree)
    records={}
    for fp in(owner,cap):
        _left(deadline)
        ref=fp.GetReference();identity=canonical._identity(board,ref,comps,instances,deadline)
        pins={}
        for pad in fp.Pads():
            number=str(pad.GetNumber())
            _require(node_net.get((ref,number))==pad.GetNetname(),
                'stationary_address_complete_selected_component_source_netmap_required')
            actual=[p for p in identity[3]['pins']if p['num']==number]
            _require(len(actual)==1,'complete_unique_stationary_address_source_pinmap_required')
            # An unrelated explicitly NC input remains NC. Only the actual
            # address/supply tie and both bypass terminals require a wired
            # Source pin; no NC marker may own a new attachment.
            pins[number]=(canonical._pin(identity,number)if fp is cap
                or number in required_owner_pins else actual[0])
        records[force._uid(fp)]=dict(ref=ref,symbol_uuid=identity[3]['uuid'],
            source=str(identity[1]),pins={n:dict(type=p['type'])for n,p in pins.items()})
    _require(all(force._hash(p)==h for p,h in hashes.items()),
        'stationary_address_schematic_changed_during_export')
    return dict(root=str(root),hierarchy=hashes,exporter=exporter,components=records)


def _live_canonical(authority):
    return (all(force._hash(p)==h for p,h in authority['hierarchy'].items())
        and force._hash(authority['exporter']['exporter'])==authority['exporter']['exporter_sha256'])


def plan(board,source,*,board_hint,pad_uuid,timeout_s=10.):
    deadline=_deadline(timeout_s)
    _require(type(board_hint)is str and bool(board_hint)and type(pad_uuid)is str and bool(pad_uuid),
        'explicit_stationary_address_source_identity_required')
    source=Path(source).resolve(strict=True)
    _require(Path(board.GetFileName()).resolve()==source,'literal_saved_stationary_address_board_required')
    digest=force._hash(source);before=binding._source_binding(board)
    floors=_saved_floors(board,source)
    pads=[p for f in board.GetFootprints()for p in f.Pads()]
    _require(len(pads)+len(list(board.GetTracks()))<=16384,
        'stationary_address_native_inventory_bound')
    by_uid={force._uid(p):p for p in pads}
    _require(len(by_uid)==len(pads)and pad_uuid in by_uid,'unique_stationary_address_land_required')
    pad=by_uid[pad_uuid];owner=pad.GetParentFootprint();model=roles.footprint_contract(owner)
    _require(model and not owner.IsDNP()and model['pins'].get(pad.GetNumber())=='address'
        and set(p.GetNumber()for p in owner.Pads())==set(model['pins'])
        and owner.GetPadCount()==len(model['pins'])and pad.GetNetCode()>0
        and pad.GetNetname()!='GND'and not pad.HasHole()
        and pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
        and pad.GetShape()in(pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,
            pcbnew.PAD_SHAPE_CIRCLE,pcbnew.PAD_SHAPE_OVAL)
        and len(list(pad.GetLayerSet().CuStack()))==1,
        'complete_manufacturer_surface_supply_tied_address_required')
    face=int(next(iter(pad.GetLayerSet().CuStack())));net=str(pad.GetNetname())
    graph=fr._read_only_route_connectivity(board)
    _require(not any(force._uid(i)!=pad_uuid for i in graph.GetConnectedItems(pad)),
        'stationary_address_source_land_must_be_stranded')
    powers=[p for p in owner.Pads()if model['pins'].get(p.GetNumber())=='power_input'
        and p.GetNetname()==net and p.GetNetCode()==pad.GetNetCode()
        and not p.HasHole()and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
        and list(map(int,p.GetLayerSet().CuStack()))==[face]]
    _require(len(powers)==1,'unique_same_package_same_surface_power_input_required')
    power=powers[0]
    assignments=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    selected=[r for r in assignments['assigned'].values()if r['requirement']['ref']==owner.GetReference()
        and str(r['requirement']['pin'])==str(power.GetNumber())and r['requirement']['rail']==net]
    _require(len(selected)==1,'unique_source_assigned_stationary_address_bypass_required')
    cap=board.FindFootprintByReference(selected[0]['cap_ref'])
    _require(cap is not None and not cap.IsDNP()and cap.GetPadCount()==2,
        'actual_selected_stationary_address_bypass_required')
    cap_pads=list(cap.Pads());supply_pads=[p for p in cap_pads if p.GetNetname()==net]
    _require(len(supply_pads)==1 and {p.GetNetname()for p in cap_pads}=={net,'GND'}
        and all(not p.HasHole()and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
            and list(map(int,p.GetLayerSet().CuStack()))==[face]for p in cap_pads)
        and math.dist(tuple(supply_pads[0].GetPosition()),tuple(power.GetPosition()))<=3500000,
        'local_same_surface_grounded_selected_bypass_required')
    reached={force._uid(power),*(force._uid(i)for i in graph.GetConnectedItems(power))}
    _require(force._uid(supply_pads[0])in reached and pad_uuid not in reached,
        'existing_power_input_and_selected_bypass_component_required')
    authority=_canonical_owner(board,owner,cap,board_hint,deadline,
        {str(pad.GetNumber()),str(power.GetNumber())})
    pin_types=authority['components'][force._uid(owner)]['pins']
    _require(pin_types[pad.GetNumber()]['type']in('input','passive')
        and pin_types[power.GetNumber()]['type']=='power_in',
        'canonical_address_and_power_input_pin_types_required')
    report=supply.audit(board,board_hint=board_hint,include_nets=[net],
        netclass_resolver=fr._project_netclass_resolver(str(source),board=board))
    _require(set(report['contracts'])=={net},'unchanged_explicit_aggregate_supply_contract_required')
    contract=report['contracts'][net];name=fab.COPPER_LAYER_IDS[face]
    _require(name in contract['routing_layers'],'source_address_surface_not_an_approved_signal_face')
    full=math.ceil(contract['required_by_layer_mm'][name]*1e6)
    profile=fab.get_profile(contract['profile'])
    rules=factory.profile_rules(factory.PROFILES[profile['vendor']],
        fab.stackup_oz(contract['profile'])[name],profile)
    physics=dimensions.current_trace_widths(contract['current_authority'],(name,),
        contract['profile'],rise_c=contract['rise_c'])[name]
    floor=max(floors['track_width_nm'],math.ceil(max(physics,rules['track'])*1e6))
    _require(0<floor<=full,'complete_full_aggregate_address_prefix_floor_required')
    gap=max(floors['clearance_nm'],math.ceil(contract['clearance_mm']*1e6))
    targets=[dict(uuid=force._uid(t),start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()))
        for t in board.GetTracks()if force._uid(t)in reached and t.GetClass()=='PCB_TRACK'
        and t.GetNetname()==net and int(t.GetLayer())==face and t.GetWidth()>=full
        and t.GetLength()>0 and not t.HasSolderMask()]
    _require(targets,'retained_full_class_source_supply_target_required')
    _require(force._hash(source)==digest and binding._source_binding(board)==before
        and force._hash(floors['project'])==floors['project_sha256']and _live_canonical(authority),
        'stationary_address_source_changed_during_planning')
    _left(deadline)
    return dict(schema=1,scope='stationary_source_address_to_own_supply_component',complete=True,
        source=str(source),source_sha256=digest,source_native_binding=before,board_hint=board_hint,
        pad_uuid=pad_uuid,power_pad_uuid=force._uid(power),bypass_supply_pad_uuid=force._uid(supply_pads[0]),
        owner_uuid=force._uid(owner),manufacturer_contract=model,canonical_source=authority,
        net=net,layer_id=face,full_width_nm=full,whole_current_prefix_floor_nm=floor,
        clearance_nm=gap,exact_saved_source_process_floors=floors,
        source_targets=targets,source_target_component_uuids=sorted(reached),
        source_components=report['nets'][net]['native_components'],aggregate_contract=contract,
        current_authority_changed=False,guessed_address_load=False,old_thin_copper_credited=False,
        placement_authority=False,retirement_authority=False,release_authority=False)


def _ordered(rows,start):
    _require(1<=len(rows)<=16,'bounded_address_track_chain_required')
    adj={}
    for t in rows:
        a,b=tuple(t.GetStart()),tuple(t.GetEnd())
        _require(a!=b and craft.is_canonical_stroke(a,b,tolerance_nm=0),
            'canonical_stationary_address_strokes_required')
        for p,q in((a,b),(b,a)):adj.setdefault(p,[]).append((force._uid(t),q))
    _require(start in adj and len(adj[start])==1 and len(adj)==len(rows)+1
        and sum(len(q)==1 for q in adj.values())==2 and all(len(q)<=2 for q in adj.values()),
        'one_simple_rooted_stationary_address_chain_required')
    path=[start];seen=set()
    while len(seen)<len(rows):
        nexts=[(u,p)for u,p in adj[path[-1]]if u not in seen]
        _require(len(nexts)==1,'whole_stationary_address_chain_required')
        uid,at=nexts[0];seen.add(uid);path.append(at)
    _require(sum(math.dist(a,b)for a,b in zip(path,path[1:]))<=16000000,
        'bounded_local_stationary_address_length_required')
    return path


def _literal_contacts(parent,rows,path,proposal,deadline):
    """Actual copper, not endpoint adjacency or same-net clearance exemption."""
    face=proposal['layer_id'];lookup={frozenset((tuple(t.GetStart()),tuple(t.GetEnd()))):t for t in rows}
    ordered=[lookup[frozenset((a,b))]for a,b in zip(path,path[1:])]
    shapes=[copper.native_contact_polygon(t,face,deadline)for t in ordered]
    def touches(a,b):
        _left(deadline)
        # A disjoint native bounding box is a negative broad-phase proof,
        # never a positive contact test or a substitute for native polygons.
        return a.BBox().Intersects(b.BBox())and a.Collide(b,0)
    for i,shape in enumerate(shapes):
        for other in shapes[i+2:]:
            _left(deadline)
            # Area-only Boolean intersection drops coincident copper edges.
            # Native contact polygons also let us reject exact tangent contact.
            _require(not touches(shape,other),'nonadjacent_address_copper_self_contact_forbidden')
    root=next(p for f in parent.GetFootprints()for p in f.Pads()if force._uid(p)==proposal['pad_uuid'])
    root_shape=copper.native_contact_polygon(root,face,deadline)
    end=pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(*path[-1]),proposal['full_width_nm'])
    kernel=pcbnew.SHAPE_POLY_SET();end.TransformToPolygon(kernel,1,pcbnew.ERROR_INSIDE)
    material=[*parent.GetTracks(),*(p for f in parent.GetFootprints()for p in f.Pads()),
        *[z for z in parent.Zones()if not z.GetIsRuleArea()]]
    material=[(force._uid(item),copper.native_contact_polygon(item,face,deadline))for item in material
        if force._uid(item)!=proposal['pad_uuid']and item.GetNetname()==proposal['net']and item.IsOnLayer(face)]
    allowed=set(proposal['source_target_component_uuids']);left_root=False;root_contacts=0
    for shape in shapes:
        _left(deadline)
        if touches(shape,root_shape):
            _require(not left_root,'address_chain_reenters_actual_source_root_land')
            root_contacts+=1
        else:left_root=True
        outside=None
        for uid,other in material:
            if not touches(shape,other):continue
            _require(uid in allowed,'address_chain_acquires_unowned_source_supply_component')
            if outside is None:
                outside=shape.CloneDropTriangulation();outside.BooleanSubtract(kernel)
            _require(not touches(outside,other),'address_source_contact_outside_terminal_copper_kernel')
    _require(root_contacts>0,'actual_source_address_copper_contact_required')
    return dict(nonadjacent_new_copper_contacts=0,source_root_contacts_are_one_initial_prefix=True,
        same_net_source_contacts_only_in_declared_terminal_kernel=True,
        terminal_kernel_radius_nm=proposal['full_width_nm'],new_copper_or_current_permission=False)


def receive(source,candidate,*,board_hint,pad_uuid,timeout_s=10.):
    deadline=_deadline(timeout_s)
    r=dict(ok=False,complete=False,errors=[],scope='saved_stationary_source_address_supply_join',
        current_qualified=False,release_authority=False,whole_saved_board_receiving_still_required=True)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        _require(source!=candidate,'distinct_stationary_address_saved_boards_required')
        epoch=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        before,after=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        q=plan(before,source,board_hint=board_hint,pad_uuid=pad_uuid,timeout_s=_left(deadline))
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        _require(not(old.keys()-new.keys()),'stationary_address_cannot_retire_source_items')
        incoming=new.keys()-old.keys()
        _require(all(new[u][0]in('segment','group')for u in incoming),
            'stationary_address_only_straight_tracks_and_endpoint_group')
        rows=[t for t in after.GetTracks()if force._uid(t)in incoming]
        _require(rows and set(literal.incoming_copper_nets(candidate.read_text(),
            {force._uid(t)for t in rows}).values())=={q['net']},'literal_address_new_track_net_required')
        _require(all(t.GetClass()=='PCB_TRACK'and t.GetNetname()==q['net']
            and int(t.GetLayer())==q['layer_id']and not t.HasSolderMask()
            and q['whole_current_prefix_floor_nm']<=t.GetWidth()<=q['full_width_nm']for t in rows),
            'whole_aggregate_current_same_source_surface_address_chain_required')
        pad=next(p for f in before.GetFootprints()for p in f.Pads()if force._uid(p)==pad_uuid)
        degrees={}
        for t in rows:
            for point in(tuple(t.GetStart()),tuple(t.GetEnd())):
                degrees[point]=degrees.get(point,0)+1
        launches=[p for p,n in degrees.items()if n==1 and
            pad.GetEffectiveShape(q['layer_id']).Collide(pcbnew.VECTOR2I(*p),0)]
        _require(len(launches)==1,'one_actual_source_address_land_contact_required')
        # A retained solid SMD land is real copper, not an obligate trace
        # from its centre. Its exact saved shape supplies this contact; no
        # near-point snap, custom island, through-hole or pose is inferred.
        path=_ordered(rows,launches[0])
        tracks={force._uid(t):t for t in before.GetTracks()}
        targets=[tracks[target['uuid']]for target in q['source_targets']]
        _require(any(t.GetEffectiveShape(q['layer_id']).Collide(pcbnew.VECTOR2I(*path[-1]),0)
            for t in targets),'address_chain_must_end_on_actual_retained_full_class_supply')
        r['literal_copper_contacts']=_literal_contacts(before,rows,path,q,deadline)
        narrow=[t for t in rows if t.GetWidth()<q['full_width_nm']]
        by_edge={frozenset((tuple(t.GetStart()),tuple(t.GetEnd()))):t for t in rows}
        full_seen=False
        for a,b in zip(path,path[1:]):
            width=by_edge[frozenset((a,b))].GetWidth()
            if width==q['full_width_nm']:full_seen=True
            else:_require(not full_seen,'thin_address_material_may_only_be_a_contiguous_root_prefix')
        qualified,refused=fr._qualified_endpoint_neckdown_tracks(after,narrow,q['full_width_nm'],
            required_clearance=q['clearance_nm'])
        _require({force._uid(t)for t in qualified}=={force._uid(t)for t in narrow}and not refused,
            'every_address_prefix_requires_independent_native_locality_proof')
        # All narrow material is one actual launch component at THIS Source
        # address land; a second thin section elsewhere cannot borrow it.
        if narrow:
            ends={tuple(t.GetStart())for t in narrow}|{tuple(t.GetEnd())for t in narrow}
            _require(launches[0]in ends and sum(t.GetLength()for t in narrow)<=1500000,
                'only_address_root_local_thin_prefix_allowed')
            groups=[g for g in after.Groups()if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP]
            _require(len(groups)==1 and all(groups[0].ContainsItem(t)for t in narrow),
                'exact_saved_address_endpoint_group_required')
        cache={};net=pad.GetNetCode()
        for t in rows:
            _left(deadline)
            _require(fr._tap_foreign_clear(before,t.GetStart(),t.GetEnd(),t.GetWidth(),q['layer_id'],
                q['clearance_nm'],{net},foreign_cache=cache)
                and fr._edge_leg_clear(before,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2+q['clearance_nm']),
                'new_address_chain_native_source_clearance_required')
        exact=additive.receive(source,candidate,timeout_s=_left(deadline),
            allow_endpoint_neckdown_additions=True,board_hint=board_hint)
        r['exact_source_plus_received_prefix']=exact
        _require(exact['ok']and exact['complete'],'stationary_address_exact_saved_replay_refused')
        current=supply.audit(after,board_hint=board_hint,include_nets=[q['net']],
            netclass_resolver=fr._project_netclass_resolver(str(source),board=before))
        _require(current['contracts']=={q['net']:q['aggregate_contract']},
            'stationary_address_aggregate_contract_changed')
        parts=current['nets'][q['net']]['native_components']
        _require(len(parts)==len(q['source_components'])-1
            and all(any(set(p)<=set(t)for t in parts)for p in q['source_components']),
            'stationary_address_requires_exact_one_native_join_without_partition_loss')
        _require(epoch==force._code_identity()and families==[force._family(p,board_hint)for p in(source,candidate)],
            'stationary_address_source_candidate_or_code_changed')
        _require(_live_canonical(q['canonical_source']),'stationary_address_canonical_hierarchy_or_exporter_changed')
        _left(deadline)
        r.update(ok=True,complete=True,source_plan=q,new_track_uuids=sorted(force._uid(t)for t in rows),
            actual_saved_address_land_contact_nm=list(launches[0]),
            source_components=len(q['source_components']),candidate_components=len(parts),
            whole_unchanged_aggregate_current_preserved=True,source_pose_and_all_original_items_preserved=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError)as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r

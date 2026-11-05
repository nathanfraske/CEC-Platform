"""Translate one canonical detached ordinary resistor; no copper ownership.

Only the literal footprint-root at coordinates may change. Both original nets
must be positively ordinary, both source pins passive, and every actual source
land electrically detached. Known source courtyards and separately reviewed
missing-body reservations remain obstacles. Routing and whole-board receiving
are separate; this cannot authorize a new barrel, current or scope exemption.
"""
import hashlib,json,math,tempfile,time
from decimal import Decimal
from pathlib import Path
import pcbnew
from shapely.geometry import Polygon
import cec_force_current as force
import cec_source_ground_leaf as leaf
import cec_source_literal_additions as lex
import cec_source_retaining_ses_import as literal
import cec_ordinary_route_receiving as ordinary
import cec_qualified_courtyard_restore as courts
import cec_field_coupling as field
import cec_copper_echo as syntax
import cec_fr as fr
import cec_native_rule_areas as rule_areas


def _need(value,reason):
    if not value:raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10,
        'bounded_detached_passive_lease_required')
    return time.monotonic()+seconds


def _tick(deadline):_need(time.monotonic()<deadline,'detached_passive_deadline')
def _stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def _detached(board,fp,deadline):
    pads=list(fp.Pads());others=[p for f in board.GetFootprints()if f!=fp for p in f.Pads()]
    for pad in pads:
        shape=pad.GetEffectiveShape(next(iter(pad.GetLayerSet().CuStack())))
        for item in [*board.GetTracks(),*others]:
            _tick(deadline)
            if any(shape.Collide(item.GetEffectiveShape(layer),0)for layer in
                    set(pad.GetLayerSet().CuStack())&set(item.GetLayerSet().CuStack())):
                raise ValueError('source_passive_land_has_existing_native_contact')
        for zone in board.Zones():
            for layer in pad.GetLayerSet().CuStack():
                if zone.GetIsRuleArea()or not zone.IsOnLayer(layer):continue
                _need(zone.IsFilled()and zone.HasFilledPolysForLayer(layer),
                    'unknown_source_passive_zone_contact')
                _need(not zone.GetFilledPolysList(layer).Collide(shape,0),
                    'source_passive_land_has_existing_native_zone_contact')


def _canonical(board,source,hint,owner,deadline):
    root=leaf.source_nc._root(board,hint)
    _need(root is not None,'canonical_detached_passive_root_required');root=root.resolve()
    files,hashes,instances=leaf._hierarchy(root,deadline)
    tree,exporter=leaf._export(root,deadline);comps,nets,node_net=leaf._tables(tree)
    identity=leaf._identity(board,owner.GetReference(),comps,instances,deadline)
    component=comps[owner.GetReference()]
    _need(leaf.synth._val(leaf.synth._first(component,'libsource'),'part','')in('R','R_Small'),
        'canonical_two_pin_resistor_symbol_required')
    pins=[]
    for pad in sorted(owner.Pads(),key=lambda p:p.GetNumber()):
        _need(leaf._pin(identity,pad.GetNumber())['type']=='passive'
            and node_net.get((owner.GetReference(),pad.GetNumber()))==pad.GetNetname(),
            'canonical_original_passive_pin_net_required')
        pins.append(dict(uuid=force._uid(pad),number=pad.GetNumber(),net=pad.GetNetname()))
    exporter=dict(exporter);exporter.pop('netlist_sha256')  # Generated date only; full semantic hash remains.
    return dict(root=str(root),schematic_files_sha256=hashes,symbol_uuid=identity[3]['uuid'],
        value=owner.GetValue(),footprint_id=owner.GetFPIDAsString(),
        mpn=leaf.footprint_properties(owner)['MPN'],pins=pins,exporter=exporter)


def _source(source,hint,uid,contracts,deadline):
    board=pcbnew.LoadBoard(str(source));owners=[f for f in board.GetFootprints()if force._uid(f)==uid]
    _need(len(owners)==1,'one_exact_native_detached_passive_owner_required');fp=owners[0];pads=list(fp.Pads())
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    # Native adapters must not silently discard literal group ownership.
    inventory,*_=lex._inventory(literal.raw_text(source))
    literal_grouped={member for _,_,node in inventory.values()if literal.kind(node)=='group'
        for member in lex._members(node)[1]}
    _need(not fp.IsLocked()and not fp.IsDNP()and not fp.GetParentGroup()and len(pads)==2
        and len({p.GetNumber()for p in pads})==2 and len({p.GetNetname()for p in pads})==2
        and not({uid,*[force._uid(p)for p in pads]}&(grouped|literal_grouped))
        and not list(fp.Zones())and all(not p.IsLocked()and not p.GetParentGroup()
            and not p.HasHole()and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
            and len(list(p.GetLayerSet().CuStack()))==1 for p in pads),
        'unlocked_ungrouped_populated_two_surface_pin_passive_required')
    _need(all(int(g.GetLayer())not in {*map(int,board.GetEnabledLayers().CuStack()),int(pcbnew.Edge_Cuts)}
        for g in [*fp.GraphicalItems(),*fp.GetFields()]),'detached_passive_cannot_carry_copper_or_board_edges')
    eligible=ordinary.eligible_nets(board,source,hint)
    _need(all(p.GetNetname()in eligible for p in pads),'both_original_nets_must_be_positively_ordinary')
    proof=_canonical(board,source,hint,fp,deadline);_detached(board,fp,deadline)
    body_proofs=[];body_inputs={};reservations={}
    native_owners={force._uid(peer):peer for peer in board.GetFootprints()}
    for contract in contracts:
        _tick(deadline)
        q=courts.plan(source,contract_id=contract,board_hint=hint,literal_source=True,
            timeout_s=max(.001,deadline-time.monotonic()))
        _need(all(p not in body_inputs or body_inputs[p]==h for p,h in q['input_sha256'].items()),
            'conflicting_reviewed_passive_body_inputs')
        body_inputs.update(q['input_sha256'])
        # These are rejection-only reservations, not authored board edits.
        # Keep immutable Python geometry instead of adding temporary native
        # shapes or borrowing a footprint from a transient projected BOARD.
        # The fresh manufacturer plan already binds every exact Source
        # package, pose, land pattern, drawing, template and contour.
        for row in q['records']:
            uid=row['footprint_uuid'];target=native_owners.get(uid)
            _need(target is not None and uid not in reservations
                and row['source_pose']==[*target.GetPosition(),target.GetOrientationDegrees()]
                and row['flipped']==target.IsFlipped()
                and row['courtyard_layer']==int(pcbnew.B_CrtYd if target.IsFlipped()else pcbnew.F_CrtYd),
                'conflicting_or_changed_reviewed_passive_obstacle')
            points=tuple(tuple(p)for p in row['world_points_nm'])
            _need(len(points)>=3 and all(len(p)==2 and all(type(v)is int for v in p)for p in points),
                'exact_reviewed_passive_body_points_required')
            shape=Polygon([(x/1e6,y/1e6)for x,y in points])
            _need(shape.is_valid and not shape.is_empty and shape.area>0,
                'valid_reviewed_passive_body_required')
            reservations[uid]=(row['courtyard_layer'],shape.buffer(.025001,join_style=2))
        # The independently replayed reservation geometry is the scope, not
        # its remaining wall-clock lease. Retain every contract/input/native
        # record; omit only this transient nested scheduling parameter.
        reservation=_stable(q);reservation['request'].pop('timeout_s')
        reservation['lease_policy']='fresh_bounded_remaining_outer_passive_lease'
        body_proofs.append(reservation)
    return board,fp,proof,body_proofs,body_inputs,reservations


def _court(fp):
    fp.BuildCourtyardCaches();face=pcbnew.B_Cu if fp.IsFlipped()else pcbnew.F_Cu
    poly=fp.GetCourtyard(face)
    _need(poly.OutlineCount()==1 and not poly.HoleCount(0),'known_closed_passive_placement_body_required')
    line=poly.COutline(0);shape=Polygon([(line.CPoint(i).x/1e6,line.CPoint(i).y/1e6)for i in range(line.PointCount())])
    _need(shape.is_valid and not shape.is_empty,'valid_passive_placement_body_required')
    width=max((g.GetWidth()for g in fp.GraphicalItems()if int(g.GetLayer())in courts.COURTS),default=0)
    # Native caches are inset. Restore an outward conservative reservation;
    # this is a search rejection, not an inward geometric clearance waiver.
    return shape.buffer(width/2e6+.000001,join_style=2)


def _peer_body(peer,reservations):
    reserved=reservations.get(force._uid(peer))
    existing=any(int(g.GetLayer())in courts.COURTS for g in peer.GraphicalItems())
    actual=_court(peer)if existing else None
    _need(actual is not None or reserved is not None,'known_closed_passive_placement_body_required')
    if reserved is not None:
        _need(reserved[0]==int(pcbnew.B_CrtYd if peer.IsFlipped()else pcbnew.F_CrtYd),
            'reviewed_passive_body_surface_changed')
        return reserved[1]if actual is None else actual.union(reserved[1])
    return actual


def _legal(board,fp,deadline,reservations):
    body=_court(fp)
    from cec_assembly_envelope import polygon_from_native
    outline=pcbnew.SHAPE_POLY_SET()
    _need(board.GetBoardPolygonOutlines(outline,False)
        and polygon_from_native(outline).covers(body),'candidate_passive_body_outside_laminate')
    face=pcbnew.B_Cu if fp.IsFlipped()else pcbnew.F_Cu
    for row in rule_areas.areas(board,'footprints'):
        _tick(deadline)
        if face in row['layers']:
            _need(body.intersection(polygon_from_native(row['shape'])).area==0,
                'candidate_passive_native_footprint_rule_area')
    for peer in board.GetFootprints():
        _tick(deadline)
        if peer==fp:continue
        if(not list(peer.Pads())and not list(peer.Models())and peer.GetAttributes()&pcbnew.FP_BOARD_ONLY
                and peer.GetAttributes()&pcbnew.FP_EXCLUDE_FROM_BOM
                and peer.GetAttributes()&pcbnew.FP_EXCLUDE_FROM_POS_FILES):continue
        if peer.IsFlipped()!=fp.IsFlipped()and not any(p.HasHole()for p in peer.Pads()):continue
        _need(body.intersection(_peer_body(peer,reservations)).area==0,
            'candidate_passive_body_overlap:'+peer.GetReference()+':'+force._uid(peer))
    resolver=fr._foreign_clearance_resolver(board)
    for pad in fp.Pads():
        _tick(deadline);layer=int(next(iter(pad.GetLayerSet().CuStack())))
        gap=max(int(board.GetDesignSettings().m_MinClearance),int(resolver(pad,layer)))
        poly=pad.GetEffectiveShape(layer);at=pad.GetPosition()
        radius=math.ceil(math.hypot(pad.GetSize().x,pad.GetSize().y)/2)
        _need(fr._edge_leg_clear(board,at,at,radius+gap),'candidate_passive_land_edge_conflict')
        # A rectangular land is not its circumscribed circle. Use its exact
        # native shape for permission/reservation/artwork checks too; the
        # old circular surrogate rejected legal clearances alongside traces.
        for row in rule_areas.areas(board,'pads'):
            _tick(deadline)
            if layer in row['layers']:
                _need(not row['shape'].Collide(poly,0),'candidate_passive_native_pad_rule_area')
        for zone in board.Zones():
            _tick(deadline)
            if(not zone.GetIsRuleArea()and zone.GetNetCode()!=pad.GetNetCode()
                    and fr._zone_is_route_reservation(board,zone,layer)):
                _need(not fr._reserved_zone_obstacle(board,zone,layer).Collide(poly,
                    max(gap,int(zone.GetLocalClearance()),int(resolver(zone,layer)))),
                    'candidate_passive_foreign_reserved_zone')
        artwork=[*board.GetDrawings(),*[g for owner in board.GetFootprints()
            for g in [*owner.GraphicalItems(),*owner.GetFields()]]]
        for item in artwork:
            _tick(deadline)
            if int(item.GetLayer())==layer:
                _need(not item.GetEffectiveShape().Collide(poly,gap),
                    'candidate_passive_native_copper_artwork')
        for peer in [*board.GetTracks(),*(p for other in board.GetFootprints()for p in other.Pads()if other!=fp),
                *[p for p in fp.Pads()if p!=pad]]:
            _tick(deadline)
            if peer.GetNetCode()==pad.GetNetCode():continue
            if peer.GetClass()=='PAD'and peer.GetAttribute()==pcbnew.PAD_ATTRIB_NPTH:
                if peer.HasHole():_need(not peer.GetEffectiveHoleShape().Collide(poly,max(gap,int(board.GetDesignSettings().m_HoleClearance))),
                    'candidate_passive_native_hole_clearance')
            if layer in peer.GetLayerSet().CuStack():
                _need(not peer.GetEffectiveShape(layer).Collide(poly,max(gap,int(resolver(peer,layer)))),
                    'candidate_passive_native_foreign_copper')
        # All actual foreign fills, including existing GND, stay untouched.
        for zone in board.Zones():
            if zone.GetIsRuleArea()or not zone.IsOnLayer(layer)or zone.GetNetCode()==pad.GetNetCode():continue
            _need(zone.IsFilled()and zone.HasFilledPolysForLayer(layer),'candidate_passive_unknown_fill')
            _need(not zone.GetFilledPolysList(layer).Collide(poly,max(gap,int(zone.GetLocalClearance()),int(resolver(zone,layer)))),
                'candidate_passive_foreign_saved_fill')
    return dict(known_body_and_native_land_clear=True,ground_fill_or_power_void_authority=False)


def _text(source,uid,at):
    text=literal.raw_text(source);a,z=literal.inventory(text)[uid];part=text[a:z]
    found=[(i,j)for i,j in literal.children(part)if literal.kind(part[i:j])=='at']
    _need(len(found)==1,'one_literal_passive_root_at_required');i,j=found[0]
    atoms=lex._atoms(part[i+1:j-1]);_need(len(atoms)in(3,4),'simple_literal_passive_root_at_required')
    coords=[format(Decimal(v)/1000000,'f')for v in at]
    replacement='(at '+' '.join([*coords,*[v[1]for v in atoms[3:]]])+')'
    return text[:a]+part[:i]+replacement+part[j:]+text[z:]


def plan(source,*,board_hint,footprint_uuid,at_nm,max_shift_mm=3.,reviewed_courtyard_contract_ids=(),timeout_s=10.):
    deadline=_deadline(timeout_s);source=Path(source).resolve(strict=True)
    _need(type(board_hint)is str and board_hint and type(footprint_uuid)is str and footprint_uuid
        and type(at_nm)in(list,tuple)and len(at_nm)==2 and all(type(x)is int for x in at_nm)
        and type(max_shift_mm)in(int,float)and math.isfinite(max_shift_mm)and 0<max_shift_mm<=5
        and type(reviewed_courtyard_contract_ids)in(list,tuple)and len(reviewed_courtyard_contract_ids)<=8
        and len(set(reviewed_courtyard_contract_ids))==len(reviewed_courtyard_contract_ids),
        'explicit_bounded_detached_passive_translation_required')
    code=force._code_identity();family=force._family(source,board_hint)
    board,fp,proof,bodies,inputs,reservations=_source(source,board_hint,footprint_uuid,reviewed_courtyard_contract_ids,deadline)
    old=list(fp.GetPosition());_need(0<math.dist(old,at_nm)<=max_shift_mm*1e6,'bounded_nonzero_passive_translation_required')
    fp.SetPosition(pcbnew.VECTOR2I(*at_nm));geometry=_legal(board,fp,deadline,reservations)
    expected=_text(source,footprint_uuid,at_nm)
    _need(code==force._code_identity()and family==force._family(source,board_hint)
        and all(force._hash(Path(p))==h for p,h in {**proof['schematic_files_sha256'],**inputs}.items()),
        'detached_passive_source_or_code_changed');_tick(deadline)
    return _stable(dict(schema=1,scope='canonical_detached_two_pin_ordinary_resistor_translation-v1',
        source=str(source),board_hint=board_hint,source_sha256=force._hash(source),source_family=family,
        code_identity=code,canonical_source=proof,body_reservations=bodies,body_input_sha256=inputs,
        footprint_uuid=footprint_uuid,old_at_nm=old,at_nm=list(at_nm),geometry=geometry,
        expected_text_sha256=hashlib.sha256(expected.encode()).hexdigest(),
        request=dict(footprint_uuid=footprint_uuid,at_nm=list(at_nm),max_shift_mm=max_shift_mm,
            reviewed_courtyard_contract_ids=list(reviewed_courtyard_contract_ids)),
        routing_admitted=False,current_qualified=False,release_authority=False))


def discover(source,*,board_hint,footprint_uuid,at_nm_candidates,max_shift_mm=5.,
        reviewed_courtyard_contract_ids=(),egress_reach_mm=1.5,timeout_s=10.):
    """Bounded joint-pin placement hints, never a saved placement permission.

    Reuse one exact immutable Source proof for rejection-only trial geometry.
    The two independent ordinary pin exits are scored together; a good exit
    on just one side cannot hide a trapped other pin. Every chosen position
    still needs a NEW plan/write/receive and complete saved routing/assembly.
    """
    deadline=_deadline(timeout_s);source=Path(source).resolve(strict=True)
    _need(type(board_hint)is str and board_hint and type(footprint_uuid)is str and footprint_uuid
        and type(at_nm_candidates)in(list,tuple)and 1<=len(at_nm_candidates)<=64
        and all(type(at)in(list,tuple)and len(at)==2 and all(type(x)is int for x in at)
            for at in at_nm_candidates)and len({tuple(at)for at in at_nm_candidates})==len(at_nm_candidates)
        and type(max_shift_mm)in(int,float)and math.isfinite(max_shift_mm)and 0<max_shift_mm<=5
        and type(egress_reach_mm)in(int,float)and math.isfinite(egress_reach_mm)and .5<=egress_reach_mm<=2
        and type(reviewed_courtyard_contract_ids)in(list,tuple)and len(reviewed_courtyard_contract_ids)<=8
        and len(set(reviewed_courtyard_contract_ids))==len(reviewed_courtyard_contract_ids),
        'bounded_explicit_joint_pin_pose_domain_required')
    import cec_source_rule_signal_launches as local
    code=force._code_identity();family=force._family(source,board_hint)
    board,fp,proof,bodies,inputs,reservations=_source(source,board_hint,footprint_uuid,
        reviewed_courtyard_contract_ids,deadline)
    original=list(fp.GetPosition());resolver=fr._project_netclass_resolver(str(source),board=board)
    rows=[]
    try:
        for position in at_nm_candidates:
            if time.monotonic()>=deadline:break
            row=dict(at_nm=list(position),complete=False,legal=False,joint_pin_access=None)
            rows.append(row)
            try:
                _need(0<math.dist(original,position)<=max_shift_mm*1e6,
                    'bounded_nonzero_passive_translation_required')
                fp.SetPosition(pcbnew.VECTOR2I(*position));_legal(board,fp,deadline,reservations)
                exits=[];cache={}
                for pad in sorted(fp.Pads(),key=lambda p:p.GetNumber()):
                    _tick(deadline);spec=resolver(pad.GetNetname())or{}
                    width=max(int(board.GetDesignSettings().m_TrackMinWidth),round(float(spec.get('track_width')or .2)*1e6))
                    gap=max(int(board.GetDesignSettings().m_MinClearance),round(float(spec.get('clearance')or .2)*1e6))
                    layer=int(next(iter(pad.GetLayerSet().CuStack())));at=pad.GetPosition();rays=[]
                    for dx,dy in((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1)):
                        _tick(deadline);step=round(egress_reach_mm*1e6/(math.sqrt(2)if dx and dy else 1))
                        end=at+pcbnew.VECTOR2I(dx*step,dy*step)
                        if(fr._edge_leg_clear(board,at,end,(width+1)//2+gap)
                            and fr._tap_foreign_clear(board,at,end,width,layer,gap,{pad.GetNetCode()},foreign_cache=cache)
                            and local._immutable_power_clear(board,at,end,width,layer,gap,pad.GetNetCode())):
                            rays.append(dict(start_nm=list(at),end_nm=list(end),layer=layer,width_nm=width,clearance_nm=gap))
                    exits.append(dict(pad_uuid=force._uid(pad),number=pad.GetNumber(),net=pad.GetNetname(),
                        native_surface_departures=rays,clear_rays=len(rays)))
                row.update(complete=True,legal=True,joint_pin_access=exits,
                    minimum_pin_exits=min(p['clear_rays']for p in exits),
                    total_pin_exits=sum(p['clear_rays']for p in exits),shift_nm=math.dist(original,position))
            except ValueError as exc:
                row['reason']=str(exc)
                if time.monotonic()>=deadline:break
                row['complete']=True
    finally:fp.SetPosition(pcbnew.VECTOR2I(*original))
    _need(code==force._code_identity()and family==force._family(source,board_hint)
        and all(force._hash(Path(p))==h for p,h in {**proof['schematic_files_sha256'],**inputs}.items()),
        'joint_pin_pose_source_or_code_changed')
    legal=sorted((r for r in rows if r['legal']),key=lambda r:(-r['minimum_pin_exits'],
        -r['total_pin_exits'],r['shift_nm'],r['at_nm']))
    return _stable(dict(scope='bounded_canonical_detached_joint_pin_pose_discovery',source=str(source),
        source_sha256=force._hash(source),source_family=family,code_identity=code,canonical_source=proof,
        footprint_uuid=footprint_uuid,original_at_nm=original,body_reservations=bodies,body_input_sha256=inputs,
        complete=len(rows)==len(at_nm_candidates)and all(r['complete']for r in rows)and time.monotonic()<deadline,
        trials=rows,ranked_legal_positions_nm=[r['at_nm']for r in legal],
        source_unchanged=True,global_route_or_via_access_proved=False,no_path_proof=False,
        placement_admitted=False,routing_admitted=False,current_qualified=False,release_authority=False,
        every_selected_pose_requires_fresh_plan_write_and_saved_receiving=True))


def receive(source,candidate,proposal,*,timeout_s=10.):
    deadline=_deadline(timeout_s);r=dict(ok=False,complete=False,errors=[],release_authority=False,
        whole_parent_current_field_ground_contact_native_intake_parity_and_stack_still_required=True)
    try:
        source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate))
        _need(source!=candidate,'distinct_saved_passive_files_required')
        families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        fresh=plan(source,board_hint=proposal['board_hint'],timeout_s=max(.001,deadline-time.monotonic()),**proposal['request'])
        _need(fresh==proposal,'stale_or_forged_detached_passive_plan')
        _need(literal.raw_text(candidate)==_text(source,proposal['footprint_uuid'],proposal['at_nm']),
            'passive_translation_changed_other_literal_material')
        _need(force._sidecars(source)==force._sidecars(candidate),'passive_translation_changed_rules_or_sidecars')
        boards=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        fp=next(f for f in boards[1].GetFootprints()if force._uid(f)==proposal['footprint_uuid'])
        _need(list(fp.GetPosition())==proposal['at_nm'],'saved_passive_at_not_exact')
        fp.SetPosition(pcbnew.VECTOR2I(*proposal['old_at_nm']))
        with tempfile.TemporaryDirectory(prefix='cec-detached-passive-native-')as work:
            trees=[]
            for i,b in enumerate(boards):
                path=Path(work)/(str(i)+'.kicad_pcb');field._save_field_snapshot(b,path)
                trees.append(syntax._freeze(syntax._parse(syntax._TOKEN.findall(path.read_text()))))
            _need(trees[0]==trees[1],'restored_passive_whole_native_source_changed')
        _need(families==[force._family(p,proposal['board_hint'])for p in(source,candidate)]
            and proposal['code_identity']==force._code_identity(),'passive_receiving_epoch_changed');_tick(deadline)
        r.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            exact_literal_root_at_only=True,all_copper_pads_fields_rules_and_parts_unchanged=True)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r


def write_private(source,candidate,proposal,*,timeout_s=10.):
    deadline=_deadline(timeout_s);source,candidate=map(Path,(source,candidate))
    _need(not candidate.parent.exists()and source.parent.resolve()!=candidate.parent.resolve(),
        'fresh_private_detached_passive_family_required')
    fresh=plan(source,board_hint=proposal['board_hint'],timeout_s=max(.001,deadline-time.monotonic()),**proposal['request'])
    _need(fresh==proposal,'stale_detached_passive_construction_plan')
    child=force._copy_family(source,candidate.parent);_need(child==candidate,'same_passive_board_basename_required')
    literal.write_raw(child,_text(source,proposal['footprint_uuid'],proposal['at_nm']))
    proof=receive(source,child,proposal,timeout_s=max(.001,deadline-time.monotonic()))
    _need(proof['ok']and proof['complete'],'saved_detached_passive_receiving_refused:'+str(proof['errors']))
    _tick(deadline);return child

"""Canonical control pull-up placement scopes; never a bypass/current budget.

Requires the existing complete control-shunt Source proof, then independently
binds the same manufacturer's VDD power-input and the unique passive resistor.
No old copper cut, routing success, timing or load-current authority is granted.
"""
import math,re,time
import pcbnew
import cec_force_current as force
import cec_source_ground_leaf as leaf
import cec_control_shunt_placement as shunt
import cec_cell_row_rebuild as row
import cec_synth_pipeline as synth


def _need(v,message):
    if not v:raise ValueError(message)


def _ohms(value):
    match=re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmMrR]?)\s*(?:[Ωω]|[Oo][Hh][Mm])?\s*',value)
    if not match:return None
    multiplier={'':1.,'r':1.,'R':1.,'k':1e3,'K':1e3,'m':1e-3,'M':1e6}[match[2]]
    answer=float(match[1])*multiplier
    return answer if math.isfinite(answer)and answer>0 else None


def _plan(board,poses,*,board_hint,timeout_s,source_role,reference_group_uuids=()):
    _need(source_role in('enable_reset_input','boot_mode_strap_input'),
        'explicit_manufacturer_control_pullup_role_required')
    _need(type(poses)is dict and 1<=len(poses)<=8 and type(board_hint)is str and bool(board_hint)
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_control_pullup_context_required')
    deadline=time.monotonic()+timeout_s;binding=row._source_binding(board);epoch=force._code_identity()
    shunt._reference_group_scope(reference_group_uuids)
    def tick():_need(time.monotonic()<deadline,'control_pullup_source_deadline')
    candidates=leaf._candidates(board)
    controls=[v for v in candidates.values()if v[1]=='source_control_shunt_ground'
        and v[2].get('role')==source_role and v[3]is not None]
    selected=[]
    for cap_ground,kind,witness,control in controls:
        owner=control.GetParentFootprint();vdd=owner.FindPadByNumber('3')
        if vdd is None or vdd.GetNetCode()<=0 or vdd.GetNetname()in('GND',control.GetNetname()):continue
        for fp in board.GetFootprints():
            pads=list(fp.Pads())
            if(fp.GetReference()in poses and len(pads)==2 and len({p.GetNumber()for p in pads})==2
                and {p.GetNetname()for p in pads}=={control.GetNetname(),vdd.GetNetname()}):
                selected.append((fp,cap_ground,control,vdd,witness))
    if not selected:return {}
    _need(len({force._uid(f)for f,*_ in selected})==len(selected),'unique_control_pullup_owner_required')
    authorized=shunt._reference_group_authorizations(board,poses,reference_group_uuids,
        binding=binding,deadline=deadline)
    tick();proof,fresh_export=leaf.plan_with_export(board,board_hint=board_hint,
        timeout_s=max(.001,deadline-time.monotonic()))
    _need(proof.get('complete')is True and not proof.get('errors'),'complete_control_pullup_canonical_source_required')
    tick();root=leaf.source_nc._root(board,board_hint)
    _need(root is not None,'canonical_control_pullup_root_required');root=root.resolve()
    files,hashes,instances=leaf._hierarchy(root,deadline)
    _need(type(fresh_export)is tuple and len(fresh_export)==3 and fresh_export[0]==str(root),
        'same_fresh_control_pullup_canonical_export_required')
    _,tree,exporter=fresh_export
    _need(all(exporter.get(key)==value for key,value in shunt.semantic.metadata(tree).items()),
        'control_pullup_fresh_export_semantic_identity_changed')
    comps,nets,node_net=leaf._tables(tree);groups={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    import cec_additive_route_receiving as additive
    groups.update(u for n in additive._nodes(board.GetFileName())[1].values()if n[0]=='group'for u in additive._members(n))
    result={}
    for resistor,ground,control,vdd,witness in selected:
        tick();ref=resistor.GetReference();owner=control.GetParentFootprint();cap=ground.GetParentFootprint()
        source=proof.get('proofs',{}).get(force._uid(ground))
        _need(source is not None and source.get('kind')=='source_control_shunt_ground'
            and source.get('manufacturer')==witness and source.get('owner')==cap.GetReference()
            and source.get('pin')==ground.GetNumber(),'actual_complete_enable_shunt_source_witness_required')
        _need(source['root_schematic']==str(root)and source['schematic_files_sha256']==hashes,
            'control_pullup_canonical_hierarchy_changed')
        fresh_source=dict(source,exporter=exporter)
        canonical=shunt._canonical_source_proof(source)
        _need(canonical==shunt._canonical_source_proof(fresh_source),'control_pullup_semantic_export_changed')
        ri=leaf._identity(board,ref,comps,instances,deadline)
        mi=leaf._identity(board,owner.GetReference(),comps,instances,deadline)
        _need(synth._val(synth._first(comps[ref],'libsource'),'part','')in('R','R_Small'), 'canonical_resistor_symbol_required')
        pads=list(resistor.Pads());signal=next(p for p in pads if p.GetNetname()==control.GetNetname())
        supply=next(p for p in pads if p.GetNetname()==vdd.GetNetname())
        _need(leaf._pin(ri,signal.GetNumber())['type']=='passive'
            and leaf._pin(ri,supply.GetNumber())['type']=='passive'
            and leaf._pin(mi,vdd.GetNumber())['type']=='power_in', 'actual_resistor_passive_and_manufacturer_vdd_power_input_required')
        _need(all(node_net.get((p.GetParentFootprint().GetReference(),p.GetNumber()))==p.GetNetname()
            for p in(signal,supply,control,vdd)),'canonical_pullup_both_nets_and_source_vdd_required')
        peers=[p for p in source['control_peers']if p['ref']==ref]
        _need(len(peers)==1 and peers[0]['pin']==signal.GetNumber()and peers[0]['symbol_uuid']==ri[3]['uuid'], 'pullup_must_be_exact_proven_enable_peer')
        # Prove uniqueness from the whole canonical EN net, not only posed refs.
        pulls=[]
        for other,pin in nets.get(control.GetNetname(),set()):
            part=synth._val(synth._first(comps.get(other,[]),'libsource'),'part','')
            if part in('R','R_Small'):pulls.append((other,pin))
        _need(pulls==[(ref,signal.GetNumber())],'unique_canonical_enable_pullup_required')
        _need(not resistor.IsDNP()and not resistor.IsLocked()
            and ((not resistor.GetParentGroup()and force._uid(resistor)not in groups)
                or force._uid(resistor)in authorized)
            and all(not p.IsLocked()and force._uid(p)not in groups
            and not p.HasHole()and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD for p in pads), 'unlocked_ungrouped_populated_two_smd_pullup_required')
        resistance=_ohms(resistor.GetValue());_need(resistance is not None,'explicit_positive_source_pullup_resistance_required')
        target=poses[ref];_need(type(target)in(list,tuple)and len(target)==3
            and all(type(v)in(int,float)and math.isfinite(v)for v in target)
            and (target[2]-resistor.GetOrientationDegrees())%90==0,'finite_cardinal_pullup_pose_required')
        owner_motion=shunt._complete_owner_motion(board,owner,poses,board_hint=board_hint,deadline=deadline)
        result[ref]=dict(role=('source_enable_reset_pullup_passive'if source_role=='enable_reset_input'
            else 'source_boot_mode_strap_pullup_passive'),resistor_uuid=force._uid(resistor),
            signal_pad_uuid=force._uid(signal),supply_pad_uuid=force._uid(supply),control_pad_uuid=force._uid(control),
            supply_target_pad_uuid=force._uid(vdd),control_owner_uuid=force._uid(owner),control_owner=owner.GetReference(),
            control_pin=control.GetNumber(),signal_net=str(signal.GetNetname()),supply_net=str(supply.GetNetname()),
            nominal_resistance_ohms=resistance,source_value=resistor.GetValue(),source_symbol_uuid=ri[3]['uuid'],
            source_proof=canonical,source_native_binding=binding,source_code_identity=epoch,
            bypass_owner=False,current_authority=False,source_trace_retirement_authority=False,
            reset_timing_qualified=False,release_authority=False)
        if source_role=='boot_mode_strap_input':
            result[ref].update(boot_timing_qualified=False,postboot_gpio_mode_assumed=False)
        if force._uid(resistor)in authorized:
            result[ref]['source_reference_group_authorization']=authorized[force._uid(resistor)]
        if owner_motion is not None:result[ref]['source_complete_owner_motion']=owner_motion
    tick();_need(binding==row._source_binding(board)and epoch==force._code_identity()
        and hashes=={str(p):force._hash(p)for p in files}
        and leaf.bindings_current([v['source_proof']for v in result.values()]),'control_pullup_source_binding_changed')
    return result


def plan(board,poses,*,board_hint,timeout_s=10.,reference_group_uuids=()):
    """Legacy EN/reset scope stays EN/reset only, never a BOOT alias."""
    return _plan(board,poses,board_hint=board_hint,timeout_s=timeout_s,source_role='enable_reset_input',
        reference_group_uuids=reference_group_uuids)


def boot_plan(board,poses,*,board_hint,timeout_s=10.,reference_group_uuids=()):
    """Exact manufacturer BOOT role AND full canonical cap/button/pull-up.

    Net spelling, an input pin, resistance or a worker assertion grants none
    of this scope. Missing/ambiguous complete Source topology refuses. The
    rail still owes its existing full aggregate current and all saved gates.
    """
    return _plan(board,poses,board_hint=board_hint,timeout_s=timeout_s,source_role='boot_mode_strap_input',
        reference_group_uuids=reference_group_uuids)


def complete_plan(board,poses,*,board_hint,timeout_s=10.,reference_group_uuids=()):
    """Two distinct positive compilers share ONE original Source lease."""
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_complete_control_pullup_context_required')
    deadline=time.monotonic()+timeout_s;result={}
    for compile_source in(plan,boot_plan):
        remaining=deadline-time.monotonic()
        _need(remaining>0,'complete_control_pullup_source_deadline')
        selected=compile_source(board,poses,board_hint=board_hint,timeout_s=min(10.,remaining),
            reference_group_uuids=reference_group_uuids)
        _need(not result.keys()&selected.keys(),'distinct_canonical_control_pullup_roles_required')
        result.update(selected)
    _need(time.monotonic()<deadline,'complete_control_pullup_source_deadline')
    return result


def requests(source,board,proposal,*,timeout_s=10.):
    started=time.monotonic()
    selected=proposal.get('selected_control_pullups',{})
    if not selected:return {}
    fresh=complete_plan(source,proposal['poses'],board_hint=proposal['board_hint'],timeout_s=timeout_s,
        reference_group_uuids=proposal.get('reference_group_uuids',()))
    _need(fresh==selected,'fresh_source_control_pullup_proposal_required')
    import cec_decoupler_cell as cell
    # Positive placement intent is NOT a new nonload ampacity exception.
    # Leave the rail connection at its existing complete aggregate contract.
    # route_width_contracts enumerates complete FORCE domains, not every
    # explicit logic supply. Use the same bound resolver as saved-cell
    # receiving; a missing/incomplete/conflicting authority still refuses.
    rail_contracts={}
    with force._thermal_hint(proposal['board_hint']):
        for net in {item['supply_net']for item in selected.values()}:
            rail_contracts[net]=cell._supply_current_widths(source,net)
    pads={force._uid(p):p for f in board.GetFootprints()for p in f.Pads()}
    old={force._uid(p):p for f in source.GetFootprints()for p in f.Pads()};requests={}
    def endpoint(p):return dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),layers=list(map(int,p.GetLayerSet().CuStack())))
    for ref,item in selected.items():
        ids=[item[k]for k in('signal_pad_uuid','supply_pad_uuid','control_pad_uuid','supply_target_pad_uuid')]
        _need(all(u in pads and u in old for u in ids),'complete_actual_projected_pullup_lands_required')
        signal,supply,control,vdd=[pads[u]for u in ids]
        resistor=signal.GetParentFootprint();original_resistor=old[item['signal_pad_uuid']].GetParentFootprint()
        mapping=item.get('source_reference_group_authorization')
        if mapping is not None:
            groups=[g for g in board.Groups()if force._uid(g)==mapping['group_uuid']]
            _need(len(groups)==1 and bool(groups[0].IsLocked())==mapping['group_locked']
                and sorted(force._uid(i)for i in groups[0].GetItems())==sorted(mapping['member_uuids'])
                and groups[0].ContainsItem(resistor)and not groups[0].GetParentGroup(),
                'projected_pullup_exact_reference_group_members_and_lock_required')
        _need(resistor.GetFPIDAsString()==original_resistor.GetFPIDAsString()
            and leaf.footprint_properties(resistor)==leaf.footprint_properties(original_resistor)
            and resistor.GetValue()==original_resistor.GetValue()and resistor.GetAttributes()==original_resistor.GetAttributes()
            and resistor.IsDNP()==original_resistor.IsDNP()and resistor.IsLocked()==original_resistor.IsLocked()
            and (not resistor.GetParentGroup()or mapping is not None)
            and len(list(resistor.Pads()))==2,'projected_pullup_part_population_or_ownership_changed')
        for uid in ids:
            a,b=old[uid],pads[uid]
            _need(a.GetNumber()==b.GetNumber()and a.GetNetname()==b.GetNetname()
                and force._uid(a.GetParentFootprint())==force._uid(b.GetParentFootprint())
                and list(a.GetLayerSet().CuStack())==list(b.GetLayerSet().CuStack()),'pullup_projected_pin_net_or_face_changed')
            _need(tuple(a.GetSize())==tuple(b.GetSize())and a.GetShape()==b.GetShape()
                and a.GetAttribute()==b.GetAttribute()and tuple(a.GetDrillSize())==tuple(b.GetDrillSize())
                and a.IsLocked()==b.IsLocked(),'pullup_projected_land_geometry_or_lock_changed')
        if 'source_complete_owner_motion'in item:
            shunt._receive_complete_owner_motion(source,board,item['source_complete_owner_motion'],proposal['poses'],
                board_hint=proposal['board_hint'],deadline=started+timeout_s)
        else:
            for p in(control,vdd):
                a=old[force._uid(p)].GetParentFootprint();b=p.GetParentFootprint()
                _need(tuple(a.GetPosition())==tuple(b.GetPosition())and a.GetOrientationDegrees()==b.GetOrientationDegrees()
                    and a.IsFlipped()==b.IsFlipped()and a.GetFPIDAsString()==b.GetFPIDAsString()
                    and leaf.footprint_properties(a)==leaf.footprint_properties(b)
                    and a.IsDNP()==b.IsDNP(),'pullup_stationary_manufacturer_owner_changed')
        for role,a,b,net in(('control_signal',signal,control,item['signal_net']),('nonload_pullup_supply',supply,vdd,item['supply_net'])):
            width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cell._netclass(board,net)['width']))
            rail=None
            if role=='nonload_pullup_supply':
                rail=rail_contracts.get(net)
                widths=rail.get('required_by_layer_nm')if type(rail)is dict else None
                _need(type(widths)is dict and widths
                    and set(widths)==set(map(int,source.GetEnabledLayers().CuStack()))
                    and all(type(v)is int and v>0 for v in widths.values())
                    and type(rail.get('current_authority'))is dict,
                    'unchanged_complete_aggregate_supply_current_contract_required')
                width=max(width,*widths.values())
            _need(width>0,'full_source_class_pullup_width_required')
            requests['control_pullup:'+force._uid(a)]=dict(kind='source_boundary',role=role,net=net,a=endpoint(a),b=endpoint(b),
                width_nm=width,source_control_pullup=item,no_power_bypass_or_current_authority=True,
                no_source_trace_retirement_authority=True,nominal_resistance_ohms=item['nominal_resistance_ohms'])
            if rail is not None:
                requests['control_pullup:'+force._uid(a)].update(unchanged_full_rail_current_contract=rail,
                    new_barrel_authority=False,class_only_supply_prefix_authority=False)
    _need(time.monotonic()-started<timeout_s,'control_pullup_requests_deadline')
    return requests

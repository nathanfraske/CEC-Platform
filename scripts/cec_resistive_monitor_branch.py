"""Bounded resistor-fed monitor leaves, not guessed full-rail load splitting.

Every tap needs an exact selected resistor/value/tolerance, a manufacturer
monitor function, its actual associated supply net, and an otherwise closed
bounded divider/filter/input node. A conservative endpoint-voltage bound
rates its own thin copper. Removing all such leaves must leave every actual
current terminal partition unchanged; source trunk failures remain failures.
"""
import math,re,time
import pcbnew
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_route_dimensions as dimensions

RESISTOR_SOURCE='https://www.uni-royal.cn/en/images/userfile/file/1753752986c56505e6d9ab55c7.pdf'
YAGEO_RT_SOURCE='https://yageogroup.com/content/datasheet/asset/file/PYU-RT_1-TO-0-01_ROHS_L'


def _yageo_rt0402_contract(fp,props):
    """Selected RT0402 B/D only; not a power, voltage or life qualification.

    Yageo RT V17 (2026-02-12), pp. 2/5/6/7: B is 0.1%, D is
    25 ppm/C, and the supported 0402 range is 4.7 ohm through 240 kohm.
    Keep this manufacturer's limits separate from the existing UNI model.
    """
    mpn=str(props.get('MPN') or '').upper()
    match=re.fullmatch(r'RT0402BRD07([1-9][0-9]{0,2})([RKM])([0-9]{0,2})L',mpn)
    if (not match or len(''.join(match.groups()))>4
            or str(props.get('Manufacturer') or '').strip().upper()!='YAGEO'
            or not re.search(r'(?:^|:)R_0402_1005Metric$',fp.GetFPIDAsString())):
        return None
    # The letter is the decimal point, not a four-digit exponent code.
    ohms=float(match[1]+'.'+(match[3] or '0'))*{'R':1.,'K':1e3,'M':1e6}[match[2]]
    if not 4.7<=ohms<=240000.:return None
    value=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*([kKM]?)\s*(?:Ω|[oO][hH][mM][sS]?)?',
        str(fp.GetValue()).strip())
    if not value:return None
    nominal=float(value[1])*{'':1.,'k':1e3,'K':1e3,'M':1e6}[value[2]]
    if not math.isfinite(nominal) or abs(nominal-ohms)>max(1e-9,ohms*1e-9):return None
    tolerance=str(props.get('Tolerance') or '').replace(' ','')
    if tolerance and tolerance not in ('0.1%','±0.1%','+/-0.1%'):return None
    pads=list(fp.Pads())
    if (len(pads)!=2 or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)
            or len({str(p.GetNumber()) for p in pads})!=2):return None
    # Table 4 uses 25 C as reference. Bound the full table-2 operating
    # interval, not just its -55/+125 C TCR test endpoints. No aging or
    # environmental drift is silently included in this initial/TCR model.
    temperature_delta=max(abs(-55.-25.),abs(155.-25.))
    minimum=ohms*(1-.001)*(1-25.*temperature_delta*1e-6)
    return dict(mpn=props['MPN'],nominal_ohms=ohms,tolerance_fraction=.001,
        tcr_bound_ppm_per_c=25.,temperature_bounds_c=[-55.,155.],reference_temperature_c=25.,
        minimum_ohms=minimum,source=YAGEO_RT_SOURCE,
        manufacturer='Yageo',manufacturer_revision='17',manufacturer_date='2026-02-12',
        manufacturer_pages=[2,5,6,7],
        manufacturer_pdf_sha256='00a9148c2958122200e8a93292e389392a795adcfe40562d6ca4f690d1e5d7d1',
        supported_resistance_range_ohms=[4.7,240000.],
        rated_power_w=1/16,power_rating_ambient_c=70.,maximum_working_voltage_v=50.,
        power_derating=dict(full_power_through_c=70.,zero_power_at_c=155.,
            interpolation='linear_above_70c',operating_temperature_bounds_c=[-55.,155.]),
        continuous_voltage_rule='min(maximum_working_voltage_v,sqrt(derated_power_w*resistance_ohms))',
        continuous_voltage_ceiling_at_70c_using_minimum_r_v=min(50.,math.sqrt(minimum/16)),
        continuous_voltage_ceiling_at_155c_v=0.,
        aging_and_fault_conditions_qualified=False,resistance_or_power_qualification=False,
        power_qualified=False,voltage_qualified=False,thermal_qualified=False,release_authority=False)


def resistor_contract(fp):
    from cec_footprint_fields import footprint_properties
    if fp.IsDNP():return None
    props=footprint_properties(fp)
    match=re.fullmatch(r'0402WGF([0-9]{4})TCE',str(props.get('MPN') or '').upper())
    if not match:return _yageo_rt0402_contract(fp,props)
    if not match or not re.search(r'(?:^|:)R_0402_1005Metric$',fp.GetFPIDAsString()):return None
    value=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*([kKM]?)\s*(?:Ω|[oO][hH][mM][sS]?)?',
        str(fp.GetValue()).strip())
    if not value:return None
    ohms=int(match[1][:3])*10**int(match[1][3])
    nominal=float(value[1])*{'':1.,'k':1e3,'K':1e3,'M':1e6}[value[2]]
    if not 1<=ohms<=1e7 or not math.isfinite(nominal) or abs(nominal-ohms)>max(1e-9,ohms*1e-9):return None
    pads=list(fp.Pads())
    if (len(pads)!=2 or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in pads)
            or len({str(p.GetNumber()) for p in pads})!=2):return None
    tcr=200. if ohms<=10 else 100.
    # Table 7 gives -55..155 C; table 10 gives the selected 0402 TCR.
    # Bound the full rated interval from the table's 25 C reference, rather
    # than treating an initial 1% value as temperature-independent resistance.
    temperature_delta=130.
    return dict(mpn=props['MPN'],nominal_ohms=ohms,tolerance_fraction=.01,
        tcr_bound_ppm_per_c=tcr,temperature_bounds_c=[-55.,155.],reference_temperature_c=25.,
        minimum_ohms=ohms*.99*(1-tcr*temperature_delta*1e-6),source=RESISTOR_SOURCE,
        aging_and_fault_conditions_qualified=False,
        resistance_or_power_qualification=False)


def source_contract(board,pad_uuid,*,deadline=None):
    deadline=deadline or time.monotonic()+2.
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(pads)>16384:raise ValueError('resistive_monitor_inventory_bound')
    matching=[p for p in pads if force._uid(p)==pad_uuid]
    if len(matching)!=1:raise ValueError('resistive_monitor_source_land_unknown')
    pad=matching[0];fp=pad.GetParentFootprint();resistor=resistor_contract(fp)
    if not resistor or pad.GetNetCode()<=0 or pad.GetNetname()=='GND':
        raise ValueError('positive_selected_monitor_resistor_required')
    other=next(p for p in fp.Pads() if force._uid(p)!=pad_uuid)
    if other.GetNetCode()<=0 or other.GetNetCode()==pad.GetNetCode() or other.GetNetname()=='GND':
        raise ValueError('distinct_resistor_divider_node_required')
    node=[p for p in pads if p.GetNetCode()==other.GetNetCode()]
    if len(node)!=3 or any(roles.resistive_sensing_endpoint_contract(
            p.GetParentFootprint(),str(p.GetNumber())) is not None
            and roles.resistive_voltage_monitor_contract(p.GetParentFootprint(),str(p.GetNumber())) is None
            for p in node):
        return _fanout_source_contract(board,pad,other,resistor,node,pads,deadline=deadline)
    monitors=[];grounds=[]
    for member in node:
        if time.monotonic()>=deadline:raise ValueError('resistive_monitor_inventory_deadline')
        if force._uid(member)==force._uid(other):continue
        owner=member.GetParentFootprint()
        monitor=roles.resistive_voltage_monitor_contract(owner,str(member.GetNumber()))
        if monitor:
            supply=owner.FindPadByNumber(monitor['associated_power_pin'])
            if supply is None or supply.GetNetCode()!=pad.GetNetCode():
                raise ValueError('monitor_associated_supply_not_source_tap_rail')
            monitors.append((member,monitor,supply))
        else:
            bottom=resistor_contract(owner)
            peers=[p for p in owner.Pads() if force._uid(p)!=force._uid(member)]
            if not bottom or len(peers)!=1 or peers[0].GetNetname()!='GND':
                raise ValueError('unowned_or_load_bearing_divider_node')
            grounds.append((member,bottom))
    if len(monitors)!=1 or len(grounds)!=1:raise ValueError('unique_manufacturer_monitor_and_ground_resistor_required')
    member,monitor,supply=monitors[0]
    power_bounds=monitor['power_voltage_bounds_v'];input_bounds=monitor['monitor_voltage_bounds_v']
    delta=max(abs(power_bounds[0]-input_bounds[1]),abs(power_bounds[1]-input_bounds[0]))
    amps=delta/resistor['minimum_ohms']
    return dict(pad_uuid=pad_uuid,ref=fp.GetReference(),pin=str(pad.GetNumber()),
        net=str(pad.GetNetname()),resistor=resistor,monitor=monitor,
        monitor_pad_uuid=force._uid(member),associated_supply_pad_uuid=force._uid(supply),
        bottom_resistor_uuid=force._uid(grounds[0][0].GetParentFootprint()),
        maximum_endpoint_differential_v=delta,current_upper_bound_a=amps,
        numeric_rail_load_budget_modified=False,release_authority=False,
        operating_absolute_limit_or_transient_qualification=False)


def _shunt_filter_contract(fp,member):
    """Selected passive two-land filters, never an unowned device or source."""
    from cec_footprint_fields import footprint_properties
    if fp.IsDNP():return None
    choices={
        'CL05B103KB5NNNC':({'10nf','0.01uf','10n'},'https://product.samsungsem.com/mlcc/CL05B103KB5NNN.do'),
        'CL05B104KO5NNNC':({'100nf','0.1uf','100n'},'https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do')}
    mpn=str(footprint_properties(fp).get('MPN') or '').upper();selected=choices.get(mpn)
    lands=list(fp.Pads())
    if (not selected or str(fp.GetValue()).replace(' ','').lower() not in selected[0]
            or not re.search(r'(?:^|:)C_0402_1005Metric$',fp.GetFPIDAsString())
            or len(lands)!=2 or len({p.GetNumber() for p in lands})!=2
            or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in lands)):return None
    peers=[p for p in lands if force._uid(p)!=force._uid(member)]
    if len(peers)!=1 or peers[0].GetNetname()!='GND':return None
    return dict(selected_mpn=mpn,source=selected[1],return_pad_uuid=force._uid(peers[0]),
        passive_shunt_filter=True,stored_energy_or_transient_qualification=False)


def _fanout_source_contract(board,pad,other,resistor,node,pads,*,deadline):
    # One selected top resistor, one selected ground resistor, at most two
    # positively typed inputs and two selected shunt capacitors. This is not
    # arbitrary net traversal or a generic resistor-as-load exemption.
    if not 3<=len(node)<=6:raise ValueError('bounded_closed_monitor_fanout_node_required')
    monitors=[];grounds=[];filters=[]
    for member in node:
        if time.monotonic()>=deadline:raise ValueError('resistive_monitor_inventory_deadline')
        if force._uid(member)==force._uid(other):continue
        owner=member.GetParentFootprint()
        endpoint=roles.resistive_sensing_endpoint_contract(owner,str(member.GetNumber()))
        if endpoint:
            supply=owner.FindPadByNumber(endpoint['associated_power_pin'])
            if supply is None or supply.GetNetCode()<=0 or supply.GetNetCode()==other.GetNetCode():
                raise ValueError('positive_distinct_monitor_power_supply_required')
            if endpoint['source_rail_must_equal_associated_power'] and supply.GetNetCode()!=pad.GetNetCode():
                raise ValueError('monitor_associated_supply_not_source_tap_rail')
            monitors.append((member,endpoint,supply));continue
        bottom=resistor_contract(owner)
        peers=[p for p in owner.Pads() if force._uid(p)!=force._uid(member)]
        if bottom and len(peers)==1 and peers[0].GetNetname()=='GND':
            grounds.append((member,bottom));continue
        cap=_shunt_filter_contract(owner,member)
        if cap:filters.append((member,cap));continue
        raise ValueError('unowned_or_load_bearing_monitor_fanout_node')
    if not 1<=len(monitors)<=2 or len(grounds)!=1 or len(filters)>2:
        raise ValueError('bounded_manufacturer_inputs_and_unique_ground_resistor_required')
    witnesses=[]
    for member in pads:
        if time.monotonic()>=deadline:raise ValueError('resistive_monitor_inventory_deadline')
        if member.GetNetCode()!=pad.GetNetCode():continue
        witness=roles.resistive_source_voltage_contract(member.GetParentFootprint(),member.GetNumber())
        if witness:witnesses.append((member,witness))
    if not witnesses:raise ValueError('positive_same_rail_manufacturer_power_voltage_witness_required')
    # Stable native identity, independent of reference names or coordinates.
    source_member,source_witness=min(witnesses,key=lambda q:force._uid(q[0]))
    power_bounds=source_witness['voltage_bounds_v']
    input_bounds=[min(0.,*(q[1]['monitor_voltage_bounds_v'][0] for q in monitors)),
                  max(0.,*(q[1]['monitor_voltage_bounds_v'][1] for q in monitors))]
    delta=max(abs(power_bounds[0]-input_bounds[1]),abs(power_bounds[1]-input_bounds[0]))
    selected=sorted(monitors,key=lambda q:force._uid(q[0]));member,monitor,supply=selected[0]
    return dict(pad_uuid=force._uid(pad),ref=pad.GetParentFootprint().GetReference(),pin=pad.GetNumber(),
        net=str(pad.GetNetname()),resistor=resistor,monitor=monitor,
        monitor_pad_uuid=force._uid(member),associated_supply_pad_uuid=force._uid(source_member),
        source_power_voltage_contract=source_witness,
        monitor_endpoint_contracts=[dict(pad_uuid=force._uid(p),contract=c,
            actual_monitor_supply_pad_uuid=force._uid(s)) for p,c,s in selected],
        shunt_filter_contracts=[dict(pad_uuid=force._uid(p),contract=c) for p,c in sorted(filters,key=lambda q:force._uid(q[0]))],
        bottom_resistor_uuid=force._uid(grounds[0][0].GetParentFootprint()),
        maximum_endpoint_differential_v=delta,current_upper_bound_a=delta/resistor['minimum_ohms'],
        current_bound_conditional_on_documented_endpoint_voltage_envelopes=True,
        gpio_high_impedance_or_equal_load_sharing_assumed=False,
        numeric_rail_load_budget_modified=False,release_authority=False,
        operating_absolute_limit_or_transient_qualification=False)


def plan(board,pad_uuid,*,timeout_s=2.):
    """Classify an exclusive tap, including native layer transitions.

    This is current-check evidence only, NOT retirement/rip-up authority.
    The walk stops at its first real junction. A plated barrel is traversed
    only when it has exactly one onward conductor and passes the declared
    ordinary or local filled/capped geometry contract.
    """
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('bounded_resistive_monitor_plan_required')
    deadline=time.monotonic()+timeout_s
    contract=source_contract(board,pad_uuid,deadline=deadline)
    result=_native_exclusive_plan(board,pad_uuid,deadline=deadline)
    result['scope']='source_typed_bounded_resistive_voltage_monitor_current_only'
    result['source_resistive_monitor_contract']=contract
    return result


def route_spec(board,source,pad_uuid,*,deadline=None):
    """Size ONLY a positively source-typed resistor-fed sensing leaf.

    KiCad netclass track width is a routing preference, not a declaration
    that a 47 kohm tap carries the parent rail's entire load. Preserve its
    clearance and ordinary-via preferences, board fabrication minimum and
    positive bounded-current floor. This must never size a bus, load branch
    or unknown endpoint; saved native exclusive-material/partition receiving
    is still required before any current-path classification is accepted.
    Native custom width rules remain independently enforced by final DRC.
    """
    demand=source_contract(board,pad_uuid,deadline=deadline)
    limits=dimensions.board_limits(board)
    if not math.isfinite(limits['track_width']) or limits['track_width']<=0:
        raise ValueError('positive_monitor_board_fabrication_width_required')
    parent=fr._project_netclass_resolver(str(source))(demand['net']) or {}
    spec=dimensions.compile_spec(dict(parent,track_width=limits['track_width']),
        limits=limits,role='branch',source='positive_selected_resistor_fanout_and_native_leaf_receiving')
    spec['dimension_contract'].update(
        source_typed_resistive_monitor_pad_uuid=pad_uuid,
        parent_net_preferred_track_width_mm=parent.get('track_width'),
        current_upper_bound_a=demand['current_upper_bound_a'],
        full_rail_load_budget_or_trunk_width_modified=False,
        exclusive_native_material_and_collective_partition_receiving_required=True)
    return spec,demand


def _native_exclusive_plan(board,pad_uuid,*,deadline):
    """Native shape walk shared by independently source-typed classifiers.

    Geometry alone does not identify a nonload input or grant any exemption.
    Callers must verify a manufacturer/divider contract and collectively cut
    all returned material before comparing actual current-terminal partitions.
    This internal result never authorizes retirement, routing or release.
    """
    import cec_fab_profile as fab
    pads=[p for f in board.GetFootprints() for p in f.Pads()]
    root=next(p for p in pads if force._uid(p)==pad_uuid)
    layers=tuple(map(int,board.GetEnabledLayers().CuStack()))
    material=[i for i in [*pads,*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]] if i.GetNetCode()==root.GetNetCode()]
    if len(material)>4096:raise ValueError('resistive_monitor_native_inventory_bound')
    def shape(item,layer):
        if item.GetClass()=='ZONE':
            if not item.IsFilled():raise ValueError('resistive_monitor_native_fill_unknown')
            return item.GetFilledPolysList(layer)
        return item.GetEffectiveShape(layer)
    def contacts(item,ignored):
        found=[]
        for other in material:
            if time.monotonic()>=deadline:raise ValueError('resistive_monitor_native_deadline')
            if force._uid(other)==force._uid(item) or force._uid(other) in ignored:continue
            if any(item.IsOnLayer(l) and other.IsOnLayer(l)
                    and shape(item,l).Collide(shape(other,l),0) for l in layers):found.append(other)
        return found
    def local_turn_barrel(track,far,onward,ignored):
        """Two geometric contacts can be one contained dogbone, not a fork.

        The short same-width surface turn must fit entirely within the
        qualified barrel's OUTER landing aperture. Require exactly one
        electrical departure on a different layer and no pad/zone/shared
        conductor contact. This never traverses a real bus junction or
        credits plating ampacity; collective current-terminal cuts follow.
        """
        if len(onward)!=2:return None
        tails=[t for t in onward if t.GetClass()=='PCB_TRACK']
        barrels=[t for t in onward if t.GetClass()=='PCB_VIA']
        if len(tails)!=1 or len(barrels)!=1:return None
        tail,barrel=tails[0],barrels[0];at=tuple(barrel.GetPosition())
        ends=[tuple(tail.GetStart()),tuple(tail.GetEnd())]
        if (force._uid(tail) in ignored or force._uid(barrel) in ignored
                or tail.GetLayer()!=track.GetLayer() or tail.GetWidth()!=track.GetWidth()
                or far not in ends or at not in ends or far==at
                or int(barrel.GetViaType())!=int(pcbnew.VIATYPE_THROUGH)
                or int(barrel.TopLayer())!=pcbnew.F_Cu or int(barrel.BottomLayer())!=pcbnew.B_Cu):return None
        diameter=int(barrel.GetWidth(barrel.TopLayer()));drill=int(barrel.GetDrillValue())
        limits=dimensions.board_limits(board)
        ordinary=(drill>=math.ceil(limits['via_drill']*1e6)
            and diameter>=math.ceil(limits['via_diameter']*1e6)
            and (diameter-drill)/2>=math.ceil(limits['annular']*1e6))
        if not ordinary and not fab.local_pofv_via_decision(board,barrel)[0]:return None
        if any(math.dist(point,at)+tail.GetWidth()/2>diameter/2 for point in ends):return None
        omitted=set(ignored)|{force._uid(track),force._uid(tail),force._uid(barrel)}
        onward_native={force._uid(t):t for i in (tail,barrel) for t in contacts(i,omitted)}
        extra=[];exit_at=at
        if len(onward_native)==2:
            # A route grid can produce one equally short turn on the other
            # face. Absorb it only if its entire outer copper aperture is
            # inside this SAME qualified landing and there remains exactly
            # one real native departure, not a second branch/pad/plane.
            contained=[t for t in onward_native.values() if t.GetClass()=='PCB_TRACK'
                and t.GetLayer()!=tail.GetLayer() and t.GetWidth()==tail.GetWidth()
                and at in (tuple(t.GetStart()),tuple(t.GetEnd()))
                and all(math.dist(point,at)+t.GetWidth()/2<=diameter/2
                    for point in (tuple(t.GetStart()),tuple(t.GetEnd())))]
            if len(contained)!=1:return None
            inset=contained[0];extra=[inset]
            exit_at=next((point for point in (tuple(inset.GetStart()),tuple(inset.GetEnd())) if point!=at),None)
            if exit_at is None:return None
            omitted.add(force._uid(inset))
            onward_native={force._uid(t):t for i in (tail,barrel,inset) for t in contacts(i,omitted)}
        if len(onward_native)!=1:return None
        child=next(iter(onward_native.values()))
        if (child.GetClass()!='PCB_TRACK' or child.GetLayer()==tail.GetLayer()
                or exit_at not in (tuple(child.GetStart()),tuple(child.GetEnd()))
                or extra and child.GetLayer()!=extra[0].GetLayer()):return None
        return tail,barrel,extra,child
    pending=contacts(root,set())
    if len(pending)!=1:raise ValueError('exclusive_single_native_monitor_departure_required')
    current=pending[0];previous=root;selected=[];track_ids=[];via_ids=[];widths={};length=0.;bundles=[]
    while True:
        if time.monotonic()>=deadline:raise ValueError('resistive_monitor_native_deadline')
        uid=force._uid(current);kind=current.GetClass()
        if uid in selected or kind not in ('PCB_TRACK','PCB_VIA'):
            raise ValueError('exclusive_native_monitor_copper_required')
        onward=contacts(current,{pad_uuid,*selected})
        if kind=='PCB_TRACK':
            width=int(current.GetWidth());layer=int(current.GetLayer())
            if not 0<width<=350000 or current.GetLength()<=0:
                raise ValueError('bounded_thin_monitor_track_required')
            ends=[tuple(current.GetStart()),tuple(current.GetEnd())]
            previous_shape=shape(previous,layer)
            inside=[p for p in ends if previous_shape.Collide(pcbnew.VECTOR2I(*p),0)]
            if len(inside)!=1:raise ValueError('monitor_track_needs_exact_exclusive_entry')
            far=ends[1] if ends[0]==inside[0] else ends[0]
            aperture=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*far),pcbnew.VECTOR2I(*far),width)
            if any(not other.IsOnLayer(layer) or not shape(other,layer).Collide(aperture,0)
                    for other in onward):
                raise ValueError('monitor_track_has_unowned_interior_contact')
            selected.append(uid);track_ids.append(uid);widths[uid]=(layer,width)
            length+=current.GetLength()/1e6
            bundle=local_turn_barrel(current,far,onward,{pad_uuid,*selected})
            if bundle:
                tail,barrel,extra,child=bundle;tail_uid=force._uid(tail);barrel_uid=force._uid(barrel)
                selected += [tail_uid,barrel_uid];track_ids.append(tail_uid);via_ids.append(barrel_uid)
                widths[tail_uid]=(int(tail.GetLayer()),int(tail.GetWidth()));length+=tail.GetLength()/1e6
                for inset in extra:
                    inset_uid=force._uid(inset);selected.append(inset_uid);track_ids.append(inset_uid)
                    widths[inset_uid]=(int(inset.GetLayer()),int(inset.GetWidth()));length+=inset.GetLength()/1e6
                bundles.append(dict(track_uuid=tail_uid,via_uuid=barrel_uid,
                    other_face_contained_track_uuids=[force._uid(t) for t in extra],
                    contained_outer_landing_aperture=True,unique_other_layer_departure_uuid=force._uid(child),
                    barrel_ampacity_or_release_qualification=False))
                if len(track_ids)>16 or len(via_ids)>4 or length>24:
                    raise ValueError('monitor_exclusive_branch_scope_bound')
                previous,current=barrel,child
                continue
            # A pad, zone, shared fork or width transition is retained, never
            # traversed. Exact endpoint-linear thin conductors alone continue.
            linear=bool(len(onward)==1 and (
                onward[0].GetClass()=='PCB_VIA' and tuple(onward[0].GetPosition())==far
                or onward[0].GetClass()=='PCB_TRACK' and int(onward[0].GetLayer())==layer
                and int(onward[0].GetWidth())==width
                and far in (tuple(onward[0].GetStart()),tuple(onward[0].GetEnd()))))
        else:
            # The first trunk barrel/zone contact is the immutable boundary.
            # Do not grant a full-rail via a small-branch classification.
            linear=bool(len(onward)==1 and onward[0].GetClass()=='PCB_TRACK'
                and tuple(current.GetPosition()) in (
                    tuple(onward[0].GetStart()),tuple(onward[0].GetEnd())))
            if not linear:
                if not track_ids or not onward:raise ValueError('monitor_barrel_boundary_unknown')
                boundary=[uid];break
            if (int(current.GetViaType())!=int(pcbnew.VIATYPE_THROUGH)
                    or int(current.TopLayer())!=pcbnew.F_Cu or int(current.BottomLayer())!=pcbnew.B_Cu):
                raise ValueError('monitor_requires_native_through_barrel')
            dia=int(current.GetWidth(current.TopLayer()));drill=int(current.GetDrillValue())
            limits=dimensions.board_limits(board)
            ordinary=bool(drill>=round(limits['via_drill']*1e6)
                and dia>=round(limits['via_diameter']*1e6)
                and (dia-drill)/2>=round(limits['annular']*1e6))
            if not ordinary and not fab.local_pofv_via_decision(board,current)[0]:
                raise ValueError('monitor_barrel_has_no_declared_factory_geometry')
            # No parallel return to the same incoming face: this must be an
            # actual layer transition, not a way to traverse a surface fork.
            if (previous.GetClass()=='PCB_TRACK' and
                    previous.GetLayer()==onward[0].GetLayer()):
                raise ValueError('monitor_barrel_is_not_exclusive_layer_transition')
            selected.append(uid);via_ids.append(uid)
        if len(track_ids)>16 or len(via_ids)>4 or length>24:
            raise ValueError('monitor_exclusive_branch_scope_bound')
        if not onward:raise ValueError('monitor_retained_boundary_missing')
        if not linear:
            boundary=sorted(force._uid(i) for i in onward);break
        previous,current=current,onward[0]
    if not track_ids:raise ValueError('monitor_thin_copper_missing')
    return dict(schema=1,scope='native_exclusive_branch_geometry_only',
        pad_uuid=pad_uuid,net=str(root.GetNetname()),track_uuids=track_ids,via_uuids=via_ids,
        native_removed_material_uuids=selected,track_widths_by_uuid=widths,
        boundary_uuids=boundary,source_length_mm=length,
        native_contained_turn_barrel_bundles=bundles,
        retirement_authority=False,release_authority=False)


def inventory(board,source,domains,*,timeout_s=2.,max_leaves=64):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(max_leaves) is not int or not 1<=max_leaves<=64):
        raise ValueError('bounded_resistive_monitor_inventory_required')
    from cec_measurement_current_branch import _partitions
    deadline=time.monotonic()+timeout_s;resolver=fr._project_netclass_resolver(str(source))
    cohorts={};refusals=[];count=0;tracks={force._uid(t):t for t in board.GetTracks()}
    for fp in board.GetFootprints():
        if time.monotonic()>=deadline:break
        if resistor_contract(fp) is None:continue
        for pad in fp.Pads():
            net=str(pad.GetNetname());domain=domains.get(net,{})
            if domain.get('complete') is not True or fp.GetReference() in domain['authority_refs']:continue
            count+=1
            if count>max_leaves or time.monotonic()>=deadline:
                return dict(uuids=[],proofs=[],refusals=refusals,complete=False,release_authority=False)
            try:
                q=plan(board,force._uid(pad),timeout_s=max(.001,deadline-time.monotonic()))
                contract=q['source_resistive_monitor_contract']
                import cec_fab_profile as fab
                hint=str(board.GetFileName() or source)
                profile=fab.active_profile_name(board,hint=hint)
                if profile is None:raise ValueError('resistive_monitor_process_profile_required')
                authority=dict(amps=contract['current_upper_bound_a'],margin_included=True,geometry_margin=1.,
                    source='manufacturer_voltage_bounds_and_selected_resistance_minimum')
                spec,retyped=route_spec(board,source,force._uid(pad),deadline=deadline)
                if retyped!=contract:raise ValueError('source_monitor_contract_changed_during_native_receiving')
                layer_name=lambda layer:fab.COPPER_LAYER_IDS.get(layer,board.GetLayerName(layer))
                layer_names={layer_name(layer) for layer,width in q['track_widths_by_uuid'].values()}
                required=dimensions.current_trace_widths(authority,sorted(layer_names),profile,rise_c=30.)
                if any(width+1e-6<max(required[layer_name(layer)],spec['track_width'])*1e6
                        for layer,width in q['track_widths_by_uuid'].values()):
                    raise ValueError('resistive_monitor_below_project_process_or_bounded_current_floor')
                cohorts.setdefault(net,[]).append(q)
            except (ValueError,RuntimeError) as exc:
                refusals.append(dict(pad_uuid=force._uid(pad),net=net,reason=str(exc)))
    admitted=set();proofs=[]
    for net,qs in sorted(cohorts.items()):
        try:
            ids={u for q in qs for u in q['track_uuids']}
            cut_ids={u for q in qs for u in q['native_removed_material_uuids']}
            pads=force._authority_pads(board,net,domains[net]);pad_ids={force._uid(p) for p in pads}
            material=[p for fp in board.GetFootprints() for p in fp.Pads()
                if p.GetNetname()==net and force._uid(p) not in pad_ids]
            material += [t for t in tracks.values() if t.GetNetname()==net]
            material += [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net]
            if not pads or len(material)+len(pads)>4096:raise ValueError('resistive_monitor_native_inventory_bound')
            before=_partitions(pads,material,deadline)
            after=_partitions(pads,[i for i in material if force._uid(i) not in cut_ids],deadline)
            if before!=after:raise ValueError('resistive_monitor_removal_changes_actual_current_terminal_partitions')
            admitted|=ids
            proofs.append(dict(net=net,track_uuids=sorted(ids),taps=[q['source_resistive_monitor_contract'] for q in qs],
                native_exclusive_branch_material_uuids=sorted(cut_ids),
                native_current_terminal_partitions=before,partitions_unchanged_after_collective_removal=True,
                source_or_sink_load_budget_changed=False,current_path_qualified=False,release_authority=False))
        except (ValueError,RuntimeError) as exc:refusals.append(dict(net=net,reason=str(exc)))
    complete=time.monotonic()<deadline
    return dict(uuids=sorted(admitted) if complete else [],proofs=proofs if complete else [],
        refusals=refusals,complete=complete,current_path_qualified=False,release_authority=False)

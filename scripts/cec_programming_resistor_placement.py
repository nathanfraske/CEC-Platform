"""Canonical manufacturer-programming resistors, not bypasses or load ratings.

The catalog distinguishes the TPS2121 RUX ILIM-to-Ground resistor from a
closed selected monitor divider's lower resistor. The latter retains its
upper resistor, associated input rail and third native/canonical terminal;
an explicitly posed upper resistor may move with the lower as a complete
source-verified pair, without moving the owner or reducing the rail budget.
it is never relabelled as ILIM or as an unqualified two-terminal pull-down.
Its selected part/value and BOTH original native terminal components remain
mandatory. Owner motion, copper retirement, a smaller width, programmed
current or fabrication qualification cannot be inferred from this role.
"""
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_control_gate_bias_placement as native
import cec_control_pullup_placement as resistors
import cec_control_shunt_placement as shunt
import cec_device_power_roles as roles
import cec_force_current as force
import cec_quiet_signal_requests as pins
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_source_signal_bias_placement as rigid
import cec_synth_pipeline as synth

ROLE='source_manufacturer_programming_resistor'
GROUND_ROLE='source_manufacturer_programming_resistor_ground'
PDF='lib/datasheets/TPS2121RUXR.pdf'
PDF_SHA256='b2f5950f596dc2c4ca33e4ebac27fd35e4dcc68ea63e173466123e1118e91a06'
PIN_NAMES={'1':'OUT','2':'IN2','3':'CP2','4':'OV2','5':'OV1','6':'PR1',
    '7':'IN1','8':'OUT','9':'ST','10':'ILM','11':'SS','12':'GND'}


def _need(value,reason):
    if not value:raise ValueError(reason)


def _left(deadline):
    left=deadline-time.monotonic();_need(left>0,'programming_resistor_Source_deadline')
    return min(10.,left)


def _wire(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def participant_refs(selected):
    """Enumerate a freshly compiled role's posed participants, not authority."""
    result=set(selected)
    for item in selected.values():
        divider=item.get('source_monitor_divider',{})
        if divider.get('upper_motion') is True:result.add(divider['upper_reference'])
    return result


def manufacturer_contract(fp):
    """Exact selected part/package, never a net-name/control-pin heuristic."""
    props=canonical.footprint_properties(fp)
    model=roles.footprint_contract(fp)
    if (fp.IsDNP()or props.get('MPN')!='TPS2121RUXR'
            or ' '.join(str(props.get('Manufacturer','')).upper().split())!='TEXAS INSTRUMENTS'
            or fp.GetFPIDAsString().split(':')[-1]!='RUX0012A'
            or not model or model['device_package']!='TPS2121 RUX'
            or model['pins'].get('10')!='control'or model['pins'].get('12')!='ground'):
        return None
    pads=list(fp.Pads());face=int(fp.GetLayer())
    if (face not in(0,2)or len(pads)!=12 or {p.GetNumber()for p in pads}!=set(PIN_NAMES)
            or any(p.HasHole()or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or tuple(map(int,p.GetLayerSet().CuStack()))!=(face,)for p in pads)):
        return None
    return dict(device_package=model['device_package'],selected_mpn=props['MPN'],
        role='output_current_limit_programming',program_pin='10',ground_pin='12',
        manufacturer_source=model['source'],datasheet=PDF,datasheet_sha256=PDF_SHA256,
        revision='SLVSEA3F August 2020',pin_table_page=4,section='9.3.2',
        schematic_program_pin_names=['ILM','ILIM'],manufacturer_pin_name='ILIM',
        current_authority=False,programmed_current_qualified=False,release_authority=False)


def monitor_divider_contract(fp,pin):
    """Positive manufacturer monitor, not a net-name or resistor heuristic."""
    base=manufacturer_contract(fp)
    monitor=roles.resistive_voltage_monitor_contract(fp,pin)
    if base is None or monitor is None:return None
    return dict(base,role='grounded_voltage_monitor_divider_lower',program_pin=str(pin),
        section='6 Pin Configuration and Functions',
        schematic_program_pin_names=[monitor['function']],manufacturer_pin_name=monitor['function'],
        manufacturer_monitor=monitor,voltage_transfer_or_operating_qualified=False)


def _identity(board,fp,comps,instances,node_net,export_pins,deadline,*,owner=False,source_context=None,owner_model=None):
    """Every canonical/export/native pin stays literal; no type normalization."""
    if not owner:
        return native._identity(board,fp,comps,instances,node_net,export_pins,deadline)
    actual=canonical._identity(board,fp.GetReference(),comps,instances,deadline)
    model=manufacturer_contract(fp)
    if owner_model is not None:
        fresh=monitor_divider_contract(fp,owner_model.get('program_pin'))
        _need(fresh is not None and fresh==owner_model,'fresh_manufacturer_monitor_divider_owner_required')
        model=fresh
    _need(model is not None,'positive_manufacturer_programming_owner_required')
    connected=(model['program_pin'],model['ground_pin'])
    roles.physical_pinmap(fp,roles.footprint_contract(fp),timeout_s=_left(deadline))
    blocks=[b for tag,b in actual[2].children if tag=='symbol'
        and canonical.sch.prop_value(b,'Reference')==fp.GetReference()]
    exported_fields={synth._val(p,'name',''):synth._val(p,'value','')
        for p in synth._kids(comps[fp.GetReference()],'property')}
    _need(len(blocks)==1 and canonical.sch.prop_value(blocks[0],'Manufacturer')
        ==exported_fields.get('Manufacturer')==canonical.footprint_properties(fp).get('Manufacturer'),
        'programming_owner_canonical_manufacturer_parity_required')
    libraries=[b for tag,b in actual[2].children if tag=='lib_symbols']
    _need(len(libraries)==1,'programming_owner_complete_embedded_library_required')
    symbols=[n for n in synth._kids(synth.parse_sexpr(libraries[0]),'symbol')
        if len(n)>1 and n[1]==actual[3]['lib_id']]
    _need(len(symbols)==1 and synth._first(symbols[0],'extends')is None,
        'programming_owner_unique_complete_embedded_symbol_required')
    pending=[symbols[0]];embedded={};count=0
    while pending:
        _left(deadline);entry=pending.pop();count+=1
        _need(count<=8192,'programming_owner_embedded_symbol_bound')
        if isinstance(entry,list)and entry:
            if entry[0]=='pin':
                number=synth._val(entry,'number','')
                _need(number and number not in embedded and len(entry)>1,'programming_owner_unique_embedded_pin_required')
                embedded[number]=dict(type=entry[1],name=synth._val(entry,'name',''))
            pending.extend(v for v in entry if isinstance(v,list))
    _need(set(embedded)==set(PIN_NAMES) and len(actual[3]['pins'])==len(embedded)
        and {p['num']for p in actual[3]['pins']}==set(embedded),
        'programming_owner_complete_canonical_pin_table_required')
    source_pins={}
    for pad in fp.Pads():
        _left(deadline);number=pad.GetNumber();pin=embedded[number]
        instance=next(p for p in actual[3]['pins']if p['num']==number)
        markers=[m for m in actual[2].no_connects
            if canonical.source_nc._nm(m['pos'])==canonical.source_nc._nm(instance['pos'])]
        # A package identity includes unused pins.  An explicit Source NC is
        # preserved as identity ONLY; it is never passed to the connected-pin
        # helper or granted routing/placement/current authority.  Mandatory
        # program/return pins must still pass that independent helper.
        nc=None
        if markers:
            _need(number not in connected and source_context is not None,
                'programming_connected_control_and_Ground_required')
            root,files,hashes,binding=source_context
            nc=canonical.source_nc._land_proof(pad,root,files,hashes,binding,lambda:_left(deadline))
            _need(nc is not None and sum(n==pad.GetNetname()for n in node_net.values())==1
                and sum(p.GetNetname()==pad.GetNetname()for f in board.GetFootprints()for p in f.Pads())==1,
                'programming_owner_explicit_unused_pin_singleton_required')
        else:
            _need(canonical._pin(actual,number)['type']==pin['type'],
                'programming_owner_literal_source_pin_type_required')
        expected=PIN_NAMES[number];names=('ILM','ILIM')if number=='10'else(expected,)
        exported=export_pins.get((fp.GetReference(),number),{})
        # KiCad's fresh exporter appends the literal '+no_connect' marker.
        # Match that EXACT representation only when independently proved NC;
        # never strip suffixes or relabel an unconnected program/return pin.
        export_type=pin['type']+('+no_connect'if nc is not None else '')
        _need(instance['type']==pin['type']and pin['name']in names and pad.GetPinFunction()in('',pin['name'])
            and pad.GetPinType()in('',pin['type'])and exported.get('type')==export_type
            and exported.get('name')in(pin['name'],pin['name']+'_'+number)
            and node_net.get((fp.GetReference(),number))==pad.GetNetname(),
            'programming_owner_complete_native_canonical_export_pin_mismatch:'+json.dumps(dict(
                pin=number,instance_type=instance['type'],embedded=pin,exported=exported,
                export_net=node_net.get((fp.GetReference(),number)),native=dict(
                    name=pad.GetPinFunction(),type=pad.GetPinType(),net=pad.GetNetname()),
                explicit_Source_no_connect=nc is not None),sort_keys=True))
        if number in connected:
            _need(pins._source_pin(actual,number,deadline)==pin,'canonical_connected_programming_pin_required')
        if number=='10':_need(pin['type']in('bidirectional','output'),'canonical_programming_pin_function_required')
        if number=='12':_need(pin['type']=='power_in'and pad.GetNetname()=='GND','canonical_programming_Ground_required')
        if model['role']=='grounded_voltage_monitor_divider_lower'and number==model['program_pin']:
            _need(pin==dict(type='input',name=model['manufacturer_pin_name']),
                'canonical_named_manufacturer_monitor_input_required')
        source_pins[number]=dict(pin,net=pad.GetNetname())
        if nc is not None:
            source_pins[number].update(explicit_Source_no_connect_identity=nc,literal_export_type=export_type,
                routing_authority=False)
    return dict(reference=fp.GetReference(),footprint_uuid=force._uid(fp),symbol_uuid=actual[3]['uuid'],
        fields=canonical.footprint_properties(fp),pins=source_pins,manufacturer=model)


def plan(board,poses,*,board_hint,timeout_s=10.,reference_group_uuids=()):
    _need(type(poses)is dict and 1<=len(poses)<=8 and type(board_hint)is str and board_hint
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,
        'bounded_programming_resistor_Source_context_required')
    deadline=time.monotonic()+timeout_s;shunt._reference_group_scope(reference_group_uuids)
    owners=[fp for fp in board.GetFootprints()if manufacturer_contract(fp)is not None]
    candidates=[]
    for ref in sorted(poses):
        fp=board.FindFootprintByReference(ref)
        if fp is None or resistors._ohms(fp.GetValue())is None:continue
        pads=list(fp.Pads())
        if len(pads)!=2 or len({p.GetNumber()for p in pads})!=2:continue
        ground=[p for p in pads if p.GetNetname()=='GND'];signal=[p for p in pads if p.GetNetname()!='GND'and p.GetNetCode()>0]
        if len(ground)!=1 or len(signal)!=1:continue
        possible=[owner for owner in owners if owner.FindPadByNumber('10').GetNetname()==signal[0].GetNetname()]
        divider=None
        if not possible:
            # This helper proves the complete selected THREE-land node and
            # exact associated power rail. A failed native witness grants no
            # new role; the ordinary unknown-component refusal remains.
            import cec_source_divider_ground_span as monitor_divider
            try:divider=monitor_divider._native_owner(board,force._uid(ground[0]),deadline)
            except ValueError:divider=None
            if divider is not None:
                owner=divider[4].GetParentFootprint()
                model=monitor_divider_contract(owner,divider[4].GetNumber())
                if model is not None and force._uid(owner)in{force._uid(q)for q in owners}:possible=[owner]
                else:divider=None
        if possible:candidates.append((fp,ground[0],signal[0],possible,divider))
    if not candidates:return {}
    binding=row._source_binding(board);epoch=force._code_identity();source=Path(board.GetFileName()).resolve(strict=True)
    _need(source.with_suffix('.kicad_pro').is_file(),'saved_programming_resistor_project_required')
    _need(binding==row._source_binding(pcbnew.LoadBoard(str(source))),
        'programming_resistor_native_board_must_equal_saved_Source')
    family=force._family(source,board_hint)
    authorized=shunt._reference_group_authorizations(board,poses,reference_group_uuids,binding=binding,deadline=deadline)
    root=canonical.source_nc._root(board,board_hint);_need(root is not None,'canonical_programming_resistor_root_required');root=root.resolve()
    files,hashes,instances=canonical._hierarchy(root,deadline);tree,exporter=canonical._export(root,deadline)
    _need(all(exporter.get(k)==v for k,v in semantic.metadata(tree).items()),'fresh_programming_resistor_export_semantics_required')
    comps,nets,node_net=canonical._tables(tree)
    export_pins={(synth._val(node,'ref',''),synth._val(node,'pin','')):
        dict(name=synth._val(node,'pinfunction',''),type=synth._val(node,'pintype',''))
        for net in synth._kids(synth._first(tree,'nets'),'net')for node in synth._kids(net,'node')}
    datasheet=Path(__file__).resolve().parents[1]/PDF
    _need(datasheet.is_file()and force._hash(datasheet)==PDF_SHA256,'reviewed_programming_resistor_manufacturer_file_changed')
    base=semantic.replay_identity(dict(root_schematic=str(root),schematic_files_sha256=hashes,
        exporter=exporter,evidence_files_sha256={str(datasheet):PDF_SHA256}))
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()};result={}
    for fp,ground,signal,possible,divider in candidates:
        _left(deadline);_need(len(possible)==1,'unique_canonical_programming_resistor_owner_required');owner=possible[0]
        ref=fp.GetReference();native._smd(fp,2);native._pose(fp,poses);native._stationary(owner,poses)
        _need(not fp.IsLocked()and not fp.IsDNP()
            and (not fp.GetParentGroup()and force._uid(fp)not in grouped or force._uid(fp)in authorized)
            and all(not p.IsLocked()and force._uid(p)not in grouped for p in fp.Pads()),
            'unlocked_populated_Source_programming_resistor_required')
        model=(manufacturer_contract(owner)if divider is None else monitor_divider_contract(owner,divider[4].GetNumber()))
        control=owner.FindPadByNumber(model['program_pin']);return_pad=owner.FindPadByNumber(model['ground_pin'])
        _need(return_pad.GetNetname()=='GND'and control.GetNetname()not in('','GND'), 'distinct_programming_signal_and_return_required')
        members={(f.GetReference(),p.GetNumber())for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==signal.GetNetname()}
        expected={(ref,signal.GetNumber()),(owner.GetReference(),control.GetNumber())}
        if divider is not None:
            uppernode,upperpower=divider[2:4];upper=uppernode.GetParentFootprint()
            native._smd(upper,2)
            upper_motion=upper.GetReference() in poses
            if upper_motion:
                native._pose(upper,poses)
                _need(not upper.IsLocked()and not upper.IsDNP()
                    and (not upper.GetParentGroup()and force._uid(upper)not in grouped or force._uid(upper)in authorized)
                    and all(not p.IsLocked()and force._uid(p)not in grouped for p in upper.Pads()),
                    'unlocked_populated_Source_monitor_upper_required')
            else:native._stationary(upper,poses)
            expected.add((upper.GetReference(),uppernode.GetNumber()))
        _need(members==expected and nets.get(signal.GetNetname())==expected,'complete_unique_canonical_programming_net_required')
        identities={ref:_identity(board,fp,comps,instances,node_net,export_pins,deadline),
            owner.GetReference():_identity(board,owner,comps,instances,node_net,export_pins,deadline,owner=True,
                source_context=(root,files,hashes,binding),**(dict(owner_model=model)if divider is not None else {}))}
        if divider is not None:
            identities[upper.GetReference()]=_identity(board,upper,comps,instances,node_net,export_pins,deadline)
            _need(synth._val(synth._first(comps[upper.GetReference()],'libsource'),'part','')in('R','R_Small')
                and all(canonical._pin(canonical._identity(board,upper.GetReference(),comps,instances,deadline),
                    p.GetNumber())['type']=='passive'for p in upper.Pads()),
                'canonical_selected_passive_upper_divider_required')
        contacts={force._uid(p):native._direct_contacts(board,p,deadline)for p in(ground,signal)}
        item=dict(role=ROLE,resistor_uuid=force._uid(fp),ground_pad_uuid=force._uid(ground),signal_pad_uuid=force._uid(signal),
            control_pad_uuid=force._uid(control),control_owner=owner.GetReference(),control_owner_uuid=force._uid(owner),
            control_pin=control.GetNumber(),net=signal.GetNetname(),source_value=fp.GetValue(),
            source_declared_resistance_ohms=resistors._ohms(fp.GetValue()),source_native_binding=binding,
            source_proof=dict(base,selected_components=identities,manufacturer=model),
            source_resistor_identity=native._footprint(board,fp),source_stationary_owner_identity=native._footprint(board,owner),
            source_terminal_contacts=contacts,all_source_contacts_are_mandatory=True,
            bypass_owner=False,current_authority=False,programmed_current_qualified=False,
            source_trace_retirement_authority=False,new_barrel_authority=False,release_authority=False)
        if divider is not None:
            item['source_monitor_divider']=dict(upper_reference=upper.GetReference(),upper_uuid=force._uid(upper),
                upper_node_pad_uuid=force._uid(uppernode),upper_power_pad_uuid=force._uid(upperpower),
                monitor_pad_uuid=force._uid(control),associated_supply_pad_uuid=force._uid(divider[5]),
                closed_node_members=sorted([list(v)for v in expected]),
                source_stationary_upper_identity=native._footprint(board,upper),
                every_closed_node_member_mandatory=True,voltage_transfer_or_operating_qualified=False)
            if upper_motion:
                record=item['source_monitor_divider']
                record['source_moving_upper_identity']=record.pop('source_stationary_upper_identity')
                record.update(upper_motion=True,supply_net=upperpower.GetNetname(),
                    source_terminal_contacts={force._uid(p):native._direct_contacts(board,p,deadline)for p in upper.Pads()},
                    all_source_contacts_are_mandatory=True,unchanged_full_rail_current_required=True,
                    current_authority=False,new_barrel_authority=False,source_trace_retirement_authority=False)
                if force._uid(upper)in authorized:
                    record['source_reference_group_authorization']=authorized[force._uid(upper)]
        if force._uid(fp)in authorized:item['source_reference_group_authorization']=authorized[force._uid(fp)]
        result[ref]=item
    _left(deadline)
    _need(binding==row._source_binding(board)and epoch==force._code_identity()and family==force._family(source,board_hint)
        and hashes=={str(p):force._hash(p)for p in files}
        and force._hash(Path(exporter['exporter']))==exporter['exporter_sha256'], 'programming_resistor_Source_identity_changed')
    return _wire(result)


def requests(source,board,proposal,*,timeout_s=10.):
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,
        'bounded_programming_resistor_request_context_required')
    selected=proposal.get('selected_programming_resistors',{})
    if not selected:return {}
    deadline=time.monotonic()+timeout_s
    fresh=plan(source,proposal['poses'],board_hint=proposal['board_hint'],timeout_s=_left(deadline),
        reference_group_uuids=proposal.get('reference_group_uuids',()))
    _need(fresh==selected,'fresh_Source_programming_resistor_proposal_required')
    import cec_decoupler_cell as cells
    pads={force._uid(p):p for f in board.GetFootprints()for p in f.Pads()};result={}
    def endpoint(p):return dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),layers=list(map(int,p.GetLayerSet().CuStack())))
    for ref,item in selected.items():
        original=source.FindFootprintByReference(ref);fp=board.FindFootprintByReference(ref)
        owner=source.FindFootprintByReference(item['control_owner']);live_owner=board.FindFootprintByReference(item['control_owner'])
        _need(fp is not None and live_owner is not None,'actual_programming_resistor_and_owner_required')
        rigid._rigid_part(original,fp,proposal['poses']);rigid._rigid_part(owner,live_owner,{})
        _need(native._footprint(board,live_owner)==item['source_stationary_owner_identity'],
            'programming_owner_complete_stationary_native_identity_changed')
        signal=pads[item['signal_pad_uuid']];control=pads[item['control_pad_uuid']]
        width=max(int(source.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(source,item['net'])['width']))
        _need(width>0,'original_Source_programming_signal_class_required')
        result['programming_resistor:'+item['signal_pad_uuid']]=dict(kind='source_boundary',net=item['net'],
            role='manufacturer_programming_control',a=endpoint(signal),b=endpoint(control),width_nm=width,
            source_programming_resistor=item,no_power_bypass_or_current_authority=True,
            every_original_contact_and_immediate_Ground_return_still_required=True)
        divider=item.get('source_monitor_divider')
        if divider is not None:
            upper=board.FindFootprintByReference(divider['upper_reference'])
            _need(upper is not None,'complete_upper_divider_required')
            if divider.get('upper_motion') is True:
                rigid._rigid_part(source.FindFootprintByReference(divider['upper_reference']),upper,proposal['poses'])
                supply=pads[divider['upper_power_pad_uuid']];anchor=pads[divider['associated_supply_pad_uuid']]
                _need(supply.GetNetname()==anchor.GetNetname()==divider['supply_net'],
                    'monitor_upper_associated_supply_identity_changed')
                with force._thermal_hint(proposal['board_hint']):
                    rail=cells._supply_current_widths(source,divider['supply_net'])
                widths=rail.get('required_by_layer_nm')if type(rail)is dict else None
                _need(type(widths)is dict and widths and set(widths)==set(map(int,source.GetEnabledLayers().CuStack()))
                    and all(type(v)is int and v>0 for v in widths.values())
                    and type(rail.get('current_authority'))is dict,
                    'unchanged_complete_monitor_upper_supply_current_contract_required')
                # A same-surface supply obligation has an actual native
                # access face. Do not leak a thin-inner-layer floor into its
                # scalar width. Saved receiving still enforces the complete
                # per-layer contract on every leg, and original contacts
                # separately retain their literal Source widths.
                common=set(map(int,supply.GetLayerSet().CuStack()))&set(map(int,anchor.GetLayerSet().CuStack()))
                supply_width=max(int(source.GetDesignSettings().m_TrackMinWidth),
                    int(cells._netclass(source,divider['supply_net'])['width']),
                    min(widths[face]for face in common)if common else max(widths.values()))
                result['monitor_divider_supply:'+divider['upper_power_pad_uuid']]=dict(
                    kind='source_boundary',net=divider['supply_net'],role='manufacturer_monitor_divider_supply',
                    a=endpoint(supply),b=endpoint(anchor),width_nm=supply_width,
                    unchanged_full_rail_current_contract=rail,source_programming_resistor=item,
                    no_power_bypass_or_current_authority=True,new_barrel_authority=False,
                    class_only_supply_prefix_authority=False,every_original_contact_and_immediate_Ground_return_still_required=True)
            else:
                _need(native._footprint(board,upper)==divider['source_stationary_upper_identity'],
                    'complete_stationary_upper_divider_identity_changed')
            result['monitor_divider_upper:'+item['signal_pad_uuid']]=dict(kind='source_boundary',net=item['net'],
                role='manufacturer_closed_monitor_divider_third_terminal',a=endpoint(signal),
                b=endpoint(pads[divider['upper_node_pad_uuid']]),width_nm=width,
                source_programming_resistor=item,no_power_bypass_or_current_authority=True,
                every_original_contact_and_immediate_Ground_return_still_required=True)
    _left(deadline);return result


def ground_root(item,*,pad_uuid,reference):
    """Structural menu label only; the compiler must freshly rederive item."""
    _need(item.get('role')==ROLE and item.get('ground_pad_uuid')==pad_uuid
        and item.get('current_authority')is False and item.get('source_trace_retirement_authority')is False,
        'fresh_Source_programming_Ground_role_required')
    return dict(pad_uuid=pad_uuid,ref=reference,role=GROUND_ROLE,source_programming_resistor=item,
        manufacturer_source=item['source_proof']['manufacturer']['manufacturer_source'],
        source_ground_strap_restored_without_role_or_current_reclassification=True,current_authority=False)


def ground_root_label(root):
    item=root.get('source_programming_resistor')
    return bool(root.get('role')==GROUND_ROLE and type(item)is dict
        and item.get('role')==ROLE and item.get('ground_pad_uuid')==root.get('pad_uuid')
        and item.get('source_resistor_identity',{}).get('reference')==root.get('ref')
        and _catalog_role_label(item)
        and item.get('all_source_contacts_are_mandatory')is True
        and item.get('programmed_current_qualified')is False and item.get('bypass_owner')is False
        and item.get('release_authority')is False
        and item.get('new_barrel_authority')is False
        and item.get('current_authority')is False and item.get('source_trace_retirement_authority')is False
        and root.get('current_authority')is False
        and root.get('source_ground_strap_restored_without_role_or_current_reclassification')is True
        and root.get('manufacturer_source')==item.get('source_proof',{}).get('manufacturer',{}).get('manufacturer_source'))


def _catalog_role_label(item):
    """Structural label only; every consumer still freshly compiles Source."""
    model=item.get('source_proof',{}).get('manufacturer',{})
    divider=item.get('source_monitor_divider')
    if model.get('role')=='output_current_limit_programming':
        return divider is None and item.get('control_pin')==model.get('program_pin')=='10'
    return bool(model.get('role')=='grounded_voltage_monitor_divider_lower'and type(divider)is dict
        and item.get('control_pin')==model.get('program_pin')==model.get('manufacturer_monitor',{}).get('pin')
        and item.get('control_pin')in('4','5','6')
        and divider.get('monitor_pad_uuid')==item.get('control_pad_uuid')
        and len(divider.get('closed_node_members',[]))==3
        and all(type(v)is list and len(v)==2 and all(type(s)is str and s for s in v)
            for v in divider['closed_node_members'])
        and len({tuple(v)for v in divider['closed_node_members']})==3
        and divider.get('upper_reference')!=item.get('control_owner')
        and divider.get('every_closed_node_member_mandatory')is True
        and divider.get('voltage_transfer_or_operating_qualified')is False
        and model.get('voltage_transfer_or_operating_qualified')is False)

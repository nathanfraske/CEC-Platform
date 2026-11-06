"""Source-owned TPS2121 SS timing ceramic; not a power bypass or EN alias.

Collection and requests are evidence/obligations only. Every old contact and
immediate Ground return remains mandatory; this module owns no copper cuts,
barrels, current budgets, timing qualification or fabrication acceptance.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_programming_resistor_placement as programming
import cec_wired_aggregate_capacitor as wired

native=programming.native
canonical=programming.canonical
force=programming.force
synth=programming.synth
ROLE='source_manufacturer_SS_timing_capacitor'
GROUND_ROLE='source_manufacturer_SS_timing_capacitor_ground'
_need=programming._need
_left=programming._left


def manufacturer_contract(fp):
    """Exact reviewed selected package, with a distinct SS contract."""
    base=programming.manufacturer_contract(fp)
    if base is None:return None
    return dict(device_package=base['device_package'],selected_mpn=base['selected_mpn'],
        role='input_settling_and_output_soft_start_timing',signal_pin='11',ground_pin='12',
        manufacturer_pin_name='SS',manufacturer_pin_type='O',
        manufacturer_source=base['manufacturer_source'],datasheet=programming.PDF,
        datasheet_sha256=programming.PDF_SHA256,revision='SLVSEA3F August 2020',
        pin_table_page=4,section='9.3.1',section_page=12,
        timing_qualified=False,current_authority=False,release_authority=False)


def participant_refs(selected):
    """Only passive participants; never hide the moving stage from receivers."""
    return set(selected)


def replay_options(proposal):
    return programming.replay_options(proposal)


def plan(board,poses,*,board_hint,timeout_s=10.,reference_group_uuids=(),
        allow_linear_power_stage_reconstruction=False):
    _need(type(poses)is dict and 1<=len(poses)<=8 and type(board_hint)is str and board_hint
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,
        'bounded_timing_capacitor_Source_context_required')
    _need(type(allow_linear_power_stage_reconstruction)is bool,
        'explicit_timing_owner_reconstruction_boolean_required')
    _need(all(type(ref)is str and ref and type(p)in(list,tuple)and len(p)==3
        and all(type(v)in(int,float)and math.isfinite(v)for v in p)for ref,p in poses.items()),
        'literal_finite_timing_participant_poses_required')
    deadline=time.monotonic()+timeout_s
    programming.shunt._reference_group_scope(reference_group_uuids)
    owners=[f for f in board.GetFootprints()if manufacturer_contract(f)is not None]
    candidates=[]
    for ref in sorted(poses):
        fp=board.FindFootprintByReference(ref)
        if fp is None or not canonical._ceramic(fp):continue
        pads=list(fp.Pads());ground=[p for p in pads if p.GetNetname()=='GND']
        signal=[p for p in pads if p.GetNetCode()>0 and p.GetNetname()!='GND']
        if len(ground)!=1 or len(signal)!=1:continue
        possible=[o for o in owners if o.FindPadByNumber('11').GetNetname()==signal[0].GetNetname()]
        if possible:candidates.append((fp,ground[0],signal[0],possible))
    if not candidates:return {}
    binding=programming.row._source_binding(board);epoch=force._code_identity()
    source=Path(board.GetFileName()).resolve(strict=True)
    _need(source.with_suffix('.kicad_pro').is_file(),'saved_timing_capacitor_project_required')
    _need(binding==programming.row._source_binding(pcbnew.LoadBoard(str(source))),
        'timing_capacitor_native_board_must_equal_saved_Source')
    family=force._family(source,board_hint)
    authorized=programming.shunt._reference_group_authorizations(board,poses,reference_group_uuids,
        binding=binding,deadline=deadline)
    root=canonical.source_nc._root(board,board_hint)
    _need(root is not None,'canonical_timing_capacitor_root_required');root=root.resolve()
    files,hashes,instances=canonical._hierarchy(root,deadline)
    tree,exporter=canonical._export(root,deadline)
    _need(all(exporter.get(k)==v for k,v in programming.semantic.metadata(tree).items()),
        'fresh_timing_capacitor_export_semantics_required')
    comps,nets,node_net=canonical._tables(tree)
    export_pins={(synth._val(n,'ref',''),synth._val(n,'pin','')):
        dict(name=synth._val(n,'pinfunction',''),type=synth._val(n,'pintype',''))
        for net in synth._kids(synth._first(tree,'nets'),'net')for n in synth._kids(net,'node')}
    datasheet=Path(__file__).resolve().parents[1]/programming.PDF
    _need(datasheet.is_file()and force._hash(datasheet)==programming.PDF_SHA256,
        'reviewed_timing_capacitor_manufacturer_file_changed')
    base=programming.semantic.replay_identity(dict(root_schematic=str(root),schematic_files_sha256=hashes,
        exporter=exporter,evidence_files_sha256={str(datasheet):programming.PDF_SHA256}))
    stages={}
    if allow_linear_power_stage_reconstruction:
        import cec_source_linear_power_stage as stage
        stages=stage.collect(board,poses,board_hint=board_hint,
            reference_group_uuids=reference_group_uuids,enabled=True,timeout_s=_left(deadline))
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()};result={}
    for fp,ground,signal,possible in candidates:
        _left(deadline);_need(len(possible)==1,'unique_canonical_SS_timing_owner_required')
        owner=possible[0];ref=fp.GetReference();native._smd(fp,2);native._pose(fp,poses)
        _need(not fp.IsLocked()and not fp.IsDNP()
            and (not fp.GetParentGroup()and force._uid(fp)not in grouped or force._uid(fp)in authorized)
            and all(not p.IsLocked()and force._uid(p)not in grouped for p in fp.Pads()),
            'unlocked_populated_Source_timing_capacitor_required')
        control=owner.FindPadByNumber('11')
        expected={(ref,signal.GetNumber()),(owner.GetReference(),'11')}
        actual={(f.GetReference(),p.GetNumber())for f in board.GetFootprints()for p in f.Pads()
            if p.GetNetname()==signal.GetNetname()}
        _need(actual==expected and nets.get(signal.GetNetname())==expected,
            'complete_unique_canonical_SS_timing_net_required')
        _need(synth._val(synth._first(comps.get(ref,[]),'libsource'),'part','')in('C','C_Small'),
            'canonical_passive_timing_capacitor_symbol_required')
        cap_model=dict(pins={p.GetNumber():dict(name='~',type='passive')for p in fp.Pads()})
        identities={ref:native._identity(board,fp,comps,instances,node_net,export_pins,deadline,model=cap_model),
            owner.GetReference():programming._identity(board,owner,comps,instances,node_net,export_pins,
                deadline,owner=True,source_context=(root,files,hashes,binding))}
        # Reuse the complete pinmap verifier, not its ILIM role label.
        identities[owner.GetReference()].pop('manufacturer',None)
        ss=canonical._pin(canonical._identity(board,owner.GetReference(),comps,instances,deadline),'11')
        _need(ss['type']in('bidirectional','output')and
            export_pins[(owner.GetReference(),'11')]['type']==ss['type'],
            'literal_connected_manufacturer_SS_pin_required')
        motion=None
        if owner.GetReference()in stages:
            with force._thermal_hint(board_hint):
                selected=wired.cap.constraints._device_bypass_assignment(board,project_max_mm=3.5)
            followers={r['cap_ref']for r in selected['assigned'].values()
                if r['requirement']['ref']==owner.GetReference()}
            _need(followers<=set(poses)and not any(r['ref']==owner.GetReference()for r in selected['missing']),
                'timing_complete_selected_owner_bypasses_required')
            motion=dict(kind='source_linear_stage_timing_owner_reconstruction',
                source_owner_identity=native._footprint(board,owner),source_linear_stage=stages[owner.GetReference()],
                selected_bypass_followers=sorted(followers),copper_transport_authority=False,
                new_barrel_authority=False,every_source_contact_and_return_mandatory=True)
        else:native._stationary(owner,poses)
        wired._reject_uninventoried_artwork(board,fp,deadline)
        # Contact inventory cannot treat unknown/unfilled copper as absent.
        for zone in board.Zones():
            _left(deadline)
            if zone.GetIsRuleArea():continue
            for face in zone.GetLayerSet().CuStack():
                _need(zone.IsFilled()and zone.GetFilledPolysList(face).OutlineCount()>0,
                    'timing_Source_filled_zone_contacts_required')
        item=dict(role=ROLE,capacitor_uuid=force._uid(fp),ground_pad_uuid=force._uid(ground),
            signal_pad_uuid=force._uid(signal),control_pad_uuid=force._uid(control),control_pin='11',
            control_owner=owner.GetReference(),control_owner_uuid=force._uid(owner),net=signal.GetNetname(),
            source_value=fp.GetValue(),source_native_binding=binding,
            source_proof=dict(base,selected_components=identities,manufacturer=manufacturer_contract(owner)),
            source_capacitor_identity=native._footprint(board,fp),
            source_terminal_contacts={force._uid(p):native._direct_contacts(board,p,deadline)for p in(ground,signal)},
            all_source_contacts_are_mandatory=True,maximum_ground_return_mm=.8,
            bypass_owner=False,current_authority=False,timing_qualified=False,
            source_trace_retirement_authority=False,new_barrel_authority=False,release_authority=False)
        if motion is None:item['source_stationary_owner_identity']=native._footprint(board,owner)
        else:item['coherent_owner_motion']=motion
        if force._uid(fp)in authorized:item['source_reference_group_authorization']=authorized[force._uid(fp)]
        result[ref]=item
    _left(deadline)
    _need(binding==programming.row._source_binding(board)and epoch==force._code_identity()
        and family==force._family(source,board_hint)and hashes=={str(p):force._hash(p)for p in files}
        and force._hash(Path(exporter['exporter']))==exporter['exporter_sha256'],
        'timing_capacitor_Source_identity_changed')
    return programming._wire(result)


def requests(source,board,proposal,*,timeout_s=10.):
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,
        'bounded_timing_capacitor_request_context_required')
    selected=proposal.get('selected_timing_capacitors',{})
    if not selected:return {}
    deadline=time.monotonic()+timeout_s
    fresh=plan(source,proposal['poses'],board_hint=proposal['board_hint'],timeout_s=_left(deadline),
        reference_group_uuids=proposal.get('reference_group_uuids',()),**replay_options(proposal))
    _need(fresh==selected,'fresh_Source_timing_capacitor_proposal_required')
    import cec_decoupler_cell as cells
    pads={force._uid(p):p for f in board.GetFootprints()for p in f.Pads()};result={}
    def endpoint(p):return dict(pad_uuid=force._uid(p),at_nm=list(p.GetPosition()),layers=list(map(int,p.GetLayerSet().CuStack())))
    for ref,item in selected.items():
        original=source.FindFootprintByReference(ref);fp=board.FindFootprintByReference(ref)
        owner=source.FindFootprintByReference(item['control_owner']);live=board.FindFootprintByReference(item['control_owner'])
        _need(fp is not None and live is not None,'actual_timing_capacitor_and_owner_required')
        programming.rigid._rigid_part(original,fp,proposal['poses'])
        programming.rigid._rigid_part(owner,live,proposal['poses']if 'coherent_owner_motion'in item else {})
        signal=pads[item['signal_pad_uuid']];control=pads[item['control_pad_uuid']]
        width=max(int(source.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(source,item['net'])['width']))
        _need(width>0,'original_Source_timing_signal_class_required')
        result['timing_capacitor:'+item['signal_pad_uuid']]=dict(kind='source_boundary',net=item['net'],
            role='manufacturer_SS_timing_control',a=endpoint(signal),b=endpoint(control),width_nm=width,
            source_timing_capacitor=item,no_power_bypass_or_current_authority=True,
            every_original_contact_and_immediate_Ground_return_still_required=True)
        ground=pads[item['ground_pad_uuid']]
        ground_width=max(200000,int(source.GetDesignSettings().m_TrackMinWidth),
            int(cells._netclass(source,'GND')['width']))
        result['ground:'+item['ground_pad_uuid']]=dict(kind='ground',net='GND',
            a=endpoint(ground),reach_mm=.8,width_nm=ground_width,
            source_timing_capacitor=item,no_power_bypass_or_current_authority=True,
            every_original_contact_and_immediate_Ground_return_still_required=True)
    _left(deadline);return result


def ground_root(item,*,pad_uuid,reference):
    _need(item.get('role')==ROLE and item.get('ground_pad_uuid')==pad_uuid
        and item.get('source_capacitor_identity',{}).get('reference')==reference
        and item.get('current_authority')is False and item.get('source_trace_retirement_authority')is False,
        'fresh_Source_timing_Ground_role_required')
    return dict(pad_uuid=pad_uuid,ref=reference,role=GROUND_ROLE,source_timing_capacitor=item,
        manufacturer_source=item['source_proof']['manufacturer']['manufacturer_source'],
        source_ground_strap_restored_without_role_or_current_reclassification=True,current_authority=False)


def ground_root_label(root):
    item=root.get('source_timing_capacitor',{})
    model=item.get('source_proof',{}).get('manufacturer',{})
    return bool(root.get('role')==GROUND_ROLE and item.get('role')==ROLE
        and item.get('ground_pad_uuid')==root.get('pad_uuid')
        and item.get('source_capacitor_identity',{}).get('reference')==root.get('ref')
        and model.get('signal_pin')==item.get('control_pin')=='11'
        and model.get('role')=='input_settling_and_output_soft_start_timing'
        and model.get('datasheet_sha256')==programming.PDF_SHA256
        and item.get('all_source_contacts_are_mandatory')is True
        and all(item.get(k)is False for k in('bypass_owner','current_authority','timing_qualified',
            'source_trace_retirement_authority','new_barrel_authority','release_authority'))
        and root.get('current_authority')is False
        and root.get('source_ground_strap_restored_without_role_or_current_reclassification')is True
        and root.get('manufacturer_source')==model.get('manufacturer_source'))

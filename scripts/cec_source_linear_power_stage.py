"""Opt-in literal Source identity for linear pass-power stage reconstruction.

This is not a low-power-device alias. Existing whole-net current authority is
replayed, never created. The first reviewed manufacturer entry is TPS2121 RUX:
its complete physical table is reused from the independent programming-owner
identity, not inferred from net names. Unknown entries remain unclaimed.
No pose, copper cut, barrel, current, route or release authority is granted.
"""
import copy
import contextvars
from contextlib import contextmanager
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_control_shunt_placement as shunt
import cec_device_power_roles as roles
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_programming_resistor_placement as manufacturer
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_synth_pipeline as synth
from cec_native_items import _native_pointer

ROLE = 'source_linear_power_stage'
_observations = contextvars.ContextVar('immutable_Source_linear_stage_observation', default=None)
# KiCad ERC metadata is not the manufacturer's physical direction table.
# The reviewed TPS2121 Source library deliberately uses power_in for both
# OUT lands and adds explicit PWR_FLAGs (gen-hub-rev2 and
# splice_usb_ingress_hub document this). A conventional power_out Source
# remains supported too. Both OUT lands must use ONE literal convention,
# and _identity still requires exact embedded/export/native parity; no
# metadata is normalized, changed or inferred from a rail name here.
REVIEWED_POWER_ERC_TYPES = {
    'TPS2121 RUX': {'power_input': ('power_in',),
                   'power_output': ('power_in', 'power_out')},
}


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _observation_key(board, poses, board_hint, references, enabled):
    return (_native_pointer(board), str(Path(board.GetFileName()).resolve()), board_hint,
        json.dumps(poses, sort_keys=True, allow_nan=False), tuple(references), enabled)


def _observation_live(context):
    """Fresh byte/native fences, including the actual hierarchy inventory."""
    _need(time.monotonic() < context['deadline'], 'linear_stage_observation_deadline')
    board=context['board'];source=context['source']
    _need(str(Path(board.GetFileName()).resolve())==str(source)
        and context['binding']==row._source_binding(board)
        and context['family']==force._family(source,context['hint'])
        and context['epoch']==force._code_identity(), 'immutable_linear_stage_Source_changed')
    if context['result'] is not None:
        root=canonical.source_nc._root(board,context['hint'])
        _need(root is not None and Path(root).resolve()==context['root'],
            'immutable_linear_stage_root_changed')
        files,hashes,_=canonical._hierarchy(context['root'],context['deadline'])
        _need({str(p)for p in files}==set(context['hierarchy'])and hashes==context['hierarchy'],
            'immutable_linear_stage_hierarchy_changed')
        _need(all(Path(name).is_file()and force._hash(Path(name))==digest
            for name,digest in context['evidence'].items()),
            'immutable_linear_stage_evidence_changed')
    _need(time.monotonic() < context['deadline'], 'linear_stage_observation_deadline')


@contextmanager
def observation_scope(board, poses, *, board_hint, reference_group_uuids=(), enabled=True, timeout_s=10.):
    """Private successful facts for ONE immutable invocation, never caller proof.

    Nested scopes are independent and restore their parent even on exceptions.
    A receiver must open its own scope; a new board/request is always a miss.
    """
    _need(type(enabled)is bool and type(board_hint)is str and board_hint
        and type(poses)is dict and 1<=len(poses)<=8
        and type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,
        'bounded_linear_stage_observation_context_required')
    shunt._reference_group_scope(reference_group_uuids)
    _need(all(type(ref)is str and type(p)in(list,tuple)and len(p)==3
        and all(type(v)in(int,float)and math.isfinite(v)for v in p)for ref,p in poses.items()),
        'finite_linear_stage_observation_poses_required')
    deadline=time.monotonic()+timeout_s
    source=Path(board.GetFileName()).resolve(strict=True)
    context=dict(board=board,source=source,hint=board_hint,deadline=deadline,
        key=_observation_key(board,poses,board_hint,reference_group_uuids,enabled),
        binding=row._source_binding(board),family=force._family(source,board_hint),
        epoch=force._code_identity(),result=None,hierarchy={},evidence={})
    token=_observations.set(context)
    try:
        _observation_live(context)
        yield
    finally:
        try:_observation_live(context)
        finally:_observations.reset(token)


def collect(board, poses, *, board_hint, reference_group_uuids=(), enabled=False, timeout_s=10.):
    """Fresh first derivation; exact invocation-local reuse with live fences."""
    _need(type(enabled)is bool,'linear_stage_explicit_boolean_opt_in_required')
    if not enabled:return {}
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,
        'bounded_linear_stage_Source_context_required')
    deadline=time.monotonic()+timeout_s
    _need(type(board_hint)is str and board_hint and type(poses)is dict and 1<=len(poses)<=8
        and all(type(ref)is str and type(p)in(list,tuple)and len(p)==3
        and all(type(v)in(int,float)and math.isfinite(v)for v in p)for ref,p in poses.items()),
        'finite_linear_stage_pose_required')
    shunt._reference_group_scope(reference_group_uuids)
    active=_observations.get();context=active
    if active is not None:
        _observation_live(active)
        deadline=min(deadline,active['deadline'])
    if context is not None:
        try:key=_observation_key(board,poses,board_hint,reference_group_uuids,enabled)
        except (TypeError,ValueError):key=None
        if key!=context['key']:context=None
    if context is not None:
        if context['result'] is not None:
            result=copy.deepcopy(context['result'])
            _need(time.monotonic()<deadline,'linear_stage_observation_deadline')
            return result
    timeout_s=deadline-time.monotonic()
    _need(timeout_s>0,'linear_stage_observation_deadline')
    result=_collect(board,poses,board_hint=board_hint,reference_group_uuids=reference_group_uuids,
        enabled=enabled,timeout_s=timeout_s)
    if context is not None and result:
        hierarchy={};evidence={};roots=set()
        for item in result.values():
            proof=item['source_proof'];roots.add(proof['root_schematic'])
            for name,digest in proof['schematic_files_sha256'].items():
                _need(name not in hierarchy or hierarchy[name]==digest,'linear_stage_observation_hierarchy_conflict')
                hierarchy[name]=digest
            evidence.update(proof['evidence_files_sha256'])
            exporter=proof['exporter'];evidence[exporter['exporter']]=exporter['exporter_sha256']
        _need(len(roots)==1,'linear_stage_observation_unique_root_required')
        context.update(result=copy.deepcopy(result),hierarchy=hierarchy,evidence=evidence,
            root=Path(next(iter(roots))).resolve())
        _observation_live(context)
    _need(time.monotonic()<deadline,'linear_stage_observation_deadline')
    return result


def _virtual_power_peer(ref, number, net, comps, instances, node_net, export_pins, deadline):
    """Prove one actual nonphysical global power symbol, not a ref exemption.

    Fresh Source export can contain power labels whose ref no longer starts
    with '#'. Their absence from the PCB is deliberate only when the full
    embedded symbol, instance, selected fields, export and pin agree. No
    physical component, missing footprint or arbitrary excluded part fits.
    """
    _need(time.monotonic() < deadline, 'linear_stage_Source_deadline')
    entries=instances.get(ref,[]);component=comps.get(ref)
    _need(number=='1' and len(entries)==1 and component is not None
          and node_net.get((ref,number))==net, 'complete_nonphysical_power_Source_instance_required')
    path,sheet,symbol,instance=entries[0];lib_id=symbol.get('lib_id','')
    _need(':'in lib_id, 'positive_global_power_symbol_library_required')
    library,part=lib_id.split(':',1)
    _need(library in ('power','cec-power') and part and part!='GND',
          'positive_global_power_symbol_library_required')
    selected=synth._first(component,'libsource')
    _need(synth._val(selected,'lib','')==library and synth._val(selected,'part','')==part
          and synth._val(component,'value','')==part and not synth._val(component,'footprint','')
          and synth._val(component,'tstamps','')==symbol['uuid'],
          'nonphysical_power_Source_export_identity_required')
    props={synth._val(p,'name',''):synth._val(p,'value','')for p in synth._kids(component,'property')}
    blocks=[b for tag,b in sheet.children if tag=='symbol'and canonical.sch.prop_value(b,'Reference')==ref]
    libraries=[b for tag,b in sheet.children if tag=='lib_symbols']
    _need(len(blocks)==len(libraries)==1 and canonical.sch.prop_value(blocks[0],'Value')==part
          and all(not props.get(k)and not canonical.sch.prop_value(blocks[0],k)
                  for k in ('Footprint','MPN','Manufacturer','LCSC')),
          'no_physical_selected_part_may_alias_a_power_symbol')
    exported_sheet=synth._first(component,'sheetpath')
    _need(not instance or synth._val(exported_sheet,'tstamps','')=='/'+'/'.join(instance)+'/',
          'nonphysical_power_exact_sheet_instance_required')
    tree=synth.parse_sexpr(libraries[0])
    declarations=[s for s in synth._kids(tree,'symbol')if len(s)>1 and s[1]==lib_id]
    _need(1<=len(declarations)<=64 and all(s==declarations[0]for s in declarations)
          and synth._first(declarations[0],'extends')is None,
          'complete_unambiguous_embedded_power_symbol_required')
    marker=synth._first(declarations[0],'power')
    _need(marker is not None and (len(marker)==1 or len(marker)==2 and marker[1]=='global'),
          'actual_global_power_symbol_marker_required')
    pending=[declarations[0]];pins=[];visited=0
    while pending:
        _need(time.monotonic()<deadline, 'linear_stage_Source_deadline')
        entry=pending.pop();visited+=1
        _need(visited<=4096, 'bounded_nonphysical_power_symbol_required')
        if isinstance(entry,list)and entry:
            if entry[0]=='pin':pins.append(entry)
            pending.extend(n for n in entry if isinstance(n,list))
    _need(len(pins)==len(symbol['pins'])==1 and synth._val(pins[0],'number','')=='1'
          and pins[0][1]==('power_out'if part=='PWR_FLAG'else'power_in')
          and synth._val(pins[0],'name','')in (part,'~'),
          'exact_single_nonphysical_power_pin_required')
    pin=canonical._pin((None,path,sheet,symbol),'1');exported=export_pins.get((ref,'1'),{})
    name=synth._val(pins[0],'name','')
    _need(pin['num']=='1' and pin['type']==pins[0][1] and exported.get('type')==pins[0][1]
          and exported.get('name')in (name,name+'_1'), 'literal_nonphysical_power_pin_parity_required')
    return dict(reference=ref,pin='1',net=net,lib_id=lib_id,source_symbol_uuid=symbol['uuid'],
        schematic=str(path),literal_source_type=pin['type'],nonphysical_global_power_symbol=True,
        physical_footprint_absent=True,current_authority=False,routing_authority=False,release_authority=False)


def _collect(board, poses, *, board_hint, reference_group_uuids=(), enabled=False, timeout_s=10.):
    """Return freshly observed moving stages; disabled is an unconditional no-op.

Only the explicit reviewed manufacturer table below is supported. A different
catalogued regulator is not silently aliased to that table. Enclosing native
constructors/receivers still own every cut, pose, return and saved final gate.
"""
    _need(type(enabled) is bool, 'linear_stage_explicit_boolean_opt_in_required')
    if not enabled:
        return {}
    _need(type(poses) is dict and 1 <= len(poses) <= 8
          and type(board_hint) is str and bool(board_hint)
          and type(timeout_s) in (int, float) and math.isfinite(timeout_s)
          and 0 < timeout_s <= 10., 'bounded_linear_stage_Source_context_required')
    deadline = time.monotonic()+timeout_s

    def tick():
        _need(time.monotonic() < deadline, 'linear_stage_Source_deadline')

    shunt._reference_group_scope(reference_group_uuids)
    candidates = []
    for ref, target in sorted(poses.items()):
        tick()
        _need(type(ref) is str and type(target) in (tuple, list) and len(target) == 3
              and all(type(v) in (int, float) and math.isfinite(v) for v in target)
              and all(abs(v) <= 2000 for v in target[:2]), 'finite_linear_stage_pose_required')
        matches = [fp for fp in board.GetFootprints() if fp.GetReference() == ref]
        _need(len(matches) == 1, 'actual_unique_linear_stage_pose_owner_required')
        fp = matches[0]
        if (tuple(fp.GetPosition()) == tuple(round(v*1e6) for v in target[:2])
                and abs((fp.GetOrientationDegrees()-target[2]+180) % 360-180) < 1e-9):
            continue
        model = roles.footprint_contract(fp)
        if model is None:
            continue  # Not a positive role. The enclosing compiler must classify it.
        kinds = set(model['pins'].values())
        if not kinds & {'power_output', 'switch', 'feedback'}:
            continue
        _need(not kinds & {'switch', 'feedback'} and {'power_input', 'power_output'} <= kinds,
              'switching_or_incomplete_stage_is_not_linear_Source_scope')
        _need((target[2]-fp.GetOrientationDegrees()) % 90 == 0
              and not fp.IsLocked() and not fp.IsDNP(), 'unlocked_cardinal_linear_stage_required')
        _need(model['device_package'] == 'TPS2121 RUX'
              and manufacturer.manufacturer_contract(fp) is not None,
              'reviewed_complete_linear_stage_manufacturer_table_required')
        roles.physical_pinmap(fp, model, board_hint=board_hint,
                             timeout_s=min(8., max(.001, deadline-time.monotonic())))
        candidates.append((fp, list(target), model))
    _need(len(candidates) <= 4 and sum(len(list(fp.Pads())) for fp, _, _ in candidates) <= 64,
          'bounded_four_stage_sixty_four_pin_Source_scope_required')
    if not candidates:
        return {}
    binding = row._source_binding(board)
    source = Path(board.GetFileName()).resolve(strict=True)
    _need(source.suffix == '.kicad_pcb' and source.with_suffix('.kicad_pro').is_file()
          and row._source_binding(pcbnew.LoadBoard(str(source))) == binding,
          'literal_unchanged_saved_linear_stage_Source_required')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    authorized = shunt._reference_group_authorizations(board, poses, reference_group_uuids,
        binding=binding, deadline=deadline)
    root = canonical.source_nc._root(board, board_hint)
    _need(root is not None, 'canonical_linear_stage_Source_root_required')
    root = Path(root).resolve(strict=True)
    files, hashes, instances = canonical._hierarchy(root, deadline)
    tree, exporter = canonical._export(root, deadline)
    _need(Path(exporter.get('exporter', '')).is_file()
          and force._hash(Path(exporter['exporter'])) == exporter.get('exporter_sha256')
          and all(exporter.get(k) == v for k, v in semantic.metadata(tree).items()),
          'fresh_complete_linear_stage_semantic_export_required')
    comps, nets, node_net = canonical._tables(tree)
    export_pins = {(synth._val(n, 'ref', ''), synth._val(n, 'pin', '')):
        dict(name=synth._val(n, 'pinfunction', ''), type=synth._val(n, 'pintype', ''))
        for net in synth._kids(synth._first(tree, 'nets'), 'net') for n in synth._kids(net, 'node')}
    groups = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    result = {}
    for fp, target, model in candidates:
        tick(); ref = fp.GetReference(); uid = force._uid(fp)
        _need(uid not in groups or uid in authorized, 'linear_stage_closed_reference_map_required')
        _need(not fp.GetParentGroup() or uid in authorized, 'linear_stage_group_owner_not_authorized')
        identity = manufacturer._identity(board, fp, comps, instances, node_net, export_pins,
            deadline, owner=True, source_context=(root, files, hashes, binding))
        output_erc_types = {identity['pins'][number]['type'] for number, role in model['pins'].items()
                            if role == 'power_output'}
        _need(len(output_erc_types) == 1, 'consistent_literal_linear_stage_output_ERC_convention_required')
        power = {}
        for number, role in sorted(model['pins'].items()):
            if role not in ('power_input', 'power_output'):
                continue
            pad = fp.FindPadByNumber(number); pin = identity['pins'][number]
            _need(pin['type'] in REVIEWED_POWER_ERC_TYPES[model['device_package']][role]
                  and pad.GetNetCode() > 0 and pad.GetNetname() != 'GND',
                  'canonical_linear_stage_power_direction_required')
            net = str(pad.GetNetname())
            actual = {(f.GetReference(), p.GetNumber()) for f in board.GetFootprints()
                      for p in f.Pads() if p.GetNetname() == net}
            exported_members=nets.get(net,set())
            _need(actual<=exported_members and len(exported_members-actual)<=32,
                  'complete_linear_stage_power_net_membership_required')
            virtual=[_virtual_power_peer(ref,pin,net,comps,instances,node_net,export_pins,deadline)
                     for ref,pin in sorted(exported_members-actual)]
            if net not in power:
                tick(); kind, domain, contract = full._model(board, source, net, board_hint); tick()
                power[net] = dict(current_domain_kind=kind, current_domain=copy.deepcopy(domain),
                    current_contract=copy.deepcopy(contract), terminals=[],
                    native_logical_members=[list(p)for p in sorted(actual)],
                    canonical_logical_members=[list(p)for p in sorted(exported_members)],
                    nonphysical_Source_global_power_symbols=virtual)
            power[net]['terminals'].append(dict(number=number, role=role, pad_uuid=force._uid(pad),
                                               literal_source_erc_type=pin['type']))
        proof = semantic.replay_identity(dict(root_schematic=str(root),
            schematic_files_sha256=hashes, exporter=exporter,
            evidence_files_sha256={str(Path(__file__).resolve().parents[1]/manufacturer.PDF):
                                   manufacturer.PDF_SHA256}))
        _need(force._hash(Path(__file__).resolve().parents[1]/manufacturer.PDF)
              == manufacturer.PDF_SHA256, 'linear_stage_manufacturer_source_changed')
        result[ref] = dict(role=ROLE, owner=ref, owner_uuid=uid, source=str(source),
            board_hint=board_hint, source_native_binding=binding, source_family=family,
            code_identity=epoch, source_pose=[fp.GetPosition().x/1e6, fp.GetPosition().y/1e6,
                                            fp.GetOrientationDegrees()], target_pose=target,
            manufacturer=copy.deepcopy(model), source_component=identity, source_proof=proof,
            literal_source_output_erc_type=next(iter(output_erc_types)),
            physical_power_direction_from_complete_manufacturer_table_not_erc_type=True,
            source_power_nets=power, source_reference_group_transport=authorized.get(uid),
            current_authority=False, source_trace_retirement_authority=False,
            new_barrel_authority=False, routing_admitted=False, placement_admitted=False,
            release_authority=False)
    tick()
    _need(binding == row._source_binding(board)
          and binding == row._source_binding(pcbnew.LoadBoard(str(source)))
          and epoch == force._code_identity() and family == force._family(source, board_hint)
          and all(force._hash(Path(name)) == digest for name, digest in hashes.items()),
          'linear_stage_live_Source_identity_changed')
    tick()
    return result

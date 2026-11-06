"""Fresh source intent for positively typed external Ground attachment leaves.

An optional reserved land and an enable/reset shunt are not decoupling
returns, package current paths or bypass owners. Manufacturer function plus
an independently exported CURRENT hierarchy must agree with exact native
parts/pins/nets. A receiver calls plan again on its parent; no producer role
boolean or stored/committed netlist can grant this permission.
Selected functional module Ground pins are independently source-bound too;
they remain separate from optional metal, bypass owners and current budgets.
"""
import copy
import contextvars
from contextlib import contextmanager
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_device_bypass as bypass
import cec_device_power_roles as roles
import cec_force_current as force
import cec_sch_lint as sch
import cec_source_no_connect as source_nc
import cec_synth_pipeline as synth
from cec_footprint_fields import footprint_properties
from cec_native_items import _native_pointer


_export_observations=contextvars.ContextVar('immutable_Source_canonical_export_observation',default=None)


def _export_inputs(root,files):
    """Literal CLI project/library inputs, including their prior absence."""
    paths={root.with_suffix('.kicad_pro')}
    for path in files:
        paths.update(path.parent/name for name in('sym-lib-table','fp-lib-table'))
    return {str(p):force._hash(p)if p.is_file()else None for p in paths}


def _export_observation_live(context,deadline):
    deadline=min(deadline,context['deadline']);_tick(deadline)
    board=context['board'];source=context['source']
    if (_native_pointer(board)!=context['pointer']
            or Path(board.GetFileName()).resolve()!=source
            or row._source_binding(board)!=context['binding']
            or force._family(source,context['hint'])!=context['family']
            or force._code_identity()!=context['epoch']
            or dict(os.environ)!=context['environment']):
        raise ValueError('immutable_canonical_export_Source_changed')
    root=source_nc._root(board,context['hint'])
    if root is None or Path(root).resolve()!=context['root']:
        raise ValueError('immutable_canonical_export_root_changed')
    files,hashes,_=_hierarchy(context['root'],deadline)
    if (set(map(str,files))!=set(context['hierarchy'])or hashes!=context['hierarchy']
            or _export_inputs(context['root'],files)!=context['inputs']):
        raise ValueError('immutable_canonical_export_hierarchy_or_inputs_changed')
    import cec_toolchain as tc
    cli=Path(tc.require_kicad_cli('immutable Source export observation')).resolve()
    if cli!=context['exporter']or force._hash(cli)!=context['exporter_sha256']:
        raise ValueError('immutable_canonical_export_exporter_changed')
    _tick(deadline)


@contextmanager
def observation_scope(board,*,board_hint,timeout_s=10.):
    """ONE immutable Source invocation; no caller result or persisted cache.

    Only the successful CLI tree is shared. Every consumer still parses the
    current hierarchy and independently proves its own native/source role.
    Nested scopes are independent; receiving opens a new scope of its own.
    """
    if(type(board_hint)is not str or not board_hint or type(timeout_s)not in(int,float)
            or not math.isfinite(timeout_s)or not 0<timeout_s<=10.):
        raise ValueError('bounded_canonical_export_observation_required')
    deadline=time.monotonic()+timeout_s
    source=Path(board.GetFileName()).resolve(strict=True)
    root=source_nc._root(board,board_hint)
    if root is None:raise ValueError('canonical_export_observation_root_required')
    root=Path(root).resolve(strict=True);files,hashes,_=_hierarchy(root,deadline)
    import cec_toolchain as tc
    cli=Path(tc.require_kicad_cli('Source export observation')).resolve()
    context=dict(board=board,pointer=_native_pointer(board),source=source,root=root,
        hint=board_hint,deadline=deadline,binding=row._source_binding(board),
        family=force._family(source,board_hint),epoch=force._code_identity(),
        environment=dict(os.environ),hierarchy=hashes,inputs=_export_inputs(root,files),
        exporter=cli,exporter_sha256=force._hash(cli),result=None)
    token=_export_observations.set(context)
    try:
        _export_observation_live(context,deadline)
        yield
    finally:
        try:_export_observation_live(context,deadline)
        finally:_export_observations.reset(token)


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('source_ground_leaf_deadline')


def _ceramic(fp):
    pads=list(fp.Pads())
    return (not fp.IsDNP() and len(pads)==2 and len({p.GetNumber() for p in pads})==2
        and re.search(r'(?:^|:)C_(?:0201|0402|0603|0805|1206|1210)_\d+Metric(?:_|$)',fp.GetFPIDAsString())
        and bypass.capacitance_f(fp.GetValue()) is not None
        and bypass.capacitance_f(fp.GetValue())>0
        and all(not p.HasHole() and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD for p in pads))


def _candidates(board):
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(pads)>16384:raise ValueError('source_ground_leaf_inventory_bound')
    candidates={};controls={}
    for fp in board.GetFootprints():
        for control_pin in ('45','23','8'):
            witness=roles.control_shunt_input_contract(fp,control_pin)
            if witness:
                pad=fp.FindPadByNumber(control_pin)
                if pad.GetNetCode()>0 and pad.GetNetname()!='GND':
                    controls.setdefault(str(pad.GetNetname()),[]).append((pad,witness))
        for pad in fp.Pads():
            if pad.GetNetname()!='GND' or pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:continue
            proof=roles.optional_ground_attachment_contract(fp,pad.GetNumber())
            if proof:candidates[force._uid(pad)]=(pad,'explicit_manufacturer_optional_ground_metal',proof,None)
            else:
                proof=roles.functional_ground_attachment_contract(fp,pad.GetNumber())
                if proof:candidates[force._uid(pad)]=(pad,'source_manufacturer_functional_ground_pin',proof,None)
    for fp in board.GetFootprints():
        if not _ceramic(fp):continue
        ground=[p for p in fp.Pads() if p.GetNetname()=='GND']
        if len(ground)!=1:continue
        other=next(p for p in fp.Pads() if force._uid(p)!=force._uid(ground[0]))
        selected=controls.get(str(other.GetNetname()),[])
        if len(selected)!=1:continue
        control,witness=selected[0]
        candidates[force._uid(ground[0])]=(ground[0],'source_control_shunt_ground',witness,control)
    if len(candidates)>64:raise ValueError('source_ground_leaf_candidate_bound')
    return candidates


def complete_ground_membership(board, exported_members, comps, instances, *, board_hint, deadline):
    """Canonical Ground plus positively received, unchanged PCB-only metal.

    This reconciles logical membership, not current/placement/cut permission.
    No reference-name exemptions, arbitrary extra Ground pads or missing
    physical schematic lands. Reused by local Source power-cell compilers.
    """
    import cec_source_mount_stitch_reconcile as mounts
    _tick(deadline)
    native = {(f.GetReference(), p.GetNumber()) for f in board.GetFootprints()
              for p in f.Pads() if p.GetNetname() == 'GND'}
    virtual = []
    for peer in sorted(exported_members-native):
        proof = _virtual_ground_peer(*peer, comps, instances, deadline)
        if proof is None:
            raise ValueError('physical_Source_Ground_peer_must_have_its_actual_native_land')
        virtual.append(proof)
    extras = native-exported_members; mechanical = None
    if extras:
        refs = {ref for ref, _ in extras}
        owners = [f for f in board.GetFootprints() if f.GetReference() in refs]
        excluded = pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES
        if (len(owners) != len(refs) or not all(
                all(p.GetNetname() == 'GND' for p in f.Pads())
                and f.GetAttributes() & excluded == excluded
                and str(f.GetFPIDAsString()).split(':')[-1].startswith('MountingHole_')
                for f in owners)):
            raise ValueError('PCB_only_mechanical_Ground_owner_must_be_complete')
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise ValueError('source_ground_membership_deadline')
        mechanical = mounts.plan(board.GetFileName(), board_hint=board_hint,
            mount_uuids=sorted(force._uid(f) for f in owners), timeout_s=min(10., remaining))
        if not mechanical['complete'] or mechanical['changed_pad_count']:
            raise ValueError('PCB_only_Ground_mounts_must_already_match_actual_Source_library')
        if {(f.GetReference(), p.GetNumber()) for f in owners for p in f.Pads()} != extras:
            raise ValueError('complete_PCB_only_mechanical_Ground_inventory_required')
    _tick(deadline)
    return dict(native_logical_members=sorted(native), canonical_logical_members=sorted(exported_members),
        nonphysical_canonical_Ground_symbols=virtual,
        unchanged_PCB_only_canonical_Ground_mounts=mechanical)


def _hierarchy(root,deadline):
    queue=[(root,())];files={};hashes={};instances={};total=0
    while queue:
        _tick(deadline);path,instance=queue.pop(0)
        if path in files:raise ValueError('source_ground_leaf_repeated_or_cyclic_sheet')
        if not path.is_file():raise ValueError('source_ground_leaf_missing_sheet')
        size=path.stat().st_size;total+=size
        if len(files)>=64 or size>4*1024*1024 or total>16*1024*1024:
            raise ValueError('source_ground_leaf_hierarchy_bound')
        hashes[str(path)]=force._hash(path);sf=sch.SchFile(str(path));files[path]=sf
        for symbol in sf.symbols:
            instances.setdefault(symbol['ref'],[]).append((path,sf,symbol,instance))
        for tag,block in sf.children:
            if tag!='sheet':continue
            name=sch.prop_value(block,'Sheetfile');uid=sch.find_uuid(block)
            if not name or not uid:raise ValueError('source_ground_leaf_exact_sheet_identity_required')
            queue.append(((path.parent/name).resolve(),instance+(uid,)))
    return files,hashes,instances


def _export(root,deadline):
    """Fresh CLI by default; private immutable-invocation observation only."""
    context=_export_observations.get()
    if context is None:return _export_fresh(root,deadline)
    _export_observation_live(context,deadline)
    if Path(root).resolve()!=context['root']:
        raise ValueError('canonical_export_observation_requested_root_mismatch')
    if context['result']is None:
        result=_export_fresh(root,min(deadline,context['deadline']))
        _export_observation_live(context,deadline)
        context['result']=copy.deepcopy(result)
    else:result=copy.deepcopy(context['result'])
    _tick(min(deadline,context['deadline']))
    return result


def _export_fresh(root,deadline):
    """Fresh bounded CLI, never a stale-file fallback."""
    import cec_toolchain as tc
    _tick(deadline);cli=Path(tc.require_kicad_cli('source Ground leaf export')).resolve()
    digest=force._hash(cli)
    with tempfile.TemporaryDirectory(prefix='cec-ground-source-') as work:
        out=Path(work)/'fresh.net'
        process=subprocess.run([str(cli),'sch','export','netlist','-o',str(out),str(root)],
            capture_output=True,text=True,timeout=min(10.,max(.001,deadline-time.monotonic())))
        if process.returncode or not out.is_file() or not 0<out.stat().st_size<=16*1024*1024:
            raise ValueError('source_ground_leaf_fresh_export_refused')
        tree=synth.parse_sexpr(out.read_text());digest_net=force._hash(out)
    if Path(synth._val(synth._first(tree,'design'),'source','')).resolve()!=root:
        raise ValueError('source_ground_leaf_export_wrong_root')
    if force._hash(cli)!=digest:raise ValueError('source_ground_leaf_exporter_epoch_changed')
    _tick(deadline)
    import cec_source_netlist_semantics as semantic
    return tree,dict(netlist_sha256=digest_net,exporter=str(cli),exporter_sha256=digest,
        **semantic.metadata(tree))


def _tables(tree):
    comps={};nets={};node_net={}
    for comp in synth._kids(synth._first(tree,'components')or[],'comp'):
        ref=synth._val(comp,'ref','')
        if not ref or ref in comps:raise ValueError('source_ground_leaf_export_duplicate_component')
        comps[ref]=comp
    for net in synth._kids(synth._first(tree,'nets')or[],'net'):
        name=synth._val(net,'name','')
        if not name or name in nets:raise ValueError('source_ground_leaf_export_duplicate_net')
        nodes=[]
        for node in synth._kids(net,'node'):
            key=(synth._val(node,'ref',''),synth._val(node,'pin',''))
            if not all(key) or key in node_net:raise ValueError('source_ground_leaf_export_duplicate_pin')
            node_net[key]=name;nodes.append(key)
        nets[name]=set(nodes)
    return comps,nets,node_net


def _identity(board,ref,comps,instances,deadline):
    _tick(deadline);fps=[f for f in board.GetFootprints() if f.GetReference()==ref]
    entries=instances.get(ref,[]);comp=comps.get(ref)
    if len(fps)!=1 or len(entries)!=1 or comp is None:
        raise ValueError('source_ground_leaf_unique_instance_required:'+ref)
    fp=fps[0];path,sf,symbol,instance=entries[0]
    if fp.IsDNP():raise ValueError('source_ground_leaf_dnp_component')
    blocks=[b for tag,b in sf.children if tag=='symbol' and sch.prop_value(b,'Reference')==ref]
    if len(blocks)!=1 or not symbol['uuid'] or '(mirror ' in blocks[0] or symbol['pos'][2]%90:
        raise ValueError('source_ground_leaf_exact_symbol_transform_required')
    block=blocks[0];props=footprint_properties(fp)
    if any(tag=='dnp' and re.fullmatch(r'\(dnp\s+yes\s*\)',child.strip())
            for tag,child in sch.iter_children(block)):
        raise ValueError('source_ground_leaf_source_dnp_component')
    exported={synth._val(p,'name',''):synth._val(p,'value','') for p in synth._kids(comp,'property')}
    for key,actual,compiled in [('Value',fp.GetValue(),synth._val(comp,'value','')),
            ('Footprint',fp.GetFPIDAsString(),synth._val(comp,'footprint','')),
            ('MPN',props.get('MPN'),exported.get('MPN'))]:
        if not actual or sch.prop_value(block,key)!=actual or compiled!=actual:
            raise ValueError('source_ground_leaf_component_identity_mismatch:'+ref+':'+key)
    if synth._val(comp,'tstamps','')!=symbol['uuid']:
        raise ValueError('source_ground_leaf_symbol_uuid_mismatch')
    sheet=synth._first(comp,'sheetpath')
    if instance and synth._val(sheet,'tstamps','')!='/'+'/'.join(instance)+'/':
        raise ValueError('source_ground_leaf_sheet_instance_mismatch')
    native=fp.GetPath().AsString()
    if native and (native.rstrip('/').split('/')[-1]!=symbol['uuid']
            or instance and '/'+('/'.join(instance))+'/' not in native):
        raise ValueError('source_ground_leaf_native_instance_mismatch')
    return fp,path,sf,symbol


def _pin(identity,pin):
    fp,path,sf,symbol=identity
    matches=[p for p in symbol['pins'] if p['num']==pin]
    if len(matches)!=1:raise ValueError('source_ground_leaf_exact_source_pin_required')
    at=source_nc._nm(matches[0]['pos'])
    if any(source_nc._nm(p['pos'])==at for p in sf.no_connects):
        raise ValueError('source_ground_leaf_conflicting_no_connect_marker')
    return matches[0]


def _c6_control_source_pin(identity,pin):
    """Fresh actual C6 EN8/IO9; net spelling is never pin authority."""
    fp,path,sf,symbol=identity
    witness=roles.control_shunt_input_contract(fp,pin)
    if not witness or witness.get('device_package')!='ESP32-C6-MINI-1':
        raise ValueError('source_boot_strap_exact_manufacturer_package_required')
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    if len(libraries)!=1:raise ValueError('source_boot_strap_symbol_library_required')
    tree=synth.parse_sexpr(libraries[0]);selected=[n for n in synth._kids(tree,'symbol')
        if len(n)>1 and n[1]==symbol['lib_id']]
    if len(selected)!=1 or synth._first(selected[0],'extends')is not None:
        raise ValueError('source_boot_strap_unique_complete_symbol_required')
    nodes=[selected[0]];pins=[];count=0
    while nodes:
        node=nodes.pop();count+=1
        if count>8192:raise ValueError('source_boot_strap_symbol_bound')
        if isinstance(node,list)and node:
            if node[0]=='pin':pins.append(node)
            nodes.extend(n for n in node if isinstance(n,list))
    if len(pins)!=53 or {synth._val(p,'number','')for p in pins}!={str(i)for i in range(1,54)}:
        raise ValueError('source_boot_strap_complete_physical_pin_map_required')
    actual=next(p for p in pins if synth._val(p,'number','')==pin)
    if (actual[1]!=witness['source_pin_type'] or synth._val(actual,'name','')!=witness['function']
            or _pin(identity,pin)['type']!=witness['source_pin_type']):
        raise ValueError('source_c6_control_actual_named_manufacturer_pin_required')


def _functional_ground_source_pin(identity, pin, cache):
    """Read the actual selected embedded symbol; lint pins omit pin names."""
    fp,path,sf,symbol=identity
    key=(str(path),symbol.get('lib_id'))
    if key not in cache:
        blocks=[child for tag,child in sf.children if tag=='lib_symbols']
        if len(blocks)!=1:raise ValueError('source_functional_ground_symbol_library_required')
        tree=synth.parse_sexpr(blocks[0])
        selected=[s for s in synth._kids(tree,'symbol') if len(s)>1 and s[1]==symbol.get('lib_id')]
        if len(selected)!=1:raise ValueError('source_functional_ground_selected_symbol_required')
        nodes=[selected[0]];pins=[];visited=0
        while nodes:
            node=nodes.pop();visited+=1
            if visited>8192:raise ValueError('source_functional_ground_symbol_inventory_bound')
            if isinstance(node,list) and node:
                if node[0]=='pin':pins.append(node)
                nodes.extend(child for child in node if isinstance(child,list))
        numbers=[synth._val(p,'number','') for p in pins]
        contract=roles.functional_ground_attachment_contract(fp,pin)
        count=10 if contract and contract.get('device_package')=='INA238 DGS' else 53
        if len(numbers)!=count or set(numbers)!={str(n)for n in range(1,count+1)}:
            raise ValueError('source_functional_ground_complete_pin_inventory_required')
        cache[key]=pins
    pins=cache[key]
    actual=[p for p in pins if synth._val(p,'number','')==pin]
    if (len(actual)!=1 or len(actual[0])<2 or actual[0][1]!='power_in'
            or synth._val(actual[0],'name','')!='GND'):
        raise ValueError('source_functional_ground_actual_ground_pin_required')


def _virtual_ground_peer(ref, pin, comps, instances, deadline):
    """Positive canonical power-symbol type, never a reference-name waiver."""
    _tick(deadline)
    entries=instances.get(ref,[]);comp=comps.get(ref)
    if len(entries)!=1 or comp is None or pin!='1':return None
    path,sf,symbol,instance=entries[0]
    lib_id=symbol.get('lib_id','')
    if lib_id not in ('power:GND','cec-power:GND','power:PWR_FLAG','cec-power:PWR_FLAG'):return None
    library,part=lib_id.split(':',1)
    libsource=synth._first(comp,'libsource')
    if (synth._val(libsource,'lib','')!=library or synth._val(libsource,'part','')!=part
            or synth._val(comp,'value','')!=part
            or synth._val(comp,'footprint','')
            or synth._val(comp,'tstamps','')!=symbol['uuid']):return None
    props={synth._val(p,'name',''):synth._val(p,'value','')for p in synth._kids(comp,'property')}
    if props.get('MPN'):return None
    sheet=synth._first(comp,'sheetpath')
    if instance and synth._val(sheet,'tstamps','')!='/'+'/'.join(instance)+'/':return None
    blocks=[b for tag,b in sf.children if tag=='symbol'and sch.prop_value(b,'Reference')==ref]
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    if (len(blocks)!=1 or len(libraries)!=1 or sch.prop_value(blocks[0],'Value')!=part
            or sch.prop_value(blocks[0],'Footprint') or sch.prop_value(blocks[0],'MPN')):return None
    tree=synth.parse_sexpr(libraries[0])
    selected=[s for s in synth._kids(tree,'symbol')if len(s)>1 and s[1]==lib_id]
    # Repeated identical embedded declarations are canonical aliases, not choices.
    # Compare complete parsed trees: conflicting geometry, pins or power types refuse.
    if not selected or len(selected)>64 or any(s!=selected[0]for s in selected[1:]):return None
    marker=synth._first(selected[0],'power')
    if marker is None or len(marker)>2 or len(marker)==2 and marker[1]!='global':return None
    nodes=[selected[0]];pins=[];visited=0
    while nodes:
        node=nodes.pop();visited+=1
        if visited>1024:return None
        if isinstance(node,list)and node:
            if node[0]=='pin':pins.append(node)
            nodes.extend(c for c in node if isinstance(c,list))
    if (len(pins)!=1 or synth._val(pins[0],'number','')!='1'
            or pins[0][1]!=('power_in'if part=='GND'else'power_out')
            or part=='GND'and synth._val(pins[0],'name','')not in ('GND','~')):return None
    source_pin=_pin((None,path,sf,symbol),pin)
    if source_pin['type']!=pins[0][1]:return None
    return dict(ref=ref,pin=pin,lib_id=lib_id,source_symbol_uuid=symbol['uuid'],
        source_schematic=str(path),nonphysical_power_symbol=True,
        physical_footprint_absent=True,mpn_absent=True,release_authority=False)


def bindings_current(proofs):
    """Recheck bindings on independently RECOMPILED receiver proofs only."""
    if type(proofs)is not list or len(proofs)>64:raise ValueError('bounded_ground_leaf_proofs_required')
    for proof in proofs:
        if proof.get('kind')not in ('explicit_manufacturer_optional_ground_metal','source_control_shunt_ground',
                'source_manufacturer_functional_ground_pin'):
            raise ValueError('typed_source_ground_leaf_proof_required')
        files=proof.get('schematic_files_sha256',{})
        exporter=proof.get('exporter',{})
        if (type(files)is not dict or not 1<=len(files)<=64
                or any(force._hash(Path(p))!=digest for p,digest in files.items())
                or force._hash(Path(exporter.get('exporter','')))!=exporter.get('exporter_sha256')):
            return False
    return True


def _plan(board,*,board_hint,timeout_s=10.,return_export=False):
    if (type(board_hint)is not str or not board_hint or type(timeout_s)not in(int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_source_ground_leaf_context_required')
    deadline=time.monotonic()+timeout_s;binding=row._source_binding(board)
    result=dict(scope='source_typed_external_ground_leaves',complete=False,proofs={},errors=[],
        refused={},current_authority=False,release_authority=False)
    fresh_export=None
    try:
        candidates=_candidates(board)
        if not candidates:
            result['complete']=True
            return (result,None)if return_export else result
        root=source_nc._root(board,board_hint)
        if root is None:raise ValueError('source_ground_leaf_current_root_required')
        root=root.resolve();files,hashes,instances=_hierarchy(root,deadline)
        tree,exporter=_export(root,deadline);comps,nets,node_net=_tables(tree);identities={}
        fresh_export=(str(root),tree,exporter)
        functional_pin_libraries={}
        def identity(ref):
            if ref not in identities:identities[ref]=_identity(board,ref,comps,instances,deadline)
            return identities[ref]
        native_nodes={}
        for fp in board.GetFootprints():
            for pad in fp.Pads():native_nodes.setdefault((fp.GetReference(),pad.GetNumber()),[]).append(pad)
        # Ground names alone are not intent: every source Ground peer must
        # have the declared native membership. Additional PCB-only mounting
        # metal is not an electrical symbol and is checked by final parity.
        result['nonphysical_ground_peers']=[]
        for peer in sorted(nets.get('GND',set())):
            _tick(deadline)
            if not native_nodes.get(peer) or any(p.GetNetname()!='GND' for p in native_nodes[peer]):
                # Existing exact-component parity excludes canonical power
                # symbols regardless of legacy in_bom/on_board booleans.
                # Re-prove the actual embedded symbol type/UUID here; never
                # exempt an unknown physical component named PWR/GND.
                if not native_nodes.get(peer):
                    virtual=_virtual_ground_peer(*peer,comps,instances,deadline)
                    if virtual is not None:
                        result['nonphysical_ground_peers'].append(virtual)
                        continue
                raise ValueError('source_ground_leaf_export_ground_peer_mismatch')
        for uid,(pad,kind,witness,control) in candidates.items():
            try:
                _tick(deadline);owner=identity(pad.GetParentFootprint().GetReference());pin=pad.GetNumber()
                source_pin=_pin(owner,pin)
                if kind=='source_manufacturer_functional_ground_pin':
                    if source_pin['type']!='power_in':
                        raise ValueError('source_functional_ground_actual_ground_pin_required')
                    _functional_ground_source_pin(owner,pin,functional_pin_libraries)
                if node_net.get((owner[0].GetReference(),pin))!='GND':
                    raise ValueError('source_ground_leaf_actual_source_ground_required')
                selected=[]
                if control is not None:
                    module=identity(control.GetParentFootprint().GetReference())
                    control_pin=_pin(module,control.GetNumber())
                    boot=witness.get('role')=='boot_mode_strap_input'
                    c6_topology=boot or witness.get('requires_complete_pullup_button_topology')is True
                    if c6_topology:
                        _c6_control_source_pin(module,control.GetNumber())
                        if source_pin['type']!='passive':raise ValueError('source_boot_strap_cap_ground_passive_required')
                        if node_net.get((module[0].GetReference(),'3'))!=module[0].FindPadByNumber('3').GetNetname():
                            raise ValueError('source_boot_strap_actual_source_power_pin_required')
                    elif control_pin['type']!='input':raise ValueError('source_ground_leaf_actual_enable_input_required')
                    net=str(control.GetNetname());expected=nets.get(net,set())
                    actual={key for key,ps in native_nodes.items() if any(p.GetNetname()==net for p in ps)}
                    if not expected or expected!=actual or any(any(p.GetNetname()!=net for p in native_nodes[k])for k in actual):
                        raise ValueError('source_ground_leaf_control_peer_membership_mismatch')
                    if net=='GND' or node_net.get((module[0].GetReference(),control.GetNumber()))!=net:
                        raise ValueError('source_ground_leaf_actual_source_control_required')
                    passive_counts={'R':0,'SW_Push':0}
                    for ref,num in sorted(expected):
                        peer=identity(ref);source_pin=_pin(peer,num)
                        if force._uid(peer[0])==force._uid(module[0]):
                            if num!=control.GetNumber():raise ValueError('source_ground_leaf_other_active_control_pin')
                        elif force._uid(peer[0])==force._uid(owner[0]):
                            if source_pin['type']!='passive':raise ValueError('source_ground_leaf_cap_passive_pin_required')
                        else:
                            part=synth._val(synth._first(comps[ref],'libsource'),'part','')
                            if part not in ('R','R_Small','SW_Push') or source_pin['type']!='passive':
                                raise ValueError('source_ground_leaf_unrecognized_control_peer')
                            passive_counts['R'if part in('R','R_Small')else part]+=1
                            peers=[p for p in peer[3]['pins'] if p['num']!=num]
                            if len(peers)!=1:raise ValueError('source_ground_leaf_two_terminal_control_peer_required')
                            other_net=node_net.get((ref,peers[0]['num']))
                            allowed={'GND'} if part=='SW_Push' else {node_net.get((module[0].GetReference(),'3'))}
                            if not other_net or other_net not in allowed or other_net==net:
                                raise ValueError('source_ground_leaf_control_peer_other_end_refused')
                            other_pin=_pin(peer,peers[0]['num'])
                            if c6_topology and other_pin['type']!='passive':raise ValueError('source_boot_strap_peer_passive_both_ends_required')
                            if c6_topology:
                                actual_other=native_nodes.get((ref,peers[0]['num']),[])
                                if (len(actual_other)!=1 or actual_other[0].GetNetname()!=other_net
                                        or len(list(peer[0].Pads()))!=2
                                        or any(p.HasHole()or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in peer[0].Pads())):
                                    raise ValueError('source_boot_strap_actual_two_terminal_peer_nets_required')
                        selected.append(dict(ref=ref,pin=num,symbol_uuid=peer[3]['uuid']))
                    if not any(p.GetNetname()==net for p in owner[0].Pads()):
                        raise ValueError('source_ground_leaf_cap_control_end_required')
                    if c6_topology and (len(expected)!=4 or passive_counts!={'R':1,'SW_Push':1}):
                        raise ValueError('source_boot_strap_exact_cap_pullup_button_module_topology_required')
                result['proofs'][uid]=dict(kind=kind,pad_uuid=uid,owner=owner[0].GetReference(),pin=pin,
                    source_symbol_uuid=owner[3]['uuid'],source_schematic=str(owner[1]),
                    root_schematic=str(root),schematic_files_sha256=hashes,exporter=exporter,
                    manufacturer=witness,control_peers=selected,net='GND',
                    functional_ground_return=witness.get('functional_ground_return') is True,
                    bypass_owner=False,current_authority=False,
                    reset_timing_qualified=False,release_authority=False)
            except ValueError as exc:result['refused'][uid]=str(exc)
        if hashes!={str(p):force._hash(p)for p in files}:
            raise ValueError('source_ground_leaf_schematic_epoch_changed')
        _tick(deadline);result['complete']=True
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc));result['proofs']={};fresh_export=None
    finally:
        if row._source_binding(board)!=binding:raise ValueError('source_ground_leaf_native_epoch_changed')
    return (result,fresh_export)if return_export else result


def plan(board,*,board_hint,timeout_s=10.):
    return _plan(board,board_hint=board_hint,timeout_s=timeout_s)


def plan_with_export(board,*,board_hint,timeout_s=10.):
    """Return the actual fresh export consumed by this one canonical plan.

    This is ephemeral in-process evidence, not a cache, caller-supplied
    netlist or permission to serialize a proof for future reuse. Every call,
    including independent saved receiving, performs its OWN bounded CLI
    export and complete Source/native checks. A consuming compiler still
    rechecks hierarchy hashes and the full semantic export identity.
    """
    return _plan(board,board_hint=board_hint,timeout_s=timeout_s,return_export=True)

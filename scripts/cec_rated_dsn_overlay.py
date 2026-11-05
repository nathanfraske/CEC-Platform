"""Staged no-cap current-width overlay; not topology/barrel/current qualification.

Only class memberships/widths change. No pin exclusion, layer remapping,
completed-net exception, current-budget change or caller capability assertion.
"""
import hashlib
import json
import math
import re
import time
from decimal import Decimal,ROUND_CEILING
from pathlib import Path


def validate_export_context(context):
    if context is None or type(context) is dict and not context:return None
    required={'source','expected_source_sha256','board_hint','requested_nets'}
    if type(context) is not dict or set(context) not in (required, required|{'construction_layers_by_net'}):
        raise ValueError('exact_explicit_rated_current_context_required')
    if (not isinstance(context['source'],str) or not context['source']
            or not isinstance(context['board_hint'],str) or not context['board_hint'].strip()
            or not isinstance(context['expected_source_sha256'],str)
            or not re.fullmatch('[0-9a-f]{64}',context['expected_source_sha256'])
            or type(context['requested_nets']) is not list
            or len(context['requested_nets'])>32768
            or any(not isinstance(n,str) or not n for n in context['requested_nets'])
            or len(context['requested_nets'])!=len(set(context['requested_nets']))):
        raise ValueError('named_source_epoch_and_requested_scope_required')
    if 'construction_layers_by_net' in context:
        import cec_rated_trace_scope as trace_scope
        context=dict(context,construction_layers_by_net=trace_scope.normalize(context['construction_layers_by_net']))
    source=Path(context['source']).resolve()
    if not source.is_file() or source.suffix!='.kicad_pcb':raise ValueError('saved_named_PCB_authority_required')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=context['expected_source_sha256']:
        raise ValueError('rated_export_source_epoch_mismatch')
    return dict(context,source=str(source),requested_nets=list(context['requested_nets']))


def preflight_export_context(export_board,dsn,context):
    """Run BEFORE native export and again in adapter; never write authority."""
    import os
    context=validate_export_context(context)
    if context is None:return context
    import cec_force_current as force
    source=Path(context['source']).resolve();target=Path(dsn).resolve()
    if target.suffix!='.dsn':raise ValueError('DSN_target_must_not_alias_non_DSN_authority')
    if target.is_relative_to(source.parent) and target.name.startswith(source.stem+'.'):
        raise ValueError('DSN_target_inside_authority_saved_family_namespace')
    companions,_=force._companion_inventory(source)
    for authority in (source,*companions.values()):
        if target==authority.resolve() or (target.exists() and authority.is_file() and os.path.samefile(target,authority)):
            raise ValueError('DSN_target_aliases_current_source_authority')
    return context


def apply_export_overlay(export_board,dsn,context):
    """Opt-in adapter for export_dsn; no global cache or PCB-looking sidecars."""
    import os
    import tempfile
    import uuid
    context=preflight_export_context(export_board,dsn,context)
    if context is None:return {'enabled':False}
    dsn=Path(dsn).resolve()
    if not dsn.is_file() or dsn.suffix!='.dsn':raise ValueError('fresh_native_export_DSN_required')
    original=dsn.read_bytes();before=hashlib.sha256(original).hexdigest()
    result,report=overlay_for_source(context['source'],dsn,
        board_hint=context['board_hint'],expected_source_sha256=context['expected_source_sha256'],
        expected_dsn_sha256=before,requested_nets=context['requested_nets'],
        construction_layers_by_net=context.get('construction_layers_by_net'))
    report.update(export_board=str(Path(export_board).resolve()),explicit_context=context,
        enabled=True,export_source_may_be_hint_copy=True,scope='rated_current_width_export_only_not_route_admission')
    payload=(json.dumps(report,sort_keys=True,indent=2,default=str)+'\n').encode()
    if len(payload)>8*1024**2:raise ValueError('bounded_rated_export_report_required')
    # Neither this directory nor its files occupy '<PCB stem>.*' next to a PCB.
    directory=dsn.parent/'rated-current-export-reports';directory.mkdir(exist_ok=True)
    report_path=directory/('export-'+uuid.uuid4().hex+'.json')
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(prefix='cec-rated-export-',suffix='.tmp',dir=dsn.parent,delete=False) as stream:
            temporary=Path(stream.name);stream.write(result.encode())
        with report_path.open('xb') as stream:stream.write(payload)
        if hashlib.sha256(dsn.read_bytes()).hexdigest()!=before:
            raise ValueError('native_export_DSN_changed_before_overlay_publication')
        os.replace(temporary,dsn);temporary=None
        return dict(enabled=True,report_path=str(report_path),input_sha256=before,
                    output_sha256=hashlib.sha256(dsn.read_bytes()).hexdigest())
    finally:
        if temporary is not None and temporary.is_file():temporary.unlink()

TOKEN=re.compile(r'\s+|[()]|"(?:\\.|[^"\\])*"|[^\s()"]+')


def parse(text,timeout_s=5.):
    if not isinstance(text,str) or len(text.encode())>64*1024**2:
        raise ValueError('bounded_native_DSN_required')
    scan=re.sub(r'(?m)^(\s*\(string_quote\s+)"(\s*\)\s*)$',r'\1Q\2',text)
    stack=[];roots=[];end=count=0;deadline=time.monotonic()+timeout_s
    for token in TOKEN.finditer(scan):
        if token.start()!=end or time.monotonic()>deadline:raise ValueError('DSN_lexical_deadline_or_gap')
        end=token.end();raw=token.group()
        if raw.isspace():continue
        count+=1
        if count>2_000_000:raise ValueError('DSN_token_bound')
        if raw=='(':
            if len(stack)>=128:raise ValueError('DSN_depth_bound')
            node=dict(start=token.start(),stop=None,atoms=[],children=[])
            if stack:stack[-1]['children'].append(node)
            else:roots.append(node)
            stack.append(node)
        elif raw==')':
            if not stack:raise ValueError('unbalanced_DSN')
            stack.pop()['stop']=token.end()
        else:
            if not stack:raise ValueError('DSN_atom_outside_root')
            value=json.loads(raw) if raw.startswith('"') else raw
            stack[-1]['atoms'].append((value,token.start(),token.end()))
    if end!=len(scan) or stack or len(roots)!=1:raise ValueError('native_single_DSN_root_required')
    return roots[0]


def head(n):return n['atoms'][0][0] if n['atoms'] else None


def one(n,name):
    rows=[x for x in n['children'] if head(x)==name]
    if len(rows)!=1:raise ValueError('unambiguous_DSN_'+name+'_required')
    return rows[0]


def network_inventory(text):
    network=one(parse(text),'network');nets={};seen=set()
    for node in network['children']:
        if head(node)!='net':continue
        if len(node['atoms'])!=2:raise ValueError('exact_DSN_net_identity_required')
        net=node['atoms'][1][0]
        if net in nets:raise ValueError('duplicate_DSN_network_net')
        pins=[a[0] for a in one(node,'pins')['atoms'][1:]]
        if len(pins)!=len(set(pins)) or seen & set(pins):raise ValueError('duplicate_DSN_network_pin')
        seen.update(pins);nets[net]=pins
    return nets


def verify_network_inventory(text,source_pin_nets):
    inventory=network_inventory(text)
    for net,pins in inventory.items():
        for pin in pins:
            if source_pin_nets.get(pin)!=net:raise ValueError('DSN_pin_not_exact_native_source_net:'+pin)
    return inventory


def overlay(text,requirements,layer_map,layer_indices=None,requested_nets=None,construction_layers_by_net=None):
    """Pure compiler; external callers must use overlay_for_source to bind inputs."""
    root=parse(text)
    if head(root)!='pcb':raise ValueError('native_DSN_pcb_required')
    unit=one(root,'unit')
    if [a[0] for a in unit['atoms']]!=['unit','um']:
        raise ValueError('native_um_DSN_unit_required')
    resolution=one(root,'resolution')['atoms']
    if len(resolution)!=3 or resolution[1][0]!='um':raise ValueError('native_DSN_resolution_required')
    scale=int(resolution[2][0])
    if scale<=0 or str(scale)!=resolution[2][0]:raise ValueError('positive_integer_DSN_resolution_required')
    structure=one(root,'structure');network=one(root,'network')
    inventory=network_inventory(text)
    active_nets={n for n,pins in inventory.items() if pins}
    if requested_nets is not None:
        if isinstance(requested_nets,(str,bytes)) or any(not isinstance(n,str) or not n for n in requested_nets):
            raise ValueError('explicit_requested_net_collection_required')
        requested=set(requested_nets)
    else:requested=set(active_nets)
    selected=set(requirements)&active_nets&requested
    layers={};active={}
    for layer in structure['children']:
        if head(layer)!='layer':continue
        if len(layer['atoms'])!=2:raise ValueError('invalid_DSN_layer')
        label=layer['atoms'][1][0]
        if label in layers or label not in layer_map:raise ValueError('DSN_layer_identity_not_bound')
        if layer_indices is not None:
            index=one(one(layer,'property'),'index')['atoms'][1][0]
            if int(index)!=layer_indices[label]:raise ValueError('DSN_layer_index_not_native_source')
        layers[label]=one(layer,'type')['atoms'][1][0]
    if set(layers)!=set(layer_map):raise ValueError('DSN_native_copper_layer_inventory_changed')
    for settings in structure['children']:
        if head(settings)!='autoroute_settings':continue
        for rule in settings['children']:
            if head(rule)!='layer_rule':continue
            label=rule['atoms'][1][0]
            if label not in layers or label in active:raise ValueError('ambiguous_DSN_layer_activity')
            active[label]=one(rule,'active')['atoms'][1][0]
            if active[label] not in ('on','off'):raise ValueError('invalid_DSN_layer_activity')
    routed=[label for label,kind in layers.items() if kind=='signal' and active.get(label,'on')=='on']
    if not routed:raise ValueError('actual_DSN_routing_layers_required')
    classes=[x for x in network['children'] if head(x)=='class']
    memberships={};class_names=set()
    for klass in classes:
        name=klass['atoms'][1][0]
        if name in class_names:raise ValueError('duplicate_DSN_class')
        class_names.add(name)
        for atom in klass['atoms'][2:]:
            if atom[0] in memberships:raise ValueError('ambiguous_DSN_netclass')
            memberships[atom[0]]=(klass,atom)
    if construction_layers_by_net is None:
        construction_layers_by_net={}
    if (type(construction_layers_by_net) is not dict
            or set(construction_layers_by_net)-selected):
        raise ValueError('explicit_present_requested_rated_layer_scopes_required')
    edits=[];new_classes=[];manifest={}
    for net in sorted(selected):
        contract=requirements[net]
        if net not in memberships:raise ValueError('rated_net_missing_exact_DSN_class:'+net)
        klass,member=memberships[net];rule=one(klass,'rule');width=one(rule,'width')
        if len(width['atoms'])!=2:raise ValueError('native_scalar_class_width_required')
        if any(head(c)=='layer_rule' for c in klass['children']):
            raise ValueError('per_layer_class_rules_require_separate_verified_compiler')
        old=float(width['atoms'][1][0])/1000.
        by_layer=contract['required_by_layer_mm']
        scoped_routed=list(routed)
        selected_layers=construction_layers_by_net.get(net)
        if selected_layers is not None:
            if (type(selected_layers) is not list or not selected_layers
                    or any(type(v) is not str or not v for v in selected_layers)
                    or len(set(selected_layers))!=len(selected_layers)
                    or not set(selected_layers)<=set(contract['routing_layers'])):
                raise ValueError('nonempty_native_contract_layer_subset_required')
            scoped_routed=[label for label in routed if layer_map[label] in selected_layers]
            if set(layer_map[label] for label in scoped_routed)!=set(selected_layers):
                raise ValueError('selected_layer_not_active_in_actual_DSN')
            circuits=[c for c in klass['children'] if head(c)=='circuit']
            if len(circuits)>1:raise ValueError('ambiguous_original_class_circuit')
            original_scopes=[c for circuit in circuits for c in circuit['children'] if head(c)=='use_layer']
            if len(original_scopes)>1:raise ValueError('ambiguous_original_class_layer_scope')
            if original_scopes:
                previous={atom[0] for atom in original_scopes[0]['atoms'][1:]}
                if not previous<=set(layer_map):raise ValueError('unbound_original_class_layer_scope')
                if not set(scoped_routed)<=previous:raise ValueError('construction_scope_widens_original_class')
        needed={label:float(by_layer[layer_map[label]]) for label in scoped_routed}
        if not all(math.isfinite(v) and v>0 for v in [old,*needed.values()]):
            raise ValueError('positive_uncapped_width_authority_required')
        # Outward integer half-width grid, not a guessed current/thermal guard.
        # A PCB1nm width can lie between DSN integer resolution coordinates.
        half_ticks=(Decimal(str(max(old,*needed.values())))*1000*scale/2).to_integral_value(rounding=ROUND_CEILING)
        target_um=(half_ticks*2/scale).quantize(Decimal('.000001'),rounding=ROUND_CEILING)
        encoded=format(target_um,'f').rstrip('0').rstrip('.')
        name='CEC_RATED_'+hashlib.sha256(net.encode()).hexdigest()[:16]
        if name in class_names:raise ValueError('rated_class_namespace_collision')
        old_body=text[klass['start']:klass['stop']]
        # Clone circuit/clearance/via/other rules exactly; change only width.
        rules=[]
        for child in klass['children']:
            raw=text[child['start']:child['stop']]
            if child is rule:
                a=width['atoms'][1][1]-child['start'];b=width['atoms'][1][2]-child['start']
                raw=raw[:a]+encoded+raw[b:]
            if selected_layers is not None and head(child)=='circuit':
                scopes=[c for c in child['children'] if head(c)=='use_layer']
                layer_rule='(use_layer '+' '.join(json.dumps(label) for label in scoped_routed)+')'
                if scopes:
                    a=scopes[0]['start']-child['start'];b=scopes[0]['stop']-child['start']
                    raw=raw[:a]+layer_rule+raw[b:]
                else:raw=raw[:-1]+'\n'+layer_rule+')'
            rules.append(raw)
        if selected_layers is not None and not any(head(c)=='circuit' for c in klass['children']):
            rules.append('(circuit (use_layer '+' '.join(json.dumps(label) for label in scoped_routed)+'))')
        edits.append((member[1],member[2],''))
        # Native exported member spelling is authority (Unicode/backslashes too).
        new_classes.append('(class '+json.dumps(name)+' '+text[member[1]:member[2]]+'\n'+'\n'.join(rules)+')')
        manifest[net]=dict(previous_class=klass['atoms'][1][0],previous_width_mm=old,
            exported_width_mm=float(target_um/1000),required_by_actual_DSN_layer_mm=needed,
            DSN_resolution_per_um=scale,integer_half_width_grid_um=2/scale,
            authority=contract,completed=False,capability=('explicit_per_class_construction_subset_width_only' if selected_layers is not None else 'conservative_single_width_all_active_layers'),
            extra_active_layers_outside_contract_pool=sorted(set(layer_map[label] for label in routed)-set(contract.get('routing_layers',layer_map.values()))),
            selected_native_construction_layers=selected_layers,
            selected_DSN_class_layers=scoped_routed if selected_layers is not None else None,
            receiver_must_enforce_new_track_layers=selected_layers is not None,
            layer_barrel_sharing_and_full_current_qualified=False)
    edits.append((network['stop']-1,network['stop']-1,'\n'+'\n'.join(new_classes)+'\n'))
    result=text
    for a,b,replacement in sorted(edits,reverse=True):result=result[:a]+replacement+result[b:]
    parse(result)
    return result,dict(schema=1,scope='source_bound_uncapped_DSN_class_width_only',
        actual_DSN_routing_layers=routed,layer_map=dict(layer_map),nets=manifest,
        actual_network_net_pins=inventory,requested_nets=sorted(requested),
        deferred_not_completed=[dict(net=n,completed=False,
            reason='absent_DSN_net' if n not in inventory else
                'no_active_DSN_pins' if n not in active_nets else 'outside_explicit_requested_scope',
            authority=requirements[n]) for n in sorted(set(requirements)-selected)],
        capability_exceptions_accepted=False,
        global_current_or_barrel_qualified=False,release_authority=False)


def overlay_for_source(source,dsn,*,board_hint,expected_source_sha256,expected_dsn_sha256,requested_nets=None,construction_layers_by_net=None):
    """Recompute real native/source/policy current contracts; no trusted dicts."""
    import pcbnew
    import cec_force_current as force
    import cec_synth_pipeline as synth
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_route_dimensions as dimensions
    source,dsn=Path(source).resolve(),Path(dsn).resolve()
    if not board_hint or force._hash(source)!=expected_source_sha256 or force._hash(dsn)!=expected_dsn_sha256:
        raise ValueError('exact_named_source_and_DSN_epoch_required')
    with force._thermal_hint(board_hint):
        family=force._family(source,board_hint);code=force._code_identity()
        cfg=synth.Config.load(board_hint)
        with synth._oracle_env(cfg.params):
            board=pcbnew.LoadBoard(str(source))
            if board is None:raise ValueError('native_source_unavailable')
            contracts=topology.route_width_contracts(board,board_hint=board_hint)
            domains=topology.board_current_domains(board,board_hint=board_hint)
            if set(domains)-set(contracts):
                raise ValueError('unresolved_current_domain_no_static_signal_fallback:'+str(sorted(set(domains)-set(contracts))))
            resolver=dimensions.project_resolver(source,board=board)
            # Retain every ordinary/project floor too; current is not a waiver.
            for net,c in contracts.items():
                floor=float(resolver(net)['track_width'])
                c['required_by_layer_mm']={k:max(floor,float(v)) for k,v in c['required_by_layer_mm'].items()}
            enabled=tuple(fab.enabled_copper_layers(board))
            layer_map={board.GetLayerName(board.GetLayerID(layer)):layer for layer in enabled}
            indices={board.GetLayerName(board.GetLayerID(layer)):i for i,layer in enumerate(enabled)}
            # Match each real exported terminal to the actual saved native net.
            # Duplicate physical pads share KiCad's registered @index aliases.
            terminals={}
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    if pad.GetNetname():
                        token=str(fp.GetReference())+'-'+str(pad.GetNumber())
                        terminals.setdefault(token,[]).append((str(fp.m_Uuid.AsString()),str(pad.GetNetname())))
            pin_nets={}
            for token,rows in terminals.items():
                if len(set(rows))!=1:raise ValueError('ambiguous_native_DSN_terminal:'+token)
                aliases=[token]+[token+'@'+str(i) for i in range(1,len(rows))]
                for alias in aliases:
                    if alias!=token and alias in terminals:raise ValueError('native_DSN_alias_collision')
                    pin_nets[alias]=rows[0][1]
            text=dsn.read_bytes().decode()
            verified=verify_network_inventory(text,pin_nets)
            result,report=overlay(text,contracts,layer_map,indices,requested_nets,construction_layers_by_net)
            report['actual_network_pin_inventory_verified_against_native_source']=True
        if family!=force._family(source,board_hint) or code!=force._code_identity() or force._hash(dsn)!=expected_dsn_sha256:
            raise ValueError('source_current_or_DSN_epoch_changed')
    report.update(source=str(source),source_sha256=expected_source_sha256,
        DSN=str(dsn),DSN_sha256=expected_dsn_sha256,code_identity=code,
        helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_family=family,output_sha256=hashlib.sha256(result.encode()).hexdigest())
    return result,report

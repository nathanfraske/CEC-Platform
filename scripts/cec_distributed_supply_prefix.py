"""Fresh canonical supply-terminal authority for bounded planar prefixes.

No consumer allocation, source-copper credit, new barrel permission or release
qualification follows.  Geometry is still received by the existing whole-
current endpoint receiver and the enclosing saved-board gates.
"""
import math
import time
import pcbnew
import cec_force_current as force
import cec_full_current_supply_prefix as prefix
import cec_fr as fr
import cec_source_ground_leaf as source


def _source_pin(identity, pin, role):
    """Actual embedded source type, not native importer annotations."""
    _fp,_path,sf,symbol=identity
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    if len(libraries)!=1:raise ValueError('source_supply_prefix_library_required')
    tree=source.synth.parse_sexpr(libraries[0])
    selected=[s for s in source.synth._kids(tree,'symbol') if len(s)>1 and s[1]==symbol['lib_id']]
    if len(selected)!=1:raise ValueError('source_supply_prefix_selected_symbol_required')
    queue=list(selected);found=[];count=0
    while queue:
        node=queue.pop();count+=1
        if count>8192:raise ValueError('source_supply_prefix_symbol_bound')
        if isinstance(node,list) and node:
            if node[0]=='pin' and source.synth._val(node,'number','')==pin:found.append(node)
            queue.extend(c for c in node if isinstance(c,list))
    kinds=('power_in','power_out') if role=='manufacturer_supply_pin' else ('passive',)
    if len(found)!=1 or len(found[0])<2 or found[0][1] not in kinds:
        raise ValueError('source_supply_prefix_positive_source_pin_type_required')


def prepare(board, contracts, *, board_hint, timeout_s=10.):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_supply_prefix_source_required')
    deadline=time.monotonic()+timeout_s
    root=source.source_nc._root(board,board_hint)
    _files,hashes,instances=source._hierarchy(root,deadline)
    tree,export=source._export(root,deadline)
    comps,nets,node_net=source._tables(tree)
    identities={};pads={};out={}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net=pad.GetNetname()
            role=prefix.supply_terminal_role(pad)
            if net not in contracts or role is None:continue
            ref=fp.GetReference();pin=pad.GetNumber()
            if ref not in identities:
                identities[ref]=source._identity(board,ref,comps,instances,deadline)
            identity=identities[ref];source._pin(identity,pin);_source_pin(identity,pin,role)
            for peer in fp.Pads():
                if node_net.get((ref,peer.GetNumber()),'')!=peer.GetNetname():
                    raise ValueError('source_supply_prefix_complete_part_net_mismatch')
            if node_net.get((ref,pin))!=net:
                raise ValueError('source_supply_prefix_pin_net_mismatch')
            pads[force._uid(pad)]=dict(ref=ref,pin=pin,net=net,role=role)
    for net,contract in contracts.items():
        refs=sorted({p['ref'] for p in pads.values() if p['net']==net})
        # No role or current inferred from an untyped native land.
        if refs:out[net]=dict(contract,authority_refs=refs)
    source._tick(deadline)
    if any(force._hash(path)!=digest for path,digest in hashes.items()):
        raise ValueError('source_supply_prefix_hierarchy_changed')
    return dict(contracts=out,pads=pads,source_bindings=dict(hierarchy=hashes,export=export),
                current_authority_changed=False,release_authority=False)


def endpoint(board, anchor, contract, context):
    if anchor['kind']!='pad_center' or anchor['uuid'] not in context['pads']:return None
    pad=next((p for fp in board.GetFootprints() for p in fp.Pads()
              if force._uid(p)==anchor['uuid']),None)
    if pad is None or context['pads'][anchor['uuid']]['net']!=contract['net']:return None
    name=__import__('cec_fab_profile').COPPER_LAYER_IDS[anchor['layer']]
    import cec_route_dimensions as dimensions
    import cec_fab_profile as fab
    import cec_fab_check as factory
    profile=fab.get_profile(contract['profile'])
    rules=factory.profile_rules(factory.PROFILES[profile['vendor']],fab.stackup_oz(contract['profile'])[name],profile)
    physics=dimensions.current_trace_widths(contract['current_authority'],(name,),contract['profile'],rise_c=30.)[name]
    floor=max(int(board.GetDesignSettings().m_TrackMinWidth),math.ceil(max(physics,rules['track'])*1e6))
    return fr._pad_local_escape(pad,math.ceil(contract['required_by_layer_mm'][name]*1e6),
        math.ceil(contract['clearance_mm']*1e6),floor)


def receive(board, contracts, ids, context, *, timeout_s=10.):
    """Exact new scope only; never silently bless an omitted narrow atom."""
    ids=set(ids)
    selected=[t for t in board.GetTracks() if force._uid(t) in ids]
    if (len(selected)!=len(ids) or any(t.GetClass()!='PCB_TRACK'
            or t.GetNetname() not in contracts or __import__('cec_fab_profile').COPPER_LAYER_IDS.get(t.GetLayer())
                not in contracts[t.GetNetname()]['routing_layers'] for t in selected)):
        raise ValueError('exact_typed_supply_new_track_scope_required')
    narrow={force._uid(t) for t in board.GetTracks() if force._uid(t) in ids
        and t.GetClass()=='PCB_TRACK' and t.GetNetname() in contracts
        and t.GetWidth()<math.ceil(contracts[t.GetNetname()]['required_by_layer_mm'][
            __import__('cec_fab_profile').COPPER_LAYER_IDS[t.GetLayer()]]*1e6)}
    if not narrow:return dict(complete=True,track_uuids=[],proofs=[],refusals=[])
    allowed={net:dict(c,authority_refs=context['contracts'][net]['authority_refs'])
        for net,c in contracts.items() if net in context['contracts']}
    report=prefix.receive(board,allowed,track_uuid_scope=narrow,timeout_s=timeout_s)
    proved=set(report['track_uuids'])
    # Native role is necessary but not enough: launch IDs must also be freshly
    # present in the canonical source compiler's positive terminal inventory.
    source_pads=set(context['pads'])
    if (not report['complete'] or proved!=narrow or any(not set(p['launch_pad_uuids'])<=source_pads
            for p in report['proofs'])):
        raise ValueError('source_supply_prefix_incoming_scope_not_independently_received')
    return report

"""Fresh canonical full pin-table evidence for native pads without pin labels.

This checks Source identity and every physical net. It neither populates blank
PCB fields nor grants a pose, cut, current budget or native connection edge.
"""
import copy,contextvars,math,time
from contextlib import contextmanager
from pathlib import Path
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_synth_pipeline as synth
from cec_native_items import _native_pointer


_observations=contextvars.ContextVar('immutable_complete_source_pinmap_observations',default=None)


def _lease(timeout_s):
    if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
        raise ValueError('bounded_complete_source_pinmap_observation_scope_required')
    return time.monotonic()+timeout_s


def _scope_live(context):
    if time.monotonic()>=context['deadline']:
        raise ValueError('complete_source_pinmap_observation_scope_deadline')
    if (context['binding']!=row._source_binding(context['board'])
            or any(force._hash(Path(name))!=digest for name,digest in context['files'].items())):
        raise ValueError('immutable_source_pinmap_observation_changed')
    if time.monotonic()>=context['deadline']:
        raise ValueError('complete_source_pinmap_observation_scope_deadline')


@contextmanager
def observation_scope(board,*,board_hint,timeout_s=10.):
    """Invocation-local facts, never a caller proof or cross-mutation cache."""
    deadline=_lease(timeout_s)
    if type(board_hint)is not str or not board_hint:
        raise ValueError('explicit_source_pinmap_observation_hint_required')
    context=dict(board=board,hint=board_hint,binding=row._source_binding(board),
        deadline=deadline,files={},proofs={})
    token=_observations.set(context)
    try:
        _scope_live(context);yield;_scope_live(context)
    finally:_observations.reset(token)


def prove(fp,model,*,board_hint,timeout_s=8.):
    if (type(board_hint)is not str or not board_hint or type(timeout_s)not in(int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or not model or model.get('device_package')!='ESP32-C6-MINI-1'):
        raise ValueError('fresh_complete_source_device_pinmap_context_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('complete_source_device_pinmap_deadline')
    import cec_device_power_roles as roles
    import cec_source_ground_leaf as canonical
    if model!=roles.footprint_contract(fp):
        raise ValueError('fresh_complete_source_device_package_required')
    board=fp.GetBoard();binding=row._source_binding(board)
    context=_observations.get()
    if context is not None and (_native_pointer(context['board'])!=_native_pointer(board) or context['hint']!=board_hint):
        # A native child/different Source is a separate observation, never
        # an alias to its parent's proof merely because pad UUIDs agree.
        context=None
    if context is not None:
        deadline=min(deadline,context['deadline'])
        _scope_live(context)
        cached=context['proofs'].get(force._uid(fp))
        if cached is not None:
            if cached['model']!=model:raise ValueError('immutable_source_pinmap_model_changed')
            proof=copy.deepcopy(cached['proof']);tick();return proof
    cfg=synth.Config.load(board_hint);root=Path(cfg.sch).resolve(strict=True)
    tick()
    files,hashes,instances=canonical._hierarchy(root,deadline)
    tree,export=canonical._export(root,deadline);comps,nets,node_net=canonical._tables(tree)
    identity=canonical._identity(board,fp.GetReference(),comps,instances,deadline)
    current,path,sf,symbol=identity
    if force._uid(current)!=force._uid(fp):raise ValueError('complete_source_device_native_owner_mismatch')
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    if len(libraries)!=1:raise ValueError('complete_source_device_symbol_library_required')
    embedded=synth.parse_sexpr(libraries[0]);selected=[n for n in synth._kids(embedded,'symbol')
        if len(n)>1 and n[1]==symbol['lib_id']]
    if len(selected)!=1 or synth._first(selected[0],'extends')is not None:
        raise ValueError('complete_source_device_unique_embedded_symbol_required')
    nodes=[selected[0]];pins={};visited=0
    while nodes:
        tick();node=nodes.pop();visited+=1
        if visited>8192:raise ValueError('complete_source_device_symbol_inventory_bound')
        if isinstance(node,list)and node:
            if node[0]=='pin':
                number=synth._val(node,'number','')
                if not number or number in pins or len(node)<2:
                    raise ValueError('complete_source_device_unique_logical_pin_required')
                pins[number]=dict(function=synth._val(node,'name',''),type=node[1])
            nodes.extend(child for child in node if isinstance(child,list))
    expected={number:dict(function=model['native_pin_functions'][number],
        type='power_in'if role in('ground','power_input')else'no_connect'if role=='no_connect'
        else'input'if number=='8'else'bidirectional')for number,role in model['pins'].items()}
    source_pins={p['num']:p for p in symbol['pins']}
    if (pins!=expected or len(source_pins)!=len(symbol['pins'])or source_pins.keys()!=pins.keys()
            or any(source_pins[number]['type']!=item['type']for number,item in pins.items())):
        raise ValueError('complete_source_device_manufacturer_pin_table_mismatch')
    pads=list(fp.Pads())
    if (len(pads)!=61 or len({force._uid(p)for p in pads})!=61
            or {p.GetNumber()for p in pads}!=set(pins)
            or any(node_net.get((fp.GetReference(),p.GetNumber()))!=p.GetNetname()for p in pads)):
        raise ValueError('complete_source_device_all_physical_pad_nets_required')
    for number in pins:
        if sum(p.GetNumber()==number for p in pads)!=model['physical_ground_land_counts'].get(number,1):
            raise ValueError('complete_source_device_physical_pin_multiplicity_changed')
    tick()
    if (binding!=row._source_binding(board)
            or any(force._hash(Path(name))!=digest for name,digest in hashes.items())):
        raise ValueError('complete_source_device_live_binding_changed')
    tick()
    proof=dict(schema=1,scope='fresh_complete_canonical_manufacturer_device_pinmap',
        board_hint=board_hint,owner_uuid=force._uid(fp),owner_reference=fp.GetReference(),
        root=str(root),source_schematic=str(path),symbol_uuid=symbol['uuid'],lib_id=symbol['lib_id'],
        hierarchy=hashes,export=export,logical_pins=pins,
        native_pad_nets={force._uid(p):dict(number=p.GetNumber(),net=p.GetNetname())for p in pads},
        native_pin_metadata_not_written=True,current_authority=False,
        native_connections_added=False,pose_or_cut_authority=False,release_authority=False)
    if context is not None:
        for name,digest in hashes.items():
            if name in context['files']and context['files'][name]!=digest:
                raise ValueError('immutable_source_pinmap_hierarchy_changed')
            context['files'][name]=digest
        context['proofs'][force._uid(fp)]=dict(model=copy.deepcopy(model),proof=copy.deepcopy(proof))
        _scope_live(context)
    tick()
    return proof

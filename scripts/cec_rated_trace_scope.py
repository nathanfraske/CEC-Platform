"""Necessary source-bound new-trace layer gate; never current/barrel authority."""
import hashlib
import json
from pathlib import Path


def normalize(scope):
    if scope is None:return {}
    if (type(scope) is not dict or len(scope)>64
            or any(type(net) is not str or not net for net in scope)):
        raise ValueError('explicit_bounded_current_net_layer_mapping_required')
    result={}
    for net,layers in scope.items():
        if (type(layers) is not list or not 1<=len(layers)<=32
                or any(type(layer) is not str or not layer for layer in layers)
                or len(set(layers))!=len(layers)):
            raise ValueError('explicit_unique_native_layer_list_required')
        result[net]=list(layers)
    if len(json.dumps(result).encode())>65536:raise ValueError('bounded_trace_scope_required')
    return result


def bind_source(source,board_hint,scope):
    scope=normalize(scope)
    if not scope:return None
    if not isinstance(board_hint,str) or not board_hint:raise ValueError('named_board_authority_required')
    import pcbnew
    import cec_force_current as force
    import cec_current_topology as topology
    import cec_fab_profile as fab
    source=Path(source).resolve();before=force._family(source,board_hint)
    with force._thermal_hint(board_hint):
        board=pcbnew.LoadBoard(str(source))
        contracts=topology.route_width_contracts(board,board_hint=board_hint)
        enabled=set(fab.enabled_copper_layers(board))
        nonplane=set(fab.routing_layers(board,hint=board_hint,include_power=False))
        for net,layers in scope.items():
            if (net not in contracts or not set(layers)<=enabled or not set(layers)<=nonplane
                    or not set(layers)<=set(contracts[net]['routing_layers'])):
                raise ValueError('construction_layers_require_actual_enabled_current_contract_subset')
        evidence={net:contracts[net] for net in sorted(scope)}
    if before!=force._family(source,board_hint):raise ValueError('source_changed_during_trace_scope_binding')
    result=dict(source=str(source),source_sha256=before[str(source)],board_hint=board_hint,
        construction_layers_by_net=scope,source_contracts=evidence,
        current_or_barrel_qualified=False,release_authority=False)
    # Descriptor identity must survive its actual request/receipt JSON boundary.
    # Reject nonfinite/opaque values rather than stringify or weaken equality.
    result=json.loads(json.dumps(result,sort_keys=True,allow_nan=False))
    result['binding_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return result


def receive(source,candidate,*,board_hint,scope):
    bound=bind_source(source,board_hint,scope)
    if bound is None:return dict(ok=True,complete=True,enabled=False)
    import pcbnew
    import cec_force_current as force
    source,candidate=Path(source).resolve(),Path(candidate).resolve()
    family=force._family(source,board_hint);code=force._code_identity();child_hash=force._hash(candidate)
    before=pcbnew.LoadBoard(str(source));after=pcbnew.LoadBoard(str(candidate))
    originals=[i.m_Uuid.AsString() for i in before.GetTracks()]
    if len(set(originals))!=len(originals):raise ValueError('duplicate_source_track_UUID')
    original=set(originals);seen=set();checked=[];violations=[];vias=[]
    for item in after.GetTracks():
        uid=item.m_Uuid.AsString()
        if uid in seen:raise ValueError('duplicate_candidate_track_UUID')
        seen.add(uid)
        net=str(item.GetNetname())
        if uid in original or net not in bound['construction_layers_by_net']:continue
        if len(checked)+len(vias)>=4096:raise ValueError('bounded_new_trace_scope_inventory_required')
        kind=item.GetClass()
        if kind=='PCB_VIA':vias.append(uid);continue
        layer=pcbnew.LayerName(item.GetLayer())
        row=dict(uuid=uid,net=net,kind=kind,layer=layer)
        checked.append(row)
        if kind not in ('PCB_TRACK','PCB_ARC') or layer not in bound['construction_layers_by_net'][net]:
            violations.append(row)
    live=(family==force._family(source,board_hint) and code==force._code_identity()
          and child_hash==force._hash(candidate) and bound==bind_source(source,board_hint,scope))
    return dict(ok=not violations and live,complete=True,enabled=True,binding=bound,
        candidate_sha256=child_hash,checked_new_tracks=checked,new_vias_not_trace_or_barrel_credit=vias,
        violations=violations,epoch_unchanged=live,current_or_barrel_qualified=False,
        original_source_geometry_must_also_pass_independent_full_source_replay=True,release_authority=False)


def assert_receipt(receipt,binding):
    if binding is None:return
    import cec_force_current as force
    proof=receipt.get('new_trace_layer_receiving',{})
    if (proof.get('ok') is not True or proof.get('complete') is not True
            or proof.get('enabled') is not True or proof.get('binding')!=binding
            or proof.get('candidate_sha256')!=force._hash(receipt['candidate'])):
        raise ValueError('live_new_trace_scope_receipt_or_candidate_changed')

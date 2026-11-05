"""Carry exact local endpoint ownership across joint-cell materialization.

Grouping is only geometric proposal ownership. Saved receiving additionally
rederives the entire source current, typed launches and full-width throats.
No unknown current, aggregate-GND rating or release permission is inferred.
"""
import json
import math
import time
from pathlib import Path

import cec_decoupler_cell as cells
import cec_force_current as force
import cec_fr as fr
import cec_fab_profile as fab


class EndpointMaterializationRefused(ValueError):
    """Native same-net construction debt, for rejecting search feedback only."""
    def __init__(self,rejected):
        super().__init__('complete_cell_new_endpoint_component_unqualified:'+str(rejected))
        pure={'too_many_fragments','branched_narrow_component','escape_budget_exceeded','no_fine_pad_contact'}
        self.rejected_nets=(tuple(sorted({row['net']for row in rejected}))if rejected and all(
            type(row)is dict and type(row.get('net'))is str and row['net']
            and row.get('reason')in pure for row in rejected)else ())
        self.native_components=()
        self.fixed_ordinary_nets=()
        self.constructed_by={}


def _fixed_ordinary_nets(board,nets,source):
    """Classification cannot change through another current partition.

    Missing Source permits no nonload exception at all. With Source, only a
    net with NO actual manufacturer measurement pin is independent of the
    collective measurement/current-partition inventory. Unknown model data
    grants no exception in either this check or _measurement().
    """
    if source is None:return tuple(sorted(nets))
    source=Path(source).resolve()
    if source.suffix!='.kicad_pcb'or not source.is_file():return tuple(sorted(nets))
    import cec_device_power_roles as roles
    result=set(nets)
    for fp in board.GetFootprints():
        model=roles.footprint_contract(fp)
        if model:
            result.difference_update(str(p.GetNetname())for p in fp.Pads()
                if model['pins'].get(str(p.GetNumber()))=='measurement')
    return tuple(sorted(result))


def _track_operation(op):
    """Strict integer native straight-line identity, not a rounded drawing."""
    if (not isinstance(op,(list,tuple))or len(op)!=5 or op[0]!='trk'
            or type(op[3])is not int or op[3]<=0 or type(op[4])is not int):
        return None
    a,b=op[1:3]
    if (not all(isinstance(p,(list,tuple))and len(p)==2
            and all(type(v)is int for v in p)for p in(a,b))or a==b):return None
    return tuple(a),tuple(b),op[3],op[4]


def _can_contribute_collinear_cover(op,stroke):
    """Any partial/equal-width/endpoint contributor can complete a union."""
    a,b,width,face=stroke;p,q,other_width,other_face=op
    if other_width<width or other_face!=face:return False
    v=(b[0]-a[0],b[1]-a[1]);square=v[0]**2+v[1]**2
    if any(v[0]*(r[1]-a[1])!=v[1]*(r[0]-a[0])for r in(p,q)):return False
    lo,hi=sorted((r[0]-a[0])*v[0]+(r[1]-a[1])*v[1]for r in(p,q))
    return hi>=0 and lo<=square


def _absolute_overlength_scope(error,selected,domains):
    """Reject only a native component that exceeds EVERY locality budget.

    Added copper cannot shorten a surviving narrow component. The sole
    constructive removal in _native_ops is exact sufficient-width collinear
    union reuse. Include every producer AND every domain whose ANY choice
    could contribute to that reuse, not just the currently selected covers.
    This is rejection-only search evidence, never current/route admission.
    """
    if (not error.native_components or not domains or set(domains)!=set(selected)
            or len(domains)>128):return None
    deadline=time.monotonic()+.25
    for component in error.native_components:
        if (component['reason']!='escape_budget_exceeded'
                or component['net']not in error.fixed_ordinary_nets
                or sum(t['length_nm']for t in component['tracks'])<=component['absolute_limit_nm']+2):
            continue
        keys=set();strokes=[]
        for t in component['tracks']:
            owner=error.constructed_by.get(t['uuid'],{})
            key=owner.get('obligation');choice=selected.get(key)
            stroke=(tuple(t['a_nm']),tuple(t['b_nm']),t['width_nm'],t['face'])
            if (not choice or owner.get('choice_id')!=choice['id']or choice['net']!=component['net']
                    or not any(_track_operation(op)==stroke for op in choice.get('ops',()))):
                return None
            keys.add(key);strokes.append(stroke)
        if not keys:return None
        for key,choices in domains.items():
            if (time.monotonic()>=deadline or not isinstance(choices,(list,tuple))
                    or not 1<=len(choices)<=128 or selected[key]not in choices):return None
            for choice in choices:
                if choice.get('net')!=component['net']:continue
                ops=choice.get('ops')
                if not isinstance(ops,(list,tuple))or len(ops)>256:return None
                for op in ops:
                    if time.monotonic()>=deadline:return None
                    if isinstance(op,(list,tuple))and op and op[0]=='via':continue
                    candidate=_track_operation(op)
                    if candidate is None:return None
                    if any(_can_contribute_collinear_cover(candidate,s)for s in strokes):keys.add(key)
        return tuple(sorted((key,selected[key]['id'])for key in keys))
    return None


def rejection_clause(error,selected,*,domain_binding,domains=None):
    """Bounded native conflict scope; unknown classification stays collective."""
    if type(error)is not EndpointMaterializationRefused or not error.rejected_nets:
        return False
    import cec_joint_connection_search as joint
    # A measurement tree's classification may depend on OTHER-net current
    # partitions. Never prune those rescuing alternatives with a same-net cut.
    fixed=set(error.rejected_nets)<=set(error.fixed_ordinary_nets)
    if domains is not None and domain_binding!=joint._binding(domains):return False
    peers=_absolute_overlength_scope(error,selected,domains)if fixed else None
    if peers:
        return joint.RejectedSelection(domain_binding,peers,
            'native_absolute_overlength_with_all_potential_collinear_rescuers')
    peers=tuple(sorted((key,choice['id'])for key,choice in selected.items()
        if not fixed or choice['net']in error.rejected_nets))
    return (joint.RejectedSelection(domain_binding,peers,
        'native_complete_same_net_endpoint_materialization_refused')if peers else False)


def _stable(value):
    return json.loads(json.dumps(value,allow_nan=False))


def _measurement(board,items,hint,source,deadline):
    """Reprove actual nonload trees, never trust a producer's role/UUID list."""
    if source is None:return dict(track_uuids=[],proofs=[])
    source=Path(source).resolve()
    # Missing Source context grants NO exception; ordinary paths continue to
    # the original strict netclass/current/prefix receivers below.
    if source.suffix!='.kicad_pcb' or not source.is_file():
        return dict(track_uuids=[],proofs=[])
    import cec_device_power_roles as roles
    nets={str(t.GetNetname()) for t in items if t.GetClass()=='PCB_TRACK'}
    relevant=False
    for fp in board.GetFootprints():
        model=roles.footprint_contract(fp)
        if model and any(str(p.GetNetname()) in nets and
                model['pins'].get(str(p.GetNumber()))=='measurement' for p in fp.Pads()):
            relevant=True;break
    if not relevant:return dict(track_uuids=[],proofs=[])
    import cec_current_topology as topology
    import cec_measurement_current_branch as measurement
    with force._thermal_hint(hint):
        domains=topology.board_current_domains(board,board_hint=hint)
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('cell_measurement_classification_deadline')
        evidence=measurement.inventory(board,source,domains,timeout_s=min(10.,remaining))
    # A timed-out inventory has no authority, even for a previously visited
    # land. Unknown branches retain the original full-current width check.
    legal=set(evidence['uuids']) if evidence['complete'] is True else set()
    actual={force._uid(t) for t in items if t.GetClass()=='PCB_TRACK'}
    legal&=actual
    return dict(track_uuids=sorted(legal),proofs=[] if not legal else [dict(
        kind='independently_typed_nonload_measurement_tree',
        track_uuids=sorted(legal),evidence=evidence,
        aggregate_current_budget_changed=False,current_capacity_qualified=False)])


def _cohorts(board,items,hint,requests,measurement_ids=()):
    import cec_source_face_widths as source_widths
    result={};contracts={};widths={}
    for item in items:
        if item.GetClass()!='PCB_TRACK':continue
        if force._uid(item) in measurement_ids:continue
        net=str(item.GetNetname());face=int(item.GetLayer())
        if net not in contracts:
            with force._thermal_hint(hint):
                contracts[net]=None if net=='GND' else cells._supply_current_widths(board,net)
            widths[net]=source_widths.envelope(board,requests,net,contracts[net])
        contract=contracts[net]
        required=widths[net][face]
        if contract:
            if face not in contract['required_by_layer_nm']:
                raise ValueError('cell_prefix_current_layer_not_authorized')
            required=max(required,contract['required_by_layer_nm'][face])
        if item.GetWidth()>=required:continue
        if net!='GND' and not contract:
            raise ValueError('cell_prefix_positive_source_current_required')
        gap=max(200000,int(cells._netclass(board,net)['clearance']))
        result.setdefault((net,face,required,gap),[]).append(item)
    return result,contracts


def group(board,items,*,board_hint,source_path=None,requests=None):
    """Requalify ALL new narrow copper, not a producer's lost group label."""
    nonload=_measurement(board,items,board_hint,source_path,time.monotonic()+10.)
    # Construction and saved receiving must see the same complete Source
    # demand widths, including wider shared demands hidden by route aliases.
    # Missing context preserves legacy direct-call behavior, not new credit.
    requests={}if requests is None else requests
    if type(requests)is not dict:raise ValueError('exact_endpoint_source_requests_required')
    cohorts,_=_cohorts(board,items,board_hint,requests,set(nonload['track_uuids']))
    checked=[]
    for (net,face,width,gap),tracks in cohorts.items():
        qualified,rejected=fr._qualified_endpoint_neckdown_tracks(board,tracks,width,
            required_clearance=gap)
        if rejected:
            error=EndpointMaterializationRefused(rejected)
            actual={force._uid(t):t for t in tracks}
            # Never learn from the report's rounded display length. Capture
            # the actual native items before rollback and use native lengths.
            error.native_components=tuple(dict(net=net,reason=r['reason'],
                absolute_limit_nm=round(fr._endpoint_neckdown_limit_mm((),width,
                    full_width_via=True)*1e6),tracks=tuple(dict(uuid=uid,
                    a_nm=tuple(actual[uid].GetStart()),b_nm=tuple(actual[uid].GetEnd()),
                    width_nm=int(actual[uid].GetWidth()),face=int(actual[uid].GetLayer()),
                    length_nm=float(actual[uid].GetLength()))for uid in r['uuids']))
                for r in rejected if r.get('uuids')and set(r['uuids'])<=set(actual))
            error.fixed_ordinary_nets=_fixed_ordinary_nets(board,error.rejected_nets,source_path)
            raise error
        if {force._uid(t) for t in qualified}!={force._uid(t) for t in tracks}:
            raise ValueError('complete_cell_new_endpoint_component_unqualified:'+str(rejected))
        checked.append((tracks,width,gap))
    proofs=list(nonload['proofs'])
    for tracks,width,gap in checked:
        proofs.append(fr.group_endpoint_neckdowns(board,tracks,width,required_clearance=gap))
    return proofs


def receive(parent,child,requests,items,*,board_hint,deadline,source_proposal=None):
    """Only exact new class-only prefixes may supplement the width check."""
    import cec_source_current_pad_ports as body_ports
    body_proofs=body_ports.receive(parent,child,requests,items,board_hint=board_hint,deadline=deadline)
    nonload=_measurement(child,items,board_hint,parent.GetFileName() or None,deadline)
    measurement_ids=set(nonload['track_uuids'])
    for net in {str(i.GetNetname()) for i in items if force._uid(i) in measurement_ids}:
        with force._thermal_hint(board_hint):
            before=cells._supply_current_widths(parent,net)
            after=cells._supply_current_widths(child,net)
        if before is None or _stable(before)!=_stable(after):
            raise ValueError('cell_nonload_original_full_current_contract_changed')
    cohorts,contracts=_cohorts(child,items,board_hint,requests,measurement_ids)
    if not cohorts:return dict(track_uuids=sorted(measurement_ids),proofs=[*body_proofs,*nonload['proofs']],current_budget_lowered=False)
    groups=[g for g in child.Groups() if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP]
    if len(groups)!=1:raise ValueError('saved_cell_exact_endpoint_group_required')
    grouped=groups[0];legal=set(measurement_ids);proofs=[*body_proofs,*nonload['proofs']];supply={};supply_ids=set()
    pads={force._uid(p):p for fp in child.GetFootprints() for p in fp.Pads()}
    for (net,face,width,gap),tracks in cohorts.items():
        if time.monotonic()>=deadline:raise ValueError('cell_prefix_receiving_deadline')
        ids={force._uid(t) for t in tracks}
        if any(not grouped.ContainsItem(t) for t in tracks):
            raise ValueError('saved_cell_ungrouped_narrow_endpoint')
        qualified,rejected=fr._qualified_endpoint_neckdown_tracks(child,tracks,width,
            required_clearance=gap)
        if rejected or {force._uid(t) for t in qualified}!=ids:
            raise ValueError('saved_cell_narrow_endpoint_geometry_refused:'+str(rejected))
        if net=='GND':
            # Each complete narrow component must start at a recompiled
            # actual Ground obligation, not a convenient unrelated fine pad.
            unseen={force._uid(t):t for t in tracks}
            while unseen:
                first=unseen.pop(min(unseen));component=[first];queue=[first]
                while queue:
                    t=queue.pop();ends={tuple(t.GetStart()),tuple(t.GetEnd())}
                    for uid,peer in list(unseen.items()):
                        if ends & {tuple(peer.GetStart()),tuple(peer.GetEnd())}:
                            component.append(peer);queue.append(peer);del unseen[uid]
                launch=[pads.get(r.get('a',{}).get('pad_uuid')) for r in requests.values()
                    if r['kind']=='ground' and r['net']=='GND']
                launch=[p for p in launch if p is not None and p.GetNetname()=='GND'
                    and min(p.GetSize())<width and p.IsOnLayer(face)
                    and any(p.GetEffectiveShape(face).Collide(at,0)
                        for t in component for at in (t.GetStart(),t.GetEnd()))]
                if not launch:raise ValueError('saved_cell_ground_prefix_has_no_recompiled_launch')
            legal.update(ids)
            proofs.append(dict(kind='typed_local_ground_endpoint_geometry',track_uuids=sorted(ids),
                aggregate_ground_current_inferred=False))
            continue
        contract=contracts[net]
        with force._thermal_hint(board_hint):before=cells._supply_current_widths(parent,net)
        if _stable(before)!=_stable(contract):raise ValueError('cell_prefix_original_current_contract_changed')
        for r in requests.values():
            expected=r.get('unchanged_full_rail_current_contract')
            if r['net']==net and expected is not None and _stable(expected)!=_stable(contract):
                raise ValueError('cell_prefix_recompiled_request_current_mismatch')
        if net not in supply:
            # Preserve the whole original authorised routing-face contract.
            # An exact new F.Cu prefix may terminate at a retained through
            # axis whose full-width throat is on B.Cu. That is not capacity
            # credit for the via, nor permission to route on a reference face.
            planes={child.GetLayerID(n) for n in fr.plane_layers(child)}
            enabled=set(child.GetEnabledLayers().CuStack())
            import cec_source_face_widths as source_widths
            actual_widths=source_widths.envelope(parent,requests,net,before)
            # Native display aliases (e.g. SIG2) identify routing roles, not
            # physical stackup copper. Current physics must use the actual
            # native layer ID's canonical thickness, never the user's name.
            widths={fab.COPPER_LAYER_IDS[int(l)]:max(actual_widths[l],w)/1e6
                for l,w in contract['required_by_layer_nm'].items()
                if l in enabled-planes and not any(label in child.GetLayerName(l).upper()
                    for label in ('GND','PWR'))}
            supply[net]=dict(current_authority=contract['current_authority'],
                profile=contract['profile'],authority_refs=[contract['current_authority'].get('source'),board_hint],
                routing_layers=sorted(widths),required_by_layer_mm=widths)
        supply_ids.update(ids)
    if supply_ids:
        import cec_full_current_supply_prefix as prefix
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('cell_prefix_receiving_deadline')
        context={} if source_proposal is None else dict(source_board=parent,source_proposal=source_proposal)
        received=prefix.receive(child,supply,track_uuid_scope=supply_ids,
            retained_via_uuids=[force._uid(t) for t in parent.GetTracks() if t.GetClass()=='PCB_VIA'],
            timeout_s=min(10.,remaining),**context)
        if not received['complete'] or set(received['track_uuids'])!=supply_ids:
            raise ValueError('saved_cell_whole_current_prefix_refused:'+str(received))
        legal.update(supply_ids);proofs.append(dict(kind='whole_original_current_endpoint_prefix',proof=received))
    return dict(track_uuids=sorted(legal),proofs=proofs,current_budget_lowered=False)

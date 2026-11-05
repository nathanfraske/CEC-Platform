"""Explicit shorter axis for exclusive Source control/programming returns.

No new hole, current role, reach, dimension, bypass or cut authority.
"""
import math,time,copy
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_cell_row_rebuild as row
import cec_control_shunt_placement as control


def derive(parent,posed,proposal,requests,*,timeout_s=10.):
    if (type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
            or type(requests)not in(list,tuple)or len(requests)>4):
        raise ValueError('bounded_source_control_return_axes_required')
    if not requests:return []
    deadline=time.monotonic()+timeout_s;binding=row._source_binding(parent)
    source=Path(parent.GetFileName()).resolve();epoch=force._code_identity()
    family=force._family(source,proposal['board_hint'])
    def tick():
        if time.monotonic()>=deadline:raise ValueError('source_control_return_axis_deadline')
    tick()
    selected=control.plan(parent,proposal['poses'],board_hint=proposal['board_hint'],
        reference_group_uuids=proposal.get('reference_group_uuids',()),
        timeout_s=min(10.,deadline-time.monotonic()))
    by_pad={q['ground_pad_uuid']:q for q in selected.values()}
    requested={q.get('owner_pad_uuid')for q in requests if type(q)is dict and type(q.get('owner_pad_uuid'))is str}
    programming_by_pad={}
    if requested-set(by_pad):
        import cec_programming_resistor_placement as programming
        actual=programming.plan(parent,proposal['poses'],board_hint=proposal['board_hint'],
            reference_group_uuids=proposal.get('reference_group_uuids',()),
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        programming_by_pad={q['ground_pad_uuid']:q for q in actual.values()}
        if by_pad.keys()&programming_by_pad.keys():raise ValueError('disjoint_Source_control_return_roles_required')
    lands=[{force._uid(p):p for f in b.GetFootprints()for p in f.Pads()}for b in(parent,posed)]
    old={force._uid(t):t for t in parent.GetTracks()};seen=set();result=[]
    import cec_ground_return_policy as policy
    import cec_fab_profile as fab
    import cec_fr as fr
    import cec_decoupler_cell as cells
    for request in requests:
        tick()
        if (type(request)is not dict or set(request)!={'owner_pad_uuid','position_nm'}
                or type(request['owner_pad_uuid'])is not str or request['owner_pad_uuid']in seen
                or request['owner_pad_uuid']not in by_pad.keys()|programming_by_pad.keys()
                or type(request['position_nm'])is not list or len(request['position_nm'])!=2
                or any(type(n)is not int or abs(n)>2000000000 for n in request['position_nm'])):
            raise ValueError('one_fresh_source_control_ground_axis_required')
        uid=request['owner_pad_uuid'];seen.add(uid);a,z=lands[0][uid],lands[1].get(uid)
        if (z is None or force._uid(a.GetParentFootprint())!=force._uid(z.GetParentFootprint())
                or tuple(a.GetPosition())==tuple(z.GetPosition())or a.GetNetname()!='GND'or z.GetNetname()!='GND'):
            raise ValueError('actual_same_source_control_ground_motion_required')
        faces=[int(l)for l in parent.GetEnabledLayers().CuStack()if a.IsOnLayer(l)]
        if len(faces)!=1 or not z.IsOnLayer(faces[0]):raise ValueError('same_source_control_return_face_required')
        face=faces[0]
        tails=[t for t in old.values()if t.GetClass()=='PCB_TRACK'and t.GetNetCode()==a.GetNetCode()
            and t.GetLayer()==face and t.GetEffectiveShape(face).Collide(a.GetEffectiveShape(face),0)]
        if len(tails)!=1:raise ValueError('one_source_control_ground_tail_required')
        tail=tails[0];axis=[]
        for via in old.values():
            tick()
            if via.GetClass()!='PCB_VIA'or via.GetNetCode()!=a.GetNetCode():continue
            if any(tuple(p)==tuple(via.GetPosition())for p in(tail.GetStart(),tail.GetEnd())):
                axis.append(via)
        if len(axis)!=1:raise ValueError('one_source_control_ground_barrel_required')
        via=axis[0];vid=force._uid(via)
        incident=[t for u,t in old.items()if u!=vid and t.GetNetCode()==via.GetNetCode()
            and any(t.IsOnLayer(l)and t.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),0)
                for l in parent.GetEnabledLayers().CuStack())]
        peers=[p for u,p in lands[0].items()if u!=uid and p.GetNetCode()==via.GetNetCode()
            and any(p.IsOnLayer(l)and p.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),0)
                for l in parent.GetEnabledLayers().CuStack())]
        if ([force._uid(t)for t in incident]!=[force._uid(tail)]or peers or tail.GetParentGroup()is not None
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.TopLayer()!=pcbnew.F_Cu
                or via.BottomLayer()!=pcbnew.B_Cu or not fab.local_pofv_via_decision(parent,via)[0]):
            raise ValueError('exclusive_source_control_ground_dogbone_required')
        spec=fr._project_netclass_resolver(parent.GetFileName())('GND')
        floor=max(int(parent.GetDesignSettings().m_TrackMinWidth),math.ceil(spec['track_width']*1e6))
        if tail.GetWidth()!=floor:raise ValueError('exact_full_source_ground_class_tail_required')
        if (any(via.GetWidth(layer)<math.ceil(spec['via_diameter']*1e6)
                    for layer in parent.GetEnabledLayers().CuStack()if via.IsOnLayer(layer))
                or via.GetDrillValue()<math.ceil(spec['via_drill']*1e6)):
            raise ValueError('source_ground_barrel_below_exact_class_floor')
        reach=policy.reach(z,{})
        after=math.dist(tuple(z.GetPosition()),request['position_nm'])
        before=math.dist(tuple(a.GetPosition()),tuple(via.GetPosition()))
        if not 0<after<=reach*1e6 or not after+10000<before:
            raise ValueError('shorter_source_local_ground_return_required')
        record=dict(uuid=vid,owner_pad_uuid=uid,position_nm=list(request['position_nm']),
            source_tail_uuid=force._uid(tail),maximum_return_nm=round(reach*1e6),source_full_width_nm=floor)
        key='source_control_shunt'if uid in by_pad else 'source_programming_resistor'
        record[key]=copy.deepcopy((by_pad if uid in by_pad else programming_by_pad)[uid])
        result.append(record)
    tick()
    if (row._source_binding(parent)!=binding or force._code_identity()!=epoch
            or force._family(source,proposal['board_hint'])!=family):
        raise ValueError('source_control_return_live_inputs_changed')
    tick();return result


def apply_and_promote(transport,derived):
    """Keep canonical control-owned seats in every existing barrel enumeration.

    This is constructor bookkeeping, never a saved proof. Every receiver
    independently reruns derive and the exact existing native transport.
    """
    if not derived:return
    expected={q['uuid']:q for q in derived}
    rows=transport['explicitly_reproved_private_signal_return_reseats']
    found={q['uuid']:q for q in rows if q['uuid']in expected}
    if found.keys()!=expected.keys():raise ValueError('complete_control_return_native_seating_required')
    old={q['uuid']for q in transport['source_process_barrel_motion']}
    if old&expected.keys():raise ValueError('duplicate_control_return_barrel_transform')
    for uid,q in expected.items():
        source_role=q.get('source_programming_resistor')
        if source_role is not None:
            import cec_programming_resistor_placement as programming
            label=programming.ground_root(source_role,pad_uuid=q['owner_pad_uuid'],
                reference=source_role['source_resistor_identity']['reference'])
            if not programming.ground_root_label(label):raise ValueError('typed_programming_return_promotion_required')
            owner=source_role['resistor_uuid']
        else:owner=q['source_control_shunt']['cap_uuid']
        proof=copy.deepcopy(found[uid]);proof.update(source_owner_pad_uuids=[q['owner_pad_uuid']],
            owner_footprint_uuids=[owner],
            actual_source_ownership_basis='bounded_native_smd_dogbone',
            source_control_shunt_return_axis=copy.deepcopy(q),
            original_barrel_geometry_count_and_relative_owner_seat_preserved=False,
            original_barrel_geometry_and_count_preserved=True)
        transport['source_process_barrel_motion'].append(proof)
    transport['explicitly_reproved_private_signal_return_reseats']=[q for q in rows if q['uuid']not in expected]
    transport['source_control_shunt_ground_return_axes']=copy.deepcopy(derived)

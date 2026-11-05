"""Mandatory Source-owned front-side measurement corridors in a moved cell.

An actual manufacturer/shunt demand, not a caller's net or line drawing,
owns each corridor. Its native strokes can explain a separately qualified
foreign-lead cut. The macro MUST subsequently build that exact simple path;
an unused corridor never grants retirement authority. Current contracts,
Source force copper, layer policy, field, craft and saved receiving remain.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

import pcbnew
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_fr as fr
import cec_isolated_measurement_completion as isolated
import cec_measurement_terminal_route as terminal
import cec_native_placement_context as native


def _deadline(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=10.:
        raise ValueError('bounded_required_measurement_corridor_lease')
    return time.monotonic()+seconds


def _remaining(deadline):
    value=deadline-time.monotonic()
    if value<=0:raise ValueError('required_measurement_corridor_deadline')
    return min(10.,value)


def requests(values):
    """Validate geometry-only requests; no role or authority follows."""
    if type(values) not in (list,tuple) or len(values)>4:
        raise ValueError('bounded_required_measurement_corridors')
    result=[];seen=set()
    for value in values:
        if (type(value) is not dict or set(value)!={'pad_uuid','points_nm'}
                or type(value['pad_uuid']) is not str or not value['pad_uuid']
                or value['pad_uuid'] in seen or type(value['points_nm']) not in (list,tuple)
                or not 2<=len(value['points_nm'])<=isolated.MAX_TRACKS+1):
            raise ValueError('exact_unique_measurement_corridor_request')
        points=value['points_nm']
        if any(type(p) not in (list,tuple) or len(p)!=2
                or any(type(v) is not int or abs(v)>1000000000 for v in p) for p in points):
            raise ValueError('literal_integer_measurement_corridor_points')
        for a,b in zip(points,points[1:]):
            dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
            if not (dx or dy) or not (dx==0 or dy==0 or dx==dy):
                raise ValueError('canonical_nonempty_measurement_corridor')
        if sum(math.dist(a,b) for a,b in zip(points,points[1:]))>isolated.MAX_PATH_LENGTH_NM:
            raise ValueError('bounded_measurement_corridor_length')
        from shapely.geometry import LineString
        if tuple(points[0])==tuple(points[-1]) or not LineString(points).is_simple:
            raise ValueError('simple_measurement_corridor_required')
        seen.add(value['pad_uuid'])
        result.append(dict(pad_uuid=value['pad_uuid'],points_nm=[list(p) for p in points]))
    return result


def _land(pad,deadline):
    value=native._native_stationary_land(pad,deadline)
    if value is None:raise ValueError('known_native_measurement_corridor_land_required')
    return hashlib.sha256(repr(value).encode()).hexdigest()


def plan(parent,private,proposal,values,*,timeout_s=10.):
    deadline=_deadline(timeout_s);values=requests(values)
    if not values:return [],[]
    source=Path(parent.GetFileName()).resolve(strict=True);binding=row._source_binding(parent)
    digest=force._hash(source);epoch=force._code_identity();family=force._family(source,proposal['board_hint'])
    if (proposal.get('source_native_binding')!=binding
            or row._source_binding(pcbnew.LoadBoard(str(source)))!=binding):
        raise ValueError('literal_saved_measurement_corridor_source_required')
    old={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    live={force._uid(p):p for f in private.GetFootprints() for p in f.Pads()}
    proofs=[];columns=[];nets=set()
    for value in values:
        _remaining(deadline);uid=value['pad_uuid']
        if uid not in old or uid not in live:raise ValueError('existing_measurement_corridor_input_required')
        before,pad=old[uid],live[uid];owner=pad.GetParentFootprint().GetReference()
        if (owner not in proposal['poses'] or pad.GetParentFootprint().IsDNP()
                or tuple(pad.GetPosition())==tuple(before.GetPosition())
                and pad.GetParentFootprint().GetOrientationDegrees()==before.GetParentFootprint().GetOrientationDegrees()):
            raise ValueError('actual_moved_source_measurement_corridor_owner_required')
        pose=proposal['poses'][owner]
        if (type(pose) not in (list,tuple) or len(pose)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in pose)):
            raise ValueError('exact_declared_measurement_corridor_pose_required')
        expected_board=pcbnew.LoadBoard(str(source))
        expected=expected_board.FindFootprintByReference(owner)
        expected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in pose[:2])))
        expected.SetOrientationDegrees(pose[2])
        expected_pad=next((p for p in expected.Pads() if force._uid(p)==uid),None)
        from cec_footprint_fields import footprint_properties
        if (expected_pad is None or _land(expected_pad,deadline)!=_land(pad,deadline)
                or tuple(pad.GetParentFootprint().GetPosition())!=tuple(expected.GetPosition())
                or abs((pad.GetParentFootprint().GetOrientationDegrees()-pose[2]+180)%360-180)>1e-9
                or pad.GetParentFootprint().GetValue()!=expected.GetValue()
                or footprint_properties(pad.GetParentFootprint())!=footprint_properties(expected)):
            raise ValueError('input_must_be_exact_rigid_source_owner_at_declared_pose')
        fresh=isolated.plan(parent,source,board_hint=proposal['board_hint'],pad_uuid=uid,
            timeout_s=_remaining(deadline))
        if not fresh['complete']:raise ValueError('positive_source_front_only_measurement_corridor_required')
        typed=fresh['request'];demand=copy.deepcopy(typed['demand']);target_uid=demand['target_uuid']
        if (demand['source_input_island_uuids']!=[uid] or target_uid not in live
                or pad.GetNetname()!=demand['net'] or demand['net'] in nets
                or pad.GetNumber()!=before.GetNumber()
                or pad.GetSize()!=before.GetSize() or pad.GetShape()!=before.GetShape()
                or pad.GetAttribute()!=before.GetAttribute()
                or tuple(pad.GetLayerSet().CuStack())!=(pcbnew.F_Cu,)
                or pad.GetParentFootprint().GetFPIDAsString()!=before.GetParentFootprint().GetFPIDAsString()
                or _land(old[target_uid],deadline)!=_land(live[target_uid],deadline)):
            raise ValueError('unchanged_singleton_input_and_stationary_shunt_land_required')
        points=value['points_nm'];target=live[target_uid]
        if (points[0]!=list(pad.GetPosition())
                or not target.GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*points[-1]),0)):
            raise ValueError('corridor_must_join_actual_posed_input_and_source_shunt_land')
        width=typed['width_nm'];demand['a_nm']=list(pad.GetPosition())
        made=[]
        for index,(a,b) in enumerate(zip(points,points[1:])):
            edge=pcbnew.PCB_TRACK(private);edge.SetStart(pcbnew.VECTOR2I(*a));edge.SetEnd(pcbnew.VECTOR2I(*b))
            edge.SetWidth(width);edge.SetLayer(pcbnew.F_Cu);edge.SetNetCode(pad.GetNetCode())
            name='required-source-measurement:'+force._hash(source)+':'+uid+':'+repr(points)+':'+str(index)
            edge.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,name))))
            made.append(edge)
        proofs.append(dict(schema=1,scope='source_required_front_measurement_corridor',source=str(source),
            source_sha256=digest,source_native_binding=binding,board_hint=proposal['board_hint'],
            code_identity=epoch,pad_uuid=uid,target_pad_uuid=target_uid,owner=owner,
            target_pose=list(proposal['poses'][owner]),net=demand['net'],points_nm=points,width_nm=width,
            clearance_nm=max(200000,int(parent.GetDesignSettings().m_MinClearance),
                int((fr._project_netclass_resolver(str(source),board=parent)(demand['net']) or {}).get('clearance',.2)*1e6)),
            face=int(pcbnew.F_Cu),source_demand=demand,ratified_layer_policy=typed['layer_policy'],
            nonload_width_basis=typed['nonload_width_basis'],actual_land_sha256=_land(pad,deadline),
            actual_target_land_sha256=_land(target,deadline),
            proposal_track_uuids=[force._uid(e) for e in made],mandatory_exact_saved_path=True,
            cuts_current_or_layer_or_Kelvin_or_release_authorized=False))
        columns.extend(made);nets.add(demand['net'])
    if (row._source_binding(parent)!=binding or force._hash(source)!=digest or force._code_identity()!=epoch
            or force._family(source,proposal['board_hint'])!=family):
        raise ValueError('measurement_corridor_source_changed')
    _remaining(deadline)
    return proofs,columns


def rederive(board,proof,*,timeout_s=10.):
    deadline=_deadline(timeout_s)
    source=Path(proof['source'])
    if (force._hash(source)!=proof['source_sha256'] or force._code_identity()!=proof['code_identity']):
        raise ValueError('required_measurement_corridor_source_or_code_changed')
    parent=pcbnew.LoadBoard(str(source))
    fresh,_=plan(parent,board,dict(source_native_binding=row._source_binding(parent),
        board_hint=proof['board_hint'],poses={proof['owner']:proof['target_pose']}),
        [dict(pad_uuid=proof['pad_uuid'],points_nm=proof['points_nm'])],timeout_s=_remaining(deadline))
    if json.loads(json.dumps(fresh[0]))!=proof:raise ValueError('required_measurement_corridor_stale_or_forged')
    _remaining(deadline)


def entry_ops(board,proof,*,timeout_s=10.):
    deadline=_deadline(timeout_s);rederive(board,proof,timeout_s=_remaining(deadline))
    ops=[('trk',tuple(a),tuple(b),proof['width_nm'],proof['face'])
        for a,b in zip(proof['points_nm'],proof['points_nm'][1:])]
    code=board.GetNetcodeFromNetname(proof['net']);cache={}
    detail=dict(found=False,routing_admitted=False,release_authority=False)
    checks=[]
    for _,a,b,width,face in ops:
        _remaining(deadline)
        start,end=pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b)
        checks.append(bool(fr._edge_leg_clear(board,start,end,width//2+proof['clearance_nm']) and
            fr._tap_foreign_clear(board,start,end,width,face,proof['clearance_nm'],{code},foreign_cache=cache)))
    detail['actual_native_clearance_and_edge']=checks
    guard=terminal.contact_guard(board,proof['source_demand'],width_nm=proof['width_nm'],deadline=deadline)
    detail['actual_source_pickup_and_force_contacts']=guard['operations'](ops)
    field=terminal.assess_path_field(board,ops,net=proof['net'],deadline=deadline,
        netclass_resolver=fr._project_netclass_resolver(str(board.GetFileName()),board=board),
        board_hint=proof['board_hint'])
    craft=terminal.assess_path_craft(board,ops,net=proof['net'],deadline=deadline)
    detail.update(field=field,craft=craft)
    good=all(checks) and detail['actual_source_pickup_and_force_contacts'] is True and all(
        proof.get('ok') is True and proof.get('complete') is True for proof in (field,craft))
    _remaining(deadline);detail['found']=good
    return (ops if good else []),detail


def _compact(points):
    result=[]
    for at in points:
        at=tuple(at)
        if result and at==result[-1]:continue
        while len(result)>1:
            a,b=result[-2:];u=(b[0]-a[0],b[1]-a[1]);v=(at[0]-b[0],at[1]-b[1])
            if u[0]*v[1]!=u[1]*v[0] or u[0]*v[0]+u[1]*v[1]<=0:break
            result.pop()
        result.append(at)
    return result


def receive(board,proofs,incoming,*,timeout_s=10.,saved_path=None):
    deadline=_deadline(timeout_s);observed=[];saved=None;literal_text=None
    if proofs and saved_path is not None:
        saved=Path(saved_path).resolve(strict=True)
        if (saved!=Path(board.GetFileName()).resolve(strict=True)
                or saved.stat().st_size>64*1024*1024):
            raise ValueError('exact_bounded_saved_measurement_corridor_board_required')
        saved_digest=force._hash(saved)
        literal_text=saved.read_text(encoding='utf-8')
        binding=row._source_binding(board)
        if row._source_binding(pcbnew.LoadBoard(str(saved)))!=binding:
            raise ValueError('saved_measurement_corridor_native_board_mismatch')
        _remaining(deadline)
    for proof in proofs:
        rederive(board,proof,timeout_s=_remaining(deadline))
        pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
        root,target=pads[proof['pad_uuid']],pads[proof['target_pad_uuid']]
        if (_land(root,deadline)!=proof['actual_land_sha256'] or
                _land(target,deadline)!=proof['actual_target_land_sha256']):
            raise ValueError('required_saved_measurement_corridor_land_changed')
        material=[t for t in board.GetTracks() if force._uid(t) in incoming and t.GetNetname()==proof['net']]
        if literal_text is not None:
            # KiCad can normalize an authored wrong-net chain to its touched
            # pad on reload. Native geometry alone cannot establish the
            # identity of the incoming saved copper.
            import cec_source_literal_additions as literal
            names=literal.incoming_copper_nets(literal_text,{force._uid(t) for t in material})
            if any(net!=proof['net'] for net in names.values()):
                raise ValueError('required_saved_measurement_corridor_literal_net_mismatch')
        ops=isolated._ordered_ops(material,root,target,width_nm=proof['width_nm'],deadline=deadline)
        actual=[ops[0][1],*[op[2] for op in ops]]
        if _compact(actual)!=_compact(proof['points_nm']):
            raise ValueError('required_saved_measurement_corridor_not_constructed')
        observed.append(dict(pad_uuid=proof['pad_uuid'],new_track_uuids=sorted(force._uid(t) for t in material),
            exact_required_corridor_constructed=True,collinear_subdivision_only=True,
            current_or_Kelvin_qualified=False,release_authority=False))
        _remaining(deadline)
    if saved is not None:
        if force._hash(saved)!=saved_digest or row._source_binding(board)!=binding:
            raise ValueError('saved_measurement_corridor_board_changed')
        _remaining(deadline)
    return observed

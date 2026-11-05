"""Add real full-width metal at an already connected weak orthogonal contact.

This is NOT a relaxed contact-site test. Exact positive Source capsule overlap
owns the request; Source current authority owns the unchanged width. A single
new centreline extension creates substantial contact without retiring either
operand. Saved material receiving is separate from the still-mandatory whole
native DRC, current, field, craft, Kelvin, partition and Ground-return checks.
No via, pour, rule, placement, current-sharing or release authority is granted.
"""
import math
from pathlib import Path
import time
import uuid

import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import cec_additive_route_receiving as additive
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_full_current_planar_reflow as full
import cec_native_current_capture as capture

SCOPE='source_full_width_orthogonal_contact_strengthening-v1'


def _budget(value):
    if type(value)not in(int,float)or not math.isfinite(value)or not 0<value<=9.1:
        raise ValueError('bounded_contact_strengthening_deadline_required')
    return time.monotonic()+value


def _geometry(first,second,face,*,maximum_reach_nm=2_000_000):
    """Finite exact cardinal capsule test; no rounded-distance fit credit."""
    if type(maximum_reach_nm)is not int or not 0<maximum_reach_nm<=2_000_000:
        raise ValueError('bounded_integer_contact_strengthening_reach_required')
    items=(first,second)
    if (any(t.GetClass()!='PCB_TRACK'or t.HasSolderMask()for t in items)
            or first.GetNetCode()<=0 or first.GetNetCode()!=second.GetNetCode()
            or any(int(t.GetLayer())!=face for t in items)
            or not 0<first.GetWidth()==second.GetWidth()<=10_000_000):
        raise ValueError('equal_positive_width_same_net_face_straight_contacts_required')
    width=first.GetWidth();axes=[]
    for item in items:
        a,b=tuple(item.GetStart()),tuple(item.GetEnd())
        if a==b or not(a[0]==b[0]or a[1]==b[1]):
            raise ValueError('nondegenerate_exact_cardinal_contact_operands_required')
        axes.append(0 if a[1]==b[1]else 1)
    if axes[0]==axes[1]:raise ValueError('perpendicular_contact_operands_required')
    if not first.GetEffectiveShape(face).Collide(second.GetEffectiveShape(face),0):
        raise ValueError('existing_actual_native_contact_required')
    proposals=[]
    for stem,bar,axis in ((first,second,axes[0]),(second,first,axes[1])):
        a,b=tuple(stem.GetStart()),tuple(stem.GetEnd());c,d=tuple(bar.GetStart()),tuple(bar.GetEnd())
        for at,far in ((a,b),(b,a)):
            target=list(at);target[axis]=c[axis];target=tuple(target)
            distance=abs(target[axis]-at[axis])
            # The stem extends OUTWARD to the actual other centreline.
            # Strictly positive old overlap refuses tangency and near misses.
            # Restrict this operation to a weak cap contact (<1/4 width).
            if (not 0<distance<=maximum_reach_nm or not 0<4*(width-distance)<width
                    or (target[axis]-at[axis])*(far[axis]-at[axis])>=0
                    or not min(c[1-axis],d[1-axis])<target[1-axis]<max(c[1-axis],d[1-axis])):
                continue
            proposals.append(dict(start_nm=list(at),end_nm=list(target),width_nm=width,
                layer_id=face,net=str(stem.GetNetname()),original_positive_overlap_nm=width-distance,
                source_stem_uuid=force._uid(stem),source_bar_uuid=force._uid(bar)))
    if len(proposals)!=1:raise ValueError('one_exact_weak_outward_orthogonal_contact_required')
    return proposals[0]


def _already_supported(board,geometry):
    a,b=geometry['start_nm'],geometry['end_nm'];axis=0 if a[1]==b[1]else 1
    for item in board.GetTracks():
        if (item.GetClass()!='PCB_TRACK'or item.GetNetname()!=geometry['net']
                or item.GetLayer()!=geometry['layer_id']or item.GetWidth()<geometry['width_nm']):continue
        c,d=tuple(item.GetStart()),tuple(item.GetEnd())
        if (c[1-axis]==d[1-axis]==a[1-axis]
                and min(c[axis],d[axis])<=min(a[axis],b[axis])
                and max(c[axis],d[axis])>=max(a[axis],b[axis])):return True
    return False


def _protected_net(board,net,source):
    import cec_pair_semantics as semantics
    import cec_route_dimensions as dimensions
    # A positive current budget cannot erase project signal intent. This
    # deliberately narrow first operator accepts only the existing ordinary
    # Default/Power classes; unknown/custom or composite protected intent is
    # a refusal, not permission inferred from a wide track or a net name.
    table=dimensions.NetclassTable.from_board_path(source)
    classes=table.assignments.get(net)
    classes=classes if isinstance(classes,list)else[table.resolve_name(net)]
    if any(str(name).casefold()not in('default','power')for name in classes):return True
    if net in fr.coupled_pair_nets(board):return True
    if net in semantics.unresolved_current_monitor_nets(board):return True
    if net in {n for row in semantics.analog_input_pairs(board)for n in(row['p'],row['n'])}:return True
    for fp in board.GetFootprints():
        model=roles.footprint_contract(fp)
        if model and any(p.GetNetname()==net and model['pins'].get(p.GetNumber())=='measurement'for p in fp.Pads()):
            return True
        for pad in fp.Pads():
            if pad.GetNetname()==net and roles.resistive_sensing_endpoint_contract(fp,pad.GetNumber()):return True
    return False


def plan(source,*,board_hint,track_uuids,maximum_reach_nm=2_000_000,timeout_s=9.1):
    """Read-only Source-derived proposal; caller cannot supply XY or a rating."""
    deadline=_budget(timeout_s);source=Path(source).resolve()
    if (not source.is_file()or type(board_hint)is not str or not board_hint
            or type(track_uuids)not in(list,tuple)or len(track_uuids)!=2
            or any(type(u)is not str or not u for u in track_uuids)or len(set(track_uuids))!=2):
        raise ValueError('exact_Source_and_two_unique_native_contact_UUIDs_required')
    sha=force._hash(source);family=force._family(source,board_hint);code=force._code_identity()
    board=pcbnew.LoadBoard(str(source));native=list(board.GetTracks());items={force._uid(t):t for t in native}
    if len(items)!=len(native)or len(native)>16384:raise ValueError('bounded_unique_Source_contact_inventory_required')
    if not set(track_uuids)<=items.keys():raise ValueError('Source_contact_operands_missing')
    pair=[items[u]for u in sorted(track_uuids)];face=int(pair[0].GetLayer())
    if face not in board.GetEnabledLayers().CuStack():raise ValueError('enabled_Source_contact_face_required')
    geometry=_geometry(*pair,face,maximum_reach_nm=maximum_reach_nm);net=geometry['net']
    if _protected_net(board,net,source):raise ValueError('protected_measurement_or_coupled_net_contact_refused')
    kind,domain,contract=full._model(board,source,net,board_hint)
    floor=full._source_width_floor(board,source,contract,face)
    if geometry['width_nm']<floor:raise ValueError('unchanged_full_Source_current_contact_width_required')
    graph=pcbnew.CONNECTIVITY_DATA()
    if (not all(graph.Add(item)for item in pair)
            or force._uid(pair[1])not in {force._uid(i)for i in graph.GetConnectedItems(pair[0])}):
        raise ValueError('already_native_connected_Source_operands_required')
    if _already_supported(board,geometry):raise ValueError('orthogonal_contact_already_centerline_supported')
    with force._thermal_hint(board_hint):
        guard=capture.Guard(board,source,net=net,board_hint=board_hint,
            timeout_s=max(.001,min(2.,deadline-time.monotonic())))
    if (guard.unclassified_owners or not guard(tuple(geometry['start_nm']),tuple(geometry['end_nm']),
            geometry['width_nm'],face)or not guard.complete):
        raise ValueError('Source_control_capture_contact_strengthening_refused')
    incoming=str(uuid.uuid5(uuid.NAMESPACE_URL,SCOPE+':'+sha+':'+':'.join(sorted(track_uuids))))
    if incoming in additive._nodes(source)[1]:raise ValueError('fresh_contact_bridge_identity_required')
    if (force._hash(source)!=sha or force._family(source,board_hint)!=family
            or force._code_identity()!=code or time.monotonic()>=deadline):
        raise ValueError('contact_strengthening_Source_identity_or_deadline_changed')
    return dict(schema=1,scope=SCOPE,source=str(source),source_sha256=sha,source_family=family,
        code_identity=code,board_hint=board_hint,track_uuids=sorted(track_uuids),maximum_reach_nm=maximum_reach_nm,
        geometry=geometry,bridge_uuid=incoming,source_current_domain_kind=kind,source_domain=domain,
        unchanged_current_contract=contract,full_current_width_floor_nm=floor,
        original_items_unchanged=True,new_via_or_zone_authority=False,current_sharing_inferred=False,
        routing_admitted=False,current_qualified=False,release_authority=False)


def _replay(source,proposal,timeout_s):
    if type(proposal)is not dict or proposal.get('scope')!=SCOPE:
        raise ValueError('explicit_Source_contact_strengthening_proposal_required')
    fresh=plan(source,board_hint=proposal['board_hint'],track_uuids=proposal['track_uuids'],
        maximum_reach_nm=proposal['maximum_reach_nm'],timeout_s=timeout_s)
    if fresh!=proposal:raise ValueError('contact_strengthening_fresh_Source_replay_differs')
    return fresh


def construct(source,proposal,*,timeout_s=9.1):
    """Private additive IR only; no saved or clearance/current admission."""
    fresh=_replay(source,proposal,timeout_s);board=pcbnew.LoadBoard(str(source));g=fresh['geometry']
    item=pcbnew.PCB_TRACK(board);item.SetNet(board.FindNet(g['net']));item.SetLayer(g['layer_id'])
    item.SetStart(pcbnew.VECTOR2I(*g['start_nm']));item.SetEnd(pcbnew.VECTOR2I(*g['end_nm']))
    item.SetWidth(g['width_nm']);item.m_Uuid.Clone(pcbnew.KIID(fresh['bridge_uuid']));board.Add(item)
    if (force._hash(source)!=fresh['source_sha256']or force._family(source,fresh['board_hint'])!=fresh['source_family']
            or force._code_identity()!=fresh['code_identity']):raise ValueError('Source_changed_during_contact_construction')
    return board


def write_private(source,directory,proposal,*,timeout_s=9.1):
    """Fresh private family, real Ground refill, literal Source-node retention."""
    import cec_field_coupling as field
    import cec_source_retaining_ses_import as literal
    directory=Path(directory).resolve();source=Path(source).resolve()
    if directory.exists():raise ValueError('new_private_contact_family_required')
    board=construct(source,proposal,timeout_s=timeout_s)
    child=force._copy_family(source,directory);ground=additive._ground_refill(board)
    field._save_field_snapshot(board,child);_,original=additive._nodes(source)
    literal.write_raw(child,literal.retain_replay_source_nodes(source.read_text(),child.read_text(),set(original),set(ground)))
    if (force._hash(source)!=proposal['source_sha256']or force._family(source,proposal['board_hint'])!=proposal['source_family']
            or force._code_identity()!=proposal['code_identity']):raise ValueError('Source_changed_during_contact_save')
    return dict(board=str(child),sha256=force._hash(child),source_retained=True,ground_refilled=ground,
        routing_admitted=False,current_qualified=False,release_authority=False)


def receive(source,candidate,proposal,*,timeout_s=9.1):
    """Exact geometry rederivation, then stock unchanged-flag additive intake.

    Two explicitly separate <=9.1s constituents: proposal rederivation and
    saved material replay. This never grants whole-board route admission.
    """
    result=dict(ok=False,complete=False,errors=[],scope=SCOPE,
        routing_admitted=False,current_qualified=False,release_authority=False)
    try:
        _budget(timeout_s);source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        if source==candidate:raise ValueError('distinct_private_contact_candidate_required')
        fresh=_replay(source,proposal,timeout_s);candidate_family=force._family(candidate,fresh['board_hint'])
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()-new.keys()or new.keys()-old.keys()!={fresh['bridge_uuid']}:
            raise ValueError('exactly_one_new_contact_bridge_required')
        node=new[fresh['bridge_uuid']]
        keys=[s[0]for s in node[1:]if isinstance(s,list)and s]
        if node[0]!='segment'or len(node)!=7 or sorted(keys)!=['end','layer','net','start','uuid','width']:
            raise ValueError('literal_single_plain_contact_segment_required')
        child=pcbnew.LoadBoard(str(candidate));item=next(t for t in child.GetTracks()if force._uid(t)==fresh['bridge_uuid'])
        g=fresh['geometry']
        if (item.GetClass()!='PCB_TRACK'or item.GetNetname()!=g['net']or int(item.GetLayer())!=g['layer_id']
                or list(item.GetStart())!=g['start_nm']or list(item.GetEnd())!=g['end_nm']
                or item.GetWidth()!=g['width_nm']or item.IsLocked()or item.GetParentGroup()is not None
                or item.HasSolderMask()):raise ValueError('saved_contact_geometry_differs_from_exact_Source')
        proof=additive.receive(source,candidate,timeout_s=timeout_s,board_hint=fresh['board_hint'])
        if not proof['ok']or not proof['complete']:raise ValueError('stock_contact_material_replay_refused:'+str(proof['errors']))
        if (force._hash(source)!=fresh['source_sha256']or force._family(source,fresh['board_hint'])!=fresh['source_family']
                or force._family(candidate,fresh['board_hint'])!=candidate_family
                or force._code_identity()!=fresh['code_identity']):raise ValueError('contact_receiving_Source_identity_changed')
        result.update(ok=True,complete=True,source_sha256=fresh['source_sha256'],candidate_sha256=force._hash(candidate),
            fresh_Source_current_and_geometry_rederived=True,stock_additive_material=proof,
            original_contact_predicate_not_relaxed=True,
            whole_native_current_field_craft_Kelvin_partition_and_return_checks_still_required=True)
    except (ValueError,KeyError,TypeError,StopIteration)as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result

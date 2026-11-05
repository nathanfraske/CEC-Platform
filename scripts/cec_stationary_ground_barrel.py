"""Keep literal Source Ground barrels fixed, without promising a new link.

An existing low-power return barrel need not follow its former SMD owner.
Keeping it cannot waive any old partition, return or current requirement.
The actual saved process and reference contacts must be received again
after all new links exist. No new hole, antipad or Ground-access credit.
"""
import json,time
from pathlib import Path
import pcbnew
import cec_cell_row_rebuild as row
import cec_fab_profile as fab
import cec_force_current as force
import cec_ground_return_shortcut as ground
import cec_ordinary_route_receiving as ordinary
import cec_projected_ground_contact as contact


def _qualified(board,via):
    d,h=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
    return bool(fab.board_legal_through_via_geometry(board,d,h)[:2]==(d,h)
        or fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0])


def plan(board,uuids,*,source_path,board_hint,timeout_s=10.):
    if type(timeout_s) not in (int,float) or not 0<timeout_s<=10.:
        raise ValueError('bounded_stationary_ground_source_context_required')
    ids=ordinary._ids(uuids,'stationary_source_ground_barrel',16)
    if not ids:return []
    if source_path is None or type(board_hint) is not str or not board_hint:
        raise ValueError('bounded_stationary_ground_source_context_required')
    deadline=time.monotonic()+timeout_s;source=Path(source_path).resolve()
    if (not source.is_file() or not board.GetFileName()
            or Path(board.GetFileName()).resolve()!=source):
        raise ValueError('literal_saved_stationary_ground_source_required')
    binding=row._source_binding(board);digest=force._hash(source)
    if row._source_binding(pcbnew.LoadBoard(str(source)))!=binding:
        raise ValueError('unchanged_saved_stationary_ground_source_required')
    live={force._uid(t):t for t in board.GetTracks()};proofs=[]
    for uid in sorted(ids):
        if time.monotonic()>=deadline:raise ValueError('stationary_ground_source_plan_deadline')
        via=live.get(uid)
        if (via is None or via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND'
                or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
                or not _qualified(board,via)):
            raise ValueError('qualified_literal_source_ground_barrel_required')
        proofs.append(dict(schema=1,source=str(source),source_sha256=digest,
            source_native_binding=binding,board_hint=board_hint,
            source_reference_via=contact._via_signature(board,via),
            padstack_mode=int(via.Padstack().Mode()),
            actual_saved_reference_contacts=ground._reference_contacts(board,via),
            stationary_source_material_only=True,new_local_connection_received=False,
            old_partitions_and_all_physical_returns_still_required=True,
            current_qualified=False,release_authority=False))
    if (time.monotonic()>=deadline or row._source_binding(board)!=binding or force._hash(source)!=digest):
        raise ValueError('stationary_ground_source_changed_or_expired')
    return json.loads(json.dumps(proofs,allow_nan=False))


def receive(board,proofs,*,timeout_s=10.):
    if (type(proofs) not in (list,tuple) or len(proofs)>16
            or type(timeout_s) not in (int,float) or not 0<timeout_s<=10.):
        raise ValueError('bounded_stationary_ground_saved_receiving_required')
    deadline=time.monotonic()+timeout_s;rows=[];seen=set()
    for proof in proofs:
        left=deadline-time.monotonic()
        if left<=0:raise ValueError('stationary_ground_saved_receiving_deadline')
        source=Path(proof['source']);uid=proof['source_reference_via']['uuid']
        if uid in seen or force._hash(source)!=proof['source_sha256']:
            raise ValueError('unique_unchanged_stationary_ground_source_required')
        fresh=plan(pcbnew.LoadBoard(str(source)),[uid],source_path=source,
            board_hint=proof['board_hint'],timeout_s=min(10.,left))
        if fresh!=[proof]:raise ValueError('stationary_ground_source_proof_not_rederived')
        via=next((t for t in board.GetTracks() if force._uid(t)==uid),None)
        if (via is None or via.GetClass()!='PCB_VIA'
                or contact._via_signature(board,via)!=proof['source_reference_via']
                or int(via.Padstack().Mode())!=proof['padstack_mode']
                or ground._reference_contacts(board,via)!=proof['actual_saved_reference_contacts']
                or not _qualified(board,via)):
            raise ValueError('stationary_ground_saved_barrel_or_live_process_changed')
        seen.add(uid);rows.append(dict(uuid=uid,stationary_native_barrel_and_live_process_reproved=True,
            no_local_ground_connection_credited_by_retention=True,release_authority=False))
    if time.monotonic()>=deadline:raise ValueError('stationary_ground_saved_receiving_deadline')
    return rows


def clearance(board,proof,*,timeout_s=10.):
    """Reprove a literal saved antipad, never grant a new/moved hole a void."""
    if type(timeout_s) not in (int,float) or not 0<timeout_s<=10.:
        raise ValueError('bounded_stationary_ground_clearance_required')
    deadline=time.monotonic()+timeout_s
    result=dict(ok=False,source_antipad_not_new_hole_authority=True,release_authority=False)
    try:
        receive(board,[proof],timeout_s=timeout_s)
        uid=proof['source_reference_via']['uuid']
        via=next(t for t in board.GetTracks() if force._uid(t)==uid)
        import cec_retained_ground_barrel_clearance as retained
        result['ok']=retained.clear(board,via,max(200000,int(board.GetDesignSettings().m_MinClearance)),
            deadline=deadline,source_path=proof['source'],allow_unreserved_ground_refill=True)
        if time.monotonic()>=deadline:raise ValueError('stationary_ground_clearance_deadline')
        if not result['ok']:result['reason']='stationary_source_antipad_or_live_clearance_refused'
    except (ValueError,KeyError,TypeError,OSError,StopIteration) as exc:
        result.update(ok=False,reason=type(exc).__name__+':'+str(exc))
    return result

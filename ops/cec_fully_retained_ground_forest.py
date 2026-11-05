"""A zero Ground cut is a result, not permission to rebuild fixed branches.

Extend only the frozen Source forest's all-tracks-retained case. Every fixed
manufacturer Ground terminal must retain a literal native Source path to an
unchanged process-qualified reference barrel. All held tracks stay literal
in the projected board, and no other cut owner may claim them. Moving lands
still need their own complete connection and required-barrel receiving.
"""
from pathlib import Path
import types

import cec_field_coupling as field
import cec_force_current as force
import cec_stationary_ground_forest as original

POLICY='complete-source-stationary-ground-path-retention-including-zero-cut-v1'
_path=Path(original.__file__).resolve();_digest=force._hash(_path)
_self_path=Path(__file__).resolve();_self_digest=force._hash(_self_path)
_text=_path.read_text()
_old='old,new=items(parent),items(posed);result=copy.deepcopy(proposal);records=[]'
assert _text.count(_old)==1
_text=_text.replace(_old,_old+';fully_retained=[]')
_old='''        try:
            fresh=forks.plan(parent,original['requested_root_pad_uuids'],moving_refs=original['moving_refs'],'''
_new='''        if held==cut:
            # Keeping the ENTIRE old fixed network is stronger than owning
            # a new departure. The old planner correctly refuses an empty
            # cut; do not turn that refusal back into the original big cut.
            required={q['pad_uuid'] for q in original['fixed_ground_terminal_contracts']}
            if {q['pad_uuid'] for q in paths}!=required:continue
            snapshots=[field._field_snapshot_inventory(b) for b in (parent,posed)]
            if any(('track',u) not in snapshots[0] or ('track',u) not in snapshots[1]
                    or snapshots[0]['track',u]!=snapshots[1]['track',u] for u in cut):continue
            cohort[index]=None
            result['retired_track_uuids']=sorted(set(result['retired_track_uuids'])-cut)
            fully_retained.append(dict(original_fork=original,paths=paths,
                kept_source_track_uuids=sorted(cut),fixed_ground_pad_uuids=sorted(required),
                original_source_tracks_and_qualified_roots_literal=True,
                no_fork_departure_reconstruction_remaining=True,
                moving_terminal_connection_and_all_native_saved_partitions_still_required=True,
                no_new_connection_hole_process_or_current_authority=True,release_authority=False))
            continue
        try:
            fresh=forks.plan(parent,original['requested_root_pad_uuids'],moving_refs=original['moving_refs'],'''
assert _text.count(_old)==1;_text=_text.replace(_old,_new)
_old="    if records:result['stationary_ground_path_preservation']=records"
_new="""    if fully_retained:
        result['source_owned_shared_ground_return_forks']=[q for q in cohort if q is not None]
        result['fully_retained_stationary_ground_forks']=fully_retained
    if records:result['stationary_ground_path_preservation']=records"""
assert _text.count(_old)==1;_text=_text.replace(_old,_new)
_old="if peer is not original:other.update(peer['track_uuids'])"
assert _text.count(_old)==1;_text=_text.replace(_old,"if peer is not None and peer is not original:other.update(peer['track_uuids'])")
_module=types.ModuleType('cec_private_fully_retained_ground_forest')
_module.__file__=str(_path);_module.__dict__['field']=field
exec(compile(_text,str(_path),'exec'),_module.__dict__)
_original_refine=_module.refine


def refine(parent,posed,proposal,*,timeout_s=10.):
    tool=_self_path;tool_digest=_self_digest
    if force._hash(_path)!=_digest or force._hash(tool)!=tool_digest:raise ValueError('frozen_source_ground_forest_changed')
    result=_original_refine(parent,posed,proposal,timeout_s=timeout_s)
    if force._hash(_path)!=_digest or force._hash(tool)!=tool_digest:
        raise ValueError('retained_ground_forest_helper_changed')
    return result


def identity():
    if force._hash(_self_path)!=_self_digest or force._hash(_path)!=_digest:
        raise ValueError('frozen_source_ground_forest_changed')
    return dict(policy=POLICY,helper_sha256={str(_path):_digest,
        str(_self_path):_self_digest},
        original_forest_global_module_unchanged=True,source_tracks_retained_not_rebuilt=True,
        no_board_component_coordinate_or_budget_special_case=True,release_authority=False)


def propose_and_restore(parent,posed,proposal,*,timeout_s=10.):
    """Retain proved Source paths after the transporter's temporary leg move.

    Only the ALREADY Source-typed Ground-fork tracks are considered. A
    private transport may have moved a soon-to-be-retired end with its pad.
    Test literal Source retention instead; restore non-retained tracks to
    the exact incoming private state even on refusal. No Source board is
    mutated and no new cut, material, connection or barrel is authorized.
    """
    import math
    if (type(proposal) is not dict or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_literal_source_ground_retention_context_required')
    forks=proposal.get('source_owned_shared_ground_return_forks',[])
    if type(forks) is not list or len(forks)>8:
        raise ValueError('bounded_literal_source_ground_fork_list_required')
    candidates={u for f in forks for u in f['track_uuids']}
    if len(candidates)>512:raise ValueError('bounded_original_ground_track_union_required')
    if not candidates:return refine(parent,posed,proposal,timeout_s=timeout_s)
    old={force._uid(t):t for t in parent.GetTracks()}
    live={force._uid(t):t for t in posed.GetTracks()}
    if not candidates<=old.keys() or not candidates<=live.keys():
        raise ValueError('literal_typed_ground_fork_restoration_items_required')
    def state(t):return (tuple(t.GetStart()),tuple(t.GetEnd()),int(t.GetLayer()),t.GetWidth(),bool(t.IsLocked()))
    def apply(t,s):
        import pcbnew
        t.SetStart(pcbnew.VECTOR2I(*s[0]));t.SetEnd(pcbnew.VECTOR2I(*s[1]));t.SetLayer(s[2]);t.SetWidth(s[3]);t.SetLocked(s[4])
    incoming={u:state(live[u]) for u in candidates};keep=set();result=None
    source_binding=original.binding._source_binding(parent)
    try:
        for u in sorted(candidates):
            if (old[u].GetClass()!=live[u].GetClass() or old[u].GetClass()!='PCB_TRACK'
                    or old[u].GetNetname()!=live[u].GetNetname() or old[u].GetNetname()!='GND'):
                raise ValueError('only_literal_existing_ground_tracks_may_be_restored')
            apply(live[u],state(old[u]))
        result=refine(parent,posed,proposal,timeout_s=timeout_s)
        keep={u for key in ('fully_retained_stationary_ground_forks','stationary_ground_path_preservation')
            for rec in result.get(key,[]) for u in rec['kept_source_track_uuids']}
        if not keep<=candidates:raise ValueError('ground_retention_must_be_subset_of_original_typed_cut')
    finally:
        for u in sorted(candidates-keep):apply(live[u],incoming[u])
    if original.binding._source_binding(parent)!=source_binding:
        raise ValueError('ground_retention_changed_original_source')
    if keep:
        result['literal_stationary_source_ground_track_restorations']=sorted(keep)
    return result

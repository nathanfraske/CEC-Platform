"""Metadata-only template derivation, never source cut or routing authority."""
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as binding
import cec_force_current as force
import cec_pair_local_reference_refinement as process

def derive(board,source,track_uuids):
    if (type(track_uuids) not in (list,tuple) or not 2<=len(track_uuids)<=32
            or len(set(track_uuids))!=len(track_uuids)
            or any(type(u) is not str or not u for u in track_uuids)):
        raise ValueError('bounded_unique_actual_track_template_scope_required')
    source=Path(source).resolve();source_hash=force._hash(source)
    if binding._source_binding(board)!=binding._source_binding(pcbnew.LoadBoard(str(source))):
        raise ValueError('template_requires_actual_unchanged_saved_source')
    _,nodes=additive._nodes(source)
    live={force._uid(t):t for t in board.GetTracks()}
    if not set(track_uuids)<=live.keys() or not set(track_uuids)<=nodes.keys():
        raise ValueError('all_native_source_template_tracks_required')
    tracks=[live[u] for u in track_uuids]
    if any(t.GetClass()!='PCB_TRACK' or t.GetParentGroup() or t.HasSolderMask() for t in tracks):
        raise ValueError('plain_ungrouped_native_track_templates_required')
    def normalized(node):
        return process._process([v for v in node if not (isinstance(v,list) and v and v[0]=='locked')])
    if len({str(normalized(nodes[u])) for u in track_uuids})!=1:
        raise ValueError('source_native_process_may_differ_only_in_lock_strength')
    locked=sorted(force._uid(t) for t in tracks if t.IsLocked())
    template=tracks[0].Duplicate();template.SetLocked(bool(locked))
    if force._hash(source)!=source_hash:raise ValueError('source_template_changed_during_observation')
    return template,dict(source_track_uuids=sorted(track_uuids),source_locked_track_uuids=locked,
        replacement_locked=bool(locked),all_source_process_fields_except_owned_stronger_lock_exact=True,
        source_native_items_not_mutated=True,no_lock_weakened=True,
        source_sha256=source_hash,source_cut_permission_or_net_classification_granted=False,current_or_release_qualified=False)

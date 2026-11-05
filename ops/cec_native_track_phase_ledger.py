"""Atomic actual-node bookkeeping after independent geometry receiving.

This helper grants no geometry/current/clearance authority. It prevents a
typed track phase from registering its removals but forgetting its additions.
Both sets must match the saved native delta before any ledger set is changed.
"""
from pathlib import Path
import cec_additive_route_receiving as native
import cec_force_current as force


def register(source,candidate,proof,retiring,added_tracks,nets,*,net):
    if not all(type(s) is set for s in (retiring,added_tracks,nets)):
        raise ValueError('native_phase_mutable_set_ledgers_required')
    if (proof.get('ok') is not True or proof.get('complete') is not True
            or proof.get('errors')!=[] or type(net) is not str or not net):
        raise ValueError('independently_received_native_track_phase_required')
    source,candidate=[Path(p).resolve() for p in (source,candidate)]
    if (source==candidate or proof.get('source_sha256')!=force._hash(source)
            or proof.get('candidate_sha256')!=force._hash(candidate)):
        raise ValueError('actual_native_track_phase_identity_required')
    before,after=[native._nodes(p)[1] for p in (source,candidate)]
    old,new=before.keys()-after.keys(),after.keys()-before.keys()
    if (old!=set(proof.get('retired_track_uuids',[])) or new!=set(proof.get('added_native_uuids',[]))
            or not old or not new or any(before[u][0]!='segment' for u in old)
            or any(after[u][0]!='segment' for u in new)):
        raise ValueError('exact_actual_native_track_phase_delta_required')
    retiring.update(old);added_tracks.update(new);nets.add(net)
    return dict(complete=True,retired_track_uuids=sorted(old),added_native_uuids=sorted(new),
        actual_saved_track_delta_registered=True,geometry_or_release_authority=False)

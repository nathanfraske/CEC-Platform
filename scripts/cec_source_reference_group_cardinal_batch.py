"""Explicit disjoint Source reference maps, one untouched-Source preflight.

Requests are (fresh inspect proof, quarter_turns 0..3, integer delta_nm).
This adapter owns only the requested map owners and their exact root ink.
Other physical owner motion/copper admission remain the macro caller's job.
Legacy translation-only APIs are untouched.
"""
import math
import tempfile
import time
from pathlib import Path
import pcbnew
import cec_source_reference_group_transport as single
import cec_field_coupling as field
import cec_source_retaining_ses_import as raw


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _deadline(timeout_s):
    _require(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,
        'bounded_cardinal_reference_batch_required')
    return time.monotonic()+timeout_s


def _tick(deadline):
    _require(time.monotonic()<deadline,'source_cardinal_reference_batch_deadline')


def _native_root(board,path):
    field._save_field_snapshot(board,path)
    return single.syntax._freeze(single.ast._nodes(path)[0])


def _preflight_source(context,board,deadline):
    """Exactly once per batch, before ANY member or owner is modified."""
    parent=context['native']
    _require(parent is not None and single._cardinal_identity(parent)==single._cardinal_identity(board),
        'exact_cardinal_batch_source_native_board_required')
    with tempfile.TemporaryDirectory(prefix='cec-cardinal-batch-preflight-')as directory:
        roots=[_native_root(native,Path(directory)/(str(i)+'.kicad_pcb'))
            for i,native in enumerate((parent,board))]
    _require(roots[0]==roots[1],'exact_cardinal_batch_source_native_serialization_required')
    _tick(deadline)


def _request_source(requests,maximum_translation_mm=10.):
    _require(type(requests)in(list,tuple)and 1<=len(requests)<=8,
        'one_to_eight_explicit_cardinal_maps_required')
    for row in requests:
        _require(type(row)in(list,tuple)and len(row)==3 and type(row[0])is dict,
            'literal_proof_quarter_delta_request_required')
        single._quarter(row[1]);single._delta(row[2],maximum_translation_mm)
        _require({'source','source_sha256','owner_uuid','group_uuid','member_uuids'}<=row[0].keys(),
            'complete_source_map_proof_required')
    source=Path(requests[0][0]['source']).resolve(strict=True)
    _require(all(Path(p['source']).resolve(strict=True)==source and
        p['source_sha256']==requests[0][0]['source_sha256']for p,q,d in requests),
        'one_exact_source_for_all_cardinal_maps_required')
    return source


def _prepare(requests,context,deadline,maximum_translation_mm=10.):
    source=context['source']
    _require(requests[0][0]['source_sha256']==context['sha'],'fresh_independent_cardinal_map_proofs_required')
    selections=[(p['owner_uuid'],p['group_uuid'])for p,q,d in requests]
    _require(len(set(selections))==len(selections),'duplicate_cardinal_map_request')
    fresh=single._inspect_context(context,selections,
        projection_geometries=[single._proof_projection(p)for p,q,d in requests])
    _require(fresh==[p for p,q,d in requests],'fresh_independent_cardinal_map_proofs_required')
    nodes={};derived=[];owned=set()
    for proof,turn,delta in requests:
        _tick(deadline)
        ids=set(proof['member_uuids'])|{proof['group_uuid']}
        _require(not ids&owned,'disjoint_cardinal_map_members_required');owned|=ids
        native,expected=single._cardinal_derive_context(context,proof,turn,delta,maximum_translation_mm)
        _require(not set(expected)&nodes.keys(),'disjoint_cardinal_literal_nodes_required')
        nodes.update(expected);derived.append(native)
    _tick(deadline)
    return source,nodes,derived


def expected_nodes(requests,*,timeout_s=10.,maximum_translation_mm=10.):
    """Independently source-derived union; caller still owes other macro nodes."""
    deadline=_deadline(timeout_s);source=_request_source(requests,maximum_translation_mm)
    with single._source_context(source,timeout_s=timeout_s)as context:
        return _prepare(requests,context,deadline,maximum_translation_mm)[1]


def transform_many(board,requests,*,timeout_s=10.,maximum_translation_mm=10.):
    """All requests validate on scratch before a single caller-board commit."""
    deadline=_deadline(timeout_s);source=_request_source(requests,maximum_translation_mm)
    with single._source_context(source,timeout_s=timeout_s)as context:
        source,nodes,derived=_prepare(requests,context,deadline,maximum_translation_mm)
        _preflight_source(context,board,deadline)
        # No Source parsing or authority decision after the complete preflight.
        single._context_live(context)
        _commit_derived(board,requests,derived)
        _tick(deadline)
        return dict(ok=True,complete=True,source=str(source),source_sha256=context['sha'],
            source_preflight_count=1,owner_uuids=[p['owner_uuid']for p,q,d in requests],
            transformed_member_uuids=sorted(u for p,q,d in requests for u in p['member_uuids']),
            pose_admitted=False,current_authority=False,release_authority=False,
            full_macro_physical_copper_receiving_still_required=True)


def _commit_derived(board,requests,derived):
    old={single.force._uid(i):i for i in [*board.GetFootprints(),*board.GetDrawings()]}
    for (proof,turn,delta),native in zip(requests,derived):
        new={single.force._uid(i):i for i in [*native.GetFootprints(),*native.GetDrawings()]}
        fp=old[proof['owner_uuid']];single._rotate_cardinal_fp(fp,turn)
        fp.SetPosition(new[proof['owner_uuid']].GetPosition())
        for uid in proof['member_uuids']:
            item,target=old[uid],new[uid]
            if item.GetClass()=='PCB_SHAPE':item.SetStart(target.GetStart());item.SetEnd(target.GetEnd())
            elif item.GetClass()=='PCB_TEXT':
                item.SetTextPos(target.GetTextPos());item.SetTextAngle(target.GetTextAngle())


def _verify_native_context(board,requests,context,nodes,deadline,derived):
    owners={p['owner_uuid']for p,q,d in requests}
    with tempfile.TemporaryDirectory(prefix='cec-cardinal-batch-replay-')as directory:
        # Derive on the intact Source, then transform in memory. Loading a
        # hybrid moved-footprint/old-barrel text can relabel copper BEFORE
        # this annotation-only query has even begun.
        expected=pcbnew.LoadBoard(str(context['snapshot']))
        _require(expected is not None,'valid_cardinal_batch_expected_source_required')
        expected.SetFileName(str(context['source']))
        _commit_derived(expected,requests,derived)
        maps=[]
        for index,native in enumerate((expected,board)):
            path=Path(directory)/(str(index)+'.kicad_pcb');single._unfinished_annotation_snapshot(native,path)
            maps.append({u:single.syntax._freeze(n)for u,n in single.ast._nodes(path)[1].items()
                if u in owners or n[0]=='group' or str(n[0]).startswith('gr_')})
        _require(maps[0]==maps[1],'native_cardinal_batch_reference_replay_differs')
    _tick(deadline)
    return dict(ok=True,complete=True,current_authority=False,release_authority=False,
        scope='unfinished_selected_footprints_and_all_root_ink_groups_native_query_only',
        copper_identity_reload_deferred=True,full_field_snapshot_proved=False,
        full_macro_physical_copper_receiving_still_required=True,
        full_macro_physical_copper_and_final_saved_receiving_still_required=True)


def verify_native(source,board,requests,*,timeout_s=10.,maximum_translation_mm=10.):
    """Separate FRESH receiver context, never the producer's private snapshot."""
    deadline=_deadline(timeout_s);bound=_request_source(requests,maximum_translation_mm)
    _require(Path(source).resolve()==bound,'same_cardinal_batch_source_required')
    with single._source_context(bound,timeout_s=timeout_s)as context:
        source,nodes,derived=_prepare(requests,context,deadline,maximum_translation_mm)
        return _verify_native_context(board,requests,context,nodes,deadline,derived)


def verify(source,candidate,requests,*,timeout_s=10.,maximum_translation_mm=10.):
    """Strict standalone saved annotation-only transaction (all root nodes)."""
    deadline=_deadline(timeout_s);bound=_request_source(requests,maximum_translation_mm)
    _require(Path(source).resolve()==bound,'same_cardinal_batch_source_required')
    with single._source_context(bound,timeout_s=timeout_s)as context:
        source,nodes,derived=_prepare(requests,context,deadline,maximum_translation_mm)
        before=context['nodes'];after=single.ast._nodes(candidate)[1]
        _require(before.keys()==after.keys()and all(single.syntax._freeze(after[u])==
            single.syntax._freeze(nodes.get(u,n))for u,n in before.items()),
            'saved_cardinal_batch_literal_replay_differs')
        actual=pcbnew.LoadBoard(str(candidate))
        for p,q,d in requests:
            single._inspect_bound(Path(candidate),actual,after,context['rules'],single.force._hash(candidate),
                owner_uuid=p['owner_uuid'],group_uuid=p['group_uuid'],
                projection_geometry=single._proof_projection(p));_tick(deadline)
        return _verify_native_context(actual,requests,context,nodes,deadline,derived)

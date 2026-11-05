"""Explicitly relock a mixed Ground cut before unchanged span receiving.

The only preparation is unlocked -> locked on EXACT selected source tracks.
It is independently compared against the entire saved source tree; no source
lock is weakened, geometry moved or ownership reclassified. The original
plane-redundant span receiver still owns every electrical and physical cut.
"""
import tempfile
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_native_ground_span_reflow as span
import cec_ordinary_route_receiving as ordinary


def require(condition,message):
    if not condition:raise ValueError(message)


def _projection(source,directory,ids,allowed):
    ids=ordinary._ids(ids,'mixed_ground_source_cut',8);allowed=ordinary._ids(allowed,'mixed_ground_explicit_locked_cut',8)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    require(2<=len(ids)<=8 and ids<=live.keys(),'bounded_actual_mixed_ground_source_required')
    cut=[live[u] for u in sorted(ids)]
    require(all(t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND' and not t.GetParentGroup()
        and not t.HasSolderMask() for t in cut) and len({bool(t.IsLocked()) for t in cut})==2,
        'actual_ungrouped_mixed_lock_ground_tracks_required')
    require(allowed=={force._uid(t) for t in cut if t.IsLocked()},'exact_original_locked_source_permission_required')
    strengthened={force._uid(t) for t in cut if not t.IsLocked()}
    projected=force._copy_family(source,directory)
    for t in cut:t.SetLocked(True)
    field._save_field_snapshot(b,projected)
    old_root,old=additive._nodes(source);new_root,new=additive._nodes(projected)
    require(old.keys()==new.keys(),'relock_preparation_changed_source_population')
    def canonical(root):
        rows=[]
        for node in root:
            uid=next((v[1].strip('"') for v in node[1:] if isinstance(v,list) and v and v[0]=='uuid'),None) if isinstance(node,list) else None
            rows.append([v for v in node if not (isinstance(v,list) and v and v[0]=='locked')]
                if uid in strengthened else node)
        return syntax._freeze(rows)
    require(canonical(old_root)==canonical(new_root) and force._sidecars(source)==force._sidecars(projected),
        'only_exact_unlocked_to_locked_preparation_is_allowed')
    require(all(t.IsLocked() for t in pcbnew.LoadBoard(str(projected)).GetTracks() if force._uid(t) in ids),
        'relock_preparation_must_strengthen_every_selected_track')
    return projected,dict(original_locked_track_uuids=sorted(allowed),newly_locked_track_uuids=sorted(strengthened),
        entire_source_tree_except_exact_stronger_locks_equal=True,no_source_lock_weakened=True,
        no_physical_copper_or_rule_or_current_change=True)


def plan(source,*,board_hint,track_uuids,points_nm,allow_locked_track_uuids):
    source=Path(source).resolve();require(type(board_hint) is str and bool(board_hint),'explicit_mixed_ground_board_context_required')
    with tempfile.TemporaryDirectory(prefix='cec-mixed-ground-plan-') as work:
        projected,relocked=_projection(source,Path(work)/'source',track_uuids,allow_locked_track_uuids)
        scope=span.plan(pcbnew.LoadBoard(str(projected)),track_uuids,points_nm,maximum_extra_nm=0,
            allow_locked_track_uuids=track_uuids)
        require(scope['source_length_nm']-scope['replacement_length_nm']>10000,'mixed_ground_span_must_strictly_shorten')
    return dict(schema=1,source_sha256=force._hash(source),authority_sha256=force._hash(Path(__file__)),
        board_hint=board_hint,track_uuids=sorted(track_uuids),points_nm=points_nm,
        allow_locked_track_uuids=sorted(allow_locked_track_uuids),source_relock_preparation=relocked,
        unchanged_native_span_scope=scope,current_or_release_qualified=False)


def construct(source,proposal):
    args={k:proposal[k] for k in ('board_hint','track_uuids','points_nm','allow_locked_track_uuids')}
    require(plan(source,**args)==proposal,'mixed_ground_stale_or_forged_plan')
    with tempfile.TemporaryDirectory(prefix='cec-mixed-ground-build-') as work:
        projected,_=_projection(Path(source),Path(work)/'source',proposal['track_uuids'],proposal['allow_locked_track_uuids'])
        board=pcbnew.LoadBoard(str(projected));added=span.materialize(board,proposal['unchanged_native_span_scope'])
        board.SetFileName(str(source))
    return board,added


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],current_qualified=False,routing_admitted=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        require(board_hint==proposal['board_hint'],'mixed_ground_board_context_changed')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        args={k:proposal[k] for k in ('board_hint','track_uuids','points_nm','allow_locked_track_uuids')}
        require(plan(source,**args)==proposal,'mixed_ground_stale_or_forged_plan')
        with tempfile.TemporaryDirectory(prefix='cec-mixed-ground-receive-') as work:
            projected,relocked=_projection(source,Path(work)/'source',proposal['track_uuids'],proposal['allow_locked_track_uuids'])
            proof=span.receive(projected,candidate,proposal['unchanged_native_span_scope'],board_hint=board_hint)
        require(proof['ok'] and proof['complete'],'unchanged_native_ground_span_receiving_refused:'+str(proof['errors']))
        require(epoch==force._code_identity() and proposal['authority_sha256']==force._hash(Path(__file__))
            and families==[force._family(p,board_hint) for p in (source,candidate)],'mixed_ground_source_or_authority_changed')
        result.update(ok=True,complete=True,source_relock_preparation=relocked,independent_native_ground_span=proof,
            retired_track_uuids=proof['retired_track_uuids'],added_native_uuids=proof['added_track_uuids'],
            source_span_already_redundant_to_retained_native_copper=True,source_candidate_and_code_unchanged=True,
            original_span_receiver_and_physical_rules_unchanged=True,
            ground_trace_length_saved_mm=(proposal['unchanged_native_span_scope']['source_length_nm']-
                proposal['unchanged_native_span_scope']['replacement_length_nm'])/1e6,
            full_original_parent_current_fields_Kelvin_native_stack_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result

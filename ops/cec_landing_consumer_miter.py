"""Full-width visible miters at source-proved consumer landing approaches.

Half-leg limits remain the default ordinary corner policy. Only exact
remaining-stub containment in a real native retained landing may extend that
search bound here. Existing consumer allocation, root, tap, widths, process,
contact and whole-board current/native receivers remain unchanged.
"""
import json,math,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_consumer_corner_miter as corner
import cec_consumer_group_reconstruction as owner
import cec_copper_echo as syntax
import cec_existing_current_path_refinement as capacity
import cec_field_coupling as field
import cec_force_current as force
import cec_landing_aware_route_geometry as geometry

POLICY='native-landing-contained-visible-consumer-miter-v1'
require=geometry.require
def plain(value):return json.loads(json.dumps(value,allow_nan=False))

def plan(source,*,board_hint,retired_track_uuids,allow_locked_source=False):
    require(type(board_hint) is str and bool(board_hint) and type(allow_locked_source) is bool,
        'explicit_landing_consumer_context_required')
    source=Path(source).resolve();epoch=force._code_identity();board=pcbnew.LoadBoard(str(source))
    ids=capacity.ordinary._ids(retired_track_uuids,'landing_consumer_cut',2)
    require(len(ids)==2,'exact_two_source_consumer_corner_strokes_required')
    live={force._uid(t):t for t in board.GetTracks()};require(ids<=live.keys(),'actual_landing_consumer_tracks_required')
    old=[live[u] for u in sorted(ids)]
    require(all(not t.IsLocked() or allow_locked_source for t in old)
        and len({bool(t.IsLocked()) for t in old})==1,'explicit_uniform_landing_consumer_source_lock_permission_required')
    _,nodes=additive._nodes(source)
    require(len({repr(capacity.chains._process(nodes[u])) for u in ids})==1,'literal_uniform_landing_consumer_process_required')
    scope=owner.plan(board,source,board_hint=board_hint,retired_track_uuids=sorted(ids))
    shape=geometry.hidden_landing_miter(board,old);points=shape['points_nm']
    capacity.geometry._clear_path(board,old,points,time.monotonic()+10.,{})
    boundary=capacity.geometry._boundary_turns(board,old,points,time.monotonic()+10.)
    capacity.no_new_enclosed_voids(board,old,points)
    new=[]
    for a,z in zip(points,points[1:]):
        t=old[0].Duplicate();t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));new.append(t)
    contacts=[i for i in [*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
        if force._uid(i) not in ids and i.GetNetname()==scope['net'] and i.IsOnLayer(old[0].GetLayer())
        and any(t.GetEffectiveShape(t.GetLayer()).Collide(i.GetEffectiveShape(t.GetLayer()),0) for t in old)]
    webs=[corner.retained_contact_proof(i,old,new,old[0].GetLayer(),old[0].GetWidth(),time.monotonic()+10.) for i in contacts]
    require(epoch==force._code_identity(),'landing_consumer_plan_epoch_changed')
    return plain(dict(policy=POLICY,source_sha256=force._hash(source),board_hint=board_hint,code_identity=epoch,
        authority_sha256=force._hash(Path(__file__)),geometry_sha256=force._hash(Path(geometry.__file__)),
        retired_track_uuids=sorted(ids),allow_locked_source=allow_locked_source,source_consumer_scope=scope,
        shape=shape,source_boundaries=boundary,retained_native_contact_webs=webs,
        source_length_nm=sum(t.GetLength() for t in old),candidate_length_nm=sum(t.GetLength() for t in new),
        current_or_width_reduced=False,new_vias_or_parts_authorized=False,release_authority=False))

def construct(source,proposal):
    board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
    exemplar=live[proposal['retired_track_uuids'][0]].Duplicate();owner.subtract(board,proposal['source_consumer_scope'])
    new=[]
    for index,(a,z) in enumerate(zip(proposal['shape']['points_nm'],proposal['shape']['points_nm'][1:])):
        t=exemplar.Duplicate();t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,
            repr((POLICY,proposal['source_sha256'],proposal['retired_track_uuids'],proposal['shape']['points_nm'],index))))))
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));board.Add(t);new.append(force._uid(t))
    owner.assign(board,proposal['source_consumer_scope'],new,[]);additive._ground_refill(board);return board

def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],source_current_reduced=False,new_vias=0,pads_moved=0,
        current_barrel_or_release_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in ('retired_track_uuids','allow_locked_source')})
        require(fresh==proposal,'stale_or_forged_landing_consumer_proposal')
        proof=owner.receive(source,candidate,board_hint=board_hint,retired_track_uuids=proposal['retired_track_uuids'])
        require(proof['ok'] and proof['complete'] and not proof['errors'] and not proof['incoming_via_uuids'],
            'original_consumer_allocation_tap_current_and_native_receiving_required')
        with tempfile.TemporaryDirectory(prefix='cec-landing-consumer-') as work:
            expected=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(construct(source,proposal),expected)
            _,want=additive._nodes(expected);_,got=additive._nodes(candidate)
            require(want.keys()==got.keys() and all(syntax._freeze(n)==syntax._freeze(got[u]) for u,n in want.items()),
                'unowned_saved_landing_consumer_reconstruction')
        require(epoch==force._code_identity() and families==[force._family(p,board_hint) for p in (source,candidate)],
            'landing_consumer_family_or_epoch_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            retired_track_uuids=proposal['retired_track_uuids'],added_native_uuids=proof['incoming_track_uuids'],
            source_consumer_receiving=proof,source_allocation_budget_and_single_tap_exact=True,
            every_saved_native_object_reconstructed=True,landing_hidden_stubs_rederived=True,
            saved_trace_length_mm=(proposal['source_length_nm']-proposal['candidate_length_nm'])/1e6,
            full_native_fields_current_kelvin_pairs_ground_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result

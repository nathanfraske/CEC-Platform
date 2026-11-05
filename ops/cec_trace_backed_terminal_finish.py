"""Full source-width/contact receiving for trace-backed terminal keepers.

The complementary contact-sector owner handles pour-only ports. This owner
requires every actual port to fit the retained trace/frame profile, then uses
the same native floor-partition and original-bounded chord checks. It never
treats absence of a modeled side branch as permission to skip a width witness.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import pcbnew
from shapely.geometry import Polygon
import cec_terminal_shadow_keeper_finish as base
import cec_terminal_contact_sector as sectors

POLICY='source-current-trace-backed-terminal-keeper-finishing-v1'
native=base.native
require=base.require


def plan(source,*,board_hint,zone_uuid,track_uuids,allow_locked_source=False):
    prior=base.plan(source,board_hint=board_hint,zone_uuid=zone_uuid,
        track_uuids=track_uuids,allow_locked_source=allow_locked_source)
    board=pcbnew.LoadBoard(str(source))
    old=next(z for z in board.Zones() if base.force._uid(z)==zone_uuid)
    face=prior['source_configuration']['layers'][0]
    contacts=sectors._contacts(board,prior)
    for uid,contact in contacts:
        inside=contact.CloneDropTriangulation();inside.BooleanIntersection(old.Outline())
        inside.BooleanSubtract(native._poly(prior['points_nm']))
        require(not inside.OutlineCount(),'pour_only_port_requires_contact_sector_owner:'+uid)
    original=sectors._shape(old.Outline())
    profile=sectors._chord_closure(Polygon(prior['points_nm']),original)
    points=sectors._points(profile)
    inherited=sectors._edges(points,sectors._points(original))
    outside=native._poly(points);outside.BooleanSubtract(old.Outline())
    require(not outside.OutlineCount(),'trace_backed_keeper_cannot_expand_authored_owner')
    proxy=old.GetFilledPolysList(face).CloneDropTriangulation()
    proxy.BooleanIntersection(native._poly(points))
    for _,contact in contacts:proxy.Append(contact)
    floor=sectors._floor_receive(old.GetFilledPolysList(face),proxy,contacts,
        prior['full_source_current_width_floor_nm'])
    q=base.plain(prior)
    q.update(policy=POLICY,points_nm=points,authority_sha256=base.force._hash(Path(__file__).resolve()),
        original_terminal_plan_sha256=hashlib.sha256(json.dumps(prior,sort_keys=True).encode()).hexdigest(),
        selected_source_sectors=[],unmodeled_pour_only_port_count=0,
        source_bounded_chord_closure_applied=True,source_floor_preflight=floor,
        inherited_literal_noncanonical_outline_subedges=inherited)
    q['helper_sha256'].update({str(Path(m.__file__).resolve()):base.force._hash(Path(m.__file__))
        for m in (base,sectors)})
    region=q['regional_contract'];region['polygon_nm']=points
    region['actual_fill_envelope_nm']=native._fill_envelope(points,style='chamfer45',margin_nm=4)
    region['regional_fill_binding']=base.regional.source_binding(board,region,time.monotonic()+10.)
    list(sectors._protected_contacts(board,q))
    return base.plain(q)


def construct(source,q):
    require(plan(source,**base._arguments(q))==q,'stale_or_forged_trace_backed_terminal_plan')
    before,after=[pcbnew.LoadBoard(str(source)) for _ in range(2)]
    base.discard_items(after,[t for t in after.GetTracks() if base.force._uid(t) in q['track_uuids']])
    zone=next(z for z in after.Zones() if base.force._uid(z)==q['zone_uuid'])
    face=q['source_configuration']['layers'][0]
    zone.UnFill();zone.Outline().RemoveAllContours();zone.Outline().Append(native._poly(q['points_nm']))
    selected=pcbnew.ZONES();selected.append(zone);base.fill.compile_selected(after,selected,timeout_s=10.)
    actual=base.regional._combine(before,zone.GetFilledPolysList(face),q['regional_contract'],time.monotonic()+10.)
    for _,contact in sectors._protected_contacts(before,q):actual.Append(contact)
    zone.UnFill();zone.SetFilledPolysList(face,actual);zone.SetIsFilled(True)
    return after


def receive_literal(source,candidate,q):
    result=dict(ok=False,complete=False,errors=[],current_or_barrel_qualified=False,
        fresh_whole_native_current_clipped_and_reference_receiving_still_required=True,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        require(source!=candidate,'distinct_saved_trace_backed_terminal_candidate_required')
        epoch=base.force._code_identity()
        families=[base.force._family(p,q['board_hint']) for p in (source,candidate)]
        rebuilt=construct(source,q)
        with tempfile.TemporaryDirectory(prefix='cec-trace-backed-terminal-') as work:
            expected=Path(work)/'board.kicad_pcb';base.field._save_field_snapshot(rebuilt,expected)
            require(base.syntax._freeze(base.additive._nodes(expected)[0])==base.syntax._freeze(base.additive._nodes(candidate)[0]),
                'trace_backed_terminal_changed_unowned_saved_native_evidence')
        require(base.force._sidecars(source)==base.force._sidecars(candidate),'trace_backed_terminal_companions_changed')
        old,new=[base.additive._nodes(p)[1] for p in (source,candidate)]
        require(old.keys()-new.keys()==set(q['track_uuids']) and not new.keys()-old.keys(),
            'exact_trace_backed_stub_retirement_required')
        require(all(base.syntax._freeze(node)==base.syntax._freeze(new[u]) for u,node in old.items()
            if u not in set(q['track_uuids'])|{q['zone_uuid']}),
            'trace_backed_other_objects_and_ground_must_remain_literal')
        before,after=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        prior=base.ordinary._partition(before,time.monotonic()+10.,retired_uuids=set(q['track_uuids']))
        last=base.ordinary._partition(after,time.monotonic()+10.,retained_keys=set().union(*prior))
        require(all(any(p<=z for z in last) for p in prior),'trace_backed_native_partition_lost')
        progress=sectors.observe(before,after,q)
        require(epoch==base.force._code_identity() and families==[base.force._family(p,q['board_hint']) for p in (source,candidate)],
            'trace_backed_family_or_code_changed')
        result.update(ok=True,complete=True,source_sha256=base.force._hash(source),candidate_sha256=base.force._hash(candidate),
            code_identity=epoch,exact_saved_source_native_reconstruction=True,
            all_other_native_items_and_ground_sheets_literal=True,every_surviving_native_partition_preserved=True,
            retired_track_uuids=q['track_uuids'],modified_zone_uuids=[q['zone_uuid']],
            modified_nets=[q['source_configuration']['net']],actual_saved_progress=progress)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError,StopIteration,native.Refused) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def discover(source,*,board_hint,allow_locked_source=False,maximum_trials=32):
    source=Path(source).resolve();digest=base.force._hash(source);epoch=base.force._code_identity()
    found=base.discover(source,board_hint=board_hint,allow_locked_source=allow_locked_source,
        maximum_trials=maximum_trials)
    proposals=[];refusals=list(found['refusals'])
    for row in found['proposals']:
        try:
            q=plan(source,board_hint=board_hint,**row['target'])
            proposals.append(dict(target=row['target'],proposal=q))
        except (ValueError,RuntimeError,KeyError,TypeError,native.Refused) as exc:
            refusals.append(dict(target=row['target'],reason=type(exc).__name__+':'+str(exc)))
    require(digest==base.force._hash(source) and epoch==base.force._code_identity(),
        'trace_backed_readonly_source_or_runtime_changed')
    return dict(ok=True,complete=True,source=str(source),source_sha256=digest,code_identity=epoch,
        maximum_trials=maximum_trials,geometric_menus=found['geometric_menus'],
        geometric_menu_domain_exhausted=found['geometric_menus']<=maximum_trials,
        proposals=proposals,refusals=refusals,actual_geometry_constructed=False,
        finite_search_is_not_all_contours_clean_proof=True,current_or_barrel_qualified=False,release_authority=False)

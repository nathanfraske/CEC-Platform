"""Remove short declared-pair detours whose two ports share ONE real pad.

The unchanged native terminal, not endpoint proximity or a net-name heuristic,
is the bypass. No replacement copper, holes, poses, plane or width change is
owned. Every surviving conductor partition and complete pair metrics must
survive. This does not qualify inherited pair/reference/fabrication debt.
"""
import collections,json,math,tempfile,time
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_force_current as force
import cec_native_ground_span_reflow as lease
import cec_ordinary_route_receiving as ordinary
import cec_paired_route_reconstruction as whole
import cec_pair_local_reference_refinement as pair_owner
import cec_precision_route as precision
import cec_route_quality as quality
import cec_return_escape as surface
from cec_native_items import discard_items


def _polygon(item,face):
    if item.GetClass()=='PAD':return item.GetEffectivePolygon(face).CloneDropTriangulation()
    p=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(p,face,0,1000,pcbnew.ERROR_OUTSIDE);return p


def _port_inside(pad,at,width,face):
    # A conservative OUTSIDE stroke polygon must fit in the literal pad
    # polygon. A rectangle bbox or a tolerance cannot bridge a rounded corner.
    t=pcbnew.PCB_TRACK(pad.GetBoard());t.SetLayer(face);t.SetStart(pcbnew.VECTOR2I(*at));t.SetEnd(pcbnew.VECTOR2I(*at));t.SetWidth(width)
    p=_polygon(t,face);land=_polygon(pad,face)
    if not p.OutlineCount() or land.OutlineCount()!=1 or land.HoleCount(0):return False
    p.BooleanSubtract(land);return not p.OutlineCount()


def _pair(board,source,hint,name):
    q=whole.plan(board,source,board_hint=hint,pair_name=name)
    return q['pair']


def plan(source,*,board_hint,pair_name,lobes,allow_locked_track_uuids=(),timeout_s=10.):
    deadline=lease._deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint or type(pair_name) is not str or not pair_name
            or type(lobes) is not list or not 1<=len(lobes)<=4):
        raise ValueError('bounded_explicit_source_pair_terminal_lobes_required')
    source=Path(source);b=pcbnew.LoadBoard(str(source));pair=_pair(b,source,board_hint,pair_name)
    tracks={force._uid(t):t for t in b.GetTracks()};pads={force._uid(p):p for f in b.GetFootprints() for p in f.Pads()}
    if len(tracks)+len(pads)>16384:raise ValueError('pair_terminal_lobe_native_inventory_bound')
    allowed=ordinary._ids(allow_locked_track_uuids,'pair_terminal_lobe_exact_source_locks',32)
    cuts=set();records=[];width=round(pair['width']*1e6)
    for request in lobes:
        if (type(request) is not dict or set(request)!={'pad_uuid','track_uuids'}
                or type(request['pad_uuid']) is not str or request['pad_uuid'] not in pads):
            raise ValueError('one_literal_native_lobe_terminal_and_track_chain_required')
        ids=ordinary._ids(request['track_uuids'],'pair_terminal_lobe_track_chain',8)
        if len(ids)<2 or not ids<=tracks.keys() or ids&cuts:raise ValueError('disjoint_bounded_native_terminal_lobe_chains_required')
        pad=pads[request['pad_uuid']];face=surface.smd_surface_layer(pad)
        if (face not in (pcbnew.F_Cu,pcbnew.B_Cu) or pad.GetNetname() not in (pair['p'],pair['n'])
                or pad.HasHole() or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_OVAL,pcbnew.PAD_SHAPE_CIRCLE)
                or max(pad.GetSize().x,pad.GetSize().y)>4000000):
            raise ValueError('one_bounded_real_surface_pair_terminal_required')
        items=[tracks[u] for u in sorted(ids)]
        if any(t.GetClass()!='PCB_TRACK' or t.GetNetname()!=pad.GetNetname() or int(t.GetLayer())!=face
                or t.GetWidth()!=width or t.HasSolderMask() or t.GetParentGroup()
                or t.IsLocked() and force._uid(t) not in allowed or t.GetLength()<=0 for t in items):
            raise ValueError('source_pair_width_face_lock_and_process_must_be_exact')
        if any(g.ContainsItem(t) for g in b.Groups() for t in items):raise ValueError('pair_terminal_lobe_group_owned')
        points=pair_owner._chain(items);length=sum(t.GetLength() for t in items)
        if (length>4000000 or length<=10000 or any(not _port_inside(pad,p,width,face) for p in (points[0],points[-1]))):
            raise ValueError('both_full_native_lobe_ports_must_share_the_same_literal_pad')
        poly=pair_owner._capsules(items,face,deadline);outside=poly.CloneDropTriangulation();outside.BooleanSubtract(_polygon(pad,face))
        if not outside.OutlineCount():raise ValueError('visible_terminal_lobe_material_required_not_metadata_cleanup')
        # All uncut same-net contacts must remain inside that terminal. A
        # redundant global plane route cannot authorize losing a side tee.
        contacts=[]
        for item in [*tracks.values(),*pads.values()]:
            if time.monotonic()>=deadline:raise ValueError('pair_terminal_lobe_contact_deadline')
            uid=force._uid(item)
            if uid in ids or uid==force._uid(pad) or item.GetNetname()!=pad.GetNetname() or not item.IsOnLayer(face):continue
            if not any(t.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0) for t in items):continue
            overlap=poly.CloneDropTriangulation();overlap.BooleanIntersection(_polygon(item,face));overlap.BooleanSubtract(_polygon(pad,face))
            if overlap.OutlineCount():raise ValueError('pair_terminal_lobe_has_unowned_outside_pad_contact')
            contacts.append(uid)
        cuts.update(ids);records.append(dict(pad_uuid=request['pad_uuid'],net=pad.GetNetname(),layer=face,
            track_uuids=sorted(ids),ports_nm=[list(points[0]),list(points[-1])],source_length_nm=length,
            retained_contacts_inside_terminal=sorted(contacts)))
    if allowed!={u for u in cuts if tracks[u].IsLocked()}:raise ValueError('only_exact_retired_lobe_source_locks_may_be_authorized')
    return dict(schema=1,source_sha256=force._hash(source),pair=json.loads(json.dumps(pair)),lobes=records,
        allow_locked_track_uuids=sorted(allowed),retired_track_uuids=sorted(cuts),
        source_trace_length_nm=sum(r['source_length_nm'] for r in records),new_holes=0,new_copper=0,
        pair_qualified=False,current_qualified=False,release_authority=False)


def _parameters(proposal):
    return dict(pair_name=proposal['pair']['name'],lobes=[dict(pad_uuid=q['pad_uuid'],track_uuids=q['track_uuids']) for q in proposal['lobes']],
        allow_locked_track_uuids=proposal['allow_locked_track_uuids'])


def construct(source,proposal,*,board_hint):
    fresh=plan(source,board_hint=board_hint,**_parameters(proposal))
    if fresh!=proposal:raise ValueError('stale_or_forged_source_pair_terminal_lobe_plan')
    b=pcbnew.LoadBoard(str(source));discard_items(b,[t for t in b.GetTracks() if force._uid(t) in proposal['retired_track_uuids']]);return b


def discover(source,*,board_hint,pair_name,allow_locked_source=False,timeout_s=10.):
    deadline=lease._deadline(timeout_s)
    if type(allow_locked_source) is not bool:raise ValueError('explicit_pair_lobe_lock_policy_required')
    source=Path(source);b=pcbnew.LoadBoard(str(source));pair=_pair(b,source,board_hint,pair_name)
    tracks={force._uid(t):t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname() in (pair['p'],pair['n'])
        and not t.GetParentGroup() and not t.HasSolderMask() and (not t.IsLocked() or allow_locked_source)}
    incidence=collections.defaultdict(list)
    for u,t in tracks.items():
        for at in (tuple(t.GetStart()),tuple(t.GetEnd())):incidence[(t.GetNetname(),int(t.GetLayer()),at)].append(u)
    seen=set();offers=[];refusals=collections.Counter()
    pads=[p for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname() in (pair['p'],pair['n']) and not p.HasHole()]
    if len(tracks)>512 or len(pads)>128:raise ValueError('bounded_pair_lobe_discovery_required')
    for pad in pads:
        for first,t in tracks.items():
            if t.GetNetname()!=pad.GetNetname() or not pad.IsOnLayer(t.GetLayer()):continue
            for start in (tuple(t.GetStart()),tuple(t.GetEnd())):
                if not pad.HitTest(pcbnew.VECTOR2I(*start)):continue
                uid=first;cursor=start;chain=[]
                while uid not in chain and len(chain)<8:
                    if time.monotonic()>=deadline:raise ValueError('pair_terminal_lobe_discovery_deadline')
                    edge=tracks[uid];ends=[tuple(edge.GetStart()),tuple(edge.GetEnd())]
                    cursor=ends[1] if cursor==ends[0] else ends[0];chain.append(uid)
                    if len(chain)>=2 and pad.HitTest(pcbnew.VECTOR2I(*cursor)):
                        signature=(force._uid(pad),tuple(sorted(chain)))
                        if signature not in seen:
                            seen.add(signature);locked=[u for u in chain if tracks[u].IsLocked()]
                            try:
                                q=plan(source,board_hint=board_hint,pair_name=pair_name,
                                    lobes=[dict(pad_uuid=force._uid(pad),track_uuids=sorted(chain))],allow_locked_track_uuids=locked,
                                    timeout_s=max(.001,min(10.,deadline-time.monotonic())))
                                offers.append(q)
                            except ValueError as exc:refusals[str(exc)]+=1
                        break
                    peers=[u for u in incidence[(edge.GetNetname(),int(edge.GetLayer()),cursor)] if u not in chain]
                    if len(peers)!=1:break
                    uid=peers[0]
    offers.sort(key=lambda q:(-q['source_trace_length_nm'],q['retired_track_uuids']))
    return dict(ok=True,complete=True,offers=offers,refusals=dict(refusals),source_sha256=force._hash(source),
        finite_portfolio_not_global_necessity_proof=True,release_authority=False)


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],pair_qualified=False,current_qualified=False,release_authority=False,
        whole_current_fields_native_DRC_absolute_Kelvin_stack_and_release_still_required=True)
    try:
        deadline=lease._deadline(timeout_s);source,candidate=map(Path,(source,candidate));epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,timeout_s=max(.001,deadline-time.monotonic()),**_parameters(proposal))
        if fresh!=proposal:raise ValueError('saved_pair_terminal_lobe_source_plan_changed')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        if precision.derive_coupled_pairs(str(source),board=parent)!=precision.derive_coupled_pairs(str(candidate),board=child):
            raise ValueError('pair_terminal_lobe_source_pair_contract_changed')
        with tempfile.TemporaryDirectory(prefix='cec-pair-terminal-lobe-') as tmp:
            expected=force._copy_family(source,Path(tmp)/'expected');board=construct(source,proposal,board_hint=board_hint);field._save_field_snapshot(board,expected)
            want_root,want=additive._nodes(expected);got_root,got=additive._nodes(candidate)
            if syntax._freeze(want_root)!=syntax._freeze(got_root) or want.keys()!=got.keys() or any(syntax._freeze(want[u])!=syntax._freeze(got[u]) for u in want):
                raise ValueError('exact_full_source_terminal_lobe_subtraction_differs')
        if force._sidecars(source)!=force._sidecars(candidate):raise ValueError('pair_terminal_lobe_sidecars_changed')
        parts=ordinary._partition(parent,deadline,retired_uuids=proposal['retired_track_uuids']);retained=set().union(*parts)
        updated=ordinary._partition(child,deadline,retained_keys=retained)
        if {frozenset(q) for q in parts}!={frozenset(q) for q in updated}:raise ValueError('pair_terminal_lobe_surviving_native_partition_changed')
        pair=proposal['pair'];complete=precision._native_pair_completion(child,pair)
        if not complete['complete'] or not complete['connected'] or any(q.get('disconnected_copper_uuids') for q in complete['nets'].values()):
            raise ValueError('pair_terminal_lobe_complete_native_pair_required')
        continuous=pair_owner.compare_continuous(pair_owner.continuous_from_board(parent,pair),pair_owner.continuous_from_board(child,pair))
        r['continuous_coupling']=continuous
        if not continuous['ok'] or not continuous['complete']:raise ValueError('pair_terminal_lobe_continuous_coupling_regression:'+str(continuous['errors']))
        samples=[]
        for step in (.5,.25,.1):
            if time.monotonic()>=deadline:raise ValueError('pair_terminal_lobe_saved_metric_deadline')
            with force._thermal_hint(board_hint):rows=[pair_owner.constraints.high_speed_pair_summary(str(p),board=b,sample_mm=step) for p,b in ((source,parent),(candidate,child))]
            values=[next(q for q in row['pairs'] if (q['p'],q['n'])==(pair['p'],pair['n'])) for row in rows]
            comparison=pair_owner.metric_progress(*values,coupling=continuous)
            samples.append(dict(sample_mm=step,before=values[0],after=values[1],comparison=comparison));r['whole_pair_metric_samples']=samples
            if not comparison['ok']:raise ValueError('pair_terminal_lobe_whole_pair_metric_regression:'+str(comparison['errors']))
        craft=[quality.analyze_board(b) for b in (parent,child)]
        if any(craft[1][k]>craft[0][k] for k in ('issue_count','non_octilinear_count')):raise ValueError('pair_terminal_lobe_whole_trace_craft_worsened')
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:raise ValueError('pair_terminal_lobe_sources_or_code_changed')
        r.update(ok=True,complete=True,code_identity=epoch,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),pair=pair,
            source_family_and_code_unchanged=True,retired_track_uuids=proposal['retired_track_uuids'],added_native_uuids=[],
            shortened_centerline_mm=proposal['source_trace_length_nm']/1e6,new_holes=0,new_copper=0,
            every_surviving_native_conductor_partition_identical=True,all_original_pads_barrels_planes_poses_rules_and_other_tracks_exact=True,
            continuous_coupling=continuous,whole_pair_metric_samples=samples,exact_native_pair_completion=complete,
            unsupported_source_reference_debt_not_qualified=True,no_replacement_copper_or_new_reference_deficit=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r

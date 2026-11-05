"""Private same-FPID optional nonpolar ink omission and library-context proof.

This scope owns no physical/source-part or whole-stage admission authority.
Every selected FPID instance receives the same original-template derivative.
"""
import json
import math
import re
import tempfile
import time
import copy
import os
from contextvars import ContextVar
from pathlib import Path

import pcbnew
import cec_ink_only_variant as ink
import cec_force_current as force
import cec_native_library_context as libraries
import cec_source_retaining_ses_import as raw
import cec_source_reference_group_transport as maps

_STAGED_PRINT = ContextVar('cec_staged_print',default=None)


def _need(ok, reason):
    if not ok:raise ValueError(reason)


def _omitted(text, graphics):
    selected=set(graphics);spans=raw.children(text);cuts=[]
    for a,b in spans:
        node=ink._node(text[a:b])
        identity=ink._uid(node)or 'literal:'+ink._digest(text[a:b])
        if identity in selected:
            _need(node[0]=='fp_line','only_literal_optional_body_lines_may_be_omitted')
            cuts.append((a,b,''))
    _need(len(cuts)==len(selected),'complete_unique_literal_optional_line_inventory_required')
    return ink._edits(text,cuts)


def _template_lines(path):
    text=path.read_text();rows=[]
    for a,b in raw.children(text):
        node=ink._node(text[a:b])
        # These exact legacy node TYPES are retained fields, not optional ink.
        # User text or other text roles remain functional/unknown artwork.
        if node[0]=='fp_text'and len(node)>2 and node[1]in('reference','value'):continue
        if node[0].startswith('fp_')and any(isinstance(c,list)and c[:1]==['layer']and c[1]in('"F.SilkS"','"B.SilkS"')for c in node):
            _need(node[0]=='fp_line','functional_or_unknown_template_ink_refused')
            rows.append(ink._uid(node)or 'literal:'+ink._digest(text[a:b]))
    _need(len(rows)==2 and len(set(rows))==2,'two_exact_optional_template_strokes_required')
    return rows


def _physical_match(actual, template, *, expected_cache=None, template_key=None):
    """Only the unique literal Fab reference field may retain an instance angle."""
    owner=pcbnew.BOARD();owner.SetCopperLayerCount(actual.GetBoard().GetCopperLayerCount());owner.Add(template)
    if actual.IsFlipped():template.Flip(pcbnew.VECTOR2I(0,0),False)
    template.SetOrientationDegrees(actual.GetOrientationDegrees());template.SetPosition(actual.GetPosition())
    face=pcbnew.B_Fab if actual.IsFlipped()else pcbnew.F_Fab
    def reference_fields(fp):
        return [g for g in fp.GraphicalItems()if g.GetClass()=='PCB_TEXT'and g.GetText()=='${REFERENCE}'and g.GetLayer()==face]
    a,t=reference_fields(actual),reference_fields(template)
    _need(len(a)==len(t)==1,'unique_literal_original_and_source_fab_reference_required')
    angle=a[0].GetTextAngle().AsDegrees()
    _need(math.isfinite(angle)and angle%90==0 and actual.GetOrientationDegrees()%90==0,
        'cardinal_instance_fab_reference_angle_required')
    def field_signature(fp):
        one=pcbnew.BOARD();one.SetCopperLayerCount(actual.GetBoard().GetCopperLayerCount());one.Add(pcbnew.FOOTPRINT(fp))
        with tempfile.TemporaryDirectory(prefix='cec-fab-field-attributes-')as work:
            path=Path(work)/'field.kicad_pcb';ink.field._save_field_snapshot(one,path)
            footprint=next(n for n in ink.frame.additive._nodes(path)[1].values()if n[0]=='footprint')
        nodes=[n for n in footprint if isinstance(n,list)and n[:3]==['fp_text','user','"${REFERENCE}"']
            and any(isinstance(c,list)and c[:2]==['layer',json.dumps('B.Fab'if actual.IsFlipped()else'F.Fab')]for c in n)]
        _need(len(nodes)==1,'unique_serialized_literal_fab_field_required')
        node=[]
        for c in nodes[0]:
            if isinstance(c,list)and c and c[0]=='uuid':continue
            if isinstance(c,list)and c and c[0]=='at':
                _need(len(c)==4,'exact_native_fab_field_pose_required');c=[c[0],c[1],c[2],'0']
            node.append(c)
        return ink.syntax._freeze(node)
    # This cache is owned by ONE fresh enclosing plan/receiver, never a
    # public proposal or cross-call success cache. Only independently
    # transformed ORIGINAL-template signatures are reused. Every actual
    # Source/candidate field and full native subtree is serialized afresh.
    # Cardinal transforms serialize relative footprint coordinates, so the
    # expected physical body depends on face/angle, not absolute board pose.
    if expected_cache is not None:
        _need(type(expected_cache)is dict and type(template_key)is str and template_key,
            'private_exact_template_comparison_cache_required')
    key=(template_key,bool(actual.IsFlipped()),actual.GetOrientationDegrees())
    field_key=key+('field',)
    if expected_cache is not None and field_key in expected_cache:
        expected_field=expected_cache[field_key]
    else:
        expected_field=field_signature(template)
        if expected_cache is not None:expected_cache[field_key]=expected_field
    _need(field_signature(actual)==expected_field,'non_angle_fab_reference_attributes_differ')
    # Align the comparison clone only. Full native subtree comparison BELOW
    # still owns position/font/text/layer/mirror/attributes and all other art.
    t[0].SetTextAngle(pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    semantic_key=key+('physical',angle)
    if expected_cache is not None and semantic_key in expected_cache:
        expected_semantic=expected_cache[semantic_key]
    else:
        with tempfile.TemporaryDirectory(prefix='cec-print-fab-angle-proof-')as work:
            path=Path(work)/'independent.kicad_pcb';ink.field._save_field_snapshot(owner,path)
            projected=pcbnew.LoadBoard(str(path));expected=next(iter(projected.GetFootprints()))
            expected_semantic=ink.frame._semantic(expected)
        if expected_cache is not None:expected_cache[semantic_key]=expected_semantic
    return ink.frame._semantic(actual)==expected_semantic


def _extras(value):
    known={'pad','fp_line','fp_arc','fp_rect','fp_poly','fp_circle','fp_text','fp_text_box','model','attr',
        'solder_mask_margin','solder_paste_margin','solder_paste_ratio','clearance','zone_connect',
        'thermal_width','thermal_gap','net_tie_pad_groups'}
    instance={'at','layer','uuid','tstamp','path','property','locked','sheetname','sheetfile','version','generator','generator_version'}
    return tuple(sorted((ink.syntax._freeze(n)for n in ink._node(value)if isinstance(n,list)and n and n[0]not in known|instance),key=repr))


def _original_defaults(template, copper_layers):
    # The native loader adds explicit defaults (notably K10's
    # duplicate_pad_numbers_are_jumpers=no) to older original templates.
    # Reproduce those defaults from the independent ORIGINAL, rather than
    # ignoring the setting or weakening the true/false comparison.
    independent=pcbnew.BOARD();independent.SetCopperLayerCount(copper_layers)
    independent.Add(pcbnew.FootprintLoad(str(template.parent),template.stem))
    with tempfile.TemporaryDirectory(prefix='cec-print-original-defaults-')as work:
        path=Path(work)/'original.kicad_pcb';ink.field._save_field_snapshot(independent,path)
        rendered=path.read_text();span=next((x,y)for x,y in raw.children(rendered)if raw.kind(rendered[x:y])=='footprint')
        return _extras(rendered[span[0]:span[1]])


def _owner(board, fp, source, template, deadline, source_part, expected_extra, source_maps,physical_cache):
    _need(not fp.IsDNP()and not fp.IsLocked(),'unlocked_populated_print_owner_required')
    source_ink=[g for g in fp.GraphicalItems()if g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)]
    _need(len(source_ink)in(0,2),'complete_two_or_already_omitted_zero_optional_lines_required')
    if source_ink:
        _need(_physical_match(fp,pcbnew.FootprintLoad(str(template.parent),template.stem),
            expected_cache=physical_cache,template_key=force._hash(template)),
            'entire_original_source_template_physical_and_art_identity_required')
    # Both immutable values are private to THIS fresh plan. No public cache,
    # previous proposal, or cross-call object can grant source authority.
    _need(_extras(source_part)==expected_extra,'unknown_or_additional_source_physical_settings_differ')
    groups=[g for g in board.Groups()if any(force._uid(i)==force._uid(fp)for i in g.GetItems())]
    proof=None
    if not fp.Reference().IsVisible():
        _need(len(groups)==1,'hidden_reference_requires_unique_existing_source_owned_map')
        proof=source_maps.get(force._uid(fp))
        _need(proof is not None and proof['owner_uuid']==force._uid(fp)and proof['group_uuid']==force._uid(groups[0]),
            'fresh_batch_source_reference_map_required')
        _need(time.monotonic()<deadline,'source_reference_map_lease_exhausted')
    else:_need(not groups,'non_map_group_owned_print_owner_refused')
    # The geometry recognizer's visible-reference prerequisite is independently
    # discharged above by the actual source-owned map, never by clone appearance.
    clone_owner=pcbnew.BOARD();clone_owner.SetCopperLayerCount(board.GetCopperLayerCount());clone=pcbnew.FOOTPRINT(fp);clone_owner.Add(clone)
    if proof:
        clone.Reference().SetVisible(True)
        clone.Reference().SetLayer(pcbnew.B_SilkS if clone.IsFlipped()else pcbnew.F_SilkS)
    bindings={};lines=ink.nonpolar._body(clone,bindings)
    _need(str(template.resolve())in bindings,'actual_resolved_original_vendored_template_required')
    if not source_ink:
        # _body independently proved the ORIGINAL two strokes symmetric and
        # nonfunctional, and bound its actual vendor path/lands above. The
        # zero-line alternative must match the COMPLETE original-minus-two
        # native subtree, not merely pads or an absence of visible ink.
        # Literal omission avoids KiCad FOOTPRINT.Remove's borrowed-proxy
        # ownership hazard. Never detach or destroy Source native children.
        text=_omitted(template.read_text(),_template_lines(template))
        with tempfile.TemporaryDirectory(prefix='cec-original-minus-two-')as work:
            derivative_path=Path(work)/(template.stem+'.kicad_mod');derivative_path.write_text(text)
            derivative=pcbnew.FootprintLoad(str(derivative_path.parent),derivative_path.stem)
            _need(_physical_match(fp,derivative,expected_cache=physical_cache,template_key=ink._digest(text)),
                'already_omitted_source_not_exact_original_minus_two_lines')
    _need(len(lines)==len(source_ink),'source_optional_line_state_changed')
    actual={ink.nonpolar._line(g):force._uid(g)for g in fp.GraphicalItems()if g.GetLayer()in(pcbnew.F_SilkS,pcbnew.B_SilkS)}
    _need(len(actual)==len(source_ink)and set(actual)=={ink.nonpolar._line(g)for g in lines},'source_optional_stroke_inventory_changed')
    gids=sorted(actual.values());grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    _need(not set(gids)&grouped and all(not g.IsLocked()for g in fp.GraphicalItems()if force._uid(g)in gids),
        'locked_or_group_owned_optional_lines_refused')
    return dict(footprint_uuid=force._uid(fp),fpid=fp.GetFPIDAsString(),graphic_uuids=gids,source_reference_map=proof,
        source_optional_body_state='original_two_lines'if source_ink else'already_omitted_zero_lines')


def _retained_map_track_ancestry(mapped,source,board_hint,*,_source_board=None):
    """Exact ENTIRE Source retention, not copper receiving or a refill lease.

    A reference association depends on retained parts/ink/process, not on
    newly added unmasked straight tracks. Compare the complete saved tree
    after removing ONLY new root segments, plus all physical companions.
    No original fill/group/rule/pad/root field may change. Holes, vias, arcs,
    mask openings and fabricated Source roles are deliberately unsupported.
    Original-parent route/current/field/native gates still receive additions.
    """
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    # Only public plan() supplies its OWN freshly loaded, entry/exit-bound
    # native board. Construction and receiving each call plan independently;
    # no caller proof, cache or native board is accepted by the public API.
    boundaries=(mapped,)if _source_board is not None else(mapped,source)
    code=force._code_identity();families=[force._family(p,board_hint)for p in boundaries]
    roots=[];inventories=[]
    for path in(mapped,source):
        root,nodes=additive._nodes(path);roots.append(root);inventories.append(nodes)
    # One complete child traversal checks bounds and EVERY nested UUID. It
    # already contains the entire Source tree; traversing both boundaries
    # again, and again for each net lookup, adds no independent evidence.
    text=source.read_text();raw_nodes,_,spans,_=literal._inventory(text)
    old,new=inventories;incoming=set(new)-set(old)
    _need(set(old)<=set(new)and len(incoming)<=64 and all(new[u][0]=='segment'for u in incoming),
        'only_bounded_unmasked_new_tracks_can_retain_received_map_association')
    def uid(node):
        return next((n[1].strip('"')for n in node[1:]if isinstance(n,list)
            and len(n)==2 and n[0]=='uuid'),None)if isinstance(node,list)else None
    projected=[roots[1][0],*(node for node in roots[1][1:]if uid(node)not in incoming)]
    _need(ink.syntax._freeze(roots[0])==ink.syntax._freeze(projected)
        and force._sidecars(mapped)==force._sidecars(source),
        'entire_opaque_received_map_Source_tree_or_companion_changed')
    board=_source_board if _source_board is not None else pcbnew.LoadBoard(str(source))
    _need(board is not None and Path(board.GetFileName()).resolve()==source,
        'fresh_internal_reference_ancestry_Source_board_required')
    items={force._uid(t):t for t in board.GetTracks()}
    names={};net_names=literal._net_names(text,spans)
    for u in incoming:
        node=raw_nodes[u][2];net_span=literal._child(node,'net')
        _need(net_span is not None,'literal_reference_ancestry_track_net_missing')
        a,b=net_span;tokens=literal._atoms(node[a+1:b-1])
        _need(len(tokens)==2,'literal_reference_ancestry_track_net_ambiguous')
        value,lexeme=tokens[1]
        names[u]=value if lexeme.startswith('"')else net_names.get(value)
    # Source net names come from the complete original tree, not the child's
    # new tracks. The already loaded child independently supplies positive
    # native net codes/class/process; full route ownership is checked later.
    known=set();pending=[roots[0]]
    while pending:
        node=pending.pop()
        if not isinstance(node,list)or not node:continue
        if node[0]=='net'and len(node)in(2,3)and type(node[-1])is str and node[-1].startswith('"'):
            value=json.loads(node[-1])
            if value:known.add(value)
        pending.extend(n for n in node if isinstance(n,list))
    _need(incoming<=items.keys()and all(items[u].GetClass()=='PCB_TRACK'
        and items[u].GetNetCode()>0 and items[u].GetNetname()==names[u]and names[u]in known
        and not items[u].HasSolderMask()and items[u].GetParentGroup()is None for u in incoming),
        'only_actual_existing_net_unmasked_track_additions_can_retain_map_association')
    _need(code==force._code_identity()and families==[force._family(p,board_hint)for p in boundaries],
        'retained_map_Source_or_code_epoch_changed')
    return dict(ok=True,complete=True,scope='entire_opaque_Source_retained_under_unmasked_straight_tracks_only',
        added_native_uuids=sorted(incoming),all_original_tree_and_companions_exact=True,
        reference_association_only=True,copper_admission=False,current_authority=False,release_authority=False)


def _received_reference_maps(source,declaration,board_hint,*,_source_board=None):
    """Discharge hidden-reference association by exact saved public replay.

    Interrupted guides are not closed-body authority. Caller success flags,
    UUID allowlists and arbitrary fragments grant nothing. Every independent
    original-template, pad, body, mark and factory check still runs below.
    """
    import cec_mask_search_reference_mapping as annotation
    _need(type(declaration)is dict and set(declaration)in(
        {'source','proposal'},{'source','proposal','mapped_source'},
        {'source','proposal','mapped_source','association_identity'}),
        'exact_saved_reference_mapping_declaration_required')
    query_mode='association_identity'in declaration
    _need(not query_mode or (type(declaration['association_identity'])is str
        and declaration['association_identity']=='same_literal_map_queries'),
        'exact_explicit_same_literal_map_query_required')
    paths=[]
    for name in('source','proposal',*(['mapped_source']if 'mapped_source'in declaration else [])):
        row=declaration[name]
        _need(type(row)is dict and set(row)=={'path','sha256'}and type(row['path'])is str
            and type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']),
            'hashed_reference_mapping_input_required')
        p=Path(row['path']);_need(p.is_absolute()and not p.is_symlink(),'absolute_reference_mapping_input_required')
        p=p.resolve(strict=True);_need(p.is_file()and force._hash(p)==row['sha256'],
            'reference_mapping_input_changed');paths.append(p)
    ancestor,proposal_path=paths[:2]
    mapped=paths[2]if len(paths)==3 else source
    _need(len({source,ancestor,proposal_path,*([mapped]if len(paths)==3 else [])})==len(paths)+1,
        'distinct_saved_reference_mapping_boundaries_required')
    q=json.loads(proposal_path.read_text())
    chart=q.get('mode')=='nearby_opposite_face_mapping_chart'
    _need(q.get('board_hint')==board_hint and q.get('reverse_ownership')=='rigid_root_group_per_component'
        and (q.get('mode')=='opposite_face_projected_courtyard'
            or (chart and q.get('opposite_face_chart')is True)),
        'independent_per_owner_reverse_reference_map_required')
    _need(not query_mode or (not chart and q.get('mode')=='opposite_face_projected_courtyard'
        and q.get('opposite_face_chart',False)is False),
        'same_literal_map_queries_require_per_owner_projected_maps')
    active=_STAGED_PRINT.get()
    proof=(active._map_proof(ancestor,mapped,q) if active is not None
        else annotation.receive(ancestor,mapped,q))
    _need(proof.get('ok')is True and proof.get('complete')is True
        and proof.get('source_bound_projection_exact')is True,
        'fresh_saved_reference_mapping_refused:'+str(proof.get('errors')))
    # A copper-only child must not lose a received reference association.
    # This is NOT transport of map authority by a hash or success flag: the
    # original map is independently replayed above, then the ENTIRE actual
    # saved Source tree and companions must pass the narrower no-refill
    # straight-track-only retention proof.
    # Existing footprints, ink, guides, groups and process cannot change.
    # Routing/current/contact/native admission is still owed independently.
    inherited=None;query=None
    if query_mode:
        import cec_reference_association_query as association
        # Derive query identities ONLY from the freshly received ORIGINAL
        # mapped boundary and producer manifest, never the copper child's
        # claims or a caller-supplied list of permissible exceptions.
        manifest=proof.get('manifest',{});raw_gids=manifest.get('added_reverse_group_uuids')
        records=q.get('records');mapped_board=pcbnew.LoadBoard(str(mapped))
        _need(type(raw_gids)is list and 1<=len(raw_gids)<=128
            and all(type(g)is str and g for g in raw_gids)and len(set(raw_gids))==len(raw_gids)
            and not manifest.get('added_group_uuid')
            and type(records)is list and len(records)==len(raw_gids)
            and all(type(r)is dict and type(r.get('footprint_uuid'))is str and r['footprint_uuid']for r in records)
            and len({r['footprint_uuid']for r in records})==len(records)
            and mapped_board is not None,'fresh_per_owner_manifest_query_scope_required')
        mapped_groups={force._uid(g):g for g in mapped_board.Groups()};pairs=[]
        for row in records:
            owner=row['footprint_uuid']
            matches=[g for uid,g in mapped_groups.items()if uid in raw_gids and
                any(i.GetClass()=='FOOTPRINT'and force._uid(i)==owner for i in g.GetItems())]
            _need(len(matches)==1,'unique_original_mapped_query_owner_required')
            pairs.append((owner,force._uid(matches[0])))
        _need({g for _,g in pairs}==set(raw_gids),'complete_original_mapped_query_cohort_required')
        query=association.compare(mapped,source,pairs,board_hint=board_hint,timeout_s=10.)
        _need(query.get('ok')is True and query.get('complete')is True
            and query.get('association_only')is True and query.get('association_identity_preserved')is True
            and query.get('producer_replay_still_required')is True
            and all(query.get(k)is False for k in('closed_body_authority','mask_authority','copper_admission',
                'current_authority','pose_authority','print_admission','release_authority'))
            and {(r['owner_uuid'],r['group_uuid'])for r in query['records']}==set(pairs),
            'same_literal_reference_association_query_refused')
    elif mapped!=source:
        inherited=_retained_map_track_ancestry(mapped,source,board_hint,_source_board=_source_board)
        _need(inherited.get('ok')is True and inherited.get('complete')is True,
            'strict_saved_additive_reference_ancestry_refused:'+str(inherited.get('errors')))
    # Only the enclosing fresh public plan may supply its OWN Source load.
    # This is not a proposal/cache input: construction and receiving each
    # call plan independently, whose Source/family/dependency exit checks
    # still bind that load. The map's independent saved receiver above is
    # intentionally NOT reused or skipped.
    native=_source_board if _source_board is not None else pcbnew.LoadBoard(str(source))
    _need(native is not None and Path(native.GetFileName()).resolve()==source,
        'fresh_internal_reference_mapping_Source_board_required')
    groups={force._uid(g):g for g in native.Groups()}
    manifest=proof['manifest'];gids=set(manifest['added_reverse_group_uuids'])
    if chart:
        # A rear chart intentionally owns one rigid relationship among its
        # actual footprints, title, leaders and callouts. It is not a closed
        # body projection or a per-part transport permission. The complete
        # saved public map receiver above must freshly reconstruct ALL of
        # it, including unchanged copper, parts, masks, marks and Source ink.
        gid=manifest.get('added_group_uuid')
        _need(type(gid)is str and gid in groups and not gids,
            'one_fresh_received_rear_chart_group_required')
        group=groups[gid]
        actual={force._uid(i)for i in group.GetItems()if i.GetClass()=='FOOTPRINT'}
        requested=[row['footprint_uuid']for row in q['records']]
        _need(group.IsLocked()and len(actual)==len(requested)
            and actual==set(requested),'exact_rigid_received_rear_chart_owners_required')
        gids={gid}
    else:
        _need(not manifest.get('added_group_uuid')and len(gids)==len(q['records']),
            'one_fresh_per_owner_map_group_required')
    result={}
    for row in q['records']:
        owner=row['footprint_uuid']
        matching=[g for uid,g in groups.items()if uid in gids and
            any(i.GetClass()=='FOOTPRINT'and force._uid(i)==owner for i in g.GetItems())]
        _need(owner not in result and len(matching)==1,'unique_fresh_reference_map_owner_required')
        result[owner]=dict(owner_uuid=owner,group_uuid=force._uid(matching[0]),
            scope='fresh_independently_received_reference_association_only',
            exact_source_map_receiving_sha256=ink._digest(json.dumps(proof,sort_keys=True)),
            closed_assembly_body_authority=False,
            actual_parts_pads_fab_courtyards_and_functional_marks_still_independently_required=True)
        if chart:
            result[owner].update(reference_association_kind='fresh_received_rigid_rear_chart',
                shared_chart_is_not_component_pose_or_closed_body_authority=True)
        if inherited is not None:
            result[owner].update(strict_opaque_Source_additive_ancestry_independently_received=True,
                mapped_source=str(mapped),mapped_source_sha256=force._hash(mapped),
                copper_addition_admission_or_current_authority=False)
        if query is not None:
            result[owner].update(reference_association_kind='fresh_received_same_literal_map_queries',
                same_literal_Source_map_queries_independently_received=True,
                exact_same_literal_map_query_sha256=ink._digest(json.dumps(ink._stable(query),sort_keys=True)),
                fresh_producer_receiving_precedes_association_query=True,
                mapped_source=str(mapped),mapped_source_sha256=force._hash(mapped),
                unrelated_PCB_changes_not_received=True,mask_or_print_admission=False,
                copper_addition_admission_or_current_authority=False)
    deps={**annotation.dependencies(),str(proposal_path):force._hash(proposal_path)}
    deps.update({p:h for p,h in force._family(ancestor,board_hint).items()if h is not None})
    if mapped!=source:deps.update({p:h for p,h in force._family(mapped,board_hint).items()if h is not None})
    if query is not None:deps.update(query['dependency_sha256'])
    return result,deps


def _inspect_plan_maps(source,board,selections,source_sha,deadline):
    """Recognize maps from ONE private fresh public-plan frame.

    Preserve the complete parsed literal root nodes and the exact legacy
    courtyard recognizer. Reopening another identical native snapshot and
    rebuilding family/code epochs would not be an independent receiver;
    plan's entry AND exit checks already own those boundaries. No public
    prepared data, cached success, or Fab-body fallback is accepted here.
    """
    _need(type(selections)is list and 1<=len(selections)<=128
        and all(type(v)in(tuple,list)and len(v)==2
            and all(type(x)is str and x for x in v)for v in selections)
        and len({tuple(v)for v in selections})==len(selections),
        'bounded_unique_source_map_selections_required')
    _need(board is not None and Path(board.GetFileName()).resolve()==source
        and force._hash(source)==source_sha,'fresh_internal_print_map_Source_required')
    # Use the SAME full literal parser as public inspect_many, not the
    # shallower UUID-to-span print-edit inventory or a caller's JSON proof.
    nodes=maps.ast._nodes(source)[1];rules=maps._cardinal_rules(source,board)
    result=[]
    for owner_uuid,group_uuid in selections:
        _need(time.monotonic()<deadline,'source_map_batch_deadline')
        result.append(maps._inspect_bound(source,board,nodes,rules,source_sha,
            owner_uuid=owner_uuid,group_uuid=group_uuid))
    _need(time.monotonic()<deadline and force._hash(source)==source_sha,
        'fresh_internal_print_map_Source_or_lease_changed')
    return result


def plan(source, *, library_table, footprint_ids, expected_instance_uuids, board_hint, timeout_s=10.,
         optional_body_footprint_ids=(),reference_mapping_transition=None,source_chart_group_uuids=()):
    _need(type(footprint_ids)is list and 1<=len(footprint_ids)<=4 and len(set(footprint_ids))==len(footprint_ids)
        and all(type(s)is str and s.count(':')==1 for s in footprint_ids),'bounded_exact_same_fpid_selection_required')
    _need(type(expected_instance_uuids)is list and 1<=len(expected_instance_uuids)<=128 and len(set(expected_instance_uuids))==len(expected_instance_uuids),
        'bounded_explicit_complete_instance_set_required')
    _need(type(optional_body_footprint_ids)in(list,tuple)and len(optional_body_footprint_ids)<=4
        and all(type(s)is str for s in optional_body_footprint_ids)
        and len(set(optional_body_footprint_ids))==len(optional_body_footprint_ids)
        and set(optional_body_footprint_ids)<=set(footprint_ids),'explicit_approved_body_fpid_subset_required')
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10 and type(board_hint)is str and board_hint,
        'bounded_explicit_print_source_context_required')
    started=time.monotonic();deadline=started+timeout_s;source=Path(source).resolve(strict=True);table=Path(library_table).resolve(strict=True)
    source_sha=force._hash(source);family=force._family(source,board_hint);code=force._code_identity()
    dependencies={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in(ink,ink.frame,libraries,maps)}
    dependencies[str(Path(__file__).resolve())]=force._hash(Path(__file__))
    if optional_body_footprint_ids:
        import cec_optional_body_ink_contract as body
        dependencies[str(Path(body.__file__).resolve())]=force._hash(Path(body.__file__))
    old=libraries.authority(source,table);board=pcbnew.LoadBoard(str(source));owners=[f for f in board.GetFootprints()if f.GetFPIDAsString()in footprint_ids]
    source_text=source.read_text();source_inventory=raw.inventory(source_text)
    _need({force._uid(f)for f in owners}==set(expected_instance_uuids)and {f.GetFPIDAsString()for f in owners}==set(footprint_ids),
        'every_selected_fpid_instance_must_be_explicitly_included')
    received_maps={}
    if reference_mapping_transition is not None:
        received_maps,reference_deps=_received_reference_maps(source,reference_mapping_transition,board_hint,
            _source_board=board)
        dependencies.update(reference_deps)
        _need(set(received_maps)<=set(expected_instance_uuids),
            'fresh_mapping_must_be_within_explicit_print_owner_scope')
    if source_chart_group_uuids:
        import cec_existing_reference_chart as charts
        current_charts=charts.inspect_many(source,source_chart_group_uuids,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())),_source_board=board)
        _need(not current_charts.keys()&received_maps.keys()and set(current_charts)<=set(expected_instance_uuids),
            'distinct_current_chart_associations_within_explicit_print_scope_required')
        received_maps.update(current_charts);dependencies.update(charts.dependencies())
    else:
        _need(type(source_chart_group_uuids)in(list,tuple),'explicit_source_chart_group_scope_required')
    requests=[]
    for fp in owners:
        if fp.Reference().IsVisible():continue
        groups=[g for g in board.Groups()if any(force._uid(i)==force._uid(fp)for i in g.GetItems())]
        _need(len(groups)==1,'hidden_reference_requires_unique_existing_source_owned_map')
        if force._uid(fp)not in received_maps:requests.append((force._uid(fp),force._uid(groups[0])))
    source_maps={p['owner_uuid']:p for p in _inspect_plan_maps(source,board,requests,source_sha,deadline)}if requests else{}
    _need(not source_maps.keys()&received_maps.keys(),'ambiguous_source_reference_authority')
    source_maps.update(received_maps)
    body_ids=[force._uid(f)for f in owners if f.GetFPIDAsString()in optional_body_footprint_ids]
    body_proofs=(body.inspect_many(source,library_table=table,footprint_uuids=body_ids,
        expected_source_sha256=source_sha,timeout_s=min(10.,max(.001,deadline-time.monotonic())),
        allow_already_omitted=True)if body_ids else{})
    records=[];derivatives=[];physical_cache={}
    for fpid in sorted(footprint_ids):
        alias,item=fpid.split(':',1);row=old['rows'].get(alias)
        _need(row and row['enabled'],'enabled_original_library_alias_required');template=Path(row['path'])/(item+'.kicad_mod')
        if fpid in optional_body_footprint_ids:
            # Fresh per-owner proofs and this independent derivation both
            # bind the registered original. Only a byte-identical copy of a
            # positively registered manufacturer template may live outside
            # vendor; no Source/cache/proposal can register a new body role.
            derivative=body.template_omission(template)
            dependencies.update(derivative['template_input_sha256'])
            template_lines=derivative['graphic_ids'];text=derivative['derivative_text']
        else:
            _need(template.is_file()and template.resolve().is_relative_to((ink.nonpolar.ROOT/'lib/vendor').resolve()),
                'independent_original_vendored_template_required')
            template_lines=_template_lines(template);text=_omitted(template.read_text(),template_lines)
        derivatives.append(dict(fpid=fpid,original_path=str(template.resolve()),original_sha256=force._hash(template),
            original_optional_line_uuids=template_lines,derivative_sha256=ink._digest(text),derivative_text=text))
        expected_extra=_original_defaults(template,board.GetCopperLayerCount())
        for fp in sorted((f for f in owners if f.GetFPIDAsString()==fpid),key=force._uid):
            _need(time.monotonic()<deadline,'print_context_source_geometry_deadline')
            a,b=source_inventory[force._uid(fp)]
            if fpid in optional_body_footprint_ids:
                proof=body_proofs[force._uid(fp)]
                records.append(dict(footprint_uuid=force._uid(fp),fpid=fpid,
                    graphic_uuids=proof['graphic_uuids'],source_optional_body_state=proof['source_optional_body_state'],
                    source_optional_body_contract=proof))
            else:records.append(_owner(board,fp,source,template,deadline,source_text[a:b],expected_extra,source_maps,physical_cache))
    # All referenced items under a redirected alias must remain available.
    copied=[];aliases={f.split(':',1)[0]for f in footprint_ids}
    for alias,item in old['references']:
        if alias not in aliases:continue
        path=Path(old['rows'][alias]['path'])/(item+'.kicad_mod')
        _need(path.is_file(),'all_other_referenced_alias_items_must_exist')
        copied.append(dict(alias=alias,item=item,path=str(path.resolve()),sha256=force._hash(path)))
    result=ink._stable(dict(schema=1,scope='private_same_fpid_optional_nonpolar_print_context',source=str(source),library_table=str(table),
        footprint_ids=footprint_ids,expected_instance_uuids=expected_instance_uuids,board_hint=board_hint,timeout_s=timeout_s,
        source_sha256=source_sha,source_family=family,old_library_context=old,
        records=records,derivatives=derivatives,all_referenced_alias_items=copied,dependency_sha256=dependencies,
        script_code_identity=code,admitted=False,canonical_source_changed=False,release_authority=False))
    if optional_body_footprint_ids:
        result.update(scope='private_same_fpid_optional_nonpolar_and_approved_body_print_context',
            optional_body_footprint_ids=list(optional_body_footprint_ids))
    if reference_mapping_transition is not None:
        result['reference_mapping_transition']=ink._stable(reference_mapping_transition)
    if source_chart_group_uuids:result['source_chart_group_uuids']=list(source_chart_group_uuids)
    _need(time.monotonic()<deadline and old==libraries.authority(source,table)
        and source_sha==force._hash(source)and family==force._family(source,board_hint)
        and code==force._code_identity()and all(force._hash(Path(p))==h for p,h in dependencies.items()),
        'print_source_context_code_or_lease_changed')
    return result


def _board_text(text, proposal):
    inventory=raw.inventory(text);changes=[]
    for row in proposal['records']:
        a,b=inventory[row['footprint_uuid']];changes.append((a,b,_omitted(text[a:b],row['graphic_uuids'])))
    return ink._edits(text,changes)


def _replay_private_family(source, proposal, out):
    """Fresh exact bytes, without deriving unused temporary publication data.

    Both public construction and independent receiving must re-plan Source.
    Only construction publishes a context for its actual saved candidate;
    receiving independently derives the real candidate's authority below.
    This helper has no skip-proof option and grants no context authority.
    """
    source=Path(source).resolve(strict=True);out=Path(out).resolve()
    fresh=plan(source,library_table=proposal['library_table'],footprint_ids=proposal['footprint_ids'],
        expected_instance_uuids=proposal['expected_instance_uuids'],board_hint=proposal['board_hint'],timeout_s=proposal['timeout_s'],
        optional_body_footprint_ids=proposal.get('optional_body_footprint_ids',()),
        reference_mapping_transition=proposal.get('reference_mapping_transition'),
        source_chart_group_uuids=proposal.get('source_chart_group_uuids',()))
    _need(fresh==proposal,'stale_or_forged_same_fpid_print_proposal')
    return _materialize_private_family(source,fresh,out)


def _materialize_private_family(source,fresh,out):
    """Private deterministic writer; only fresh enclosing owners call this."""
    source=Path(source).resolve(strict=True);out=Path(out).resolve()
    _need(not out.exists()and source.parent not in out.parents,'fresh_disjoint_private_print_context_required');out.mkdir(parents=True)
    child=out/'board.kicad_pcb';child.write_text(_board_text(source.read_text(),fresh))
    for suffix,digest in force._sidecars(source).items():
        if digest is not None:child.with_suffix(suffix).write_bytes(source.with_suffix(suffix).read_bytes())
    aliases=sorted({f.split(':',1)[0]for f in fresh['footprint_ids']});folders={a:'print-'+ink._digest(a)[:16]+'.pretty'for a in aliases}
    for name in folders.values():(out/name).mkdir()
    derivatives={r['fpid']:r for r in fresh['derivatives']}
    for row in fresh['all_referenced_alias_items']:
        target=out/folders[row['alias']]/(row['item']+'.kicad_mod');fpid=row['alias']+':'+row['item']
        target.write_bytes(derivatives[fpid]['derivative_text'].encode()if fpid in derivatives else Path(row['path']).read_bytes())
    _,rendered,_=libraries._table(Path(fresh['library_table']).read_text(),Path(fresh['library_table']).parent,fresh['old_library_context']['variables'])
    edits=[]
    for a,b in raw.children(rendered):
        node=ink._node(rendered[a:b])
        if node[0]!='lib':continue
        name=next((n[1].strip('"')for n in node if isinstance(n,list)and n[:1]==['name']),None)
        if name not in folders:continue
        part=rendered[a:b];uri=[(x,y)for x,y in raw.children(part)if raw.kind(part[x:y])=='uri']
        _need(len(uri)==1,'one_original_alias_uri_required');x,y=uri[0]
        edits.append((a,b,part[:x]+'(uri '+json.dumps('${KIPRJMOD}/'+folders[name])+')'+part[y:]))
    table=out/'fp-lib-table';table.write_text(ink._edits(rendered,edits))
    force._write(out/'print-proposal.json',fresh)
    return child,table,fresh


def construct_private(source, proposal, out):
    child,table,fresh=_replay_private_family(source,proposal,out)
    new=ink._stable(libraries.authority(child,table))
    result=dict(candidate=str(child),library_table=str(table),old_library_context=fresh['old_library_context'],new_library_context=new,
        physical_original_template_authority_retained=True,whole_stage_source_current_native_receiving_still_required=True,
        admitted=False,release_authority=False)
    force._write(child.parent/'print-context.json',result);return result


def _saved_comparison(source,candidate,proposal,root):
        def files(path):return {p.relative_to(path):p.read_bytes()for p in path.rglob('*')if p.is_file()and p.relative_to(path)!=Path('print-context.json')}
        _need(files(root)==files(candidate.parent),'private_print_board_library_sidecars_not_exact_original_replay')
        old=proposal['old_library_context'];new=ink._stable(libraries.authority(candidate,candidate.parent/'fp-lib-table'))
        metadata=json.loads((candidate.parent/'print-context.json').read_text())
        _need(metadata==dict(candidate=str(candidate),library_table=str(candidate.parent/'fp-lib-table'),
            old_library_context=old,new_library_context=new,physical_original_template_authority_retained=True,
            whole_stage_source_current_native_receiving_still_required=True,admitted=False,release_authority=False),
            'saved_print_context_metadata_or_admission_claim_forged')
        _need(ink._stable(old['references'])==ink._stable(new['references']),'same_fpid_references_changed')
        board=pcbnew.LoadBoard(str(candidate));physical_cache={}
        for record in proposal['records']:
            fp=next(f for f in board.GetFootprints()if force._uid(f)==record['footprint_uuid'])
            alias,item=record['fpid'].split(':',1);template=Path(new['rows'][alias]['path'])/(item+'.kicad_mod')
            if 'source_optional_body_contract'in record:
                import cec_optional_body_ink_contract as body
                matched=body._native_match(fp,template)
            else:matched=_physical_match(fp,pcbnew.FootprintLoad(str(template.parent),item),
                expected_cache=physical_cache,template_key=force._hash(template))
            _need(fp.GetFPIDAsString()==record['fpid']and matched,'all_same_fpid_native_bodies_must_match_print_derivative')
        with tempfile.TemporaryDirectory(prefix='cec-print-second-save-')as work:
            first=Path(work)/'first.kicad_pcb';second=Path(work)/'second.kicad_pcb'
            ink.field._save_field_snapshot(board,first);ink.field._save_field_snapshot(pcbnew.LoadBoard(str(first)),second)
            _need(ink.syntax._freeze(ink.frame.additive._nodes(first)[0])==ink.syntax._freeze(ink.frame.additive._nodes(second)[0]),'print_second_native_save_unstable')
        return dict(ok=True,complete=True,scope_only=True,admitted=False,release_authority=False,
            old_library_context=old,new_library_context=new,
            exact_same_fpid_source_optional_body_omission_received=True,source_physical_identity_unchanged=True)


class _PrintReplay:
    """One invocation's sealed material, never a serialized proof or cache."""
    def __init__(self,source,options,timeout_s,candidate=None,proposal=None):
        _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_staged_print_required')
        _need(not Path(source).is_symlink(),'staged_print_source_symlink_refused')
        self._source=Path(source).resolve(strict=True);self._options=copy.deepcopy(options)
        self._limit=timeout_s;self._candidate=Path(candidate).resolve(strict=True)if candidate is not None else None
        _need(self._candidate is None or (self._candidate!=self._source and not self._candidate.samefile(self._source)),
            'distinct_staged_print_candidate_required')
        self._requested=copy.deepcopy(proposal);self._q=None;self._state='new';self._times={}
        self._identity=None;self._map=None;self._map_result=None;self._map_key=None;self._map_seal=None
        self._q_seal=None;self._started=time.monotonic()
        self._stage_names=tuple((['map_reconstruct','map_receive']if self._options.get('reference_mapping_transition')is not None else[])+
            ['source_plan','reconstruct','saved_compare'])
        self._expected=None;self._seal=None
    def _snapshot(self):
        import _pcbnew
        import cec_mask_search_reference_mapping as annotation
        paths={self._source,Path(self._options['library_table']).resolve(strict=True)}
        context=libraries.authority(self._source,self._options['library_table'])
        for alias,item in context['references']:
            paths.add(Path(context['rows'][alias]['path'])/(item+'.kicad_mod'))
        decl=self._options.get('reference_mapping_transition')
        families=[force._family(self._source,self._options['board_hint'])]
        if decl:
            for value in decl.values():
                if type(value)is dict and set(value)=={'path','sha256'}:paths.add(Path(value['path']).resolve(strict=True))
            q=json.loads(Path(decl['proposal']['path']).read_text())
            for key in('grade','native_report'):
                value=q.get('binding',{}).get(key)
                if value:paths.add(Path(value).resolve(strict=True))
            for key in('source','mapped_source'):
                if key in decl:families.append(force._family(Path(decl[key]['path']),self._options['board_hint']))
        implementation={str(Path(m.__file__).resolve()):force._hash(Path(m.__file__))for m in(pcbnew,_pcbnew,ink,ink.frame,libraries,maps)}
        implementation.update(annotation.dependencies())
        if self._options.get('optional_body_footprint_ids'):
            import cec_optional_body_ink_contract as body
            implementation[str(Path(body.__file__).resolve())]=force._hash(Path(body.__file__))
            for fpid in self._options['optional_body_footprint_ids']:
                alias,item=fpid.split(':',1)
                implementation.update(body.template_inputs(Path(context['rows'][alias]['path'])/(item+'.kicad_mod')))
        implementation[str(Path(__file__).resolve())]=force._hash(Path(__file__))
        candidate=None
        if self._candidate is not None:candidate=self._files(self._candidate.parent)
        return (force._code_identity(),families,self._files(self._source.parent),{str(p):force._hash(p)for p in paths},implementation,
            sorted((k,v)for k,v in os.environ.items()if k.startswith(('CEC_','KICAD'))or k=='PATH'),
            ink._digest(json.dumps(self._options,sort_keys=True,default=str)),candidate)
    @staticmethod
    def _files(root):
        result={}
        for p in Path(root).rglob('*'):
            _need(not p.is_symlink(),'staged_print_family_symlink_refused')
            if p.is_file():result[str(p.relative_to(root))]=p.read_bytes()
        return result
    def _run(self,name,required,next_state,fn):
        if self._state!=required:
            self._state='failed';raise ValueError('staged_print_'+name+'_order_required')
        self._state='failed';start=time.monotonic()
        try:
            _need(start-self._started<len(self._stage_names)*self._limit,'staged_print_aggregate_deadline')
            before=self._snapshot()
            if self._identity is not None:_need(before==self._identity,'staged_print_inputs_changed')
            else:self._identity=before
            value=fn()
            _need(self._snapshot()==self._identity,'staged_print_inputs_changed')
            _need(time.monotonic()-start<self._limit,'staged_print_'+name+'_deadline')
            _need(time.monotonic()-self._started<len(self._stage_names)*self._limit,'staged_print_aggregate_deadline')
            self._state=next_state;return value
        finally:
            self._times[name]=time.monotonic()-start
            if self._state==next_state:
                if self._times[name]>=self._limit:
                    self._state='failed';raise ValueError('staged_print_'+name+'_deadline')
                if time.monotonic()-self._started>=len(self._stage_names)*self._limit:
                    self._state='failed';raise ValueError('staged_print_aggregate_deadline')
    def map_reconstruct(self):
        def run():
            import cec_mask_search_reference_mapping as annotation
            d=self._options['reference_mapping_transition'];q=json.loads(Path(d['proposal']['path']).read_text())
            source=Path(d['source']['path']).resolve(strict=True)
            mapped=Path(d['mapped_source']['path']).resolve(strict=True)if 'mapped_source'in d else self._source
            self._map_key=(str(source),str(mapped),ink._digest(json.dumps(q,sort_keys=True)))
            self._map=annotation.saved_replay(source,mapped,q,timeout_s=self._limit)
            return self._map.reconstruct()
        return self._run('map_reconstruct','new','map_reconstructed',run)
    def map_receive(self):
        def run():
            result=self._map.receive()
            _need(result.get('ok')is True and result.get('complete')is True and result.get('source_bound_projection_exact')is True,'staged_print_map_refused')
            self._map_result=json.dumps(result,sort_keys=True)
            self._map_seal=ink._digest((self._map_key,self._map_result))
            return copy.deepcopy(result)
        return self._run('map_receive','map_reconstructed','map_received',run)
    def _map_proof(self,source,mapped,q):
        _need(self._state=='failed'and self._snapshot()==self._identity and self._map_result is not None
            and self._map_seal==ink._digest((self._map_key,self._map_result))
            and self._map_key==(str(source),str(mapped),ink._digest(json.dumps(q,sort_keys=True))),
            'fresh_private_print_map_material_required')
        return json.loads(self._map_result)
    def plan(self):
        def run():
            token=_STAGED_PRINT.set(self)
            try:q=plan(self._source,**self._options,timeout_s=self._limit)
            finally:_STAGED_PRINT.reset(token)
            if self._requested is not None:_need(q==self._requested,'stale_or_forged_same_fpid_print_proposal')
            # Literal proposal file order is part of the complete family.
            self._q=json.dumps(q);self._q_seal=ink._digest(self._q);return copy.deepcopy(q)
        required='map_received'if self._options.get('reference_mapping_transition')is not None else'new'
        return self._run('source_plan',required,'planned',run)
    def reconstruct(self,out):
        def run():
            _need(self._q_seal==ink._digest(self._q),'staged_print_plan_material_changed')
            q=json.loads(self._q);child,table,_=_materialize_private_family(self._source,q,out)
            new=ink._stable(libraries.authority(child,table))
            force._write(child.parent/'print-context.json',dict(candidate=str(child),library_table=str(table),
                old_library_context=q['old_library_context'],new_library_context=new,
                physical_original_template_authority_retained=True,whole_stage_source_current_native_receiving_still_required=True,
                admitted=False,release_authority=False))
            self._expected=self._files(child.parent)
            self._seal=ink._digest(repr(sorted(self._expected.items())))
            return dict(candidate=str(child),library_table=str(table),reconstruction_only=True,saved_candidate_received=False,release_authority=False)
        return self._run('reconstruct','planned','reconstructed',run)
    def receive(self):
        def run():
            _need(self._candidate is not None,'actual_saved_print_candidate_required')
            _need(self._q_seal==ink._digest(self._q),'staged_print_plan_material_changed')
            _need(self._seal==ink._digest(repr(sorted(self._expected.items()))),'staged_print_material_changed')
            with tempfile.TemporaryDirectory(prefix='cec-staged-print-compare-')as work:
                root=Path(work)
                for name,data in self._expected.items():
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                return _saved_comparison(self._source,self._candidate,json.loads(self._q),root)
        return self._run('saved_compare','reconstructed','received',run)
    def compare_origin(self,candidate,historical_proposal):
        """Saved historical metadata is a locator, never a physical verdict.

        The complete current expected family/native physical proof is still
        mandatory. ONLY the already-authored proposal file's freshness fields
        remain historical; all actual library metadata is derived again.
        """
        def run():
            child=Path(candidate).resolve(strict=True);history=Path(historical_proposal).resolve(strict=True)
            _need(self._candidate is not None and child==self._candidate,'exact_bound_print_origin_candidate_required')
            before=self._files(child.parent);historical=history.read_bytes();old=json.loads(historical)
            q=json.loads(self._q)
            _need(self._q_seal==ink._digest(self._q)and self._seal==ink._digest(repr(sorted(self._expected.items()))),
                'staged_print_material_changed')
            _need(Path(old['source']).resolve(strict=True)==self._source
                and old['source_sha256']==force._hash(self._source)
                and before.get('print-proposal.json')==historical,'historical_print_origin_binding_changed')
            for key in('board_hint','footprint_ids','expected_instance_uuids'):
                _need(old[key]==q[key],'historical_print_finite_recipe_changed')
            for key in('optional_body_footprint_ids','source_chart_group_uuids'):
                _need(list(old.get(key,()))==list(q.get(key,())),'historical_print_finite_recipe_changed')
            _need(Path(old['library_table']).resolve(strict=True)==Path(q['library_table']).resolve(strict=True),
                'historical_print_library_authority_changed')
            with tempfile.TemporaryDirectory(prefix='cec-print-origin-compare-')as work:
                root=Path(work)
                for name,data in self._expected.items():
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
                (root/'print-proposal.json').write_bytes(historical)
                proof=_saved_comparison(self._source,child,q,root)
            _need(before==self._files(child.parent)and history.read_bytes()==historical,
                'historical_print_candidate_or_metadata_changed_during_comparison')
            return proof
        return self._run('saved_compare','reconstructed','received',run)
    def observation(self):
        names=list(self._stage_names)
        return dict(state=self._state,timings_s=copy.deepcopy(self._times),per_constituent_limit_s=self._limit,
            constituents=names,aggregate_limit_s=len(names)*self._limit,
            no_saved_verdict_or_release_authority=True)


def staged_replay(source,*,options,timeout_s=10.,candidate=None,proposal=None):
    return _PrintReplay(source,options,timeout_s,candidate,proposal)


def receive_staged(source,candidate,proposal,*,timeout_s=10.):
    result=dict(ok=False,complete=False,scope_only=True,admitted=False,release_authority=False)
    replay=None;started=time.monotonic()
    try:
        options={k:proposal[k]for k in('library_table','footprint_ids','expected_instance_uuids','board_hint')}
        for key in('optional_body_footprint_ids','reference_mapping_transition','source_chart_group_uuids'):
            if key in proposal:options[key]=proposal[key]
        replay=staged_replay(source,options=options,timeout_s=timeout_s,candidate=candidate,proposal=proposal)
        if options.get('reference_mapping_transition')is not None:replay.map_reconstruct();replay.map_receive()
        replay.plan()
        with tempfile.TemporaryDirectory(prefix='cec-staged-print-expected-')as work:
            replay.reconstruct(Path(work)/'exact');result=replay.receive()
        _need(time.monotonic()-started<replay.observation()['aggregate_limit_s'],'staged_print_aggregate_deadline')
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,StopIteration)as exc:
        result['error']=str(exc)
        if replay is not None:replay._state='failed'
    if 'error'in result:result.update(ok=False,complete=False)
    result['staged_replay']=replay.observation()if replay else None
    if replay is not None:
        observation=replay.observation()
        result['timings_s']=observation['timings_s']
        result['bounded_composition']=dict(kind='fresh_source_plan_reconstruct_saved_native',
            per_constituent_limit_s=timeout_s,constituents=observation['constituents'],
            aggregate_limit_s=observation['aggregate_limit_s'])
    result['elapsed_s']=time.monotonic()-started
    return result


def receive(source, candidate, proposal, *, timeout_s=10.):
    result=dict(ok=False,complete=False,scope_only=True,admitted=False,release_authority=False)
    try:
        _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10,'bounded_print_receiving_required')
        started=time.monotonic();candidate=Path(candidate).resolve(strict=True)
        composed=proposal.get('reference_mapping_transition')is not None
        with tempfile.TemporaryDirectory(prefix='cec-independent-print-context-')as work:
            expected,_,_=_replay_private_family(source,proposal,Path(work)/'exact');root=expected.parent
            reconstruction_done=time.monotonic()
            _need(reconstruction_done-started<timeout_s,'print_source_reconstruction_deadline')
            def files(path):return {p.relative_to(path):p.read_bytes()for p in path.rglob('*')if p.is_file()and p.relative_to(path)!=Path('print-context.json')}
            _need(files(root)==files(candidate.parent),'private_print_board_library_sidecars_not_exact_original_replay')
        old=proposal['old_library_context'];new=ink._stable(libraries.authority(candidate,candidate.parent/'fp-lib-table'))
        metadata=json.loads((candidate.parent/'print-context.json').read_text())
        _need(metadata==dict(candidate=str(candidate),library_table=str(candidate.parent/'fp-lib-table'),
            old_library_context=old,new_library_context=new,physical_original_template_authority_retained=True,
            whole_stage_source_current_native_receiving_still_required=True,admitted=False,release_authority=False),
            'saved_print_context_metadata_or_admission_claim_forged')
        _need(ink._stable(old['references'])==ink._stable(new['references']),'same_fpid_references_changed')
        board=pcbnew.LoadBoard(str(candidate))
        physical_cache={}
        for record in proposal['records']:
            fp=next(f for f in board.GetFootprints()if force._uid(f)==record['footprint_uuid'])
            alias,item=record['fpid'].split(':',1);template=Path(new['rows'][alias]['path'])/(item+'.kicad_mod')
            if 'source_optional_body_contract'in record:
                import cec_optional_body_ink_contract as body
                matched=body._native_match(fp,template)
            else:matched=_physical_match(fp,pcbnew.FootprintLoad(str(template.parent),item),
                expected_cache=physical_cache,template_key=force._hash(template))
            _need(fp.GetFPIDAsString()==record['fpid']and matched,
                'all_same_fpid_native_bodies_must_match_print_derivative')
        with tempfile.TemporaryDirectory(prefix='cec-print-second-save-')as work:
            first=Path(work)/'first.kicad_pcb';second=Path(work)/'second.kicad_pcb'
            ink.field._save_field_snapshot(board,first);ink.field._save_field_snapshot(pcbnew.LoadBoard(str(first)),second)
            _need(ink.syntax._freeze(ink.frame.additive._nodes(first)[0])==ink.syntax._freeze(ink.frame.additive._nodes(second)[0]),'print_second_native_save_unstable')
        finished=time.monotonic()
        _need(finished-(reconstruction_done if composed else started)<timeout_s,'print_receiving_deadline')
        if composed:
            _need(finished-started<2*timeout_s,'print_composed_receiving_deadline')
            result.update(bounded_composition=dict(kind='source_reconstruction_then_saved_native_comparison',
                per_constituent_limit_s=timeout_s,aggregate_limit_s=2*timeout_s),
                timings_s=dict(source_reconstruction=reconstruction_done-started,
                    saved_native_comparison=finished-reconstruction_done,aggregate=finished-started))
        result.update(ok=True,complete=True,old_library_context=old,new_library_context=new,
            exact_same_fpid_source_optional_body_omission_received=True,source_physical_identity_unchanged=True)
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,StopIteration)as exc:result['error']=str(exc)
    return result

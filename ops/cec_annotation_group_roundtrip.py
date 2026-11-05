"""Retire only broken legacy legend groups, preserving every real annotation.

An old producer placed footprint-owned silk graphics in a board-level group.
KiCad serializes those IDs once, reloads the group empty and drops it on the
next save. This typed migration owns ONLY that producer's nonfunctional group
metadata. All child glyphs, native footprints, fields, copper and rules remain
literal Source material. Unknown or functional groups are not normalized.
"""
import json,tempfile
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_dense_reference_mapping as producer
import cec_field_coupling as field
import cec_force_current as force
from cec_native_items import discard_items


def require(condition,message):
    if not condition:raise ValueError(message)


def plan(source,*,board_hint):
    source=Path(source).resolve()
    require(type(board_hint) is str and bool(board_hint),'explicit_annotation_roundtrip_context_required')
    b=pcbnew.LoadBoard(str(source));root,nodes=additive._nodes(source)
    groups={force._uid(g):g for g in b.Groups()};children={}
    for fp in b.GetFootprints():
        for item in fp.GraphicalItems():
            require(force._uid(item) not in children,'unique_source_annotation_child_required')
            children[force._uid(item)]=(fp,item)
    require(len(nodes)+len(children)<=16384,'annotation_group_native_inventory_bound')
    found=[]
    for uid,g in groups.items():
        if list(g.GetItems()):continue
        raw=nodes.get(uid);require(raw and raw[0]=='group','literal_saved_native_annotation_group_required')
        members=additive._members(raw)
        require(g.GetName()==producer.GROUP and g.IsLocked() and 1<=len(members)<=256
            and len(set(members))==len(members),'unknown_empty_or_unresolved_source_group_is_not_a_legend_repair')
        require(all(u in children for u in members),'legacy_legend_group_must_name_actual_footprint_graphics_only')
        for u in members:
            fp,item=children[u]
            require(item.GetClass() in ('PCB_SHAPE','PCB_TEXT')
                and item.GetLayer() in (pcbnew.F_SilkS,pcbnew.B_SilkS)
                and item.IsLocked() and not fp.Reference().IsVisible(),
                'legacy_group_members_must_be_retained_locked_reference_silkscreen_children')
        require(not any(uid in additive._members(n) for n in nodes.values() if n[0]=='group'
            and n is not raw),'legacy_legend_group_cannot_have_a_functional_parent_group')
        found.append(dict(group_uuid=uid,raw_member_uuids=sorted(members),
            native_loaded_member_count=0,retained_owner_footprint_uuids=sorted({force._uid(children[u][0]) for u in members})))
    require(1<=len(found)<=8,'bounded_nonempty_broken_legacy_legend_groups_required')
    return dict(schema=1,source=str(source),source_sha256=force._hash(source),board_hint=board_hint,
        authority_sha256=force._hash(Path(__file__).resolve()),groups=sorted(found,key=lambda r:r['group_uuid']),
        retired_group_uuids=sorted(r['group_uuid'] for r in found),
        actual_annotation_copper_parts_and_rules_unchanged=True,release_authority=False)


def construct(source,proposal):
    require(plan(source,board_hint=proposal['board_hint'])==proposal,'stale_or_forged_annotation_group_roundtrip_plan')
    b=pcbnew.LoadBoard(str(source));ids=set(proposal['retired_group_uuids'])
    discard_items(b,[g for g in b.Groups() if force._uid(g) in ids])
    return b


def receive(source,candidate,proposal,*,board_hint):
    r=dict(ok=False,complete=False,errors=[],fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)]
        require(source!=candidate and board_hint==proposal['board_hint'],'distinct_explicit_annotation_roundtrip_candidate_required')
        epoch=force._code_identity();families=[force._family(f,board_hint) for f in (source,candidate)]
        expected=construct(source,proposal);old_root,old=additive._nodes(source);new_root,new=additive._nodes(candidate)
        retired=set(proposal['retired_group_uuids'])
        require(old.keys()-new.keys()==retired and not new.keys()-old.keys(),
            'only_exact_broken_annotation_group_metadata_may_be_retired')
        def without_groups(root):
            return syntax._freeze([n for n in root if not (type(n) is list and n and n[0]=='group'
                and next((v[1].strip('"') for v in n if type(v) is list and v and v[0]=='uuid'),None) in retired)])
        require(without_groups(old_root)==syntax._freeze(new_root),
            'annotation_group_repair_changed_other_literal_source_evidence')
        with tempfile.TemporaryDirectory(prefix='cec-annotation-roundtrip-') as work:
            path=Path(work)/'expected.kicad_pcb';field._save_field_snapshot(expected,path)
            require(syntax._freeze(additive._nodes(path)[0])==syntax._freeze(new_root),
                'annotation_group_repair_does_not_match_native_reconstruction')
            second=Path(work)/'second.kicad_pcb';field._save_field_snapshot(pcbnew.LoadBoard(str(candidate)),second)
            require(syntax._freeze(additive._nodes(second)[0])==syntax._freeze(new_root),
                'annotation_group_repair_is_not_stable_under_second_native_save')
        require(force._sidecars(source)==force._sidecars(candidate),'annotation_group_repair_changed_companions')
        require(epoch==force._code_identity() and families==[force._family(f,board_hint) for f in (source,candidate)],
            'annotation_group_source_candidate_or_code_changed')
        r.update(ok=True,complete=True,retired_group_uuids=sorted(retired),retired_track_uuids=[],added_native_uuids=[],
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            every_source_item_except_exact_broken_group_metadata_identical=True,
            no_copper_pad_pose_glyph_field_rule_or_valid_group_change=True,
            retained_native_footprint_child_ownership_exact=True,second_native_roundtrip_stable=True,
            source_candidate_and_code_unchanged=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:r['errors'].append(type(exc).__name__+':'+str(exc))
    return r

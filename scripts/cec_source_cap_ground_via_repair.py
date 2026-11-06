"""Exact existing-capacitor Ground-via seating repair, not missing bypass work.

The Source overlap is explicit debt, never a positive in-pad ownership proof.
Only one exclusive pad/filled-plane barrel may change position. No emitted
copper, new hole, changed dimensions, current allocation or release authority.
"""
from pathlib import Path
import math
import tempfile
import re

import pcbnew
import cec_corrective_bypass_ground_barrel as barrel
import cec_source_aggregate_capacitor_cell as cap
import cec_control_gate_bias_placement as native
import cec_additive_route_receiving as additive
import cec_native_partition_pair as partitions
import cec_wired_aggregate_capacitor as wired
import cec_source_literal_additions as literal
import cec_source_literal_retirement as retirement
import cec_source_retaining_ses_import as raw

SCOPE = 'Source_existing_ceramic_partial_overlap_Ground_via_repair-v1'
_EXACT_TOKENS=re.compile(r'"(?:[^"\\]|\\.)*"|;[^\r\n]*|[()]|[^\s();"]+|[^\s]')


def _root_tokens(text):
    """Exact scalar lexemes, excluding only whitespace and line comments.

    The final regex alternative retains malformed/unmatched characters rather
    than silently dropping them. Quoted whitespace/semicolons remain tokens.
    No absent defaults, numeric values or escaped strings are normalized.
    """
    return tuple(m.group()for m in _EXACT_TOKENS.finditer(text)if not m.group().startswith(';'))


def _contained(pad, via, position):
    face = int(pad.GetLayer()); metal = pcbnew.SHAPE_POLY_SET()
    via.TransformShapeToPolygon(metal,face,100,1,pcbnew.ERROR_OUTSIDE)
    metal.Move(pcbnew.VECTOR2I(position[0]-via.GetPosition().x,position[1]-via.GetPosition().y))
    metal.BooleanSubtract(pad.GetEffectivePolygon(face,pcbnew.ERROR_INSIDE))
    return not metal.OutlineCount()


def _no_artwork(board, via, deadline):
    graphics = list(board.GetDrawings())
    for fp in board.GetFootprints():
        graphics.extend(fp.GraphicalItems()); graphics.extend(fp.GetFields())
    barrel._need(len(graphics)<=16384,'repair_bounded_artwork_inventory_required')
    for face in board.GetEnabledLayers().CuStack():
        shape=via.GetEffectiveShape(face)
        for item in graphics:
            barrel._left(deadline)
            if item.GetLayer()!=face:continue
            try:
                if not shape.BBox().Intersects(item.GetBoundingBox()):continue
                hit=shape.Collide(item.GetEffectiveShape(),0)
            except Exception as error:
                raise ValueError('repair_barrel_artwork_contact_unknown') from error
            barrel._need(not hit,'repair_barrel_unsupported_artwork_contact')


def _known_local_zone_fills(board,via,deadline):
    for zone in board.Zones():
        if zone.GetIsRuleArea():continue
        for face in board.GetEnabledLayers().CuStack():
            barrel._left(deadline)
            if not zone.IsOnLayer(face):continue
            gap=max(0,int(board.GetDesignSettings().m_MinClearance),int(zone.GetLocalClearance()))
            try:
                outline=zone.Outline()
                barrel._need(outline.OutlineCount()>0,'repair_zone_outline_unknown')
                relevant=outline.Collide(via.GetEffectiveShape(face),gap)
            except Exception as error:
                raise ValueError('repair_zone_relevance_unknown') from error
            if relevant:
                barrel._need(zone.IsFilled() and zone.HasFilledPolysForLayer(face),
                    'repair_relevant_saved_zone_fill_unknown')


def plan(source, ground_pad_uuid, via_uuid, target_nm, *, board_hint,
         allow_locked_via_uuid=None, timeout_s=10.):
    deadline=barrel._deadline(timeout_s)
    barrel._need(type(board_hint)is str and board_hint and type(target_nm)is list
        and len(target_nm)==2 and all(type(v)is int and abs(v)<=2_000_000_000 for v in target_nm),
        'repair_literal_bounded_target_and_hint_required')
    source=Path(source).resolve(strict=True);digest=barrel.force._hash(source)
    epoch=barrel.force._code_identity();family=barrel.force._family(source,board_hint)
    board=pcbnew.LoadBoard(str(source));binding=cap.row._source_binding(board)
    pad,via,_=barrel._objects(board,ground_pad_uuid,via_uuid)
    barrel._need(allow_locked_via_uuid is None or allow_locked_via_uuid==via_uuid,
        'repair_only_exact_locked_via_consent_required')
    barrel._need(not via.IsLocked()or allow_locked_via_uuid==via_uuid,
        'repair_locked_via_requires_explicit_consent')
    barrel._need(not any(g.ContainsItem(via)for g in board.Groups()),'repair_grouped_via_refused')
    fp=cap._owner(board,barrel.force._uid(pad.GetParentFootprint()),None,source)
    barrel._need(not fp.IsDNP() and pad.GetNetname()=='GND','repair_populated_canonical_ceramic_ground_required')
    canonical=cap._canonical(board,fp,board_hint,deadline)
    barrel._need(any(r['uuid']==ground_pad_uuid and r['net']=='GND'for r in canonical['pins']),
        'repair_exact_canonical_ground_pad_required')
    wired._reject_uninventoried_artwork(board,fp,deadline)
    faces,width,drill=barrel._geometry(board,via)
    _no_artwork(board,via,deadline)
    _known_local_zone_fills(board,via,deadline)
    contacts=barrel._contacts(board,pad,via,deadline)
    source_at=list(via.GetPosition())
    barrel._need(not _contained(pad,via,source_at),
        'repair_requires_explicit_source_partial_overlap_debt')
    barrel._need(0<math.dist(source_at,target_nm)<=1_000_000,
        'repair_nonzero_one_mm_seat_required')
    barrel._need(_contained(pad,via,target_nm),'repair_positive_target_full_land_containment_required')
    ok,reason=barrel.fab.via_pad_decision(board,pad,pcbnew.VECTOR2I(*target_nm),
        via.GetWidth(pad.GetLayer()),via.GetDrillValue(),via.GetNetCode())
    barrel._need(ok,'repair_target_process_refused:'+reason)
    pad_contacts=native._direct_contacts(board,pad,deadline)
    barrel._need(digest==barrel.force._hash(source)and epoch==barrel.force._code_identity()
        and family==barrel.force._family(source,board_hint)
        and all(barrel.force._hash(p)==h for p,h in canonical['files_sha256'].items())
        and barrel.force._hash(canonical['exporter']['exporter'])==canonical['exporter']['exporter_sha256'],
        'repair_source_or_code_epoch_changed')
    barrel._left(deadline)
    return barrel._wire(dict(schema=1,scope=SCOPE,source=str(source),source_sha256=digest,
        board_hint=board_hint,source_native_binding=binding,source_family=family,code_identity=epoch,
        canonical_source=canonical,source_capacitor_identity=native._footprint(board,fp),
        ground_pad_uuid=ground_pad_uuid,via_uuid=via_uuid,allow_locked_via_uuid=allow_locked_via_uuid,
        source_via_at_nm=source_at,target_nm=target_nm,source_debt='existing_partial_overlap_not_positive_inpad_ownership',
        via_process=barrel._via_process(source,via_uuid),diameter_nm=width,drill_nm=drill,
        connected_layer_ids=list(map(int,faces)),source_reference_contacts=contacts,
        source_ground_pad_contacts=pad_contacts,all_original_returns_and_partitions_mandatory=True,
        source_inpad_containment_qualified=False,target_positive_containment_margin_nm=100,
        new_barrel_authority=False,other_material_cut_authority=False,current_qualified=False,
        fabrication_qualified=False,clearance_qualified=False,admitted=False,release_authority=False))


def receive(source,candidate,proposal,*,board_hint,timeout_s=10.):
    deadline=barrel._deadline(timeout_s)
    barrel._need(proposal.get('scope')==SCOPE and proposal.get('board_hint')==board_hint,
        'repair_exact_source_role_and_hint_required')
    fresh=plan(source,proposal['ground_pad_uuid'],proposal['via_uuid'],proposal['target_nm'],
        board_hint=board_hint,allow_locked_via_uuid=proposal['allow_locked_via_uuid'],
        timeout_s=barrel._left(deadline))
    barrel._need(fresh==proposal,'repair_requires_exact_fresh_source_replay')
    source=Path(source).resolve(strict=True);candidate=Path(candidate).resolve(strict=True)
    barrel._need(source!=candidate and not source.samefile(candidate),'repair_distinct_saved_candidate_required')
    digest=barrel.force._hash(candidate);family=barrel.force._family(candidate,board_hint)
    barrel._need(barrel.force._sidecars(source)==barrel.force._sidecars(candidate),
        'repair_exact_unchanged_source_sidecar_family_required')
    parent,child=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
    pad,via,_=barrel._objects(child,proposal['ground_pad_uuid'],proposal['via_uuid'])
    barrel._need(list(via.GetPosition())==proposal['target_nm']
        and barrel._via_process(candidate,proposal['via_uuid'])==proposal['via_process'],
        'repair_exact_position_and_unchanged_via_process_required')
    barrel._need(_contained(pad,via,list(via.GetPosition())),'repair_saved_full_land_containment_required')
    _no_artwork(child,via,deadline)
    _known_local_zone_fills(child,via,deadline)
    contacts=barrel._contacts(child,pad,via,deadline)
    barrel._need(set((r['zone_uuid'],r['layer_id'])for r in contacts)>=
        set((r['zone_uuid'],r['layer_id'])for r in proposal['source_reference_contacts']),
        'repair_original_actual_ground_reference_destinations_lost')
    with tempfile.TemporaryDirectory(prefix='cec-source-ground-via-repair-')as work:
        expected=barrel.force._copy_family(source,Path(work)/'expected')
        _,oldvia,_=barrel._objects(parent,proposal['ground_pad_uuid'],proposal['via_uuid'])
        oldvia.SetPosition(pcbnew.VECTOR2I(*proposal['target_nm']))
        ground=additive._ground_refill(parent)
        snapshot=Path(work)/'native.kicad_pcb'
        additive.field._save_field_snapshot(parent,snapshot)
        # Native Save may normalize unrelated opaque nodes (e.g. add an
        # explicit zero text angle). Preserve original lexemes and replace
        # ONLY the independently produced via node and existing Ground fills.
        expected.write_text(literal.assemble(
            retirement.subtract(raw.raw_text(source),{proposal['via_uuid']}),
            raw.raw_text(snapshot),ground_ids=ground))
        # Full expected-root token equality is stricter than additive delta
        # acceptance. The expected frame above already independently refills
        # Ground; repeating a second additive native refill adds no proof.
        barrel._left(deadline)
        barrel._need(_root_tokens(raw.raw_text(expected))==
                     _root_tokens(raw.raw_text(candidate)),
            'repair_only_exact_via_seat_and_independently_replayed_ground_fill_allowed')
        exact=dict(ok=True,complete=True,full_expected_native_root_tokens_equal=True,
            independent_native_ground_refill=True,source_opaque_nodes_preserved=True,
            added_native_uuids=[],whitespace_and_comments_only_ignored=True,
            expected_sha256=barrel.force._hash(expected))
    original=pcbnew.LoadBoard(str(source))
    physical=partitions.compare(original,child,timeout_s=barrel._left(deadline),
        retired_uuids={proposal['via_uuid']})
    barrel._need(physical['available']is True and physical['preserved']is True,
        'repair_all_original_ground_and_other_native_partitions_required')
    barrel._need(digest==barrel.force._hash(candidate)and family==barrel.force._family(candidate,board_hint)
        and proposal['source_sha256']==barrel.force._hash(source)
        and proposal['source_family']==barrel.force._family(source,board_hint)
        and proposal['code_identity']==barrel.force._code_identity(),'repair_receiving_epoch_changed')
    barrel._left(deadline)
    return barrel._wire(dict(scope=SCOPE,ok=True,complete=True,source_sha256=proposal['source_sha256'],
        candidate_sha256=digest,exact_saved_frame=exact,retained_native_partitions=physical,
        candidate_reference_contacts=contacts,original_via_dimensions_and_identity_preserved=True,
        original_returns_preserved=True,source_debt_repaired=True,new_barrel_authority=False,
        current_qualified=False,fabrication_qualified=False,clearance_qualified=False,
        release_authority=False,admitted=False))

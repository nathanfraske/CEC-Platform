"""A pretty plot cannot replace complete source-relative native evidence."""
import math


def require_saved_grade(grade, *, epoch, source_sha256, candidate_sha256,
                        contour_construction=None, board_hint=None):
    if (grade.get('code_identity')!=epoch
            or grade.get('source_candidate_and_code_unchanged') is not True
            or grade.get('new_native_fault_ids')!=[]):
        raise ValueError('current_complete_fault_identity_grade_required')
    clipped=grade.get('clipped_kelvin_comparison') or {}
    if clipped.get('comparison_complete') is not True:
        raise ValueError('changed_or_incomplete_clipped_evidence_cannot_publish_as_nonregression')
    requalification = None
    keeper_requalification = None
    force_requalification = None
    face_requalification = None
    joint_bank_requalification = None
    bank_repair_requalification = None
    bundle_requalification = None
    planar_requalification = None
    if isinstance(contour_construction,dict) and contour_construction.get('native_planar_current_chain'):
        if (not board_hint or contour_construction.get('source_sha256')!=source_sha256
                or contour_construction.get('candidate_sha256')!=candidate_sha256):
            raise ValueError('exact_hash_native_planar_current_lineage_required')
        import cec_full_current_planar_reflow as planar
        planar_requalification=planar.receive_force_sense_chain(contour_construction['source'],
            contour_construction['candidate'],board_hint=board_hint,
            phases=contour_construction['native_planar_current_chain'])
        physical=planar_requalification.get('physical_preservation') or {}
        if (planar_requalification.get('ok') is not True or planar_requalification.get('complete') is not True
                or planar_requalification.get('source_sha256')!=source_sha256
                or planar_requalification.get('candidate_sha256')!=candidate_sha256
                or planar_requalification.get('code_identity')!=epoch
                or physical.get('comparison_complete') is not True or physical.get('same_evidence') is not True):
            raise ValueError('fresh_exact_planar_current_and_absolute_cut_requalification_required')
        planar_requalification.pop('source_sense');planar_requalification.pop('candidate_sense')
    if isinstance(contour_construction,dict) and contour_construction.get('native_force_bundle_scope'):
        if (not board_hint or contour_construction.get('source_sha256')!=source_sha256
                or contour_construction.get('candidate_sha256')!=candidate_sha256):
            raise ValueError('exact_hash_native_force_bundle_construction_required')
        import cec_redundant_force_bundle as bundles
        bundle_requalification=bundles.receive(contour_construction['source'],
            contour_construction['candidate'],board_hint=board_hint,timeout_s=20.,
            **contour_construction['native_force_bundle_scope'])
        if (bundle_requalification.get('ok') is not True
                or bundle_requalification.get('complete') is not True
                or bundle_requalification.get('source_sha256')!=source_sha256
                or bundle_requalification.get('candidate_sha256')!=candidate_sha256
                or bundle_requalification.get('code_identity')!=epoch):
            raise ValueError('fresh_exact_native_force_bundle_requalification_required')
        bundle_requalification.pop('source_sense');bundle_requalification.pop('candidate_sense')
    if isinstance(contour_construction,dict) and contour_construction.get('native_force_bank_receiving'):
        if (not board_hint or contour_construction.get('source_sha256')!=source_sha256
                or contour_construction.get('candidate_sha256')!=candidate_sha256):
            raise ValueError('exact_hash_native_force_bank_repair_construction_required')
        import cec_force_bank_repair as bank
        bank_repair_requalification=bank.receive(contour_construction['source'],
            contour_construction['candidate'],board_hint=board_hint,timeout_s=20.)
        if (bank_repair_requalification.get('ok') is not True
                or bank_repair_requalification.get('complete') is not True
                or bank_repair_requalification.get('source_sha256')!=source_sha256
                or bank_repair_requalification.get('candidate_sha256')!=candidate_sha256
                or bank_repair_requalification.get('code_identity')!=epoch):
            raise ValueError('fresh_exact_native_source_bank_repair_requalification_required')
        bank_repair_requalification.pop('source_sense');bank_repair_requalification.pop('candidate_sense')
    if (isinstance(contour_construction,dict) and contour_construction.get('scope')
            == 'private_joint_pth_bank_and_full_load_branch_prototype'):
        if (not board_hint or contour_construction.get('source_sha256')!=source_sha256
                or contour_construction.get('candidate_sha256')!=candidate_sha256):
            raise ValueError('exact_hash_joint_bank_force_preclear_construction_required')
        from root_native_pth_bank_preclear_receiving_20261013 import receive as receive_bank
        # Rebuild the whole zone on the opposite equal-thickness face from
        # the SOURCE, receive full-original-load incoming copper, restore all
        # old material contacts, and replay absolute changed/unaffected cuts.
        # A producer's success flag or an old matching counter is not proof.
        joint_bank_requalification=receive_bank(contour_construction['source'],
            contour_construction['candidate'],dict(
                source_zone_uuid=contour_construction.get('reflowed_zone_uuid'),
                target_layer=contour_construction.get('target_layer'),
                enclosure_margin_nm=contour_construction.get('source_bank_enclosure_margin_nm'),
                retired_track_uuids=contour_construction.get('retired_track_uuids')),
            board_hint=board_hint)
        preservation=joint_bank_requalification.get('physical_kelvin_preservation') or {}
        if (joint_bank_requalification.get('ok') is not True
                or joint_bank_requalification.get('complete') is not True
                or joint_bank_requalification.get('source_sha256')!=source_sha256
                or joint_bank_requalification.get('candidate_sha256')!=candidate_sha256
                or joint_bank_requalification.get('code_identity')!=epoch
                or joint_bank_requalification.get('exact_native_reconstruction') is not True
                or preservation.get('comparison_complete') is not True
                or preservation.get('same_evidence') is not True):
            raise ValueError('independent_fresh_joint_bank_force_preclear_receiving_refused:'
                +str(joint_bank_requalification.get('errors')))
    if isinstance(contour_construction,dict) and contour_construction.get('force_branch_scope'):
        if (not board_hint or contour_construction.get('source_sha256')!=source_sha256
                or contour_construction.get('candidate_sha256')!=candidate_sha256):
            raise ValueError('exact_hash_force_face_cut_construction_required')
        from root_native_redundant_force_face_receiving_20261012 import receive as receive_face
        face_requalification=receive_face(contour_construction['source'],contour_construction['candidate'],
            contour_construction['force_branch_scope'],board_hint=board_hint)
        if (not face_requalification['ok'] or not face_requalification['complete']
                or face_requalification.get('code_identity')!=epoch):
            raise ValueError('independent_fresh_source_force_face_cut_receiving_refused')
    if isinstance(contour_construction,dict) and contour_construction.get('crossface_phase')=='typed_owned_force_crossface':
        if (not board_hint or contour_construction.get('source_sha256')!=source_sha256
                or contour_construction.get('candidate_sha256')!=candidate_sha256):
            raise ValueError('exact_hash_owned_force_crossface_construction_required')
        import cec_force_crossface_receiving as crossface
        force_requalification=crossface.receive(contour_construction['source'],contour_construction['candidate'],
            contour_construction.get('retired_track_uuids'),board_hint=board_hint)
        if (not force_requalification['ok'] or not force_requalification['complete']
                or force_requalification.get('code_identity')!=epoch):
            raise ValueError('independent_fresh_owned_force_crossface_receiving_refused')
    if isinstance(contour_construction, dict) and contour_construction.get('contour_phase') == 'typed_owned_keeper_recompile':
        if (not board_hint or contour_construction.get('source_sha256') != source_sha256
                or contour_construction.get('candidate_sha256') != candidate_sha256):
            raise ValueError('exact_hash_keeper_recompile_construction_required')
        from root_native_keeper_recompile_receiving_20261012 import receive as receive_keeper
        keeper_requalification = receive_keeper(contour_construction['source'], contour_construction['candidate'],
            contour_construction.get('contours'), board_hint=board_hint)
        if (keeper_requalification.get('ok') is not True or keeper_requalification.get('complete') is not True
                or keeper_requalification.get('source_sha256') != source_sha256
                or keeper_requalification.get('candidate_sha256') != candidate_sha256
                or keeper_requalification.get('code_identity') != epoch):
            raise ValueError('independent_fresh_keeper_requalification_refused:'
                             + str(keeper_requalification.get('errors')))
    if (clipped.get('same_evidence') is not True and keeper_requalification is None
            and joint_bank_requalification is None and bank_repair_requalification is None
            and bundle_requalification is None and planar_requalification is None):
        if (not isinstance(contour_construction, dict) or not board_hint
                or contour_construction.get('source_sha256') != source_sha256
                or contour_construction.get('candidate_sha256') != candidate_sha256):
            raise ValueError('changed_or_incomplete_clipped_evidence_cannot_publish_as_nonregression')
        from root_native_positive_contour_receiving_20261012 import receive
        # A worker's JSON success flag is never an authorization. The gate
        # itself replays the exact saved native boards, owned additive zones,
        # full source current debt and both absolute physical cuts now.
        requalification = receive(contour_construction['source'], contour_construction['candidate'],
            contour_construction.get('contours'), board_hint=board_hint)
        if (requalification.get('ok') is not True or requalification.get('complete') is not True
                or requalification.get('source_sha256') != source_sha256
                or requalification.get('candidate_sha256') != candidate_sha256
                or requalification.get('code_identity') != epoch):
            raise ValueError('independent_fresh_positive_contour_requalification_refused:'
                             + str(requalification.get('errors')))
    boards=grade.get('boards') or {}
    maps=[]
    for key,wanted in (('source',source_sha256),('candidate',candidate_sha256)):
        row=boards.get(key) or {};native=row.get('native_producer') or {}
        if (row.get('sha256')!=wanted or native.get('ok') is not True
                or native.get('complete') is not True
                or (native.get('native_inventory') or {}).get('potentially_truncated') is not False
                or any(type(row.get(k)) is not int or row[k]<0 for k in ('opens','scored_drc'))):
            raise ValueError('exact_hash_uncapped_native_grade_required')
        entries=row.get('full50_checks') or []
        mapping={item.get('id'):item.get('status') for item in entries}
        if (len(entries)!=50 or len(mapping)!=50 or None in mapping
                or any(status not in ('PASS','FAIL','N/A','DECLARED') for status in mapping.values())):
            raise ValueError('complete_unique_fifty_check_grade_required')
        maps.append(mapping)
        bbox=row.get('board_bbox_mm')
        if (type(bbox) is not list or len(bbox)!=4
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in bbox)
                or any(bbox[i+2]<=bbox[i] for i in range(2))):
            raise ValueError('actual_native_outline_evidence_required')
    before,after=[boards[k] for k in ('source','candidate')]
    if (any(after[k]>before[k] for k in ('opens','scored_drc'))
            or any(round((after['board_bbox_mm'][i+2]-after['board_bbox_mm'][i])*1e6)>
                round((before['board_bbox_mm'][i+2]-before['board_bbox_mm'][i])*1e6) for i in range(2))):
        raise ValueError('native_count_or_outline_regression_refused')
    if maps[0].keys()!=maps[1].keys() or any(
            maps[1][key]!=old and not (old=='FAIL' and maps[1][key]=='PASS')
            for key,old in maps[0].items()):
        raise ValueError('existing_design_check_status_regressed_or_changed')
    return dict(scope='complete_native_nonregression_not_fabrication_qualification',
        same_clipped_evidence_preserved=clipped.get('same_evidence') is True,
        independent_fresh_positive_contour_requalification=requalification,
        independent_fresh_keeper_requalification=keeper_requalification,
        independent_fresh_owned_force_crossface_requalification=force_requalification,
        independent_fresh_source_force_face_cut_requalification=face_requalification,
        independent_fresh_joint_bank_force_preclear_requalification=joint_bank_requalification,
        independent_fresh_native_force_bank_repair_requalification=bank_repair_requalification,
        independent_fresh_native_force_bundle_requalification=bundle_requalification,
        independent_fresh_native_planar_current_requalification=planar_requalification,
        all_fifty_check_statuses_preserved=True,
        release_authority=False)

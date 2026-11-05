"""Native producer/continuation ownership, never blanket unlock or signoff."""
import json
from pathlib import Path

import pytest

import cec_route_copper_lineage as lineage
from test_local_copper_cell import native_cell


def generated_family(tmp_path):
    import pcbnew
    board, fps, internal, external, _, track = native_cell()
    before, after = tmp_path/'before.kicad_pcb', tmp_path/'after.kicad_pcb'
    external.SetLocked(True)
    pcbnew.SaveBoard(str(before), board)
    added = track((10, 10), (12, 10))
    added.SetLocked(True)
    pcbnew.SaveBoard(str(after), board)
    return before, after, added.m_Uuid.AsString(), external.m_Uuid.AsString()


@pytest.mark.parametrize('fault',['none','hash','schema','kind','missing','terminals'])
def test_declared_actual_origin_replaces_only_an_identical_routed_baseline(tmp_path,fault):
    import hashlib
    import pcbnew
    before,after,uid,authored=generated_family(tmp_path)
    row=dict(schema=1,kind='pipeline_placement_authored_prefix',board=str(before),
        sha256=hashlib.sha256(before.read_bytes()).hexdigest())
    if fault=='hash':row['sha256']='0'*64
    elif fault=='schema':row['schema']=True
    elif fault=='kind':row['kind']='unverified_hint'
    elif fault=='missing':row['board']=str(tmp_path/'absent.kicad_pcb')
    elif fault=='terminals':
        foreign,_,_,_,_,_=native_cell(names=('OTHER','FOREIGN'))
        pcbnew.SaveBoard(str(before),foreign)
        row['sha256']=hashlib.sha256(before.read_bytes()).hexdigest()
    after.with_suffix('.authored-prefix.json').write_text(json.dumps(row))
    selected=lineage.resolve_authored_baseline(after,str(after))
    assert selected==str(before if fault=='none' else after)
    if fault=='none':
        assert lineage.generated_locked(after,selected)==(uid,)
        assert authored not in lineage.generated_locked(after,selected)


def test_a_distinct_explicit_origin_is_never_overridden_by_sidecar(tmp_path):
    before,after,_,_=generated_family(tmp_path)
    after.with_suffix('.authored-prefix.json').write_text('{"schema": 1}')
    assert lineage.resolve_authored_baseline(after,str(before))==str(before)


def test_durable_read_only_authority_survives_renamed_continuation(tmp_path):
    import cec_fr
    import cec_certificate_repair as repair
    before, after, uid, authored = generated_family(tmp_path)
    original = after.read_bytes()
    report = lineage.record(before, after, producer='synthetic-route-stage')
    assert report['ok'] and report['added_members'] == 1
    copied = tmp_path/'renamed.kicad_pcb'
    repair._copy_board_family(str(after), str(copied))
    # The continuation's immediate baseline already contains generated copper.
    assert repair._generated_locked_route_uuids(str(copied), str(copied)) == (uid,)
    assert repair._generated_locked_route_uuids(str(copied), None) == (uid,)
    assert authored not in lineage.generated_locked(after, before)
    assert after.read_bytes() == original and copied.read_bytes() == original
    assert copied.with_suffix(lineage.SUFFIX).read_bytes() == after.with_suffix(lineage.SUFFIX).read_bytes()
    # Reusing that path for a source with no lineage cannot retain stale rights.
    repair._copy_board_family(str(before), str(copied))
    assert not copied.with_suffix(lineage.SUFFIX).exists()
    assert lineage.generated_locked(copied) == ()


def test_saved_provenance_enables_only_the_generated_rigid_cell(tmp_path):
    import pcbnew
    import cec_certificate_repair as repair
    from cec_native_items import discard_items
    board, fps, internal, external, _, track = native_cell()
    discard_items(board, internal)
    external.SetLocked(True)
    before, after = tmp_path/'placed.kicad_pcb', tmp_path/'routed.kicad_pcb'
    pcbnew.SaveBoard(str(before), board)
    added = [track((5, 5), (6, 5)), track((6, 5), (7, 6)), track((7, 6), (8, 6))]
    for item in added: item.SetLocked(True)
    ids = {item.m_Uuid.AsString() for item in added}
    pcbnew.SaveBoard(str(after), board)
    assert lineage.record(before, after, producer='synthetic-detail-route')['ok']
    routed_baseline = tmp_path/'routed-baseline.kicad_pcb'
    repair._copy_board_family(str(after), str(routed_baseline))
    permissions = repair._generated_locked_route_uuids(str(after), str(after))
    assert set(permissions) == ids
    request = repair.FootprintRepairTarget(ref='A17', target_net='/LOCAL',
        endpoint_ref='B92', endpoint_pad='1', endpoint_x_mm=8., endpoint_y_mm=6.,
        hit_count=1, distance_mm=4., priority=(0,), companion_refs=('B92',))
    changed, move = repair._relocate_footprint_worker(str(after), repair.asdict(request),
        dict(dx_mm=.25, dy_mm=.25, rotation_delta_deg=90),
        generated_locked_uuids=permissions)
    assert changed, move
    assert set(move['moved_internal_track_uuids']) == ids
    assert move['copper_ownership']['retained_unrelated_items'] == 1
    assert move['copper_ownership']['ok']
    assert set(lineage.generated_locked(after)) == ids
    assert move['lineage_motion']['reissued_members'] == 3
    assert move['lineage_motion']['new_authority_members'] == 0
    # Final routing provenance must not erase a separately certified mutation
    # of objects that already existed in this continuation's input.
    final = lineage.record(routed_baseline, after, producer='final-copper-stage')
    assert final['inherited_members'] == 3 and final['added_members'] == 0
    assert set(lineage.generated_locked(after)) == ids


@pytest.mark.parametrize('tamper', ['geometry', 'layer', 'width', 'net', 'pad_net', 'pad_identity'])
def test_stale_member_or_electrical_context_grants_no_authority(tmp_path, tamper):
    import pcbnew
    before, after, uid, _ = generated_family(tmp_path)
    assert lineage.record(before, after, producer='synthetic')['ok']
    board = pcbnew.LoadBoard(str(after))
    item = next(obj for obj in board.GetTracks() if obj.m_Uuid.AsString() == uid)
    if tamper == 'geometry': item.SetEnd(pcbnew.VECTOR2I_MM(13, 10))
    elif tamper == 'layer': item.SetLayer(pcbnew.B_Cu)
    elif tamper == 'width': item.SetWidth(pcbnew.FromMM(.3))
    else:
        other_net = pcbnew.NETINFO_ITEM(board, '/DIFFERENT')
        board.Add(other_net)
        if tamper == 'net': item.SetNet(other_net)
        else:
            pad = next(iter(board.FindFootprintByReference('A17').Pads()))
            if tamper == 'pad_net': pad.SetNet(other_net)
            else: pad.SetNumber('different')
    pcbnew.SaveBoard(str(after), board)
    assert lineage.generated_locked(after) == ()


def test_baseline_mismatch_cannot_authorize_every_locked_item(tmp_path):
    import pcbnew
    before, after, uid, _ = generated_family(tmp_path)
    # Explicit real same-terminal input proves just the newly generated item.
    assert lineage.generated_locked(after, before) == (uid,)
    unrelated, _, _, _, _, _ = native_cell(names=('FOREIGN', 'ANOTHER'))
    empty = tmp_path/'unrelated.kicad_pcb'
    pcbnew.SaveBoard(str(empty), unrelated)
    assert lineage.generated_locked(after, empty) == ()
    pcbnew.SaveBoard(str(empty), pcbnew.CreateEmptyBoard())
    assert lineage.generated_locked(after, empty) == ()
    assert lineage.generated_locked(after, tmp_path/'absent.kicad_pcb') == ()


def test_unrelated_pose_changes_do_not_erase_true_producer_identity(tmp_path):
    import pcbnew
    before, after, uid, _ = generated_family(tmp_path)
    assert lineage.record(before, after, producer='synthetic')['ok']
    board = pcbnew.LoadBoard(str(after))
    board.FindFootprintByReference('A17').SetPosition(pcbnew.VECTOR2I_MM(6, 5))
    pcbnew.SaveBoard(str(after), board)
    assert lineage.generated_locked(after) == (uid,)


def test_new_stage_carries_only_matching_inherited_and_new_items(tmp_path):
    import pcbnew
    before, after, uid, _ = generated_family(tmp_path)
    assert lineage.record(before, after, producer='first')['ok']
    board = pcbnew.LoadBoard(str(after))
    old = next(obj for obj in board.GetTracks() if obj.m_Uuid.AsString() == uid)
    new = pcbnew.PCB_VIA(board)
    new.SetPosition(pcbnew.VECTOR2I_MM(15, 15))
    new.SetWidth(pcbnew.FromMM(.5)); new.SetDrill(pcbnew.FromMM(.25))
    new.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); new.SetNet(old.GetNet()); new.SetLocked(True)
    board.Add(new)
    final = tmp_path/'final.kicad_pcb'
    pcbnew.SaveBoard(str(final), board)
    report = lineage.record(after, final, producer='second')
    assert report['inherited_members'] == 1 and report['added_members'] == 1
    assert set(lineage.generated_locked(final)) == {uid, new.m_Uuid.AsString()}
    # A changed inherited item isn't silently reauthorized by UUID alone.
    old.SetEnd(pcbnew.VECTOR2I_MM(13, 10)); pcbnew.SaveBoard(str(final), board)
    report = lineage.record(after, final, producer='changed-inherited')
    assert report['inherited_members'] == 0
    assert lineage.generated_locked(final) == (new.m_Uuid.AsString(),)


@pytest.mark.parametrize('payload', ['{', '[]', '{"schema": 2}', '{"schema": 1, "members": []}'])
def test_malformed_receipt_never_supplies_permission(tmp_path, payload):
    before, after, _, _ = generated_family(tmp_path)
    after.with_suffix(lineage.SUFFIX).write_text(payload)
    assert lineage.generated_locked(after) == ()


def test_receipt_is_an_evidence_dependency(tmp_path):
    import cec_route_evidence as evidence
    before, after, _, _ = generated_family(tmp_path)
    deps = evidence.artifact_paths(after)
    assert deps[lineage.SUFFIX] == after.with_suffix(lineage.SUFFIX)
    old = evidence.files(deps)
    assert lineage.record(before, after, producer='synthetic')['ok']
    assert evidence.files(deps) != old


def test_oracle_wires_before_certificate_and_after_finishing():
    source = Path('scripts/cec_synth_pipeline.py').read_text()
    route = source[source.index('def route_oracle_grade('):source.index('def _oracle_fail_dict(')]
    assert route.index('producer="route_oracle_pre_certificate"') < route.index('authored_baseline=placed')
    assert route.index('producer="route_oracle_final_copper"') > route.index('final_degenerate_cleanup')
    assert '"generated_copper_lineage": _final_lineage' in route


def test_capture_error_grants_nothing_and_preserves_boards(tmp_path):
    before, after, _, _ = generated_family(tmp_path)
    original = after.read_bytes()
    report = lineage.record_optional(tmp_path/'missing', after, producer='synthetic')
    assert not report['ok'] and report['release_authority'] is False
    assert not after.with_suffix(lineage.SUFFIX).exists()
    assert after.read_bytes() == original


def mutation_fixture(tmp_path):
    import pcbnew
    before, after, uid, authored = generated_family(tmp_path)
    assert lineage.record(before, after, producer='synthetic')['ok']
    board = pcbnew.LoadBoard(str(after))
    token = lineage.begin_owned_mutation(after, board)
    item = next(obj for obj in board.GetTracks() if obj.m_Uuid.AsString() == uid)
    return after, board, token, item, uid, authored


@pytest.mark.parametrize('change', ['width', 'layer', 'net', 'lock'])
def test_positional_permission_cannot_change_other_conductor_properties(tmp_path, change):
    import pcbnew
    after, board, token, item, uid, _ = mutation_fixture(tmp_path)
    original = after.read_bytes()
    if change == 'width': item.SetWidth(pcbnew.FromMM(.5))
    elif change == 'layer': item.SetLayer(pcbnew.B_Cu)
    elif change == 'lock': item.SetLocked(False)
    else:
        net = pcbnew.NETINFO_ITEM(board, '/OTHER')
        board.Add(net); item.SetNet(net)
    receipt, report = lineage.reissue_owned_mutation(token, board, moved=[uid], producer='motion')
    assert receipt is None and not report['ok']
    assert report['changed_property_uuids'] == [uid]
    assert after.read_bytes() == original


def test_declared_motion_does_not_hide_unrelated_changes(tmp_path):
    import pcbnew
    after, board, token, item, uid, authored = mutation_fixture(tmp_path)
    other = next(obj for obj in board.GetTracks() if obj.m_Uuid.AsString() == authored)
    other.Move(pcbnew.VECTOR2I_MM(.5, .5))
    receipt, report = lineage.reissue_owned_mutation(token, board, moved=[uid], producer='motion')
    assert receipt is None and not report['ok']
    assert report['copper']['unauthorized_uuids'] == [authored]


def test_receipt_membership_never_expands_to_unproven_motion(tmp_path):
    import pcbnew
    after, board, token, item, uid, authored = mutation_fixture(tmp_path)
    # An explicitly caller-owned mutation of a different item still must not
    # turn that item's unknown producer into a generated-copper claim.
    other = next(obj for obj in board.GetTracks() if obj.m_Uuid.AsString() == authored)
    other.Move(pcbnew.VECTOR2I_MM(.5, .5))
    receipt, report = lineage.reissue_owned_mutation(token, board, moved=[authored], producer='motion')
    assert report['ok'] and report['new_authority_members'] == 0
    assert set(receipt['members']) == {uid}


def test_mutation_receipt_failure_rolls_back_native_board_and_receipt(tmp_path, monkeypatch):
    import pcbnew
    after, board, token, item, uid, _ = mutation_fixture(tmp_path)
    item.Move(pcbnew.VECTOR2I_MM(.25, -.25))
    receipt, report = lineage.reissue_owned_mutation(token, board, moved=[uid], producer='motion')
    assert report['ok']
    replace = lineage.os.replace
    def fail_second(source, destination):
        if Path(source).name == 'receipt.json':
            # Simulate a writer that touched the receipt before reporting an
            # error: recovery must restore BOTH artifacts, not just the PCB.
            Path(destination).write_bytes(b'partial receipt')
            raise OSError('injected publication error')
        return replace(source, destination)
    monkeypatch.setattr(lineage.os, 'replace', fail_second)
    with pytest.raises(OSError, match='injected publication'):
        lineage.commit_owned_mutation(after, board, token, receipt)
    assert after.read_bytes() == token['board_bytes']
    assert after.with_suffix(lineage.SUFFIX).read_bytes() == token['receipt_bytes']
    assert not list(tmp_path.glob('.cec-owned-motion-*'))


def test_native_stage_save_failure_never_touches_published_artifacts(tmp_path, monkeypatch):
    import pcbnew
    after, board, token, item, uid, _ = mutation_fixture(tmp_path)
    item.Move(pcbnew.VECTOR2I_MM(.25, -.25))
    receipt, report = lineage.reissue_owned_mutation(token, board, moved=[uid], producer='motion')
    def fail_save(path, _board):
        Path(path).write_bytes(b'partial PCB')
        raise OSError('injected native save')
    monkeypatch.setattr(pcbnew, 'SaveBoard', fail_save)
    with pytest.raises(OSError, match='injected native save'):
        lineage.commit_owned_mutation(after, board, token, receipt)
    assert after.read_bytes() == token['board_bytes']
    assert after.with_suffix(lineage.SUFFIX).read_bytes() == token['receipt_bytes']


@pytest.mark.parametrize('changed', ['board', 'receipt'])
def test_stale_capture_cannot_overwrite_a_newer_input(tmp_path, changed):
    after, board, token, item, uid, _ = mutation_fixture(tmp_path)
    receipt, report = lineage.reissue_owned_mutation(token, board, producer='motion')
    target = after if changed == 'board' else after.with_suffix(lineage.SUFFIX)
    target.write_bytes(b'newer external state')
    with pytest.raises(RuntimeError, match='inputs changed'):
        lineage.commit_owned_mutation(after, board, token, receipt)
    assert target.read_bytes() == b'newer external state'

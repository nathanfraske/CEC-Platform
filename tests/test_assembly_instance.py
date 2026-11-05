"""A selected saved pair replaces stale peers, never physical requirements."""
import json

import pytest

import cec_assembly_instance as instance


def bound_fixture(tmp_path):
    paths = {key: tmp_path / (key + '.data') for key in ('carrier', 'cover', 'contract')}
    for key, path in paths.items():
        path.write_text(key)
    records = {key: dict(path=str(path), sha256=instance.digest(path)) for key, path in paths.items()}
    context = dict(schema=1, role='carrier', contract=records['contract'],
                   members={key: records[key] for key in instance.ROLES})
    return paths, context


@pytest.mark.parametrize('role', instance.ROLES)
def test_literal_member_and_contract_are_all_bound(tmp_path, role):
    paths, context = bound_fixture(tmp_path)
    context['role'] = role
    result = instance.resolve(paths[role], context, tmp_path)
    assert result['role'] == role and len(result['hashes']) == 3


@pytest.mark.parametrize('changed', ['carrier', 'cover', 'contract'])
def test_mutated_dependency_never_falls_back_to_legacy_policy(tmp_path, changed):
    paths, context = bound_fixture(tmp_path)
    paths[changed].write_text('changed')
    with pytest.raises(ValueError, match='hash changed'):
        instance.resolve(paths['carrier'], context, tmp_path)


@pytest.mark.parametrize('fault', ['missing_member', 'wrong_role', 'wrong_file', 'same_member',
                                  'uppercase_hash', 'short_hash', 'missing_hash', 'extra_field',
                                  'boolean_schema', 'unknown_schema', 'empty', 'missing_contract'])
def test_incomplete_or_ambiguous_context_is_refused(tmp_path, fault):
    paths, context = bound_fixture(tmp_path)
    reviewed = paths['carrier']
    if fault == 'missing_member': del context['members']['cover']
    elif fault == 'wrong_role': context['role'] = 'nearest'
    elif fault == 'wrong_file': reviewed = paths['cover']
    elif fault == 'same_member': context['members']['cover'] = context['members']['carrier']
    elif fault == 'uppercase_hash': context['contract']['sha256'] = 'A' * 64
    elif fault == 'short_hash': context['contract']['sha256'] = 'a' * 63
    elif fault == 'missing_hash': del context['contract']['sha256']
    elif fault == 'extra_field': context['allow_failure'] = True
    elif fault == 'boolean_schema': context['schema'] = True
    elif fault == 'unknown_schema': context['schema'] = 2
    elif fault == 'empty': context = {}
    else: del context['contract']
    with pytest.raises(ValueError):
        instance.resolve(reviewed, context, tmp_path)


def native_fixture(tmp_path, *, reflected, collision=False):
    pcbnew = pytest.importorskip('pcbnew')
    import cec_swig_guard
    cec_swig_guard.pin()
    a, b = pcbnew.BOARD(), pcbnew.BOARD()
    for board in (a, b):
        for start, end in [((0, 0), (100, 0)), ((100, 0), (100, 100)),
                           ((100, 100), (0, 100)), ((0, 100), (0, 0))]:
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*start))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
            edge.SetLayer(pcbnew.Edge_Cuts)
            edge.SetWidth(pcbnew.FromMM(.05))
            board.Add(edge)
    transform = [-1, 0, 0, 1, 100, 3] if reflected else [1, 0, 0, 1, 4, 3]
    for idx, board in enumerate((a, b)):
        for ref, kind, xy in [('RENAMED_MATE', 'link', (20, 30))] + (
                [('RENAMED_BODY', 'block', (40, 40))] if collision else []):
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference(ref)
            fp.SetFPID(pcbnew.LIB_ID('fixture', kind))
            board.Add(fp)
            x, y = xy
            if idx:
                x = 100 - x if reflected else x - 4
                y -= 3
            fp.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            if kind == 'link':
                pad = pcbnew.PAD(fp)
                pad.SetNumber('pin-x')
                pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
                pad.SetPosition(fp.GetPosition())
                fp.Add(pad)
    paths = {key: tmp_path / (key + '.kicad_pcb') for key in instance.ROLES}
    pcbnew.SaveBoard(str(paths['carrier']), a)
    pcbnew.SaveBoard(str(paths['cover']), b)
    contract = dict(transform=transform, gap_mm=[10, 10], xy_allowance_each_mm=.1,
                    body_clearance_mm=.5, mating_pairs=[['RENAMED_MATE', 'RENAMED_MATE']],
                    envelopes={kind: dict(height_max_mm=height, local_box_mm=[-1, -1, 1, 1],
                                          basis='synthetic', evidence='synthetic geometry, not a hardware rating')
                               for kind, height in [('link', 1), ('block', 8)]},
                    vertical=dict(gap=[10, 10], cap_height=[1, 1], cap_seating=[0, 0], vent_min=1,
                                  header_reach=[7, 7], socket_height=[5, 5], header_seating=[0, 0],
                                  socket_seating=[0, 0], insertion_limits=[1, 3]))
    path = tmp_path / 'contract.json'
    path.write_text(json.dumps(contract))
    context = dict(schema=1, role='carrier', contract=dict(path=str(path), sha256=instance.digest(path)),
                   members={role: dict(path=str(value), sha256=instance.digest(value)) for role, value in paths.items()})
    return a, b, paths, path, contract, context


@pytest.mark.parametrize('reflected', [False, True])
@pytest.mark.parametrize('role', instance.ROLES)
def test_native_pair_registration_is_not_a_filename_or_pose_special_case(tmp_path, reflected, role):
    a, b, paths, _, _, context = native_fixture(tmp_path, reflected=reflected)
    context['role'] = role
    result = instance.check(a if role == 'carrier' else b, paths[role], context, tmp_path)
    assert result['ok'] and result['authority_unchanged'] and not result['release_authority']
    assert all(row['ok'] for row in result['contacts'])


@pytest.mark.parametrize('fault', ['pad_shift', 'body_collision', 'missing_contact', 'vertical', 'changed_during'])
def test_native_physical_or_late_identity_failure_is_not_waived(tmp_path, monkeypatch, fault):
    pcbnew = pytest.importorskip('pcbnew')
    a, b, paths, contract_path, contract, context = native_fixture(
        tmp_path, reflected=True, collision=fault == 'body_collision')
    if fault == 'pad_shift':
        pad = next(iter(next(iter(a.GetFootprints())).Pads()))
        pad.SetPosition(pcbnew.VECTOR2I_MM(20.2, 30))
    elif fault == 'missing_contact':
        pad = next(iter(next(iter(a.GetFootprints())).Pads()))
        pad.SetNumber('wrong-pin')
    elif fault == 'vertical':
        contract['vertical']['vent_min'] = 12
        contract_path.write_text(json.dumps(contract))
        context['contract']['sha256'] = instance.digest(contract_path)
    elif fault == 'changed_during':
        import cec_assembly_envelope as env
        original = env.evaluate_boards
        def changed(*args):
            result = original(*args)
            paths['cover'].write_bytes(paths['cover'].read_bytes() + b'\n')
            return result
        monkeypatch.setattr(env, 'evaluate_boards', changed)
    result = instance.check(a, paths['carrier'], context, tmp_path)
    assert not result['ok'] and not result['release_authority']


def test_invalid_explicit_checker_context_does_not_use_legacy_policy(tmp_path):
    pcbnew = pytest.importorskip('pcbnew')
    import cec_constraints as constraints
    with pytest.raises(ValueError, match='complete explicit'):
        constraints._chk_paired_assembly_envelope(pcbnew.BOARD(), 'unused.kicad_pcb',
                                                 {instance.CONTEXT_KEY: {}})


@pytest.mark.parametrize('role', instance.ROLES)
def test_early_source_intake_receives_exact_instance(tmp_path, monkeypatch, role):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_constraints as constraints
    import cec_generalization_gate as generic
    import cec_beta_electrical_audit as electrical
    import cec_source_current_endpoint_intake as endpoint_intake
    paths, context = bound_fixture(tmp_path)
    context['role'] = role
    cfg = synth.Config.load('hub-standard-rev2' if role == 'cover' else 'atx-24pin-rev3')
    observed = []
    def gate(path, ctx, **kwargs):
        observed.append(ctx)
        return dict(ok=True, reasons=[])
    monkeypatch.setattr(constraints, 'intake_gate', gate)
    monkeypatch.setattr(generic, 'audit', lambda root: dict(ok=True, release_ok=False))
    monkeypatch.setattr(electrical, 'audit', lambda root: dict(findings=[]))
    monkeypatch.setattr(pipeline, '_project_rule_authority_delta', lambda *args: dict(ok=True))
    # This test's .data members exercise selected-pair binding, not native
    # current endpoints. The independent source-current tests cover refusal
    # and propagation of this newer mandatory production gate.
    monkeypatch.setattr(endpoint_intake,'check',lambda *args:dict(ok=True,neutral=True))
    result = pipeline._source_intake(cfg, paths[role], tmp_path/'intake.json',
        allow_derived_input=True, assembly_instance=context)
    assert result['ok'] and result['assembly_instance'] == context
    assert observed[0][instance.CONTEXT_KEY] == context
    assert set(result['selected_assembly_hashes']) == {'carrier', 'cover', 'contract'}
    context['role'] = 'mutated-after-call'
    assert observed[0][instance.CONTEXT_KEY]['role'] == role


@pytest.mark.parametrize('fault', ['empty', 'changed_peer', 'changed_contract', 'wrong_member'])
def test_invalid_early_intake_instance_stops_before_legacy_gate(tmp_path, monkeypatch, fault):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_constraints as constraints
    paths, context = bound_fixture(tmp_path)
    if fault == 'empty': context = {}
    elif fault == 'changed_peer': paths['cover'].write_text('changed')
    elif fault == 'changed_contract': paths['contract'].write_text('changed')
    else: context['role'] = 'cover'
    def forbidden(*args, **kwargs):
        raise AssertionError('invalid explicit pair reached the gate')
    monkeypatch.setattr(constraints, 'intake_gate', forbidden)
    monkeypatch.setattr(pipeline, '_project_rule_authority_delta', lambda *args: dict(ok=True))
    with pytest.raises(ValueError):
        pipeline._source_intake(synth.Config.load('atx-24pin-rev3'), paths['carrier'],
            tmp_path/'intake.json', allow_derived_input=True, assembly_instance=context)


def test_explicit_peer_changed_late_in_intake_is_not_a_pass(tmp_path, monkeypatch):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    import cec_constraints as constraints
    import cec_generalization_gate as generic
    import cec_beta_electrical_audit as electrical
    paths, context = bound_fixture(tmp_path)
    def gate(*args, **kwargs):
        paths['cover'].write_text('changed during intake')
        return dict(ok=True, reasons=[])
    monkeypatch.setattr(constraints, 'intake_gate', gate)
    monkeypatch.setattr(generic, 'audit', lambda root: dict(ok=True, release_ok=False))
    monkeypatch.setattr(electrical, 'audit', lambda root: dict(findings=[]))
    monkeypatch.setattr(pipeline, '_project_rule_authority_delta', lambda *args: dict(ok=True))
    result = pipeline._source_intake(synth.Config.load('atx-24pin-rev3'), paths['carrier'],
        tmp_path/'intake.json', allow_derived_input=True, assembly_instance=context)
    assert not result['ok']
    assert any('assembly changed' in error for error in result['manifest_errors'])

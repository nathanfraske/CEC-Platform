"""Opt-in wave authority; no capability assertion or current exception.

An explicit selected-net scope is configuration, NEVER current authority.
The native compiler still resolves every selected endpoint/current contract.
Absent selection all rated domains defer. Each queued source epoch and each
admitted tier is bound separately. No current or barrel qualification follows.
"""
import hashlib
import json
import os
from pathlib import Path


def policy_from_params(params, board_hint):
    value = params.get('wave_rated_current_export', False)
    if type(value) is not bool:
        raise ValueError('boolean_wave_rated_current_export_required')
    retaining = params.get('wave_source_retaining_import', False)
    if type(retaining) is not bool:
        raise ValueError('boolean_wave_source_retaining_import_required')
    if not value:
        if retaining:
            raise ValueError('source_retaining_import_requires_bound_rated_wave_job')
        return None
    if not isinstance(board_hint, str) or not board_hint.strip():
        raise ValueError('explicit_logical_board_hint_required')
    selected = params.get('wave_rated_current_nets', [])
    policy = {'board_hint': board_hint, 'selected_current_nets': selected}
    if retaining:
        policy['retaining_import'] = _retaining_settings({
            'wall_s': params.get('wave_source_retaining_wall_s', 120.),
            'native_s': params.get('wave_source_retaining_native_s', 10.),
            'cleanup_dangling': params.get('wave_source_retaining_cleanup', False),
            'assembly_instance': params.get('wave_source_retaining_assembly_instance')})
    layers=params.get('wave_rated_current_layers', {})
    if layers:
        policy['construction_layers_by_net']=layers
    elif type(layers) is not dict:
        raise ValueError('explicit_layer_scope_mapping_required')
    return _policy(policy)


def _policy(policy):
    if policy is None or type(policy) is dict and not policy:
        return None
    if (type(policy) is not dict or (not {'board_hint', 'selected_current_nets'}<=set(policy)
            or not set(policy)<={'board_hint', 'selected_current_nets', 'retaining_import', 'construction_layers_by_net'})
            or not isinstance(policy['board_hint'], str)
            or not policy['board_hint'].strip()
            or type(policy['selected_current_nets']) is not list
            or len(policy['selected_current_nets']) > 64
            or any(type(n) is not str or not n for n in policy['selected_current_nets'])
            or len(set(policy['selected_current_nets'])) != len(policy['selected_current_nets'])):
        raise ValueError('exact_named_wave_policy_required')
    result = dict(policy, selected_current_nets=list(policy['selected_current_nets']))
    if 'retaining_import' in result:
        result['retaining_import'] = _retaining_settings(result['retaining_import'])
    if 'construction_layers_by_net' in result:
        import cec_rated_trace_scope as trace_scope
        result['construction_layers_by_net']=trace_scope.normalize(result['construction_layers_by_net'])
        if (result['construction_layers_by_net'] and 'retaining_import' not in result
                or not set(result['construction_layers_by_net'])<=set(result['selected_current_nets'])):
            raise ValueError('trace_scope_requires_selected_current_nets_and_retaining_receiver')
    return result


def _sha(path):
    import cec_force_current as force
    return force._hash(path)


def _identity(source, hint):
    import cec_force_current as force
    path = Path(source).resolve()
    before = force._companion_inventory(path)
    family = force._family(path, hint)
    result = {'source': str(path), 'source_sha256': family[str(path)],
              'family': family, 'code': force._code_identity()}
    if force._companion_inventory(path) != before:
        raise ValueError('wave_family_inventory_changed_while_binding')
    return result


def _authority(source, hint):
    import cec_full_pipeline as pipeline
    import cec_synth_pipeline as synth
    cfg = synth.Config.load(hint)
    paths = set(pipeline._source_files(cfg, source))
    paths.update((Path(pipeline.ROOT) / 'lib').rglob('*.json'))
    import cec_force_current as force
    environment = sorted((key, value) for key, value in os.environ.items()
                         if key.startswith(('CEC_', 'KICAD')) or key == 'PATH')
    payload = [cfg.params, cfg.board, cfg.board_key,
               force._family_file_hashes(sorted(paths)), environment]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def bind_job(source, policy):
    policy = _policy(policy)
    if policy is None:
        return None
    identity = _job_identity(source, policy)
    authority = _authority(source, policy['board_hint'])
    if identity != _job_identity(source, policy):
        raise ValueError('wave_family_changed_while_binding_authority')
    return {'schema': 1, 'policy': policy, 'policy_sha256': _policy_sha(policy), 'identity': identity,
            'authority_sha256': authority}


def validate_job(source, job):
    if job is None:
        return None
    if (type(job) is not dict or set(job) != {'schema', 'policy', 'policy_sha256', 'identity', 'authority_sha256'}
            or type(job['schema']) is not int or job['schema'] != 1
            or _policy(job['policy']) is None
            or job['policy_sha256'] != _policy_sha(job['policy'])
            or job['identity'] != _job_identity(source, job['policy'])
            or job['authority_sha256'] != _authority(source, job['policy']['board_hint'])):
        raise ValueError('queued_wave_source_family_or_code_epoch_changed')
    return job


def _nets(value, *, optional=False):
    if optional and value is None:
        return None
    if (type(value) not in (list, tuple, set, frozenset) or len(value) > 32768
            or any(type(net) is not str or not net for net in value)):
        raise ValueError('explicit_bounded_net_collection_required')
    return set(value)


def _selected(policy, domains, contracts):
    selected = set(policy['selected_current_nets'])
    for net in selected:
        domain = domains.get(net, {})
        if (net not in contracts or domain.get('complete') is not True
                or not domain.get('source_refs') or not domain.get('sink_refs')
                or domain.get('missing_refs')):
            raise ValueError('selected_current_scope_requires_native_bound_endpoints_and_width_contract')
    return selected


def prepare(source, job, requested_nets=None, completed_nets=()):
    """Recompute native authority, never accept caller current/capability rows."""
    if job is None:
        return None
    requested_nets = _nets(requested_nets, optional=True)
    completed_requested = _nets(completed_nets)
    validate_job(source, job)
    import pcbnew
    import cec_current_topology as topology
    import cec_locked_net_ownership as ownership
    board = pcbnew.LoadBoard(str(source))
    board.BuildConnectivity()
    hint = job['policy']['board_hint']
    domains = topology.board_current_domains(board, board_hint=hint)
    contracts = topology.route_width_contracts(board, board_hint=hint)
    if isinstance(contracts, tuple):
        contracts = contracts[0]
    actual = {str(p.GetNetname()) for fp in board.GetFootprints() for p in fp.Pads()
              if str(p.GetNetname())}
    connectivity = ownership.certificate(board, locked_only=False)
    pending = {net for net in actual if not connectivity['nets'].get(net, {}).get('complete')}
    requested = pending if requested_nets is None else pending & set(requested_nets)
    selected = _selected(job['policy'], domains, contracts)
    deferred = set(contracts) - selected
    completed = {net for net in completed_requested
                 if connectivity['nets'].get(net, {}).get('complete') is True}
    eligible = requested - deferred - completed
    validate_job(source, job)
    result={'job': job, 'requested_nets': sorted(requested),
            'native_pending_nets': sorted(pending),
            'native_connectivity_is_not_current_qualification': True,
            'route_nets': sorted(eligible), 'completed_nets': sorted(completed),
            'completed_requested': sorted(completed_requested),
            'completed_demoted': sorted(completed_requested - completed),
            'deferred_not_completed': sorted(deferred),
            'domain_origins': {net: domains.get(net, {}).get('source')
                               for net in sorted(contracts)},
            'selected_scope_is_not_role_or_capacity_authority': True,
            'native_width_contracts': contracts,
            'export_context': {'source': job['identity']['source'],
                'expected_source_sha256': job['identity']['source_sha256'],
                'board_hint': hint, 'requested_nets': sorted(eligible)},
            'current_or_barrel_qualified': False}
    if job['policy'].get('construction_layers_by_net'):
        scope=job['policy']['construction_layers_by_net']
        result['new_trace_scope_binding']=job['identity']['new_trace_scope']
        # No class is synthesized for a physically complete/unrequested net.
        result['export_context']['construction_layers_by_net']={
            net:layers for net,layers in scope.items() if net in eligible}
    return result


def restrict_pending(dsn, preparation):
    if preparation is None:
        return
    import cec_staged_fr
    cec_staged_fr._dsn_restrict_to_nets(str(dsn), set(preparation['route_nets']))


def record(dsn, preparation):
    if preparation is None:
        return
    validate_job(preparation['job']['identity']['source'], preparation['job'])
    payload = dict(preparation, final_dsn_sha256=_sha(dsn),
                   scope='routing_scope_and_width_only_not_current_admission')
    # Not a PCB companion; persists only if the caller retains its workdir.
    target = Path(dsn).parent / 'rated-wave-reports'
    target.mkdir(exist_ok=True)
    data = json.dumps(payload, sort_keys=True, default=str).encode()
    if len(data) > 8 * 1024 ** 2:
        raise ValueError('bounded_wave_report_required')
    with (target / (Path(dsn).name + '.json')).open('xb') as stream:
        stream.write(data)


def _retaining_settings(value):
    if (type(value) is not dict or set(value) != {
            'wall_s', 'native_s', 'cleanup_dangling', 'assembly_instance'}
            or type(value['cleanup_dangling']) is not bool
            or type(value['wall_s']) not in (int, float)
            or not 0 < value['wall_s'] <= 300
            or type(value['native_s']) not in (int, float)
            or value['native_s'] != 10
            or value['assembly_instance'] is not None
               and type(value['assembly_instance']) is not dict):
        raise ValueError('bounded_source_retaining_import_policy_required')
    # Copies simple IPC data, rejecting non-JSON objects and unbounded contexts.
    text = json.dumps(value, sort_keys=True, allow_nan=False)
    if len(text.encode()) > 65536:
        raise ValueError('bounded_assembly_instance_context_required')
    return json.loads(text)


def _job_identity(source, policy):
    identity = _identity(source, policy['board_hint'])
    settings = policy.get('retaining_import')
    if settings is not None:
        import cec_source_retaining_ses_import as retaining
        instance = settings['assembly_instance']
        if instance is not None:
            import cec_force_current as force
            import cec_full_pipeline as pipeline
            if (set(instance) != {'schema', 'role', 'contract', 'members'}
                    or type(instance['schema']) is not int or instance['schema'] != 1
                    or instance['role'] not in ('carrier', 'cover')
                    or type(instance['members']) is not dict
                    or set(instance['members']) != {'carrier', 'cover'}):
                raise ValueError('complete_explicit_assembly_context_required')
            records = [instance['contract'], *instance['members'].values()]
            if any(type(row) is not dict or set(row) != {'path', 'sha256'}
                    or type(row['path']) is not str or not row['path']
                    or type(row['sha256']) is not str for row in records):
                raise ValueError('bound_assembly_artifact_records_required')
            force._family_file_hashes([
                (Path(pipeline.ROOT) / row['path']).resolve() for row in records])
        identity['retaining_assembly_identity'] = retaining.assembly_identity(
            source, instance)
    if policy.get('construction_layers_by_net'):
        import cec_rated_trace_scope as trace_scope
        identity['new_trace_scope']=trace_scope.bind_source(
            source,policy['board_hint'],policy['construction_layers_by_net'])
    return identity


def _policy_sha(policy):
    return hashlib.sha256(json.dumps(_policy(policy),sort_keys=True,allow_nan=False).encode()).hexdigest()


def retaining_requested(policy):
    normalized = _policy(policy)
    return normalized is not None and normalized.get('retaining_import') is not None


def import_operator(source, job):
    """Construct only inside the executing worker/direct oracle, never in IPC.

    Scope selection grants no source/native/current exception. Publication
    validates this exact queued job inside the operator's rollback boundary.
    """
    if job is None:
        return None
    validate_job(source, job)
    settings = job['policy'].get('retaining_import')
    if settings is None:
        return None
    from functools import partial
    import cec_source_retaining_ses_import as retaining
    callback = partial(retaining.route_once_operator,
        board_hint=job['policy']['board_hint'],
        expected_source_sha256=job['identity']['source_sha256'],
        wall_s=settings['wall_s'], native_s=10.,
        cleanup_dangling=settings['cleanup_dangling'],
        assembly_instance=settings['assembly_instance'],
        trace_layer_scope=job['policy'].get('construction_layers_by_net'),
        publication_guard=partial(validate_job, source, job))

    def checked(saved_source, ses, output):
        validate_job(saved_source, job)
        # The final post-board epoch check belongs inside the publisher's
        # own rollback boundary. Do not turn a committed publication into an
        # apparent failure with an additional check after it has returned.
        return callback(saved_source, ses, output)

    return checked

"""Source-typed analog-output/ADC port, with exact native local antipads.

This is not an ordinary-net alias. A fresh selected schematic export, exact
manufacturer output and physical ADC terminal, sensitive class and permitted
faces are rederived at every public boundary. Kelvin inputs and rated power
cannot enter here. The shared original-parent current, field, cut, return,
source, native DRC and final review gates remain mandatory.
"""
from copy import deepcopy
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_force_current as force
import cec_fr as fr
import cec_native_partition_pair as partitions
import cec_native_pad_octilinear_entry as pad_entry
import cec_quiet_signal_requests as requests
import cec_signal_via_clearance_window as geometry
import cec_source_netlist_semantics as semantics
import cec_source_retaining_ses_import as text_io

SCOPE = 'Source_typed_quiet_analog_signal_via_native_clearance_windows'


def _request_identity(request):
    result = deepcopy(request)
    result['source_bindings'] = semantics.replay_identity(result['source_bindings'])
    return result


def plan(source, *, board_hint, pad_uuid, position_nm, timeout_s=10.):
    deadline = geometry.lease._deadline(timeout_s)
    if type(board_hint) is not str or not board_hint or type(pad_uuid) is not str or not pad_uuid:
        raise ValueError('explicit_Source_quiet_window_identity_required')
    source = Path(source).resolve(strict=True)
    family, code = force._family(source, board_hint), force._code_identity()
    board = pcbnew.LoadBoard(str(source)); pad, face = geometry._pad(board, pad_uuid)
    before = requests.row._source_binding(board)
    typed = requests.plan(board, source, board_hint=board_hint,
        timeout_s=min(10., max(.001, deadline-time.monotonic())))
    if typed.get('complete') is not True or typed.get('errors') or not requests.bindings_current(typed):
        raise ValueError('fresh_canonical_Source_quiet_window_request_required')
    matches = [r for r in typed['requests'] if pad_uuid in (r['root_pad_uuid'],r['target_pad_uuid'])]
    if len(matches) != 1:
        raise ValueError('one_actual_Source_analog_output_ADC_window_endpoint_required')
    request = matches[0]
    if (request['net'] != pad.GetNetname() or request['kind'] != 'source_typed_quiet_analog_output'
            or request['root']['role'] != 'analog_output'
            or request['target']['role'] != 'adc_capable_physical_gpio'
            or request['target']['manufacturer'].get('adc_capable') is not True):
        raise ValueError('exact_Source_output_and_physical_ADC_roles_required')
    spec = fr._project_netclass_resolver(str(source), board=board)(request['net']) or {}
    if str(spec.get('name','')).casefold() != 'sense':
        raise ValueError('Source_quiet_window_sensitive_class_required')
    layers = sorted(fr._lastmile_route_layers(board,net_name=request['net'],spec=spec,
        exclude_front=False,allow_nonplane_power_role=False))
    if face not in layers or not layers:
        raise ValueError('Source_quiet_window_actual_endpoint_signal_face_required')
    # Retained inputs remain governed by their separate front-only policy;
    # neither a Sense net name nor generic window geometry supplies this scope.
    point = geometry._axis(position_nm); centre = list(pad.GetPosition())
    entry = None
    distance = math.dist(centre,point)
    if not geometry.quality.is_canonical_stroke(centre,point,tolerance_nm=0):
        entry=pad_entry.choose(pad,point,width_nm=request['width_nm'],deadline=deadline)['start_nm']
    elif distance > 1500000:
        delta = [point[k]-centre[k] for k in (0,1)]
        if not geometry.quality.is_canonical_stroke(centre,point,tolerance_nm=0):
            raise ValueError('Source_quiet_window_canonical_finite_land_entry_required')
        unit = [(v>0)-(v<0) for v in delta]
        advance = math.ceil((distance-1500000)/math.hypot(*unit))
        entry = [centre[k]+unit[k]*advance for k in (0,1)]
        # A positive native full-width start disk is checked independently by
        # geometry. This changes no clearance/width or1.5mm exposed-leg cap.
    result = geometry._plan_geometry(source,board_hint=board_hint,pad_uuid=pad_uuid,
        position_nm=point,_start_nm=entry,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if (result['source_family'] != family or result['script_code_identity'] != code
            or result['width_nm'] != request['width_nm']
            or result['clearance_nm'] < request['clearance_nm']
            or result['source_class'].casefold() != 'sense'
            or requests.row._source_binding(board) != before
            or not requests.bindings_current(typed)):
        raise ValueError('Source_quiet_window_role_dimensions_or_epoch_changed')
    result.update(scope=SCOPE,quiet_request=_request_identity(request),permitted_signal_layers=layers,
        endpoint_role='analog_output' if pad_uuid==request['root_pad_uuid'] else 'adc_capable_physical_gpio',
        finite_Source_land_entry=entry is not None,source_pad_centre_nm=centre,
        maximum_exposed_surface_leg_nm=1500000,
        ordinary_net_alias=False,Kelvin_input_authority=False,power_authority=False,
        adc_mode_qualified=False,load_qualified=False,field_qualified=False,
        window_is_not_itself_an_open_count_progress_claim=True)
    geometry._tick(deadline)
    return result


def _proof(value):
    result = dict(value)
    # The shared geometry retains precisely the supplied Source class. Its
    # historical key must not mislabel a newly typed Sense endpoint ordinary.
    result['full_Source_sensitive_class_dimensions'] = result.pop('full_Source_ordinary_class_dimensions')
    result.update(ordinary_net_alias=False,field_and_current_and_absolute_cut_receiving_required=True)
    return result


def write_private(proposal,directory,*,timeout_s=10.):
    deadline = geometry.lease._deadline(timeout_s)
    fresh = plan(proposal['source'],board_hint=proposal['board_hint'],pad_uuid=proposal['pad_uuid'],
        position_nm=proposal['at_nm'],timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if proposal != fresh:
        raise ValueError('fresh_exact_Source_quiet_window_proposal_required')
    board,proof = geometry._construct_fresh(fresh,None,deadline)
    target = force._copy_family(Path(fresh['source']),Path(directory))
    text_io.write_raw(target,geometry.geometry._literal_text(Path(fresh['source']),board,fresh))
    if (fresh['script_code_identity'] != force._code_identity()
            or fresh['source_family'] != force._family(Path(fresh['source']),fresh['board_hint'])):
        raise ValueError('Source_quiet_window_changed_before_private_save')
    geometry._tick(deadline)
    return dict(complete=True,candidate=str(target),candidate_sha256=force._hash(target),
        construction=_proof(proof),routing_admitted=False,release_authority=False,
        current_capacity_qualified=False,all_original_parent_gates_still_required=True)


def receive(source,candidate,*,board_hint,pad_uuid,position_nm,timeout_s=10.):
    result = dict(ok=False,complete=False,errors=[],scope_only=True,ordinary_net_alias=False,
        Kelvin_input_authority=False,power_authority=False,routing_admitted=False,
        current_capacity_qualified=False,field_qualified=False,adc_mode_qualified=False,
        release_authority=False,all_original_parent_gates_still_required=True)
    try:
        deadline = geometry.lease._deadline(timeout_s)
        source,candidate = [Path(p).resolve(strict=True) for p in (source,candidate)]
        if source == candidate:
            raise ValueError('distinct_saved_quiet_window_boundaries_required')
        code = force._code_identity(); families = [force._family(p,board_hint) for p in (source,candidate)]
        fresh = plan(source,board_hint=board_hint,pad_uuid=pad_uuid,position_nm=position_nm,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        _,old = additive._nodes(source); new_root,new = additive._nodes(candidate)
        incoming = new.keys()-old.keys()
        if old.keys()-new.keys() or len(incoming)!=2 or {new[u][0] for u in incoming}!={'via','segment'}:
            raise ValueError('one_new_quiet_via_and_leg_without_retirement_required')
        ids = {new[u][0]:u for u in incoming}
        board,proof = geometry._construct_fresh(fresh,ids,deadline)
        with tempfile.TemporaryDirectory(prefix='cec-quiet-window-independent-') as work:
            expected = force._copy_family(source,Path(work)/'expected')
            text_io.write_raw(expected,geometry.geometry._literal_text(source,board,fresh))
            expected_root = additive._nodes(expected)[0]
        if syntax._freeze(expected_root)!=syntax._freeze(new_root) or force._sidecars(source)!=force._sidecars(candidate):
            raise ValueError('saved_quiet_window_differs_from_complete_independent_Source_replay')
        parent,child = [pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        paired = partitions.compare(parent,child,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if paired.get('available') is not True or paired.get('preserved') is not True:
            raise ValueError('Source_quiet_window_demoted_a_retained_native_partition')
        pad,_ = geometry._pad(child,pad_uuid); graph = fr._read_only_route_connectivity(child)
        reached = {force._uid(pad)}|{force._uid(i) for i in graph.GetConnectedItems(pad)}
        if not incoming<=reached:
            raise ValueError('quiet_window_material_not_attached_to_exact_Source_land')
        if code!=force._code_identity() or families!=[force._family(p,board_hint) for p in (source,candidate)]:
            raise ValueError('Source_quiet_window_saved_families_or_code_changed')
        geometry._tick(deadline)
        result.update(ok=True,complete=True,plan=fresh,construction=_proof(proof),
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            all_original_authored_items_unchanged=True,original_native_partitions_preserved=True,
            exact_native_Source_reconstruction_received=True,only_Source_bounded_foreign_clearance_removal=True,
            source_sensitive_class_preserved=True,window_is_not_itself_an_open_count_progress_claim=True)
        geometry._tick(deadline)
    except Exception as exc:
        result.update(ok=False,complete=False)
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result

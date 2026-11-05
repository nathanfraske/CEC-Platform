"""Fresh source-owned quiet analog requests; no routing or electrical rating.

Exactly two physical terminals, selected INA240 output and physical ADC-capable
GPIO, retain their Sense class. Recompile this planner independently in a saved
receiver; neither stored requests nor bindings_current grant admission.
"""
import math
import json
from pathlib import Path
import subprocess
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_current_topology as topology
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_pair_semantics as pairs
import cec_source_ground_leaf as source_roles
import cec_source_no_connect as source_nc
import cec_synth_pipeline as synth


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('quiet_signal_request_deadline')


def _source_pin(identity, number, deadline):
    """Actual selected embedded pin name/type, not net or reference spelling."""
    _tick(deadline)
    pin = source_roles._pin(identity, number)
    symbol = identity[3]
    libraries = [b for tag, b in identity[2].children if tag == 'lib_symbols']
    if len(libraries) != 1:
        raise ValueError('quiet_signal_selected_source_library_required')
    tree = synth.parse_sexpr(libraries[0])
    selected = [s for s in synth._kids(tree, 'symbol')
                if len(s) > 1 and s[1] == symbol.get('lib_id')]
    if len(selected) != 1:
        raise ValueError('quiet_signal_unique_source_library_required')
    stack = [selected[0]]; actual = []; count = 0
    while stack:
        _tick(deadline); node = stack.pop(); count += 1
        if count > 8192:
            raise ValueError('quiet_signal_source_library_bound')
        if isinstance(node, list) and node:
            if node[0] == 'pin' and synth._val(node, 'number', '') == number:
                actual.append(node)
            stack.extend(c for c in node if isinstance(c, list))
    if len(actual) != 1 or len(actual[0]) < 2 or actual[0][1] != pin['type']:
        raise ValueError('quiet_signal_actual_source_pin_required')
    return dict(type=pin['type'], name=synth._val(actual[0], 'name', ''))


def _gpio(fp, pin):
    witness = roles.scalar_gpio_pin(fp, pin)
    if not witness:
        return None
    if witness.get('adc_capable') is True:
        return witness
    # The existing selected WROOM voltage-envelope witness distinguishes ADC
    # physical capability; do not infer ADC mode or reuse its numeric envelope.
    physical = roles.resistive_sensing_endpoint_contract(fp, pin)
    if (physical and physical.get('endpoint_role') ==
            'adc_capable_gpio_voltage_envelope_not_application_mode'
            and str(witness.get('selected_mpn', '')).startswith('ESP32-S3-WROOM-')):
        return dict(witness, adc_capable=True)
    return None


def _nm(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('quiet_signal_positive_' + name + '_required')
    return math.ceil(value * 1e6)


def bindings_current(proof):
    """Epoch check only on fresh receiver-derived planner metadata."""
    if type(proof) is not dict or proof.get('scope') != 'source_typed_quiet_analog_requests':
        raise ValueError('quiet_signal_source_bindings_required')
    binding = proof.get('source_bindings', {})
    if type(binding) is not dict:
        return False
    files = binding.get('schematic_files_sha256', {})
    exporter = binding.get('exporter', {})
    projects = binding.get('project_files_sha256')
    if (type(files) is not dict or not 1 <= len(files) <= 64
            or type(exporter) is not dict or type(projects) is not dict
            or len(projects) != 2):
        return False
    try:
        return (all(force._hash(Path(p)) == digest for p, digest in files.items())
            and force._hash(Path(binding['source'])) == binding['source_sha256']
            and all((force._hash(Path(p)) if Path(p).is_file() else None) == digest
                    for p, digest in binding['project_files_sha256'].items())
            and force._hash(Path(exporter['exporter'])) == exporter['exporter_sha256'])
    except (OSError, KeyError, ValueError, TypeError):
        return False


def plan(board, source, *, board_hint, timeout_s=10.):
    if (type(board_hint) is not str or not board_hint or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_quiet_signal_source_context_required')
    deadline = time.monotonic() + timeout_s
    result = dict(scope='source_typed_quiet_analog_requests', complete=False,
        requests=[], refused={}, errors=[], current_authority=False,
        adc_mode_qualified=False, load_qualified=False, voltage_qualified=False,
        thermal_qualified=False, release_authority=False, admission_authority=False)
    binding = row._source_binding(board)
    try:
        source = Path(source).resolve()
        if (not source.is_file() or source.suffix != '.kicad_pcb'
                or Path(board.GetFileName()).resolve() != source):
            raise ValueError('quiet_signal_named_source_board_required')
        digest = force._hash(source)
        project_files = {str(source.with_suffix(ext)):
            force._hash(source.with_suffix(ext)) if source.with_suffix(ext).is_file() else None
            for ext in ('.kicad_pro', '.kicad_dru')}
        if row._source_binding(pcbnew.LoadBoard(str(source))) != binding:
            raise ValueError('quiet_signal_saved_native_source_mismatch')
        root = source_nc._root(board, board_hint)
        if root is None:
            raise ValueError('quiet_signal_current_canonical_root_required')
        root = root.resolve()
        files, hashes, instances = source_roles._hierarchy(root, deadline)
        tree, exporter = source_roles._export(root, deadline)
        if (type(tree) is not list or type(exporter) is not dict
                or any(type(exporter.get(k)) is not str or not exporter[k]
                       for k in ('exporter', 'exporter_sha256', 'netlist_sha256'))):
            raise ValueError('quiet_signal_fresh_export_shape_required')
        comps, nets, node_net = source_roles._tables(tree)
        resolver = fr._project_netclass_resolver(str(source), board=board)
        with force._thermal_hint(board_hint):
            protected = set(topology.board_current_domains(board, board_hint))
        protected |= set(fr.coupled_pair_nets(board))
        protected |= {q[k] for q in pairs.analog_input_pairs(board) for k in ('p', 'n')}
        protected |= set(pairs.unresolved_current_monitor_nets(board))
        protected |= {str(z.GetNetname()) for z in board.Zones() if not z.GetIsRuleArea()}
        native = {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                native.setdefault(str(pad.GetNetname()), []).append(pad)
        if sum(map(len, native.values())) > 16384:
            raise ValueError('quiet_signal_native_inventory_bound')
        identities = {}
        board.BuildConnectivity()
        connectivity = board.GetConnectivity()
        for net, pads in sorted(native.items()):
            _tick(deadline); spec = resolver(net) or {}
            if str(spec.get('name', '')).casefold() != 'sense':
                continue
            try:
                classification = field.classify_net(net, netclass=spec)
                with force._thermal_hint(board_hint):
                    current = synth.spec_net_current_contract(board_hint, net)
                if (not net or net == 'GND' or net in protected or current is not None
                        or classification['power'] or classification['aggressor']):
                    raise ValueError('quiet_signal_protected_net')
                if (len(pads) != 2 or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                        or p.GetParentFootprint().IsDNP() for p in pads)):
                    raise ValueError('quiet_signal_exact_two_surface_terminals_required')
                outputs = []
                for pad in pads:
                    model = roles.footprint_contract(pad.GetParentFootprint())
                    if (model and model['device_package'] in ('INA240 D', 'INA240 PW')
                            and model['pins'].get(pad.GetNumber()) == 'signal_output'):
                        outputs.append((pad, model))
                if len(outputs) != 1:
                    raise ValueError('quiet_signal_unique_manufacturer_analog_output_required')
                output, model = outputs[0]
                target = next(p for p in pads if force._uid(p) != force._uid(output))
                gpio = _gpio(target.GetParentFootprint(), target.GetNumber())
                if not gpio:
                    raise ValueError('quiet_signal_selected_physical_adc_gpio_required')
                expected = {(p.GetParentFootprint().GetReference(), p.GetNumber()) for p in pads}
                if len(expected) != 2 or nets.get(net) != expected:
                    raise ValueError('quiet_signal_exact_source_native_net_required')
                endpoints = []
                for pad, role, witness in [(output, 'analog_output', model),
                        (target, 'adc_capable_physical_gpio', gpio)]:
                    ref = pad.GetParentFootprint().GetReference(); number = pad.GetNumber()
                    if ref not in identities:
                        identities[ref] = source_roles._identity(board, ref, comps, instances, deadline)
                    identity = identities[ref]; pin = _source_pin(identity, number, deadline)
                    wanted = 'OUT' if role == 'analog_output' else gpio['function']
                    allowed = ('output',) if role == 'analog_output' else ('bidirectional',)
                    source_names = ('OUT', '~') if role == 'analog_output' else (wanted,)
                    native_names = ('', wanted, '~') if role == 'analog_output' and pin['name'] == '~' else ('', wanted)
                    # KiCad import may omit native annotations. Blank is not
                    # authority: the fresh selected source name/type above is
                    # mandatory; any nonempty native contradiction refuses.
                    if (node_net.get((ref, number)) != net or pin['type'] not in allowed
                            or pin['name'] not in source_names or pad.GetPinType() not in ('', pin['type'])
                            or pad.GetPinFunction() not in native_names):
                        raise ValueError('quiet_signal_source_native_pin_role_contradiction')
                    endpoints.append(dict(ref=ref, pin=number, role=role, manufacturer=witness,
                        actual_source_pin=pin,
                        manufacturer_function='OUT' if role == 'analog_output' else gpio['function'],
                        unnamed_source_placeholder=pin['name'] == '~',
                        source_symbol_uuid=identity[3]['uuid'], source_schematic=str(identity[1])))
                if force._uid(target) in {force._uid(p) for p in connectivity.GetConnectedItems(output)}:
                    continue  # Exact native route already joins these physical terminals.
                limits = spec.get('dimension_contract', {}).get('board_limits_mm', {})
                width = max(_nm(spec.get('track_width'), 'width'),
                    _nm(limits.get('track_width'), 'board_minimum'))
                clearance = _nm(spec.get('clearance'), 'clearance')
                result['requests'].append(dict(kind='source_typed_quiet_analog_output',
                    net=net, width_nm=width, clearance_nm=clearance,
                    root_pad_uuid=force._uid(output), target_pad_uuid=force._uid(target),
                    root=endpoints[0], target=endpoints[1], field_classification=classification,
                    current_authority=False, adc_mode_qualified=False,
                    load_qualified=False, release_authority=False))
            except ValueError as exc:
                result['refused'][net] = str(exc)
        result['source_bindings'] = dict(root_schematic=str(root), source=str(source),
            source_sha256=digest, schematic_files_sha256=hashes, exporter=exporter,
            project_files_sha256=project_files, native_binding=json.loads(json.dumps(binding)))
        for request in result['requests']:
            request['source_bindings'] = result['source_bindings']
        if (hashes != {str(p): force._hash(p) for p in files}
                or force._hash(source) != digest or not bindings_current(result)):
            raise ValueError('quiet_signal_source_epoch_changed')
        _tick(deadline); result['complete'] = True
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc)); result['requests'] = []
    finally:
        if row._source_binding(board) != binding:
            raise ValueError('quiet_signal_native_epoch_changed')
    return result

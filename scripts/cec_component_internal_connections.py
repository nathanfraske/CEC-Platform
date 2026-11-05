"""Manufacturer-enrolled fitted-component continuity, never PCB copper.

The native jumper field models a connection inside a populated component.
It must not change pad numbers, authored nets, conductor capacity, physical
contact/Kelvin graphs, field geometry or Ground-return evidence.  Enrollment
requires the exact selected part, all physical pins and a fresh hierarchy
export; a footprint name or a caller-supplied group is not authority.
"""
import copy
import json
import math
from pathlib import Path
import re
import tempfile
import time
import uuid

import pcbnew
import cec_component_jumper_metadata as metadata
import cec_device_power_roles as roles
import cec_force_current as force
import cec_protector_cell as protector
import cec_sch_lint as sch
import cec_synth_pipeline as synth
from cec_footprint_fields import footprint_properties

_SELECTION_FIELDS = ('Manufacturer', 'MPN', 'LCSC')


def _property(node, name):
    found = [x for x in metadata._children(node, 'property')
             if len(x) >= 3 and metadata._text(x[1]) == name]
    _need(len(found) <= 1, 'unique_component_selection_property_required')
    return found[0] if found else None


def _fill_missing_selection(board, saved, hint, deadline):
    """Only recover blank fitted-part fields from the actual current instance.

    This is not an alias or substitution. A nonblank disagreement is never
    overwritten. Positive manufacturer enrollment and the independent fresh
    full-export pin/net/instance proof must still succeed afterwards.
    """
    pending = [fp for fp in board.GetFootprints() if not fp.IsDNP()
               and any(not footprint_properties(fp).get(k) for k in _SELECTION_FIELDS)]
    if not pending:
        return {}
    root = protector.source_nc._root(board, hint)
    if root is None:
        return {}
    _, hashes, instances = protector.source_pin._hierarchy(root.resolve(), deadline)
    saved_fps = metadata._footprints(metadata._parse(Path(saved).read_text()))
    result = {}
    for fp in pending:
        _remaining(deadline)
        entries = instances.get(fp.GetReference(), [])
        if len(entries) != 1:
            continue
        _, sf, _symbol, _instance = entries[0]
        blocks = [b for tag, b in sf.children if tag == 'symbol'
                  and sch.prop_value(b, 'Reference') == fp.GetReference()]
        if len(blocks) != 1:
            continue
        block = blocks[0]
        if (sch.prop_value(block, 'Value') != fp.GetValue()
                or sch.prop_value(block, 'Footprint') != fp.GetFPIDAsString()):
            continue
        current = footprint_properties(fp)
        selected = {k: sch.prop_value(block, k) for k in _SELECTION_FIELDS}
        if (not all(type(v) is str and v for v in selected.values())
                or any(current.get(k) and current[k] != selected[k] for k in _SELECTION_FIELDS)):
            continue
        missing = [k for k in _SELECTION_FIELDS if not current.get(k)]
        # Work on a detached copy until a registered exact supplier/package
        # validates. Unregistered Source parts cannot acquire new authority.
        probe = pcbnew.Cast_to_FOOTPRINT(fp.Duplicate(False))
        for key in missing:
            probe.SetField(key, selected[key])
            field = probe.GetField(key)
            if key not in current:
                field.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(
                    uuid.UUID(force._uid(fp)), 'CEC Source selection field:' + key))))
            field.SetVisible(False)
            field.SetLayer(pcbnew.F_Fab if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_Fab)
        if roles.passive_steering_protector_contract(probe) is None:
            continue
        io = pcbnew.PCB_IO_KICAD_SEXPR()
        io.Format(probe)
        expected = metadata._parse(io.GetStringOutput(False))
        records = [dict(name=k, before=copy.deepcopy(_property(saved_fps[fp.GetReference()], k)),
                        after=copy.deepcopy(_property(expected, k)), value=selected[k]) for k in missing]
        for key in missing:
            fp.SetField(key, selected[key])
        result[force._uid(fp)] = records
    _need(all(force._hash(p) == h for p, h in hashes.items()),
          'component_selection_source_hierarchy_changed')
    _remaining(deadline)
    return result


def _apply_missing_selection(path, owners, deadline):
    """Exact saved private-field delta, checked by native IO before writing."""
    path = Path(path)
    original = path.read_bytes()
    root = metadata._parse(original.decode())
    fps = metadata._footprints(root)
    changed = False
    literal_edits = {}
    for owner in owners:
        fp = fps[owner['owner_ref']]
        for record in owner.get('restored_source_fields', []):
            key = record['name']
            _need(_property(fp, key) == record['before'],
                  'component_selection_original_field_changed')
            literal_edits.setdefault(owner['owner_ref'], []).append(dict(
                tag='property', name=key, before=copy.deepcopy(record['before']),
                after=copy.deepcopy(record['after'])))
            previous = _property(fp, key)
            if previous is None:
                fp.append(copy.deepcopy(record['after']))
            else:
                fp[fp.index(previous)] = copy.deepcopy(record['after'])
            changed = True
    if not changed:
        return
    with tempfile.TemporaryDirectory(prefix='cec-source-selection-') as tmp:
        candidate = Path(tmp) / 'board.kicad_pcb'
        import cec_literal_footprint_metadata as literal
        emitted = literal.splice(original.decode(), literal_edits)
        _need(metadata._parse(emitted) == root,
              'component_selection_literal_emission_changed_complete_AST')
        candidate.write_text(emitted)
        board = pcbnew.LoadBoard(str(candidate))
        for owner in owners:
            fp = board.FindFootprintByReference(owner['owner_ref'])
            _need(fp is not None, 'component_selection_native_owner_missing')
            for record in owner.get('restored_source_fields', []):
                field = fp.GetField(record['name'])
                _need(field.GetText() == record['value'] and not field.IsVisible()
                      and field.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab),
                      'component_selection_native_field_roundtrip_mismatch')
        _remaining(deadline)
        _need(path.read_bytes() == original, 'component_selection_saved_input_changed')
        path.write_bytes(candidate.read_bytes())


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds)
          and 0 < seconds <= 10., 'bounded_internal_connection_constituent_required')
    return time.monotonic() + seconds


def _remaining(deadline):
    value = deadline - time.monotonic()
    _need(value > 0, 'internal_connection_constituent_deadline')
    return min(10., value)


def _stable(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _datasheet(model):
    """Part-specific reviewed primary evidence, not an unbound web locator."""
    root = Path(__file__).resolve().parent.parent
    relative = model.get('selected_datasheet_path')
    _need(type(relative) is str and not Path(relative).is_absolute(),
          'reviewed_part_datasheet_required')
    path = (root / relative).resolve(strict=True)
    _need(path.is_relative_to(root / 'lib' / 'datasheets')
          and path.suffix == '.pdf' and 0 < path.stat().st_size <= 4 * 1024 * 1024
          and force._hash(path) == model.get('selected_datasheet_sha256'),
          'reviewed_part_datasheet_identity_changed')
    return dict(path=str(path), sha256=force._hash(path), page=model['page'],
                section=model['section'], revision=model['revision'])


def _source_groups(symbol_proof):
    """Read the exact embedded instance already independently source-bound."""
    sf = sch.SchFile(symbol_proof['sheet'])
    symbols = [s for s in sf.symbols if s['uuid'] == symbol_proof['symbol_uuid']]
    _need(len(symbols) == 1, 'unique_internal_connection_source_instance_required')
    libraries = [b for tag, b in sf.children if tag == 'lib_symbols']
    _need(len(libraries) == 1, 'embedded_internal_connection_source_required')
    nodes = [n for n in synth._kids(synth.parse_sexpr(libraries[0]), 'symbol')
             if len(n) > 1 and n[1] == symbols[0]['lib_id']]
    _need(len(nodes) == 1 and synth._first(nodes[0], 'extends') is None,
          'complete_internal_connection_embedded_symbol_required')
    explicit = list(synth._kids(nodes[0], 'jumper_pin_groups'))
    implicit = list(synth._kids(nodes[0], 'duplicate_pin_numbers_are_jumpers'))
    _need(len(explicit) == 1 and len(implicit) <= 1
          and (not implicit or implicit[0] == ['duplicate_pin_numbers_are_jumpers', 'no']),
          'explicit_source_pin_groups_without_implicit_jumpers_required')
    return metadata._groups(explicit[0][1:])


def _native_contract(record):
    contract = record['exported_contract']
    return dict(groups=tuple(tuple(g) for g in contract['groups']),
                pin_numbers=tuple(contract['pin_numbers']), pad_nets=contract['pad_nets'])


def plan(source, *, board_hint, owner_uuids=None, timeout_s=10.):
    """Compile exact fitted signal-bank metadata from the live saved Source."""
    deadline = _deadline(timeout_s)
    source = Path(source).resolve(strict=True)
    _need(source.suffix == '.kicad_pcb' and type(board_hint) is str and board_hint,
          'saved_named_internal_connection_source_required')
    family = force._family(source, board_hint)
    code = force._code_identity()
    board = pcbnew.LoadBoard(str(source))
    restored_fields = _fill_missing_selection(board, source, board_hint, deadline)
    candidates = {force._uid(fp): (fp, roles.passive_steering_protector_contract(fp))
                  for fp in board.GetFootprints()}
    candidates = {uid: value for uid, value in candidates.items() if value[1] is not None}
    if owner_uuids is None:
        owner_uuids = sorted(candidates)
    _need(type(owner_uuids) is list and 1 <= len(owner_uuids) <= 4
          and len(set(owner_uuids)) == len(owner_uuids)
          and all(type(uid) is str and re.fullmatch(
              r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', uid)
                  and uid in candidates for uid in owner_uuids),
          'bounded_positive_manufacturer_connection_owners_required')
    saved = metadata.read_saved(source)
    records = []
    for uid in sorted(owner_uuids):
        _remaining(deadline)
        fp, model = candidates[uid]
        proof = protector._source_symbol(board, fp, model, board_hint, deadline)
        ref = fp.GetReference()
        expected = metadata._groups(model['io_banks'])
        contract = proof['exported_component_jumper_contract']
        _need(_source_groups(proof) == expected and contract is not None
              and contract['groups'] == expected
              and set(contract['pin_numbers']) == set(model['pins'])
              and all(contract['pad_nets'].get(p.GetNumber()) == p.GetNetname()
                      for p in fp.Pads()),
              'manufacturer_embedded_exported_native_connection_mismatch')
        _need(not fp.GetDuplicatePadNumbersAreJumpers() and saved[ref] in ((), expected),
              'contradictory_existing_native_internal_groups')
        records.append(dict(owner_uuid=uid, owner_ref=ref, manufacturer=model,
                            datasheet=_datasheet(model), source_symbol=proof,
                            source_groups=saved[ref], exported_contract=contract,
                            restored_source_fields=restored_fields.get(uid, [])))
    result = _stable(dict(schema=1, scope='source_manufacturer_component_internal_connection_metadata',
        source=str(source), source_sha256=force._hash(source), source_family=family,
        code_identity=code, board_hint=board_hint, owners=records,
        all_physical_pin_numbers_and_authored_nets_preserved=True,
        fitted_component_electrical_continuity_only=True,
        PCB_copper_current_ground_field_and_Kelvin_credit=False,
        routing_admitted=False, current_qualified=False, release_authority=False))
    _live(result, deadline)
    return result


def _live(proposal, deadline):
    _need(proposal['code_identity'] == force._code_identity()
          and proposal['source_family'] == force._family(
              Path(proposal['source']), proposal['board_hint']),
          'internal_connection_source_or_code_epoch_changed')
    for owner in proposal['owners']:
        files = owner['source_symbol']['files_sha256']
        exporter = owner['source_symbol']['exporter']
        _need(all(force._hash(path) == digest for path, digest in files.items())
              and force._hash(owner['datasheet']['path']) == owner['datasheet']['sha256'],
              'internal_connection_manufacturer_or_hierarchy_changed')
        _need(type(exporter.get('exporter')) is str
              and type(exporter.get('exporter_sha256')) is str
              and re.fullmatch('[0-9a-f]{64}', exporter['exporter_sha256'])
              and force._hash(exporter['exporter']) == exporter['exporter_sha256'],
              'internal_connection_exporter_changed')
    _remaining(deadline)


def literal_scope(source, candidate, owners):
    """Independent exact saved AST delta: only explicit enrolled FP fields."""
    roots = [metadata._parse(Path(p).read_text()) for p in (source, candidate)]
    before, after = [metadata._footprints(root) for root in roots]
    _need(before.keys() == after.keys(), 'internal_connection_native_inventory_changed')
    refs = [o['owner_ref'] for o in owners]
    _need(1 <= len(refs) <= 4 and len(set(refs)) == len(refs),
          'unique_bounded_enrolled_components_required')
    changed = []
    clean = copy.deepcopy(roots)
    for owner in owners:
        ref = owner['owner_ref']
        _need(ref in before and ref in after, 'enrolled_native_component_missing')
        expected = _native_contract(owner)['groups']
        for index, table in enumerate((before, after)):
            fp = table[ref]
            uid = metadata._one(fp, 'uuid')
            _need(uid is not None and metadata._atom(uid[1]) == owner['owner_uuid'],
                  'enrolled_native_component_identity_changed')
            implicit = metadata._one(fp, 'duplicate_pad_numbers_are_jumpers')
            _need(implicit is None or implicit == ['duplicate_pad_numbers_are_jumpers', 'no'],
                  'implicit_native_connection_mode_refused')
            actual = metadata._groups(metadata._one(fp, 'jumper_pad_groups', ['jumper_pad_groups'])[1:])
            _need(actual in ((), expected) if index == 0 else actual == expected,
                  'only_exact_manufacturer_native_groups_permitted')
            if index == 0 and actual != expected:
                changed.append(ref)
        for root in clean:
            fp = metadata._footprints(root)[ref]
            fp[:] = [x for x in fp if not (isinstance(x, list) and x
                                           and x[0] in metadata._FIELDS)]
        field_names = []
        for record in owner.get('restored_source_fields', []):
            key = record['name']
            _need(key in _SELECTION_FIELDS and key not in field_names
                  and type(record['value']) is str and bool(record['value'])
                  and (record['before'] is None or metadata._text(record['before'][2]) == ''),
                  'only_blank_source_selection_fields_may_be_restored')
            field_names.append(key)
            _need(_property(before[ref], key) == record['before']
                  and _property(after[ref], key) == record['after']
                  and metadata._text(record['after'][1]) == key
                  and metadata._text(record['after'][2]) == record['value'],
                  'only_exact_source_selection_field_delta_permitted')
            for root in clean:
                fp = metadata._footprints(root)[ref]
                fp[:] = [x for x in fp if not (isinstance(x, list) and x
                         and x[0] == 'property' and len(x) >= 3 and metadata._text(x[1]) == key)]
    _need(clean[0] == clean[1], 'internal_connection_changed_nonmetadata_native_item')
    _need(force._sidecars(Path(source)) == force._sidecars(Path(candidate)),
          'internal_connection_changed_saved_companion')
    return dict(exact_saved_literal_delta=True, changed_refs=sorted(changed),
                physical_copper_and_contact_query_inputs_identical=True,
                all_pad_numbers_nets_parts_poses_groups_and_rules_identical=True,
                PCB_copper_or_current_capacity_inferred=False)


def construct(proposal, out_dir, *, timeout_s=10.):
    """Private metadata-only descendant; no saved admission or native verdict."""
    deadline = _deadline(timeout_s)
    _need(type(proposal) is dict, 'exact_internal_connection_proposal_required')
    fresh = plan(proposal['source'], board_hint=proposal['board_hint'],
                 owner_uuids=[o['owner_uuid'] for o in proposal['owners']],
                 timeout_s=_remaining(deadline))
    _need(_stable(proposal) == fresh, 'stale_or_forged_internal_connection_proposal')
    source = Path(proposal['source'])
    out_dir = Path(out_dir).resolve()
    force._check_output(out_dir, force._protected_paths(source, proposal['board_hint']))
    _need(not out_dir.exists() and not out_dir.is_relative_to(source.parent),
          'distinct_new_private_internal_connection_family_required')
    candidate = force._copy_family(source, out_dir)
    contracts = {o['owner_ref']: _native_contract(o) for o in proposal['owners']}
    metadata.apply_saved(candidate, contracts, timeout_s=_remaining(deadline))
    _apply_missing_selection(candidate, proposal['owners'], deadline)
    scope = literal_scope(source, candidate, proposal['owners'])
    result = dict(complete=True, candidate=str(candidate),
        candidate_sha256=force._hash(candidate), scope=scope, proposal=fresh,
        saved_original_parent_receiving_still_required=True, routing_admitted=False,
        current_qualified=False, release_authority=False)
    _live(proposal, deadline)
    return candidate, result


def receive(source, candidate, proposal, *, timeout_s=10.):
    """Fresh original-Source model receiving; whole-board gates remain due."""
    deadline = _deadline(timeout_s)
    _need(type(proposal) is dict, 'exact_internal_connection_proposal_required')
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    _need(source != candidate and not source.samefile(candidate),
          'distinct_saved_internal_connection_boundaries_required')
    child_family = force._family(candidate, proposal['board_hint'])
    fresh = plan(source, board_hint=proposal['board_hint'],
                 owner_uuids=[o['owner_uuid'] for o in proposal['owners']],
                 timeout_s=_remaining(deadline))
    _need(fresh == _stable(proposal), 'stale_or_forged_internal_connection_proposal')
    scope = literal_scope(source, candidate, fresh['owners'])
    _need(child_family == force._family(candidate, proposal['board_hint']),
          'internal_connection_candidate_family_changed')
    result = dict(ok=True, complete=True, scope_only=True, proposal=fresh, scope=scope,
                candidate=str(candidate), candidate_sha256=force._hash(candidate),
                candidate_family=child_family, fitted_component_electrical_continuity_only=True,
                all_native_current_field_ground_pair_and_parity_gates_still_required=True,
                no_physical_open_reduction_claimed=True, routing_admitted=False,
                current_qualified=False, full_Kelvin_qualified=False, fab_ready=False,
                release_authority=False)
    _live(fresh, deadline)
    _need(child_family == force._family(candidate, proposal['board_hint'])
          and result['candidate_sha256'] == force._hash(candidate),
          'internal_connection_candidate_family_changed')
    _remaining(deadline)
    return result

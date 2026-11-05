"""Private, source-bound missing-alias proposal; never library qualification.

Existing literal entries survive the proposed source table unchanged. A
separate native table resolves those SAME entries against the actual source
project, not the private output directory or user-global configuration.
"""
import hashlib
import json
import os
from pathlib import Path
import re

import cec_native_library_context as context

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def propose(board, table, aliases, *, expected_board_sha256, expected_table_sha256):
    board, table = Path(board).resolve(strict=True), Path(table).resolve(strict=True)
    if (board.suffix != '.kicad_pcb' or table.name != 'fp-lib-table'
            or not table.is_relative_to((ROOT/'beta').resolve())
            or sha(board) != expected_board_sha256 or sha(table) != expected_table_sha256):
        raise ValueError('exact_source_board_and_project_table_required')
    if (type(aliases) is not list or not aliases or len(aliases) > 16
            or len(set(aliases)) != len(aliases)
            or any(type(a) is not str or not re.fullmatch(r'cec-[A-Za-z0-9_]+', a) for a in aliases)):
        raise ValueError('unique_explicit_vendored_aliases_required')
    env = dict(os.environ)
    original = table.read_text()
    rows, _, _ = context._table(original, table.parent, env)
    references = context._references(board)
    additions = []; targets = {}
    for alias in aliases:
        if alias in rows: raise ValueError('alias_already_present_or_disabled')
        items = sorted(item for name, item in references if name == alias)
        if len(items) != 1: raise ValueError('one_exact_referenced_footprint_id_required')
        vendor = ROOT/'lib/vendor'/(alias[4:]+'.pretty')
        if vendor.is_symlink() or not vendor.is_dir(): raise ValueError('actual_vendored_directory_required')
        vendor = vendor.resolve()
        if not vendor.is_relative_to((ROOT/'lib/vendor').resolve()): raise ValueError('vendor_path_escape')
        target = vendor/(items[0]+'.kicad_mod')
        if target.is_symlink() or not target.is_file(): raise ValueError('actual_vendored_item_required')
        # The source URI is project-relative and must resolve to this exact
        # repository-vendored target; no environment/global alias fallback.
        relative = os.path.relpath(vendor, table.parent).replace(os.sep, '/')
        uri = '${KIPRJMOD}/'+relative
        additions.append('  (lib (name '+json.dumps(alias)+')(type "KiCad")(uri '+json.dumps(uri)+')(options "")(descr "Existing vendored footprint; alias registration only"))\n')
        targets[str(target)] = sha(target)
    end = original.rfind(')')
    patched = original[:end]+''.join(additions)+original[end:]
    final_rows, native_table, _ = context._table(patched, table.parent, env)
    if any(final_rows[name] != row for name, row in rows.items()): raise ValueError('existing_alias_changed')
    binding = dict(board=str(board), board_sha256=expected_board_sha256,
        table=str(table), table_sha256=expected_table_sha256, vendor_items=targets,
        helper_sha256=sha(__file__), context_helper_sha256=sha(context.__file__),
        original_library_authority=canonical(context.authority(board, table)))
    if not live(binding): raise ValueError('source_epoch_changed_during_alias_proposal')
    return dict(binding=binding, aliases=aliases, proposed_source_table=patched,
        native_explicit_table=native_table, existing_entries_preserved=True,
        source_project=str(table.parent), library_qualification=False,
        native_replay_still_required=True, missing_alias_not_geometry_pass=True)


def live(binding):
    return (sha(binding['board']) == binding['board_sha256']
        and sha(binding['table']) == binding['table_sha256']
        and sha(__file__) == binding['helper_sha256']
        and sha(context.__file__) == binding['context_helper_sha256']
        and canonical(context.authority(binding['board'], binding['table'])) == binding['original_library_authority']
        and all(sha(path) == digest for path, digest in binding['vendor_items'].items()))


def write_private(proposal, output):
    """Write a fresh diagnostic namespace, not a PCB family or publication."""
    if not live(proposal['binding']): raise ValueError('stale_alias_proposal')
    binding = proposal['binding']
    fresh = propose(binding['board'], binding['table'], proposal['aliases'],
        expected_board_sha256=binding['board_sha256'], expected_table_sha256=binding['table_sha256'])
    if canonical(proposal) != canonical(fresh): raise ValueError('private_alias_proposal_not_independently_rederived')
    output = Path(output).resolve()
    if output.is_relative_to(ROOT.resolve()): raise ValueError('private_external_output_required')
    output.mkdir(parents=True, exist_ok=False)
    (output/'proposed-source-fp-lib-table').write_text(proposal['proposed_source_table'])
    native = output/'fp-lib-table'; native.write_text(proposal['native_explicit_table'])
    receipt = {k:v for k,v in proposal.items() if k not in ('proposed_source_table', 'native_explicit_table')}
    receipt.update(native_table=str(native), native_table_sha256=sha(native),
        replay=dict(api='cec_native_drc_runner.run', board=proposal['binding']['board'],
            footprint_table=str(native), board_hint=None, timeout_s=10,
            instruction='Explicit diagnostic table only; independently bind the named source board and original project. Never claim canonical table repaired.'))
    if not live(proposal['binding']): raise ValueError('source_epoch_changed_before_private_receipt')
    (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt

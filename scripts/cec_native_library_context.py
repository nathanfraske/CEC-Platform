"""Read-only native footprint parity in an explicit, source-bound library context.

Private candidates are not projects: their directory usually has no library
table, and copying a relative table there resolves KIPRJMOD incorrectly. Give
the unmodified native checker a private global table with absolute URIs from
the authoritative project table instead. Never edit user settings or invent a
library from the embedded board footprints. Missing libraries/items remain
native findings; real differences from the vendored library remain findings.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import cec_source_literal_additions as literal
from cec_source_retaining_ses_import import children, kind

MAX_TABLE_BYTES = 1024 * 1024
MAX_LIBRARIES = 256
MAX_DIRECTORY_ITEMS = 20000
MAX_REFERENCED_ITEMS = 2048
MAX_ITEM_BYTES = 8 * 1024 * 1024


def _hash(path, limit):
    path = Path(path)
    if not path.is_file():
        return None
    if path.stat().st_size > limit:
        raise ValueError('native_library_file_byte_bound')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _table(text, project, env):
    if len(text.encode()) > MAX_TABLE_BYTES or not re.match(r'\s*\(\s*fp_lib_table(?:\s|\))', text):
        raise ValueError('bounded_native_footprint_table_required')
    # Validate the whole root, not just whichever rows a permissive parser sees.
    literal._root(text.replace('fp_lib_table', 'kicad_pcb', 1))
    rows = {}; edits = []; variables = {}; version_seen = False
    for start, end in children(text):
        node = text[start:end]
        if kind(node) == 'version':
            if version_seen or literal._atoms(node[1:-1]) != [('version', 'version'), ('7', '7')]:
                raise ValueError('unsupported_native_library_table_version')
            version_seen = True
            continue
        if kind(node) != 'lib':
            raise ValueError('unrecognized_native_library_table_child')
        fields = {}
        for a, b in children(node):
            key = kind(node[a:b]); atoms = literal._atoms(node[a+1:b-1])
            if key in fields or key not in ('name', 'type', 'uri', 'options', 'descr', 'disabled', 'hidden'):
                raise ValueError('ambiguous_or_unsupported_native_library_row')
            if len(atoms) != (1 if key in ('disabled', 'hidden') else 2):
                raise ValueError('scalar_native_library_field_required')
            fields[key] = (atoms[-1][0], a, b)
        if not {'name', 'type', 'uri', 'options'} <= fields.keys():
            raise ValueError('incomplete_native_library_row')
        name = fields['name'][0]
        if not name or name in rows or fields['type'][0] != 'KiCad' or fields['options'][0]:
            raise ValueError('unique_native_kicad_directory_library_required')
        uri, a, b = fields['uri']
        def replace(match):
            key = match.group(1)
            value = str(project) if key == 'KIPRJMOD' else env.get(key)
            if not value or '${' in value or '$(' in value or '\x00' in value:
                raise ValueError('unresolved_or_recursive_native_library_variable')
            variables[key] = value
            return value
        uri = re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', replace, uri)
        if '$' in uri or '\x00' in uri or '://' in uri or not Path(uri).is_absolute():
            raise ValueError('absolute_local_native_library_uri_required')
        path = Path(uri).resolve()
        rows[name] = dict(path=str(path), enabled='disabled' not in fields,
                          hidden='hidden' in fields)
        edits.append((start+a, start+b, '(uri '+json.dumps(str(path), ensure_ascii=False)+')'))
        if len(rows) > MAX_LIBRARIES:
            raise ValueError('native_library_row_bound')
    if not version_seen:
        raise ValueError('explicit_native_library_table_version_required')
    rewritten = text
    for a, b, value in reversed(edits):
        rewritten = rewritten[:a] + value + rewritten[b:]
    return rows, rewritten, variables


def _references(board):
    text = Path(board).read_text()
    spans, _ = literal._root(text)
    result = set()
    for a, b in spans:
        node = text[a:b]
        if kind(node) != 'footprint':
            continue
        inner = children(node)
        head = literal._atoms(node[1:inner[0][0] if inner else len(node)-1])
        if len(head) != 2:
            raise ValueError('explicit_native_footprint_id_required')
        name = head[1][0]
        if ':' not in name:
            continue  # The native checker likewise cannot compare a library-less item.
        nickname, item = name.split(':', 1)
        if not nickname or not item or item in ('.', '..') or any(c in item for c in '/\\\x00'):
            raise ValueError('bounded_native_library_item_name_required')
        result.add((nickname, item))
        if len(result) > MAX_REFERENCED_ITEMS:
            raise ValueError('native_referenced_library_item_bound')
    return sorted(result)


def _snapshot(board, table, env):
    table = Path(table).resolve()
    digest = _hash(table, MAX_TABLE_BYTES)
    if digest is None:
        raise ValueError('declared_native_footprint_table_missing')
    rows, rendered, variables = _table(table.read_text(), table.parent, env)
    references = _references(board)
    directories = {}; items = {}
    for nickname, item in references:
        row = rows.get(nickname)
        if row is None or not row['enabled']:
            continue  # Do not manufacture an alias or enable a disabled library.
        directory = Path(row['path'])
        if row['path'] not in directories:
            entries = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else None
            if entries is not None and len(entries) > MAX_DIRECTORY_ITEMS:
                raise ValueError('native_library_directory_inventory_bound')
            directories[row['path']] = entries
        path = directory / (item+'.kicad_mod')
        items[str(path)] = dict(resolved_path=str(path.resolve()), sha256=_hash(path, MAX_ITEM_BYTES))
    return dict(table=str(table), table_sha256=digest, rows=rows,
                variables=variables, references=references, directory_entries=directories,
                referenced_files=items, rendered_table_sha256=hashlib.sha256(rendered.encode()).hexdigest()), rendered


def authority(board, table, *, environment=None):
    """Bind a queued whole-stage epoch to the same inputs as its native calls."""
    return _snapshot(board, table, dict(os.environ if environment is None else environment))[0]


@contextmanager
def prepare(board, *, library_table=None, environment=None, version='10.0'):
    """Yield environment/proof/verify without touching the source board family.

    An absent context is reported as unbound, never as successful library
    qualification. Callers selecting a production board must supply its table.
    """
    env = dict(os.environ if environment is None else environment)
    board = Path(board).resolve(); local = board.parent/'fp-lib-table'
    selected = Path(library_table).resolve() if library_table is not None else (local if local.is_file() else None)
    if selected is None:
        proof = dict(bound=False, isolated=False, reason='no_explicit_or_board_local_library_table',
                     findings_suppressed=0, source_geometry_changed=False)
        yield env, proof, lambda: None
        return
    if not re.fullmatch(r'[1-9][0-9]*\.[0-9]+', version):
        raise ValueError('explicit_native_config_version_required')
    snapshot, rendered = _snapshot(board, selected, env)
    local_hash = _hash(local, MAX_TABLE_BYTES)
    if local_hash is not None and local.resolve() != selected:
        other, _ = _snapshot(board, local, env)
        if other['rows'] != snapshot['rows']:
            raise ValueError('conflicting_candidate_project_library_table')
    with tempfile.TemporaryDirectory(prefix='cec-native-library-') as root:
        config = Path(root)/version; config.mkdir()
        relocated = config/'fp-lib-table'; relocated.write_text(rendered)
        env['KICAD_CONFIG_HOME'] = root
        proof = dict(bound=True, isolated=True, authority=snapshot,
                     candidate_project_table_sha256=local_hash,
                     private_table=str(relocated), private_table_sha256=_hash(relocated, MAX_TABLE_BYTES),
                     findings_suppressed=0, source_geometry_changed=False,
                     original_user_configuration_edited=False, source_and_context_unchanged=False)
        def verify():
            after, after_text = _snapshot(board, selected, env)
            if (after != snapshot or after_text != rendered
                    or _hash(local, MAX_TABLE_BYTES) != local_hash
                    or _hash(relocated, MAX_TABLE_BYTES) != proof['private_table_sha256']):
                raise ValueError('native_library_context_changed_during_run')
            proof['source_and_context_unchanged'] = True
        yield env, proof, verify

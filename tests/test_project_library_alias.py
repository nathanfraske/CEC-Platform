import json
from pathlib import Path
import pytest
import cec_project_library_alias as op


@pytest.fixture
def case(tmp_path, monkeypatch):
    root = tmp_path/'repo'; project = root/'beta/renamed'; project.mkdir(parents=True)
    monkeypatch.setattr(op, 'ROOT', root)
    vendor = root/'lib/vendor/Package_SON.pretty'; vendor.mkdir(parents=True)
    item = vendor/'Exact.kicad_mod'; item.write_text('(footprint "Exact")')
    board = tmp_path/'board.kicad_pcb'; board.write_text('(kicad_pcb (footprint "cec-Package_SON:Exact"))')
    table = project/'fp-lib-table'
    table.write_text('(fp_lib_table (version 7)\n(lib (name "old")(type "KiCad")(uri "${KIPRJMOD}/../../lib/old.pretty")(options "")(descr "opaque existing entry"))\n)')
    return board, table, vendor, item


def proposal(case, aliases=None):
    board, table, *_ = case
    return op.propose(board, table, ['cec-Package_SON'] if aliases is None else aliases,
        expected_board_sha256=op.sha(board), expected_table_sha256=op.sha(table))


def test_private_alias_retains_existing_literal_entries_and_exact_source_resolution(case, tmp_path):
    board, table, vendor, item = case; original = table.read_bytes(); pcb = board.read_bytes()
    q = proposal(case); assert original[:-1].decode() in q['proposed_source_table']
    assert '${KIPRJMOD}/../../lib/vendor/Package_SON.pretty' in q['proposed_source_table']
    receipt = op.write_private(q, tmp_path/'private')
    assert str(vendor) in (tmp_path/'private/fp-lib-table').read_text()
    assert receipt['replay']['board_hint'] is None and not receipt['library_qualification']
    assert table.read_bytes() == original and board.read_bytes() == pcb
    assert op.live(json.loads(json.dumps(q['binding'])))


@pytest.mark.parametrize('fault', ['wrong-target','traversal','duplicate','ambiguous','global-fallback','existing','stale-board','stale-table','vendor-symlink'])
def test_alias_authority_is_not_inferred_or_substituted(case, fault, tmp_path):
    board, table, vendor, item = case
    if fault == 'wrong-target': item.rename(vendor/'Other.kicad_mod')
    elif fault == 'traversal': board.write_text('(kicad_pcb (footprint "cec-Package_SON:../Exact"))')
    elif fault == 'ambiguous': board.write_text('(kicad_pcb (footprint "cec-Package_SON:Exact")(footprint "cec-Package_SON:Other"))')
    elif fault == 'global-fallback': item.unlink()
    elif fault == 'existing': table.write_text('(fp_lib_table (version 7)(lib (name "cec-Package_SON")(type "KiCad")(uri "${KIPRJMOD}/wrong")(options "")))')
    elif fault == 'vendor-symlink': item.unlink(); item.symlink_to(table)
    if fault in ('stale-board','stale-table'):
        q = proposal(case); (board if fault == 'stale-board' else table).write_text('changed')
        with pytest.raises(ValueError): op.write_private(q, tmp_path/'private')
    else:
        with pytest.raises(ValueError): proposal(case, ['cec-Package_SON']*2 if fault == 'duplicate' else None)


def test_vendor_item_mutation_invalidates_private_proposal(case, tmp_path):
    q = proposal(case)
    case[3].write_text('(footprint "Exact" (pad "1" smd rect))')
    with pytest.raises(ValueError): op.write_private(q, tmp_path/'private')
    assert not (tmp_path/'private').exists()


def test_duplicate_existing_library_names_refuse_before_alias_append(case):
    board, table, *_ = case
    text = table.read_text(); row = text[text.index('(lib'):text.rfind(')')]
    table.write_text(text[:text.rfind(')')]+row+')')
    with pytest.raises(ValueError): proposal(case)


def test_modified_private_table_cannot_reuse_a_real_source_binding(case, tmp_path):
    q = proposal(case); q['native_explicit_table'] = '(fp_lib_table (version 7))'
    with pytest.raises(ValueError): op.write_private(q, tmp_path/'private')
    assert not (tmp_path/'private').exists()

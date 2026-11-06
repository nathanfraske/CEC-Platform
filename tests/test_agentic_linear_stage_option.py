"""Explicit pipeline wiring only; manufacturer/current proofs remain independent."""
import pcbnew
import pytest
from cec_pipeline import cells, protocol
from test_agentic_annotation_cell_transport import operation
from test_source_reference_group_transport import external_fixture

FLAG = 'allow_linear_power_stage_reconstruction'


@pytest.mark.parametrize('value', [None, 0, 1, 'yes', [], {}])
def test_invalid_option_fails_before_source_work(value):
    op = {FLAG: value}
    for call in (lambda: cells.plan(None, op, 'opaque'),
                 lambda: cells.compile_macro(None, op, 'opaque'),
                 lambda: cells.construct(None, op, board_hint='opaque', request={}),
                 lambda: cells.receive_macro('unused', 'unused', op, {}, 'opaque')):
        with pytest.raises(ValueError, match='explicit_linear_power_stage_boolean'):
            call()


@pytest.mark.parametrize('enabled', [False, True])
def test_plan_and_native_compile_forward_explicit_option(tmp_path, monkeypatch, enabled):
    import cec_cell_escape_replan as escape
    import cec_cell_macro_requests as compiler
    source, _, group = external_fixture(tmp_path)
    board = pcbnew.LoadBoard(str(source)); op = operation(group)
    if enabled:
        op[FLAG] = True
    seen = []
    monkeypatch.setattr(escape, 'prepare', lambda *a, **k:
                        seen.append(k) or dict(retired_track_uuids=[]))
    cells.plan(board, op, 'opaque')
    assert seen[-1][FLAG] is enabled
    class CompilerReached(Exception):
        pass
    def compile_spy(*args, **kwargs):
        seen.append(kwargs)
        raise CompilerReached
    monkeypatch.setattr(compiler, 'compile', compile_spy)
    with pytest.raises(CompilerReached):
        cells.compile_macro(board, op, 'opaque')
    assert seen[-1][FLAG] is enabled


@pytest.mark.parametrize('enabled', [False, True])
def test_macro_receiver_recompiles_then_forwards_same_option(monkeypatch, enabled):
    import cec_complete_macro_cell as receiving
    op = dict(native_macro=True)
    if enabled:
        op[FLAG] = True
    packet = {'source_plan': {}}; seen = []
    monkeypatch.setattr(pcbnew, 'LoadBoard', lambda path: object())
    def compile_spy(board, operation, hint):
        seen.append(cells.linear_stage_option(operation))
        return None, packet, []
    monkeypatch.setattr(cells, 'compile_macro', compile_spy)
    monkeypatch.setattr(receiving, 'receive', lambda *a, **k: seen.append(k) or {'ok': True})
    receipt = dict(native_macro_packet_version=1, native_macro_packet=packet,
                   transported_source_copper_uuids=[])
    assert cells.receive_macro('source', 'candidate', op, receipt, 'opaque')['ok']
    assert seen[0] is enabled and seen[1][FLAG] is enabled


def test_public_closed_schemas_expose_opt_in_without_changing_old_requests():
    variants = [v for v in protocol._OPERATIONS
                if v['properties']['kind']['const'] == 'place_cell']
    assert len(variants) == 4
    assert sum(FLAG in v['properties'] for v in variants) == 2
    assert all(v['properties'][FLAG] == {'type': 'boolean'}
               and FLAG in v['required'] for v in variants if FLAG in v['properties'])
    assert protocol.TOOL_PARAMETERS['plan_cell'][FLAG] == {'type': 'boolean'}

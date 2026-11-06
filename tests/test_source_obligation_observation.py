"""One endpoint operation observes Source afresh, preserving exact demands."""
from contextlib import contextmanager
import os

import pytest
import cec_cell_escape_replan as escape
import cec_source_device_pinmap as pinmap
import cec_source_ground_leaf as canonical
import cec_source_linear_power_stage as stage
from test_linear_stage_ground_entries import fixture


@pytest.mark.parametrize('back',[False,True])
def test_native_demands_equal_uncached_and_each_invocation_is_fresh(tmp_path,monkeypatch,back):
    source,posed,partial,hint,owner,calls=fixture(tmp_path,monkeypatch,back=back)
    plan=escape.prepare(source,partial['poses'],board_hint=hint,
        allow_linear_power_stage_reconstruction=True)
    expected=escape._derive_obligations(source,posed,plan)
    original=escape._source_observations;seen=[]
    before=(escape.row._source_binding(source),escape.row._source_binding(posed),dict(os.environ))
    @contextmanager
    def observe(*a,**kw):
        with original(*a,**kw):
            scopes=(pinmap._observations.get(),canonical._export_observations.get(),stage._observations.get())
            assert all(v is not None for v in scopes)
            seen.append(scopes)
            yield
    monkeypatch.setattr(escape,'_source_observations',observe)
    for _ in range(2):
        assert escape._obligations(source,posed,plan)==expected
        assert pinmap._observations.get()is None
        assert canonical._export_observations.get()is None
        assert stage._observations.get()is None
    assert len(seen)==2 and all(a is not b for a,b in zip(*seen))
    assert before==(escape.row._source_binding(source),escape.row._source_binding(posed),dict(os.environ))


def test_canonical_mutation_during_operation_is_not_hidden_by_observation(tmp_path,monkeypatch):
    source,posed,partial,hint,owner,calls=fixture(tmp_path,monkeypatch)
    plan=escape.prepare(source,partial['poses'],board_hint=hint,
        allow_linear_power_stage_reconstruction=True)
    original=escape._derive_obligations
    from pathlib import Path
    root=Path(hint);before=root.read_bytes()
    def changed(*a,**kw):
        result=original(*a,**kw)
        root.write_bytes(before+b'\n; changed canonical source\n')
        return result
    monkeypatch.setattr(escape,'_derive_obligations',changed)
    try:
        with pytest.raises(ValueError,match='changed'):
            escape._obligations(source,posed,plan)
    finally:root.write_bytes(before)
    assert pinmap._observations.get()is None
    assert canonical._export_observations.get()is None
    assert stage._observations.get()is None


def test_ordinary_demands_do_not_add_Source_observation_preconditions(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    path,source,posed,plan=native_source(tmp_path,monkeypatch)
    monkeypatch.setattr(escape,'_source_observations',lambda *a,**kw:pytest.fail('ordinary scope changed'))
    assert escape._obligations(source,posed,plan)==escape._derive_obligations(source,posed,plan)

"""A policy, assembly peer or hidden environment change invalidates a job."""

import json
from pathlib import Path

from cec_pipeline import authority
from cec_pipeline.workbench import Workbench
from cec_pipeline.identity import code_identity, family
from cec_pipeline.checkpoint import sha
import pytest


def test_semantic_authority_includes_actual_library_and_selected_peer_bytes(
    tmp_path, monkeypatch
):
    import cec_beta_manifest as manifest
    import cec_assembly_envelope as assembly
    import cec_pipeline.native as native

    monkeypatch.setattr(authority, "ROOT", tmp_path)
    monkeypatch.setattr(manifest, "BY_BOARD", {})
    monkeypatch.setattr(native, "_native", lambda: (None, None))
    peer = tmp_path / "peer.kicad_pcb"
    peer.write_text("actual selected peer")
    pair = tmp_path / "pair.json"
    pair.write_text(json.dumps(dict(cover=dict(path=peer.name))))
    contract = tmp_path / "contract.json"
    contract.write_text("physical contract")
    policy = dict(role="carrier", contract=contract.name, pair=pair.name)
    monkeypatch.setattr(assembly, "declared_policy", lambda *args: policy)
    library = tmp_path / "lib"
    library.mkdir()
    part = library / "body.json"
    part.write_text("actual body")
    first = authority.inputs("source", "opaque")
    assert first[str(part)] and first[str(peer)]
    peer.write_text("different selected peer")
    assert authority.inputs("source", "opaque") != first
    peer.unlink()
    assert authority.inputs("source", "opaque")[str(peer)] is None


def test_physical_environment_is_hashed_not_plaintext_or_ignored(monkeypatch):
    monkeypatch.setenv("CEC_SYNTHETIC_POLICY_TEST", "not-a-real-secret-fixture")
    first = authority.environment_identity()
    assert first["CEC_SYNTHETIC_POLICY_TEST"] != "not-a-real-secret-fixture"
    monkeypatch.setenv("CEC_SYNTHETIC_POLICY_TEST", "changed")
    assert authority.environment_identity() != first


def test_cell_obligations_are_paged_without_replanning_or_losing_ports(tmp_path):
    w = object.__new__(Workbench)
    w.workspace = tmp_path
    w._make_job = lambda *args: "a" * 24
    requests = {
        str(n): dict(net="N" + str(n), ports=[[n, 0], [n, 1]]) for n in range(40)
    }
    w._run = lambda *args: dict(
        complete=True, result=dict(source_owned_connections=requests)
    )
    first = w.plan_cell("opaque", [], limit=16)
    last = w.plan_cell("opaque", [], offset=32, limit=16)
    assert (
        first["obligation_count"] == 40 and len(first["source_owned_connections"]) == 16
    )
    assert first["next_offset"] == 16 and last["next_offset"] is None
    assert len(last["source_owned_connections"]) == 8


def test_persisted_job_rechecks_semantic_and_environment_context(tmp_path, monkeypatch):
    source = tmp_path / "source.kicad_pcb"
    source.write_text("synthetic identity fixture, not native evidence")
    table = tmp_path / "fp-lib-table"
    table.write_text("(fp_lib_table)")
    token = "a" * 24
    directory = tmp_path / token
    directory.mkdir()
    state = {"peer": "exact"}
    monkeypatch.setattr(authority, "inputs", lambda *args: dict(state))
    row = dict(
        source_receipt_sha256="a" * 64,
        board="opaque",
        source=str(source),
        source_sha256=sha(source),
        source_family=family(source),
        code_identity=code_identity(),
        authority_inputs=dict(state),
        environment_identity=authority.environment_identity(),
        footprint_table=str(table),
        footprint_table_sha256=sha(table),
    )
    (directory / "job.json").write_text(json.dumps(row))
    workbench = object.__new__(Workbench)
    workbench.workspace = tmp_path
    workbench.manifest = dict(source_receipt_sha256="a" * 64)
    assert workbench._job(token)[1]["authority_inputs"] == state
    state["peer"] = "changed"
    with pytest.raises(ValueError, match="selected_assembly_input_changed"):
        workbench._job(token)
    state["peer"] = "exact"
    monkeypatch.setenv("CEC_SYNTHETIC_EPOCH_TEST", "changed")
    with pytest.raises(ValueError, match="physical_policy_environment_changed"):
        workbench._job(token)

"""Retired jobs cannot reappear behind a live layout tool or policy loader."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cec_synth_pipeline as backend

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "docs/legacy-job-retirement-2026-11-05.json"


def receipt():
    return json.loads(RECEIPT.read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def test_removed_jobs_are_absent_and_not_in_project_mcp():
    for name in receipt()["removed_paths"]:
        assert not (ROOT / name).exists(), name
    servers = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]
    assert "cec-layout" in servers and "cec-compute" not in servers


def test_library_compatibility_cannot_launch_an_old_autonomous_job():
    for name in receipt()["library_only_entrypoints"]:
        result = subprocess.run([sys.executable, str(ROOT / name), "--help"],
            text=True, capture_output=True, timeout=10, cwd=ROOT)
        assert result.returncode != 0, name
        assert "Retired legacy job" in result.stderr, (name, result.stderr)
        assert "cec_agentic_workbench.py" in result.stderr


def test_all_nine_policy_values_survive_without_loading_a_wave(monkeypatch):
    monkeypatch.setitem(sys.modules, "cec_fresh_wave", None)
    for board, expected in receipt()["preserved_resolved_policy_sha256"].items():
        assert digest(backend.Config.load(board).params) == expected, board


def test_active_control_plane_cannot_import_removed_jobs():
    retired = {Path(name).stem for name in receipt()["removed_paths"]
        if name.endswith(".py") and not name.startswith("tests/")}
    for source in (ROOT / "src/cec_pipeline").glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = {node.module.split(".")[0]}
            else:
                continue
            assert not imported & retired, (source.name, imported & retired)


def test_only_supported_inspection_service_is_read_only_and_has_no_watcher():
    unit = (ROOT / "ops/systemd/cec-inspection.service").read_text()
    assert "--inspection-only --no-watch --port 8091" in unit
    assert "cec_dashboard.py --port 8090" not in unit
    assert "Restart=on-failure" in unit
    assert "TimeoutStopSec=10" in unit

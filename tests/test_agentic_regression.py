"""The active regression runner cannot reuse old passes or hidden build code."""

import json
from pathlib import Path
import subprocess
import sys

from cec_pipeline import regression as runner


def test_active_process_ownership_and_batch_split_are_narrow():
    records = {
        1: dict(ppid=0, start=10, rss=1),
        2: dict(ppid=1, start=20, rss=2),
        3: dict(ppid=0, start=30, rss=3),
    }
    assert set(runner.owned_processes(1, 10, records)) == {1, 2}
    assert not runner.owned_processes(1, 11, records)
    assert runner.split_batch(("test_a", "test_b")) == (("test_a",), ("test_b",))


def test_short_lived_fresh_run_writes_bound_evidence_without_build_imports(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "fresh.xml"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "ops/cec_regression.py"),
            "--out",
            str(out),
            "--module",
            "test_agentic_campaign",
            "--workers",
            "1",
            "--batch-size",
            "1",
        ],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15.0,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads(out.with_name("fresh-receipt.json").read_text())
    assert receipt["ok"] and receipt["complete"] and receipt["prior_passes_not_reused"]
    assert receipt["counts"]["tests"] == 4 and receipt["counts"]["failures"] == 0
    assert receipt["code_unchanged"] and receipt["dependencies_unchanged"]
    assert all("/build/" not in path for path in receipt["dependencies"])

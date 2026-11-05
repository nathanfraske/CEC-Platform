"""Run the platform-neutral event bridge contracts in normal pytest discovery."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_node_event_bridge_contracts():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required by the desktop completion bridge')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/test_wave_completion_bridge.mjs'],
                            cwd=root, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr

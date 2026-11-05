"""Rated-subgraph checks must not consume KiCad's native type registry."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("operation", ["checker", "prune"])
def test_repeated_current_domain_operations_preserve_native_lifetime(tmp_path, operation):
    script = r'''
import gc, hashlib, sys
from pathlib import Path
from unittest import mock
root, out, operation = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path[:0] = [str(root / 'scripts'), str(root / 'tests')]
import pcbnew
import cec_constraints
import cec_current_topology
from test_current_domain_width import CurrentDomainWidthTests
path = str(out / 'anonymous.kicad_pcb')
fixture = CurrentDomainWidthTests()
board = fixture._aggregate_board(path)
renames = {'U7': 'SOURCE_X', 'F1': 'SINK_Y', 'C1': 'BYPASS_Z'}
for fp in board.GetFootprints():
    fp.SetReference(renames[fp.GetReference()])
pcbnew.SaveBoard(path, board)
original = hashlib.sha256(Path(path).read_bytes()).hexdigest()
capsule = sys.modules['swig_runtime_data4'].type_pointer_capsule
def domain(*args, **kwargs):
    return ({'+5VSB': 2.5}, None,
            {'+5VSB': {'refs_src': ['SOURCE_X'], 'refs_sink': ['SINK_Y']}}, None)
def probe():
    loaded = pcbnew.LoadBoard(path)
    with mock.patch('cec_thermal_overlay.board_thermal_config', side_effect=domain):
        if operation == 'checker':
            result = cec_constraints.CHECKERS['trace-width-high-current'](loaded, path, {})
            assert result[0] is True, result
        else:
            result = cec_current_topology.prune_undersized_current_tracks(
                loaded, ['+5VSB'], board_hint=path)
            assert result['removed_count'] == 1, result
for _ in range(12):
    gc.collect()
    before = sys.getrefcount(capsule)
    probe()
    gc.collect()
    assert sys.getrefcount(capsule) == before, 'native registry reference imbalance'
    assert isinstance(pcbnew.LoadBoard(path), pcbnew.BOARD)
assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == original
'''
    result = subprocess.run(
        [sys.executable, "-c", script,
         str(Path(__file__).resolve().parents[1]), str(tmp_path), operation],
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr[-4000:]

"""Render source copper for the finite short-bridge topology study; no refill."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import cec_suite_inspection as view

SOURCE = ROOT / 'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
SHA = '4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310'
parser = argparse.ArgumentParser()
parser.add_argument('--layer', required=True, choices=['F.Cu', 'B.Cu'])
args = parser.parse_args()
out = Path(__file__).parent
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SHA
target = out / (args.layer + '.svg')
subprocess.run(view.plot_command(SOURCE, target, [args.layer, 'Edge.Cuts']),
               timeout=9.5, check=True, capture_output=True)
view.reframe_svg(target, [-2, -2, 82, 93])
subprocess.run(['rsvg-convert', '-w', '1500', '-b', '#101c22',
                '-o', str(target.with_suffix('.png')), str(target)], timeout=9.5, check=True)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SHA
(out / (args.layer + '-source.json')).write_text(json.dumps({
    'schema': 1, 'source': str(SOURCE.relative_to(ROOT)), 'sha256': SHA,
    'layers': [args.layer, 'Edge.Cuts'], 'refill': False, 'board_changed': False,
    'annotation': 'Existing source copper only; no proposed bridge drawn or installed.'
}, indent=2) + '\n')
print(target.with_suffix('.png'))

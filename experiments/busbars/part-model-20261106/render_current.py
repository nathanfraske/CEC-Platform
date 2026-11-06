"""Read-only full-board plots for the endpoint-first review; saved copper only."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import cec_suite_inspection as view

SOURCE = ROOT / 'experiments/repack/bar-corridor-20261106/c9-corrective-v4/candidate/board.kicad_pcb'
EXPECTED = 'b118546af6665d77b190a9ac8ce3132cde413d607cdb3d9b28ba620a3857be24'
OUT = Path(__file__).parent / 'endpoint-first-20261106'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED
OUT.mkdir(exist_ok=True)
for layer in ('F.Cu', 'B.Cu'):
    target = OUT / (layer + '.svg')
    subprocess.run(view.plot_command(SOURCE, target, [layer, 'F.Fab', 'Edge.Cuts']),
                   timeout=9.5, check=True, capture_output=True)
    view.reframe_svg(target, [-2, -2, 82, 93])
    subprocess.run(['rsvg-convert', '-w', '1200', '-b', '#101c22',
                    '-o', str(target.with_suffix('.png')), str(target)],
                   timeout=9.5, check=True)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED
(OUT / 'plot-sources.json').write_text(json.dumps(dict(
    schema=1, source=str(SOURCE.relative_to(ROOT)), sha256=EXPECTED,
    layers=['F.Cu', 'B.Cu'], other_layers=['F.Fab', 'Edge.Cuts'],
    annotation='Existing board only; no installed bar or improved candidate shown.',
    no_refill=True, no_copper_edit=True), indent=2) + '\n')
print(OUT)

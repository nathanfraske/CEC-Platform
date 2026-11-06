"""Read-only native paired-body/vent screen using the explicit stack contract."""
import argparse
import hashlib
import json
from pathlib import Path
from cec_pipeline.native import _native
p,_ = _native()
import cec_assembly_envelope as assembly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--carrier', type=Path, required=True)
    parser.add_argument('--cover', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = [args.carrier.resolve(), args.cover.resolve(), args.contract.resolve()]
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    contract = json.loads(paths[2].read_text())
    fit, _ = assembly.evaluate(paths[0],paths[1],contract)
    board = p.LoadBoard(str(paths[0]))
    vents = assembly.vent_reservations(board, assembly.facing_vents(fit,contract,'carrier'))
    margins = [row['margin_mm'] for row in fit['checks'] if 'margin_mm' in row]
    unchanged = hashes == [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    result = dict(schema=1, scope='declared_paired_body_and_vent_screen_not_guaranteed_physical_fit',
        source_files=dict(zip(map(str,paths),hashes)), source_files_unchanged=unchanged,
        ok=fit['ok'] and all(row['ok'] for row in vents) and unchanged,
        paired_body_checks=len(fit['checks']), missing=fit['missing'],
        failures=[row for row in fit['checks'] if not row['ok']],
        minimum_reported_margin_mm=min(margins) if margins else None,
        contacts=fit['contacts'], hardware=fit['hardware'], vent_checks=vents,
        projected_dimensions=fit['projected_dimensions'], assembled_Z_qualified=False,
        bar_installed=False, current_qualified=False, release_authority=False)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('ok','paired_body_checks','minimum_reported_margin_mm','failures')}))


if __name__ == '__main__': main()

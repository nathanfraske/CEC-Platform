#!/usr/bin/env python3
"""Create an unpromoted, source-hashed nominal mating repair candidate."""
from __future__ import annotations

import argparse
import json

import cec_interface_eco
import cec_xfcn_contract as contract


def repair(project, source, output, *, expected_sha256):
    import pcbnew
    import cec_swig_guard
    cec_swig_guard.pin()
    if project not in contract.PROJECTS:
        raise ValueError('project has no declared output mating rows')
    if cec_interface_eco.sha(source) != expected_sha256:
        raise ValueError('mating input digest changed')
    board = pcbnew.LoadBoard(str(source))
    plan = contract.PROJECTS[project]
    contract.require_mating_compilation(plan)
    declared = contract.project_refs(plan)
    if any(fp.IsFlipped() for fp in board.GetFootprints() if fp.GetReference() in declared):
        raise ValueError('flipped interface requires an explicit mated-side transform')
    poses = cec_interface_eco.poses(board)
    outline = None
    if plan.get('mating_datum_authority') == 'parent_rows' and plan['kind'] == 'daughterboard':
        # Recompile a declared, origin-bound source drawing. This explicit
        # width ECO must not masquerade as rigid transport of an old pattern.
        # Translated/flipped campaign frames require their own explicit map.
        footprints = {fp.GetReference():fp for fp in board.GetFootprints()}
        seed = plan['interface_frame_seed_mm']
        anchor = min(plan['refs'], key=lambda r: seed[r][0])
        if any(abs(a-b) > .01 for a,b in zip(poses[anchor], seed[anchor])):
            raise ValueError('daughter outline ECO requires declared source origin')
        for ref, expectation in declared.items():
            fp = footprints[ref]
            expected_id = contract.PARTS[expectation['part']]['footprint'].split(':')[-1]
            if str(fp.GetFPID().GetLibItemName()) != expected_id:
                raise ValueError('daughter outline ECO footprint identity differs')
            if abs((poses[ref][2]-seed[ref][2]+180)%360-180) > .01:
                raise ValueError('daughter outline ECO rotation differs')
            nets = contract.expectation_nets(expectation)
            for pad in fp.Pads():
                expected = nets.get(pad.GetNumber())
                actual = pad.GetNetname()
                if expected is None or not (actual == expected or expected.startswith('/') and actual.endswith(expected)):
                    raise ValueError('daughter outline ECO net mapping differs')
        targets = {r:plan['placements_mm'][r] for r in declared}
        outline = plan['outline_rect_mm']
    else:
        target_fn = (contract.mating_row_targets if project in contract.OUTPUT_MOUNT_PORTS
                     else contract.daughter_mating_targets)
        targets = target_fn(project, poses)
    return cec_interface_eco.apply(source, output, targets,
                                   expected_sha256=expected_sha256, outline_rect_mm=outline)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, choices=contract.PROJECTS)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    result = repair(args.project, args.input, args.output,
                    expected_sha256=args.expected_sha256)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

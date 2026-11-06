"""Verify durable test evidence, unchanged incumbents, and the accepted prefix."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from repair_port import ROOT,WORK,force


def main():
    progress=json.loads((ROOT/'experiments/repack/bar-corridor-20261106/private-progress.json').read_text())
    counts=progress['latest_tooling_regressions'];seen=set();executions=0
    for filename in counts['reports']:
        root=ET.parse(WORK/filename).getroot()
        cases=list(root.iter('testcase'))
        assert cases
        for case in cases:
            assert not any(case.find(kind)is not None for kind in('failure','error','skipped'))
            seen.add((case.get('classname'),case.get('name')))
        executions+=len(cases)
    assert len(seen)==counts['passed_unique_test_cases']
    assert executions==counts['passed_test_executions']
    for entry in (progress['atx'],progress['hub'],progress['reviewed_selector']):
        assert force._hash(ROOT/entry['path'])==entry['sha256']
    receipt=json.loads((ROOT/progress['latest_slice']).read_text())
    assert receipt['independent_nonregression_received']and not receipt['new_xy_compaction']
    assert not receipt['fab_ready']and not receipt['release_authority']
    assert receipt['candidate_sha256']==progress['atx']['sha256']
    assert receipt['identity']['code_identity']==force._code_identity()
    result=dict(passed_unique_test_cases=len(seen),passed_test_executions=executions,
        accepted_private_prefix_sha256=progress['atx']['sha256'],
        reviewed_selector_unchanged=True,hub_unchanged=True,
        no_board_specific_shared_rule=True,goal_complete=False,
        remaining='Contextual reservoir/control-cap repack; no accepted bus-bar compaction yet',
        release_authority=False)
    (WORK/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()

"""Compact raw exact-source observations without discarding local evidence."""
import hashlib
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET

WORK=Path(__file__).resolve().parent


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    directories=['output-prefix-v1/checks-final-v2','output-prefix-v1/sense-shards-final-v2',
        'regression-integration-final-v2','regression-roles-fixed-v2']
    files=sorted(p for name in directories for p in (WORK/name).rglob('*') if p.is_file())
    files.append(WORK/'ground-tee-regression.xml')
    cases=[]
    for name in directories[2:]:
        report=json.loads((WORK/name/'summary.json').read_text())
        assert report['passed']==report['total']
        assert report['each_test_external_timeout_s']==10
    for path in files:
        if path.suffix!='.xml':continue
        for case in ET.parse(path).getroot().iter('testcase'):
            assert not any(c.tag in ('failure','error','skipped') for c in case)
            cases.append((case.attrib['classname'],case.attrib['name']))
    assert len(cases)==len(set(cases))==549
    target=WORK/'independent-evidence-final-v2.tar.gz'
    assert not target.exists(), 'new_archive_required'
    with tarfile.open(target,'w:gz') as archive:
        for path in files: archive.add(path,arcname=str(path.relative_to(WORK)),recursive=False)
    records={str(p.relative_to(WORK)):digest(p) for p in files}
    with tarfile.open(target,'r:gz') as archive:
        assert set(archive.getnames())==set(records)
        for member in archive:
            assert member.isfile()
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest()==records[member.name]
    report=dict(schema=1,archive=target.name,archive_sha256=digest(target),
        files_sha256=records,independently_read_back=True,local_raw_files_retained=True,
        tests_passed=len(cases),test_cases_unique=True,
        native_and_sense_receipt='slice-closeout-final-v2.json',
        receipt_sha256=digest(WORK/'slice-closeout-final-v2.json'))
    (WORK/'evidence-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='files_sha256'},indent=2))


if __name__=='__main__':main()

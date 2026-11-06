"""Bounded independent receivers with at most three native subprocesses."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
WORK=Path(__file__).resolve().parent


def main():
    revision=sys.argv[1]
    assert revision and len(revision)<=48 and all(c.isalnum()or c in '-_'for c in revision)
    folder=WORK/('checks-'+revision)
    assert not folder.exists(),'fresh_check_directory_required'
    folder.mkdir()
    def job(name):
        command=[sys.executable,str(WORK/'check_stage.py'),name,'--revision',revision]
        try:
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=10)
            record=dict(stage=name,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
        except subprocess.TimeoutExpired as error:
            record=dict(stage=name,timeout_s=10,stdout=str(error.stdout or ''),stderr=str(error.stderr or ''))
        target=folder/(name+'.json')
        record['ok']=record.get('returncode')==0 and target.is_file()and json.loads(target.read_text())['ok']
        (folder/(name+'-process.json')).write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(dict(stage=name,ok=record['ok'],returncode=record.get('returncode'))),flush=True)
        return record['ok']
    if not job('source-plan'):raise ValueError('fresh_source_plan_failed')
    # The exact native receiver uses most of its 10-second lease; keep it
    # alone so optional parallel work cannot steal that bounded budget.
    if not job('barrel'):raise ValueError('independent_barrel_receiver_failed')
    names=('ground','current','craft','pairs','drc-source','drc-candidate','field-source','field-candidate')
    with ThreadPoolExecutor(max_workers=3)as pool:
        results=list(pool.map(job,names))
    if not all(results):raise ValueError('one_or_more_independent_receivers_failed')


if __name__=='__main__':main()

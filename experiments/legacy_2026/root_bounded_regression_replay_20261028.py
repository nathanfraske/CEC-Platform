"""Replay an explicit test inventory in short-lived, memory-guarded batches.

The prior XML supplies module names only, never a prior pass. Each pytest
process exits after a small batch so native KiCad allocations cannot build
up over the entire suite. A resource interruption splits that batch rather
than crediting its partial XML. Every native test keeps its own <=10s lease;
the batch wall limit is a composed multi-test work bound, not a native lease.
Only processes created by this runner, with matching /proc start identities,
may be stopped. No source, board, cache or unrelated process is removed.
"""
import argparse
import collections
import copy
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

import cec_force_current as force


MIB=1024*1024


def require(value,reason):
    if not value:raise ValueError(reason)


def module_names(xml):
    return {part for case in ET.parse(xml).iter('testcase')
        for part in case.get('classname','').split('.')if part.startswith('test_')}


def split_batch(names):
    require(len(names)>1,'single_module_resource_refusal_cannot_be_hidden')
    middle=len(names)//2
    return tuple(names[:middle]),tuple(names[middle:])


def fixture_inputs(values):
    """Bind explicitly named real fixture inputs, not only test source code."""
    require(type(values)is list and len(values)<=256,'finite_explicit_regression_fixture_inputs_required')
    paths=set();total=0
    for value in values:
        path=Path(value)
        require(path.is_absolute() and not path.is_symlink() and path.is_file(),
            'absolute_regular_regression_fixture_input_required')
        path=path.resolve(strict=True)
        require(path not in paths,'unique_regression_fixture_input_required')
        size=path.stat().st_size
        require(size<=64*MIB,'bounded_regression_fixture_input_required')
        total+=size;paths.add(path)
    require(total<=256*MIB,'bounded_total_regression_fixture_inputs_required')
    return paths


def process_inventory(proc=Path('/proc')):
    """Read bounded Linux process identities/RSS without a new dependency."""
    paths=[p for p in proc.iterdir()if p.name.isdigit()]
    require(len(paths)<=8192,'bounded_regression_process_inventory_required')
    result={};page=os.sysconf('SC_PAGE_SIZE')
    for path in paths:
        try:
            tail=(path/'stat').read_text().rsplit(') ',1)[1].split()
            resident=int((path/'statm').read_text().split()[1])*page
            result[int(path.name)]=dict(ppid=int(tail[1]),group=int(tail[2]),
                start=int(tail[19]),rss=resident)
        except (FileNotFoundError,ProcessLookupError):continue
    return result


def owned_processes(pid,start,inventory):
    root=inventory.get(pid)
    if root is None or root['start']!=start:return {}
    owned={pid:root}
    while True:
        additions={p:r for p,r in inventory.items()if p not in owned and r['ppid']in owned}
        if not additions:break
        owned.update(additions)
    return owned


def available_memory(proc=Path('/proc')):
    lines={p[0].rstrip(':'):int(p[1])*1024 for line in (proc/'meminfo').read_text().splitlines()
        if len(p:=line.split())>=2 and p[0]in('MemAvailable:',)}
    require('MemAvailable'in lines,'positive_live_MemAvailable_required')
    return lines['MemAvailable']


def stop_owned(job):
    """Narrow interruption only; identify each PID before signalling it."""
    for sig in (signal.SIGTERM,signal.SIGKILL):
        inventory=process_inventory();owned=owned_processes(job['process'].pid,job['start'],inventory)
        for pid,record in sorted(owned.items(),reverse=True):
            try:
                current=process_inventory().get(pid)
                if current is not None and current['start']==record['start']:
                    os.kill(pid,sig)
            except ProcessLookupError:pass
        try:job['process'].wait(timeout=1.);return
        except subprocess.TimeoutExpired:pass
    require(job['process'].poll()is not None,'owned_regression_job_did_not_stop')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior-receipt',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--added-module',action='append',default=[])
    p.add_argument('--fixture-input',type=Path,action='append',default=[])
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--batch-size',type=int,default=8)
    p.add_argument('--rss-mib',type=int,default=8192)
    p.add_argument('--job-rss-mib',type=int,default=2048)
    p.add_argument('--reserve-mib',type=int,default=4096)
    p.add_argument('--batch-timeout-s',type=int,default=300)
    a=p.parse_args();root=Path(__file__).resolve().parents[2];os.chdir(root)
    require(1<=a.workers<=4 and 1<=a.batch_size<=16 and 1024<=a.job_rss_mib<=3072
        and 2048<=a.rss_mib<=8192 and a.job_rss_mib<=a.rss_mib
        and 4096<=a.reserve_mib<=8192 and 30<=a.batch_timeout_s<=600,
        'bounded_regression_worker_memory_and_composed_batch_limits_required')
    out=a.out.resolve();receipt=out.with_name(out.stem+'-receipt.json')
    work=out.with_name(out.stem+'-batches')
    require(out.suffix=='.xml'and not any(q.exists()for q in(out,receipt,work)),
        'fresh_bounded_regression_outputs_required')
    old=json.loads(a.prior_receipt.read_text());prior=Path(old['xml']).resolve(strict=True)
    require(force._hash(prior)==old['xml_sha256'],'exact_prior_inventory_XML_required')
    inherited=module_names(prior)
    require(inherited and len(inherited)==old['modules'],'complete_prior_module_inventory_required')
    require(all(type(n)is str and n.startswith('test_')and n.replace('_','').isalnum()
        for n in a.added_module),'literal_added_test_module_names_required')
    names=sorted(inherited|set(a.added_module));tests={root/'tests'/(n+'.py')for n in names}
    require(all(q.is_file()for q in tests),'every_explicit_test_module_must_exist')
    deps=tests|set((root/'ops').rglob('*.py'))|{root/'tests/conftest.py',Path(__file__).resolve(),
        prior,a.prior_receipt.resolve(),root/'build/root_receive_local_transaction_20261022.py',
        root/'build/root_received_goal_scope_20261024.py'}
    deps.update(Path(q)for q in old['dependencies']if '/build/'in q and Path(q).is_file())
    fixtures=fixture_inputs(a.fixture_input);deps.update(fixtures)
    bound={str(q):force._hash(q)for q in sorted(deps)};epoch=force._code_identity()
    queue=collections.deque(tuple(names[i:i+a.batch_size])for i in range(0,len(names),a.batch_size))
    env=dict(os.environ,PYTHONPATH='scripts:ops:tests:build',
        CEC_NATIVE_DRC_TEST_BUILD='/home/codex/.cache/cec/native-drc-10.0.5',
        OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    active=[];attempts=[];finished=[];peak=0;max_job=0;fatal=None;started=time.monotonic()
    work.mkdir();os.nice(10)
    def journal():
        force._write(work/'progress.json',dict(complete=False,ok=False,
            active_batches=len(active),queued_batches=len(queue),completed_modules=sum(len(j['names'])for j in finished),
            required_modules=len(names),attempts=len(attempts),peak_owned_RSS_bytes=peak,
            elapsed_s=time.monotonic()-started,resource_limits=dict(total_RSS_bytes=a.rss_mib*MIB,
                each_job_RSS_bytes=a.job_rss_mib*MIB,reserve_bytes=a.reserve_mib*MIB),
            partial_success_not_receiving_authority=True,release_authority=False))
    try:
        while queue or active:
            while queue and len(active)<a.workers:
                require(available_memory()>=a.reserve_mib*MIB,'memory_reserve_before_launch_refused')
                batch=queue.popleft();number=len(attempts)+len(active)
                prefix=work/('batch-%04d'%number);log=prefix.with_suffix('.log');xml=prefix.with_suffix('.xml')
                require(not log.exists()and not xml.exists(),'fresh_batch_identity_required')
                handle=log.open('wb');command=['python3','-m','pytest','-q','--disable-warnings',
                    '--show-capture=no','--tb=short','--junitxml='+str(xml),
                    *('tests/'+n+'.py'for n in batch)]
                process=subprocess.Popen(command,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                inventory=process_inventory();record=inventory.get(process.pid)
                require(record is not None and record['group']==process.pid,'owned_new_regression_session_required')
                active.append(dict(process=process,start=record['start'],names=batch,xml=xml,log=log,
                    handle=handle,command=command,started=time.monotonic(),peak_RSS_bytes=0))
                journal()
            inventory=process_inventory();total=0
            for job in active:
                rss=sum(r['rss']for r in owned_processes(job['process'].pid,job['start'],inventory).values())
                job['live_RSS_bytes']=rss;job['peak_RSS_bytes']=max(job['peak_RSS_bytes'],rss);total+=rss
            peak=max(peak,total);max_job=max([max_job]+[j['peak_RSS_bytes']for j in active])
            pressure=total>a.rss_mib*MIB or available_memory()<a.reserve_mib*MIB
            victim=max(active,key=lambda j:j['live_RSS_bytes'])if pressure and active else None
            for job in list(active):
                reason=None
                if job['live_RSS_bytes']>a.job_rss_mib*MIB:reason='owned_job_RSS_budget'
                elif job is victim:reason='aggregate_RSS_or_live_memory_reserve'
                elif time.monotonic()-job['started']>a.batch_timeout_s:reason='composed_multi_test_batch_deadline'
                elif job['log'].stat().st_size>16*MIB:reason='bounded_batch_output_budget'
                if reason is not None:stop_owned(job)
                status=job['process'].poll()
                if status is None:continue
                job['handle'].close();active.remove(job)
                record={k:copy.deepcopy(v)for k,v in job.items()if k not in('process','handle','started')}
                record.update(exit_code=status,resource_interruption=reason,
                    elapsed_s=time.monotonic()-job['started'],partial_interrupted_XML_not_credited=reason is not None)
                record.update(xml=str(job['xml']),log=str(job['log']))
                attempts.append(record)
                if reason is not None:
                    if len(job['names'])==1:raise ValueError('single_module_resource_refusal:'+job['names'][0]+':'+reason)
                    left,right=split_batch(job['names']);queue.appendleft(right);queue.appendleft(left)
                else:
                    require(job['xml'].is_file(),'completed_batch_XML_missing')
                    require(set(job['names'])<=module_names(job['xml']),'completed_batch_module_coverage_missing')
                    finished.append(dict(names=job['names'],xml=job['xml'],exit_code=status))
                journal()
            time.sleep(.25)
        covered=[n for j in finished for n in j['names']]
        require(len(covered)==len(names)and set(covered)==set(names),'exactly_once_final_module_coverage_required')
    except BaseException as exc:
        fatal=type(exc).__name__+':'+str(exc)
    finally:
        for job in active:
            stop_owned(job);job['handle'].close()
        merged=ET.Element('testsuites')
        for job in finished:
            tree=ET.parse(job['xml']).getroot()
            for suite in ([tree]if tree.tag=='testsuite'else list(tree)):
                merged.append(copy.deepcopy(suite))
        ET.ElementTree(merged).write(out,encoding='utf-8',xml_declaration=True)
        counts={k:sum(int(s.get(k,0))for s in merged.iter('testsuite'))for k in('tests','failures','errors','skipped')}
        live=epoch==force._code_identity();unchanged=all(force._hash(q)==h for q,h in bound.items())
        complete=fatal is None and sum(len(j['names'])for j in finished)==len(names)
        ok=complete and all(j['exit_code']==0 for j in finished)and live and unchanged
        ok=ok and all(counts[k]==0 for k in('failures','errors','skipped'))
        result=dict(ok=ok,complete=complete,exit_code=0 if ok else 1,error=fatal,
            modules=len(names),completed_modules=sum(len(j['names'])for j in finished),counts=counts,
            newly_included_modules=sorted(set(a.added_module)-inherited),
            inherited_module_inventory_only=True,prior_receipt_hardware_or_test_pass_not_reused=True,
            code_identity=epoch,dependencies=bound,code_unchanged=live,dependencies_unchanged=unchanged,
            xml=str(out),xml_sha256=force._hash(out),attempts=attempts,
            elapsed_s=time.monotonic()-started,peak_owned_RSS_bytes=peak,peak_job_RSS_bytes=max_job,
            process_lifetime_bounded_by_batch=True,memory_limits=dict(aggregate_RSS_bytes=a.rss_mib*MIB,
                each_job_RSS_bytes=a.job_rss_mib*MIB,live_available_memory_reserve_bytes=a.reserve_mib*MIB),
            interrupted_partial_tests_never_credited=True,native_command_deadlines_not_raised=True,
            explicitly_bound_fixture_inputs={str(q):bound[str(q)]for q in sorted(fixtures)},
            whole_repository_claim=False,release_authority=False)
        force._write(receipt,result)
        print(json.dumps({k:result[k]for k in('ok','complete','error','modules','completed_modules','counts',
            'code_unchanged','dependencies_unchanged','peak_owned_RSS_bytes','elapsed_s')}),flush=True)
    return 0 if ok else 1


if __name__=='__main__':raise SystemExit(main())

"""Durable, bounded subprocess diagnostics for expensive native operations."""
import faulthandler
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback


# These files are outputs of the operation supervisor, never board/solver
# authority. Keep the exact declaration shared with input-identity capture;
# unknown CEC_* file-valued policy remains bound by default.
DIAGNOSTIC_OUTPUT_ENV_KEYS = frozenset((
    'CEC_OPERATION_PROGRESS', 'CEC_OPERATION_STACKS'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    temporary.write_text(json.dumps(value, indent=2, default=str)+'\n', encoding='utf-8')
    os.replace(temporary, path)


def progress(phase, **fields):
    path = os.environ.get('CEC_OPERATION_PROGRESS')
    # Fork/spawn probe children must not overwrite the owner's current phase.
    if not path or os.environ.get('CEC_OPERATION_OWNER_PID') != str(os.getpid()):
        return
    row = dict(phase=phase, timestamp=time.time(), pid=os.getpid(), **fields)
    write_json(path, row)
    with Path(path).with_suffix('.jsonl').open('a', encoding='utf-8') as sink:
        sink.write(json.dumps(row, default=str)+'\n')


def arm_diagnostics():
    """Called at native worker entry; keep handles alive until process exit."""
    path = os.environ.get('CEC_OPERATION_STACKS')
    if not path:
        return None
    handle = open(path, 'a', encoding='utf-8')
    faulthandler.enable(file=handle)
    # Periodic native faulthandler unwinding crashed inside Python's frame
    # dumper on the KiCad worker. Sample Python frames while holding the GIL
    # instead. Fatal-signal handling remains armed, but routine diagnostics
    # must not add an asynchronous native frame walk to a healthy operation.
    def snapshot(*_args):
        handle.write('\nPython stack snapshot %.3f\n' % time.time())
        for ident, frame in list(sys._current_frames().items())[:32]:
            handle.write('Thread %s\n' % ident)
            traceback.print_stack(frame, limit=60, file=handle)
        handle.flush()

    if hasattr(signal, 'SIGUSR1'):
        signal.signal(signal.SIGUSR1, snapshot)

    def sample():
        while True:
            time.sleep(60)
            snapshot()

    threading.Thread(target=sample, name='operation-stack-sampler', daemon=True).start()
    os.environ['CEC_OPERATION_OWNER_PID'] = str(os.getpid())
    progress('worker_entry')
    return handle


def available_timeout(requested, env, reserve_s=15):
    """Child budgets cannot outlive either enclosing operation or campaign.

    A nested worker gets its own operation deadline. Clamp before replacing
    that environment field, otherwise it silently renews its parent's lease.
    The reserve belongs to the caller's cleanup/certification, not search.
    """
    requested = float(requested)
    reserve_s = float(reserve_s)
    if (not math.isfinite(requested) or requested < 0
            or not math.isfinite(reserve_s) or reserve_s < 0):
        raise ValueError('operation timeout must be finite and nonnegative')
    deadlines = [float(env[key]) for key in
                 ('CEC_OPERATION_DEADLINE_EPOCH', 'CEC_JOB_DEADLINE_EPOCH')
                 if key in env]
    if any(not math.isfinite(deadline) for deadline in deadlines):
        raise ValueError('enclosing deadline must be finite')
    return (min(requested, max(0.0, min(deadlines)-time.time()-reserve_s))
            if deadlines else requested)


class OperationFailure(RuntimeError):
    def __init__(self, evidence):
        self.failure_evidence = evidence
        phase = (evidence.get('last_progress') or {}).get('phase', 'not_reported')
        super().__init__('%s: %s at %s; evidence %s' % (
            evidence['operation'], evidence['status'], phase, evidence['directory']))


@contextmanager
def finalization_reserve(reserve_s, *, env=None):
    """Give a serial coordinator's optional transaction a shorter shared lease.

    Every nested repair, power rebuild and measurement inherits the SAME
    deadline. Returning to the caller restores its reserved finalization time;
    no child may renew it. The caller must restore a complete selected artifact
    on exhaustion. Only explicit supervisor budget failures are caught, never
    crashes, cancellation or integrity errors. This grants no board admission.
    """
    environment = os.environ if env is None else env
    reserve_s = float(reserve_s)
    available_timeout(0., environment, reserve_s=reserve_s)
    key = 'CEC_OPERATION_DEADLINE_EPOCH'
    previous = environment.get(key)
    deadlines = [float(environment[name]) for name in
                 (key, 'CEC_JOB_DEADLINE_EPOCH') if name in environment]
    original = min(deadlines) if deadlines else None
    limited = original-reserve_s if original is not None else None
    report = dict(schema=1, reserve_s=reserve_s, applicable=bool(deadlines),
        parent_deadline_epoch=original, work_deadline_epoch=limited,
        budget_exhausted=False, release_authority=False)
    if limited is not None:
        environment[key] = str(limited)
    try:
        yield report
    except OperationFailure as exc:
        if exc.failure_evidence.get('status') not in (
                'operation_budget_exhausted', 'campaign_budget_exhausted'):
            raise
        report.update(budget_exhausted=True, reason='finalization_time_reserved',
                      operation_failure=dict(exc.failure_evidence))
    finally:
        if previous is None:
            environment.pop(key, None)
        else:
            environment[key] = previous


def probe_allocation(requested, jobs, workers, pairs_per_probe, *, reserve_s=60,
                     fraction=.5, batch_overhead_s=5., env=None):
    """Admit fewer fully funded probes instead of starving every candidate.

    The fractional share is a target, not a reason to strand every probe:
    one complete batch may borrow unused share when the hard deadline and
    finalist reserve both permit it. This never reduces per-pair effort or
    grants admission. Without an outer deadline requested effort is unchanged.
    """
    environment = os.environ if env is None else env
    requested = float(requested)
    if (not all(math.isfinite(v) for v in (requested, fraction, reserve_s, batch_overhead_s))
            or requested < 5 or not 0 < fraction <= 1 or reserve_s < 0
            or batch_overhead_s < 0 or jobs < 0 or workers < 1 or pairs_per_probe < 0
            or any(not isinstance(v, int) or isinstance(v, bool)
                   for v in (jobs, workers, pairs_per_probe))):
        raise ValueError('invalid probe allocation policy')
    deadlines = [float(environment[key]) for key in
                 ('CEC_OPERATION_DEADLINE_EPOCH','CEC_JOB_DEADLINE_EPOCH')
                 if key in environment]
    if any(not math.isfinite(value) for value in deadlines):
        raise ValueError('nonfinite probe deadline')
    jobs, workers = int(jobs), int(workers)
    requested_batches = math.ceil(jobs/workers)
    pairs = max(1,pairs_per_probe)
    allocated_at = time.monotonic()
    remaining = max(0., min(deadlines)-time.time()) if deadlines else None
    available = max(0., remaining-reserve_s) if remaining is not None else None
    fractional_allocation = available*fraction if available is not None else None
    allocation = fractional_allocation
    batch_cost = requested * pairs + batch_overhead_s
    minimum_batch_funded = bool(jobs and allocation is not None
                               and allocation < batch_cost <= available)
    if minimum_batch_funded:
        allocation = batch_cost
    batches = (min(requested_batches, int(allocation // batch_cost))
               if allocation is not None else requested_batches)
    admitted = min(jobs, batches * workers)
    return {'per_pair_timeout_s':requested if admitted else None,
            'requested_per_pair_s':requested, 'remaining_s':remaining,
            'reserve_s':reserve_s, 'fraction':fraction, 'allocated_s':allocation,
            'fractional_allocation_s':fractional_allocation,
            'available_after_reserve_s':available,
            'minimum_batch_funded':minimum_batch_funded,
            'allocated_at_monotonic_s':allocated_at,
            'minimum_remaining_s':batch_cost + reserve_s if jobs else 0.,
            'minimum_budget_shortfall_s':(max(0., batch_cost-available)
                if jobs and available is not None else 0.),
            'batches':batches, 'requested_batches':requested_batches,
            'admitted_jobs':admitted, 'deferred_jobs':jobs-admitted,
            'estimated_batch_s':batch_cost, 'batch_overhead_s':batch_overhead_s,
            'pairs_per_probe':pairs, 'workers':workers}


def run_probe_cohorts(payloads, allocation, run_batch, *, clock=None, env=None):
    """Refill a fixed probe-time share with previously unmeasured jobs only.

    The initial worst-case count is not a lifetime quota: fast completed jobs
    return unused time to this same share. Every new cohort still needs its
    full worst-case cost, and neither the original share nor the enclosing
    deadline/finalist reserve is renewed. Result collection never grants board
    admission. Failed workers stop refills; no slot is submitted twice.
    """
    clock = time.monotonic if clock is None else clock
    environment = os.environ if env is None else env
    payloads = list(payloads)
    slots = [row['slot'] for row in payloads]
    if len(set(slots)) != len(slots):
        raise ValueError('duplicate probe slots')
    workers = allocation['workers']
    cost = float(allocation['estimated_batch_s'])
    share = allocation['allocated_s']
    if (not isinstance(workers, int) or isinstance(workers, bool) or workers < 1
            or not math.isfinite(cost) or cost <= 0
            or (share is not None and (not math.isfinite(share) or share < 0))):
        raise ValueError('invalid probe cohort allocation')
    started = clock()
    allocated_at = float(allocation.get('allocated_at_monotonic_s', started))
    overhead = float(allocation.get('batch_overhead_s', 0.))
    if (not math.isfinite(allocated_at) or allocated_at > started
            or not math.isfinite(overhead) or not 0 <= overhead < cost):
        raise ValueError('invalid probe allocation clock or overhead')
    results, cohorts = [], []
    offset = 0
    stop = 'all_jobs_dispatched'
    while offset < len(payloads):
        elapsed = max(0., clock()-started)
        allocation_age = max(0., clock()-allocated_at)
        remaining = (max(0., share-allocation_age) if share is not None
                     else cost*len(payloads))
        remaining = available_timeout(remaining, environment,
                                      reserve_s=allocation['reserve_s'])
        # The first batch's setup allowance has already paid for the time
        # between allocation and dispatch (including pool setup). Requiring
        # that SAME overhead again stranded a precisely funded batch after
        # even a microsecond elapsed. Credit only actual setup, at most once,
        # never solver time. Later cohorts need their entire fresh batch cost.
        setup_paid = min(overhead, allocation_age) if not cohorts else 0.
        count = min(len(payloads)-offset,
                    int(math.nextafter(remaining+setup_paid, math.inf)//cost)*workers)
        if not count or allocation['per_pair_timeout_s'] is None:
            stop = 'insufficient_complete_probe_budget'
            break
        batch = payloads[offset:offset+count]
        expected = [row['slot'] for row in batch]
        before = clock()
        progress('repair_probe_cohort', cohort=len(cohorts), slots=expected,
                 remaining_share_s=remaining)
        error = None
        try:
            current = list(run_batch(batch))
            received = [row['slot'] for row in current]
            if len(received) != len(expected) or set(received) != set(expected):
                raise ValueError('probe cohort returned incomplete or duplicate slot identities')
        except Exception as exc:  # Failed native workers cannot consume a second lease.
            error = '%s: %s' % (type(exc).__name__, exc)
            current = [dict(slot=slot, pair_report=None,
                error='probe_cohort_worker_failure', detail=error, wall_s=0.) for slot in expected]
        results.extend(current)
        offset += count
        cohorts.append(dict(index=len(cohorts), slots=expected,
            remaining_share_s=remaining, estimated_s=math.ceil(count/workers)*cost,
            setup_already_spent_s=setup_paid,
            estimated_remaining_s=math.ceil(count/workers)*cost-setup_paid,
            wall_s=round(max(0., clock()-before), 6), error=error))
        if error or any(row.get('error') for row in current):
            stop = 'probe_worker_failure_no_retry'
            break
    return results, dict(schema=1, initial_admitted_jobs=allocation['admitted_jobs'],
        dispatched_slots=slots[:offset], deferred_slots=slots[offset:],
        initial_share_s=share, elapsed_s=round(max(0., clock()-started), 6),
        allocation_age_s=round(max(0., clock()-allocated_at), 6),
        cohorts=cohorts, stop=stop, release_authority=False)


def round_admission(observed_s=None, *, reserve_s=60., margin=1.1, env=None):
    """Do not strand an accepted result by launching an unaffordable round.

    The previous measured round is a conservative scheduling estimate, not
    a reduced solver limit. Native supervision remains the hard backstop.
    """
    environment = os.environ if env is None else env
    observed = 0. if observed_s is None else float(observed_s)
    if (not all(math.isfinite(value) for value in (observed, reserve_s, margin))
            or observed < 0 or reserve_s < 0 or margin < 1):
        raise ValueError('invalid repair round budget policy')
    deadlines = [float(environment[key]) for key in
                 ('CEC_OPERATION_DEADLINE_EPOCH', 'CEC_JOB_DEADLINE_EPOCH')
                 if key in environment]
    if any(not math.isfinite(value) for value in deadlines):
        raise ValueError('nonfinite round deadline')
    remaining = max(0., min(deadlines)-time.time()) if deadlines else None
    required = reserve_s + max(5., observed)*margin
    return {'start':remaining is None or remaining >= required,
            'remaining_s':remaining, 'required_s':required,
            'observed_round_s':observed_s, 'reserve_s':reserve_s, 'margin':margin}


def checkpoint(value):
    """Keep one atomic diagnostic snapshot; this is never promotion authority."""
    path = os.environ.get('CEC_OPERATION_PROGRESS')
    if not path or os.environ.get('CEC_OPERATION_OWNER_PID') != str(os.getpid()):
        return
    write_json(Path(path).with_name('checkpoint.json'), {
        **value, 'schema':1, 'purpose':'completed-round-diagnostics',
        'promotion_allowed':False, 'timestamp':time.time()})


def generation_admission(requested_s, observed_s=None, *, reserve_s=120., env=None):
    """Fund a finite cohort while reserving time for winner certification.

    The cap is scheduling, not a solver success condition. A timed-out job is
    still unproved, and a deferred cohort must not be called an infeasible one.
    Without an enclosing deadline the requested effort is unchanged.
    """
    requested_s = float(requested_s)
    if not math.isfinite(requested_s) or requested_s <= 0:
        raise ValueError('generation effort must be finite and positive')
    report = round_admission(observed_s, reserve_s=reserve_s, env=env)
    available = (requested_s if report['remaining_s'] is None else
                 max(0., report['remaining_s']-reserve_s))
    return {**report, 'timeout_s':min(requested_s, available),
            'requested_timeout_s':requested_s}


def optional_work_admission(requested_s, *, reserve_s=120., env=None):
    """Only start optional work if its whole allowance and finish reserve fit.

    This is scheduling, not physical admission. Deferring a repair leaves its
    input and every signoff obligation intact; it does not waive the defect.
    Unlike generation_admission, this does not shrink a fully specified solve
    into a predictably unfinished one. Without a deadline behavior is unchanged.
    """
    requested_s = float(requested_s)
    environment = os.environ if env is None else env
    available = available_timeout(requested_s, environment, reserve_s=reserve_s)
    return {'start':available >= requested_s, 'requested_s':requested_s,
            'available_s':available, 'reserve_s':float(reserve_s),
            'reason':('funded' if available >= requested_s else
                      'insufficient_optional_work_budget'),
            'release_authority':False}


def evaluations_exhausted(*reports):
    """A deferred lookahead is unproved even when the primary sweep finished."""
    return any((report or {}).get('budget_exhausted') is True for report in reports)


def _stop_owned_process(proc):
    """Terminate only the new process session owned by this invocation."""
    if os.name == 'posix':
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    # The leader can exit before its descendants. Kill the owned group even
    # when wait() returned, so native/grandchild workers cannot escape a budget.
    if os.name == 'posix':
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)


def run(command, directory, *, operation, timeout, env=None, accepted_exit_codes=(0,)):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ if env is None else env)
    allowed = available_timeout(timeout, environment)
    evidence = dict(operation=operation, directory=str(directory), command=list(command),
                    requested_timeout_s=float(timeout), allowed_timeout_s=allowed,
                    status='starting', log=str(directory/'worker.log'),
                    stacks=str(directory/'stacks.log'))
    started = time.monotonic()
    process = None
    old_handler = None
    environment.update(PYTHONUNBUFFERED='1',
        CEC_OPERATION_PROGRESS=str(directory/'progress.json'),
        CEC_OPERATION_STACKS=str(directory/'stacks.log'),
        CEC_OPERATION_DEADLINE_EPOCH=str(time.time()+allowed))
    try:
        if allowed <= 0:
            evidence['status'] = 'campaign_budget_exhausted'
        else:
            with (directory/'worker.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                    env=environment, start_new_session=True)
                evidence.update(status='running', pid=process.pid)
                write_json(directory/'operation.json', evidence)
                # An outer campaign TERM must also terminate this separately
                # owned session, not strand the native operation behind it.
                if threading.current_thread() is threading.main_thread():
                    def cancelled(signum, frame):
                        evidence['status'] = 'cancelled_by_parent'
                        raise SystemExit(128+signum)
                    old_handler = signal.signal(signal.SIGTERM, cancelled)
                try:
                    code = process.wait(timeout=allowed)
                    evidence.update(exit_code=code, status=(
                        'complete' if code in accepted_exit_codes else 'worker_failed'))
                except subprocess.TimeoutExpired:
                    evidence['status'] = 'operation_budget_exhausted'
                    if (directory/'stacks.log').exists() and hasattr(signal, 'SIGUSR1'):
                        try:
                            os.kill(process.pid, signal.SIGUSR1)
                        except ProcessLookupError:
                            pass
                        time.sleep(.1)
    finally:
        if process is not None and (process.poll() is None or evidence['status'] != 'complete'):
            _stop_owned_process(process)
        if process is not None:
            evidence['exit_code'] = process.returncode
        if old_handler is not None:
            signal.signal(signal.SIGTERM, old_handler)
        evidence['elapsed_s'] = round(time.monotonic()-started, 3)
        progress_path = directory/'progress.json'
        if progress_path.is_file():
            evidence['last_progress'] = json.loads(progress_path.read_text(encoding='utf-8'))
        write_json(directory/'operation.json', evidence)
    if evidence['status'] != 'complete':
        raise OperationFailure(evidence)
    return evidence

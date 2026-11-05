"""Preserve this job's exact native runtime lock outside a private family."""
import copy,getpass,json,os,secrets,socket,stat,time
from pathlib import Path

_ACTIVE_FENCES={}

def lock_path(candidate):
    p=Path(candidate).resolve(strict=True)
    return p.parent/('~'+p.with_suffix('.kicad_pro').name+'.lck')

def _absent(candidate):
    if lock_path(candidate).exists()or lock_path(candidate).is_symlink():
        raise ValueError('typed_print_preexisting_runtime_lock_refused')


def before_native(candidate,*,evidence_dir=None):
    _absent(candidate)
    if evidence_dir is not None:
        import cec_force_current as force
        p=Path(candidate).resolve(strict=True);out=Path(evidence_dir).resolve(strict=True)
        if out==p.parent or out.is_relative_to(p.parent):
            raise ValueError('runtime_observation_output_must_be_outside_family')
        if out.stat().st_dev!=p.parent.stat().st_dev:
            raise ValueError('runtime_fence_same_filesystem_required')
        fence=out/'native-runtime-start.json'
        if fence.exists()or fence.is_symlink():raise ValueError('fresh_runtime_fence_required')
        record=dict(candidate=str(p),candidate_sha256=force._hash(p),
            started_ns=time.time_ns(),started_monotonic_ns=time.monotonic_ns(),
            preexisting_runtime_lock_absent=True,nonce=secrets.token_hex(24),
            pid=os.getpid(),hostname=socket.gethostname(),username=getpass.getuser(),
            filesystem_clock_not_cross_clock_wall_comparison=True,release_authority=False)
        force._write(fence,record)
        s=fence.lstat()
        if not stat.S_ISREG(s.st_mode)or fence.is_symlink()or s.st_nlink!=1:
            raise ValueError('regular_private_runtime_fence_required')
        token=dict(schema=1,kind='same_filesystem_native_runtime_fence',record=record,
            fence=str(fence),fence_sha256=force._hash(fence),device=s.st_dev,
            inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns,size=s.st_size)
        _absent(p)
        if len(_ACTIVE_FENCES)>=128:raise ValueError('bounded_runtime_fence_inventory_required')
        _ACTIVE_FENCES[record['nonce']]=copy.deepcopy(token)
        return token
    return time.time_ns()


def _fenced_interval(candidate,out,token):
    """Prove creation against two clocks from the same filesystem domain.

    WSL time.time_ns and Windows/DrvFS file times can differ. Neither a
    tolerance nor a stale-lock exemption is used. The in-process lease,
    exact start marker, native producer, owner, and two filesystem creation
    fences are all required; pre-existing files are never adopted.
    """
    import cec_force_current as force
    if type(token)is not dict or token.get('kind')!='same_filesystem_native_runtime_fence':
        raise ValueError('exact_active_runtime_fence_required')
    record=token.get('record',{});nonce=record.get('nonce')
    saved=_ACTIVE_FENCES.get(nonce)if type(nonce)is str else None
    if saved is None or json.dumps(saved,sort_keys=True,allow_nan=False)!=json.dumps(token,sort_keys=True,allow_nan=False):
        raise ValueError('exact_active_runtime_fence_required')
    p=Path(candidate).resolve(strict=True);out=Path(out).resolve(strict=True)
    fence=Path(token['fence'])
    if (record['pid']!=os.getpid()or record['candidate']!=str(p)
            or record['candidate_sha256']!=force._hash(p)
            or record['hostname']!=socket.gethostname()or record['username']!=getpass.getuser()
            or time.monotonic_ns()<record['started_monotonic_ns']
            or fence!=out/'native-runtime-start.json'
            or out==p.parent or out.is_relative_to(p.parent)):
        raise ValueError('runtime_fence_exact_invocation_required')
    s=fence.lstat()
    if (not stat.S_ISREG(s.st_mode)or fence.is_symlink()or s.st_nlink!=1
            or (s.st_dev,s.st_ino,s.st_mtime_ns,s.st_ctime_ns,s.st_size)!=
               (token['device'],token['inode'],token['mtime_ns'],token['ctime_ns'],token['size'])
            or force._hash(fence)!=token['fence_sha256']
            or json.loads(fence.read_bytes())!=record):
        raise ValueError('runtime_start_fence_changed')
    end=out/'native-runtime-end.json'
    if end.exists()or end.is_symlink():raise ValueError('fresh_runtime_end_fence_required')
    force._write(end,dict(start_fence_sha256=token['fence_sha256'],nonce=nonce,
        completed_monotonic_ns=time.monotonic_ns(),release_authority=False))
    last=end.lstat()
    if (not stat.S_ISREG(last.st_mode)or end.is_symlink()or last.st_nlink!=1
            or last.st_dev!=s.st_dev or last.st_mtime_ns<s.st_mtime_ns
            or p.parent.stat().st_dev!=s.st_dev):
        raise ValueError('runtime_filesystem_creation_interval_refused')
    return s.st_mtime_ns,last.st_mtime_ns,nonce


def failure_evidence(candidate,producer=None,fence=None):
    """Bounded inspection only: never adopt, alter, or remove an unowned lock."""
    import cec_force_current as force
    lock=lock_path(candidate)
    inspection=dict(path=str(lock),exists=lock.exists(),symlink=lock.is_symlink())
    try:
        s=lock.lstat()
        inspection.update(mode=s.st_mode,device=s.st_dev,inode=s.st_ino,
            nlink=s.st_nlink,size=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
        if stat.S_ISREG(s.st_mode)and not lock.is_symlink()and s.st_size<=4096:
            inspection.update(bytes_hex=lock.read_bytes().hex(),sha256=force._hash(lock))
    except FileNotFoundError:pass
    except OSError as exc:inspection['inspection_error']=str(exc)
    return dict(raw_producer=copy.deepcopy(producer),runtime_fence=copy.deepcopy(fence),
        lock_inspection=inspection,diagnostic_only=True,release_authority=False)


def observe(candidate,out,run_native):
    """Keep this invocation's ephemeral lock out of BOTH compared families.

    The native producer is still independently checked by its caller. This
    wrapper owns no pre-existing lock and cannot quarantine an unsuccessful
    or differently bound producer's file. Save the absence-check timestamp
    before launch so an interrupted invocation has exact recovery evidence.
    """
    import cec_force_current as force
    out=Path(out).resolve();p=Path(candidate).resolve(strict=True)
    if out==p.parent or out.is_relative_to(p.parent):
        raise ValueError('runtime_observation_output_must_be_outside_family')
    started=None;proof=None
    try:
        _absent(p)
        out.mkdir(parents=True,exist_ok=False)
        started=before_native(p,evidence_dir=out)
        proof=run_native()
        observed=quarantine(p,out,proof,started)
        force._write(out/'native-runtime-preservation.json',observed)
        return proof,observed
    except Exception as exc:
        diagnostic=failure_evidence(p,proof,started)
        diagnostic['error']=str(exc)
        if out.is_dir():
            try:force._write(out/'native-runtime-failure.json',diagnostic)
            except Exception as logging_exc:diagnostic['evidence_write_error']=str(logging_exc)
        failure=ValueError(str(exc));failure.native_runtime_evidence=diagnostic
        raise failure from exc

def quarantine(candidate,out,producer,started_ns):
    import cec_force_current as force
    p=Path(candidate).resolve(strict=True);lock=lock_path(p)
    nonce=None
    if type(started_ns)is dict:
        lower,upper,nonce=_fenced_interval(p,out,started_ns)
    elif type(started_ns)is int:
        lower,upper=started_ns,time.time_ns()
    else:raise ValueError('exact_native_runtime_start_required')
    if not lock.exists()and not lock.is_symlink():
        if nonce is not None:_ACTIVE_FENCES.pop(nonce)
        return dict(generated=False,no_source_owner_lock_touched=True)
    if (producer.get('ok')is not True or producer.get('complete')is not True
            or producer.get('source_and_producer_unchanged')is not True
            or producer.get('command',[])[-1:]!=[str(p)]):
        raise ValueError('runtime_lock_native_lineage_refused')
    if not all(force._hash(Path(n))==h for n,h in producer['source_files'].items()):
        raise ValueError('runtime_lock_native_source_drift')
    s=lock.lstat()
    if (not stat.S_ISREG(s.st_mode)or lock.is_symlink()or s.st_nlink!=1 or s.st_size>4096
            or not lower<=s.st_mtime_ns<=upper
            or nonce is not None and (s.st_dev!=started_ns['device']or not lower<=s.st_ctime_ns<=upper)):
        raise ValueError('runtime_lock_exact_owner_or_generation_refused')
    data=lock.read_bytes()
    if json.loads(data)!=dict(hostname=socket.gethostname(),username=getpass.getuser()):
        raise ValueError('runtime_lock_exact_owner_or_generation_refused')
    target=Path(out).resolve()/'runtime-artifacts'/lock.name
    if target.is_relative_to(p.parent)or target.exists():raise ValueError('runtime_lock_quarantine_target_refused')
    target.parent.mkdir(parents=True,exist_ok=True);digest=force._hash(lock)
    lock.rename(target)
    if target.read_bytes()!=data or force._hash(target)!=digest or lock.exists():
        raise ValueError('runtime_lock_preservation_failed')
    if nonce is not None:_ACTIVE_FENCES.pop(nonce)
    return dict(generated=True,old=str(lock),new=str(target),sha256=digest,
                bytes_preserved=True,no_source_owner_lock_touched=True,
                same_filesystem_creation_fences=nonce is not None)

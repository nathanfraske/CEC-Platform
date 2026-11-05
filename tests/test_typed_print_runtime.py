import copy,getpass,json,os,socket,time
from pathlib import Path
import pytest
import cec_force_current as force
import typed_print_runtime as runtime


def producer(path):
    return dict(ok=True,complete=True,source_and_producer_unchanged=True,
        command=['actual-native',str(path)],source_files={str(path):force._hash(path)})


def write_lock(path,**changes):
    value=dict(hostname=socket.gethostname(),username=getpass.getuser());value.update(changes)
    runtime.lock_path(path).write_text(json.dumps(value))


def test_both_exact_native_endpoints_keep_their_own_locks_outside_family(tmp_path):
    for label in('source','candidate'):
        path=tmp_path/label/'board.kicad_pcb';path.parent.mkdir();path.write_text('exact material '+label)
        before=path.read_bytes();out=tmp_path/(label+'-runtime')
        def run():write_lock(path);return producer(path)
        proof,witness=runtime.observe(path,out,run)
        assert proof['ok']and witness['generated']and witness['bytes_preserved']
        assert path.read_bytes()==before and not runtime.lock_path(path).exists()
        assert (out/'native-runtime-start.json').is_file()
        assert (out/'native-runtime-preservation.json').is_file()
        assert json.loads((out/'native-runtime-start.json').read_text())['preexisting_runtime_lock_absent']
    assert len(list(tmp_path.glob('*-runtime/runtime-artifacts/*')))==2


def test_preexisting_owner_lock_is_never_removed_or_overwritten(tmp_path):
    path=tmp_path/'board.kicad_pcb';path.write_text('material');write_lock(path)
    before=runtime.lock_path(path).read_bytes();called=[]
    with pytest.raises(ValueError,match='preexisting_runtime_lock'):
        runtime.observe(path,tmp_path.parent/(tmp_path.name+'-out'),lambda:called.append(True))
    assert not called and runtime.lock_path(path).read_bytes()==before


@pytest.mark.parametrize('fault',['failed','foreign_command','source_drift','foreign_owner'])
def test_wrong_producer_or_owner_cannot_authorize_runtime_removal(tmp_path,fault):
    path=tmp_path/'source/board.kicad_pcb';path.parent.mkdir();path.write_text('material')
    def run():
        write_lock(path,**({'username':'different-owner'}if fault=='foreign_owner'else{}))
        proof=producer(path)
        if fault=='failed':proof['ok']=False
        elif fault=='foreign_command':proof['command'][-1]='different-board'
        elif fault=='source_drift':path.write_text('changed')
        return proof
    with pytest.raises(ValueError):runtime.observe(path,tmp_path/'runtime',run)
    assert runtime.lock_path(path).is_file()


def test_runtime_output_may_not_pollute_source_family(tmp_path):
    path=tmp_path/'board.kicad_pcb';path.write_text('material')
    with pytest.raises(ValueError,match='outside_family'):
        runtime.observe(path,tmp_path/'runtime',lambda:producer(path))


@pytest.mark.parametrize('offset_ns',[-120000000000,120000000000])
def test_native_filesystem_clock_fences_do_not_compare_wsl_and_windows_clocks(tmp_path,monkeypatch,offset_ns):
    path=tmp_path/'source/board.kicad_pcb';path.parent.mkdir();path.write_text('literal Source')
    wall=time.time_ns
    monkeypatch.setattr(runtime.time,'time_ns',lambda:wall()+offset_ns)
    result,witness=runtime.observe(path,tmp_path/'runtime',lambda:(write_lock(path),producer(path))[1])
    assert result['ok']and witness['generated']and witness['same_filesystem_creation_fences']
    assert not runtime.lock_path(path).exists()
    assert (tmp_path/'runtime/native-runtime-end.json').is_file()


def _fence(tmp_path):
    path=tmp_path/'source/board.kicad_pcb';path.parent.mkdir();path.write_text('literal Source')
    out=tmp_path/'runtime';out.mkdir()
    token=runtime.before_native(path,evidence_dir=out)
    return path,out,token


@pytest.mark.parametrize('fault',['nonce','pid','candidate','source_hash','marker_hash',
    'schema_float','schema_boolean','monotonic','mtime'])
def test_fence_tokens_are_exact_in_process_capabilities_not_caller_time_claims(tmp_path,fault):
    path,out,token=_fence(tmp_path);forged=copy.deepcopy(token);write_lock(path)
    if fault=='nonce':forged['record']['nonce']='not-the-invocation'
    elif fault=='pid':forged['record']['pid']+=1
    elif fault=='candidate':forged['record']['candidate']+='-different'
    elif fault=='source_hash':forged['record']['candidate_sha256']='0'*64
    elif fault=='marker_hash':forged['fence_sha256']='0'*64
    elif fault=='schema_float':forged['schema']=1.0
    elif fault=='schema_boolean':forged['schema']=True
    elif fault=='monotonic':forged['record']['started_monotonic_ns']=0
    elif fault=='mtime':forged['mtime_ns']=0
    before=runtime.lock_path(path).read_bytes()
    with pytest.raises(ValueError,match='exact_active_runtime_fence'):
        runtime.quarantine(path,out,producer(path),forged)
    assert runtime.lock_path(path).read_bytes()==before


@pytest.mark.parametrize('fault',['marker_bytes','marker_inode','marker_hardlink','marker_symlink',
    'old_lock','future_lock','lock_hardlink','lock_symlink','different_output'])
def test_same_filesystem_fences_never_adopt_replaced_or_out_of_interval_locks(tmp_path,fault):
    path,out,token=_fence(tmp_path);write_lock(path);lock=runtime.lock_path(path)
    marker=Path(token['fence']);before=lock.read_bytes()
    if fault=='marker_bytes':marker.write_text('different marker')
    elif fault=='marker_inode':
        replacement=out/'replacement';replacement.write_bytes(marker.read_bytes());replacement.replace(marker)
    elif fault=='marker_hardlink':os.link(marker,out/'extra-marker-link')
    elif fault=='marker_symlink':
        replacement=out/'real-marker';marker.rename(replacement);marker.symlink_to(replacement)
    elif fault=='old_lock':os.utime(lock,ns=(token['mtime_ns']-10000000000,)*2)
    elif fault=='future_lock':os.utime(lock,ns=(time.time_ns()+120000000000,)*2)
    elif fault=='lock_hardlink':os.link(lock,out/'extra-lock-link')
    elif fault=='lock_symlink':
        replacement=out/'real-lock';lock.rename(replacement);lock.symlink_to(replacement)
    elif fault=='different_output':out=tmp_path/'different-runtime';out.mkdir()
    with pytest.raises(ValueError):runtime.quarantine(path,out,producer(path),token)
    assert lock.read_bytes()==before


def test_fence_cannot_be_reused_for_a_second_lock(tmp_path):
    path,out,token=_fence(tmp_path);write_lock(path)
    result=runtime.quarantine(path,out,producer(path),token)
    assert result['bytes_preserved']
    write_lock(path);before=runtime.lock_path(path).read_bytes()
    with pytest.raises(ValueError,match='exact_active_runtime_fence'):
        runtime.quarantine(path,out,producer(path),token)
    assert runtime.lock_path(path).read_bytes()==before


def test_no_native_lock_still_closes_the_fresh_filesystem_lease(tmp_path):
    path,out,token=_fence(tmp_path)
    result=runtime.quarantine(path,out,producer(path),token)
    assert result==dict(generated=False,no_source_owner_lock_touched=True)
    assert token['record']['nonce']not in runtime._ACTIVE_FENCES


def test_fence_output_and_source_must_use_same_native_filesystem(tmp_path,monkeypatch):
    path=tmp_path/'source/board.kicad_pcb';path.parent.mkdir();path.write_text('Source')
    out=tmp_path/'runtime';out.mkdir();original=Path.stat
    def mismatch(p,*args,**kwargs):
        value=original(p,*args,**kwargs)
        if p==out:
            class Different:
                st_dev=value.st_dev+1
            return Different()
        return value
    monkeypatch.setattr(Path,'stat',mismatch)
    with pytest.raises(ValueError,match='same_filesystem'):
        runtime.before_native(path,evidence_dir=out)
    assert not(out/'native-runtime-start.json').exists()

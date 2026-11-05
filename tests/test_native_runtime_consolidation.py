"""Exact observer ownership, same-filesystem fences, and durable failures."""
import getpass,json,socket,tempfile
from pathlib import Path
import pytest
import cec_force_current as force
import cec_native_runtime as runtime
import typed_print_runtime as compatibility
import cec_chained_annotation_transition as chain
from test_chained_annotation_transition import env


def producer(p):
    return dict(ok=True,complete=True,source_and_producer_unchanged=True,
        command=['native',str(p)],source_files={str(p):force._hash(p)})


def board(root):
    p=root/'family'/'board.kicad_pcb';p.parent.mkdir();p.write_text('literal Source')
    return p


def lock(p,foreign=False):
    runtime.lock_path(p).write_text(json.dumps(dict(hostname='foreign'if foreign else socket.gethostname(),
        username=getpass.getuser())))


def test_facade_shares_implementation_and_live_private_registry():
    for name in ('observe','quarantine','before_native','_fenced_interval','_ACTIVE_FENCES','failure_evidence'):
        assert getattr(compatibility,name)is getattr(runtime,name)


@pytest.mark.parametrize('skew',[-120_000_000_000,120_000_000_000])
def test_chain_cross_filesystem_report_uses_adjacent_clock_fences(tmp_path,monkeypatch,skew):
    import cec_native_drc_runner as native
    original=runtime.time.time_ns
    monkeypatch.setattr(runtime.time,'time_ns',lambda:original()+skew)
    with tempfile.TemporaryDirectory(prefix='cec-runtime-test-',dir='/dev/shm')as directory:
        p=board(Path(directory));output=tmp_path/'report.json'
        assert p.parent.stat().st_dev!=tmp_path.stat().st_dev
        def run(source,report,**kwargs):
            assert kwargs['timeout_s']==10.
            lock(source);return producer(source)
        monkeypatch.setattr(native,'run',run)
        result=chain._native_map_ancestor(p,output,Path('/tool'),Path('/table'),10.)
        assert result['ok']and not runtime.lock_path(p).exists()
        evidence=tmp_path/'report-runtime-evidence'
        manifest=json.loads((tmp_path/'report-runtime-evidence.json').read_text())
        assert not Path(manifest['local_evidence_root']).exists()
        assert manifest['files_preserved_exactly']
        assert all(force._hash(evidence/name)==digest for name,digest in manifest['exact_file_sha256'].items())
        assert (tmp_path/'runtime-lock').read_bytes()==next((evidence/'runtime-artifacts').iterdir()).read_bytes()
        assert p.read_text()=='literal Source'


@pytest.mark.parametrize('fault',['failed','foreign_command','foreign_owner','source','sidecar','raised'])
def test_chain_failure_keeps_raw_producer_and_unowned_lock(tmp_path,monkeypatch,fault):
    import cec_native_drc_runner as native
    p=board(tmp_path);out=tmp_path/'evidence';out.mkdir();raw=[]
    def run(source,report,**kwargs):
        result=producer(source);raw.append(result);lock(source,fault=='foreign_owner')
        if fault=='failed':result['ok']=False
        if fault=='foreign_command':result['command']=['native','/different']
        if fault=='source':source.write_text('mutation')
        if fault=='sidecar':source.with_suffix('.kicad_prl').write_text('mutation')
        if fault=='raised':raise RuntimeError('actual producer crashed')
        return result
    monkeypatch.setattr(native,'run',run)
    with pytest.raises(ValueError)as caught:
        chain._native_map_ancestor(p,out/'report.json',Path('/tool'),Path('/table'),10.)
    diagnostic=caught.value.native_runtime_evidence
    assert diagnostic['raw_producer']==(None if fault=='raised'else raw[0])
    assert diagnostic['lock_inspection']['bytes_hex']==runtime.lock_path(p).read_bytes().hex()
    assert runtime.lock_path(p).exists()
    manifest=json.loads(Path(diagnostic['evidence_manifest']).read_text())
    assert manifest['failure_diagnostic']==diagnostic
    assert (Path(diagnostic['copied_evidence_root'])/'native-runtime-failure.json').is_file()


def test_preexisting_is_inspected_not_adopted_or_launched(tmp_path,monkeypatch):
    import cec_native_drc_runner as native
    p=board(tmp_path);lock(p);before=runtime.lock_path(p).read_bytes()
    monkeypatch.setattr(native,'run',lambda *a,**kw:pytest.fail('preexisting lock launched native'))
    with pytest.raises(ValueError,match='preexisting_map_ancestor_runtime_lock_refused')as caught:
        chain._native_map_ancestor(p,tmp_path/'report.json',Path('/tool'),Path('/table'),10.)
    assert caught.value.native_runtime_evidence['raw_producer']is None
    assert runtime.lock_path(p).read_bytes()==before


@pytest.mark.parametrize('row',[False,True])
def test_public_receivers_retain_failure_without_success(env,monkeypatch,row):
    diagnostic=dict(raw_producer={'ok':False,'actual':'producer'},runtime_fence={'nonce':'diagnostic'})
    def fail(*a,**kw):
        exc=ValueError('native refused');exc.native_runtime_evidence=diagnostic;raise exc
    monkeypatch.setattr(chain,'_origin_replay',fail)
    if row:
        declaration=dict(source=dict(path=str(env[0]),sha256=force._hash(env[0])),
            proposal=dict(path=str(env[3]),sha256=force._hash(env[3])))
        result=chain.receive_print_row(env[1],declaration,board_hint='renamed')
    else:result=chain.receive(env[1],env[2],env[5],board_hint='renamed')
    assert not result['ok']and not result['complete']and not result['admitted']
    assert result['native_runtime_failure']==diagnostic and result['error']=='native refused'

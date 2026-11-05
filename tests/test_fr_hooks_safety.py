"""Execute staged hook text with a fake subprocess: never starts a JVM."""
import ast,hashlib,json,re,sys,types
from pathlib import Path
import pytest

@pytest.fixture
def patched_fr(monkeypatch):
    import cec_fr
    source=Path(cec_fr.__file__).read_text();lines=source.splitlines(True)
    if '_transcript.capture_if_due(lambda:'in source:
        # After production integration, exercise the actual installed hook;
        # the staging-only patch artifact need not accompany production tests.
        module=types.ModuleType('_installed_fr_hooks_test');module.__file__=cec_fr.__file__
        monkeypatch.setitem(sys.modules,module.__name__,module)
        exec(compile(source,'installed-cec-fr-hooks.py','exec'),module.__dict__)
        module._staged_source=source;return module
    patch=(Path(__file__).parent/'cec-fr-hooks.patch').read_text().splitlines(True)
    hunks=[];i=0
    while i<len(patch):
        m=re.match(r'@@ -(\d+),\d+ \+\d+,\d+ @@',patch[i])
        if not m:i+=1;continue
        i+=1;old=[];new=[]
        while i<len(patch)and not patch[i].startswith('@@'):
            row=patch[i]
            if row.startswith((' ','-')):old.append(row[1:])
            if row.startswith((' ','+')):new.append(row[1:])
            i+=1
        hunks.append((int(m.group(1))-1,old,new))
    for start,old,new in reversed(hunks):
        assert lines[start:start+len(old)]==old
        lines[start:start+len(old)]=new
    text=''.join(lines);module=types.ModuleType('_staged_fr_hooks')
    module.__file__=cec_fr.__file__;monkeypatch.setitem(sys.modules,module.__name__,module)
    exec(compile(text,'staged-cec-fr-hooks.py','exec'),module.__dict__)
    module._staged_source=text
    return module

def test_actual_stream_hot_path_uses_lazy_throttled_capture(patched_fr):
    source=patched_fr._staged_source
    assert '_lines.append(_ln)\n                _transcript.capture_if_due(lambda: "".join(_lines), lambda: "")'in source
    assert '_lines.append(_ln)\n                _transcript.capture('not in source

def fake_run(monkeypatch,tmp_path,fr,*,broken_IO=False):
    import cec_fr_bounded_transcript as diagnostics
    monkeypatch.delenv('CEC_FR_PLATEAU_KILL',raising=False)
    monkeypatch.setenv('XDG_STATE_HOME',str(tmp_path/'durable'))
    scratch=tmp_path/'scratch';scratch.mkdir();fr._TMP=str(scratch)
    dsn=scratch/'input.dsn';dsn.write_text('(pcb p(structure))');jar=tmp_path/'jar';jar.write_bytes(b'JAR-identity')
    monkeypatch.setattr(fr,'_rest_base',lambda:None)
    monkeypatch.setattr(fr,'ensure_jar',lambda *a,**k:str(jar))
    monkeypatch.setattr(fr,'_fr_command',lambda *a,**k:['fake-java'])
    monkeypatch.setattr(fr,'_raise_on_fr_headless_exception',lambda *a,**k:None)
    ticks=iter((0.,0.,2.,2.,2.));fr.time=types.SimpleNamespace(monotonic=lambda:next(ticks,2.))
    killed=[]
    class Process:
        returncode=None
        def poll(self):return self.returncode
        def communicate(self,timeout):
            if self.returncode is not None:raise OSError('cleanup communicate failed')
            raise fr.subprocess.TimeoutExpired('fake-java',timeout,output=b'parser done\nCEC_PASS pass=1\n',stderr=b'partial error\n')
    process=Process();monkeypatch.setattr(fr.subprocess,'Popen',lambda *a,**k:process)
    def kill(p):killed.append(p);p.returncode=-9
    monkeypatch.setattr(fr,'_kill_fr_tree',kill)
    if broken_IO:
        original=diagnostics.Transcript
        class Broken(original):
            def capture(self,*args):
                self.calls=getattr(self,'calls',0)+1
                if self.calls>1:raise OSError('diagnostic IO failure')
                return super().capture(*args)
            def finish(self,*args,**kwargs):raise OSError('diagnostic IO failure')
        monkeypatch.setattr(diagnostics,'Transcript',Broken)
    with pytest.raises((RuntimeError,OSError)):
        fr.run_freerouting(str(dsn),str(scratch/'result.ses'),timeout=1,jar=str(jar))
    assert killed==[process] and process.poll()==-9
    assert not list(scratch.glob('cec_fr_run_*'))
    return tmp_path/'durable',jar

def test_timeout_partial_survives_failed_cleanup_and_default_workdir_cleanup(monkeypatch,tmp_path,patched_fr):
    durable,jar=fake_run(monkeypatch,tmp_path,patched_fr)
    manifest=next(durable.rglob('manifest.json'));r=json.loads(manifest.read_text())
    assert r['termination']=='timeout'
    assert r['context']['jar_sha256']==hashlib.sha256(jar.read_bytes()).hexdigest()
    assert (manifest.parent/'stdout.log').read_bytes().startswith(b'parser done')
    assert (manifest.parent/'stderr.log').read_bytes()==b'partial error\n'

def test_logging_IO_failure_cannot_bypass_real_hook_process_cleanup(monkeypatch,tmp_path,patched_fr):
    fake_run(monkeypatch,tmp_path,patched_fr,broken_IO=True)

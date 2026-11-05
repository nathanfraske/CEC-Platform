"""Durable bounded cumulative subprocess output; no routing/admission change."""
import json,os,time,uuid
from pathlib import Path

class Transcript:
    def __init__(self,directory=None,*,max_bytes=2*1024*1024,context=None):
        if type(max_bytes)is not int or not 4096<=max_bytes<=8*1024*1024:raise ValueError('bounded_transcript_limit_required')
        if directory is None:
            # Never default to a DSN/workdir that the router itself deletes.
            state=os.environ.get('XDG_STATE_HOME')
            directory=(Path(state)if state else Path.home()/'.local/state')/'cec/freerouting-diagnostics'
        parent=Path(directory)
        if parent.is_symlink():raise ValueError('diagnostics_parent_alias_refused')
        parent.mkdir(parents=True,exist_ok=True)
        self.directory=parent/('attempt-'+uuid.uuid4().hex);self.directory.mkdir(exist_ok=False)
        self.limit=max_bytes;self.context=context or {};self.counts={};self.paths={};self.termination='running'
        self._last_capture=time.monotonic();self.capture('','')

    def capture(self,stdout,stderr):
        for name,value in (('stdout',stdout),('stderr',stderr)):
            # A cleanup communicate() failure must not erase an earlier
            # TimeoutExpired partial buffer. None means no newer evidence.
            if value is None:continue
            data=(value or b'') if isinstance(value,(bytes,type(None))) else value.encode('utf-8',errors='replace')
            self.counts[name]=len(data);head=self.limit//4
            marker=b'\n[CEC output truncated: middle omitted]\n'
            tail=self.limit-head-len(marker)
            kept=data if len(data)<=self.limit else data[:head]+marker+data[-tail:]
            path=self.directory/(name+'.log');path.write_bytes(kept);self.paths[name]=str(path)
        self.flush()
        self._last_capture=time.monotonic()

    def capture_if_due(self,stdout_provider,stderr_provider):
        # Providers prevent even the cumulative join until the 1Hz gate opens.
        if time.monotonic()-self._last_capture<1.0:return False
        self.capture(stdout_provider(),stderr_provider());return True

    def finish(self,termination,*,returncode=None):
        if termination not in ('completed','timeout','exception','plateau_kill'):raise ValueError('explicit_transcript_termination_required')
        self.termination=termination;self.returncode=returncode;self.flush()

    def flush(self):
        receipt=dict(scope='diagnostics_only_not_partial_SES_or_admission',termination=self.termination,
            output_bytes_observed=self.counts,per_stream_payload_limit_bytes=self.limit,paths=self.paths,
            context=self.context,returncode=getattr(self,'returncode',None),strict_SES_receiving_required=True)
        (self.directory/'manifest.json').write_text(json.dumps(receipt,indent=2,default=str))

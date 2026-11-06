"""One bounded source-owned cell compile, with no saved product-board edits."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
WORK=Path(__file__).resolve().parent
SOURCE=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
SOURCE_SHA='4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310'
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]


def worker():
    from cec_pipeline.native import _native
    from cec_pipeline import cells
    import cec_cell_macro_requests as compiler
    import cec_force_current as force
    p,_=_native()
    source,expected=SOURCE,SOURCE_SHA
    if '--repaired'in sys.argv:
        record=json.loads((WORK/'port-repaired-v1'/'construction.json').read_text())
        assert json.loads((WORK/'port-repaired-v1'/'barrel.json').read_text())['ok']
        assert json.loads((WORK/'port-repaired-v1'/'drc-candidate.json').read_text())['ok']
        source,expected=Path(record['candidate']),record['candidate_sha256']
    assert force._hash(source)==expected
    b=p.LoadBoard(str(source));refs={'U6','C9','C27','R54','C54','C55','C51'}
    mode=sys.argv[-1]
    if mode=='six':refs.remove('C55')
    elif mode=='five':refs-={'C55','C51'}
    else:assert mode=='seven'
    fps={fp.GetReference():fp for fp in b.GetFootprints()}
    tracks={force._uid(t):t for t in b.GetTracks()}
    dx=2000000 if '--half-shift'in sys.argv else 4000000
    op=dict(kind='place_cell',native_macro=True,
        allow_linear_power_stage_reconstruction=True,
        poses=[dict(reference=r,at_nm=[fps[r].GetPosition().x+dx,fps[r].GetPosition().y],
                    rotation_deg=round(fps[r].GetOrientationDegrees())%360)for r in sorted(refs)],
        allow_locked_footprint_uuids=[force._uid(fps[r])for r in refs if fps[r].IsLocked()],
        allow_locked_track_uuids=[],allow_locked_transport_uuids=[],reference_group_uuids=[],
        routes=[],vias=[],max_shift_nm=dx)
    result=dict(source=str(source.relative_to(ROOT)),source_sha256=expected,mode=mode,
        operation=op,board_saved=False,accepted=False)
    start=time.monotonic()
    watched={('cec_programming_resistor_placement','plan'),('cec_source_linear_power_stage','collect'),
        ('cec_additional_aggregate_macro','collect'),('cec_cell_escape_replan','_prepare_source'),
        ('cec_cell_row_rebuild','plan'),('cec_decoupler_constraints','_device_bypass_assignment'),
        ('cec_retained_bypass_contact_frame','plan'),('cec_source_ground_leaf','plan')}
    def profile(frame,event,arg):
        key=(frame.f_globals.get('__name__'),frame.f_code.co_name)
        if event in('call','return')and key in watched:
            print('CEC_STEP='+json.dumps(dict(module=key[0],function=key[1],event=event,
                elapsed_s=time.monotonic()-start)),flush=True)
    try:
        if '--profile'in sys.argv:sys.setprofile(profile)
        with compiler.observe_compilation_phases(lambda event:
                print('CEC_PHASE='+json.dumps(event),flush=True)):
            projected,packet,transported=cells.compile_macro(b,op,'atx-24pin-rev3',enforce_locks=False)
        op['allow_locked_track_uuids']=[u for u in packet['retired_track_uuids']if tracks[u].IsLocked()]
        op['allow_locked_transport_uuids']=[u for u in transported if tracks[u].IsLocked()]
        result.update(status='source_compiled',packet=packet,transported=transported)
    except Exception as exc:
        result.update(status='compile_refused',error_type=type(exc).__name__,error=str(exc),
            traceback=traceback.format_exc())
    finally:
        sys.setprofile(None)
    assert force._hash(source)==expected
    result['elapsed_s']=time.monotonic()-start
    print('CEC_RESULT='+json.dumps(result,separators=(',',':')))


def bounded_compile(command):
    """Hard ten-second process deadline per existing ordered compiler phase.

    A valid new phase starts a new lease; chatter and repeated phase starts
    never extend one. No native call is interrupted by a Python signal handler.
    """
    phases=('source_ownership','native_frame_and_cuts','canonical_boundary_ownership',
        'canonical_ground_multiport_boundary','canonical_boundary_composition',
        'complete_endpoint_obligations','independent_ground_endpoint_obligations',
        'complete_component_inventory')
    child=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        start_new_session=True)
    selector=selectors.DefaultSelector();selector.register(child.stdout,selectors.EVENT_READ)
    chunks=[];pending=b'';index=-1;closed=True;deadline=time.monotonic()+10;absolute=deadline+90
    reason=None
    try:
        while True:
            remaining=min(deadline,absolute)-time.monotonic()
            if remaining<=0:
                reason='ten_second_ordered_phase_deadline';break
            ready=selector.select(remaining)
            if not ready:continue
            data=os.read(child.stdout.fileno(),65536)
            if not data:break
            chunks.append(data);pending+=data
            while b'\n'in pending:
                line,pending=pending.split(b'\n',1)
                if not line.startswith(b'CEC_PHASE='):continue
                event=json.loads(line.split(b'=',1)[1])
                n=event['index']
                if event['event']=='start':
                    if not closed or n!=index+1 or n>=len(phases) or event['phase']!=phases[n]:
                        raise ValueError('invalid_ordered_native_phase')
                    supplied=event['deadline_monotonic']
                    if not time.monotonic()<supplied<=time.monotonic()+10:
                        raise ValueError('invalid_native_phase_deadline')
                    index=n;closed=False;deadline=supplied
                elif event['event']=='finish':
                    if closed or n!=index or event['phase']!=phases[index]:
                        raise ValueError('invalid_native_phase_finish')
                    closed=True
                    if n==len(phases)-1:deadline=time.monotonic()+10
                else:raise ValueError('unknown_native_phase_event')
                print(line.decode(),flush=True)
        if reason:
            os.killpg(child.pid,signal.SIGKILL)
        child.wait(timeout=max(.001,min(10.,absolute-time.monotonic())))
    finally:
        if child.poll()is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
        selector.close();child.stdout.close()
    return child.returncode,b''.join(chunks).decode(errors='replace'),reason


def main():
    mode=sys.argv[1]if len(sys.argv)>1 else 'seven'
    assert mode in('five','six','seven')
    profiling='--profile'in sys.argv
    repaired='--repaired'in sys.argv
    half='--half-shift'in sys.argv
    try:
        code,output,reason=bounded_compile([sys.executable,str(Path(__file__).resolve()),'--worker',
            *(['--profile']if profiling else []),*(['--repaired']if repaired else []),
            *(['--half-shift']if half else []),mode])
        lines=[v.removeprefix('CEC_RESULT=')for v in output.splitlines()if v.startswith('CEC_RESULT=')]
        events=[json.loads(v.split('=',1)[1])for v in output.splitlines()
            if v.startswith(('CEC_STEP=','CEC_PHASE='))]
        if code or len(lines)!=1:
            report=dict(status='bounded_worker_timeout'if reason else 'worker_failed',exit_code=code,
                reason=reason,diagnostic_output=output[-8000:],board_saved=False,accepted=False,events=events)
        else:
            report=json.loads(lines[0])
            report['events']=events
    except subprocess.TimeoutExpired as exc:
        output=exc.stdout.decode(errors='replace')if isinstance(exc.stdout,bytes)else(exc.stdout or '')
        stderr=exc.stderr.decode(errors='replace')if isinstance(exc.stderr,bytes)else(exc.stderr or '')
        phases=[json.loads(line.split('=',1)[1])for line in output.splitlines()if line.startswith(('CEC_PHASE=','CEC_STEP='))]
        report=dict(status='bounded_worker_timeout',worker_limit_s=10,board_saved=False,accepted=False,
            observed_phases=phases,native_stack_sample=stderr[-10000:])
    report['python_profiling_enabled']=profiling
    (WORK/('compile-'+mode+('-repaired'if repaired else '')+('-2mm'if half else '')+('-profile'if profiling else '')+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k not in('packet','operation','traceback')},indent=2))


if __name__=='__main__':
    worker()if '--worker'in sys.argv else main()

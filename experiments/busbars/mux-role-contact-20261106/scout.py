"""Compile one current-source seven-part cohort; no product-board edits."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
WORK=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
SOURCE=ROOT/'experiments/busbars/mux-reconstruction-20261106/output-prefix-v1/candidate/board.kicad_pcb'
SHA='c4c92165a0e8efec60458b91af80807233033bb5668ade92f171cdacb4ce0b88'


def study_path():
    choices=[arg.split('=',1)[1]for arg in sys.argv if arg.startswith('--study=')]
    assert len(choices)<=1
    name=choices[0]if choices else'geometry.json'
    assert Path(name).name==name and name.endswith('.json')
    return WORK/name


def worker():
    import pcbnew
    import cec_force_current as force
    import cec_cell_macro_requests as compiler
    from cec_pipeline import cells
    assert force._hash(SOURCE)==SHA
    study_file=study_path();study=json.loads(study_file.read_text())
    assert study['source_sha256']==SHA and study['paired_ok'] and not study['same_face_courtyard_collisions']
    board=pcbnew.LoadBoard(str(SOURCE));poses=study['proposed_poses']
    fps={fp.GetReference():fp for fp in board.GetFootprints()}
    operation=dict(kind='place_cell',native_macro=True,allow_linear_power_stage_reconstruction=True,
        poses=[dict(reference=r,at_nm=v[:2],rotation_deg=round(v[2])%360)for r,v in sorted(poses.items())],
        allow_locked_footprint_uuids=[force._uid(fps[r])for r in poses if fps[r].IsLocked()],
        allow_locked_track_uuids=[],allow_locked_transport_uuids=[],reference_group_uuids=[],
        routes=[],vias=[],max_shift_nm=6000000,
        max_source_boundary_span_nm=12000000)
    result=dict(source=str(SOURCE),source_sha256=SHA,study_file=str(study_file),study_sha256=force._hash(study_file),
        code_identity=force._code_identity(),operation=operation,board_saved=False,accepted=False)
    start=time.monotonic()
    try:
        with compiler.observe_compilation_phases(lambda e:print('CEC_PHASE='+json.dumps(e),flush=True)):
            if '--stationary-ground'in sys.argv:
                options=dict(board_hint='atx-24pin-rev3',max_shift_mm=6.,timeout_s=10.,
                    allow_owned_locked_escapes=True,max_obstacle_track_mm=12.,
                    compilation_phase_timeouts_s=[10.]*9,allow_linear_power_stage_reconstruction=True,
                    stationary_ground_barrel_uuids=['8fcb6331-0f3f-403a-ba73-e7a6da00710b'])
                result['explicit_direct_compiler_options']=options
                _,packet=compiler.compile(SOURCE,cells.normalize_poses(operation['poses']),**options)
                transported=None
            else:
                _,packet,transported=cells.compile_macro(board,operation,'atx-24pin-rev3',enforce_locks=False)
        result.update(status='source_compiled',packet=packet,transported=transported)
    except Exception as exc:
        result.update(status='compile_refused',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
        # Read-only fault evidence, never a recovered construction packet.
        for frame,_line in traceback.walk_tb(exc.__traceback__):
            if frame.f_code.co_name=='compose_rated_leaves':
                first=frame.f_locals.get('leaf');last=frame.f_locals.get('fresh')
                if isinstance(first,dict)and isinstance(last,dict):
                    result['rated_leaf_replay_differences']={k:dict(original=first.get(k),rederived=last.get(k))
                        for k in sorted(first.keys()|last.keys())if first.get(k)!=last.get(k)}
    assert force._hash(SOURCE)==SHA
    result['elapsed_s']=time.monotonic()-start
    print('CEC_RESULT='+json.dumps(result,separators=(',',':')))


def main():
    import cec_cell_macro_requests as compiler
    revision=sys.argv[1]
    assert revision and len(revision)<=32 and all(c.isalnum()or c in '-_'for c in revision)
    target=WORK/('compile-'+revision+'.json');assert not target.exists()
    path=ROOT/'experiments/busbars/coherent-mux-20261106/scout.py'
    spec=importlib.util.spec_from_file_location('ordered_watchdog',path)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    args=['--stationary-ground']if '--stationary-ground'in sys.argv else []
    args.extend(arg for arg in sys.argv if arg.startswith('--study='))
    code,output,reason=runner.bounded_compile([sys.executable,str(Path(__file__).resolve()),'--worker',*args],
        phases=compiler.compilation_phases([10.]*9))
    lines=[v.split('=',1)[1]for v in output.splitlines()if v.startswith('CEC_RESULT=')]
    report=json.loads(lines[0])if code==0 and len(lines)==1 else dict(status='worker_timeout'if reason else 'worker_failed',
        reason=reason,exit_code=code,diagnostic_output=output[-12000:],board_saved=False,accepted=False)
    report['events']=[json.loads(v.split('=',1)[1])for v in output.splitlines()if v.startswith('CEC_PHASE=')]
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k not in('packet','operation','code_identity')},indent=2))


if __name__=='__main__':worker()if '--worker'in sys.argv else main()

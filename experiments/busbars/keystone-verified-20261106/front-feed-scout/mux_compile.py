import sys,json,time,traceback
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
from cec_pipeline import cells
import cec_force_current as force
p,_=_native();source=ROOT/'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb'
b=p.LoadBoard(str(source));refs={'U6','C9','C27','R54','C54','C55','C51'};fps={fp.GetReference():fp for fp in b.GetFootprints()};items={force._uid(t):t for t in b.GetTracks()}
op=dict(kind='place_cell',native_macro=True,poses={r:[fps[r].GetPosition().x/1e6+4,fps[r].GetPosition().y/1e6,fps[r].GetOrientationDegrees()]for r in refs},allow_locked_footprint_uuids=[force._uid(fps[r])for r in refs if fps[r].IsLocked()],allow_locked_track_uuids=[],allow_locked_transport_uuids=[],reference_group_uuids=[],routes=[],vias=[],max_shift_nm=4000000)
op['poses']=[dict(reference=r,at_nm=[fps[r].GetPosition().x+4000000,fps[r].GetPosition().y],rotation_deg=round(fps[r].GetOrientationDegrees())%360)for r in sorted(refs)]
out=Path(__file__).parent/'mux-compile.json'
out.write_text(json.dumps(dict(status='started',operation=op,source_sha256=force._hash(source)),indent=2)+'\n')
started=time.monotonic()
try:
 frame,packet,transported=cells.compile_macro(b,op,'atx-24pin-rev3',enforce_locks=False)
 op['allow_locked_track_uuids']=[u for u in packet['retired_track_uuids']if items[u].IsLocked()]
 op['allow_locked_transport_uuids']=[u for u in transported if items[u].IsLocked()]
 out.write_text(json.dumps(dict(status='source_compiled_lock_permissions_derived',elapsed_s=time.monotonic()-started,operation=op,packet=packet,transported=transported,board_saved=False,accepted=False),indent=2)+'\n')
 print(json.dumps(dict(status='source_compiled_lock_permissions_derived',retired=len(packet['retired_track_uuids']),transported=len(transported),requests=len(packet['requests']),elapsed_s=time.monotonic()-started)))
except Exception as e:
 out.write_text(json.dumps(dict(status='compile_refused',error_type=type(e).__name__,error=str(e),traceback=traceback.format_exc(),elapsed_s=time.monotonic()-started,operation=op,board_saved=False),indent=2)+'\n');print(traceback.format_exc())

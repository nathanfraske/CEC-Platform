"""Native-derived no-cut boundary parity; no new poses or placement claims."""
import sys,json,time,copy
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import cec_swig_guard,pcbnew
cec_swig_guard.pin()
import cec_force_current as force,cec_cell_row_rebuild as row
import cec_macro_boundary_composition as composition
WORK=Path(__file__).parent
prior=ROOT/'experiments/repack/bar-corridor-20261106/cross-board-replay.json'
review=json.loads(prior.read_text());prior_hash=force._hash(prior);records=[]
for entry in review['rows']:
 folder=ROOT/'checkpoints/review-20261105-outline-compaction/boards'/entry['board']
 source=folder/'board.kicad_pcb'
 if not source.exists():
  files=list(folder.glob('*-board.kicad_pcb'));assert len(files)==1;source=files[0]
 assert force._hash(source)==entry['source_sha256']
 board=pcbnew.LoadBoard(str(source));binding=row._source_binding(board)
 tracks=sorted((t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK'and 0<t.GetWidth()<=350000),key=force._uid)
 plan=dict(scope='source_typed_complete_cell_escape_proposal',source_native_binding=binding,board_hint=entry['board'],retired_track_uuids=[],poses={},device_contracts={})
 count=0;batches=0;start=time.monotonic()
 for offset in range(0,len(tracks),64):
  assert time.monotonic()-start<10.,'per_board_noop_replay_deadline'
  requests={'boundary:'+force._uid(t):dict(kind='source_boundary',net=str(t.GetNetname()),width_nm=int(t.GetWidth()),a=dict(at_nm=list(t.GetStart()),layers=[int(t.GetLayer())]),b=dict(at_nm=list(t.GetEnd()),layers=[int(t.GetLayer())]))for t in tracks[offset:offset+64]}
  before=copy.deepcopy(requests)
  result,extras,proofs=composition.compose(board,source,plan,requests,[],deadline=time.monotonic()+min(2.,10.-(time.monotonic()-start)))
  assert result==before and requests==before and not extras and not proofs
  count+=len(requests);batches+=1
 assert force._hash(source)==entry['source_sha256']and row._source_binding(board)==binding
 record=dict(board=entry['board'],source_sha256=entry['source_sha256'],native_thin_track_boundaries=count,batches=batches,exact_no_cut_packet_parity=True,no_authority_or_additional_cuts=True,source_file_and_RAM_unchanged=True,elapsed_s=time.monotonic()-start)
 records.append(record);print(json.dumps(record),flush=True)
assert force._hash(prior)==prior_hash
result=dict(schema=1,scope='NO_CUT_NATIVE_DERIVED_BOUNDARY_PACKET_IDENTITY_ONLY_NOT_ROLE_PLACEMENT_OR_ROUTING_RECEIVING',historical_role_receipt=dict(path=str(prior),sha256=prior_hash,preserved=True),code=dict(path=str(ROOT/'scripts/cec_macro_boundary_composition.py'),sha256=force._hash(ROOT/'scripts/cec_macro_boundary_composition.py')),rows=records,boards=len(records),native_boundaries=sum(r['native_thin_track_boundaries']for r in records),limitations='These packets use literal native endpoints/layers/widths with an EMPTY retired set and no poses. This proves inert behavior when no Source base pair is owned; it does not recompile placements or qualify new ordinary cuts. Positive programming-node rotation/face/contact preservation is separately exercised by existing synthetic tests.',source_boards_or_selector_modified=False)
(WORK/'composition-source-noop-receipt.json').write_text(json.dumps(result,indent=2)+'\n')

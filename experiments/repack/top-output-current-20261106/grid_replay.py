"""Read-only exact-row compatibility replay on nine reviewed native boards."""
from pathlib import Path
import subprocess
import time
import types
from cec_pipeline.native import _native
import cec_pad_bank_collector as new
import cec_force_current as force
import cec_suite_inspection as inspect
import cec_native_drc_runner as native


def main():
    pcb,quiet = _native()
    old = types.ModuleType('source_pad_bank_before_grid')
    exec(subprocess.check_output(['git','show','00a586c2:scripts/cec_pad_bank_collector.py'],text=True),old.__dict__)
    root = Path('checkpoints/review-20261105-outline-compaction/boards')
    rows=[]
    for parent in sorted(root.iterdir()):
        path=parent/'board.kicad_pcb'
        if not path.exists():
            candidates=list(parent.glob('*-board.kicad_pcb'))
            assert len(candidates)==1, parent
            path=candidates[0]
        source_hash=force._hash(path);board=pcb.LoadBoard(str(path));count=grids=0
        for fp in board.GetFootprints():
            nets={str(p.GetNetname()) for p in fp.Pads() if str(p.GetNetname())}
            for net in sorted(nets):
                pads=[p for p in fp.Pads() if p.GetNetname()==net and p.IsOnLayer(pcb.F_Cu)]
                if not 2<=len(pads)<=32 or net.rsplit('/',1)[-1]=='GND':continue
                centres=[tuple(p.GetPosition()) for p in pads];xs={p[0] for p in centres};ys={p[1] for p in centres}
                if len(set(centres))!=len(centres) or set(centres)!={(x,y)for x in xs for y in ys}:continue
                ids=[force._uid(p) for p in pads];policy=dict(grid_nm=1000,margin_nm=1000,chamfer_nm=250000)
                try:after=new._geometry(board,ids,[],pcb.F_Cu,policy,time.monotonic()+5.)
                except new.Refused:continue
                if len(xs)>1 and len(ys)>1:
                    try:old._geometry(board,ids,[],pcb.F_Cu,policy,time.monotonic()+5.)
                    except old.Refused:grids+=1
                    else:raise AssertionError('previously_accepted_nonrow_unexpected')
                else:
                    before=old._geometry(board,ids,[],pcb.F_Cu,policy,time.monotonic()+5.)
                    assert [before[i] for i in(0,1,2,4,5)]==[after[i] for i in(0,1,2,4,5)]
                    count+=1
        assert force._hash(path)==source_hash
        rows.append(dict(board=parent.name,source_sha256=source_hash,unchanged_exact_rows=count,
            complete_grids_newly_supported=grids,source_unchanged=True))
    assert len(rows)==9 and sum(r['unchanged_exact_rows']for r in rows)>0
    inspect.write_json('docs/evidence/20261105-bottom-compaction/pad-grid-cross-board.json',dict(
        schema=1,ok=True,scope='source_geometry_replay_not_full_pipeline_or_capacity_qualification',
        old_code_commit='00a586c2',rows=rows,original_rows_exactly_unchanged=True,board_mutated=False))
    print(rows,flush=True)
    pcie=root/'pcie-8pin-2port/board.kicad_pcb'
    r=native.run(pcie,Path('docs/evidence/20261105-bottom-compaction/pcie2-grid-regression-drc.json'),
        reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',timeout_s=10.,
        footprint_table=str(pcie.parent/'library/fp-lib-table'))
    inspect.write_json('docs/evidence/20261105-bottom-compaction/pcie2-grid-regression-drc.runner.json',r)
    print('pcie_native_production',r['ok'],r['complete'],r.get('errors'))


if __name__=='__main__':main()

"""Read-only old-role parity and complete-pair compilation on reviewed boards."""
from pathlib import Path
import json
import subprocess
import types
from cec_pipeline.native import _native
pcb,quiet=_native()
import cec_programming_resistor_placement as new
import cec_force_current as force
import cec_native_drc_runner as drc

OUT=Path(__file__).resolve().parent

def main():
    old=types.ModuleType('before_pair_role')
    old.__file__=new.__file__
    exec(subprocess.check_output(['git','show','c1fa80b4:scripts/cec_programming_resistor_placement.py'],text=True),old.__dict__)
    rows=[]
    for folder in sorted(Path('checkpoints/review-20261105-outline-compaction/boards').iterdir()):
        path=folder/'board.kicad_pcb'
        if not path.exists():
            candidates=list(folder.glob('*-board.kicad_pcb'));assert len(candidates)==1
            path=candidates[0]
        sha=force._hash(path);b=pcb.LoadBoard(str(path));chosen=None
        for owner in sorted(b.GetFootprints(),key=lambda f:f.GetReference()):
            if new.manufacturer_contract(owner)is None:continue
            for pin in('4','5','6'):
                control=owner.FindPadByNumber(pin)
                node=[p for f in b.GetFootprints()for p in f.Pads()if p.GetNetCode()==control.GetNetCode()]
                lower=[p.GetParentFootprint()for p in node if p.GetParentFootprint()!=owner and
                    len(list(p.GetParentFootprint().Pads()))==2 and any(q.GetNetname()=='GND'for q in p.GetParentFootprint().Pads())]
                if len(node)!=3 or len(lower)!=1:continue
                upper=[p.GetParentFootprint()for p in node if p.GetParentFootprint()not in(owner,lower[0])]
                if len(upper)==1:chosen=(lower[0],upper[0]);break
            if chosen:break
        record=dict(board=folder.name,source_sha256=sha,source_unchanged=True)
        if chosen:
            low,up=chosen
            pose=lambda fp:[fp.GetPosition().x/1e6+.25,fp.GetPosition().y/1e6,(fp.GetOrientationDegrees()+90)%360]
            poses={low.GetReference():pose(low)}
            groups=[force._uid(g)for g in b.Groups()if any(g.ContainsItem(f)for f in chosen)]
            try:
                args=dict(board_hint=folder.name,reference_group_uuids=[force._uid(g)for g in b.Groups()if g.ContainsItem(low)])
                before=old.plan(b,poses,**args);after=new.plan(b,poses,**args)
                assert before==after
                if after:
                    poses[up.GetReference()]=pose(up)
                    args['reference_group_uuids']=groups
                    pair=new.plan(b,poses,**args)
                    assert new.participant_refs(pair)==set(poses)
                    record.update(lower_only_exact_parity=True,pair_compiled=True,refs=sorted(poses),routing_or_placement_accepted=False)
                else:record.update(lower_only_exact_parity=True,positive_role_present=False)
            except ValueError as exc:record.update(pair_compiled=False,refusal=str(exc),routing_or_placement_accepted=False)
        else:record.update(applicable_pair=False)
        assert force._hash(path)==sha
        rows.append(record);print(json.dumps(record),flush=True)
    assert len(rows)==9
    (OUT/'cross-board-replay.json').write_text(json.dumps(dict(rows=rows,source_boards_mutated=False,
        scope='role compilation only; not placement, routing, current or fab qualification'),indent=2)+'\n')
    pcie=Path('checkpoints/review-20261105-outline-compaction/boards/pcie-8pin-2port/board.kicad_pcb')
    receipt=drc.run(pcie,OUT/'pcie2-drc.json',reporting_build='/home/codex/.cache/cec/native-drc-10.0.5',
        timeout_s=10.,footprint_table=str(pcie.parent/'library/fp-lib-table'))
    (OUT/'pcie2-drc.runner.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(native_produced=receipt['ok'],complete=receipt['complete'],errors=receipt.get('errors'))))

if __name__=='__main__':main()

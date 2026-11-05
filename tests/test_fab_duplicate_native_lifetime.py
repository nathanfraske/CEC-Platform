"""Loaded exact-duplicate cleanup preserves copper width and native ownership."""
from pathlib import Path
import subprocess
import sys

import pytest


NATIVE = r'''
import gc,hashlib,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import pcbnew
import cec_fab_repair as repair
import cec_native_items
root=Path(sys.argv[2]);mode=sys.argv[3]
board=pcbnew.CreateEmptyBoard()
net=pcbnew.NETINFO_ITEM(board,'renamed_net');board.Add(net)
rows=[]
for index,width in enumerate((.2,.5) if mode in ('different-width','legacy-width') else (.2,.2)):
    track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(8,10));track.SetEnd(pcbnew.VECTOR2I_MM(8,15))
    track.SetWidth(pcbnew.FromMM(width));track.SetLayer(pcbnew.B_Cu);track.SetNet(net)
    track.SetLocked(index==0);board.Add(track);rows.append(track)
kept=rows[0].m_Uuid.AsString();removed=rows[1].m_Uuid.AsString()
group=pcbnew.PCB_GROUP(board);group.SetName('test-owned');board.Add(group)
group.AddItem(rows[1])
source=root/'source.kicad_pcb';target=root/'out.kicad_pcb'
pcbnew.SaveBoard(str(source),board,True)
original=hashlib.sha256(source.read_bytes()).hexdigest()
if mode=='legacy-width':
    # Reproduce the old width-blind survivor rule itself. Merely changing its
    # grouping key no longer bypasses the independent widest-survivor guard.
    def legacy_width_blind_cleanup(b,**kwargs):
        seen={}
        for t in sorted(b.GetTracks(),key=lambda t:not t.IsLocked()):
            s,e=t.GetStart(),t.GetEnd()
            key=tuple(sorted(((s.x,s.y),(e.x,e.y))))+(t.GetLayer(),t.GetNetname())
            if key in seen:
                return cec_native_items.discard_items(b,[t])
            seen[key]=t
        return 0
    repair.repair_backtracks=legacy_width_blind_cleanup
if mode=='legacy-detach':
    def detach(b,items):
        for item in items:
            for g in b.Groups():
                if g.ContainsItem(item):g.RemoveItem(item)
            b.Remove(item)
        return len(items)
    cec_native_items.discard_items=detach

def run():
    loaded=pcbnew.LoadBoard(str(source))
    before={t.m_Uuid.AsString():t.GetWidth() for t in loaded.GetTracks()}
    count=repair.repair_backtracks(loaded,allow_grouped_track_uuids=[removed])
    after={t.m_Uuid.AsString():t.GetWidth() for t in loaded.GetTracks()}
    if mode in ('different-width','legacy-width'):
        assert count==0 and before==after,'different-width copper was deleted'
    else:
        assert count==1 and set(after)=={kept}
        assert all(i.m_Uuid.AsString()!=removed for g in loaded.Groups() for i in g.GetItems())
    # A second cleanup, save, reload and normal interpreter exit must all work.
    assert repair.repair_backtracks(loaded)==0
    pcbnew.SaveBoard(str(target),loaded,True)
    saved=pcbnew.LoadBoard(str(target))
    assert {t.m_Uuid.AsString():t.GetWidth() for t in saved.GetTracks()}==after

run();gc.collect()
capsule=sys.modules['swig_runtime_data4'].type_pointer_capsule
for _ in range(8):
    before=sys.getrefcount(capsule);run();gc.collect()
    assert sys.getrefcount(capsule)==before,'borrowed registry imbalance'
assert hashlib.sha256(source.read_bytes()).hexdigest()==original
'''


@pytest.mark.parametrize('mode',['equal-width','different-width','legacy-detach','legacy-width'])
def test_loaded_cleanup_and_legacy_negative_control(tmp_path,mode):
    result=subprocess.run([sys.executable,'-X','faulthandler','-c',NATIVE,
        str(Path(__file__).resolve().parents[1]/'scripts'),str(tmp_path),mode],
        capture_output=True,text=True,timeout=10)
    if mode=='legacy-detach':
        assert result.returncode!=0
        assert 'borrowed registry imbalance' in result.stderr,result.stderr[-3000:]
    elif mode=='legacy-width':
        assert result.returncode!=0
        assert 'different-width copper was deleted' in result.stderr,result.stderr[-3000:]
    else:
        assert result.returncode==0,result.stderr[-3000:]

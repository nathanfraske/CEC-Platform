"""The native blank-project factory must never unload a live saved project."""
import json
import subprocess
import sys

import pcbnew
import pytest

from cec_native_items import create_empty_board


_ISOLATED_WITNESS = r'''
import hashlib,json,os,sys,tempfile
from pathlib import Path
import pcbnew
from cec_native_items import create_empty_board

with tempfile.TemporaryDirectory(prefix='cec-empty-board-lifetime-') as root:
    root=Path(root)
    # SaveBoard renames this actual blank project; retaining its BOARD proxy
    # does not stop KiCad's manager from deleting a DIFFERENT saved project.
    default_owner=pcbnew.BOARD()
    seed=pcbnew.BOARD()
    seed.SetCopperLayerCount(6)
    settings=seed.GetDesignSettings();nets=settings.m_NetSettings
    default=nets.GetDefaultNetclass()
    default.SetTrackWidth(470000);default.SetClearance(230000)
    default.SetViaDiameter(700000);default.SetViaDrill(300000)
    for a,b in (((0,0),(10,0)),((10,0),(10,8)),((10,8),(0,8)),((0,8),(0,0))):
        edge=pcbnew.PCB_SHAPE(seed);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetWidth(100000)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));seed.Add(edge)
    seed_path=root/'z-seed.kicad_pcb'
    assert pcbnew.SaveBoard(str(seed_path),seed)
    source=root/'a-saved.kicad_pcb'
    source.write_bytes(seed_path.read_bytes())
    source.with_suffix('.kicad_pro').write_bytes(seed_path.with_suffix('.kicad_pro').read_bytes())
    files=(source,source.with_suffix('.kicad_pro'))
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    parent=pcbnew.LoadBoard(str(source));second=pcbnew.LoadBoard(str(source))
    manager=pcbnew.GetSettingsManager();project_path=str(source.with_suffix('.kicad_pro'))
    assert manager.GetProject(project_path) is not None
    assert manager.GetProject('') is None
    safe=sys.argv[1]=='safe'
    scratch=create_empty_board() if safe else pcbnew.BOARD()
    registered=manager.GetProject(project_path) is not None
    report=dict(safe=safe,source_registered_after=registered,
        files_unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==hashes[str(p)] for p in files),
        native_bbox_checked=False)
    if safe:
        assert registered
        assert int(parent.GetProject())==int(manager.GetProject(project_path))
        assert int(second.GetProject())==int(parent.GetProject())
        actual_settings=parent.GetDesignSettings();actual_nets=actual_settings.m_NetSettings
        actual=actual_nets.GetDefaultNetclass()
        report['saved_rules_nm']=[actual.GetTrackWidth(),actual.GetClearance(),
            actual.GetViaDiameter(),actual.GetViaDrill()]
        bounds=parent.GetBoardEdgesBoundingBox()
        report['native_bbox_nm']=[bounds.GetWidth(),bounds.GetHeight()]
        report['native_bbox_checked']=True
        # Further safe factory calls do not activate or replace the Source.
        again=create_empty_board()
        assert int(manager.GetProject(project_path))==int(parent.GetProject())
    else:
        # Do not call GetVisibleLayers/BBox or any virtual method through the
        # now-dangling Source PROJECT. The manager's absence proves the cut.
        assert not registered
print(json.dumps(report,sort_keys=True),flush=True)
# Exit only after the synthetic family has been cleaned, without invoking
# destructors through the intentionally invalid Source of the negative case.
os._exit(0)
'''


@pytest.mark.parametrize('mode',['unsafe','safe'])
def test_saved_project_survives_only_nonactivating_empty_factory(mode):
    result=subprocess.run([sys.executable,'-c',_ISOLATED_WITNESS,mode],
        capture_output=True,text=True,timeout=10.)
    assert result.returncode==0,(result.returncode,result.stdout,result.stderr)
    report=json.loads(result.stdout.splitlines()[-1])
    assert report['files_unchanged']
    assert report['source_registered_after']==(mode=='safe')
    assert report['native_bbox_checked']==(mode=='safe')
    if mode=='safe':
        assert report['saved_rules_nm']==[470000,230000,700000,300000]
        assert report['native_bbox_nm']==[10100000,8100000]


@pytest.mark.parametrize('already_present',[False,True])
def test_factory_loads_only_missing_blank_project_nonactively(monkeypatch,already_present):
    calls=[];project=object();board=object()
    class Manager:
        blank=project if already_present else None
        def GetProject(self,path):
            assert path==''
            return self.blank
        def LoadProject(self,path,active):
            calls.append((path,active));self.blank=project
            return False  # No file is not the same as failure to establish it.
    manager=Manager()
    monkeypatch.setattr(pcbnew,'GetSettingsManager',lambda:manager)
    monkeypatch.setattr(pcbnew,'BOARD',lambda:board)
    assert create_empty_board() is board
    assert calls==([] if already_present else [('',False)])


@pytest.mark.parametrize('missing_manager',[False,True])
def test_unestablished_default_refuses_before_native_factory(monkeypatch,missing_manager):
    calls=[]
    class Manager:
        def GetProject(self,path):return None
        def LoadProject(self,path,active):
            calls.append(('load',path,active));return False
    monkeypatch.setattr(pcbnew,'GetSettingsManager',lambda:None if missing_manager else Manager())
    monkeypatch.setattr(pcbnew,'BOARD',lambda:calls.append(('unsafe_constructor',)))
    with pytest.raises(ValueError,match='native_empty_board_'):
        create_empty_board()
    assert calls==([] if missing_manager else [('load','',False)])

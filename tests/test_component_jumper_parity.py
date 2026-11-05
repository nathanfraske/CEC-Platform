"""Exact native-RAM jumper parity and bounded actual hierarchy parsing."""
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
import pcbnew
import cec_component_jumper_metadata as jumper
import cec_constraints as constraints
from test_component_jumper_metadata import board_fixture,exported


def hierarchy(tmp_path,root='(kicad_sch (sheet (property "Sheetfile" "child.kicad_sch")))',child='(kicad_sch)'):
    path=tmp_path/'root.kicad_sch';path.write_text(root)
    if child is not None:(tmp_path/'child.kicad_sch').write_text(child)
    return path


def test_compact_and_multiline_real_child_inventory(tmp_path):
    p=hierarchy(tmp_path)
    files=jumper._hierarchy(p,deadline=time.monotonic()+10)
    assert set(files)=={p.resolve(),(tmp_path/'child.kicad_sch').resolve()}
    observation=dict(root=str(p),files={str(k):v for k,v in files.items()},deadline=time.monotonic()+10)
    jumper.check_observation(observation)
    (tmp_path/'child.kicad_sch').write_text('(kicad_sch (uuid "changed"))')
    with pytest.raises(ValueError,match='changed'):jumper.check_observation(observation)


@pytest.mark.parametrize('kind',['cycle','repeated','missing','empty','double-property','no-property','wrong-root','bytes','files','depth','expired','late-read'])
def test_hierarchy_fail_closed(tmp_path,monkeypatch,kind):
    p=hierarchy(tmp_path)
    if kind=='cycle':(tmp_path/'child.kicad_sch').write_text('(kicad_sch (sheet (property "Sheetfile" "root.kicad_sch")))')
    if kind=='repeated':p.write_text('(kicad_sch (sheet (property "Sheetfile" "child.kicad_sch")) (sheet (property "Sheetfile" "child.kicad_sch")))')
    if kind=='missing':(tmp_path/'child.kicad_sch').unlink()
    if kind=='empty':p.write_text('(kicad_sch (sheet (property "Sheetfile" "")))')
    if kind=='double-property':p.write_text('(kicad_sch (sheet (property "Sheetfile" "child.kicad_sch") (property "Sheetfile" "child.kicad_sch")))')
    if kind=='no-property':p.write_text('(kicad_sch (sheet (property "Sheetname" "no file")))')
    if kind=='wrong-root':p.write_text('(not_a_schematic)')
    if kind=='bytes':monkeypatch.setattr(jumper,'_MAX_HIERARCHY_BYTES',8)
    if kind=='files':monkeypatch.setattr(jumper,'_MAX_HIERARCHY_FILES',1)
    if kind=='depth':monkeypatch.setattr(jumper,'_MAX_HIERARCHY_DEPTH',0)
    deadline=time.monotonic()+10
    if kind=='expired':deadline=0
    if kind=='late-read':
        original=Path.read_bytes
        def late(path):
            result=original(path);monkeypatch.setattr(jumper.time,'monotonic',lambda:deadline+1);return result
        monkeypatch.setattr(Path,'read_bytes',late)
    with pytest.raises((ValueError,FileNotFoundError)):jumper._hierarchy(p,deadline=deadline)


def parity_fixture(tmp_path,monkeypatch,*,metadata=True,exporttext=None):
    path=board_fixture(tmp_path);source=hierarchy(tmp_path)
    if metadata:jumper.apply_saved(path,jumper.from_export(exported()))
    board=pcbnew.LoadBoard(str(path));board.SetFileName(str(path));calls=[]
    inventory={'X72':dict(lib_id='fixture:six',value='arbitrary',footprint='fixture:generic-package',on_board=True,in_bom=True,dnp=False)}
    monkeypatch.setattr(constraints,'_schematic_inventory_for_board',lambda p,c:(str(source),inventory))
    monkeypatch.setattr(constraints.cec_toolchain,'kicad_cli',lambda:'fixture-cli')
    def export(command,**kwargs):
        assert 0<kwargs['timeout']<=10;calls.append(command)
        text=exported()if exporttext is None else exporttext
        # Match real CLI layout also consumed by the unchanged legacy
        # spice-sanity pin/net parser (not a parity-verdict substitution).
        Path(command[command.index('-o')+1]).write_text(text.replace('(net (code','\n\t\t(net\n(code'))
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(constraints.subprocess,'run',export)
    return board,path,source,calls


@pytest.mark.parametrize('metadata',[True,False])
def test_real_ram_parity_and_one_shared_export(tmp_path,monkeypatch,metadata):
    board,path,source,calls=parity_fixture(tmp_path,monkeypatch,metadata=metadata)
    before=path.read_bytes();filename=board.GetFileName()
    # Disk may disagree with RAM: native parity must not silently load path.
    if not metadata:jumper.apply_saved(path,jumper.from_export(exported()))
    saved=path.read_bytes();ctx={}
    verdict,message=constraints._chk_sch_pcb_sync(board,str(path),ctx)
    assert verdict is metadata,message
    assert 'jumper' in message
    assert len(calls)==1
    assert constraints._schematic_component_signatures(str(source),{'X72':dict(value='arbitrary',footprint='fixture:generic-package')},ctx)
    assert len(calls)==1
    assert board.GetFileName()==filename and path.read_bytes()==saved
    expected=(('1','6'),('3','4'))if metadata else ()
    assert jumper.read_native(board)['X72']['groups']==expected


def test_empty_expected_groups_reject_stale_pcb_and_implicit(tmp_path,monkeypatch):
    board,path,source,calls=parity_fixture(tmp_path,monkeypatch,exporttext=exported(groups=''))
    verdict,message=constraints._chk_sch_pcb_sync(board,str(path),{})
    assert verdict is False and 'jumper groups'in message and len(calls)==1
    board.FindFootprintByReference('X72').SetDuplicatePadNumbersAreJumpers(True)
    assert constraints._chk_sch_pcb_sync(board,str(path),{})[0]is False


def test_mechanical_metadata_not_schematic_owned(tmp_path,monkeypatch):
    board,path,source,calls=parity_fixture(tmp_path,monkeypatch)
    board.FindFootprintByReference('H57').SetDuplicatePadNumbersAreJumpers(True)
    assert constraints._chk_sch_pcb_sync(board,str(path),{})[0]is True


def test_same_export_source_change_and_cached_late_never_pass(tmp_path,monkeypatch):
    board,path,source,calls=parity_fixture(tmp_path,monkeypatch)
    ctx={};assert constraints._chk_sch_pcb_sync(board,str(path),ctx)[0]is True
    child=source.parent/'child.kicad_sch';child.write_text('(kicad_sch (uuid "different"))')
    with pytest.raises(ValueError,match='changed'):constraints._chk_sch_pcb_sync(board,str(path),ctx)
    assert len(calls)==1


def test_late_native_formatter_and_unknown_export_refuse(tmp_path,monkeypatch):
    board,path,source,calls=parity_fixture(tmp_path,monkeypatch)
    original=jumper.read_native
    def late(*args,**kwargs):
        result=original(*args,**kwargs);monkeypatch.setattr(jumper.time,'monotonic',lambda:float('inf'));return result
    monkeypatch.setattr(jumper,'read_native',late)
    with pytest.raises(ValueError,match='deadline'):constraints._chk_sch_pcb_sync(board,str(path),{})


def test_footprint_only_formatter_keeps_all_native_properties_and_path(tmp_path):
    path=board_fixture(tmp_path,'B',270);jumper.apply_saved(path,jumper.from_export(exported()))
    board=pcbnew.LoadBoard(str(path));board.SetFileName('RAM-only.kicad_pcb')
    before=path.read_bytes();footprints=list(board.GetFootprints())
    def snapshot():
        return [(str(f.m_Uuid.AsString()),f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees(),f.GetLayer(),
                 [(str(p.m_Uuid.AsString()),p.GetNumber(),p.GetPosition().x,p.GetPosition().y,p.GetNetCode())for p in f.Pads()])for f in footprints]
    prior=snapshot();first=jumper.read_native(board);second=jumper.read_native(board)
    assert first==second and snapshot()==prior and board.GetFileName()=='RAM-only.kicad_pcb'and path.read_bytes()==before

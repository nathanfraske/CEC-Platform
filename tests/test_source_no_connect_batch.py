"""Batch NC evidence shares only one immutable invocation-local Source parse."""
import pcbnew
import pytest
import cec_source_no_connect as nc
import cec_force_current as force
from test_source_no_connect import fixture as single_fixture


def fixture(tmp_path,quarter=0,back=False):
    board,source,fp,pad,sch,symbol,marker,at=single_fixture(tmp_path,quarter=quarter)
    other=pcbnew.PAD(fp);other.SetNumber('4');other.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    other.SetLayerSet(pcbnew.PAD.SMDMask());other.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
    net=pcbnew.NETINFO_ITEM(board,'another_opaque_net');board.Add(net);other.SetNet(net);fp.Add(other)
    delta=[(2,0),(0,-2),(-2,0),(0,2)][quarter]
    text=sch.read_text().replace('(name "opaque_input") (number "3"))',
        '(name "opaque_input") (number "3")) (pin input line (at 2 0 0) (length 1) (name "other") (number "4"))')
    text=text[:-1]+f'(no_connect (at {10+delta[0]} {10+delta[1]}) (uuid "31c410bb-9531-4d95-bb14-0f81a799916b")))'
    sch.write_text(text)
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    return board,fp,[force._uid(pad),force._uid(other)],sch


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_batch_exact_sequential_verdicts_one_parse(tmp_path,monkeypatch,quarter,back):
    board,fp,ids,sch=fixture(tmp_path,quarter,back)
    expected={u:nc.plan(board,u,board_hint=str(sch)) for u in ids}
    original=nc.schematic.SchFile;calls=[]
    def counted(path):calls.append(path);return original(path)
    monkeypatch.setattr(nc.schematic,'SchFile',counted)
    assert nc.plan_many(board,ids,board_hint=str(sch))==expected
    assert calls==[str(sch)] and all(expected.values())


@pytest.mark.parametrize('ids',[[],['missing'],['same','same'],[''],[None],list(map(str,range(65)))])
def test_invalid_inventory_refuses_before_source_parse(tmp_path,monkeypatch,ids):
    board,fp,actual,sch=fixture(tmp_path)
    monkeypatch.setattr(nc.schematic,'SchFile',lambda *a:pytest.fail('must validate native inventory first'))
    with pytest.raises(ValueError):nc.plan_many(board,ids,board_hint=str(sch))


@pytest.mark.parametrize('timeout',[0,-1,11,True,float('nan')])
def test_invalid_original_bounds(tmp_path,timeout):
    board,fp,ids,sch=fixture(tmp_path)
    with pytest.raises(ValueError):nc.plan_many(board,ids,board_hint=str(sch),timeout_s=timeout)


def test_ineligible_native_never_parses_and_mixed_batch_keeps_strictness(tmp_path,monkeypatch):
    board,fp,ids,sch=fixture(tmp_path)
    track=pcbnew.PCB_TRACK(board);track.SetNet(next(p for p in fp.Pads()if force._uid(p)==ids[0]).GetNet())
    track.SetWidth(220000);track.SetStart(pcbnew.VECTOR2I_MM(1,1));track.SetEnd(pcbnew.VECTOR2I_MM(2,1));board.Add(track)
    assert nc.plan_many(board,ids,board_hint=str(sch))[ids[0]] is None
    monkeypatch.setattr(nc.schematic,'SchFile',lambda *a:pytest.fail('unisolated never parses'))
    assert nc.plan_many(board,[ids[0]],board_hint=str(sch))=={ids[0]:None}


@pytest.mark.parametrize('mutation',['source','native','late'])
def test_final_original_binding_and_clock_after_entire_batch(tmp_path,monkeypatch,mutation):
    board,fp,ids,sch=fixture(tmp_path);original=nc._land_proof;calls=[]
    def observed(*args):
        result=original(*args);calls.append(1)
        if len(calls)==2:
            if mutation=='source':sch.write_text(sch.read_text()+'\n')
            elif mutation=='native':fp.Move(pcbnew.VECTOR2I(1,0))
            else:monkeypatch.setattr(nc.time,'monotonic',lambda:float('inf'))
        return result
    monkeypatch.setattr(nc,'_land_proof',observed)
    with pytest.raises(ValueError):nc.plan_many(board,ids,board_hint=str(sch))
    assert len(calls)==2


def test_hierarchy_parsed_once_for_all_physical_ids(tmp_path,monkeypatch):
    board,fp,ids,leaf=fixture(tmp_path)
    root=tmp_path/'root.kicad_sch';root.write_text('(kicad_sch (sheet (at 10 10) (size 10 10) (property "Sheetfile" "current.kicad_sch")))')
    original=nc.schematic.SchFile;calls=[]
    def counted(path):calls.append(path);return original(path)
    monkeypatch.setattr(nc.schematic,'SchFile',counted)
    result=nc.plan_many(board,ids,board_hint=str(root))
    assert all(result.values()) and calls==[str(root),str(leaf)]
    assert all(set(p['schematic_files_sha256'])=={str(root),str(leaf)} for p in result.values())

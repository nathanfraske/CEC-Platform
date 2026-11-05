"""Loaded native overlap normalization preserves copper and authority."""
import hashlib
import math

import pcbnew
import pytest
import cec_copper_overlap as overlap


@pytest.mark.parametrize('angle,layer', [(0,pcbnew.F_Cu),(45,pcbnew.In2_Cu),(90,pcbnew.B_Cu),
                                      (180,pcbnew.F_Cu),(270,pcbnew.B_Cu)])
@pytest.mark.parametrize('wide_short', [True,False])
@pytest.mark.parametrize('writable_long', [True,False])
def test_loaded_exact_prefix_scope_and_width(tmp_path, angle, layer, wide_short, writable_long):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'renamed supply');board.Add(net)
    radians=math.radians(angle)
    direction=(round(math.cos(radians)),round(math.sin(radians))) if angle!=45 else (1,1)
    def point(distance):
        return pcbnew.VECTOR2I_MM(23+direction[0]*distance,17+direction[1]*distance)
    def track(a,b,width):
        item=pcbnew.PCB_TRACK(board);item.SetStart(a);item.SetEnd(b)
        item.SetWidth(pcbnew.FromMM(width));item.SetLayer(layer);item.SetNet(net)
        item.SetLocked(True);board.Add(item);return item
    short=track(point(0),point(1),.25 if wide_short else .2)
    long=track(point(0),point(3),.2 if wide_short else .25)
    # An explicit branch must remain attached to exactly the short endpoint.
    branch=track(point(1),pcbnew.VECTOR2I(point(1).x-direction[1]*1000000,
        point(1).y+direction[0]*1000000),.2)
    short_id,long_id=short.m_Uuid.AsString(),long.m_Uuid.AsString()
    group=pcbnew.PCB_GROUP(board);group.SetName('declared-generated-cell');board.Add(group)
    group.AddItem(long)
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board,True)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    loaded=pcbnew.LoadBoard(str(source))
    tracks={t.m_Uuid.AsString():t for t in loaded.GetTracks()}
    before={uid:(t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth(),t.GetLayer(),t.IsLocked())
            for uid,t in tracks.items()}
    result=overlap.trim_covered_prefixes(loaded,{long_id} if writable_long else {short_id})
    expected=wide_short and writable_long
    assert result['changed_count']==int(expected)
    assert set(tracks)=={t.m_Uuid.AsString() for t in loaded.GetTracks()}
    for uid,t in tracks.items():
        after=(t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetWidth(),t.GetLayer(),t.IsLocked())
        if uid!=long_id or not expected:
            assert after==before[uid]
        else:
            assert after[:2]==(point(1).x,point(1).y) and after[2:]==before[uid][2:]
    assert any(i.m_Uuid.AsString()==long_id for g in loaded.Groups() for i in g.GetItems())
    if expected:
        assert overlap.trim_covered_prefixes(loaded,{long_id})['changed_count']==0
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    out=tmp_path/'out.kicad_pcb';pcbnew.SaveBoard(str(out),loaded,True)
    assert len(list(pcbnew.LoadBoard(str(out)).GetTracks()))==3


@pytest.mark.parametrize('difference',['layer','net','angle','opposite','no-origin','equal-length'])
def test_noncovered_geometry_is_untouched(difference):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    nets=[]
    for name in ('left','right'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets.append(net)
    rows=[]
    for length in (1,3):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(10,10))
        t.SetEnd(pcbnew.VECTOR2I_MM(10+length,10));t.SetWidth(pcbnew.FromMM(.25))
        t.SetLayer(pcbnew.F_Cu);t.SetNet(nets[0]);board.Add(t);rows.append(t)
    short,long=rows
    if difference=='layer':short.SetLayer(pcbnew.B_Cu)
    elif difference=='net':short.SetNet(nets[1])
    elif difference=='angle':short.SetEnd(pcbnew.VECTOR2I_MM(11,10.000001))
    elif difference=='opposite':short.SetEnd(pcbnew.VECTOR2I_MM(9,10))
    elif difference=='no-origin':short.Move(pcbnew.VECTOR2I_MM(.1,0))
    else:short.SetEnd(long.GetEnd())
    assert overlap.trim_covered_prefixes(board,{long.m_Uuid.AsString()})['changed_count']==0


def test_multiple_wide_prefixes_form_one_explicit_chain():
    board=pcbnew.CreateEmptyBoard()
    net=pcbnew.NETINFO_ITEM(board,'chain');board.Add(net)
    tracks=[]
    for x0,x1,width in ((0,.75,.25),(.75,1.25,.25),(0,1.655,.2)):
        item=pcbnew.PCB_TRACK(board);item.SetStart(pcbnew.VECTOR2I_MM(10+x0,10))
        item.SetEnd(pcbnew.VECTOR2I_MM(10+x1,10));item.SetWidth(pcbnew.FromMM(width))
        item.SetLayer(pcbnew.F_Cu);item.SetNet(net);item.SetLocked(True)
        board.Add(item);tracks.append(item)
    long=tracks[-1];scope={long.m_Uuid.AsString()}
    result=overlap.trim_covered_prefixes(board,scope)
    assert result['changed_count']==2
    assert long.GetStart()==pcbnew.VECTOR2I_MM(11.25,10)
    assert long.GetEnd()==pcbnew.VECTOR2I_MM(11.655,10)
    assert overlap.trim_covered_prefixes(board,scope)['changed_count']==0

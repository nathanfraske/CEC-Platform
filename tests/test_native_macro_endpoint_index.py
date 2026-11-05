"""Indexing Source contacts changes cost, never their exact native meaning."""
import pcbnew
import pytest
import cec_smd_macro_transport as macro
import cec_force_current as force
from test_complete_macro_cell import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_index_matches_all_native_contact_checks_in_every_face_and_phase(tmp_path,monkeypatch,quarter,back):
    source,board,unused,packet=fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    items=[(p,(170000,-230000),force._uid(p.GetParentFootprint()))
        for f in board.GetFootprints() for p in f.Pads()]
    items += [(t,(-310000,190000),force._uid(t)) for t in board.GetTracks() if t.GetClass()=='PCB_VIA']
    index=macro._endpoint_contact_index(board,items)
    points={tuple(p.GetPosition()) for p,_,_ in items}
    for t in board.GetTracks():points.update((tuple(t.GetStart()),tuple(t.GetEnd())))
    for p,_,_ in items:
        for face in board.GetEnabledLayers().CuStack():
            if not p.IsOnLayer(face):continue
            box=p.GetEffectiveShape(face).BBox()
            points.update(((box.GetLeft(),box.GetTop()),(box.GetRight(),box.GetBottom()),
                (box.GetLeft()-1,box.GetTop()),(box.GetRight()+1,box.GetBottom())))
    points.add((-1000000000,1000000000))
    nets={p.GetNetCode() for p,_,_ in items}|{0,1234567}
    for face in board.GetEnabledLayers().CuStack():
        for code in nets:
            for point in points:
                at=pcbnew.VECTOR2I(*point)
                brute=[(force._uid(p),shift,owner) for p,shift,owner in items
                    if p.GetNetCode()==code and p.IsOnLayer(face)
                    and p.GetEffectiveShape(face).Collide(at,0)]
                indexed=[(force._uid(p),shift,owner) for p,shift,owner in
                    macro._endpoint_contacts(index,code,face,point)]
                assert indexed==brute


def test_contact_index_is_empty_without_literal_source_items():
    board=pcbnew.CreateEmptyBoard();index=macro._endpoint_contact_index(board,[])
    assert not index and macro._endpoint_contacts(index,1,pcbnew.F_Cu,(0,0))==[]


@pytest.mark.parametrize('shape',[pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_CIRCLE,
    pcbnew.PAD_SHAPE_OVAL,pcbnew.PAD_SHAPE_ROUNDRECT,pcbnew.PAD_SHAPE_TRAPEZOID])
@pytest.mark.parametrize('back',[False,True])
def test_native_shape_offsets_drilled_lands_and_one_nm_boundaries_remain_exact(shape,back):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'test_native_net');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);board.Add(fp);items=[]
    for i,attribute in enumerate((pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)):
        pad=pcbnew.PAD(fp);pad.SetAttribute(attribute);pad.SetShape(shape)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.2,.8));pad.SetPosition(pcbnew.VECTOR2I_MM(-3+i*3,2))
        pad.SetOffset(pcbnew.VECTOR2I(130000,-170000));pad.SetOrientationDegrees(45)
        pad.SetNet(net);pad.SetNumber(str(i+1))
        if attribute==pcbnew.PAD_ATTRIB_PTH:
            pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetLayerSet(pcbnew.PAD.PTHMask())
        else:
            ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);pad.SetLayerSet(ls)
        fp.Add(pad);items.append((pad,(i,-i),'literal_'+str(i)))
    index=macro._endpoint_contact_index(board,items)
    for face in board.GetEnabledLayers().CuStack():
        for item,_,_ in items:
            if not item.IsOnLayer(face):continue
            box=item.GetEffectiveShape(face).BBox();centre=box.GetCenter()
            points=[tuple(item.GetPosition()),tuple(centre)]
            for x in (box.GetLeft()-1,box.GetLeft(),box.GetRight(),box.GetRight()+1):
                for y in (box.GetTop()-1,box.GetTop(),centre.y,box.GetBottom(),box.GetBottom()+1):
                    points.append((x,y))
            for point in points:
                brute=[(force._uid(p),d,o) for p,d,o in items if p.IsOnLayer(face)
                    and p.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*point),0)]
                actual=[(force._uid(p),d,o) for p,d,o in
                    macro._endpoint_contacts(index,net.GetNetCode(),face,point)]
                assert actual==brute

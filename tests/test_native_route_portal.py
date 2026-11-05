"""Retained native track ends seed the maze without demanding new barrels."""
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_native_route_portal as portal


def fixture(angle=0,mirror=False):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    n=pcbnew.NETINFO_ITEM(b,'/arbitrary-power');b.Add(n)
    points=[pcbnew.VECTOR2I_MM(10,10),pcbnew.VECTOR2I_MM(14,10)]
    for at,layer in zip(points,(pcbnew.F_Cu,pcbnew.B_Cu)):
        t=pcbnew.PCB_TRACK(b);t.SetNet(n);t.SetLayer(layer);t.SetWidth(200000)
        t.SetStart(at);t.SetEnd(at+pcbnew.VECTOR2I(0,1000000));b.Add(t)
        t.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirror:t.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    tracks=list(b.GetTracks())
    return b,n,tracks


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_exact_track_face_seeds_skip_endpoint_via_search(monkeypatch,angle,mirror):
    b,n,tracks=fixture(angle,mirror);first,last=tracks
    a,z=[tuple(t.GetStart()) for t in tracks];seen={}
    def middle(board,start,end,code,layers,gap,guard,**kw):
        seen.update(kw)
        return [('trk',start,end,200000,first.GetLayer())]
    monkeypatch.setattr(fr,'_multilayer_maze_lastmile_ops',middle)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:pytest.fail('no endpoint barrel should be proposed'))
    before={fr._uid(t) for t in b.GetTracks()} if hasattr(fr,'_uid') else [tuple(t.GetStart()) for t in tracks]
    d={}
    out=fr._lastmile_bridge(b,a,[first.GetLayer()],z,[last.GetLayer()],200000,n.GetNetCode(),
        [pcbnew.F_Cu,pcbnew.B_Cu],200000,allow_maze=True,_multilayer_only=True,
        endpoint_handoffs=False,native_endpoint_seeds=True,middle_grid_mm=.5,
        deadline_monotonic=time.monotonic()+2.,diagnostics=d)
    assert out and seen['start_layers']==[first.GetLayer()] and seen['end_layers']==[last.GetLayer()]
    assert d['exact_native_endpoint_seeds']['new_endpoint_vias']==0
    assert d['endpoints']==[] and not d['release_authority'] and not d['no_path_proof']
    assert [tuple(t.GetStart()) for t in tracks]==[tuple(t.GetStart()) for t in b.GetTracks()]


@pytest.mark.parametrize('fault',['off_endpoint','foreign_net','invented_layer','missing_track'])
def test_endpoint_seed_cannot_invent_copper_or_layer_access(fault):
    b,n,tracks=fixture();a,z=[tuple(t.GetStart()) for t in tracks]
    first=[pcbnew.F_Cu];last=[pcbnew.B_Cu]
    if fault=='off_endpoint':a=(a[0]+1,a[1])
    elif fault=='foreign_net':
        n=pcbnew.NETINFO_ITEM(b,'/other');b.Add(n)
    elif fault=='invented_layer':first=[pcbnew.B_Cu]
    else:
        from cec_native_items import discard_items
        discard_items(b,[tracks[0]])
    with pytest.raises(ValueError,match='exact_native_endpoint_layer_access'):
        fr._lastmile_bridge(b,a,first,z,last,200000,n.GetNetCode(),[pcbnew.F_Cu,pcbnew.B_Cu],200000,
            allow_maze=True,_multilayer_only=True,endpoint_handoffs=False,native_endpoint_seeds=True,
            middle_grid_mm=.5,deadline_monotonic=time.monotonic()+2.)


@pytest.mark.parametrize('attribute',[pcbnew.PAD_ATTRIB_NPTH,pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH])
def test_unplated_and_mask_only_pads_cannot_expose_the_stack(attribute):
    b,n,_=fixture();fp=pcbnew.FOOTPRINT(b);b.Add(fp)
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNet(n);pad.SetAttribute(attribute)
    pad.SetPosition(pcbnew.VECTOR2I_MM(30,30));pad.SetLayerSet(pcbnew.PAD.PTHMask())
    pad.SetSize(pcbnew.VECTOR2I(2000000,2000000));pad.SetDrillSize(pcbnew.VECTOR2I(0,0))
    assert portal.endpoint_layers(b,(30000000,30000000),n.GetNetCode())==set()

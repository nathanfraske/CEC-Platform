"""Potential PTH layers are not copper on a disabled routing face."""
import time
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_force_current as force
from test_macro_required_ground_ingress import source_frame


@pytest.mark.parametrize('count',[2,4,6])
def test_potential_pth_mask_never_expands_actual_routing_stack(monkeypatch,count):
    board=pcbnew.BOARD();board.SetCopperLayerCount(count)
    enabled=pcbnew.LSET()
    for lid in [pcbnew.F_Cu,*[pcbnew.In1_Cu+2*i for i in range(count-2)],pcbnew.B_Cu]:
        enabled.AddLayer(lid)
    board.SetEnabledLayers(enabled)
    net=pcbnew.NETINFO_ITEM(board,'arbitrary_source_control');board.Add(net)
    ends=[];masks=[]
    for ref,xy in [('RENAMED_LEFT',(10,10)),('RENAMED_RIGHT',(14,10))]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(net)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*xy));pad.SetLayerSet(pcbnew.PAD.PTHMask());fp.Add(pad)
        masks.append(tuple(pad.GetLayerSet().CuStack()))
        ends.append(dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),
            layers=list(map(int,pad.GetLayerSet().CuStack()))))
    assert len(masks[0])>count
    monkeypatch.setattr(escape.cell,'_supply_current_widths',lambda *args:None)
    monkeypatch.setattr(escape.cell,'_netclass',lambda *args:dict(width=200000,clearance=200000))
    request=dict(kind='source_boundary',net=str(net.GetNetname()),a=ends[0],b=ends[1],width_nm=200000)
    choices=[];detail={};binding=escape.row._source_binding(board)
    escape._connection_menu(board,request,board_hint='renamed',deadline=time.monotonic()+2,
        layers=[int(pcbnew.B_Cu)],append=lambda ops:choices.append(ops),detail=detail)
    assert choices and any(ops for ops in choices)
    actual=set(map(int,board.GetEnabledLayers().CuStack()))
    assert all(op[4]in actual for ops in choices for op in ops if op[0]=='trk')
    assert escape.row._source_binding(board)==binding
    assert [tuple(next(iter(fp.Pads())).GetLayerSet().CuStack())for fp in board.GetFootprints()]==masks


@pytest.mark.parametrize('bad_layer',[pcbnew.In6_Cu,pcbnew.F_SilkS,pcbnew.Edge_Cuts])
def test_native_constructor_rejects_whole_packet_before_any_disabled_layer_edit(bad_layer):
    board=pcbnew.BOARD();net=pcbnew.NETINFO_ITEM(board,'arbitrary_control');board.Add(net)
    assert not board.IsLayerEnabled(bad_layer) or bad_layer not in board.GetEnabledLayers().CuStack()
    before=escape.row._source_binding(board)
    ops=[['trk',[1000000,1000000],[2000000,1000000],200000,int(pcbnew.F_Cu)],
         ['trk',[2000000,1000000],[3000000,1000000],200000,int(bad_layer)]]
    with pytest.raises(ValueError,match='invalid_octilinear_native_cell_operation'):
        escape._native_ops(board,ops,'arbitrary_control')
    assert escape.row._source_binding(board)==before and not list(board.GetTracks())


@pytest.mark.parametrize('back',[False,True])
def test_source_compiled_pth_boundaries_name_only_real_stack_copper(tmp_path,monkeypatch,back):
    source,poses,pad,obstruction=source_frame(tmp_path,monkeypatch,back=back)
    before=source.read_bytes()
    private,packet=compiler.compile(source,poses,board_hint='opaque',
        required_ground_pad_entries=[pad],additional_obstacle_track_uuids=[obstruction])
    enabled=set(map(int,private.GetEnabledLayers().CuStack()))
    controls=[r for r in packet['requests'].values()if r['net']=='source_owned_control_aperture']
    assert controls
    for request in controls:
        for end in(request['a'],request['b']):
            assert end['layers']and set(end['layers'])<=enabled
    assert source.read_bytes()==before

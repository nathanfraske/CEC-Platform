"""Spatial work pruning must reproduce the exhaustive actual-copper observer."""
import math
from unittest import mock
import pcbnew
import pytest
import cec_decoupler_cell as op
import cec_field_coupling as field
import cec_force_current as force
from test_field_proposals import track
from test_lastmile import _board


def exhaustive(board,pad,reach,*,allow_native_track_body=False):
    choices=[];pos=pad.GetPosition()
    for item in board.GetTracks():
        if item.GetClass()!='PCB_VIA' or item.GetNetname()!='GND' or item.GetNetCode()!=pad.GetNetCode():continue
        # An independent exhaustive oracle deliberately performs NO spatial
        # prefilter. In particular, centre distance is not the path metric
        # for an elongated native terminal.
        path=op._shortest_track_path_mm(board,pad,item,snap_mm=.000001)
        if path is None or path>reach+1e-9:
            path=op._straight_filled_return_mm(board,pad,item,include_native_tracks=allow_native_track_body)
        if path is not None and path<=reach+1e-9:
            if path==0.:return path,item
            choices.append((path,item))
    return min(choices,default=None,key=lambda row:row[0])


def fixture(quarter=0,mirror=False,layer=pcbnew.F_Cu,*,filled=False,near_disconnected=False):
    b=_board([],edge=(0,0,40,40));b.SetCopperLayerCount(6);b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
    def point(x,y):
        if mirror:x=30-x
        for _ in range(quarter):x,y=30-y,x
        return x,y
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ANY_RETURN');b.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(b.FindNet('GND'))
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetPosition(pcbnew.VECTOR2I_MM(*point(5,5)))
    layers=pcbnew.LSET();layers.AddLayer(layer);p.SetLayerSet(layers);fp.Add(p)
    def via(x,y):
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*point(x,y)))
        v.SetWidth(600000);v.SetDrill(300000);v.SetNet(b.FindNet('GND'))
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v);return v
    target=via(6,5)
    for x in range(8,16):
        for y in range(8,16):via(x,y)
    if near_disconnected:via(5,5.7)
    if not filled:track(b,'GND',point(5,5),point(6,5),width=.2,layer=layer)
    else:
        import cec_additive_route_receiving as additive
        z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(layer)
        z.SetLocalClearance(200000);z.SetMinThickness(100000);z.Outline().NewOutline()
        for x,y in ((1,1),(29,1),(29,29),(1,29)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z);additive._ground_refill(b)
    return b,p,target,via


def signature(result):return None if result is None else (result[0],force._uid(result[1]))


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('filled',[False,True])
def test_actual_native_result_and_tie_identity_equal_exhaustive_scan_in_all_rigid_frames(quarter,mirror,layer,filled):
    b,p,target,_=fixture(quarter,mirror,layer,filled=filled);before=field._field_snapshot_inventory(b)
    expected=exhaustive(b,p,16.,allow_native_track_body=True)
    with mock.patch.object(op,'_query_explicit_track_path_mm',wraps=op._query_explicit_track_path_mm) as observed:
        actual=op._existing_return(b,p,16.,allow_native_track_body=True)
    assert signature(actual)==signature(expected)
    # Native fill/island rules may leave the nearest geometric seat without
    # a straight proof. The exhaustive copper witness, not distance, decides.
    assert actual is not None and observed.call_count<10
    if not filled:assert force._uid(actual[1])==force._uid(target)
    assert field._field_snapshot_inventory(b)==before


def test_nearest_barrel_is_not_a_connectivity_or_locality_witness():
    b,p,target,_=fixture(near_disconnected=True)
    assert signature(op._existing_return(b,p,16.))==signature(exhaustive(b,p,16.))
    assert force._uid(op._existing_return(b,p,16.)[1])==force._uid(target)


def test_each_call_reads_live_material_and_no_cached_proof_survives_a_mutation():
    b,p,target,add=fixture();assert op._existing_return(b,p,16.)[0]==1.
    new=add(5,5);r=op._existing_return(b,p,16.)
    assert r[0]==0. and force._uid(r[1])==force._uid(new)


def test_equal_zero_and_positive_costs_retain_the_actual_original_source_order():
    b,p,target,add=fixture();add(5,5);add(5,5)
    assert signature(op._existing_return(b,p,16.))==signature(exhaustive(b,p,16.))
    b,p,target,add=fixture();other=add(5,6);track(b,'GND',(5,5),(5,6),width=.2)
    assert signature(op._existing_return(b,p,16.))==signature(exhaustive(b,p,16.))


@pytest.mark.parametrize('reach',[0.,.9,1.,16.])
def test_original_reach_and_unknown_semantics_are_unchanged(reach):
    b,p,_,_=fixture(near_disconnected=True)
    assert signature(op._existing_return(b,p,reach))==signature(exhaustive(b,p,reach))


def test_unsupported_bounds_never_skip_geometry_work_or_infer_a_path():
    assert op._return_path_aabb_lower_bound_mm(object(),object())==0.


def test_expanded_native_bounds_are_no_greater_than_any_proved_explicit_path():
    b,p,_,_=fixture()
    for v in b.GetTracks():
        if v.GetClass()!='PCB_VIA':continue
        lower=op._return_path_aabb_lower_bound_mm(p,v)
        actual=op._shortest_track_path_mm(b,p,v)
        assert lower>=0. and (actual is None or lower<=actual)

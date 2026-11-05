import time

import pcbnew
import pytest

import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_native_component_ports as ports
from cec_native_items import discard_items
from test_measurement_leaf import fixture


def split_fixture(name='ordinary', quarter=0):
    board, pad, anchor, old, xy = fixture(name, quarter)
    discard_items(board, [old[-1]])
    def track(a, b, width=200000):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(xy(a)); item.SetEnd(xy(b)); item.SetWidth(width)
        item.SetLayer(pcbnew.In2_Cu); item.SetNetCode(pad.GetNetCode())
        board.Add(item); return item
    def via(at, diameter=600000):
        item = pcbnew.PCB_VIA(board); item.SetPosition(xy(at))
        item.SetWidth(diameter); item.SetDrill(300000)
        item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetNetCode(pad.GetNetCode()); board.Add(item); return item
    a, b = via((10,10)), via((20,10))
    left, right = track((10,10),(10,15)), track((20,10),(20,15))
    island = track((14,20),(16,20))
    return board, xy, (a,b), (left,right), island


def menu(board, xy, name='ordinary', **options):
    policy = dict(route_layers=[int(pcbnew.In2_Cu)], minimum_width_nm=200000,
        deadline=time.monotonic()+3., max_ports=16)
    policy.update(options)
    return ports.retained_face_ports(board, name, int(pcbnew.F_Cu),
        [list(xy((15,10))), list(xy((20,10)))], **policy)


@pytest.mark.parametrize('name', ['unrelated_net', '/different/stage'])
@pytest.mark.parametrize('quarter', range(4))
def test_native_components_offer_actual_other_face_exits_not_same_net_islands(name,quarter):
    board, xy, vias, tracks, island = split_fixture(name,quarter)
    before = leaf._binding(board)
    rows = menu(board, xy, name)
    assert len(rows) == 2
    assert rows[0]['source_anchors_nm'] == [list(xy((15,10)))]
    for row, via, track in zip(rows,vias,tracks):
        assert force._uid(via) in row['retained_component_native_uuids']
        assert force._uid(track) in row['retained_component_native_uuids']
        assert force._uid(island) not in row['retained_component_native_uuids']
        assert {p['layers'][0] for p in row['ports']} == {int(pcbnew.In2_Cu)}
        assert any(p['native_uuids']==[force._uid(track)] for p in row['ports'])
        assert any(p['native_uuids']==[force._uid(via)] for p in row['ports'])
        assert not row['new_barrels'] and not row['current_authority']
        assert not row['routing_admitted'] and not row['release_authority']
    assert before == leaf._binding(board)


def test_ports_do_not_infer_opposite_face_or_use_thinner_track_or_via_web():
    board, xy, vias, tracks, _ = split_fixture()
    tracks[0].SetWidth(199999)
    vias[0].SetWidth(499999)
    before = leaf._binding(board)
    rows = menu(board,xy)
    assert rows[0]['ports'] == []
    assert rows[1]['ports']
    assert before == leaf._binding(board)


@pytest.mark.parametrize('options', [
    {'route_layers':[]}, {'route_layers':[True]}, {'route_layers':[999]},
    {'route_layers':[int(pcbnew.In2_Cu)]*2}, {'minimum_width_nm':True},
    {'minimum_width_nm':0}, {'minimum_width_nm':20000001}, {'max_ports':0},
    {'max_ports':True}, {'max_ports':33}, {'deadline':float('nan')},
    {'deadline':time.monotonic()-1}, {'deadline':time.monotonic()+1000}])
def test_invalid_face_port_policy_fails_closed_without_mutation(options):
    board,xy,_,_,_ = split_fixture()
    before = leaf._binding(board)
    with pytest.raises(ValueError):
        menu(board,xy,**options)
    assert before == leaf._binding(board)


def test_forged_source_anchor_cannot_acquire_another_component():
    board,xy,_,_,_ = split_fixture()
    before = leaf._binding(board)
    with pytest.raises(ValueError,match='retained_native_cut_boundary_contact_required'):
        ports.retained_face_ports(board,'ordinary',int(pcbnew.F_Cu),
            [list(xy((12,22))),list(xy((20,10)))], route_layers=[int(pcbnew.In2_Cu)],
            minimum_width_nm=200000,deadline=time.monotonic()+3.)
    assert before == leaf._binding(board)


def test_menu_stays_finite_and_preserves_real_component_obligations():
    board,xy,_,_,_ = split_fixture()
    rows = menu(board,xy,max_ports=2)
    assert all(0 < len(row['ports']) <= 2 for row in rows)
    assert rows[0]['source_anchors_nm'] == [list(xy((15,10)))]
    assert rows[1]['source_anchors_nm'] == [list(xy((20,10)))]


def plated_fixture(name='ordinary',quarter=0):
    board,xy,vias,tracks,_=split_fixture(name,quarter)
    discard_items(board,[vias[0],tracks[0]])
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_PLATED_SOURCE')
    pad=pcbnew.PAD(fp);pad.SetNumber('7');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(1.2,1.2))
    pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    pad.SetPosition(xy((10,10)));pad.SetNetCode(board.GetNetcodeFromNetname(name))
    fp.Add(pad);board.Add(fp)
    return board,xy,pad


@pytest.mark.parametrize('name',['renamed_stage','/arbitrary/PORT'])
@pytest.mark.parametrize('quarter',range(4))
def test_exact_retained_plated_pad_axis_is_explicit_other_face_port(name,quarter):
    board,xy,pad=plated_fixture(name,quarter)
    before=leaf._binding(board)
    assert menu(board,xy,name)[0]['ports']==[]
    rows=menu(board,xy,name,allow_plated_pad_ports=True)
    assert rows[0]['ports']==[dict(at_nm=list(pad.GetPosition()),layers=[int(pcbnew.In2_Cu)],
        native_uuids=[force._uid(pad)],existing_native_contact=True)]
    assert not rows[0]['new_barrels'] and not rows[0]['barrel_ampacity_qualified']
    assert not rows[0]['current_authority'] and not rows[0]['release_authority']
    assert before==leaf._binding(board)


@pytest.mark.parametrize('fault',['smd','npth','web','no_hole','no_target_face','custom','offset'])
def test_plated_port_cannot_infer_physical_barrel_or_web(fault):
    board,xy,pad=plated_fixture()
    if fault=='smd':pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    elif fault=='npth':pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault=='web':pad.SetSize(pcbnew.VECTOR2I(799999,799999))
    elif fault=='no_hole':pad.SetDrillSize(pcbnew.VECTOR2I(0,0))
    elif fault=='no_target_face':pad.SetLayerSet(pcbnew.PAD.SMDMask())
    elif fault=='custom':pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='offset':pad.SetOffset(pcbnew.VECTOR2I(100000,0))
    before=leaf._binding(board)
    assert menu(board,xy,allow_plated_pad_ports=True)[0]['ports']==[]
    assert before==leaf._binding(board)


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_plated_port_flag_is_not_implicit_permission(flag):
    board,xy,_=plated_fixture()
    before=leaf._binding(board)
    with pytest.raises(ValueError,match='bounded_native_retained_face_port_policy_required'):
        menu(board,xy,allow_plated_pad_ports=flag)
    assert before==leaf._binding(board)

from types import SimpleNamespace
import pytest
import pcbnew
import cec_swig_guard
cec_swig_guard.pin()
import cec_outline_geometry as outlines
from cec_board_geometry import outline_bbox_mm


def fixture(radius=0.,reverse=False):
    board=pcbnew.BOARD()
    segments,arcs=outlines._primitives(11,17,40,30,radius)
    for points in segments+arcs:
        if reverse: points=points[::-1]
        shape=pcbnew.PCB_SHAPE(board)
        shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT if len(points)==2 else pcbnew.SHAPE_T_ARC)
        p=[pcbnew.VECTOR2I_MM(*v) for v in points]
        if len(p)==3: shape.SetArcGeometry(*p)
        else: shape.SetStart(p[0]); shape.SetEnd(p[1])
        board.Add(shape)
    return board


@pytest.mark.parametrize('edge', ['left','right','top','bottom'])
@pytest.mark.parametrize('radius', [0,2.5])
def test_single_edge_extension_keeps_datum_and_all_other_edges(edge,radius):
    board=fixture(radius)
    old=outline_bbox_mm(board)
    r=outlines.extend_outer_edge(board,edge=edge,amount_mm=.49)
    new=outline_bbox_mm(board)
    index={'left':0,'top':1,'right':2,'bottom':3}[edge]
    target=list(old);target[index]+=-.49 if index<2 else .49
    assert new==pytest.approx(target,abs=.002)
    assert r['preserves_component_datum']
    for e in board.GetDrawings():
        if e.GetShape()==pcbnew.SHAPE_T_ARC:
            assert e.GetRadius()/1e6==pytest.approx(radius,abs=.002)


@pytest.mark.parametrize('radius',[0.,2.5])
@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('size',[(36,30),(40,26),(36,26)])
def test_actual_outline_matches_requested_size_and_keeps_corner_radius(radius,reverse,size):
    board=fixture(radius,reverse)
    track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(20,20)); track.SetEnd(pcbnew.VECTOR2I_MM(25,25))
    board.Add(track)
    signature=[(e.m_Uuid.AsString(),int(e.GetShape())) for e in board.GetDrawings()]
    result=outlines.resize_rectangular(board,*size)
    assert result['changed']
    assert outline_bbox_mm(board)==pytest.approx((11,17,11+size[0],17+size[1]),abs=.002)
    assert result['corner_radius_mm']==pytest.approx(radius,abs=.002)
    assert [(e.m_Uuid.AsString(),int(e.GetShape())) for e in board.GetDrawings()]==signature
    assert track.GetStart()==pcbnew.VECTOR2I_MM(20,20)
    assert not outlines.resize_rectangular(board,*size)['changed']


@pytest.mark.parametrize('size',[(0,20),(20,float('nan')),(float('inf'),20),(4,20)])
def test_invalid_dimensions_refused_before_mutation(size):
    board=fixture(2.5)
    before=outline_bbox_mm(board)
    with pytest.raises(ValueError): outlines.resize_rectangular(board,*size)
    assert outline_bbox_mm(board)==before


def test_cutout_preserved_by_refusing_unqualified_resize():
    board=fixture()
    cutout=pcbnew.PCB_SHAPE(board); cutout.SetLayer(pcbnew.Edge_Cuts)
    cutout.SetShape(pcbnew.SHAPE_T_CIRCLE)
    cutout.SetStart(pcbnew.VECTOR2I_MM(20,20)); cutout.SetEnd(pcbnew.VECTOR2I_MM(21,20))
    board.Add(cutout)
    with pytest.raises(ValueError,match='cutouts'): outlines.resize_rectangular(board,36,26)
    assert outline_bbox_mm(board)==(11,17,51,47)


def test_unsupported_shrink_keeps_original_candidate_and_source(tmp_path):
    import hashlib
    board=fixture()
    cutout=pcbnew.PCB_SHAPE(board);cutout.SetLayer(pcbnew.Edge_Cuts)
    cutout.SetShape(pcbnew.SHAPE_T_CIRCLE)
    cutout.SetStart(pcbnew.VECTOR2I_MM(20,20));cutout.SetEnd(pcbnew.VECTOR2I_MM(21,20))
    board.Add(cutout)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    accepted,rejected=outlines.screen_rectangular_proposals(path,[(36,26),(40,30)])
    assert accepted==[(40,30)]
    assert rejected[0]['kind']=='unsupported_outline_transform'
    assert 'cutouts' in rejected[0]['reason']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_rectangular_proposals_remain_available(tmp_path):
    board=fixture(2.5);path=tmp_path/'source.kicad_pcb'
    pcbnew.SaveBoard(str(path),board)
    sizes=[(36,26),(40,30)]
    assert outlines.screen_rectangular_proposals(path,sizes)==(sizes,[])


@pytest.mark.parametrize('crossing',[False,True])
def test_footprint_owned_shine_through_cutout_is_preserved_not_scaled(crossing):
    board=fixture(2.5)
    fp=pcbnew.FOOTPRINT(board); board.Add(fp)
    cutout=pcbnew.PCB_SHAPE(fp); cutout.SetLayer(pcbnew.Edge_Cuts)
    cutout.SetShape(pcbnew.SHAPE_T_CIRCLE)
    cutout.SetStart(pcbnew.VECTOR2I_MM(47 if crossing else 25,25))
    cutout.SetEnd(pcbnew.VECTOR2I_MM(48 if crossing else 26,25))
    fp.Add(cutout)
    before=(cutout.GetStart(),cutout.GetEnd())
    if crossing:
        with pytest.raises(ValueError,match='cutout'): outlines.resize_rectangular(board,36,26)
        assert outline_bbox_mm(board)==pytest.approx((11,17,51,47),abs=.002)
    else:
        assert outlines.resize_rectangular(board,36,26)['retained_footprint_cutouts']==1
    assert (cutout.GetStart(),cutout.GetEnd())==before


def test_metadata_only_shrink_requires_explicit_replacement_authority():
    board=fixture()
    candidate=SimpleNamespace(W=36,H=26)
    with pytest.raises(ValueError,match='authority'): outlines.reconcile_candidate(board,candidate)
    assert outline_bbox_mm(board)==(11,17,51,47)
    candidate.outline_replacement_authorized=True
    assert outlines.reconcile_candidate(board,candidate)['changed']


def test_incremental_replacement_releases_only_its_private_copper_proof():
    import cec_full_pipeline as pipeline
    base=SimpleNamespace(P={'DEVICE':(15,20,0)},W=40,H=30,route_preflight={},
                         protected_power_prefix={'items':['frozen source']})
    rows=pipeline._incremental_outline_repack_variants(None,None,base,base.P,
        'unused',{}, {},None,width=36,height=26)
    candidate=rows[0][0]
    assert candidate.outline_replacement_authorized
    assert candidate.protected_power_prefix=={}
    assert base.protected_power_prefix=={'items':['frozen source']}
    assert (base.W,base.H)==(40,30)


def test_incremental_outline_applies_rebound_datums_to_native_candidate_poses():
    import cec_full_pipeline as pipeline
    base=SimpleNamespace(P={'PORT_A':(15,20,0),'PORT_B':(25,20,0),'CELL':(20,10,0)},
                         W=40,H=30,route_preflight={},protected_power_prefix={})
    cfg=SimpleNamespace(pins={'PORT_A':(13,16,0),'PORT_B':(23,16,0)})
    rows=pipeline._incremental_outline_repack_variants(None,cfg,base,base.P,
        'unused',{}, {},None,width=36,height=26)
    candidate,report=rows[0]
    assert candidate.P['PORT_A']==(13,16,0)
    assert candidate.P['PORT_B']==(23,16,0)
    assert candidate.P['CELL']==base.P['CELL']
    assert set(report['required_anchors']['changed'])=={'PORT_A','PORT_B'}
    assert base.P['PORT_A']==(15,20,0)

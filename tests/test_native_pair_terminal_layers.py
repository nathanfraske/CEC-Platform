"""Native plated access must reach the pair router, not only post-route cleanup."""
from unittest.mock import patch
import time

import pcbnew
import pytest
import cec_precision_route as route
import cec_local_copper_cell as cell


def fixture(offset=0., names=('LEFT17','RIGHT8'), attributes=None):
    board=pcbnew.BOARD();board.SetCopperLayerCount(4)
    pair=dict(name='RENAMED_PAIR',p='/DATA_P',n='/DATA_N',width=.2,gap=.13)
    for name in (pair['p'],pair['n'],'GND','FOREIGN'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    endpoints=((4+offset,9),(24+offset,9),(4+offset,11),(24+offset,11))
    pads=[]
    for index,(point,net) in enumerate(zip(endpoints,(pair['p'],pair['p'],pair['n'],pair['n']))):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(names[index%2]+str(index))
        pad=pcbnew.PAD(fp);pad.SetNumber(str(index+1));pad.SetPosition(pcbnew.VECTOR2I_MM(*point))
        pad.SetSize(pcbnew.VECTOR2I_MM(.9,.9));pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        attr=(attributes or {}).get(index, pcbnew.PAD_ATTRIB_PTH if index%2==0 else pcbnew.PAD_ATTRIB_SMD)
        pad.SetAttribute(attr)
        pad.SetLayerSet(pcbnew.PAD.PTHMask() if attr!=pcbnew.PAD_ATTRIB_SMD else pcbnew.PAD.SMDMask())
        if attr!=pcbnew.PAD_ATTRIB_SMD:pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
        pad.SetNetCode(board.GetNetcodeFromNetname(net));fp.Add(pad);board.Add(fp);pads.append(pad)
    return board,pair,endpoints,pads


@pytest.mark.parametrize('offset,names',[(0,('LEFT17','RIGHT8')),(37,('X41','Z99'))])
@pytest.mark.parametrize('middle',['In2.Cu','B.Cu'])
def test_plated_pair_uses_actual_target_layer_without_via(offset,names,middle):
    board,pair,ends,pads=fixture(offset,names)
    report=route._paired_native_terminal_layers(board,pair,ends,layer='F.Cu',middle_layer=middle)
    assert report['start']['native_plated_access'] and report['start']['source_layer']==middle
    assert len(report['start']['pads'])==2
    assert not report['end']['native_plated_access'] and report['end']['source_layer']=='F.Cu'


@pytest.mark.parametrize('case',['smd','npth','wrong_net','offset','drill_missing','layer_missing','ambiguous'])
def test_one_invalid_member_cannot_invent_paired_native_access(case):
    attrs={2:pcbnew.PAD_ATTRIB_SMD} if case=='smd' else {2:pcbnew.PAD_ATTRIB_NPTH} if case=='npth' else {}
    board,pair,ends,pads=fixture(attributes=attrs)
    if case=='wrong_net':pads[2].SetNetCode(board.GetNetcodeFromNetname('FOREIGN'))
    elif case=='offset':pads[2].SetPosition(pcbnew.VECTOR2I_MM(4.0001,11))
    elif case=='drill_missing':pads[2].SetDrillSize(pcbnew.VECTOR2I_MM(0,0))
    elif case=='layer_missing':pads[2].SetLayerSet(pcbnew.PAD.SMDMask())
    elif case=='ambiguous':
        duplicate=pcbnew.PAD(pads[2].GetParentFootprint())
        duplicate.SetAttribute(pcbnew.PAD_ATTRIB_PTH);duplicate.SetLayerSet(pcbnew.PAD.PTHMask())
        duplicate.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4));duplicate.SetPosition(pads[2].GetPosition())
        duplicate.SetNetCode(pads[2].GetNetCode());pads[2].GetParentFootprint().Add(duplicate)
    report=route._paired_native_terminal_layers(board,pair,ends,layer='F.Cu',middle_layer='B.Cu')
    assert not report['start']['native_plated_access']


def test_same_layer_and_unavailable_layer_do_not_change_domain():
    board,pair,ends,_=fixture()
    for middle in ('F.Cu','In30.Cu'):
        report=route._paired_native_terminal_layers(board,pair,ends,layer='F.Cu',middle_layer=middle)
        assert all(not r['native_plated_access'] for r in report.values())


def test_beam_routes_plated_fanin_on_middle_and_never_allocates_its_signal_vias():
    board,pair,ends,_=fixture()
    old=cell.copper_inventory(board);fanins=[];fields=[]
    def fanin(_board,_pair,points,**kwargs):
        fanins.append((points[0],kwargs['layer']))
        return dict(refused='synthetic blocked stub')
    def field(row,**kwargs):
        fields.append(row['side'])
        return dict(ok=True,reason=None,p_via={},n_via={},return_status='covered')
    with patch.object(route,'_route_paired_stub',side_effect=fanin), \
            patch.object(route,'_probe_matched_transition_field',side_effect=field):
        report=route._route_coupled_via_portal_beam(board,pair,ends,
            middle_layer='B.Cu',max_fanins_per_side=1,max_portal_pairs=1,
            deadline=time.monotonic()+3.)
    assert report.get('refused') and fanins
    assert any(point==ends[0] and layer=='B.Cu' for point,layer in fanins)
    assert any(point==ends[1] and layer=='F.Cu' for point,layer in fanins)
    assert fields and set(fields)=={'end'}
    assert cell.copper_inventory(board)==old
    assert report['portal_evidence']['terminal_layer_access']['start']['native_plated_access']


def test_native_plated_ends_close_on_back_without_four_redundant_signal_vias():
    board,pair,ends,_=fixture(attributes={i:pcbnew.PAD_ATTRIB_PTH for i in range(4)})
    for a,b in (((0,0),(30,0)),((30,0),(30,20)),((30,20),(0,20)),((0,20),(0,0))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
        edge.SetLayer(pcbnew.Edge_Cuts);board.Add(edge)
    report=route._route_coupled_via_portal_beam(board,pair,ends,
        middle_layer='B.Cu',max_fanins_per_side=2,max_portal_pairs=8,
        minimum_coupled_fraction=.6,deadline=time.monotonic()+5.)
    assert not report.get('refused'),report
    tracks=list(board.GetTracks());assert tracks
    assert all(t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu for t in tracks)
    assert all(r.get('signal_vias_added')==0 for r in report['transitions'])
    import cec_fr
    board.BuildConnectivity()
    assert all(cec_fr.net_connectivity_component_count(board,board.GetNetcodeFromNetname(net))==1
               for net in (pair['p'],pair['n']))


def test_compact_diagnostics_preserve_bounded_per_end_layer_witnesses():
    import cec_probe_evidence
    portal=dict(source_layer='F.Cu',middle_layer='B.Cu',terminal_layer_access={
        'start':dict(source_layer='B.Cu',native_plated_access=True,
                     pads=[dict(uuid=str(i)) for i in range(8)]),
        'end':dict(source_layer='F.Cu',native_plated_access=False,pads=[]),
        'unexpected':dict(source_layer='other',pads=[]),
    })
    rows=cec_probe_evidence.compact_pair_search_trace({'portal_evidence':portal})
    access=rows[0]['terminal_layer_access']
    assert set(access)=={'start','end'}
    assert access['start']==dict(source_layer='B.Cu',native_plated_access=True,pad_uuids=['0','1'])
    assert not access['end']['native_plated_access']
    assert cec_probe_evidence.compact_pair_search_trace({'search_trace':rows})==rows


def fully_plated_profile_fixture(rotation=0):
    board,pair,ends,pads=fixture(attributes={i:pcbnew.PAD_ATTRIB_PTH for i in range(4)})
    board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    if rotation:
        pivot=pcbnew.VECTOR2I_MM(14,10);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for fp in board.GetFootprints():fp.Rotate(pivot,angle)
    ends=tuple((p.GetPosition().x/1e6,p.GetPosition().y/1e6) for p in pads)
    return board,pair,ends,pads


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('layer',['F.Cu','In2.Cu','B.Cu'])
def test_early_native_face_dispatch_proves_all_four_actual_plated_lands(rotation,layer):
    board,pair,ends,pads=fully_plated_profile_fixture(rotation)
    evidence=route._native_plated_pair_face(board,pair,ends,layer)
    assert evidence['applicable'] and evidence['new_signal_vias_required']==0
    assert evidence['native_pad_uuids']==[p.m_Uuid.AsString() for p in pads]
    assert not evidence['physical_qualified']
    assert not list(board.GetTracks())


@pytest.mark.parametrize('case',['smd','npth','wrong_net','offset','drill_missing',
    'layer_missing','ambiguous','plane','unavailable_layer','missing_profile'])
def test_early_dispatch_cannot_borrow_access_from_one_member_or_a_layer_mask(case):
    board,pair,ends,pads=fully_plated_profile_fixture();layer='B.Cu'
    if case=='smd':pads[0].SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    elif case=='npth':pads[0].SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif case=='wrong_net':pads[0].SetNetCode(board.GetNetcodeFromNetname('FOREIGN'))
    elif case=='offset':pads[0].Move(pcbnew.VECTOR2I(1,0))
    elif case=='drill_missing':pads[0].SetDrillSize(pcbnew.VECTOR2I(0,0))
    elif case=='layer_missing':pads[0].SetLayerSet(pcbnew.PAD.SMDMask())
    elif case=='ambiguous':
        p=pcbnew.PAD(pads[0].GetParentFootprint());p.SetPosition(pads[0].GetPosition())
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetLayerSet(pcbnew.PAD.PTHMask())
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4));p.SetNetCode(pads[0].GetNetCode())
        pads[0].GetParentFootprint().Add(p)
    elif case=='plane':layer='In1.Cu'
    elif case=='unavailable_layer':layer='In30.Cu'
    elif case=='missing_profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='';board.SetProperties(props)
    assert not route._native_plated_pair_face(board,pair,ends,layer)['applicable']


def dispatch_plan(ends):
    return dict(ports={
        'one':dict(p=ends[0],n=ends[2],layers=['B.Cu'],through=True),
        'two':dict(p=ends[1],n=ends[3],layers=['B.Cu'],through=True)},
        terminals=['one','two'],edges=[dict(a='one',b='two',length_mm=20,
            layers=['B.Cu'],through_hole_edge=True)],preferred_signal_layers=['B.Cu'])


def test_tree_uses_prepared_native_body_and_mandatory_return_operator_before_remote_portals():
    board,pair,ends,pads=fully_plated_profile_fixture()
    with patch.object(route,'_route_coupled_endpoint_pofv',return_value=dict(segments=0)) as native, \
            patch.object(route,'route_coupled_pair') as legacy, \
            patch.object(route,'_drop_fully_covered_tracks',return_value={}), \
            patch.object(route,'_pair_graph_geometry',return_value=dict(ok=True)), \
            patch.object(route,'_pair_transaction_detour',return_value=dict(ok=True)), \
            patch.object(route.cec_pair_skew,'from_board',return_value=dict(ok=True)):
        result=route._route_direct_pair_tree(board,pair,dispatch_plan(ends),
            deadline=time.monotonic()+2.)
    assert not result.get('refused') and result['completed_edge_count']==1
    legacy.assert_not_called();native.assert_called_once()
    assert native.call_args.kwargs['target_layer']=='B.Cu'
    assert native.call_args.kwargs['minimum_coupled_fraction']==.35
    assert native.call_args.kwargs['clearance']>=.2
    assert result['legs'][0]['layer_attempts'][0]['native_plated_face_access']['applicable']


def test_refused_prepared_face_removes_supporting_ground_via_before_other_strategies():
    board,pair,ends,pads=fully_plated_profile_fixture()
    def native(*args,**kwargs):
        via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(pcbnew.VECTOR2I_MM(14,15))
        via.SetWidth(600000);via.SetDrill(300000);via.SetNetCode(board.GetNetcodeFromNetname('GND'))
        board.Add(via);return dict(refused='mandatory plated return failed')
    def legacy(*args,**kwargs):
        assert not list(board.GetTracks())
        return dict(refused='other search also refused')
    with patch.object(route,'_route_coupled_endpoint_pofv',side_effect=native), \
            patch.object(route,'route_coupled_pair',side_effect=legacy), \
            patch.object(route,'_drop_fully_covered_tracks',return_value={}), \
            patch.object(route,'_pair_graph_geometry',return_value=dict(ok=True)), \
            patch.object(route,'_pair_transaction_detour',return_value=dict(ok=True)):
        result=route._route_direct_pair_tree(board,pair,dispatch_plan(ends))
    assert result.get('refused') and not list(board.GetTracks())

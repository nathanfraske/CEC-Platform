import math
from unittest import mock
import pytest
import pcbnew as pcb
import cec_pth_pair_returns as returns
import cec_precision_route as precision


def fixture(ground_kind='via', signal_type=pcb.PAD_ATTRIB_PTH):
    board=pcb.BOARD();board.SetCopperLayerCount(6)
    nets={}
    for name in ('GND','P','N'):
        nets[name]=pcb.NETINFO_ITEM(board,name);board.Add(nets[name])
    fp=pcb.FOOTPRINT(board);fp.SetReference('ARBITRARY_77');board.Add(fp)
    pad=pcb.PAD(fp);pad.SetNumber('x');pad.SetAttribute(signal_type)
    pad.SetShape(pcb.PAD_SHAPE_CIRCLE);pad.SetSize(pcb.VECTOR2I_MM(1.5,1.5))
    pad.SetDrillSize(pcb.VECTOR2I_MM(.8,.8));pad.SetPosition(pcb.VECTOR2I_MM(0,0))
    pad.SetLayerSet(pcb.LSET.AllCuMask());pad.SetNet(nets['P']);fp.Add(pad)
    if ground_kind=='via':
        ground=pcb.PCB_VIA(board);ground.SetViaType(pcb.VIATYPE_THROUGH)
        ground.SetLayerPair(pcb.F_Cu,pcb.B_Cu);ground.SetWidth(pcb.FromMM(.6))
        ground.SetDrill(pcb.FromMM(.3));board.Add(ground)
    else:
        ground=pcb.PAD(fp);ground.SetAttribute(pcb.PAD_ATTRIB_PTH)
        ground.SetShape(pcb.PAD_SHAPE_CIRCLE);ground.SetSize(pcb.VECTOR2I_MM(.6,.6))
        ground.SetLayerSet(pcb.LSET.AllCuMask());ground.SetDrillSize(pcb.VECTOR2I_MM(.3,.3))
        fp.Add(ground)
    ground.SetPosition(pcb.VECTOR2I_MM(1.3,.6));ground.SetNet(nets['GND'])
    poly=pcb.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in ((1.1,.2),(2,.2),(2,2),(1.1,2)):poly.Append(round(x*1e6),round(y*1e6))
    return board,pad,ground,poly


@pytest.mark.parametrize('kind',['via','pad'])
def test_native_ground_barrel_requires_plane_contact_and_nearby_plated_signal(kind):
    board,pad,ground,poly=fixture(kind)
    cells=returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[poly])
    assert len(cells)==1 and cells[0]['pad_uuid']==pad.m_Uuid.AsString()
    assert returns.contains_sample(pcb.VECTOR2I_MM(.6,0),cells,clearance_mm=.2,sample_mm=.5)
    assert not returns.contains_sample(pcb.VECTOR2I_MM(2,0),cells,clearance_mm=.2,sample_mm=.5)
    assert not returns.reference_cells(board,'N',pcb.F_Cu,pcb.In1_Cu,[poly])
    assert not returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[])
    ground.SetPosition(pcb.VECTOR2I_MM(-1.3,.6)) # equally near, no plane contact
    assert not returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[poly])
    ground.SetPosition(pcb.VECTOR2I_MM(2,.6)) # plane contact, too far
    assert not returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[poly])


@pytest.mark.parametrize('attribute',[pcb.PAD_ATTRIB_NPTH,pcb.PAD_ATTRIB_SMD])
def test_unplated_or_surface_pad_never_receives_barrel_exclusion(attribute):
    board,_,_,poly=fixture(signal_type=attribute)
    assert not returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[poly])


def test_wrong_net_or_nonspanning_return_refuses():
    board,pad,ground,poly=fixture()
    ground.SetNet(board.FindNet('N'))
    assert not returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[poly])
    ground.SetNet(board.FindNet('GND'));ground.SetViaType(pcb.VIATYPE_BLIND)
    ground.SetLayerPair(pcb.In1_Cu,pcb.In2_Cu)
    assert not returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[poly])


def test_failed_native_field_rolls_back_only_new_returns():
    board,pad,ground,poly=fixture()
    before={item.m_Uuid.AsString() for item in board.GetTracks()}
    def fail(*a,**kw):
        via=pcb.PCB_VIA(board);board.Add(via)
        return [via],'no legal field'
    contract=dict(diameter_nm=600000,drill_nm=300000,clearance_nm=200000)
    with mock.patch.object(returns,'ground_return_contract',return_value=contract), \
         mock.patch.object(precision,'_add_pair_transition_returns',side_effect=fail)as construct:
        result=returns.synthesize(board,{'p':'P','n':'N','width':.2,'gap':.25})
    construct.assert_called_once()
    assert not result['ok']
    assert {item.m_Uuid.AsString() for item in board.GetTracks()}==before


@pytest.mark.parametrize('reach',[0,-1,math.inf,math.nan])
def test_invalid_reference_reach_refuses(reach):
    board,_,_,poly=fixture()
    with pytest.raises(ValueError):returns.reference_cells(board,'P',pcb.F_Cu,pcb.In1_Cu,[poly],reach_mm=reach)


def test_ground_contract_maxes_class_board_annular_fabrication_and_rule_floors(tmp_path):
    from test_pth_return_repair import fixture as saved_fixture
    source=tmp_path/'board.kicad_pcb';saved_fixture(source,ground_dimensions=(.9,.5))
    source.with_suffix('.kicad_dru').write_text('''(version 1)
      (rule "not a waiver" (condition "A.NetClass == 'AnyClass'")
        (constraint via_diameter (min .95mm))
        (constraint hole_size (min .55mm))
        (constraint annular_width (min .25mm))
        (constraint clearance (min .35mm)))''')
    board=pcb.LoadBoard(str(source));settings=board.GetDesignSettings();settings.m_ViasMinSize=1100000
    contract=returns.ground_return_contract(board)
    assert contract['diameter_nm']==1100000 and contract['drill_nm']==550000
    assert contract['annular_min_nm']==250000 and contract['clearance_nm']==350000
    assert contract['rules']['present']and contract['rules']['sha256']
    assert contract['class_spec']['via_diameter']==.9 and contract['class_spec']['via_drill']==.5


def test_ground_contract_observes_declared_fab_clearance_floor(tmp_path):
    import json
    from test_pth_return_repair import fixture as saved_fixture
    source=tmp_path/'board.kicad_pcb';saved_fixture(source,ground_dimensions=(.9,.5))
    project=json.loads(source.with_suffix('.kicad_pro').read_text())
    for row in project['net_settings']['classes']:row['clearance']=.01
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    board=pcb.LoadBoard(str(source));board.GetDesignSettings().m_MinClearance=0
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';board.SetProperties(props)
    assert returns.ground_return_contract(board)['clearance_nm']==200000


@pytest.mark.parametrize('fault',['project_absent','class_unknown','profile_absent','rule_expression','rule_negative'])
def test_missing_or_unsupported_ground_authority_refuses_without_construction(tmp_path,fault):
    import json
    from test_pth_return_repair import fixture as saved_fixture
    source=tmp_path/'board.kicad_pcb';saved_fixture(source,ground_dimensions=(.9,.5))
    board=pcb.LoadBoard(str(source))
    if fault=='project_absent':source.with_suffix('.kicad_pro').unlink()
    elif fault=='class_unknown':
        data=json.loads(source.with_suffix('.kicad_pro').read_text())
        data['net_settings']['netclass_assignments']['GND']=['UndefinedReturnClass']
        source.with_suffix('.kicad_pro').write_text(json.dumps(data))
    elif fault=='profile_absent':
        props=board.GetProperties();props.erase('CEC_FAB_PROFILE');board.SetProperties(props)
    else:
        value='(0.2mm + 0.3mm)'if fault=='rule_expression'else'-0.1mm'
        source.with_suffix('.kicad_dru').write_text('(version 1)(rule "unknown" (constraint hole_size (min '+value+')))')
    before={item.m_Uuid.AsString()for item in board.GetTracks()}
    with mock.patch.object(precision,'_add_pair_transition_returns')as constructor:
        result=returns.synthesize(board,dict(p='/CAN_H',n='/CAN_L',width=.25,gap=.25,via_diameter=.6,via_drill=.3))
    constructor.assert_not_called()
    assert not result['ok']and result['reason']=='ground_return_contract_unavailable'
    assert {item.m_Uuid.AsString()for item in board.GetTracks()}==before


def test_expired_ground_constructor_does_not_even_compile_reference_preview():
    board,_,_,_=fixture()
    with mock.patch('cec_return_plane_preview.compile_contact_filter')as preview:
        result=returns.synthesize(board,dict(p='P',n='N'),deadline=0)
    preview.assert_not_called()
    assert not result['ok']and result['reason']=='ground_return_deadline_exhausted'


def test_ground_contract_keeps_board_fabrication_and_rule_spacing_floors(tmp_path):
    from test_pth_return_repair import fixture as saved_fixture
    source=tmp_path/'board.kicad_pcb';saved_fixture(source,ground_dimensions=(.9,.5))
    source.with_suffix('.kicad_dru').write_text('''(version 1)
      (rule "conservative bounded minima" (condition "A.NetClass == 'Arbitrary'")
        (constraint hole_to_hole (min .7mm))
        (constraint hole_clearance (min .8mm))
        (constraint edge_clearance (min .9mm)))''')
    board=pcb.LoadBoard(str(source));settings=board.GetDesignSettings()
    settings.m_HoleToHoleMin=750000;settings.m_CopperEdgeClearance=950000
    contract=returns.ground_return_contract(board)
    assert contract['spacing_nm']==dict(hole_to_hole=750000,hole_clearance=800000,edge_clearance=950000)
    # A .2 mm annulus already protects that much of the new drilled wall.
    assert contract['clearance_nm']>=600000


@pytest.mark.parametrize('kind',['hole_to_hole','hole_clearance','edge_clearance'])
def test_ground_site_native_spacing_observes_larger_rule_minimum(tmp_path,kind):
    from test_pth_return_repair import fixture as saved_fixture
    source=tmp_path/'board.kicad_pcb';saved_fixture(source,ground_dimensions=(.9,.5))
    board=pcb.LoadBoard(str(source));at=pcb.VECTOR2I_MM(13.5,8)
    contract=returns.ground_return_contract(board)
    assert returns.ground_site_guard(board,at,900000,500000,contract)['ok']
    floor=7 if kind=='edge_clearance'else 1.0
    source.with_suffix('.kicad_dru').write_text(
        '(version 1)(rule "strict"(constraint '+kind+'(min '+str(floor)+'mm)))')
    strict=returns.ground_return_contract(board)
    result=returns.ground_site_guard(board,at,900000,500000,strict)
    assert not result['ok']
    assert result['reason']==('ground_site_native_edge_refused'if kind=='edge_clearance'
                             else'ground_site_native_hole_spacing_refused')


def test_ground_site_native_outline_not_just_bounding_box(tmp_path):
    from test_pth_return_repair import fixture as saved_fixture
    source=tmp_path/'board.kicad_pcb';saved_fixture(source)
    board=pcb.LoadBoard(str(source));contract=returns.ground_return_contract(board)
    # Retain the same outer bounding box but cut a material notch through this
    # proposed seat. A bbox-only constructor would still consider it interior.
    for item in list(board.GetDrawings()):board.Remove(item)
    points=((0,0),(20,0),(20,20),(11,20),(11,9),(9,9),(9,20),(0,20),(0,0))
    for a,b in zip(points,points[1:]):
        edge=pcb.PCB_SHAPE(board);edge.SetShape(pcb.SHAPE_T_SEGMENT);edge.SetLayer(pcb.Edge_Cuts)
        edge.SetStart(pcb.VECTOR2I_MM(*a));edge.SetEnd(pcb.VECTOR2I_MM(*b));board.Add(edge)
    result=returns.ground_site_guard(board,pcb.VECTOR2I_MM(10,10),600000,300000,contract)
    assert not result['ok']and result['reason']=='ground_site_native_edge_refused'


def test_ground_site_bounded_missing_geometry_and_deadline_refuse(tmp_path):
    from test_pth_return_repair import fixture as saved_fixture
    source=tmp_path/'board.kicad_pcb';saved_fixture(source)
    board=pcb.LoadBoard(str(source));contract=returns.ground_return_contract(board)
    at=pcb.VECTOR2I_MM(13.5,8)
    assert returns.ground_site_guard(board,at,600000,300000,contract,deadline=0)['reason']=='ground_site_deadline_exhausted'
    assert returns.ground_site_guard(board,at,600000,300000,contract,
        existing_via_uuid='missing')['reason']=='ground_site_existing_identity_missing'
    with mock.patch.object(pcb.SHAPE,'Collide',side_effect=RuntimeError('native unavailable')):
        assert returns.ground_site_guard(board,at,600000,300000,contract)['reason']=='ground_site_native_geometry_unavailable'
    for item in list(board.GetDrawings()):board.Remove(item)
    assert returns.ground_site_guard(board,at,600000,300000,contract)['reason']=='ground_site_native_outline_required'

"""Source-width geometry proposals; no invented current or barrel credit."""
import copy,json
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_force_current as force
import cec_native_supply_via_context as web
import cec_macro_supply_departure as departure
import cec_cell_macro_requests as compiler
import cec_fr as fr
from test_native_supply_via_context import native_fixture
from test_macro_supply_departure import fixture as departure_fixture


def contract(board,width=500000):
    return dict(current_authority=dict(amps=.3,geometry_margin=1.,margin_included=True,
        source='synthetic_unit_source_only'),required_by_layer_nm={int(l):width
        for l in board.GetEnabledLayers().CuStack()})


@pytest.mark.parametrize('angle,back',[(a,b)for a in (0,90,180,270)for b in (False,True)])
def test_real_outer_contacts_receive_derived_full_web_without_unused_inner_credit(angle,back):
    board,via,physical=native_fixture(angle,back)
    source=contract(board);source['required_by_layer_nm'][pcbnew.In2_Cu]=1800000
    before=copy.deepcopy(source)
    geometry=escape._source_current_via_geometry(board,source,[pcbnew.F_Cu,pcbnew.B_Cu])
    assert geometry['minimum_local_via_web_nm']==500000
    assert round(geometry['dia']*1e6)-round(geometry['drill']*1e6)>=500000
    via.SetWidth(round(geometry['dia']*1e6));via.SetDrill(round(geometry['drill']*1e6))
    physical['required_by_layer_mm']={board.GetLayerName(l):w/1e6 for l,w in source['required_by_layer_nm'].items()}
    proof=web.receive(board,force._uid(via),physical)
    assert proof['ok'] and proof['complete'] and proof['actual_contact_layers']==['B.Cu','F.Cu']
    assert not proof['plated_barrel_current_qualified'] and source==before


def test_actual_larger_board_drill_is_recomputed_not_minimum_drill():
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    board.GetDesignSettings().m_MinThroughDrill=450000
    geometry=escape._source_current_via_geometry(board,contract(board),[pcbnew.F_Cu,pcbnew.In2_Cu])
    assert geometry['drill']>=.45
    assert round(geometry['dia']*1e6)-round(geometry['drill']*1e6)>=500000


def test_actual_inner_contact_reinstates_full_inner_width_and_json_roundtrip_is_exact():
    board=pcbnew.BOARD();board.SetCopperLayerCount(6);source=contract(board)
    source['required_by_layer_nm'][pcbnew.In2_Cu]=1100000
    a=escape._source_current_via_geometry(board,source,[pcbnew.F_Cu,pcbnew.In2_Cu])
    b=escape._source_current_via_geometry(board,json.loads(json.dumps(source)),[pcbnew.F_Cu,pcbnew.In2_Cu])
    assert a==b and a['minimum_local_via_web_nm']==1100000
    assert round(a['dia']*1e6)-round(a['drill']*1e6)>=1100000


@pytest.mark.parametrize('back',[False,True])
def test_full_web_geometry_never_waives_actual_same_net_smd_land_exclusion(back):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'renamed_source_supply');board.Add(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('different_owner');board.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('17');pad.SetNet(net);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    layer=pcbnew.B_Cu if back else pcbnew.F_Cu
    ls=pcbnew.LSET();ls.AddLayer(layer);pad.SetLayerSet(ls);fp.Add(pad)
    pad.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    geometry=escape._source_current_via_geometry(board,contract(board),[pcbnew.F_Cu,pcbnew.B_Cu])
    detail={}
    assert not fr._via_spot_clear(board,pad.GetPosition(),round(geometry['dia']*1e6),200000,
        {pad.GetNetCode()},drill_nm=round(geometry['drill']*1e6),net_code=pad.GetNetCode(),report=detail)
    assert detail['reason']=='pad or hole excludes via land'


@pytest.mark.parametrize('fault',['missing_face','unknown_face','bad_face','zero','bool','nan','no_authority','bool_amps','duplicate','noncanonical_key'])
def test_unknown_ambiguous_or_invalid_source_is_not_a_geometry_floor(fault):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6);source=contract(board);faces=[pcbnew.F_Cu,pcbnew.B_Cu]
    if fault=='missing_face':source['required_by_layer_nm'].pop(pcbnew.B_Cu)
    elif fault=='unknown_face':faces.append(pcbnew.F_SilkS)
    elif fault=='bad_face':faces=[True]
    elif fault in ('zero','bool','nan'):source['required_by_layer_nm'][pcbnew.F_Cu]={'zero':0,'bool':True,'nan':float('nan')}[fault]
    elif fault=='no_authority':source['current_authority']={}
    elif fault=='bool_amps':source['current_authority']['amps']=True
    elif fault=='duplicate':source['required_by_layer_nm']['0']=500000
    else:source['required_by_layer_nm']['00']=500000
    with pytest.raises(ValueError):escape._source_current_via_geometry(board,source,faces)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_required_departure_uses_full_web_before_native_guards_and_saved_check(tmp_path,monkeypatch,quarter,back):
    source,parent,poses,request=departure_fixture(tmp_path,monkeypatch,quarter=quarter,back=back)
    private,packet=compiler.compile(source,poses,board_hint='opaque',required_supply_departures=[request])
    proof=packet['required_supply_departure_columns'][0]
    assert proof['diameter_nm']-proof['drill_nm']>=500000
    assert proof['required_full_contact_web_nm']==500000
    import cec_additive_route_receiving as additive
    additive._ground_refill(private)
    ops,detail=departure.entry_ops(private,proof)
    assert detail['found']
    made=escape._native_ops(private,ops,proof['net']);incoming={force._uid(t)for t in made}
    assert departure.receive(private,[proof],incoming)[0]['exact_required_supply_column_constructed']
    via=next(t for t in made if t.GetClass()=='PCB_VIA');via.SetWidth(proof['drill_nm']+499999)
    with pytest.raises(ValueError):departure.receive(private,[proof],incoming)

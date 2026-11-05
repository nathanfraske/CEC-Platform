import time
import pytest
import cec_swig_guard;cec_swig_guard.pin()
import pcbnew
import cec_thermal_terminal_selection as selection
import cec_thermal2d as thermal


def fixture():
    b=pcbnew.CreateEmptyBoard();b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,'arbitrary-current-net');b.Add(net)
    other=pcbnew.NETINFO_ITEM(b,'other-native-net');b.Add(other)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('SOURCE_BANK');b.Add(fp)
    pads=[]
    for n,x in enumerate((2.,10.,18.),1):
        p=pcbnew.PAD(fp);fp.Add(p);p.SetNumber(str(n));p.SetNet(net if n<3 else other)
        p.SetPosition(pcbnew.VECTOR2I_MM(x,5));p.SetSize(pcbnew.VECTOR2I_MM(2,2))
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetDrillSize(pcbnew.VECTOR2I_MM(1,1));p.SetLayerSet(pcbnew.LSET.AllCuMask());pads.append(p)
    return b,net,pads


def uid(p):return str(p.m_Uuid.AsString())
LAYERS={pcbnew.F_Cu:'F.Cu',pcbnew.B_Cu:'B.Cu'}


def test_default_selection_preserves_all_on_net_pins():
    b,n,p=fixture();rows=selection.pads(b,n.GetNetname(),['SOURCE_BANK'],LAYERS)
    assert {r['uuid'] for r in rows}=={uid(p[0]),uid(p[1])}


@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
def test_single_worst_contact_does_not_spread_injection_over_other_pins(face):
    b,n,p=fixture();grid=thermal.Grid(0,0,22,10,.25)
    cells=thermal._terminal_cells_for_pad_uuids(b,grid,LAYERS,n.GetNetname(),
        ['SOURCE_BANK'],[uid(p[1])],[face])
    assert {layer for layer,c in cells}=={face}
    assert {c for layer,c in cells}==thermal._pad_cell_set(p[1],grid)
    assert not {c for layer,c in cells}&thermal._pad_cell_set(p[0],grid)


@pytest.mark.parametrize('bad',['missing','foreign_net','duplicate','empty'])
def test_bad_native_pad_scope_is_not_a_reference_bank_fallback(bad):
    b,n,p=fixture()
    ids={'missing':['stale-native-uuid'],'foreign_net':[uid(p[2])],
         'duplicate':[uid(p[0])]*2,'empty':[]}[bad]
    with pytest.raises(ValueError):selection.pads(b,n.GetNetname(),['SOURCE_BANK'],LAYERS,pad_uuids=ids)


def test_wrong_reference_or_face_does_not_authorize_selected_pad():
    b,n,p=fixture()
    for refs,layers in ((['WRONG_SOURCE'],['F.Cu']),(['SOURCE_BANK'],['In9.Cu'])):
        with pytest.raises(ValueError):selection.pads(b,n.GetNetname(),refs,LAYERS,
            pad_uuids=[uid(p[0])],allowed_layers=layers)


def test_disabled_layer_is_not_created_by_all_copper_pad_mask():
    b,n,p=fixture();b.SetCopperLayerCount(2)
    mapping=dict(LAYERS);mapping[pcbnew.In3_Cu]='In3.Cu'
    with pytest.raises(ValueError):selection.pads(b,n.GetNetname(),['SOURCE_BANK'],mapping,
        pad_uuids=[uid(p[0])],allowed_layers=['In3.Cu'])


def test_explicit_empty_selector_and_deadline_refuse():
    b,n,p=fixture();grid=thermal.Grid(0,0,22,10,.25)
    with pytest.raises(ValueError):thermal._terminal_cells_for_pad_uuids(
        b,grid,LAYERS,n.GetNetname(),['SOURCE_BANK'],None)
    with pytest.raises(ValueError):selection.pads(b,n.GetNetname(),['SOURCE_BANK'],LAYERS,
        pad_uuids=[uid(p[0])],deadline=time.monotonic()-1)


def test_native_board_serialization_does_not_change_for_scenario_selection():
    b,n,p=fixture()
    def state():
        formatter=pcbnew.STRING_FORMATTER();writer=pcbnew.PCB_IO_KICAD_SEXPR()
        writer.FormatBoardToFormatter(formatter,b);return formatter.GetString()
    before=state();selection.pads(b,n.GetNetname(),['SOURCE_BANK'],LAYERS,pad_uuids=[uid(p[1])])
    assert before==state()

"""Inner enlargement never invents surface copper or omits actual pad faces."""
import pcbnew
import pytest
import cec_fr as fr
import cec_native_via_pad_context as context
import cec_fab_profile as fab
from test_lastmile import _board
from test_field_proposals import track


def layers(*faces):
    mask = pcbnew.LSET()
    for layer in faces: mask.AddLayer(layer)
    return mask


def fixture(rotation=0, flip=False):
    board = _board([], edge=(0, 0, 25, 25))
    board.SetCopperLayerCount(6)
    props = board.GetProperties()
    props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_high_current'
    board.SetProperties(props)
    for name in ('/ordinary', '/foreign'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference('U_TEST')
    board.Add(fp)
    pad = pcbnew.PAD(fp)
    pad.SetNumber('1')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.8, .8))
    pad.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    pad.SetLayerSet(layers(pcbnew.B_Cu if flip else pcbnew.F_Cu))
    pad.SetNetCode(board.GetNetcodeFromNetname('/ordinary'))
    fp.Add(pad)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    via.SetNetCode(pad.GetNetCode())
    via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.Padstack().SetMode(pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)
    for layer in board.GetEnabledLayers().CuStack():
        via.SetWidth(layer, 600000 if layer in (pcbnew.F_Cu, pcbnew.B_Cu) else 1200000)
    if rotation:
        centre = pcbnew.VECTOR2I_MM(12, 12)
        angle = pcbnew.EDA_ANGLE(rotation, pcbnew.DEGREES_T)
        fp.Rotate(centre, angle)
        via.Rotate(centre, angle)
    return board, via, pad


def probe(board, via, **overrides):
    arguments = dict(at=via.GetPosition(), maximum_diameter_nm=1200000,
        drill_nm=300000, net_code=via.GetNetCode(), clearance_nm=200000)
    arguments.update(overrides)
    return context.conflicts(board, via, **arguments)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('flip', [False, True])
def test_actual_surface_land_not_inner_maximum_must_fit_smd(rotation, flip):
    board, via, pad = fixture(rotation, flip)
    assert fab.via_at_pad_conflicts(board, via.GetPosition(), 1200000, 300000,
        via.GetNetCode())[0] is not None
    blocking, records = probe(board, via)
    assert blocking is None and len(records) == 1
    assert records[0]['native_diameter_nm'] == 600000
    report = {}
    assert fr._via_spot_clear(board, via.GetPosition(), 1200000, 200000, {via.GetNetCode()},
        drill_nm=300000, net_code=via.GetNetCode(), native_padstack_via=via,
        foreign_cache={}, report=report), report
    assert report['actual_native_pad_exclusions'] == records
    assert not list(board.GetTracks())


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('fault', ['foreign', 'tht', 'npth', 'surface_overhang',
    'inner_smd', 'multiple_faces', 'missing_profile', 'custom_pad', 'unassigned'])
def test_native_pad_overlap_cannot_be_waived(rotation, fault):
    board, via, pad = fixture(rotation)
    if fault == 'foreign':
        pad.SetNetCode(board.GetNetcodeFromNetname('/foreign'))
    elif fault == 'tht':
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3, .3))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    elif fault == 'npth':
        pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4, .4))
    elif fault == 'surface_overhang':
        pad.SetSize(pcbnew.VECTOR2I_MM(.5, .5))
    elif fault == 'inner_smd':
        pad.SetLayerSet(layers(pcbnew.In2_Cu))
    elif fault == 'multiple_faces':
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    elif fault == 'missing_profile':
        props = board.GetProperties()
        props['CEC_FAB_PROFILE'] = 'missing'
        board.SetProperties(props)
    elif fault == 'custom_pad':
        # An actual native custom pad shape cannot borrow RECT containment.
        pad.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault == 'unassigned':
        pad.SetNetCode(0)
    assert probe(board, via)[0] is not None
    assert not fr._via_spot_clear(board, via.GetPosition(), 1200000, 200000, {via.GetNetCode()},
        drill_nm=300000, net_code=via.GetNetCode(), native_padstack_via=via, foreign_cache={})


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu,
    pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu])
def test_enlarged_inner_and_both_outer_foreign_copper_still_block(rotation, layer):
    board, via, pad = fixture(rotation)
    at = via.GetPosition()
    # Place a literal foreign shape directly through the via axis on each
    # tested face. It cannot disappear behind a same-net surface exception.
    x, y = at.x / 1e6, at.y / 1e6
    track(board, '/foreign', (x-.6, y), (x+.6, y), layer=layer)
    assert not fr._via_spot_clear(board, at, 1200000, 200000, {via.GetNetCode()},
        drill_nm=300000, net_code=via.GetNetCode(), native_padstack_via=via, foreign_cache={})


@pytest.mark.parametrize('fault', ['at', 'net', 'maximum', 'drill', 'blind', 'inner_floor'])
def test_fresh_native_context_is_rederived_not_a_caller_size_map(fault):
    board, via, pad = fixture()
    args = {}
    if fault == 'at': args['at'] = pcbnew.VECTOR2I_MM(10.1, 10)
    elif fault == 'net': args['net_code'] = board.GetNetcodeFromNetname('/foreign')
    elif fault == 'maximum': args['maximum_diameter_nm'] = 1100000
    elif fault == 'drill': args['drill_nm'] = 400000
    elif fault == 'blind': via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault == 'inner_floor': via.SetWidth(pcbnew.In1_Cu, 400000)
    with pytest.raises(ValueError): probe(board, via, **args)


def test_saved_native_layered_padstack_receives_without_mutating_source(tmp_path):
    board, via, pad = fixture()
    board.Add(via)
    path = tmp_path / 'board.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    before = path.read_bytes()
    loaded = pcbnew.LoadBoard(str(path))
    actual = next(t for t in loaded.GetTracks() if t.GetClass() == 'PCB_VIA')
    assert probe(loaded, actual)[0] is None
    assert path.read_bytes() == before

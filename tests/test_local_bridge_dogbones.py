"""Native local-launch geometry, independent reproof, and immutable planning."""
import time
import pcbnew
import pytest
import cec_fr as fr
import cec_fab_profile as fab
import cec_certificate_repair as repair


def fixture(*, quarter=0, back=False, size=.3, profile=True):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    if profile:
        props = board.GetProperties()
        props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
        board.SetProperties(props)
    net = pcbnew.NETINFO_ITEM(board, '/RENAMED_SIGNAL'); board.Add(net)
    other = pcbnew.NETINFO_ITEM(board, '/OTHER'); board.Add(other)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference('RENAMED_CELL'); board.Add(fp)
    pad = pcbnew.PAD(fp); pad.SetNumber('arbitrary')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetPosition(pcbnew.VECTOR2I_MM(30, 40)); pad.SetSize(pcbnew.VECTOR2I_MM(size, size))
    pad.SetNet(net); pad.SetOrientationDegrees(quarter*90)
    layer = pcbnew.B_Cu if back else pcbnew.F_Cu
    layers = pcbnew.LSET(); layers.AddLayer(layer); pad.SetLayerSet(layers); fp.Add(pad)
    settings = board.GetDesignSettings()
    settings.m_HoleToHoleMin = pcbnew.FromMM(.2)
    # This fixture explicitly exercises a fine native POFV process, rather
    # than relying on local custom rules to override stock absolute floors.
    settings.m_ViasMinSize = pcbnew.FromMM(.3)
    settings.m_MinThroughDrill = pcbnew.FromMM(.2)
    settings.m_ViasMinAnnularWidth = pcbnew.FromMM(.05)
    return board, pad, net.GetNetCode(), layer


def seats(board, pad, nc, layer, **kwargs):
    defaults = dict(profile=fab.PROFILES.get(fab.board_profile_name(board)),
        leg_ok=lambda *a: True, limit=8, offsets_mm=(.5,), angles_deg=(0,),
        foreign_cache={}, width=pcbnew.FromMM(.2))
    defaults.update(kwargs)
    return fr._local_pofv_dogbone_seats(board, pad.GetPosition(), layer,
        nc=nc, clearance_nm=pcbnew.FromMM(.2), **defaults)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_native_owned_seat_survives_independent_live_reproof(tmp_path, quarter, back):
    board, pad, nc, layer = fixture(quarter=quarter, back=back)
    rows = seats(board,pad,nc,layer,angles_deg=(quarter*90,))
    assert len(rows)==1 and not list(board.GetTracks()) and not list(board.Groups())
    geometry = repair._lay_ops(board,rows[0][1],nc,lock=False)
    assert geometry['tracks']==geometry['vias']==1
    via = next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    assert fab.local_pofv_via_decision(board,via)[0]
    assert fr.group_local_pofv_signal_vias(board,[via])['added_vias']==1
    path=tmp_path/'renamed.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    saved=pcbnew.LoadBoard(str(path))
    saved_via=next(t for t in saved.GetTracks() if t.GetClass()=='PCB_VIA')
    assert fab.local_pofv_via_decision(saved,saved_via)[0]


@pytest.mark.parametrize('kwargs', [dict(profile=False),dict(size=1.0)])
def test_profile_and_partial_land_overlap_fail_closed(kwargs):
    board,pad,nc,layer=fixture(**kwargs)
    assert not seats(board,pad,nc,layer)
    assert not list(board.GetTracks())


@pytest.mark.parametrize('block_layer',[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
def test_actual_foreign_copper_on_any_layer_blocks_barrel(block_layer):
    board,pad,nc,layer=fixture()
    track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('/OTHER'))
    track.SetStart(pcbnew.VECTOR2I_MM(30.5,39));track.SetEnd(pcbnew.VECTOR2I_MM(30.5,41))
    track.SetWidth(pcbnew.FromMM(.2));track.SetLayer(block_layer);board.Add(track)
    assert not seats(board,pad,nc,layer)
    assert len(list(board.GetTracks()))==1


def test_actual_reserved_pour_outline_is_not_antipadded():
    board,pad,nc,layer=fixture()
    zone=pcbnew.ZONE(board);zone.SetLayer(layer);zone.SetNet(board.FindNet('/OTHER'))
    zone.SetZoneName('pourfirst:reserved');zone.Outline().NewOutline()
    for x,y in [(30.4,39.8),(30.8,39.8),(30.8,40.2),(30.4,40.2)]:
        zone.Outline().Append(round(x*1e6),round(y*1e6))
    board.Add(zone)
    assert not seats(board,pad,nc,layer)


def test_same_net_hole_spacing_is_retained():
    board,pad,nc,layer=fixture()
    via=pcbnew.PCB_VIA(board);via.SetNetCode(nc)
    via.SetPosition(pcbnew.VECTOR2I_MM(30.6,40));via.SetWidth(pcbnew.FromMM(.5))
    via.SetDrill(pcbnew.FromMM(.3));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(via)
    assert not seats(board,pad,nc,layer)


@pytest.mark.parametrize('kwargs', [dict(limit=0),dict(offsets_mm=(2.,)),
    dict(angles_deg=(30,)),dict(max_length_nm=400000),
    dict(deadline_monotonic=0.),dict(width=1000000),dict(leg_ok=lambda *a:False)])
def test_bounded_domain_does_not_weaken_limits(kwargs):
    board,pad,nc,layer=fixture()
    assert not seats(board,pad,nc,layer,**kwargs)
    assert not list(board.GetTracks())


def test_bare_origin_and_wrong_layer_have_no_owner():
    board,pad,nc,layer=fixture()
    pad.SetNetCode(board.FindNet('/OTHER').GetNetCode())
    assert not seats(board,pad,nc,layer)
    pad.SetNetCode(nc)
    assert not seats(board,pad,nc,pcbnew.B_Cu)


def test_bridge_actually_uses_local_dogbone_tier(monkeypatch):
    board,pad,nc,layer=fixture()
    original=fr._local_pofv_dogbone_seats
    called=[]
    def spy(*args,**kwargs):
        result=original(*args,**kwargs);called.extend(result);return result
    monkeypatch.setattr(fr,'_local_pofv_dogbone_seats',spy)
    # The origin POFV is deliberately blocked; its offset is genuinely legal.
    track=pcbnew.PCB_TRACK(board);track.SetNet(board.FindNet('/OTHER'))
    track.SetStart(pcbnew.VECTOR2I_MM(30,39.8));track.SetEnd(pcbnew.VECTOR2I_MM(30,40.2))
    track.SetWidth(pcbnew.FromMM(.2));track.SetLayer(pcbnew.In2_Cu);board.Add(track)
    ops=fr._lastmile_bridge(board,(30000000,40000000),{layer},
        (35000000,40000000),{layer,pcbnew.In2_Cu},200000,nc,[pcbnew.In2_Cu],200000,
        leg_ok=lambda *a:True,allow_maze=False,allow_lattice=False,
        seat_limit=1,seat_offsets_mm=(.5,),seat_angles_deg=(0,))
    assert called and ops and any(op[0]=='via' and op[3]<.5 for op in ops)
    assert len(list(board.GetTracks()))==1

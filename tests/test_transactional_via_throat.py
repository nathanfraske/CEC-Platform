"""A generated dogbone must not require ownership from its future commit."""
import pcbnew
import pytest
import cec_fr as fr
from test_lastmile import _board


def scene(offset=0, name='/UNRELATED_RAIL', profile=True):
    board = _board([(5+offset, 5, name), (10+offset, 5, name)],
                   edge=(offset, 0, 16+offset, 12))
    board.SetCopperLayerCount(6)
    if profile:
        props = board.GetProperties()
        props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
        board.SetProperties(props)
    for footprint in board.GetFootprints():
        footprint.SetReference('PART_'+str(footprint.GetPosition().x))
        for pad in footprint.Pads():
            pad.SetNumber('1')
            # Too small for even the minimum POFV land: exercise a real
            # dogbone instead of the zero-length via-in-pad fast path.
            pad.SetSize(pcbnew.VECTOR2I_MM(.3, .3))
    board.BuildConnectivity()
    return board


def resolver(_name):
    return dict(track_width=1., clearance=.2,
                via_diameter=.8, via_drill=.4)


@pytest.mark.parametrize('offset,name', [(0, '/ONE'), (30, 'OTHER_SUPPLY')])
def test_live_bridge_commits_then_survives_reload(tmp_path, offset, name):
    board = scene(offset, name)
    result = fr.synthesize_lastmile(
        board, max_mm=8., min_w=.2, clearance=0.,
        netclass_resolver=resolver, include_nets=[name], prefer_bridge=True,
        attempts_per_pair=2, maze_max_mm=0., bridge_fast=True)
    assert result['closed'] == 1, result
    assert result['endpoint_neckdown']['tracks'] > 0
    assert result['local_pofv_signal_vias']['added_vias'] > 0
    path = tmp_path/'arbitrary.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    loaded = pcbnew.LoadBoard(str(path))
    loaded.BuildConnectivity()
    assert fr.net_connectivity_component_count(
        loaded, loaded.GetNetcodeFromNetname(name)) == 1
    narrow = [t for t in loaded.GetTracks() if t.GetClass() == 'PCB_TRACK'
              and t.GetWidth() < pcbnew.FromMM(1.)]
    accepted, rejected = fr._qualified_endpoint_neckdown_tracks(
        loaded, narrow, pcbnew.FromMM(1.))
    assert not rejected
    assert len(accepted) == len(narrow)
    recovered = fr.reconcile_endpoint_neckdown_groups(
        loaded, netclass_resolver=resolver)
    assert recovered['tracks'] == len(narrow), recovered
    assert recovered['recovered'] == 0
    group = next(g for g in loaded.Groups() if g.GetName() == fr.ENDPOINT_NECKDOWN_GROUP)
    for item in narrow:
        group.RemoveItem(item)
    recovered = fr.reconcile_endpoint_neckdown_groups(loaded, netclass_resolver=resolver)
    assert recovered['recovered'] == len(narrow), recovered


def add_plan(board, *, length=1., continuation=1.):
    source = min((p for fp in board.GetFootprints() for p in fp.Pads()),
                 key=lambda p: p.GetPosition().x)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(5+length, 5))
    via.SetWidth(pcbnew.FromMM(.8)); via.SetDrill(pcbnew.FromMM(.4))
    via.SetNet(source.GetNet()); board.Add(via)
    neck = pcbnew.PCB_TRACK(board)
    neck.SetStart(source.GetPosition()); neck.SetEnd(via.GetPosition())
    neck.SetWidth(pcbnew.FromMM(.2)); neck.SetLayer(pcbnew.F_Cu)
    neck.SetNet(source.GetNet()); board.Add(neck)
    trunk = pcbnew.PCB_TRACK(board)
    trunk.SetStart(via.GetPosition()); trunk.SetEnd(pcbnew.VECTOR2I_MM(9, 5))
    trunk.SetWidth(pcbnew.FromMM(continuation)); trunk.SetLayer(pcbnew.B_Cu)
    trunk.SetNet(source.GetNet()); board.Add(trunk)
    board.BuildConnectivity()
    return via, neck


@pytest.mark.parametrize('profile,length,continuation,expected', [
    (True, 1., 1., True), (False, 1., 1., False),
    (True, 1., .2, False), (True, 1.6, 1., False)])
def test_provisional_identity_is_not_a_width_or_locality_waiver(
        profile, length, continuation, expected):
    board = scene(profile=profile)
    via, neck = add_plan(board, length=length, continuation=continuation)
    before = [(g.GetName(), g.m_Uuid.AsString()) for g in board.Groups()]
    accepted, rejected = fr._qualified_endpoint_neckdown_tracks(
        board, [neck], pcbnew.FromMM(1.),
        provisional_via_ids={via.m_Uuid.AsString()})
    assert bool(accepted) is expected, rejected
    assert bool(rejected) is not expected
    assert [(g.GetName(), g.m_Uuid.AsString()) for g in board.Groups()] == before
    # Without either native group ownership or explicit transaction scope,
    # the identical object is still not an owned layer-transition exception.
    assert not fr._qualified_endpoint_neckdown_tracks(
        board, [neck], pcbnew.FromMM(1.))[0]


def test_partial_neckdown_refusal_leaves_no_groups_or_copper(monkeypatch):
    board = scene()
    # One legal escape and one overlong escape share a complete bridge. The
    # electrical graph connects, but the whole transaction must roll back.
    def bridge(*args, **kwargs):
        vec = pcbnew.VECTOR2I_MM
        return [('trk', vec(5, 5), vec(6, 5), pcbnew.FromMM(.2), pcbnew.F_Cu),
                ('via', vec(6, 5), .4, .8),
                ('trk', vec(6, 5), vec(8.4, 5), pcbnew.FromMM(1.), pcbnew.B_Cu),
                ('via', vec(8.4, 5), .4, .8),
                ('trk', vec(8.4, 5), vec(10, 5), pcbnew.FromMM(.2), pcbnew.F_Cu)]
    monkeypatch.setattr(fr, '_lastmile_bridge', bridge)
    result = fr.synthesize_lastmile(
        board, max_mm=8., min_w=.2, clearance=0., netclass_resolver=resolver,
        prefer_bridge=True, attempts_per_pair=1, maze_max_mm=0.)
    assert result['closed'] == 0
    assert any(r['reason'] == 'unqualified_generated_endpoint_neckdown'
               for r in result['refused_details'])
    assert not list(board.GetTracks())
    assert not list(board.Groups())
    assert result['endpoint_neckdown'] is None

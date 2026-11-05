"""Layer-accurate frozen-power checks and physical-vs-search authority."""
from copy import deepcopy
import json
import pcbnew
import pytest
import cec_constraints as rules
import cec_fr
import cec_power_guard_geometry as geometry


def board_fixture():
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    for name in ('PWR','SIGNAL','GND'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    return board


def state(layer='In3.Cu',polygon=None):
    return dict(placement_scope='complete',frozen_nets=['PWR'],corridors=[],
                pours=[dict(net='PWR',layer=layer,
                    polygon=polygon or [[4,4],[6,4],[6,6],[4,6]])])


def track(board,layer):
    t=pcbnew.PCB_TRACK(board);t.SetLayer(layer);t.SetNet(board.FindNet('SIGNAL'))
    t.SetStart(pcbnew.VECTOR2I_MM(3,5));t.SetEnd(pcbnew.VECTOR2I_MM(7,5))
    t.SetWidth(pcbnew.FromMM(.2));board.Add(t)
    return t


@pytest.mark.parametrize('layer_name',['F.Cu','In1.Cu','In2.Cu','In3.Cu','In4.Cu','B.Cu'])
def test_resolves_every_enabled_layer_without_top_fallback(layer_name):
    board=board_fixture()
    assert geometry.copper_layer(board,layer_name)==board.GetLayerID(layer_name)


def test_display_alias_supported_unknown_and_disabled_fail_closed():
    board=board_fixture();layer=board.GetLayerID('In3.Cu');board.SetLayerName(layer,'CUSTOM_POWER')
    assert geometry.copper_layer(board,'CUSTOM_POWER')==layer
    assert geometry.copper_layer(board,'In3.Cu')==layer
    for name in ('F.Mask','not-a-layer','In8.Cu'):
        with pytest.raises(ValueError):geometry.copper_layer(board,name)


@pytest.mark.parametrize('trace_layer,expected',[('F.Cu',0),('In2.Cu',0),('In3.Cu',1),('B.Cu',0)])
def test_checker_counts_same_layer_only_and_still_counts_through_via(tmp_path,monkeypatch,trace_layer,expected):
    board=board_fixture();track(board,board.GetLayerID(trace_layer))
    v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(5,5));v.SetWidth(pcbnew.FromMM(.6))
    v.SetDrill(pcbnew.FromMM(.3));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetNet(board.FindNet('GND'));board.Add(v)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    monkeypatch.delenv('CEC_POURFIRST_STATE',raising=False)
    path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state()))
    result=rules.foreign_on_pour_summary(str(path))
    assert result['n_tracks']==expected and result['n_vias']==1
    assert {r['layer'] for r in rules.high_current_pour_regions(str(path))}=={'In3.Cu'}


def test_clipped_corridors_cannot_authorize_via_through_actual_frozen_polygon(monkeypatch):
    board=board_fixture();s=state();original=deepcopy(s)
    monkeypatch.setattr(cec_fr,'_pourfirst_state',lambda:s)
    report={}
    assert not cec_fr._via_spot_clear(board,pcbnew.VECTOR2I_MM(5,5),pcbnew.FromMM(.6),
        pcbnew.FromMM(.2),{board.FindNet('GND').GetNetCode()},drill_nm=pcbnew.FromMM(.3),
        net_code=board.FindNet('GND').GetNetCode(),report=report)
    assert report['layer']=='In3.Cu' and report['blockers'][0]['net']=='PWR'
    assert s==original
    # A same-net rail transition is not a foreign incursion.
    assert cec_fr._via_spot_clear(board,pcbnew.VECTOR2I_MM(5,5),pcbnew.FromMM(.6),
        pcbnew.FromMM(.2),{board.FindNet('PWR').GetNetCode()},drill_nm=pcbnew.FromMM(.3),
        net_code=board.FindNet('PWR').GetNetCode())


def test_hook_pocket_is_not_a_phantom_slab(monkeypatch):
    board=board_fixture()
    s=state(polygon=[[1,1],[6,1],[6,2],[2,2],[2,5],[6,5],[6,6],[1,6]])
    monkeypatch.setattr(cec_fr,'_pourfirst_state',lambda:s)
    assert cec_fr._via_spot_clear(board,pcbnew.VECTOR2I_MM(4,3.5),pcbnew.FromMM(.6),
        pcbnew.FromMM(.2),{board.FindNet('GND').GetNetCode()},drill_nm=pcbnew.FromMM(.3),
        net_code=board.FindNet('GND').GetNetCode())


@pytest.mark.parametrize('layer,expected',[('F.Cu',True),('In3.Cu',False)])
def test_additive_track_guard_uses_same_full_geometry_on_correct_layer(monkeypatch,layer,expected):
    board=board_fixture();monkeypatch.setattr(cec_fr,'_pourfirst_state',lambda:state())
    net=board.FindNet('SIGNAL').GetNetCode()
    path=cec_fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I_MM(4.5,5),
        pcbnew.VECTOR2I_MM(5.5,5),pcbnew.FromMM(.2),board.GetLayerID(layer),
        pcbnew.FromMM(.2),net,lambda *a:True,allow_maze=False)
    assert bool(path)==expected


@pytest.mark.parametrize('broken',[{}, {'net':'PWR','layer':'In3.Cu'},
    {'net':'PWR','layer':'In3.Cu','polygon':[[0,0],[2,0],[1,2]]}])
def test_incomplete_or_non_manhattan_frozen_authority_is_not_a_waiver(broken):
    s=state();s['pours']=[broken]
    with pytest.raises(ValueError):geometry.reservations(s)


def test_anchor_search_hint_semantics_and_cache_mutation_safety():
    hints=dict(corridors=[dict(net='PWR',layer='F.Cu',x0=0,y0=0,x1=1,y1=1)])
    assert geometry.reservations(hints)==hints['corridors']
    s=state();first=geometry.reservations(s)
    s['pours'][0]['polygon']=[[8,8],[10,8],[10,10],[8,10]]
    second=geometry.reservations(s)
    assert first!=second
    first[0]['net']='edited';assert geometry.reservations(state())[0]['net']=='PWR'

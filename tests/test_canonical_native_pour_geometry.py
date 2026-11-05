"""Native laid geometry survives explicit empty execution ownership lists."""
import json
import pcbnew
import pytest
import cec_constraints as constraints
import cec_fr as fr


def fixture(tmp_path, *, name='independently_renamed_copper', layer=pcbnew.F_Cu):
    board=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(board,'/independently_named_force_HI');board.Add(net)
    zone=pcbnew.ZONE(board);zone.SetNet(net);zone.SetLayer(layer);zone.SetZoneName(name)
    polygon=[[1,1],[8,1],[8,3],[3,3],[3,8],[1,8]]
    zone.Outline().NewOutline()
    for x,y in polygon:zone.Outline().Append(round(x*1e6),round(y*1e6))
    board.Add(zone)
    path=tmp_path/'unrelated_source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    return board,zone,path,polygon


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('state',[None,dict(placement_scope='complete',frozen_nets=[],pours=[])])
def test_actual_renamed_concave_pour_is_recovered_not_invented(tmp_path,monkeypatch,layer,state):
    board,zone,path,polygon=fixture(tmp_path,layer=layer,
        name='orthofill:independent_source' if state is None else 'independently_renamed_copper')
    if state is not None:path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    monkeypatch.delenv('CEC_POURFIRST_STATE',raising=False)
    def never_derive(*a,**kw):raise AssertionError('native copper must not become a pad-derived slab')
    monkeypatch.setattr(fr,'derive_power_pours',never_derive)
    rows=constraints.canonical_high_current_pours(str(path),board=board)
    assert len(rows)==1 and rows[0]['polygon']==polygon
    assert rows[0]['zone_uuid']==zone.m_Uuid.AsString()
    assert not rows[0]['capacity_qualified']
    regions=constraints._exact_pour_rectangles(rows)
    assert regions and not any(r['x0']<=6<=r['x1'] and r['y0']<=6<=r['y1'] for r in regions)


@pytest.mark.parametrize('state',[
    dict(placement_scope='partial',frozen_nets=[],pours=[]),
    dict(placement_scope='complete',frozen_nets=['/required_HI'],pours=[]),
    dict(placement_scope='complete',frozen_nets=[],pours=[dict(net='/required_HI')]),
    dict(placement_scope='complete'),
])
def test_missing_declared_frozen_authority_cannot_be_recovered_away(tmp_path,monkeypatch,state):
    board,zone,path,_=fixture(tmp_path)
    path.with_suffix('.pourfirst-state.json').write_text(json.dumps(state))
    monkeypatch.delenv('CEC_POURFIRST_STATE',raising=False)
    with pytest.raises(ValueError):constraints.canonical_high_current_pours(str(path),board=board)


def test_explicit_empty_state_without_native_copper_never_derives_slab(tmp_path,monkeypatch):
    board=pcbnew.BOARD();path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    path.with_suffix('.pourfirst-state.json').write_text(json.dumps(dict(
        placement_scope='complete',frozen_nets=[],pours=[])))
    monkeypatch.delenv('CEC_POURFIRST_STATE',raising=False)
    monkeypatch.setattr(fr,'derive_power_pours',lambda *a,**kw:pytest.fail('no speculative pour allowed'))
    with pytest.raises(ValueError,match='no recoverable native force territory'):
        constraints.canonical_high_current_pours(str(path),board=board)


def test_native_hole_cannot_be_filled_by_outline_recovery(tmp_path,monkeypatch):
    board,zone,path,polygon=fixture(tmp_path,name='orthofill:independent_source')
    zone.Outline().NewHole(0)
    for x,y in [(1.5,1.5),(2.5,1.5),(2.5,2.5),(1.5,2.5)]:
        zone.Outline().Append(round(x*1e6),round(y*1e6),0,0)
    monkeypatch.delenv('CEC_POURFIRST_STATE',raising=False)
    rows=constraints.canonical_high_current_pours(str(path),board=board)
    from shapely.geometry import Polygon,Point
    from shapely.ops import unary_union
    shape=unary_union([Polygon(r['polygon']) for r in rows])
    assert not shape.covers(Point(2,2))
    assert shape.equals(Polygon(polygon,[[(1.5,1.5),(2.5,1.5),(2.5,2.5),(1.5,2.5)]]))
    regions=constraints._exact_pour_rectangles(rows)
    assert not any(r['x0']<=2<=r['x1'] and r['y0']<=2<=r['y1'] for r in regions)

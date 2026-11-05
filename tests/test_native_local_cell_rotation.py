"""Cardinal local poses own exact pad/barrel contacts, never remote leads."""
import pcbnew
import pytest

import cec_native_placement_context as native
from test_native_placement_portals import fixture


def setup():
    b,fp,p,v,net=fixture()
    fp.SetPosition(pcbnew.VECTOR2I_MM(20,20));p.SetPosition(fp.GetPosition())
    t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNet(net);t.SetWidth(200000)
    t.SetStart(p.GetPosition());t.SetEnd(v.GetPosition());b.Add(t)
    return b,fp,p,v,t,net


@pytest.mark.parametrize('turn',[90,180,270])
def test_native_rigid_rotation_carries_dogbone_and_all_barrel_layers(turn):
    b,fp,p,v,t,net=setup()
    before=(tuple(v.GetPosition()),tuple(t.GetEnd()),v.GetDrill(),v.GetWidth(v.TopLayer()))
    layers=list(v.GetLayerSet().Seq());uuids={i.m_Uuid.AsString() for i in b.GetTracks()}
    result=native.rotate_isolated_local_cells(b,{fp.GetReference():turn})
    assert result['rotated_refs']==[fp.GetReference()]
    assert set(result['rotated_conductor_uuids'])==uuids
    assert tuple(v.GetPosition())==tuple(t.GetEnd()) and tuple(p.GetPosition())==tuple(t.GetStart())
    assert tuple(v.GetPosition())!=before[0] and fp.GetOrientationDegrees()%360==turn
    assert (v.GetDrill(),v.GetWidth(v.TopLayer()))==before[2:]
    assert layers==list(v.GetLayerSet().Seq())
    assert uuids=={i.m_Uuid.AsString() for i in b.GetTracks()}
    assert not result['source_items_retired'] and not result['release_authority']


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu])
def test_remote_barrel_contact_on_any_actual_layer_refuses_before_motion(layer):
    b,fp,p,v,t,net=setup()
    remote=pcbnew.PCB_TRACK(b);remote.SetLayer(layer);remote.SetNet(net);remote.SetWidth(200000)
    remote.SetStart(v.GetPosition());remote.SetEnd(pcbnew.VECTOR2I_MM(25,20));b.Add(remote)
    before=(fp.GetOrientationDegrees(),tuple(v.GetPosition()),tuple(t.GetStart()),tuple(t.GetEnd()))
    with pytest.raises(ValueError,match='external_native_local_cell_leads_require_reconstruction'):
        native.rotate_isolated_local_cells(b,{fp.GetReference():180})
    assert before==(fp.GetOrientationDegrees(),tuple(v.GetPosition()),tuple(t.GetStart()),tuple(t.GetEnd()))


def test_shared_source_pad_barrel_never_gets_reassigned_by_rotation():
    b,fp,p,v,t,net=setup();v.SetPosition(p.GetPosition());t.SetEnd(p.GetPosition())
    other=pcbnew.FOOTPRINT(b);other.SetReference('ANOTHER_OWNER');b.Add(other)
    q=pcbnew.PAD(other);q.SetNumber('1');q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    q.SetLayerSet(p.GetLayerSet());q.SetSize(p.GetSize());q.SetPosition(p.GetPosition());q.SetNet(net);other.Add(q)
    with pytest.raises(ValueError,match='shared_native_local_portal_rotation_refused'):
        native.rotate_isolated_local_cells(b,{fp.GetReference():90})
    assert fp.GetOrientationDegrees()==0 and tuple(v.GetPosition())==tuple(p.GetPosition())


@pytest.mark.parametrize('rotations',[{}, {'missing':90}, {'OWNER_OTHER_BOARD':True},
    {'OWNER_OTHER_BOARD':45}, {'OWNER_OTHER_BOARD':90.0}])
def test_unbounded_or_noncardinal_pose_cannot_mutate_native_source(rotations):
    b,fp,p,v,t,net=setup();before=(tuple(p.GetPosition()),tuple(v.GetPosition()))
    with pytest.raises(ValueError):native.rotate_isolated_local_cells(b,rotations)
    assert before==(tuple(p.GetPosition()),tuple(v.GetPosition()))


def test_drilled_footprint_is_not_a_surface_cell_rotation_permission():
    b,fp,p,v,t,net=setup();p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    with pytest.raises(ValueError,match='unlocked_native_surface_local_cell_required'):
        native.rotate_isolated_local_cells(b,{fp.GetReference():90})


def fixed_supply_setup(*, layer=pcbnew.F_Cu, square=False):
    b, fp, ground, via, dogbone, net = setup()
    fp.SetReference('SOURCE_ASSIGNED_PASSIVE')
    rail = pcbnew.NETINFO_ITEM(b, '/UNRELATED_SUPPLY_NAME'); b.Add(rail)
    supply = pcbnew.PAD(fp); supply.SetNumber('FIXED_POSITIVE')
    supply.SetAttribute(pcbnew.PAD_ATTRIB_SMD); supply.SetShape(pcbnew.PAD_SHAPE_RECT)
    supply.SetSize(pcbnew.VECTOR2I_MM(.6, .6 if square else .4))
    supply.SetPosition(pcbnew.VECTOR2I_MM(20, 18)); supply.SetNet(rail)
    layers = pcbnew.LSET(); layers.AddLayer(layer); supply.SetLayerSet(layers); fp.Add(supply)
    ground.SetLayerSet(layers); dogbone.SetLayer(layer); fp.SetLayer(layer)
    trunk = pcbnew.PCB_TRACK(b); trunk.SetLayer(layer); trunk.SetNet(rail); trunk.SetWidth(200000)
    trunk.SetStart(pcbnew.VECTOR2I_MM(15, 18)); trunk.SetEnd(supply.GetPosition()); b.Add(trunk)
    return b, fp, supply, ground, via, dogbone, trunk, rail


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.B_Cu])
@pytest.mark.parametrize('turn', [90, 180, 270])
def test_exact_stationary_supply_land_preserves_external_trunk_while_ground_moves(layer, turn):
    b, fp, supply, ground, via, dogbone, trunk, _ = fixed_supply_setup(layer=layer, square=turn!=180)
    prior_trunk = (tuple(trunk.GetStart()), tuple(trunk.GetEnd()), trunk.GetLayer(), trunk.GetWidth())
    prior_supply = native._native_stationary_land(supply, __import__('time').monotonic()+2.)
    original_ground = tuple(ground.GetPosition())
    old_ids = {t.m_Uuid.AsString() for t in b.GetTracks()}
    result = native.rotate_isolated_local_cells(b, {fp.GetReference():turn},
                  pivot_pad_uuids={fp.GetReference():supply.m_Uuid.AsString()})
    assert prior_supply == native._native_stationary_land(supply, __import__('time').monotonic()+2.)
    assert prior_trunk == (tuple(trunk.GetStart()), tuple(trunk.GetEnd()), trunk.GetLayer(), trunk.GetWidth())
    assert tuple(ground.GetPosition()) != original_ground
    assert tuple(dogbone.GetStart()) == tuple(ground.GetPosition())
    assert tuple(dogbone.GetEnd()) == tuple(via.GetPosition())
    assert old_ids == {t.m_Uuid.AsString() for t in b.GetTracks()}
    assert result['exact_stationary_pivot_land_replay'][fp.GetReference()] == prior_supply
    assert not result['source_items_retired'] and not result['remote_copper_stretched']


def test_nonsquare_quarter_turn_cannot_change_fixed_trunk_terminal_copper():
    b, fp, supply, _, _, _, _, _ = fixed_supply_setup()
    before = (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(supply.GetPosition()))
    with pytest.raises(ValueError, match='local_cell_pivot_copper_not_exactly_stationary'):
        native.rotate_isolated_local_cells(b, {fp.GetReference():90},
                  pivot_pad_uuids={fp.GetReference():supply.m_Uuid.AsString()})
    assert before == (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(supply.GetPosition()))


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu])
def test_fixed_supply_does_not_exempt_moving_ground_barrel_remote_leads(layer):
    b, fp, supply, _, via, _, _, _ = fixed_supply_setup()
    remote = pcbnew.PCB_TRACK(b); remote.SetLayer(layer); remote.SetNetCode(via.GetNetCode())
    remote.SetWidth(200000); remote.SetStart(via.GetPosition())
    remote.SetEnd(pcbnew.VECTOR2I_MM(26, 20)); b.Add(remote)
    before = (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(via.GetPosition()))
    with pytest.raises(ValueError, match='external_native_local_cell_leads_require_reconstruction'):
        native.rotate_isolated_local_cells(b, {fp.GetReference():180},
                  pivot_pad_uuids={fp.GetReference():supply.m_Uuid.AsString()})
    assert before == (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(via.GetPosition()))


def test_exact_pivot_barrel_retains_its_external_inner_layer_trunk():
    b, fp, supply, _, _, _, _, rail = fixed_supply_setup()
    fixed = pcbnew.PCB_VIA(b); fixed.SetNet(rail); fixed.SetPosition(supply.GetPosition())
    fixed.SetWidth(600000); fixed.SetDrill(300000)
    fixed.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(fixed)
    remote = pcbnew.PCB_TRACK(b); remote.SetLayer(pcbnew.In2_Cu); remote.SetNet(rail)
    remote.SetWidth(200000); remote.SetStart(fixed.GetPosition()); remote.SetEnd(pcbnew.VECTOR2I_MM(26,18)); b.Add(remote)
    before = (tuple(fixed.GetPosition()), tuple(remote.GetStart()), tuple(remote.GetEnd()))
    result = native.rotate_isolated_local_cells(b, {fp.GetReference():180},
                  pivot_pad_uuids={fp.GetReference():supply.m_Uuid.AsString()})
    assert before == (tuple(fixed.GetPosition()), tuple(remote.GetStart()), tuple(remote.GetEnd()))
    assert fixed.m_Uuid.AsString() in result['rotated_conductor_uuids']


@pytest.mark.parametrize('fault', ['foreign_uuid', 'empty_uuid', 'unknown_ref', 'wrong_type', 'offset', 'custom_shape'])
def test_invalid_fixed_land_scope_or_geometry_refuses_before_native_motion(fault):
    b, fp, supply, _, via, _, _, _ = fixed_supply_setup()
    pivots = {fp.GetReference():supply.m_Uuid.AsString()}
    if fault == 'foreign_uuid': pivots[fp.GetReference()] = pcbnew.KIID().AsString()
    elif fault == 'empty_uuid': pivots[fp.GetReference()] = ''
    elif fault == 'unknown_ref': pivots = {'OTHER_BOARD_REF': supply.m_Uuid.AsString()}
    elif fault == 'wrong_type': pivots[fp.GetReference()] = True
    elif fault == 'offset': supply.SetOffset(pcbnew.VECTOR2I(10000,0))
    else: supply.SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    before = (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(via.GetPosition()))
    with pytest.raises(ValueError):
        native.rotate_isolated_local_cells(b, {fp.GetReference():180}, pivot_pad_uuids=pivots)
    assert before == (tuple(fp.GetPosition()), fp.GetOrientationDegrees(), tuple(via.GetPosition()))

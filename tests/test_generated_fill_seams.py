import pcbnew
import pytest
from shapely.geometry import box, Polygon
from shapely.ops import unary_union
import cec_fr
import cec_generated_fill_seams as seams


def zone(board, name, shape, *, net='arbitrary-rail', layer=pcbnew.B_Cu, priority=2):
    found=board.FindNet(net)
    if found is None:
        found=pcbnew.NETINFO_ITEM(board,net);board.Add(found)
    result=pcbnew.ZONE(board);result.SetNet(found);result.SetLayer(layer)
    result.SetZoneName(name);result.SetAssignedPriority(priority)
    result.SetMinThickness(pcbnew.FromMM(.25))
    result.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    assert cec_fr._replace_zone_outline(result,shape)
    board.Add(result)
    return result


def fixture():
    board=pcbnew.BOARD()
    parent=zone(board,'pourplan:arbitrary',box(0,0,5,10))
    patch=zone(board,'orthofill:arbitrary',box(5,0,5.098,10),priority=9)
    return board,parent,patch


def test_thin_strip_merges_without_changing_union_and_is_idempotent():
    board,parent,patch=fixture()
    intended=unary_union([cec_fr._zone_outline_geometry(z) for z in board.Zones()])
    result=seams.coalesce(board,managed_nets={'arbitrary-rail'})
    assert result['merged_count']==1
    assert len(list(board.Zones()))==1
    assert cec_fr._zone_outline_geometry(parent).equals(intended)
    assert parent.GetAssignedPriority()==2
    assert seams.coalesce(board,managed_nets={'arbitrary-rail'})['merged_count']==0


@pytest.mark.parametrize('prefix',[p for p in cec_fr._GENERATED_ZONE_PREFIXES if p!='orthofill:'])
def test_all_materializer_owned_parent_kinds_have_identical_seam_policy(prefix):
    board,parent,patch=fixture()
    parent.SetZoneName(prefix+'unrelated-domain')
    intended=unary_union([cec_fr._zone_outline_geometry(z) for z in board.Zones()])
    result=seams.coalesce(board,managed_nets={'arbitrary-rail'})
    assert result['merged_count']==1
    assert result['merged'][0]['patch_bounds_mm']==[5.,0.,5.098,10.]
    assert cec_fr._zone_outline_geometry(parent).equals(intended)


@pytest.mark.parametrize('change', ['foreign-layer','foreign-net','locked-parent','locked-patch',
    'authored-parent','different-fill','different-clearance','different-minimum','unmanaged',
    'disconnected','foreign-priority','hatch-fill','different-island-area'])
def test_incompatible_or_unauthorized_zones_stay_separate(change):
    board,parent,patch=fixture();managed={'arbitrary-rail'}
    if change=='foreign-layer':patch.SetLayer(pcbnew.F_Cu)
    elif change=='foreign-net':
        net=pcbnew.NETINFO_ITEM(board,'other');board.Add(net);patch.SetNet(net)
    elif change=='locked-parent':parent.SetLocked(True)
    elif change=='locked-patch':patch.SetLocked(True)
    elif change=='authored-parent':parent.SetZoneName('user-pour')
    elif change=='different-fill':patch.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif change=='different-clearance':patch.SetLocalClearance(pcbnew.FromMM(.7))
    elif change=='different-minimum':patch.SetMinThickness(pcbnew.FromMM(.2))
    elif change=='unmanaged':managed={'unrelated'}
    elif change=='disconnected':cec_fr._replace_zone_outline(patch,box(7,0,7.098,10))
    elif change=='foreign-priority':zone(board,'foreign',box(5,1,6,9),net='other',priority=5)
    elif change=='hatch-fill':
        parent.SetFillMode(pcbnew.ZONE_FILL_MODE_HATCH_PATTERN)
        patch.SetFillMode(pcbnew.ZONE_FILL_MODE_HATCH_PATTERN)
    elif change=='different-island-area':patch.SetMinIslandArea(3_000_000_000_000)
    count=len(list(board.Zones()))
    assert seams.coalesce(board,managed_nets=managed)['merged_count']==0
    assert len(list(board.Zones()))==count


def test_interior_hole_and_hook_are_preserved():
    board=pcbnew.BOARD()
    shape=Polygon([(0,0),(6,0),(6,2),(3,2),(3,8),(0,8)],
                  [[(1,1),(1,2),(2,2),(2,1)]])
    parent=zone(board,'pourplan:arbitrary',shape)
    patch=zone(board,'orthofill:arbitrary',box(0,8,3,8.098),priority=4)
    intended=shape.union(cec_fr._zone_outline_geometry(patch))
    assert seams.coalesce(board,managed_nets={'arbitrary-rail'})['merged_count']==1
    assert cec_fr._zone_outline_geometry(parent).equals(intended)


def test_materializer_invokes_seam_consolidation():
    from unittest.mock import patch
    board=pcbnew.BOARD()
    net=pcbnew.NETINFO_ITEM(board,'arbitrary-rail');board.Add(net)
    def regularize(board,parents,**kwargs):
        extra=zone(board,'orthofill:arbitrary',box(5,0,5.098,10),priority=9)
        extra.SetLocalClearance(parents[0].GetLocalClearance())
        extra.SetThermalReliefGap(parents[0].GetThermalReliefGap())
        extra.SetThermalReliefSpokeWidth(parents[0].GetThermalReliefSpokeWidth())
        extra.SetIslandRemovalMode(parents[0].GetIslandRemovalMode())
    with patch.object(cec_fr,'regularize_power_pour_boundaries',side_effect=regularize):
        evidence={}
        parents=cec_fr.add_power_pours(board,[dict(net='arbitrary-rail',layer='B.Cu',
            polygon=[(0,0),(5,0),(5,10),(0,10)])],evidence=evidence)
    assert len(parents)==1 and len(list(board.Zones()))==1
    assert cec_fr._zone_outline_geometry(parents[0]).equals(box(0,0,5.098,10))
    assert evidence['generated_fill_seams']['merged'][0]['patch_bounds_mm']==[5.,0.,5.098,10.]

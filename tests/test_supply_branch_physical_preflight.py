"""A lower primitive-bend count is not actual copper-polish progress."""
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
from test_redundant_supply_branch_sweep import fixture,_check_refusal_order


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_hidden_duplicate_corner_cut_is_rejected_before_expensive_current_receiving(tmp_path,quarter,mirror,face):
    source,ids,main,catalog=fixture(tmp_path,quarter,mirror,face);b=pcbnew.LoadBoard(str(source))
    selected=[t for t in b.GetTracks() if force._uid(t) in ids]
    boxes=[t.GetBoundingBox() for t in selected]
    x0=min(q.GetX() for q in boxes)-500000;y0=min(q.GetY() for q in boxes)-500000
    x1=max(q.GetRight() for q in boxes)+500000;y1=max(q.GetBottom() for q in boxes)+500000
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):poly.Append(x,y)
    zone=pcbnew.ZONE(b);zone.SetLayer(face);zone.SetNet(selected[0].GetNet());b.Add(zone)
    outline=poly.CloneDropTriangulation();zone.SetOutline(outline);outline.thisown=False
    zone.SetFilledPolysList(face,poly);zone.SetIsFilled(True)
    field._save_field_snapshot(b,source);original=source.read_bytes()
    got=_check_refusal_order(tmp_path,source,sorted(ids),catalog,should_fund=False)
    trial=got['attempts'][0]['causal_tail_trials'][0]['saved_geometry_preflight']
    assert trial['actual_native_material_observation']['positive_material_removed'] is False
    assert got['attempts'][0]['refusal']=='only_representation_changed_not_physical_polish'
    assert not trial['independent_current_receiving_run'] and source.read_bytes()==original

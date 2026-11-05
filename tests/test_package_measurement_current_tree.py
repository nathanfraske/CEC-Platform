"""Manufacturer-typed package input aliases remain nonload, never power credit."""
import time
import pytest
import pcbnew
import cec_force_current as force
import cec_measurement_current_branch as branch
import cec_measurement_leaf as leaf
import cec_field_coupling as field
from cec_native_items import discard_items
from test_measurement_input_island import native_island


def fixture(tmp_path,quarter=0):
    b,root,aux,local,tap,xy=native_island(quarter)
    aux.SetOrientationDegrees(quarter*90)
    tap.SetSize(pcbnew.VECTOR2I_MM(2.5,2.5))
    # These are actual source/sink authority lands, not label/name matching.
    sink=pcbnew.FOOTPRINT(b);sink.SetReference('OTHER_LOAD');b.Add(sink)
    pad=pcbnew.PAD(sink);pad.SetNumber('x');pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetNet(root.GetNet());pad.SetPosition(xy((20,20)));sink.Add(pad)
    main=pcbnew.PCB_TRACK(b);main.SetStart(tap.GetPosition());main.SetEnd(pad.GetPosition())
    main.SetLayer(pcbnew.F_Cu);main.SetWidth(2000000);main.SetNet(root.GetNet());b.Add(main)
    route=pcbnew.PCB_TRACK(b);route.SetStart(root.GetPosition());route.SetEnd(tap.GetPosition())
    route.SetLayer(pcbnew.F_Cu);route.SetWidth(250000);route.SetNet(root.GetNet());b.Add(route)
    source=tmp_path/'renamed-native-tree.kicad_pcb';field._save_field_snapshot(b,source)
    domain=dict(complete=True,source_refs=[tap.GetParentFootprint().GetReference()],
        sink_refs=['OTHER_LOAD'],authority_refs=[tap.GetParentFootprint().GetReference(),'OTHER_LOAD'])
    return source,b,root,aux,local,tap,route,main,domain,xy


@pytest.mark.parametrize('quarter',range(4))
def test_positive_renamed_rotated_tree_preserves_current_terminals(tmp_path,quarter):
    source,b,root,aux,local,tap,route,main,domain,xy=fixture(tmp_path,quarter)
    before=leaf._binding(b)
    q=branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2)
    assert set(q['track_uuids'])=={force._uid(local),force._uid(route)}
    assert q['leaf_pad_uuids']==sorted([force._uid(root),force._uid(aux)])
    assert not q['retirement_authority'] and not q['current_path_qualified']
    r=branch.inventory(b,source,{root.GetNetname():domain})
    assert r['complete'] and set(r['uuids'])==set(q['track_uuids']),r
    assert force._uid(main) not in r['uuids']
    assert r['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert before==leaf._binding(b)


@pytest.mark.parametrize('quarter',range(4))
def test_fully_land_contained_segment_is_not_a_false_graph_loop(tmp_path,quarter):
    source,b,root,aux,local,tap,route,main,domain,xy=fixture(tmp_path,quarter)
    # Split the final .1 mm of the real route INSIDE the source land. Both
    # native caps, not just the centreline endpoints, must fit in the land.
    end=tuple(tap.GetPosition());start=tuple(root.GetPosition())
    vector=(start[0]-end[0],start[1]-end[1]);length=max(abs(x) for x in vector)
    inside=tuple(round(end[i]+vector[i]/length*100000) for i in range(2))
    discard_items(b,[route]);made=[]
    for a,z in ((start,inside),(inside,end)):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        t.SetWidth(250000);t.SetLayer(pcbnew.F_Cu);t.SetNet(root.GetNet());b.Add(t);made.append(t)
    field._save_field_snapshot(b,source);before=leaf._binding(b)
    q=branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2)
    assert q['fully_land_contained_track_uuids']==[force._uid(made[-1])]
    assert set(q['track_uuids'])=={force._uid(local),*(force._uid(t) for t in made)}
    assert force._uid(main) not in q['track_uuids']
    result=branch.inventory(b,source,{root.GetNetname():domain})
    assert result['complete'] and set(result['uuids'])==set(q['track_uuids']),result
    assert result['proofs'][0]['fully_land_contained_track_uuids']==[force._uid(made[-1])]
    assert leaf._binding(b)==before


def test_land_node_collapse_cannot_hide_a_track_cap_outside_the_land(tmp_path):
    source,b,root,aux,local,tap,route,main,domain,xy=fixture(tmp_path)
    centre=tuple(root.GetPosition());half=root.GetSize().x//2
    # Both ends lie just inside the pad; one whole manufactured round cap
    # protrudes outside, so collapsing its graph edge would be unsound.
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I(centre[0]+half-50000,centre[1]))
    t.SetEnd(pcbnew.VECTOR2I(centre[0]+half-25000,centre[1]));t.SetWidth(250000)
    t.SetLayer(pcbnew.F_Cu);t.SetNet(root.GetNet());b.Add(t)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError,match='redundant_loop'):
        branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2)


@pytest.mark.parametrize('fault',['control','unknown_model','dnp','current_terminal','group',
    'buried','wide','remote_contact','second_tap','thin_current_bypass','below_process'])
def test_untyped_external_or_load_bearing_tree_is_never_exempted(tmp_path,fault):
    source,b,root,aux,local,tap,route,main,domain,xy=fixture(tmp_path)
    if fault=='control':aux.SetNumber('3')
    elif fault=='unknown_model':root.GetParentFootprint().SetValue('UNKNOWN')
    elif fault=='dnp':root.GetParentFootprint().SetDNP(True)
    elif fault=='current_terminal':domain['authority_refs'].append(root.GetParentFootprint().GetReference())
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);group.SetName('unrelated_owner');b.Add(group);group.AddItem(local)
    elif fault=='buried':route.SetLayer(pcbnew.In2_Cu)
    elif fault=='wide':route.SetWidth(350001)
    elif fault=='below_process':route.SetWidth(50000)
    else:
        extra=pcbnew.PCB_TRACK(b);extra.SetStart(root.GetPosition())
        extra.SetEnd(xy((20,20)) if fault=='second_tap' else xy((20,15)))
        extra.SetLayer(pcbnew.F_Cu);extra.SetWidth(250000 if fault=='thin_current_bypass' else 1000000)
        extra.SetNet(root.GetNet());b.Add(extra)
    field._save_field_snapshot(b,source);before=leaf._binding(b)
    result=branch.inventory(b,source,{root.GetNetname():domain})
    if fault=='buried':
        # The retained local alias still is a nonload stub; the disconnected
        # buried wire cannot acquire either transition or tree authority.
        assert force._uid(route) not in result['uuids'] and force._uid(main) not in result['uuids']
    else:assert not result['uuids'],result
    assert before==leaf._binding(b)

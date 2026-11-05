"""Typed package aliases may cross only actual qualified exclusive barrels."""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_current_branch as branch
import cec_measurement_leaf as leaf
import cec_field_coupling as field
import cec_fr as fr
import cec_fab_profile as fab
from cec_native_items import discard_items
from test_package_measurement_current_tree import fixture


def layered(tmp_path,quarter=0):
    source,b,root,aux,local,tap,route,main,domain,xy=fixture(tmp_path,quarter)
    discard_items(b,[route]);made=[];vias=[]
    for layer,points in [(pcbnew.F_Cu,[(10,10),(10,12),(12,12)]),
            (pcbnew.In2_Cu,[(12,12),(18,12)]),(pcbnew.F_Cu,[(18,12),(18,10),(20,10)])]:
        for a,z in zip(points,points[1:]):
            t=pcbnew.PCB_TRACK(b);t.SetStart(xy(a));t.SetEnd(xy(z));t.SetLayer(layer)
            t.SetWidth(250000);t.SetNet(root.GetNet());b.Add(t);made.append(t)
    for at in [(12,12),(18,12)]:
        v=pcbnew.PCB_VIA(b);v.SetPosition(xy(at));v.SetWidth(600000);v.SetDrill(300000)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNet(root.GetNet());b.Add(v);vias.append(v)
    field._save_field_snapshot(b,source)
    return source,b,root,local,tap,main,domain,xy,made,vias


@pytest.mark.parametrize('quarter',range(4))
def test_native_rotated_alias_tree_has_real_exclusive_layer_transitions(tmp_path,quarter):
    source,b,root,local,tap,main,domain,xy,made,vias=layered(tmp_path,quarter)
    original=leaf._binding(b)
    q=branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
        allow_layer_branches=True)
    assert set(q['track_uuids'])=={force._uid(t) for t in [local,*made]}
    assert set(q['via_uuids'])=={force._uid(v) for v in vias}
    assert set(q['native_removed_material_uuids'])==set(q['track_uuids']+q['via_uuids'])
    result=branch.inventory(b,source,{root.GetNetname():domain})
    assert result['complete'] and set(result['uuids'])==set(q['track_uuids']),result
    assert force._uid(main) not in result['uuids']
    assert result['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert not q['retirement_authority'] and not q['current_path_qualified']
    assert leaf._binding(b)==original


@pytest.mark.parametrize('fault',['no_transition','missing_barrel','wrong_net','bad_factory',
    'remote_current_contact','barrel_fork','unowned_group','control_alias','wide'])
def test_alias_layer_tree_never_grants_unowned_or_current_carrying_copper_authority(tmp_path,fault):
    source,b,root,local,tap,main,domain,xy,made,vias=layered(tmp_path)
    if fault=='no_transition':made[2].SetLayer(pcbnew.F_Cu)
    elif fault=='missing_barrel':discard_items(b,[vias[0]])
    elif fault=='wrong_net':vias[0].SetNetCode(0)
    elif fault=='bad_factory':vias[0].SetWidth(300000);vias[0].SetDrill(290000)
    elif fault=='unowned_group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.SetName('foreign');g.AddItem(vias[0])
    elif fault=='control_alias':next(p for p in root.GetParentFootprint().Pads() if p.GetNumber()=='8').SetNumber('3')
    elif fault=='wide':made[2].SetWidth(350001)
    else:
        t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetWidth(250000)
        t.SetLayer(pcbnew.F_Cu);t.SetStart(vias[0].GetPosition())
        t.SetEnd(xy((20,20) if fault=='remote_current_contact' else (12,15)));b.Add(t)
    original=leaf._binding(b)
    with pytest.raises(ValueError):
        branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
            allow_layer_branches=True)
    assert leaf._binding(b)==original


def local_process_tree(tmp_path,quarter=0):
    source,b,root,local,tap,main,domain,xy,made,vias=layered(tmp_path,quarter)
    discard_items(b,[*made,*vias]);made=[];vias=[]
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for layer,a,z in [(pcbnew.F_Cu,(10,10),(10,10.75)),
            (pcbnew.In2_Cu,(10,10.75),(18,10.75)),
            (pcbnew.F_Cu,(18,10.75),(19.25,10.75))]:
        t=pcbnew.PCB_TRACK(b);t.SetStart(xy(a));t.SetEnd(xy(z));t.SetLayer(layer)
        t.SetWidth(250000);t.SetNet(root.GetNet());b.Add(t);made.append(t)
    for at,dia,drill in [((10,10.75),350000,250000),((18,10.75),600000,300000)]:
        v=pcbnew.PCB_VIA(b);v.SetPosition(xy(at));v.SetWidth(dia);v.SetDrill(drill)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNet(root.GetNet());b.Add(v);vias.append(v)
    assert fab.local_pofv_via_decision(b,vias[0])[0]
    assert fr.group_local_pofv_signal_vias(b,vias)
    field._save_field_snapshot(b,source)
    return source,b,root,local,tap,main,domain,xy,made,vias


@pytest.mark.parametrize('quarter',range(4))
def test_live_owned_local_barrel_is_classified_without_cut_or_capacity_authority(tmp_path,quarter):
    source,b,root,local,tap,main,domain,xy,made,vias=local_process_tree(tmp_path,quarter)
    b=pcbnew.LoadBoard(str(source));original=leaf._binding(b)
    q=branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
        allow_layer_branches=True)
    assert set(q['track_uuids'])=={force._uid(t) for t in [local,*made]}
    assert set(q['via_uuids'])=={force._uid(v) for v in vias}
    assert not q['retirement_authority'] and not q['current_path_qualified'] and not q['release_authority']
    result=branch.inventory(b,source,{root.GetNetname():domain})
    assert result['complete'] and set(result['uuids'])==set(q['track_uuids']),result
    assert force._uid(main) not in result['uuids']
    assert result['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert leaf._binding(b)==original


@pytest.mark.parametrize('fault',['foreign_owner','track_in_process_group','duplicate_group',
    'no_profile','stale_local_owner','bad_factory','wrong_net','dangling_barrel_branch'])
def test_copied_process_group_never_substitutes_for_live_tree_or_factory_proof(tmp_path,fault):
    source,b,root,local,tap,main,domain,xy,made,vias=local_process_tree(tmp_path)
    group=next(g for g in b.Groups() if g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP)
    if fault=='foreign_owner':group.SetName('unrelated_owner')
    elif fault=='track_in_process_group':group.AddItem(made[0])
    elif fault=='duplicate_group':
        g=pcbnew.PCB_GROUP(b);g.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(g)
    elif fault=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='unknown';b.SetProperties(props)
    elif fault=='stale_local_owner':made[0].SetStart(xy((10,11.5)))
    elif fault=='bad_factory':vias[0].SetDrill(340000)
    elif fault=='wrong_net':vias[0].SetNetCode(0)
    else:
        t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetWidth(250000);t.SetLayer(pcbnew.F_Cu)
        t.SetStart(vias[0].GetPosition());t.SetEnd(xy((12,12)));b.Add(t)
    original=leaf._binding(b)
    with pytest.raises(ValueError):
        branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
            allow_layer_branches=True)
    assert leaf._binding(b)==original


def test_inventory_keeps_the_full_rejected_classifier_stack(tmp_path):
    source,b,root,local,tap,main,domain,xy,made,vias=local_process_tree(tmp_path)
    next(g for g in b.Groups() if g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP).SetName('foreign_owner')
    result=branch.inventory(b,source,{root.GetNetname():domain})
    row=next(r for r in result['refusals'] if r.get('pad_uuid')==force._uid(root))
    assert row['attempts'][1]==dict(stage='native_layer_package_tree',reason='package_input_tree_grouped_material')
    assert [a['stage'] for a in row['attempts']]==['surface_package_tree','native_layer_package_tree',
        'resolved_multiowner_input_tree','exclusive_native_leaf']


@pytest.mark.parametrize('quarter',range(4))
def test_contained_terminal_barrel_needs_no_fictional_surface_track(tmp_path,quarter):
    source,b,root,local,tap,main,domain,xy,made,vias=local_process_tree(tmp_path,quarter)
    discard_items(b,[made[-1]]);vias[-1].SetPosition(xy((20,10.75)))
    made[1].SetEnd(vias[-1].GetPosition());fr.group_local_pofv_signal_vias(b,vias)
    original=leaf._binding(b)
    q=branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
        allow_layer_branches=True)
    assert set(q['track_uuids'])=={force._uid(t) for t in [local,*made[:-1]]}
    assert set(q['via_uuids'])=={force._uid(v) for v in vias}
    result=branch.inventory(b,source,{root.GetNetname():domain})
    assert result['complete'] and set(result['uuids'])==set(q['track_uuids']),result
    assert not q['retirement_authority'] and not q['current_path_qualified']
    assert leaf._binding(b)==original


@pytest.mark.parametrize('fault',['partial_land','no_profile','unused_barrel','extra_layer_fork'])
def test_terminal_barrel_edge_is_never_inferred_from_partial_or_unproved_contact(tmp_path,fault):
    source,b,root,local,tap,main,domain,xy,made,vias=local_process_tree(tmp_path)
    discard_items(b,[made[-1]]);vias[-1].SetPosition(xy((20,10.75)));made[1].SetEnd(vias[-1].GetPosition())
    fr.group_local_pofv_signal_vias(b,vias)
    if fault=='partial_land':
        vias[-1].SetPosition(xy((21.2,10)));made[1].SetEnd(vias[-1].GetPosition())
    elif fault=='no_profile':
        props=b.GetProperties();props['CEC_FAB_PROFILE']='unknown';b.SetProperties(props)
    elif fault=='unused_barrel':made[1].SetLayer(pcbnew.F_Cu)
    else:
        t=pcbnew.PCB_TRACK(b);t.SetStart(vias[-1].GetPosition());t.SetEnd(xy((20,13)))
        t.SetLayer(pcbnew.B_Cu);t.SetWidth(250000);t.SetNet(root.GetNet());b.Add(t)
    original=leaf._binding(b)
    with pytest.raises(ValueError):
        branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
            allow_layer_branches=True)
    assert leaf._binding(b)==original

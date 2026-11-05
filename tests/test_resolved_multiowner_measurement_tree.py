"""Shared input trees require exact, unique source topology for every owner."""
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_measurement_current_branch as branch
import cec_measurement_leaf as leaf
import cec_field_coupling as field
from test_package_measurement_current_tree import fixture


def resolved_tree(tmp_path,quarter=0):
    source,b,root,aux,local,tap,route,main,domain,xy=fixture(tmp_path,quarter)
    hi=pcbnew.NETINFO_ITEM(b,'different-positive-net');b.Add(hi)
    shunt=tap.GetParentFootprint()
    shunt.SetFPID(pcbnew.LIB_ID('Resistor_SMD','R_2512_6332Metric'))
    def land(owner,number,net,at):
        p=pcbnew.PAD(owner);p.SetNumber(number);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetSize(pcbnew.VECTOR2I_MM(.5,.5));p.SetNet(net);p.SetPosition(xy(at));owner.Add(p)
        return p
    land(shunt,'2',hi,(20,7))
    land(root.GetParentFootprint(),'10',hi,(10,6))
    other=pcbnew.FOOTPRINT(b);other.SetReference('UNRELATED_ID');other.SetValue('INA181A2IDBVR');b.Add(other)
    other_input=land(other,'4',root.GetNet(),(10,13))
    positive=land(other,'3',hi,(14,6))
    extra=pcbnew.PCB_TRACK(b);extra.SetStart(other_input.GetPosition());extra.SetEnd(root.GetPosition())
    extra.SetWidth(250000);extra.SetLayer(pcbnew.F_Cu);extra.SetNet(root.GetNet());b.Add(extra)
    field._save_field_snapshot(b,source)
    return source,b,root,aux,tap,main,domain,xy,other_input,positive,extra


@pytest.mark.parametrize('quarter',range(4))
def test_source_resolved_shared_tree_is_current_classification_not_authority(tmp_path,quarter):
    source,b,root,aux,tap,main,domain,xy,other_input,positive,extra=resolved_tree(tmp_path,quarter)
    b=pcbnew.LoadBoard(str(source));before=leaf._binding(b)
    q=branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
        allow_layer_branches=True,allow_resolved_multiowner_inputs=True)
    assert q['scope']=='typed_resolved_multi_package_input_tree_current_only'
    assert set(q['leaf_pad_uuids'])=={force._uid(root),force._uid(aux),force._uid(other_input)}
    assert force._uid(main) not in q['track_uuids']
    assert not any(q[k] for k in ('retirement_authority','release_authority','current_path_qualified','new_numeric_load_assumed'))
    result=branch.inventory(b,source,{root.GetNetname():domain})
    assert result['complete'] and force._uid(extra) in result['uuids'],result
    assert result['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert before==leaf._binding(b)


@pytest.mark.parametrize('fault',['unknown_package','dnp','wrong_input','missing_peer',
    'duplicate_anchor','current_owner','remote_load_contact','wide','same_net_peer'])
def test_shared_name_or_geometry_never_substitutes_for_exact_source_resolution(tmp_path,fault):
    source,b,root,aux,tap,main,domain,xy,other_input,positive,extra=resolved_tree(tmp_path)
    other=other_input.GetParentFootprint()
    if fault=='unknown_package':other.SetValue('UNKNOWN')
    elif fault=='dnp':other.SetDNP(True)
    elif fault=='wrong_input':other_input.SetNumber('5')
    elif fault=='missing_peer':positive.SetNetCode(0)
    elif fault=='same_net_peer':positive.SetNet(root.GetNet())
    elif fault=='current_owner':domain['authority_refs'].append(other.GetReference())
    elif fault=='wide':extra.SetWidth(350001)
    elif fault=='duplicate_anchor':
        shunt=pcbnew.Cast_to_FOOTPRINT(tap.GetParentFootprint().Duplicate(False));shunt.SetReference('SECOND_SOURCE');b.Add(shunt)
        shunt.Move(xy((0,3))-xy((0,0)))
        domain['authority_refs'].append(shunt.GetReference())
    else:
        extra.SetEnd(xy((20,20)))
    before=leaf._binding(b)
    with pytest.raises(ValueError):
        branch._package_input_tree(b,force._uid(root),domain,deadline=time.monotonic()+2,
            allow_layer_branches=True,allow_resolved_multiowner_inputs=True)
    result=branch.inventory(b,source,{root.GetNetname():domain})
    # The existing exclusive-leaf classifier may still prove a genuinely
    # high-impedance *single* input branch. It gains no shared-tree, Kelvin,
    # retirement or capacity authority from that partial proof.
    assert force._uid(main) not in result['uuids'],result
    assert not result['current_path_qualified'] and not result['release_authority']
    assert before==leaf._binding(b)

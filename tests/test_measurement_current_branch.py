"""Nonload input classification cannot turn an underqualified trunk green."""
from unittest import mock
import json
import pcbnew
import pytest
import cec_measurement_current_branch as branch
import cec_current_topology as topology
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
from test_local_branch_access import fixture as original_fixture
from test_force_current import authority
from cec_native_items import discard_items


def fixture(tmp_path):
    source,_,_=original_fixture(tmp_path);b=pcbnew.LoadBoard(str(source));net='MEASURE_MINUS'
    owner=pcbnew.FOOTPRINT(b);owner.SetReference('POWER_SINK');b.Add(owner)
    pad=pcbnew.PAD(owner);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.8,.8));pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetPosition(pcbnew.VECTOR2I_MM(10,18));pad.SetNet(b.FindNet(net));owner.Add(pad)
    t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet(net));t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
    t.SetStart(pcbnew.VECTOR2I_MM(10,13));t.SetEnd(pcbnew.VECTOR2I_MM(10,18));b.Add(t)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    field._save_field_snapshot(b,source)
    domains={net:dict(complete=True,authority_refs=['FIXED','POWER_SINK'],source_refs=['FIXED'],sink_refs=['POWER_SINK'])}
    return source,b,net,domains,force._uid(t)


def test_verified_nonload_leaf_does_not_remove_a_real_underwidth_current_path_failure(tmp_path):
    source,b,net,domains,trunk=fixture(tmp_path);before=source.read_bytes()
    result=branch.inventory(b,source,domains)
    assert result['complete'] and result['uuids'] and trunk not in result['uuids']
    assert result['proofs'][0]['partitions_unchanged_after_collective_removal']
    assert not result['current_path_qualified'] and not result['release_authority']
    with authority(net,amps=3.,source='FIXED',sink='POWER_SINK'):
        check=constraints.CHECKERS['trace-width-high-current'](pcbnew.LoadBoard(str(source)),str(source),{})
    assert check[0] is False
    faults=[r for r in check[2] if r.get('type')=='current_domain_path']
    assert faults and faults[0]['rated_connectivity']['connected'] is False
    assert trunk in {r['uuid'] for r in faults[0]['undersized_segments']}
    assert not set(result['uuids']) & {r['uuid'] for r in faults[0]['undersized_segments']}
    assert source.read_bytes()==before


def test_authored_nonload_role_does_not_inherit_aggregate_rail_width_or_hide_trunk(tmp_path):
    source,b,net,domains,trunk=fixture(tmp_path)
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {
        'classes': [{'name': 'Default', 'track_width': .2},
                    {'name': 'arbitrary_full_load_class', 'track_width': 2.5}],
        'netclass_assignments': {net: ['arbitrary_full_load_class']}}}))
    before=source.read_bytes();project=source.with_suffix('.kicad_pro').read_bytes()
    result=branch.inventory(b,source,domains)
    assert result['complete'] and result['uuids'] and trunk not in result['uuids'],result
    proof=result['proofs'][0]
    assert proof['partitions_unchanged_after_collective_removal']
    assert proof['nonload_width_bases'][0]['width_nm']==200000
    assert proof['nonload_width_bases'][0]['parent_net_class']['track_width']==2.5
    with authority(net,amps=3.,source='FIXED',sink='POWER_SINK'):
        check=constraints.CHECKERS['trace-width-high-current'](b,str(source),{})
    assert check[0] is False
    undersized={r['uuid'] for row in check[2] if row.get('type')=='current_domain_path'
                for r in row['undersized_segments']}
    assert trunk in undersized and not undersized.intersection(result['uuids'])
    assert source.read_bytes()==before and source.with_suffix('.kicad_pro').read_bytes()==project


@pytest.mark.parametrize('fault',['unknown_owner','current_terminal','below_class','native_partition'])
def test_unknown_or_load_bearing_material_has_no_measurement_exemption(tmp_path,fault,monkeypatch):
    source,b,net,domains,trunk=fixture(tmp_path)
    if fault=='unknown_owner':b.FindFootprintByReference('U_RENAMED').SetValue('UNKNOWN')
    elif fault=='current_terminal':domains[net]['authority_refs'].append('U_RENAMED')
    elif fault=='below_class':
        for t in b.GetTracks():
            if t.GetNetname()==net and force._uid(t)!=trunk:t.SetWidth(50000)
    else:
        actual=branch.leaf.plan
        def forged(*args,**kwargs):
            r=actual(*args,**kwargs);r['track_uuids'].append(trunk);return r
        monkeypatch.setattr(branch.leaf,'plan',forged)
    result=branch.inventory(b,source,domains)
    assert not result['uuids']
    if fault!='unknown_owner':assert result['refusals']


def test_branch_classification_is_native_layer_and_identity_independent(tmp_path):
    source,b,net,domains,trunk=fixture(tmp_path)
    expected=branch.inventory(b,source,domains)['uuids'];assert expected
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
        item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source)
    result=branch.inventory(b,source,domains)
    assert result['complete'] and result['uuids']==expected


def native_fixture(tmp_path):
    source,b,net,domains,trunk=fixture(tmp_path)
    old=branch.inventory(b,source,domains)['uuids'];assert old
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in old])
    owner=b.FindFootprintByReference('U_RENAMED');root=owner.FindPadByNumber('4')
    t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet(net));t.SetLayer(pcbnew.In2_Cu);t.SetWidth(200000)
    t.SetStart(root.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(10,13));b.Add(t)
    vias=[]
    for xy,diameter,drill in [(tuple(root.GetPosition()),.4,.2),((10000000,13000000),.9,.5)]:
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I(*xy))
        v.SetWidth(round(diameter*1e6));v.SetDrill(round(drill*1e6))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v);vias.append(v)
    field._save_field_snapshot(b,source)
    return source,b,net,domains,trunk,root,t,vias


def test_native_input_layer_transition_never_grants_power_barrel_or_trunk_credit(tmp_path):
    source,b,net,domains,trunk,root,t,vias=native_fixture(tmp_path)
    original=source.read_bytes();q=branch.plan(b,force._uid(root))
    assert q['track_uuids']==[force._uid(t)] and q['via_uuids']==[force._uid(vias[0])]
    assert force._uid(vias[1]) not in q['native_removed_material_uuids']
    assert not q['retirement_authority'] and not q['release_authority']
    r=branch.inventory(b,source,domains)
    assert r['complete'] and r['uuids']==[force._uid(t)],r
    assert force._uid(vias[0]) in r['proofs'][0]['native_exclusive_branch_material_uuids']
    with authority(net,amps=3.,source='FIXED',sink='POWER_SINK'):
        result=constraints.CHECKERS['trace-width-high-current'](pcbnew.LoadBoard(str(source)),str(source),{})
    assert result[0] is False
    remaining={item['uuid'] for row in result[2] if row.get('type')=='current_domain_path'
        for item in row['undersized_segments']}
    assert trunk in remaining and force._uid(t) not in remaining
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['dnp','wrong_package','unknown_mpn','unqualified_barrel',
    'underwidth','interior_contact','forged_partition_cut'])
def test_native_measurement_classification_fails_closed(tmp_path,fault,monkeypatch):
    source,b,net,domains,trunk,root,t,vias=native_fixture(tmp_path)
    fp=root.GetParentFootprint()
    if fault=='dnp':fp.SetDNP(True)
    elif fault=='wrong_package':fp.SetFPID(pcbnew.LIB_ID('fixture','SOT-23-5'))
    elif fault=='unknown_mpn':fp.SetField('MPN','NOT_AN_INA')
    elif fault=='unqualified_barrel':vias[0].SetWidth(180000);vias[0].SetDrill(100000)
    elif fault=='underwidth':t.SetWidth(50000)
    elif fault=='interior_contact':
        fork=pcbnew.PCB_TRACK(b);fork.SetNet(b.FindNet(net));fork.SetLayer(pcbnew.In2_Cu)
        fork.SetWidth(200000);fork.SetStart(pcbnew.VECTOR2I_MM(13,13));fork.SetEnd(pcbnew.VECTOR2I_MM(13,14));b.Add(fork)
    else:
        actual=branch.plan
        def forged(*args,**kwargs):
            q=actual(*args,**kwargs);q['native_removed_material_uuids'].append(trunk);return q
        monkeypatch.setattr(branch,'plan',forged)
    field._save_field_snapshot(b,source)
    result=branch.inventory(b,source,domains)
    assert not result['uuids'],result


def test_native_measurement_branch_survives_rotation_back_face_and_layer_alias(tmp_path):
    source,b,net,domains,trunk,root,t,vias=native_fixture(tmp_path)
    assert b.SetLayerName(pcbnew.In2_Cu,'ARBITRARY_SIGNAL_LAYER')
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(90,pcbnew.DEGREES_T))
        item.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source)
    result=branch.inventory(b,source,domains)
    assert result['complete'] and result['uuids']==[force._uid(t)],result


@pytest.mark.parametrize('bad',[True,-1,float('nan'),float('inf')])
def test_measurement_inventory_has_no_unbounded_or_implicit_deadline(tmp_path,bad):
    source,b,_,domains,_=fixture(tmp_path)
    with pytest.raises(ValueError):branch.inventory(b,source,domains,timeout_s=bad)

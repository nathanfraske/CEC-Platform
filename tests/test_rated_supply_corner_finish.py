"""Positive full-load authority, transformed native copper, hostile saved edits."""
import copy
import json
import math
from unittest import mock
import pcbnew
import pytest
import cec_rated_supply_corner_finish as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    net='/arbitrary-renamed-regulator-output'
    def point(x,y):
        if mirror:x=20-x
        for _ in range(quarter):x,y=20-y,x
        return (x,y)
    b=_board([(*point(5,5),net),(*point(10,10),net)],edge=(0,0,20,20));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for fp in b.GetFootprints():next(iter(fp.Pads())).SetNumber('1')
    for a,z in (((5,5),(10,5)),((10,5),(10,10))):track(b,net,point(*a),point(*z),width=.25,layer=layer).SetLocked(True)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    # Deliberately synthetic test authority, never a production load estimate.
    contract=dict(role='all_terminal_conservative_aggregate',branch_sharing_assumed=False,
        current_authority=dict(amps=.1,geometry_margin=1.2,margin_included=True,source='SYNTHETIC_TEST_ONLY'),
        required_by_layer_mm={n:.25 for n in ('F.Cu','In1.Cu','In2.Cu','In3.Cu','In4.Cu','B.Cu')},
        routing_layers=('F.Cu','In2.Cu','In3.Cu','B.Cu'))
    return b,source,net,dict(contracts={net:contract})


def proposal(b,source):
    r=op.discover(b,source,board_hint='synthetic',allow_locked_source=True,include_source_inner_layers=True)
    assert len(r['requests'])==1,r
    return op.plan(b,source,r['requests'],board_hint='synthetic',allow_locked_source=True,include_source_inner_layers=True)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_native_full_load_supply_corner_is_shorter_without_ordinary_reclassification(tmp_path,quarter,mirror,layer):
    b,source,net,catalog=fixture(tmp_path,quarter,mirror,layer);original=source.read_bytes()
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.object(op.geometry,'receive_saved',side_effect=AssertionError('NO_ORDINARY_AUTHORITY')):
        q=json.loads(json.dumps(proposal(b,source)));made=op.materialize(b,source,q,board_hint='synthetic')
        child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=op.receive(source,child,q,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['chamfered']==1 and len(r['retired_track_uuids'])==2 and len(r['added_native_uuids'])==3
    assert math.isclose(r['saved_trace_length_mm'],.4-math.sqrt(.08),abs_tol=1e-9)
    assert not r['ordinary_reclassification'] and not r['current_qualified'] and not r['release_authority']
    assert r['new_barrels']==0 and r['full_source_current_and_margins_unchanged']
    assert all(t.GetLayer()==layer and t.GetWidth()==250000 and t.IsLocked() for t in b.GetTracks())
    assert made['generic_geometry_is_not_ordinary_net_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('fault',['no_contract','unknown_role','sharing','no_margin','zero_current','boolean_current',
    'nan_current','missing_geometry_margin','underwidth','inner_plane','no_inner_policy','no_lock',
    'protected_force_net','group','mask','pad_launch','new_body_tee','wrong_source','boolean_bound','over_bound'])
def test_supply_identity_and_load_are_not_inferred_from_name_or_nearby_power_copper(tmp_path,fault):
    b,source,net,catalog=fixture(tmp_path);contract=catalog['contracts'][net];t=next(iter(b.GetTracks()))
    options=dict(allow_locked_source=True,include_source_inner_layers=True)
    if fault=='no_contract':catalog['contracts']={}
    elif fault=='unknown_role':contract['role']='assumed_consumer_island'
    elif fault=='sharing':contract['branch_sharing_assumed']=True
    elif fault=='no_margin':contract['current_authority'].pop('margin_included')
    elif fault=='zero_current':contract['current_authority']['amps']=0
    elif fault=='boolean_current':contract['current_authority']['amps']=True
    elif fault=='nan_current':contract['current_authority']['amps']=math.nan
    elif fault=='missing_geometry_margin':contract['current_authority'].pop('geometry_margin')
    elif fault=='underwidth':contract['required_by_layer_mm']['F.Cu']=.250001
    elif fault=='inner_plane':
        for t in b.GetTracks():t.SetLayer(pcbnew.In1_Cu)
    elif fault=='no_inner_policy':
        for t in b.GetTracks():t.SetLayer(pcbnew.In2_Cu)
        options['include_source_inner_layers']=False
    elif fault=='no_lock':options['allow_locked_source']=False
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED');b.Add(g);g.AddItem(t)
    elif fault=='mask':t.SetHasSolderMask(True)
    elif fault=='pad_launch':next(iter(next(iter(b.GetFootprints())).Pads())).SetPosition(pcbnew.VECTOR2I_MM(10,5))
    elif fault=='new_body_tee':track(b,net,(10,4),(10,6),width=.25)
    elif fault=='wrong_source':b.SetFileName('other.kicad_pcb')
    elif fault=='boolean_bound':options['minimum_nm']=True
    elif fault=='over_bound':options['maximum_nm']=2000001
    before=field._field_snapshot_inventory(b)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.object(op.topology,'board_current_domains',return_value={net:{}} if fault=='protected_force_net' else {}):
        if fault in ('wrong_source','boolean_bound','over_bound'):
            with pytest.raises(ValueError):op.discover(b,source,board_hint='synthetic',**options)
        else:assert not op.discover(b,source,board_hint='synthetic',**options)['requests']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['width','geometry','face','unlock','remove','extra_track','extra_via','pose',
    'source_header','retained_rule_area','changed_contract','forged_scope','forged_margin','unchanged_child'])
def test_exact_saved_replay_and_independent_electrical_owner_both_remain_mandatory(tmp_path,fault):
    b,source,net,catalog=fixture(tmp_path)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        q=proposal(b,source);made=op.materialize(b,source,q,board_hint='synthetic')
        t=next(t for t in b.GetTracks() if force._uid(t) in made['added_native_uuids'])
        if fault=='width':t.SetWidth(249999)
        elif fault=='geometry':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
        elif fault=='face':t.SetLayer(pcbnew.B_Cu)
        elif fault=='unlock':t.SetLocked(False)
        elif fault=='remove':b.Remove(t)
        elif fault=='extra_track':track(b,net,(1,1),(2,1),width=.25)
        elif fault=='extra_via':
            v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetWidth(600000);v.SetDrill(300000)
            v.SetPosition(pcbnew.VECTOR2I_MM(10,10));v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='source_header':
            props=b.GetProperties();props['UNOWNED_METADATA']='changed';b.SetProperties(props)
        elif fault=='retained_rule_area':
            z=pcbnew.ZONE(b);z.SetIsRuleArea(True);z.SetLayer(pcbnew.F_Cu);z.SetDoNotAllowTracks(True);z.Outline().NewOutline()
            for x,y in ((1,1),(2,1),(2,2),(1,2)):z.Outline().Append(x*1000000,y*1000000)
            b.Add(z)
        elif fault=='changed_contract':catalog['contracts'][net]['current_authority']['amps']=.2
        elif fault=='forged_scope':q=copy.deepcopy(q);q['requests'][0]['at_nm'][0]+=1
        elif fault=='forged_margin':q=copy.deepcopy(q);q['contracts'][net]['current_authority']['geometry_margin']=1.0
        child=force._copy_family(source,tmp_path/'hostile');field._save_field_snapshot(b,child)
        r=op.receive(source,source if fault=='unchanged_child' else child,q,board_hint='synthetic')
    assert not r['ok'] and not r['complete'] and r['errors'] and not r['release_authority'],r


def test_electrical_owner_failure_is_not_bypassed_by_a_matching_geometric_replay(tmp_path):
    b,source,net,catalog=fixture(tmp_path)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        q=proposal(b,source);op.materialize(b,source,q,board_hint='synthetic')
        child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        with mock.patch.object(op.rated,'receive',return_value=dict(ok=False,complete=False,errors=['deliberate typed refusal'])):
            r=op.receive(source,child,q,board_hint='synthetic')
    assert not r['ok'] and 'full_load_rated_supply_corner_receiving_refused' in r['errors'][0]


def test_source_authority_is_an_independent_json_stable_snapshot_not_a_mutable_alias(tmp_path):
    b,source,net,catalog=fixture(tmp_path)
    with mock.patch.object(op.topology,'distributed_supply_contracts',return_value=catalog):
        q=proposal(b,source)
    before=copy.deepcopy(q);catalog['contracts'][net]['current_authority']['amps']=.2
    assert q==before and q==json.loads(json.dumps(q))
    assert q['contracts'][net]['current_authority']['amps']==.1

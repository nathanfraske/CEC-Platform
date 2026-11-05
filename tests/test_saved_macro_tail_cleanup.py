"""Saved physical Ground composition and adversarial literal-chain boundaries."""
import copy
import json
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_source_class_ground_dead_end_tail as ground
import cec_saved_macro_tail_cleanup as op
from test_source_class_ground_dead_end_tail import fixture
from test_field_proposals import track
from cec_native_items import discard_items

def boundary(path):
    return dict(path=str(path),sha256=force._hash(path))

def case(tmp_path,angle=0):
    source,b,body,tip,root,xy=fixture(tmp_path,angle)
    q=ground.plan(b,source,force._uid(tip));ground.subtract(b,q)
    child=force._copy_family(source,tmp_path/'child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    row=dict(kind='ground',source=boundary(source),candidate=boundary(child),
        retired_track_uuids=q['retired_track_uuids'])
    proposal=dict(schema=1,kind='typed_saved_macro_tail_cleanup',
        original=boundary(source),prefix=boundary(source),steps=[row])
    return source,child,proposal

@pytest.mark.parametrize('angle',[0,90,180,270])
def test_real_saved_ground_cut_rederives_whole_chain_and_receives(tmp_path,angle):
    source,child,p=case(tmp_path,angle)
    raw=source.read_bytes()
    r=op.receive(source,source,child,json.loads(json.dumps(p)),board_hint='unclassified-test')
    assert r['ok'] and r['complete'],r
    assert r['steps'][0]['receiving']['all_surviving_native_partitions_preserved']
    assert not r['current_qualified'] and not r['release_authority']
    assert r['original_macro_source_receiving_still_required']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',[None,'missing','extra','boolean'])
def test_ground_source_lock_scope_is_exact_and_saved_not_worker_asserted(tmp_path,fault):
    source,b,body,tip,root,_=fixture(tmp_path)
    body.SetLocked(True);field._save_field_snapshot(b,source)
    ids=[force._uid(body)]
    q=ground.plan(b,source,force._uid(tip),allow_locked_track_uuids=ids)
    ground.subtract(b,q);child=force._copy_family(source,tmp_path/'locked-child')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    row=dict(kind='ground',source=boundary(source),candidate=boundary(child),
        retired_track_uuids=q['retired_track_uuids'],allow_locked_ground_track_uuids=ids)
    if fault=='missing':row.pop('allow_locked_ground_track_uuids')
    if fault=='extra':row['allow_locked_ground_track_uuids']=[*ids,force._uid(tip)]
    if fault=='boolean':row['allow_locked_ground_track_uuids']=True
    p=dict(schema=1,kind='typed_saved_macro_tail_cleanup',original=boundary(source),
        prefix=boundary(source),steps=[row])
    r=op.receive(source,source,child,p,board_hint='unclassified-test')
    assert bool(r['ok'])==(fault is None),r

def test_two_actual_typed_cuts_chain_without_promoting_intermediate(tmp_path):
    source,b,body,tip,root,_=fixture(tmp_path)
    project=json.loads(source.with_suffix('.kicad_pro').read_text())
    default=project['net_settings']['classes'][0]
    ground_class=dict(default,name='Ground')
    default['track_width']=.2
    project['net_settings']['classes'].append(ground_class)
    project['net_settings']['netclass_assignments']={'GND':'Ground'}
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    a=track(b,'/CONTROL',(25.1,16),(27,16))
    z=track(b,'/CONTROL',(27,16),(28,17))
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ORDINARY_ROOT');b.Add(fp)
    pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNumber('1');pad.SetPosition(pcbnew.VECTOR2I_MM(25,16))
    pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetNet(a.GetNet())
    layer=pcbnew.LSET();layer.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layer)
    field._save_field_snapshot(b,source)
    q=ground.plan(b,source,force._uid(tip));ground.subtract(b,q)
    middle=force._copy_family(source,tmp_path/'middle')
    additive._ground_refill(b);field._save_field_snapshot(b,middle)
    ids=[force._uid(a),force._uid(z)]
    discard_items(b,[a,z])
    final=force._copy_family(middle,tmp_path/'final')
    additive._ground_refill(b);field._save_field_snapshot(b,final)
    p=dict(schema=1,kind='typed_saved_macro_tail_cleanup',original=boundary(source),
        prefix=boundary(source),steps=[
            dict(kind='ground',source=boundary(source),candidate=boundary(middle),
                retired_track_uuids=q['retired_track_uuids']),
            dict(kind='ordinary',source=boundary(middle),candidate=boundary(final),
                retired_track_uuids=ids)])
    r=op.receive(source,source,final,p,board_hint='unclassified-test')
    assert r['ok'] and r['complete'],r
    assert [x['kind']for x in r['steps']]==['ground','ordinary']

@pytest.mark.parametrize('fault',['hash','prefix','final','duplicate_kind','extra_kind','boolean',
    'retired_subset','retired_unknown','lock_forgery','role_forgery','source_mismatch','no_steps',
    'too_many','incoming','malformed','oversized_timeout'])
def test_no_worker_claim_or_malformed_chain_can_admit(tmp_path,fault):
    source,child,p=case(tmp_path)
    original=source;prefix=source;final=child;timeout=10
    if fault=='hash':p['steps'][0]['candidate']['sha256']='0'*64
    elif fault=='prefix':p['prefix']=boundary(child)
    elif fault=='final':final=source
    elif fault=='duplicate_kind':p['steps'].append(copy.deepcopy(p['steps'][0]))
    elif fault=='extra_kind':p['steps'][0]['kind']='unknown'
    elif fault=='boolean':p['steps'][0]['receiver_ok']=True
    elif fault=='retired_subset':p['steps'][0]['retired_track_uuids'].pop()
    elif fault=='retired_unknown':p['steps'][0]['retired_track_uuids']=['unknown']
    elif fault=='lock_forgery':p['steps'][0]['allow_locked_supply_track_uuids']=[]
    elif fault=='role_forgery':p['steps'][0]['kind']='ordinary'
    elif fault=='source_mismatch':p['steps'][0]['source']=boundary(child)
    elif fault=='no_steps':p['steps']=[]
    elif fault=='too_many':p['steps']*=4
    elif fault=='incoming':
        b=pcbnew.LoadBoard(str(child))
        t=pcbnew.PCB_TRACK(b);t.SetNet(next(v for v in b.GetTracks() if v.GetNetname()=='GND').GetNet())
        t.SetStart(pcbnew.VECTOR2I_MM(13,14));t.SetEnd(pcbnew.VECTOR2I_MM(14,14))
        t.SetWidth(500000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
        field._save_field_snapshot(b,child);p['steps'][0]['candidate']=boundary(child)
    elif fault=='malformed':p['schema']=True
    else:timeout=11
    r=op.receive(original,prefix,final,p,board_hint='unclassified-test',timeout_s=timeout)
    assert not r['ok'],r
    assert r['errors']

@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('locked',[False,True])
def test_compound_obsolete_multiface_port_is_independently_received(tmp_path,rotation,locked):
    from test_native_macro_tail_cleanup import port_case,report,warning
    import cec_native_macro_tail_cleanup as cleanup
    source,tracks,trunk,port=port_case(tmp_path,rotation,False,locked)
    made=cleanup.construct(source,tmp_path/'constructed',board_hint='synthetic',
        original_native=report(),proposed_native=report(warning(tracks[0])),
        allow_locked_obsolete_port_vias=locked)
    assert made['ok'],made
    from pathlib import Path
    child=Path(made['candidate'])
    row=dict(kind='ordinary',source=boundary(source),candidate=boundary(child),
        retired_track_uuids=tracks,retired_via_uuids=[port],
        allow_locked_ordinary_via_uuids=[port]if locked else [])
    p=dict(schema=1,kind='typed_saved_macro_tail_cleanup',original=boundary(source),
        prefix=boundary(source),steps=[row])
    r=op.receive(source,source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    witness=r['steps'][0]['receiving']['independently_rederived_obsolete_port_vias'][0]
    assert len(witness['source_actual_contact_faces'])==2
    assert witness['retained_contact_layers']==[int(pcbnew.B_Cu)]
    # Constructor success flags cannot substitute for exact public lock scope.
    row['allow_locked_ordinary_via_uuids']=[]if locked else [port]
    assert not op.receive(source,source,child,p,board_hint='synthetic')['ok']

def test_one_face_source_via_is_not_an_obsolete_multiface_routing_port(tmp_path):
    from test_native_macro_tail_cleanup import port_case
    source,tracks,trunk,port=port_case(tmp_path)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    live[trunk].SetLayer(pcbnew.F_Cu)
    field._save_field_snapshot(b,source)
    discard_items(b,[live[u]for u in [*tracks,port]])
    child=force._copy_family(source,tmp_path/'one-face-cut')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    p=dict(schema=1,kind='typed_saved_macro_tail_cleanup',original=boundary(source),
        prefix=boundary(source),steps=[dict(kind='ordinary',source=boundary(source),
            candidate=boundary(child),retired_track_uuids=tracks,retired_via_uuids=[port],
            allow_locked_ordinary_via_uuids=[])])
    r=op.receive(source,source,child,p,board_hint='synthetic')
    assert not r['ok'] and 'original_multiface' in str(r['errors']),r

@pytest.mark.parametrize('disabled',[False,True])
def test_six_layer_inner_face_port_requires_actual_enabled_copper(tmp_path,disabled):
    from test_native_macro_tail_cleanup import port_case
    source,tracks,trunk,port=port_case(tmp_path)
    b=pcbnew.LoadBoard(str(source));b.SetCopperLayerCount(6)
    live={force._uid(t):t for t in b.GetTracks()}
    face=pcbnew.In2_Cu if not disabled else pcbnew.In6_Cu
    assert (int(face)in set(map(int,b.GetEnabledLayers().CuStack()))) is not disabled
    live[trunk].SetLayer(face)
    field._save_field_snapshot(b,source)
    discard_items(b,[live[u]for u in [*tracks,port]])
    child=force._copy_family(source,tmp_path/'inner-face-cut')
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    p=dict(schema=1,kind='typed_saved_macro_tail_cleanup',original=boundary(source),
        prefix=boundary(source),steps=[dict(kind='ordinary',source=boundary(source),
            candidate=boundary(child),retired_track_uuids=tracks,retired_via_uuids=[port],
            allow_locked_ordinary_via_uuids=[])])
    r=op.receive(source,source,child,p,board_hint='synthetic')
    if disabled:assert not r['ok'],r
    else:
        assert r['ok'] and r['complete'],r
        proof=r['steps'][0]['receiving']['independently_rederived_obsolete_port_vias'][0]
        assert proof['retained_contact_layers']==[int(face)]
        assert proof['source_actual_contact_faces']==[int(pcbnew.F_Cu),int(face)]

def test_final_acute_step_uses_real_saved_whole_current_receiver(tmp_path):
    from test_full_current_acute_cleanup import fixture as acute_fixture
    from unittest.mock import patch
    import cec_full_current_acute_cleanup as acute
    import cec_full_current_planar_reflow as full
    source,ids,net,contract,domains=acute_fixture(tmp_path)
    with patch.object(full.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(full.topology,'board_current_domains',return_value=domains):
        q=acute.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',source_track_uuids=ids)
        child=force._copy_family(source,tmp_path/'acute-child')
        acute.construct_private(source,child,q,board_hint='synthetic')
        row=dict(kind='supply_acute',source=boundary(source),candidate=boundary(child),source_track_uuids=ids)
        p=dict(schema=1,kind='typed_saved_macro_tail_cleanup',original=boundary(source),
            prefix=boundary(source),steps=[row])
        r=op.receive(source,source,child,p,board_hint='synthetic')
        assert r['ok'] and r['complete'],r
        assert r['steps'][0]['receiving']['strictly_shorter']
        p['steps'].append(dict(kind='ground',source=boundary(child),candidate=boundary(source),
            retired_track_uuids=ids))
        r=op.receive(source,source,source,p,board_hint='synthetic')
        assert not r['ok'] and 'supply_acute_must_be_final' in str(r['errors']),r

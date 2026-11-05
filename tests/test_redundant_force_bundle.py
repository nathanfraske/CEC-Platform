"""Collector retirement keeps native material, current paths and clipped cuts.

Explicit synthetic budgets isolate catalog lookup only. Real source boards
continue to use their existing, unchanged current and fabrication authority.
"""
import copy
import math
from contextlib import contextmanager
from unittest.mock import patch

import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_received_route_evidence as received
import cec_redundant_force_bundle as bundle
import cec_zone_fill as fill
from cec_native_items import discard_items
from test_force_sense_evidence import fixture


def saved_bundle(tmp_path,*,angle=0,filtered=True,face='F.Cu',zone_only=False,fault=None):
    source=tmp_path/'source.kicad_pcb'
    domains=fixture(source,angle=angle,filtered=filtered)
    for d in domains.values():d['amps']=1.
    b=pcbnew.LoadBoard(str(source))
    net='RENAMED_FEED'
    feed=max((t for t in b.GetTracks() if t.GetNetname()==net),key=lambda t:t.GetLength())
    start,end=tuple(feed.GetStart()),tuple(feed.GetEnd())
    def at(t,offset=0):
        dx,dy=end[0]-start[0],end[1]-start[1];length=math.hypot(dx,dy)
        return pcbnew.VECTOR2I(round(start[0]+dx*t-dy/length*offset),
                              round(start[1]+dy*t+dx/length*offset))
    for a,z in zip(((-150,-150),(250,-150),(250,250),(-150,250)),
                   ((250,-150),(250,250),(-150,250),(-150,-150))):
        e=pcbnew.PCB_SHAPE(b);e.SetLayer(pcbnew.Edge_Cuts);e.SetShape(pcbnew.SHAPE_T_SEGMENT)
        e.SetWidth(100000);e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(e)
    layer=b.GetLayerID(face)
    if face=='B.Cu':
        pad=next(iter(b.FindFootprintByReference('POWER_IN').Pads()))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetLayerSet(pcbnew.LSET.AllCuMask())
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I_MM(.9,.9))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
        v=pcbnew.PCB_VIA(b);v.SetPosition(at(2/3));v.SetWidth(900000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNetCode(b.GetNetcodeFromNetname(net));b.Add(v)
    trace=pcbnew.PCB_TRACK(b);trace.SetNetCode(b.GetNetcodeFromNetname(net))
    trace.SetStart(at(0));trace.SetEnd(at(2/3));trace.SetLayer(layer);trace.SetWidth(600000)
    trace.SetLocked(True);b.Add(trace)
    zone=pcbnew.ZONE(b);zone.SetLayer(layer);zone.SetNetCode(b.GetNetcodeFromNetname(net))
    zone.SetLocalClearance(200000);zone.SetMinThickness(100000)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL);zone.SetLocked(True)
    zone.Outline().NewOutline()
    for p in (at(1/3,-350000),at(1/2,-350000),at(1/2,350000),at(1/3,350000)):
        zone.Outline().Append(p)
    b.Add(zone)
    fill.compile_selected(b,[zone],initialize_selected=True)
    if fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(zone)
    if fault=='unfilled':zone.UnFill()
    field._save_field_snapshot(b,source)
    ids=[force._uid(zone)]+([] if zone_only else [force._uid(trace)])
    child=force._copy_family(source,tmp_path/'child')
    b=pcbnew.LoadBoard(str(child))
    cut=set(ids)
    if fault=='only_path':cut.add(force._uid(feed));ids=sorted(cut)
    if fault=='via':
        via=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA')
        cut.add(force._uid(via));ids=sorted(cut)
    discard_items(b,[i for i in [*b.GetTracks(),*b.Zones()] if force._uid(i) in cut])
    if fault=='source_edit':b.FindFootprintByReference('POWER_IN').SetValue('unauthorized')
    if fault=='addition':
        t=pcbnew.PCB_TRACK(b);t.SetNetCode(b.GetNetcodeFromNetname(net));t.SetLayer(pcbnew.F_Cu)
        t.SetStart(pcbnew.VECTOR2I_MM(5,5));t.SetEnd(pcbnew.VECTOR2I_MM(5,6));t.SetWidth(200000);b.Add(t)
    additive._ground_refill(b);field._save_field_snapshot(b,child)
    raw={n:dict(net=n,amps=1.,profile='explicit-fixture',authority_refs=d['authority_refs'],
        routing_layers=['F.Cu','B.Cu'],required_by_layer_mm={'F.Cu':.5,'B.Cu':.5},
        current_authority=dict(amps=1.,geometry_margin=1.,margin_included=False,source='bounded_fixture_only'))
        for n,d in domains.items()}
    return source,child,ids,domains,raw


@contextmanager
def authority(domains,raw,*,debt=False):
    with patch('cec_current_topology.board_current_domains',return_value=domains), \
         patch('cec_current_topology.route_width_contracts',return_value=raw), \
         patch('cec_fr._project_netclass_resolver',return_value=lambda n:dict(track_width=.2,clearance=.2)), \
         patch('cec_current_debt.receive',return_value=dict(ok=not debt,complete=True,release_authority=False)):
        yield


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
@pytest.mark.parametrize('filtered',[False,True])
def test_real_filled_material_all_barrels_and_typed_cuts_survive(tmp_path,angle,face,filtered):
    source,child,ids,domains,raw=saved_bundle(tmp_path,angle=angle,face=face,filtered=filtered)
    hashes=force._hash(source),force._hash(child)
    with authority(domains,raw):
        result=bundle.receive(source,child,board_hint='explicit-fixture',native_uuids=ids,
            allow_locked_native_uuids=ids,timeout_s=10.)
    assert result['ok'] and result['complete'],result['errors']
    assert result['physical_preservation']['same_evidence']
    assert all(r['all_actual_terminals_definitely_connected'] for r in result['actual_physical_terminal_graphs'])
    assert result['source_sense']['clipped_isolation']['passed']==2
    assert result['candidate_sense']['clipped_isolation']['passed']==2
    assert result['native_count_manifest'][0]['retired_zone_uuids']
    assert result['native_material_delta']['ok'] and result['native_material_delta']['complete']
    assert result['routing_corridor_freed_not_inferred']
    assert not result['native_material_delta']['routing_corridor_qualified']
    assert not result['current_qualified'] and not result['full_kelvin_qualification'] and not result['release_authority']
    assert hashes==(force._hash(source),force._hash(child))


@pytest.mark.parametrize('zone_only',[False,True])
def test_common_receiver_uses_independent_exact_cut_not_a_worker_success_flag(tmp_path,zone_only):
    source,child,ids,domains,raw=saved_bundle(tmp_path,face='B.Cu',zone_only=zone_only)
    with authority(domains,raw):
        before,after=[sense.replay(p,board_hint='explicit-fixture',timeout_s=10.) for p in (source,child)]
        result=received.compare(source,child,before,after,timeout_s=10.,
            retired_force_bundle_native_uuids=ids,allow_locked_force_bundle_native_uuids=ids)
    assert result['ok'] and result['complete'],result['errors']
    assert result['source_delta']['exact_native_source_minus_bundle_received']
    assert result['contact_count_transforms'][0]['retired_zone_uuids']
    assert not result['release_authority']


@pytest.mark.parametrize('fault',['group','unfilled','only_path','via','source_edit','addition'])
def test_cut_cannot_remove_a_needed_path_or_touch_unowned_native_material(tmp_path,fault):
    source,child,ids,domains,raw=saved_bundle(tmp_path,face='B.Cu',fault=fault)
    with authority(domains,raw):
        result=bundle.receive(source,child,board_hint='explicit-fixture',native_uuids=ids,
            allow_locked_native_uuids=ids,timeout_s=10.)
    assert not result['ok'] and result['errors'],result
    assert not result['release_authority']


@pytest.mark.parametrize('fault',['missing_lock','outside_lock','partial_cut','stale','duplicate','debt','authority'])
def test_exact_authorization_inventory_and_unchanged_current_contract_remain_required(tmp_path,fault):
    source,child,ids,domains,raw=saved_bundle(tmp_path)
    locks=ids
    if fault=='missing_lock':locks=[]
    if fault=='outside_lock':locks=ids+['not-in-cut']
    if fault=='partial_cut':ids=ids[:1];locks=ids
    if fault=='stale':ids=ids+['not-native'];locks=ids
    if fault=='duplicate':ids=ids*2;locks=ids
    if fault=='authority':domains={}
    with authority(domains,raw,debt=fault=='debt'):
        result=bundle.receive(source,child,board_hint='explicit-fixture',native_uuids=ids,
            allow_locked_native_uuids=locks,timeout_s=10.)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('fault',['ordinary','pose','lock_without_cut'])
def test_common_receiver_cannot_mix_retirement_authority(tmp_path,fault):
    source,child,ids,domains,raw=saved_bundle(tmp_path)
    kw=dict(retired_force_bundle_native_uuids=ids,allow_locked_force_bundle_native_uuids=ids)
    if fault=='ordinary':kw['retired_ordinary_track_uuids']=['arbitrary']
    if fault=='pose':kw['allow_selected_bypass_poses']=True
    if fault=='lock_without_cut':kw['retired_force_bundle_native_uuids']=[]
    with authority(domains,raw):
        before,after=[sense.replay(p,board_hint='explicit-fixture',timeout_s=10.) for p in (source,child)]
        result=received.compare(source,child,before,after,timeout_s=10.,**kw)
    assert not result['ok'] and result['errors']


@pytest.mark.parametrize('fault',['cut_guard','unaffected_guard','cut_count'])
def test_raw_cut_failure_guards_and_coverage_cannot_be_normalized(tmp_path,fault):
    source,child,ids,domains,raw=saved_bundle(tmp_path)
    real=sense.replay
    def replay(path,**kw):
        result=real(path,**kw)
        if path.resolve()==child.resolve():
            net='RENAMED_LOAD' if fault=='unaffected_guard' else 'RENAMED_FEED'
            row=next(r for r in result['clipped_isolation']['details'] if r['net']==net)
            if fault=='cut_count':result['clipped_isolation']['passed']-=1
            else:row['native']['numerical_guard_nm']+=1
        return result
    with authority(domains,raw),patch('cec_force_sense_evidence.replay',side_effect=replay):
        result=bundle.receive(source,child,board_hint='explicit-fixture',native_uuids=ids,
            allow_locked_native_uuids=ids,timeout_s=10.)
    assert not result['ok'] and result['errors'],result


@pytest.mark.parametrize('bad',[None,'zone',[None],['same','same'],['track']])
def test_retired_zone_count_manifest_is_not_an_arbitrary_counter_waiver(tmp_path,bad):
    source,child,ids,domains,raw=saved_bundle(tmp_path)
    with authority(domains,raw):
        before,after=[sense.replay(p,board_hint='explicit-fixture',timeout_s=10.) for p in (source,child)]
    transform=dict(net='RENAMED_FEED',retired_track_uuids=['track'],added_track_uuids=[],
        added_zone_uuids=[],retired_zone_uuids=copy.deepcopy(bad))
    result=sense.compare_contact_preservation(before,after,native_copper_transforms=[transform])
    assert not result['same_evidence'] and result['errors']

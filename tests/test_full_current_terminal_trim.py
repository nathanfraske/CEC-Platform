"""Real saved native T-junctions with test-only, never board, current catalogs."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import os
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_terminal_trim as owner
import cec_full_current_terminal_trim_stage as stage
import cec_native_track_ports as ports
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,*,quarter=0,mirror=False,face=pcbnew.F_Cu,width=.2,net='/renamed/BUS',peer_extension=0.,tip_extension=.8):
    def pose(p):
        x,y=p[0]-20,p[1]-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 20+x,20+y
    b=_board([(*pose(p),net) for p in ((18,20),(20,22))],edge=(0,0,40,40));b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            ls=pcbnew.LSET();ls.AddLayer(face);pad.SetLayerSet(ls)
    for a,z in [((18,20),(20+tip_extension,20)),((20,20-peer_extension),(20,22))]:
        track(b,net,pose(a),pose(z),layer=face,width=width).SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    return source,net


@contextmanager
def authority(net,face=pcbnew.F_Cu,*,incomplete=False,floor=.1,missing=False):
    name=pcbnew.BOARD().GetLayerName(face)
    contract=dict(net=net,required_by_layer_mm={name:floor},routing_layers=[name],
        current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False,source='board_design_basis'))
    domains={net:dict(net=net,complete=not incomplete,source_refs=['source'],sink_refs=['sink'])}
    with patch.object(owner.full.topology,'board_current_domains',return_value={} if missing else domains), \
         patch.object(owner.full.topology,'route_width_contracts',return_value={net:contract}), \
         patch.object(owner.full.topology,'distributed_supply_contracts',return_value={'contracts':{}}):
        yield


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('width',[.2,1.])
def test_full_current_native_tip_trims_to_the_real_retained_tap(tmp_path,quarter,mirror,face,width):
    source,net=fixture(tmp_path,quarter=quarter,mirror=mirror,face=face,width=width);before=source.read_bytes()
    with authority(net,face):
        b=pcbnew.LoadBoard(str(source));d=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
        assert len(d['requests'])==1,d
        p=owner.plan(b,source,d['requests'][0],board_hint='synthetic',allow_locked_source=True)
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=owner.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['saved_trace_length_mm']==pytest.approx(.8),r
    assert r['source_width_face_current_and_native_contacts_preserved'] and r['source_capsule_subset_rederived']
    assert r['new_vias']==r['new_holes']==r['pads_moved']==0 and not r['power_pours_changed'] and not r['release_authority']
    assert len(made['retired_track_uuids'])==len(made['added_native_uuids'])==1
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['untyped','incomplete','below_floor','locked','mask','group','non45','ground','no_tap','tip_contact','peeled_side_contact','plane'])
def test_unqualified_source_or_real_contacts_never_become_a_cosmetic_cut(tmp_path,fault):
    face=pcbnew.In1_Cu if fault=='plane' else pcbnew.F_Cu
    source,net=fixture(tmp_path,face=face,net='GND' if fault=='ground' else '/renamed/BUS');b=pcbnew.LoadBoard(str(source));edges=list(b.GetTracks())
    old=max(edges,key=lambda t:t.GetLength())
    if fault=='mask':old.SetHasSolderMask(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(old)
    elif fault=='non45':old.SetEnd(pcbnew.VECTOR2I(20800000,20000001))
    elif fault=='plane':
        b.Add(pcbnew.NETINFO_ITEM(b,'GND'));z=pcbnew.ZONE(b);z.SetNet(b.FindNet('GND'));z.SetLayer(face)
        z.Outline().NewOutline()
        for x,y in ((1,1),(39,1),(39,39),(1,39)):z.Outline().Append(x*1000000,y*1000000)
        b.Add(z)
    elif fault=='no_tap':
        for t in edges:
            if t is not old:t.Move(pcbnew.VECTOR2I_MM(0,.1))
    elif fault=='tip_contact':track(b,net,(20.8,20),(21.4,20.4))
    elif fault=='peeled_side_contact':track(b,net,(20.7,19.91),(21.1,19.51))
    field._save_field_snapshot(b,source);b=pcbnew.LoadBoard(str(source))
    with authority(net,face,incomplete=fault=='incomplete',floor=.3 if fault=='below_floor' else .1,missing=fault=='untyped'):
        r=owner.discover(b,source,board_hint='synthetic',allow_locked_source=fault!='locked')
    assert not r['requests'],r


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_retained_body_intersection_not_just_endpoint_alias_is_a_real_contact(tmp_path,quarter,mirror,face):
    source,net=fixture(tmp_path,quarter=quarter,mirror=mirror,face=face,peer_extension=.00624)
    with authority(net,face):
        b=pcbnew.LoadBoard(str(source));d=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
        assert len(d['requests'])==2,d
        import math
        assert [math.dist(r['free_end_nm'],r['junction_nm'])/1e6 for r in d['requests']]==pytest.approx([.8,.00624])
        p=owner.plan(b,source,d['requests'][0],board_hint='synthetic',allow_locked_source=True)
        assert any(c['method']=='exact_same_width_native_capsule_kernel' for c in p['native_proposal']['native_contacts'])
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=owner.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'],r


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
def test_second_retained_round_contact_replays_exactly_without_polygon_erosion(tmp_path,quarter,mirror):
    source,net=fixture(tmp_path,quarter=quarter,mirror=mirror,peer_extension=.00624)
    b=pcbnew.LoadBoard(str(source))
    def pose(x,y):
        x,y=x-20,y-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 20+x,20+y
    # A real contact on the side of the source remains, despite not having
    # its centreline exactly at the junction. No location-specific runtime.
    track(b,net,pose(20,20.17876),pose(20,20.6)).SetLocked(True)
    field._save_field_snapshot(b,source)
    with authority(net):
        b=pcbnew.LoadBoard(str(source));d=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
        assert d['requests'],d
        p=owner.plan(b,source,d['requests'][0],board_hint='synthetic',allow_locked_source=True)
        assert any(c['method']=='exact_capsule_axis_distance_preserved' for c in p['native_proposal']['native_contacts'])
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=owner.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'],r


@pytest.mark.parametrize('quarter',[0,1,2,3])
@pytest.mark.parametrize('mirror',[False,True])
def test_short_tip_inside_retained_tap_still_needs_real_visible_native_material_removal(tmp_path,quarter,mirror):
    source,net=fixture(tmp_path,quarter=quarter,mirror=mirror,tip_extension=.00624)
    with authority(net):
        b=pcbnew.LoadBoard(str(source));d=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
        assert len(d['requests'])==1,d
        p=owner.plan(b,source,d['requests'][0],board_hint='synthetic',allow_locked_source=True)
        assert p['native_proposal']['actual_visible_native_material_removed']['ok']
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
        r=owner.receive(source,child,p,board_hint='synthetic')
    assert r['ok'] and r['complete'] and r['saved_trace_length_mm']==pytest.approx(.00624),r


def test_a_current_contract_cannot_grant_a_declared_pair_a_cosmetic_cut(tmp_path,monkeypatch):
    source,net=fixture(tmp_path)
    monkeypatch.setattr(owner.precision,'derive_coupled_pairs',lambda *a,**k:[dict(p=net,n='/OTHER')])
    with authority(net):
        r=owner.discover(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',allow_locked_source=True)
    assert not r['requests'] and r['refusals'][0]['reason']=='declared_pair_contact_has_no_planar_current_trim_authority'


@pytest.mark.parametrize('args,want',[
    (((0,0),(10,0),(5,-3),(5,3)),(0,1)),
    (((0,0),(10,0),(5,4),(7,4)),(16,1)),
    (((0,0),(10,10),(10,0),(20,10)),(50,1)),
    (((0,0),(3,0),(5,2),(5,4)),(8,1)),
    (((0,0),(0,0),(1,1),(2,2)),(2,1)),
    (((0,0),(10,0),(10,0),(20,0)),(0,1)),
    (((0,0),(3,2),(0,3),(0,4)),(81,13)),
])
def test_native_axis_distance_is_rational_rotation_and_order_invariant(args,want):
    from fractions import Fraction
    expected=Fraction(*want)
    for a,b,c,d in [args,(args[1],args[0],args[3],args[2]),(args[2],args[3],args[0],args[1])]:
        assert ports.segment_distance_squared(a,b,c,d)==expected
        assert ports.segment_distance_squared(*[(-y,x) for x,y in (a,b,c,d)])==expected


@pytest.mark.parametrize('fault',['narrow','layer','pose','sidecar','via','extra_track','request','witness'])
def test_saved_receiver_rejects_unowned_mutation_or_forged_trim(tmp_path,fault):
    source,net=fixture(tmp_path)
    with authority(net):
        b=pcbnew.LoadBoard(str(source));r=owner.discover(b,source,board_hint='synthetic',allow_locked_source=True)
        p=owner.plan(b,source,r['requests'][0],board_hint='synthetic',allow_locked_source=True)
        made=owner.materialize(b,source,p,board_hint='synthetic');child=force._copy_family(source,tmp_path/'child')
        t=next(t for t in b.GetTracks() if force._uid(t) in made['added_native_uuids'])
        if fault=='narrow':t.SetWidth(199999)
        elif fault=='layer':t.SetLayer(pcbnew.B_Cu)
        elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
        elif fault=='via':
            v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(20,20));v.SetWidth(600000);v.SetDrill(300000)
            v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='extra_track':track(b,net,(30,30),(31,30))
        elif fault=='request':p['request']['junction_nm'][0]+=1
        else:p['native_proposal']['native_contacts']=[]
        field._save_field_snapshot(b,child);r=owner.receive(source,child,p,board_hint='synthetic')
    assert not r['ok'] and r['errors'] and not r['release_authority'],r


@pytest.mark.parametrize('kwargs',[dict(allow_locked_source=1),dict(max_trials=True),dict(max_trials=0),dict(max_trials=17),dict(expected_source_sha256='no')])
def test_bad_stage_context_never_creates_output(tmp_path,kwargs):
    args=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native');args.update(kwargs)
    out=tmp_path/'never-created'
    with pytest.raises(ValueError):stage.run(tmp_path/'missing',out,**args)
    assert not out.exists()


@pytest.mark.parametrize('quarter',[0,2])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_stage_keeps_actual_zero_opens_and_uncapped_fault_inventory(tmp_path,quarter,face):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('native reporting build not configured')
    source,net=fixture(tmp_path,quarter=quarter,face=face);before=source.read_bytes()
    with authority(net,face):
        r=stage.run(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
            reporting_build=Path(native),allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'],r
    assert r['trimmed']==1 and r['source_family_and_code_unchanged'] and not r['attempts'][0]['new_native_fault_ids']
    assert all(p['ok'] and p['complete'] and not p['native_inventory']['potentially_truncated'] for p in r['native_producers'].values())
    assert source.read_bytes()==before

"""Proposed local barrels are not retained aliases or remote via waivers."""
import time
import json
import os
from pathlib import Path

import pcbnew
import pytest
import cec_existing_local_pofv_pad_rule as rule
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_portal_geometry as geometry
import cec_source_rule_signal_launches as local
from test_existing_local_pofv_pad_rule import case


LAYERS=[pcbnew.F_Cu,pcbnew.In2_Cu,pcbnew.B_Cu]


def offer(board,pad,**kw):
    args=dict(width_nm=200000,clearance_nm=200000,route_layers=LAYERS,
        deadline=time.monotonic()+3.,max_sites=8);args.update(kw)
    return local.propose(board,pad,**args)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_source_rule_launches_preserve_saved_rule_and_global_floors(tmp_path,angle,face):
    board,source,pad=case(tmp_path,angle,face)
    before=force._family(source);native=field._field_snapshot_inventory(board);floors=rule._floors(board)
    q=offer(board,pad)
    assert q['complete']and q['choices'],q
    assert any(r['kind']=='bounded_source_dogbone'for r in q['choices']),q
    for row in q['choices']:
        assert row['proposed_not_retained_native_contact']and 'native_uuids'not in row
        assert row['source_pad_uuid']==force._uid(pad)and row['layers']==LAYERS
        assert row['source_rule']['minimum_nm']==dict(via_diameter=300000,hole_size=200000,annular_width=50000)
        via=row['operations'][-1];assert via[0]=='via'and via[-2:]==(200000,300000)
        assert row['actual_native_source_rule_preflight']and not row['release_authority']
    assert not q['electrical_role_qualified']and not q['current_qualified']and not q['routing_admitted']
    assert before==force._family(source)and native==field._field_snapshot_inventory(board)and floors==rule._floors(board)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_narrow_saved_land_uses_external_dogbone_not_partial_vip(tmp_path,face):
    board,source,pad=case(tmp_path,face=face)
    pad.SetSize(pcbnew.VECTOR2I(600000,200000));field._save_field_snapshot(board,source)
    board=pcbnew.LoadBoard(str(source));pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==force._uid(pad))
    q=offer(board,pad)
    assert q['choices']and all(r['kind']in('bounded_source_dogbone','bounded_source_radial_dogbone')
        for r in q['choices']),q
    assert q['refusals'].get('source_pad_cannot_fully_contain_local_land')==1


@pytest.mark.parametrize('fault',['missing_rule','missing_group','locked_group','changed_pad','changed_floor','profile','DNP'])
def test_missing_or_contradictory_source_context_proposes_no_small_barrel(tmp_path,fault):
    board,source,pad=case(tmp_path)
    if fault=='missing_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='missing_group':
        group=next(g for g in board.Groups()if g.GetName()==rule.GROUP)
        for item in list(group.GetItems()):group.RemoveItem(item)
        board.Remove(group)
    elif fault=='locked_group':next(g for g in board.Groups()if g.GetName()==rule.GROUP).SetLocked(True)
    elif fault=='changed_pad':pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='changed_floor':board.GetDesignSettings().m_ViasMinSize+=1
    elif fault=='profile':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='unknown';board.SetProperties(props)
    else:pad.GetParentFootprint().SetDNP(True)
    before=source.read_bytes();q=offer(board,pad)
    assert not q['choices'],q
    assert before==source.read_bytes()


@pytest.mark.parametrize('layer',LAYERS+[pcbnew.In1_Cu,pcbnew.In3_Cu,pcbnew.In4_Cu])
def test_new_local_barrel_still_obeys_foreign_copper_on_every_layer(tmp_path,layer):
    board,source,pad=case(tmp_path)
    centre=pad.GetPosition()
    # Cover the full existing1.5mm radial domain, not only former near seats.
    edge=pcbnew.PCB_TRACK(board);edge.SetLayer(layer);edge.SetNet(board.FindNet('obstruction'));edge.SetWidth(3200000)
    edge.SetStart(centre-pcbnew.VECTOR2I(2000000,0));edge.SetEnd(centre+pcbnew.VECTOR2I(2000000,0));board.Add(edge)
    q=offer(board,pad);assert not q['choices'],q
    assert q['refusals'].get('source_local_native_foreign_copper',0)>0,q


@pytest.mark.parametrize('kwargs',[{'width_nm':1},{'clearance_nm':0},{'route_layers':[pcbnew.In1_Cu]},
    {'max_sites':0},{'max_sites':True},{'deadline':float('nan')},{'deadline':float('inf')}])
def test_bad_or_plane_launch_policy_cannot_relax_process(kwargs,tmp_path):
    board,source,pad=case(tmp_path)
    with pytest.raises(ValueError,match='bounded_exact_saved_rule_signal_launch'):offer(board,pad,**kwargs)


def test_expired_geometry_lease_is_not_reset(tmp_path):
    board,source,pad=case(tmp_path)
    q=offer(board,pad,deadline=time.monotonic()-1.)
    assert not q['choices']and not q['complete']and q['reason']=='source_local_launch_deadline'


@pytest.mark.parametrize('guard_passes',[False,True])
def test_complete_local_prefix_and_middle_pass_same_final_guard(tmp_path,monkeypatch,guard_passes):
    board,source,pad=case(tmp_path)
    other=next(p for f in board.GetFootprints()for p in f.Pads()if p.GetNumber()=='2')
    a=tuple(pad.GetPosition());b=tuple(other.GetPosition());at=[a[0],a[1]+750000]
    prefix=[('trk',a[0],a[1],*at,200000,pcbnew.F_Cu),('via',*at,200000,300000)]
    def choices(board,p,**kw):
        return dict(choices=[dict(at_nm=at,layers=LAYERS,operations=prefix,
            proposed_not_retained_native_contact=True)]if force._uid(p)==force._uid(pad)else[])
    monkeypatch.setattr(local,'propose',choices)
    seen=[]
    native_before=field._field_snapshot_inventory(board)
    def guard(ops):seen.append(ops);return guard_passes
    def bridge(board,A,al,B,bl,width,*args,**kw):
        from cec_native_route_portal import endpoint_layers
        assert endpoint_layers(board,A,pad.GetNetCode())&set(al)
        assert endpoint_layers(board,B,pad.GetNetCode())&set(bl)
        ops=[('trk',pcbnew.VECTOR2I(*A),pcbnew.VECTOR2I(*B),width,pcbnew.In2_Cu)]
        return ops if kw['ops_ok'](ops)else None
    monkeypatch.setattr(fr,'_lastmile_bridge',bridge)
    menus=[[dict(at_nm=list(a),layers=[pcbnew.F_Cu],native_uuids=[force._uid(pad)])],
        [dict(at_nm=list(b),layers=[pcbnew.F_Cu],native_uuids=[force._uid(other)])]]
    result,r=geometry._source_local_operations(board,[pad,other],menus,net=pad.GetNetname(),
        width=200000,clearance=200000,layers=LAYERS,bridges=[pcbnew.In2_Cu],deadline=time.monotonic()+2.,
        guard=guard,planar=None,turn_guard=None)
    assert bool(result)==guard_passes and seen
    assert all(len(ops)==3 and any(op[0]=='via'and op[-2:]==(.2,.3)for op in ops)for ops in seen)
    assert not r['release_authority']and not r['no_path_proof']
    assert field._field_snapshot_inventory(board)==native_before


def test_ordinary_constructor_only_opts_in_after_independent_role_compilation(tmp_path,monkeypatch):
    import cec_certificate_repair as repair
    import cec_ordinary_signal_completion as ordinary
    from test_ordinary_native_portals import fixture
    source,board,net=fixture(tmp_path);candidate=force._copy_family(source,tmp_path/'child');seen=[]
    monkeypatch.setattr(repair,'_spawn_apply',lambda worker,args,**kw:seen.append(args[1])or dict(closed=0))
    ordinary.construct_private(source,candidate,dict(net=net),board_hint='synthetic')
    assert seen[0]['source_local_pad_rule_launches']is True
    assert seen[0]['width_mm']==.22 and seen[0]['clearance_mm']==.2


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_saved_generated_launch_keeps_existing_rule_and_requires_native_membership(tmp_path,face):
    import cec_certificate_repair as repair
    import cec_native_drc_runner as native
    from cec_route_proposal_guard import RouteProposalGuard
    board,source,pad=case(tmp_path,face=face);before=force._family(source)
    q=offer(board,pad)
    row=next(r for r in q['choices']if r['kind']=='bounded_source_dogbone')
    made=repair._lay_ops(board,RouteProposalGuard._unpack(row['operations']),pad.GetNetCode())
    via=next(t for t in board.GetTracks()if force._uid(t)in made['uuids']and t.GetClass()=='PCB_VIA')
    assert fr.group_local_pofv_signal_vias(board,[via])
    child=force._copy_family(source,tmp_path/'owned');field._save_field_snapshot(board,child)
    assert source.with_suffix('.kicad_dru').read_bytes()==child.with_suffix('.kicad_dru').read_bytes()
    assert before==force._family(source)
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('requires explicit native rule reporting build')
    def dimensions(path,label):
        output=tmp_path/(label+'.json');r=native.run(path,output,reporting_build=Path(build),timeout_s=10.)
        assert r['ok']and r['complete']and not r['native_inventory']['potentially_truncated']
        return {v['type']for v in json.loads(output.read_text())['violations']
            if v['type']in('via_diameter','drill_out_of_range','annular_width')
            and any(i.get('uuid')==force._uid(via)for i in v['items'])}
    assert not dimensions(child,'actual-owned-local-launch')
    outside=pcbnew.LoadBoard(str(child));v=next(t for t in outside.GetTracks()if force._uid(t)==force._uid(via))
    next(g for g in outside.Groups()if g.GetName()==rule.GROUP).RemoveItem(v)
    control=force._copy_family(child,tmp_path/'outside');field._save_field_snapshot(outside,control)
    assert dimensions(control,'actual-unowned-control')=={'via_diameter','drill_out_of_range','annular_width'}


@pytest.mark.parametrize('filled',[False,True])
@pytest.mark.parametrize('layer',LAYERS+[pcbnew.In3_Cu])
def test_local_launch_cannot_take_immutable_foreign_power_antipad_credit(tmp_path,filled,layer):
    board,source,pad=case(tmp_path);at=pad.GetPosition()
    z=pcbnew.ZONE(board);z.SetLayer(layer);z.SetNet(board.FindNet('obstruction'))
    poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
    for x,y in((-1,-1),(1,-1),(1,1),(-1,1)):poly.Append(at.x+x*1000000,at.y+y*1000000)
    z.Outline().Append(poly)
    if filled:z.SetFilledPolysList(layer,poly);z.SetIsFilled(True)
    board.Add(z)
    assert not local._immutable_power_clear(board,at,at,300000,layer,200000,pad.GetNetCode())

@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_blocked_nearest_candidates_reach_real_clear_radial_diagonal(tmp_path,angle,face):
    import math
    board,source,pad=case(tmp_path,angle,face)
    pad.GetParentFootprint().SetReference('RENAMED_SOURCE_RADIAL_OWNER')
    centre=pad.GetPosition()
    # Foreign buried cross blocks the centre and every old just-outside
    # cardinal dogbone through-barrel, but not the diagonal native seats.
    for dx,dy in [(1100000,0),(0,1100000)]:
        wall=pcbnew.PCB_TRACK(board);wall.SetNet(board.FindNet('obstruction'))
        wall.SetLayer(pcbnew.In2_Cu);wall.SetWidth(400000)
        wall.SetStart(centre-pcbnew.VECTOR2I(dx,dy));wall.SetEnd(centre+pcbnew.VECTOR2I(dx,dy))
        board.Add(wall)
    field._save_field_snapshot(board,source);board=pcbnew.LoadBoard(str(source))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==force._uid(pad))
    before=force._family(source);native=field._field_snapshot_inventory(board)
    q=offer(board,pad,max_sites=4,deadline=time.monotonic()+5.)
    assert q['complete'] and q['choices'],q
    assert q['generated_face_candidates']<=45  # one centre +12 near +32 radial
    assert all(r['kind']=='bounded_source_radial_dogbone'for r in q['choices']),q
    for row in q['choices']:
        dx,dy=(v-u for u,v in zip(tuple(pad.GetPosition()),row['at_nm']))
        assert abs(dx)==abs(dy) and 750000<math.hypot(dx,dy)<=1500000
        assert row['actual_native_source_rule_preflight']
        assert row['source_rule']['minimum_nm']['via_diameter']==300000
        assert row['source_rule']['minimum_nm']['hole_size']==200000
        assert not row['release_authority'] and row['proposed_not_retained_native_contact']
    assert native==field._field_snapshot_inventory(board) and before==force._family(source)

def test_far_radial_seats_still_require_actual_native_hole_clearance(tmp_path):
    board,source,pad=case(tmp_path);centre=pad.GetPosition()
    # A real foreign plated hole, not a mocked guard, excludes the far
    # cardinal seat at the exact existing maximum reach.
    at=centre+pcbnew.VECTOR2I(1500000,0)
    hole=pcbnew.PCB_VIA(board);hole.SetNet(board.FindNet('obstruction'))
    hole.SetPosition(at);hole.SetWidth(600000);hole.SetDrill(300000)
    hole.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(hole)
    field._save_field_snapshot(board,source);board=pcbnew.LoadBoard(str(source))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==force._uid(pad))
    import cec_decoupler_cell as cells
    assert not cells._hole_to_hole_clear(board,at,.2)[0]
    q=offer(board,pad,max_sites=8)
    assert all(tuple(r['at_nm'])!=tuple(at)for r in q['choices'])
    assert not fr._via_spot_clear(board,at,300000,200000,{pad.GetNetCode()},
        drill_nm=200000,net_code=pad.GetNetCode(),
        local_pofv_dogbone=dict(pad=pad,start=pad.GetPosition(),layer=pcbnew.F_Cu),report={})


def narrow_interval_case(tmp_path,angle=0,face=pcbnew.F_Cu):
    """Real buried walls leave a contained interval, not a stencil seat."""
    board,source,pad=case(tmp_path,angle,face)
    board.Add(pcbnew.NETINFO_ITEM(board,'arbitrary_source_control'))
    pad.SetSize(pcbnew.VECTOR2I(540000,640000));pad.SetNet(board.FindNet('arbitrary_source_control'))
    centre=pad.GetPosition();wall_face=pcbnew.B_Cu if face==pcbnew.F_Cu else pcbnew.F_Cu
    # Offset coordinates are in the actual package frame. These foreign
    # walls block the centre and every historical exterior/radial proposal.
    for A,B,width in [((-1.,-3.),(-1.,3.),1.4),((1.,-3.),(1.,3.),1.),
                      ((-3.,-1.3),(3.,-1.3),1.6),((-3.,1.3),(3.,1.3),1.6)]:
        wall=pcbnew.PCB_TRACK(board);wall.SetNet(board.FindNet('obstruction'));wall.SetLocked(True)
        wall.SetLayer(wall_face);wall.SetWidth(pcbnew.FromMM(width))
        wall.SetStart(centre+pcbnew.VECTOR2I_MM(*A));wall.SetEnd(centre+pcbnew.VECTOR2I_MM(*B))
        wall.Rotate(centre,pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T));board.Add(wall)
    uid=force._uid(pad);field._save_field_snapshot(board,source);board=pcbnew.LoadBoard(str(source))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
    return board,source,pad


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_source_rule_fallback_finds_strict_contained_interval_without_mutation(tmp_path,angle,face):
    import cec_native_contained_via_events as contained
    board,source,pad=narrow_interval_case(tmp_path,angle,face)
    before=force._family(source);native=field._field_snapshot_inventory(board);floors=rule._floors(board)
    q=offer(board,pad,deadline=time.monotonic()+5.,max_sites=4)
    assert q['complete']and q['choices'],q
    assert q['generated_face_candidates']<=45 and q['examined']>q['generated_face_candidates']
    assert q['contained_interval_discovery']['complete']and q['contained_interval_discovery']['events']
    assert all(r['kind']=='contained_source_pad_interval'for r in q['choices']),q
    for row in q['choices']:
        at=pcbnew.VECTOR2I(*row['at_nm']);assert at!=pad.GetPosition()
        assert contained.contains(pad,at,300000)
        assert row['operations']==[('via',at.x,at.y,200000,300000)]
        assert row['actual_native_source_rule_preflight']['pad_uuid']==force._uid(pad)
        # The old centre-only API intentionally remains centre-only.
        assert rule.inspect(board,pad,at,300000,200000,pad.GetNetCode())is None
        assert rule.inspect_contained(board,pad,at,300000,200000,pad.GetNetCode())
        assert not fr._via_spot_clear(board,at,300000,200000,{pad.GetNetCode()},
            drill_nm=200000,net_code=pad.GetNetCode())
        assert fr._via_spot_clear(board,at,300000,200000,{pad.GetNetCode()},
            drill_nm=200000,net_code=pad.GetNetCode(),local_pofv_contained_pad=pad)
        assert not row['release_authority']and row['proposed_not_retained_native_contact']
    assert before==force._family(source)and native==field._field_snapshot_inventory(board)
    assert floors==rule._floors(board)


@pytest.mark.parametrize('fault',['outside_land','buried_copper','forged_event','missing_rule',
    'pad_changed','ambiguous_land','wrong_net','ordinary_context','mixed_context','denied_rule'])
def test_interval_metadata_never_replaces_source_or_full_native_guards(tmp_path,monkeypatch,fault):
    board,source,pad=narrow_interval_case(tmp_path)
    row=offer(board,pad,max_sites=1)['choices'][0];at=pcbnew.VECTOR2I(*row['at_nm'])
    if fault=='outside_land':at=pad.GetPosition()+pcbnew.VECTOR2I(250000,0)
    elif fault=='buried_copper':
        wall=pcbnew.PCB_TRACK(board);wall.SetNet(board.FindNet('obstruction'))
        wall.SetLayer(pcbnew.In3_Cu);wall.SetWidth(100000)
        wall.SetStart(at-pcbnew.VECTOR2I(1000000,0));wall.SetEnd(at+pcbnew.VECTOR2I(1000000,0));board.Add(wall)
    elif fault=='forged_event':
        monkeypatch.setattr(local.contained_events,'candidates',lambda *a,**kw:dict(
            complete=True,events=[dict(at_nm=list(pad.GetPosition()),strict_native_pad_containment=True)]))
        assert not offer(board,pad)['choices'];return
    elif fault=='missing_rule':source.with_suffix('.kicad_dru').unlink()
    elif fault=='pad_changed':pad.Move(pcbnew.VECTOR2I(1,0))
    elif fault=='ambiguous_land':
        clone=pcbnew.PAD(pad.GetParentFootprint());clone.SetNumber('second_actual_owner')
        clone.SetNet(pad.GetNet());clone.SetPosition(pad.GetPosition());clone.SetSize(pad.GetSize())
        clone.SetShape(pad.GetShape());clone.SetAttribute(pad.GetAttribute());clone.SetLayerSet(pad.GetLayerSet())
        pad.GetParentFootprint().Add(clone)
    elif fault=='denied_rule':monkeypatch.setattr(rule,'inspect_contained',lambda *a:None)
    code=pad.GetNetCode()+(1 if fault=='wrong_net'else 0)
    context=(dict(local_pofv_pad=pad)if fault=='ordinary_context'else
        dict(local_pofv_pad=pad,local_pofv_contained_pad=pad)if fault=='mixed_context'else
        dict(local_pofv_contained_pad=pad))
    assert not fr._via_spot_clear(board,at,300000,200000,{code},
        drill_nm=200000,net_code=code,**context)


def test_successful_legacy_menu_does_not_spend_an_interval_discovery_lease(tmp_path,monkeypatch):
    board,source,pad=case(tmp_path)
    def unexpected(*a,**kw):raise AssertionError('legacy positive portfolio must stay first')
    monkeypatch.setattr(local.contained_events,'candidates',unexpected)
    q=offer(board,pad,max_sites=1)
    assert q['choices']and q['contained_interval_discovery']is None


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_independent_contained_tier_cannot_be_starved_by_legal_exterior_land(tmp_path,face):
    board,source,pad=narrow_interval_case(tmp_path,face=face)
    for wall in list(board.GetTracks()):
        if wall.GetClass()=='PCB_TRACK'and wall.GetWidth()in(1000000,1600000):board.Remove(wall)
    uid=force._uid(pad);field._save_field_snapshot(board,source);board=pcbnew.LoadBoard(str(source))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
    old=offer(board,pad,max_sites=1)
    assert old['choices'][0]['kind']=='bounded_source_dogbone'
    q=offer(board,pad,contained_intervals_only=True,max_sites=1)
    assert q['complete']and q['choices'][0]['kind']=='contained_source_pad_interval'
    assert q['generated_face_candidates']==1
    assert q['choices'][0]['actual_native_source_rule_preflight']


@pytest.mark.parametrize('value',[0,1,'yes',None])
def test_contained_tier_is_an_explicit_bool_not_fabrication_permission(tmp_path,value):
    board,source,pad=case(tmp_path)
    with pytest.raises(ValueError,match='bounded_exact_saved_rule_signal_launch'):
        offer(board,pad,contained_intervals_only=value)


@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_contained_interval_needs_real_group_membership_under_existing_native_rule(tmp_path,face):
    import cec_certificate_repair as repair
    import cec_native_drc_runner as native
    from cec_route_proposal_guard import RouteProposalGuard
    board,source,pad=narrow_interval_case(tmp_path,face=face);before=force._family(source)
    q=offer(board,pad,max_sites=1);row=q['choices'][0]
    assert row['kind']=='contained_source_pad_interval'
    made=repair._lay_ops(board,RouteProposalGuard._unpack(row['operations']),pad.GetNetCode())
    via=next(t for t in board.GetTracks()if force._uid(t)in made['uuids'])
    evidence=fr.group_local_pofv_signal_vias(board,[via]);assert evidence
    child=force._copy_family(source,tmp_path/'contained-owned');field._save_field_snapshot(board,child)
    assert before==force._family(source)
    assert source.with_suffix('.kicad_dru').read_bytes()==child.with_suffix('.kicad_dru').read_bytes()
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    assert build,'explicit native rule reporting build required for this regression'
    def dimensions(path,label):
        output=tmp_path/(label+'.json');r=native.run(path,output,reporting_build=Path(build),timeout_s=10.)
        assert r['ok']and r['complete']and not r['native_inventory']['potentially_truncated']
        return {v['type']for v in json.loads(output.read_text())['violations']
            if v['type']in('via_diameter','drill_out_of_range','annular_width')
            and any(i.get('uuid')==force._uid(via)for i in v['items'])}
    assert not dimensions(child,'actual-contained-owned')
    control=pcbnew.LoadBoard(str(child));v=next(t for t in control.GetTracks()if force._uid(t)==force._uid(via))
    next(g for g in control.Groups()if g.GetName()==rule.GROUP).RemoveItem(v)
    outside=force._copy_family(child,tmp_path/'contained-outside');field._save_field_snapshot(control,outside)
    assert dimensions(outside,'actual-contained-outside')=={'via_diameter','drill_out_of_range','annular_width'}

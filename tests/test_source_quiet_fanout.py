"""Experimental fan-out scope uses native saved boards, not route mocks."""
import copy
import time
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_current_topology as topology
import cec_measurement_quiet_fanout as op
from test_isolated_measurement_completion import case,refused


def fixture(tmp_path,monkeypatch,quarter=0):
    source,root_uid,target_uid=case(tmp_path,monkeypatch,renamed=True)
    b=pcbnew.LoadBoard(str(source));pads=op._native_pads(b)
    root,target=pads[root_uid],pads[target_uid]
    opposite=next(p for p in target.GetParentFootprint().Pads() if force._uid(p)!=target_uid)
    peer_owner=pcbnew.FOOTPRINT(b);peer_owner.SetReference('SECOND_TYPED_CONSUMER')
    peer_owner.SetValue('INA181A2IDBVR')
    peer_owner.SetFPID(pcbnew.LIB_ID('Package_TO_SOT_SMD','SOT-23-6'));b.Add(peer_owner)
    def land(pin,net,at):
        p=pcbnew.PAD(peer_owner);p.SetNumber(pin);p.SetNet(net)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        p.SetPosition(pcbnew.VECTOR2I_MM(*at));peer_owner.Add(p);return p
    peer=land('3',root.GetNet(),(14,12));land('4',opposite.GetNet(),(14,16))
    paths=[((20,10),(18,10)),((18,10),(16,12)),((16,12),(14,12))]
    quiet=[]
    for a,c in paths:
        t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(250000)
        t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*c));b.Add(t);quiet.append(force._uid(t))
    if quarter:
        pivot=pcbnew.VECTOR2I_MM(30,30);angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for item in[*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:item.Rotate(pivot,angle)
    anchor=target.GetParentFootprint().GetReference()
    domains={n.GetNetname():dict(complete=True,authority_refs=[anchor],source_refs=[anchor],sink_refs=[])
        for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:copy.deepcopy(domains))
    field._save_field_snapshot(b,source)
    return source,root_uid,target_uid,force._uid(peer),quiet


def proposal(source,root,peer,**kw):
    return op.plan(pcbnew.LoadBoard(str(source)),source,board_hint='RENAMED_SOURCE',
        pad_uuid=root,peer_pad_uuid=peer,**kw)


def child(source,tmp_path,q,points=None,fault=None):
    candidate=force._copy_family(source,tmp_path/'private')
    b=pcbnew.LoadBoard(str(candidate));pads=op._native_pads(b);root=pads[q['pad_uuid']]
    if points is None:
        port=q['ports'][0];a=tuple(root.GetPosition());c=tuple(port['at_nm'])
        import cec_fr as fr
        points=fr._canonical_45_xy_paths(a,c)[0]
    for a,c in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*c))
        t.SetLayer(pcbnew.B_Cu if fault=='back' else pcbnew.F_Cu)
        t.SetNet(root.GetNet());t.SetWidth(100000 if fault=='thin' else 200000);b.Add(t)
    if fault=='moved_peer':pads[q['peer_pad_uuid']].GetParentFootprint().Move(pcbnew.VECTOR2I_MM(.1,0))
    if fault=='source_cut':
        from cec_native_items import discard_items
        discard_items(b,[t for t in b.GetTracks() if force._uid(t) in q['source_quiet_tree']['track_uuids']][:1])
    if fault=='via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(root.GetPosition());v.SetNet(root.GetNet())
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    field._save_field_snapshot(b,candidate)
    return candidate


@pytest.mark.parametrize('quarter',range(4))
def test_actual_saved_quiet_land_fanout_is_additive_not_new_shunt_pickup(tmp_path,monkeypatch,quarter):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch,quarter)
    before=source.read_bytes();q=proposal(source,root,peer)
    assert q['complete'],(q.get('reason'),q.get('refusals'),q.get('source_request',{}).get('reason'))
    assert q['source_quiet_tree']['exact_shunt_pad_uuid']==target
    assert set(q['source_quiet_tree']['track_uuids'])==set(quiet)
    candidate=child(source,tmp_path,q)
    r=op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=root,peer_pad_uuid=peer)
    assert r['ok'] and r['complete'],r
    assert r['candidate_components']==r['source_components']-1
    assert source.read_bytes()==before
    assert not any(r[k] for k in('routing_admitted','kelvin_qualified','current_authority','release_authority'))


@pytest.mark.parametrize('fault',['unknown_peer','power_pin','unknown_mpn','dnp',
    'force_contact','back_quiet','wide_quiet','thin_quiet','same_net_peer','interior_port'])
def test_source_ownership_is_not_same_net_or_caller_permission(tmp_path,monkeypatch,fault):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));pads=op._native_pads(b);p=pads[peer]
    kwargs={}
    if fault=='unknown_peer':peer='arbitrary_same_net_uuid'
    elif fault=='power_pin':p.SetNumber('6')
    elif fault=='unknown_mpn':p.GetParentFootprint().SetValue('UNQUALIFIED')
    elif fault=='dnp':p.GetParentFootprint().SetDNP(True)
    elif fault=='back_quiet':
        for t in b.GetTracks():
            if force._uid(t) in quiet:t.SetLayer(pcbnew.B_Cu)
    elif fault=='wide_quiet':
        for t in b.GetTracks():
            if force._uid(t) in quiet:t.SetWidth(400000)
    elif fault=='thin_quiet':
        for t in b.GetTracks():
            if force._uid(t) in quiet:t.SetWidth(100000)
    elif fault=='same_net_peer':p.GetParentFootprint().FindPadByNumber('4').SetNet(p.GetNet())
    elif fault=='interior_port':kwargs['port_key']='junction:worker_invented_location'
    else:
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(16,12));t.SetEnd(pcbnew.VECTOR2I_MM(16,20))
        t.SetWidth(750000);t.SetLayer(pcbnew.F_Cu);t.SetNet(p.GetNet());b.Add(t)
    field._save_field_snapshot(b,source)
    refused(lambda:proposal(source,root,peer,**kwargs))


@pytest.mark.parametrize('fault',['thin','back','source_cut','moved_peer','via'])
def test_saved_delta_cannot_retire_move_reclassify_or_bridge(tmp_path,monkeypatch,fault):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch);q=proposal(source,root,peer)
    assert q['complete'],q
    candidate=child(source,tmp_path,q,fault=fault)
    r=op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=root,peer_pad_uuid=peer)
    assert not r['ok'] and not r['complete'],r


def test_exact_junction_is_source_derived_not_arbitrary_track_interior(tmp_path,monkeypatch):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch);q=proposal(source,root,peer)
    junction=next(p for p in q['ports'] if p['at_nm']==[16000000,12000000])
    q['ports']=[junction]
    # Approach from below/left without crossing the retained input land.
    points=[[10000000,10000000],[10000000,14000000],[11000000,15000000],
        [15000000,15000000],[16000000,14000000],[16000000,12000000]]
    candidate=child(source,tmp_path,q,points)
    r=op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=root,peer_pad_uuid=peer)
    assert r['ok'] and r['complete'],r


def test_geometry_recompiles_ignores_worker_width_and_ops(tmp_path,monkeypatch):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch);q=proposal(source,root,peer)
    q=copy.deepcopy(q);q['width_nm']=1;q['ops']=[['via',[0,0],1,1]]
    candidate=force._copy_family(source,tmp_path/'constructor')
    r=op.construct_private(source,candidate,q,board_hint='RENAMED_SOURCE')
    assert r['complete'],r
    assert all(row[0]=='trk' and row[3]==200000 for row in r['ops'])
    received=op.receive(source,candidate,board_hint='RENAMED_SOURCE',pad_uuid=root,peer_pad_uuid=peer)
    assert received['ok'] and received['complete'],received


@pytest.mark.parametrize('points',[
    [(10,10),(12,8),(8,8),(12,12),(10,12),(10,11),(11,10)],
    [(10,10),(16,10),(13,10),(13,11),(14,12)]])
def test_endpoint_linear_graph_does_not_hide_nonadjacent_native_body_contacts(tmp_path,monkeypatch,points):
    source,root,target,peer,quiet=fixture(tmp_path,monkeypatch)
    b=pcbnew.LoadBoard(str(source));pad=op._native_pads(b)[root];items=[]
    for a,z in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z))
        t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetNet(pad.GetNet());b.Add(t);items.append(t)
    with pytest.raises(ValueError,match='nonadjacent_native_copper_contact'):
        op._ordered_branch(items,pad,width_nm=200000,deadline=time.monotonic()+2.)

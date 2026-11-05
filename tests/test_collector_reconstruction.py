"""Native collector preflight; fixture authority is explicit, never inferred share."""
import math
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_collector_reconstruction as collector
import cec_current_topology as topology
import cec_fab_profile as fab


def fixture(monkeypatch, angle=0, face='F.Cu'):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    board.SetFileName('synthetic-collector.kicad_pcb')
    net = pcbnew.NETINFO_ITEM(board, '/ARBITRARY_SHARED_RAIL')
    other = pcbnew.NETINFO_ITEM(board, '/ARBITRARY_FOREIGN')
    board.Add(net); board.Add(other)
    def at(x, y):
        x, y = x-40, y-40
        for _ in range(angle//90):
            x, y = -y, x
        return pcbnew.VECTOR2I_MM(x+40, y+40)
    for a, b in zip(((0,0),(80,0),(80,80),(0,80)), ((80,0),(80,80),(0,80),(0,0))):
        edge = pcbnew.PCB_SHAPE(board); edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT); edge.SetWidth(100000)
        edge.SetStart(at(*a)); edge.SetEnd(at(*b)); board.Add(edge)
    pads = []
    for ref, points in (('RENAMED_BANK', [(20,40),(30,40)]), ('RENAMED_SINK',[(60,40)])):
        fp = pcbnew.FOOTPRINT(board); fp.SetReference(ref); board.Add(fp)
        for number, point in enumerate(points, 1):
            pad = pcbnew.PAD(fp); fp.Add(pad); pad.SetNumber(str(number)); pad.SetNet(net)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH); pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I_MM(2.7,2.7)); pad.SetDrillSize(pcbnew.VECTOR2I_MM(1.8,1.8))
            pad.SetLayerSet(pcbnew.LSET.AllCuMask()); pad.SetPosition(at(*point)); pads.append(pad)
    # The fixture supplies ONE declared aggregate. Contact count grants no
    # per-pin current, and widths use the real selected factory buildup.
    authority = dict(amps=20., geometry_margin=1.25, margin_included=False, source='explicit_synthetic_authority')
    widths = {layer:fab.ipc2221_required_width_mm(20., layer,
        profile_name='jlcpcb_6l_pofv_high_current', rise_c=30., margin=1.25)
        for layer in fab.COPPER_LAYERS}
    domain = dict(complete=True, source_refs=('RENAMED_BANK',), sink_refs=('RENAMED_SINK',))
    contract = dict(net=net.GetNetname(), amps=20., required_by_layer_mm=widths,
        geometry_margin=1.25, current_authority=authority)
    monkeypatch.setattr(topology, 'board_current_domains', lambda *args,**kwargs:{net.GetNetname():domain})
    monkeypatch.setattr(topology, 'route_width_contracts', lambda *args,**kwargs:{net.GetNetname():contract})
    def mm(point): return [v/1e6 for v in at(*point)]
    paths = [dict(layer=face, points_mm=[mm((20,40)),mm((60,40))])]
    return board, net, other, pads, at, paths, contract


def screen(board, net, paths, **kwargs):
    return collector.preflight(board, net.GetNetname(), paths,
        board_hint='atx-24pin-rev3', **kwargs)


@pytest.mark.parametrize('angle', [0,90,180,270])
@pytest.mark.parametrize('face', ['F.Cu','B.Cu'])
def test_both_faces_all_rotations_keep_full_aggregate_and_all_contacts(monkeypatch, angle, face):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch,angle,face)
    before = len(list(b.GetTracks())),[(p.m_Uuid.AsString(),tuple(p.GetPosition())) for p in pads]
    result = screen(b,n,paths)
    assert result['ok'] and result['complete_source_bank_contact'], result
    assert result['checks'][0]['width_nm'] == math.ceil(contract['required_by_layer_mm'][face]*1e6)
    assert result['no_per_contact_current_division'] and result['no_copper_mutated']
    assert not result['release_authority'] and not result['routing_admitted']
    assert before == (len(list(b.GetTracks())),[(p.m_Uuid.AsString(),tuple(p.GetPosition())) for p in pads])


@pytest.mark.parametrize('face', ['F.Cu','B.Cu'])
def test_npth_barrel_blocks_both_faces_with_native_identity(monkeypatch, face):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch,face=face)
    fp = pcbnew.FOOTPRINT(b); fp.SetReference('MOVED_HOLE_OWNER'); b.Add(fp)
    hole = pcbnew.PAD(fp); fp.Add(hole); hole.SetNumber('')
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH); hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetSize(pcbnew.VECTOR2I_MM(3.2,3.2)); hole.SetDrillSize(pcbnew.VECTOR2I_MM(3.2,3.2))
    hole.SetLayerSet(pcbnew.LSET.AllCuMask()); hole.SetPosition(at(45,40))
    result = screen(b,n,paths)
    assert not result['ok'] and not result['geometric_paths_clear']
    assert hole.m_Uuid.AsString() in result['blocker_uuids']
    row = next(r for r in result['checks'][0]['native_hits'] if r.get('uuid')==hole.m_Uuid.AsString())
    assert row['owner_ref']=='MOVED_HOLE_OWNER' and row['drilled']
    assert not row['automatic_ripup_authorized']


@pytest.mark.parametrize('kind',['pad','zone','footprint_graphic'])
def test_foreign_physical_obstacle_keeps_exact_native_owner_identity(monkeypatch,kind):
    b,n,other,pads,at,paths,contract=fixture(monkeypatch)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('RENAMED_OBSTACLE_OWNER');b.Add(fp)
    if kind=='pad':
        item=pcbnew.PAD(fp);fp.Add(item);item.SetNumber('9');item.SetNet(other)
        item.SetAttribute(pcbnew.PAD_ATTRIB_SMD);item.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        item.SetSize(pcbnew.VECTOR2I_MM(2,2));item.SetLayerSet(layers);item.SetPosition(at(45,40))
    elif kind=='zone':
        item=pcbnew.ZONE(b);item.SetLayer(pcbnew.F_Cu);item.SetNet(other)
        item.SetZoneName('CEC_RECTILINEAR_POWER_CONTOUR');b.Add(item)
        poly=item.Outline();poly.NewOutline()
        for point in ((44,39),(46,39),(46,41),(44,41)):poly.Append(at(*point))
    else:
        item=pcbnew.PCB_SHAPE(fp);fp.Add(item);item.SetLayer(pcbnew.F_Cu)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT);item.SetWidth(200000)
        item.SetStart(at(45,39));item.SetEnd(at(45,41))
    result=screen(b,n,paths)
    row=next(hit for check in result['checks'] for hit in check['native_hits'] if hit.get('uuid')==item.m_Uuid.AsString())
    assert not result['ok'] and row['kind']==kind
    assert row['native_kind']==item.GetClass() and not row['automatic_ripup_authorized']
    if kind!='zone':assert row['footprint_uuid']==fp.m_Uuid.AsString()


def test_missing_diagnostic_uuid_never_drops_a_native_obstacle(monkeypatch):
    import cec_fr as fr
    b,n,other,pads,at,paths,contract=fixture(monkeypatch)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('ADAPTER');b.Add(fp)
    native=pcbnew.PAD(fp);fp.Add(native);native.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    native.SetShape(pcbnew.PAD_SHAPE_RECT);native.SetNet(other)
    layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
    native.SetSize(pcbnew.VECTOR2I_MM(2,2));native.SetLayerSet(layers);native.SetPosition(at(45,40))
    class Adapter:
        def __getattr__(self,key):
            if key=='m_Uuid':raise AttributeError('diagnostic UUID unavailable')
            return getattr(native,key)
    monkeypatch.setattr(fp,'Pads',lambda:[Adapter()])
    monkeypatch.setattr(b,'GetFootprints',lambda:[fp])
    zones,copper=fr._layer_foreign_shapes(b,pcbnew.F_Cu,{n.GetNetCode()},identified=True)
    row=next(row for row in copper if row[2].get('kind')=='pad')
    assert row[2]['native_identity_unavailable'] and row[0].Collide(
        pcbnew.SHAPE_SEGMENT(at(20,40),at(60,40),6535523),200000)


def test_missing_contact_is_not_hidden_by_rail_or_outline_progress(monkeypatch):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch)
    paths[0]['points_mm'] = [[30,40],[60,40]]
    result = screen(b,n,paths)
    assert result['geometric_paths_clear'] and not result['ok']
    assert result['unconnected_source_pins'][0]['pin']=='1'


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('offset_mm',[0,1.0])
def test_source_locating_hole_outside_outline_refuses_even_when_all_routes_fit(monkeypatch,angle,offset_mm):
    b,n,other,pads,at,paths,contract=fixture(monkeypatch,angle=angle)
    fp=next(fp for fp in b.GetFootprints() if fp.GetReference()=='RENAMED_BANK')
    hole=pcbnew.PAD(fp);fp.Add(hole);hole.SetNumber('')
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH);hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    hole.SetDrillSize(pcbnew.VECTOR2I_MM(3.2,3.2));hole.SetSize(pcbnew.VECTOR2I_MM(3.2,3.2))
    hole.SetPosition(at(78.8,70));hole.SetOffset(pcbnew.VECTOR2I_MM(offset_mm,0))
    result=screen(b,n,paths)
    assert result['geometric_paths_clear'] and result['complete_source_bank_contact']
    assert not result['ok'] and not result['source_mount_material_clear']
    assert any(r['uuid']==hole.m_Uuid.AsString() and not r['hole_inside_material'] for r in result['source_holes'])
    assert not list(b.GetTracks())


def test_source_slot_crossing_a_closed_cutout_refuses_not_just_bbox(monkeypatch):
    b,n,other,pads,at,paths,contract=fixture(monkeypatch)
    fp=next(fp for fp in b.GetFootprints() if fp.GetReference()=='RENAMED_BANK')
    hole=pcbnew.PAD(fp);fp.Add(hole);hole.SetNumber('')
    hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH);hole.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
    hole.SetDrillSize(pcbnew.VECTOR2I_MM(8,2));hole.SetSize(pcbnew.VECTOR2I_MM(8,2))
    hole.SetPosition(at(40,70))
    vertices=((42,68),(44,68),(44,72),(42,72))
    for a,z in zip(vertices,vertices[1:]+vertices[:1]):
        e=pcbnew.PCB_SHAPE(b);e.SetLayer(pcbnew.Edge_Cuts);e.SetShape(pcbnew.SHAPE_T_SEGMENT)
        e.SetStart(at(*a));e.SetEnd(at(*z));e.SetWidth(100000);b.Add(e)
    result=screen(b,n,paths)
    assert result['geometric_paths_clear'] and result['complete_source_bank_contact']
    assert not result['ok'] and not result['source_mount_material_clear']


def test_thin_inner_layer_does_not_borrow_outer_capacity(monkeypatch):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch,face='In3.Cu')
    result = screen(b,n,paths)
    assert result['checks'][0]['width_nm'] == math.ceil(contract['required_by_layer_mm']['In3.Cu']*1e6)
    assert result['checks'][0]['width_nm'] > result['current_width_contract']['required_by_layer_mm']['F.Cu']*1e6
    assert not result['ok'] and not result['checks'][0]['material_clear']


@pytest.mark.parametrize('face', ['In1.Cu','In4.Cu','Edge.Cuts','In5.Cu'])
def test_reference_planes_and_absent_layers_are_not_escape_routes(monkeypatch, face):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch,face=face)
    with pytest.raises(ValueError,match='unpermitted_native_copper_layer'):
        screen(b,n,paths)


@pytest.mark.parametrize('bad', [0,-1,11,float('nan'),True])
def test_unbounded_budget_refuses_without_mutation(monkeypatch, bad):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch)
    with pytest.raises(ValueError,match='bounded_native_budget'):
        screen(b,n,paths,timeout_s=bad)
    assert not list(b.GetTracks())


@pytest.mark.parametrize('change', ['caller_width','non45','zero','nonfinite','overflow','path_bound'])
def test_no_caller_width_or_noncanonical_centerline_can_sneak_through(monkeypatch, change):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch)
    if change=='caller_width': paths[0]['width_mm']=1.4
    if change=='non45': paths[0]['points_mm']=[[20,40],[55,41]]
    if change=='zero': paths[0]['points_mm']=[[20,40],[20,40]]
    if change=='nonfinite': paths[0]['points_mm']=[[float('inf'),40],[60,40]]
    if change=='overflow': paths[0]['points_mm']=[[2100,40],[60,40]]
    if change=='path_bound': paths=paths*65
    with pytest.raises(ValueError): screen(b,n,paths)
    assert not list(b.GetTracks())


def test_explicit_locked_cut_resolves_all_exact_items_without_mutation(monkeypatch):
    b,n,other,pads,at,paths,contract = fixture(monkeypatch)
    track = pcbnew.PCB_TRACK(b); track.SetStart(at(20,40)); track.SetEnd(at(60,40))
    track.SetLayer(pcbnew.F_Cu); track.SetWidth(6535523); track.SetNet(n); track.SetLocked(True); b.Add(track)
    live, receipt = collector.owned_retirement(b,n.GetNetname(),track_uuids=[track.m_Uuid.AsString()])
    assert live==[track] and receipt['explicit_locked_cut_authority']
    assert len(list(b.GetTracks()))==1 and track.IsLocked()
    for ids in ([track.m_Uuid.AsString(),'stale'],[track.m_Uuid.AsString()]*2):
        with pytest.raises(ValueError):collector.owned_retirement(b,n.GetNetname(),track_uuids=ids)
        assert len(list(b.GetTracks()))==1
    with pytest.raises(ValueError):collector.owned_retirement(b,other.GetNetname(),track_uuids=[track.m_Uuid.AsString()])
    group=pcbnew.PCB_GROUP(b); b.Add(group); group.AddItem(track)
    with pytest.raises(ValueError,match='owner_or_kind_mismatch'):
        collector.owned_retirement(b,n.GetNetname(),track_uuids=[track.m_Uuid.AsString()])
    assert group.ContainsItem(track)


def cut_fixture(monkeypatch,angle=0):
    b,n,other,pads,at,paths,contract=fixture(monkeypatch,angle=angle)
    via=pcbnew.PCB_VIA(b);via.SetPosition(at(45,20));via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetWidth(600000);via.SetDrill(300000)
    via.SetNet(n);via.SetLocked(True);b.Add(via)
    tracks=[]
    for layer,start,end in [(pcbnew.F_Cu,(43,20),(45,20)),(pcbnew.B_Cu,(45,20),(45,23))]:
        t=pcbnew.PCB_TRACK(b);t.SetLayer(layer);t.SetStart(at(*start));t.SetEnd(at(*end))
        t.SetWidth(500000);t.SetNet(n);t.SetLocked(True);b.Add(t);tracks.append(t)
    return b,n,other,at,via,tracks


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_exact_branch_cut_proves_and_explicitly_resolves_its_stranded_barrel(monkeypatch,angle):
    b,n,other,at,via,tracks=cut_fixture(monkeypatch,angle)
    uid=via.m_Uuid.AsString();cuts=[t.m_Uuid.AsString() for t in tracks]
    proof=collector.exclusive_cut_via_proof(b,[uid],cuts)
    assert proof[0]['exact_cut_exclusivity'] and len(proof[0]['contact_layers'])==2
    assert proof[0]['source_contact_track_uuids']==sorted(cuts)
    assert not proof[0]['automatic_retirement_authority'] and not proof[0]['current_qualified']
    live,receipt=collector.owned_retirement(b,n.GetNetname(),track_uuids=cuts,via_uuids=[uid])
    assert len(live)==3 and receipt['via_uuids']==[uid]
    assert len(list(b.GetTracks()))==3  # proof and resolution are read-only


@pytest.mark.parametrize('kind',['pad','surviving_track','group','zone','incomplete_cut','foreign_net'])
def test_branch_cut_cannot_adopt_unowned_or_surviving_contacts(monkeypatch,kind):
    b,n,other,at,via,tracks=cut_fixture(monkeypatch)
    uid=via.m_Uuid.AsString();cuts=[t.m_Uuid.AsString() for t in tracks]
    if kind=='pad':
        fp=pcbnew.FOOTPRINT(b);b.Add(fp);pad=pcbnew.PAD(fp);fp.Add(pad)
        pad.SetNet(n);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1,1));pad.SetPosition(at(45,20))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
    elif kind=='surviving_track':
        t=pcbnew.PCB_TRACK(b);t.SetNet(n);t.SetLayer(pcbnew.In2_Cu);t.SetWidth(200000)
        t.SetStart(at(45,20));t.SetEnd(at(47,20));b.Add(t)
    elif kind=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(tracks[0])
    elif kind=='zone':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.In2_Cu);z.SetNet(n);z.Outline().NewOutline()
        for point in [(44,19),(46,19),(46,21),(44,21)]:z.Outline().Append(at(*point))
        b.Add(z)
    elif kind=='incomplete_cut':cuts=cuts[:1]
    else:tracks[0].SetNet(other)
    with pytest.raises(ValueError):collector.exclusive_cut_via_proof(b,[uid],cuts)
    assert len(list(b.GetTracks()))>=3


def test_explicit_barrel_retirement_does_not_infer_net_or_group_authority(monkeypatch):
    b,n,other,at,via,tracks=cut_fixture(monkeypatch)
    uid=via.m_Uuid.AsString()
    with pytest.raises(ValueError):collector.owned_retirement(b,other.GetNetname(),via_uuids=[uid])
    with pytest.raises(ValueError):collector.owned_retirement(b,n.GetNetname(),via_uuids=[uid,uid])
    with pytest.raises(ValueError):collector.owned_retirement(b,n.GetNetname(),via_uuids=['stale'])
    group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(via)
    with pytest.raises(ValueError):collector.owned_retirement(b,n.GetNetname(),via_uuids=[uid])


def two_rail_fixture(monkeypatch, *, other_y=60, other_face='F.Cu'):
    b,n,other,pads,at,paths,contract=fixture(monkeypatch)
    for ref,point in (('ARBITRARY_SECOND_SOURCE',(20,other_y)),
                      ('ARBITRARY_SECOND_SINK',(60,other_y))):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);b.Add(fp)
        pad=pcbnew.PAD(fp);fp.Add(pad);pad.SetNumber('A');pad.SetNet(other)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I_MM(2.7,2.7));pad.SetDrillSize(pcbnew.VECTOR2I_MM(1.8,1.8))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask());pad.SetPosition(at(*point))
    domains={n.GetNetname():dict(complete=True,source_refs=['RENAMED_BANK'],sink_refs=['RENAMED_SINK']),
        other.GetNetname():dict(complete=True,source_refs=['ARBITRARY_SECOND_SOURCE'],sink_refs=['ARBITRARY_SECOND_SINK'])}
    contracts={n.GetNetname():contract,other.GetNetname():dict(contract,net=other.GetNetname())}
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**k:domains)
    monkeypatch.setattr(topology,'route_width_contracts',lambda *a,**k:contracts)
    proposals=[dict(net=n.GetNetname(),paths=paths),dict(net=other.GetNetname(),
        paths=[dict(layer=other_face,points_mm=[[20,other_y],[60,other_y]])])]
    return b,n,other,proposals


@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
def test_joint_bank_native_widths_cover_every_source_without_mutation(monkeypatch,face):
    b,n,other,proposals=two_rail_fixture(monkeypatch,other_face=face)
    result=collector.preflight_bank(b,proposals,board_hint='atx-24pin-rev3')
    assert result['ok'] and not result['proposed_collector_conflicts'],result
    assert all(r['complete_source_bank_contact'] for r in result['members'])
    assert result['no_copper_mutated'] and not list(b.GetTracks())
    assert not result['release_authority'] and not result['routing_admitted']


@pytest.mark.parametrize('other_face',['F.Cu','B.Cu'])
def test_joint_future_crossing_uses_actual_layer_not_projected_picture(monkeypatch,other_face):
    b,n,other,proposals=two_rail_fixture(monkeypatch,other_face=other_face)
    proposals[0]['paths'][0]['points_mm']=[[20,40],[40,40],[40,60]]
    result=collector.preflight_bank(b,proposals,board_hint='atx-24pin-rev3')
    assert all(row['ok'] for row in result['members'])
    assert bool(result['proposed_collector_conflicts']) == (other_face=='F.Cu')
    assert result['ok'] == (other_face!='F.Cu')
    assert not list(b.GetTracks())


def test_joint_future_full_capsules_respect_stricter_net_clearance(monkeypatch):
    import cec_fr as fr
    b,n,other,proposals=two_rail_fixture(monkeypatch,other_y=46.85)
    monkeypatch.setattr(fr,'_project_netclass_resolver',lambda _:lambda net:{
        'clearance':.4 if net==other.GetNetname() else .2})
    result=collector.preflight_bank(b,proposals,board_hint='atx-24pin-rev3')
    assert all(row['ok'] for row in result['members'])
    assert not result['ok'] and result['proposed_collector_conflicts'][0]['clearance_nm']==400000


@pytest.mark.parametrize('face',['F.Cu','B.Cu'])
def test_plated_foreign_source_bank_still_blocks_other_layer(monkeypatch,face):
    b,n,other,proposals=two_rail_fixture(monkeypatch,other_face=face)
    proposals[0]['paths'][0]['points_mm']=[[20,40],[20,60],[40,60],[40,40]]
    result=collector.preflight_bank(b,proposals,board_hint='atx-24pin-rev3')
    assert not result['members'][0]['ok'] and not result['ok']
    hits=[hit for check in result['members'][0]['checks'] for hit in check['native_hits']]
    assert any(hit.get('owner_ref')=='ARBITRARY_SECOND_SOURCE' for hit in hits)


@pytest.mark.parametrize('bad',['empty','duplicate','unknown','too_many','unbounded'])
def test_joint_bank_invalid_inventory_and_deadline_refuse_atomically(monkeypatch,bad):
    b,n,other,proposals=two_rail_fixture(monkeypatch)
    kwargs={}
    if bad=='empty':proposals=[]
    if bad=='duplicate':proposals=proposals[:1]*2
    if bad=='unknown':proposals[0]['current_share']=.5
    if bad=='too_many':proposals*=9
    if bad=='unbounded':kwargs['timeout_s']=11
    with pytest.raises(ValueError):collector.preflight_bank(b,proposals,board_hint='atx-24pin-rev3',**kwargs)
    assert not list(b.GetTracks())


def test_constructor_adds_only_explicit_whole_bank_at_native_rated_widths(monkeypatch):
    b,n,other,proposals=two_rail_fixture(monkeypatch,other_face='B.Cu')
    result=collector.construct_prefix(b,proposals,board_hint='atx-24pin-rev3')
    assert result['applied'] and len(result['added_track_uuids'])==2
    tracks=list(b.GetTracks())
    assert {t.m_Uuid.AsString() for t in tracks}==set(result['added_track_uuids'])
    assert all(t.IsLocked() and t.GetWidth()==6535523 for t in tracks)
    assert {t.GetLayer() for t in tracks}=={pcbnew.F_Cu,pcbnew.B_Cu}
    assert not result['release_authority'] and not result['routing_admitted']


def test_constructor_never_silently_emits_successful_subset_of_failed_bank(monkeypatch):
    b,n,other,proposals=two_rail_fixture(monkeypatch)
    proposals[0]['paths'][0]['points_mm']=[[20,40],[40,40],[40,60]]
    result=collector.construct_prefix(b,proposals,board_hint='atx-24pin-rev3')
    assert not result['applied'] and not result['added_track_uuids']
    assert not list(b.GetTracks()) and not result['preflight']['ok']


def test_constructor_rolls_back_native_add_failure_not_a_partial_prefix(monkeypatch):
    b,n,other,proposals=two_rail_fixture(monkeypatch)
    native_add=b.Add;calls=[]
    def add(item):
        calls.append(item)
        if len(calls)==2:raise RuntimeError('native insertion failure')
        return native_add(item)
    monkeypatch.setattr(b,'Add',add)
    with pytest.raises(RuntimeError,match='native insertion failure'):
        collector.construct_prefix(b,proposals,board_hint='atx-24pin-rev3')
    assert len(calls)==2 and not list(b.GetTracks())

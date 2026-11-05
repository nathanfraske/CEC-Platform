"""Demand-owned planar copper, not net-name or indivisible-track reachability."""
import time
import pcbnew
import pytest
import cec_column_destination_ports as ports
import cec_field_coupling as field
import cec_force_current as force
import cec_kelvin_copper_cut as cut


class Guard:
    def allows_endpoint(self,endpoint):return True


def fixture(quarter=0,back=False,*,fault=None,diagonal=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'renamed_source_rail');board.Add(net)
    owner=pcbnew.FOOTPRINT(board);owner.SetReference('unrelated_owner');board.Add(owner)
    pad=pcbnew.PAD(owner);pad.SetNumber('1');pad.SetNet(net)
    pad.SetPosition(pcbnew.VECTOR2I_MM(10,10));pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());owner.Add(pad)
    def track(a,b,width=.5,layer=pcbnew.F_Cu):
        item=pcbnew.PCB_TRACK(board);item.SetNet(net);item.SetWidth(round(width*1e6));item.SetLayer(layer)
        item.SetStart(pcbnew.VECTOR2I_MM(*a));item.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(item);return item
    far=track((10,10.549)if fault=='sliver'else(10,10),(16,16)if diagonal else(16,10.549 if fault=='sliver'else 10))
    if fault=='thin_neck':
        far.SetStart(pcbnew.VECTOR2I_MM(12,10));track((10,10),(12,10),.01)
    disconnected=track((20,10),(23,10))
    if fault=='foreign_hole':
        hole_owner=pcbnew.FOOTPRINT(board);hole_owner.SetReference('renamed_mount');board.Add(hole_owner)
        hole=pcbnew.PAD(hole_owner);hole.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        hole.SetPosition(pcbnew.VECTOR2I_MM(13,10));hole.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
        hole.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8));hole.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        hole.SetLayerSet(pcbnew.LSET.AllCuMask());hole_owner.Add(hole)
    elif fault=='unknown_vertical':
        owner.Flip(pcbnew.VECTOR2I_MM(10,10),False)
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(10,10));via.SetNet(net)
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        if back:item.Flip(pcbnew.VECTOR2I_MM(15,15),False)
        if quarter:item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    material=[*(p for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==net.GetNetname()),
        *[t for t in board.GetTracks()if t.GetNetname()==net.GetNetname()]]
    contract={'required_by_layer_nm':{int(l):100000 for l in board.GetEnabledLayers().CuStack()}}
    return board,pad,far,disconnected,material,contract


def index(board,material,contract):
    return ports.DestinationPorts(board,material,contract,guard=Guard(),deadline=time.monotonic()+5.)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_retained_full_width_destination_endpoints_are_real_alternate_contacts(quarter,back):
    b,p,t,other,material,contract=fixture(quarter,back)
    before=field._field_snapshot_inventory(b);scope=index(b,material,contract)
    sites=scope.sites(p,toward_nm=tuple(t.GetEnd()),width_nm=500000)
    assert sites[0][0]==tuple(p.GetPosition())
    assert any(at==tuple(t.GetEnd())and uid==force._uid(t)for at,face,uid in sites)
    assert all(uid!=force._uid(other)for at,face,uid in sites)
    assert all(face==int(next(iter(p.GetLayerSet().CuStack())))for at,face,uid in sites)
    proof=scope.report();assert proof['vertical_edges_credited']==0
    assert not proof['current_qualified']and not proof['release_authority']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('fault',['sliver','thin_neck','foreign_hole','unknown_vertical'])
def test_same_net_or_item_connectivity_cannot_supply_a_missing_whole_current_core(fault):
    b,p,t,other,material,contract=fixture(fault=fault);scope=index(b,material,contract)
    sites=scope.sites(p,toward_nm=tuple(t.GetEnd()),width_nm=500000)
    assert not any(at==tuple(t.GetEnd())for at,face,uid in sites),sites
    if fault=='foreign_hole':assert all(at[0]<13000000 for at,face,uid in sites)
    if fault=='unknown_vertical':assert all(face==pcbnew.B_Cu for at,face,uid in sites)


@pytest.mark.parametrize('quarter',range(4))
def test_exact_diagonal_interiors_stay_on_the_retained_integer_centreline(quarter):
    import cec_native_track_ports as tracks
    b,p,t,other,material,contract=fixture(quarter,diagonal=True)
    sites=index(b,material,contract).sites(p,toward_nm=tuple(t.GetEnd()),width_nm=500000)
    interiors=[at for at,face,uid in sites if uid==force._uid(t)and at not in(tuple(t.GetStart()),tuple(t.GetEnd()))]
    assert interiors and all(tracks.on_centerline(t,at)for at in interiors)


def test_port_pairs_are_fair_bounded_and_do_not_repeat_the_blocked_pad_for_every_root():
    left=list(range(8));right=list('abcdefgh');pairs=ports.interleave_pairs(left,right)
    assert pairs[:3]==[(0,'a'),(0,'b'),(1,'a')]
    assert len(pairs)==64 and len(set(pairs))==64
    assert ports.interleave_pairs([],right)==[]
    with pytest.raises(ValueError):ports.interleave_pairs(left+[8],right)


def test_actual_source_and_distinct_directions_survive_a_dense_nearest_alias_cloud():
    candidates=[((1000000+i*600000,0),0,'renamed_near_'+str(i))for i in range(40)]
    source=((70000000,-40000000),0,'actual_regulator_output')
    other_direction=((30000000,30000000),0,'independent_approach')
    candidates.extend((source,other_direction));before=list(candidates)
    selected=ports.source_portfolio(candidates,(0,0),width_nm=500000,source_pad_port=source)
    assert selected[0]==candidates[0]and selected[1]==source
    assert other_direction in selected and len(selected)==8 and candidates==before
    with pytest.raises(ValueError):ports.source_portfolio(candidates,(0,0),width_nm=500000,
        source_pad_port=((1,1),0,'not_in_source'))


def test_two_legal_launches_form_a_coalesced_source_web_not_a_folded_remote_link():
    import cec_column_surface_launch as launch
    b,p,t,other,material,contract=fixture()
    at=tuple(p.GetPosition());left=(8000000,10000000);right=(12000000,10000000)
    web=ports.paired_launch_web([(at,left,500000)],[(at,right,500000)],pcbnew.F_Cu)
    proof=launch.SurfaceLaunch(b,'renamed_source_rail',deadline=time.monotonic()+2.).assess(web,pcbnew.F_Cu)
    assert proof['ok']and proof['complete'],proof
    assert len(web)==1 and set((web[0][0],web[0][1]))=={left,right}
    assert not proof['current_authority']and not proof['release_authority']


@pytest.mark.parametrize('fault',['expired','source_mutation','boolean_width','boolean_floor'])
def test_unknown_or_changed_plan_context_cannot_reuse_a_planar_port_hint(fault):
    b,p,t,other,material,contract=fixture()
    if fault=='boolean_floor':
        contract['required_by_layer_nm'][pcbnew.F_Cu]=True
        with pytest.raises(ValueError):index(b,material,contract)
        return
    scope=index(b,material,contract);width=500000
    if fault=='expired':scope.work.deadline=time.monotonic()-1
    elif fault=='source_mutation':t.Move(pcbnew.VECTOR2I(1,0))
    else:width=True
    with pytest.raises((ValueError,cut.Unknown)):scope.sites(p,toward_nm=tuple(t.GetEnd()),width_nm=width)


@pytest.mark.parametrize('fault',['shape','orientation','offset','roundrect','chamfer'])
def test_full_native_pad_contour_epoch_prevents_stale_planar_core_reuse(fault):
    b,p,t,other,material,contract=fixture();scope=index(b,material,contract)
    scope.sites(p,toward_nm=tuple(t.GetEnd()),width_nm=500000)
    if fault=='shape':p.SetShape(pcbnew.PAD_SHAPE_OVAL)
    elif fault=='orientation':p.SetOrientationDegrees(23.)
    elif fault=='offset':p.SetOffset(pcbnew.VECTOR2I(1,0))
    elif fault=='roundrect':p.SetRoundRectRadiusRatio(.17)
    else:p.SetChamferRectRatio(.13)
    with pytest.raises(ValueError,match='source_geometry_changed'):
        scope.sites(p,toward_nm=tuple(t.GetEnd()),width_nm=500000)


def test_actual_column_pipeline_can_use_a_component_port_outside_a_blocked_centroid(tmp_path,monkeypatch):
    import cec_ordinary_power_columns as columns
    from test_ordinary_power_columns import fixture as column_fixture,track
    b,unused,source,unused_items,contract=column_fixture(tmp_path,monkeypatch)
    # Legal .5 mm retained copper leaves the one-millimetre channel; ordinary
    # .9 mm barrels plus .2 mm clearance cannot fit inside it. Exiting the
    # channel from the pad would exceed the fixed six-millimetre launch cap.
    supply=b.GetNetInfo().GetNetItem('arbitrary_supply')
    retained=track(b,supply,(15,5),(26,5))
    blocker=pcbnew.NETINFO_ITEM(b,'unrelated_corridor_walls');b.Add(blocker)
    for y in (4.3,5.7):track(b,blocker,(17,y),(29.7,y),width=.4)
    field._save_field_snapshot(b,source);before=field._field_snapshot_inventory(b)
    demand=b.FindFootprintByReference('renamed_cap').FindPadByNumber('1')
    proposal=columns.plan(b,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.)
    assert proposal['complete'],proposal
    assert proposal['target_port_nm']!=list(demand.GetPosition())
    assert proposal['target_port_uuid']==force._uid(retained)
    assert any(row['origin_nm']==list(demand.GetPosition())and row['redundant_pairs']==0
        for row in proposal['endpoint_portfolios'])
    child=pcbnew.LoadBoard(str(source));columns.construct_private(child,proposal,source=source,board_hint='synthetic')
    proof=columns.receive_native(b,child,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.)
    assert proof['ok']and proof['complete'],(proposal,proof)
    assert force._uid(demand)in proof['joined_source_supply_terminals']
    assert proof['every_single_new_vertical_barrel_loss_preserves_whole_current_path']
    assert not proof['current_qualified']and not proof['release_authority']
    assert field._field_snapshot_inventory(b)==before


def test_positive_output_land_is_not_mistaken_for_a_trace_width_floor(tmp_path,monkeypatch):
    import cec_ordinary_power_columns as columns
    from test_ordinary_power_columns import fixture as column_fixture
    b,unused,source,unused_items,contract=column_fixture(tmp_path,monkeypatch)
    output=b.FindFootprintByReference('renamed_regulator').FindPadByNumber('5')
    output.SetSize(pcbnew.VECTOR2I_MM(.3,.6))
    field._save_field_snapshot(b,source);before=field._field_snapshot_inventory(b)
    proposal=columns.plan(b,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.)
    assert proposal['complete'],proposal
    assert all(r['actual_source_output_port_offered']for r in proposal['source_portfolios'])
    assert all(o[3]>=500000 for o in proposal['ops']if o[0]=='trk')
    assert output.GetSize().x==300000 and field._field_snapshot_inventory(b)==before

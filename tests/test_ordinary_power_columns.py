"""Whole-source-current ordinary columns, not fine-POFV rating inheritance."""
import math
import copy
import pcbnew
import pytest
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_force_current as force
import cec_field_coupling as field
from cec_route_dimensions import current_trace_widths
from cec_native_items import discard_items


def track(b,net,start,end,layer=pcbnew.F_Cu,width=.5):
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*start));t.SetEnd(pcbnew.VECTOR2I_MM(*end))
    t.SetLayer(layer);t.SetWidth(round(width*1e6));t.SetNet(net);b.Add(t);return t


def fixture(tmp_path,monkeypatch,quarter=0,back=False):
    import cec_ordinary_power_columns as op
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    ds=b.GetDesignSettings();ds.m_TrackMinWidth=200000;ds.m_MinClearance=200000
    ds.m_ViasMinSize=900000;ds.m_MinThroughDrill=500000;ds.m_ViasMinAnnularWidth=100000
    net=pcbnew.NETINFO_ITEM(b,'arbitrary_supply');gnd=pcbnew.NETINFO_ITEM(b,'GND');b.Add(net);b.Add(gnd)
    def fp(ref,value,mpn,lib,foot,pads):
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue(value);f.SetField('MPN',mpn)
        f.SetFPID(pcbnew.LIB_ID(lib,foot));b.Add(f)
        for number,x,y,n in pads:
            p=pcbnew.PAD(f);p.SetNumber(number);p.SetPosition(pcbnew.VECTOR2I_MM(x,y));p.SetNet(n)
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
            p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));f.Add(p)
        return f
    src=fp('renamed_regulator','LP5907MFX-3.3','LP5907MFX-3.3','Package_TO_SOT_SMD','SOT-23-5', [('5',5,5,net),('2',5,7,gnd)])
    cap=fp('renamed_cap','100nF','CL05B104KO5NNNC','Capacitor_SMD','C_0402_1005Metric',[('1',25,5,net),('2',25,7,gnd)])
    owner=fp('renamed_load','INA240A3','INA240A3DR','Package_SO','SOIC-8_3.9x4.9mm_P1.27mm',[('5',26,5,net),('2',26,7,gnd)])
    track(b,net,(5,5),(8,5))
    for a,z in [((0,0),(30,0)),((30,0),(30,15)),((30,15),(0,15)),((0,15),(0,0))]:
        e=pcbnew.PCB_SHAPE();e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(e)
    source=tmp_path/'source.kicad_pcb';b.SetFileName(str(source))
    field._save_field_snapshot(b,source)
    child=pcbnew.LoadBoard(str(source));live=child.GetNetInfo().GetNetItem('arbitrary_supply');added=[]
    for x in (8,10,22,24):
        via=pcbnew.PCB_VIA(child);via.SetPosition(pcbnew.VECTOR2I_MM(x,5));via.SetNet(live)
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetWidth(900000);via.SetDrill(500000);child.Add(via);added.append(via)
    added.extend([track(child,live,(8,5),(10,5)),track(child,live,(22,5),(26,5)),track(child,live,(8,5),(24,5),pcbnew.B_Cu)])
    for board in (b,child):
        board.GetNetInfo().GetNetItem('arbitrary_supply').GetNetClassSlow().SetTrackWidth(500000)
    for board in (b,child):
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings()]:
            if back:item.Flip(pcbnew.VECTOR2I_MM(15,7.5),False)
            if quarter:item.Rotate(pcbnew.VECTOR2I_MM(15,7.5),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    field._save_field_snapshot(b,source)
    authority=dict(amps=.25,geometry_margin=1.,margin_included=True,source='component_power_budget')
    profile='jlcpcb_6l_pofv_high_current'
    widths=current_trace_widths(authority,tuple(fab.enabled_copper_layers(b)),profile,rise_c=30.)
    contract=dict(current_authority=authority,profile=profile,required_by_layer_nm={b.GetLayerID(n):math.ceil(w*1e6)for n,w in widths.items()})
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *a,**kw:copy.deepcopy(contract))
    return b,child,source,added,contract


def receive(b,c,source):
    import cec_ordinary_power_columns as op
    return op.receive_native(b,c,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_ordinary_redundant_array_is_actual_native_source_connected(tmp_path,monkeypatch,quarter,back):
    b,c,source,added,contract=fixture(tmp_path,monkeypatch,quarter,back)
    before=field._field_snapshot_inventory(b);candidate=field._field_snapshot_inventory(c)
    q=receive(b,c,source)
    assert q['ok'] and q['complete'],q
    assert q['source_policy_column_capacity_received'] is True
    assert q['current_qualified'] is False
    assert not q.get('release_authority',False)
    assert field._field_snapshot_inventory(b)==before and field._field_snapshot_inventory(c)==candidate


def test_larger_same_bore_annulus_is_a_native_copper_superset_not_new_rating(tmp_path,monkeypatch):
    b,c,source,added,contract=fixture(tmp_path,monkeypatch)
    for via in added[:4]:via.SetWidth(1000000)
    q=receive(b,c,source)
    assert q['ok'] and q['complete'] and q['source_policy_column_capacity_received'],q
    assert not q['current_qualified'] and not q.get('thermal_qualified',False)


@pytest.mark.parametrize('netname,expected',[('GND',True),('unrelated_power',False)])
def test_only_ground_refill_is_delegated_to_independent_saved_receiving(tmp_path,monkeypatch,netname,expected):
    b,c,source,added,contract=fixture(tmp_path,monkeypatch)
    if netname!='GND':
        for board in (b,c):board.Add(pcbnew.NETINFO_ITEM(board,netname))
    original=pcbnew.ZONE(b);original.SetLayer(pcbnew.In1_Cu)
    original.SetNet(b.GetNetInfo().GetNetItem(netname))
    original.Outline().NewOutline()
    for x,y in ((1,1),(3,1),(3,3),(1,3)):original.Outline().Append(round(x*1e6),round(y*1e6))
    def filled(board,zone,edge):
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in ((1,1),(edge,1),(edge,edge),(1,edge)):poly.Append(round(x*1e6),round(y*1e6))
        zone.SetFilledPolysList(pcbnew.In1_Cu,poly);zone.SetIsFilled(True);board.Add(zone)
    filled(b,original,3)
    clone=pcbnew.ZONE(original);clone.SetNet(c.GetNetInfo().GetNetItem(netname));filled(c,clone,2)
    field._save_field_snapshot(b,source)
    q=receive(b,c,source)
    assert q['ok'] is expected,q
    if expected:
        assert q['ground_fill_changes_not_received_by_column_cut_scope'] is True
        assert q['whole_saved_native_DRC_source_intake_current_field_Kelvin_and_release_still_required']
        assert not q['current_qualified'] and not q['release_authority']


@pytest.mark.parametrize('timeout',[0,-1,True,float('nan'),float('inf'),11])
def test_no_unbounded_or_boolean_receiving_budget(tmp_path,monkeypatch,timeout):
    import cec_ordinary_power_columns as op
    b,c,source,*_=fixture(tmp_path,monkeypatch)
    try:q=op.receive_native(b,c,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=timeout)
    except ValueError:return
    assert not q['ok'] and not q.get('source_policy_column_capacity_received',False)


@pytest.mark.parametrize('fault',['fine_pofv','larger_bore','single_source_column','single_target_column',
    'thin_body','decorative_column','changed_source_track','unknown_source','source_dnp','wrong_net',
    'contact_sliver','foreign_old_barrel','unknown_current','guessed_current','wrong_profile','fake_floor'])
def test_new_columns_need_exact_policy_source_cuts_and_actual_redundancy(tmp_path,monkeypatch,fault):
    b,c,source,added,contract=fixture(tmp_path,monkeypatch)
    if fault=='fine_pofv':
        for v in added[:4]:v.SetWidth(300000);v.SetDrill(200000)
    elif fault=='larger_bore':added[0].SetDrill(600000)
    elif fault=='single_source_column':discard_items(c,[added[0]])
    elif fault=='single_target_column':discard_items(c,[added[2]])
    elif fault=='thin_body':added[-1].SetWidth(1)
    elif fault=='decorative_column':added[0].SetPosition(pcbnew.VECTOR2I_MM(8,10))
    elif fault=='changed_source_track':next(t for t in c.GetTracks()if force._uid(t)not in {force._uid(i)for i in added}).SetWidth(450000)
    elif fault in ('unknown_source','source_dnp'):
        f=c.FindFootprintByReference('renamed_regulator')
        if fault=='unknown_source':f.SetValue('UNKNOWN');f.SetField('MPN','UNKNOWN')
        else:f.SetDNP(True)
    elif fault=='wrong_net':added[0].SetNet(c.GetNetInfo().GetNetItem('GND'))
    elif fault=='contact_sliver':added[0].SetPosition(pcbnew.VECTOR2I_MM(8,5.699))
    elif fault=='foreign_old_barrel':
        # An inherited, unrated barrel cannot substitute for a new spare.
        added[1].SetWidth(800000);added[1].SetDrill(400000)
        v=pcbnew.PCB_VIA(b);v.m_Uuid.Clone(added[1].m_Uuid)
        v.SetPosition(pcbnew.VECTOR2I_MM(10,5));v.SetWidth(800000);v.SetDrill(400000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.GetNetInfo().GetNetItem('arbitrary_supply'));b.Add(v)
        field._save_field_snapshot(b,source)
    elif fault=='unknown_current':monkeypatch.setattr(cells,'_supply_current_widths',lambda *a,**kw:None)
    elif fault=='guessed_current':contract['current_authority']['source']='caller_guess'
    elif fault=='wrong_profile':contract['profile']='jlcpcb_6l_pofv_signal'
    elif fault=='fake_floor':contract['required_by_layer_nm'][pcbnew.F_Cu]=1
    q=receive(b,c,source)
    assert not q['ok'],q
    assert not q.get('source_policy_column_capacity_received',False)


@pytest.mark.parametrize('fault',['layer_sliver','foreign_hole_pinch','target_zone','new_unknown_pad',
    'partial_via_span','factory_min_drill','factory_min_annular','changed_old_track_layer',
    'source_file_epoch','unused_inner_annuli_only'])
def test_actual_native_layer_contacts_holes_and_source_factory_bounds(tmp_path,monkeypatch,fault):
    b,c,source,added,contract=fixture(tmp_path,monkeypatch)
    if fault=='layer_sliver':
        # The only spanning body is inner copper, offset so its near edge
        # merely kisses all four annuli. Collision is not a current cut.
        added[-1].SetLayer(pcbnew.In2_Cu)
        added[-1].SetStart(pcbnew.VECTOR2I_MM(8,5.699));added[-1].SetEnd(pcbnew.VECTOR2I_MM(24,5.699))
    elif fault=='foreign_hole_pinch':
        # An unchanged physical bore crosses the only far-face collector.
        for board in (b,c):
            f=pcbnew.FOOTPRINT(board);f.SetReference('mechanical_bore');f.SetValue('NPTH');board.Add(f)
            p=pcbnew.PAD(f);p.SetNumber('');p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
            p.SetPosition(pcbnew.VECTOR2I_MM(16,5));p.SetSize(pcbnew.VECTOR2I_MM(1,1))
            p.SetDrillSize(pcbnew.VECTOR2I_MM(1,1));p.SetLayerSet(pcbnew.LSET.AllCuMask());f.Add(p)
            if board is b:uid=force._uid(f);puid=force._uid(p)
            else:f.m_Uuid.Clone(pcbnew.KIID(uid));p.m_Uuid.Clone(pcbnew.KIID(puid))
        field._save_field_snapshot(b,source)
    elif fault=='target_zone':
        z=pcbnew.ZONE(c);z.SetNet(c.GetNetInfo().GetNetItem('arbitrary_supply'));z.SetLayer(pcbnew.F_Cu)
        z.Outline().NewOutline()
        for x,y in [(4,4),(27,4),(27,6),(4,6)]:z.Outline().Append(round(x*1e6),round(y*1e6))
        c.Add(z)
    elif fault=='new_unknown_pad':
        f=pcbnew.FOOTPRINT(c);f.SetReference('extra_owner');c.Add(f)
    elif fault=='partial_via_span':added[0].SetViaType(pcbnew.VIATYPE_BLIND);added[0].SetLayerPair(pcbnew.F_Cu,pcbnew.In2_Cu)
    elif fault=='factory_min_drill':c.GetDesignSettings().m_MinThroughDrill=600000
    elif fault=='factory_min_annular':c.GetDesignSettings().m_ViasMinAnnularWidth=300000
    elif fault=='changed_old_track_layer':
        old={force._uid(t)for t in b.GetTracks()};next(t for t in c.GetTracks()if force._uid(t)in old).SetLayer(pcbnew.In2_Cu)
    elif fault=='source_file_epoch':
        b.FindFootprintByReference('renamed_regulator').SetField('MPN','CHANGED_AFTER_SAVE')
    else:
        # Unused inner lands exist on a through barrel, but they cannot
        # supply a horizontal route in the absence of actual copper.
        discard_items(c,[added[-1]])
    q=receive(b,c,source)
    assert not q['ok'] and not q.get('source_policy_column_capacity_received',False),q


def test_saved_composition_keeps_current_receiver_signature_and_independent_native_proof(tmp_path,monkeypatch):
    import cec_ordinary_power_columns as op
    import cec_additive_route_receiving as additive
    import cec_current_debt as current
    import cec_certificate_repair as repair
    b,c,source,added,contract=fixture(tmp_path,monkeypatch)
    candidate=tmp_path/'candidate.kicad_pcb';field._save_field_snapshot(c,candidate)
    calls=[]
    # These mocks are only the saved composition boundary. The actual
    # column/core/contact/vertical counterfactual remains the real receiver.
    def debt(a,z,*,board_hint):
        calls.append(('current',str(a),str(z)));return dict(ok=True,complete=True)
    def replay(a,z,*,board_hint,timeout_s):
        calls.append(('additive',str(a),str(z)));return dict(ok=True,complete=True)
    monkeypatch.setattr(current,'receive',debt);monkeypatch.setattr(additive,'receive',replay)
    monkeypatch.setattr(repair,'_spawn_apply',lambda fn,args,*,timeout_s:fn(*args))
    q=op.receive(source,candidate,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.)
    assert q['ok'] and q['complete'],q
    assert [r[0]for r in calls]==['additive','current']
    assert not q['current_qualified'] and not q['thermal_qualified'] and not q['release_authority']


@pytest.mark.parametrize('fault',[None,'old_fine_barrels','old_single_source_barrel','new_single_barrel'])
def test_later_collector_branch_rederives_old_columns_and_all_single_axis_cuts(tmp_path,monkeypatch,fault):
    """A received extension can use saved copper, but never its old receipt."""
    b,first,source,added,contract=fixture(tmp_path,monkeypatch)
    for board in (b,first):
        f=pcbnew.FOOTPRINT(board);f.SetReference('another_arbitrary_load');f.SetValue('100nF')
        f.SetField('MPN','CL05B104KO5NNNC')
        f.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0402_1005Metric'));board.Add(f)
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetPosition(pcbnew.VECTOR2I_MM(15,12))
        p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetNet(board.GetNetInfo().GetNetItem('arbitrary_supply'));f.Add(p)
        g=pcbnew.PAD(f);g.SetNumber('2');g.SetPosition(pcbnew.VECTOR2I_MM(15,14))
        g.SetSize(pcbnew.VECTOR2I_MM(.6,.6));g.SetShape(pcbnew.PAD_SHAPE_RECT)
        g.SetAttribute(pcbnew.PAD_ATTRIB_SMD);g.SetLayerSet(pcbnew.PAD.SMDMask())
        g.SetNet(board.GetNetInfo().GetNetItem('GND'));f.Add(g)
        if board is b:fpuid=force._uid(f);paduid=force._uid(p);guid=force._uid(g)
        else:
            f.m_Uuid.Clone(pcbnew.KIID(fpuid));p.m_Uuid.Clone(pcbnew.KIID(paduid))
            g.m_Uuid.Clone(pcbnew.KIID(guid))
    field._save_field_snapshot(b,source)
    assert receive(b,first,source)['ok']
    if fault=='old_fine_barrels':
        for v in added[:2]:v.SetWidth(800000);v.SetDrill(400000)
    if fault=='old_single_source_barrel':discard_items(first,[added[0]])
    # The later source is saved native copper, with no trusted receipt,
    # UUID allowlist, source budget override or current qualification flag.
    prior=tmp_path/'prior.kicad_pcb';field._save_field_snapshot(first,prior)
    parent=pcbnew.LoadBoard(str(prior));second=pcbnew.LoadBoard(str(prior))
    net=second.GetNetInfo().GetNetItem('arbitrary_supply');new=[]
    for x in (10,12):
        v=pcbnew.PCB_VIA(second);v.SetPosition(pcbnew.VECTOR2I_MM(x,12));v.SetNet(net)
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetWidth(900000);v.SetDrill(500000);second.Add(v);new.append(v)
    track(second,net,(10,5),(10,12),pcbnew.B_Cu)
    track(second,net,(10,12),(12,12),pcbnew.B_Cu)
    track(second,net,(10,12),(15,12),pcbnew.F_Cu)
    if fault=='new_single_barrel':discard_items(second,[new[0]])
    q=receive(parent,second,prior)
    assert q['ok'] is (fault is None),q
    if fault is None:
        assert len(q['rederived_existing_column_uuids'])==4
        assert len(q['new_column_uuids'])==2
        assert q['every_single_credited_vertical_barrel_loss_preserves_whole_current_path']
        assert q['inherited_unknown_barrel_capacity_credited'] is False
        assert q['current_qualified'] is False and q['release_authority'] is False


def test_source_portfolio_funds_each_terminal_before_aliases():
    import cec_ordinary_power_columns as op
    assert op._interleave_ports([['first_a','second_a','third_a'],[],['first_b','second_b'],['first_c']])==[
        'first_a','first_b','first_c','second_a','second_b','third_a']
    assert op._interleave_ports([])==[]


@pytest.mark.parametrize('fault',[None,'fine_barrels','thin_middle'])
@pytest.mark.parametrize('quarter,back',[(0,False),(1,True)])
def test_proposal_ports_do_not_use_native_unknown_capacity_shortcuts(tmp_path,monkeypatch,fault,quarter,back):
    import time
    import cec_ordinary_power_columns as op,cec_native_current_capture as capture
    b,c,source,added,contract=fixture(tmp_path,monkeypatch,quarter,back)
    if fault=='fine_barrels':
        for v in added[:4]:v.SetWidth(800000);v.SetDrill(400000)
    elif fault=='thin_middle':added[-1].SetWidth(1)
    prior=tmp_path/'saved-collector.kicad_pcb';field._save_field_snapshot(c,prior)
    root,terms=op._root_and_terminals(c,'arbitrary_supply')
    far=c.FindFootprintByReference('renamed_cap').FindPadByNumber('1')
    graph=op.fr._read_only_route_connectivity(c)
    assert force._uid(far) in {force._uid(i) for i in graph.GetConnectedItems(root)}
    guard=capture.Guard(c,prior,net='arbitrary_supply',board_hint='synthetic',timeout_s=10.)
    hints=op._capacity_port_hints(c,op._inventory(c,'arbitrary_supply'),root,contract,
        gap=200000,guard=guard,deadline=time.monotonic()+10.)
    assert (force._uid(far) in hints) is (fault is None)


@pytest.mark.parametrize('quarter,back',[(0,False),(1,False),(0,True)])
def test_actual_bounded_producer_constructs_receiver_provable_redundant_columns(tmp_path,monkeypatch,quarter,back):
    import cec_ordinary_power_columns as op
    b,unused,source,unused_items,contract=fixture(tmp_path,monkeypatch,quarter,back)
    original=field._field_snapshot_inventory(b);raw=source.read_bytes()
    q=op.plan(b,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.,max_pairs=8)
    assert q['complete'] and q['ops'],q
    assert all(oprow[3]>=500000 for oprow in q['ops'] if oprow[0]=='trk'),q
    assert q['complete_packet_preflight']['board_mutated'] is False
    assert q['complete_packet_preflight']['current_qualified'] is False
    assert q['complete_packet_preflight']['release_authority'] is False
    assert q['proposed_collinear_union']['source_items_inspected_or_mutated'] is False
    assert field._field_snapshot_inventory(b)==original and source.read_bytes()==raw
    child=pcbnew.LoadBoard(str(source))
    made=op.construct_private(child,q,source=source,board_hint='synthetic')
    assert made
    import cec_route_quality as quality
    craft=quality.analyze_board(child)
    assert craft['geometry_ok'] and craft['craft_ok'],craft
    proof=op.receive_native(b,child,source=source,board_hint='synthetic',net='arbitrary_supply',timeout_s=10.)
    assert proof['ok'] and proof['complete'],(q,proof)
    assert proof['source_policy_column_capacity_received']
    assert not proof['current_qualified'] and not proof['thermal_qualified'] and not proof['release_authority']
    assert field._field_snapshot_inventory(b)==original and source.read_bytes()==raw

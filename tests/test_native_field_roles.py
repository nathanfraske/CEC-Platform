"""DC power backbone roles cannot waive actual sensing or design intent."""
import time
import pytest
import pcbnew
import cec_native_field_roles as native
import cec_current_topology as topology
import cec_field_coupling as field
import cec_field_search as search
import cec_force_current as force


def fixture(monkeypatch, *, name='/arbitrary/SENSE_BUS', angle=0, mirror=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    rail=pcbnew.NETINFO_ITEM(board,name);board.Add(rail)
    control=pcbnew.NETINFO_ITEM(board,'/unrelated/THRESH_PWM');board.Add(control)
    for ref,xy in [('ALPHA',(5,10)),('OMEGA',(25,10))]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue('drilled_power_terminal');board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(rail);p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetLayerSet(pcbnew.PAD.PTHMask())
        p.SetSize(pcbnew.VECTOR2I_MM(2,2));p.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8))
        p.SetPosition(pcbnew.VECTOR2I_MM(*xy));fp.Add(p)
    def track(start,end,width,net=rail):
        t=pcbnew.PCB_TRACK(board);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetWidth(round(width*1e6))
        t.SetStart(pcbnew.VECTOR2I_MM(*start));t.SetEnd(pcbnew.VECTOR2I_MM(*end));board.Add(t);return t
    trunk=track((5,10),(25,10),2)
    stem=track((15,10),(15,13),.2);leaf=track((15,13),(25,13),.2)
    spur=track((18,10),(18,6),.6)
    island=track((30,10),(40,10),2)
    domain={name:dict(net=name,complete=True,amps=5.,source_refs=['ALPHA'],sink_refs=['OMEGA'])}
    monkeypatch.setattr(topology,'board_current_domains',lambda *_a,**_k:domain)
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirror:item.Flip(pcbnew.VECTOR2I_MM(20,20),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    return board,name,trunk,leaf,spur,island,domain,track,control


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('name',['/arbitrary/SENSE_BUS','/another/KELVIN_POWER'])
def test_only_actual_load_backbone_changes_name_based_role(monkeypatch,angle,mirror,name):
    board,name,trunk,leaf,spur,island,domain,_,_=fixture(monkeypatch,name=name,angle=angle,mirror=mirror)
    before=field._field_snapshot_inventory(board)
    roles=native.NativeFieldRoles(board,board_hint='opaque',netclass_resolver=lambda _n:'Power')
    assert set(roles.typed)=={force._uid(trunk)},roles.report()
    baseline=field.classify_net(name,netclass='Power')
    assert baseline['victim']
    assert not roles.role(trunk,baseline)['victim']
    for item in (leaf,spur,island):assert roles.role(item,baseline)['victim']
    assert field._field_snapshot_inventory(board)==before
    assert not roles.report()['current_kelvin_clearance_and_shielding_authority']


@pytest.mark.parametrize('fault',['missing_source','missing_sink','same_terminal','incomplete',
    'zero_current','nan_current','bool_current','custom_pad','arc','expired_deadline','disconnected'])
def test_unknown_native_or_current_evidence_keeps_original_field_role(monkeypatch,fault):
    board,name,trunk,*rest=fixture(monkeypatch);domain=rest[3]
    if fault=='missing_source':domain[name]['source_refs']=['NOT_PRESENT']
    elif fault=='missing_sink':domain[name]['sink_refs']=['NOT_PRESENT']
    elif fault=='same_terminal':domain[name]['sink_refs']=['ALPHA']
    elif fault=='incomplete':domain[name]['complete']=False
    elif fault=='zero_current':domain[name]['amps']=0
    elif fault=='nan_current':domain[name]['amps']=float('nan')
    elif fault=='bool_current':domain[name]['amps']=True
    elif fault=='custom_pad':board.FindFootprintByReference('ALPHA').FindPadByNumber('1').SetShape(pcbnew.PAD_SHAPE_CUSTOM)
    elif fault=='arc':
        arc=pcbnew.PCB_ARC(board);arc.SetNet(board.FindNet(name));board.Add(arc)
    elif fault=='disconnected':trunk.SetEnd(pcbnew.VECTOR2I_MM(20,10))
    roles=native.NativeFieldRoles(board,board_hint='opaque',
        deadline=0 if fault=='expired_deadline' else None)
    assert not roles.typed,roles.report()
    assert roles.role(trunk,field.classify_net(name))['victim']


@pytest.mark.parametrize('netclass',['Analog','Sensitive','Reference','ADC','Kelvin','HighSpeed','Clock'])
def test_explicit_design_intent_outranks_native_load_backbone(monkeypatch,netclass):
    board,name,trunk,*_=fixture(monkeypatch)
    roles=native.NativeFieldRoles(board,board_hint='opaque',netclass_resolver=lambda _n:netclass)
    assert not roles.typed
    baseline=field.classify_net(name,netclass=netclass)
    assert roles.role(trunk,baseline)==baseline


def test_full_audit_and_search_share_per_conductor_roles(monkeypatch):
    board,name,trunk,leaf,spur,island,_,track,control=fixture(monkeypatch)
    track((5,13.5),(25,13.5),.2,control)
    report=field.field_coupling_summary('opaque',board=board)
    assert report['native_conductor_field_roles']['classified_force_track_count']==1
    assert report['blocking_count']>0
    assert any(force._uid(leaf) in row['track_uuids'] for row in report['interactions'] if row['blocking'])
    assert not any(force._uid(trunk) in row['track_uuids'] for row in report['interactions'])
    guard=search.PlanarSearchGuard(board,control.GetNetname(),board_hint='opaque')
    assert force._uid(trunk) not in {row['uuid'] for row in guard.rows}
    assert force._uid(leaf) in {row['uuid'] for row in guard.rows}


def test_pendant_cycle_does_not_become_load_backbone():
    adjacency={v:set() for v in 'ABCDEFG'}
    for a,b in [('A','B'),('B','C'),('B','D'),('D','E'),('E','F'),('F','D'),('F','G')]:
        adjacency[a].add(b);adjacency[b].add(a)
    core,witness=native._backbone(adjacency,{'A'},{'C'},lambda:None)
    assert core=={'A','B','C'} and witness


def test_true_alternative_load_paths_remain_backbone():
    adjacency={v:set() for v in 'ABCDEF'}
    for a,b in [('A','B'),('B','C'),('C','D'),('B','E'),('E','C'),('E','F')]:
        adjacency[a].add(b);adjacency[b].add(a)
    core,_=native._backbone(adjacency,{'A'},{'D'},lambda:None)
    assert core==set('ABCDE')


@pytest.mark.parametrize('angle,mirror',[(0,False),(90,False),(180,True),(270,True)])
def test_explicit_identity_survives_private_filename_and_foreign_environment(monkeypatch,angle,mirror):
    board,name,trunk,leaf,spur,island,domain,track,control=fixture(monkeypatch,angle=angle,mirror=mirror)
    # The first fixture's entire native assembly is transformed; put the
    # aggressor through the same transform rather than a refdes exception.
    t=track((5,8),(25,8),.2,control)
    t.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    if mirror:t.Flip(pcbnew.VECTOR2I_MM(20,20),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    import os
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT','unrelated-design')
    monkeypatch.setattr(topology,'board_current_domains',lambda *_a,**_k:
        domain if os.environ.get('CEC_THERMAL_BOARD_HINT')=='bound-source' else {})
    before=field._field_snapshot_inventory(board)
    unknown=field.field_coupling_summary('private-candidate.kicad_pcb',board=board)
    fixed=field.field_coupling_summary('private-candidate.kicad_pcb',board=board,board_hint='bound-source')
    assert unknown['native_conductor_field_roles']['classified_force_track_count']==0
    assert unknown['blocking_count']>0
    assert fixed['native_conductor_field_roles']['classified_force_track_count']==1
    assert fixed['blocking_count']==0
    assert force._uid(leaf) not in native.NativeFieldRoles(board,board_hint='unresolved').typed
    assert field._field_snapshot_inventory(board)==before
    assert os.environ['CEC_THERMAL_BOARD_HINT']=='unrelated-design'


@pytest.mark.parametrize('hint',['', '   ',False,42,{}])
def test_invalid_explicit_identity_cannot_authorize_a_field_summary(monkeypatch,hint):
    board,*_=fixture(monkeypatch)
    with pytest.raises(ValueError,match='explicit_field_design_identity'):
        field.field_coupling_summary('private.kicad_pcb',board=board,board_hint=hint)


@pytest.mark.parametrize('with_via',[False,True])
def test_planar_and_nested_native_refill_proposals_keep_explicit_identity(monkeypatch,with_via,tmp_path):
    board,name,trunk,leaf,spur,island,domain,track,control=fixture(monkeypatch)
    from cec_native_items import discard_items
    discard_items(board,[spur])  # Keep the test proposal physically clear.
    control_name=control.GetNetname()
    track((0,0),(1,0),.2,control)
    # Establish a saved native baseline before measuring the proposal. A
    # builder's not-yet-serialized footprint offsets are not saved evidence.
    path=tmp_path/'opaque-source.kicad_pcb'
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
    board=pcbnew.LoadBoard(str(path))
    import os
    monkeypatch.setenv('CEC_THERMAL_BOARD_HINT','other-source')
    monkeypatch.setattr(topology,'board_current_domains',lambda *_a,**_k:
        domain if os.environ.get('CEC_THERMAL_BOARD_HINT')=='source-for-this-proposal' else {})
    before=field._field_snapshot_inventory(board)
    rows=[dict(net=control_name,layer=int(pcbnew.F_Cu),
        start_nm=[5000000,8000000],end_nm=[25000000,8000000],width_nm=200000)]
    vias=([dict(net=control_name,at_nm=[5000000,8000000],
        diameter_nm=600000,drill_nm=300000,top_layer=int(pcbnew.F_Cu),
        bottom_layer=int(pcbnew.B_Cu))] if with_via else [])
    unresolved=field.assess_proposed_route(board,rows,proposed_vias=vias,deadline=time.monotonic()+10.)
    received=field.assess_proposed_route(board,rows,proposed_vias=vias,
        deadline=time.monotonic()+10.,board_hint='source-for-this-proposal')
    assert unresolved['complete'] and unresolved['ok'] is False,unresolved
    assert received['complete'] and received['ok'] is True,received
    assert field._field_snapshot_inventory(board)==before
    assert os.environ['CEC_THERMAL_BOARD_HINT']=='other-source'


def zone_backbone(monkeypatch,mode='continuous',angle=0,mirror=False):
    board,name,trunk,leaf,spur,island,domain,track,control=fixture(monkeypatch)
    trunk.SetEnd(pcbnew.VECTOR2I_MM(12,10))
    right=track((18,10),(25,10),2)
    zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet(name));zone.SetLayer(pcbnew.F_Cu)
    def rectangle(x0,y0,x1,y1):
        poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
        for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):
            poly.Append(round(x*1e6),round(y*1e6))
        return poly
    zone.Outline().Append(rectangle(11,9,19,11));board.Add(zone)
    filled=rectangle(11,9,19,11)
    if mode=='disconnected':
        filled=rectangle(11,9,13,11);filled.Append(rectangle(17,9,19,11))
    elif mode in ('separate_faces','real_barrel'):
        right.SetLayer(pcbnew.B_Cu)
        mask=pcbnew.LSET();mask.AddLayer(pcbnew.F_Cu);mask.AddLayer(pcbnew.B_Cu);zone.SetLayerSet(mask)
        filled=rectangle(11,9,16,11)
        zone.SetFilledPolysList(pcbnew.B_Cu,rectangle(14,9,19,11))
        if mode=='real_barrel':
            via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet(name));via.SetPosition(pcbnew.VECTOR2I_MM(15,10))
            via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    elif mode=='hole':
        filled=rectangle(0,0,30,20);hole=rectangle(3,8,7,12)
        filled.BooleanSubtract(hole);trunk.SetStart(pcbnew.VECTOR2I_MM(8,10))
    elif mode=='empty':filled=pcbnew.SHAPE_POLY_SET()
    zone.SetFilledPolysList(pcbnew.F_Cu,filled);zone.SetIsFilled(mode!='unfilled')
    if mode=='foreign':zone.SetNet(control)
    if mode=='rulearea':zone.SetIsRuleArea(True)
    for a,z in (((-10,-10),(50,-10)),((50,-10),(50,50)),
            ((50,50),(-10,50)),((-10,50),(-10,-10))):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*z));board.Add(edge)
    for item in [*board.GetFootprints(),*board.GetTracks(),zone]:
        item.Rotate(pcbnew.VECTOR2I_MM(20,20),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        if mirror:item.Flip(pcbnew.VECTOR2I_MM(20,20),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if mirror:
        # Native Flip intentionally invalidates fill. Recompile the actual
        # flipped owner, never toggle IsFilled on stale, untransformed copper.
        import cec_zone_fill
        batch=pcbnew.ZONES();batch.append(zone)
        cec_zone_fill.compile_selected(board,batch,initialize_selected=True)
    # These explicit native fills isolate island/face/hole semantics. Native
    # emitter/refill/serialization is also tested end-to-end in the zone stage.
    return board,name,trunk,right,leaf,spur,island,zone


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_zone_continuity_keeps_power_role_but_not_thin_or_pendant_branches(monkeypatch,angle,mirror):
    board,name,left,right,leaf,spur,island,zone=zone_backbone(monkeypatch,angle=angle,mirror=mirror)
    before=field._field_snapshot_inventory(board)
    roles=native.NativeFieldRoles(board,board_hint='opaque')
    assert set(roles.typed)=={force._uid(left),force._uid(right)},roles.report()
    proof=roles.report()['proofs'][0]
    assert len(proof['actual_native_zone_islands'])==1
    assert proof['actual_native_zone_islands'][0]['zone_uuid']==force._uid(zone)
    assert before==field._field_snapshot_inventory(board)
    for item in (leaf,spur,island):assert roles.role(item,field.classify_net(name))['victim']


@pytest.mark.parametrize('mode',['disconnected','separate_faces','hole','empty','unfilled','foreign','rulearea'])
@pytest.mark.parametrize('angle',[0,90,180,270])
def test_owner_uuid_outline_or_projected_overlap_cannot_connect_real_voids(monkeypatch,mode,angle):
    board,name,left,right,*_=zone_backbone(monkeypatch,mode=mode,angle=angle)
    roles=native.NativeFieldRoles(board,board_hint='opaque')
    assert not roles.typed,roles.report()
    assert roles.role(left,field.classify_net(name))['victim']
    assert roles.role(right,field.classify_net(name))['victim']


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_only_real_native_plated_barrel_can_join_distinct_filled_zone_faces(monkeypatch,angle):
    board,name,left,right,*_=zone_backbone(monkeypatch,mode='real_barrel',angle=angle)
    roles=native.NativeFieldRoles(board,board_hint='opaque')
    assert set(roles.typed)=={force._uid(left),force._uid(right)},roles.report()
    proof=roles.report()['proofs'][0]
    assert len(proof['actual_native_zone_islands'])==2
    assert len({row['layer_id'] for row in proof['actual_native_zone_islands']})==2
    assert not roles.report()['current_kelvin_clearance_and_shielding_authority']

"""Missing future islands are not missing routes or current certificates."""
import copy
import time
import uuid

import pcbnew
import pytest
from shapely import affinity
from shapely.geometry import Polygon,box

import cec_pending_copper_frontier as pending
import cec_native_construction_frame as frame
import cec_zone_fill as fill


def _key(face,shape):
    return face,pending._shape_id(shape)


def fixture_geometry(turn=0,mirror=False,translation=(0,0)):
    def move(shape):
        shape=affinity.scale(shape,-1 if mirror else 1,1,origin=(15,15))
        shape=affinity.rotate(shape,turn,origin=(15,15))
        return affinity.translate(shape,*translation)
    # Actual final islands before the pending middle is stitched.
    left,right=move(box(0,0,14,30)),move(box(16,0,30,30))
    upper,middle,lower=[move(box(0,a,30,b)) for a,b in ((0,9),(11,19),(21,30))]
    parts={0:[left,right],8:[upper,middle,lower]}
    terminals={'arbitrary_first':[_key(0,left),_key(8,upper)],
               'arbitrary_last':[_key(0,right),_key(8,lower)]}
    return parts,terminals


def middle_guard(at_nm,turn=0,translation=(0,0)):
    import math
    x=at_nm[0]/1e6-translation[0]-15
    y=at_nm[1]/1e6-translation[1]-15
    native_y=-math.sin(math.radians(turn))*x+math.cos(math.radians(turn))*y+15
    return 11<native_y<19


@pytest.mark.parametrize('turn',[0,45,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('translation',[(0,0),(17.123456,-21.765432)])
def test_distinct_future_island_joins_chain_without_world_grid_bias(turn,mirror,translation):
    parts,terms=fixture_geometry(turn,mirror,translation)
    r=pending.component_proposals(parts,terminal_components=terms,land_radius_mm=.3,
        native_transition_clear=lambda p:middle_guard(p,turn,translation))
    assert r['proposed_face_path_found'] and len(r['proposed_transitions'])==2
    assert r['component_counts']=={'0':2,'8':3}
    assert not any(r[k] for k in ('no_path_proof','final_native_contacts_received',
        'current_qualified','barrel_ampacity_qualified','current_sharing_inferred',
        'routing_admitted','release_authority'))


def test_already_removed_middle_is_not_misreported_as_no_path_proof():
    parts,terms=fixture_geometry();parts[8].pop(1)
    r=pending.component_proposals(parts,terminal_components=terms,land_radius_mm=.3,
        native_transition_clear=middle_guard)
    assert not r['proposed_face_path_found'] and not r['no_path_proof']


def test_all_mandatory_terminals_are_retained_including_uncontacted_terminal():
    parts,terms=fixture_geometry();terms['actual_uncontacted_terminal']=[]
    r=pending.component_proposals(parts,terminal_components=terms,land_radius_mm=.3,
        native_transition_clear=lambda p:True)
    assert not r['proposed_face_path_found']
    assert r['unresolved_terminals']==['actual_uncontacted_terminal']
    assert r['terminal_component_hints']['actual_uncontacted_terminal']==[]


@pytest.mark.parametrize('answer',[False,None,0,1,{'ok':True}])
def test_only_positive_native_boolean_can_propose_a_transition(answer):
    parts,terms=fixture_geometry()
    r=pending.component_proposals(parts,terminal_components=terms,land_radius_mm=.3,
        native_transition_clear=lambda p:answer)
    assert not r['proposed_face_path_found'] and not r['proposed_transitions']


def test_pairs_get_a_turn_before_large_or_many_piece_pairs_consume_budget():
    # The large root-root intersection does not starve the useful middle pair.
    parts,terms=fixture_geometry()
    seen=[]
    def guard(at):
        seen.append(at);return middle_guard(at)
    r=pending.component_proposals(parts,terminal_components=terms,land_radius_mm=.3,
        native_transition_clear=guard,maximum_checks=6)
    assert r['candidate_component_pairs']==6 and r['native_checked_count']==6
    assert r['proposed_face_path_found'] and r['proposal_budget_exhausted']
    assert len({tuple(tuple(n) for n in row['components']) for row in r['native_checked_sites']})==6


def test_first_rejected_site_does_not_end_pair_search():
    parts,terms=fixture_geometry();calls={}
    def guard(at):
        # Reject the representative site for every geometrically useful pair.
        side=(at[0]<15000000,10000000<at[1]<20000000)
        calls[side]=calls.get(side,0)+1
        return calls[side]>1 and middle_guard(at)
    r=pending.component_proposals(parts,terminal_components=terms,land_radius_mm=.3,
        native_transition_clear=guard)
    assert r['proposed_face_path_found']
    assert any(not row['native_clear'] for row in r['native_checked_sites'])


def test_hole_sliver_and_boundary_touch_do_not_supply_land_contact():
    donut=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(1,1),(9,1),(9,9),(1,9)]])
    a=box(2,2,8,8);sliver=box(0,0,.1,10)
    components={0:[donut],8:[a,sliver]}
    r=pending.component_proposals(components,terminal_components={
        'first':[_key(0,donut)],'last':[_key(8,a)]},land_radius_mm=.3,
        native_transition_clear=lambda p:pytest.fail('no full-land interior exists'))
    assert not r['proposed_face_path_found'] and r['native_checked_count']==0


def test_budget_and_deadline_are_unresolved_not_no_path():
    parts,terms=fixture_geometry()
    for extra in (dict(maximum_checks=1),dict(deadline=time.monotonic()-1),dict(maximum_pairs=1)):
        r=pending.component_proposals(parts,terminal_components=terms,land_radius_mm=.3,
            native_transition_clear=lambda p:True,**extra)
        assert r['proposal_budget_exhausted'] and not r['proposed_face_path_found']
        assert not r['no_path_proof']


@pytest.mark.parametrize('fault',['duplicate','multi','nan','bool','checks','pairs','unknown','invalid'])
def test_malformed_or_unbounded_geometry_refuses(fault):
    parts,terms=fixture_geometry()
    args=dict(terminal_components=terms,land_radius_mm=.3,native_transition_clear=lambda p:True)
    if fault=='duplicate':parts[0].append(parts[0][0])
    elif fault=='multi':
        from shapely.geometry import MultiPolygon
        parts[0]=[MultiPolygon(parts[0])]
    elif fault=='nan':args['land_radius_mm']=float('nan')
    elif fault=='bool':args['land_radius_mm']=True
    elif fault=='checks':args['maximum_checks']=257
    elif fault=='pairs':args['maximum_pairs']=4097
    elif fault=='unknown':terms['missing']=[(0,'caller-asserted-component')]
    elif fault=='invalid':parts[0]=[Polygon([(0,0),(1,1),(1,0),(0,1)])]
    with pytest.raises(ValueError):pending.component_proposals(parts,**args)


def native_fixture(tmp_path,quarter=0,mirror=False):
    board=pcbnew.CreateEmptyBoard();board.SetCopperLayerCount(6)
    for name in ('arbitrary force net','unrelated control net'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    def xy(x,y):
        x,y=x-15,y-15
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return pcbnew.VECTOR2I(round((x+51.234567)*1e6),round((y+62.765432)*1e6))
    corners=[(0,0),(30,0),(30,30),(0,30)]
    for a,b in zip(corners,corners[1:]+corners[:1]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(xy(*a));edge.SetEnd(xy(*b));edge.SetWidth(50000)
        board.Add(edge)
    for face,a,b in ((pcbnew.B_Cu,(15,-1),(15,31)),
                     (pcbnew.In3_Cu,(-1,10),(31,10)),(pcbnew.In3_Cu,(-1,20),(31,20))):
        track=pcbnew.PCB_TRACK(board);track.SetLayer(face);track.SetWidth(500000)
        track.SetStart(xy(*a));track.SetEnd(xy(*b));track.SetNet(board.FindNet('unrelated control net'))
        board.Add(track)
    # Other enabled faces prohibit the two one-via shortcuts. The middle
    # corridor requires TWO real transitions, not an invented center contact.
    for a,b in (((15,5),(31,5)),((-1,25),(15,25))):
        track=pcbnew.PCB_TRACK(board);track.SetLayer(pcbnew.In2_Cu);track.SetWidth(12000000)
        track.SetStart(xy(*a));track.SetEnd(xy(*b));track.SetNet(board.FindNet('unrelated control net'))
        board.Add(track)
    def via(at,add=True):
        v=pcbnew.PCB_VIA(board);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(600000);v.SetDrill(300000)
        v.SetNet(board.FindNet('arbitrary force net'));v.SetPosition(at)
        if add:board.Add(v)
        return v
    terminals=[]
    for number,at in enumerate((xy(5,5),xy(25,25))):
        owner=pcbnew.FOOTPRINT(board);owner.SetReference('arbitrary terminal '+str(number))
        owner.SetPosition(at);board.Add(owner)
        pad=pcbnew.PAD(owner);pad.SetNumber(str(number));pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE);pad.SetSize(pcbnew.VECTOR2I(900000,900000))
        pad.SetDrillSize(pcbnew.VECTOR2I(300000,300000));pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetNet(board.FindNet('arbitrary force net'));pad.SetPosition(at);owner.Add(pad)
        terminals.append(pad)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary metadata owner');fp.SetValue('unchanged exact value')
    fp.SetPosition(xy(2,2));board.Add(fp)
    group=pcbnew.PCB_GROUP(board);group.SetName('unchanged locked group');group.SetLocked(True)
    board.Add(group);group.AddItem(fp)
    path=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    board=pcbnew.LoadBoard(str(path));board.SetFileName(str(path))
    definitions=[]
    for face in (pcbnew.B_Cu,pcbnew.In3_Cu):
        definitions.append(dict(uuid=str(uuid.uuid4()),net='arbitrary force net',layer=int(face),
            outline_nm=[list(xy(*p)) for p in ((1,1),(29,1),(29,29),(1,29))],
            clearance_nm=200000,min_thickness_nm=200000,priority=0,island_removal='ALWAYS'))
    proposal=pcbnew.PCB_VIA(board);proposal.SetViaType(pcbnew.VIATYPE_THROUGH)
    proposal.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);proposal.SetWidth(600000);proposal.SetDrill(300000)
    proposal.SetNet(board.FindNet('arbitrary force net'));proposal.SetPosition(xy(15,15))
    return board,definitions,[v.m_Uuid.AsString() for v in terminals],proposal,path


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_real_native_pending_island_never_mutates_source_and_final_always_requires_actual_vias(tmp_path,quarter,mirror):
    board,defs,ids,via,path=native_fixture(tmp_path,quarter,mirror)
    raw=path.read_bytes();binding=frame.binding(board,time.monotonic()+9.)
    result=pending.native_frontier(board,source_binding=binding,incoming_definitions=defs,
        terminal_uuids=ids,via=via,clearance_nm=200000,maximum_checks=32)
    assert result['proposed_face_path_found'] and len(result['proposed_transitions'])==2
    assert sorted(result['component_counts'].values())==[2,3]
    assert frame.binding(board,time.monotonic()+9.)==binding and path.read_bytes()==raw
    assert not list(board.Zones()) and not result['routing_admitted']
    # Independent construction on a new frame, never the NEVER planning copy.
    child=frame.clone(board,time.monotonic()+9.)
    zones=pending._add_definitions(child,defs,pending._uuid_values(frame.nodes(child,time.monotonic()+9.)[0]))
    fill.compile_selected(child,zones,initialize_selected=True)
    inner=next(z for z in zones if z.GetLayer()==pcbnew.In3_Cu)
    assert inner.GetFilledPolysList(inner.GetLayer()).OutlineCount()==2
    import cec_ordinary_route_receiving as ordinary
    import cec_force_current as force
    def joined():
        pads={p.m_Uuid.AsString():p for f in child.GetFootprints() for p in f.Pads()}
        keys={force._item_key(pads[uid]) for uid in ids}
        return any(keys<=part for part in ordinary._partition(child,time.monotonic()+9.))
    assert not joined()
    created=[]
    for row in result['proposed_transitions']:
        v=pcbnew.PCB_VIA(child);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetWidth(600000);v.SetDrill(300000)
        v.SetPosition(pcbnew.VECTOR2I(*row['at_nm']));v.SetNet(child.FindNet('arbitrary force net'));child.Add(v)
        created.append(v)
    fill.compile_selected(child,zones,initialize_selected=True)
    assert inner.GetFilledPolysList(inner.GetLayer()).OutlineCount()==3
    assert all(z.GetIslandRemovalMode()==pcbnew.ISLAND_REMOVAL_MODE_ALWAYS for z in zones)
    assert joined()
    # A retained middle island by itself is NOT proof of a complete chain.
    from cec_native_items import discard_items
    discard_items(child,[created.pop()]);fill.compile_selected(child,zones,initialize_selected=True)
    assert not joined()
    assert path.read_bytes()==raw


@pytest.mark.parametrize('fault',['stale_binding','collision','nested_collision','wrong_terminal','filtered_terminal',
    'wrong_net','retained_policy','live_via','inner_floor','blind','bad_definition','native_failure','retained_fill_mutation'])
def test_native_ownership_process_and_retained_source_faults_refuse(tmp_path,monkeypatch,fault):
    board,defs,ids,via,path=native_fixture(tmp_path)
    if fault=='collision':
        zones=pending._add_definitions(board,copy.deepcopy(defs),set())
        assert len(zones)==2
    elif fault=='nested_collision':defs[0]['uuid']=ids[0]
    elif fault=='wrong_terminal':ids[0]=str(uuid.uuid4())
    elif fault=='filtered_terminal':ids.append(str(uuid.uuid4()))
    elif fault=='wrong_net':via.SetNet(board.FindNet('unrelated control net'))
    elif fault=='retained_policy':defs[0]['island_removal']='NEVER'
    elif fault=='live_via':board.Add(via)
    elif fault=='inner_floor':board.GetDesignSettings().m_ViasMinSize=700000
    elif fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault=='bad_definition':defs[0]['min_thickness_nm']=True
    elif fault=='native_failure':
        def fail(*a,**k):raise RuntimeError('synthetic native refusal')
        monkeypatch.setattr(fill,'compile_selected',fail)
    elif fault=='retained_fill_mutation':
        real=fill.compile_selected
        def corrupt(b,*a,**k):
            real(b,*a,**k);next(iter(b.GetFootprints())).SetValue('mutated retained metadata')
        monkeypatch.setattr(fill,'compile_selected',corrupt)
    before=frame.binding(board,time.monotonic()+9.);raw=path.read_bytes()
    with pytest.raises((ValueError,RuntimeError)):
        pending.native_frontier(board,source_binding='stale' if fault=='stale_binding' else before,
            incoming_definitions=defs,terminal_uuids=ids,via=via,clearance_nm=200000)
    assert frame.binding(board,time.monotonic()+9.)==before and path.read_bytes()==raw


def test_original_success_deadline_includes_final_mandatory_source_identity_check(tmp_path,monkeypatch):
    board,defs,ids,via,path=native_fixture(tmp_path)
    before=frame.binding(board,time.monotonic()+9.);raw=path.read_bytes()
    clock=[100.];monkeypatch.setattr(time,'monotonic',lambda:clock[0])
    real=frame.binding;calls=[]
    def delayed_final_binding(*a,**kw):
        value=real(*a,**kw);calls.append(value)
        if len(calls)==2:clock[0]+=9.2
        return value
    monkeypatch.setattr(frame,'binding',delayed_final_binding)
    with pytest.raises(ValueError,match='pending_copper_deadline'):
        pending.native_frontier(board,source_binding=before,incoming_definitions=defs,
            terminal_uuids=ids,via=via,clearance_nm=200000)
    assert calls==[before,before] and path.read_bytes()==raw


@pytest.mark.parametrize('fault',['retained_fill','retained_policy'])
def test_actual_prefilled_retained_native_zone_is_never_planning_owned(tmp_path,monkeypatch,fault):
    board,defs,ids,via,path=native_fixture(tmp_path)
    zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet('unrelated control net'));zone.SetLayer(pcbnew.F_Cu)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    zone.SetMinThickness(200000);zone.SetLocalClearance(200000)
    for x,y in ((38,49),(63,74)):
        zone.Outline().NewOutline()
        for dx,dy in ((0,0),(2,0),(2,2),(0,2)):zone.Outline().Append(round((x+dx)*1e6),round((y+dy)*1e6))
    board.Add(zone);fill.compile_selected(board,[zone],initialize_selected=True)
    assert zone.GetFilledPolysList(zone.GetLayer()).OutlineCount()==2
    retained=zone.m_Uuid.AsString();pcbnew.SaveBoard(str(path),board)
    board=pcbnew.LoadBoard(str(path));board.SetFileName(str(path))
    # Bind a fresh detached native via to the actual reloaded context.
    via.SetNet(board.FindNet('arbitrary force net'))
    before=frame.binding(board,time.monotonic()+9.);raw=path.read_bytes()
    real=fill.compile_selected
    def corrupt(child,*a,**kw):
        answer=real(child,*a,**kw)
        retained_zone=next(z for z in child.Zones() if z.m_Uuid.AsString()==retained)
        if fault=='retained_fill':retained_zone.UnFill()
        else:retained_zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        return answer
    monkeypatch.setattr(fill,'compile_selected',corrupt)
    with pytest.raises(ValueError,match='changed_retained_source'):
        pending.native_frontier(board,source_binding=before,incoming_definitions=defs,
            terminal_uuids=ids,via=via,clearance_nm=200000)
    assert frame.binding(board,time.monotonic()+9.)==before and path.read_bytes()==raw

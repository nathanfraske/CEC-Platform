"""Draft-only native-reference and segmentation-invariant pair craft receiving."""
import copy,json,math,os,time
from pathlib import Path
import pcbnew
import pytest
import cec_pair_local_reference_refinement as repair
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track
import cec_pair_neutral_miter as neutral
import cec_pair_craft_reflow as physical_craft


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_width_aware_miter_changes_actual_copper_flat_not_just_centerline_count(quarter,mirror,reverse):
    def point(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+10000000,y+10000000]
    points=[point(x,y) for x,y in ((0,0),(1000000,1000000),(1040000,1000000),(2040000,0),(2540000,0))]
    if reverse:points.reverse()
    frame=physical_craft.miter_frames(points,250000)[0]
    assert not physical_craft.visible_miter(frame['source_flat_nm'],250000)
    result=physical_craft.wider_points(frame,250000)
    assert result[0]==points[0] and result[-1]==points[-1]
    def lengths(rows):
        edges=[[b[i]-a[i] for i in (0,1)] for a,b in zip(rows,rows[1:])]
        return sorted(x*x+y*y for x,y in edges if x and y),sum(abs(x)+abs(y) for x,y in edges if not x or not y)
    assert lengths(points)==lengths(result)
    assert physical_craft.visible_miter(250000,250000)
    assert not physical_craft.visible_miter(196776,250000)
    assert physical_craft.visible_miter(196777,250000)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('placement',['start','end'])
def test_source_phase_pack_retains_exact_cardinal_and_diagonal_totals(quarter,mirror,placement):
    def point(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+10000000,y+10000000]
    points=[point(x,y) for x,y in ((0,0),(1000000,1000000),(1200000,1000000),(1500000,1300000),(1900000,1300000))]
    result=physical_craft.packed_points(points,placement)
    assert len(result)==3 and result[0]==points[0] and result[-1]==points[-1]
    def exact_parts(rows):
        edges=[[b[i]-a[i] for i in (0,1)] for a,b in zip(rows,rows[1:])]
        return sum(abs(x) for x,y in edges if x and y),sum(abs(x)+abs(y) for x,y in edges if not x or not y)
    assert exact_parts(points)==exact_parts(result)


@pytest.mark.parametrize('reverse',[False,True])
def test_plated_port_miter_length_nonincrease_is_integer_proven(reverse):
    points=[[0,0],[1000000,1000000],[1040000,1000000],[2040000,0],[2133502,0]]
    if reverse:points.reverse()
    frame=physical_craft.miter_frames(points,250000)[0]
    result,proof=physical_craft.port_points(frame,250000)
    assert physical_craft.visible_miter(250000,250000)
    assert proof['integer_squared_nonincrease'] and proof['no_meaningful_centerline_shortening_claimed']
    assert len(result)==4
    lengths=lambda p:sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(p,p[1:]))
    assert lengths(result)<=lengths(points)


@pytest.mark.parametrize('value',[True,0,-1,20000.,float('nan')])
def test_width_aware_pair_geometry_rejects_invalid_or_invisible_flat(value):
    frame=physical_craft.miter_frames([[0,0],[1000000,1000000],[1040000,1000000],[2040000,0],[2540000,0]],250000)[0]
    with pytest.raises(ValueError):physical_craft.wider_points(frame,value)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('placement',['start','end'])
@pytest.mark.parametrize('seed',[
    [[0,0],[0,1000000],[500000,1500000]],
    [[0,0],[0,1000000],[500000,1500000],[500000,1600000]]])
def test_short_monotone_phases_reorder_without_a_length_or_angle_waiver(quarter,mirror,placement,seed):
    def point(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+10000000,y+10000000]
    old=[point(*p) for p in seed];new=physical_craft.phase_points(old,placement)
    parts=lambda rows:(sum(abs(b[0]-a[0]) for a,b in zip(rows,rows[1:]) if a[0]!=b[0] and a[1]!=b[1]),
        sum(abs(b[0]-a[0])+abs(b[1]-a[1]) for a,b in zip(rows,rows[1:]) if a[0]==b[0] or a[1]==b[1]))
    assert old[0]==new[0] and old[-1]==new[-1] and parts(old)==parts(new)
    if len(seed)==3:
        with pytest.raises(ValueError):physical_craft.packed_points(old,placement)
    else:assert physical_craft.packed_points(old,placement)==new


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_private_ordinary_proposal_is_packed_and_pad_clipped_without_mutating_native_source(quarter,mirror,face):
    def point(x,y):
        x,y=x-15,y-15
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [round((x+15)*1e6),round((y+15)*1e6)]
    points=[point(x,y) for x,y in ((5,20),(5,15),(6,14),(6,13.75),(10,13.75),(10,14),(11,15))]
    board=_board([(p[0]/1e6,p[1]/1e6,'/RENAMED/SUPPORT') for p in (points[0],points[-1])],edge=(0,0,30,30))
    for f in board.GetFootprints():
        for p in f.Pads():
            layers=pcbnew.LSET();layers.AddLayer(face);p.SetLayerSet(layers)
    target=next(p for f in board.GetFootprints() for p in f.Pads() if list(p.GetPosition())==points[-1])
    before=field._field_snapshot_inventory(board)
    result=physical_craft.polish_proposed_chain(board,points,net_code=target.GetNetCode(),layer=face,
        width_nm=200000,clearance_nm=200000,target_pad_uuid=force._uid(target))
    assert result['ok'] and result['complete'] and result['changed']
    assert result['hard90_before_after']==[2,0] and result['proposed_edges_before_after'][1]<6
    assert result['fully_target_pad_contained_retired_proposals']
    assert result['points_nm'][0]==points[0] and before==field._field_snapshot_inventory(board)
    assert not result['native_copper_mutated'] and not result['release_authority']


@pytest.mark.parametrize('fault',['foreign_on_source','keepout_on_source','wrong_target','missing_target','too_narrow','non45'])
def test_proposed_chain_never_waives_native_geometry_or_terminal_identity(fault):
    points=[[5000000,20000000],[5000000,15000000],[6000000,14000000],[6000000,13750000],
        [10000000,13750000],[10000000,14000000],[11000000,15000000]]
    board=_board([(5,20,'/S'),(11,15,'/S'),(25,25,'/FOREIGN')],edge=(0,0,30,30))
    target=next(p for f in board.GetFootprints() for p in f.Pads() if list(p.GetPosition())==points[-1])
    target_id=force._uid(target);width=200000
    if fault=='foreign_on_source':track(board,'/FOREIGN',(4.5,17),(5.5,17),width=.2)
    elif fault=='keepout_on_source':
        z=pcbnew.ZONE(board);z.SetIsRuleArea(True);z.SetLayer(pcbnew.F_Cu);z.SetDoNotAllowTracks(True);z.Outline().NewOutline()
        for x,y in ((4,16),(6,16),(6,18),(4,18)):z.Outline().Append(round(x*1e6),round(y*1e6))
        board.Add(z)
    elif fault=='wrong_target':target.SetNet(board.FindNet('/FOREIGN'))
    elif fault=='missing_target':target_id='not-an-actual-native-pad'
    elif fault=='too_narrow':width=1
    else:points[2][0]+=1
    before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):physical_craft.polish_proposed_chain(board,points,net_code=board.GetNetcodeFromNetname('/S'),
        layer=pcbnew.F_Cu,width_nm=width,clearance_nm=200000,target_pad_uuid=target_id)
    assert before==field._field_snapshot_inventory(board)


def straight_rows(parts=1,quarter=0,mirror=False,translation=(0,0),gap=.4):
    def point(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [round((x+translation[0])*1e6),round((y+translation[1])*1e6)]
    return [dict(net=net,layer='arbitrary-face',start_nm=point(10*i/parts,y),
        end_nm=point(10*(i+1)/parts,y)) for net,y in (('/renamed/P',0),('/renamed/N',gap)) for i in range(parts)]


PAIR=dict(p='/renamed/P',n='/renamed/N',width=.2,gap=.2)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_neutral_pair_splice_preserves_exact_diagonal_vectors_and_cardinal_length(quarter,mirror,reverse):
    def point(x,y):
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return [x+10000000,y+10000000]
    points=[point(x,y) for x,y in ((0,0),(0,1000000),(-1000000,2000000),(1000000,4000000))]
    if reverse:points.reverse()
    frames=neutral.frames(points);assert len(frames)==1
    result=neutral.shifted_points(frames[0],20000)
    assert result[0]==points[0] and result[-1]==points[-1]
    def lengths(rows):
        diffs=[(b[0]-a[0],b[1]-a[1]) for a,b in zip(rows,rows[1:])]
        return sorted(x*x+y*y for x,y in diffs if x and y),sum(abs(x)+abs(y) for x,y in diffs if not x or not y)
    assert lengths(points)==lengths(result)
    edges=[(b[0]-a[0],b[1]-a[1]) for a,b in zip(result,result[1:])]
    assert all(x==0 or y==0 or abs(x)==abs(y) for x,y in edges)
    assert all(u[0]*v[0]+u[1]*v[1]>0 and abs(u[0]*v[1]-u[1]*v[0])<=u[0]*v[0]+u[1]*v[1]
        for u,v in zip(edges,edges[1:]))


def neutral_fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    def point(x,y):
        x,y=x-20,y-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return round(x+20,6),round(y+20,6)
    nets=('/SOURCE_RENAMED/CAN_H','/SOURCE_RENAMED/CAN_L')
    # The inner-face fixture has real plated endpoint antipads. Give that
    # already-qualified bus enough real referenced length to satisfy its
    # unchanged 95% whole-pair contract before testing a neutral splice.
    paths={net:[point(x+shift,y) for x,y in ((10,5),(10,15),(9,16),(19,26))]
        for net,shift in zip(nets,(0.,.7))}
    board=_board([(*p[i],net) for net,p in paths.items() for i in (0,-1)]+[(4,4,'GND')],edge=(0,0,40,40))
    board.SetCopperLayerCount(6);props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pad.SetNumber('1')
            pad.SetSize(pcbnew.VECTOR2I_MM(.45,.45))
            if pad.GetNetname()=='GND' or layer==pcbnew.In2_Cu:
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
    for net,points in paths.items():
        for a,b in zip(points,points[1:]):track(board,net,a,b,layer=layer,width=.25)
    for ref in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet('GND'));zone.SetLayer(ref);zone.SetLocalClearance(200000)
        zone.SetMinThickness(100000);zone.Outline().NewOutline()
        for x,y in ((1,1),(39,1),(39,39),(1,39)):zone.Outline().Append(round(x*1e6),round(y*1e6))
        board.Add(zone)
    repair.additive._ground_refill(board)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        dict(name='Default',track_width=.25,diff_pair_width=.25,diff_pair_gap=.2,clearance=.2)]}}))
    field._save_field_snapshot(board,source)
    pair=next(p for p in repair.precision.derive_coupled_pairs(str(source),board=board) if p['kind']=='can')
    return board,source,pair


def physical_craft_fixture(tmp_path,operation,quarter=0,mirror=False,layer=pcbnew.F_Cu):
    board,source,pair=neutral_fixture(tmp_path,quarter,mirror,layer)
    if operation=='wide_miter':
        request=neutral.discover(board,source,pair)[0]
        neutral.construct_whole_pair(board,source,pair,request,20000,board_hint='synthetic')
    else:
        def point(x,y):
            x,y=x-20,y-20
            if mirror:x=-x
            for _ in range(quarter):x,y=-y,x
            return round(x+20,6),round(y+20,6)
        seed=([(5,5),(5,20),(6,21),(6.1,21),(7.1,22),(7.2,22),(12.2,27)] if operation=='phase_pack' else
            [(2,10),(34,10),(35,11),(35.04,11),(36.04,10),(36.134,10)])
        discard_items(board,list(board.GetTracks()))
        for net,shift in ((pair['p'],0.),(pair['n'],.7)):
            pads=[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==net]
            old_ends=[point(10+shift,5),point(19+shift,26)]
            shift_x,shift_y=(0.,shift) if operation=='port_miter' else (shift,0.)
            endpoints=[point(seed[i][0]+shift_x,seed[i][1]+shift_y) for i in (0,-1)]
            for pad in pads:
                position=tuple(v/1e6 for v in pad.GetPosition())
                index=min(range(2),key=lambda i:math.dist(position,old_ends[i]))
                pad.GetParent().SetPosition(pcbnew.VECTOR2I_MM(*endpoints[index]))
                if operation=='port_miter' and index==1:
                    pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
                    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
                    pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            points=[point(x+shift_x,y+shift_y) for x,y in seed]
            for a,b in zip(points,points[1:]):
                native=track(board,net,a,b,layer=layer,width=.25)
                # Fixture coordinates are exact integer stations. The older
                # convenience helper truncates binary floats after rotation.
                native.SetStart(pcbnew.VECTOR2I(*(round(v*1e6) for v in a)))
                native.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6) for v in b)))
    repair.additive._ground_refill(board)
    saved=force._copy_family(source,tmp_path/'craft-source');field._save_field_snapshot(board,saved)
    return board,saved,pair


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('operation',['wide_miter','phase_pack','port_miter'])
def test_native_physical_pair_craft_replays_under_full_saved_bus_contract(tmp_path,quarter,mirror,layer,operation):
    board,source,pair=physical_craft_fixture(tmp_path,operation,quarter,mirror,layer)
    original=source.read_bytes();refusals=[]
    requests=[r for r in physical_craft.discover(board,source,pair) if r['operation']==operation]
    assert requests
    # Phase placement and transformed plated-end direction remain source-derived;
    # native geometry and full-pair receiving decide which alternative is legal.
    for request in requests:
        board=pcbnew.LoadBoard(str(source))
        try:made=physical_craft.construct_whole(board,source,pair,request,board_hint='synthetic')
        except ValueError as exc:refusals.append(str(exc));continue
        child=force._copy_family(source,tmp_path/('candidate-'+str(len(refusals))))
        repair.additive._ground_refill(board);field._save_field_snapshot(board,child)
        proof=neutral.receive_phase(source,child,json.loads(json.dumps(made)),board_hint='synthetic',pair_name=pair['name'])
        if proof['ok'] and proof['complete']:break
        refusals.append(proof)
    else:pytest.fail(str(refusals))
    assert proof['physical_craft_operation']==operation and proof['continuous_coupling']['ok']
    assert proof['hard90_before_after'][1]<=proof['hard90_before_after'][0]
    assert all(not p['before']['violations'] and not p['after']['violations'] for p in proof['full_pair_physical_samples'])
    assert proof['existing_full_bus_receiver']['ok'] and not proof['release_authority']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['geometry','target','certificate','mapping','width','port','declaration','extra_key'])
def test_physical_miter_never_waives_process_ports_scope_or_exact_certificate(tmp_path,fault):
    board,source,pair=physical_craft_fixture(tmp_path,'wide_miter')
    request=next(r for r in physical_craft.discover(board,source,pair) if r['operation']=='wide_miter')
    made=physical_craft.construct_whole(board,source,pair,request,board_hint='synthetic')
    live={force._uid(t):t for t in board.GetTracks()}
    if fault=='geometry':live[made['local_new_track_uuids'][1]].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='target':made['operation_parameters']['target_flat_nm']+=1
    elif fault=='certificate':made['exact_neutral_geometry']['progress']['candidate_flat_nm']+=1
    elif fault=='mapping':made['unchanged_pair_native_copies'].pop(next(iter(made['unchanged_pair_native_copies'])))
    elif fault=='width':live[made['local_new_track_uuids'][0]].SetWidth(249999)
    elif fault=='port':next(p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==pair['p']).GetParent().Move(pcbnew.VECTOR2I(1,0))
    elif fault=='declaration':made['all_barrels_pads_and_nonpair_conductors_retained']=False
    else:made['extra_key']='waiver'
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    proof=neutral.receive_phase(source,child,json.loads(json.dumps(made)),board_hint='synthetic',pair_name=pair['name'])
    assert not proof['ok'] and not proof['complete'],proof


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_native_neutral_miter_receives_only_via_the_unchanged_positive_whole_pair_contract(tmp_path,quarter,mirror,layer):
    board,source,pair=neutral_fixture(tmp_path,quarter,mirror,layer);original=source.read_bytes()
    requests=neutral.discover(board,source,pair)
    assert requests
    made=neutral.construct_whole_pair(board,source,pair,requests[0],20000,board_hint='synthetic')
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    persisted=json.loads(json.dumps(made,allow_nan=False))
    proof=neutral.receive_phase(source,child,persisted,board_hint='synthetic',pair_name=pair['name'])
    assert proof['ok'] and proof['complete'],proof
    assert proof['shortened_centerline_mm']==0. and proof['exact_neutral_geometry']['exact_centerline_length_unchanged']
    assert proof['existing_full_bus_receiver']['ok'] and proof['continuous_coupling']['ok']
    assert all(not q['before']['violations'] and not q['after']['violations'] for q in proof['full_pair_physical_samples'])
    assert proof['hard90_before_after'][1]<proof['hard90_before_after'][0]
    assert not proof['pair_qualified'] and not proof['release_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('fault',['new_diagonal','old_diagonal','source_mapping','wrong_member','via','pose','width','flag','certificate'])
def test_neutral_whole_pair_receiving_never_authorizes_other_material_or_length_edits(tmp_path,fault):
    board,source,pair=neutral_fixture(tmp_path)
    request=neutral.discover(board,source,pair)[0]
    made=neutral.construct_whole_pair(board,source,pair,request,20000,board_hint='synthetic')
    live={force._uid(t):t for t in board.GetTracks()}
    if fault=='new_diagonal':live[made['local_new_track_uuids'][1]].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='old_diagonal':live[next(iter(made['unchanged_pair_native_copies'].values()))].Move(pcbnew.VECTOR2I(1,0))
    elif fault=='source_mapping':made['unchanged_pair_native_copies'].pop(next(iter(made['unchanged_pair_native_copies'])))
    elif fault=='wrong_member':pass  # Persist the hostile net field without a repairing native rebuild below.
    elif fault=='via':
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(4,4));via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(board.FindNet('GND'));board.Add(via)
    elif fault=='pose':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='width':live[made['local_new_track_uuids'][0]].SetWidth(249999)
    elif fault=='flag':made['all_barrels_pads_and_nonpair_conductors_retained']=False
    else:made['exact_neutral_geometry']['delta_nm']+=1
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    if fault=='wrong_member':
        root,nodes=repair.additive._nodes(child)
        node=nodes[made['local_new_track_uuids'][0]]
        next(row for row in node if isinstance(row,list) and row and row[0]=='net')[1]=str(board.FindNet(pair['n']).GetNetCode())
        child.write_text(repair.additive._render(root)+'\n')
    proof=neutral.receive_phase(source,child,json.loads(json.dumps(made)),board_hint='synthetic',pair_name=pair['name'])
    assert not proof['ok'] and not proof['complete'],proof


@pytest.mark.parametrize('delta',[0,True,19999,200001,float('nan'),20000.])
def test_neutral_splice_does_not_widen_the_source_geometry_work_domain(delta):
    frame=neutral.frames([[0,0],[0,1000000],[-1000000,2000000],[1000000,4000000]])[0]
    with pytest.raises(ValueError):neutral.shifted_points(frame,delta)


@pytest.mark.parametrize('parts',[1,2,7,31])
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_continuous_measure_does_not_vote_per_fragment(parts,quarter,mirror):
    result=repair.continuous_coupling(straight_rows(parts,quarter,mirror,(123.3,-456.7)),PAIR)
    assert result['ok'] and result['complete']
    assert result['coupled_fraction']==pytest.approx(1.,abs=1e-10)
    assert result['uncoupled_length_mm']==pytest.approx(0.,abs=1e-8)
    assert all(v==pytest.approx(10.) for v in result['member_lengths_mm'].values())
    assert not result['per_segment_sample_votes'] and not result['release_authority']


@pytest.mark.parametrize('gap,expected',[(.1,0.),(.4,1.),(2.,0.)])
def test_inner_and_outer_distance_limits_are_both_enforced(gap,expected):
    q=repair.continuous_coupling(straight_rows(gap=gap),PAIR)
    assert q['coupled_fraction']==pytest.approx(expected)


def test_capsule_endpoint_intersections_match_analytic_circle_span():
    rows=straight_rows();rows[1]['start_nm']=[5000000,400000];rows[1]['end_nm']=[6000000,400000]
    q=repair.continuous_coupling(rows,PAIR)
    radius=.85;expected=1.+2*math.sqrt(radius**2-.4**2)
    assert q['coupled_lengths_mm'][PAIR['p']]==pytest.approx(expected,abs=1e-10)
    assert q['coupled_lengths_mm'][PAIR['n']]==pytest.approx(1.)
    split=copy.deepcopy(rows);split[0]['end_nm']=[3000000,0]
    split.append(dict(net=PAIR['p'],layer='arbitrary-face',start_nm=[3000000,0],end_nm=[10000000,0]))
    other=repair.continuous_coupling(split,PAIR)
    assert other['coupled_fraction']==pytest.approx(q['coupled_fraction'],abs=1e-12)


@pytest.mark.parametrize('fault',['one_member','zero','wrong_net','wrong_face','bool_point','float_point','nan_width','infinite_gap'])
def test_missing_or_invalid_continuous_evidence_is_not_a_pass(fault):
    rows=straight_rows();pair=copy.deepcopy(PAIR)
    if fault=='one_member':rows=rows[:1]
    elif fault=='zero':rows[0]['end_nm']=rows[0]['start_nm']
    elif fault=='wrong_net':rows[0]['net']='/not_pair'
    elif fault=='wrong_face':rows[0]['layer']=None
    elif fault=='bool_point':rows[0]['start_nm'][0]=True
    elif fault=='float_point':rows[0]['start_nm'][0]=0.
    elif fault=='nan_width':pair['width']=float('nan')
    else:pair['gap']=float('inf')
    with pytest.raises(ValueError):repair.continuous_coupling(rows,pair)


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,hole=False,right_angle=False,renamed=False):
    def point(x,y):
        x,y=x-20,y-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return round(x+20,6),round(y+20,6)
    nets=('/renamed/USB_D_P','/renamed/USB_D_N')
    old_geometry=((10,10),(14,10),(14,14)) if right_angle else ((10,10),(12,10),(11,11),(14,11))
    new_geometry=((10,10),(13.8,10),(14,10.2),(14,14)) if right_angle else ((10,10),(13,10),(14,11))
    if renamed and not right_angle:
        # The inner-layer fixture uses plated terminal antipads. Preserve its
        # original entry/arrival directions and stay on the old line until
        # beyond each antipad; changing that approach is separately rejected.
        new_geometry=((10,10),(10.8,10),(11.8,11),(14,11))
    shifts=(0,6) if right_angle else (0,4)
    paths={net:[point(x,y+shift) for x,y in old_geometry] for net,shift in zip(nets,shifts)}
    new_paths={net:[point(x,y+shift) for x,y in new_geometry] for net,shift in zip(nets,shifts)}
    pads=[(*path[i],net) for net,path in paths.items() for i in (0,-1)]+[(4,4,'GND')]
    b=_board(pads,edge=(0,0,40,40));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    if renamed:b.SetLayerName(layer,'RENAMED_SIGNAL_FACE')
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            pad.SetNumber('1')
            if pad.GetNetname()=='GND' or layer==pcbnew.In2_Cu:
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
    cut=[]
    for net,path in paths.items():
        cut += [track(b,net,a,z,layer=layer,width=.2) for a,z in zip(path,path[1:])]
    zone=pcbnew.ZONE(b);zone.SetNet(b.FindNet('GND'))
    zone.SetLayer(pcbnew.In1_Cu if layer in (pcbnew.F_Cu,pcbnew.In2_Cu) else pcbnew.In4_Cu)
    zone.SetLocalClearance(200000);zone.SetMinThickness(100000)
    poly=zone.Outline();poly.NewOutline()
    for x,y in ((1,1),(39,1),(39,39),(1,39)):poly.Append(round(x*1e6),round(y*1e6))
    if hole:
        poly.NewHole(0)
        for x,y in ((12.8,9.7),(13.2,9.7),(13.2,10.3),(12.8,10.3)):
            x,y=point(x,y);poly.Append(round(x*1e6),round(y*1e6),0,0)
    b.Add(zone);repair.additive._ground_refill(b)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        dict(name='Default',track_width=.2,diff_pair_width=.2,diff_pair_gap=.2,clearance=.2)]}}))
    field._save_field_snapshot(b,source)
    ids=sorted(force._uid(t) for t in cut);exemplars={net:next(t for t in cut if t.GetNetname()==net) for net in nets}
    fresh=[]
    for net,path in new_paths.items():
        for a,z in zip(path,path[1:]):
            t=exemplars[net].Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);fresh.append(t)
    discard_items(b,cut);repair.additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,child)
    pair=repair.precision.derive_coupled_pairs(str(source),board=pcbnew.LoadBoard(str(source)))[0]
    return source,child,ids,pair


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_native_saved_draft_refinement_never_qualifies_an_uncoupled_source(tmp_path,quarter,mirror,layer):
    source,child,ids,pair=fixture(tmp_path,quarter,mirror,layer)
    old=(source.read_bytes(),child.read_bytes())
    q=repair.receive_literal_phase(source,child,ids,board_hint='synthetic',pair_name=pair['name'])
    assert q['ok'] and q['complete'],q
    assert q['exact_native_reference_deficit_receiving']['ok']
    assert q['independent_continuous_coupling_comparison']['ok']
    assert q['craft_before_after'][1]<q['craft_before_after'][0]
    assert not q['pair_qualified'] and not q['routing_admitted'] and not q['release_authority']
    assert all(row['after']['violations'] for row in q['whole_pair_physical_samples'])
    assert old==(source.read_bytes(),child.read_bytes())


def test_new_plane_gap_is_not_hidden_by_better_percent_or_shorter_path(tmp_path):
    source,child,ids,pair=fixture(tmp_path,hole=True)
    q=repair.receive_literal_phase(source,child,ids,board_hint='synthetic',pair_name=pair['name'])
    assert not q['ok'] and not q['complete'] and any('unreferenced_pair_copper' in e for e in q['errors']),q


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_zero_acute_counter_does_not_hide_real_native_pair_right_angles(tmp_path,quarter,mirror,layer):
    source,child,ids,pair=fixture(tmp_path,quarter,mirror,layer,right_angle=True)
    q=repair.receive_literal_phase(source,child,ids,board_hint='synthetic',pair_name=pair['name'])
    assert q['ok'] and q['complete'],q
    assert q['craft_before_after']==[0,0] and q['eligible_hard90_before_after']==[2,0]
    assert q['independent_continuous_coupling_comparison']['ok']
    assert not q['pair_qualified'] and not q['release_authority']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('right_angle',[False,True])
def test_inner_signal_roles_use_canonical_identity_not_native_display_label(tmp_path,quarter,mirror,right_angle):
    source,child,ids,pair=fixture(tmp_path,quarter,mirror,pcbnew.In2_Cu,right_angle=right_angle,renamed=True)
    q=repair.receive_literal_phase(source,child,ids,board_hint='synthetic',pair_name=pair['name'])
    assert q['ok'] and q['complete'],q
    witness=q['exact_native_reference_deficit_receiving']
    assert witness['signal_face']=='In2.Cu' and witness['reference_face']=='In1.Cu'
    assert witness['native_display_signal_face']=='RENAMED_SIGNAL_FACE'
    assert not q['pair_qualified'] and not q['release_authority']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_inner_plated_antipad_approach_is_not_exempted_by_canonical_layer_identity(tmp_path,quarter,mirror):
    source,child,ids,pair=fixture(tmp_path,quarter,mirror,pcbnew.In2_Cu)
    q=repair.receive_literal_phase(source,child,ids,board_hint='synthetic',pair_name=pair['name'])
    assert not q['ok'] and not q['complete']
    assert any('new_native_unreferenced_pair_copper' in e for e in q['errors']),q


@pytest.mark.parametrize('fault',['missing','duplicate','mask','width','lock','extra_via','pad','metadata','sidecar','ground_fill','source_track'])
def test_saved_worker_cannot_launder_unowned_source_changes(tmp_path,fault):
    source,child,ids,pair=fixture(tmp_path)
    if fault=='missing':ids[0]='not_a_source_uuid'
    elif fault=='duplicate':ids[0]=ids[1]
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    else:
        b=pcbnew.LoadBoard(str(child));t=next(iter(b.GetTracks()))
        if fault=='mask':t.SetHasSolderMask(True)
        elif fault=='width':t.SetWidth(190000)
        elif fault=='lock':t.SetLocked(True)
        elif fault=='extra_via':
            v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(30,30));v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        elif fault=='pad':next(iter(next(iter(b.GetFootprints())).Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
        elif fault=='metadata':b.SetCopperLayerCount(4)
        elif fault=='ground_fill':next(iter(b.Zones())).UnFill()
        else:track(b,'/renamed/USB_D_P',(25,25),(26,25))
        field._save_field_snapshot(b,child)
    before=(source.read_bytes(),child.read_bytes())
    q=repair.receive_literal_phase(source,child,ids,board_hint='synthetic',pair_name=pair['name'])
    assert not q['ok'] and not q['complete'] and q['errors'],q
    assert not q['release_authority'] and before==(source.read_bytes(),child.read_bytes())


def test_metric_comparison_cannot_be_used_without_its_continuous_witness():
    assert not repair.metric_progress({}, {})['ok']


def test_continuous_comparison_cannot_hide_genuinely_worse_coupling():
    old=repair.continuous_coupling(straight_rows(gap=.4),PAIR)
    new=repair.continuous_coupling(straight_rows(gap=2.),PAIR)
    q=repair.compare_continuous(old,new)
    assert not q['ok'] and not q['release_authority']


def test_saved_full_receiving_requires_all_independent_evidence(tmp_path):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    source,child,ids,pair=fixture(tmp_path)
    q=repair.receive(source,child,ids,board_hint='synthetic',pair_name=pair['name'],reporting_build=Path(native))
    assert q['ok'] and q['complete'] and q['opens']==0,q
    assert q['whole_parent_current_receiving']['ok'] and q['whole_parent_clipped_preservation']['same_evidence']
    assert not q['new_native_fault_ids'] and not q['pair_qualified'] and not q['release_authority']


@pytest.mark.parametrize('kwargs',[dict(max_trials=True),dict(max_trials=0),dict(max_trials=33),
    dict(max_accepted=0),dict(max_accepted=5),dict(allow_locked_source=1),
    dict(expected_source_sha256='bad'),dict(reporting_build=None),dict(board_hint='')])
def test_invalid_automatic_pair_context_creates_no_candidate(tmp_path,kwargs):
    options=dict(board_hint='synthetic',expected_source_sha256='0'*64,reporting_build=tmp_path/'native')
    options.update(kwargs);out=tmp_path/'no-output'
    with pytest.raises(ValueError):repair.run_chamfer_stage(tmp_path/'missing',out,**options)
    assert not out.exists()


def test_automatic_pair_stage_and_independent_whole_chain_use_real_native_geometry(tmp_path):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    source,_,_,_=fixture(tmp_path,right_angle=True)
    before=source.read_bytes()
    q=repair.run_chamfer_stage(source,tmp_path/'stage',board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=Path(native),max_trials=3,max_accepted=1)
    assert q['ok'] and q['complete'] and q['changed'],q
    proof=q['independent_whole_parent_receiving']
    assert proof['ok'] and proof['complete'] and proof['hard90_vertices_removed']==2
    assert proof['opens']==0 and not proof['new_native_fault_ids']
    assert source.read_bytes()==before and q['source_family_and_code_unchanged']
    replay=repair.receive_chain(source,q['candidate'],q['records'],board_hint='synthetic',reporting_build=Path(native))
    assert replay['ok'] and replay['complete'] and not replay['pair_qualified'] and not replay['release_authority']


@pytest.mark.parametrize('fault',['extra_field','wrong_source_hash','wrong_candidate_hash','not_contiguous'])
def test_worker_chain_flags_cannot_substitute_for_exact_saved_source_lineage(tmp_path,fault):
    source,child,ids,pair=fixture(tmp_path,right_angle=True)
    row=dict(source=str(source),source_sha256=force._hash(source),candidate=str(child),
        candidate_sha256=force._hash(child),pair_name=pair['name'],retired_track_uuids=ids)
    if fault=='extra_field':row['worker_pass']=True
    elif fault=='wrong_source_hash':row['source_sha256']='0'*64
    elif fault=='wrong_candidate_hash':row['candidate_sha256']='0'*64
    else:row['source']=str(child)
    before=(source.read_bytes(),child.read_bytes())
    q=repair.receive_chain(source,child,[row],board_hint='synthetic',reporting_build=tmp_path/'not-used')
    assert not q['ok'] and not q['complete'] and q['errors'],q
    assert before==(source.read_bytes(),child.read_bytes()) and not q['release_authority']


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_small_diagonal_corner_in_existing_reference_void_has_exact_physical_source_cover(tmp_path,quarter,mirror,layer):
    def at(x,y):
        x,y=x-20,y-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return round(x+20,6),round(y+20,6)
    nets=('/synthetic/USB_D_P','/synthetic/USB_D_N')
    paths={net:[at(x,y+offset) for x,y in ((10,10),(12,12),(10,14))]
           for net,offset in zip(nets,(0,6))}
    b=_board([(*points[i],net) for net,points in paths.items() for i in (0,-1)]+[(4,4,'GND')],edge=(0,0,40,40))
    b.SetCopperLayerCount(6);props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            pad.SetNumber('1')
            if pad.GetNetname()=='GND':
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            else:
                layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
    for net,points in paths.items():
        for a,z in zip(points,points[1:]):track(b,net,a,z,width=.2,layer=layer)
    zone=pcbnew.ZONE(b);zone.SetNet(b.FindNet('GND'))
    zone.SetLayer(pcbnew.In1_Cu if layer==pcbnew.F_Cu else pcbnew.In4_Cu)
    zone.SetLocalClearance(200000);zone.SetMinThickness(100000)
    poly=zone.Outline();poly.NewOutline()
    for x,y in ((1,1),(39,1),(39,39),(1,39)):poly.Append(round(x*1e6),round(y*1e6))
    poly.NewHole(0)
    for x,y in ((8,8),(20,8),(20,32),(8,32)):
        x,y=at(x,y);poly.Append(round(x*1e6),round(y*1e6),0,0)
    b.Add(zone);repair.additive._ground_refill(b)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        dict(name='Default',track_width=.2,diff_pair_width=.2,diff_pair_gap=.2,clearance=.2)]}}))
    field._save_field_snapshot(b,source)
    pair=repair.precision.derive_coupled_pairs(str(source),board=b)[0]
    import cec_scalar_corner_stage as constructor
    requests=repair.bend_inventory(b,pair)['selected'];assert len(requests)==2
    made=constructor.construct(b,requests,set(nets),minimum_nm=20000,maximum_nm=50000,timeout_s=10.)
    repair.additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(b,child)
    proof=repair.receive_literal_phase(source,child,made['retired_track_uuids'],board_hint='synthetic',pair_name=pair['name'])
    assert proof['ok'] and proof['complete'],proof
    reference=proof['exact_native_reference_deficit_receiving']
    assert reference['actual_source_capsule_containment']['ok']
    assert reference['actual_source_capsule_containment']['numeric_tolerance_nm']==0
    assert not reference['numeric_or_area_waiver_used'] and not proof['pair_qualified']


def test_fair_heads_do_not_exhaust_one_pair_before_funding_another_face():
    def req(net,index,face):return dict(net=net,layer=face,at_nm=[index,0],source_track_uuids=[str(index)+'a',str(index)+'b'])
    pair_a=dict(name='a',p='aP',n='aN');pair_b=dict(name='b',p='bP',n='bN')
    portfolios=[(pair_a,0,[req('aP',i,0) for i in range(12)]),
        (pair_a,2,[req('aP',21,2),req('aN',22,2)]),(pair_b,0,[req('bP',31,0)])]
    heads=repair._fair_chamfer_heads(portfolios,set(),{})
    assert [(p['name'],rows[0]['layer']) for _,p,rows,_ in heads]==[('a',0),('a',2),('b',0)]
    assert all(maximum==200000 for _,_,_,maximum in heads)
    key=heads[0][0];next_heads=repair._fair_chamfer_heads(portfolios,{(key,200000)},{key:100000})
    assert next_heads[0][0]==key and next_heads[0][-1]==100000
    assert next_heads[1:]==heads[1:]


@pytest.mark.parametrize('message',['new_native_unreferenced_pair_copper',
    'whole_pair_continuous_coupling_regression','native_pair_chamfer_constructor_made_no_change'])
@pytest.mark.parametrize('maximum,expected',[(200000,100000),(100000,50000),(50000,21000),(21000,None)])
def test_only_finite_smaller_geometry_is_queued_not_a_receiving_exception(message,maximum,expected):
    assert repair._smaller_chamfer(maximum,message)==expected


@pytest.mark.parametrize('message',['single_native_local_pair_path_required','skew_mm',
    'unchanged_profile_referenced_signal_face_required','local_pair_source_contract_changed'])
def test_intrinsic_contract_or_topology_failures_are_not_repeated_at_smaller_sizes(message):
    assert repair._smaller_chamfer(200000,message) is None


def mixed_coupling_rows(main_nm=10000000,p_tail_nm=500000,n_tail_nm=1000000):
    return [dict(net=net,layer=face,start_nm=a,end_nm=b) for net,face,a,b in (
        (PAIR['p'],'common',[0,0],[main_nm,0]),
        (PAIR['n'],'common',[0,400000],[main_nm,400000]),
        (PAIR['p'],'P-only',[main_nm,0],[main_nm+p_tail_nm,0]),
        (PAIR['n'],'N-only',[main_nm,400000],[main_nm+n_tail_nm,400000]))]


def test_shortening_good_copper_does_not_invent_more_actual_uncoupled_length():
    before=repair.continuous_coupling(mixed_coupling_rows(),PAIR)
    after=repair.continuous_coupling(mixed_coupling_rows(main_nm=9000000),PAIR)
    assert after['coupled_fraction']<before['coupled_fraction']
    assert after['legacy_fraction_weighted_uncoupled_length_mm']>before['legacy_fraction_weighted_uncoupled_length_mm']
    assert after['member_uncoupled_lengths_mm']==pytest.approx(before['member_uncoupled_lengths_mm'])
    result=repair.compare_continuous(before,after)
    assert result['ok'] and result['complete'] and not result['pair_qualified'],result
    assert result['previously_passing_production_coupling_contract_must_remain_positive']


def test_one_member_deficit_cannot_be_traded_against_an_improvement_in_the_other():
    before=repair.continuous_coupling(mixed_coupling_rows(),PAIR)
    after=repair.continuous_coupling(mixed_coupling_rows(p_tail_nm=600000,n_tail_nm=800000),PAIR)
    assert after['uncoupled_length_mm']<before['uncoupled_length_mm']
    result=repair.compare_continuous(before,after)
    assert not result['ok'] and any(PAIR['p'] in e for e in result['errors']),result


@pytest.mark.parametrize('fault',['missing','forged','negative','extra_member','wrong_maximum'])
def test_continuous_deficits_are_rederived_not_worker_success_fields(fault):
    before=repair.continuous_coupling(mixed_coupling_rows(),PAIR);after=copy.deepcopy(before)
    if fault=='missing':after.pop('member_uncoupled_lengths_mm')
    elif fault=='forged':after['member_uncoupled_lengths_mm'][PAIR['p']]=0.
    elif fault=='negative':after['coupled_lengths_mm'][PAIR['p']]=-1.
    elif fault=='extra_member':after['member_lengths_mm']['not-the-pair']=1.
    else:after['uncoupled_length_mm']=0.
    result=repair.compare_continuous(before,after)
    assert not result['ok'] and result['errors'] and not result['release_authority']


def test_actual_deficit_progress_does_not_waive_a_previously_positive_production_contract(tmp_path):
    source,child,ids,pair=fixture(tmp_path,right_angle=True)
    proof=repair.receive_literal_phase(source,child,ids,board_hint='synthetic',pair_name=pair['name'])
    assert proof['ok'],proof
    old=copy.deepcopy(proof['whole_pair_physical_samples'][0]['before']);new=copy.deepcopy(old)
    old['coupling_admission']['ok']=True;new['coupling_admission']['ok']=False
    comparison=repair.metric_progress(old,new,coupling=proof['independent_continuous_coupling_comparison'])
    assert not comparison['ok'] and 'previously_passing_release_coupling_check_lost' in comparison['errors']


def terminal_tie_fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu,mixed_member_locks=False,tie_layer=None):
    def point(x,y):
        x,y=x-20,y-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return round(x+20,6),round(y+20,6)
    nets=('/synthetic/USB_D_P','/synthetic/USB_D_N')
    paths={nets[0]:[point(x,y) for x,y in ((10,10),(10,11.8),(10.2,12),(12.8,12),(13,11.8),(13,10))],
           nets[1]:[point(x,y) for x,y in ((16,10),(18,10),(18,12))]}
    board=_board([(4,4,'GND')],edge=(0,0,40,40));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';board.SetProperties(props)
    ground=next(iter(next(iter(board.GetFootprints())).Pads()))
    ground.SetAttribute(pcbnew.PAD_ATTRIB_PTH);ground.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));ground.SetLayerSet(pcbnew.LSET.AllCuMask())
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('UNRELATED_PORT_NAME');board.Add(fp)
    for index,(net,path) in enumerate(paths.items()):
        board.Add(pcbnew.NETINFO_ITEM(board,net))
        for i,at in enumerate((path[0],path[-1])):
            pad=pcbnew.PAD(fp);pad.SetNumber(str(index*2+i+1));pad.SetNet(board.FindNet(net))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.6,.6));layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
            pad.SetPosition(pcbnew.VECTOR2I_MM(*at));fp.Add(pad)
        for a,z in zip(path,path[1:]):
            t=track(board,net,a,z,width=.2,layer=tie_layer if index==0 and tie_layer is not None else layer)
            t.SetLocked(bool(mixed_member_locks and net==nets[0]))
        if index==0 and tie_layer is not None and tie_layer!=layer:
            for at in (path[0],path[-1]):
                via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet(net));via.SetPosition(pcbnew.VECTOR2I_MM(*at))
                via.SetWidth(300000);via.SetDrill(200000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    reference_faces={pcbnew.In1_Cu if layer==pcbnew.F_Cu else pcbnew.In4_Cu}
    if tie_layer==pcbnew.In2_Cu:reference_faces.add(pcbnew.In1_Cu)
    for ref in sorted(reference_faces):
        zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet('GND'));zone.SetLayer(ref)
        zone.SetLocalClearance(200000);zone.SetMinThickness(100000);poly=zone.Outline();poly.NewOutline()
        for x,y in ((1,1),(39,1),(39,39),(1,39)):poly.Append(round(x*1e6),round(y*1e6))
        board.Add(zone)
    repair.additive._ground_refill(board)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    source.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings':{'classes':[
        dict(name='Default',track_width=.2,diff_pair_width=.2,diff_pair_gap=.2,clearance=.2)]}}))
    field._save_field_snapshot(board,source)
    pair=repair.precision.derive_coupled_pairs(str(source),board=board)[0]
    return board,source,pair


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_joint_corner_and_source_terminal_tie_shortening_preserves_ports_and_skew(tmp_path,quarter,mirror,layer):
    board,source,pair=terminal_tie_fixture(tmp_path,quarter,mirror,layer)
    ties=repair.terminal_tie_inventory(board,pair);assert len(ties)==1
    request=repair.bend_inventory(board,pair)['selected'];assert len(request)==1
    before=source.read_bytes()
    made=repair.construct_terminal_tie_rebalance(board,source,pair,request[0],ties[0])
    assert made['companion_shift_nm']>0 and len(made['retired_track_uuids'])==7
    repair.additive._ground_refill(board)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    proof=repair.receive_literal_phase(source,child,made['retired_track_uuids'],board_hint='synthetic',pair_name=pair['name'])
    assert proof['ok'] and proof['complete'],proof
    assert proof['eligible_hard90_before_after']==[1,0]
    assert proof['shortened_centerline_mm']>.2
    assert all(q['after']['skew_mm']<=q['before']['skew_mm']+1e-9 for q in proof['whole_pair_physical_samples'])
    assert source.read_bytes()==before and not proof['pair_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['points','pad','owner','net','layer','scope','frame','locked'])
def test_forged_terminal_tie_scope_or_missing_source_permission_is_refused_before_mutation(tmp_path,fault):
    board,source,pair=terminal_tie_fixture(tmp_path,mixed_member_locks=fault=='locked')
    tie=copy.deepcopy(repair.terminal_tie_inventory(board,pair)[0]);request=repair.bend_inventory(board,pair)['selected'][0]
    if fault=='points':tie['points_nm'][1][0]+=1
    elif fault=='pad':tie['endpoint_pad_uuids'][0]='invented'
    elif fault=='owner':tie['footprint_uuid']='invented'
    elif fault=='net':tie['net']=request['net']
    elif fault=='layer':tie['layer']+=2
    elif fault=='scope':tie['source_track_uuids'][0]='invented'
    elif fault=='frame':tie['frame']['depth_nm']-=1
    before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):repair.construct_terminal_tie_rebalance(board,source,pair,request,tie)
    assert field._field_snapshot_inventory(board)==before


@pytest.mark.parametrize('mixed',[False,True])
def test_automatic_source_stage_funds_joint_rebalance_and_preserves_each_members_locks(tmp_path,mixed):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    _,source,pair=terminal_tie_fixture(tmp_path,mixed_member_locks=mixed)
    before=source.read_bytes()
    result=repair.run_chamfer_stage(source,tmp_path/'stage',board_hint='synthetic',
        expected_source_sha256=force._hash(source),reporting_build=Path(native),
        allow_locked_source=mixed,max_trials=1,max_accepted=1)
    assert result['ok'] and result['complete'] and result['changed'],result
    assert result['attempts'][0]['construction']=='balanced_terminal_tie'
    proof=result['independent_whole_parent_receiving']
    assert proof['ok'] and proof['complete'] and proof['hard90_vertices_removed']==1
    assert proof['opens']==0 and not proof['new_native_fault_ids'] and source.read_bytes()==before
    child=pcbnew.LoadBoard(result['candidate'])
    assert all(t.IsLocked()==bool(mixed and t.GetNetname()==pair['p']) for t in child.GetTracks())


def test_rebalance_cannot_disconnect_a_retained_native_track_body_contact(tmp_path):
    board,source,pair=terminal_tie_fixture(tmp_path)
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet(pair['p']));via.SetPosition(pcbnew.VECTOR2I_MM(11.5,12.399))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(via)
    assert any(t.GetClass()=='PCB_TRACK' and t.GetNetname()==pair['p'] and
        t.GetEffectiveShape(pcbnew.F_Cu).Collide(via.GetEffectiveShape(pcbnew.F_Cu),0) for t in board.GetTracks())
    repair.additive._ground_refill(board);field._save_field_snapshot(board,source)
    tie=repair.terminal_tie_inventory(board,pair)[0];request=repair.bend_inventory(board,pair)['selected'][0]
    made=repair.construct_terminal_tie_rebalance(board,source,pair,request,tie)
    repair.additive._ground_refill(board);child=force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(board,child)
    proof=repair.receive_literal_phase(source,child,made['retired_track_uuids'],board_hint='synthetic',pair_name=pair['name'])
    assert not proof['ok'] and not proof['complete'] and any('side_contact_lost' in e for e in proof['errors']),proof


@pytest.mark.parametrize('bounds',[dict(max_span_nm=True),dict(max_span_nm=8000001),dict(max_steps=0),dict(timeout_s=float('nan'))])
def test_terminal_tie_discovery_has_no_unbounded_or_fuzzy_context(tmp_path,bounds):
    board,source,pair=terminal_tie_fixture(tmp_path);before=source.read_bytes()
    with pytest.raises(ValueError):repair.terminal_tie_inventory(board,pair,**bounds)
    assert source.read_bytes()==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_existing_qualified_barrels_allow_atomic_crossface_shortening_not_new_transitions(tmp_path,quarter,mirror,layer):
    board,source,pair=terminal_tie_fixture(tmp_path,quarter,mirror,layer,tie_layer=pcbnew.In2_Cu)
    tie=repair.terminal_tie_inventory(board,pair);assert len(tie)==1
    assert tie[0]['layer']==pcbnew.In2_Cu
    assert all(w['kind']=='existing_qualified_native_barrel' for w in tie[0]['endpoint_native_witnesses'])
    vias={force._uid(t):repair.additive._nodes(source)[1][force._uid(t)]
          for t in board.GetTracks() if t.GetClass()=='PCB_VIA'}
    request=repair.bend_inventory(board,pair)['selected'][0];assert request['layer']==layer
    made=repair.construct_terminal_tie_rebalance(board,source,pair,request,tie[0])
    repair.additive._ground_refill(board);child=force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(board,child)
    proof=repair.receive_literal_phase(source,child,made['retired_track_uuids'],board_hint='synthetic',pair_name=pair['name'])
    assert proof['ok'] and proof['complete'],proof
    reference=proof['exact_native_reference_deficit_receiving']
    assert reference['every_existing_source_face_independently_received']
    assert len(reference['by_signal_face'])==2 and all(q['ok'] for q in reference['by_signal_face'].values())
    assert reference['unchanged_source_crossface_terminal_tie']['exact_source_stations_rederived']
    assert not reference['pads_barrels_and_signal_faces_moved']
    assert proof['eligible_hard90_before_after']==[1,0]
    _,nodes=repair.additive._nodes(child)
    assert {u:nodes[u] for u in vias}==vias
    assert not proof['pair_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['profile','blind','wrong_net','drill','off_pad','partial_overlap','deleted'])
def test_inner_terminal_face_cannot_be_inferred_from_an_unqualified_or_absent_barrel(tmp_path,fault):
    board,source,pair=terminal_tie_fixture(tmp_path,tie_layer=pcbnew.In2_Cu)
    via=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    if fault=='profile':
        props=board.GetProperties();del props['CEC_FAB_PROFILE'];board.SetProperties(props)
    elif fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault=='wrong_net':via.SetNet(board.FindNet('GND'))
    elif fault=='drill':via.SetDrill(100000)
    elif fault=='off_pad':via.SetPosition(via.GetPosition()+pcbnew.VECTOR2I_MM(1,0))
    elif fault=='partial_overlap':via.SetPosition(via.GetPosition()+pcbnew.VECTOR2I_MM(.25,0))
    else:discard_items(board,[via])
    assert not repair.terminal_tie_inventory(board,pair)


@pytest.mark.parametrize('fault',['barrel_id','pad_id','station_kind','station_face'])
def test_forged_crossface_native_station_is_not_mutation_authority(tmp_path,fault):
    board,source,pair=terminal_tie_fixture(tmp_path,tie_layer=pcbnew.In2_Cu)
    tie=copy.deepcopy(repair.terminal_tie_inventory(board,pair)[0])
    request=repair.bend_inventory(board,pair)['selected'][0]
    if fault=='barrel_id':tie['endpoint_native_witnesses'][0]['via_uuid']='invented'
    elif fault=='pad_id':tie['endpoint_native_witnesses'][0]['pad_uuid']='invented'
    elif fault=='station_kind':tie['endpoint_native_witnesses'][0]['kind']='actual_native_pad_face'
    else:tie['layer']=pcbnew.In3_Cu
    before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):repair.construct_terminal_tie_rebalance(board,source,pair,request,tie)
    assert field._field_snapshot_inventory(board)==before


@pytest.mark.parametrize('fault',['barrel_move','barrel_drill','pad_move','new_face','new_reference_gap'])
def test_crossface_saved_receiver_rejects_station_motion_layer_changes_and_reference_loss(tmp_path,fault):
    board,source,pair=terminal_tie_fixture(tmp_path,layer=pcbnew.B_Cu,tie_layer=pcbnew.In2_Cu)
    tie=repair.terminal_tie_inventory(board,pair)[0];request=repair.bend_inventory(board,pair)['selected'][0]
    made=repair.construct_terminal_tie_rebalance(board,source,pair,request,tie)
    via=next(t for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    if fault=='barrel_move':via.SetPosition(via.GetPosition()+pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='barrel_drill':via.SetDrill(250000)
    elif fault=='pad_move':
        pad=next(p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==pair['p'])
        pad.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='new_face':
        t=next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==pair['p'])
        t.SetLayer(pcbnew.F_Cu)
    else:
        zone=next(z for z in board.Zones() if z.IsOnLayer(pcbnew.In1_Cu));zone.Outline().RemoveAllContours()
        zone.Outline().NewOutline()
        for x,y in ((1,1),(2,1),(2,2),(1,2)):zone.Outline().Append(round(x*1e6),round(y*1e6))
    repair.additive._ground_refill(board);child=force._copy_family(source,tmp_path/'candidate')
    field._save_field_snapshot(board,child)
    proof=repair.receive_literal_phase(source,child,made['retired_track_uuids'],board_hint='synthetic',pair_name=pair['name'])
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


@pytest.mark.parametrize('mixed',[False,True])
def test_automatic_crossface_rebalance_preserves_barrels_and_independent_whole_parent_proofs(tmp_path,mixed):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    _,source,pair=terminal_tie_fixture(tmp_path,layer=pcbnew.B_Cu,tie_layer=pcbnew.In2_Cu,mixed_member_locks=mixed)
    result=repair.run_chamfer_stage(source,tmp_path/'stage',board_hint='synthetic',expected_source_sha256=force._hash(source),
        reporting_build=Path(native),allow_locked_source=mixed,max_trials=1,max_accepted=1)
    assert result['ok'] and result['complete'] and result['changed'],result
    whole=result['independent_whole_parent_receiving'];assert whole['ok'] and whole['complete']
    assert whole['hard90_vertices_removed']==1 and whole['opens']==0 and not whole['new_native_fault_ids']
    assert result['attempts'][0]['construction']=='balanced_terminal_tie'

"""Complete routing proposals never inherit authority from ground-only fit."""
import copy
import json
import time

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_escape_pose_frontier as frontier
import cec_cell_row_rebuild as row
import cec_force_current as force
from cec_native_items import create_empty_board

from test_cell_escape_replan import fixture
from test_escape_pose_frontier import two_follower_fixture


def native_source(tmp_path,monkeypatch,*,turn=0,planes=True,source_class_width_mm=.2):
    board,poses,owner,cap=fixture(monkeypatch,prefix='names_without_board_authority')
    cap.SetPosition(pcbnew.VECTOR2I_MM(13,9))
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal'
    board.SetProperties(props);board.GetDesignSettings().m_MinClearance=200000
    # Real retained source targets, not synthetic already-connected promises.
    def track(net,a,b):
        item=pcbnew.PCB_TRACK(board);item.SetNet(board.FindNet(net));item.SetLayer(pcbnew.F_Cu)
        item.SetStart(pcbnew.VECTOR2I_MM(*a));item.SetEnd(pcbnew.VECTOR2I_MM(*b))
        item.SetWidth(200000);board.Add(item);return item
    def target(net,at):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('external_'+net);board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet(net))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        pad.SetPosition(pcbnew.VECTOR2I_MM(*at));pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad)
    paths={'OUT':[(9,9),(8,9),(8,6),(6,6)],
           'INPUT_P':[(9,11),(8,11),(8,14),(6,14)],
           'INPUT_N':[(11,11),(14,11),(14,14),(16,14)],
           'RAIL':[(11,9),(12.5,9),(12.5,7),(18,7)],
           'GND':[(9,10),(13.5,10),(13.5,9)]}
    for net,points in paths.items():
        for a,b in zip(points,points[1:]):track(net,a,b)
        if net!='GND':target(net,points[-1])
    if planes:
        zone=pcbnew.ZONE(board);zone.SetLayer(pcbnew.In1_Cu);zone.SetNet(board.FindNet('GND'))
        shape=pcbnew.SHAPE_POLY_SET();i=shape.NewOutline()
        for x,y in ((0,0),(30,0),(30,30),(0,30)):
            shape.Outline(i).Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
        zone.Outline().Append(shape);zone.SetFilledPolysList(pcbnew.In1_Cu,shape)
        zone.SetIsFilled(True);board.Add(zone)
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(13.5,10))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetNet(board.FindNet('GND'));board.Add(via)
    if turn:
        origin=pcbnew.VECTOR2I_MM(15,15);angle=pcbnew.EDA_ANGLE(90*turn,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks(),*board.Zones()]:item.Rotate(origin,angle)
    poses={fp.GetReference():[fp.GetPosition().x/1e6+.5,fp.GetPosition().y/1e6+.5,
        fp.GetOrientationDegrees()] for fp in (owner,cap)}
    # Capture actual scratch-board minima rather than relying on SaveBoard
    # to emit a project sidecar (that side effect differs across KiCad builds).
    settings=board.GetDesignSettings()
    source_rules={key:pcbnew.ToMM(getattr(settings,member)) for key,member in (
        ('min_clearance','m_MinClearance'),('min_track_width','m_TrackMinWidth'),
        ('min_via_diameter','m_ViasMinSize'),('min_through_hole_diameter','m_MinThroughDrill'),
        ('min_hole_to_hole','m_HoleToHoleMin'),('min_hole_clearance','m_HoleClearance'),
        ('min_copper_edge_clearance','m_CopperEdgeClearance'),
        ('min_via_annular_width','m_ViasMinAnnularWidth'))}
    # SaveBoard caches a dummy project. Use a seed path, restore the borrowed
    # Default, then load a distinct final path with its complete sidecar first.
    klass=board.GetDesignSettings().m_NetSettings.GetDefaultNetclass()
    borrowed=(klass.GetTrackWidth(),klass.GetClearance(),klass.GetViaDiameter(),klass.GetViaDrill())
    try:
        klass.SetTrackWidth(round(source_class_width_mm*1e6))
        klass.SetClearance(200000);klass.SetViaDiameter(600000);klass.SetViaDrill(300000)
        seed=tmp_path/'seed-native-source.kicad_pcb'
        pcbnew.SaveBoard(str(seed),board)
    finally:
        # Unattached BOARD instances borrow this shared Default object.  The
        # saved/reloaded project owns its own class, but the seed must never
        # pollute later unrelated fixtures in this pytest worker.
        klass.SetTrackWidth(borrowed[0]);klass.SetClearance(borrowed[1])
        klass.SetViaDiameter(borrowed[2]);klass.SetViaDrill(borrowed[3])
    path=tmp_path/'saved-native-source.kicad_pcb'
    project_path=seed.with_suffix('.kicad_pro')
    project=json.loads(project_path.read_text()) if project_path.is_file() else {
        'board':{'design_settings':{'rules':source_rules}},
        'net_settings':{'classes':[{'name':'Default'}]}}
    default=next(entry for entry in project['net_settings']['classes']if entry['name']=='Default')
    default.update(track_width=source_class_width_mm,clearance=.2,via_diameter=.6,via_drill=.3)
    project['net_settings']['netclass_assignments']={}
    project['net_settings']['netclass_patterns']=[]
    path.with_suffix('.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')
    path.write_bytes(seed.read_bytes())
    parent=pcbnew.LoadBoard(str(path));proposal=escape.prepare(parent,poses,board_hint='opaque')
    private=pcbnew.LoadBoard(str(path));escape.apply_private(private,proposal)
    expected=dict(width=round(source_class_width_mm*1e6),clearance=200000,
        via_dia=.6,via_drill=.3)
    assert escape.cell._netclass(parent,'RAIL')==expected
    assert escape.cell._netclass(private,'RAIL')==expected
    return path,parent,private,proposal


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('source_class_width_mm',[.2,.5])
def test_saved_source_project_rules_not_uuid_or_process_defaults_control_launch(
        tmp_path,monkeypatch,turn,source_class_width_mm):
    def unrelated_defaults():
        unrelated=create_empty_board()
        default=unrelated.GetDesignSettings().m_NetSettings.GetDefaultNetclass()
        return(default.GetTrackWidth(),default.GetClearance(),
            default.GetViaDiameter(),default.GetViaDrill())
    defaults_before=unrelated_defaults()
    path,parent,board,proposal=native_source(tmp_path,monkeypatch,turn=turn,
        source_class_width_mm=source_class_width_mm)
    assert unrelated_defaults()==defaults_before
    # Rotate the displacement as well as Source geometry so the physical
    # barrel/endpoint counterexample is identical in every quarter turn.
    dx,dy=((.5,.5),(.5,-.5),(-.5,-.5),(-.5,.5))[turn]
    poses={ref:[parent.FindFootprintByReference(ref).GetPosition().x/1e6+dx,
        parent.FindFootprintByReference(ref).GetPosition().y/1e6+dy,
        parent.FindFootprintByReference(ref).GetOrientationDegrees()]
        for ref in proposal['poses']}
    proposal=escape.prepare(parent,poses,board_hint='opaque')
    board=pcbnew.LoadBoard(str(path));escape.apply_private(board,proposal)
    family={p:force._hash(p) for p in tmp_path.iterdir() if p.is_file()}
    before=row._source_binding(board)
    via=next(t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA')
    assert via.GetWidth()==600000 and via.GetDrillValue()==300000
    assert force._uid(via) not in proposal['retired_track_uuids']
    assert any(force._uid(t)==force._uid(via) for t in board.GetTracks())
    assert all(t.GetWidth()==200000 for t in parent.GetTracks()
        if t.GetClass()=='PCB_TRACK')
    # This is a real saved-rule negative: the retained foreign Ground barrel
    # blocks the .5 mm RAIL launch (gap about .1571 mm < .2 mm).  It is not a
    # receiver override or an assertion that this pose passed native DRC.
    proof=escape.complete_connection_screen(path,board,proposal,
        board_hint='opaque',timeout_s=10.)
    if source_class_width_mm==.5:
        assert not proof['complete'] and not proof['routing_admitted']
        assert proof['empty_obligations']
        assert any(proof['requests'][key]['net']=='RAIL'
            for key in proof['empty_obligations'])
    else:
        assert proof['complete'],proof
        assert proof['selection']['all_obligations_present']
    assert row._source_binding(board)==before
    assert {p:force._hash(p) for p in family}==family
    assert unrelated_defaults()==defaults_before


@pytest.mark.parametrize('turn',range(4))
def test_complete_native_selection_restores_moving_identities_and_rolls_back(tmp_path,monkeypatch,turn):
    path,parent,board,proposal=native_source(tmp_path,monkeypatch,turn=turn)
    source_hash=force._hash(path);source=row._source_binding(parent);draft=row._source_binding(board)
    proof=escape.complete_connection_screen(path,board,proposal,board_hint='opaque',timeout_s=10.)
    assert proof['complete'],proof
    assert proof['selection']['all_obligations_present']
    assert proof['complete_selection_partition_trials'][-1]==dict(lost_source_partitions=0,
        unreceived_native_terminal_obligations=[])
    assert not proof['routing_admitted'] and not proof['release_authority']
    assert not proof['placement_authority'] and not proof['kelvin_qualified']
    assert row._source_binding(board)==draft and row._source_binding(parent)==source
    assert force._hash(path)==source_hash
    # The same untouched private draft can independently be screened again.
    again=escape.complete_connection_screen(path,board,proposal,board_hint='opaque')
    assert again['complete'] and row._source_binding(board)==draft


@pytest.mark.parametrize('turn',range(4))
def test_explicit_independent_connection_leases_still_receive_every_native_obligation(tmp_path,monkeypatch,turn):
    path,parent,board,proposal=native_source(tmp_path,monkeypatch,turn=turn)
    before=row._source_binding(board)
    proof=escape.complete_connection_screen(path,board,proposal,board_hint='opaque',
        timeout_s=2.,per_obligation_leases=True,measurement_bridges=True)
    assert proof['complete'],proof
    assert proof['packet']['all_obligations_present']
    assert proof['independent_stage_max_seconds']==2.
    preparation=proof.get('source_ground_expectation_preparation',{})
    # This report subtracts two monotonic-clock floats. Preserve the exact
    # independent work budget without demanding bit-exact float subtraction.
    assert proof['total_work_bound_seconds']==pytest.approx(
        2.*(proof['obligation_count']+2)+preparation.get('aggregate_deadline_extension_seconds',0.),
        rel=0.,abs=1e-9)
    if preparation:
        assert preparation['stage_max_seconds']==2.
        assert preparation['additional_bounded_stages']==1
    assert proof['packet']['total_menu_work_bound_seconds']==2.*proof['obligation_count']
    assert proof['packet']['per_obligation_leases']
    assert not proof['routing_admitted'] and row._source_binding(board)==before


def test_legal_barrels_without_saved_ground_material_are_not_received(tmp_path,monkeypatch):
    path,parent,board,proposal=native_source(tmp_path,monkeypatch,planes=False)
    draft=row._source_binding(board)
    # This deliberate rejection consumes its entire finite search lease.
    # Keep fixture + actual native trial + rollback within the 10 s command
    # budget; do not weaken the missing-material or rollback assertions.
    proof=escape.complete_connection_screen(path,board,proposal,board_hint='opaque',timeout_s=4.)
    assert not proof['complete'] and not proof['no_path_proof']
    assert proof['complete_selection_partition_trials']
    assert any(row['unreceived_native_terminal_obligations']
        for row in proof['complete_selection_partition_trials'])
    assert row._source_binding(board)==draft


@pytest.mark.parametrize('fault',['forged_plan','extra_copper','isolated_input'])
def test_forged_or_underplanned_cell_is_not_promoted(tmp_path,monkeypatch,fault):
    path,parent,board,proposal=native_source(tmp_path,monkeypatch)
    if fault=='forged_plan':proposal=copy.deepcopy(proposal);proposal['retired_track_uuids'].append('made-up')
    elif fault=='extra_copper':
        item=pcbnew.PCB_TRACK(board);item.SetStart(pcbnew.VECTOR2I_MM(25,25))
        item.SetEnd(pcbnew.VECTOR2I_MM(26,25));item.SetWidth(200000)
        item.SetNet(board.FindNet('OUT'));board.Add(item)
    else:
        owner=next(iter(proposal['device_contracts']))
        pad=parent.FindFootprintByReference(owner).FindPadByNumber('3')
        isolated=pcbnew.NETINFO_ITEM(parent,'declared_but_unrouted_scalar');parent.Add(isolated)
        pad.SetNet(isolated);pcbnew.SaveBoard(str(path),parent)
        poses=proposal['poses'];proposal=escape.prepare(parent,poses,board_hint='opaque')
        board=pcbnew.LoadBoard(str(path));escape.apply_private(board,proposal)
    draft=row._source_binding(board);digest=force._hash(path)
    proof=escape.complete_connection_screen(path,board,proposal,board_hint='opaque')
    assert not proof['complete'] and not proof['routing_admitted']
    assert proof['errors'] and row._source_binding(board)==draft and force._hash(path)==digest
    if fault=='isolated_input':assert proof['inherited_unplanned_terminals']


def test_native_trial_exception_cannot_leak_partial_operations(tmp_path,monkeypatch):
    path,parent,board,proposal=native_source(tmp_path,monkeypatch)
    before=row._source_binding(board);actual=escape._native_ops;calls=[]
    def fail_after_first(*values,**options):
        made=actual(*values,**options);calls.append(made)
        raise RuntimeError('injected partial native construction')
    monkeypatch.setattr(escape,'_native_ops',fail_after_first)
    proof=escape.complete_connection_screen(path,board,proposal,board_hint='opaque')
    assert not proof['complete']
    assert any('partial native construction' in error for error in proof['selection']['errors'])
    assert calls and row._source_binding(board)==before


@pytest.mark.parametrize('fault', ['regressed', 'unknown'])
def test_partition_and_plane_connectivity_cannot_waive_physical_ground_return_receiving(tmp_path,monkeypatch,fault):
    import cec_ground_return_preservation as preservation
    path,parent,board,proposal=native_source(tmp_path,monkeypatch)
    before=row._source_binding(board);calls=[]
    def refuse(*values,**options):
        calls.append(options)
        return dict(ok=False,complete=fault=='regressed',errors=[fault],
            regressed_terminals=[dict(source_return_mm=.2,candidate_return_mm=2.)]
                if fault=='regressed' else [],release_authority=False)
    monkeypatch.setattr(preservation,'receive',refuse)
    proof=escape.complete_connection_screen(path,board,proposal,board_hint='opaque',timeout_s=4.)
    assert calls and not proof['complete'] and not proof['routing_admitted']
    assert proof['complete_selection_ground_return_trials']
    assert all(not trial['ok'] for trial in proof['complete_selection_ground_return_trials'])
    assert row._source_binding(board)==before


def test_ground_only_success_does_not_stop_complete_pose_frontier(tmp_path,monkeypatch):
    board,source,selected,caps,path=two_follower_fixture(tmp_path)
    owner=next(iter(selected.values()))['owner']
    monkeypatch.setattr(frontier.force,'_family',lambda *a:force._hash(path))
    monkeypatch.setattr(frontier.force,'_code_identity',lambda:'fixed_test_code_epoch')
    monkeypatch.setattr(frontier.constraints,'_device_bypass_assignment',lambda *a,**kw:dict(
        assigned={i:dict(cap_ref=ref,requirement=dict(ref=owner)) for i,ref in enumerate(selected)}))
    monkeypatch.setattr(frontier.escape,'prepare',lambda *a,**kw:dict(
        stationary_device_owners=[],selected_bypasses=selected))
    monkeypatch.setattr(frontier.escape,'apply_private',lambda *a,**kw:None)
    monkeypatch.setattr(frontier,'courtyard_screen',lambda *a,**kw:dict(ok=True))
    monkeypatch.setattr(frontier,'surface_screen',lambda *a,**kw:dict(ok=True))
    monkeypatch.setattr(frontier,'ground_screen',lambda *a,**kw:dict(ok=True))
    visited=[]
    def complete(*a,**kw):
        visited.append(kw);return dict(complete=len(visited)==2)
    monkeypatch.setattr(frontier.escape,'complete_connection_screen',complete)
    proof=frontier.frontier(path,[owner],board_hint='opaque',deltas_mm=[(.1,0),(.2,0)],
        rotations=(0,),max_results=1,complete_escapes=True,include_power_layer=True)
    assert len(visited)==2 and len(proof['poses'])==1
    assert proof['history'][0]['reason']=='complete_cell_connections_not_constructed'
    assert proof['poses'][0]['every_connection_proposed']
    assert not proof['poses'][0]['remaining_connection_obligations_required']
    assert not proof['routing_admitted'] and not proof['no_path_proof']


@pytest.mark.parametrize('options',[{'timeout_s':11},{'measurement_bridges':1},
    {'include_power_layer':'yes'},{'per_obligation_leases':1},{'require_trace_craft_nonregression':1}])
def test_complete_connection_work_scope_is_explicitly_bounded(tmp_path,monkeypatch,options):
    path,parent,board,proposal=native_source(tmp_path,monkeypatch)
    before=row._source_binding(board)
    with pytest.raises(ValueError):
        escape.complete_connection_screen(path,board,proposal,board_hint='opaque',**options)
    assert row._source_binding(board)==before


@pytest.mark.parametrize('always_bad',[False,True])
def test_requested_upstream_craft_check_retries_but_never_waives_new_backtracking(tmp_path,monkeypatch,always_bad):
    import cec_route_quality as quality
    path,parent,board,proposal=native_source(tmp_path,monkeypatch)
    binding=row._source_binding(board);calls=[]
    def analyze(b):
        if b is board:calls.append(True)
        bad=b is board and (always_bad or len(calls)==1)
        return dict(issue_count=int(bad),non_octilinear_count=0)
    monkeypatch.setattr(quality,'analyze_board',analyze)
    # The always-bad case exhausts the aggregate of its independent leases.
    # A short per-obligation lease still must produce a real first craft
    # trial and, in the positive case, a distinct accepted retry.
    result=escape.complete_connection_screen(path,board,proposal,board_hint='opaque',timeout_s=.6,
        per_obligation_leases=True,require_trace_craft_nonregression=True)
    assert result['upstream_trace_craft_nonregression_requested']
    assert result['complete_selection_trace_craft_trials'][0]['candidate_issues']==1
    assert result['complete'] is not always_bad,result
    assert row._source_binding(board)==binding and not result['routing_admitted']


@pytest.mark.parametrize('options',[{'complete_escapes':1},
    {'include_power_layer':True},{'complete_escapes':True,'include_power_layer':1}])
def test_complete_pose_mode_cannot_be_enabled_by_truthy_or_unscoped_flags(tmp_path,monkeypatch,options):
    board,source,selected,caps,path=two_follower_fixture(tmp_path)
    digest=force._hash(path);owner=next(iter(selected.values()))['owner']
    with pytest.raises(ValueError,match='bounded_escape_pose_portfolio_required'):
        frontier.frontier(path,[owner],board_hint='opaque',deltas_mm=[(.1,0)],**options)
    assert force._hash(path)==digest

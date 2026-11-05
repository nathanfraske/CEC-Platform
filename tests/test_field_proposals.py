"""Read-only field admission before ordinary native route emission."""
from pathlib import Path

import pcbnew
import pytest

import cec_field_coupling as field
import cec_fr as fr
from test_lastmile import _board
import test_field_coupling as field_fixtures


def add_net(board, name):
    if name not in board.GetNetsByName():
        board.Add(pcbnew.NETINFO_ITEM(board, name))


def track(board, name, a, b, layer=pcbnew.F_Cu, width=.2):
    add_net(board, name)
    item=pcbnew.PCB_TRACK(board);item.SetNetCode(board.GetNetcodeFromNetname(name))
    item.SetLayer(layer);item.SetWidth(pcbnew.FromMM(width))
    item.SetStart(pcbnew.VECTOR2I_MM(*a));item.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(item)
    return item


def proposal(name, a, b, layer=pcbnew.F_Cu, width=.2):
    return dict(net=name,layer=int(layer),start_nm=[round(x*1e6) for x in a],
        end_nm=[round(x*1e6) for x in b],width_nm=round(width*1e6))


def signature(board):
    return [(t.m_Uuid.AsString(),t.GetClass(),int(t.GetLayer()),t.GetNetname(),
             list(t.GetStart()),list(t.GetEnd()),t.GetWidth()) for t in board.GetTracks()]


@pytest.mark.parametrize('angle,prefix',[(0,'/a/'),(90,'/renamed/'),(180,'/nested/x/'),(270,'/fourth/')])
def test_rotated_renamed_role_proposal_matches_actual_policy(angle,prefix):
    import math
    board=_board([],edge=(0,0,40,40))
    def rotate(point):
        a=math.radians(angle);x,y=point[0]-20,point[1]-20
        return (round(20+x*math.cos(a)-y*math.sin(a),6),round(20+x*math.sin(a)+y*math.cos(a),6))
    victim=prefix+'ADC_INPUT';aggressor=prefix+'GATE'
    track(board,victim,rotate((10,20.8)),rotate((25,20.8)))
    add_net(board,aggressor)
    p=proposal(aggressor,rotate((10,20)),rotate((25,20)))
    before=signature(board)
    result=field.assess_proposed_tracks(board,[p])
    assert result['complete'] and result['ok'] is False
    assert result['new_blockers'][0]['aggressor']==aggressor
    assert result['new_blockers'][0]['victim']==victim
    assert signature(board)==before and result['board_mutated'] is False
    track(board,aggressor,rotate((10,20)),rotate((25,20)))
    actual=field.field_coupling_summary('',board=board)
    assert actual['blocking_count']==len(result['new_blockers'])==1
    for key in ('angle_deg','parallel_overlap_mm','edge_gap_mm','interaction_reach_mm','reason','shield'):
        assert actual['interactions'][0][key]==result['interactions'][0][key]


def test_neutral_name_uses_real_netclass_role_without_inference():
    board=_board([],edge=(0,0,30,30));track(board,'/ADC', (5,6),(15,6))
    add_net(board,'/RENAMED');p=proposal('/RENAMED',(5,5.2),(15,5.2))
    neutral=field.assess_proposed_tracks(board,[p])
    assert neutral['ok'] is True and not neutral['interactions']
    classified=field.assess_proposed_tracks(board,[p],netclass_resolver=lambda n:{'name':'Clock' if n=='/RENAMED' else 'Default'})
    assert classified['ok'] is False
    assert classified['classified_nets']['/RENAMED']['netclass']=='Clock'


def test_inherited_fault_is_not_global_requalification_or_new_fault():
    board=_board([],edge=(0,0,30,30))
    track(board,'/PWM',(5,5),(15,5));track(board,'/ADC',(5,5.8),(15,5.8))
    add_net(board,'/CONTROL')
    assert not field.field_coupling_summary('',board=board)['ok']
    result=field.assess_proposed_tracks(board,[proposal('/CONTROL',(5,12),(15,12))])
    assert result['ok'] is True and result['inherited_interactions_requalified'] is False
    assert result['release_authority'] is False


def test_proposed_to_proposed_interaction_is_not_omitted():
    board=_board([],edge=(0,0,30,30));add_net(board,'/PWM');add_net(board,'/ADC')
    result=field.assess_proposed_tracks(board,[proposal('/PWM',(5,5),(15,5)),proposal('/ADC',(5,5.8),(15,5.8))])
    assert result['ok'] is False and len(result['new_blockers'])==1
    assert list(board.GetTracks())==[]


def test_oblique_retained_projection_cannot_pass_only_because_of_uuid_order():
    board=_board([],edge=(0,0,30,30));track(board,'/ADC',(1,5),(11,5));add_net(board,'/PWM')
    p=proposal('/PWM',(6,5.5),(6.994656,5.675385))
    # The old long axis sees <1 mm; the proposed short axis sees >1 mm.
    # Both are evaluated by the same unmodified final policy depending on
    # native item ordering, so preflight conservatively must reject either.
    result=field.assess_proposed_tracks(board,[p])
    assert result['ok'] is False
    assert result['new_blockers'][0]['parallel_overlap_mm']>1


def native_ground_board(tmp_path):
    path=field_fixtures.FieldCouplingTest()._board(str(tmp_path),[
        ('/ADC','In2.Cu',(4,8.2),(20,8.2)),('/PWM','F.Cu',(2,2),(2.1,2))])
    return Path(path),pcbnew.LoadBoard(path)


def test_actual_filled_ground_allows_new_cross_layer_run_not_same_layer(tmp_path):
    path,board=native_ground_board(tmp_path);before=path.read_bytes()
    good=field.assess_proposed_tracks(board,[proposal('/PWM',(4,8),(20,8))],board_path=path)
    assert good['ok'] is True
    assert good['interactions'][0]['shield']['coverage_pct']>=95
    same=field.assess_proposed_tracks(board,[proposal('/PWM',(4,8),(20,8),pcbnew.In2_Cu)],board_path=path)
    assert same['ok'] is False and same['interactions'][0]['shield']['reason']=='same routing layer'
    assert path.read_bytes()==before


def test_no_ground_fill_does_not_inherit_stackup_shield_credit(tmp_path):
    path,board=native_ground_board(tmp_path)
    for zone in board.Zones():zone.UnFill()
    result=field.assess_proposed_tracks(board,[proposal('/PWM',(4,8),(20,8))],board_path=path)
    assert result['ok'] is False
    assert result['new_blockers'][0]['shield']['coverage_pct']==0


@pytest.mark.parametrize('via,plane',[(True,False),(False,True)])
def test_unproved_refill_transition_and_ground_cut_are_unknown(tmp_path,via,plane):
    path,board=native_ground_board(tmp_path)
    result=field.assess_proposed_tracks(board,[proposal('/PWM',(4,8),(20,8),pcbnew.In1_Cu if plane else pcbnew.F_Cu)],
        board_path=path,proposed_vias=[{'at_nm':[4000000,8000000]}] if via else ())
    assert result['ok'] is None and result['complete'] is False
    assert 'refill' in result['reason'] and result['no_path_proof'] is False


def test_perpendicular_crossing_without_plane_uses_unchanged_angle_policy():
    board=_board([],edge=(0,0,30,30));track(board,'/ADC',(10,3),(10,17),pcbnew.In2_Cu)
    add_net(board,'/PWM')
    result=field.assess_proposed_tracks(board,[proposal('/PWM',(5,10),(15,10))])
    assert result['ok'] is True
    assert result['interactions'][0]['angle_deg']==90
    assert result['interactions'][0]['shield']['shielded'] is False


@pytest.mark.parametrize('kwargs,reason',[
    ({'deadline':0},'deadline'),({'max_board_items':1},'items_budget'),
    ({'max_pair_checks':1},'pairs_budget'),({'max_samples':1},'samples_budget'),
    ({'max_interactions':1},'interactions_budget'),
    ({'max_proposed':1},'count_budget'),({'max_samples':True},'invalid_max_samples')])
def test_budgets_refuse_unknown_without_native_mutation(kwargs,reason):
    board=_board([],edge=(0,0,30,30));track(board,'/ADC',(5,6),(15,6));track(board,'/TEMP',(5,7),(15,7))
    add_net(board,'/PWM');before=signature(board)
    result=field.assess_proposed_tracks(board,[proposal('/PWM',(5,5.8),(15,5.8)),proposal('/PWM',(5,15),(15,15))],**kwargs)
    assert result['ok'] is None and reason in result['reason'],result
    assert result['complete'] is False and result['no_path_proof'] is False
    assert signature(board)==before


@pytest.mark.parametrize('update',[{'net':'/ABSENT'},{'width_nm':0},{'width_nm':True},
    {'layer':999},{'start_nm':[True,5]},{'end_nm':[5000000,5000000]}])
def test_invalid_geometry_and_missing_authority_do_not_pass(update):
    board=_board([],edge=(0,0,30,30));add_net(board,'/PWM')
    p=proposal('/PWM',(5,5),(15,5));p.update(update)
    result=field.assess_proposed_tracks(board,[p])
    assert result['ok'] is None and not result['complete']


def test_related_native_curve_is_unknown_not_silently_ignored():
    board=_board([],edge=(0,0,30,30));add_net(board,'/ADC');add_net(board,'/PWM')
    arc=pcbnew.PCB_ARC(board);arc.SetNetCode(board.GetNetcodeFromNetname('/ADC'))
    arc.SetLayer(pcbnew.F_Cu);arc.SetWidth(200000)
    arc.SetStart(pcbnew.VECTOR2I_MM(5,6));arc.SetMid(pcbnew.VECTOR2I_MM(10,8));arc.SetEnd(pcbnew.VECTOR2I_MM(15,6));board.Add(arc)
    result=field.assess_proposed_tracks(board,[proposal('/PWM',(5,5),(15,5))])
    assert result['ok'] is None and result['reason']=='related_native_curved_copper_unsupported'


def test_path_validator_keeps_safe_legacy_and_searches_alternative():
    board=_board([(5,5,'/CONTROL'),(10,6,'/CONTROL')],edge=(0,0,20,20))
    start=pcbnew.VECTOR2I_MM(5,5);end=pcbnew.VECTOR2I_MM(10,6)
    args=(board,start,end,200000,pcbnew.F_Cu,200000,board.GetNetcodeFromNetname('/CONTROL'),lambda *a:True)
    old=fr._guarded_lastmile_legs(*args,allow_maze=False)
    keep=fr._guarded_lastmile_legs(*args,allow_maze=False,path_validator=lambda plan:True)
    assert [(list(a),list(b)) for a,b in old]==[(list(a),list(b)) for a,b in keep]
    tested=[]
    def validator(plan):
        tested.append([(list(a),list(b)) for a,b,w in plan]);return len(tested)>1
    alternative=fr._guarded_lastmile_legs(*args,allow_maze=False,path_validator=validator)
    assert alternative is not None and len(tested)==2 and tested[0]!=tested[1]


def test_path_validator_requires_literal_true_and_checks_maze(monkeypatch):
    board=_board([(5,5,'/CONTROL'),(10,5,'/CONTROL')],edge=(0,0,20,20))
    start=pcbnew.VECTOR2I_MM(5,5);end=pcbnew.VECTOR2I_MM(10,5);calls=[]
    monkeypatch.setattr(fr,'_maze_lastmile_legs',lambda *a,**k:[(start,end,200000)])
    result=fr._guarded_lastmile_legs(board,start,end,200000,pcbnew.F_Cu,200000,
        board.GetNetcodeFromNetname('/CONTROL'),lambda *a:True,
        path_validator=lambda plan:calls.append(plan) or {'ok':True})
    assert result is None and len(calls)>1


def test_ordinary_integration_rejects_direct_parallel_and_commits_safe_detour():
    board=_board([(5,5,'/GATE'),(10,5,'/GATE')],edge=(0,0,20,20))
    victim=track(board,'/ADC',(5,5.9),(10,5.9));old=signature(board)
    board.BuildConnectivity()
    report=fr.synthesize_lastmile(board,include_nets=['/GATE'],min_w=.2,clearance=.2,
        max_mm=8,cap=1,maze_max_mm=0,attempts_per_pair=1,wall_timeout_s=5,
        netclass_resolver=lambda n:{'name':'Default','track_width':.2,'clearance':.2},field_guard=True)
    assert report['closed']==1,report
    # A conclusive search preflight may reject the unsafe straight segment
    # before the expensive complete proposal receiver is invoked. Either
    # phase must demonstrate rejection, and final material must still pass.
    early=sum(row['conclusive_same_layer_refusals']
              for row in report['field_search_preflight'])
    assert report['field_guard']['refused'] + early >= 1
    assert report['field_guard']['passed'] >= 1
    assert field.field_coupling_summary('',board=board)['ok']
    assert [row for row in signature(board) if row[0]==victim.m_Uuid.AsString()]==old
    assert all(t.GetWidth()==200000 for t in board.GetTracks())


def test_ordinary_integration_unknown_never_emits(monkeypatch):
    board=_board([(5,5,'/CONTROL'),(8,5,'/CONTROL')],edge=(0,0,15,15))
    monkeypatch.setattr(field,'assess_proposed_tracks',lambda *a,**k:dict(ok=None,complete=False,reason='test_missing_native_proof'))
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *a,**k:None)
    report=fr.synthesize_lastmile(board,include_nets=['/CONTROL'],min_w=.2,max_mm=5,cap=1,
        maze_max_mm=0,wall_timeout_s=3,field_guard=True,
        netclass_resolver=lambda n:{'track_width':.2,'clearance':.2})
    assert report['closed']==0 and report['field_guard']['unknown']>0
    assert list(board.GetTracks())==[]


def test_actual_final_completion_dispatch_enables_field_guard():
    # Guard wiring belongs to the real importer, not only a private task
    # harness. This assertion supplements native synthesize_lastmile tests.
    import inspect
    text=inspect.getsource(fr.import_ses)
    final=text[text.index('_final_lm = synthesize_lastmile('):]
    assert 'field_guard=True' in final[:1500]


def test_unsupported_new_via_portfolio_is_pruned_before_bridge_search(monkeypatch):
    board=_board([(5,5,'/CONTROL'),(8,5,'/CONTROL')],edge=(0,0,15,15))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
            pad.SetDrillSize(pcbnew.VECTOR2I(0,0))
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *a,**k:None)
    planar_capabilities=field.proposal_capabilities()
    monkeypatch.setattr(field,'proposal_capabilities',lambda **kwargs:planar_capabilities)
    bridge_calls=[]
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *a,**k:bridge_calls.append(a) or None)
    board.BuildConnectivity()
    before=signature(board)
    result=fr.synthesize_lastmile(board,include_nets=['/CONTROL'],max_mm=5,cap=1,
        attempts_per_pair=2,maze_max_mm=0,field_guard=True,
        netclass_resolver=lambda n:{'track_width':.2,'clearance':.2})
    assert result['closed']==0 and not bridge_calls
    assert result['field_guard']['portfolio_preflight_skipped']>0
    assert result['field_guard']['assessed']==0
    assert not result['field_guard']['capabilities']['new_vias']
    assert signature(board)==before


def test_existing_through_hole_barrels_are_not_pruned_as_new_vias(monkeypatch):
    board=_board([(5,5,'/CONTROL'),(8,5,'/CONTROL')],edge=(0,0,15,15))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetDrillSize(pcbnew.VECTOR2I(300000,300000))
            pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *a,**k:None)
    bridge_calls=[]
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *a,**k:bridge_calls.append(a) or None)
    board.BuildConnectivity()
    result=fr.synthesize_lastmile(board,include_nets=['/CONTROL'],max_mm=5,cap=1,
        attempts_per_pair=1,maze_max_mm=0,field_guard=True,
        netclass_resolver=lambda n:{'track_width':.2,'clearance':.2})
    assert bridge_calls and result['field_guard']['portfolio_preflight_skipped']==0
    assert result['closed']==0

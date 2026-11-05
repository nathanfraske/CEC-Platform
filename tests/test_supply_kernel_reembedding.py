"""Bounded, opaque-board reembedding; a thin pickup is not a current waiver."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_supply_kernel_reembedding as repair
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


def case(tmp_path,monkeypatch,quarter=0,back=False):
    net='/UNFAMILIAR/POWER';board=_board([(5,5,net),(15,15,net)],edge=(-25,-25,40,40))
    board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for fp in board.GetFootprints():
        for pad in fp.Pads():pad.SetSize(pcbnew.VECTOR2I_MM(2,2));pad.SetPadName('1')
    def barrel(xy,diameter=1.4):
        v=pcbnew.PCB_VIA(board);v.SetNet(board.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        v.SetWidth(round(diameter*1e6));v.SetDrill(400000 if diameter>1 else 300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);board.Add(v);return v
    roots=[barrel((5,5)),barrel((15,15))];pickup=barrel((9,5),.8)
    group=pcbnew.PCB_GROUP(board);group.SetName('opaque component attachment');board.Add(group);group.AddItem(roots[0])
    old=[track(board,net,(5,5),(9,5),width=.2),
        track(board,net,(9,5),(9,15),width=.2),track(board,net,(9,15),(15,15),width=.2)]
    for t in old[1:]:t.SetLayer(pcbnew.B_Cu)
    for t in old:t.SetLocked(True)
    ghosts=[]
    for xy in ((5,5),(5,12),(8,15),(15,15)):
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(*xy));t.SetEnd(t.GetStart());ghosts.append(t)
    for item in [*board.GetFootprints(),*board.GetTracks(),*board.GetDrawings(),*ghosts]:
        if quarter:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    contract=dict(net=net,required_by_layer_mm={'F.Cu':.5,'B.Cu':.5},routing_layers=['F.Cu','B.Cu'],
        current_authority=dict(amps=1.,geometry_margin=1.25,margin_included=False,source='board_design_basis'),
        fixture_only_not_a_hardware_rating=True)
    domain=dict(net=net,complete=True,source_refs=['source'],sink_refs=['sink'])
    monkeypatch.setattr(repair.capacity.full.topology,'route_width_contracts',lambda *a,**k:{net:copy.deepcopy(contract)})
    monkeypatch.setattr(repair.capacity.full.topology,'board_current_domains',lambda *a,**k:{net:copy.deepcopy(domain)})
    monkeypatch.setattr(repair.capacity.fr,'_project_netclass_resolver',lambda *a,**k:lambda n:dict(track_width=2.,clearance=.2))
    # This unit fixture has a declared test budget, not a production board ID.
    # Integration receiving uses the real unchanged hardware current checker.
    monkeypatch.setattr(repair.debt,'receive',lambda *a,**k:dict(ok=True,complete=True,synthetic_fixture_only=True))
    args=dict(board_hint='opaque',retired_track_uuids=[force._uid(t) for t in old],
        retired_via_uuids=[force._uid(pickup)],start_uuid=force._uid(roots[0]),end_uuid=force._uid(roots[1]),
        layer=int(pcbnew.F_Cu if back else pcbnew.B_Cu),width_nm=1000000,
        points_nm=[list(t.GetStart()) for t in ghosts],allow_locked_source=True)
    return source,args,contract,domain


def make(source,tmp_path,proposal):
    child=force._copy_family(source,tmp_path/'child')
    field._save_field_snapshot(repair.construct(source,proposal),child);return child


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_cross_layer_kernel_and_component_attached_roots(tmp_path,monkeypatch,quarter,back):
    source,args,contract,domain=case(tmp_path,monkeypatch,quarter,back);raw=source.read_bytes()
    found=repair.discover(source,board_hint='opaque',seed_track_uuids=args['retired_track_uuids'],allow_locked_source=True)
    assert found['complete'] and len(found['kernels'])==1 and not found['refusals']
    kernel=found['kernels'][0]
    assert kernel['retired_track_uuids']==sorted(args['retired_track_uuids'])
    assert kernel['retired_via_uuids']==args['retired_via_uuids']
    proposal=json.loads(json.dumps(repair.plan(source,**args)));child=make(source,tmp_path,proposal)
    proof=repair.receive(source,child,proposal,board_hint='opaque')
    assert proof['ok'] and proof['complete'],proof['errors']
    assert proof['all_surviving_native_components_preserved'] and proof['all_old_current_sized_joins_preserved']
    assert all(g['all_actual_terminals_definitely_connected'] for g in proof['actual_drilled_terminal_graphs'])
    assert proof['centerline_removed_mm']>1.7 and not proof['new_capacity_credited']
    assert not proof['current_or_barrel_qualified'] and not proof['new_barrels'] and not proof['pads_moved']
    assert not proof['source_current_reduced'] and not proof['release_authority'] and source.read_bytes()==raw


@pytest.mark.parametrize('fault',['new_underfloor','source_rated','implicit_lock','group','pad_attached_via',
    'wrong_anchor_net','moved_anchor','raw_diagonal','hard90','backtrack','unknown_budget','incomplete_domain',
    'inner_face','boolean_width','repeated_port','ground','same_component_loop','disconnected_cut'])
def test_discovery_is_not_retirement_current_or_component_authority(tmp_path,monkeypatch,fault):
    source,args,contract,domain=case(tmp_path,monkeypatch);board=pcbnew.LoadBoard(str(source))
    live={force._uid(t):t for t in board.GetTracks()}
    if fault=='new_underfloor':args['width_nm']=499999
    elif fault=='source_rated':live[args['retired_track_uuids'][0]].SetWidth(500000)
    elif fault=='implicit_lock':args['allow_locked_source']=False
    elif fault=='group':
        g=pcbnew.PCB_GROUP(board);board.Add(g);g.AddItem(live[args['retired_track_uuids'][0]])
    elif fault=='pad_attached_via':args['retired_via_uuids'].append(args['end_uuid'])
    elif fault=='wrong_anchor_net':
        n=pcbnew.NETINFO_ITEM(board,'FOREIGN');board.Add(n);live[args['end_uuid']].SetNet(n)
    elif fault=='moved_anchor':live[args['end_uuid']].SetPosition(pcbnew.VECTOR2I_MM(14,15))
    elif fault=='raw_diagonal':args['points_nm'][1][0]+=1
    elif fault=='hard90':args['points_nm']=[[5000000,5000000],[5000000,15000000],[15000000,15000000]]
    elif fault=='backtrack':args['points_nm']=[[5000000,5000000],[4000000,5000000],[15000000,16000000],[15000000,15000000]]
    elif fault=='unknown_budget':contract['current_authority']['source']='guessed'
    elif fault=='incomplete_domain':domain['complete']=False
    elif fault=='inner_face':args['layer']=int(pcbnew.In1_Cu)
    elif fault=='boolean_width':args['width_nm']=True
    elif fault=='repeated_port':args['end_uuid']=args['start_uuid']
    elif fault=='ground':
        for n in board.GetNetsByNetcode().values():
            if n.GetNetname()==contract['net']:n.SetNetname('GND')
    elif fault=='same_component_loop':track(board,contract['net'],(5,5),(15,15),width=1.).SetLayer(pcbnew.B_Cu)
    elif fault=='disconnected_cut':args['retired_track_uuids'].append(force._uid(track(board,contract['net'],(30,30),(31,30),width=.2)))
    try:field._save_field_snapshot(board,source)
    except field._ProposalUnknown as e:
        assert fault=='wrong_anchor_net' and str(e)=='native_field_snapshot_changed_saved_identity';return
    with pytest.raises(ValueError):repair.plan(source,**args)


@pytest.mark.parametrize('fault',['width','face','net','point','lock','extra_copper','via','pad_pose','barrel_drill',
    'group','sidecar','budget','forged_plan','current_refusal','current_unknown'])
def test_saved_receiving_rejects_unowned_geometry_model_and_unknown_debt(tmp_path,monkeypatch,fault):
    source,args,contract,domain=case(tmp_path,monkeypatch);proposal=repair.plan(source,**args);child=make(source,tmp_path,proposal)
    board=pcbnew.LoadBoard(str(child));live={force._uid(t):t for t in board.GetTracks()}
    t=next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK')
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='face':t.SetLayer(pcbnew.F_Cu)
    elif fault=='net':
        n=pcbnew.NETINFO_ITEM(board,'FOREIGN');board.Add(n);t.SetNet(n)
    elif fault=='point':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='lock':t.SetLocked(not t.IsLocked())
    elif fault=='extra_copper':q=t.Duplicate();q.m_Uuid.Clone(pcbnew.KIID());board.Add(q)
    elif fault=='via':q=live[args['end_uuid']].Duplicate();q.m_Uuid.Clone(pcbnew.KIID());board.Add(q)
    elif fault=='pad_pose':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='barrel_drill':live[args['end_uuid']].SetDrill(450000)
    elif fault=='group':next(iter(board.Groups())).SetName('changed')
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='budget':contract['current_authority']['amps']=.9
    elif fault=='forged_plan':proposal['width_nm']-=1
    elif fault in ('current_refusal','current_unknown'):
        monkeypatch.setattr(repair.debt,'receive',lambda *a,**k:dict(ok=fault=='current_unknown',complete=False))
    try:field._save_field_snapshot(board,child)
    except field._ProposalUnknown as e:
        assert fault=='net' and str(e)=='native_field_snapshot_changed_saved_identity';return
    proof=repair.receive(source,child,proposal,board_hint='opaque')
    assert not proof['ok'] and proof['errors'] and not proof['release_authority']


def test_unknown_or_locked_discovery_seed_is_not_silently_accepted(tmp_path,monkeypatch):
    source,args,contract,domain=case(tmp_path,monkeypatch)
    found=repair.discover(source,board_hint='opaque',seed_track_uuids=args['retired_track_uuids'])
    assert found['complete'] and not found['kernels'] and len(found['refusals'])==3
    contract['current_authority']['source']='unproved'
    found=repair.discover(source,board_hint='opaque',seed_track_uuids=args['retired_track_uuids'],allow_locked_source=True)
    assert found['complete'] and not found['kernels'] and len(found['refusals'])==3

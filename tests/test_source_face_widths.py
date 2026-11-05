"""Layer-aware demand propagation must not invent narrower Source paths."""
import copy
import time

import pcbnew
import pytest
import cec_cell_endpoint_groups as groups
import cec_cell_escape_replan as escape
import cec_decoupler_cell as cells
import cec_force_current as force
import cec_fr as fr
import cec_source_face_widths as widths
from test_lastmile import _board


def fixture(monkeypatch):
    board=_board([],edge=(0,0,40,40));board.SetCopperLayerCount(4)
    board.GetDesignSettings().m_TrackMinWidth=200000
    net=pcbnew.NETINFO_ITEM(board,'renamed/power');board.Add(net)
    current=dict(current_authority=dict(amps=.75,geometry_margin=1.25,
        margin_included=False,source='synthetic_unchanged_contract'),
        profile='jlcpcb_6l_pofv_high_current',required_by_layer_nm={
            int(l):(845075 if int(l)==6 else 70539)for l in board.GetEnabledLayers().CuStack()})
    monkeypatch.setattr(cells,'_netclass',lambda *_:dict(width=500000,clearance=200000))
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *_:copy.deepcopy(current))
    return board,current


def request(width,face=0,other=None):
    return dict(kind='source_boundary',net='renamed/power',width_nm=width,
        a=dict(at_nm=[10000000,10000000],layers=[face]),
        b=dict(at_nm=[12000000,10000000],layers=[face if other is None else other]))


def demands():return {'front':request(500000),'inner':request(845075,6)}


def test_only_explained_actual_inner_floor_stops_bleeding(monkeypatch):
    board,current=fixture(monkeypatch);source=demands();before=copy.deepcopy(source)
    assert widths.envelope(board,source,'renamed/power',current)=={0:500000,2:500000,4:500000,6:845075}
    assert source==before


@pytest.mark.parametrize('face,other',[(0,0),(6,6),(0,2),(0,6)])
def test_unexplained_and_disjoint_widths_keep_global_source_demand(monkeypatch,face,other):
    board,current=fixture(monkeypatch)
    source=demands();source['opaque']=request(900000,face,other)
    assert set(widths.envelope(board,source,'renamed/power',current).values())=={900000}


@pytest.mark.parametrize('raw',[None,[],0,'6',[True],['6'],[999],[8],set([6])])
def test_invalid_access_cannot_earn_narrower_copper(monkeypatch,raw):
    board,current=fixture(monkeypatch);source=demands();source['inner']['a']['layers']=raw
    assert set(widths.envelope(board,source,'renamed/power',current).values())=={845075}


@pytest.mark.parametrize('kind',['unknown','ground','quiet'])
def test_noncurrent_ground_and_quiet_keep_legacy_net_global_width(monkeypatch,kind):
    board,current=fixture(monkeypatch);source=demands();net='renamed/power'
    if kind=='ground':
        net='GND'
        for r in source.values():r['net']=net
    else:current=None
    if kind=='quiet':
        for r in source.values():r['kind']='source_typed_incoming_quiet_output'
    assert set(widths.envelope(board,source,net,current).values())=={845075}


@pytest.mark.parametrize('fault',['amps_bool','margin_bool','missing_floor','floor_bool','string_face'])
def test_malformed_current_never_grants_face_narrowing(monkeypatch,fault):
    board,current=fixture(monkeypatch)
    if fault=='amps_bool':current['current_authority']['amps']=True
    if fault=='margin_bool':current['current_authority']['geometry_margin']=True
    if fault=='missing_floor':del current['required_by_layer_nm'][6]
    if fault=='floor_bool':current['required_by_layer_nm'][6]=True
    if fault=='string_face':current['required_by_layer_nm']['6']=current['required_by_layer_nm'].pop(6)
    assert min(widths.envelope(board,demands(),'renamed/power',current).values())>=845075


def test_legacy_partial_contract_cannot_earn_face_credit(monkeypatch):
    board,_=fixture(monkeypatch)
    current=dict(required_by_layer_nm={0:200000},synthetic_contract_identity='immutable')
    assert set(widths.envelope(board,demands(),'renamed/power',current).values())=={845075}


@pytest.mark.parametrize('face,width,under',[(0,500000,False),(0,500000,True),(6,845075,False),(6,845075,True)])
def test_endpoint_grouping_recomputes_exact_actual_face_floor(monkeypatch,face,width,under):
    board,current=fixture(monkeypatch);net=board.FindNet('renamed/power')
    track=pcbnew.PCB_TRACK(board);track.SetNet(net);track.SetLayer(face)
    track.SetStart(pcbnew.VECTOR2I_MM(10,10));track.SetEnd(pcbnew.VECTOR2I_MM(12,10))
    track.SetWidth(width-int(under));board.Add(track)
    cohorts,_=groups._cohorts(board,[track],'synthetic',demands())
    assert list(cohorts)==([('renamed/power',face,width,200000)]if under else [])


@pytest.mark.parametrize('partial',[False,True])
def test_complete_source_context_survives_menu_subsets(monkeypatch,partial):
    board,current=fixture(monkeypatch);whole=demands();work={'front':whole['front']}if partial else whole
    seen=[]
    def observe(_board,req,**kwargs):
        seen.append(kwargs['source_requests'])
        face=req['a']['layers'][0]
        width=widths.envelope(_board,kwargs['source_requests'],req['net'],current)[face]
        kwargs['append']([('trk',(10000000,10000000),(12000000,10000000),width,face)])
    monkeypatch.setattr(escape,'_connection_menu',observe)
    monkeypatch.setattr(fr,'coupled_pair_nets',lambda *_:set())
    monkeypatch.setattr(fr,'_lastmile_route_layers',lambda *_a,**_k:[2,6])
    result=escape.menus(board,work,board_path='not-a-loader',board_hint='synthetic',
        source_board=board,whole_requests=whole,timeout_s=2.)
    assert result['all_obligations_present']and all(q is whole for q in seen)
    for key,choices in result['domains'].items():
        assert all(op[3]==(845075 if key=='inner'else 500000)for c in choices for op in c['ops'])


def test_front_body_receiver_uses_independent_complete_source_face_context(monkeypatch):
    from test_source_current_pad_ports import saved_fixture
    import cec_source_current_pad_ports as ports
    source,child,pad,track,requests=saved_fixture(monkeypatch)
    for board in (source,child):board.SetCopperLayerCount(4)
    current=copy.deepcopy(ports.cells._supply_current_widths(source,pad.GetNetname()))
    current['required_by_layer_nm']={0:90000,2:90000,4:90000,6:845075}
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *_:copy.deepcopy(current))
    requests['mandatory_source']['unchanged_full_rail_current_contract']=copy.deepcopy(current)
    requests['inner']=request(845075,6);requests['inner']['net']=pad.GetNetname()
    result=ports.receive(source,child,requests,[track],board_hint='synthetic',deadline=time.monotonic()+3.)
    assert len(result)==1 and result[0]['full_width_nm']==500000 and not result[0]['class_width_exemption']


def test_actual_connection_menu_keeps_front_and_all_contact_via_floors(monkeypatch):
    from test_source_current_pad_ports import fixture as pad_fixture
    source,board,pad=pad_fixture(monkeypatch)
    for b in (source,board):b.SetCopperLayerCount(4)
    current=dict(current_authority=dict(amps=.75,geometry_margin=1.25,
        margin_included=False,source='synthetic_original'),profile='jlcpcb_6l_pofv_high_current',
        required_by_layer_nm={0:70539,2:70539,4:845075,6:845075})
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *_:copy.deepcopy(current))
    endpoint=dict(pad_uuid=force._uid(pad),at_nm=list(pad.GetPosition()),layers=[0])
    target=pcbnew.PCB_TRACK(board);target.SetNet(pad.GetNet());target.SetLayer(0);target.SetWidth(500000)
    target.SetStart(pcbnew.VECTOR2I(22500000,20000000));target.SetEnd(pcbnew.VECTOR2I(23500000,20000000))
    board.Add(target)
    front=dict(kind='source_boundary',net=pad.GetNetname(),width_nm=500000,a=endpoint,
        b=dict(at_nm=[22500000,20000000],layers=[0],native_uuids=[force._uid(target)]))
    inner=request(845075,6);inner['net']=pad.GetNetname()
    seen=[];detail={}
    def surface(*_args,**kwargs):seen.append(kwargs);return None
    monkeypatch.setattr(cells,'_canonical_whole_rail_surface',surface)
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',lambda *_a,**_k:None)
    monkeypatch.setattr(fr,'_lastmile_bridge',lambda *_a,**_k:None)
    import cec_native_via_frontier as frontier
    import cec_native_component_ports as ports
    monkeypatch.setattr(frontier,'sites',lambda *_a,**_k:dict(sites_nm=[]))
    monkeypatch.setattr(ports,'surface_maze_pairs',lambda *_a,**_k:[])
    escape._connection_menu(board,front,board_hint='synthetic',deadline=time.monotonic()+2.,
        layers=[2,6],append=lambda _ops:None,detail=detail,source_board=source,
        full_net_width_nm=845075,source_requests={'front':front,'inner':inner})
    assert seen and all(q['class_width_nm']==500000 for q in seen)
    assert detail['source_current_barrel_geometry']['minimum_local_via_web_nm']==845075


def test_saved_prefix_context_preserves_front_and_inner_floors(monkeypatch):
    from test_cell_endpoint_groups import supply
    import cec_full_current_supply_prefix as prefix_receiver
    board,launch,via,trunk,prefix,current,requests=supply(monkeypatch)
    monkeypatch.setattr(cells,'_netclass',lambda *_:dict(width=500000,clearance=200000))
    current['required_by_layer_nm']={int(l):(845075 if int(l)==6 else 70539)
        for l in board.GetEnabledLayers().CuStack()}
    monkeypatch.setattr(cells,'_supply_current_widths',lambda *_:copy.deepcopy(current))
    first=next(iter(requests.values()));first['width_nm']=500000
    first['unchanged_full_rail_current_contract']=copy.deepcopy(current)
    first['a']['layers']=[int(prefix.GetLayer())];first['b']=dict(layers=[int(prefix.GetLayer())])
    requests['inner']=request(845075,6);requests['inner']['net']=launch.GetNetname()
    seen=[]
    def observe(_board,contracts,**kwargs):
        seen.append(contracts)
        return dict(complete=True,track_uuids=list(kwargs['track_uuid_scope']))
    monkeypatch.setattr(prefix_receiver,'receive',observe)
    proof=groups.receive(board,board,requests,[prefix],board_hint='synthetic',deadline=time.monotonic()+3.)
    assert proof['track_uuids']==[force._uid(prefix)]
    actual=seen[0][launch.GetNetname()]['required_by_layer_mm']
    assert actual['F.Cu']==actual['B.Cu']==.5 and actual['In2.Cu']==.845075

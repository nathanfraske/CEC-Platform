"""Native copper search/receiving; only canonical source compilation is stubbed."""
import copy
import shutil
import json
from unittest import mock
import pcbnew
import pytest
import cec_distributed_supply as supply
import cec_distributed_supply_prefix as prefixes
import cec_force_current as force
from test_distributed_supply import fixture,authority,resolver


def native_fixture(tmp_path,turn=0,layer=pcbnew.F_Cu):
    b,net=fixture(tmp_path,turn=turn,layer=layer,count=2)
    ground=pcbnew.NETINFO_ITEM(b,'GND');b.Add(ground)
    foreign=pcbnew.NETINFO_ITEM(b,'foreign');b.Add(foreign)
    for i,fp in enumerate(b.GetFootprints()):
        fp.SetReference('C'+str(i+1));fp.SetValue('100nF')
        fp.SetFPID(pcbnew.LIB_ID('Device','C_0402_1005Metric'))
        p=next(iter(fp.Pads()));p.SetNumber('1');p.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        q=pcbnew.PAD(fp);q.SetNumber('2');q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        q.SetShape(pcbnew.PAD_SHAPE_RECT);q.SetSize(pcbnew.VECTOR2I_MM(.3,.6))
        q.SetLayerSet(p.GetLayerSet());q.SetNet(ground)
        q.SetPosition(p.GetPosition()+pcbnew.VECTOR2I_MM(*((1.5,0)if turn%2 else (0,1.5))));fp.Add(q)
    for fp in list(b.GetFootprints()):
        p=fp.FindPadByNumber('1')
        for sign in (-1,1):
            blocker=pcbnew.FOOTPRINT(b);blocker.SetReference('X'+str(sign)+fp.GetReference())
            q=pcbnew.PAD(blocker);q.SetNumber('1');q.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            q.SetShape(pcbnew.PAD_SHAPE_RECT);q.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
            q.SetLayerSet(p.GetLayerSet());q.SetNet(foreign)
            delta=(sign*.5,0) if turn%2 else (0,sign*.5)
            q.SetPosition(p.GetPosition()+pcbnew.VECTOR2I_MM(*delta));blocker.Add(q);b.Add(blocker)
    return b,net


def compile_boundary(board,contracts,**kwargs):
    return dict(contracts={n:dict(c,authority_refs=['C1','C2'])for n,c in contracts.items()},
        pads={force._uid(p):dict(ref=f.GetReference(),pin=p.GetNumber(),net=p.GetNetname(),
            role='value_qualified_grounded_ceramic_supply_terminal')
            for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()in contracts},
        source_bindings={'fresh_test_source_export':True})


@pytest.mark.parametrize('turn,layer',[(0,pcbnew.F_Cu),(1,pcbnew.F_Cu),(2,pcbnew.B_Cu),(3,pcbnew.B_Cu)])
def test_native_prefix_search_then_independent_receive(tmp_path,turn,layer):
    b,net=native_fixture(tmp_path,turn,layer)
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary):
        result=supply.construct(b,board_hint='synthetic-selected-source',include_nets=[net],
            netclass_resolver=lambda n:dict(name='Power',track_width=.5,clearance=.2),
            timeout_s=5.,max_pair_s=1.,allow_supply_prefixes=True)
    assert result['joins']==1,result
    ids=result['created_uuids'];context=result['supply_prefix_source_context']
    proof=prefixes.receive(b,result['contracts'],ids,context)
    assert proof['track_uuids']
    assert any(t.GetWidth()==500000 for t in b.GetTracks())
    assert all(t.GetWidth()>=b.GetDesignSettings().m_TrackMinWidth for t in b.GetTracks())
    assert result['whole_power_qualified'] is False
    assert result['new_vias']==0


def test_no_source_positive_pad_has_no_escape(tmp_path):
    b,n=native_fixture(tmp_path);a=dict(kind='pad_center',uuid='unknown',layer=0)
    assert prefixes.endpoint(b,a,{},dict(pads={})) is None


@pytest.mark.parametrize('value',[True,0,-1,11,float('nan')])
def test_source_compiler_timeout_failclosed(tmp_path,value):
    b,n=native_fixture(tmp_path)
    with pytest.raises(ValueError):prefixes.prepare(b,{},board_hint='x',timeout_s=value)


@pytest.mark.parametrize('kind',['input','output','passive','bidirectional'])
def test_source_manufacturer_supply_pin_contradiction(kind):
    sf=type('Sheet',(),{'children':[('lib_symbols',
        '(lib_symbols (symbol "D:X" (symbol "D:X_1_1" (pin '+kind+' line (name "X") (number "1")))))')]})()
    with pytest.raises(ValueError):prefixes._source_pin((None,None,sf,{'lib_id':'D:X'}),'1','manufacturer_supply_pin')


def test_missing_new_thin_group_never_received(tmp_path):
    b,n=native_fixture(tmp_path);p=next(p for f in b.GetFootprints()for p in f.Pads()if p.GetNetname()==n)
    t=pcbnew.PCB_TRACK(b);t.SetNetCode(p.GetNetCode());t.SetLayer(p.GetLayer());t.SetWidth(200000)
    t.SetStart(p.GetPosition());t.SetEnd(p.GetPosition()+pcbnew.VECTOR2I_MM(1,0));b.Add(t)
    contract=dict(net=n,required_by_layer_mm={'F.Cu':.5},routing_layers=['F.Cu'])
    with pytest.raises(ValueError):prefixes.receive(b,{n:contract},[force._uid(t)],dict(contracts={},pads={}))


@pytest.mark.parametrize('mutation',['under_current','lost_group','unknown_current','foreign_net','missing_uuid','unknown_source_pad'])
def test_saved_new_prefix_mutations_failclosed(tmp_path,mutation):
    b,net=native_fixture(tmp_path)
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary):
        result=supply.construct(b,board_hint='synthetic-selected-source',include_nets=[net],
            netclass_resolver=lambda n:dict(name='Power',track_width=.5,clearance=.2),
            timeout_s=5.,allow_supply_prefixes=True)
    assert result['joins']==1
    contracts=copy.deepcopy(result['contracts']);context=copy.deepcopy(result['supply_prefix_source_context'])
    ids=list(result['created_uuids']);thin=next(t for t in b.GetTracks()if t.GetWidth()<500000)
    if mutation=='under_current':thin.SetWidth(50000)
    elif mutation=='lost_group':thin.GetParentGroup().RemoveItem(thin)
    elif mutation=='unknown_current':contracts[net]['current_authority']={}
    elif mutation=='foreign_net':thin.SetNetCode(b.GetNetInfo().GetNetItem('foreign').GetNetCode())
    elif mutation=='missing_uuid':ids.append('absent')
    elif mutation=='unknown_source_pad':context['pads']={}
    with pytest.raises(ValueError):prefixes.receive(b,contracts,ids,context)


def test_refused_independent_prefix_receiving_leaks_no_copper_or_group(tmp_path):
    b,net=native_fixture(tmp_path)
    old={force._uid(t)for t in b.GetTracks()};groups={force._uid(g)for g in b.Groups()}
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary), \
            mock.patch.object(prefixes,'receive',side_effect=ValueError('negative receiving control')):
        result=supply.construct(b,board_hint='synthetic-selected-source',include_nets=[net],
            netclass_resolver=lambda n:dict(name='Power',track_width=.5,clearance=.2),
            timeout_s=2.,max_attempts=8,allow_supply_prefixes=True)
    assert result['joins']==0
    assert {force._uid(t)for t in b.GetTracks()}==old
    assert {force._uid(g)for g in b.Groups()}==groups


def test_enabled_actual_literal_save_reloads_surviving_prefix_ids(tmp_path):
    b,net=native_fixture(tmp_path)
    source=tmp_path/'source.kicad_pcb';candidate=tmp_path/'candidate.kicad_pcb'
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(source),b)
    project=dict(net_settings=dict(classes=[dict(name='Default',track_width=.5,clearance=.2)],
        netclass_assignments={net:'Default'}))
    source.with_suffix('.kicad_pro').write_text(json.dumps(project))
    candidate.with_suffix('.kicad_pro').write_text(json.dumps(project))
    shutil.copy2(source,candidate);b.SetFileName(str(candidate))
    with authority(net),mock.patch.object(prefixes,'prepare',side_effect=compile_boundary):
        result=supply.construct(b,board_hint='synthetic-selected-source',include_nets=[net],
            netclass_resolver=lambda n:dict(name='Power',track_width=.5,clearance=.2),
            timeout_s=5.,allow_supply_prefixes=True)
    assert result['joins']==1
    # The constructor ledger is not material authority. Simulate an atom
    # already retired by a previous construction cleanup; reload actual IDs.
    result['created_uuids'].append('stale-constructor-atom')
    with mock.patch.object(force,'_finalize_current_segments',side_effect=AssertionError('legacy finalizer forbidden')):
        proof=supply._save_constructed_supply(b,str(source),candidate,result,
            board_hint='synthetic-selected-source',allow_supply_prefixes=True)
    saved=pcbnew.LoadBoard(str(candidate))
    assert proof['source_literal'] is True
    assert len(result['created_uuids'])<len(result['pre_finalization_created_uuids'])
    assert set(result['created_uuids'])=={force._uid(t)for t in saved.GetTracks()}
    assert result['created_tracks']==supply._track_records(saved,result['created_uuids'])
    assert prefixes.receive(saved,result['contracts'],result['created_uuids'],
        result['supply_prefix_source_context'])['track_uuids']
    import cec_additive_route_receiving as additive
    # Real independent literal/rule/refill replay; no positive admission mock.
    received=additive.receive(source,candidate,timeout_s=10.,
        allow_endpoint_neckdown_additions=True,board_hint='synthetic-selected-source')
    assert received['ok'] and received['complete'],received


def test_legacy_finalizer_dispatch_is_unchanged():
    sentinel=object()
    with mock.patch.object(force,'_finalize_current_segments',return_value=sentinel)as old:
        assert supply._save_constructed_supply('board','source','candidate',{},
            board_hint='hint',allow_supply_prefixes=False)is sentinel
    old.assert_called_once_with('board','source','candidate')

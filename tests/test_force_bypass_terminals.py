"""Capacitor tree completion never reclassifies taps or reduces force widths."""
import copy
import time
from unittest import mock

import pcbnew
import pytest

import cec_current_topology as topology
import cec_force_bypass_terminals as terminals
import cec_force_current as force
import cec_fr as fr
from test_force_current import fixture, authority, worker


def add_cap(board, net, *, rotated=False, value="100nF", namespace="vendor-Capacitor_SMD",
            return_net="GND", swap=False):
    ground = board.FindNet(return_net)
    if ground is None:
        ground = pcbnew.NETINFO_ITEM(board, return_net); board.Add(ground)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference("ANY_SUPPORT_NAME")
    fp.SetValue(value); fp.SetFPID(pcbnew.LIB_ID(namespace, "C_Synthetic")); board.Add(fp)
    pads = []
    for number, x, n in (("Q", 20., board.FindNet(net)), ("R", 23., ground)):
        p = pcbnew.PAD(fp); p.SetNumber(number); p.SetNet(n)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
        ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); p.SetLayerSet(ls)
        p.SetPosition(pcbnew.VECTOR2I_MM(18 if rotated else x, x if rotated else 32))
        fp.Add(p); pads.append(p)
    if swap:
        pads[0].SetNet(ground); pads[1].SetNet(board.FindNet(net))
    return fp, pads[1] if swap else pads[0], pads[0] if swap else pads[1]


@pytest.mark.parametrize("rotated,renamed,swap", [(False,False,False),(True,True,True)])
def test_native_graph_expansion_is_explicit_read_only_and_preserves_full_load(tmp_path,rotated,renamed,swap):
    path=tmp_path/'board.kicad_pcb'
    r=fixture(path,narrow=False,monitor=True,rotated=rotated,renamed=renamed)
    b=pcbnew.LoadBoard(str(path)); fp, supply, ground=add_cap(b,r['net'],rotated=rotated,swap=swap)
    selection=terminals.select(b,r['net'])
    assert selection['pad_uuids']==[force._uid(supply)]
    assert selection['capacitors'][0]['ref']=='ANY_SUPPORT_NAME'
    assert not any(selection[k] for k in ('load_reduced','width_reduced',
        'source_sink_contract_changed','measurement_terminals_reclassified','release_authority'))
    before=copy.deepcopy([(force._uid(p),tuple(p.GetPosition()),str(p.GetNetname()))
        for f in b.GetFootprints() for p in f.Pads()])
    with authority(r['net'],source=r['source'],sink=r['sink']):
        domain=topology.board_current_domains(b)[r['net']]
        contract=topology.route_width_contracts(b)[r['net']]
    original=copy.deepcopy(domain)
    project={'track_width':1.0}
    legacy,_=force._graph(b,r['net'],domain,contract,project)
    expanded,_=force._graph(b,r['net'],domain,contract,project,include_bypass_terminals=True)
    assert legacy['rated_connectivity']['connected']
    assert not expanded['rated_connectivity']['connected']
    assert legacy['rated_connectivity']['authority_pad_count']==2
    assert expanded['rated_connectivity']['authority_pad_count']==3
    assert expanded['required_by_layer_mm']==legacy['required_by_layer_mm']
    leaves=force._leaf_obstacles(b,r['net'],domain,expanded)
    assert supply not in leaves and any(p.GetClass()=='PAD' and
        p.GetParentFootprint().GetReference()=='MONITOR' for p in leaves)
    assert domain==original
    assert before==[(force._uid(p),tuple(p.GetPosition()),str(p.GetNetname()))
        for f in b.GetFootprints() for p in f.Pads()]


@pytest.mark.parametrize('change', ['resistor','ic_namespace','power_return','different_faces','drilled','extra_land'])
def test_value_alone_never_reclassifies_untyped_or_nonshunt_parts(tmp_path,change):
    path=tmp_path/'board.kicad_pcb';r=fixture(path);b=pcbnew.LoadBoard(str(path))
    fp,p,g=add_cap(b,r['net'])
    if change=='resistor':fp.SetValue('47kΩ')
    elif change=='ic_namespace':fp.SetFPID(pcbnew.LIB_ID('Package_DFN_QFN','C_Pretend'))
    elif change=='power_return':g.SetNet(b.FindNet(r['peer']))
    elif change=='different_faces':
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu);g.SetLayerSet(ls)
    elif change=='drilled':
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH);p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif change=='extra_land':
        extra=pcbnew.PAD(fp);extra.SetNumber('EXTRA');extra.SetNet(g.GetNet());fp.Add(extra)
    assert terminals.select(b,r['net'])['pad_uuids']==[]


def test_explicit_renamed_return_uses_actual_nets_not_a_ground_alias_guess(tmp_path):
    path=tmp_path/'board.kicad_pcb';r=fixture(path);b=pcbnew.LoadBoard(str(path))
    _,p,_=add_cap(b,r['net'],return_net='/OTHER_PROJECT_RETURN')
    assert not terminals.select(b,r['net'])['pad_uuids']
    assert terminals.select(b,r['net'],return_nets=('/OTHER_PROJECT_RETURN',))['pad_uuids']==[force._uid(p)]


@pytest.mark.parametrize('flag',['SetDNP','SetExcludedFromBOM'])
def test_unpopulated_support_does_not_become_a_qualified_load_terminal(tmp_path,flag):
    path=tmp_path/'board.kicad_pcb';r=fixture(path);b=pcbnew.LoadBoard(str(path))
    fp,_,_=add_cap(b,r['net'])
    getattr(fp,flag)(True)
    assert terminals.select(b,r['net'])['pad_uuids']==[]


def test_dispatcher_binds_explicit_capacitor_tree_mode_and_rejects_nonboolean_options():
    import cec_saved_family_repair as saved
    assert saved._options('force_current',{})['include_bypass_terminals'] is False
    assert saved._options('force_current',{'include_bypass_terminals':True})['include_bypass_terminals'] is True
    with pytest.raises(ValueError):saved._options('force_current',{'include_bypass_terminals':1})
    with pytest.raises(ValueError):saved._options('kelvin_branch',{'include_bypass_terminals':True})


def test_independent_dispatch_receiving_refuses_primary_only_qualified_capacitor_tree(tmp_path):
    import cec_saved_family_repair as saved
    import cec_score
    import cec_stage_admission as admission
    path=tmp_path/'board.kicad_pcb';r=fixture(path,narrow=False,monitor=False)
    b=pcbnew.LoadBoard(str(path));add_cap(b,r['net']);pcbnew.SaveBoard(str(path),b)
    request=dict(source=str(path),net=r['net'],board_hint='synthetic',operator='force_current',
                 options={'include_bypass_terminals':True})
    replay=dict(source_family_before=force._family(path,'synthetic'),loaded_board_identity_verified=True)
    with authority(r['net']), mock.patch.object(saved,'_remaining'), \
         mock.patch.object(force,'preservation',return_value={'ok':True}), \
         mock.patch.object(cec_score,'score',return_value={}), \
         mock.patch.object(admission,'evaluate',return_value={'accepted':True}), \
         mock.patch.object(saved,'_replay',return_value=replay), \
         mock.patch('cec_force_sense_evidence.admit_changed_net',return_value={'ok':True}):
        assert force.diagnose(path,[r['net']])['domains'][r['net']]['qualified']
        with pytest.raises(saved.Refusal,match='independent_rated_bypass_tree_refused'):
            saved._native_validate(request,path,{})


def test_construct_joins_bypass_at_unchanged_full_width_and_keeps_monitor(tmp_path):
    path=tmp_path/'board.kicad_pcb';r=fixture(path,narrow=False,monitor=True)
    b=pcbnew.LoadBoard(str(path));_,p,_=add_cap(b,r['net'])
    old={force._uid(t):(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in b.GetTracks()}
    with authority(r['net']):
        d=topology.board_current_domains(b)[r['net']];c=topology.route_width_contracts(b)[r['net']]
        graph,_=force._graph(b,r['net'],d,c,fr._project_netclass_resolver(str(path))(r['net']) or {},
                             include_bypass_terminals=True)
        result=force._construct(b,str(path),r['net'],d,c,max_pairs=16,max_bridges=4,
            deadline=time.monotonic()+8.,allow_maze=False,include_bypass_terminals=True)
    assert result['connected'] and result['bridge_count']>=1 and result['created_uuids']
    required=graph['required_by_layer_mm']
    for t in b.GetTracks():
        if force._uid(t) in old:
            assert old[force._uid(t)]==(tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth())
        else:
            name=fr._project_netclass_resolver(str(path))(r['net'])
            assert t.GetWidth()>=round(required['F.Cu']*1e6)
    assert result['rated_after']['bypass_terminal_selection']['pad_uuids']==[force._uid(p)]


def test_qualified_primary_prefix_cannot_skip_open_bypass_when_mode_is_requested(tmp_path):
    path=tmp_path/'board.kicad_pcb';r=fixture(path,narrow=False,monitor=False)
    b=pcbnew.LoadBoard(str(path));add_cap(b,r['net']);pcbnew.SaveBoard(str(path),b)
    # The current contract stays real. Returning an empty bounded constructor
    # proves that the worker reaches the auxiliary obligation rather than
    # mistaking a primary-only diagnosis for completed capacitor connectivity.
    empty=dict(created_uuids=[],connected=False,reason='bounded_no_legal_rated_path',attempts=[])
    with mock.patch.object(force,'_construct',return_value=empty) as construct:
        result=worker(path,tmp_path/'trial',r,include_bypass_terminals=True)
    assert construct.called and not result['accepted']
    assert not result['input_bypass_tree']['rated_connectivity']['connected']
    assert construct.call_args.kwargs['include_bypass_terminals'] is True


@pytest.mark.parametrize('value',[1,'yes',None])
def test_bypass_mode_requires_boolean_before_worker_launch(tmp_path,value):
    path=tmp_path/'board.kicad_pcb';r=fixture(path)
    with pytest.raises(ValueError):
        force.propose(path,tmp_path/'trial',r['net'],board_hint='synthetic',immutable_nets=(),
                      include_bypass_terminals=value)


@pytest.mark.parametrize('kwargs',[{'return_nets':[]},{'return_nets':'GND'},
    {'return_nets':['GND','GND']},{'max_pads':True},{'max_pads':513}])
def test_unknown_unbounded_selection_cannot_be_a_permission(kwargs,tmp_path):
    path=tmp_path/'board.kicad_pcb';r=fixture(path);b=pcbnew.LoadBoard(str(path))
    with pytest.raises(ValueError):terminals.select(b,r['net'],**kwargs)

"""Exact Source aliases preserve all obligations and construct one path."""
import ast
import copy
from pathlib import Path

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_exact_connection_aliases as aliases
import cec_force_current as force
from cec_native_items import discard_items


def request():
    return dict(kind='source_boundary',net='arbitrary_scalar',width_nm=200000,
        a=dict(pad_uuid='literal-a',at_nm=[10000000,10000000],layers=[0]),
        b=dict(native_uuids=['literal-b'],at_nm=[13000000,10000000],layers=[31]))


@pytest.mark.parametrize('names',[('boundary:x','retained:y'),('not-a-board','no-refdes')])
def test_full_literal_equality_has_one_routing_variable_but_two_original_witnesses(names):
    original={names[1]:request(),names[0]:request()};before=copy.deepcopy(original)
    view,proof=aliases.routing_view(original)
    assert list(view)==[min(names)]and original==before
    assert proof['original_count']==2 and proof['routing_count']==1
    assert proof['groups'][0]['members']==sorted(names)
    assert proof['all_original_requests_retained']and proof['native_endpoint_receiving_still_required']
    assert not proof['copper_authority']and not proof['release_authority']
    assert aliases.derive(dict(reversed(list(original.items()))))==proof
    assert aliases.verify(original,proof,view)==proof


@pytest.mark.parametrize('fault',['width','net','a_pad','b_native','point','layer','reverse',
    'permission','current','source_owner','local_supply','ground','required_entry'])
def test_similar_requests_or_permissions_are_not_exact_aliases(fault):
    first=request();second=copy.deepcopy(first)
    if fault=='width':second['width_nm']+=1
    elif fault=='net':second['net']='other'
    elif fault=='a_pad':second['a']['pad_uuid']='different-owner'
    elif fault=='b_native':second['b']['native_uuids']=['different-literal']
    elif fault=='point':second['b']['at_nm'][0]+=1
    elif fault=='layer':second['b']['layers']=[2]
    elif fault=='reverse':second['a'],second['b']=second['b'],second['a']
    elif fault=='permission':first['permission']=second['permission']='not-authority'
    elif fault=='current':first['unchanged_full_rail_current_contract']=second['unchanged_full_rail_current_contract']={}
    elif fault=='source_owner':second['source_owner']='different'
    elif fault=='local_supply':first['kind']=second['kind']='local_supply'
    elif fault=='ground':first['net']=second['net']='GND'
    elif fault=='required_entry':first['required_projected_ground_entry']=second['required_projected_ground_entry']={}
    original={'a':first,'b':second};view,proof=aliases.routing_view(original)
    assert set(view)==set(original)and proof['groups']==[]


@pytest.mark.parametrize('fault',['mapping','sha','members','count','drop_key','extra_key','partial_packet'])
def test_forged_alias_metadata_or_incomplete_coverage_refuses(fault):
    original={'a':request(),'b':request()};view,proof=aliases.routing_view(original)
    packet=dict(domains={k:[]for k in view},original_source_requests=original,exact_source_request_aliases=proof)
    if fault=='mapping':proof['canonical_by_original']['b']='b'
    elif fault=='sha':proof['source_inventory_sha256']='0'*64
    elif fault=='members':proof['groups'][0]['members']=['a']
    elif fault=='count':proof['original_count']=1
    elif fault=='drop_key':packet['domains']={}
    elif fault=='extra_key':packet['domains']['b']=[]
    elif fault=='partial_packet':del packet['original_source_requests']
    with pytest.raises(ValueError):aliases.packet_coverage(packet)


@pytest.mark.parametrize('value',[{},[],{'a':[]},{str(i):request()for i in range(65)},
    {'a':dict(request(),width_nm=float('nan'))}])
def test_inventory_bounds_refuse_without_partial_alias_credit(value):
    with pytest.raises((ValueError,TypeError)):aliases.derive(value)


def fixture():
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(board,'arbitrary_scalar');board.Add(net)
    def pad(ref,at,face):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(net);fp.Add(p)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        layers=pcbnew.LSET();layers.AddLayer(face)
        p.SetSize(pcbnew.VECTOR2I_MM(.6,.6));p.SetLayerSet(layers)
        p.SetPosition(pcbnew.VECTOR2I_MM(*at));return p
    first=pad('renamed-a',(10,10),pcbnew.F_Cu);last=pad('renamed-b',(13,10),pcbnew.B_Cu)
    r=dict(kind='source_boundary',net='arbitrary_scalar',width_nm=200000,
        a=dict(pad_uuid=force._uid(first),at_nm=list(first.GetPosition()),layers=[pcbnew.F_Cu]),
        b=dict(pad_uuid=force._uid(last),at_nm=list(last.GetPosition()),layers=[pcbnew.B_Cu]))
    ops=[['trk',[10000000,10000000],[11000000,10000000],200000,pcbnew.F_Cu],
        ['via',[11000000,10000000],.3,.6],
        ['trk',[11000000,10000000],[13000000,10000000],200000,pcbnew.B_Cu]]
    choice=dict(id='one-physical-path',net='arbitrary_scalar',cost=5.,clearance_nm=200000,ops=ops)
    return board,r,choice


def test_exact_alias_constructs_one_barrel_and_saved_observer_checks_both_originals():
    board,r,choice=fixture();original={'boundary:opaque':r,'retained:opaque':copy.deepcopy(r)}
    view,proof=aliases.routing_view(original)
    # The old independent-demand model really does conflict on its own hole.
    assert escape.conflict_oracle(board)(choice,copy.deepcopy(choice))
    packet=dict(domains={key:[choice]for key in view},source_native_binding=escape.row._source_binding(board),
        original_source_requests=original,exact_source_request_aliases=proof)
    selection=escape.choose(board,packet)
    assert selection['complete']and selection['original_obligation_coverage']==proof
    made=escape.construct_private(board,packet,selection)
    assert len(made)==3 and sum(t.GetClass()=='PCB_VIA'for t in board.GetTracks())==1
    received=aliases.receive_paths(board,original)
    assert received['complete']and received['ok']and len(received['witnesses'])==2
    assert {q['original_obligation']for q in received['witnesses']}==set(original)
    assert all(q['native_endpoint_connection']['all_named_contacts_connected']for q in received['witnesses'])
    # No same-net or a Source alias label may disguise an actual missing path.
    discard_items(board,made[-1:])
    with pytest.raises(ValueError,match='not_natively_connected'):aliases.receive_paths(board,original)


def test_alias_selection_coverage_cannot_be_forged_before_construction():
    board,r,choice=fixture();original={'a':r,'b':copy.deepcopy(r)};view,proof=aliases.routing_view(original)
    packet=dict(domains={key:[choice]for key in view},source_native_binding=escape.row._source_binding(board),
        original_source_requests=original,exact_source_request_aliases=proof)
    selection=escape.choose(board,packet);selection['original_obligation_coverage']['routing_count']=2
    before=escape.row._source_binding(board)
    with pytest.raises(ValueError):escape.construct_private(board,packet,selection)
    assert escape.row._source_binding(board)==before


@pytest.mark.parametrize('timeout',[True,0,-1,10.1,float('nan'),float('inf')])
def test_native_witness_lease_is_explicitly_bounded(timeout):
    with pytest.raises(ValueError):aliases.receive_paths(None,{'a':request()},timeout_s=timeout)


def test_saved_cell_receiver_reconstructs_every_alias_from_full_source_requests():
    root=Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'scripts/cec_complete_cell_receiving.py').read_text())
    receive=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_receive_paths')
    calls=[n for n in ast.walk(receive)if isinstance(n,ast.Call)and ast.unparse(n.func)=='aliases.receive_paths']
    assert len(calls)==1 and [ast.unparse(v)for v in calls[0].args]==['child','requests']
    compiler=(root/'scripts/cec_cell_macro_requests.py').read_text()
    assert 'requests=requests'in compiler and 'aliases.routing_view'not in compiler


def test_construction_packet_does_not_modify_legacy_nonalias_behavior():
    assert aliases.packet_coverage(dict(domains={}))is None

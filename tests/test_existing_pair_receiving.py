"""Native contact evidence, not caller lock lists, governs route reuse."""
import math
from unittest.mock import patch

import pcbnew
import pytest
import cec_constraints as constraints
import cec_field_coupling as field
import cec_precision_route as route
from cec_local_copper_cell import copper_inventory


def fixture(angle=0., offset=(0., 0.), prefix='arbitrary', extra=False):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    pair=dict(name=prefix+' pair',p='/'+prefix+'/CAN_H',n='/'+prefix+'/CAN_L',
              kind='can',width=.25,gap=.2)
    radians=math.radians(angle)
    def point(x,y):
        return pcbnew.VECTOR2I_MM(offset[0]+x*math.cos(radians)-y*math.sin(radians),
                                 offset[1]+x*math.sin(radians)+y*math.cos(radians))
    for net,y in ((pair['p'],5.),(pair['n'],5.45)):
        board.Add(pcbnew.NETINFO_ITEM(board,net))
        for index,x in enumerate((3.,23.)):
            fp=pcbnew.FOOTPRINT(board);fp.SetReference(prefix+str(index)+net[-1]);board.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet(net))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
            pad.SetPosition(point(x,y));fp.Add(pad)
            if extra and index==0 and net==pair['p']:
                duplicate=pad.Duplicate();duplicate.SetPosition(point(x,y+2.));fp.Add(duplicate)
        item=pcbnew.PCB_TRACK(board);item.SetStart(point(3.,y));item.SetEnd(point(23.,y))
        item.SetWidth(pcbnew.FromMM(.25));item.SetLayer(pcbnew.F_Cu)
        item.SetNet(board.FindNet(net));item.SetLocked(False);board.Add(item)
    return board,pair


@pytest.mark.parametrize('angle,offset,prefix',[(0.,(0.,0.),'renamed'),
    (90.,(40.,12.),'different hierarchy'),(180.,(28.,18.),'other')])
def test_native_complete_pair_needs_no_lock_bookkeeping(angle,offset,prefix,tmp_path):
    board,pair=fixture(angle,offset,prefix)
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path));before=copper_inventory(board)
    result=route._native_pair_completion(board,pair)
    assert result['complete'] and result['connected'] is True
    assert all(row['pad_count']==2 and not row['unreachable_pad_uuids']
               for row in result['nets'].values())
    assert copper_inventory(board)==before
    assert all(not item.IsLocked() for item in board.GetTracks())


def test_duplicate_number_is_an_additional_physical_contact_not_netname_proof():
    board,pair=fixture(extra=True);before=copper_inventory(board)
    result=route._native_pair_completion(board,pair)
    assert result['complete'] and result['connected'] is False
    assert result['nets'][pair['p']]['pad_count']==3
    assert len(result['nets'][pair['p']]['unreachable_pad_uuids'])==1
    assert copper_inventory(board)==before


def test_bounded_inventory_is_unknown_not_disconnected_or_complete():
    board,pair=fixture();result=route._native_pair_completion(board,pair,max_items=2)
    assert not result['complete'] and result['connected'] is None
    assert 'inventory' in result['reason']


def receiving_mocks(monkeypatch,pair,violations=(),field_rows=()):
    monkeypatch.setattr(constraints,'high_speed_pair_summary',lambda *a,**kw:
        dict(applicable=True,pairs=[dict(p=pair['p'],n=pair['n'],violations=list(violations))]))
    monkeypatch.setattr(field,'field_coupling_summary',lambda *a,**kw:
        dict(interactions=list(field_rows)))


@pytest.mark.parametrize('case',['good','physical-debt','field-debt','unrelated-field-debt'])
def test_connected_reuse_requires_exact_physical_and_field_contract(monkeypatch,case):
    board,pair=fixture();before=copper_inventory(board)
    rows=[dict(blocking=True,nets=[pair['p'] if case=='field-debt' else 'elsewhere','ADC'])]
    receiving_mocks(monkeypatch,pair,violations=['bad return'] if case=='physical-debt' else [],
                    field_rows=rows if 'field-debt' in case else [])
    result=route._preexisting_pair_receiving(board,pair,board_path='')
    assert result['applicable'] and result['qualified'] is (case in ('good','unrelated-field-debt'))
    assert copper_inventory(board)==before and result['board_mutated'] is False
    assert result['release_authority'] is False


def test_missing_profile_cannot_qualify_connected_pair(monkeypatch):
    board,pair=fixture()
    monkeypatch.setattr(constraints,'high_speed_pair_summary',lambda *a,**kw:
                        dict(applicable=False,pairs=[]))
    result=route._preexisting_pair_receiving(board,pair,board_path='')
    assert result['applicable'] and not result['qualified']
    assert 'qualification_unknown' in result['reason']


@pytest.mark.parametrize('case',['valid-reuse','existing-debt','unknown','dishonest-lock'])
def test_entry_never_reroutes_received_or_unproved_locked_pair(monkeypatch,case):
    board,pair=fixture(extra=case=='dishonest-lock');before=copper_inventory(board)
    receiving_mocks(monkeypatch,pair,violations=['inherited debt'] if case=='existing-debt' else [])
    monkeypatch.setattr(route,'derive_coupled_pairs',lambda *a,**kw:[pair])
    monkeypatch.setattr(route,'_scheduled_coupled_pairs',lambda *a,**kw:
                        ([pair],[dict(name=pair['name'])]))
    if case=='unknown':
        monkeypatch.setattr(route,'_native_pair_completion',lambda *a,**kw:
            dict(complete=False,connected=None,reason='native_inventory_bounded'))
    def unexpected(*a,**kw):pytest.fail('preflight must not consume any routing-search budget')
    monkeypatch.setattr(route,'_future_pair_launch_reservations',unexpected)
    monkeypatch.setattr(route,'route_coupled_pair',unexpected)
    result=route.precision_route_board(board,board_path='',do_kelvin=False,
        existing_locked_nets={pair['p'],pair['n']} if case=='dishonest-lock' else (),
        _group_order_retry=False,verbose=False)
    assert copper_inventory(board)==before
    assert result['generated_item_count']==0 and result['n_new_locked_segments']==0
    if case=='valid-reuse':
        assert result['pairs_ok'] and not result['pairs']['refused']
        assert result['pairs']['routed'][0]['route_mode']=='preexisting-native-qualified'
        assert result['pairs']['routed'][0]['segments']==0
        assert set(result['locked_nets'])=={pair['p'],pair['n']}
        assert set(result['received_existing_pair_nets'])=={pair['p'],pair['n']}
    else:
        assert not result['pairs_ok'] and len(result['pairs']['refused'])==1
        assert result['received_existing_pair_nets']==[]


def test_connected_terminals_do_not_hide_disconnected_native_copper(monkeypatch):
    board,pair=fixture()
    item=pcbnew.PCB_TRACK(board);item.SetStart(pcbnew.VECTOR2I_MM(7.,15.))
    item.SetEnd(pcbnew.VECTOR2I_MM(8.,15.));item.SetWidth(pcbnew.FromMM(.25))
    item.SetLayer(pcbnew.F_Cu);item.SetNet(board.FindNet(pair['p']));board.Add(item)
    expected=copper_inventory(board)
    receiving_mocks(monkeypatch,pair)
    proof=route._native_pair_completion(board,pair)
    assert proof['connected'] is True
    assert proof['nets'][pair['p']]['disconnected_copper_uuids']==[item.m_Uuid.AsString()]
    result=route._preexisting_pair_receiving(board,pair,board_path='')
    assert result['applicable'] and not result['qualified']
    assert result['reason']=='existing_connected_pair_has_unowned_native_copper_islands'
    assert copper_inventory(board)==expected


def test_generic_residual_coordinator_receives_existing_pair_exclusion():
    import ast
    from pathlib import Path
    source=Path(route.__file__).with_name('cec_synth_pipeline.py')
    tree=ast.parse(source.read_text())
    assert any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
        and isinstance(node.func.value,ast.Name) and node.func.value.id=='_completed_route_nets'
        and node.func.attr=='update' and any(isinstance(child,ast.Constant)
            and child.value=='received_existing_pair_nets' for child in ast.walk(node))
        for node in ast.walk(tree))


def test_complete_pair_coupling_sees_inherited_uncoupled_branches(tmp_path):
    # The new short parallel pieces are perfect; the old long legs are not.
    from test_topology_candidate_qualification import board_fixture,track
    board=board_fixture();pair=dict(name='different',p='P',n='N',kind='can',width=.25,gap=.2)
    for net,y in [('P',5.),('N',8.)]:
        for index,x in enumerate((3.,23.)):
            fp=pcbnew.FOOTPRINT(board);fp.SetReference(net+str(index));board.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet(net))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.2,.2))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x,y));fp.Add(pad)
        track(board,net,y)
    before_ids={t.m_Uuid.AsString() for t in board.GetTracks()}
    created=[track(board,'P',15.),track(board,'N',15.45)]
    for item in created:item.SetEnd(pcbnew.VECTOR2I_MM(4.,item.GetEnd().y/1e6))
    new_ids={t.m_Uuid.AsString() for t in created}
    assert route._pair_coupling_summary(board,pair,new_ids)['coverage_pct']==100.
    assert route._pair_coupling_summary(board,pair)['coverage_pct']<10.
    path=tmp_path/'mixed-native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    # Earlier route obligations are mocked here only to reach the coupling
    # receiver. Its production native measurements are left intact.
    with patch.object(route.cec_fr,'synthesize_same_footprint_links',return_value={}), \
            patch.object(route.cec_fr,'owned_locked_nets_board',return_value={'P','N'}), \
            patch.object(route,'_pair_graph_geometry',return_value={'ok':True}), \
            patch.object(route,'_pair_transaction_detour',return_value={'ok':True}), \
            patch.object(route,'_pair_detour_failure_certificate',return_value={}), \
            patch('cec_pair_skew.from_board',return_value={'ok':True}):
        result=route._qualify_pair_candidate(board,pair,{},pair_pre_ids=before_ids,
            board_path=str(path),pair_avoid=(),endpoint_stations=[])
    assert result['physical_coupling_admission']['ok'] is False
    assert result['failure_certificate']['classification']==['insufficient_coupling']
    assert {t.m_Uuid.AsString() for t in board.GetTracks()}==before_ids

import pytest
import pcbnew
import cec_pair_skew as skew


@pytest.mark.parametrize('kind,limit',[('usb',3.81),('can',4.0)])
def test_same_existing_signoff_limit_at_boundary(kind,limit):
    assert skew.evaluate(kind,10+limit,10)['ok']
    assert not skew.evaluate(kind,10+limit+.00001,10)['ok']
    assert skew.evaluate(kind,10,10+limit)['ok']


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1])
def test_invalid_lengths_fail_closed(bad):
    assert not skew.evaluate('can',bad,1)['ok']


def test_individually_legal_legs_can_fail_whole_pair_skew():
    assert skew.evaluate('can',8,5)['ok']
    assert skew.evaluate('can',9,6)['ok']
    assert not skew.evaluate('can',17,11)['ok']


def test_saved_geometry_includes_previous_prefix_and_all_layers():
    board=pcbnew.BOARD()
    for name in ('arbitrary/high','arbitrary/low','unrelated'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    for name,length,layer,locked in [('arbitrary/high',8,pcbnew.F_Cu,True),
                                    ('arbitrary/high',9,pcbnew.B_Cu,False),
                                    ('arbitrary/low',11,pcbnew.B_Cu,False),
                                    ('unrelated',50,pcbnew.F_Cu,True)]:
        item=pcbnew.PCB_TRACK(board);item.SetNet(board.FindNet(name));item.SetLayer(layer)
        item.SetStart(pcbnew.VECTOR2I_MM(0,2));item.SetEnd(pcbnew.VECTOR2I_MM(length,2))
        item.SetLocked(locked);board.Add(item)
    result=skew.from_board(board,dict(kind='can',p='arbitrary/high',n='arbitrary/low'))
    assert result['skew_mm']==6 and not result['ok']


def test_precision_rolls_back_whole_pair_and_support_when_aggregate_skew_fails():
    from unittest.mock import patch
    import cec_precision_route as precision
    board=pcbnew.BOARD()
    for name in ('arbitrary/high','arbitrary/low','GND'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    pair=dict(name='arbitrary',kind='can',p='arbitrary/high',n='arbitrary/low',width=.2,gap=.2)
    def generated(*args,**kwargs):
        for name,length in ((pair['p'],17),(pair['n'],11),('GND',1)):
            item=pcbnew.PCB_TRACK(board);item.SetNet(board.FindNet(name));item.SetLayer(pcbnew.F_Cu)
            item.SetStart(pcbnew.VECTOR2I_MM(0,2));item.SetEnd(pcbnew.VECTOR2I_MM(length,2))
            item.SetWidth(pcbnew.FromMM(.2));board.Add(item)
        return dict(name=pair['name'],p=pair['p'],n=pair['n'],segments=2)
    with patch.object(precision,'derive_coupled_pairs',return_value=[pair]), \
         patch.object(precision,'_flow_through_pair_legs',return_value=None), \
         patch.object(precision,'_multidrop_pair_plan',return_value=None), \
         patch.object(precision,'route_coupled_pair',side_effect=generated), \
         patch.object(precision.cec_fr,'owned_locked_nets_board',return_value={pair['p'],pair['n']}), \
         patch.object(precision.cec_fr,'synthesize_same_footprint_links',return_value={}), \
         patch.object(precision,'_pair_graph_geometry',return_value={'ok':True}), \
         patch.object(precision,'_pair_transaction_detour',return_value={'ok':True}):
        report=precision.precision_route_board(board,board_path='unused',do_kelvin=False,verbose=False)
    assert not report['critical_routes_ok']
    refusal=report['pairs']['refused'][0]
    assert refusal['physical_skew_admission']['skew_mm']==6
    assert 'whole-pair copper skew' in refusal['refused']
    assert not list(board.GetTracks())

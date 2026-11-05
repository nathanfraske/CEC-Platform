"""A caller's narrowed middle-layer portfolio must stay narrowed when requested."""
import time
import pcbnew
import pytest
import cec_fr as fr
from test_lastmile import _board


@pytest.mark.parametrize('reverse',[False,True])
def test_strict_middle_domain_does_not_search_the_other_endpoint_layer(monkeypatch,reverse):
    board=_board([(8,8,'/RENAMED'),(12,8,'/RENAMED')],edge=(3,3,18,18))
    start,end=(8000000,8000000),(12000000,8000000)
    a,b={pcbnew.F_Cu},{pcbnew.B_Cu}
    if reverse:start,end,a,b=end,start,b,a
    # Test the scheduling decision independently of endpoint via geometry.
    # The existing barrel and native copper guards remain the actual callers'
    # responsibility and are not supplied as qualification by this test.
    monkeypatch.setattr(fr._fab,'board_profile_name',lambda b:None)
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:True)
    seen=[]
    def middle(b,s,t,width,layer,*args,**kwargs):
        seen.append(layer)
        return [(s,t)]
    monkeypatch.setattr(fr,'_guarded_lastmile_legs',middle)
    result=fr._lastmile_bridge(board,start,a,end,b,200000,
        board.GetNetcodeFromNetname('/RENAMED'),[pcbnew.B_Cu],200000,
        allow_maze=False,seat_limit=1,endpoint_handoffs=False,
        deadline_monotonic=time.monotonic()+2.)
    assert result and seen==[pcbnew.B_Cu]
    assert all(op[4]==pcbnew.B_Cu for op in result if op[0]=='trk')
    assert len([op for op in result if op[0]=='via'])==1


@pytest.mark.parametrize('value',[None,0,1,'false',[]])
def test_handoff_option_requires_an_explicit_boolean(value):
    board=_board([],edge=(0,0,20,20))
    with pytest.raises(ValueError,match='explicit_endpoint_handoff_policy_required'):
        fr._lastmile_bridge(board,(5000000,5000000),{0},(10000000,5000000),{2},
            200000,1,[2],200000,endpoint_handoffs=value)

"""Native, no-source-mutation craft preflight for generic route menus."""
import time
import pcbnew
import cec_route_quality as quality
from test_field_proposals import track,add_net,signature,proposal
from test_lastmile import _board


def test_canonical_proposal_cannot_backtrack_into_retained_copper():
    b=_board([],edge=(0,0,30,30));track(b,'/CONTROL',(10,10),(11,10))
    before=signature(b)
    result=quality.assess_proposed_route(b,[proposal('/CONTROL',(10,10),(15,10))])
    assert result['complete'] and result['ok'] is False
    assert result['issues'][0]['type']=='covered_backtrack'
    assert result['issues'][0]['proposed_track_indices']==[0]
    assert signature(b)==before


def test_new_path_internal_acute_join_is_rejected_before_native_emission():
    b=_board([],edge=(0,0,30,30));add_net(b,'/CONTROL')
    result=quality.assess_proposed_route(b,[proposal('/CONTROL',(10,10),(11,10)),
        proposal('/CONTROL',(11,10),(8,13))])
    assert result['ok'] is False and result['complete']
    assert result['issues'][0]['type']=='acute_backtrack'
    assert not list(b.GetTracks())


def test_alternative_canonical_elbow_passes_and_expired_evidence_stays_unknown():
    b=_board([],edge=(0,0,30,30));add_net(b,'/CONTROL')
    rows=[proposal('/CONTROL',(10,10),(12,10)),proposal('/CONTROL',(12,10),(14,12))]
    result=quality.assess_proposed_route(b,rows)
    assert result['complete'] and result['ok'] is True
    assert not list(b.GetTracks())
    late=quality.assess_proposed_route(b,rows,deadline=time.monotonic()-1)
    assert late['ok'] is None and not late['complete']


def test_scope_does_not_blame_inherited_other_net_defect():
    b=_board([],edge=(0,0,30,30));track(b,'/OTHER',(10,10),(11,10))
    track(b,'/OTHER',(10,10),(15,10));add_net(b,'/CONTROL')
    result=quality.assess_proposed_route(b,[proposal('/CONTROL',(10,15),(15,15))])
    assert result['complete'] and result['ok'] is True

"""The screenshot's backwards kink must fail on every native copper layer."""
import pytest
import cec_route_quality as quality
import cec_dashboard as dashboard
import cec_fab_review_regression as review
from test_fab_review_regression import _summary, _probes
from test_route_junction_serial_bridges import native_board


POINTS=[(0,0),(4000000,0),(4200000,200000),(4000000,400000),(6000000,2400000)]


@pytest.mark.parametrize('face',range(0,64,2))
def test_every_copper_face_proposal_and_final_consumers_reject_kink(face):
    whole=native_board(POINTS,face,0,False)
    whole.SetCopperLayerCount(32)
    report=quality.analyze_board(whole)
    # Ordinary/advisory intermediate progress is not a final clean result.
    assert report['ok'] and report['reverse_diagonal_jog_count']>0
    assert not report['craft_ok']
    assert all(row['layer']==whole.GetLayerName(face)for row in report['issues'])
    probes=_probes();probes['route_quality']=report
    verdict=review.compare_to_baseline(_summary(),probes,'abc')
    assert not verdict['ok'] and verdict['failed_terms']==['route_craft']
    gates=dict(ok=True,kelvin_ok=True,drc=0,unconnected=0,
        foreign=dict(status='na'),route_sanity=report)
    assert dashboard._verdict(gates,dict(ok=False))==('FAILED',['route-craft'])

    retained=native_board(POINTS[:3],face,0,False)
    retained.SetCopperLayerCount(32)
    before=[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.IsLocked())
        for t in retained.GetTracks()]
    def shifted(p):return [p[0]+43000000,p[1]-17000000]
    proposed=[dict(net='/renamed_signal',layer=face,width_nm=200000,
        start_nm=shifted(a),end_nm=shifted(b))for a,b in zip(POINTS[2:],POINTS[3:])]
    gate=quality.assess_proposed_route(retained,proposed)
    assert gate['complete'] and gate['ok'] is False,gate
    assert any(row['type']=='reverse_diagonal_jog'for row in gate['issues'])
    assert all(row['proposed_track_indices']for row in gate['issues'])
    assert before==[(t.m_Uuid.AsString(),tuple(t.GetStart()),tuple(t.GetEnd()),t.IsLocked())
        for t in retained.GetTracks()]
    assert gate['board_mutated']is False

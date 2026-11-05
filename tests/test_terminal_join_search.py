"""A short rejected diagonal is not proof that a terminal cannot escape."""
import math
import pcbnew
import pytest
import cec_terminal_join_search as joins
import cec_route_quality as craft
import cec_field_coupling as field
from test_field_proposals import track
from test_lastmile import _board


@pytest.mark.parametrize('angle',range(0,360,90))
def test_chamfer_variants_restore_style_without_moving_endpoints_or_source(angle):
    def point(x,y):
        a=math.radians(angle);x,y=x-10,y-10
        return pcbnew.VECTOR2I(round((10+x*math.cos(a)-y*math.sin(a))*1e6),
            round((10+x*math.sin(a)+y*math.cos(a))*1e6))
    net='/renamed/control/'+str(angle);b=_board([(5,5,net)])
    old=track(b,net,(10,10),(11.6,10),width=.2)
    if angle:old.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(-angle,pcbnew.DEGREES_T))
    ops=[('trk',point(10,10),point(10.1,10.1),200000,pcbnew.F_Cu),
        ('trk',point(10.1,10.1),point(10.1,12),200000,pcbnew.F_Cu)]
    before=field._field_snapshot_inventory(b);start,end=tuple(ops[0][1]),tuple(ops[-1][2])
    def validate(candidate):
        proof=craft.assess_proposed_route(b,[dict(net=net,layer=o[4],start_nm=list(o[1]),
            end_nm=list(o[2]),width_nm=o[3]) for o in candidate])
        return proof['ok'] is True and proof['complete'] is True
    assert not validate(ops)
    assert joins.accept(b,ops,net_code=b.GetNetcodeFromNetname(net),clearance_nm=200000,validate=validate)
    assert tuple(ops[0][1])==start and tuple(ops[-1][2])==end and validate(ops)
    assert all(o[3:]==(200000,pcbnew.F_Cu) for o in ops)
    assert before==field._field_snapshot_inventory(b)


def test_failed_complete_validation_never_modifies_proposal_or_native_board():
    b=_board([(5,5,'/control')]);before=field._field_snapshot_inventory(b)
    ops=[('trk',pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(5.1,5.1),200000,pcbnew.F_Cu)]
    prior=list(ops)
    assert not joins.accept(b,ops,net_code=b.GetNetcodeFromNetname('/control'),
        clearance_nm=200000,validate=lambda candidate:False)
    assert ops==prior and before==field._field_snapshot_inventory(b)


def test_join_rewrite_never_changes_provisional_barrels_or_bypasses_foreign_copper():
    b=_board([(5,5,'/control')]);b.Add(pcbnew.NETINFO_ITEM(b,'/foreign'))
    # Every short join alternative collides with this actual foreign copper.
    track(b,'/foreign',(9,10.05),(11,10.05),width=.6)
    barrel=('via',pcbnew.VECTOR2I_MM(10.1,10.1),.3,.6)
    ops=[('trk',pcbnew.VECTOR2I_MM(10,10),pcbnew.VECTOR2I_MM(10.1,10.1),200000,pcbnew.F_Cu),barrel]
    before=list(ops);calls=[]
    assert all(candidate[-1] is barrel for candidate in joins.variants(ops))
    assert not joins.accept(b,ops,net_code=b.GetNetcodeFromNetname('/control'),
        clearance_nm=200000,validate=lambda candidate:calls.append(candidate) or True)
    assert ops==before and not calls


@pytest.mark.parametrize('span',[0,True,1000001])
def test_terminal_rewrite_is_explicitly_bounded(span):
    with pytest.raises(ValueError):joins.variants([],max_span_nm=span)


def test_expired_verification_does_not_call_guards_or_mutate_proposal(monkeypatch):
    b=_board([(5,5,'/control')]);prior=field._field_snapshot_inventory(b)
    ops=[('trk',pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(5.1,5.1),200000,pcbnew.F_Cu)]
    original=list(ops);calls=[]
    assert not joins.accept(b,ops,net_code=b.GetNetcodeFromNetname('/control'),
        clearance_nm=200000,validate=lambda plan:calls.append(plan) or True,deadline=0.)
    assert not calls and ops==original and prior==field._field_snapshot_inventory(b)


def test_late_positive_verdict_cannot_outlive_its_lease(monkeypatch):
    b=_board([(5,5,'/control')]);prior=field._field_snapshot_inventory(b)
    ops=[('trk',pcbnew.VECTOR2I_MM(5,5),pcbnew.VECTOR2I_MM(5.1,5.1),200000,pcbnew.F_Cu)]
    original=list(ops);clock=[1.]
    monkeypatch.setattr(joins.time,'monotonic',lambda:clock[0])
    def validate(plan):clock[0]=3.;return True
    assert not joins.accept(b,ops,net_code=b.GetNetcodeFromNetname('/control'),
        clearance_nm=200000,validate=validate,deadline=2.)
    assert ops==original and prior==field._field_snapshot_inventory(b)


@pytest.mark.parametrize('deadline',[True,'soon',float('nan'),float('inf')])
def test_invalid_verification_lease_refused(deadline):
    b=_board([(5,5,'/control')])
    with pytest.raises(ValueError,match='verification_lease'):
        joins.accept(b,[('via',(5000000,5000000),.3,.6)],net_code=1,
            clearance_nm=200000,validate=lambda p:True,deadline=deadline)

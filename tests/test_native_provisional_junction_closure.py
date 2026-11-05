import math
import pytest
import pcbnew
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from test_native_pending_joint_cohort import row
from cec_native_branch_forest import plan


def source(rotation=0,shift=(0,0),defect=None):
    b=_board([(10,20,'RENAMED_SUPPLY'),(40,20,'RENAMED_SUPPLY'),
        (20,30,'RENAMED_SUPPLY'),(20,20,'OTHER')])
    edges=[track(b,'RENAMED_SUPPLY',(10,20),(20,20)),
        track(b,'RENAMED_SUPPLY',(20,20),(30,20)),
        track(b,'RENAMED_SUPPLY',(20,20),(20,30)),
        track(b,'RENAMED_SUPPLY',(30,20),(40,20))]
    if defect=='width':edges[-1].SetWidth(250000)
    elif defect=='lock':edges[-1].SetLocked(True)
    elif defect=='owner':
        g=pcbnew.PCB_GROUP(b);g.SetName('OTHER_OWNER');b.Add(g);g.AddItem(edges[-1])
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation*90,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(*shift))
    return b,edges


def options(edges):
    return dict(clearance_for=lambda n:200000,allow_literal_body_cohort=True,
        provisional_reconstruction_track_uuids=[force._uid(t) for t in edges],
        collapse_retained_native_ports=True,close_provisional_native_junctions=True)


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('shift',[(0,0),(5,-3)])
def test_provisional_supply_junction_closes_to_actual_source_terminals(rotation,shift):
    b,edges=source(rotation,shift)
    before=[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in b.GetTracks()]
    _,forests,proof=plan(b,[row(edges[0])],**options(edges))
    assert len(forests)==1 and len(forests[0]['route_rows'])==2
    assert set(proof['exact_retired_uuids'])=={force._uid(t) for t in edges}
    assert len(forests[0]['external_ports_nm'])==3
    closed=forests[0]['closed_provisional_junctions']
    assert closed and all(not c['external_port_or_current_authority'] for c in closed)
    assert before==[(force._uid(t),tuple(t.GetStart()),tuple(t.GetEnd()),t.GetWidth()) for t in b.GetTracks()]
    assert proof['saved_whole_source_current_receiving_required'] and not proof['current_qualified']


def test_default_does_not_normalize_declared_supply_junctions():
    b,edges=source()
    settings=options(edges);settings['close_provisional_native_junctions']=False
    with pytest.raises(ValueError,match='retained_port_has_missing_or_ambiguous_actual_material'):
        plan(b,[row(edges[0])],**settings)


@pytest.mark.parametrize('defect',['width','lock','owner'])
def test_same_net_pending_declaration_cannot_cross_source_ownership_boundaries(defect):
    b,edges=source(defect=defect)
    with pytest.raises(ValueError,match='branch_width_lock_group_or_current_allocation_boundary'):
        plan(b,[row(edges[0])],**options(edges))


@pytest.mark.parametrize('bad',[None,1,'yes'])
def test_opt_in_is_explicit_and_requires_native_port_receiving(bad):
    b,edges=source();settings=options(edges);settings['close_provisional_native_junctions']=bad
    with pytest.raises(ValueError):plan(b,[row(edges[0])],**settings)


@pytest.mark.parametrize('bound',[True,None,0,33,math.inf])
def test_work_bounds_remain_finite_independent_of_ownership(bound):
    b,edges=source();settings=options(edges)
    with pytest.raises(ValueError):plan(b,[row(edges[0])],maximum_members=bound,**settings)
    with pytest.raises(ValueError):plan(b,[row(edges[0])],maximum_ports=bound,**settings)


def test_bigger_work_scope_does_not_grant_other_owner_retirement():
    b,edges=source(defect='owner')
    with pytest.raises(ValueError,match='branch_width_lock_group_or_current_allocation_boundary'):
        plan(b,[row(edges[0])],maximum_members=32,maximum_ports=32,**options(edges))


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('shift',[(0,0),(4,-2)])
def test_actual_body_closure_reclassifies_newly_owned_provisional_only_endpoint(rotation,shift):
    b=_board([(10,20,'SUPPLY'),(40,20,'SUPPLY'),(20,30,'SUPPLY'),
        (40,30,'SUPPLY'),(20,20,'OTHER')])
    edges=[track(b,'SUPPLY',(10,20),(40,20)),track(b,'SUPPLY',(20,20),(20,30)),
        track(b,'SUPPLY',(30,20),(30,30)),track(b,'SUPPLY',(30,30),(40,30))]
    for i in [*b.GetFootprints(),*b.GetTracks()]:
        i.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation*90,pcbnew.DEGREES_T))
        i.Move(pcbnew.VECTOR2I_MM(*shift))
    # The third source edge is not pending. Literal body-contact closure
    # adopts it later; its old retained-endpoint classification must then be
    # invalidated before the tree is formed.
    settings=options(edges)
    settings['provisional_reconstruction_track_uuids']=[force._uid(edges[i]) for i in (0,1,3)]
    _,forests,proof=plan(b,[row(edges[1])],**settings)
    assert set(proof['exact_retired_uuids'])=={force._uid(t) for t in edges}
    assert len(forests[0]['external_ports_nm'])==4 and len(forests[0]['route_rows'])==3
    internal=list(edges[3].GetStart())
    assert internal not in forests[0]['external_ports_nm']
    assert any(c['at_nm']==internal for c in forests[0]['closed_provisional_junctions'])
    settings=options(edges);settings['collapse_retained_native_ports']=False
    with pytest.raises(ValueError):plan(b,[row(edges[0])],**settings)

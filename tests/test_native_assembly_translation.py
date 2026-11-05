"""Exact paired feasibility must run before a placement proposal is saved."""
import copy
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_assembly_envelope as assembly
from cec_field_coupling import _field_snapshot_inventory


def board_with_body(ref, key, at):
    board=pcbnew.BOARD()
    for a,b in zip([(0,0),(20,0),(20,20),(0,20)],[(20,0),(20,20),(0,20),(0,0)]):
        edge=pcbnew.PCB_SHAPE(board);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetWidth(pcbnew.FromMM(.05))
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetFPID(pcbnew.LIB_ID('arbitrary',key))
    fp.SetPosition(pcbnew.VECTOR2I_MM(*at))
    points=[(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5),(-.5,-.5)]
    for a,b in zip(points,points[1:]):
        edge=pcbnew.PCB_SHAPE(fp);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.F_CrtYd);edge.SetWidth(pcbnew.FromMM(.05))
        edge.SetStart(pcbnew.VECTOR2I_MM(at[0]+a[0],at[1]+a[1]))
        edge.SetEnd(pcbnew.VECTOR2I_MM(at[0]+b[0],at[1]+b[1]));fp.Add(edge)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
    pad.SetPosition(fp.GetPosition());fp.Add(pad);board.Add(fp)
    return board


def fixture(receiver='carrier'):
    moving=board_with_body('arbitrary-mover','low-package',(5,5))
    peer=board_with_body('arbitrary-reservoir','storage-package',
                         (8,5) if receiver=='carrier' else (12,5))
    contract=dict(transform=[1,0,0,1,0,0] if receiver=='carrier' else [-1,0,0,1,20,0],
        gap_mm=[21.5,22.5],xy_allowance_each_mm=.15,body_clearance_mm=.5,
        mating_pairs=[],envelopes={
            'low-package':dict(height_max_mm=3,basis='design_allocation',evidence='fixture'),
            'storage-package':dict(height_max_mm=17.2,diameter_max_mm=2,vent_min_mm=3,
                basis='design_allocation',evidence='fixture')})
    return moving,peer,contract


@pytest.mark.parametrize('receiver',['carrier','cover'])
@pytest.mark.parametrize('delta',[(0,0),(-1,0),(1.25,0)])
def test_exact_both_tolerances_and_real_flip_are_preserved(receiver,delta):
    moving,peer,contract=fixture(receiver);original=copy.deepcopy(contract)
    before=_field_snapshot_inventory(moving);other=_field_snapshot_inventory(peer)
    result=assembly.native_translation_check(moving,peer,contract,
        {'arbitrary-mover':delta},receiver=receiver)
    assert result['ok'] is (delta!=(1.25,0))
    if not result['ok']:
        assert any(v['kind']=='opposing_bodies' for v in result['violations'])
    assert result['source_and_peer_unchanged'] and not result['release_authority']
    assert _field_snapshot_inventory(moving)==before and _field_snapshot_inventory(peer)==other
    assert contract==original and tuple(moving.FindFootprintByReference('arbitrary-mover').GetPosition())==(5000000,5000000)


def test_unknown_body_cannot_disappear_from_the_probe():
    moving,peer,contract=fixture();contract['envelopes'].pop('low-package')
    result=assembly.native_translation_check(moving,peer,contract,{'arbitrary-mover':(0,0)})
    assert not result['ok'] and result['missing'] and result['source_and_peer_unchanged']


def test_exception_after_move_rolls_back_exact_native_pose(monkeypatch):
    moving,peer,contract=fixture();before=_field_snapshot_inventory(moving)
    def broken(*args):
        assert tuple(moving.FindFootprintByReference('arbitrary-mover').GetPosition())==(6000000,5000000)
        raise RuntimeError('independent native gate failed')
    monkeypatch.setattr(assembly,'evaluate_boards',broken)
    with pytest.raises(RuntimeError,match='independent native'):
        assembly.native_translation_check(moving,peer,contract,{'arbitrary-mover':(1,0)})
    assert _field_snapshot_inventory(moving)==before
    assert tuple(moving.FindFootprintByReference('arbitrary-mover').GetPosition())==(5000000,5000000)


def test_expired_native_gate_cannot_admit_and_still_restores(monkeypatch):
    import time
    moving,peer,contract=fixture();before=_field_snapshot_inventory(moving);now=[0.]
    monkeypatch.setattr(time,'monotonic',lambda:now[0]);evaluate=assembly.evaluate_boards
    def slow(*args):
        answer=evaluate(*args);now[0]=3.;return answer
    monkeypatch.setattr(assembly,'evaluate_boards',slow)
    result=assembly.native_translation_check(moving,peer,contract,{'arbitrary-mover':(0,0)})
    assert not result['ok'] and result['timed_out'] and result['source_and_peer_unchanged']
    assert _field_snapshot_inventory(moving)==before


@pytest.mark.parametrize('bad',[{}, {'unknown':(0,0)}, {'arbitrary-mover':(True,0)},
    {'arbitrary-mover':(float('nan'),0)}, {'arbitrary-mover':(0,)}, {'arbitrary-mover':(2001,0)}])
def test_invalid_translation_identity_or_scope_refuses_before_mutation(bad):
    moving,peer,contract=fixture();before=_field_snapshot_inventory(moving)
    with pytest.raises(ValueError):assembly.native_translation_check(moving,peer,contract,bad)
    assert _field_snapshot_inventory(moving)==before


@pytest.mark.parametrize('timeout',[True,0,11,float('nan')])
def test_invalid_deadline_is_not_unbounded(timeout):
    moving,peer,contract=fixture()
    with pytest.raises(ValueError):assembly.native_translation_check(
        moving,peer,contract,{'arbitrary-mover':(0,0)},timeout_s=timeout)


@pytest.mark.parametrize('receiver',['carrier','cover'])
@pytest.mark.parametrize('policy',['together','fixed','opposed'])
def test_coordinated_peer_poses_use_each_native_frame_and_full_envelope(receiver,policy):
    moving,peer,contract=fixture(receiver)
    before=[_field_snapshot_inventory(b) for b in (moving,peer)]
    signed=1.25 if receiver=='carrier' else -1.25
    delta={'together':signed,'fixed':0.,'opposed':-signed}[policy]
    result=assembly.native_translation_check(moving,peer,contract,
        {'arbitrary-mover':(1.25,0)},receiver=receiver,
        peer_translations={'arbitrary-reservoir':(delta,0)})
    assert result['ok'] is (policy=='together')
    assert result['source_and_peer_unchanged'] and not result['release_authority']
    assert before==[_field_snapshot_inventory(b) for b in (moving,peer)]


@pytest.mark.parametrize('receiver',['carrier','cover'])
@pytest.mark.parametrize('peer_dx',[-1.,0.,1.])
def test_identically_named_mating_refs_remain_distinct_and_numbered(receiver,peer_dx):
    moving=board_with_body('same-ref','low-package',(5,5))
    peer=board_with_body('same-ref','low-package',(15,5))
    contract=dict(transform=[-1,0,0,1,20,0],gap_mm=[21.5,22.5],
        xy_allowance_each_mm=.15,body_clearance_mm=.5,mating_pairs=[['same-ref','same-ref']],
        envelopes={'low-package':dict(height_max_mm=3,basis='design_allocation',evidence='fixture')})
    before=[_field_snapshot_inventory(b) for b in (moving,peer)]
    result=assembly.native_translation_check(moving,peer,contract,
        {'same-ref':(1.,0.)},receiver=receiver,peer_translations={'same-ref':(peer_dx,0.)})
    assert result['ok'] is (peer_dx==-1.)
    assert before==[_field_snapshot_inventory(b) for b in (moving,peer)]


@pytest.mark.parametrize('bad',[[], {'unknown':(0,0)}, {'arbitrary-reservoir':(False,0)},
    {'arbitrary-reservoir':(float('inf'),0)}, {'arbitrary-reservoir':(0,)},
    {'arbitrary-reservoir':(2001,0)}, {str(i):(0,0) for i in range(65)}])
def test_bad_peer_scope_is_rejected_before_either_board_moves(bad):
    moving,peer,contract=fixture();before=[_field_snapshot_inventory(b) for b in (moving,peer)]
    with pytest.raises(ValueError):
        assembly.native_translation_check(moving,peer,contract,
            {'arbitrary-mover':(1,0)},peer_translations=bad)
    assert before==[_field_snapshot_inventory(b) for b in (moving,peer)]


def test_failure_after_both_boards_move_rolls_back_both_exactly(monkeypatch):
    moving,peer,contract=fixture();before=[_field_snapshot_inventory(b) for b in (moving,peer)]
    def broken(*args):
        assert tuple(moving.FindFootprintByReference('arbitrary-mover').GetPosition())==(6000000,5000000)
        assert tuple(peer.FindFootprintByReference('arbitrary-reservoir').GetPosition())==(9000000,5000000)
        raise RuntimeError('paired transaction failed')
    monkeypatch.setattr(assembly,'evaluate_boards',broken)
    with pytest.raises(RuntimeError,match='paired transaction'):
        assembly.native_translation_check(moving,peer,contract,
            {'arbitrary-mover':(1,0)},peer_translations={'arbitrary-reservoir':(1,0)})
    assert before==[_field_snapshot_inventory(b) for b in (moving,peer)]


def test_deadline_between_boards_rolls_back_the_partial_move(monkeypatch):
    import time
    moving,peer,contract=fixture();before=[_field_snapshot_inventory(b) for b in (moving,peer)]
    times=iter([0.,0.,3.])
    monkeypatch.setattr(time,'monotonic',lambda:next(times,3.))
    result=assembly.native_translation_check(moving,peer,contract,
        {'arbitrary-mover':(1,0)},peer_translations={'arbitrary-reservoir':(1,0)})
    assert not result['ok'] and result['timed_out']
    assert result['source_and_peer_unchanged']
    assert before==[_field_snapshot_inventory(b) for b in (moving,peer)]

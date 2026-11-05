"""Selected immutable owners are assignment witnesses, not movable modules."""
import copy

import pcbnew
import pytest

import test_cell_escape_replan as source_fixture
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row


def fixture(monkeypatch, prefix='renamed', angle=0, flipped=False, locked=False):
    board, poses, owner, cap = source_fixture.fixture(monkeypatch, prefix)
    ground = owner.FindPadByNumber('2')
    ground.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    ground.SetDrillSize(pcbnew.VECTOR2I(200000,200000))
    ground.SetLayerSet(pcbnew.LSET.AllCuMask())
    aperture = pcbnew.PAD(owner); aperture.SetNumber('')
    aperture.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    aperture.SetDrillSize(pcbnew.VECTOR2I(300000,300000))
    aperture.SetSize(pcbnew.VECTOR2I(300000,300000)); owner.Add(aperture)
    owner.SetOrientationDegrees(angle)
    if flipped:
        owner.Flip(owner.GetPosition(), False)
        cap.Flip(cap.GetPosition(), False)
    owner.SetLocked(locked)
    poses[owner.GetReference()] = [owner.GetPosition().x/1e6, owner.GetPosition().y/1e6,
                                   owner.GetOrientationDegrees()]
    poses[cap.GetReference()] = [cap.GetPosition().x/1e6+.1, cap.GetPosition().y/1e6,
                                 cap.GetOrientationDegrees()]
    return board, poses, owner, cap


@pytest.mark.parametrize('prefix,angle,flipped,locked', [
    ('renamed_A',0,False,False), ('different_labels',90,False,True),
    ('backface',180,True,False), ('locked_backface',270,True,True)])
def test_selected_stationary_module_has_no_motion_cut_or_unlock_authority(monkeypatch, prefix, angle, flipped, locked):
    board, poses, owner, cap = fixture(monkeypatch,prefix,angle,flipped,locked)
    before = row._source_binding(board)
    proposal = escape.prepare(board, poses, board_hint='opaque-board')
    context = proposal['stationary_bypass_owner_context'][owner.GetReference()]
    assert not context['motion_authority'] and not context['cut_authority'] and not context['unlock_authority']
    assert context['source_locked'] == locked
    assert owner.GetReference() not in proposal['row_plan']['target_poses']
    assert owner.GetReference() not in proposal['device_contracts']
    assert owner.GetReference() in proposal['stationary_device_owners']
    assert row._source_binding(board) == before
    original = (tuple(owner.GetPosition()), owner.GetOrientationDegrees(), owner.IsLocked(),
                owner.IsFlipped(), [(escape.force._uid(p),tuple(p.GetPosition()),p.GetAttribute(),p.GetDrillSize().x) for p in owner.Pads()])
    escape.apply_private(board, proposal)
    actual = (tuple(owner.GetPosition()), owner.GetOrientationDegrees(), owner.IsLocked(),
              owner.IsFlipped(), [(escape.force._uid(p),tuple(p.GetPosition()),p.GetAttribute(),p.GetDrillSize().x) for p in owner.Pads()])
    assert actual == original


def test_moving_through_hole_owner_still_refuses(monkeypatch):
    board, poses, owner, cap = fixture(monkeypatch)
    poses[owner.GetReference()][0] += .1
    with pytest.raises(ValueError, match='native_surface_cell'):
        escape.prepare(board, poses, board_hint='opaque-board')


@pytest.mark.parametrize('damage', ['pad', 'pose', 'lock', 'proposal'])
def test_source_or_proposal_tamper_refuses_independent_replay(monkeypatch, damage):
    board, poses, owner, cap = fixture(monkeypatch)
    proposal = escape.prepare(board, poses, board_hint='opaque-board')
    if damage == 'pad':
        owner.FindPadByNumber('1').SetSize(pcbnew.VECTOR2I(600000,600000))
    elif damage == 'pose':
        owner.SetPosition(owner.GetPosition()+pcbnew.VECTOR2I(1,0))
    elif damage == 'lock':
        owner.SetLocked(True)
    else:
        proposal = copy.deepcopy(proposal)
        proposal['stationary_bypass_owner_context'][owner.GetReference()]['unlock_authority'] = True
    with pytest.raises(ValueError):
        escape.apply_private(board, proposal)


@pytest.mark.parametrize('assignment', ['missing', 'unknown_owner', 'wrong_pin', 'wrong_net'])
def test_missing_or_unknown_source_assignment_never_creates_context(monkeypatch, assignment):
    board, poses, owner, cap = fixture(monkeypatch)
    req = dict(ref=owner.GetReference(), pin='5', rail='RAIL', return_rail='GND')
    if assignment == 'unknown_owner': req['ref'] = 'unknown'
    elif assignment == 'wrong_pin': req['pin'] = 'nonexistent'
    elif assignment == 'wrong_net': req['rail'] = 'unknown'
    assigned = {} if assignment == 'missing' else {'selected':dict(cap_ref=cap.GetReference(), requirement=req)}
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a, **kw:dict(assigned=assigned))
    with pytest.raises(ValueError):
        escape.prepare(board, poses, board_hint='opaque-board')

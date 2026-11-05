"""A blocking support need not carry the net whose pin it obstructs."""
import hashlib

import pcbnew
import pytest

import cec_certificate_repair as repair
import cec_fixed_pofv_mobility as fixed
import cec_support_motion as motion
from test_support_motion import fixture


def board_and_target(tmp_path, *, offset=(0, 0), back=False, angle=0,
                     same_net=False, via=False):
    board = fixture(offset=offset, back=back)
    owner = board.FindFootprintByReference('SUPPORT')
    owner.SetReference('UNRELATED_PASSIVE')
    owner.SetOrientationDegrees(angle)
    rail = pcbnew.NETINFO_ITEM(board, '/DIFFERENT_RAIL')
    ground = pcbnew.NETINFO_ITEM(board, '/DIFFERENT_RETURN')
    board.Add(rail)
    board.Add(ground)
    pads = list(owner.Pads())
    if not same_net:
        pads[0].SetNet(rail)
        pads[1].SetNet(ground)
    if via:
        props = board.GetProperties()
        props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
        board.SetProperties(props)
        settings = board.GetDesignSettings()
        settings.m_ViasMinSize = pcbnew.FromMM(.5)
        settings.m_MinViaAnnularWidth = pcbnew.FromMM(.1)
        item = pcbnew.PCB_VIA(board)
        item.SetPosition(pads[1].GetPosition())
        item.SetWidth(pcbnew.FromMM(.35))
        item.SetDrill(pcbnew.FromMM(.25))
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetNet(pads[1].GetNet())
        item.SetLocked(True)
        board.Add(item)
    source = tmp_path / 'foreign.kicad_pcb'
    pcbnew.SaveBoard(str(source), board)
    target = repair.asdict(repair.FootprintRepairTarget(
        ref=owner.GetReference(), target_net='/RENAMED', endpoint_ref='PEER',
        endpoint_pad='1', endpoint_x_mm=23.5+offset[0], endpoint_y_mm=20+offset[1],
        hit_count=1, distance_mm=3.5, priority=(0,), motion='away_from_endpoint'))
    return board, source, target


@pytest.mark.parametrize('offset,back,angle', [
    ((0, 0), False, 0), ((17, -8), True, 0),
    ((0, 0), False, 90), ((17, -8), True, 270)])
def test_foreign_blocker_has_bounded_native_geometry_menu(tmp_path, offset, back, angle):
    board, source, target = board_and_target(tmp_path, offset=offset, back=back, angle=angle)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    rows = repair._occupancy_relocation_candidates(str(source), target, limit=7,
                                                   support_limits=motion.limits())
    assert len(rows) == 7
    assert all(row['generator'] == 'occupancy_away_field' for row in rows)
    assert all('occupancy_score' in row for row in rows)
    domain = motion.capture(board, target, motion.limits())
    assert all(motion.evaluate(domain, row)['ok'] for row in rows)
    assert rows == repair._occupancy_relocation_candidates(str(source), target, limit=7,
                                                           support_limits=motion.limits())
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_toward_endpoint_still_requires_electrical_membership(tmp_path):
    board, source, target = board_and_target(tmp_path)
    target['motion'] = 'toward_endpoint'
    assert repair._occupancy_relocation_candidates(str(source), target) == []


def test_connected_support_keeps_endpoint_seat_generator(tmp_path):
    board, source, target = board_and_target(tmp_path, same_net=True)
    target['motion'] = 'toward_endpoint'
    rows = repair._occupancy_relocation_candidates(str(source), target, limit=7,
                                                   support_limits=motion.limits())
    assert len(rows) == 7
    assert all(row['generator'] == 'occupancy_endpoint_ring' for row in rows)


def test_foreign_owner_fixed_via_domain_is_not_bypassed(tmp_path):
    board, source, target = board_and_target(tmp_path, via=True)
    assert fixed.constraints(board, [target['ref']])
    before = source.read_bytes()
    rows = repair._occupancy_relocation_candidates(str(source), target, limit=512,
                                                   support_limits=motion.limits())
    assert any(row['generator'] == 'fixed_local_via_domain' for row in rows)
    assert all(fixed.evaluate(board, target, row)['ok'] for row in rows)
    assert source.read_bytes() == before


@pytest.mark.parametrize('protection', ['locked', 'policy'])
def test_foreign_blocker_keeps_component_immutability(tmp_path, protection):
    board, source, target = board_and_target(tmp_path)
    policy = motion.limits()
    if protection == 'locked':
        owner = board.FindFootprintByReference(target['ref'])
        owner.SetLocked(True)
        pcbnew.SaveBoard(str(source), board)
    else:
        policy = motion.limits(immutable_refs=[target['ref']])
    assert repair._occupancy_relocation_candidates(str(source), target,
                                                   support_limits=policy) == []

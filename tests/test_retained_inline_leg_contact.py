"""Retained partial-chain contact schedules work; it never qualifies a pair."""
from unittest.mock import patch
import time
import pcbnew
import pytest
import cec_precision_route as route


PAIR = dict(name='ANY_LINK', p='P', n='N', width=.2, gap=.3)
LEGS = [((5, 10), (10, 10), (5, 10.5), (10, 10.5)),
        ((10, 10), (20, 10), (10, 10.5), (20, 10.5))]


def fixture(connected=('P', 'N'), face=pcbnew.F_Cu):
    b = pcbnew.BOARD()
    for name in ('P', 'N'):
        b.Add(pcbnew.NETINFO_ITEM(b, name))
    for index, x in enumerate((5, 10, 20)):
        fp = pcbnew.FOOTPRINT(b); fp.SetReference('renamed_' + str(index)); b.Add(fp)
        for number, net, y in (('7', 'P', 10), ('9', 'N', 10.5)):
            pad = pcbnew.PAD(fp); pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(.4, .3)); pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            layers = pcbnew.LSET(); layers.AddLayer(face)
            pad.SetLayerSet(layers); pad.SetNetCode(b.GetNetcodeFromNetname(net)); fp.Add(pad)
    for net, y in (('P', 10), ('N', 10.5)):
        if net not in connected: continue
        t = pcbnew.PCB_TRACK(b); t.SetLayer(face); t.SetNetCode(b.GetNetcodeFromNetname(net))
        t.SetStart(pcbnew.VECTOR2I_MM(5, y)); t.SetEnd(pcbnew.VECTOR2I_MM(10, y)); t.SetWidth(200000)
        b.Add(t)
    return b, {t.m_Uuid.AsString() for t in b.GetTracks()}


@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_exact_saved_contact_is_not_physical_or_release_qualification(face):
    b, retained = fixture(face=face)
    result = route._retained_inline_leg_contact(b, PAIR, LEGS[0], retained)
    assert result['complete'] and result['connected']
    assert not result['physical_qualified'] and not result['release_authority']
    assert result['whole_pair_physical_receiving_still_required']
    assert not route._retained_inline_leg_contact(b, PAIR, LEGS[1], retained)['connected']


@pytest.mark.parametrize('connected', [(), ('P',), ('N',)])
def test_both_real_members_must_be_connected(connected):
    b, retained = fixture(connected)
    result = route._retained_inline_leg_contact(b, PAIR, LEGS[0], retained)
    assert result['complete'] and not result['connected']


def test_new_or_foreign_or_noncontact_copper_cannot_borrow_retained_authority():
    b, retained = fixture()
    assert not route._retained_inline_leg_contact(b, PAIR, LEGS[0], set())['connected']
    t = next(t for t in b.GetTracks() if t.GetNetname() == 'N')
    t.SetNetCode(b.GetNetcodeFromNetname('P'))
    assert not route._retained_inline_leg_contact(b, PAIR, LEGS[0], retained)['connected']
    t.SetNetCode(b.GetNetcodeFromNetname('N')); t.Move(pcbnew.VECTOR2I_MM(0, .8))
    assert not route._retained_inline_leg_contact(b, PAIR, LEGS[0], retained)['connected']


def test_expired_or_ambiguous_or_inventory_unknown_contact_is_not_skip_credit():
    b, retained = fixture()
    assert not route._retained_inline_leg_contact(b, PAIR, LEGS[0], retained,
        deadline=time.monotonic()-1)['complete']
    assert not route._retained_inline_leg_contact(b, PAIR, LEGS[0], retained, max_items=1)['complete']
    fp = next(iter(b.GetFootprints())); pad = pcbnew.PAD(fp)
    source = next(p for f in b.GetFootprints() for p in f.Pads()
                  if p.GetNetname() == 'P' and tuple(p.GetPosition()) == (5000000,10000000))
    pad.SetPosition(source.GetPosition()); pad.SetNetCode(source.GetNetCode()); fp.Add(pad)
    assert not route._retained_inline_leg_contact(b, PAIR, LEGS[0], retained)['complete']


def test_pending_leg_receives_work_and_retained_leg_remains_unqualified():
    b, retained = fixture()
    with patch.object(route, '_scheduled_flow_legs', return_value=[(0, LEGS[0], (9,)), (1, LEGS[1], (1,))]), \
         patch.object(route, 'route_coupled_pair', return_value=dict(segments=2, length_mm=10)) as solve:
        result = route._route_flow_leg_orders(b, PAIR, LEGS, ['any_station'])
    assert solve.call_count == 1 and solve.call_args.kwargs['endpoints'] == LEGS[1]
    assert solve.call_args.kwargs['avoid'] == ()
    first = result['legs'][0]
    assert first['segments'] == 0 and not first['solver_local_qualified']
    assert first['whole_pair_physical_receiving_still_required']
    assert {t.m_Uuid.AsString() for t in b.GetTracks()} == retained


def test_reused_contact_cannot_bypass_final_whole_pair_rejection():
    b, retained = fixture()
    qualifier = lambda candidate: dict(candidate, refused='actual whole-pair physics failed')
    with patch.object(route, '_scheduled_flow_legs', return_value=[(0, LEGS[0], (9,)), (1, LEGS[1], (1,))]), \
         patch.object(route, 'route_coupled_pair', return_value=dict(segments=2, length_mm=10)):
        result = route._route_flow_bank_orders(b, PAIR, LEGS, ['any_station'],
            candidate_qualifier=qualifier, max_variants=1)
    assert result['refused'] == 'actual whole-pair physics failed'
    assert {t.m_Uuid.AsString() for t in b.GetTracks()} == retained

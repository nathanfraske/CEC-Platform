"""PTH source ownership and exact-reconstruction mutants, not board ratings."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pair_tht_redundant_span as terminal
from test_lastmile import _board


def fixture(tmp_path, monkeypatch, *, locked=False):
    b = _board([(10, 10, 'SYNTH_P'), (15, 10, 'SYNTH_N')], edge=(0, 0, 25, 20))
    b.SetCopperLayerCount(6)
    pad = next(p for p in b.GetPads() if p.GetNetname() == 'SYNTH_P')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH); pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I_MM(1.7, 1.7)); pad.SetDrillSize(pcbnew.VECTOR2I_MM(.5, .5))
    pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    t = pcbnew.PCB_TRACK(b); t.SetLayer(pcbnew.B_Cu)
    t.SetNetCode(b.GetNetcodeFromNetname('SYNTH_P')); t.SetWidth(200000); t.SetLocked(locked)
    t.SetStart(pcbnew.VECTOR2I_MM(9.5, 10)); t.SetEnd(pcbnew.VECTOR2I_MM(10.5, 10)); b.Add(t)
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir()
    field._save_field_snapshot(b, source)
    pair = dict(name='Synthetic pair', kind='can', p='SYNTH_P', n='SYNTH_N', width=.2, gap=.2)
    monkeypatch.setattr(terminal.pairs.precision, 'derive_coupled_pairs', lambda *args, **kw: [pair])
    return source, force._uid(t), force._uid(pad)


@pytest.mark.parametrize('locked', [False, True])
def test_literal_one_plated_pad_scope_constructs_only_the_owned_subtraction(tmp_path, monkeypatch, locked):
    source, uid, pad = fixture(tmp_path, monkeypatch, locked=locked)
    proposal = terminal.plan(source, board_hint='synthetic_only', pair_name='Synthetic pair',
        track_uuids=[uid], allow_locked_source=locked)
    assert proposal['records'][0]['pad_uuid'] == pad
    assert not proposal['source_terminal_or_barrel_current_qualified']
    child = force._copy_family(source, tmp_path/'child')
    field._save_field_snapshot(terminal.construct(source, proposal), child)
    old, new = [additive._nodes(q)[1] for q in (source, child)]
    assert old.keys()-new.keys() == {uid} and not new.keys()-old.keys()
    assert all(old[k] == n for k, n in new.items())


@pytest.mark.parametrize('fault', ['not_plated', 'no_hole', 'other_net', 'outside_pad',
    'wrong_width', 'owned_group', 'locked_without_permission'])
def test_same_net_proximity_cannot_substitute_for_one_actual_source_plated_pad(tmp_path, monkeypatch, fault):
    source, uid, pid = fixture(tmp_path, monkeypatch)
    b = pcbnew.LoadBoard(str(source)); t = next(t for t in b.GetTracks() if force._uid(t) == uid)
    pad = next(p for p in b.GetPads() if force._uid(p) == pid)
    if fault == 'not_plated': pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    elif fault == 'no_hole': pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetDrillSize(pcbnew.VECTOR2I(0, 0))
    elif fault == 'other_net':
        # Keep the native source intact; remove this real source net from
        # the synthetic declared-pair contract instead of asking a writer
        # to serialize a deliberate foreign-net short under the old land.
        other = dict(name='Synthetic pair', kind='can', p='NO_OWNERSHIP', n='SYNTH_N', width=.2, gap=.2)
        monkeypatch.setattr(terminal.pairs.precision, 'derive_coupled_pairs', lambda *args, **kw: [other])
    elif fault == 'outside_pad': t.SetEnd(pcbnew.VECTOR2I_MM(12, 10))
    elif fault == 'wrong_width': t.SetWidth(190000)
    elif fault == 'owned_group':
        group = pcbnew.PCB_GROUP(b); b.Add(group); group.AddItem(t)
    elif fault == 'locked_without_permission': t.SetLocked(True)
    field._save_field_snapshot(b, source)
    with pytest.raises(ValueError):
        terminal.plan(source, board_hint='synthetic_only', pair_name='Synthetic pair', track_uuids=[uid])


@pytest.mark.parametrize('fault', ['source_hash', 'pair_rule', 'pad_identity', 'source_lock_policy'])
def test_saved_subtraction_proposal_cannot_be_repurposed(tmp_path, monkeypatch, fault):
    source, uid, _ = fixture(tmp_path, monkeypatch, locked=fault == 'source_lock_policy')
    proposal = terminal.plan(source, board_hint='synthetic_only', pair_name='Synthetic pair', track_uuids=[uid],
        allow_locked_source=fault == 'source_lock_policy')
    bad = copy.deepcopy(proposal)
    if fault == 'source_hash': bad['source_sha256'] = '0'*64
    elif fault == 'pair_rule': bad['pair']['width'] = .19
    elif fault == 'pad_identity': bad['records'][0]['pad_uuid'] = 'wrong'
    elif fault == 'source_lock_policy': bad['allow_locked_source'] = False
    with pytest.raises(ValueError):
        terminal.construct(source, bad)

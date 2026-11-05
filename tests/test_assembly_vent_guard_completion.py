"""Generic guard construction preserves all native material and rejects hits."""
import json

import pytest

import cec_assembly_instance as instance
from test_assembly_instance import native_fixture


def fixture(tmp_path, monkeypatch, *, obstruct=False):
    import pcbnew
    import cec_complete_assembly_vent_guards as guards
    a, b, paths, contract_path, contract, context = native_fixture(tmp_path, reflected=True)
    fp = pcbnew.FOOTPRINT(b)
    fp.SetReference('RENAMED_RESERVOIR')
    fp.SetFPID(pcbnew.LIB_ID('fixture', 'storage'))
    fp.SetPosition(pcbnew.VECTOR2I_MM(50, 50))
    b.Add(fp)
    contract['envelopes']['storage'] = dict(height_max_mm=1, local_box_mm=[-2, -2, 2, 2],
                                           vent_min_mm=1, kind='reservoir', basis='synthetic',
                                           evidence='synthetic, not a hardware rating')
    if obstruct:
        track = pcbnew.PCB_TRACK(a)
        track.SetStart(pcbnew.VECTOR2I_MM(49, 53))
        track.SetEnd(pcbnew.VECTOR2I_MM(51, 53))
        track.SetWidth(pcbnew.FromMM(.2))
        track.SetLayer(pcbnew.F_Cu)
        a.Add(track)
        pcbnew.SaveBoard(str(paths['carrier']), a)
        context['members']['carrier']['sha256'] = instance.digest(paths['carrier'])
    pcbnew.SaveBoard(str(paths['cover']), b)
    context['members']['cover']['sha256'] = instance.digest(paths['cover'])
    contract_path.write_text(json.dumps(contract))
    context['contract']['sha256'] = instance.digest(contract_path)
    monkeypatch.setattr(guards, 'ROOT', tmp_path)
    return a, b, paths, context, guards


def test_saved_guard_completion_is_additive_and_roundtrips(tmp_path, monkeypatch):
    _, _, paths, context, guards = fixture(tmp_path, monkeypatch)
    before = {role: value.read_bytes() for role, value in paths.items()}
    result = guards.complete(paths['carrier'], context, tmp_path / 'private')
    assert result['ok'] and result['all_existing_native_items_exact']
    assert result['missing_guards_completed'] == ['RENAMED_RESERVOIR']
    assert len(result['added_rule_uuids']) == 1
    assert result['saved_assembly']['ok'] and not result['release_authority']
    assert all(paths[role].read_bytes() == data for role, data in before.items())
    with pytest.raises(ValueError, match='no missing guard'):
        guards.complete(result['candidate'], result['new_assembly_instance'], tmp_path / 'unnecessary')


def test_copper_hit_is_refused_before_emitting_candidate(tmp_path, monkeypatch):
    _, _, paths, context, guards = fixture(tmp_path, monkeypatch, obstruct=True)
    destination = tmp_path / 'refused'
    with pytest.raises(ValueError, match='actual native copper'):
        guards.complete(paths['carrier'], context, destination)
    assert not destination.exists()


def test_wrong_member_context_cannot_add_a_guard(tmp_path, monkeypatch):
    _, _, paths, context, guards = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='selected assembly member'):
        guards.complete(paths['cover'], context, tmp_path / 'refused')

"""Source-qualified short escapes may stay put; route groups are not waived."""
import json
import pcbnew
import pytest

import cec_current_topology as topology
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_smd_macro_transport as macro
from test_local_pofv_ownership import fixture as ground_fixture
from test_smd_macro_transport import inventory


def pair(tmp_path, monkeypatch, *, quarter=0, back=False, delta=.1, fault=None, positive_barrel=False):
    board, via = ground_fixture(offset=(0, 0), connected=False)
    owner = next(iter(board.GetFootprints()))
    ground = next(iter(owner.Pads()))
    owner.SetReference('opaque_owner_' + str(quarter))
    owner.SetPosition(pcbnew.VECTOR2I_MM(20, 30))
    ground.SetPosition(pcbnew.VECTOR2I_MM(20, 30))
    net = pcbnew.NETINFO_ITEM(board, '/opaque_input')
    board.Add(net)
    pad = pcbnew.PAD(owner)
    pad.SetNumber('opaque_input')
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetSize(pcbnew.VECTOR2I_MM(.5, .8))
    pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetPosition(pcbnew.VECTOR2I_MM(22, 30))
    pad.SetNet(net)
    owner.Add(pad)

    def track(a, z, width):
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(*a))
        item.SetEnd(pcbnew.VECTOR2I_MM(*z))
        item.SetWidth(round(width * 1e6))
        item.SetLayer(pcbnew.F_Cu)
        item.SetNet(net)
        board.Add(item)
        return item

    at = (20, 30) if fault == 'overlong' else (21.5, 30)
    prefix = track(at, (22, 30), .2)
    throat = None if fault == 'no_throat' else track(at, (at[0], 28), 1.)
    group = pcbnew.PCB_GROUP(board)
    group.SetName('arbitrary route group' if fault == 'wrong_group' else fr.ENDPOINT_NECKDOWN_GROUP)
    group.SetLocked(fault == 'locked_group')
    board.Add(group)
    group.AddItem(prefix)
    if fault == 'locked_track':
        prefix.SetLocked(True)
    if fault == 'branch':
        for end in ((21.3, 29.8), (21.3, 30.2)):
            group.AddItem(track(at, end, .2))
    barrels=[via]
    if positive_barrel:
        supply=pcbnew.PCB_VIA(board)
        supply.SetViaType(pcbnew.VIATYPE_THROUGH)
        supply.SetPosition(pad.GetPosition())
        supply.SetWidth(350000);supply.SetDrill(250000)
        supply.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        supply.SetNet(net);board.Add(supply);barrels.append(supply)
    fr.group_local_pofv_signal_vias(board, barrels)
    origin = pcbnew.VECTOR2I_MM(20, 30)
    angle = pcbnew.EDA_ANGLE(quarter * 90, pcbnew.DEGREES_T)
    owner.Rotate(origin, angle)
    for item in board.GetTracks():
        item.Rotate(origin, angle)
    if back:
        owner.SetLayer(pcbnew.B_Cu)
        layers = pcbnew.LSET()
        for layer in (pcbnew.B_Cu, pcbnew.B_Mask, pcbnew.B_Paste):
            layers.AddLayer(layer)
        for item in owner.Pads():
            item.SetLayerSet(layers)
        for item in board.GetTracks():
            if item.GetClass() == 'PCB_TRACK':
                item.SetLayer(pcbnew.B_Cu)
    path = tmp_path / 'source.kicad_pcb'
    field._save_field_snapshot(board, path)
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='Default', track_width=1., clearance=.15)]))))
    before, after = [pcbnew.LoadBoard(str(path)) for _ in range(2)]
    owner_after = next(iter(after.GetFootprints()))
    dx, dy = 0, delta
    for _ in range(quarter):
        dx, dy = dy, -dx
    owner_after.Move(pcbnew.VECTOR2I_MM(dx, dy))
    monkeypatch.setattr(topology, 'board_current_domains', lambda *a, **kw: {})
    monkeypatch.setattr(topology, 'current_contract_for_net', lambda *a, **kw: None)
    return before, after, path, force._uid(prefix), force._uid(via), force._uid(throat) if throat else None


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('delta', [-.1, .1])
@pytest.mark.parametrize('track_locked', [False, True])
def test_retains_actual_source_prefix_and_throat_while_owner_return_follows(
        tmp_path, monkeypatch, quarter, back, delta, track_locked):
    a, b, path, prefix, via, throat = pair(tmp_path, monkeypatch,
        quarter=quarter, back=back, delta=delta, fault='locked_track' if track_locked else None)
    original = inventory(a)
    r = macro.apply(a, b, source_path=path, board_hint='opaque_synthetic')
    final = inventory(b)
    assert inventory(a) == original
    assert final[prefix] == original[prefix] and final[throat] == original[throat]
    assert final[via] != original[via]
    assert r['independently_retained_source_endpoint_neckdowns'][0]['uuid'] == prefix
    assert prefix not in {q['uuid'] for q in r['changes']}
    assert not r['current_qualified'] and not r['saved_candidate_authorized']
    assert not r['routing_admitted'] and not r['release_authority']


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_source_owned_in_pad_barrel_can_follow_while_exact_prefix_stays_in_same_land(
        tmp_path, monkeypatch, quarter, back):
    a,b,path,prefix,via,throat=pair(tmp_path,monkeypatch,quarter=quarter,
        back=back,delta=.22,positive_barrel=True,fault='locked_track')
    original=inventory(a)
    r=macro.apply(a,b,source_path=path,board_hint='opaque_synthetic')
    proof=r['independently_retained_source_endpoint_neckdowns'][0]
    assert inventory(b)[prefix]==original[prefix] and inventory(b)[throat]==original[throat]
    assert proof['source_owned_barrels_carried_within_same_land']
    assert proof['after_complete_transport_neckdown_geometry_reproved']
    assert len(r['source_process_barrel_motion'])==2
    assert not r['routing_admitted'] and not r['release_authority']


@pytest.mark.parametrize('back', [False, True])
@pytest.mark.parametrize('fault', ['wrong_group', 'locked_group', 'changed_lock',
    'overlong', 'branch', 'no_throat', 'lost_contact', 'missing_context',
    'wrong_path', 'increased_current', 'changed_source'])
def test_group_name_or_old_contact_is_not_permission_to_keep_an_unqualified_escape(
        tmp_path, monkeypatch, back, fault):
    a, b, path, prefix, via, throat = pair(tmp_path, monkeypatch, back=back,
        delta=1. if fault == 'lost_contact' else .1, fault=fault)
    if fault == 'increased_current':
        monkeypatch.setattr(topology, 'current_contract_for_net', lambda *a, **kw:
            dict(amps=20., geometry_margin=1.25, margin_included=False))
    if fault == 'changed_source':
        for board in (a, b):
            next(t for t in board.GetTracks() if force._uid(t) == prefix).SetWidth(210000)
    if fault == 'changed_lock':
        next(t for t in b.GetTracks() if force._uid(t) == prefix).SetLocked(True)
    original = inventory(b)
    params = dict(source_path=path, board_hint='opaque_synthetic')
    if fault == 'missing_context':
        params = {}
    if fault == 'wrong_path':
        params['source_path'] = tmp_path / 'not_source.kicad_pcb'
    with pytest.raises(ValueError):
        macro.apply(a, b, **params)
    assert inventory(b) == original


def test_departing_throat_reproof_failure_rolls_back_every_conductor(tmp_path, monkeypatch):
    a, b, path, prefix, via, throat = pair(tmp_path, monkeypatch)
    original = inventory(b)
    real = fr._qualified_endpoint_neckdown_tracks
    calls = []
    def qualify(board, items, width, **kw):
        calls.append(board)
        if len(calls) == 3:
            return [], [dict(reason='injected_departing_full_width_throat')]
        return real(board, items, width, **kw)
    monkeypatch.setattr(fr, '_qualified_endpoint_neckdown_tracks', qualify)
    with pytest.raises(ValueError, match='throat_lost_after_transport'):
        macro.apply(a, b, source_path=path, board_hint='opaque_synthetic')
    assert len(calls) == 3 and inventory(b) == original


def test_failure_after_transport_rolls_back_every_conductor(tmp_path, monkeypatch):
    a, b, path, prefix, via, throat = pair(tmp_path, monkeypatch)
    original = inventory(b)
    import cec_fab_profile as fab
    real = fab.local_pofv_via_decision
    monkeypatch.setattr(fab, 'local_pofv_via_decision', lambda board, item, **kw:
        (False, 'injected_candidate_failure') if board is b else real(board, item, **kw))
    with pytest.raises(ValueError, match='destination_POFV'):
        macro.apply(a, b, source_path=path, board_hint='opaque_synthetic')
    assert inventory(b) == original

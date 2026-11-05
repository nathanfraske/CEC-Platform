"""An explicitly fitted optional Ground strap keeps its nonfunctional role.

The only test substitution is the synthetic canonical netlist exporter.
Manufacturer tables, hierarchy parsing, complete package identity, native
metal, project class and source binding are real and independently checked.
"""
import copy
import hashlib
import json
import time
from pathlib import Path

import pcbnew
import pytest

import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_force_current as force
import cec_source_ground_leaf as ground
import cec_source_netlist_semantics as semantics
from test_field_proposals import track
from test_source_ground_leaf import source_fixture


def fixture(tmp_path, monkeypatch, *, quarter=0, back=False):
    board, owner, target, root, tree, _ = source_fixture(tmp_path, monkeypatch)
    # Netlist data is synthetic, its identity is full (not just a pin map).
    # A real executable identity permits bindings_current to detect changes.
    executable = Path('/usr/bin/python3').resolve()
    def export(path, deadline):
        return tree, dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),
            exporter=str(executable), exporter_sha256=force._hash(executable),
            **semantics.metadata(tree))
    monkeypatch.setattr(ground, '_export', export)
    board.SetCopperLayerCount(6)
    for pad in owner.Pads():
        pad.SetPosition(pcbnew.VECTOR2I_MM(30 + 2 * int(pad.GetNumber()), 30))
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    owner.FindPadByNumber('2').SetPosition(pcbnew.VECTOR2I_MM(12, 10))
    target.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    edge = track(board, 'GND', (10, 10), (12, 10), width=.5)
    if back:
        owner.Flip(pcbnew.VECTOR2I(0, 0), False)
        edge.SetLayer(pcbnew.B_Cu)
        edge.SetStart(target.GetPosition())
        edge.SetEnd(owner.FindPadByNumber('2').GetPosition())
    if quarter:
        for item in [owner, edge]:
            item.Rotate(pcbnew.VECTOR2I_MM(20, 20),
                pcbnew.EDA_ANGLE(90 * quarter, pcbnew.DEGREES_T))
    path = tmp_path / 'source.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    # Authored geometry floor, not a current rating or ambient NETCLASS.
    path.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(
        classes=[dict(name='Default', track_width=.5, clearance=.2)],
        netclass_patterns=[]))))
    board = pcbnew.LoadBoard(str(path))
    owner = board.FindFootprintByReference('renamed_owner')
    target = owner.FindPadByNumber('4')
    edge = next(t for t in board.GetTracks() if force._uid(t) == force._uid(edge))
    model = roles.footprint_contract(owner)
    assert model and model['pins']['4'] == 'no_connect'
    proposal = dict(scope='source_typed_complete_cell_escape_proposal',
        source_native_binding=row._source_binding(board),
        poses={owner.GetReference(): [20., 20., 180.]},
        device_contracts={owner.GetReference(): model},
        selected_bypasses={}, board_hint=str(root))
    transport = dict(source_process_barrel_motion=[])
    return board, owner, target, edge, root, tree, proposal, transport


def authority(board, edge, proposal, transport):
    return compiler._ground_boundary_authority(board, edge, transport, proposal,
        time.monotonic() + 10.)


def request(proof):
    return dict(kind='source_boundary', net='GND', width_nm=500000,
        every_surviving_source_component_port_mandatory=True,
        exact_additional_macro_component_source_ownership=[proof])


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_fresh_source_optional_strap_is_owned_without_becoming_functional(tmp_path, monkeypatch, quarter, back):
    board, owner, target, edge, root, _, proposal, transport = fixture(
        tmp_path, monkeypatch, quarter=quarter, back=back)
    raw = root.read_bytes(); before = row._source_binding(board)
    proof = authority(board, edge, proposal, transport)
    optional, = [r for r in proof['source_pad_roots']
        if r['role'] == 'source_optional_ground_attachment']
    assert optional['pad_uuid'] == force._uid(target)
    assert optional['primary_manufacturer_role'] == 'no_connect'
    assert optional['functional_ground_return'] is False
    assert optional['current_authority'] is False
    assert optional['source_ground_attachment']['manufacturer'] == roles.optional_ground_attachment_contract(owner, '4')
    assert 'netlist_semantic_sha256' in optional['source_ground_attachment']['exporter']
    assert 'netlist_sha256' not in optional['source_ground_attachment']['exporter']
    assert escape._typed_macro_ground_scope(request(proof)) is not None
    assert proof['source_width_nm'] == proof['source_full_class_width_nm'] == 500000
    assert root.read_bytes() == raw and row._source_binding(board) == before
    assert authority(board, edge, proposal, transport) == proof


@pytest.mark.parametrize('fault', ['source_missing', 'source_mpn', 'source_net',
    'no_canonical_export', 'stale_hierarchy', 'primary_role_missing', 'no_manufacturer_option',
    'native_net', 'not_moving', 'missing_optional_false'])
def test_optional_label_is_not_authority_without_actual_current_source(tmp_path, monkeypatch, fault):
    board, owner, target, edge, root, tree, proposal, transport = fixture(tmp_path, monkeypatch)
    if fault == 'source_missing': root.write_text(root.read_text().replace('renamed_owner', 'unknown_owner'))
    elif fault == 'source_mpn': root.write_text(root.read_text().replace('INA240A3DR', 'UNKNOWN'))
    elif fault == 'source_net':
        nets = next(n for n in tree if isinstance(n, list) and n and n[0] == 'nets')
        net = next(n for n in nets[1:] if ['name', 'GND'] in n)
        net[net.index(['name', 'GND'])] = ['name', 'NOT_GROUND']
    elif fault == 'no_canonical_export': monkeypatch.setattr(ground, '_export', lambda *a: ({}, {}))
    elif fault == 'stale_hierarchy': monkeypatch.setattr(ground, 'bindings_current', lambda *a: False)
    elif fault == 'primary_role_missing': proposal['device_contracts'][owner.GetReference()]['pins']['4'] = 'untyped'
    elif fault == 'no_manufacturer_option': monkeypatch.setattr(roles, 'optional_ground_attachment_contract', lambda *a: None)
    elif fault == 'native_net': target.SetNet(board.FindNet('arbitrary_control'))
    elif fault == 'not_moving': proposal['poses'] = {}
    else:
        original = ground.plan
        def forged(*a, **kw):
            value = original(*a, **kw)
            value['proofs'][force._uid(target)]['functional_ground_return'] = True
            return value
        monkeypatch.setattr(ground, 'plan', forged)
    with pytest.raises(ValueError):
        authority(board, edge, proposal, transport)


@pytest.mark.parametrize('fault', ['role', 'root_current', 'root_functional', 'primary',
    'proof_current', 'proof_functional', 'bypass', 'release', 'manufacturer_current',
    'manufacturer_functional', 'manufacturer_release', 'permitted_net', 'wrong_pad',
    'wrong_owner', 'proof_kind', 'proof_list', 'manufacturer_list', 'manufacturer_none'])
def test_menu_rejects_forged_optional_ground_scope(tmp_path, monkeypatch, fault):
    board, owner, target, edge, root, tree, proposal, transport = fixture(tmp_path, monkeypatch)
    proof = authority(board, edge, proposal, transport)
    optional = next(r for r in proof['source_pad_roots'] if r['role'] == 'source_optional_ground_attachment')
    attachment = optional['source_ground_attachment']; manufacturer = attachment['manufacturer']
    if fault == 'role': optional['role'] = 'arbitrary_ground'
    elif fault == 'root_current': optional['current_authority'] = True
    elif fault == 'root_functional': optional['functional_ground_return'] = True
    elif fault == 'primary': optional['primary_manufacturer_role'] = 'ground'
    elif fault == 'proof_current': attachment['current_authority'] = True
    elif fault == 'proof_functional': attachment['functional_ground_return'] = True
    elif fault == 'bypass': attachment['bypass_owner'] = True
    elif fault == 'release': attachment['release_authority'] = True
    elif fault == 'manufacturer_current': manufacturer['current_authority'] = True
    elif fault == 'manufacturer_functional': manufacturer['functional_ground_return'] = True
    elif fault == 'manufacturer_release': manufacturer['release_authority'] = True
    elif fault == 'permitted_net': manufacturer['permitted_external_nets'].append('arbitrary_control')
    elif fault == 'wrong_pad': attachment['pad_uuid'] = force._uid(owner.FindPadByNumber('2'))
    elif fault == 'wrong_owner': attachment['owner'] = 'unknown_owner'
    elif fault == 'proof_kind': attachment['kind'] = 'functional_return'
    elif fault == 'proof_list': optional['source_ground_attachment'] = ['forged']
    elif fault == 'manufacturer_list': attachment['manufacturer'] = ['forged']
    else: attachment['manufacturer'] = None
    assert escape._typed_macro_ground_scope(request(proof)) is None

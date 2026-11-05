"""Selected output capacitors retain the actual fixed manufacturer's role."""
import copy
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_field_coupling as field
import cec_force_current as force
from test_stationary_power_stage_owner import stage_fixture


OUTPUT_STAGES = ('TPS2121RUXR', 'LP5907MF-3.3/NOPB')


def fixture(monkeypatch, part, quarter=0, back=False):
    board, poses, owner, cap, model = stage_fixture(monkeypatch, part, quarter, back)
    pin = next(k for k,v in model['pins'].items() if v == 'power_output')
    pad = owner.FindPadByNumber(pin)
    cap_supply = next(p for p in cap.Pads() if p.GetNetname() != 'GND')
    cap_supply.SetNet(pad.GetNet())
    assignment = dict(assigned={'source_output':dict(cap_ref=cap.GetReference(),
        requirement=dict(ref=owner.GetReference(), pin=pin, rail=pad.GetNetname(),
            return_rail='GND'))})
    monkeypatch.setattr(escape.constraints, '_device_bypass_assignment', lambda *a,**kw:assignment)
    return board, poses, owner, cap, model, assignment


@pytest.mark.parametrize('part', OUTPUT_STAGES)
@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('back', [False, True])
def test_stationary_output_role_survives_native_saved_proposal_and_replay(
        tmp_path, monkeypatch, part, quarter, back):
    board, poses, owner, cap, model, assignment = fixture(monkeypatch,part,quarter,back)
    path = tmp_path/'source.kicad_pcb'; field._save_field_snapshot(board,path)
    source, child = [pcbnew.LoadBoard(str(path)) for _ in range(2)]
    raw = path.read_bytes(); before = row._source_binding(source)
    proposal = escape.prepare(source,poses,board_hint='opaque_stationary_output')
    assert proposal['stationary_device_owners'] == [owner.GetReference()]
    assert proposal['device_contracts'][owner.GetReference()] == model
    selected = proposal['selected_bypasses'][cap.GetReference()]
    assert model['pins'][selected['pin']] == 'power_output'
    assert not proposal['retired_track_uuids']
    assert not proposal['measurement_leaves']
    escape.apply_private(child,proposal)
    requests = escape.obligations(source,child,proposal)
    owner_supply = child.FindFootprintByReference(owner.GetReference()).FindPadByNumber(selected['pin'])
    local = requests['local_supply:'+force._uid(owner_supply)]
    assert local['a']['pad_uuid'] == force._uid(owner_supply)
    assert local['net'] == owner_supply.GetNetname()
    assert local['width_nm'] >= 200000
    cap_ground = next(p for p in child.FindFootprintByReference(cap.GetReference()).Pads()
        if p.GetNetname() == 'GND')
    assert requests['ground:'+force._uid(cap_ground)]['a']['pad_uuid'] == force._uid(cap_ground)
    assert not any(q['kind']=='ground' and q['a']['pad_uuid'] in {
        force._uid(p) for p in owner.Pads()} for q in requests.values())
    assert row._source_binding(source) == before and path.read_bytes() == raw
    assert not proposal['routing_admitted'] and not proposal['release_authority']


@pytest.mark.parametrize('part', OUTPUT_STAGES)
@pytest.mark.parametrize('fault', ['one_nm', 'turn', 'output_to_control', 'output_to_switch',
    'unknown_device', 'wrong_rail', 'missing_owner', 'forged_pose'])
def test_output_capacitor_never_acquires_owner_or_switch_motion_authority(monkeypatch,part,fault):
    board, poses, owner, cap, model, assignment = fixture(monkeypatch,part)
    if fault == 'one_nm': poses[owner.GetReference()][0] += .000001
    elif fault == 'turn': poses[owner.GetReference()][2] += 90
    elif fault.startswith('output_to_'):
        target = fault.removeprefix('output_to_')
        changed = copy.deepcopy(model)
        changed['pins'][assignment['assigned']['source_output']['requirement']['pin']] = target
        original = escape.roles.footprint_contract
        monkeypatch.setattr(escape.roles,'footprint_contract',
            lambda fp: changed if fp.GetReference()==owner.GetReference() else original(fp))
    elif fault == 'unknown_device': owner.SetValue('UnknownStage')
    elif fault == 'wrong_rail': assignment['assigned']['source_output']['requirement']['rail'] = 'RAIL'
    elif fault == 'missing_owner': del poses[owner.GetReference()]
    before = row._source_binding(board)
    if fault == 'forged_pose':
        proposal = escape.prepare(board,poses,board_hint='opaque_stationary_output')
        proposal['poses'] = copy.deepcopy(proposal['poses'])
        proposal['poses'][owner.GetReference()][0] += .000001
        with pytest.raises(ValueError): escape.apply_private(board,proposal)
    else:
        with pytest.raises(ValueError): escape.prepare(board,poses,board_hint='opaque_stationary_output')
    assert row._source_binding(board) == before

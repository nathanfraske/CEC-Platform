"""A fixed stage does not acquire a low-power return through its moving cap."""
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_field_coupling as field
import cec_force_current as force
from test_stationary_power_stage_owner import PARTS,stage_fixture


@pytest.mark.parametrize('part',PARTS)
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_fixed_owner_keeps_identity_and_cap_keeps_its_own_mandatory_ground(
        tmp_path,monkeypatch,part,quarter,back):
    board,poses,owner,cap,model=stage_fixture(monkeypatch,part,quarter,back)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,path)
    source,private=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    proposal=escape.prepare(source,poses,board_hint='opaque_synthetic')
    escape.apply_private(private,proposal)
    requests=escape.obligations(source,private,proposal)
    cap_ground=next(p for p in private.FindFootprintByReference(cap.GetReference()).Pads() if p.GetNetname()=='GND')
    assert requests['ground:'+force._uid(cap_ground)]['a']['pad_uuid']==force._uid(cap_ground)
    owner_grounds={force._uid(p) for p in private.FindFootprintByReference(owner.GetReference()).Pads()
        if p.GetNetname()=='GND'}
    assert not any(r['kind']=='ground' and r['a']['pad_uuid'] in owner_grounds for r in requests.values())
    assert any(r['kind']=='local_supply' and r['net']=='RAIL' for r in requests.values())
    assert proposal['stationary_device_owners']==[owner.GetReference()]
    assert not proposal['routing_admitted'] and not proposal['release_authority']

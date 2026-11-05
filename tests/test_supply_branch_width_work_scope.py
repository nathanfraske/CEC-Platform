"""An explicit search ceiling changes effort, never current or cut authority."""
from unittest import mock
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_redundant_supply_branch_sweep as sweep
from test_redundant_supply_branch_sweep import fixture


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_bounded_medium_width_source_is_discoverable_without_changing_default_or_floor(tmp_path,quarter,mirror,face):
    source,ids,main,catalog=fixture(tmp_path,quarter,mirror,face)
    b=pcbnew.LoadBoard(str(source))
    for t in b.GetTracks():t.SetWidth(477370)
    field._save_field_snapshot(b,source);original=source.read_bytes()
    with mock.patch.object(sweep.owner.rated.topology,'distributed_supply_contracts',return_value=catalog):
        narrow=sweep.source_requests(pcbnew.LoadBoard(str(source)),source,board_hint='unfamiliar',allow_locked_source=True)
        explicit=sweep.source_requests(pcbnew.LoadBoard(str(source)),source,board_hint='unfamiliar',allow_locked_source=True,max_source_width_mm=.5)
    assert narrow['requests']==[] and narrow['explicit_source_width_work_ceiling_mm']==.35
    assert len(explicit['requests'])==1 and set(explicit['requests'][0]['source_track_uuids'])==ids
    assert main not in explicit['requests'][0]['source_track_uuids']
    assert explicit['explicit_source_width_work_ceiling_mm']==.5
    assert not explicit['deletion_or_current_authority_granted'] and source.read_bytes()==original


@pytest.mark.parametrize('value',[True,False,0,-1,1.000001,float('inf'),float('nan'),'.5'])
def test_invalid_or_unbounded_width_ceiling_is_not_a_design_rule_override(tmp_path,value):
    source,ids,main,catalog=fixture(tmp_path)
    with pytest.raises(ValueError):
        sweep.source_requests(pcbnew.LoadBoard(str(source)),source,board_hint='unfamiliar',max_source_width_mm=value)

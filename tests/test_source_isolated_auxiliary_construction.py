"""A safe Source-typed package prefix must not include an unowned sibling.

No names or coordinates grant scope. The original saved parent and unchanged
independent literal receiver own every produced item.
"""
from pathlib import Path
from unittest.mock import patch

import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_native_items as native
import cec_sense_auxiliary as aux
import cec_sense_auxiliary_stage as stage
from test_measurement_auxiliary_cut import fixture as native_fixture


def fixture(tmp_path,quarter=0,back=False,value='INA238AIDGSR'):
    b,source,fp,strap,departure=native_fixture(tmp_path,quarter,back)
    native.discard_items(b,[strap,departure]);fp.SetValue(value)
    field._save_field_snapshot(b,source)
    return b,source,fp


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('value',['INA238AIDGSR'])
def test_actual_positive_source_strap_has_independent_saved_receiving(tmp_path,quarter,back,value):
    b,source,fp=fixture(tmp_path,quarter,back,value);old=source.read_bytes()
    result=aux.construct(b,require_source_isolated=True)
    assert result['ok']and result['joins']==1 and not result['deferred'],result
    assert result['complete']and result['source_isolated_only']
    assert result['terminals'][0]['source_scope']['eligible']
    candidate=tmp_path/'private.kicad_pcb';field._save_field_snapshot(b,candidate)
    receiving=stage.receive_straps(source,candidate)
    assert receiving['ok']and len(receiving['proofs'])==1
    assert not receiving['current_authority']and not receiving['kelvin_qualified']
    assert source.read_bytes()==old


@pytest.mark.parametrize('fault',['DNP','locked_owner','owner_group','pad_group',
    'wrong_package','unregistered_complete_role_model','incomplete_pin_map',
    'external_pickup','barrel_pickup','wide_input_tail'])
def test_ineligible_original_source_is_explicitly_deferred_without_new_copper(tmp_path,fault):
    b,source,fp=fixture(tmp_path);a=fp.FindPadByNumber('8');p=fp.FindPadByNumber('9')
    if fault=='DNP':fp.SetDNP(True)
    elif fault=='locked_owner':fp.SetLocked(True)
    elif fault in ('owner_group','pad_group'):
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(fp if fault=='owner_group'else p)
    elif fault=='wrong_package':fp.SetFPID(pcbnew.LIB_ID('Unknown','not_the_manufacturer_package'))
    elif fault=='unregistered_complete_role_model':fp.SetValue('INA228AIDGSR')
    elif fault=='incomplete_pin_map':fp.FindPadByNumber('1').SetNumber('invented')
    elif fault=='barrel_pickup':
        via=pcbnew.PCB_VIA(b);via.SetNet(p.GetNet());via.SetPosition(p.GetPosition())
        via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    else:
        track=pcbnew.PCB_TRACK(b);track.SetNet(p.GetNet());track.SetStart(p.GetPosition())
        track.SetEnd(b.FindFootprintByReference('unrelated_external_boundary').FindPadByNumber('1').GetPosition())
        track.SetLayer(pcbnew.F_Cu);track.SetWidth(400000 if fault=='wide_input_tail'else 200000);b.Add(track)
    before=field._field_snapshot_inventory(b)
    result=aux.construct(b,require_source_isolated=True)
    assert result['joins']==0 and result['generated_items']==[]
    assert result['deferred']and not result['complete']
    assert field._field_snapshot_inventory(b)==before


@pytest.mark.parametrize('reverse_names',[False,True])
def test_mixed_source_constructs_only_positive_scope_and_receiver_owns_every_new_item(tmp_path,reverse_names):
    b,source,fp=fixture(tmp_path)
    fp.SetReference('ZZ_VALID'if reverse_names else'AA_VALID')
    other=pcbnew.Cast_to_FOOTPRINT(fp.Duplicate(False));b.Add(other);other.Move(pcbnew.VECTOR2I_MM(10,12))
    other.SetReference('AA_DEFERRED'if reverse_names else'ZZ_DEFERRED')
    group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(other)
    field._save_field_snapshot(b,source);before=source.read_bytes()
    result=aux.construct(b,require_source_isolated=True)
    assert result['ok']and result['joins']==1 and len(result['deferred'])==1,result
    assert result['deferred'][0]['ref']==other.GetReference()
    assert not result['complete']and not result['refused']
    candidate=tmp_path/'positive-prefix.kicad_pcb';field._save_field_snapshot(b,candidate)
    received=stage.receive_straps(source,candidate)
    assert received['ok']and len(received['proofs'])==1
    assert received['proofs'][0]['owner']==fp.GetReference()
    assert source.read_bytes()==before


def test_all_source_scopes_are_inventoried_before_the_first_new_track(tmp_path):
    import cec_measurement_terminal_access as access
    b,source,fp=fixture(tmp_path)
    other=pcbnew.Cast_to_FOOTPRINT(fp.Duplicate(False));b.Add(other);other.Move(pcbnew.VECTOR2I_MM(10,12));other.SetReference('SECOND')
    initial={force._uid(t)for t in b.GetTracks()};observed=[];real=access._input_island
    def inspect(*a,**kw):
        observed.append({force._uid(t)for t in b.GetTracks()})
        return real(*a,**kw)
    with patch.object(access,'_input_island',side_effect=inspect):
        result=aux.construct(b,require_source_isolated=True)
    assert result['ok']and result['joins']==2 and len(observed)==4
    assert all(ids==initial for ids in observed)


def test_source_tier_does_not_emit_a_width_the_literal_receiver_cannot_own(tmp_path):
    b,source,fp=fixture(tmp_path);old=field._field_snapshot_inventory(b)
    result=aux.construct(b,require_source_isolated=True,width_mm=.4)
    assert result['refused']and not result['generated_items']
    assert field._field_snapshot_inventory(b)==old


def test_source_mode_must_be_an_explicit_boolean(tmp_path):
    b,source,fp=fixture(tmp_path)
    with pytest.raises(ValueError):aux.construct(b,require_source_isolated=1)


def test_worker_never_saves_a_partially_failed_batch(tmp_path):
    b,source,fp=fixture(tmp_path)
    with patch.object(aux,'construct',return_value=dict(generated_item_count=1,
            refused=[dict(reason='another construction failed')])),\
            patch.object(force,'_copy_family',side_effect=AssertionError('must not save')):
        result=stage._worker(str(source),'synthetic',str(tmp_path),1.)
    assert not result['ok']and not result['prefix_accepted']
    assert result['status']=='construction_refused'and result['selected']==str(source)

"""Geometry and multiplicity changes must reach the real annotation owner."""
import copy
import pytest
import cec_force_current as force
import cec_reference_field_seating as fields
from test_ordinary_native_portals import fixture


def finding(board,*,x=1.,severity='warning',kind='silk_over_copper',second=False):
    fps=list(board.GetFootprints());fp=fps[1 if second else 0]
    return dict(type=kind,severity=severity,description='Actual native finding',items=[
        dict(uuid=force._uid(fp.Reference()),description='Reference field',pos=dict(x=x,y=2.)),
        dict(uuid=force._uid(next(iter(fps[0].Pads()))),description='Pad',pos=dict(x=3.,y=4.))])


def test_same_uuids_but_changed_geometry_selects_actual_reference_owner(tmp_path):
    source,b,net=fixture(tmp_path);before=dict(violations=[finding(b)])
    after=dict(violations=[finding(b,x=1.000001)])
    scope=fields.new_native_reference_owner_scope(b,before,after)
    assert scope==[force._uid(next(iter(b.GetFootprints())))]


def test_unchanged_and_reordered_item_inventory_never_create_work(tmp_path):
    source,b,net=fixture(tmp_path);row=finding(b);other=copy.deepcopy(row);other['items'].reverse()
    assert fields.new_native_reference_owner_scope(b,dict(violations=[row]),dict(violations=[other]))==[]


def test_duplicate_introduced_finding_still_selects_owner_once(tmp_path):
    source,b,net=fixture(tmp_path);row=finding(b)
    assert len(fields.new_native_reference_owner_scope(b,dict(violations=[row]),dict(violations=[row,row])))==1


def test_only_reference_properties_and_silkscreen_fault_types_supply_scope(tmp_path):
    source,b,net=fixture(tmp_path);row=finding(b,kind='clearance')
    assert fields.new_native_reference_owner_scope(b,dict(violations=[]),dict(violations=[row]))==[]
    row=finding(b);row['items']=row['items'][1:]
    assert fields.new_native_reference_owner_scope(b,dict(violations=[]),dict(violations=[row]))==[]


def test_finite_scope_is_not_silently_truncated(tmp_path):
    source,b,net=fixture(tmp_path)
    after=dict(violations=[finding(b),finding(b,second=True)])
    with pytest.raises(ValueError,match='bounded_new_native_reference_owner_scope'):
        fields.new_native_reference_owner_scope(b,dict(violations=[]),after,maximum_components=1)


@pytest.mark.parametrize('value',[True,0,17,1.5,None])
def test_invalid_bound_refuses_before_native_inventory(value):
    with pytest.raises(ValueError,match='bounded_new_native_reference_owner_scope'):
        fields.new_native_reference_owner_scope(None,{}, {},maximum_components=value)


def test_unknown_native_severity_does_not_turn_into_cleanup_authority(tmp_path):
    source,b,net=fixture(tmp_path)
    with pytest.raises(ValueError,match='known_native_finding_severity'):
        fields.new_native_reference_owner_scope(b,dict(violations=[]),dict(violations=[finding(b,severity='ignored')]))

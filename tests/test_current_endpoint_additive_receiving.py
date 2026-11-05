"""Small classes do not hide the independently typed current escape floor."""
from unittest import mock

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_current_topology as topology
import cec_force_current as force
from test_current_supply_escape import AUTHORITY, fixture


def receive_prefix(board, thin, *, hint='SYNTHETIC_DESIGN'):
    with mock.patch('cec_route_dimensions.project_resolver',
            return_value=lambda _net: {'track_width': .2, 'clearance': .2}), \
            mock.patch.object(topology,'board_current_domains',return_value={}), \
            mock.patch.object(topology,'current_contract_for_net',return_value=AUTHORITY):
        return additive._qualified_endpoint_additions(board,'anonymous.kicad_pcb',
            {force._uid(thin)},{force._uid(t):t for t in board.GetTracks()},
            board_hint=hint)


@pytest.mark.parametrize('back,angle,net,ref', [
    (False, 0, 'UNRELATED_VDD_A', 'RENAMED_A'),
    (False, 90, '/deep/RAIL_B', 'OTHER_B'),
    (True, 180, 'SUPPLY_C', 'PART_C'),
    (True, 270, '/somewhere/SUPPLY_D', 'FOURTH_D'),
])
def test_current_typed_endpoint_can_equal_the_small_class(back,angle,net,ref):
    board, thin, required=fixture(back=back,angle=angle,net=net,ref=ref)
    assert thin.GetWidth()==200000 and required>200000
    assert receive_prefix(board,thin) is None


@pytest.mark.parametrize('fault', ['missing_hint','untyped','measurement',
    'no_group','no_throat','remote','aggregate','no_current','ground'])
def test_no_label_or_small_class_can_create_current_escape_authority(fault):
    board, thin, _=fixture(value='UNKNOWN_PART' if fault=='untyped' else 'INA181A2IDBVR',
        pin='3' if fault=='measurement' else '6',group=fault!='no_group',
        throat=fault!='no_throat',length=2 if fault=='remote' else .8,
        net='GND' if fault=='ground' else 'RENAMED_SUPPLY')
    if fault in ('aggregate','no_current'):
        domains={'RENAMED_SUPPLY': {'declared': True}} if fault=='aggregate' else {}
        with mock.patch('cec_route_dimensions.project_resolver',
                return_value=lambda _net: {'track_width': .2, 'clearance': .2}), \
                mock.patch.object(topology,'board_current_domains',return_value=domains), \
                mock.patch.object(topology,'current_contract_for_net',
                    return_value=None if fault=='no_current' else AUTHORITY), \
                pytest.raises(ValueError):
            additive._qualified_endpoint_additions(board,'anonymous.kicad_pcb',
                {force._uid(thin)},{force._uid(t):t for t in board.GetTracks()},
                board_hint='SYNTHETIC_DESIGN')
    else:
        with pytest.raises(ValueError):
            receive_prefix(board,thin,hint=None if fault=='missing_hint' else 'SYNTHETIC_DESIGN')


def test_full_current_width_is_not_mislabelled_as_an_endpoint_exception():
    board, thin, required=fixture()
    thin.SetWidth(required)
    with pytest.raises(ValueError,match='incoming_endpoint_not_subclass_escape'):
        receive_prefix(board,thin)

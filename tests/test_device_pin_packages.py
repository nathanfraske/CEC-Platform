"""Manufacturer package tables are not family/net/refdes heuristics."""
import pcbnew
import pytest

import cec_device_bypass as bypass
import cec_device_power_roles as roles
import cec_pair_semantics as pairs
import cec_power_connectivity as power


@pytest.mark.parametrize('value,inputs,supply', [
    ('INA181A2IDBVR', ('3', '4'), '6'),
    ('INA181A2IDCKR', ('4', '5'), '3'),
    ('INA240A3DR', ('8', '1'), '6'),
    ('INA240A3PWR', ('2', '3'), '5')])
def test_selected_package_owns_input_pair_and_actual_supply(value, inputs, supply):
    assert pairs.current_input_contract(value)[1] == inputs
    assert {p for p, *_ in bypass.requirements_for_value(value)} == {supply}
    manufacturer = roles.contract(value)
    assert manufacturer['pins'][supply] == 'power_input'
    assert all(manufacturer['pins'][p] == 'measurement' for p in inputs)


@pytest.mark.parametrize('family', ['INA181', 'INA240', 'INA240A3'])
def test_unqualified_family_cannot_choose_package_or_waive_a_bypass(family):
    assert pairs.current_input_contract(family) is None
    assert roles.contract(family) is None
    with pytest.raises(ValueError, match='package_required'):
        list(bypass.requirements_for_value(family))


def test_native_embedded_mpn_qualifies_family_and_refuses_wrong_package():
    board = pcbnew.BOARD()
    fp = pcbnew.FOOTPRINT(board); board.Add(fp)
    fp.SetReference('ARBITRARY'); fp.SetValue('INA240A3')
    fp.SetField('MPN', 'INA240A3DR')
    fp.SetFPID(pcbnew.LIB_ID('Package_SO', 'SOIC-8_3.9x4.9mm_P1.27mm'))
    assert roles.footprint_contract(fp)['device_package'] == 'INA240 D'
    assert pairs.footprint_input_contract(fp) == ('INA240', ('8', '1'))
    fp.SetField('MPN', 'INA240A3PWR')
    with pytest.raises(ValueError, match='footprint_mismatch'):
        roles.footprint_contract(fp)
    with pytest.raises(ValueError, match='footprint_mismatch'):
        pairs.footprint_input_contract(fp)


def test_native_selected_package_can_qualify_a_family_without_inventing_an_mpn():
    assert roles.contract('INA240A3', footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')['device_package'] == 'INA240 D'
    assert pairs.current_input_contract('INA240A3', footprint='Package_SO:TSSOP-8_3x3mm_P0.65mm') == ('INA240', ('2', '3'))
    with pytest.raises(ValueError, match='family_mismatch'):
        roles.contract('INA240A3', mpn='INA181A2IDBVR')


@pytest.mark.parametrize('pin,expected', [('2', 'ground'), ('3', 'ground_reference'),
                                        ('4', 'not_power'), ('7', 'ground_reference')])
def test_grounded_reference_and_permitted_nc_do_not_become_chip_ground(pin, expected):
    assert power.terminal_role('GND', pin, '', set(),
        manufacturer=roles.contract('INA240A3DR'))[0] == expected


def test_grounded_s_control_and_drv_exposed_pad_have_distinct_roles():
    can = roles.contract('TJA1051T/3,118')
    assert power.terminal_role('GND', '8', '', set(), manufacturer=can)[0] == 'not_power'
    assert power.terminal_role('GND', '2', '', set(), manufacturer=can)[0] == 'ground'
    drv = roles.contract('TLV75533PDRVR')
    assert power.terminal_role('GND', '7', '', set(), manufacturer=drv)[0] == 'ground'
    assert roles.contract('TJA1051T/E') is None  # /3 VIO cannot transfer to /E EN


@pytest.mark.parametrize('suffix', ['', ',112', ',118', '/1J', '/2Z', '/CM,118'])
def test_nxp_so8_orderable_suffix_keeps_the_verified_vio_pin_table(suffix):
    # NXP TJA1051 product ordering table + rev 9 table 3. Packaging suffixes
    # may not make an actual fitted supply terminal silently untyped.
    selected = roles.contract('TJA1051T/3', mpn='TJA1051T/3' + suffix,
        footprint='cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')
    assert selected['device_package'] == 'TJA1051T/3 SO8'
    assert selected['pins']['3'] == selected['pins']['5'] == 'power_input'
    assert selected['pins']['8'] == 'control'


@pytest.mark.parametrize('mpn', ['TJA1051T/E/1J', 'TJA1051TK/3/1J',
    'TJA1051T/3/UNKNOWN', 'TJA1051T/3,UNKNOWN', 'TJA1051T/3/1JX'])
def test_unknown_or_functional_nxp_variants_cannot_borrow_so8_vio_contract(mpn):
    assert roles.contract('TJA1051T/3', mpn=mpn,
        footprint='cec-Package_SO:SOIC-8_3.9x4.9mm_P1.27mm') is None


def test_nxp_known_orderable_so8_suffix_cannot_authorize_hvson_footprint():
    with pytest.raises(ValueError, match='footprint_mismatch'):
        roles.contract('TJA1051T/3', mpn='TJA1051T/3/1J',
            footprint='cec-Package_DFN_QFN:HVSON-8')


def test_symbol_ground_tied_signal_or_measurement_is_not_a_power_ground():
    assert power.terminal_role('GND', 'S', 'input', set())[0] == 'not_power'
    assert power.terminal_role('GND', 'IP', '', set(), {'IP'})[0] == 'not_power'


@pytest.mark.parametrize('displayed,mpn', [
    ('INA181', 'INA240A3DR'), ('INA240A3', 'INA181A2IDBVR')])
def test_pair_decoder_cannot_hide_a_contradictory_displayed_family(displayed,mpn):
    with pytest.raises(ValueError,match='family_mismatch'):
        pairs.current_input_contract(displayed,mpn=mpn)

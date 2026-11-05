"""MINI roles follow the selected manufacturer package, never a board/refdes."""
import pcbnew
import pytest

import cec_device_power_roles as roles
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from test_gpio_series_semantics import fixture as series_fixture


def fixture(*,pin='14',module='1',memory='N4R2',alias='S2',quarter=0,back=False):
    board,fp,resistor,name=series_fixture(pin=pin,name='/unfamiliar/STATUS_SENSE')
    mpn='ESP32-S3-MINI-'+module+'-'+memory
    fp.SetValue(mpn);fp.SetField('MPN',mpn)
    fp.SetFPID(pcbnew.LIB_ID('different_vendor','ESP32-'+alias+'-MINI-'+module+'_NoAntKeepout'))
    ground=pcbnew.NETINFO_ITEM(board,'GND');board.Add(ground)
    supply=pcbnew.NETINFO_ITEM(board,'/unfamiliar/LOGIC_RAIL');board.Add(supply)
    unused=pcbnew.NETINFO_ITEM(board,'unconnected-(unused-physical-package-land)');board.Add(unused)
    ground_numbers={'1','2','42','43'}|{str(n)for n in range(46,66)}
    for number in range(1,66):
        if str(number)==pin:continue
        pad=pcbnew.PAD(fp);pad.SetNumber(str(number));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(.4,.8));pad.SetPosition(pcbnew.VECTOR2I_MM(10+number*.05,12))
        pad.SetNet(ground if str(number)in ground_numbers else supply if number==3 else unused)
        fp.Add(pad)
    fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    return board,fp,resistor,name


@pytest.mark.parametrize('module',['1','1U'])
@pytest.mark.parametrize('memory',['N4R2','N8'])
@pytest.mark.parametrize('alias',['S2','S3'])
@pytest.mark.parametrize('pin',['5','9','14','22'])
def test_positive_mini_pin_map_has_no_voltage_current_or_application_mode_claim(module,memory,alias,pin):
    b,fp,r,net=fixture(module=module,memory=memory,alias=alias,pin=pin)
    proof=roles.scalar_gpio_pin(fp,pin)
    assert proof['function']=='IO'+str(int(pin)-4)
    assert proof['package']=='ESP32-S3-MINI-'+module and proof['associated_power_pin']=='3'
    assert proof['source_table']=='3-1' and proof['adc_capable']
    assert not any(proof[k]for k in ('gpio_application_mode_or_high_impedance_assumed',
        'current_authority','voltage_envelope_authority','release_authority'))
    assert fr._native_series_gpio_signal(b,net)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_mini_series_witness_follows_pose_and_keeps_sensitive_class_exclusion(monkeypatch,quarter,back):
    b,fp,r,net=fixture(quarter=quarter,back=back)
    assert fr._native_series_gpio_signal(b,net)
    assert net in fr._ordinary_final_completion_nets(b,lambda n:{'track_width':.2})
    monkeypatch.setattr(fr,'_project_netclass_resolver',lambda p:lambda n:{'track_width':.2,'name':'Sense'})
    assert net not in ordinary.eligible_nets(b,'synthetic','synthetic')


@pytest.mark.parametrize('pin',['1','3','4','23','24','26','42','45','61','66'])
def test_power_ground_usb_boot_or_unknown_lands_do_not_borrow_mini_scalar_roles(pin):
    b,fp,r,net=fixture()
    assert roles.scalar_gpio_pin(fp,pin) is None


@pytest.mark.parametrize('fault',['mpn','value','footprint','missing_pin','duplicate_pin',
    'ground_net','supply_missing','input_on_supply','drilled','wrong_face','dnp'])
def test_contradictory_or_incomplete_mini_native_package_fails_closed(fault):
    b,fp,r,net=fixture()
    if fault=='mpn':fp.SetField('MPN','ESP32-S2-MINI-1-N4R2')
    elif fault=='value':fp.SetValue('ESP32-S3-WROOM-1-N4R2')
    elif fault=='footprint':fp.SetFPID(pcbnew.LIB_ID('library','ESP32-S3-WROOM-1'))
    elif fault=='missing_pin':fp.Remove(next(p for p in fp.Pads()if p.GetNumber()=='12'))
    elif fault=='duplicate_pin':
        pad=pcbnew.PAD(fp);pad.SetNumber('14');fp.Add(pad)
    elif fault=='ground_net':next(p for p in fp.Pads()if p.GetNumber()=='42').SetNetCode(0)
    elif fault=='supply_missing':next(p for p in fp.Pads()if p.GetNumber()=='3').SetNetCode(0)
    elif fault=='input_on_supply':
        next(p for p in fp.Pads()if p.GetNumber()=='14').SetNet(next(p for p in fp.Pads()if p.GetNumber()=='3').GetNet())
    elif fault=='drilled':next(p for p in fp.Pads()if p.GetNumber()=='14').SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='wrong_face':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu)
        next(p for p in fp.Pads()if p.GetNumber()=='14').SetLayerSet(layers)
    elif fault=='dnp':fp.SetDNP(True)
    assert roles.scalar_gpio_pin(fp,'14') is None
    assert not fr._native_series_gpio_signal(b,net)


def test_split_ground_ep_is_one_terminal_not_extra_signal_permission():
    b,fp,r,net=fixture()
    pad=pcbnew.PAD(fp);pad.SetNumber('61');pad.SetNet(b.FindNet('GND'))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad)
    assert roles.scalar_gpio_pin(fp,'14')
    assert roles.scalar_gpio_pin(fp,'61') is None

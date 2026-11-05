"""Names do not override native selected digital-buffer/GPIO pin roles."""
import pcbnew
import pytest

import cec_device_power_roles as roles
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from test_lastmile import _board


def fixture(*,name='/arbitrary/STATUS_SENSE',back=False,angle=0):
    board=_board([(5,5,name),(8,5,name)],edge=(0,0,20,20))
    gpio,driver=list(board.GetFootprints())
    gpio.SetReference('RENAMED_HOST');gpio.SetValue('ESP32-C6-MINI-1-N4')
    gpio.SetFPID(pcbnew.LIB_ID('another-lib','ESP32-C6-MINI-1'))
    list(gpio.Pads())[0].SetNumber('10')
    driver.SetReference('ARBITRARY_BUFFER');driver.SetValue('74LVC1G17')
    driver.SetField('MPN','SN74LVC1G17DBVR')
    driver.SetFPID(pcbnew.LIB_ID('other-lib','SOT-23-5'))
    list(driver.Pads())[0].SetNumber('4')
    for number in ('1','2','3','5'):
        p=pcbnew.PAD(driver);p.SetNumber(number)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.6,.5))
        p.SetPosition(pcbnew.VECTOR2I_MM(8,int(number)+7));driver.Add(p)
    for fp in (gpio,driver):
        if back:fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if angle:fp.Rotate(fp.GetPosition(),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    return board,gpio,driver,name


@pytest.mark.parametrize('name,back,angle',[
    ('/elsewhere/READBACK_SENSE',False,0),('/nested/SENSE_STATUS',False,90),
    ('RENAMED_SENSE',True,180),('/other/STATUS',True,270)])
def test_selected_buffered_scalar_signal_follows_native_renaming(name,back,angle):
    board,gpio,driver,net=fixture(name=name,back=back,angle=angle)
    witness=roles.scalar_logic_output_pin(driver,'4')
    assert witness['function']=='Y' and not witness['release_authority']
    assert roles.scalar_gpio_pin(gpio,'10')['function']=='IO5'
    assert fr._native_buffered_gpio_signal(board,net)
    assert net in fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})


@pytest.mark.parametrize('fault',['mpn_absent','wrong_package','wrong_display',
    'wrong_footprint','driver_input','usb','unknown_gpio','power','extra_terminal',
    'extra_driver_land','missing_driver_land','dnp','drilled','zone'])
def test_unknown_or_different_signal_owners_are_not_promoted(fault):
    board,gpio,driver,net=fixture()
    if fault=='mpn_absent':driver.SetField('MPN','')
    elif fault=='wrong_package':driver.SetField('MPN','SN74LVC1G17DCKR')
    elif fault=='wrong_display':driver.SetValue('OPA320')
    elif fault=='wrong_footprint':driver.SetFPID(pcbnew.LIB_ID('lib','SC-70-5'))
    elif fault=='driver_input':driver.FindPadByNumber('4').SetNumber('2')
    elif fault=='usb':list(gpio.Pads())[0].SetNumber('17')
    elif fault=='unknown_gpio':gpio.SetField('MPN','UNKNOWN')
    elif fault=='power':list(gpio.Pads())[0].SetNumber('3')
    elif fault=='extra_terminal':
        fp=pcbnew.FOOTPRINT(board);board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNet(board.FindNet(net));fp.Add(p)
    elif fault=='extra_driver_land':
        p=pcbnew.PAD(driver);p.SetNumber('6');driver.Add(p)
    elif fault=='missing_driver_land':driver.Remove(driver.FindPadByNumber('1'))
    elif fault=='dnp':driver.SetDNP(True)
    elif fault=='drilled':
        p=driver.FindPadByNumber('4');p.SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    else:
        z=pcbnew.ZONE(board);z.SetNet(board.FindNet(net));z.SetIsRuleArea(False)
        z.Outline().NewOutline()
        for x,y in ((3,3),(9,3),(9,8),(3,8)):z.Outline().Append(int(x*1e6),int(y*1e6))
        board.Add(z)
    assert not fr._native_buffered_gpio_signal(board,net)
    assert net not in fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})


@pytest.mark.parametrize('name',['/x/KELVIN_SENSE','/x/SENSE_CLOCK','/x/SENSE_CLK',
    '/x/SENSE_P','/x/USB_DP_SENSE','/x/+3V3_SENSE'])
def test_positive_buffer_does_not_override_other_sensitive_exclusions(name):
    board,_,_,net=fixture(name=name)
    assert net not in fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})


@pytest.mark.parametrize('klass',['Sense','Kelvin','Clock','HighSpeed','Power'])
def test_specialized_project_authority_remains_specialized(monkeypatch,klass):
    board,_,_,net=fixture()
    monkeypatch.setattr(fr,'_project_netclass_resolver',lambda p:lambda n:{'track_width':.2,'name':klass})
    assert net not in ordinary.eligible_nets(board,'anonymous','synthetic')

"""Lexical SENSE overrides require complete native package/series evidence."""
import pcbnew
import pytest

import cec_device_power_roles as roles
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
from test_lastmile import _board


def fixture(*,name='/renamed/STATUS_SENSE', pin='12'):
    board=_board([(5,5,name),(8,5,name)],edge=(0,0,20,20))
    fps=list(board.GetFootprints())
    gpio,resistor=fps
    gpio.SetReference('RENAMED_MODULE');gpio.SetValue('ESP32-C6-MINI-1-N4')
    gpio.SetFPID(pcbnew.LIB_ID('renamed-library','ESP32-C6-MINI-1'))
    list(gpio.Pads())[0].SetNumber(pin)
    resistor.SetReference('ARBITRARY_RESISTOR');resistor.SetValue('100kΩ')
    resistor.SetFPID(pcbnew.LIB_ID('arbitrary-library','R_0402_1005Metric'))
    list(resistor.Pads())[0].SetNumber('1')
    other=pcbnew.NETINFO_ITEM(board,'/renamed/STATUS_INPUT');board.Add(other)
    p=pcbnew.PAD(resistor);p.SetNumber('2');p.SetNet(other)
    p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetSize(pcbnew.VECTOR2I_MM(.45,.45))
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
    p.SetPosition(pcbnew.VECTOR2I_MM(8,6));resistor.Add(p)
    return board,gpio,resistor,name


@pytest.mark.parametrize('name',['/x/STATUS_SENSE','/another/a/SENSE_STATUS','/arbitrary/STATUS'])
def test_positive_series_gpio_identity_follows_renaming(name):
    board,gpio,resistor,net=fixture(name=name)
    assert fr._native_series_gpio_signal(board,net)
    assert net in fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})
    witness=roles.scalar_gpio_pin(gpio,'12')
    assert witness['function']=='IO0' and witness['source_table']=='3-1'
    assert not witness['release_authority']


@pytest.mark.parametrize('fault',['usb','ground','nc','unknown_package','contradictory_mpn',
    'wrong_footprint','unknown_resistor','short_resistor','extra_land','extra_terminal','drilled','zone','nc_peer'])
def test_missing_or_specialized_native_identity_stays_sensitive(fault):
    board,gpio,resistor,net=fixture()
    if fault in ('usb','ground','nc'):
        list(gpio.Pads())[0].SetNumber({'usb':'17','ground':'11','nc':'4'}[fault])
    elif fault=='unknown_package':gpio.SetValue('ESP32-C3-MINI-1-N4')
    elif fault=='contradictory_mpn':gpio.SetField('MPN','UNKNOWN')
    elif fault=='wrong_footprint':gpio.SetFPID(pcbnew.LIB_ID('library','ESP32-C6-WROOM-1'))
    elif fault=='unknown_resistor':resistor.SetFPID(pcbnew.LIB_ID('library','Unknown'))
    elif fault=='short_resistor':resistor.SetValue('0R')
    elif fault=='extra_land':
        p=pcbnew.PAD(resistor);p.SetNumber('3');resistor.Add(p)
    elif fault=='extra_terminal':
        fp=pcbnew.FOOTPRINT(board);board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNetCode(board.GetNetcodeFromNetname(net));fp.Add(p)
    elif fault=='drilled':
        list(resistor.Pads())[0].SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
        list(resistor.Pads())[0].SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='zone':
        z=pcbnew.ZONE(board);z.SetIsRuleArea(False);z.SetNet(board.FindNet(net))
        z.Outline().NewOutline()
        for x,y in ((3,3),(9,3),(9,8),(3,8)):z.Outline().Append(int(x*1e6),int(y*1e6))
        board.Add(z)
    else:
        nc=pcbnew.NETINFO_ITEM(board,'unconnected-(anonymous)');board.Add(nc)
        list(resistor.Pads())[1].SetNet(nc)
    assert not fr._native_series_gpio_signal(board,net)
    assert net not in fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})


@pytest.mark.parametrize('name',['/x/KELVIN_SENSE','/x/SENSE_CLOCK','/x/SENSE_CLK','/x/SENSE_P','/x/USB_DP_SENSE','/x/+3V3_SENSE'])
def test_other_sensitive_owners_are_not_overridden(name):
    board,_,_,net=fixture(name=name)
    assert net not in fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})


@pytest.mark.parametrize('klass',['Sense','Kelvin','Clock','HighSpeed','Power'])
def test_specialized_project_class_is_still_excluded(monkeypatch,klass):
    board,_,_,net=fixture()
    monkeypatch.setattr(fr,'_project_netclass_resolver',lambda p:lambda n:{'track_width':.2,'name':klass})
    assert net not in ordinary.eligible_nets(board,'synthetic','synthetic')

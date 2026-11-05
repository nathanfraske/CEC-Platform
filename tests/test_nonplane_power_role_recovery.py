"""Explicit routable-role recovery never consumes a plane or a pair role."""
import pcbnew
import pytest
import cec_fr as fr
import cec_fab_profile as fab
from test_lastmile import _board


def board():
    b=_board([(5,5,'/CLOCK')],edge=(0,0,30,30));b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';b.SetProperties(props)
    return b


def test_explicit_portfolio_admits_only_profile_authorized_routable_roles():
    b=board();before=fr._lastmile_route_layers(b,net_name='/CLOCK',spec=dict(name='Default'))
    after=fr._lastmile_route_layers(b,net_name='/CLOCK',spec=dict(name='Default'),allow_nonplane_power_role=True)
    assert b.GetLayerID('In3.Cu') not in before and b.GetLayerID('In3.Cu') in after
    assert set(before)<=set(after)
    assert all(fab.copper_layer_role(b,fab.COPPER_LAYER_IDS[l])!='GND' for l in after)
    assert fr._lastmile_route_layers(b,net_name='/CLOCK',spec=dict(name='Default'))==before


@pytest.mark.parametrize('net',['/CAN_H','/USB_D_P','/PCIE_CLK_N','/PAIR_P'])
def test_coupled_nets_never_gain_a_power_role(net):
    b=board()
    assert fr._lastmile_route_layers(b,net_name=net,spec=dict(name='Default'),allow_nonplane_power_role=True)==\
        fr._lastmile_route_layers(b,net_name=net,spec=dict(name='Default'))


def test_actual_full_plane_still_excluded_when_role_fallback_requested():
    b=board();z=pcbnew.ZONE(b);z.SetLayer(pcbnew.In3_Cu);z.SetNetCode(b.GetNetcodeFromNetname('/CLOCK'))
    z.Outline().NewOutline()
    for q in ((0,0),(30,0),(30,30),(0,30)):z.Outline().Append(pcbnew.VECTOR2I_MM(*q))
    b.Add(z)
    assert pcbnew.In3_Cu not in fr._lastmile_route_layers(b,net_name='/CLOCK',spec=dict(name='Default'),allow_nonplane_power_role=True)


@pytest.mark.parametrize('flag',[1,None,'yes',[],{}])
def test_layer_policy_is_not_an_inferred_truthy_permission(flag):
    with pytest.raises(ValueError):fr._lastmile_route_layers(board(),allow_nonplane_power_role=flag)
    with pytest.raises(ValueError):fr.synthesize_lastmile(board(),allow_nonplane_power_role=flag)


def test_explicit_final_pipeline_environment_switch():
    assert not fr.lastmile_nonplane_power_role_policy({})
    assert fr.lastmile_nonplane_power_role_policy({'CEC_LASTMILE_FINAL_NONPLANE_POWER_ROLE':'1'})
    assert not fr.lastmile_nonplane_power_role_policy({'CEC_LASTMILE_FINAL_NONPLANE_POWER_ROLE':'0'})
    for value in ('true','yes','',1,None):
        with pytest.raises(ValueError):fr.lastmile_nonplane_power_role_policy(
            {'CEC_LASTMILE_FINAL_NONPLANE_POWER_ROLE':value})

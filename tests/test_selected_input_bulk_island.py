"""Selected input bulk recognition is not a new load/current qualification."""
import copy
import pcbnew,pytest
import cec_supply_consumer_branch as branch
import cec_field_coupling as field
import cec_force_current as force
from test_pass_through_supply_branch import fixture


def case(tmp_path,monkeypatch,quarter=0,back=False):
    b,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream=fixture(monkeypatch,tmp_path)
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('OPAQUE_PASSIVE');fp.SetValue('10uF')
    fp.SetFPID(pcbnew.LIB_ID('unfamiliar','C_0805_2012Metric'));fp.SetField('MPN','CL21A106KAYNNNE')
    fp.SetField('Manufacturer','Samsung');b.Add(fp)
    for number,net,at in [('1',root.GetNet(),(11,8)),('2',b.FindNet('GND'),(11,11))]:
        p=pcbnew.PAD(fp);p.SetNumber(number);p.SetNet(net);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I_MM(1,1));p.SetPosition(pcbnew.VECTOR2I_MM(*at));fp.Add(p)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        if quarter:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,b.GetFileName())
    return b,fp,row,downstream,domain


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_native_input_bulk_keeps_the_existing_design_budget_and_one_tap(tmp_path,monkeypatch,quarter,back):
    b,fp,row,downstream,domain=case(tmp_path,monkeypatch,quarter,back);snapshot=field._field_snapshot_inventory(b)
    budgets=copy.deepcopy((row,downstream,domain));proof=branch.inventory(b,board_hint='unrelated_identity',timeout_s=10.)
    assert proof['complete'] and len(proof['proofs'])==1,proof['refusals']
    own=proof['proofs'][0];assert own['physical_trunk_tap_count']==1 and own['shared_terminal_partitions_preserved']
    assert own['budget']['current_authority']['amps']==3.0004
    assert own['budget']['aggregate_current_authority']['amps']==20.
    assert own['budget']['current_authority']['geometry_margin']==1.25
    assert not own['inrush_fault_barrel_and_release_qualified'] and not own['release_authority']
    model=branch.selected_bypass_contract(fp,allow_pass_through_input_bulk=True)
    assert model and not model['leakage_inrush_fault_and_thermal_qualified']
    assert branch.selected_bypass_contract(fp) is None
    assert field._field_snapshot_inventory(b)==snapshot and budgets==(row,downstream,domain)
    assert branch.inventory(pcbnew.LoadBoard(b.GetFileName()),board_hint='unrelated_identity',timeout_s=10.)==proof


@pytest.mark.parametrize('fault',['mpn','package','value','manufacturer','cross_rail','dnp','hole','extra_active_load','third_cap'])
def test_unknown_or_different_load_cannot_borrow_selected_bulk_identity(tmp_path,monkeypatch,fault):
    b,fp,row,downstream,domain=case(tmp_path,monkeypatch)
    if fault=='mpn':fp.SetField('MPN','CL21A106_UNKNOWN')
    elif fault=='package':fp.SetFPID(pcbnew.LIB_ID('unfamiliar','C_0603_1608Metric'))
    elif fault=='value':fp.SetValue('100uF')
    elif fault=='manufacturer':fp.SetField('Manufacturer','Unknown')
    elif fault=='cross_rail':fp.FindPadByNumber('2').SetNet(b.FindNet('/arbitrary/DELIVERY'))
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='hole':fp.FindPadByNumber('1').SetDrillSize(pcbnew.VECTOR2I(300000,300000))
    elif fault in ('extra_active_load','third_cap'):
        extra=pcbnew.FOOTPRINT(b);extra.SetReference('OTHER_ROLE');extra.SetValue(fp.GetValue())
        extra.SetFPID(fp.GetFPID());extra.SetField('MPN','CL21A106KAYNNNE');extra.SetField('Manufacturer','Samsung');b.Add(extra)
        for original in fp.Pads():
            p=pcbnew.PAD(extra);p.SetNumber(original.GetNumber());p.SetNet(original.GetNet())
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(original.GetLayerSet());p.SetShape(original.GetShape())
            p.SetSize(original.GetSize());p.SetPosition(original.GetPosition());extra.Add(p)
        if fault=='extra_active_load':extra.SetField('MPN','ACTIVE_UNKNOWN')
    proof=branch.inventory(b,board_hint='unrelated_identity',timeout_s=10.)
    assert not proof['complete'] and proof['refusals'] and not proof['all_owned_track_requirements']

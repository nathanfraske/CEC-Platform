"""An exact unchanged power stage can witness its own capacitor, not move."""
import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_force_current as force
from test_cell_escape_replan import fixture
from cec_native_items import discard_footprint_children

PARTS=('TPS2121RUXR','LP5907MF-3.3/NOPB','TLV62569DBVR','TJA1051T/3')

def stage_fixture(monkeypatch,part,quarter=0,back=False):
    b,poses,owner,cap=fixture(monkeypatch,prefix='unrelated_names')
    discard_footprint_children(b,owner,list(owner.Pads()))
    owner.SetValue(part)
    package='RUX0012A' if part.startswith('TPS') else 'SOIC-8' if part.startswith('TJA') else 'SOT-23-5'
    owner.SetFPID(pcbnew.LIB_ID('qualified_library',package))
    model=roles.footprint_contract(owner);assert model is not None
    rail_pin=next(k for k,v in model['pins'].items() if v=='power_input')
    other_pin=next((k for k,v in model['pins'].items()
        if k!=rail_pin and v in ('power_input','power_output')),rail_pin)
    other_rail='RAIL' if other_pin==rail_pin else 'OUT'
    for index,(pin,role) in enumerate(model['pins'].items()):
        pad=pcbnew.PAD(owner);pad.SetNumber(pin)
        net='RAIL' if pin==rail_pin else 'GND' if role in ('ground','power_return') else 'OUT'
        pad.SetNet(b.FindNet(net));pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4));owner.Add(pad)
        pad.SetPosition(pcbnew.VECTOR2I_MM(8 if index%2==0 else 12,7+index*.6))
    cap.SetPosition(pcbnew.VECTOR2I_MM(15,10))
    assignment=dict(assigned={'primary':dict(cap_ref=cap.GetReference(),
        requirement=dict(ref=owner.GetReference(),pin=rail_pin,rail='RAIL',return_rail='GND'))})
    secondary=pcbnew.FOOTPRINT(b);secondary.SetReference('unchanged_other_supply_cap')
    secondary.SetValue('1uF');secondary.SetFPID(pcbnew.LIB_ID('Capacitor_SMD','C_0603_1608Metric'))
    secondary.SetPosition(pcbnew.VECTOR2I_MM(20,20));b.Add(secondary)
    for number,x,net in [('1',19.5,other_rail),('2',20.5,'GND')]:
        pad=pcbnew.PAD(secondary);pad.SetNumber(number);pad.SetNet(b.FindNet(net))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        secondary.Add(pad);pad.SetPosition(pcbnew.VECTOR2I_MM(x,20))
    assignment['assigned']['secondary']=dict(cap_ref=secondary.GetReference(),
        requirement=dict(ref=owner.GetReference(),pin=other_pin,rail=other_rail,return_rail='GND'))
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**kw:assignment)
    if back:
        for fp in (owner,cap):fp.Flip(pcbnew.VECTOR2I_MM(10,10),False)
    if quarter:
        angle=pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T)
        for fp in (owner,cap):fp.Rotate(pcbnew.VECTOR2I_MM(10,10),angle)
    poses={fp.GetReference():[*[v/1e6 for v in fp.GetPosition()],fp.GetOrientationDegrees()]
        for fp in (owner,cap)}
    poses[cap.GetReference()][0]+=.25
    return b,poses,owner,cap,model

@pytest.mark.parametrize('part',PARTS)
@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_stationary_stage_is_only_a_source_identity_witness(monkeypatch,part,quarter,back):
    board,poses,owner,cap,model=stage_fixture(monkeypatch,part,quarter,back)
    before=row._source_binding(board)
    proposal=escape.prepare(board,poses,board_hint='opaque')
    assert row._source_binding(board)==before
    assert proposal['stationary_device_owners']==[owner.GetReference()]
    assert proposal['device_contracts'][owner.GetReference()]==model
    assert proposal['selected_bypasses'][cap.GetReference()]['owner']==owner.GetReference()
    assert not proposal['measurement_leaves']
    assert not proposal['retired_track_uuids']
    assert not proposal['routing_admitted'] and not proposal['release_authority']

@pytest.mark.parametrize('part',PARTS)
@pytest.mark.parametrize('motion',['one_nm','quarter_turn'])
def test_same_stage_cannot_acquire_motion_authority(monkeypatch,part,motion):
    board,poses,owner,cap,model=stage_fixture(monkeypatch,part)
    if motion=='one_nm':poses[owner.GetReference()][0]+=.000001
    else:poses[owner.GetReference()][2]+=90
    before=row._source_binding(board)
    expected='complete_selected_supply_followers_required' if part.startswith('TJA') else 'positive_complete_low_power_device_pin_contract_required'
    with pytest.raises(ValueError,match=expected):
        escape.prepare(board,poses,board_hint='opaque')
    assert row._source_binding(board)==before

@pytest.mark.parametrize('part',PARTS)
@pytest.mark.parametrize('fault',['missing_pin','extra_pin','unknown_device'])
def test_stationary_witness_still_requires_complete_manufacturer_pin_identity(monkeypatch,part,fault):
    board,poses,owner,cap,model=stage_fixture(monkeypatch,part)
    if fault=='missing_pin':discard_footprint_children(board,owner,[next(iter(owner.Pads()))])
    elif fault=='extra_pin':
        pad=pcbnew.PAD(owner);pad.SetNumber('unsupported');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask());owner.Add(pad)
    else:owner.SetValue('UnknownPowerStage')
    before=row._source_binding(board)
    with pytest.raises(ValueError,match='positive_complete_low_power_device_pin_contract_required'):
        escape.prepare(board,poses,board_hint='opaque')
    assert row._source_binding(board)==before

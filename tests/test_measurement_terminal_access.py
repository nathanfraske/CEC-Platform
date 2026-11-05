"""Source topology, not net/ref/zone origin, selects an isolated input's goal."""
from unittest.mock import patch
import time
import pytest
import pcbnew
import cec_measurement_terminal_access as access
import cec_force_current as force
import cec_cell_row_rebuild as row
from test_sense_topology import native_network


def board_direct():
    b=native_network();owner=b.FindFootprintByReference('MONITOR')
    owner.FindPadByNumber('8').SetNet(b.FindNet('FORCE_A'))
    owner.FindPadByNumber('1').SetNet(b.FindNet('FORCE_B'))
    for j,fp in enumerate(sorted(b.GetFootprints(),key=lambda fp:fp.GetReference())):
        fp.SetPosition(pcbnew.VECTOR2I_MM(j*10,10))
        for k,p in enumerate(sorted(fp.Pads(),key=lambda p:p.GetNumber())):
            p.SetPosition(pcbnew.VECTOR2I_MM(j*10,k*2+10))
    return b


def get(b,**kwargs):
    # Positive current-domain evidence is injected only for this proposal
    # test; the module cannot confer numeric current or release authority.
    domains={n.GetNetname():dict(complete=True,authority_refs=['SHUNT'])
        for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    with patch('cec_current_topology.board_current_domains',return_value=domains):
        return access.requests(b,board_hint='RENAMED_SOURCE',**kwargs)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('flipped',[False,True])
def test_direct_goal_is_actual_anchor_land_under_rigid_transforms(angle,flipped):
    b=board_direct();owner=b.FindFootprintByReference('MONITOR');anchor=b.FindFootprintByReference('SHUNT')
    owner.SetReference('ARBITRARY_PACKAGE');anchor.SetReference('SHUNT')
    for fp in b.GetFootprints():
        if flipped:fp.Flip(pcbnew.VECTOR2I(0,0),True)
        fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
        fp.Move(pcbnew.VECTOR2I_MM(123,456))
    before=row._source_binding(b);q=get(b)
    assert len(q['requests'])==2 and before==row._source_binding(b)
    for d in q['requests']:
        target=anchor.FindPadByNumber('a' if d['input_pin']=='8' else 'b')
        assert d['target_uuid']==force._uid(target) and d['b_nm']==list(target.GetPosition())
        assert d['source_layer_ids']==[pcbnew.B_Cu if flipped else pcbnew.F_Cu]
        assert not d['current_capacity_qualified'] and not d['kelvin_qualified'] and not d['release_authority']


def test_filtered_goal_is_first_series_land_never_shunt_bypass():
    b=board_direct();owner=b.FindFootprintByReference('MONITOR')
    owner.FindPadByNumber('8').SetNet(b.FindNet('INPUT_A'))
    owner.FindPadByNumber('1').SetNet(b.FindNet('INPUT_B'))
    q=get(b);assert len(q['requests'])==2
    for d in q['requests']:
        resistor=b.FindFootprintByReference('SERIES_A' if d['input_pin']=='8' else 'SERIES_B')
        assert d['target_uuid']==force._uid(resistor.FindPadByNumber('right'))
        assert d['source_topology']['kind']=='filtered'


def test_source_connected_input_is_not_an_additive_isolated_demand():
    b=board_direct();root=b.FindFootprintByReference('MONITOR').FindPadByNumber('8')
    t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(root.GetNetCode());t.SetWidth(200000)
    t.SetStart(root.GetPosition());t.SetEnd(root.GetPosition()+pcbnew.VECTOR2I_MM(1,0));b.Add(t)
    assert force._uid(root) not in {d['pad_uuid'] for d in get(b)['requests']}


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_explicit_partial_input_request_preserves_its_native_prefix(angle):
    b=board_direct();root=b.FindFootprintByReference('MONITOR').FindPadByNumber('8')
    t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(root.GetNetCode());t.SetWidth(200000)
    t.SetStart(root.GetPosition());t.SetEnd(root.GetPosition()+pcbnew.VECTOR2I_MM(1,0));b.Add(t)
    for fp in b.GetFootprints():fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    t.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    before=row._source_binding(b)
    q=next(d for d in get(b,allow_partial_inputs=True)['requests'] if d['pad_uuid']==force._uid(root))
    assert q['preserved_source_prefix'] and q['source_input_island_uuids']==sorted([force._uid(root),force._uid(t)])
    assert before==row._source_binding(b) and not q['current_capacity_qualified']


@pytest.mark.parametrize('fault',['power_pin','external_pad','barrel','zone','wide','noncanonical'])
def test_partial_input_opt_in_cannot_acquire_unknown_or_load_copper(fault):
    b=board_direct();owner=b.FindFootprintByReference('MONITOR');root=owner.FindPadByNumber('8')
    end=root.GetPosition()+pcbnew.VECTOR2I_MM(1,0)
    t=pcbnew.PCB_TRACK(b);t.SetLayer(pcbnew.F_Cu);t.SetNetCode(root.GetNetCode());t.SetWidth(200000)
    t.SetStart(root.GetPosition());t.SetEnd(end);b.Add(t)
    if fault in ('power_pin','external_pad'):
        peer=(owner.FindPadByNumber('6') if fault=='power_pin' else b.FindFootprintByReference('SERIES_A').FindPadByNumber('left'))
        peer.SetNet(root.GetNet());peer.SetPosition(end)
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetPosition(end);v.SetNet(root.GetNet());v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='zone':
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNet(root.GetNet());z.Outline().NewOutline()
        for xy in ((end.x-500000,end.y-500000),(end.x+500000,end.y-500000),(end.x+500000,end.y+500000),(end.x-500000,end.y+500000)):
            z.Outline().Append(*xy)
        z.SetFilledPolysList(pcbnew.F_Cu,z.Outline());z.SetIsFilled(True);b.Add(z)
    elif fault=='wide':t.SetWidth(400000)
    else:t.SetEnd(root.GetPosition()+pcbnew.VECTOR2I_MM(1,.2))
    assert force._uid(root) not in {d['pad_uuid'] for d in get(b,allow_partial_inputs=True)['requests']}


def test_partial_input_mode_requires_explicit_boolean():
    with pytest.raises(ValueError):get(board_direct(),allow_partial_inputs=1)


@pytest.mark.parametrize('fault',['unknown_mpn','wrong_package','dnp','ambiguous_anchor','incomplete_domain'])
def test_missing_positive_evidence_never_chooses_nearest_whole_net(fault):
    b=board_direct();fp=b.FindFootprintByReference('MONITOR')
    if fault=='unknown_mpn':fp.SetValue('UNKNOWN_INPUT')
    elif fault=='wrong_package':fp.SetFPID(pcbnew.LIB_ID('fixture','SOT-23-5'))
    elif fault=='dnp':fp.SetDNP(True)
    elif fault=='ambiguous_anchor':
        other=b.FindFootprintByReference('SERIES_A')
        for p in other.Pads():p.SetNet(b.FindNet('FORCE_A' if p.GetNumber()=='left' else 'FORCE_B'))
        domains={n:dict(complete=True,authority_refs=['SHUNT','SERIES_A']) for n in ('FORCE_A','FORCE_B')}
        with patch('cec_current_topology.board_current_domains',return_value=domains):
            q=access.requests(b,board_hint='RENAMED_SOURCE')
        assert not q['requests'];return
    else:
        with patch('cec_current_topology.board_current_domains',return_value={}):
            q=access.requests(b,board_hint='RENAMED_SOURCE')
        assert not q['requests'];return
    try:q=get(b)
    except ValueError:return  # A malformed manufacturer/package contract fails closed.
    assert not q['requests']


@pytest.mark.parametrize('kwargs',[{'timeout_s':True},{'timeout_s':11},{'timeout_s':float('nan')},
    {'max_requests':True},{'max_requests':0},{'max_requests':65}])
def test_inventory_work_is_explicit_finite_and_bounded(kwargs):
    with pytest.raises(ValueError):get(board_direct(),**kwargs)


def test_request_bound_refuses_partial_positive_portfolio():
    with pytest.raises(ValueError,match='request_bound'):get(board_direct(),max_requests=1)


def test_expired_work_never_returns_positive_demands(monkeypatch):
    b=board_direct();actual=access.row._source_binding
    def slow(board):
        value=actual(board);time.sleep(.01);return value
    monkeypatch.setattr(access.row,'_source_binding',slow)
    with pytest.raises(ValueError,match='deadline'):get(b,timeout_s=.001)

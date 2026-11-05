"""Final scalar routing must not take over a specialized electrical pair."""
import pcbnew
import pytest

import cec_fr
import cec_pair_semantics as semantics


def fixture(tmp_path, names, *, monitor=False, offset=0., angle=0.,package='SOIC'):
    board=pcbnew.CreateEmptyBoard()
    for name in names:board.Add(pcbnew.NETINFO_ITEM(board,name))
    # KiCad drops orphan net declarations on save. Give every test net a
    # live terminal so the loaded-board case actually exercises its identity.
    for index,name in enumerate(names):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('TERMINAL_'+str(index));board.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(board.FindNet(name))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetSize(pcbnew.VECTOR2I_MM(.5,.8))
        pad.SetPosition(pcbnew.VECTOR2I_MM(40+index,40));fp.Add(pad)
    if monitor:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_MONITOR')
        fp.SetValue('INA240A2');board.Add(fp)
        if package=='SOIC':
            fp.SetField('MPN','INA240A2DR');fp.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
        elif package=='TSSOP':
            fp.SetField('MPN','INA240A2PWR');fp.SetFPID(pcbnew.LIB_ID('Package_SO','TSSOP-8_3x3mm_P0.65mm'))
        fp.SetPosition(pcbnew.VECTOR2I_MM(20+offset,20));fp.SetOrientationDegrees(angle)
        # TI SBOS662C table 6-1: the SOIC and TSSOP inputs differ.
        numbers=('2','3') if package=='TSSOP' else ('8','1')
        for number,name in zip(numbers,names):
            pad=pcbnew.PAD(fp);pad.SetNumber(number);pad.SetNet(board.FindNet(name))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetSize(pcbnew.VECTOR2I_MM(.5,.8));fp.Add(pad)
    path=tmp_path/'native.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    return path


@pytest.mark.parametrize('prefix,suffix', [('', '_BRANCH42'),('/sheet/', '_PORT'),('/renamed/deeper/', '_9')])
def test_loaded_series_bus_members_are_not_scalar_routes(tmp_path,prefix,suffix):
    names=[prefix+'CAN_H'+suffix,prefix+'CAN_L'+suffix,
           prefix+'USB_DP'+suffix,prefix+'USB_DM'+suffix,
           prefix+'CAN_RX',prefix+'CAN_TX',prefix+'USB_CC1',prefix+'GPIO']
    path=fixture(tmp_path,names);original=path.read_bytes();board=pcbnew.LoadBoard(str(path))
    specialized={net for _,p,n in semantics.coupled_pair_names(board) for net in (p,n)}
    assert specialized==set(names[:4])
    eligible=cec_fr._ordinary_final_completion_nets(board,lambda net:{'track_width':.2})
    assert not set(eligible)&specialized
    assert set(eligible)==set(names[4:])
    assert path.read_bytes()==original


@pytest.mark.parametrize('package',['SOIC','TSSOP'])
def test_actual_selected_package_protects_its_inputs(package,tmp_path):
    path=fixture(tmp_path,['/opaque/a','/opaque/b','/CONTROL'],monitor=True,package=package)
    board=pcbnew.LoadBoard(str(path));pairs=semantics.analog_input_pairs(board)
    assert len(pairs)==1 and pairs[0]['pins']==(['8','1'] if package=='SOIC' else ['2','3'])
    assert not semantics.unresolved_current_monitor_nets(board)
    assert cec_fr._ordinary_final_completion_nets(board,lambda net:{'track_width':.2})==('/CONTROL',)


def test_missing_monitor_package_holds_anonymous_inputs_without_guessing(tmp_path):
    path=fixture(tmp_path,['/opaque/a','/opaque/b','/CONTROL'],monitor=True,package=None)
    saved=path.read_bytes();board=pcbnew.LoadBoard(str(path))
    assert semantics.analog_input_pairs(board)==[]
    assert semantics.unresolved_current_monitor_nets(board)=={'/opaque/a','/opaque/b'}
    assert cec_fr._ordinary_final_completion_nets(board,lambda net:{'track_width':.2})==('/CONTROL',)
    assert path.read_bytes()==saved


@pytest.mark.parametrize('offset,angle', [(0.,0.),(91.5,180.),(-3.,90.)])
def test_device_input_contract_protects_arbitrarily_named_analog_pair(tmp_path,offset,angle):
    names=['/renamed/a','/renamed/b','/CONTROL']
    path=fixture(tmp_path,names,monitor=True,offset=offset,angle=angle)
    original=path.read_bytes();board=pcbnew.LoadBoard(str(path))
    assert not semantics.coupled_pair_names(board)
    assert len(semantics.analog_input_pairs(board))==1
    assert cec_fr._ordinary_final_completion_nets(board,lambda net:{'track_width':.2})==('/CONTROL',)
    assert path.read_bytes()==original


def test_unrelated_hierarchies_are_not_joined_and_default_dimensions_do_not_define_pair(tmp_path):
    path=fixture(tmp_path,['/left/CAN_H_PORT','/right/CAN_L_PORT','/STATUS'])
    board=pcbnew.LoadBoard(str(path))
    assert not semantics.coupled_pair_names(board)
    # Pair dimensions on KiCad's default class do not classify a scalar net.
    eligible=cec_fr._ordinary_final_completion_nets(board,lambda net:{
        'track_width':.2,'diff_pair_width':.2,'diff_pair_gap':.25})
    assert '/STATUS' in eligible


def test_identity_failure_cannot_silently_fall_back_to_name_guess(monkeypatch,tmp_path):
    path=fixture(tmp_path,['/CONTROL']);board=pcbnew.LoadBoard(str(path))
    def fail(*args,**kwargs):raise ValueError('invalid identity evidence')
    monkeypatch.setattr(semantics,'coupled_pair_names',fail)
    with pytest.raises(ValueError,match='identity evidence'):
        cec_fr._ordinary_final_completion_nets(board,lambda net:{'track_width':.2})


def test_loaded_scalar_dispatch_connects_control_but_emits_no_pair_copper(tmp_path):
    from test_lastmile import _board
    board=_board([(5,5,'/PORT/CAN_H_LEG'),(8,5,'/PORT/CAN_H_LEG'),
                  (5,7,'/PORT/CAN_L_LEG'),(8,7,'/PORT/CAN_L_LEG'),
                  (5,10,'/CONTROL'),(8,10,'/CONTROL')],edge=(0,0,15,15))
    path=tmp_path/'dispatch.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    original=path.read_bytes();board=pcbnew.LoadBoard(str(path))
    resolver=lambda net:{'track_width':.2,'clearance':.2}
    eligible=cec_fr._ordinary_final_completion_nets(board,resolver)
    assert eligible==('/CONTROL',)
    report=cec_fr.synthesize_lastmile(board,include_nets=eligible,netclass_resolver=resolver,
        max_mm=10,cap=4,wall_timeout_s=5)
    assert report['closed']==1
    assert {t.GetNetname() for t in board.GetTracks()}=={'/CONTROL'}
    assert path.read_bytes()==original


@pytest.mark.parametrize('prefix', ['', '/renamed/', '/deep/arbitrary/'])
@pytest.mark.parametrize('rail', ['+5V_SYS_PORT', '-12V', 'ATX_NEG12V',
    '5VSB_MUX', '3V3', 'GND_LOCAL', '12V_AUX'])
def test_hierarchical_voltage_leaves_never_become_ordinary(tmp_path,prefix,rail):
    name=prefix+rail
    path=fixture(tmp_path,[name,'/STATUS','/DET12V','/ADC12V'])
    board=pcbnew.LoadBoard(str(path));old=path.read_bytes()
    eligible=cec_fr._ordinary_final_completion_nets(board,lambda net:{'track_width':.2})
    assert name not in eligible
    assert {'/STATUS','/DET12V','/ADC12V'} <= set(eligible)
    assert path.read_bytes()==old


def resistor_junction(name, *, values=('15kΩ','10kΩ','100kΩ'), kind='R_0402_1005Metric'):
    board=pcbnew.BOARD();board.Add(pcbnew.NETINFO_ITEM(board,name))
    board.Add(pcbnew.NETINFO_ITEM(board,'/unrelated/elsewhere'))
    for index,value in enumerate(values):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_'+str(index));fp.SetValue(value)
        fp.SetFPID(pcbnew.LIB_ID('vendor-library',kind));board.Add(fp)
        for number,net in [('1',name),('2','/unrelated/elsewhere')]:
            pad=pcbnew.PAD(fp);pad.SetNumber(number);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetSize(pcbnew.VECTOR2I_MM(.5,.8))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10+index,10+int(number)))
            pad.SetNet(board.FindNet(net));fp.Add(pad)
    return board


@pytest.mark.parametrize('name',['NEG12V_DIV','/unknown/7V_READBACK','/renamed/POS24V_SUM'])
def test_native_passive_junction_can_override_lexical_rail_guess(name):
    board=resistor_junction(name)
    assert cec_fr._native_resistor_only_junction(board,name)
    assert name in cec_fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})


@pytest.mark.parametrize('values,kind',[(('0R','10k','100k'),'R_0402_1005Metric'),
    (('999','10k','100k'),'R_0402_1005Metric'),(('unknown','10k','100k'),'R_0402_1005Metric'),
    (('10k','10k','100k'),'C_0402_1005Metric')])
def test_unknown_component_or_low_ohm_link_cannot_demote_power(values,kind):
    name='/renamed/NEG12V_DIV';board=resistor_junction(name,values=values,kind=kind)
    assert not cec_fr._native_resistor_only_junction(board,name)
    assert name not in cec_fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})


def test_any_extra_terminal_or_explicit_current_authority_keeps_owner(monkeypatch):
    name='/renamed/NEG12V_DIV';board=resistor_junction(name)
    import cec_synth_pipeline as synth
    monkeypatch.setattr(synth,'spec_net_current_contract',lambda hint,n:dict(amps=3.))
    assert name not in cec_fr._ordinary_final_completion_nets(board,lambda n:{'track_width':.2})
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('external');board.Add(fp)
    p=pcbnew.PAD(fp);p.SetNumber('1');p.SetNet(board.FindNet(name));fp.Add(p)
    assert not cec_fr._native_resistor_only_junction(board,name)

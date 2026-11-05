"""Physical C6 EN8 Source topology; no name-based GPIO or RC permission."""
import pcbnew
import pytest
import re
import cec_device_power_roles as roles
import cec_source_ground_leaf as leaf
import cec_synth_pipeline as synth
import cec_force_current as force
from test_c6_boot_strap_shunt import fixture as boot_fixture


def pin_type(text,name,num,kind):
    pattern=r'\(pin (passive|input|bidirectional)(?= line \(at [^)]+\) \(length 1\) \(name "'+name+r'"\) \(number "'+num+r'"\))'
    result,count=re.subn(pattern,'(pin '+kind,text)
    assert count==1
    return result


def fixture(tmp_path,monkeypatch):
    b,m,c,r,s,root,tree=boot_fixture(tmp_path,monkeypatch)
    code=m.FindPadByNumber('23').GetNetCode()
    m.FindPadByNumber('23').SetNetCode(0);m.FindPadByNumber('8').SetNetCode(code)
    root.write_text(pin_type(root.read_text().replace('(name "P8")','(name "EN")'),'EN','8','input'))
    for net in synth._kids(synth._first(tree,'nets'),'net'):
        for node in synth._kids(net,'node'):
            if synth._val(node,'ref','')=='controller'and synth._val(node,'pin','')=='23':
                synth._first(node,'pin')[1]='8'
    return b,m,c,r,s,root,tree


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_exact_physical_en8_source_role_and_four_peers(tmp_path,monkeypatch,turn,back):
    b,m,c,r,s,root,tree=fixture(tmp_path,monkeypatch)
    for f in b.GetFootprints():
        f.SetOrientationDegrees(turn*90)
        if back:f.Flip(pcbnew.VECTOR2I(0,0),False)
    role=roles.control_shunt_input_contract(m,'8')
    assert role and role['role']=='enable_reset_input'and role['function']=='EN'
    assert role['requires_complete_pullup_button_topology']is True
    result=leaf.plan(b,board_hint=str(root))
    q=result['proofs'].get(force._uid(c.FindPadByNumber('2')))
    assert result['complete']and q,result['refused']
    assert len(q['control_peers'])==4 and q['manufacturer']==role
    assert q['functional_ground_return']is False and q['current_authority']is False
    assert q['reset_timing_qualified']is False and q['release_authority']is False
    assert roles.control_shunt_input_contract(m,'12')is None


@pytest.mark.parametrize('fault',['source_name','source_type','native_name','native_type','wrong_mpn',
    'wrong_package','duplicate_pin','wrong_power','wrong_ground','missing_pull','missing_button',
    'wrong_pull_end','wrong_switch_end','wrong_cap_ground_type','extra_peer','stale_uuid'])
def test_no_en_authority_from_partial_or_contradictory_source(tmp_path,monkeypatch,fault):
    b,m,c,r,s,root,tree=fixture(tmp_path,monkeypatch)
    if fault=='source_name':root.write_text(root.read_text().replace('(name "EN")','(name "GPIO0")'))
    elif fault=='source_type':root.write_text(pin_type(root.read_text(),'EN','8','bidirectional'))
    elif fault=='native_name':m.FindPadByNumber('8').SetPinFunction('IO9')
    elif fault=='native_type':m.FindPadByNumber('8').SetPinType('output')
    elif fault=='wrong_mpn':m.SetField('MPN','ESP32-C6-MINI-1-N8')
    elif fault=='wrong_package':m.SetFPID(pcbnew.LIB_ID('RF_Module','ESP32-S3-MINI-1'))
    elif fault=='duplicate_pin':m.FindPadByNumber('53').SetNumber('8')
    elif fault=='wrong_power':m.FindPadByNumber('3').SetNetCode(c.FindPadByNumber('2').GetNetCode())
    elif fault=='wrong_ground':m.FindPadByNumber('1').SetNetCode(0)
    elif fault=='missing_pull':b.Remove(r)
    elif fault=='missing_button':b.Remove(s)
    elif fault=='wrong_pull_end':r.FindPadByNumber('1').SetNetCode(c.FindPadByNumber('2').GetNetCode())
    elif fault=='wrong_switch_end':s.FindPadByNumber('1').SetNetCode(r.FindPadByNumber('1').GetNetCode())
    elif fault=='wrong_cap_ground_type':
        text=root.read_text();start=text.index('(symbol "fixture:C"');end=text.index('(symbol "fixture:R"')
        chunk=pin_type(text[start:end],'P2','2','input')
        root.write_text(text[:start]+chunk+text[end:])
    elif fault=='extra_peer':m.FindPadByNumber('12').SetNetCode(m.FindPadByNumber('8').GetNetCode())
    elif fault=='stale_uuid':
        comp=next(synth._kids(synth._first(tree,'components'),'comp'));synth._first(comp,'tstamps')[1]='stale'
    result=leaf.plan(b,board_hint=str(root))
    assert force._uid(c.FindPadByNumber('2'))not in result['proofs'],result

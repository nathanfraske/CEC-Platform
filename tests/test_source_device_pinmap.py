"""Blank native labels require the entire freshly parsed manufacturer Source."""
import hashlib
import uuid
import pytest
import cec_device_power_roles as roles
import cec_source_device_pinmap as checker
import cec_source_ground_leaf as canonical
import cec_synth_pipeline as synth
from test_c6_device_physical_pinmap import fixture as native_fixture


def fixture(tmp_path, monkeypatch, turn=0, back=False):
    board, fp = native_fixture(turn, back)
    board.SetFileName(str(tmp_path/'native.kicad_pcb'))
    model = roles.footprint_contract(fp)
    pins=[]; nodes={}; uid=str(uuid.uuid4()); ref=fp.GetReference()
    for number, role in model['pins'].items():
        kind=('power_in' if role in ('ground','power_input') else 'no_connect'
              if role=='no_connect' else 'input' if number=='8' else 'bidirectional')
        pins.append(f'(pin {kind} line (at {int(number)} 0 0) (length 1) '
                    f'(name "{model["native_pin_functions"][number]}") (number "{number}"))')
        pad=next(p for p in fp.Pads() if p.GetNumber()==number)
        nodes.setdefault(pad.GetNetname(), []).append(number)
    props={'Reference':ref,'Value':fp.GetValue(),'Footprint':fp.GetFPIDAsString(),
           'MPN':fp.GetField('MPN').GetText()}
    root=tmp_path/'source.kicad_sch'
    root.write_text('(kicad_sch (version 20250114) (uuid "'+str(uuid.uuid4())+'") '
        '(lib_symbols (symbol "fixture:Module" (symbol "body_1_1" '+' '.join(pins)+'))) '
        '(symbol (lib_id "fixture:Module") (at 0 0 0) (unit 1) (uuid "'+uid+'") '+
        ' '.join(f'(property "{k}" "{v}")' for k,v in props.items())+'))')
    tree=synth.parse_sexpr('(export (components (comp (ref "'+ref+'") '
        '(value "'+fp.GetValue()+'") (footprint "'+fp.GetFPIDAsString()+'") '
        '(property (name "MPN") (value "'+props['MPN']+'")) (tstamps "'+uid+'"))) '
        '(nets '+' '.join('(net (name "'+net+'") '+' '.join(
            f'(node (ref "{ref}") (pin "{n}"))' for n in nums)+')'
            for net,nums in nodes.items())+'))')
    def export(path, deadline):
        assert path==root and deadline>checker.time.monotonic()
        return tree,dict(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest())
    monkeypatch.setattr(canonical,'_export',export)
    for p in fp.Pads():p.SetPinFunction('');p.SetPinType('')
    return board,fp,model,root,tree


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_fresh_canonical_blank_native_full_inventory(tmp_path,monkeypatch,turn,back):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch,turn,back)
    before=[(p.m_Uuid.AsString(),tuple(p.GetPosition()),p.GetPinFunction(),p.GetPinType()) for p in fp.Pads()]
    proof=checker.prove(fp,model,board_hint=str(root))
    assert len(proof['logical_pins'])==53 and len(proof['native_pad_nets'])==61
    assert not proof['current_authority'] and not proof['pose_or_cut_authority']
    assert sum(map(len,roles.physical_pinmap(fp,model,board_hint=str(root)).values()))==61
    assert before==[(p.m_Uuid.AsString(),tuple(p.GetPosition()),p.GetPinFunction(),p.GetPinType()) for p in fp.Pads()]


@pytest.mark.parametrize('fault',['name','type','missing','duplicate','extends','duplicate_symbol',
    'malformed','identity','export_identity','one49','duplicate_net_pin','missing_net_pin'])
def test_source_contradictions_never_authorize_blank_native(tmp_path,monkeypatch,fault):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch)
    text=root.read_text()
    if fault=='name':text=text.replace('(name "EN")','(name "FAKE")')
    elif fault=='type':text=text.replace('(pin input line','(pin output line')
    elif fault=='missing':text=text.replace('(number "53")','(number "54")')
    elif fault=='duplicate':text=text.replace('(number "53")','(number "52")')
    elif fault=='extends':text=text.replace('(symbol "fixture:Module"','(symbol "fixture:Module" (extends "other")',1)
    elif fault=='duplicate_symbol':text=text.replace('(lib_symbols','(lib_symbols (symbol "fixture:Module")',1)
    elif fault=='malformed':text='(not_a_schematic)'
    elif fault=='identity':text=text.replace('ESP32-C6-MINI-1-N4','WRONG')
    elif fault=='export_identity':synth._first(synth._first(tree,'components')[1],'tstamps')[1]='wrong'
    elif fault=='one49':
        next(p for p in fp.Pads() if p.GetNumber()=='49').SetNet(next(p for p in fp.Pads() if p.GetNumber()=='3').GetNet())
    else:
        net=synth._first(tree,'nets')[1]
        if fault=='duplicate_net_pin':net.append(list(net[2]))
        else:net.pop(2)
    root.write_text(text)
    with pytest.raises((ValueError,KeyError,IndexError)):
        checker.prove(fp,model,board_hint=str(root))


def test_blank_requires_hint_and_mixed_labels_never_fallback(tmp_path,monkeypatch):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):roles.physical_pinmap(fp,model)
    next(iter(fp.Pads())).SetPinFunction('GND')
    with pytest.raises(ValueError,match='complete_native_manufacturer'):
        roles.physical_pinmap(fp,model,board_hint=str(root))


@pytest.mark.parametrize('lease',[0,-1,11,float('inf'),float('nan'),True])
def test_invalid_bounded_lease(tmp_path,monkeypatch,lease):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):checker.prove(fp,model,board_hint=str(root),timeout_s=lease)


def test_wrong_hint_and_shared_deadline_expiry(tmp_path,monkeypatch):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch)
    with pytest.raises((ValueError,FileNotFoundError)):
        checker.prove(fp,model,board_hint=str(tmp_path/'missing.kicad_sch'))
    original=canonical._export
    def expired(path,deadline):
        result=original(path,deadline)
        monkeypatch.setattr(checker.time,'monotonic',lambda:deadline+1)
        return result
    monkeypatch.setattr(canonical,'_export',expired)
    with pytest.raises(ValueError,match='deadline'):
        checker.prove(fp,model,board_hint=str(root))


def test_live_source_changes_refuse_after_export(tmp_path,monkeypatch):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch)
    original=canonical._export
    def changed(path,deadline):
        result=original(path,deadline);root.write_text(root.read_text()+'\n');return result
    monkeypatch.setattr(canonical,'_export',changed)
    with pytest.raises(ValueError,match='live_binding_changed'):
        checker.prove(fp,model,board_hint=str(root))


def test_live_native_binding_changes_refuse_after_export(tmp_path,monkeypatch):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch)
    original=canonical._export
    def changed(path,deadline):
        result=original(path,deadline);fp.SetPosition(fp.GetPosition()+__import__('pcbnew').VECTOR2I(1,0));return result
    monkeypatch.setattr(canonical,'_export',changed)
    with pytest.raises(ValueError,match='live_binding_changed'):
        checker.prove(fp,model,board_hint=str(root))


def test_export_and_hierarchy_share_one_original_lease(tmp_path,monkeypatch):
    board,fp,model,root,tree=fixture(tmp_path,monkeypatch)
    original_hierarchy=canonical._hierarchy;original_export=canonical._export;seen=[]
    def hierarchy(path,deadline):
        seen.append(deadline);return original_hierarchy(path,deadline)
    def export(path,deadline):
        seen.append(deadline);return original_export(path,deadline)
    monkeypatch.setattr(canonical,'_hierarchy',hierarchy)
    monkeypatch.setattr(canonical,'_export',export)
    checker.prove(fp,model,board_hint=str(root),timeout_s=.8)
    assert len(seen)==2 and seen[0]==seen[1]

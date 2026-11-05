from unittest.mock import patch
import json
import pytest
import pcbnew
import cec_fr, cec_precision_route, cec_constraints
import cec_placement_route_prefix as prefix


def board_file(tmp_path, *, disconnected=False, ground_trunk=False):
    b=pcbnew.BOARD();nets={}
    for name in ('P','N','GND'):
        nets[name]=pcbnew.NETINFO_ITEM(b,name);b.Add(nets[name])
    for index,name in enumerate(('P','N')):
        for x in (2,8):
            fp=pcbnew.FOOTPRINT(b);fp.SetReference(name+str(x));b.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNet(nets[name]);pad.SetNumber('1')
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
            layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
            pad.SetPosition(pcbnew.VECTOR2I_MM(x,index+2));fp.Add(pad)
        starts=(2,8) if disconnected else (2,)
        for x in starts:
            t=pcbnew.PCB_TRACK(b);t.SetNet(nets[name]);t.SetLayer(pcbnew.F_Cu)
            t.SetWidth(pcbnew.FromMM(.2));t.SetStart(pcbnew.VECTOR2I_MM(x,index+2))
            t.SetEnd(pcbnew.VECTOR2I_MM(x+.2 if disconnected else 8,index+2))
            t.SetLocked(True);b.Add(t)
    vias=[]
    for x in (2,20):
        via=pcbnew.PCB_VIA(b);via.SetNet(nets['GND']);via.SetPosition(pcbnew.VECTOR2I_MM(x,5))
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetWidth(pcbnew.FromMM(.6));via.SetDrill(pcbnew.FromMM(.3));via.SetLocked(True)
        b.Add(via);vias.append(via)
    cec_fr.group_local_pair_return_vias(b,[vias[0]])
    if ground_trunk:
        t=pcbnew.PCB_TRACK(b);t.SetNet(nets['GND']);t.SetLayer(pcbnew.F_Cu)
        t.SetWidth(pcbnew.FromMM(1));t.SetStart(pcbnew.VECTOR2I_MM(2,5))
        t.SetEnd(pcbnew.VECTOR2I_MM(8,5));t.SetLocked(True);b.Add(t)
    target=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(target),b)
    return target,[v.m_Uuid.AsString() for v in vias]


def capture(path, *, physics_ok=True):
    with patch.object(cec_precision_route,'derive_coupled_pairs',return_value=[dict(name='pair',p='P',n='N')]), \
         patch.object(cec_constraints,'high_speed_pair_summary',return_value={'pairs':[dict(p='P',n='N',violations=[] if physics_ok else ['bad'])]}):
        return prefix.capture(path)


def test_exact_complete_pair_and_only_owned_returns_are_preserved(tmp_path):
    path,vias=board_file(tmp_path)
    result=capture(path)
    assert set(prefix.preserved_nets(result))=={'P','N'}
    assert prefix.preserved_uuids(result)==(vias[0],)
    assert result['items_by_net']=={'P':1,'N':1,'GND':1}
    assert cec_fr.check_copper_geometry_prefix(str(path),result)['ok']


def test_disconnected_locked_stubs_do_not_qualify(tmp_path):
    path,vias=board_file(tmp_path,disconnected=True)
    assert not (cec_fr.owned_locked_nets(str(path)) & {'P','N'})
    assert capture(path)['items']==0


def test_missing_physics_is_not_protection_authority(tmp_path):
    path,vias=board_file(tmp_path)
    assert capture(path,physics_ok=False)['items']==0


def test_existing_ground_power_trunk_is_not_double_counted(tmp_path):
    path,vias=board_file(tmp_path,ground_trunk=True)
    result=capture(path)
    assert result['items_by_net']['GND']==3
    assert prefix.preserved_uuids(result)==()
    assert cec_fr.check_copper_geometry_prefix(str(path),result)['ok']


def test_revalidation_rejects_changed_pair_physics(tmp_path):
    path,_vias=board_file(tmp_path)
    contract=capture(path)
    with patch.object(cec_precision_route,'derive_coupled_pairs',return_value=[dict(name='pair',p='P',n='N')]), \
         patch.object(cec_constraints,'high_speed_pair_summary',return_value={'pairs':[dict(p='P',n='N',violations=['reference plane lost'])]}):
        result=prefix.check_qualified_pairs(path,contract)
    assert result['applicable'] and not result['ok']
    assert result['pairs'][0]['connected']


def test_revalidation_rejects_changed_pair_identity(tmp_path):
    path,_vias=board_file(tmp_path)
    contract=capture(path)
    with patch.object(cec_precision_route,'derive_coupled_pairs',return_value=[]), \
         patch.object(cec_constraints,'high_speed_pair_summary',return_value={'pairs':[]}):
        assert not prefix.check_qualified_pairs(path,contract)['ok']


@pytest.mark.parametrize('scope,admission', [
    ('complete',None), ('complete',False), ('partial',True),
])
def test_unadmitted_local_copper_has_typed_refusal_without_claiming_ownership(tmp_path,scope,admission):
    path,_vias=board_file(tmp_path)
    state={'placement_scope':scope,'local_copper_contract':{'schema':1}}
    if admission is not None:state['exact_admission']={'passed':admission}
    state_path=path.with_suffix('.pourfirst-state.json')
    state_path.write_text(json.dumps(state))
    before=path.read_bytes(),state_path.read_bytes()
    with pytest.raises(prefix.UnadmittedLocalCopper) as raised:
        capture(path)
    evidence=raised.value.evidence
    assert evidence['reason']=='local_copper_lacks_admitted_frozen_authority'
    assert evidence['blocked_stage']=='frozen_power_authority'
    assert evidence['state']==str(state_path)
    assert evidence['placement_scope']==scope
    assert evidence['exact_admission_passed'] is (admission is True)
    assert evidence['grants_copper_ownership'] is False
    assert evidence['release_authority'] is False
    assert (path.read_bytes(),state_path.read_bytes())==before


def test_retention_does_not_require_or_grant_local_power_qualification(tmp_path):
    path,_vias=board_file(tmp_path)
    state_path=path.with_suffix('.pourfirst-state.json')
    state_path.write_text(json.dumps({'placement_scope':'complete',
        'local_copper_contract':{'schema':1},'exact_admission':{'passed':False}}))
    before=path.read_bytes(),state_path.read_bytes()
    with patch.object(cec_precision_route,'derive_coupled_pairs',return_value=[]):
        contract=prefix.capture(path,include_local_authority=False)
    assert contract['retention_only'] and not contract['grants_local_copper_ownership']
    assert 'placement_local_copper' not in contract
    assert (path.read_bytes(),state_path.read_bytes())==before
    with pytest.raises(ValueError,match='cannot_authorize_placement'):
        prefix.rehydration_coverage(pcbnew.LoadBoard(str(path)),contract)

"""A wired address input is not a power input or a guessed small load."""
import copy
import uuid

import pcbnew
import pytest
import cec_force_current as force
import cec_source_supply_endpoint_cut as cut
import cec_synth_pipeline as synth
from test_source_device_supply_chain import fixture as power_case


def case(tmp_path,monkeypatch,**kwargs):
    f=power_case(tmp_path,monkeypatch,**kwargs)
    address=f['owner'].FindPadByNumber('2');power=f['pad']
    a,b=address.GetPosition(),power.GetPosition()
    address.SetPosition(b);power.SetPosition(a);address.SetNet(power.GetNet())
    root=f['root']
    root.write_text(root.read_text().replace('(pin bidirectional line (at 2 ',
        '(pin input line (at 2 '))
    nets=synth._first(f['tree'],'nets')
    for net in synth._kids(nets,'net'):
        net[:]=[node for node in net if not(isinstance(node,list)and node
            and node[0]=='node'and synth._val(node,'pin','')=='2')]
    rail=next(net for net in synth._kids(nets,'net')if synth._val(net,'name','')==power.GetNetname())
    rail.append(['node',['ref',f['owner'].GetReference()],['pin','2']])
    f.update(address=address,power=power)
    return f


def plan(f,**kwargs):
    return cut.plan(f['board'],f['posed'](),board_hint=str(f['root']),
        source_floor=lambda t:(500000,200000),allow_locked=True,**kwargs)


@pytest.mark.parametrize('face', [pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('turn', [0,90,180,270])
def test_rotated_renamed_complete_address_chain_preserves_whole_rail(tmp_path,monkeypatch,face,turn):
    f=case(tmp_path,monkeypatch,face=face,turn=turn,offset=(21,17))
    before=f['root'].read_bytes(), {force._uid(t):[list(t.GetStart()),list(t.GetEnd()),t.GetWidth(),t.IsLocked()]
        for t in f['board'].GetTracks()}
    q,=plan(f);authority=q['source_authority']
    assert q['pad_uuid']==force._uid(f['address'])
    assert authority['scope']=='fresh_source_manufacturer_supply_tied_address'
    assert authority['pin']=='2'and authority['power_input_pin']=='6'
    assert authority['source_power_input_authority']['scope']=='fresh_source_manufacturer_power_input'
    assert authority['source_address_electrical_type']=='input'
    assert authority['address_role_not_reclassified']and authority['address_load_not_inferred']
    assert len(authority['complete_pin_nets'])==10 and not authority['current_authority']
    assert q['width_nm']==500000 and q['unchanged_full_rail_current_contract']==f['contract']
    assert set(q['retired_track_uuids'])=={force._uid(t)for t in f['chain']}
    assert q['retained_throat_track_uuids']==[force._uid(f['carrier'])]
    assert q['remaining_group_members']==[force._uid(f['residue'])]
    assert not q['new_thin_allowance']and not q['saved_candidate_authorized']
    assert before==(f['root'].read_bytes(),{force._uid(t):[list(t.GetStart()),list(t.GetEnd()),t.GetWidth(),t.IsLocked()]
        for t in f['board'].GetTracks()})


@pytest.mark.parametrize('fault', ['native_tie','export_tie','embedded_output','embedded_partial',
    'source_mpn','native_mpn','native_name','native_type','address_nc','dnp','other_role',
    'extra_land','side_tap','zone','barrel','group_locked','no_carrier','current_unknown'])
def test_address_chain_never_borrows_a_name_or_partial_source(tmp_path,monkeypatch,fault):
    import cec_decoupler_cell as cells
    f=case(tmp_path,monkeypatch);root=f['root'];board=f['board'];owner=f['owner']
    if fault=='native_tie':f['power'].SetNet(owner.FindPadByNumber('1').GetNet())
    elif fault=='export_tie':
        rail=next(n for n in synth._kids(synth._first(f['tree'],'nets'),'net')
            if synth._val(n,'name','')=='renamed_supply')
        rail[:]=[n for n in rail if not(isinstance(n,list)and n and n[0]=='node'
            and synth._val(n,'pin','')=='2')]
    elif fault=='embedded_output':root.write_text(root.read_text().replace('(pin input line (at 2 ','(pin output line (at 2 '))
    elif fault=='embedded_partial':root.write_text(root.read_text().replace('(number "10")','(number "9")'))
    elif fault=='source_mpn':root.write_text(root.read_text().replace('INA238AIDGSR','UNKNOWN'))
    elif fault=='native_mpn':owner.SetField('MPN','UNKNOWN')
    elif fault=='native_name':f['address'].SetPinFunction('OUT')
    elif fault=='native_type':f['address'].SetPinType('output')
    elif fault=='address_nc':root.write_text(root.read_text()[:-1]+
        ' (no_connect (at 12 10) (uuid "'+str(uuid.uuid4())+'")))')
    elif fault=='dnp':owner.SetDNP(True)
    elif fault=='other_role':
        a=owner.FindPadByNumber('3');a.SetPosition(f['address'].GetPosition());a.SetNet(f['address'].GetNet())
        f['address'].SetPosition(pcbnew.VECTOR2I_MM(30,30))
    elif fault=='extra_land':owner.FindPadByNumber('10').SetPosition(pcbnew.VECTOR2I_MM(5.8,5))
    elif fault=='side_tap':f['edge']((5.5,5),(5.5,6),.2,grouped=False)
    elif fault=='zone':
        z=pcbnew.ZONE(board);z.SetLayer(f['face']);z.SetNet(f['address'].GetNet());z.Outline().NewOutline()
        for x,y in ((4,4),(7,4),(7,6),(4,6)):z.Outline().Append(x*1000000,y*1000000)
        board.Add(z)
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(5.8,5));v.SetWidth(600000)
        v.SetDrill(300000);v.SetNet(f['address'].GetNet());board.Add(v)
    elif fault=='group_locked':f['group'].SetLocked(True)
    elif fault=='no_carrier':f['carrier'].SetWidth(200000)
    else:monkeypatch.setattr(cells,'_supply_current_widths',lambda *a:None)
    try:result=plan(f)
    except ValueError:return
    assert not result


@pytest.mark.parametrize('fault',[None,'other_owner','other_pin','other_rail'])
def test_address_cut_keeps_its_own_power_pin_and_selected_cap_contacts(tmp_path,monkeypatch,fault):
    import cec_measurement_leaf as leaf
    f=case(tmp_path,monkeypatch);q,=plan(f);board=f['board']
    cap=pcbnew.FOOTPRINT(board);board.Add(cap);cap.SetReference('BYPASS_RENAMED')
    land=pcbnew.PAD(cap);land.SetNumber('1');land.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    land.SetLayerSet(pcbnew.PAD.SMDMask());land.SetShape(pcbnew.PAD_SHAPE_RECT)
    land.SetSize(pcbnew.VECTOR2I_MM(1.2,.4));land.SetPosition(pcbnew.VECTOR2I_MM(7.1,4.9))
    land.SetNet(f['address'].GetNet());cap.Add(land)
    proof=dict(owner=f['owner'].GetReference(),supply_pin='6',rail='renamed_supply')
    if fault=='other_owner':proof['owner']='OTHER'
    elif fault=='other_pin':proof['supply_pin']='2'  # The address is NOT VS.
    elif fault=='other_rail':proof['rail']='quiet_a'
    monkeypatch.setattr(leaf,'_bypass_supply_owner',lambda *a:copy.deepcopy(proof))
    posed=f['posed']();posed.FindFootprintByReference(cap.GetReference()).Move(pcbnew.VECTOR2I_MM(0,-.4))
    action=lambda:cut.retained_throat_contacts(board,posed,[q],board_hint=str(f['root']))
    if fault:
        with pytest.raises(ValueError):action()
    else:
        r,=action();assert r['lost_moving_contacts'][0]['pad_uuid']==force._uid(land)
        assert r['literal_source_throat_retained']and not r['saved_candidate_authorized']


def test_address_cut_discloses_moving_same_package_power_contact(tmp_path,monkeypatch):
    f=case(tmp_path,monkeypatch)
    f['power'].SetPosition(pcbnew.VECTOR2I_MM(7.2,4.9))
    q,=plan(f)
    r,=cut.retained_throat_contacts(f['board'],f['posed'](),[q],board_hint=str(f['root']))
    contact,=r['lost_moving_contacts']
    assert contact['pad_uuid']==force._uid(f['power'])
    assert contact['source_contact_nm']==[list(f['carrier'].GetEnd())]
    assert contact['source_companion_authority']['scope']=='fresh_source_manufacturer_power_input'
    assert contact['source_companion_authority']['pin']=='6'
    assert contact['exact_old_port_reconstruction_mandatory']

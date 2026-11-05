"""Legacy width may shrink only above the same real load/process requirements."""
import copy
import pcbnew,pytest
import cec_force_current as force
import cec_current_topology as topology
import cec_native_current_route_width as sizing
from test_lastmile import _board
from test_field_proposals import track


def fixture(monkeypatch,face=0):
    net='/renamed/SMALL_SUPPLY';board=_board([(5,5,net),(15,5,net)],edge=(0,0,20,20))
    board.GetDesignSettings().m_TrackMinWidth=200000
    item=track(board,net,(5,5),(15,5),layer=face,width=1.)
    refs=sorted(f.GetReference() for f in board.GetFootprints())
    domain=dict(net=net,amps=.5,complete=True,source_refs=refs[:1],sink_refs=refs[1:],authority_refs=refs)
    contract=dict(net=net,amps=.5,authority_refs=refs,routing_layers=['F.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':.15,'B.Cu':.15},current_authority=dict(amps=.5,geometry_margin=1.25,margin_included=False))
    monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:{net:copy.deepcopy(domain)})
    monkeypatch.setattr(topology,'route_width_contracts',lambda *a,**kw:{net:copy.deepcopy(contract)})
    row=dict(uid=force._uid(item),net=net,layer=face,width=item.GetWidth())
    return board,item,row,domain,contract


@pytest.mark.parametrize('face',[0,2])
@pytest.mark.parametrize('width',[200000,300000,800000])
def test_explicit_full_load_width_does_not_infer_a_smaller_load_or_new_layer(monkeypatch,face,width):
    board,item,row,domain,contract=fixture(monkeypatch,face);before=item.GetWidth()
    plan=sizing.plan(board,'synthetic.kicad_pcb',row,board_hint='synthetic',width_nm=width)
    assert plan['unchanged_current_domain']==domain and plan['unchanged_whole_source_contract']==contract
    assert plan['replacement_width_nm']==width and plan['native_board_minimum_nm']==200000
    assert item.GetWidth()==before and not plan['current_qualified'] and not plan['release_authority']


@pytest.mark.parametrize('mode',['below_current','below_fab','unknown_current','no_domain','main_bus','layer','net','width','group','pair','gnd','bool'])
def test_source_authority_and_critical_geometry_cannot_be_waived(monkeypatch,mode):
    board,item,row,domain,contract=fixture(monkeypatch);width=200000
    if mode=='below_current':contract['required_by_layer_mm']['F.Cu']=.3
    elif mode=='below_fab':board.GetDesignSettings().m_TrackMinWidth=300000
    elif mode=='unknown_current':contract['required_by_layer_mm']['F.Cu']=float('nan')
    elif mode=='no_domain':domain['complete']=False
    elif mode=='main_bus':contract['required_by_layer_mm']['F.Cu']=6.5
    elif mode in ('layer','width'):row[mode]+=1
    elif mode=='net':row['net']='/wrong'
    elif mode=='group':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(item)
    elif mode in ('pair','gnd'):
        name='/USB_D_P' if mode=='pair' else 'GND';board.Add(pcbnew.NETINFO_ITEM(board,name))
        item.SetNetCode(board.GetNetcodeFromNetname(name));row['net']=name
    else:width=True
    with pytest.raises(ValueError):sizing.plan(board,'synthetic.kicad_pcb',row,board_hint='synthetic',width_nm=width)

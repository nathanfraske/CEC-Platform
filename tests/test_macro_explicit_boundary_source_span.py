"""Larger finite Source work never supplies ordinary/current/Ground rights."""
import copy,time
from pathlib import Path
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_field_coupling as field
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,quarter=0,back=False,renamed=False,length=8.28,width=.22):
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    name='opaque_signal_new'if renamed else 'signal'
    board.Add(pcbnew.NETINFO_ITEM(board,name))
    edge=track(board,name,(10,10),(10+length,10),width=width)
    if back:edge.SetLayer(pcbnew.B_Cu)
    if quarter:edge.Rotate(pcbnew.VECTOR2I_MM(10,10),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,path)
    transport=dict(changes=[dict(uuid=force._uid(edge),net=name,
        source_nm=[list(edge.GetStart()),list(edge.GetEnd())])])
    proposal=dict(retired_track_uuids=[],board_hint='synthetic')
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:{name})
    return board,path,edge,transport,proposal


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('renamed',[False,True])
def test_explicit_boundary_work_keeps_default_and_native_source_identity(tmp_path,monkeypatch,quarter,back,renamed):
    board,path,edge,transport,proposal=fixture(tmp_path,monkeypatch,quarter=quarter,back=back,renamed=renamed)
    raw=path.read_bytes();binding=row._source_binding(board);original=copy.deepcopy(transport)
    with pytest.raises(ValueError,match='changed_macro_boundary_not_a_bounded_small_source_edge'):
        compiler._extra_ownership(board,path,transport,proposal,time.monotonic()+10.)
    result=compiler._extra_ownership(board,path,transport,proposal,time.monotonic()+10.,max_source_track_mm=9.)
    assert len(result)==1 and result[0]['authority']['kind']=='positive_source_ordinary'
    assert result[0]['change']==transport['changes'][0]
    assert row._source_binding(board)==binding and path.read_bytes()==raw and transport==original


@pytest.mark.parametrize('limit',[0,-1,True,False,32.001,float('nan'),float('inf'),'9'])
def test_boundary_work_must_be_finite_and_explicit(limit):
    with pytest.raises(ValueError,match='bounded_additional_macro_boundary_source_span'):
        compiler._extra_ownership(None,None,{}, {},time.monotonic()+10.,max_source_track_mm=limit)


@pytest.mark.parametrize('fault',['length','width','mask','points','group','unrated'])
def test_larger_work_cannot_grant_other_source_rights(tmp_path,monkeypatch,fault):
    board,path,edge,transport,proposal=fixture(tmp_path,monkeypatch,length=9.01 if fault=='length'else 8.28)
    if fault=='width':edge.SetWidth(500000)
    elif fault=='mask':edge.SetHasSolderMask(True)
    elif fault=='points':transport['changes'][0]['source_nm'][0][0]+=1
    elif fault=='group':
        group=pcbnew.PCB_GROUP(board);board.Add(group);group.AddItem(edge)
    elif fault=='unrated':monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:set())
    before=row._source_binding(board)
    if fault=='group':
        assert compiler._extra_ownership(board,path,transport,proposal,time.monotonic()+10.,max_source_track_mm=9.)==[]
    else:
        with pytest.raises(ValueError):
            compiler._extra_ownership(board,path,transport,proposal,time.monotonic()+10.,max_source_track_mm=9.)
    assert before==row._source_binding(board)


def test_rated_boundary_rederives_same_source_width_and_current_with_explicit_span(tmp_path,monkeypatch):
    board,path,edge,transport,proposal=fixture(tmp_path,monkeypatch,width=.5)
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:set())
    contract=dict(net=edge.GetNetname(),routing_layers=['F.Cu'],required_by_layer_mm={'F.Cu':.5},
        current_authority=dict(amps=.231,margin_included=True,geometry_margin=1.,source='component_power_budget'))
    monkeypatch.setattr(compiler.full,'_model',lambda *a,**k:('synthetic_explicit',None,contract))
    result=compiler._extra_ownership(board,path,transport,proposal,time.monotonic()+10.,max_source_track_mm=9.)
    proof=result[0]['authority']['source_plan']
    assert proof['contract']==contract and proof['width_nm']==500000
    assert proof['max_source_track_mm']==9. and not proof['source_current_reduced']
    assert proof['retired_track_uuids']==[force._uid(edge)]


def test_positive_work_cannot_turn_ground_into_an_ordinary_signal(tmp_path,monkeypatch):
    board,path,edge,transport,proposal=fixture(tmp_path,monkeypatch,width=.5)
    net=pcbnew.NETINFO_ITEM(board,'GND');board.Add(net);edge.SetNet(net)
    transport['changes'][0]['net']='GND'
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',lambda *a,**k:{'GND'})
    with pytest.raises(ValueError):
        compiler._extra_ownership(board,path,transport,proposal,time.monotonic()+10.,max_source_track_mm=9.)


def test_existing_explicit_macro_option_is_forwarded_and_reconstructible(tmp_path,monkeypatch):
    from test_complete_cell_connections import native_source
    path,parent,private,proposal=native_source(tmp_path,monkeypatch)
    original=compiler._extra_ownership;observed=[]
    def observe(*args,**kwargs):
        observed.append(kwargs.get('max_source_track_mm',8.));return original(*args,**kwargs)
    monkeypatch.setattr(compiler,'_extra_ownership',observe)
    _,packet=compiler.compile(path,proposal['poses'],board_hint='opaque',max_obstacle_track_mm=9.)
    assert observed==[9.]
    assert compiler.packet_options(packet)['max_obstacle_track_mm']==9.
    assert not packet['saved_candidate_authorized']and packet['all_extra_omissions_positively_source_typed']

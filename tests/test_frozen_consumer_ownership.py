import copy
import hashlib
import json
import pcbnew
import pytest
import cec_power_guard_geometry as geometry
import cec_full_pipeline as pipeline
import cec_decoupler_cell as cells


def state():
    return dict(placement_scope='complete',frozen_nets=['POWER'],corridors=[],
        exclude_pins=['TERM_A-1','TERM_B-1'],
        reserve_report={'POWER':dict(reserved=True,exclude_pins=['TERM_A-1','TERM_B-1'])},
        pours=[dict(net='POWER',layer='In3.Cu',polygon=[[0,0],[3,0],[3,3],[0,3]])])


def test_consumer_does_not_become_a_terminal_merely_by_sharing_a_net():
    s=state();nets={'TERM_A-1':{'POWER'},'TERM_B-1':{'POWER'},'LOAD-1':{'POWER'}}
    assert geometry.frozen_terminal_tokens(s,nets)=={'TERM_A-1','TERM_B-1'}


@pytest.mark.parametrize('failure',['scope','missing','extra','net','duplicate_net','unreserved','one_terminal'])
def test_missing_or_disagreeing_ownership_keeps_whole_net_frozen(failure):
    s=state();nets={'TERM_A-1':{'POWER'},'TERM_B-1':{'POWER'}}
    if failure=='scope':s['placement_scope']='anchors'
    if failure=='missing':s.pop('reserve_report')
    if failure=='extra':s['exclude_pins'].append('unknown')
    if failure=='net':nets['TERM_B-1']={'GND'}
    if failure=='duplicate_net':nets['TERM_B-1']={'POWER','GND'}
    if failure=='unreserved':s['reserve_report']['POWER']['reserved']=False
    if failure=='one_terminal':s['reserve_report']['POWER']['exclude_pins']=['TERM_A-1']
    assert geometry.frozen_terminal_tokens(s,nets) is None


def native_board(tmp_path):
    b=pcbnew.BOARD();b.SetCopperLayerCount(6)
    net=pcbnew.NETINFO_ITEM(b,'POWER');b.Add(net)
    positions={'TERM_A':[1.,1.,0.],'TERM_B':[2.,2.,0.],'LOAD':[10.,10.,0.]}
    for ref,(x,y,r) in positions.items():
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetPosition(pcbnew.VECTOR2I_MM(x,y));b.Add(fp)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetPosition(fp.GetPosition());pad.SetNet(net)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers);fp.Add(pad)
    path=tmp_path/'board.kicad_pcb';pcbnew.SaveBoard(str(path),b,True)
    s=state();s['placements']=copy.deepcopy(positions);s['placements']['LOAD'][0]=9.
    path.with_suffix('.pourfirst-state.json').write_text(json.dumps(s))
    return path,s


@pytest.mark.parametrize('mutation,accepted',[(None,True),('terminal',False),('original_contact',False),('separated_layer',True),
    ('new_contact',False),('missing_proof',False)])
def test_loaded_native_sync_preserves_terminals_and_both_body_clearances(tmp_path,mutation,accepted):
    path,s=native_board(tmp_path)
    if mutation=='terminal':s['placements']['TERM_A']=[.5,1.,0.]
    if mutation in ('original_contact','separated_layer'):s['placements']['LOAD']=[2.,2.,0.]
    if mutation=='original_contact':s['pours'][0]['layer']='F.Cu'
    if mutation=='new_contact':
        s['pours'][0]['polygon']=[[9,9],[11,9],[11,11],[9,11]]
        s['pours'][0]['layer']='F.Cu'
    if mutation=='missing_proof':s.pop('reserve_report')
    sidecar=path.with_suffix('.pourfirst-state.json');sidecar.write_text(json.dumps(s))
    original=sidecar.read_bytes();digest=hashlib.sha256(path.read_bytes()).hexdigest()
    result=pipeline._sync_safe_postfreeze_placement_delta(path)
    assert result['ok']==accepted,result
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    if accepted:
        assert result['deferred_consumers'][0]['ref']=='LOAD'
        new=json.loads(sidecar.read_text())
        assert new['placements']['LOAD']==[10.,10.,0.]
        assert new['pours']==s['pours'] and new['exclude_pins']==s['exclude_pins']
    else:assert sidecar.read_bytes()==original


def test_native_return_refusal_keeps_bounded_measured_seats(tmp_path,monkeypatch):
    path,_=native_board(tmp_path);board=pcbnew.LoadBoard(str(path))
    pad=board.FindFootprintByReference('LOAD').FindPadByNumber('1')
    def refuse(*args,**kwargs):
        report=kwargs.get('report')
        if report is not None:
            report.update(ok=False,at_mm=[args[1].x/1e6,args[1].y/1e6],diameter_mm=args[2]/1e6,
                clearance_mm=.2,blockers=[dict(kind='pour_first_reservation',layer='In3.Cu',net='OTHER',rect_mm=[9,9,11,11])])
        return False
    monkeypatch.setattr(cells.cec_fr,'_via_spot_clear',refuse)
    monkeypatch.setattr(cells.cec_fr,'_edge_leg_clear',lambda *a,**k:True)
    detail={}
    _,error=cells._add_ground_return(board,pad,board_path=str(path),reach_mm=1.5,lock=True,diagnostics=detail)
    assert error and detail['search_exhausted']
    assert 0<len(detail['dogbone_candidates'])<=16
    assert detail['dogbone_candidates_truncated']>0
    assert all(r['copper_admission']['blockers'] for r in detail['dogbone_candidates'])
    assert not list(board.GetTracks())


def test_through_pad_and_frozen_via_cannot_hide_on_other_layers(tmp_path):
    path,s=native_board(tmp_path);board=pcbnew.LoadBoard(str(path))
    fp=board.FindFootprintByReference('LOAD');pad=fp.FindPadByNumber('1')
    fp.SetPosition(pcbnew.VECTOR2I_MM(2,2))
    assert not geometry.frozen_pad_contacts(board,fp,s,.3)
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    assert geometry.frozen_pad_contacts(board,fp,s,.3)
    fp.SetPosition(pcbnew.VECTOR2I_MM(10,10));s['vias']=[dict(x_mm=10,y_mm=10,diameter_mm=.8,net='POWER')]
    assert geometry.frozen_pad_contacts(board,fp,s,.3)[0]['kind']=='frozen_through_via'

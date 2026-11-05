"""Search must preserve each electrical endpoint, not just geometry totals."""
import copy
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_placement_relation_guard as guard
import cec_placement_dependencies as dependencies
import cec_synth_pipeline as synth


def fixture(tmp_path, *, back=False, offset=0.):
    board=pcbnew.CreateEmptyBoard();nets={}
    for name in ('alpha','beta','/cell/DETAMP'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    descriptions=[('source','R',offset+2.,5.,[('1','alpha',-1.),('2','beta',1.)]),
                  ('receiver','INA181',offset+8.,5.,[('1','alpha',-1.),('2','beta',1.)]),
                  ('amplifier','INA181',offset+15.,5.,[('OUT','/cell/DETAMP',0.)]),
                  ('comparator','TLV7011',offset+19.,5.,[('IN','/cell/DETAMP',0.)])]
    for ref,value,x,y,pads in descriptions:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);fp.SetValue(value)
        board.Add(fp);fp.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        for pin,net,dy in pads:
            pad=pcbnew.PAD(fp);pad.SetNumber(pin);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
            pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetPosition(pcbnew.VECTOR2I_MM(x,y+dy))
            pad.SetNet(nets[net]);fp.Add(pad)
        if back:fp.Flip(fp.GetPosition(),False)
    path=tmp_path/'fixture.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path))
    craft=dict(detection_cell=synth._oracle_comparator_adjacency(str(path)),
        critical_terminal_order=dict(details=[dict(anchor_ref='source',ref='receiver',
            nets=['alpha','beta'],follower_pad_contract={'alpha':'1','beta':'2'})]))
    return path,board,craft,guard.build(board,craft)


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('offset',[0.,43.])
def test_native_binding_uses_normal_range_slack_and_rejects_new_range_debt(tmp_path,back,offset):
    path,board,craft,contract=fixture(tmp_path,back=back,offset=offset)
    before=path.read_bytes();positions=copy.deepcopy(contract['positions'])
    assert guard.check(contract,positions)['ok']
    positions['receiver']=(offset+10.,5.,positions['receiver'][2])
    assert guard.check(contract,positions)['ok'] # 8 mm, still under constructor's 9 mm.
    positions['receiver']=(offset+12.,5.,positions['receiver'][2])
    result=guard.check(contract,positions)
    assert not result['ok'] and {r['kind'] for r in result['errors']}=={'terminal_range'}
    assert path.read_bytes()==before


def test_primary_detector_move_cannot_spend_another_cells_improvement(tmp_path):
    _,_,_,contract=fixture(tmp_path)
    positions=dict(contract['positions']);positions['comparator']=(24.,5.,0.)
    result=guard.check(contract,positions)
    assert not result['ok'] and result['errors'][0]['kind']=='detector_locality'
    context=dict(ok=True,relation_guard=contract)
    moves=[dict(ref='comparator',position=(24.,5.,0.)),dict(ref='comparator',position=(21.,5.,0.))]
    kept,report=dependencies.filter_moves(context,contract['positions'],moves)
    assert kept==moves[1:] and report['refused']==1


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0.,90.,180.,270.])
def test_native_pad_projection_matches_materialized_rotation(tmp_path,back,angle):
    _,board,_,contract=fixture(tmp_path,back=back)
    positions=dict(contract['positions']);positions['receiver']=(9.,7.,angle)
    fp=board.FindFootprintByReference('receiver');fp.SetPosition(pcbnew.VECTOR2I_MM(9,7))
    fp.SetOrientationDegrees(angle)
    for pin,net in (('1','alpha'),('2','beta')):
        projected=guard._point(positions,contract['templates'],dict(ref='receiver',pad=pin,net=net))
        pad=next(p for p in fp.Pads() if p.GetNumber()==pin)
        assert projected==pytest.approx((pad.GetPosition().x/1e6,pad.GetPosition().y/1e6),abs=1e-6)


def test_rotation_cannot_introduce_crossed_terminals(tmp_path):
    _,_,_,contract=fixture(tmp_path)
    positions=dict(contract['positions']);positions['receiver']=(8.,5.,180.)
    assert 'terminal_crossing' in {r['kind'] for r in guard.check(contract,positions)['errors']}


def test_each_terminal_checked_even_when_total_length_improves(tmp_path,monkeypatch):
    _,_,_,contract=fixture(tmp_path)
    baseline=contract['terminal_baseline']['details'][0]
    baseline['terminal_distances_mm']={'alpha':8.,'beta':8.};baseline['direct_length_mm']=16.
    row=dict(baseline,terminal_distances_mm={'alpha':3.,'beta':10.},direct_length_mm=13.)
    monkeypatch.setattr(synth,'_parallel_pour_critical_terminal_geometry',lambda *a:dict(details=[row]))
    result=guard.check(contract,contract['positions'])
    assert not result['ok'] and result['errors'][0]['net']=='beta'


@pytest.mark.parametrize('fault',['missing_ref','wrong_net','nan_pose','missing_pad','missing_relation'])
def test_missing_or_invalid_native_binding_fails_closed(tmp_path,fault):
    _,_,_,contract=fixture(tmp_path);positions=dict(contract['positions'])
    if fault=='missing_ref':positions.pop('receiver')
    if fault=='wrong_net':contract['templates']['receiver'][0]['net']='other'
    if fault=='nan_pose':positions['receiver']=(float('nan'),5.,0.)
    if fault=='missing_pad':contract['templates']['receiver']=()
    if fault=='missing_relation':contract['specs']=()
    assert not guard.check(contract,positions)['ok']


def test_preexisting_distance_debt_can_improve_but_not_grow(tmp_path):
    _,board,craft,_=fixture(tmp_path)
    board.FindFootprintByReference('receiver').SetPosition(pcbnew.VECTOR2I_MM(14,5))
    contract=guard.build(board,craft);positions=dict(contract['positions'])
    assert guard.check(contract,positions)['ok']
    positions['receiver']=(13.,5.,0.)
    assert guard.check(contract,positions)['ok']
    positions['receiver']=(15.,5.,0.)
    assert not guard.check(contract,positions)['ok']


def test_unavailable_context_cannot_pass_primary_screen():
    kept,report=dependencies.filter_moves(dict(ok=False,error='bad binding'),
        {'part':(0,0,0)},[dict(ref='part',position=(1,0,0))])
    assert kept==[] and report['refused']==1


def test_macro_rejects_bad_primary_before_any_collateral(tmp_path):
    from types import SimpleNamespace
    _,_,_,contract=fixture(tmp_path)
    candidate=SimpleNamespace(P=contract['positions'],W=40,H=20,back_refs=())
    trace={}
    result=synth._placement_bounded_macro_legalizations(candidate,
        {'comparator':(24.,5.,0.)},set(),{ref:object() for ref in candidate.P},{},{},lambda ref:True,
        bbox_fn=lambda ref,p:(p[0]-.2,p[0]+.2,p[1]-.2,p[1]+.2),exact_bbox_overlap=True,
        dependency_context=dict(ok=True,relation_guard=contract),trace=trace)
    assert not result and trace['reason']=='primary_electrical_regression'


def test_beam_chooses_an_electrically_safe_collateral_direction(tmp_path):
    from types import SimpleNamespace
    _,board,craft,_=fixture(tmp_path)
    board.FindFootprintByReference('receiver').SetPosition(pcbnew.VECTOR2I_MM(11,5))
    contract=guard.build(board,craft)
    candidate=SimpleNamespace(P=dict(contract['positions'],primary=(1.,1.,0.)),
                              W=40,H=20,back_refs=())
    trace={};context=dict(ok=True,relation_guard=contract)
    results=synth._placement_bounded_macro_legalizations(candidate,{'primary':(11.,5.,0.)},
        set(),{ref:object() for ref in candidate.P},{},{},lambda ref:ref=='receiver',
        bbox_fn=lambda ref,p:(p[0]-.2,p[0]+.2,p[1]-.2,p[1]+.2),exact_bbox_overlap=True,
        dependency_context=context,max_steps=1,trace=trace)
    assert results and trace['steps'][0]['electrical_rejected']>=2
    assert all(guard.check(contract,dict(candidate.P,**poses))['ok'] for poses,_,_ in results)

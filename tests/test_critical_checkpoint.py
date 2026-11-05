from copy import deepcopy
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
import cec_critical_checkpoint as checkpoint


def proof():
    return dict(new_pairs=[{'p':'alpha','n':'beta'}], zones_refilled=True,
                parent_copper={'ok':True}, placement_unchanged=True,
                source_unchanged=True, complete_owned_pairs=True,
                baseline_refill={'source_unchanged':True},
                pair_physics={'ok':True,'applicable':True},
                score_admission={'accepted':True})


@pytest.mark.parametrize('field',list(proof()))
def test_every_partial_gate_is_required(field):
    row=proof()
    assert checkpoint.partial_admitted(row)
    row.pop(field)
    assert not checkpoint.partial_admitted(row)


def test_no_empty_or_missing_physics_can_be_a_checkpoint():
    for value in ({'ok':True}, {'applicable':True}, {'ok':False,'applicable':True}):
        assert not checkpoint.partial_admitted(dict(proof(),pair_physics=value))
    assert not checkpoint.partial_admitted(dict(proof(),new_pairs=[]))


def test_refused_sibling_does_not_replace_last_admitted_parent(tmp_path):
    import cec_fr
    import cec_precision_route as precision
    import cec_route_preflight as preflight
    source=tmp_path/'source.kicad_pcb';source.write_text('unchanged')
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    pairs=[dict(name=str(i),p='p'+str(i),n='n'+str(i)) for i in range(3)]
    calls=[]
    def solve(parent,target,**kwargs):
        calls.append((parent,target,kwargs))
        Path(target).write_text('candidate')
        return {'zones_refilled':True}
    with patch.object(cec_fr,'owned_locked_nets',return_value=set()), \
         patch.object(preflight,'compile_route_reservations',return_value={}), \
         patch.object(preflight,'priority_pair_avoid',return_value=()), \
         patch.object(precision,'precision_route',side_effect=solve), \
         patch.object(checkpoint,'validate',side_effect=[{'ok':True},{'ok':False},{'ok':False}]):
        result=checkpoint.construct(source,tmp_path/'result',pairs)
    selected=calls[0][1]
    assert [row[0] for row in calls]==[str(source),selected,selected]
    assert result['selected']==selected and result['ok']
    assert not result['residual_allowed'] and not result['release_accepted']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    assert all(not call[2]['do_kelvin'] for call in calls)


def test_recovery_copy_requires_source_engine_and_saved_candidate_identity(tmp_path):
    import cec_full_pipeline as pipeline
    import cec_operation_budget
    from types import SimpleNamespace
    source=tmp_path/'board.kicad_pcb';source.write_text('parent')
    child=tmp_path/'child.kicad_pcb';child.write_text('child')
    directory=tmp_path/'recovery';directory.mkdir()
    report=dict(ok=False,source_inputs_unchanged=True,engine_unchanged=True,
                source_unchanged=True,partial_selected=str(child),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                partial_proof=dict(ok=True,board_sha256=hashlib.sha256(child.read_bytes()).hexdigest(),
                                   artifact_signature=pipeline._files_signature([child])))
    cfg=SimpleNamespace(board='arbitrary',params={})
    for change,expected in [({},True),({'engine_unchanged':False},False),
                            ({'source_unchanged':False},False),
                            ({'source_sha256':'stale'},False),
                            ({'partial_proof':{'ok':True,'board_sha256':'stale'}},False)]:
        pipeline.atomic_json(directory/'recovery.json',dict(deepcopy(report),**change))
        with patch.object(pipeline.tempfile,'mkdtemp',return_value=str(directory)), \
             patch.object(cec_operation_budget,'run',return_value={'exit_code':2}), \
             patch.object(pipeline,'_copy_sidecars') as copy:
            result=pipeline._recover_placement_priority_routes(cfg,source)
        assert result['changed']==expected
        assert copy.called==expected


@pytest.mark.parametrize('ground_ok',[True,False])
def test_construct_cannot_skip_declared_reference_stage(tmp_path,ground_ok):
    import cec_fr
    import cec_precision_route as precision
    import cec_route_preflight as preflight
    source=tmp_path/'source.kicad_pcb';source.write_text('parent')
    pair=dict(name='pair',p='positive',n='negative')
    with patch.object(cec_fr,'owned_locked_nets',return_value=set()), \
         patch.object(preflight,'compile_route_reservations',return_value={}), \
         patch.object(preflight,'priority_pair_avoid',return_value=()), \
         patch.object(precision,'precision_route',return_value={'pairs_ok':True,'zones_refilled':True}), \
         patch.object(checkpoint,'complete_reference_planes',return_value={'ok':ground_ok}) as ground, \
         patch.object(checkpoint,'validate',return_value={'ok':True}) as validate:
        result=checkpoint.construct(source,tmp_path/'run',[pair])
    assert ground.call_count==1
    assert validate.called==ground_ok
    assert result['ok']==ground_ok
    if ground_ok:
        assert result['selected'].endswith('/referenced.kicad_pcb')
        assert validate.call_args.args[1].name=='referenced.kicad_pcb'


def test_disconnected_locked_pad_stubs_are_not_a_complete_pair(tmp_path):
    import pcbnew
    import cec_score
    import cec_constraints
    board=pcbnew.BOARD();pads=[]
    for index,name in enumerate(('alpha','beta')):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net)
        for column in (1,5):
            fp=pcbnew.FOOTPRINT(board);fp.SetReference('%s%d'%(name,column));board.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNet(net);pad.SetNumber('1')
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetPosition(pcbnew.VECTOR2I_MM(column,index+2))
            layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);pad.SetLayerSet(layers)
            fp.Add(pad);pads.append(pad)
    parent=tmp_path/'parent.kicad_pcb';child=tmp_path/'child.kicad_pcb'
    pcbnew.SaveBoard(str(parent),board)
    for pad in pads:
        track=pcbnew.PCB_TRACK(board);track.SetNet(pad.GetNet());track.SetLayer(pcbnew.F_Cu)
        track.SetWidth(pcbnew.FromMM(.2));track.SetStart(pad.GetPosition())
        point=pad.GetPosition();point.x+=pcbnew.FromMM(.2);track.SetEnd(point)
        track.SetLocked(True);board.Add(track)
    pcbnew.SaveBoard(str(child),board)
    pair=dict(name='whatever',p='alpha',n='beta')
    metrics=dict(drc=0,unconnected=2,kelvin_ok=True,diffpair_ok=False)
    from types import SimpleNamespace
    with patch.object(cec_score,'score',return_value=SimpleNamespace(**metrics)), \
         patch.object(cec_constraints,'high_speed_pair_summary',return_value={'pairs':[dict(pair,violations=[])]}):
        result=checkpoint.validate(parent,child,[pair],zones_refilled=True)
    # The shared ownership gate now refuses before spending the independent
    # pair-physics/refill budget, not only at the checkpoint's second check.
    assert not result['new_pairs'] and not result['ok']
    assert result['reason'] == 'no_new_complete_owned_pair'

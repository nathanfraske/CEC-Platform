"""Resuming an admitted power prefix must not stack copies of its zones."""
import json
import pcbnew
import pytest
import cec_fr
import cec_synth_pipeline as synth


@pytest.mark.parametrize('net,offset,layer', [('supply-alpha',0,'B.Cu'),('supply-beta',40,'F.Cu')])
@pytest.mark.parametrize('admitted',[True,False])
def test_frozen_replay_replaces_authority_and_keeps_native_gate(tmp_path,monkeypatch,net,offset,layer,admitted):
    import cec_constraints,cec_slab_pour
    board=pcbnew.BOARD()
    for name in (net,'unmanaged'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    def declaration(name,x):
        return dict(net=name,layer=layer,name='pour:'+name,
                    polygon=[(x,0),(x+4,0),(x+4,4),(x,4)])
    pour=declaration(net,offset)
    cec_fr.add_power_pours(board,[pour,declaration('unmanaged',offset+10)])
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),board)
    state=dict(placement_scope='complete',frozen_nets=[net],pours=[pour],vias=[],
               corridors=[dict(net=net,layer=layer,polygon=pour['polygon'])],placements={})
    monkeypatch.setenv('CEC_POURFIRST_STATE',str(tmp_path/'authority.json'))
    monkeypatch.setattr(cec_fr,'_pourfirst_state',lambda:state)
    monkeypatch.setattr(cec_constraints,'foreign_on_pour_summary',lambda p:dict(status='ok',n_tracks=0,n_vias=0))
    monkeypatch.setattr(synth,'_synthesize_priority_power_local_pin_access',lambda *a:{})
    monkeypatch.setattr(cec_fr,'reseat_overunder_vias',lambda *a:([],dict(ok=True,changed=False)))
    monkeypatch.setattr(cec_fr,'add_overunder_vias',lambda *a,**kw:[])
    monkeypatch.setattr(cec_slab_pour,'cleanup_floating_zones',lambda *a:0)
    observations=[]
    def gate(path,nets,baseline):
        current=pcbnew.LoadBoard(str(path))
        rows=[(z.GetNetname(),z.GetAssignedPriority()) for z in current.Zones()]
        observations.append(sorted(rows))
        return dict(passed=admitted,reason=None if admitted else 'synthetic_native_refusal',open_after=[],exact_after={})
    monkeypatch.setattr(synth,'_admit_priority_power_candidate_isolated',gate)
    original=source.read_bytes()
    for index in range(2):
        output=tmp_path/f'output-{index}.kicad_pcb';report=tmp_path/f'state-{index}.json'
        if admitted:
            result=synth._compile_post_priority_power_state(str(source),[pour],str(report),str(output))
            assert result['power_pour_replacement']['removed']==1
            assert result['power_pour_replacement']['added']==1
        else:
            with pytest.raises(RuntimeError,match='frozen power exact admission refused'):
                synth._compile_post_priority_power_state(str(source),[pour],str(report),str(output))
            assert json.loads(report.read_text())['exact_admission']['passed'] is False
        assert observations[-1]==sorted([(net,2),('unmanaged',2)])
        if index==0:assert source.read_bytes()==original
        source=output
    assert observations[0]==observations[1]

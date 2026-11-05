"""Late route repairs must not reintroduce import quantization artifacts."""
from unittest import mock
import pytest
import pcbnew
import cec_fr
import cec_certificate_repair as repair
import cec_constraints
import cec_synth_pipeline as synth
import cec_search_policy
import cec_collinear_copper


def test_native_sanitizer_keeps_locked_prefix_and_real_short_necks():
    board=pcbnew.BOARD()
    def track(length,locked=False):
        item=pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I(1000000,1000000))
        item.SetEnd(pcbnew.VECTOR2I(1000000+length,1000000))
        item.SetWidth(270000);item.SetLocked(locked);board.Add(item)
        return item.m_Uuid.AsString()
    removed=track(1)
    frozen=track(1,True)
    real=track(10001)
    assert cec_fr.prune_degenerate_tracks(board,preserve_locked=True)==1
    assert {item.m_Uuid.AsString() for item in board.GetTracks()}=={frozen,real}
    board.BuildConnectivity()
    assert cec_fr.prune_degenerate_tracks(board,preserve_locked=True)==0


def test_repair_save_sanitizes_before_groups_and_serialization():
    board=mock.Mock();board.Zones.return_value=[];board.GetTracks.return_value=[]
    sequence=[]
    with mock.patch.object(cec_fr,'prune_degenerate_tracks',side_effect=lambda *a,**k:sequence.append('prune') or 1) as prune, \
        mock.patch.object(cec_collinear_copper,'normalize',side_effect=lambda *a,**k:sequence.append('normalize') or {'trimmed':1}) as normalize, \
        mock.patch.object(cec_fr,'_project_netclass_resolver',return_value=None), \
        mock.patch.object(cec_fr,'reconcile_endpoint_neckdown_groups',side_effect=lambda *a,**k:sequence.append('groups') or {}), \
        mock.patch.object(cec_fr,'group_local_pofv_signal_vias',return_value={}), \
        mock.patch.object(pcbnew,'SaveBoard',side_effect=lambda *a:sequence.append('save')), \
        mock.patch.object(cec_fr,'ensure_endpoint_neckdown_rule',return_value={}), \
        mock.patch.object(cec_fr,'ensure_local_pofv_signal_via_rule',return_value={}):
        report=repair._save_with_reconciled_endpoint_neckdowns('scratch',board,{})
    assert sequence==['prune','normalize','groups','save']
    prune.assert_called_once_with(board,preserve_locked=True)
    normalize.assert_called_once_with(board)
    assert report['degenerate_tracks_removed']==1
    assert report['collinear_copper_normalization']['trimmed']==1


@pytest.mark.parametrize('status',[True,False,None,'error'])
def test_independent_width_gate_is_fail_closed(status):
    checker=mock.Mock(side_effect=ValueError('invalid geometry')) if status=='error' else mock.Mock(return_value=(status,'measured',[]))
    with mock.patch.object(pcbnew,'LoadBoard',return_value=mock.Mock()), \
        mock.patch.dict(cec_constraints.CHECKERS,{'netclass-geometry-conformance':checker}):
        result=synth._oracle_netclass_geometry('board')
    assert result['ok'] is (status is True)
    assert cec_search_policy.incumbent_gate_regressions(
        {'gate_terms':{'netclass_geometry_ok':result['ok']}},
        {'gate_terms':{'netclass_geometry_ok':True}})==([] if status is True else ['netclass_geometry_ok'])


def test_route_oracle_schema_requires_independent_width_gate():
    terms={name:True for name in synth._ROUTE_ORACLE_GATE_TERMS}
    assert 'netclass_geometry_ok' in terms
    assert synth._route_oracle_accepts(terms)
    terms['netclass_geometry_ok']=False
    assert not synth._route_oracle_accepts(terms)


def test_wave_publisher_rechecks_width_after_mutating_the_board(tmp_path):
    from types import SimpleNamespace
    import cec_fresh_wave as wave
    path=tmp_path/'published.kicad_pcb';path.write_text('published bytes')
    best={'gate':True,'kelvin_ok':True,'diffpair_ok':True,'drc':0,'unconnected':0,
          'gate_terms':{name:True for name in synth._ROUTE_ORACLE_GATE_TERMS}}
    metrics=SimpleNamespace(gates_pass=True,kelvin_ok=True,diffpair_ok=True,drc=0,
        unconnected=0,drc_types={},vias=0,tracks=1,length=1.0,detail={})
    with mock.patch.object(wave.cec_score.Rules,'from_board',return_value=object()), \
        mock.patch.object(wave.cec_score,'score',return_value=metrics), \
        mock.patch.object(synth,'_classify_unconnected',return_value=([],[])), \
        mock.patch.object(synth,'_oracle_netclass_geometry',return_value={'ok':False}) as checker:
        result=wave._rescore_published(best,str(path))
    checker.assert_called_once_with(str(path))
    assert result['gate'] is False
    assert result['gate_terms']['netclass_geometry_ok'] is False

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import cec_full_pipeline as pipeline
import cec_synth_pipeline as synth
import cec_route_evidence
import cec_route_preflight as preflight


@pytest.mark.parametrize('multiresolution',[True,False])
def test_authored_priority_measurement_does_not_rebuild_or_strip_copper(tmp_path,multiresolution):
    source=tmp_path/'board.kicad_pcb';source.write_text('exact saved artifact')
    cfg=SimpleNamespace(params={'placement_route_preflight_multiresolution':multiresolution})
    result={'critical_pair_refused_count':2}
    with patch.object(cec_route_evidence,'baseline_context',return_value={'stable':True}), \
         patch.object(cec_route_evidence,'seal',side_effect=lambda evidence,context:evidence), \
         patch.object(synth,'config_with_board_route_authority',return_value=(cfg,{'ok':True,'bound':True})), \
         patch.object(pipeline,'_requires_frozen_route_authority',return_value=True), \
         patch.object(synth,'_oracle_env',return_value=nullcontext()), \
         patch.object(synth,'_placement_route_preflight_env',return_value=nullcontext()), \
         patch.object(synth,'placement_candidate_from_board') as candidate, \
         patch.object(synth,'rerank_route_preflight') as rerank, \
         patch.object(preflight,'analyze',return_value={}) as simple, \
         patch.object(preflight,'analyze_multiresolution',return_value={}) as multi, \
         patch.object(preflight,'compact_placement_evidence',return_value=result):
        measured=pipeline._measure_placement_priority_routes_in_process(cfg,source,allow_authored_prefix=True)
    candidate.assert_not_called();rerank.assert_not_called()
    assert (multi if multiresolution else simple).call_args.args==(str(source),)
    assert measured['measurement_domain']=='exact_saved_artifact'
    assert source.read_text()=='exact saved artifact'

"""Publish hygiene must grade the actual saved copper, not earlier true terms."""
from types import SimpleNamespace
import copy
from unittest import mock
import pytest
import cec_fresh_wave as wave
import cec_synth_pipeline as synth


@pytest.mark.parametrize('cause',[None,'reverse_jog','power_blob','missing','truthy'])
def test_fresh_saved_craft_overwrites_prepublication_release_terms(tmp_path,cause):
    path=tmp_path/'published.kicad_pcb';path.write_bytes(b'literal published identity')
    before=path.read_bytes()
    craft={'craft_ok':True,'power_contour_review_ok':True,'issue_count':0,
        'power_contours':{'finding_count':0}}
    if cause=='reverse_jog':craft.update(craft_ok=False,issue_count=1)
    elif cause=='power_blob':craft.update(power_contour_review_ok=False,power_contours={'finding_count':1})
    elif cause=='missing':craft={}
    elif cause=='truthy':craft['craft_ok']=1
    metrics=SimpleNamespace(gates_pass=True,kelvin_ok=True,diffpair_ok=True,drc=0,
        unconnected=0,drc_types={},vias=0,tracks=3,length=2.,detail={'route_quality':craft})
    best={'gate':True,'gate_terms':{name:True for name in synth._ROUTE_ORACLE_GATE_TERMS},
        'route_geometry_ok':True,'power_contour_review_ok':True,'reasons':[]}
    with mock.patch.object(wave.cec_score.Rules,'from_board',return_value=object()), \
        mock.patch.object(wave.cec_score,'score',return_value=metrics), \
        mock.patch.object(synth,'_classify_unconnected',return_value=([],[])), \
        mock.patch.object(synth,'_oracle_netclass_geometry',return_value={'ok':True}):
        result=wave._rescore_published(best,str(path))
    assert result['gate'] is (cause is None)
    assert result['gate_terms']['route_geometry_ok'] is (cause in(None,'power_blob'))
    assert result['gate_terms']['power_contour_review_ok'] is (cause not in('power_blob','missing'))
    assert path.read_bytes()==before

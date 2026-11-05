"""Physical witness contributors have canonical order, not weaker comparison."""
import copy,json
import pcbnew
import pytest
import cec_kelvin_copper_cut as cut
from test_kelvin_copper_cut import native_board_fixture,audit,track,zone


@pytest.mark.parametrize('angle',[0,37,90,180])
@pytest.mark.parametrize('filled',[False,True])
def test_native_container_permutation_preserves_exact_witness_material(tmp_path,monkeypatch,angle,filled):
    values=native_board_fixture(tmp_path/'board.kicad_pcb',angle=angle)
    b=values[0]
    if filled:zone(b,[(88,71,94,79)])
    before=audit(values);items=list(b.GetTracks());zones=list(b.Zones())
    monkeypatch.setattr(b,'GetTracks',lambda:list(reversed(items)))
    monkeypatch.setattr(b,'Zones',lambda:list(reversed(zones)))
    after=audit(values)
    assert before['complete']and after['complete']
    for key in('baseline_geometry','upper','lower'):
        assert before.get(key)==after.get(key),(key,before,after)
        for witness in before.get(key,{}).get('witnesses',[]):
            for node in witness['path']:
                expected=sorted(node['contributors'],key=lambda r:json.dumps(r,sort_keys=True,separators=(',',':')))
                assert node['contributors']==expected
    assert before['ok']==after['ok']and before['reason']==after['reason']


def test_redundant_material_removal_is_still_a_witness_difference(tmp_path):
    values=native_board_fixture(tmp_path/'board.kicad_pcb');b=values[0]
    duplicate=track(b,(90,72),(90,73));uid=duplicate.m_Uuid.AsString()
    before=audit(values)
    old=before['baseline_geometry']
    assert any(r['uuid']==uid for w in old['witnesses']for p in w['path']for r in p['contributors'])
    b.Remove(duplicate);after=audit(values)
    assert old!=after['baseline_geometry']
    assert not any(r['uuid']==uid for w in after['baseline_geometry']['witnesses']
        for p in w['path']for r in p['contributors'])


def test_canonical_serialization_does_not_deduplicate_or_drop_identity_fields():
    values=[dict(kind='PCB_TRACK',uuid='same',net='signal'),
        dict(kind='PCB_TRACK',uuid='same',net='other'),dict(kind='PCB_TRACK',uuid='same',net='signal')]
    before=copy.deepcopy(values);values.sort(key=lambda r:json.dumps(r,sort_keys=True,separators=(',',':')))
    assert len(values)==3 and values.count(before[0])==2
    assert before[1]in values

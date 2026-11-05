import pytest
import cec_profile_ground_addition as s

SOURCE='(kicad_pcb (version 1) (zone(net 2)(layer "F.Cu")(uuid "old")(filled_polygon(pts(xy 1 2)))))'
NEW='(zone(net 1)(layer "In1.Cu")(uuid "new")(connect_pads(clearance 0.3))(polygon(pts(xy 0 0)(xy 10 0)(xy 10 10)))(filled_polygon(pts(xy 1 1)(xy 9 1)(xy 9 9))))'
@pytest.mark.parametrize('old,new',[
 ('(net 1)','(net 2)'),('(clearance 0.3)','(clearance 0.1)'),
 ('(xy 10 10)','(xy 11 11)'),('(layer "In1.Cu")','(layer "B.Cu")'),
 ('(uuid "new")','(uuid "unexpected")'),
 ('(net 1)','(net 1)(unknown permission)'),
])
def test_malicious_child_cannot_authorize_own_plane(tmp_path,old,new):
    source=tmp_path/'source.kicad_pcb';source.write_text(SOURCE)
    expected=SOURCE[:-1]+NEW+')'
    with pytest.raises(ValueError):s.validate_expected(source,expected.replace(old,new),expected,{'In1.Cu':'new'})

def test_literal_source_power_fill_never_normalized(tmp_path):
    source=tmp_path/'source.kicad_pcb';source.write_text(SOURCE)
    expected=SOURCE[:-1]+NEW+')'
    assert s.validate_expected(source,expected,expected,{'In1.Cu':'new'})
    changed=expected.replace('(xy 1 2)','(xy 2 2)')
    with pytest.raises(ValueError):s.validate_expected(source,changed,changed,{'In1.Cu':'new'})

def test_partial_existing_ground_literal_survives_new_plane_graft(tmp_path):
    oldground='(zone(net 1)(layer "In1.Cu")(uuid "old-ground")(filled_polygon(pts(xy 3 4))))'
    source_text=SOURCE[:-1]+oldground+')';source=tmp_path/'partial.kicad_pcb';source.write_text(source_text)
    # Even if a serializer's old ground cache changed, graft ignores it.
    generated=source_text.replace('(xy 3 4)','(xy 999 999)')[:-1]+NEW+')'
    result=s.graft(source_text,generated,['new'])
    assert oldground in result and '(xy 999 999)'not in result
    assert s.validate_expected(source,result,result,{'In4.Cu':'new'})
    bad=result.replace('(xy 3 4)','(xy 4 3)')
    with pytest.raises(ValueError):s.validate_expected(source,bad,bad,{'In4.Cu':'new'})

@pytest.mark.parametrize('mapping',[
 {'In1.Cu':'not-uuid'}, {'other':'12345678-1234-1234-1234-123456789abc'},
 {'In1.Cu':'12345678-1234-1234-1234-123456789ABC'},
])
def test_malformed_layer_or_uuid_mapping_refuses(mapping):
    with pytest.raises(ValueError):s.validate_new_ids(mapping,{'In1.Cu'},set())

def test_uuid_duplicates_aliases_refuse():
    uid='12345678-1234-1234-1234-123456789abc'
    with pytest.raises(ValueError):s.validate_new_ids({'a':uid,'b':uid},{'a','b'},set())
    with pytest.raises(ValueError):s.validate_new_ids({'a':uid},{'a'},{uid})

def test_unknown_profile_refuses(monkeypatch):
    import cec_synth_pipeline
    monkeypatch.setattr(cec_synth_pipeline.Config,'load',lambda key:None)
    monkeypatch.setattr(s.force,'_hash',lambda path:'a'*64)
    monkeypatch.setattr(s.pcbnew,'LoadBoard',lambda path:object())
    monkeypatch.setattr(s.ground,'_dedicated_ground_layers',lambda b,h:([],None))
    with pytest.raises(ValueError,match='profile_ground_authority'):s.validate_binding('x','unknown','a'*64)

def test_failed_receiver_persists_traceback(tmp_path):
    report=s.receive_full('absent','absent',tmp_path/'refusal',board_hint='',new_ids={},expected_source_sha256='invalid')
    assert report['ok']is False and report['traceback'] and (tmp_path/'refusal/receiving.json').is_file()

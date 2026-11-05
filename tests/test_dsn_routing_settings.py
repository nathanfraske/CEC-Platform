"""Route-only means a native postroute flag, not zero optimizer threshold."""
import hashlib

import pytest

import cec_dsn_routing_settings as settings
from cec_fr02 import set_postroute_in_dsn


def fixture(extra=''):
    return ('(pcb "board (postroute off)"\n (parser\n (string_quote ")\n)\n'
            ' (structure (layer F.Cu (type signal))'+extra+'\n)\n'
            ' (network (net "postroute (structure)" (pins "X-1" "X-2")))\n'
            ' (wiring (wire (path F.Cu 250 0 0 1000 1000) (net "N") (type protect))))\n')


@pytest.mark.parametrize('extra', ['', ' (autoroute_settings)',
    ' (autoroute_settings (fanout on) (autoroute on) (postroute on) (vias off))',
    ' (autoroute_settings (postroute off) (layer_rule F.Cu (active on)))'])
@pytest.mark.parametrize('enabled', [False, True])
def test_only_owned_execution_setting_changes_and_is_idempotent(extra, enabled):
    text=fixture(extra);new, report=settings.set_postroute(text, enabled)
    start, stop=report['original_span'];difference=len(new)-len(text)
    assert new[:start] == text[:start] and new[stop+difference:] == text[stop:]
    assert report['outside_owned_setting_exact'] and not report['route_or_release_authority']
    assert report['source_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    again, received=settings.set_postroute(new,enabled)
    assert again == new and not received['changed']
    assert received['previous_explicit_postroute'] is enabled
    assert '(type protect)' in new and '(layer F.Cu (type signal))' in new


@pytest.mark.parametrize('extra', [
    ' (autoroute_settings) (autoroute_settings)',
    ' (autoroute_settings (postroute on) (postroute off))',
    ' (autoroute_settings (postroute maybe))',
    ' (autoroute_settings (postroute on off))',
    ' (autoroute_settings (postroute on (fake off)))',
    ' (autoroute_settings ("postroute" off))',
    ' ("autoroute_settings" (postroute off))',
    ' (autoroute_settings (postroute "off"))'])
def test_ambiguous_or_invalid_settings_refused(extra):
    with pytest.raises(ValueError): settings.set_postroute(fixture(extra),False)


@pytest.mark.parametrize('text', ['', '(pcb "unterminated)', '(pcb X (structure)',
    '(pcb X (structure))(pcb Y (structure))', '(pcb X (structure)(structure))',
    '(pcb X)', '(not_pcb X (structure))', '(pcb X (structure)) garbage',
    '(pcb X (structure))\x00'])
def test_invalid_or_unowned_dsn_refused(text):
    with pytest.raises(ValueError): settings.set_postroute(text,False)


@pytest.mark.parametrize('enabled', [0,1,None,'off'])
def test_no_truthiness_based_phase_switch(enabled):
    with pytest.raises(ValueError): settings.set_postroute(fixture(),enabled)


@pytest.mark.parametrize('bound', ['MAX_BYTES','MAX_TOKENS','MAX_DEPTH'])
def test_inventory_bounds_are_not_clean_results(monkeypatch,bound):
    monkeypatch.setattr(settings,bound,1)
    with pytest.raises(ValueError): settings.set_postroute(fixture(),False)


def test_zero_deadline_and_failed_file_transform_leave_input_exact(tmp_path):
    path=tmp_path/'private.dsn';path.write_text(fixture())
    before=path.read_bytes()
    with pytest.raises(RuntimeError):set_postroute_in_dsn(path,False,timeout_s=0)
    assert path.read_bytes()==before
    path.write_text(fixture(' (autoroute_settings (postroute on) (postroute off))'))
    before=path.read_bytes()
    with pytest.raises(ValueError):set_postroute_in_dsn(path,False)
    assert path.read_bytes()==before


def test_atomic_file_transform_keeps_crlf_and_quote_offsets(tmp_path):
    path=tmp_path/'private.dsn';path.write_bytes(fixture().replace('\n','\r\n').encode())
    before=path.read_bytes();report=set_postroute_in_dsn(path,False)
    assert report['source_sha256']==hashlib.sha256(before).hexdigest()
    assert report['output_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert b'\r\n (network' in path.read_bytes()


def test_settings_precede_native_planes_and_keep_power_layers_inactive():
    text=fixture(' (layer "Reference plane" (type power))'
                 ' (plane "G" (polygon "Reference plane" 0 0 0 1 0 1 1))')
    new,report=settings.set_postroute(text,False)
    assert new.index('(autoroute_settings') < new.index('(plane "G"')
    assert '(layer_rule "Reference plane" (active off))' in new
    assert report['inserted_settings_before_planes']
    assert '(layer "Reference plane" (type power))' in new
    assert '(layer_rule "F.Cu" (active on)' in new
    assert '(vias on)' in new and '(start_pass_no 1)' in new
    assert '(preferred_direction_trace_costs 1.0)' in new
    assert not report['absent_settings_heuristics_equivalent']


def test_late_settings_that_native_parser_ignores_are_refused():
    text=fixture(' (plane G (polygon F.Cu 0 0 0 1 0 1 1))'
                 ' (autoroute_settings (postroute on))')
    with pytest.raises(ValueError,match='must_precede_planes'):
        settings.set_postroute(text,False)


def test_layer_restriction_preserves_all_geometry_and_never_enables_power():
    text=fixture(' (layer "mid (power word)" (type signal))'
        ' (layer "plane" (type power)) (layer B.Cu (type signal))'
        ' (plane G (polygon plane 0 0 0 1 0 1 1))')
    text,_=settings.set_postroute(text,False)
    new,report=settings.restrict_active_layers(text,['F.Cu','B.Cu','plane'])
    assert report['changed_fields']==1
    assert '(layer_rule "mid (power word)" (active off)' in new
    assert '(layer_rule "plane" (active off)' in new
    assert new==text.replace('(layer_rule "mid (power word)" (active on)',
                            '(layer_rule "mid (power word)" (active off)')
    again,received=settings.restrict_active_layers(new,['F.Cu','B.Cu','plane'])
    assert again==new and not received['changed']
    assert not report['route_or_release_authority']


@pytest.mark.parametrize('allowed',[[],['missing'],'F.Cu',[None],['plane']])
def test_invalid_unknown_or_only_power_layer_request_refuses(allowed):
    text,_=settings.set_postroute(fixture(' (layer plane (type power))'),False)
    with pytest.raises(ValueError):settings.restrict_active_layers(text,allowed)


def test_duplicate_active_rule_and_incomplete_layer_inventory_refuse():
    text,_=settings.set_postroute(fixture(),False)
    for bad in (text.replace('(active on)','(active on) (active off)'),
                text.replace('(layer_rule "F.Cu"','(layer_rule "wrong"')):
        with pytest.raises(ValueError):settings.restrict_active_layers(bad,['F.Cu'])


def test_failed_layer_restriction_does_not_partially_change_file(tmp_path):
    path=tmp_path/'layers.dsn';path.write_text(fixture())
    before=path.read_bytes()
    with pytest.raises(ValueError):set_postroute_in_dsn(path,False,allowed_layers=['missing'])
    assert path.read_bytes()==before

"""Legacy routing/scoring DRC calls cannot outlive the ten-second command cap."""
import importlib
import json
import subprocess

import pytest


@pytest.mark.parametrize('name', ['cec_score', 'cec_certificate_repair'])
def test_legacy_native_call_has_real_subprocess_deadline_without_reinterpreting_results(tmp_path, monkeypatch, name):
    module = importlib.import_module(name)
    target = tmp_path/'native.json'
    report = {'violations': [{'type': 'clearance', 'severity': 'error'}],
              'unconnected_items': [{'type': 'unconnected_items'}]}
    monkeypatch.setattr(module._tc, 'require_kicad_cli', lambda purpose: '/verified/kicad-cli')
    def run(command, **kwargs):
        assert kwargs['timeout'] == 10.0
        assert kwargs['capture_output'] is True
        assert command[0] == '/verified/kicad-cli'
        target.write_text(json.dumps(report))
        # Violation exit status is not a timeout or a permission to suppress.
        return subprocess.CompletedProcess(command, 2)
    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module._run_drc('explicit.kicad_pcb', str(target)) == report


@pytest.mark.parametrize('name', ['cec_score', 'cec_certificate_repair'])
def test_timed_out_native_call_cannot_return_an_existing_or_partial_report(tmp_path, monkeypatch, name):
    module = importlib.import_module(name)
    target = tmp_path/'stale-native.json'
    target.write_text(json.dumps({'violations': [], 'unconnected_items': []}))
    monkeypatch.setattr(module._tc, 'require_kicad_cli', lambda purpose: '/verified/kicad-cli')
    def stalled(command, **kwargs):
        assert kwargs['timeout'] == 10.0
        raise subprocess.TimeoutExpired(command, kwargs['timeout'])
    monkeypatch.setattr(module.subprocess, 'run', stalled)
    with pytest.raises(subprocess.TimeoutExpired):
        module._run_drc('explicit.kicad_pcb', str(target))

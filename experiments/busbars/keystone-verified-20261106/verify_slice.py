"""Reproducible evidence closeout; no board mutation or release authority."""
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
expected = {
    'experiments/busbars/part-model-20261106/endpoint-first-20261106/vbus-shortcut-v6/candidate/board.kicad_pcb': '4b7457bd28a1a798b6c851b354a2807d02472b8c85b6f583ec48833dce616310',
    'experiments/repack/paired-closed-v2-20261105/cover/board.kicad_pcb': 'c611b8ab0a066dd2bca1d0c6ea6bc9fb665decdc4389b085c30010900fba34db',
    'beta/assembly/hub-atx-stack.json': '0ebac5220a5082a85e4ba431ca56152cbc5153a3e0ae67c8eb7d74970188ac1a',
    'checkpoints/current.json': '1798d2a9b8bfef323c08a5a1aa25ba9872333657a7234e4f8a0d1c9859c82484',
}
assert all(sha(ROOT/p) == digest for p, digest in expected.items())
assets = [WORK/'CEC_Keystone_Study.pretty/Keystone_5104TR_DrawingA_ApplicationPending.kicad_mod',
          WORK/'CEC_Keystone_Study.kicad_sym', WORK/'asset-receipt.json']
before = {str(p.relative_to(ROOT)): sha(p) for p in assets}
subprocess.run([sys.executable, str(WORK/'build_assets.py')], check=True, timeout=10,
               stdout=subprocess.DEVNULL)
assert before == {str(p.relative_to(ROOT)): sha(p) for p in assets}
profile = json.loads((WORK/'part.json').read_text())
assert sha(ROOT/profile['drawing']['path']) == profile['drawing']['sha256']
native = json.loads((WORK/'asset-receipt.json').read_text())
assert native['native_readback_pass'] and not native['span_PCB_copper_present']
test = ET.parse(WORK/'combined-regression.xml').getroot().find('testsuite')
assert int(test.get('tests')) == 62 and int(test.get('failures')) == int(test.get('errors')) == 0
assert not json.loads((WORK/'front-feed-scout/copper-shortcut.json').read_text())['shared_all_guards_probe']['geometry_screen_clear']
assert json.loads((WORK/'front-feed-scout/mux-compile.json').read_text())['status'] == 'compile_refused'
result = dict(schema=1, status='documented_component_ready_for_application_engineering_not_fab_release',
    part='Keystone 5104TR / C7466142', component_drawing_verified=True,
    exact_JLC_Economic_and_Standard_SMT_listing_verified=True,
    basic_assembly_supplier_permission_needed=False,
    JLC_unit_price_USD_at_100_to_499=0.3979, reserved_stock=False, all_in_assembly_quote=False,
    conservative_bare_height_max_mm=1.9304, old_backside_reference_min_mm=1.86,
    old_backside_no_Z_increase_guarantee_rejected=True,
    front_trial_height_allocation_mm=2.5, trial_allocation_is_supplier_guarantee=False,
    guaranteed_constant_underbridge_tunnel=False,
    catalog_current_A=20, application_conductor_screen_A=15, catalog_screen_pass=True,
    application_current_and_thermal_qualified=False,
    native_assets=before, asset_generation_byte_reproducible=True,
    regression=dict(tests=62,failures=0,errors=0,report='combined-regression.xml'),
    independent_review=dict(part_geometry_no_actionable_findings=True,
        path_probe_false_clear_findings_repaired=['fresh edge cache and missing outline',
            'actual ground and plane fills', 'missing native shape inventory',
            'local unknown versus positive obstruction classification'],
        final_source_review_no_further_concrete_false_clear_finding=True,
        saved_fill_freshness_not_qualified=True),
    source_boards_stack_selector_unchanged=expected,
    new_product_boards_saved=0, new_xy_compaction_demonstrated=False,
    native_DRC_rerun=False,
    retained_ATX_counts=dict(errors=0,opens=0,warnings=94,basis='unchanged exact prior received source; not a fresh DRC run'),
    diagnostic_progress=dict(
        fixed_bar_front_poses_rejected=3,
        copper_only_shortcut_rejected_by_full_copper=True,
        coordinated_mux_translation_mm=[4,0],
        mux_body_and_declared_stack_screen_pass=True,
        mux_copper_admitted=False,
        generic_compiler_limitation='programming resistor planner requires its IC owner stationary',
        next_operation='coherent owner/programming-passive source transport; then full-cut power corridor receiving'),
    new_tool='scripts/cec_path_probe.py',
    tool_scope='read-only native path scout with foreign copper, actual saved plane fills, holes, rule areas, fresh edge geometry and unknown inventory; no ownership/current/DRC authority',
    release_authority=False)
(WORK/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))

assert all(sha(ROOT/p) == digest for p, digest in expected.items())

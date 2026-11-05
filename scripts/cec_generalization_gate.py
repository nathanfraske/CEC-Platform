#!/usr/bin/env python3
"""Static anti-overfit gate for the reusable physical-design engine.

Board policy is allowed to name products, terminals, and mechanical seats in
the manifest, board-local JSON, or domain contract modules.  The reusable
search, placement, routing, evidence, and cleanup primitives are not.  This
gate makes that boundary executable so a successful Hub repair cannot quietly
become a Hub-shaped algorithm.
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import cec_beta_manifest


ROOT = Path(__file__).resolve().parents[1]

# These modules form the deliberately product-neutral core.  ``ok`` retains its
# historical meaning: a release run is refused if code advertised as generic
# contains a product or exact-ref selector.
GENERIC_ENGINE_MODULES = (
    "scripts/cec_return_plane_preview.py",
    "scripts/cec_shared_pin_reference.py",
    "scripts/cec_prefreeze_local_pi.py",
    "scripts/cec_full_pipeline.py",
    "scripts/cec_future_congestion.py",
    "scripts/cec_search_policy.py",
    "scripts/cec_courtyard_edge.py",
    "scripts/cec_field_coupling.py",
    "scripts/cec_field_coupling_repair.py",
    "scripts/cec_field_transition_return.py",
    "scripts/cec_route_field_finish.py",
    "scripts/cec_thermal_contract.py",
    "scripts/cec_route_preflight.py",
    "scripts/cec_constraint_ir.py",
    "scripts/cec_sense_topology.py",
    "scripts/cec_kelvin_departure.py",
    "scripts/cec_current_binding.py",
    "scripts/cec_force_current.py",
    "scripts/cec_pad_surface_access.py",
    "scripts/cec_force_sense_evidence.py",
    "scripts/cec_kelvin_copper_cut.py",
    "scripts/cec_kelvin_force_separation.py",
    "scripts/cec_kelvin_branch_repair.py",
    "scripts/cec_saved_family_repair.py",
    "scripts/cec_priority_force_dispatch.py",
    "scripts/cec_terminal_launch_pocket.py",
    "scripts/cec_pth_return_repair.py",
    "scripts/cec_fiducial_reuse.py",
    "scripts/cec_systemd_completion_event.py",
    "scripts/cec_route_candidate_worker.py",
    "scripts/cec_hole_index.py",
    "scripts/cec_fab_native_geometry.py",
    "scripts/cec_blocker_provenance.py",
    "scripts/cec_completion_evidence.py",
    "scripts/cec_final_residual.py",
    "scripts/cec_decoupler_cell.py",
    "scripts/cec_return_escape.py",
    "scripts/cec_endpoint_roadmap.py",
    "scripts/cec_certified_island_access.py",
    "scripts/cec_additive_pair_repair.py",
    "scripts/cec_power_artifact_worker.py",
    "scripts/cec_power_failure.py",
    "scripts/cec_local_via_rebuild.py",
    "scripts/cec_copper_echo.py",
    "scripts/cec_priority_dependency.py",
    "scripts/cec_priority_replacement_receipt.py",
    "scripts/cec_pair_pad_guard.py",
    "scripts/cec_pair_order_repair.py",
    "scripts/cec_qualified_escape.py",
    "scripts/cec_power_guard_geometry.py",
    "scripts/cec_local_return_feedback.py",
    "scripts/cec_post_authority_recovery.py",
    "scripts/cec_reservation_index.py",
    "scripts/cec_finalist_evidence.py",
    "scripts/cec_probe_scope.py",
    "scripts/cec_placement_probe_coverage.py",
    "scripts/cec_placement_search_domain.py",
    "scripts/cec_terminal_range.py",
    "scripts/cec_translation_halfplanes.py",
    "scripts/cec_placement_dependencies.py",
    "scripts/cec_placement_relation_guard.py",
    "scripts/cec_operation_budget.py",
    "scripts/cec_search_budget.py",
    "scripts/cec_frozen_placement_domain.py",
    "scripts/cec_locked_net_ownership.py",
    "scripts/cec_placement_evidence_identity.py",
    "scripts/cec_placement_reconstruction.py",
    "scripts/cec_stage_admission.py",
    "scripts/cec_pass_review.py",
    "scripts/cec_placement_checkpoint.py",
    "scripts/cec_outline_geometry.py",
    "scripts/cec_outline_compaction.py",
    "scripts/cec_assembly_access.py",
    "scripts/cec_assembly_envelope.py",
    "scripts/cec_assembly_instance.py",
    "scripts/cec_assembly_cad.py",
    "scripts/cec_stack_fit_screen.py",
    "scripts/cec_reservoir_screen.py",
    "scripts/cec_edge_recess.py",
    "scripts/cec_placement_geometry.py",
    "scripts/cec_noncontact_placement.py",
    "scripts/cec_board_suite.py",
    "scripts/cec_route_evidence.py",
    "scripts/cec_probe_evidence.py",
    "scripts/cec_search_completion.py",
    "scripts/cec_pair_return_field.py",
    "scripts/cec_preflight_native_recovery.py",
    "scripts/cec_mount_patterns.py",
    "scripts/cec_mating_rows.py",
    "scripts/cec_interface_eco.py",
    "scripts/cec_interface_routes.py",
    "scripts/cec_maze_channels.py",
    "scripts/cec_hardware_qualification.py",
    "scripts/cec_output_mount_audit.py",
    "scripts/cec_board_policy.py",
    "scripts/cec_rail_geometry.py",
    "scripts/cec_rail_detour.py",
    "scripts/cec_transition_landings.py",
    "scripts/cec_parallel_copper.py",
    "scripts/cec_rail_transition_search.py",
    "scripts/cec_construction_feedback.py",
    "scripts/cec_native_pad_obstacles.py",
    "scripts/cec_materialized_candidate.py",
    "scripts/cec_conductor_proposal.py",
    "scripts/cec_route_dimensions.py",
    "scripts/cec_dimension_repair.py",
    "scripts/cec_escape_cell.py",
    "scripts/cec_native_items.py",
    "scripts/cec_copper_overlap.py",
    "scripts/cec_failure_replay.py",
    "scripts/cec_passes.py",
    "scripts/cec_cell_packing.py",
    "scripts/cec_supply_group.py",
    "scripts/cec_supply_native.py",
    "scripts/cec_placement_commit.py",
    "scripts/cec_portal_copper.py",
    "scripts/cec_portal_feedback.py",
    "scripts/cec_frozen_copper.py",
    "scripts/cec_blueprint_ownership.py",
    "scripts/cec_blueprint_placement.py",
    "scripts/cec_power_body.py",
    "scripts/cec_power_local_replay.py",
    "scripts/cec_power_order.py",
    "scripts/cec_ranked_frontier.py",
    "scripts/cec_local_seating.py",
    "scripts/cec_constraint_seating.py",
    "scripts/cec_cell_domains.py",
    "scripts/cec_cell_proposals.py",
    "scripts/cec_pair_banks.py",
    "scripts/cec_parallel_links.py",
    "scripts/cec_edge_packing.py",
    "scripts/cec_mounting_contract.py",
    "scripts/cec_placement_route_prefix.py",
    "scripts/cec_pair_heading_boundary.py",
    "scripts/cec_critical_checkpoint.py",
    "scripts/cec_generated_fill_seams.py",
    "scripts/cec_pth_pair_returns.py",
    "scripts/cec_local_power_prefix.py",
    "scripts/cec_power_terminal_access.py",
    "scripts/cec_distributed_supply.py",
    "scripts/cec_rated_supply_detour.py",
    "scripts/cec_measurement_current_branch.py",
    "scripts/cec_local_branch_access.py",
    "scripts/cec_ground_reference_access.py",
)

# The production entry point still traverses older coordinator modules.  They
# must be audited too: otherwise a clean ten-file core can incorrectly make the
# *whole* pipeline look generic while the live placer contains J3/J4 moves or a
# product-keyed branch.  Policy/contract modules are intentionally not listed;
# board facts belong there and are data consumed by these engines.
FULL_PIPELINE_RUNTIME_MODULES = tuple(dict.fromkeys((
    *GENERIC_ENGINE_MODULES,
    "scripts/cec_synth_pipeline.py",
    "scripts/cec_constraints.py",
    "scripts/cec_fr.py",
    "scripts/cec_staged_fr.py",
    "scripts/cec_slab_pour.py",
    "scripts/cec_pour_plan.py",
    "scripts/cec_precision_route.py",
    "scripts/cec_coord_router.py",
    "scripts/cec_pair_return.py",
    "scripts/cec_device_bypass.py",
    "scripts/cec_ground_plane.py",
    "scripts/cec_fab_repair.py",
    "scripts/cec_score.py",
    "scripts/cec_route_quality.py",
)))

PHYSICAL_MUTATION_MODULES = tuple(dict.fromkeys((
    *FULL_PIPELINE_RUNTIME_MODULES,
    "scripts/cec_force_lanes.py",
    "scripts/cec_force_rails.py",
    "scripts/cec_current_topology.py",
)))

# Product facts are expected here.  These files are contracts/data providers,
# not search or mutation engines, and their values are selected through generic
# interfaces.  They remain visible in the report rather than disappearing from
# the runtime closure.
DECLARATIVE_POLICY_MODULES = frozenset({
    "scripts/cec_beta_manifest.py",
    "scripts/cec_board_policy.py",
    "scripts/cec_mezz_contract.py",
    "scripts/cec_xfcn_contract.py",
    "scripts/cec_power_budget.py",
})

# Restrict this to conventional reference prefixes.  The previous broad
# ``[A-Z]{1,4}`` expression classified part families such as INA238 and ESP32
# as reference designators, which made extending the gate to the live runtime
# too noisy to be useful.
_REFERENCE = re.compile(
    r"^(?:FID|LED|RS|SW|TP|FB|[JHURCQLFD])[1-9][0-9]{0,3}$")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Return identities of literal nodes used only as documentation."""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.add(id(first.value))
    return out


def _literal_strings(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            yield node.lineno, node.value


def audit_file(path: str | os.PathLike[str], *, product_keys=()) -> list[dict]:
    """Audit one executable module without requiring repository layout.

    This small public seam is also the synthetic regression fixture: planted
    product and exact-ref selectors must be caught before the repository-wide
    gate can be trusted.
    """
    path = Path(path)
    product_keys = tuple(sorted((str(value) for value in product_keys),
                                key=len, reverse=True))
    violations = []
    for line, literal in _literal_strings(path):
        lower = literal.lower()
        product = next((key for key in product_keys
                        if key.lower() in lower), None)
        if product:
            violations.append({
                "line": line, "kind": "product_identity",
                "literal": product,
            })
            continue
        # Exact reference selectors are forbidden in an engine.  Generic
        # prefix/role rules (for example ref.startswith("FID")) remain legal.
        if _REFERENCE.fullmatch(literal.strip()):
            violations.append({
                "line": line, "kind": "reference_selector",
                "literal": literal,
            })
    return violations


def _audit_modules(root: Path, modules, product_keys):
    violations = []
    checked = []
    for relative in modules:
        path = root / relative
        if not path.is_file():
            violations.append({
                "module": relative, "line": 0,
                "kind": "missing_runtime_module", "literal": "",
            })
            continue
        checked.append(relative)
        for row in audit_file(path, product_keys=product_keys):
            violations.append({"module": relative, **row})
    return checked, violations


def _local_imports(path: Path):
    """Yield repository-local module basenames imported anywhere in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            base = str(name).split(".", 1)[0]
            if base.startswith("cec_"):
                yield base


def runtime_module_closure(root: str | os.PathLike[str] = ROOT):
    """Resolve the actual local import closure of the production entry point."""
    root = Path(root).resolve()
    pending = ["scripts/cec_full_pipeline.py"]
    seen = set()
    while pending:
        relative = pending.pop()
        if relative in seen:
            continue
        seen.add(relative)
        path = root / relative
        if not path.is_file():
            continue
        for module in _local_imports(path):
            child = "scripts/%s.py" % module
            if (root / child).is_file() and child not in seen:
                pending.append(child)
    return tuple(sorted(seen))


def audit(root: str | os.PathLike[str] = ROOT) -> dict:
    """Audit both the neutral core and the complete production runtime.

    ``ok`` protects the already-declared generic core and remains the intake
    safety gate.  ``full_pipeline_generic`` is the stronger maturity claim: it
    stays false until *every* load-bearing runtime module is free of executable
    product/ref selectors.  Keeping the two fields separate prevents legacy
    debt from being hidden while allowing it to be migrated in bounded slices.
    """
    root = Path(root).resolve()
    product_keys = tuple(sorted(
        (str(row["board"]) for row in cec_beta_manifest.PROJECTS),
        key=len, reverse=True))
    checked, violations = _audit_modules(
        root, GENERIC_ENGINE_MODULES, product_keys)
    physical_checked, physical_violations = _audit_modules(
        root, (relative for relative in PHYSICAL_MUTATION_MODULES
               if relative not in DECLARATIVE_POLICY_MODULES), product_keys)
    physical_engine_generic = not physical_violations
    runtime_closure = tuple(sorted(set(FULL_PIPELINE_RUNTIME_MODULES)
                                   | set(runtime_module_closure(root))))
    runtime_policy_modules = tuple(
        relative for relative in runtime_closure
        if relative in DECLARATIVE_POLICY_MODULES)
    runtime_engine_modules = tuple(
        relative for relative in runtime_closure
        if relative not in DECLARATIVE_POLICY_MODULES)
    runtime_checked, runtime_violations = _audit_modules(
        root, runtime_engine_modules, product_keys)
    full_pipeline_generic = not runtime_violations
    if full_pipeline_generic:
        maturity = "generic_runtime"
    elif physical_engine_generic:
        maturity = "generic_physical_engine_with_integration_debt"
    else:
        maturity = "generic_core_with_legacy_physical_and_integration_debt"
    return {
        "schema": 2,
        "ok": not violations,
        # ``ok`` is retained for compatibility with the original core-only
        # intake guard.  A generic *release* claim is stronger and may only
        # pass when the actual production import closure is clean.
        "release_ok": full_pipeline_generic,
        "checked_modules": checked,
        "known_products": list(product_keys),
        "violations": violations,
        "physical_engine_generic": physical_engine_generic,
        "physical_checked_modules": physical_checked,
        "physical_violations": physical_violations,
        "physical_violation_count": len(physical_violations),
        "full_pipeline_generic": full_pipeline_generic,
        "pipeline_maturity": maturity,
        "runtime_checked_modules": runtime_checked,
        "runtime_policy_modules": list(runtime_policy_modules),
        "runtime_module_closure": list(runtime_closure),
        "runtime_violations": runtime_violations,
        "runtime_violation_count": len(runtime_violations),
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["release_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

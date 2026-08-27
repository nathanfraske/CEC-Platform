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

# These modules form the new reusable pipeline feature set.  Board-local policy
# and compatibility monoliths (for example cec_fresh_wave.py) are deliberately
# outside this list; migrating those contracts is a separate, explicit task.
GENERIC_ENGINE_MODULES = (
    "scripts/cec_full_pipeline.py",
    "scripts/cec_future_congestion.py",
    "scripts/cec_search_policy.py",
    "scripts/cec_route_preflight.py",
    "scripts/cec_constraint_ir.py",
    "scripts/cec_blocker_provenance.py",
    "scripts/cec_completion_evidence.py",
    "scripts/cec_decoupler_cell.py",
    "scripts/cec_power_artifact_worker.py",
    "scripts/cec_board_policy.py",
)

_REFERENCE = re.compile(r"^(?:[A-Z]{1,4})[1-9][0-9]{0,3}$")


def _literal_strings(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def audit(root: str | os.PathLike[str] = ROOT) -> dict:
    """Return an auditable report; ``ok`` is false on product/ref literals."""
    root = Path(root).resolve()
    product_keys = tuple(sorted(
        (str(row["board"]) for row in cec_beta_manifest.PROJECTS),
        key=len, reverse=True))
    violations = []
    checked = []
    for relative in GENERIC_ENGINE_MODULES:
        path = root / relative
        if not path.is_file():
            violations.append({
                "module": relative, "line": 0,
                "kind": "missing_generic_module", "literal": "",
            })
            continue
        checked.append(relative)
        for line, literal in _literal_strings(path):
            lower = literal.lower()
            product = next((key for key in product_keys
                            if key.lower() in lower), None)
            if product:
                violations.append({
                    "module": relative, "line": line,
                    "kind": "product_identity", "literal": product,
                })
                continue
            # A complete refdes selector in engine code is almost always a
            # board repair in disguise.  Words embedded in prose are allowed;
            # exact selectors belong in policy or a domain contract.
            if _REFERENCE.fullmatch(literal.strip()):
                violations.append({
                    "module": relative, "line": line,
                    "kind": "reference_selector", "literal": literal,
                })
    return {
        "schema": 1,
        "ok": not violations,
        "checked_modules": checked,
        "known_products": list(product_keys),
        "violations": violations,
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

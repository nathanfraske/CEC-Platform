"""Bind semantic source and selected assembly inputs, not only Python code.

Missing physical peers remain missing observations, never an applicability
waiver. Receiving must still establish the complete physical contract.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .legacy import ROOT, bootstrap
from .identity import require

bootstrap()


def environment_identity():
    return {
        key: hashlib.sha256(value.encode()).hexdigest()
        for key, value in os.environ.items()
        if key.startswith(("CEC_", "KICAD_"))
    }


def inputs(source, board_hint):
    import cec_beta_manifest as manifest
    import cec_assembly_envelope as assembly
    from .native import _native

    paths = {ROOT / "cec-policy.json"}
    paths.update((ROOT / "lib").rglob("*.json"))
    paths.update((ROOT / "lib").rglob("*.csv"))
    entry = manifest.BY_BOARD.get(board_hint)
    if entry:
        directory = ROOT / "beta" / entry["directory"]
        for suffix in ("*.kicad_sch", "*.json", "*.kicad_dru", "*.kicad_pro"):
            paths.update(
                path
                for path in directory.glob(suffix)
                if not path.name.startswith("tmp")
            )
        paths.update((directory / "bom").glob("*.csv"))
    pcbnew, quiet = _native()
    policy = assembly.declared_policy(str(source))
    if policy:
        require(
            policy.get("role") in ("carrier", "cover"),
            "literal_selected_assembly_role_required",
        )
        contract = ROOT / policy["contract"]
        pair = ROOT / policy["pair"]
        paths.update((contract, pair))
        if pair.is_file():
            declaration = json.loads(pair.read_text())
            peer = declaration["cover" if policy["role"] == "carrier" else "carrier"]
            paths.add(ROOT / peer["path"])
    require(len(paths) <= 1024, "bounded_semantic_authority_closure_required")
    result = {}
    total = 0
    for path in sorted(paths):
        path = path.resolve()
        identity = None
        if path.is_file():
            total += path.stat().st_size
            require(
                total <= 128 * 1024 * 1024, "bounded_semantic_authority_bytes_required"
            )
            identity = hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path)] = identity
    return result

"""Explicit, content-bound assembly instances for saved-board release reviews.

An instance selects two immutable artifacts, not new dimensions, tolerances or
an approval. Invalid explicit context must fail closed rather than fall back to
an older policy peer. The normal native envelope/contact/vent tests still run.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


CONTEXT_KEY = "assembly_instance"
ROLES = ("carrier", "cover")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _bound_file(record, root):
    if (not isinstance(record, dict) or set(record) != {"path", "sha256"}
            or not isinstance(record["path"], str) or not record["path"]
            or not isinstance(record["sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
        raise ValueError("exact assembly artifact path and SHA-256 required")
    path = (Path(root) / record["path"]).resolve()
    if not path.is_file() or digest(path) != record["sha256"]:
        raise ValueError("assembly artifact missing or hash changed: " + str(path))
    return path


def resolve(path, instance, root):
    """Validate both sides AND the contract before reading native geometry."""
    if (not isinstance(instance, dict)
            or set(instance) != {"schema", "role", "contract", "members"}
            or type(instance["schema"]) is not int or instance["schema"] != 1
            or instance["role"] not in ROLES
            or not isinstance(instance["members"], dict)
            or set(instance["members"]) != set(ROLES)):
        raise ValueError("complete explicit two-member assembly instance required")
    contract = _bound_file(instance["contract"], root)
    members = {role: _bound_file(instance["members"][role], root) for role in ROLES}
    if members["carrier"] == members["cover"]:
        raise ValueError("distinct assembly member artifacts required")
    if Path(path).resolve() != members[instance["role"]]:
        raise ValueError("reviewed board is not the selected assembly member")
    paths = {"contract": contract, **members}
    return dict(role=instance["role"], paths=paths,
                hashes={key: digest(value) for key, value in paths.items()})


def check(board, path, instance, root):
    """Run the original physical checks on an explicitly selected artifact pair."""
    import pcbnew
    import cec_assembly_envelope as assembly
    from cec_stack_fit_screen import vertical_screen

    bound = resolve(path, instance, root)
    contract = json.loads(bound["paths"]["contract"].read_text())
    peer_role = "cover" if bound["role"] == "carrier" else "carrier"
    peer = pcbnew.LoadBoard(str(bound["paths"][peer_role]))
    if peer is None:
        raise ValueError("selected native assembly peer cannot be loaded")
    boards = {bound["role"]: board, peer_role: peer}
    result, _ = assembly.evaluate_boards(boards["carrier"], boards["cover"], contract)
    result["vertical"] = vertical_screen(**contract["vertical"])
    result["ok"] &= result["vertical"]["ok"]
    result["vent_reservations"] = []
    for role in ROLES:
        vents = assembly.facing_vents(result, contract, role)
        result["vent_reservations"].extend(
            dict(row, receiver=role) for row in assembly.vent_reservations(boards[role], vents))
    result["ok"] &= all(row["ok"] for row in result["vent_reservations"])
    result["authority_unchanged"] = all(
        digest(value) == bound["hashes"][key] for key, value in bound["paths"].items())
    result["ok"] &= result["authority_unchanged"]
    result["selected_instance"] = {
        "role": bound["role"],
        "files": {key: dict(path=str(value), sha256=bound["hashes"][key])
                  for key, value in bound["paths"].items()},
        "mating_pairs": contract["mating_pairs"],
        "hardware_anchor_pairs": [row["anchor_pair"] for row in contract.get("hardware", [])],
    }
    result["release_authority"] = False
    return result

"""Partition source-proven auxiliary supply cells from rigid precision cells.

This is a template compiler, not an editor of routed boards. Released parts
remain in the source population and must earn the normal placement/local-route
admission. Unknown/shared precision copper is retained, never guessed away.
"""
from __future__ import annotations

import copy


def partition_supply(template, *, ref_map, net_map, requirements, pin_nets):
    """Return a new template and a deterministic ownership certificate.

    Only a source-assigned, fully recorded two-terminal bypass whose owner is
    in this template can leave it. A delegated role may touch only released
    caps or their owners. If another part uses it (e.g. a force terminal or
    filter), retain the complete cell. No board, reference or coordinate rule
    participates. Retained precision copper is copied byte-for-byte as data.
    """
    parts = template.get("parts") or {}
    dest = {r: str(ref_map.get(r, r)) for r in parts}
    if len(set(dest.values())) != len(dest):
        raise ValueError("blueprint reference map is not one-to-one")
    inverse = {value: key for key, value in dest.items()}
    roles = template.get("net_roles") or {}
    resolve = lambda role: str(net_map.get(role, roles.get(role, role)))
    rows = {}
    for section in ("ports", "internal_pads"):
        for role, spec in (template.get(section) or {}).items():
            rows.setdefault(role, []).extend(spec.get("pads") or ())
    anchor = template.get("anchor")
    anchor = anchor.get("ref") if isinstance(anchor, dict) else anchor
    candidates = {}
    for cap, req in sorted(requirements.items()):
        owner = str(req.get("owner") or "")
        local_cap = inverse.get(str(cap))
        local_owner = inverse.get(owner)
        if not local_cap or not local_owner or local_cap == anchor:
            continue
        rail = str(req.get("rail") or "")
        ret = str(req.get("return_rail") or "GND")
        source = {str(p): str(n) for (r, p), n in pin_nets.items()
                  if str(r) == str(cap) and n}
        recorded = {(str(p.get("pad")), resolve(role))
                    for role, group in rows.items() for p in group
                    if p.get("ref") == local_cap}
        if (not rail or rail == ret or len(source) != 2
                or set(source.values()) != {rail, ret}
                or recorded != set(source.items())
                or pin_nets.get((owner, str(req.get("pin")))) != rail):
            continue
        used_roles = {role for role, group in rows.items()
                      if any(p.get("ref") == local_cap for p in group)}
        candidates[local_cap] = {"owner": local_owner, "roles": used_roles}

    # Removing one unsafe cap can make a previously shared role unsafe for
    # another. Reach the finite fixed point before deleting any template data.
    while candidates:
        allowed = set(candidates) | {q["owner"] for q in candidates.values()}
        rejected = set()
        for cap, req in candidates.items():
            for role in req["roles"]:
                for pad in rows[role]:
                    ref, pin = str(pad.get("ref")), str(pad.get("pad"))
                    if (ref not in allowed or ref not in dest
                            or pin_nets.get((dest[ref], pin)) != resolve(role)):
                        rejected.add(cap)
        if not rejected:
            break
        candidates = {r: q for r, q in candidates.items() if r not in rejected}

    delegated = set().union(*(q["roles"] for q in candidates.values())) if candidates else set()
    out = copy.deepcopy(template)
    removed = {}
    for key in ("internal_tracks", "port_tracks", "vias"):
        old = out.get(key) or []
        new = [row for row in old if row.get("net_role") not in delegated]
        removed[key] = len(old) - len(new)
        if key in out:
            out[key] = new
    if candidates:
        out["parts"] = {r: p for r, p in out["parts"].items() if r not in candidates}
        for section in ("ports", "internal_pads"):
            for spec in (out.get(section) or {}).values():
                spec["pads"] = [p for p in spec.get("pads") or () if p.get("ref") not in candidates]
        for role in sorted(delegated):
            spec = (out.get("internal_pads") or {}).pop(role, None)
            if spec:
                port = out.setdefault("ports", {}).setdefault(role, {"net": spec.get("net"), "pads": []})
                for pad in spec["pads"]:
                    if pad not in port["pads"]:
                        port["pads"].append(pad)
        # Legacy extraction stores this non-emitted list with implicit GND
        # ownership. Do not leave obsolete ground-return geometry in metadata.
        if "GND" in {resolve(role) for role in delegated} and "gnd_vias" in out:
            removed["gnd_vias"] = len(out["gnd_vias"])
            out["gnd_vias"] = []
    report = {"schema": 1, "released_refs": sorted(dest[r] for r in candidates),
              "retained_refs": sorted(dest[r] for r in parts if r not in candidates),
              "delegated_nets": sorted({resolve(role) for role in delegated}),
              "removed_copper": removed,
              "scope": "source_proven_supply_ownership_not_route_admission"}
    return out, report

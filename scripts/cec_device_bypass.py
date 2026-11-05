#!/usr/bin/env python3
"""Shared selected-device bypass rules for placement and board verification."""
import re


def distinct_assignment(edges, order):
    """Maximum-cardinality matching of ordered requirement/capacitor edges.

    Edges are ``requirement -> [(capacitor, caller_metric), ...]``; their
    supplied order is the caller's deterministic preference. The alternating
    path is iterative (no recursion-depth dependence for large boards). Keep
    one authoritative capacitor-owner map and reconstruct results only after
    all augmentations: deleting an old owner's result after recursively moving
    it used to discard its *new* assignment in the physical-board checker.
    """
    cap_owner = {}
    owner_cap = {}
    metrics = {}
    for start in order:
        if start in owner_cap:
            continue
        # Preserve already chosen owners when an unused compatible part is
        # available. Alternating paths are for increasing cardinality, not
        # gratuitously swapping otherwise valid common-rail assignments.
        unused = next(((cap, metric) for cap, metric in edges.get(start, ())
                       if cap not in cap_owner), None)
        if unused is not None:
            cap, metric = unused
            cap_owner[cap] = start
            owner_cap[start] = cap
            metrics[start] = metric
            continue
        # Iterative depth-first traversal preserves each caller's edge order.
        stack = [(start, iter(edges.get(start, ())))]
        seen_caps = set()
        parents = {}
        free = None
        while stack:
            req, choices = stack[-1]
            edge = next(choices, None)
            if edge is None:
                stack.pop()
                continue
            cap, metric = edge
            if cap in seen_caps:
                continue
            seen_caps.add(cap)
            parents[cap] = (req, metric)
            previous = cap_owner.get(cap)
            if previous is None:
                free = cap
                break
            stack.append((previous, iter(edges.get(previous, ()))))
        while free is not None:
            req, metric = parents[free]
            old = owner_cap.get(req)
            cap_owner[free] = req
            owner_cap[req] = free
            metrics[req] = metric
            free = old
    return {req: (cap, metrics[req]) for req, cap in owner_cap.items()}


FIXED_DEVICE_RULES = (
    ("INA238", "6", "100n", "INA238"),
    ("INA181", "6", "100n", "INA181"),
    ("INA180", "5", "100n", "INA180"),
    ("INA240", "6", "100n", "INA240"),
    ("74AHCT244", "20", "100n", "74AHCT244"),
    ("SN74AHCT1G08", "5", "100n", "SN74AHCT1G08"),
    ("74LVC1G17", "5", "100n", "SN74LVC1G17"),
    ("REF3030", "1", "100n", "REF3030"),
    ("TPS3839", "3", "100n", "TPS3839"),
    ("TLV7011", "5", "100n", "TLV7011"),
    ("TJA1051", "3", "100n", "TJA1051"),
)


# Some devices require a high-frequency capacitor between two supply domains,
# not from one domain to ground.  Keep this separate from FIXED_DEVICE_RULES:
# both contracts apply to a TJA1051T/3 (VCC-to-GND on pin 3 and VIO-to-VCC
# between pins 5 and 3), and treating the second capacitor as an ordinary
# ground bypass encodes the wrong EMC circuit.
RAIL_TO_RAIL_DEVICE_RULES = (
    ("TJA1051T/3", "5", "3", "100n",
     "NXP AH1014 Rev. 1.5 sec. 8.9: VIO-to-VCC"),
    ("TJA1051TK/3", "5", "3", "100n",
     "NXP AH1014 Rev. 1.5 sec. 8.9: VIO-to-VCC"),
    ("TJA1042/3", "5", "3", "100n",
     "NXP AH1014 Rev. 1.5 sec. 8.9: VIO-to-VCC"),
)


def rail_return_repair_proposals(comps, nets, missing, sheets):
    """Identify an unambiguous existing local VIO bypass for source review.

    This is a schematic-change proposal, never a placement/gate waiver. Only
    a selected-device rail-to-rail requirement may nominate a same-sheet,
    compatible, populated ceramic presently returned to GND. Explicit owners
    must agree. Multiple candidates or a different owner are not guessed.
    Callers must prove the local wire branch is isolated and verify the full
    exported netlist delta before accepting the proposed source change.
    """
    pins = {}
    for net, nodes in nets.items():
        for ref, pin in nodes:
            pins.setdefault(ref, {})[str(pin)] = net
    proposals = []
    for req in missing:
        owner, pin = req['ref'], str(req['pin'])
        if not req.get('return_pin') or req.get('return_rail') in (None, 'GND'):
            continue
        matches = []
        for ref, comp in comps.items():
            if (not ref.startswith('C') or getattr(comp, 'excluded_from_bom', False)
                    or sheets.get(ref) != sheets.get(owner) or not sheets.get(owner)):
                continue
            cp = pins.get(ref, {})
            if len(cp) != 2 or set(cp.values()) != {req['rail'], 'GND'}:
                continue
            declared = declared_owner(comp.props)
            if declared and declared not in ((owner, pin), (owner, '')):
                continue
            farads = capacitance_f(comp.value)
            if (farads is None or not kind_compatible(req['kind'], farads)
                    or not local_bypass_technology(comp.value, comp.footprint)):
                continue
            matches.append((ref, next(p for p,n in cp.items() if n == 'GND')))
        if len(matches) == 1:
            ref, return_pin = matches[0]
            proposals.append(dict(cap=ref, cap_return_pin=return_pin,
                                  owner=owner, owner_pin=pin,
                                  old_net='GND', new_net=req['return_rail'],
                                  source=req['source'], sheet=sheets[ref]))
    return proposals


def reference_affinity(cap_ref, owner_ref):
    """Whether two reference designators declare the same named cell.

    C30/U30 and C65VSB1/U65VSB1 are common schematic conventions.  Comparing
    only the trailing decimal incorrectly aliases every repeated ``*V1`` or
    ``*A1`` channel and lets geometrically identical rail capacitors swap
    owners.  Strip only the alphabetic component-class prefix and require the
    complete remaining alphanumeric cell key to match.  Callers additionally
    apply this only to single-supply owners; boards without the convention
    continue to use the ordinary topology/value/distance matcher.
    """
    cap = re.fullmatch(r"[A-Za-z]+([0-9][A-Za-z0-9_]*)",
                       str(cap_ref or ""))
    owner = re.fullmatch(r"[A-Za-z]+([0-9][A-Za-z0-9_]*)",
                         str(owner_ref or ""))
    return bool(cap and owner
                and cap.group(1).upper() == owner.group(1).upper())


def declared_owner(properties):
    """Parse an explicit schematic bypass owner as ``(reference, pin)``.

    Common-rail capacitors are electrically interchangeable in a netlist, but
    their placement function is not.  A ``BypassOwner=U1.2`` symbol property
    provides a portable source-level tie when reference-number affinity cannot
    express multiple capacitors at one supply pin.  Invalid declarations fail
    closed by returning a non-matching owner token to the caller rather than
    silently reverting the capacitor to the common pool.
    """
    raw = str((properties or {}).get("BypassOwner", "") or "").strip()
    if not raw:
        return None
    match = re.fullmatch(r"([A-Za-z]+[0-9][A-Za-z0-9_]*)(?:\.([^\s.]+))?", raw)
    if not match:
        return (raw, "")
    return match.group(1), match.group(2)


def capacitor_identity(reference,footprint):
    """Preserve legacy C references and recognise real renamed cap packages.

    Do not treat a bare resistance value as farads just because the generic
    value parser accepts unitless notation. Imported/native capacitor library
    identity is a positive alternative to the reference convention, not a
    general two-pad or nearest-to-an-IC component heuristic.
    """
    return bool(str(reference).startswith('C') or re.search(
        r'(?:^|:)(?:Capacitor_SMD|Capacitor_THT)(?::|$)',str(footprint)))


def local_bypass_technology(value, footprint):
    """Whether a capacitor may own a selected-device local bypass role.

    Local bypass ownership is a high-frequency placement/routing contract, not
    a generic capacitance-on-the-rail query.  A bulk electrolytic, polymer or
    tantalum reservoir may be essential to the PDN, but it cannot substitute
    for the ceramic at the IC pins.  Unknown footprints remain eligible for
    legacy/imported designs; known bulk technologies fail closed.
    """
    text = "%s %s" % (value or "", footprint or "")
    normalized = text.lower().replace("-", "_")
    bulk_tokens = (
        "cp_elec", "cp_radial", "capacitor_tht", "supercap",
        "tantalum", "polymer",
    )
    return not any(token in normalized for token in bulk_tokens)


def capacitance_f(value):
    """Parse compact PCB/schematic capacitance notation into farads."""
    text = (value or "").strip().lower().replace("µ", "u").replace("μ", "u")
    text = text.replace(" ", "").removesuffix("f")
    embedded = re.fullmatch(r"(\d+)([pnum])(\d+)", text)
    if embedded:
        number = float("%s.%s" % (embedded.group(1), embedded.group(3)))
        prefix = embedded.group(2)
    else:
        plain = re.fullmatch(r"(\d+(?:\.\d+)?)([pnum]?)", text)
        if not plain:
            return None
        number = float(plain.group(1))
        prefix = plain.group(2)
    return number * {"": 1.0, "p": 1e-12, "n": 1e-9,
                     "u": 1e-6, "m": 1e-3}[prefix]


def kind_compatible(kind, farads):
    if farads is None:
        return False
    if kind == "100n":
        return abs(farads - 100e-9) <= 1e-15
    if kind == "at-least-1u":
        return farads + 1e-15 >= 1e-6
    if kind == "at-least-10u":
        return farads + 1e-15 >= 10e-6
    if kind == "local-ceramic":
        # TI TPS212x Rev F section 11 specifies local low-ESR X5R/X7R
        # ceramics, not a <=1 uF value ceiling. Technology, one-to-one
        # ownership and pin proximity are independently enforced. This
        # inventory rule does not qualify effective capacitance or transients.
        return farads > 0
    if kind == "local-hf":
        # A large ceramic reservoir is still useful for load-step energy, but
        # it must not own the device's high-frequency pin-bypass role.  Keep
        # the value ceiling intentionally broad enough for 100 nF or 1 uF
        # X5R/X7R implementations; footprint technology is checked
        # independently by ``local_bypass_technology``.
        return 0 < farads <= 1e-6 + 1e-15
    return farads > 0


def bind_declared_requirements(requirements, caps, pin_nets, *, project_max_mm=3.5, owner_refs=None,
                               is_ground=lambda n: n.rsplit("/", 1)[-1].upper() == "GND"):
    """Make every fitted, explicitly owned local capacitor a physical contract.

    Device minimums and declared local bulk are complementary. Bind compatible
    minimums first (one capacitor per requirement); append an exact-capacitor
    contract for every remaining declaration. Never manufacture a universal
    bulk value or let a larger capacitor replace a required HF bypass. The
    project distance ceiling is a placement policy, not a datasheet claim.
    Both source placement and native-board verification consume these rows.
    """
    import math
    if not math.isfinite(project_max_mm) or project_max_mm <= 0:
        raise ValueError("declared bypass distance must be finite and positive")
    rows = [dict(req) for req in requirements]
    declared = []
    for cap in sorted(caps, key=lambda c: c["ref"]):
        owner = cap.get("declared_owner")
        if not owner:
            continue
        nets = set(cap.get("net_pins", cap.get("net_pads", {})))
        ref, pin = owner
        candidates = [(p, net) for (r, p), net in pin_nets.items()
                      if r == ref and (not pin or str(p) == pin)
                      and net in nets and not is_ground(net)]
        if (len(nets) != 2 or len(candidates) != 1
                or not cap.get("local_bypass_technology", True)):
            raise ValueError("invalid or ambiguous declared bypass %s -> %s.%s" % (cap["ref"], ref, pin))
        pin, rail = candidates[0]
        return_rail = next(n for n in nets if n != rail)
        if not is_ground(return_rail) and not any(r == ref and n == return_rail
                                                   for (r, _p), n in pin_nets.items()):
            raise ValueError("declared bypass %s return is not an owner supply or ground" % cap["ref"])
        if owner_refs is not None and ref not in owner_refs:
            continue  # valid declaration owned outside this placement subproblem
        declared.append((cap, str(pin), rail, return_rail))
    edges = {}
    for index, req in enumerate(rows):
        edges[index] = [(cap["ref"], None) for cap, pin, rail, ret in declared
                        if cap["declared_owner"][0] == req["ref"] and pin == req["pin"]
                        and rail == req["rail"] and ret == req.get("return_rail", "GND")
                        and kind_compatible(req["kind"], cap["farads"])]
    matches = distinct_assignment(edges, sorted(edges, key=lambda i: (len(edges[i]), i)))
    bound = set()
    for index, (cap_ref, _metric) in matches.items():
        rows[index]["cap_ref"] = cap_ref
        bound.add(cap_ref)
    for cap, pin, rail, ret in declared:
        if cap["ref"] in bound:
            continue
        ref = cap["declared_owner"][0]
        rows.append({"id": "%s:%s:declared:%s" % (ref, pin, cap["ref"]),
                     "ref": ref, "pin": pin, "rail": rail, "return_rail": ret,
                     "return_pin": None, "kind": "local-ceramic",
                     "cap_ref": cap["ref"], "max_mm": project_max_mm,
                     "source": "schematic BypassOwner local-capacitor contract"})
    return rows


def requirements_for_value(value, project_max_mm=3.5, *, mpn=None, footprint=None):
    """Yield (pin, kind, max_mm, source) requirements for a fitted device."""
    value = value or ""
    # These families have genuinely different supply pins by package.
    # Never extrapolate a DBV/D table into SC70/TSSOP from the family name.
    qualified_supply = None
    if re.match(r'^INA(?:181|240)', str(mpn or value), re.I):
        import cec_device_power_roles as roles
        manufacturer = roles.contract(value, mpn=mpn, footprint=footprint)
        if manufacturer is None:
            raise ValueError('selected_measurement_package_required_for_bypass')
        supplies = [pin for pin, role in manufacturer['pins'].items() if role == 'power_input']
        if len(supplies) != 1:
            raise ValueError('unambiguous_measurement_supply_pin_required')
        qualified_supply = supplies[0]
    for token, pin, kind, source in FIXED_DEVICE_RULES:
        if token in value:
            yield qualified_supply or pin, kind, project_max_mm, source
            break

    if "ESP32-C6-MINI-1" in value or "ESP32-S3-MINI-1" in value:
        yield "3", "100n", project_max_mm, "ESP32 peripheral schematic"
    elif "ESP32-S3-WROOM-1" in value:
        yield "2", "100n", project_max_mm, "ESP32 peripheral schematic"
        yield "2", "at-least-10u", project_max_mm, \
            "ESP32-S3-WROOM-1 peripheral schematic local bulk"

    if "LP5907" in value:
        yield "1", "at-least-1u", 10.0, "LP5907"
        yield "5", "at-least-1u", 100.0, "LP5907"
    if "TLV62569" in value:
        yield "4", "at-least-10u", 2.0, "TLV62569"
    if "TLV75533" in value:
        pins = (("6", "ldo-input"), ("1", "ldo-output")) \
            if "PDRVR" in value else (("1", "ldo-input"), ("5", "ldo-output"))
        for pin, role in pins:
            yield pin, "at-least-1u", 2.0, "TLV75533:" + role
    if "TPS2121" in value:
        for pin, role in (("7", "IN1"), ("2", "IN2"), ("1", "OUT")):
            yield pin, "local-ceramic", project_max_mm, "TPS2121:" + role


def rail_to_rail_requirements_for_value(value, project_max_mm=3.5):
    """Yield local two-supply bypass contracts.

    Rows are ``(supply_pin, return_pin, kind, max_mm, source)``.  "return"
    identifies the capacitor's other terminal and does not imply ground.
    Callers resolve both actual pad net names from the fitted device, so the
    rule stays valid when projects rename their 3.3 V or 5 V domains.
    """
    value = value or ""
    for token, supply_pin, return_pin, kind, source in \
            RAIL_TO_RAIL_DEVICE_RULES:
        if token in value:
            yield supply_pin, return_pin, kind, project_max_mm, source

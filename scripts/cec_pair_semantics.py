"""Shared pair identity, independent of placement and copper generation.

Net suffixes identify candidate pairs, not their electrical role. Known
current-monitor input pin contracts take precedence over a generic _P/_N
spelling. Unknown devices remain subject to the conservative differential
policy. Electrical completion and Kelvin topology are checked separately.
"""
import re


# Existing current-monitor pin contracts used by cec_score's Kelvin/topology
# checks. Match actual device values, never board names or reference numbers.
CURRENT_INPUT_PINS = {
    "INA181": ("3", "4"),
    "INA240": ("8", "1"),
    "INA226": ("10", "9"),
    "INA228": ("10", "9"),
    "INA238": ("10", "9"),
}

# Manufacturer pin roles, not permission to join different schematic nets.
# TI INA238 SLYS025B section 4 / INA228 SLYS021A section 5:
# https://www.ti.com/lit/ds/symlink/ina238.pdf
# https://www.ti.com/lit/ds/symlink/ina228.pdf
CURRENT_AUXILIARY_INPUT_PINS = {
    "INA228": (("8", "9", "VBUS", "IN-"),),
    "INA238": (("8", "9", "VBUS", "IN-"),),
}


def current_auxiliary_input_contract(value):
    """Known auxiliary analog pins; live same-net identity still owns a strap."""
    contract=current_input_contract(value)
    return ((contract[0],CURRENT_AUXILIARY_INPUT_PINS[contract[0]])
            if contract and contract[0] in CURRENT_AUXILIARY_INPUT_PINS else None)


def current_input_contract(value, *, mpn=None, footprint=None):
    """Resolve the existing device-pin authority without geometry heuristics."""
    displayed = str(value or "")
    value = str(mpn or displayed).upper()
    device = next((name for name in CURRENT_INPUT_PINS
                   if re.match(r"^" + name + r"(?:[A-Z0-9_-]*)(?:\s|$)", value)), None)
    if device in ('INA181', 'INA240'):
        import cec_device_power_roles as roles
        manufacturer = roles.contract(displayed, mpn=mpn, footprint=footprint)
        if manufacturer is None:
            return None
        package_inputs = {'INA181 DBV': ('3', '4'), 'INA181 DCK': ('4', '5'),
                          'INA240 D': ('8', '1'), 'INA240 PW': ('2', '3')}
        pins = package_inputs.get(manufacturer['device_package'])
        return (device, pins) if pins else None
    return (device, CURRENT_INPUT_PINS[device]) if device else None


def footprint_input_contract(fp):
    """Board consumers use embedded MPN/package, not just displayed family."""
    from cec_footprint_fields import footprint_properties
    return current_input_contract(fp.GetValue(), mpn=footprint_properties(fp).get('MPN'),
        footprint=getattr(fp, 'GetFPIDAsString', lambda: '')())


def analog_input_pairs(board):
    """Return exact connected input-net witnesses for recognized devices."""
    rows = []
    for fp in getattr(board, "GetFootprints", lambda: ())():
        contract = footprint_input_contract(fp)
        if contract is None:
            continue
        device, (p_pin, n_pin) = contract
        by_pin = {}
        for pad in fp.Pads():
            if pad.GetNetname():
                by_pin.setdefault(pad.GetPadName(), set()).add(pad.GetNetname())
        p_nets, n_nets = by_pin.get(p_pin, set()), by_pin.get(n_pin, set())
        if len(p_nets) != 1 or len(n_nets) != 1 or p_nets == n_nets:
            continue
        rows.append(dict(kind="kelvin_input", p=next(iter(p_nets)),
                         n=next(iter(n_nets)), device=device,
                         ref=fp.GetReference(), pins=[p_pin, n_pin]))
    return rows


def unresolved_current_monitor_nets(board):
    """Hold ambiguous monitor-package nets, without inventing a pin table.

    Absence of a qualified SOIC/TSSOP (or DBV/DCK) identity cannot make the
    family's anonymously named inputs ordinary. Conservatively holding all
    supplied terminals is NOT pairing them, rating them, or assuming that a
    particular package pinout is correct. Contradictory metadata still raises
    through the existing authoritative decoder.
    """
    result=set()
    from cec_footprint_fields import footprint_properties
    for fp in board.GetFootprints():
        values=(str(fp.GetValue() or '').upper(),str(footprint_properties(fp).get('MPN') or '').upper())
        if not any(re.match(r'^'+name+r'(?:[A-Z0-9_-]*)(?:\s|$)',value)
                for name in CURRENT_INPUT_PINS for value in values):continue
        if footprint_input_contract(fp) is None:
            result.update(str(p.GetNetname()) for p in fp.Pads() if p.GetNetname())
    return result


def split_termination_midpoints(board):
    """Recognize only an exact passive CAN split-termination junction.

    This is connectivity ownership, not resistor/capacitor qualification or
    permission to route either pair member as an ordinary signal. A midpoint
    must have exactly two fitted two-land resistors, one to each live CAN
    member, and one fitted shunt capacitor to ground. No active terminal,
    extra tap, guessed net suffix, reference designator or pose is accepted.
    The source values identify the nominal 120-ohm termination topology;
    voltage, fault, EMC and component tolerances remain separate checks.
    """
    import math
    import pcbnew
    from cec_device_bypass import capacitance_f
    from cec_footprint_fields import footprint_properties
    footprints = list(board.GetFootprints())
    pads = [p for fp in footprints for p in fp.Pads() if p.GetNetCode() > 0]
    if len(footprints) > 4096 or len(pads) > 16384:
        raise ValueError('split_termination_native_inventory_bound')
    by_net = {}
    for pad in pads:
        by_net.setdefault(str(pad.GetNetname()), []).append(pad)
    result = {}
    pair_members = {n for _kind, p, q in coupled_pair_names(board) for n in (p, q)}
    can = [(p, q) for kind, p, q in coupled_pair_names(board) if kind == 'can']
    for net, terminals in sorted(by_net.items()):
        if net in pair_members or len(terminals) != 3:
            continue
        resistors, capacitors = [], []
        for pad in terminals:
            fp = pad.GetParentFootprint()
            lands = list(fp.Pads())
            props = footprint_properties(fp)
            if (fp.IsDNP() or not props.get('MPN') or len(lands) != 2
                    or len({str(p.GetNumber()) for p in lands}) != 2
                    or any(p.HasHole() or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                        or p.GetNetCode() <= 0 for p in lands)):
                break
            other = next(p for p in lands if p.m_Uuid.AsString() != pad.m_Uuid.AsString())
            if other.GetNetCode() == pad.GetNetCode():
                break
            package = str(fp.GetFPIDAsString())
            if re.search(r'(?:^|:)R_\d{4}_\d{4}Metric(?:_|$)', package):
                value = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:[rR]|Ω|[oO][hH][mM][sS]?)?',
                    str(fp.GetValue()).strip())
                if not value or not 40. <= float(value[1]) <= 80.:
                    break
                resistors.append((str(other.GetNetname()), float(value[1]),
                    str(pad.m_Uuid.AsString())))
            elif re.search(r'(?:^|:)C_\d{4}_\d{4}Metric(?:_|$)', package):
                value = capacitance_f(fp.GetValue())
                if (value is None or not math.isfinite(value) or not 10e-12 <= value <= 1e-6
                        or not (other.GetNetname() == 'GND' or other.GetNetname().endswith('/GND'))):
                    break
                capacitors.append(str(pad.m_Uuid.AsString()))
            else:
                break
        else:
            if len(resistors) != 2 or len(capacitors) != 1:
                continue
            values = [r[1] for r in resistors]
            matches = [(p, q) for p, q in can if {p, q} == {r[0] for r in resistors}]
            if (len(matches) != 1 or not 108. <= sum(values) <= 132.
                    or abs(values[0]-values[1]) > max(values)*.02):
                continue
            result[net] = dict(pair_members=list(matches[0]),
                terminal_pad_uuids=sorted(str(p.m_Uuid.AsString()) for p in terminals),
                resistor_nominal_ohms=values, shunt_capacitor_pad_uuid=capacitors[0],
                scope='source_passive_split_termination_connectivity_only',
                pair_member_scalar_permission=False, electrical_or_release_qualified=False)
    return result


def conventional_pair_names(names, extra_diff_pairs=()):
    """Pure candidate names, with exact hierarchy and series suffix intact.

    A repeated leaf in another sheet is not ambiguous if its mate is in the
    same sheet. This grants neither electrical pairing nor clearance/current
    exemptions. Board consumers must still apply the native device contracts.
    """
    names = {name for name in names if name}
    result, seen = [], set()

    def add(kind, p, n):
        key = frozenset((p, n))
        if p == n or p not in names or n not in names or key in seen:
            return
        seen.add(key)
        result.append((kind, p, n))

    for p, n in sorted(set(extra_diff_pairs) | {
            (name, name[:-2] + "_N") for name in names if name.endswith("_P")}):
        leaf = p.rsplit("/", 1)[-1].upper()
        kind = "usb" if "USB" in leaf else ("can" if "CAN" in leaf else "diff")
        add(kind, p, n)
    for p in sorted(names):
        leaf = p.rsplit("/", 1)[-1]
        prefix = p[:-len(leaf)]
        if leaf == "CAN_H" or leaf.startswith("CAN_H_"):
            add("can", p, prefix + "CAN_L" + leaf[len("CAN_H"):])
        for pos, neg in (("USB_DP", "USB_DM"), ("USB_D+", "USB_D-")):
            if leaf == pos or leaf.startswith(pos + "_"):
                add("usb", p, prefix + neg + leaf[len(pos):])
    return result


def coupled_pair_names(board, extra_diff_pairs=()):
    """Return actual candidate pairs after the existing device-pin exclusion.

    Conventional names alone cannot turn known current-monitor inputs into
    high-speed differential pairs; electrical completion remains independent.
    """
    names = {net.GetNetname() for net in board.GetNetInfo().NetsByNetcode().values()
             if net.GetNetname()}
    analog = {frozenset((row["p"], row["n"])) for row in analog_input_pairs(board)}
    return [row for row in conventional_pair_names(names, extra_diff_pairs)
            if frozenset(row[1:]) not in analog]

"""Read-only, board-independent constant-power reservoir screening.

This does not qualify a capacitor, converter, or assembled product. ESR and
leakage must be supplied with their applicable frequency/temperature evidence.
The leakage branch is across the ideal capacitor; ESR carries converter input
current. Conversion losses are included in input_power_w by the caller.
"""
from __future__ import annotations

import math


def check_bank(inventory, pins, *, references, positive_net, negative_net,
               capacitance, same_net, expected_each_f,
               expected_properties, expected_footprint):
    """Check an explicitly declared parallel reservoir, not similarly named C's.

    Component selections and pin nets belong to the caller's circuit contract.
    Do not count absent/DNP parts or energy upstream of the isolation element.
    This is source consistency, not an electrical/thermal qualification.
    """
    if (not references or len(set(references)) != len(references)
            or not math.isfinite(expected_each_f) or expected_each_f <= 0
            or same_net(positive_net, negative_net)):
        raise ValueError("unique bank members and distinct rails required")
    issues = []
    total = 0.
    for ref in references:
        rec = inventory.get(ref) or {}
        reasons = []
        if not rec.get("on_board") or rec.get("dnp") or not rec.get("in_bom"):
            reasons.append("reservoir member absent, DNP or excluded from BOM")
        try:
            value = capacitance(rec.get("value", ""))
        except (ValueError, TypeError):
            value = None
        if not math.isclose(value or 0., expected_each_f, rel_tol=1e-9):
            reasons.append("reservoir capacitance differs from declared bank")
        if rec.get("footprint") != expected_footprint:
            reasons.append("reservoir land pattern differs from declared package")
        for key, expected in expected_properties.items():
            if rec.get("props", {}).get(key) != expected:
                reasons.append(f"reservoir {key} must be {expected}")
        for pin, net in (("1", positive_net), ("2", negative_net)):
            if not same_net((pins.get(ref) or {}).get(pin), net):
                reasons.append(f"reservoir pin {pin} must connect to {net}")
        issues.extend(dict(ref=ref, reason=reason) for reason in reasons)
        if not reasons:
            total += value
    return dict(ok=not issues, issues=issues, nominal_f=total,
                fabrication_qualified=False)


def ramp_screen(*, capacitance_max_f, slew_v_per_s, load_a,
                leakage_a, current_limit_a):
    """C*dV/dt plus declared load/leakage; never invent source-load headroom."""
    values = (capacitance_max_f, slew_v_per_s, load_a, leakage_a, current_limit_a)
    if (not all(math.isfinite(v) for v in values)
            or min(capacitance_max_f, slew_v_per_s, current_limit_a) <= 0
            or min(load_a, leakage_a) < 0):
        raise ValueError("valid positive ramp/capacity and nonnegative loads required")
    charging = capacitance_max_f * slew_v_per_s
    total = charging + load_a + leakage_a
    return dict(charging_a=charging, total_a=total,
                margin_a=current_limit_a-total, ok=total<=current_limit_a,
                fabrication_qualified=False)


def discharge_ms(*, capacitance_f: float, start_v: float, floor_v: float,
                 input_power_w: float, esr_ohm: float = 0.0,
                 leakage_a: float = 0.0, intervals: int = 4096) -> float:
    """Integrate C dVc/dt = -(P/Vterminal + Ileak), with Vc=Vterminal+R*P/Vterminal.

    The stable constant-power operating branch must extend down to floor_v.
    Composite Simpson integration is over ideal capacitor voltage, not time.
    Returned time is from source loss, before subtracting detection/ISR latency.
    """
    values = (capacitance_f, start_v, floor_v, input_power_w, esr_ohm, leakage_a)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("All electrical inputs must be finite")
    if min(capacitance_f, start_v, floor_v, input_power_w) <= 0:
        raise ValueError("Capacitance, voltages, and power must be positive")
    if min(esr_ohm, leakage_a) < 0:
        raise ValueError("ESR and leakage cannot be negative")
    if not isinstance(intervals, int) or intervals < 2 or intervals % 2:
        raise ValueError("Use a positive even integration interval count")
    if floor_v <= math.sqrt(esr_ohm * input_power_w):
        raise ValueError("Cutoff is outside the stable constant-power branch")
    stop_cap_v = floor_v + esr_ohm * input_power_w / floor_v
    if start_v <= stop_cap_v:
        return 0.0

    def integrand(cap_v: float) -> float:
        terminal_v = (cap_v + math.sqrt(
            cap_v * cap_v - 4 * esr_ohm * input_power_w)) / 2
        return capacitance_f / (input_power_w / terminal_v + leakage_a)

    step = (start_v - stop_cap_v) / intervals
    total = integrand(stop_cap_v) + integrand(start_v)
    total += sum((4 if i % 2 else 2) * integrand(stop_cap_v + i * step)
                 for i in range(1, intervals))
    return total * step / 3 * 1000


def tolerance_aged_capacitance(*, nominal_f: float, initial_loss: float,
                             endurance_loss: float) -> float:
    """Endurance change is relative to initial measured capacitance, not nominal."""
    if not math.isfinite(nominal_f) or nominal_f <= 0:
        raise ValueError("Nominal capacitance must be positive and finite")
    if not all(math.isfinite(x) and 0 <= x < 1
               for x in (initial_loss, endurance_loss)):
        raise ValueError("Loss fractions must be in [0, 1)")
    return nominal_f * (1 - initial_loss) * (1 - endurance_loss)

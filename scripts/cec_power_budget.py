#!/usr/bin/env python3
"""Auditable worst-case +3V3 budgets for the two current BETA boards.

Every entry maps to a fitted schematic consumer or a deliberately conservative
controller envelope.  Values are wired-mode maxima; BETA firmware has wireless
disabled by owner decision.  The system design margin is applied once, after
the complete component subtotal.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass


DESIGN_MARGIN = 0.20


@dataclass(frozen=True)
class Load:
    name: str
    quantity: int
    each_mA: float
    basis: str

    @property
    def total_mA(self) -> float:
        return self.quantity * self.each_mA


LOADS: dict[str, tuple[Load, ...]] = {
    "12vhpwr-standard": (
        Load("ESP32-S3-MINI wired controller envelope", 1, 160.000,
             "107.9mA modem-sleep/all clocks + 10mA flash, rounded up"),
        Load("INA240 current-sense amplifier", 6, 2.400,
             "datasheet maximum quiescent current"),
        Load("TJA1051 VIO", 1, 0.500, "datasheet dominant-state maximum"),
        Load("REF3030 reference", 1, 0.059, "datasheet maximum quiescent current"),
        Load("RESET and BOOT pull-ups, both asserted", 2, 0.330, "3.3V / 10k"),
        Load("fan gate and tach pull-ups, both low", 2, 0.330, "3.3V / 10k"),
        Load("temperature-divider upper bounds", 2, 0.330, "3.3V / 10k"),
    ),
    "hub-standard-rev2": (
        Load("ESP32-S3-WROOM wired controller envelope", 1, 160.000,
             "107.9mA modem-sleep/all clocks + 10mA flash, rounded up"),
        Load("TJA1051 VIO", 1, 0.500, "datasheet dominant-state maximum"),
        Load("TPS3839 supervisor", 1, 0.0005, "datasheet maximum quiescent current"),
        Load("TLV7011 comparator", 1, 0.010, "datasheet maximum quiescent current"),
        Load("four DETECT pull-ups, all low", 4, 0.330, "3.3V / 10k"),
        Load("RESET and BOOT pull-ups, both asserted", 2, 0.330, "3.3V / 10k"),
        Load("temperature-divider upper bound", 1, 0.330, "3.3V / 10k"),
        Load("HUB_3V3 sense divider", 1, 3.3 / 57_000 * 1e3, "3.3V / (47k+10k)"),
        Load("comparator threshold divider", 1, 3.3 / 21_000 * 1e3, "3.3V / (11k+10k)"),
        Load("comparator hysteresis path", 1, 3.3 / 1_000_000 * 1e3, "3.3V / 1M"),
        Load("buck feedback divider", 1, 3.3 / 553_000 * 1e3, "3.3V / (453k+100k)"),
    ),
}


def budget(board: str) -> dict:
    rows = LOADS[board]
    subtotal_mA = sum(row.total_mA for row in rows)
    required_mA = subtotal_mA * (1.0 + DESIGN_MARGIN)
    return {
        "board": board,
        "loads": [{**asdict(row), "total_mA": row.total_mA} for row in rows],
        "subtotal_mA": subtotal_mA,
        "design_margin_fraction": DESIGN_MARGIN,
        "design_margin_mA": subtotal_mA * DESIGN_MARGIN,
        "required_mA": required_mA,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", choices=sorted(LOADS), nargs="*")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = [budget(board) for board in (args.board or sorted(LOADS))]
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for result in results:
            print(result["board"])
            for row in result["loads"]:
                print(f"  {row['name']}: {row['quantity']} x {row['each_mA']:.6g} = "
                      f"{row['total_mA']:.6g} mA")
            print(f"  subtotal: {result['subtotal_mA']:.6f} mA")
            print(f"  +20% margin: {result['required_mA']:.6f} mA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

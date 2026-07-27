#!/usr/bin/env python3
"""Consolidate a wave chain's audit lines into a per-board trend.

A chain emits one audit line per winner per round; read individually they say
nothing about whether a fix HOLDS ACROSS SEEDS, which is the only question a
multi-round chain exists to answer. This groups them by board and shows the
per-metric range, so a single lucky placement cannot read as a fixed pipeline.

Usage: python3 scripts/cec_wave_trend.py build/waves-final.log
"""
import collections
import re
import sys

ROW = re.compile(
    r"^(?P<f>\S+\.kicad_pcb)\s+incursion\(p/t/v\)=(?P<p>\d+)/(?P<t>\d+)/(?P<v>\d+)\s+"
    r"diagonal=(?P<d>\d+)\s+via_rows=(?P<vr>\d+).*?stray_vias=(?P<sv>\d+)\s+"
    r"gap_intrusions=(?P<gi>\d+)\s+dead=(?P<dz>\d+)")

BOARDS = ("eps-8pin", "pcie-8pin-2port", "pcie-8pin-3port",
          "12vhpwr-standard", "atx-24pin-rev3")


def board_of(line, current):
    m = re.search(r"=====\s+(\S+)\s+round", line)
    return m.group(1) if m else current


def main(path):
    rows = collections.defaultdict(list)
    cur = "?"
    for line in open(path, errors="replace"):
        cur = board_of(line, cur)
        m = ROW.match(line.strip())
        if m:
            rows[cur].append({k: int(m.group(k))
                              for k in ("p", "t", "v", "d", "vr", "sv", "gi", "dz")})
    if not rows:
        print("no audit rows yet")
        return 0
    hdr = ("board", "n", "pads", "tracks", "vias", "diag", "stray", "gap", "dead")
    print("%-18s %-3s %-11s %-11s %-11s %-7s %-7s %-5s %s" % hdr)
    for b in list(BOARDS) + [k for k in rows if k not in BOARDS]:
        rs = rows.get(b)
        if not rs:
            continue

        def rng(k):
            vs = [r[k] for r in rs]
            return "%d" % vs[0] if len(set(vs)) == 1 else "%d-%d" % (min(vs), max(vs))

        print("%-18s %-3d %-11s %-11s %-11s %-7s %-7s %-5s %s"
              % (b[:18], len(rs), rng("p"), rng("t"), rng("v"), rng("d"),
                 rng("sv"), rng("gi"), rng("dz")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "build/waves-final.log"))

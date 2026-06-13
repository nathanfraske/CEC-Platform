#!/usr/bin/env python3
"""cec_capture_analyze.py -- per-module analysis of CEC bench captures.

Turns a ``===BURST_CSV===`` dump (from ``fastburst`` / ``autoburst`` / ``stream``)
into the standard plot battery + a metrics summary, *per module* -- because each
module asks a different question:

  * 12vhpwr : per-PIN current imbalance (the melt metric) + transients + droop
  * atx-24pin (stub) : per-RAIL power + energy (INA228 accumulators)
  * eps / pcie (stub) : per-CABLE balance + total power + transient events

Design rules:
  * The time/frequency axis is derived from the capture's MEASURED sample rate
    (the ``# ... us = idx x N us`` header stamp), never a nominal label. If the
    capture says NOMINAL, every frequency is flagged suspect (see ``rate`` cmd).
  * Profiles are pluggable (a module -> a Profile); this is the seed of the
    Concierge (spec Appendix C) per-module analysis stage.

Usage:
  python3 cec_capture_analyze.py CAPTURE.csv|putty.log [--module 12vhpwr]
        [--rate HZ] [--out DIR] [--index N] [--analog-rc-hz 15900 --analog-adc-hz 14000]

CAPTURE may be a single capture file (one block) or a serial log (many blocks);
every ``===BURST_CSV===`` block found is analyzed. Outputs PNGs + a metrics.md/.json
per block into --out (default: <input>.analysis/).
License: Apache-2.0 (CEC-Platform)
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------------
# Capture parsing
# ----------------------------------------------------------------------------
class Capture:
    """One ===BURST_CSV=== block: metadata + columnar data."""

    def __init__(self, kind, rate_hz, rate_measured, columns, data, meta_line):
        self.kind = kind                  # fastburst | autoburst | stream | burst | unknown
        self.rate_hz = rate_hz            # native sample rate (Hz)
        self.rate_measured = rate_measured
        self.columns = columns            # ordered column labels (incl. us, seq/drop)
        self.data = data                  # {label: np.ndarray}
        self.meta = meta_line             # the raw "# ..." line
        self.n = len(next(iter(data.values()))) if data else 0

    @property
    def uniform(self):
        # fastburst/autoburst are FPGA-paced uniform; ESP-paced `burst` is not.
        return self.kind in ("fastburst", "autoburst")

    def signal_columns(self):
        """Data columns that are signals (exclude the index/seq/drop columns)."""
        return [c for c in self.columns if c not in ("us", "seq", "drop")]


_RATE_USPER = re.compile(r"us\s*=\s*idx\s*x\s*([0-9.]+)")      # "us = idx x 5.000 us"
_RATE_KSPS = re.compile(r"@\s*~?([0-9.]+)\s*kSPS")            # "@ 100.50 kSPS native"
_RATE_KHZ = re.compile(r"@\s*~?([0-9.]+)\s*kHz")             # legacy "@ ~200 kHz native"


def _parse_rate(meta, kind):
    """(rate_hz, measured) from a '# ...' metadata line. us-per-sample wins."""
    measured = ("(measured)" in meta) and ("NOMINAL" not in meta and "nominal" not in meta)
    m = _RATE_USPER.search(meta)
    if m:
        us = float(m.group(1))
        if us > 0:
            return 1.0e6 / us, measured
    for rx in (_RATE_KSPS, _RATE_KHZ):
        m = rx.search(meta)
        if m:
            return float(m.group(1)) * 1000.0, measured
    return None, measured


def parse_captures(text):
    """Yield Capture objects for every ===BURST_CSV=== block in `text`."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "===BURST_CSV_BEGIN===" not in lines[i]:
            i += 1
            continue
        i += 1
        meta = ""
        cols = None
        rows = []
        while i < len(lines) and "===BURST_CSV_END===" not in lines[i]:
            ln = lines[i].strip()
            i += 1
            if not ln:
                continue
            if ln.startswith("#"):
                meta = ln
                continue
            if cols is None and not ln[0].isdigit() and ln[0] not in "+-.":
                cols = [c.strip() for c in ln.split(",")]
                continue
            parts = ln.split(",")
            if cols and len(parts) == len(cols):
                try:
                    rows.append([float(p) for p in parts])   # PuTTY may mangle a row; skip it
                except ValueError:
                    continue
        if cols and rows:
            arr = np.array(rows, dtype=float)
            data = {c: arr[:, j] for j, c in enumerate(cols)}
            kind = meta.split(":", 1)[0].lstrip("# ").split()[0] if meta else "unknown"
            rate, measured = _parse_rate(meta, kind)
            yield Capture(kind, rate, measured, cols, data, meta)


# ----------------------------------------------------------------------------
# Spectral helpers (match the bench charts: Blackman-Harris, dBc)
# ----------------------------------------------------------------------------
def blackman_harris(n):
    a = (0.35875, 0.48829, 0.14128, 0.01168)
    k = np.arange(n)
    w = (a[0] - a[1] * np.cos(2 * np.pi * k / (n - 1))
              + a[2] * np.cos(4 * np.pi * k / (n - 1))
              - a[3] * np.cos(6 * np.pi * k / (n - 1)))
    return w


def fft_dbc(x, rate_hz):
    """One-sided spectrum in dBc (relative to the largest non-DC bin)."""
    x = np.asarray(x, float)
    x = x - x.mean()
    w = blackman_harris(len(x))
    X = np.abs(np.fft.rfft(x * w))
    f = np.fft.rfftfreq(len(x), 1.0 / rate_hz)
    if len(X) > 2 and X[1:].max() > 0:
        ref = X[1:].max()
    else:
        ref = X.max() if X.max() > 0 else 1.0
    db = 20.0 * np.log10(np.maximum(X, ref * 1e-9) / ref)
    return f, db


def analog_ceiling_db(f, rc_hz, adc_hz):
    """Two cascaded 1st-order low-passes (perfboard RC x AD7606), in dB."""
    h = 1.0 / np.sqrt(1 + (f / rc_hz) ** 2) / np.sqrt(1 + (f / adc_hz) ** 2)
    return 20.0 * np.log10(np.maximum(h, 1e-9))


# ----------------------------------------------------------------------------
# Per-module profiles
# ----------------------------------------------------------------------------
class Profile:
    name = "base"

    def classify(self, cap):
        raise NotImplementedError

    def metrics(self, cap):
        raise NotImplementedError

    def plots(self, cap, stem, out, args):
        raise NotImplementedError


class Profile12VHPWR(Profile):
    """per-PIN current imbalance (melt risk) + transients + rail droop."""
    name = "12vhpwr"
    IMBALANCE_FLAG_PCT = 20.0   # spread/mean above this -> flag (tune to spec)
    MIN_LOAD_A = 1.0            # below this the pins are idle -> imbalance undefined

    def classify(self, cap):
        sig = cap.signal_columns()
        currents = [c for c in sig if re.fullmatch(r"i\d+", c)]
        rails = [c for c in sig if c.startswith("v")]   # vrail
        return currents, rails

    def metrics(self, cap):
        currents, rails = self.classify(cap)
        m = {"module": self.name, "kind": cap.kind, "n": cap.n,
             "rate_hz": cap.rate_hz, "rate_measured": cap.rate_measured,
             "sensed_pins": currents}
        if not currents:
            m["error"] = "no current channels (i#) found"
            return m

        I = np.vstack([cap.data[c] for c in currents])     # pins x samples
        pin_mean = I.mean(axis=1)
        pin_peak = I.max(axis=1)
        per_pin = {}
        for k, c in enumerate(currents):
            per_pin[c] = {"mean_A": float(pin_mean[k]), "peak_A": float(pin_peak[k]),
                          "min_A": float(I[k].min()), "rms_A": float(np.sqrt((I[k] ** 2).mean()))}
        m["per_pin"] = per_pin

        # IMBALANCE -- the headline metric. Across-pin spread vs the mean pin.
        # Only defined UNDER LOAD: at idle the mean pin current is ~0 (and is
        # dominated by uncalibrated INA offsets -- run `cal`), so spread/mean
        # blows up meaninglessly. Guard on a minimum load.
        mean_of_means = float(pin_mean.mean())
        spread = float(pin_mean.max() - pin_mean.min())
        worst = currents[int(np.argmax(pin_mean))]
        inst_spread = float((I.max(axis=0) - I.min(axis=0)).max())   # worst instantaneous
        loaded = abs(mean_of_means) >= self.MIN_LOAD_A
        imb_pct = (spread / abs(mean_of_means) * 100.0) if loaded else None
        m["imbalance"] = {
            "load_state": "loaded" if loaded else "no_load (idle/uncal -- run under load)",
            "mean_pin_A": mean_of_means, "spread_A": spread, "worst_pin": worst,
            "worst_instantaneous_spread_A": inst_spread,
            "imbalance_pct": imb_pct,
            "worst_pin_excess_pct": (float((pin_mean.max() - mean_of_means) / abs(mean_of_means) * 100.0)
                                     if loaded else None),
            "FLAG": bool(loaded and imb_pct is not None and imb_pct > self.IMBALANCE_FLAG_PCT),
        }

        total = I.sum(axis=0)
        m["total"] = {"mean_A": float(total.mean()), "peak_A": float(total.max()),
                      "min_A": float(total.min())}

        if rails:
            v = cap.data[rails[0]]
            m["rail"] = {"name": rails[0], "mean_V": float(v.mean()),
                         "min_V": float(v.min()), "max_V": float(v.max()),
                         "droop_mV": float((v.mean() - v.min()) * 1000.0),
                         "ripple_pkpk_mV": float((v.max() - v.min()) * 1000.0)}

        # spectral: fundamental of the total current (the load cadence)
        if cap.uniform and cap.rate_hz and cap.n > 16:
            f, db = fft_dbc(total, cap.rate_hz)
            band = (f > 50)                      # ignore DC/very-low
            if band.any():
                pk = int(np.argmax(db[band]))
                m["spectral"] = {"load_fundamental_Hz": float(f[band][pk]),
                                 "noise_floor_dBc": float(np.median(db[f > cap.rate_hz * 0.35])),
                                 "rate_caveat": None if cap.rate_measured else
                                 "rate is NOMINAL -- frequencies may be ~2x off; run `rate`"}
        return m

    def plots(self, cap, stem, out, args):
        currents, rails = self.classify(cap)
        files = []
        t_ms = np.arange(cap.n) * (1.0e3 / cap.rate_hz) if cap.rate_hz else np.arange(cap.n)
        ratetag = "measured" if cap.rate_measured else "NOMINAL(2x?)"

        # --- time-domain: per-pin + sum + rail ---
        nrow = 2 + (1 if rails else 0)
        fig, ax = plt.subplots(nrow, 1, figsize=(11, 7), sharex=True)
        if rails:
            I = np.vstack([cap.data[c] for c in currents])
            for c in currents:
                ax[0].plot(t_ms, cap.data[c], lw=0.8, label=c)
            ax[0].set_ylabel("per-pin current (A)"); ax[0].legend(ncol=len(currents), fontsize=8)
            ax[1].plot(t_ms, I.sum(axis=0), lw=0.8, color="tab:blue", label="sum of sensed pins")
            ax[1].set_ylabel("total (A)"); ax[1].legend(fontsize=8)
            ax[2].plot(t_ms, cap.data[rails[0]], lw=0.8, color="tab:red", label=rails[0])
            ax[2].set_ylabel("rail (V)"); ax[2].legend(fontsize=8)
            ax[-1].set_xlabel("time (ms)")
        else:
            for c in currents:
                ax[0].plot(t_ms, cap.data[c], lw=0.8, label=c)
            ax[0].set_ylabel("per-pin current (A)"); ax[0].legend(fontsize=8)
        fig.suptitle(f"12VHPWR per-pin -- {cap.kind}, {cap.n} frames @ "
                     f"{cap.rate_hz/1000:.1f} kSPS [{ratetag}]")
        fig.tight_layout()
        p = os.path.join(out, f"{stem}-time.png"); fig.savefig(p, dpi=110); plt.close(fig)
        files.append(p)

        # --- FFT with the analog-ceiling overlay ---
        if cap.uniform and cap.rate_hz and cap.n > 16:
            total = np.vstack([cap.data[c] for c in currents]).sum(axis=0)
            f, db = fft_dbc(total, cap.rate_hz)
            fig, a2 = plt.subplots(figsize=(11, 5))
            a2.semilogx(f[1:], db[1:], lw=0.7, color="tab:blue", label="sum current")
            if rails:
                fr, dbr = fft_dbc(cap.data[rails[0]], cap.rate_hz)
                a2.semilogx(fr[1:], dbr[1:], lw=0.6, color="tab:red", alpha=0.7, label=rails[0])
            a2.semilogx(f[1:], analog_ceiling_db(f[1:], args.analog_rc_hz, args.analog_adc_hz),
                        "g--", lw=1.2, label=f"analog ceiling ({args.analog_rc_hz/1000:.1f}k x "
                                             f"{args.analog_adc_hz/1000:.0f}k)")
            a2.set_ylim(-90, 5); a2.set_xlabel("frequency (Hz)"); a2.set_ylabel("magnitude (dBc)")
            a2.set_title(f"FFT @ {cap.rate_hz/1000:.1f} kSPS [{ratetag}] -- "
                         + ("axes honest" if cap.rate_measured else "AXES ~2x SUSPECT, run `rate`"))
            a2.grid(True, which="both", alpha=0.3); a2.legend(fontsize=8)
            fig.tight_layout()
            p = os.path.join(out, f"{stem}-fft.png"); fig.savefig(p, dpi=110); plt.close(fig)
            files.append(p)
        return files


class _Stub(Profile):
    def __init__(self, name, what):
        self.name = name; self._what = what
    def classify(self, cap): return [], []
    def metrics(self, cap):
        return {"module": self.name, "error": f"profile not implemented yet -- would compute: {self._what}"}
    def plots(self, cap, stem, out, args): return []


PROFILES = {
    "12vhpwr": Profile12VHPWR(),
    "atx-24pin": _Stub("atx-24pin", "per-rail power + energy (INA228 accumulators), rail stability"),
    "eps": _Stub("eps", "per-cable balance + total power + §6.13 transient events"),
    "pcie": _Stub("pcie", "per-cable balance + total power + §6.13 transient events"),
}


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------
def write_metrics(m, stem, out):
    jp = os.path.join(out, f"{stem}-metrics.json")
    with open(jp, "w") as f:
        json.dump(m, f, indent=2)
    mp = os.path.join(out, f"{stem}-metrics.md")
    with open(mp, "w") as f:
        f.write(f"# {stem}  ({m.get('module','?')} / {m.get('kind','?')})\n\n")
        if "error" in m:
            f.write(f"**{m['error']}**\n"); return [jp, mp]
        f.write(f"- samples: {m['n']} @ {m['rate_hz']/1000:.2f} kSPS "
                f"({'measured' if m['rate_measured'] else 'NOMINAL -- run `rate`, axes ~2x suspect'})\n")
        if "imbalance" in m:
            im = m["imbalance"]
            flag = "  **<-- FLAG: over the imbalance limit**" if im["FLAG"] else ""
            f.write(f"\n## Imbalance (the melt metric){flag}\n")
            if im["imbalance_pct"] is None:
                f.write(f"- **{im['load_state']}** -- mean pin {im['mean_pin_A']:.3f} A "
                        f"(below load threshold; capture under GPU load for a meaningful number)\n")
            else:
                f.write(f"- mean pin: {im['mean_pin_A']:.3f} A; spread: {im['spread_A']:.3f} A; "
                        f"**imbalance {im['imbalance_pct']:.1f}%**\n")
                f.write(f"- worst pin: {im['worst_pin']} (+{im['worst_pin_excess_pct']:.1f}% over mean); "
                        f"worst instantaneous spread {im['worst_instantaneous_spread_A']:.3f} A\n")
        if "total" in m:
            f.write(f"\n## Total\n- mean {m['total']['mean_A']:.2f} A, peak {m['total']['peak_A']:.2f} A\n")
        if "rail" in m:
            r = m["rail"]
            f.write(f"\n## Rail ({r['name']})\n- {r['mean_V']:.3f} V mean, droop {r['droop_mV']:.1f} mV, "
                    f"ripple {r['ripple_pkpk_mV']:.1f} mVpp\n")
        if "spectral" in m:
            s = m["spectral"]
            f.write(f"\n## Spectral\n- load fundamental {s['load_fundamental_Hz']:.0f} Hz, "
                    f"floor {s['noise_floor_dBc']:.0f} dBc\n")
            if s.get("rate_caveat"):
                f.write(f"- **{s['rate_caveat']}**\n")
        if "per_pin" in m:
            f.write("\n## Per-pin\n| pin | mean A | peak A | rms A |\n|---|---|---|---|\n")
            for c, d in m["per_pin"].items():
                f.write(f"| {c} | {d['mean_A']:.3f} | {d['peak_A']:.3f} | {d['rms_A']:.3f} |\n")
    return [jp, mp]


def main():
    ap = argparse.ArgumentParser(description="Analyze a CEC bench capture (per module).")
    ap.add_argument("input", help="capture file or serial log (one or more ===BURST_CSV=== blocks)")
    ap.add_argument("--module", default="12vhpwr", choices=sorted(PROFILES))
    ap.add_argument("--rate", type=float, default=None, help="override sample rate (Hz)")
    ap.add_argument("--index", type=int, default=None, help="analyze only the Nth block (0-based)")
    ap.add_argument("--out", default=None, help="output dir (default <input>.analysis)")
    ap.add_argument("--analog-rc-hz", type=float, default=15900.0)
    ap.add_argument("--analog-adc-hz", type=float, default=14000.0)
    args = ap.parse_args()

    with open(args.input) as f:
        text = f.read()
    caps = list(parse_captures(text))
    if not caps:
        print("no ===BURST_CSV=== blocks found", file=sys.stderr); sys.exit(2)

    out = args.out or (os.path.splitext(args.input)[0] + ".analysis")
    os.makedirs(out, exist_ok=True)
    prof = PROFILES[args.module]
    base = os.path.splitext(os.path.basename(args.input))[0]

    flagged = 0
    for bi, cap in enumerate(caps):
        if args.index is not None and bi != args.index:
            continue
        if args.rate:
            cap.rate_hz, cap.rate_measured = args.rate, True
        if not cap.rate_hz:
            cap.rate_hz, cap.rate_measured = 100000.0, False   # last-ditch; flagged
        stem = f"{base}-{bi:02d}-{cap.kind}"
        m = prof.metrics(cap)
        files = prof.plots(cap, stem, out, args)
        files += write_metrics(m, stem, out)
        flag = m.get("imbalance", {}).get("FLAG")
        flagged += 1 if flag else 0
        tag = "" if cap.rate_measured else "  [RATE NOMINAL -- run `rate`]"
        if "imbalance" in m and m["imbalance"]["imbalance_pct"] is not None:
            imbtag = f"  IMBALANCE {m['imbalance']['imbalance_pct']:.1f}%" + (" FLAG" if flag else "")
        elif "imbalance" in m:
            imbtag = "  (no load -- imbalance N/A)"
        else:
            imbtag = ""
        print(f"[{bi}] {cap.kind} {cap.n} frames @ {cap.rate_hz/1000:.1f} kSPS{tag}{imbtag}")
        for fp in files:
            print(f"    -> {fp}")
    if flagged:
        print(f"\n{flagged} capture(s) FLAGGED over the imbalance limit.")


if __name__ == "__main__":
    main()

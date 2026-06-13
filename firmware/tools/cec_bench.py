#!/usr/bin/env python3
"""cec_bench.py -- serial capture host for the CEC 12vhpwr proto bench.

Replaces "open PuTTY and log everything" with a tool that OWNS the serial port:
no dropped/mangled lines, scripts command sequences, and auto-organizes every
capture into its own file + a run manifest, optionally auto-analyzing each.

It is a terminal (you still see the device output and can type commands) that
ALSO, in the background:
  * splits each ``===BURST_CSV===`` block into its own timestamped file under
    ``<run>/captures/``,
  * appends every command + capture to ``<run>/manifest.md`` (the "doc"),
  * (``--analyze``) runs cec_capture_analyze.py on each capture as it lands, so
    metrics + plots write themselves into ``<run>/analysis/``.

Keep using TelePlot for the live 5 Hz monitor; this owns the bursts + the record.
This capture->organize->analyze path is the precursor of the Concierge host
layer (spec Appendix C).

Usage:
  pip install pyserial
  python3 cec_bench.py --port COM7 --analyze              # interactive
  python3 cec_bench.py --port /dev/ttyACM0 --analyze \
        --script "cal; rate; fastburst"                   # run a setup sequence, then interactive
  # then induce transients and run `autoburst 500 5` interactively.

The scripted sequence uses quiet-detection between commands (good for the
deterministic cal/rate/fastburst/stream setup). `autoburst` waits for a transient
you induce, so run it interactively.
License: Apache-2.0 (CEC-Platform)
"""
from __future__ import annotations
import argparse
import datetime
import os
import subprocess
import sys
import threading
import time

try:
    import serial   # pyserial
except ImportError:
    sys.exit("cec_bench: pyserial is required -- `pip install pyserial`")


def tool_version():
    """A documented version: TOOL_VERSION + the repo's short git SHA (best-effort)."""
    v = "v1.0"
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=os.path.dirname(os.path.abspath(__file__)),
                             capture_output=True, text=True, timeout=5).stdout.strip()
        if sha:
            v += "+" + sha
    except Exception:
        pass
    return v


class Bench:
    def __init__(self, port, baud, run_dir, analyze, module, analyzer, show_teleplot, tp_addr):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        self.run_dir = run_dir
        self.captures_dir = os.path.join(run_dir, "captures")
        os.makedirs(self.captures_dir, exist_ok=True)
        self.analyze = analyze
        self.module = module
        self.analyzer = analyzer
        self.show_teleplot = show_teleplot
        self.tp_sock = None
        self.tp_addr = tp_addr
        if tp_addr:
            import socket
            self.tp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last_rx = time.time()
        self._buf = None
        self._cap_n = 0
        self._stop = threading.Event()
        self.version = tool_version()
        self.session_log = open(os.path.join(run_dir, "session.log"), "a", buffering=1)
        self._man = open(os.path.join(run_dir, "manifest.md"), "a", buffering=1)
        self._man.write(f"# CEC bench run `{os.path.basename(run_dir)}`\n\n"
                        f"- tooling: cec_bench {self.version}\n"
                        f"- port {port} @ {baud}, module {module}\n"
                        f"- started {datetime.datetime.now().isoformat(timespec='seconds')}\n\n"
                        f"| time | event | detail |\n|---|---|---|\n")

    def _manifest(self, event, detail):
        self._man.write(f"| {datetime.datetime.now().strftime('%H:%M:%S')} | {event} | {detail} |\n")

    # ---- background reader: terminal passthrough + capture extraction ----
    def reader(self):
        while not self._stop.is_set():
            try:
                raw = self.ser.readline()
            except Exception:
                break
            if not raw:
                continue
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            self.session_log.write(line + "\n")
            if line.startswith(">"):              # teleplot: keep it OFF the terminal so you can
                if self.tp_sock:                  #   type + read command output; forward/log it.
                    try:
                        self.tp_sock.sendto(line[1:].encode(), self.tp_addr)
                    except Exception:
                        pass
                if self.show_teleplot:
                    sys.stdout.write(line + "\n"); sys.stdout.flush()
                continue                          # don't mark activity, don't treat as capture
            self.last_rx = time.time()
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            if "===BURST_CSV_BEGIN===" in line:
                self._buf = [line]
            elif self._buf is not None:
                self._buf.append(line)
                if "===BURST_CSV_END===" in line:
                    self._save_capture(self._buf)
                    self._buf = None

    def _save_capture(self, block):
        kind = "capture"
        for ln in block:
            if ln.startswith("#"):
                kind = ln.lstrip("# ").split(":", 1)[0].split()[0]
                break
        self._cap_n += 1
        name = f"{self._cap_n:03d}-{datetime.datetime.now().strftime('%H%M%S')}-{kind}.csv"
        path = os.path.join(self.captures_dir, name)
        with open(path, "w") as f:                 # version-stamp the CSV (before the block, so
            f.write(f"# cec_bench {self.version}  " #   the analyzer's parser ignores it)
                    f"{datetime.datetime.now().isoformat(timespec='seconds')}\n")
            f.write("\n".join(block) + "\n")
        self._manifest("capture", f"`{name}` ({len(block)} lines, {self.version})")
        print(f"\n[bench] saved captures/{name}")
        if self.analyze and self.analyzer:
            self._run_analyzer(path, name)

    def _run_analyzer(self, path, name):
        stem = os.path.splitext(name)[0]
        out = os.path.join(self.run_dir, "analysis", stem)   # per-capture subfolder
        try:
            r = subprocess.run([sys.executable, self.analyzer, path,
                                "--module", self.module, "--out", out],
                               capture_output=True, text=True, timeout=180)
            for ln in r.stdout.splitlines():
                print("[analyze] " + ln)
            if r.returncode != 0:
                print(f"[analyze] FAILED (rc={r.returncode}) -- "
                      f"is numpy+matplotlib installed for {os.path.basename(sys.executable)}?")
                print("[analyze] " + (r.stderr.strip() or "(no stderr)"))
            else:
                self._manifest("analyze", f"`{name}` -> `analysis/{stem}/`")
        except Exception as e:
            print(f"[bench] analyze failed to launch: {e}")

    # ---- command send + quiet-detection (for scripted sequences) ----
    def send(self, cmd):
        self.ser.write((cmd + "\r\n").encode())
        self._manifest("cmd", "`" + cmd + "`")
        self.last_rx = time.time()
        print(f"[bench] > {cmd}")

    def wait_idle(self, idle_s=1.5, timeout=60.0):
        time.sleep(0.3)                       # let the command start producing
        t0 = time.time()
        while time.time() - t0 < timeout:
            if time.time() - self.last_rx > idle_s:
                return
            time.sleep(0.1)

    def close(self):
        self._stop.set()
        time.sleep(0.3)
        try:
            self.ser.close()
        except Exception:
            pass
        if self.tp_sock:
            self.tp_sock.close()
        self.session_log.close()
        self._man.close()


def main():
    ap = argparse.ArgumentParser(description="CEC proto serial capture host.")
    ap.add_argument("--port", required=True, help="serial port (COM7, /dev/ttyACM0, ...)")
    ap.add_argument("--baud", type=int, default=115200, help="ignored on USB-CDC; any value")
    ap.add_argument("--run-dir", default=None, help="default runs/run-<timestamp>")
    ap.add_argument("--analyze", action="store_true", help="auto-run the analyzer per capture")
    ap.add_argument("--module", default="12vhpwr")
    ap.add_argument("--script", default=None, help="';'-separated commands to run first")
    ap.add_argument("--script-idle", type=float, default=1.5, help="quiet seconds = command done")
    ap.add_argument("--show-teleplot", action="store_true",
                    help="show the 5Hz teleplot '>' lines in the terminal (default: hidden so "
                         "you can type and read command output)")
    ap.add_argument("--teleplot-udp", default=None, metavar="HOST:PORT",
                    help="forward teleplot to UDP (e.g. 127.0.0.1:47269) so Teleplot can graph "
                         "live WHILE this owns the serial port")
    args = ap.parse_args()

    tp_addr = None
    if args.teleplot_udp:
        h, _, p = args.teleplot_udp.partition(":")
        tp_addr = (h or "127.0.0.1", int(p or "47269"))

    run_dir = args.run_dir or os.path.join(
        "runs", datetime.datetime.now().strftime("run-%Y%m%d-%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    analyzer = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cec_capture_analyze.py")
    if args.analyze and not os.path.exists(analyzer):
        print("[bench] analyzer not found next to this script; --analyze disabled")
        analyzer = None

    try:
        b = Bench(args.port, args.baud, run_dir, args.analyze, args.module, analyzer,
                  args.show_teleplot, tp_addr)
    except serial.SerialException as e:
        sys.exit(f"cec_bench: cannot open {args.port}: {e}")

    threading.Thread(target=b.reader, daemon=True).start()
    print(f"[bench] run dir: {run_dir}  (cec_bench {b.version})")
    if args.analyze:
        chk = subprocess.run([sys.executable, "-c", "import numpy, matplotlib"],
                             capture_output=True, text=True)
        if chk.returncode != 0:
            print("[bench] *** --analyze WANTED but numpy/matplotlib are MISSING in this Python:")
            print(f"        {sys.executable}")
            print(f"        fix: \"{sys.executable}\" -m pip install numpy matplotlib")
            print("        (captures still save; charts are skipped until you install them)")
        else:
            print("[bench] auto-analyze: ON -> analysis/<capture>/ per capture")
    else:
        print("[bench] auto-analyze: OFF (re-run with --analyze to plot each capture)")
    if tp_addr:
        print(f"[bench] forwarding teleplot -> UDP {tp_addr[0]}:{tp_addr[1]} (point Teleplot there)")
    print("[bench] teleplot '>' lines are HIDDEN here (use --show-teleplot to see them).")
    print("[bench] type device commands + Enter (frame/cal/rate/fastburst/autoburst), "
          "'quit' to stop.\n")
    try:
        if args.script:
            for cmd in args.script.split(";"):
                cmd = cmd.strip()
                if cmd:
                    b.send(cmd)
                    b.wait_idle(idle_s=args.script_idle)
            print("[bench] script done -- interactive now (induce a load, run `autoburst`).")
        for line in sys.stdin:
            cmd = line.rstrip("\n").strip()
            if cmd in ("quit", "exit"):
                break
            if cmd:
                b.send(cmd)
    except KeyboardInterrupt:
        pass
    finally:
        b.close()
        print(f"\n[bench] done. run dir: {run_dir}")


if __name__ == "__main__":
    main()

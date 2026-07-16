#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Push a firmware image to a CEC 24-pin module THROUGH the Hub, over CAN.
#
# Data path:  this host --(USB-CDC, hex lines)--> Hub --(CAN, cec_canota)--> 24-pin
#
# The ESP32-S3 has no ROM CAN bootloader, so flashing over CAN is an
# application OTA: the 24-pin writes the streamed image to its inactive OTA
# slot and reboots. The Hub buffers the image in PSRAM, verifies its CRC32,
# then runs the stop-and-wait CAN transfer (see firmware/esp/components/
# cec_comms/cec_canota.*). This script just feeds the Hub's `ota` command.
#
# Prereqs: pip install pyserial
#
# Usage:
#   python3 can_ota_push.py /dev/ttyACM0 path/to/cec_24pin.bin
#   python3 can_ota_push.py COM7 build/cec_24pin.bin --chunk 128
#
# The PORT is the HUB's USB serial port (not the 24-pin's). The 24-pin must
# already be running an OTA-partitioned image (one USB flash to convert it)
# with the CAN-OTA receiver, and both boards must share the CAN bus + bitrate.

import argparse
import sys
import time
import zlib

try:
    import serial  # pyserial
except ImportError:
    sys.exit("error: pyserial not installed -- run: pip install pyserial")


def main():
    ap = argparse.ArgumentParser(description="Flash a CEC 24-pin module over CAN via the Hub.")
    ap.add_argument("port", help="the HUB's USB serial port (e.g. /dev/ttyACM0, COM7)")
    ap.add_argument("image", help="firmware .bin to send (e.g. build/cec_24pin.bin)")
    ap.add_argument("--baud", type=int, default=115200, help="USB-CDC is rate-agnostic; any value")
    ap.add_argument("--chunk", type=int, default=128, help="payload bytes per hex line (<=256)")
    args = ap.parse_args()

    if not (1 <= args.chunk <= 256):
        sys.exit("error: --chunk must be 1..256")

    with open(args.image, "rb") as f:
        img = f.read()
    size = len(img)
    crc = zlib.crc32(img) & 0xFFFFFFFF
    print(f"image: {args.image}  size={size} bytes  crc32={crc:08x}")

    ser = serial.Serial(args.port, args.baud, timeout=2)
    time.sleep(0.3)
    ser.reset_input_buffer()

    # Kick the Hub's `ota` command and wait for its "ready" prompt.
    ser.write(f"ota {size} {crc:08x}\n".encode())
    ser.flush()
    if not _wait_for(ser, b"OTA: ready", timeout=5):
        sys.exit("error: Hub did not acknowledge `ota` (is it the Hub port? is the firmware current?)")

    # Stream the image as hex lines. Intake is silent on the Hub side, so we
    # can push all lines, then read the buffered/CRC/streaming/progress lines.
    t0 = time.time()
    for off in range(0, size, args.chunk):
        ser.write(img[off:off + args.chunk].hex().encode())
        ser.write(b"\n")
    ser.flush()
    print(f"image streamed to Hub in {time.time() - t0:.1f}s; Hub now flashing over CAN...")

    # Relay the Hub's progress + result lines until DONE / ERR / timeout.
    ok = False
    deadline = time.time() + 600
    while time.time() < deadline:
        line = ser.readline().decode(errors="replace").rstrip()
        if not line:
            continue
        if line.startswith("OTA") or "canota" in line:
            print("  " + line)
        if "DONE" in line:
            ok = True
            break
        if "ERR" in line or line.startswith("OTA: ESP_"):
            break

    ser.close()
    if ok:
        print("SUCCESS: module reported DONE and is rebooting into the new image.")
        sys.exit(0)
    sys.exit("FAILED: see the Hub output above (and the 24-pin console for the receiver side).")


def _wait_for(ser, needle, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = ser.readline()
        if not line:
            continue
        if needle in line:
            print("  " + line.decode(errors="replace").rstrip())
            return True
    return False


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Install the firmware toolchain in an ephemeral "Claude Code on the web"
# container so the firmware build gate runs in remote sessions:
#
#   * iverilog (Icarus Verilog 12, Ubuntu archive) -- the RTL sim gate
#     for firmware/rtl/**.
#   * ESP-IDF v6.0.1 at /opt/esp-idf-v60 with the esp32s3 + esp32p4
#     toolchains -- builds the firmware/esp/proto/* apps.
#     v6.0.1 is the platform pin (versions.env): the eps-8pin app's CAN
#     code needs IDF >= 6.x esp_twai APIs, the others build there too.
#
# Build gate, once this has run:
#   . "${IDF_PATH:-/opt/esp-idf-v60}/export.sh"
#   cd firmware/esp/proto/<app> && idf.py set-target <esp32s3|esp32p4> build
#
# Idempotent, root-only, non-interactive, and FAIL-SOFT like
# scripts/setup-kicad-cli.sh: never exits nonzero, so the SessionStart
# hook calling it cannot block the session if the network policy changes.
# A cold container pays ~6-10 min once; the post-hook container snapshot
# is cached, so warm sessions hit the fast-paths below and skip it.
set -uo pipefail

log() { printf '[setup-esp-idf] %s\n' "$*" >&2; }

IDF_DIR=/opt/esp-idf-v60
IDF_TAG=v6.0.1
IDF_TARGETS=esp32s3,esp32p4
TOOLS_OK_MARKER="$HOME/.espressif/.cec-idf-v601-s3p4-ok"

if [ "$(id -u)" != 0 ]; then
  log "not root -- cannot install toolchain; skipping"
  exit 0
fi

# --- 1. iverilog ---------------------------------------------------------
if command -v iverilog >/dev/null 2>&1; then
  log "iverilog present: $(iverilog -V 2>/dev/null | head -1)"
else
  log "installing iverilog via apt..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >&2 || true
  apt-get install -y -qq --no-install-recommends iverilog >&2 \
    && log "iverilog installed: $(iverilog -V 2>/dev/null | head -1)" \
    || log "WARNING: iverilog install failed; RTL sim gate unavailable"
fi

# --- 2. ESP-IDF prerequisites (cheap if present) --------------------------
if ! command -v cmake >/dev/null 2>&1 || ! command -v ninja >/dev/null 2>&1; then
  log "installing ESP-IDF host prerequisites via apt..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >&2 || true
  apt-get install -y -qq --no-install-recommends \
    git wget flex bison gperf python3 python3-pip python3-venv \
    cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0 >&2 \
    || log "WARNING: prerequisite install failed; ESP-IDF may not build"
fi

# --- 3. ESP-IDF clone ------------------------------------------------------
if [ -f "$IDF_DIR/tools/cmake/project.cmake" ]; then
  log "ESP-IDF present at $IDF_DIR"
else
  log "cloning ESP-IDF $IDF_TAG to $IDF_DIR (shallow, ~5 min)..."
  rm -rf "$IDF_DIR"
  git clone --depth 1 --branch "$IDF_TAG" --recurse-submodules \
    --shallow-submodules https://github.com/espressif/esp-idf.git "$IDF_DIR" >&2 \
    || { log "WARNING: ESP-IDF clone failed; firmware builds unavailable"; exit 0; }
fi

# --- 4. ESP-IDF tools (xtensa + riscv toolchains, python env) --------------
if [ -f "$TOOLS_OK_MARKER" ]; then
  log "ESP-IDF tools already installed for $IDF_TARGETS"
else
  log "installing ESP-IDF tools for $IDF_TARGETS..."
  if ( cd "$IDF_DIR" && ./install.sh "$IDF_TARGETS" >&2 ); then
    touch "$TOOLS_OK_MARKER"
    log "ESP-IDF tools installed"
  else
    log "WARNING: ESP-IDF tools install failed; firmware builds unavailable"
    exit 0
  fi
fi

# --- 5. smoke + env handoff -------------------------------------------------
if ( . "$IDF_DIR/export.sh" >/dev/null 2>&1 && idf.py --version >&2 ); then
  log "toolchain ready"
else
  log "WARNING: idf.py smoke failed"
fi
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  grep -q '^export IDF_PATH=' "$CLAUDE_ENV_FILE" 2>/dev/null \
    || echo "export IDF_PATH=$IDF_DIR" >> "$CLAUDE_ENV_FILE"
fi
exit 0

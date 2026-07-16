#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  ops/provision.sh -- one-shot CEC compute-box provisioner (WSL2 / bare Linux)
# ============================================================================
# WSL volumes are EPHEMERAL by definition (see CLAUDE.md "WSL-ephemeral state
# policy"). Disaster recovery for this box is therefore exactly:
#
#     1. install WSL + the Windows NVIDIA driver
#     2. git clone https://github.com/nathanfraske/CEC-Platform
#     3. bash ops/provision.sh
#
# This script reproduces the 2026-06-12 rebuild from scratch: system deps, KiCad
# 10 (pcbnew + kicad-cli), Java 21 + xvfb, Docker + the NVIDIA Container Toolkit,
# the pinned routing container, and the cec-llm-broker systemd unit -- then runs
# four smoke tests. It is IDEMPOTENT: re-running is safe and skips finished work.
#
# The GGUF model files are NOT provisioned here -- they live on Windows
# (E:\AI Models = /mnt/e/AI Models) and survive a WSL wipe by design.
#
# Usage:
#   bash ops/provision.sh                 # full provision + smoke tests
#   SMOKE_ONLY=1 bash ops/provision.sh    # just run the smoke tests
#   SMOKE_DEEP=0 bash ops/provision.sh    # skip the model-boot smoke test (#4)
#   SUDO_PASS=... bash ops/provision.sh   # non-interactive sudo (else prompts)
# ============================================================================
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
[ -f versions.env ] && . versions.env

BROKER_DIR="${CEC_BROKER_DIR:-$HOME/cec-llm-broker}"
BROKER_PORT="${CEC_BROKER_PORT:-8080}"
COMPOSE="docker compose -f $REPO_ROOT/docker/compose.yaml"

# --- pretty logging ---------------------------------------------------------
c_grn=$'\e[32m'; c_red=$'\e[31m'; c_ylw=$'\e[33m'; c_rst=$'\e[0m'
step() { printf '\n%s==>%s %s\n' "$c_ylw" "$c_rst" "$*"; }
ok()   { printf '%s  ok%s %s\n'  "$c_grn" "$c_rst" "$*"; }
die()  { printf '%s fail%s %s\n' "$c_red" "$c_rst" "$*" >&2; exit 1; }

# sudo wrapper: uses SUDO_PASS if provided, else interactive.
SUDO() {
  if [ -n "${SUDO_PASS:-}" ]; then echo "$SUDO_PASS" | sudo -S "$@"; else sudo "$@"; fi
}
have() { command -v "$1" >/dev/null 2>&1; }

# ============================================================================
#  Provision
# ============================================================================
provision() {
  step "1/6  APT repositories (KiCad 10, Docker, NVIDIA Container Toolkit)"
  SUDO bash -c '
    set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends software-properties-common ca-certificates curl gnupg
    add-apt-repository -y ppa:kicad/kicad-10.0-releases
    install -m 0755 -d /etc/apt/keyrings
    [ -f /etc/apt/keyrings/docker.asc ] || curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
    [ -f /etc/apt/keyrings/nvidia-container-toolkit-keyring.gpg ] || curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /etc/apt/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
      sed "s#deb https://#deb [signed-by=/etc/apt/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g" \
      > /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update -y
  ' || die "apt repo setup failed"
  ok "repositories configured"

  step "2/6  System packages (KiCad 10, Python deps, Java 21, xvfb, Docker, NVIDIA toolkit)"
  # Python deps go into the SYSTEM python3 (apt) so they import alongside pcbnew
  # (which KiCad installs into the system interpreter; a venv would not see it).
  SUDO bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get install -y --no-install-recommends \
      kicad \
      python3-numpy python3-scipy python3-matplotlib python3-pil \
      openjdk-21-jre xvfb xauth \
      git-lfs jq \
      docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
      nvidia-container-toolkit' || die "package install failed"
  ok "packages installed"

  step "3/6  Docker daemon + NVIDIA runtime + user group"
  SUDO nvidia-ctk runtime configure --runtime=docker >/dev/null 2>&1 || die "nvidia-ctk configure failed"
  SUDO usermod -aG docker "$USER" || true
  SUDO systemctl enable docker >/dev/null 2>&1 || true
  SUDO systemctl restart docker || die "docker failed to start"
  ok "docker $(SUDO docker version --format '{{.Server.Version}}' 2>/dev/null) running"

  step "4/6  .wslconfig template (coexistence sizing) -> Windows %UserProfile%"
  # We can't write %UserProfile% from inside WSL reliably; surface the template + the
  # one-line copy instruction. docker/.wslconfig.example is the canonical source.
  ok "template: docker/.wslconfig.example  (copy to %UserProfile%\\.wslconfig, then: wsl --shutdown)"
  printf '     sizing: memory=128GB processors=18 -> ~2 cores + ~64GB left to Windows for\n'
  printf '     the GPU driver + parallel Freerouting JVMs (one ~0.5GB JVM/core).\n'

  step "5/6  Build the pinned routing container ($KICAD_IMAGE -> cec/routing:kicad10)"
  if SUDO docker image inspect cec/routing:kicad10 >/dev/null 2>&1; then
    ok "cec/routing:kicad10 already built"
  else
    SUDO $COMPOSE build routing || die "routing image build failed"
    ok "cec/routing:kicad10 built"
  fi

  step "6/6  Deploy + start the cec-llm-broker systemd unit (from the vendored repo copy)"
  # The broker source is vendored at ops/cec-llm-broker (WSL-ephemeral policy: it must be
  # recoverable from the remote, not WSL-only). Deploy it to $BROKER_DIR, preserving an
  # existing models.json if the operator tuned it locally.
  vendored="$REPO_ROOT/ops/cec-llm-broker"
  if [ -f "$vendored/broker.py" ]; then
    mkdir -p "$BROKER_DIR"
    cp "$vendored/broker.py" "$vendored/cec-llm-broker.service" "$vendored/README.md" "$BROKER_DIR/"
    [ -f "$BROKER_DIR/models.json" ] || cp "$vendored/models.json" "$BROKER_DIR/"
    SUDO cp "$BROKER_DIR/cec-llm-broker.service" /etc/systemd/system/
    SUDO systemctl daemon-reload
    SUDO systemctl enable --now cec-llm-broker >/dev/null 2>&1 || true
    SUDO systemctl restart cec-llm-broker
    ok "cec-llm-broker deployed from repo, active on :$BROKER_PORT"
  else
    printf '%s  warn%s vendored broker not found at %s -- skipping\n' "$c_ylw" "$c_rst" "$vendored"
  fi

  step "bot git auth (from the survives-WSL secrets file, if present)"
  # shellcheck disable=SC1091
  . "$REPO_ROOT/ops/secrets/load-secrets.sh" 2>/dev/null || true
  if [ -n "${CEC_BOT_PAT:-}" ]; then
    git config --local user.name "${CEC_BOT_USER:-nathanfraske-bot}"
    bot_id="$(GH_TOKEN="$CEC_BOT_PAT" gh api user --jq '.id' 2>/dev/null || true)"
    [ -n "$bot_id" ] && git config --local user.email "${bot_id}+${CEC_BOT_USER:-nathanfraske-bot}@users.noreply.github.com"
    git config --local credential.https://github.com.helper ""
    git config --local --add credential.https://github.com.helper "$REPO_ROOT/ops/secrets/git-credential-cec.sh"
    ok "git authors + pushes as ${CEC_BOT_USER:-nathanfraske-bot} (PAT from $CEC_SECRETS_FILE)"
  else
    printf '%s  warn%s no bot PAT at %s -- git falls back to the WSL-local gh login (disposable). See ops/secrets/README.md\n' \
      "$c_ylw" "$c_rst" "${CEC_SECRETS_FILE:-/mnt/e/secrets/cec-bot.env}"
  fi

  # bot-push GUARD -- installed UNCONDITIONALLY (its whole point is to catch the no-PAT case above,
  # where git would otherwise silently push as the owner via the inherited gh helper). Owner directive
  # 2026-06-13: the agent must push as nathanfraske-bot, never the owner.
  step "bot-push guard hook (.git/hooks/pre-push: refuses a push that would authenticate as the owner)"
  if install -m755 "$REPO_ROOT/ops/hooks/pre-push" "$REPO_ROOT/.git/hooks/pre-push" 2>/dev/null; then
    ok "installed .git/hooks/pre-push (bot-push guard)"
  else
    printf '%s  warn%s could not install the pre-push guard\n' "$c_ylw" "$c_rst"
  fi
}

# ============================================================================
#  Smoke tests (the four)
# ============================================================================
smoke() {
  local fail=0
  step "Smoke 1/4  KiCad: kicad-cli + pcbnew import"
  if kicad-cli version >/dev/null 2>&1 && \
     python3 -c 'import pcbnew' 2>/dev/null; then
    ok "kicad-cli $(kicad-cli version 2>/dev/null) | pcbnew imports"
  else printf '%s fail%s KiCad/pcbnew\n' "$c_red" "$c_rst"; fail=1; fi

  step "Smoke 2/4  GPU reaches a container"
  if SUDO docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 \
       nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | grep -q .; then
    ok "GPU visible in container: $(SUDO docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null)"
  else printf '%s fail%s GPU-in-container (try: nvidia-cdi-refresh)\n' "$c_red" "$c_rst"; fail=1; fi

  step "Smoke 3/4  Broker catalog answers on :$BROKER_PORT"
  if curl -fsS "http://localhost:$BROKER_PORT/v1/models" 2>/dev/null | grep -q '"data"'; then
    n=$(curl -fsS "http://localhost:$BROKER_PORT/v1/models" 2>/dev/null | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["data"]))' 2>/dev/null)
    ok "broker live: $n models registered"
  else printf '%s fail%s broker catalog (systemctl status cec-llm-broker)\n' "$c_red" "$c_rst"; fail=1; fi

  if [ "${SMOKE_DEEP:-1}" = "1" ]; then
    step "Smoke 4/4  Broker boots a backend on demand (loads a model on the GPU)"
    printf '     requesting cec-worker-quality (cold-loads ~17GB from /mnt/e; up to 15 min)...\n'
    resp=$(curl -s -m 900 "http://localhost:$BROKER_PORT/v1/chat/completions" \
      -H 'Content-Type: application/json' -H 'X-CEC-Client: provision-smoke' \
      -d '{"model":"cec-worker-quality","messages":[{"role":"user","content":"ping"}],"max_tokens":1}' 2>/dev/null)
    if echo "$resp" | grep -q '"chat.completion"'; then
      ok "on-demand boot + proxied completion OK"
      SUDO $COMPOSE --profile worker-quality stop worker-quality >/dev/null 2>&1 || true
      SUDO systemctl restart cec-llm-broker 2>/dev/null || true
    else printf '%s fail%s broker boot test\n     %s\n' "$c_red" "$c_rst" "${resp:0:200}"; fail=1; fi
  else
    step "Smoke 4/4  skipped (SMOKE_DEEP=0)"
  fi

  echo
  [ "$fail" = 0 ] && ok "ALL SMOKE TESTS PASSED" || die "one or more smoke tests FAILED (see above)"
}

# ============================================================================
main() {
  [ "${SMOKE_ONLY:-0}" = "1" ] || provision
  smoke
}
main "$@"

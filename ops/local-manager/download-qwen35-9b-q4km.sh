#!/usr/bin/env bash
# Download exactly one verified GGUF without creating a duplicate HF cache.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root (installs under /var/lib/cec-local-llm)" >&2
  exit 2
fi

MODEL_DIR="/var/lib/cec-local-llm/models"
MODEL="${MODEL_DIR}/qwen35-9b-Q4_K_M.gguf"
PARTIAL="${MODEL}.partial"
URL="https://huggingface.co/AtomicChat/Qwen3.5-9B-GGUF/resolve/main/qwen35-9b-Q4_K_M.gguf"
SHA256="257d67756177fa088cbebac83a14c9ab7067f5dccc0b5bc79c2ba24610b28266"

install -d -m 0755 "${MODEL_DIR}"
if [[ -f "${MODEL}" ]] && echo "${SHA256}  ${MODEL}" | sha256sum --check --status; then
  echo "verified model already present: ${MODEL}"
  exit 0
fi

curl --fail --location --retry 8 --retry-all-errors --continue-at - \
  --output "${PARTIAL}" "${URL}"
echo "${SHA256}  ${PARTIAL}" | sha256sum --check
mv -f -- "${PARTIAL}" "${MODEL}"
chmod 0644 "${MODEL}"
du -h "${MODEL}"

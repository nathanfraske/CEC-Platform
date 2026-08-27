#!/usr/bin/env bash
# Download exactly one verified GGUF without creating a duplicate HF cache.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root (installs under /var/lib/cec-local-llm)" >&2
  exit 2
fi

MODEL_DIR="/var/lib/cec-local-llm/models"
MODEL="${MODEL_DIR}/qwythos-9b-v2-Q4_K_M.gguf"
PARTIAL="${MODEL}.partial"
URL="https://huggingface.co/empero-ai/Qwythos-9B-v2-GGUF/resolve/main/Qwythos-9B-v2-Q4_K_M.gguf"
SHA256="c0a588704f422b713eca29b2c1f192ae6f69aea3f9e7cb64f9ecdb76ff7a85f4"
BYTES="5736063744"

install -d -m 0755 "${MODEL_DIR}"
if [[ -f "${MODEL}" ]] && echo "${SHA256}  ${MODEL}" | sha256sum --check --status; then
  echo "verified model already present: ${MODEL}"
  exit 0
fi

# Hugging Face's Xet redirect has not reliably honored Range after an interrupted
# transfer. A clean retry costs bandwidth, but prevents an appended/corrupt GGUF
# from temporarily consuming more disk than the actual model.
rm -f -- "${PARTIAL}"
curl --fail --location --retry 8 --retry-all-errors \
  --output "${PARTIAL}" "${URL}"
[[ "$(stat -c %s "${PARTIAL}")" == "${BYTES}" ]]
echo "${SHA256}  ${PARTIAL}" | sha256sum --check
mv -f -- "${PARTIAL}" "${MODEL}"
chmod 0644 "${MODEL}"
du -h "${MODEL}"

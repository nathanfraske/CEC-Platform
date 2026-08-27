#!/usr/bin/env bash
# Build a compact CUDA llama.cpp runtime for the local wave-intent manager.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root (installs under /opt/cec-local-llm)" >&2
  exit 2
fi

TAG="${LLAMA_CPP_TAG:-b10289}"
BUILD_ROOT="/var/tmp/cec-llama-build"
INSTALL_ROOT="/opt/cec-local-llm"
JOBS="${CEC_BUILD_JOBS:-$(nproc)}"

for tool in git cmake ninja nvcc gcc-12 g++-12; do
  command -v "${tool}" >/dev/null || {
    echo "missing build dependency: ${tool}" >&2
    exit 2
  }
done

# The recursive cleanup is deliberately constrained to this fixed scratch path.
[[ "$(realpath -m "${BUILD_ROOT}")" == "/var/tmp/cec-llama-build" ]]
rm -rf -- "${BUILD_ROOT}"
git clone --depth 1 --branch "${TAG}" \
  https://github.com/ggml-org/llama.cpp.git "${BUILD_ROOT}"

CC=/usr/bin/gcc-12 CXX=/usr/bin/g++-12 CUDAHOSTCXX=/usr/bin/g++-12 \
  cmake -S "${BUILD_ROOT}" -B "${BUILD_ROOT}/build" -G Ninja \
    -DGGML_CUDA=ON \
    -DGGML_NATIVE=ON \
    -DLLAMA_CURL=OFF \
    -DCMAKE_CUDA_ARCHITECTURES=89 \
    -DCMAKE_BUILD_TYPE=Release
cmake --build "${BUILD_ROOT}/build" --target llama-server -j "${JOBS}"

install -d -m 0755 "${INSTALL_ROOT}/bin"
cp -a "${BUILD_ROOT}/build/bin/." "${INSTALL_ROOT}/bin/"

"${INSTALL_ROOT}/bin/llama-server" --version
du -sh "${BUILD_ROOT}" "${INSTALL_ROOT}"

# Keep only the installed runtime, not a second source/object-tree copy.
[[ "$(realpath -m "${BUILD_ROOT}")" == "/var/tmp/cec-llama-build" ]]
rm -rf -- "${BUILD_ROOT}"

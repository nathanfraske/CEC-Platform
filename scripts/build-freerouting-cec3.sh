#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Rebuild the hash-pinned CEC Freerouting 1.7.0-cec3 artifact in WSL/Linux.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="${1:-$repo_root/build/fr-fork/freerouting-1.7.0-cec3.jar}"
base_commit="ba0b23e89858bbfe7113df38f9de8dab090a0079"
expected_sha="202136e7e73d5aa3e2a852bab186f71b67289a4068dee0804cb9c7b2efd8c7f7"
jdk_home="${CEC_FR_BUILD_JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
temp_root="$(mktemp -d /tmp/cec-fr-cec3-XXXXXXXX)"

cleanup() {
  case "$temp_root" in
    /tmp/cec-fr-cec3-*) rm -rf -- "$temp_root" ;;
    *) printf 'Refusing unsafe cleanup target: %s\n' "$temp_root" >&2 ;;
  esac
}
trap cleanup EXIT

test -x "$jdk_home/bin/java" || {
  printf 'JDK 17 not found at %s (install openjdk-17-jdk-headless or set CEC_FR_BUILD_JAVA_HOME)\n' "$jdk_home" >&2
  exit 1
}

git clone --filter=blob:none --depth 1 --branch v1.7.0 \
  https://github.com/freerouting/freerouting.git "$temp_root/source"
actual_commit="$(git -C "$temp_root/source" rev-parse HEAD)"
test "$actual_commit" = "$base_commit" || {
  printf 'Freerouting base mismatch: expected %s, got %s\n' "$base_commit" "$actual_commit" >&2
  exit 1
}
git -C "$temp_root/source" apply \
  "$repo_root/scripts/patches/freerouting-1.7.0-cec2.patch"
git -C "$temp_root/source" apply \
  "$repo_root/scripts/patches/freerouting-1.7.0-cec3.patch"

env JAVA_HOME="$jdk_home" PATH="$jdk_home/bin:/usr/bin:/bin" \
  "$temp_root/source/gradlew" -p "$temp_root/source" executableJar \
  --rerun-tasks --no-daemon --console=plain
artifact="$temp_root/source/build/libs/freerouting-executable.jar"
actual_sha="$(sha256sum "$artifact" | awk '{print $1}')"
test "$actual_sha" = "$expected_sha" || {
  printf 'Freerouting JAR hash mismatch: expected %s, got %s\n' "$expected_sha" "$actual_sha" >&2
  exit 1
}
mkdir -p "$(dirname "$output")"
install -m 0644 "$artifact" "$output"
printf 'Built %s\nsha256 %s\n' "$output" "$actual_sha"

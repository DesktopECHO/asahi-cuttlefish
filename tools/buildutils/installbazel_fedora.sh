#!/usr/bin/env bash

# Fedora replacement for tools/buildutils/installbazel.sh
# Mirrors the upstream Debian script: installs Bazel per-architecture.
#
# Debian x86_64 installs native 'bazel' from APT repo.
# Debian aarch64 installs Bazelisk from GitHub.
# Fedora: Bazelisk on both architectures (no Bazel RPM available).
# Bazelisk auto-downloads the correct Bazel version from .bazelversion.

set -e

BAZELISK_VERSION=v1.25.0

function install_bazel_x86_64() {
  echo "Installing Bazelisk ${BAZELISK_VERSION} (x86_64)"
  curl -fsSL -o /usr/local/bin/bazel \
    "https://github.com/bazelbuild/bazelisk/releases/download/${BAZELISK_VERSION}/bazelisk-linux-amd64"
  chmod 0755 /usr/local/bin/bazel
  dnf install -y zip unzip 2>/dev/null || true
}

function install_bazel_aarch64() {
  echo "Installing Bazelisk ${BAZELISK_VERSION} (aarch64)"
  curl -fsSL -o /usr/local/bin/bazel \
    "https://github.com/bazelbuild/bazelisk/releases/download/${BAZELISK_VERSION}/bazelisk-linux-arm64"
  chmod 0755 /usr/local/bin/bazel
  dnf install -y zip unzip 2>/dev/null || true
}

install_bazel_$(uname -m)

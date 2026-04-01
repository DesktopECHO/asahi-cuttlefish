#!/usr/bin/env bash

set -e -x

function install_rpm_build_dependencies() {
  echo "Installing RPM build dependencies"
  sudo dnf -y upgrade --refresh

  # Core RPM build tooling
  sudo dnf -y install \
    rpm-build \
    rpmdevtools \
    systemd-rpm-macros

  # cuttlefish-base BuildRequires (Bazel C++ build)
  sudo dnf -y install \
    libaom-devel \
    clang-devel \
    cmake \
    fmt-devel \
    gcc-c++ \
    gflags-devel \
    git \
    glog-devel \
    gtest-devel \
    jsoncpp-devel \
    libX11-devel \
    libXext-devel \
    libcurl-devel \
    libdrm-devel \
    libuuid-devel \
    libxml2-devel \
    libsrtp-devel \
    opus-devel \
    openssl-devel \
    pkgconf-pkg-config \
    protobuf-c-devel \
    protobuf-compiler \
    protobuf-devel \
    python3 \
    mesa-libgbm-devel \
    virglrenderer-devel \
    wayland-devel \
    which \
    xxd \
    xz-devel \
    z3-devel

  # cuttlefish-frontend BuildRequires (Go + Node.js)
  sudo dnf -y install \
    curl \
    golang \
    npm

  # Runtime tools needed during rpmbuild
  sudo dnf -y install \
    rsync
}

REPO_DIR="$(realpath "$(dirname "$0")/../..")"
INSTALL_BAZEL="$(dirname "$0")/installbazel.sh"
BUILD_PACKAGE="$(dirname "$0")/build_package.sh"

install_rpm_build_dependencies
command -v bazel >/dev/null 2>&1 || sudo "${INSTALL_BAZEL}"

# Builds all RPM specs under base/rpm and frontend/rpm unless excluded.
"${BUILD_PACKAGE}" "$@" "${REPO_DIR}/base"
"${BUILD_PACKAGE}" "$@" "${REPO_DIR}/frontend"

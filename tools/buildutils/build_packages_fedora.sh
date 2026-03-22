#!/usr/bin/env bash

# Fedora replacement for tools/buildutils/build_packages.sh
# Mirrors the upstream Debian script's structure and argument handling.
#
# Usage: bash tools/buildutils/build_packages_fedora.sh [-r <remote_cache>] [-c <cache_version>] [-d <disk_cache_dir>]
#        (run from the android-cuttlefish repo root, same as the Debian script)

set -e -x

function install_rpmbuild_dependencies() {
  echo "Installing rpmbuild dependencies"
  sudo dnf install -y \
    rpm-build rpmdevtools dnf-plugins-core \
    gcc gcc-c++ cmake make git pkgconf \
    clang-devel libcap-devel fmt-devel gflags-devel glog-devel gtest-devel \
    jsoncpp-devel xz-devel opus-devel protobuf-c-devel protobuf-devel \
    libsrtp-devel openssl-devel libxml2-devel z3-devel libuuid-devel \
    libaom-devel libcurl-devel protobuf-compiler vim-common \
    golang curl systemd-rpm-macros \
    perl-FindBin perl-Getopt-Long libxcrypt-compat
}

# Fedora-specific: apply source patches before building.
# No Debian equivalent needed because Debian builds from unpatched source.
function apply_patches() {
  local patches_dir="${SCRIPT_DIR}/../../patches"
  if [ ! -d "${patches_dir}" ]; then
    echo "No patches directory found at ${patches_dir}, skipping"
    return
  fi
  echo "Applying Fedora patches"
  for p in "${patches_dir}"/*.patch; do
    [ -f "$p" ] || continue
    if git -C "${REPO_DIR}" apply --check "$p" 2>/dev/null; then
      git -C "${REPO_DIR}" apply "$p"
      echo "  Applied: $(basename "$p")"
    else
      echo "  Skipped (already applied): $(basename "$p")"
    fi
  done
}

REPO_DIR="$(realpath "$(dirname "$0")/../..")"
SCRIPT_DIR="$(realpath "$(dirname "$0")")"
INSTALL_BAZEL="${SCRIPT_DIR}/installbazel_fedora.sh"
BUILD_PACKAGE="${SCRIPT_DIR}/build_package_fedora.sh"

# Extract version from upstream Debian changelog (same source of truth).
# Can be overridden: PKG_VERSION=2.0.0 bash build_packages_fedora.sh
if [ -z "${PKG_VERSION:-}" ]; then
  PKG_VERSION="$(head -1 "${REPO_DIR}/base/debian/changelog" | sed 's/.*(\(.*\)).*/\1/')"
fi
export PKG_VERSION
echo "Package version: ${PKG_VERSION}"

command -v bazel &>/dev/null || sudo "${INSTALL_BAZEL}"
install_rpmbuild_dependencies
apply_patches

"${BUILD_PACKAGE}" "${REPO_DIR}/base" "$@"
"${BUILD_PACKAGE}" "${REPO_DIR}/frontend" "$@"

echo ""
echo "=== RPMs built ==="
find "${REPO_DIR}/rpm/_rpms" -name '*.rpm' 2>/dev/null | sort
echo ""
echo "Install with:"
echo "  sudo dnf install ${REPO_DIR}/rpm/_rpms/*/*.rpm"

#!/bin/bash
# Build crosvm from source on Fedora Asahi (aarch64, 16k kernel)
#
# This builds crosvm with system Rust (which produces 16k-aligned binaries)
# and links against system glibc Mesa libraries (not musl).
# The result replaces the prebuilt musl crosvm that can't use host GPU.
#
# Usage:
#   bash build_crosvm_fedora.sh ~/dm
#
# Where ~/dm is your cvd-host_package directory.

set -euo pipefail

INSTALL_DIR="${1:?Usage: $0 <cvd-host-package-dir>}"
CROSVM_REV="bc84c8bd6ce078e251594aa1af9e84932c5d0d81"
CROSVM_REPO="https://chromium.googlesource.com/crosvm/crosvm"
BUILD_DIR="/tmp/crosvm-build"

echo "=== Step 1: Install build dependencies ==="
sudo dnf install -y --skip-unavailable \
  rust cargo make gcc gcc-c++ \
  libcap-devel libdrm-devel libepoxy-devel \
  virglrenderer-devel wayland-devel wayland-protocols-devel \
  mesa-libEGL-devel mesa-libgbm-devel libglvnd-devel \
  protobuf-devel protobuf-compiler pkg-config

echo ""
echo "=== Step 2: Clone crosvm at the exact commit cuttlefish uses ==="
if [ -d "${BUILD_DIR}" ]; then
  echo "Reusing existing clone at ${BUILD_DIR}"
  cd "${BUILD_DIR}"
  git checkout "${CROSVM_REV}" 2>/dev/null || true
else
  git clone "${CROSVM_REPO}" "${BUILD_DIR}"
  cd "${BUILD_DIR}"
  git checkout "${CROSVM_REV}"
  git submodule update --init
fi

echo ""
echo "=== Step 3: Build crosvm ==="
# Use system Mesa libgbm and system virglrenderer instead of building
# from crosvm's bundled submodules. The submodule minigbm build produces
# libminigbm.pie.a but rutabaga_gfx expects libgbm, causing a link error.
# System libraries are also glibc-compatible (the whole point of this build).
#
# Key features:
#   gpu            - virtio-gpu device support
#   virgl_renderer - virglrenderer backend (uses host OpenGL via Mesa)
#   composite-disk - needed for cuttlefish disk images
#   net            - virtio-net support
#   balloon        - memory ballooning
#   qcow           - qcow2 disk image support
#   config-file    - --cfg flag support
#   usb            - USB passthrough

CROSVM_USE_SYSTEM_MINIGBM=1 \
CROSVM_USE_SYSTEM_VIRGLRENDERER=1 \
cargo build --release \
  --features "gpu,virgl_renderer,composite-disk,net,balloon,qcow,config-file,usb"

echo ""
echo "=== Step 4: Back up old prebuilt binaries and install ==="
CROSVM_BIN="${BUILD_DIR}/target/release/crosvm"

if [ ! -f "${CROSVM_BIN}" ]; then
  echo "ERROR: Build failed - ${CROSVM_BIN} not found"
  exit 1
fi

echo "Built crosvm binary:"
file "${CROSVM_BIN}"
readelf -l "${CROSVM_BIN}" | grep -A1 'LOAD' | head -4

# Back up originals
for f in "${INSTALL_DIR}/bin/crosvm" "${INSTALL_DIR}/bin/aarch64-linux-gnu/crosvm"; do
  if [ -f "$f" ] && [ ! -f "$f.prebuilt" ]; then
    cp "$f" "$f.prebuilt"
    echo "Backed up: $f -> $f.prebuilt"
  fi
done

# Install the new glibc-linked crosvm
cp "${CROSVM_BIN}" "${INSTALL_DIR}/bin/crosvm"
cp "${CROSVM_BIN}" "${INSTALL_DIR}/bin/aarch64-linux-gnu/crosvm"
chmod +x "${INSTALL_DIR}/bin/crosvm" "${INSTALL_DIR}/bin/aarch64-linux-gnu/crosvm"

echo ""
echo "=== Done ==="
echo ""
echo "Installed system-built crosvm to:"
echo "  ${INSTALL_DIR}/bin/crosvm"
echo "  ${INSTALL_DIR}/bin/aarch64-linux-gnu/crosvm"
echo ""
echo "Try GPU-accelerated launch:"
echo "  cd ${INSTALL_DIR}"
echo "  ulimit -n 65536"
echo "  HOME=\$PWD ./bin/launch_cvd --gpu_mode=drm_virgl --gpu_vhost_user_mode=off"
echo ""
echo "To restore prebuilt binaries:"
echo "  cp ${INSTALL_DIR}/bin/crosvm.prebuilt ${INSTALL_DIR}/bin/crosvm"
echo "  cp ${INSTALL_DIR}/bin/aarch64-linux-gnu/crosvm.prebuilt ${INSTALL_DIR}/bin/aarch64-linux-gnu/crosvm"

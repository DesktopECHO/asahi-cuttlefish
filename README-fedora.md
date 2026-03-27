# Cuttlefish on Fedora Asahi Remix (Apple Silicon)

The [android-cuttlefish](https://github.com/google/android-cuttlefish) emulator targets Debian Linux for build and deployment.  

This repo adds an RPM overlay for Fedora Asahi (aarch64), making as few changes as possible to upstream code for a successful RPM build.

<img width="3456" height="2160" alt="cf" src="https://github.com/user-attachments/assets/7ee4f5a0-76b2-4b8e-8832-f4fd22321347" />

## Quick start

```bash
# 1. Clone upstream and the overlay
git clone https://github.com/google/android-cuttlefish.git
cd android-cuttlefish
git clone https://github.com/DesktopECHO/asahi-cuttlefish.git _overlay

# 2. Copy overlay into the upstream tree
rsync -a --exclude='README.md' _overlay/ .

# 3. Build (applies patches, installs deps, builds RPMs)
bash tools/buildutils/build_packages_fedora.sh

# 4. Install
sudo dnf install rpm/_rpms/aarch64/*.rpm

# 5. Add yourself to groups and reboot
sudo usermod -aG kvm,cvdnetwork,render "$USER"
sudo reboot

# 6. Download Android images from https://ci.android.com
#    Branch: aosp-main-throttled
#    Target: aosp_cf_arm64_only_phone-trunk_staging-userdebug
#    Download: aosp_cf_arm64_only_phone-img-*.zip + cvd-host_package.tar.gz
mkdir ~/cf && cd ~/cf
unzip ~/Downloads/aosp_cf_arm64_only_phone-img-*.zip
tar xzf ~/Downloads/cvd-host_package.tar.gz

# 7. Launch
HOME=$PWD ./bin/cvd_internal_start \
  --gpu_mode=guest_swiftshader \
  --cpus=8 --memory_mb=8192 \
  --x_res=1280 --y_res=720 --dpi=160

# 8. Open https://localhost:8443 in a browser — click cvd-1 to connect
```

## GPU acceleration status

On ARM64 Asahi Linux, **`guest_swiftshader` is currently the only working
GPU mode** with standard prebuilt images from `ci.android.com`. All
accelerated modes are blocked:

| Mode | Status | Reason |
|---|---|---|
| `guest_swiftshader` | **Works** | CPU rendering in guest |
| `drm_virgl` | Blocked | Guest image lacks `libEGL_mesa.so` |
| `gfxstream` | Blocked | Prebuilt `libgfxstream_backend.so` is musl-linked; incompatible with glibc host |
| `gfxstream_guest_angle` | Blocked | Same musl/glibc mismatch |

The prebuilt `crosvm` and supporting libraries from Google's CI are
statically linked against musl libc. They cannot load system Mesa (glibc)
libraries for GPU passthrough. Building crosvm from source with system
Rust works (see `build_crosvm_fedora.sh`) but the guest images lack the
virgl-compatible Mesa EGL driver needed for `drm_virgl`.

## Usage

SwiftShader is CPU-bound. Recommended launch command:

```bash
HOME=$PWD ./bin/cvd_internal_start \
  --gpu_mode=guest_swiftshader \
  --cpus=8 \
  --memory_mb=8192 \
  --x_res=1280 --y_res=720 --dpi=160
```

- **`--cpus=8`**: Give most of your cores to the VM (M1 Pro has 10).
- **`--memory_mb=8192`**: More RAM for the guest.
- **Lower resolution**: 1280x720 renders 56% fewer pixels than 1920x1080.
- **`--dpi=160`**: Lower DPI reduces UI element rendering load.

Disable animations via ADB for a dramatic perceived speedup:

```bash
adb shell settings put global window_animation_scale 0
adb shell settings put global transition_animation_scale 0
adb shell settings put global animator_duration_scale 0
```

## What this overlay handles

Google develops Cuttlefish primarily for Debian-based systems. Porting to
Fedora requires changes in four categories — **all handled by this overlay**:

### 1. Dependency name mapping

Fedora and Debian use different package names for the same libraries.
The RPM specs translate every dependency. Common misconceptions:

- **`libslirp-devel` is NOT needed.** Android's netsim includes its own
  pure-Rust `libslirp-rs` implementation; it does not link against the
  system C library.
- **`mesa-libgbm-devel` is NOT needed.** The cuttlefish host code has no
  GBM references. The guest uses `minigbm` internally.
- **`lz4` is NOT needed.** Bazel builds lz4 from source (`MODULE.bazel`
  pins `lz4 1.9.4.bcr.2`).

### 2. The cuttlefish-common package equivalent

On Debian you install a `.deb` that sets up udev rules, user groups, and
network bridges. Our `cuttlefish-base` RPM does the same thing:

- **udev rules**: Installed to `/usr/lib/udev/rules.d/` granting
  `cvdnetwork` group access to `/dev/vhost-net` and `/dev/vhost-vsock`.
- **`cvdnetwork` group**: Created automatically in the RPM `%pre` scriptlet.
- **Network bridges**: The `cuttlefish-host-resources.service` systemd unit
  creates `cvd-wbr`, `cvd-ebr`, and per-instance tap interfaces on start,
  and tears them down on stop. Patch 0003 uses firewalld's **direct interface**
  to install the same IPv4 masquerade and bridge-filter rules as Debian, and
  also saves those rules to the permanent firewalld config so a later
  `firewall-cmd --reload` does not silently break guest networking. If
  firewalld is down, the service now warns instead of failing so `slirp`
  launches are not blocked, but bridge/tap networking remains degraded
  until firewalld is restored.
- **`setcap`**: Applied to `cvdalloc` in the RPM `%post` scriptlet.
- **SELinux policy**: Auto-generated from AVCs in the `%post` scriptlet
  using `audit` + `audit2allow`, which are now required for install-time
  policy generation.

No manual setup required beyond `sudo dnf install` and adding your user
to the `kvm,cvdnetwork,render` groups.

### 3. Kernel modules

The upstream `modules-load.d/cuttlefish-common.conf` (installed by our RPM)
auto-loads on boot:

- `vhci-hcd` — Virtual USB host controller for ADB
- `vhost_net` — Virtio networking
- `vhost_vsock` — Host-guest communication channel

No manual `modprobe` needed.

### 4. Build system

- **`lib64` path**: Fedora cmake installs to `lib64/` instead of `lib/`.
  Patch 0002 bumps libzip to a version that forces `CMAKE_INSTALL_LIBDIR=lib`.
- **Debian-only tools**: `dpkg-parsechangelog` (patch 0004), `. /lib/lsb/init-functions`
  (patch 0003), and `debuild`/`mk-build-deps` are replaced throughout.
- **SELinux**: Fedora runs SELinux enforcing. See the SELinux section below.
- **crosvm**: Ships in the `cvd-host_package.tar.gz` download from
  `ci.android.com`. Cannot be built via Bazel on 16k-page kernels because
  the hermetic Rust toolchain produces 4k-aligned ELF binaries that the
  kernel rejects. Can be built outside Bazel with system Rust — see
  `build_crosvm_fedora.sh`.

## What this overlay contains

```
base/rpm/cuttlefish-base.spec                # replaces base/debian/*
frontend/rpm/cuttlefish-frontend.spec        # replaces frontend/debian/*
tools/buildutils/build_packages_fedora.sh    # replaces build_packages.sh
tools/buildutils/build_package_fedora.sh     # replaces build_package.sh
tools/buildutils/installbazel_fedora.sh      # replaces installbazel.sh
tools/buildutils/build_crosvm_fedora.sh      # optional: build crosvm from source
tools/testutils/prepare_host_fedora.sh       # replaces prepare_host.sh
patches/
 0001-mtools-fix-termio-h-fedora.patch               # glibc 2.39 removed <termio.h>
 0002-libzip-bump-to-bcr1-fix-lib64-fedora.patch     # cmake lib64 path fix
 0003-host-resources-fedora-firewalld.patch          # lsb, sysconfig, firewalld direct rules
 0004-stamp-helper-remove-dpkg-parsechangelog.patch  # Debian-only tool
 0005-module-bazel-bump-dep-versions.patch           # silence version mismatch warnings
```

**Total: 5 patches (4 one-liners + 1 init script), 2 specs, 4 shell scripts.**

The Fedora scripts mirror the Debian scripts' structure: `build_packages_fedora.sh`
calls `installbazel_fedora.sh` then `build_package_fedora.sh` for each package,
forwarding the same `-r`/`-c`/`-d` cache flags. The per-package script uses
`dnf builddep` + `rpmbuild` in place of `mk-build-deps` + `debuild`.

## Patch details

| # | File changed | Lines | Why |
|---|---|---|---|
| 0001 | `base/cvd/build_external/mtools/config.h` | 1 | Fedora glibc >= 2.39 removed legacy `<termio.h>` |
| 0002 | `base/cvd/MODULE.bazel` | 1 | libzip 1.10.1 cmake installs to `lib64/` on Fedora; `.bcr.1` adds `CMAKE_INSTALL_LIBDIR=lib` |
| 0003 | `base/debian/...host-resources.init` | ~70 | Removes `. /lib/lsb/init-functions`; `/etc/default/` to `/etc/sysconfig/`; recreates Debian NAT + bridge filtering via firewalld direct rules; fixes `ipv6_bridge` and bridge IPv6 teardown bugs |
| 0004 | `base/stamp_helper.sh` | 1 | Replaces `dpkg-parsechangelog` (Debian-only) with `sed` to extract version from changelog |
| 0005 | `base/cvd/MODULE.bazel` | 3 | Bumps `googleapis`, `protobuf`, `rules_java` to match resolved dependency graph |

## Dependency mapping (Debian to Fedora)

| Debian | Fedora |
|---|---|
| `adduser` | `shadow-utils` |
| `dnsmasq-base` | `dnsmasq` |
| `ebtables-legacy`, `iptables` | `firewalld` direct rules backed by `ebtables` + `iptables` |
| `iproute2` | `iproute` |
| `libarchive-tools` | `bsdtar` |
| `libcap2-bin` | `libcap` |
| `libfdt1` | `libfdt` |
| `opus-tools` | `opus` |
| `xxd` | `vim-common` |
| `grub-efi-arm64-bin` | `grub2-efi-aa64-modules` (Suggests, not hard dep) |
| `perl FindBin` | `perl-FindBin` (split from `perl-core` in Fedora 39+) |
| `perl Getopt::Long` | `perl-Getopt-Long` |
| `libcrypt.so.1` (implicit) | `libxcrypt-compat` (Fedora 40+ removed old ABI) |
| `devscripts`, `debhelper` | `rpm-build`, `rpmdevtools` |
| `mk-build-deps -i` | `dnf builddep` |
| `debuild` | `rpmbuild -bb` |
| `dpkg-parsechangelog` | `sed` (patch 0004) |
| nginx `sites-available`/`sites-enabled` | `/etc/nginx/conf.d/` |

### Dependencies that are NOT needed on Fedora

| Package | Why not needed |
|---|---|
| `libslirp-devel` | netsim bundles its own Rust `libslirp-rs`; no system `libslirp.so` linkage |
| `mesa-libgbm-devel` | No host GBM usage; guest uses internal `minigbm` |
| `lz4` | Built from source by Bazel (`MODULE.bazel` pins `lz4 1.9.4.bcr.2`) |

## Asahi / 16k kernel notes

- **ELF alignment**: Binaries with LOAD segments aligned below 16k (0x4000)
  will segfault or get `ENOENT` from the kernel's ELF loader. Bazel's
  hermetic C/C++ toolchain (LLVM) produces correct output, but the hermetic
  **Rust toolchain does not** — it links with 4k alignment by default.
- **crosvm via Bazel**: Cannot be built on 16k-page kernels. Bazel's
  `rules_rust` compiles intermediate build scripts (`_bs-` binaries)
  with the hermetic Rust toolchain; the kernel rejects them immediately.
- **crosvm via system Rust**: Can be built with `build_crosvm_fedora.sh`
  using Fedora's system `rustc` (produces 64k-aligned binaries). However,
  GPU acceleration still doesn't work due to the guest image lacking Mesa
  virgl EGL drivers, and the prebuilt `libgfxstream_backend.so` being
  musl-linked.
- **qemu-user-static**: Broken on 16k kernels (x86 binfmt emulation fails).
  Use `box64` for x86_64 emulation if needed.
- **`HOME=$PWD`**: Run `launch_cvd` from a disk-backed directory (not `/tmp`
  tmpfs) to avoid quota issues.
- **`ulimit -n 65536`**: The prebuilt crosvm requires a high file descriptor
  limit. The RPM installs `/etc/security/limits.d/1_cuttlefish.conf` but
  you may need to log out and back in for it to take effect. Verify with
  `ulimit -n` before launching.
- **libcrypt.so.1**: Bazel's `rules_perl` downloads a prebuilt perl binary
  linked against `libcrypt.so.1`. The `libxcrypt-compat` BuildRequires
  handles this automatically.

## SELinux

Fedora runs SELinux enforcing. The RPM `%post` scriptlet automatically
generates and installs an SELinux policy module from any AVCs triggered
during the initial `cuttlefish-host-resources.service` start. The RPM now
pulls in the `audit` and `policycoreutils-python-utils` tooling needed for
that first-pass policy generation. If you hit additional permission denials
later:

```bash
sudo ausearch -m AVC -ts recent | audit2allow -M cuttlefish
sudo semodule -i cuttlefish.pp
```

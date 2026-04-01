# Cuttlefish on Fedora Asahi Remix (Apple Silicon)

This repository is a full fork of
[google/android-cuttlefish](https://github.com/google/android-cuttlefish)
focused on Fedora and Fedora Asahi Remix (aarch64). Fedora packaging, host
integration, and Asahi-specific workflow changes now live directly in this
tree. You build and run from this fork; there is no separate overlay checkout
or `rsync` step anymore.

<img width="3456" height="2160" alt="cf" src="https://github.com/user-attachments/assets/7ee4f5a0-76b2-4b8e-8832-f4fd22321347" />

## Quick start

```bash
# 1. Clone this fork
git clone https://github.com/DesktopECHO/asahi-cuttlefish.git
cd asahi-cuttlefish

# 2. Optional: keep the Google repository around as an upstream remote
git remote add upstream https://github.com/google/android-cuttlefish.git

# 3. Build the RPMs from this fork
bash tools/buildutils/build_packages.sh

# 4. Install the local host packages and bundled AOSP tree
sudo dnf install \
  ./out/rpmbuild/RPMS/*/cuttlefish-base-*.rpm \
  ./out/rpmbuild/RPMS/*/cuttlefish-user-*.rpm \
  ./out/rpmbuild/RPMS/*/cuttlefish-aosp-*.rpm

# 5. Add yourself to groups and reboot
sudo usermod -aG kvm,cvdnetwork,render,video "$USER"
sudo reboot

# 6. Launch
acf start \
  --gpu_mode=guest_swiftshader \
  --cpus=8 --memory_mb=8192 \
  --x_res=1280 --y_res=720 --dpi=160

# 7. Open https://localhost:8443 in a browser and click cvd-1
```

## GPU acceleration status

On ARM64 Asahi Linux, **`guest_swiftshader` remains the safe documented GPU
mode** for the packaged workflow in this fork. The host-side Fedora changes
now live directly in-tree, but accelerated modes on Apple Silicon still need
additional validation before they should be the default recommendation.

## Usage

SwiftShader is CPU-bound. Recommended launch command:

```bash
acf start \
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

## What this fork carries

Fedora and Asahi support now lives directly in the fork instead of in a
separate patch stack. The main downstream pieces are:

- Fedora RPM specs and service integration in `base/rpm/` and `frontend/rpm/`
- Fedora-aware build tooling in `tools/buildutils/build_packages.sh`,
  `tools/buildutils/build_package.sh`, and `tools/buildutils/installbazel.sh`
- Local host prep and launch helpers in `tools/testutils/prepare_host.sh` and
  `tools/acf`
- The bundled `aosp/` tree and `base/rpm/cuttlefish-aosp.spec` package for a
  self-contained local workflow

If Fedora or Asahi support requires source changes, they are committed directly
to the forked files rather than carried as an external overlay or `patches/`
directory.

## Asahi / 16k kernel notes

- **ELF alignment**: Binaries with LOAD segments aligned below 16k (0x4000)
  will segfault or get `ENOENT` from the kernel's ELF loader. Bazel's
  hermetic C/C++ toolchain (LLVM) produces correct output, but the hermetic
  **Rust toolchain does not** — it links with 4k alignment by default.
- **crosvm via Bazel**: Cannot be built on 16k-page kernels. Bazel's
  `rules_rust` compiles intermediate build scripts (`_bs-` binaries)
  with the hermetic Rust toolchain; the kernel rejects them immediately.
- **crosvm via system Rust**: Building with Fedora's system `rustc` remains a
  possible escape hatch when you need 16k-page-compatible Rust binaries, but it
  is not wired up as a standalone helper script in this fork.
- **qemu-user-static**: Broken on 16k kernels (x86 binfmt emulation fails).
  Use `box64` for x86_64 emulation if needed.
- **Disk-backed runtime dir**: Keep `CVD_HOME_DIR` on a disk-backed directory
  instead of `/tmp` tmpfs to avoid quota issues during launch and runtime.
- **`ulimit -n 65536`**: The packaged crosvm workflow can require a high file
  descriptor limit. The RPM installs `/etc/security/limits.d/1_cuttlefish.conf`
  but you may need to log out and back in for it to take effect. Verify with
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

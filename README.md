# Android Cuttlefish and CrosVM for Fedora Asahi Remix

This repository is a fork of
[google/android-cuttlefish](https://github.com/google/android-cuttlefish) refactored for RPM distributions..

[Cuttlefish](https://source.android.com/setup/create/cuttlefish) is a
configurable Android Virtual Device (AVD) that runs on Linux x86_64 and
aarch64 hosts as well as Google Compute Engine.

## Quick start on Fedora Asahi

```bash
# 1. Clone the repo
git clone https://github.com/DesktopECHO/asahi-cuttlefish.git
cd asahi-cuttlefish

# 2. Start the build from the repo root
./tools/buildutils/build_packages.sh
# If this repo is mounted at /asahi-cuttlefish, the equivalent command is:
# /asahi-cuttlefish/tools/buildutils/build_packages.sh

# 4. Install the local host packages and bundled AOSP tree
sudo dnf install \
  ./out/rpmbuild/RPMS/*/cuttlefish-base-*.rpm \
  ./out/rpmbuild/RPMS/*/cuttlefish-user-*.rpm \
  ./out/rpmbuild/RPMS/*/cuttlefish-aosp-*.rpm

# 5. Add yourself to the required groups and reboot
sudo usermod -aG kvm,cvdnetwork,render,video "$USER"
sudo reboot

# 6. Launch
acf start \
  --gpu_mode=guest_swiftshader \
  --cpus=8 --memory_mb=8192 \
  --x_res=1280 --y_res=720 --dpi=160
```

After launch, open `https://localhost:8443` in a browser and connect to
`cvd-1`.

## Fedora RPM packages

The repo currently builds these Fedora packages:

* `cuttlefish-base` - Core host binaries, networking helpers, and system
  services
* `cuttlefish-user` - Browser-facing operator service
* `cuttlefish-orchestration` - Host Orchestrator service and nginx config
* `cuttlefish-integration` - Cloud integration utilities
* `cuttlefish-defaults` - Optional defaults override service and config
* `cuttlefish-metrics` - Metrics transmitter binary
* `cuttlefish-aosp` - Bundled `aosp/` tree installed under
  `/usr/share/cuttlefish-common/aosp`
* `cuttlefish-common` - Deprecated compatibility metapackage

For the local Fedora/Asahi workflow, `cuttlefish-base`, `cuttlefish-user`, and
`cuttlefish-aosp` are the key packages.

## Notes

On ARM64 Asahi Linux, `guest_swiftshader` is the safe documented GPU mode for
the packaged workflow in this fork.

`acf` expects your login session to be in `kvm`, `cvdnetwork`, `render`, and
`video`. Log out fully and back in after changing group membership.

Bazel is installed automatically through Bazelisk by
[`tools/buildutils/installbazel.sh`](tools/buildutils/installbazel.sh).

The networking helper uses `nftables` when `ebtables` is not installed, which
matches the default on Asahi Fedora systems.

## Google Compute Engine

The current GCE image tooling in this fork lives under `tools/baseimage/`.
See [tools/baseimage/README.md](tools/baseimage/README.md) for the current
workflow.

## Container images

Please read [container/README.md](container/README.md) to build and use Docker
or Podman images containing the Cuttlefish RPM packages.

<img width="2480" height="2064" alt="Screenshot From 2026-04-01 22-30-37" src="https://github.com/user-attachments/assets/24e59e40-5dfd-45c2-9d69-ed64f1155c6c" />

# Android Cuttlefish+CrosVM for Fedora Asahi Remix

This repository is a fork of
[google/android-cuttlefish](https://github.com/google/android-cuttlefish), adapted for RPM-based distributions like Fedora Asahi Remix. 

[Cuttlefish](https://source.android.com/setup/create/cuttlefish) is a
configurable Android Virtual Device (AVD) that runs on Linux x86_64 and
aarch64 hosts as well as Google Compute Engine.

## Quick start on Fedora Asahi

```bash
# 1. Clone the Asahi-Cuttlefish repo:
git clone https://github.com/DesktopECHO/asahi-cuttlefish.git
cd asahi-cuttlefish

# 2. Start the build from the repo root
./tools/buildutils/build_packages.sh
  It will take 30-60 min to build Cuttlefish and CrosVM.

# 3. Install the local host packages and bundled LineageOS tree
sudo dnf install \
  ./out/rpmbuild/RPMS/*/cuttlefish-base-*.rpm \
  ./out/rpmbuild/RPMS/*/cuttlefish-user-*.rpm \
  ./out/rpmbuild/RPMS/*/cuttlefish-lineageos-*.rpm

# 4. Add yourself to the required groups and reboot
sudo usermod -aG kvm,cvdnetwork,render,video "$USER"
sudo reboot

# 5. Launch
ika start 
``` 

A few seconds after the virtual device is started, `scrcpy` will automatically open.  Alternatively, visit `https://localhost:8443` in a browser to view the WebRTC virtual device console.

## Managing the VM with `ika`

After the RPMs are installed, `ika` is available on your `PATH` and can be used
to start, stop, and restart the packaged Cuttlefish environment.

```bash
# Start a windowed VM
ika start 

# Check whether the VM is running
ika status

# Stop the VM and clear instance state
ika stop

# Restart with new launch arguments
ika restart --gpu_mode=guest_swiftshader --cpus=8 --memory_mb=8192

# Show the built-in usage text
ika help
```

`ika start` and `ika restart` pass extra arguments directly to
`cvd_internal_start`, so you can override launch settings on the command line.
`stop` calls the matching low-level stop helper (`cvd_internal_stop` or
`stop_cvd`) with `--clear_instance_dirs` and then cleans up local Cuttlefish
processes.

By default `ika` uses:

- host tools from `/usr/lib/cuttlefish-common`
- the packaged LineageOS tree from `/usr/share/cuttlefish-common/lineageos`
- instance state under `~/.config/cuttlefish`
- host Bluetooth, with Wi-Fi, netsim, and UWB disabled unless you override them

For this Fedora Asahi workflow, `guest_swiftshader` is the documented GPU mode
to pass when launching the VM.

## Fedora RPM packages

The repo currently builds these Fedora packages:

* `cuttlefish-base` - Core host binaries, networking helpers, and system
  services
* `cuttlefish-user` - Browser-facing operator service
* `cuttlefish-orchestration` - Host Orchestrator service and nginx config
* `cuttlefish-integration` - Cloud integration utilities
* `cuttlefish-defaults` - Optional defaults override service and config
* `cuttlefish-metrics` - Metrics transmitter binary
* `cuttlefish-lineageos` - Bundled `lineageos/` tree installed under
  `/usr/share/cuttlefish-common/lineageos`
* `cuttlefish-common` - Deprecated compatibility metapackage

For the local Fedora/Asahi workflow, `cuttlefish-base`, `cuttlefish-user`, and
`cuttlefish-lineageos` are the key packages.

## Notes

On ARM64 Asahi Linux, `guest_swiftshader` is the safe documented GPU mode for
the packaged workflow in this fork.

`ika` expects your login session to be in `kvm`, `cvdnetwork`, `render`, and
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

# Virtual Device for Android host-side utilities

This repository holds supporting tools that prepare a host to boot
[Cuttlefish](https://source.android.com/setup/create/cuttlefish), a configurable
Android Virtual Device (AVD) that targets both locally hosted Linux x86/arm64
and remotely hosted Google Compute Engine (GCE) instances rather than physical
hardware.

## Fedora RPM packages

The following RPM packages are provided:

* `cuttlefish-base` - Creates static resources needed by the Cuttlefish devices
* `cuttlefish-user` - Provides a local web server that enables interactions with
the devices through the browser
* `cuttlefish-integration` - Installs additional utilities to run Cuttlefish in
Google Compute Engine
* `cuttlefish-orchestration` - Replaces `cuttlefish-user` in the
[Orchestration project](https://github.com/google/cloud-android-orchestration)
* `cuttlefish-common` - [DEPRECATED] Provided for compatibility only, it's a
metapackage that depends on `cuttlefish-base` and `cuttlefish-user`

### Build and install manually

The RPMs can be built with the following script on Fedora (including Asahi Linux
on Apple Silicon):

```bash
tools/buildutils/build_packages.sh
```

Cuttlefish requires only `cuttlefish-base` to be installed, but `cuttlefish-user`
is recommended to enjoy a better user experience. These can be installed after
building with the following commands:

```bash
sudo dnf install ./out/rpmbuild/RPMS/*/cuttlefish-base-*.rpm ./out/rpmbuild/RPMS/*/cuttlefish-user-*.rpm
sudo usermod -aG kvm,cvdnetwork,render $USER
sudo reboot
```

The last two commands above add the user to the groups necessary to run the Cuttlefish 
Virtual Device and reboot the machine to trigger the installation of additional
kernel modules and apply udev rules.

### Asahi Linux (Apple Silicon) notes

Building on Asahi Linux requires Fedora 43+ (aarch64). Bazel 9.0.1 is
installed automatically via Bazelisk. If KVM is not available on your kernel,
Cuttlefish will fall back to software emulation.

The networking helper uses `nftables` natively when `ebtables` is not installed,
which is the default on Asahi Fedora spins.

## Google Compute Engine

The following script can be used to build a host image for Google Compute Engine:

    device/google/cuttlefish/tools/create_base_image.go

[Check out the AOSP tree](https://source.android.com/setup/build/downloading)
to obtain the script.

## Container images

Please read [container/README.md](container/README.md) to know how to build and
use docker or podman image containing Cuttlefish RPM packages.

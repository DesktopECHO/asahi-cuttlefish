# cuttlefish-base.spec — Fedora RPM port of base/debian/*
# Drop this file into base/rpm/ alongside the upstream base/debian/ directory.
# Build with: rpmbuild -bb --define "repo_root /path/to/android-cuttlefish" ...

# pkg_version is passed by build_packages_fedora.sh via --define, extracted
# from base/debian/changelog at build time.  Fallback if run standalone.
%{!?pkg_version: %global pkg_version 1.48.0}
# repo_root must be passed via --define on the rpmbuild command line.
%{!?repo_root: %{error: repo_root must be defined}}

Name:           cuttlefish-base
Version:        %{pkg_version}
Release:        1%{?dist}
Summary:        Cuttlefish Android Virtual Device companion package
License:        Apache-2.0
URL:            https://github.com/google/android-cuttlefish

# --- Build Dependencies (translated from base/debian/control Build-Depends) ---
# bazel is installed separately by installbazel_fedora.sh (not a system package).
BuildRequires:  cmake
BuildRequires:  make
BuildRequires:  git
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  libaom-devel
BuildRequires:  clang-devel
BuildRequires:  libcap-devel
BuildRequires:  libcurl-devel
BuildRequires:  fmt-devel
BuildRequires:  gflags-devel
BuildRequires:  glog-devel
BuildRequires:  gtest-devel
BuildRequires:  jsoncpp-devel
BuildRequires:  xz-devel
BuildRequires:  opus-devel
BuildRequires:  protobuf-c-devel
BuildRequires:  protobuf-devel
BuildRequires:  libsrtp-devel
BuildRequires:  openssl-devel
BuildRequires:  libxml2-devel
BuildRequires:  z3-devel
BuildRequires:  pkgconf
BuildRequires:  protobuf-compiler
BuildRequires:  libuuid-devel
BuildRequires:  vim-common
BuildRequires:  systemd-rpm-macros
# Perl modules split from perl-core in Fedora 39+ (needed by libvpx build scripts)
BuildRequires:  perl-FindBin
BuildRequires:  perl-Getopt-Long
# rules_perl downloads a prebuilt perl (for openssl asm) linked against libcrypt.so.1
# which Fedora 40+ removed; libxcrypt-compat provides the shim.
BuildRequires:  libxcrypt-compat

# --- Runtime Dependencies (translated from base/debian/control Depends) ---
# adduser -> shadow-utils (useradd/groupadd)
# dnsmasq-base -> dnsmasq
# firewalld remains the control plane on Fedora, but patch 0003 uses its
# direct interface to preserve Debian's NAT and bridge-filtering behavior.
# iproute2 -> iproute
# libarchive-tools -> bsdtar
# libcap2-bin -> libcap
# grub-efi-arm64-bin -> grub2-efi-aa64-modules (aarch64 only, Suggests not hard Requires)
# binfmt-support -> systemd-binfmt (built-in on Fedora)
# qemu-user-static -> qemu-user-static-aarch64 (Note: broken on 16k kernels)
Requires:       shadow-utils
Requires:       bridge-utils
Requires:       curl
Requires:       dnsmasq
Requires:       ebtables
Requires:       firewalld
Requires:       iproute
Requires:       iptables
Requires:       bsdtar
Requires:       libcap
Requires:       libcurl
Requires:       libdrm
Requires:       libfdt
Requires:       fmt
Requires:       gflags
Requires:       mesa-libGL
Requires:       jsoncpp
Requires:       xz-libs
Requires:       protobuf
Requires:       libsrtp
Requires:       openssl-libs
Requires:       libwayland-client
Requires:       libwayland-server
Requires:       libX11
Requires:       libXext
Requires:       libxml2
Requires:       z3-libs
Requires:       net-tools
Requires:       openssl
Requires:       opus
Requires:       python3
Requires:       xdg-utils
Suggests:       grub2-efi-aa64-modules
# SELinux policy tools — used in %post to auto-generate a policy module
# from any AVCs triggered by the cuttlefish-host-resources service.
Requires(post): audit
Requires(post): policycoreutils-python-utils

%description
Contains set of tools and binaries required to boot up and manage
Cuttlefish Android Virtual Device that are used in all deployments.

# --- Sub-packages (match Debian's multi-package layout) ---
%package -n cuttlefish-common
Summary:        Cuttlefish AVD metapackage
Requires:       cuttlefish-base = %{version}-%{release}
Requires:       cuttlefish-user

%description -n cuttlefish-common
Metapackage ensuring all packages needed to run and interact with
Cuttlefish device are installed.

%package -n cuttlefish-integration
Summary:        Cuttlefish AVD cloud integration
Requires:       cuttlefish-base = %{version}-%{release}
Requires:       qemu-system-arm >= 2.8.0
Requires:       qemu-system-x86 >= 2.8.0

%description -n cuttlefish-integration
Configuration and utilities for Android cuttlefish devices running on
Google Compute Engine. Not intended for use on developer machines.

%package -n cuttlefish-defaults
Summary:        Cuttlefish AVD default configuration
Requires:       cuttlefish-base = %{version}-%{release}

%description -n cuttlefish-defaults
May potentially enable new or experimental cuttlefish features before
being enabled by default.

%package -n cuttlefish-metrics
Summary:        Cuttlefish AVD metrics
Requires:       cuttlefish-base = %{version}-%{release}

%description -n cuttlefish-metrics
Enables metrics transmissions to Google.

# =========================================================================
%prep
# Nothing — sources come from repo_root via --define.

%build
export CC=gcc CXX=g++

# Bazel cache flags — mirrors debian/rules which reads these from environment.
# On Fedora they arrive as RPM macros from build_package_fedora.sh -r/-c/-d flags.
%{?bazel_remote_cache:remote_cache_arg="--google_default_credentials --remote_cache=%{bazel_remote_cache}/%{?bazel_cache_version}%{!?bazel_cache_version:default}"}
%{?bazel_disk_cache:disk_cache_arg="--disk_cache=%{bazel_disk_cache}"}

pushd %{repo_root}/base/cvd
bazel build \
  ${remote_cache_arg:-} ${disk_cache_arg:-} \
  -c opt \
  --spawn_strategy=local \
  --workspace_status_command=../stamp_helper.sh \
  --build_tag_filters=-clang-tidy \
  'cuttlefish/package:cvd' \
  'cuttlefish/package:defaults' \
  'cuttlefish/package:metrics'
popd

%install
ARCH=$(uname -m)
case "${ARCH}" in
  x86_64)  BAZEL_OUT="%{repo_root}/base/cvd/bazel-out/k8-opt/bin/cuttlefish/package" ;;
  aarch64) BAZEL_OUT="%{repo_root}/base/cvd/bazel-out/aarch64-opt/bin/cuttlefish/package" ;;
esac

# --- cuttlefish-base ---
# Bazel outputs: copy the cuttlefish-common DIRECTORY into /usr/lib/ so the
# tree lands at /usr/lib/cuttlefish-common/bin/cvd, etc.  This matches Debian's
# dh_install which does: "cuttlefish-common /usr/lib".
install -d %{buildroot}/usr/lib
cp -a "${BAZEL_OUT}/cuttlefish-common" %{buildroot}/usr/lib/
# Bazel outputs are read-only; make writable so rpm brp-strip can process them.
chmod -R u+w %{buildroot}/
# Static package files (NetworkManager, modules-load, limits) — these ship
# their own /etc/ tree so cp -a to / is correct here.
cp -a %{repo_root}/base/host/packages/cuttlefish-base/. %{buildroot}/
# capability_query script
install -D -m 0755 %{repo_root}/base/host/deploy/capability_query.py \
  %{buildroot}/usr/lib/cuttlefish-common/bin/capability_query.py
# Symlink: /usr/bin/cvd -> /usr/lib/cuttlefish-common/bin/cvd
install -d %{buildroot}/usr/bin
ln -sf /usr/lib/cuttlefish-common/bin/cvd %{buildroot}/usr/bin/cvd
# Symlinks for graphics detector and vulkan (from base/debian/cuttlefish-base.links)
install -d %{buildroot}/usr/lib/cuttlefish-common/bin/aarch64-linux-gnu
install -d %{buildroot}/usr/lib/cuttlefish-common/bin/x86_64-linux-gnu
install -d %{buildroot}/usr/lib/cuttlefish-common/lib64
ln -sf /usr/lib/cuttlefish-common/bin/graphics_detector    %{buildroot}/usr/lib/cuttlefish-common/bin/aarch64-linux-gnu/gfxstream_graphics_detector
ln -sf /usr/lib/cuttlefish-common/bin/libvk_swiftshader.so %{buildroot}/usr/lib/cuttlefish-common/bin/aarch64-linux-gnu/libvk_swiftshader.so
ln -sf /usr/lib/cuttlefish-common/bin/graphics_detector    %{buildroot}/usr/lib/cuttlefish-common/bin/x86_64-linux-gnu/gfxstream_graphics_detector
ln -sf /usr/lib/cuttlefish-common/bin/libvk_lavapipe.so    %{buildroot}/usr/lib/cuttlefish-common/lib64/vulkan.lvp.so
ln -sf /usr/lib/cuttlefish-common/bin/libvk_swiftshader.so %{buildroot}/usr/lib/cuttlefish-common/lib64/vulkan.pastel.so
# Remove bazel metadata (repo_mapping, runfiles dirs, runfiles manifests)
find %{buildroot}/usr/lib/cuttlefish-common -name '*.repo_mapping' -delete 2>/dev/null || true
find %{buildroot}/usr/lib/cuttlefish-common -name '*.runfiles*' -exec rm -rf {} + 2>/dev/null || true
# Fix permissions (bazel marks everything executable)
find %{buildroot}/usr/lib/cuttlefish-common -name '*.json' -exec chmod -x {} + 2>/dev/null || true
find %{buildroot}/usr/lib/cuttlefish-common/etc -type f -exec chmod -x '{}' ';' 2>/dev/null || true
# udev rules (from base/debian/cuttlefish-base.udev)
install -D -m 0644 /dev/stdin %{buildroot}/usr/lib/udev/rules.d/60-cuttlefish-base.rules << 'EOF'
ACTION=="add", KERNEL=="vhost-net", SUBSYSTEM=="misc", MODE="0660", GROUP="cvdnetwork"
ACTION=="add", KERNEL=="vhost-vsock", SUBSYSTEM=="misc", MODE="0660", GROUP="cvdnetwork"
EOF
# Host-resources init script — installed from upstream with patches already applied
install -D -m 0755 %{repo_root}/base/debian/cuttlefish-base.cuttlefish-host-resources.init \
  %{buildroot}/usr/lib/cuttlefish-common/bin/cuttlefish-host-resources.sh
# Host-resources sysconfig (Fedora name for /etc/default/)
install -D -m 0644 %{repo_root}/base/debian/cuttlefish-base.cuttlefish-host-resources.default \
  %{buildroot}/etc/sysconfig/cuttlefish-host-resources
# systemd unit for host-resources
install -D -m 0644 /dev/stdin %{buildroot}%{_unitdir}/cuttlefish-host-resources.service << 'EOF'
[Unit]
Description=Cuttlefish host network resource setup
After=network-online.target firewalld.service
Wants=network-online.target firewalld.service

[Service]
Type=oneshot
RemainAfterExit=yes
EnvironmentFile=-/etc/sysconfig/cuttlefish-host-resources
ExecStart=/usr/lib/cuttlefish-common/bin/cuttlefish-host-resources.sh start
ExecStop=/usr/lib/cuttlefish-common/bin/cuttlefish-host-resources.sh stop

[Install]
WantedBy=multi-user.target
EOF
# /var/empty for service users
install -d %{buildroot}/var/empty

# --- cuttlefish-integration ---
# Bazel 'cuttlefish/package:defaults' outputs to cuttlefish-integration/bin/cf_defaults.
# Debian installs bin/* to /usr/bin/, giving /usr/bin/cf_defaults.
install -d %{buildroot}/usr/bin
install -m 0755 "${BAZEL_OUT}/cuttlefish-integration/bin/cf_defaults" \
  %{buildroot}/usr/bin/cf_defaults 2>/dev/null || true
# Static package files (modprobe, rsyslog, sshd_config, instance_configs)
cp -a %{repo_root}/base/host/packages/cuttlefish-integration/. %{buildroot}/
install -D -m 0644 /dev/stdin %{buildroot}/usr/lib/udev/rules.d/60-cuttlefish-integration.rules << 'EOF'
KERNEL=="tpm[0-9]*", MODE="0660", OWNER="tss", GROUP="cvdnetwork"
KERNEL=="tpmrm[0-9]*", MODE="0660", OWNER="tss", GROUP="cvdnetwork"
EOF

# --- cuttlefish-defaults ---
install -D -m 0644 %{repo_root}/base/debian/cf_defaults \
  %{buildroot}/usr/lib/cuttlefish-common/etc/cf_defaults

# --- cuttlefish-metrics ---
# Debian: "cuttlefish-metrics /usr/lib" -> copies directory into /usr/lib/
cp -a "${BAZEL_OUT}/cuttlefish-metrics" %{buildroot}/usr/lib/ 2>/dev/null || true
chmod -R u+w %{buildroot}/usr/lib/cuttlefish-metrics 2>/dev/null || true
find %{buildroot}/usr/lib/cuttlefish-metrics -name '*.repo_mapping' -delete 2>/dev/null || true
find %{buildroot}/usr/lib/cuttlefish-metrics -name '*.runfiles*' -exec rm -rf {} + 2>/dev/null || true

# =========================================================================
%pre
# Equivalent of base/debian/cuttlefish-base.postinst
# Create the cvdnetwork group
getent group cvdnetwork >/dev/null 2>&1 || groupadd -r cvdnetwork
# Create /var/empty
if [ -L /var/empty ]; then unlink /var/empty; fi
if [ -f /var/empty ]; then rm -rf /var/empty; fi
mkdir -p /var/empty
# Inside docker: create kvm group if missing
if [ -f /.dockerenv ] && ! getent group kvm >/dev/null 2>&1; then
    groupadd -r kvm
fi

%post
setcap cap_net_admin,cap_net_bind_service,cap_net_raw=+ep \
    /usr/lib/cuttlefish-common/bin/cvdalloc 2>/dev/null || true
%systemd_post cuttlefish-host-resources.service
# Start (or restart) the network service immediately so tap devices and bridges
# are available without requiring a reboot.
systemctl restart cuttlefish-host-resources.service 2>/dev/null || true
# Generate an SELinux policy module from any AVCs the service just triggered.
# Fedora runs SELinux enforcing by default; cuttlefish's bridge creation,
# setcap, and KVM access commonly trip policy denials on first install.
if command -v ausearch >/dev/null 2>&1 && \
   command -v audit2allow >/dev/null 2>&1 && \
   command -v semodule >/dev/null 2>&1; then
    sleep 1  # give auditd a moment to flush
    ausearch -m AVC -ts recent 2>/dev/null | audit2allow -M cuttlefish-avd 2>/dev/null || true
    if [ -f cuttlefish-avd.pp ]; then
        semodule -i cuttlefish-avd.pp 2>/dev/null || true
        rm -f cuttlefish-avd.pp cuttlefish-avd.te 2>/dev/null
    fi
fi

%preun
%systemd_preun cuttlefish-host-resources.service

%postun
%systemd_postun_with_restart cuttlefish-host-resources.service

# =========================================================================
%files
/usr/lib/cuttlefish-common/
/usr/bin/cvd
/etc/modules-load.d/cuttlefish-common.conf
/etc/NetworkManager/conf.d/99-cuttlefish.conf
/etc/security/limits.d/1_cuttlefish.conf
/etc/sysconfig/cuttlefish-host-resources
/usr/lib/udev/rules.d/60-cuttlefish-base.rules
%{_unitdir}/cuttlefish-host-resources.service
%dir /var/empty

%files -n cuttlefish-integration
/usr/bin/cf_defaults
/etc/ssh/sshd_config.cuttlefish
/etc/modprobe.d/cuttlefish-integration.conf
/etc/default/instance_configs.cfg.template
/etc/rsyslog.d/91-cuttlefish.conf
/usr/lib/udev/rules.d/60-cuttlefish-integration.rules

%files -n cuttlefish-defaults
/usr/lib/cuttlefish-common/etc/cf_defaults

%files -n cuttlefish-metrics
/usr/lib/cuttlefish-metrics/

%files -n cuttlefish-common
# metapackage — no files of its own

%changelog
* Sat Mar 21 2026 Cuttlefish Team <cloud-android-ext@google.com>
- Fedora RPM port of cuttlefish-base Debian package

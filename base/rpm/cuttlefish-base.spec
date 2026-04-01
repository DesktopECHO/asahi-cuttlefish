Name:           cuttlefish-base
Version:        1.50.0
Release:        1%{?dist}
Summary:        Cuttlefish Android Virtual Device host packages for Fedora
License:        Apache-2.0
URL:            https://github.com/google/android-cuttlefish
Source0:        android-cuttlefish-%{version}.tar.gz
%undefine _debugsource_packages

BuildRequires:  libaom-devel
BuildRequires:  clang-devel
BuildRequires:  cmake
BuildRequires:  fmt-devel
BuildRequires:  gcc-c++
BuildRequires:  gflags-devel
BuildRequires:  git
BuildRequires:  glog-devel
BuildRequires:  gtest-devel
BuildRequires:  jsoncpp-devel
BuildRequires:  libX11-devel
BuildRequires:  libXext-devel
BuildRequires:  libcurl-devel
BuildRequires:  libdrm-devel
BuildRequires:  libuuid-devel
BuildRequires:  libxml2-devel
BuildRequires:  libsrtp-devel
BuildRequires:  opus-devel
BuildRequires:  openssl-devel
BuildRequires:  pkgconf-pkg-config
BuildRequires:  protobuf-c-devel
BuildRequires:  protobuf-compiler
BuildRequires:  protobuf-devel
BuildRequires:  python3
BuildRequires:  systemd-rpm-macros
BuildRequires:  mesa-libgbm-devel
BuildRequires:  virglrenderer-devel
BuildRequires:  wayland-devel
BuildRequires:  which
BuildRequires:  xxd
BuildRequires:  xz-devel
BuildRequires:  z3-devel

Requires:       bsdtar
Requires:       curl
Requires:       dnsmasq
Requires:       iproute
Requires:       iptables-nft
Requires:       libcap
Requires:       libdrm
Requires:       libX11
Requires:       libXext
Requires:       mesa-libgbm
Requires:       mesa-libGL
Requires:       net-tools
Requires:       NetworkManager
Requires:       nftables
Requires:       openssl
Requires:       python3
Requires:       virglrenderer
Requires:       xdg-utils
Requires:       xz-libs
Recommends:     ebtables

Requires(post): /usr/sbin/groupadd
Requires(post): /usr/sbin/usermod
Requires(post): /usr/sbin/setcap
Requires(post): /usr/sbin/sysctl
Requires(post): /usr/bin/systemctl
Requires(preun): /usr/bin/systemctl
Requires(postun): /usr/bin/systemctl

%description
Contains the base host-side binaries, networking helpers, and system services
required to boot and manage Cuttlefish Android Virtual Devices on Fedora.

%package -n cuttlefish-common
Summary:        Compatibility metapackage for Cuttlefish host packages
Requires:       cuttlefish-base = %{version}-%{release}
Requires:       cuttlefish-defaults = %{version}-%{release}
Requires:       cuttlefish-user = %{version}-%{release}

%description -n cuttlefish-common
Compatibility metapackage ensuring the primary host-side Cuttlefish packages
are installed together.

%package -n cuttlefish-integration
Summary:        Cloud integration utilities for Cuttlefish
Requires:       cuttlefish-base = %{version}-%{release}
%ifarch aarch64
Requires:       qemu-system-aarch64-core
%endif
%ifarch x86_64
Requires:       qemu-system-x86-core
%endif

%description -n cuttlefish-integration
Contains cloud-oriented integration helpers and metadata-driven defaults for
Cuttlefish deployments.

%package -n cuttlefish-defaults
Summary:        Optional Cuttlefish defaults override file
Requires:       cuttlefish-base = %{version}-%{release}
Requires:       cuttlefish-integration = %{version}-%{release}

%description -n cuttlefish-defaults
Provides an optional override file for Cuttlefish defaults in a standard Fedora
configuration path.

%package -n cuttlefish-metrics
Summary:        Metrics transmission support for Cuttlefish
Requires:       cuttlefish-base = %{version}-%{release}

%description -n cuttlefish-metrics
Contains the metrics transmitter binary used by Cuttlefish.

%prep
%autosetup -n android-cuttlefish-%{version}

%build
case "%{_arch}" in
  x86_64) bazel_arch=k8 ;;
  aarch64) bazel_arch=aarch64 ;;
  *) echo "Unsupported architecture: %{_arch}" >&2; exit 1 ;;
esac

readonly package_output_root="base/cvd/bazel-out/${bazel_arch}-opt/bin/cuttlefish/package"
pushd base/cvd
# Use a local output_base so that stale Bazel repo/action caches from
# previous builds (in ~/.cache/bazel/) cannot interfere. The rpmbuild
# BUILD directory is cleaned between runs, guaranteeing a fresh state.
# Place it outside the Bazel workspace (base/cvd/) to avoid glob issues.
BAZEL_OUTPUT_BASE="$(realpath "$PWD/..")/.bazel_output"
mkdir -p "$BAZEL_OUTPUT_BASE"
# Keep download/build caches persistent across rpmbuild runs so external
# repositories are fetched once and then reused on slow connections.
BAZEL_CACHE_ROOT="${CUTTLEFISH_BAZEL_CACHE_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/cuttlefish-bazel}"
BAZEL_REPOSITORY_CACHE="$BAZEL_CACHE_ROOT/repository"
BAZEL_DISK_CACHE="$BAZEL_CACHE_ROOT/disk"
BAZEL_DISTDIR="$BAZEL_CACHE_ROOT/distdir"
mkdir -p "$BAZEL_REPOSITORY_CACHE" "$BAZEL_DISK_CACHE" "$BAZEL_DISTDIR"
# Point TMPDIR into the build tree so that cargo-bazel workspace splicing
# (crate_universe) creates its temp symlinks here instead of /tmp, avoiding
# quota-exceeded errors on size- or inode-limited filesystems.
BAZEL_TMPDIR="$BAZEL_OUTPUT_BASE/tmp"
mkdir -p "$BAZEL_TMPDIR"
export TMPDIR="$BAZEL_TMPDIR"

retry_count=0
max_retries=9
retry_delay=60
while true; do
  if DISABLE_BAZEL_WRAPPER=yes USE_BAZEL_VERSION=8.5.1 \
    bazel --output_base="$BAZEL_OUTPUT_BASE" build -c opt \
    --repository_cache="$BAZEL_REPOSITORY_CACHE" \
    --disk_cache="$BAZEL_DISK_CACHE" \
    --distdir="$BAZEL_DISTDIR" \
    'cuttlefish/package:cvd' \
    'cuttlefish/package:defaults' \
    'cuttlefish/package:metrics' \
    --spawn_strategy=local \
    --repo_env=TMPDIR="$BAZEL_TMPDIR" \
    --workspace_status_command=../stamp_helper.sh \
    --build_tag_filters=-clang-tidy; then
    break
  fi

  retry_count=$((retry_count + 1))
  if [ "$retry_count" -ge "$max_retries" ]; then
    echo "Bazel build failed after ${retry_count} attempts." >&2
    exit 1
  fi

  echo "Bazel build failed, retrying in ${retry_delay}s (${retry_count}/${max_retries})..." >&2
  sleep "$retry_delay"
done
popd

%install
rm -rf %{buildroot}

case "%{_arch}" in
  x86_64) bazel_arch=k8 ;;
  aarch64) bazel_arch=aarch64 ;;
  *) echo "Unsupported architecture: %{_arch}" >&2; exit 1 ;;
esac

mkdir -p %{buildroot}/usr/lib
cp -a base/cvd/bazel-out/${bazel_arch}-opt/bin/cuttlefish/package/cuttlefish-common %{buildroot}/usr/lib/
mkdir -p %{buildroot}/usr/bin
cp -a base/cvd/bazel-out/${bazel_arch}-opt/bin/cuttlefish/package/cuttlefish-integration/bin/* %{buildroot}/usr/bin/
mkdir -p %{buildroot}/usr/lib/cuttlefish-metrics/bin
cp -a base/cvd/bazel-out/${bazel_arch}-opt/bin/cuttlefish/package/cuttlefish-metrics/bin/metrics_transmitter %{buildroot}/usr/lib/cuttlefish-metrics/bin/

rm -rf %{buildroot}/usr/lib/cuttlefish-common/bin/cvd.repo_mapping
rm -rf %{buildroot}/usr/lib/cuttlefish-common/bin/cvd.runfiles*
rm -rf %{buildroot}/usr/lib/cuttlefish-common/bin/crosvm.repo_mapping
rm -rf %{buildroot}/usr/lib/cuttlefish-common/bin/crosvm.runfiles*
rm -rf %{buildroot}/usr/bin/cf_defaults.repo_mapping
rm -rf %{buildroot}/usr/bin/cf_defaults.runfiles*
rm -rf %{buildroot}/usr/lib/cuttlefish-metrics/bin/metrics_transmitter.repo_mapping
rm -rf %{buildroot}/usr/lib/cuttlefish-metrics/bin/metrics_transmitter.runfiles*

chmod -x %{buildroot}/usr/lib/cuttlefish-common/bin/*.json
chmod -x %{buildroot}/usr/lib/cuttlefish-common/bin/mke2fs.conf
find %{buildroot}/usr/lib/cuttlefish-common/etc -type f -exec chmod -x '{}' ';'
find %{buildroot}/usr/lib/cuttlefish-common/usr/share/webrtc/assets -type f -exec chmod -x '{}' ';'

install -Dpm0755 base/host/deploy/capability_query.py %{buildroot}/usr/lib/cuttlefish-common/bin/capability_query.py
install -Dpm0755 tools/acf %{buildroot}/bin/acf
install -Dpm0644 base/host/packages/cuttlefish-base/etc/NetworkManager/conf.d/99-cuttlefish.conf %{buildroot}/etc/NetworkManager/conf.d/99-cuttlefish.conf
install -Dpm0644 base/rpm/99-cuttlefish.conf %{buildroot}/etc/sysctl.d/99-cuttlefish.conf
install -Dpm0644 base/host/packages/cuttlefish-base/etc/modules-load.d/cuttlefish-common.conf %{buildroot}/etc/modules-load.d/cuttlefish-common.conf
install -Dpm0644 base/host/packages/cuttlefish-base/etc/security/limits.d/1_cuttlefish.conf %{buildroot}/etc/security/limits.d/1_cuttlefish.conf
install -Dpm0755 base/rpm/cuttlefish-ulimit.sh %{buildroot}/etc/profile.d/cuttlefish-ulimit.sh
install -Dpm0644 base/rpm/70-cuttlefish-base.rules %{buildroot}/usr/lib/udev/rules.d/70-cuttlefish-base.rules
install -Dpm0644 base/rpm/cuttlefish-host-resources.service %{buildroot}/usr/lib/systemd/system/cuttlefish-host-resources.service
install -Dpm0755 base/rpm/cuttlefish-host-resources.sh %{buildroot}/usr/libexec/cuttlefish/cuttlefish-host-resources
install -Dpm0755 base/rpm/cuttlefish-add-user-to-groups.sh %{buildroot}/usr/libexec/cuttlefish/cuttlefish-add-user-to-groups
install -Dpm0644 base/rpm/cuttlefish-host-resources.sysconfig %{buildroot}/etc/sysconfig/cuttlefish-host-resources

install -Dpm0644 base/rpm/71-cuttlefish-integration.rules %{buildroot}/usr/lib/udev/rules.d/71-cuttlefish-integration.rules
install -Dpm0644 base/host/packages/cuttlefish-integration/etc/modprobe.d/cuttlefish-integration.conf %{buildroot}/etc/modprobe.d/cuttlefish-integration.conf
install -Dpm0644 base/host/packages/cuttlefish-integration/etc/rsyslog.d/91-cuttlefish.conf %{buildroot}/etc/rsyslog.d/91-cuttlefish.conf
install -Dpm0644 base/host/packages/cuttlefish-integration/etc/ssh/sshd_config.cuttlefish %{buildroot}/etc/ssh/sshd_config.d/cuttlefish.conf
install -Dpm0644 base/rpm/instance_configs.cfg.template %{buildroot}/etc/sysconfig/instance_configs.cfg.template
install -Dpm0644 base/rpm/cuttlefish-defaults.service %{buildroot}/usr/lib/systemd/system/cuttlefish-defaults.service
install -Dpm0755 base/rpm/cuttlefish-defaults.sh %{buildroot}/usr/libexec/cuttlefish/cuttlefish-defaults
install -Dpm0644 base/rpm/cuttlefish-integration.sysconfig %{buildroot}/etc/sysconfig/cuttlefish-integration

install -d %{buildroot}/etc/cuttlefish-common
: > %{buildroot}/etc/cuttlefish-common/cf_defaults

ln -sfn ../lib/cuttlefish-common/bin/cvd %{buildroot}/usr/bin/cvd
mkdir -p %{buildroot}/usr/lib/cuttlefish-common/bin/aarch64-linux-gnu
mkdir -p %{buildroot}/usr/lib/cuttlefish-common/bin/x86_64-linux-gnu
mkdir -p %{buildroot}/usr/lib/cuttlefish-common/lib64
ln -sfn ../graphics_detector %{buildroot}/usr/lib/cuttlefish-common/bin/aarch64-linux-gnu/gfxstream_graphics_detector
ln -sfn ../libvk_swiftshader.so %{buildroot}/usr/lib/cuttlefish-common/bin/aarch64-linux-gnu/libvk_swiftshader.so
ln -sfn ../graphics_detector %{buildroot}/usr/lib/cuttlefish-common/bin/x86_64-linux-gnu/gfxstream_graphics_detector
ln -sfn ../bin/libvk_lavapipe.so %{buildroot}/usr/lib/cuttlefish-common/lib64/vulkan.lvp.so
ln -sfn ../bin/libvk_swiftshader.so %{buildroot}/usr/lib/cuttlefish-common/lib64/vulkan.pastel.so

%post
if ! getent group cvdnetwork >/dev/null 2>&1; then
  groupadd -r cvdnetwork >/dev/null 2>&1 || :
fi
if ! getent group kvm >/dev/null 2>&1; then
  groupadd -r kvm >/dev/null 2>&1 || :
fi
mkdir -p /var/empty
setcap cap_net_admin,cap_net_bind_service,cap_net_raw=+ep /usr/lib/cuttlefish-common/bin/cvdalloc >/dev/null 2>&1 || :
/usr/sbin/sysctl --system >/dev/null 2>&1 || :
/usr/libexec/cuttlefish/cuttlefish-add-user-to-groups || :
udevadm control --reload >/dev/null 2>&1 || :
systemctl daemon-reload >/dev/null 2>&1 || :
%ifarch aarch64
systemctl disable --now cuttlefish-host-resources.service >/dev/null 2>&1 || :
%else
systemctl enable --now cuttlefish-host-resources.service >/dev/null 2>&1 || :
%endif
required_nofile=524288
required_rtprio=10
current_soft_nofile="$(ulimit -Sn 2>/dev/null || echo 0)"
current_hard_nofile="$(ulimit -Hn 2>/dev/null || echo 0)"
current_soft_rtprio="$(ulimit -Sr 2>/dev/null || echo 0)"
current_hard_rtprio="$(ulimit -Hr 2>/dev/null || echo 0)"
case "$current_soft_nofile" in
  unlimited) current_soft_nofile="$required_nofile" ;;
esac
case "$current_hard_nofile" in
  unlimited) current_hard_nofile="$required_nofile" ;;
esac
case "$current_soft_rtprio" in
  unlimited) current_soft_rtprio="$required_rtprio" ;;
esac
case "$current_hard_rtprio" in
  unlimited) current_hard_rtprio="$required_rtprio" ;;
esac
if [ "${current_soft_nofile:-0}" -lt "$required_nofile" ] || \
   [ "${current_hard_nofile:-0}" -lt "$required_nofile" ] || \
   [ "${current_soft_rtprio:-0}" -lt "$required_rtprio" ] || \
   [ "${current_hard_rtprio:-0}" -lt "$required_rtprio" ]; then
  echo "Cuttlefish installed nofile=524288 and rtprio=10 for @cvdnetwork in /etc/security/limits.d/1_cuttlefish.conf." >&2
  echo "A new login session may be required before 'ulimit -n' and 'ulimit -r' reflect the higher limits." >&2
fi

%post -n cuttlefish-defaults
systemctl daemon-reload >/dev/null 2>&1 || :

%preun
if [ $1 -eq 0 ]; then
  systemctl disable --now cuttlefish-host-resources.service >/dev/null 2>&1 || :
fi

%preun -n cuttlefish-defaults
if [ $1 -eq 0 ]; then
  systemctl disable --now cuttlefish-defaults.service >/dev/null 2>&1 || :
fi

%postun
systemctl daemon-reload >/dev/null 2>&1 || :

%postun -n cuttlefish-defaults
systemctl daemon-reload >/dev/null 2>&1 || :

%files
%license LICENSE
/bin/acf
/usr/bin/cvd
/usr/lib/cuttlefish-common
/etc/NetworkManager/conf.d/99-cuttlefish.conf
%config(noreplace) /etc/sysctl.d/99-cuttlefish.conf
/etc/modules-load.d/cuttlefish-common.conf
/etc/profile.d/cuttlefish-ulimit.sh
/etc/security/limits.d/1_cuttlefish.conf
/etc/sysconfig/cuttlefish-host-resources
/usr/lib/systemd/system/cuttlefish-host-resources.service
/usr/lib/udev/rules.d/70-cuttlefish-base.rules
/usr/libexec/cuttlefish/cuttlefish-host-resources
/usr/libexec/cuttlefish/cuttlefish-add-user-to-groups

%files -n cuttlefish-common
%license LICENSE

%files -n cuttlefish-integration
%license LICENSE
/usr/bin/cf_defaults
/etc/modprobe.d/cuttlefish-integration.conf
/etc/rsyslog.d/91-cuttlefish.conf
/etc/ssh/sshd_config.d/cuttlefish.conf
/etc/sysconfig/instance_configs.cfg.template
/usr/lib/udev/rules.d/71-cuttlefish-integration.rules

%files -n cuttlefish-defaults
%license LICENSE
%config(noreplace) /etc/cuttlefish-common/cf_defaults
/etc/sysconfig/cuttlefish-integration
/usr/lib/systemd/system/cuttlefish-defaults.service
/usr/libexec/cuttlefish/cuttlefish-defaults

%files -n cuttlefish-metrics
%license LICENSE
/usr/lib/cuttlefish-metrics

%changelog
* Sat Mar 28 2026 Daniel Milisic <dmilisic@desktopecho.com> - 1.50.0-1
- Port host packaging and service assets to Fedora RPMs

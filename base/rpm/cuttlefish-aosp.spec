Name:           cuttlefish-aosp
Version:        20260401
Release:        1%{?dist}
Summary:        AOSP tree for Cuttlefish host workflows
License:        Apache-2.0
URL:            https://github.com/google/android-cuttlefish
Source0:        android-cuttlefish-1.50.0.tar.gz
ExclusiveArch:  aarch64
%global debug_package %{nil}
%global __debug_install_post %{nil}
%undefine _debugsource_packages
AutoReqProv:    no

Requires:       cuttlefish-base
Requires(post): /usr/sbin/setcap

%description
Contains the AOSP tree used by this Cuttlefish workflow, installed under
/usr/share/cuttlefish-common/aosp.

%prep
%autosetup -n android-cuttlefish-1.50.0

%build
case "%{_arch}" in
  x86_64) bazel_arch=k8 ;;
  aarch64) bazel_arch=aarch64 ;;
  *) echo "Unsupported architecture: %{_arch}" >&2; exit 1 ;;
esac

pushd base/cvd
BAZEL_OUTPUT_BASE="$(realpath "$PWD/..")/.bazel_output"
mkdir -p "$BAZEL_OUTPUT_BASE"
BAZEL_CACHE_ROOT="${CUTTLEFISH_BAZEL_CACHE_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/cuttlefish-bazel}"
BAZEL_REPOSITORY_CACHE="$BAZEL_CACHE_ROOT/repository"
BAZEL_DISK_CACHE="$BAZEL_CACHE_ROOT/disk"
BAZEL_DISTDIR="$BAZEL_CACHE_ROOT/distdir"
mkdir -p "$BAZEL_REPOSITORY_CACHE" "$BAZEL_DISK_CACHE" "$BAZEL_DISTDIR"
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

mkdir -p %{buildroot}/usr/share/cuttlefish-common
cp -a aosp %{buildroot}/usr/share/cuttlefish-common/
pushd base/cvd/bazel-out/${bazel_arch}-opt/bin/cuttlefish/package/cuttlefish-common
while IFS= read -r overlay_path; do
  while IFS= read -r -d '' entry; do
    dest="%{buildroot}/usr/share/cuttlefish-common/aosp/${entry#./}"
    if [ -d "${entry}" ]; then
      install -d "${dest}"
    else
      install -d "$(dirname "${dest}")"
      cp -a --remove-destination "${entry}" "${dest}"
    fi
  done < <(find "${overlay_path}" -mindepth 1 -print0)
done <<'EOF'
bin
lib64
usr/share/webrtc
EOF
popd
install -Dpm0755 base/rpm/avbtool-wrapper.sh %{buildroot}/usr/share/cuttlefish-common/aosp/bin/avbtool
install -Dpm0644 base/rpm/vendor/avbtool.py %{buildroot}/usr/share/cuttlefish-common/aosp/bin/avbtool.py
find %{buildroot}/usr/share/cuttlefish-common/aosp ! -type l -exec chmod u+w '{}' +
find %{buildroot}/usr/share/cuttlefish-common/aosp ! -type l -exec chmod g=u '{}' +

%files
%license LICENSE
%defattr(-,root,kvm,-)
/usr/share/cuttlefish-common/aosp

%post
setcap cap_net_admin,cap_net_bind_service,cap_net_raw=+ep /usr/share/cuttlefish-common/aosp/bin/cvdalloc >/dev/null 2>&1 || :

%changelog
* Tue Mar 31 2026 Daniel Milisic <dmilisic@desktopecho.com> - 20260401-1
- Package the AOSP tree as a standalone RPM

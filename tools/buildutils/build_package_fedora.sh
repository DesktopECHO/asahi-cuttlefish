#!/usr/bin/env bash

# Fedora replacement for tools/buildutils/build_package.sh
# Mirrors the upstream Debian script: takes a package directory and
# optional -r/-c/-d flags for Bazel cache configuration.
#
# Usage: build_package_fedora.sh /path/to/pkgdir [-r <remote_cache>] [-c <cache_version>] [-d <disk_cache_dir>]

set -o errexit -o nounset -o pipefail

function print_usage() {
  >&2 echo "usage: $0 /path/to/pkgdir [-r <remote_cache>] [-c <cache_version>] [-d <disk_cache_dir>]"
}

if [[ $# -eq 0 ]]; then
  >&2 echo "missing path to package directory"
  print_usage
  exit 1
fi

readonly PKGDIR="$1"
shift

# Parse cache options — same flags as the Debian build_package.sh.
# On Debian these become debuild -e envvars -> debian/rules -> bazel flags.
# On Fedora these become rpmbuild --define macros -> spec %build -> bazel flags.
remote_cache_arg=""
cache_version_arg=""
disk_cache_arg=""

while getopts ":r:c:d:" opt; do
  case "${opt}" in
    r) remote_cache_arg="${OPTARG}" ;;
    c) cache_version_arg="${OPTARG}" ;;
    d) disk_cache_arg="${OPTARG}" ;;
    \?)
      echo "Invalid option: ${OPTARG}" >&2
      print_usage
      exit 1
      ;;
    :)
      echo "Invalid option: ${OPTARG} requires an argument" >&2
      print_usage
      exit 1
      ;;
  esac
done

# Find the spec file (the spec name doesn't have to match the directory name,
# e.g. base/ contains cuttlefish-base.spec, frontend/ contains cuttlefish-frontend.spec).
RPM_DIR="${PKGDIR}/rpm"
mapfile -t SPEC_FILES < <(find "${RPM_DIR}" -maxdepth 1 -name '*.spec' 2>/dev/null)

if [[ ${#SPEC_FILES[@]} -eq 0 ]]; then
  echo "ERROR: no *.spec file found in ${RPM_DIR}" >&2
  exit 1
elif [[ ${#SPEC_FILES[@]} -gt 1 ]]; then
  echo "ERROR: multiple *.spec files found in ${RPM_DIR}:" >&2
  printf '  %s\n' "${SPEC_FILES[@]}" >&2
  exit 1
fi

SPEC_FILE="${SPEC_FILES[0]}"
REPO_DIR="$(realpath "${PKGDIR}/..")"

# Version comes from the parent build_packages_fedora.sh via env, or fallback.
: "${PKG_VERSION:=1.48.0}"

# Build the --define array that replaces Debian's debuild -e envvars.
RPM_DEFINES=(
  --define "repo_root ${REPO_DIR}"
  --define "pkg_version ${PKG_VERSION}"
  --define "_rpmdir ${REPO_DIR}/rpm/_rpms"
  --define "_srcrpmdir ${REPO_DIR}/rpm/_srpms"
  --define "_builddir ${REPO_DIR}/rpm/_build"
)

# Forward Bazel cache settings as RPM macros.
# The spec's %build section reads these to construct bazel flags, mirroring
# how debian/rules reads BAZEL_REMOTE_CACHE / BAZEL_DISK_CACHE_DIR env vars.
if [[ -n "${remote_cache_arg}" ]]; then
  RPM_DEFINES+=(--define "bazel_remote_cache ${remote_cache_arg}")
fi
if [[ -n "${cache_version_arg}" ]]; then
  RPM_DEFINES+=(--define "bazel_cache_version ${cache_version_arg}")
fi
if [[ -n "${disk_cache_arg}" ]]; then
  RPM_DEFINES+=(--define "bazel_disk_cache ${disk_cache_arg}")
fi

# Preserve proxy environment — mirrors Debian's build_package.sh behavior.
if [[ -n "${http_proxy:-}" ]]; then
  RPM_DEFINES+=(--define "__http_proxy ${http_proxy}")
fi
if [[ -n "${https_proxy:-}" ]]; then
  RPM_DEFINES+=(--define "__https_proxy ${https_proxy}")
fi

pushd "${PKGDIR}"
echo "Installing package dependencies"
sudo dnf builddep -y "${RPM_DEFINES[@]}" "${SPEC_FILE}" || true
echo "Building packages"
rpmbuild -bb "${RPM_DEFINES[@]}" "${SPEC_FILE}"
popd

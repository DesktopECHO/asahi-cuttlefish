#!/usr/bin/env bash

# Copyright (C) 2025 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -o errexit -o nounset -o pipefail

function print_usage() {
  >&2 echo "usage: $0 [--exclude-spec NAME[.spec]]... /path/to/pkgdir"
  >&2 echo "   or: $0 [--exclude-spec NAME[.spec]]... /path/to/specfile.spec"
}

declare -a excluded_specs=()
input_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --exclude-spec)
      [[ $# -ge 2 ]] || {
        >&2 echo "missing value for --exclude-spec"
        print_usage
        exit 1
      }
      excluded_specs+=("$2")
      shift 2
      ;;
    --exclude-spec=*)
      excluded_specs+=("${1#--exclude-spec=}")
      shift
      ;;
    --help|-h)
      print_usage
      exit 0
      ;;
    --*)
      >&2 echo "unknown option: $1"
      print_usage
      exit 1
      ;;
    *)
      if [[ -n "${input_path}" ]]; then
        >&2 echo "unexpected extra argument: $1"
        print_usage
        exit 1
      fi
      input_path="$1"
      shift
      ;;
  esac
done

[[ -n "${input_path}" ]] || {
  >&2 echo "missing path to package directory"
  print_usage
  exit 1
}

readonly INPUT_PATH="${input_path}"
readonly INPUT_PATH_ABS="$(realpath "${INPUT_PATH}")"

readonly REPO_DIR="$(realpath "$(dirname "$0")/../..")"
readonly VERSION_FILE="${REPO_DIR}/packaging/VERSION"
readonly VERSION="$(tr -d '\n' < "${VERSION_FILE}")"
readonly RPMBUILD_TOPDIR="${REPO_DIR}/out/rpmbuild"
readonly RPMBUILD_WORK_ROOT="${RPMBUILD_TOPDIR}/work"
readonly TAR_BASENAME="android-cuttlefish-${VERSION}"
readonly SOURCE_TARBALL="${RPMBUILD_TOPDIR}/SOURCES/${TAR_BASENAME}.tar.gz"
readonly SOURCE_MANIFEST="${RPMBUILD_TOPDIR}/SOURCES/${TAR_BASENAME}.manifest"
readonly SOURCE_STAGING_DIR="${RPMBUILD_TOPDIR}/SOURCES/${TAR_BASENAME}"
declare -a build_workdirs=()

function normalize_spec_name() {
  local spec_name="$1"
  spec_name="$(basename "${spec_name}")"
  spec_name="${spec_name%.spec}"
  printf '%s\n' "${spec_name}"
}

function should_exclude_spec() {
  local normalized_spec
  local excluded_spec

  normalized_spec="$(normalize_spec_name "$1")"
  for excluded_spec in "${excluded_specs[@]}"; do
    if [[ "${normalized_spec}" == "$(normalize_spec_name "${excluded_spec}")" ]]; then
      return 0
    fi
  done
  return 1
}

function build_source_manifest() {
  local manifest_path="$1"

  (
    cd "${REPO_DIR}"
    find . \
      \( -path './.git' -o -path './.jj' -o -path './out' -o -path './base/cvd/bazel-out' -o -name 'bazel-*' \) -prune -o \
      -print0 | sort -z | while IFS= read -r -d '' path; do
        local relpath="${path#./}"
        [[ -n "${relpath}" ]] || continue

        local mode
        mode="$(stat -c '%f' "${path}")"

        if [[ -d "${path}" ]]; then
          printf 'dir\t%s\t%s\n' "${relpath}" "${mode}"
        elif [[ -L "${path}" ]]; then
          printf 'symlink\t%s\t%s\t%s\n' "${relpath}" "${mode}" "$(readlink "${path}")"
        elif [[ -f "${path}" ]]; then
          printf 'file\t%s\t%s\t%s\n' "${relpath}" "${mode}" "$(sha256sum "${path}" | cut -d' ' -f1)"
        fi
      done
  ) > "${manifest_path}"
}

function refresh_source_tarball_if_needed() {
  local tmp_manifest
  tmp_manifest="$(mktemp "${RPMBUILD_TOPDIR}/SOURCES/${TAR_BASENAME}.manifest.XXXXXX")"
  trap 'rm -f "${tmp_manifest}"' RETURN

  local scrcpy_server_dest="${REPO_DIR}/scrcpy/scrcpy-server"
  local scrcpy_server_build_helper="${REPO_DIR}/tools/build_scrcpy_server_aarch64.sh"
  local local_scrcpy_server="${REPO_DIR}/out/build-scrcpy-server/scrcpy-server"

  # Only prepare the scrcpy-server when the scrcpy spec is actually being built.
  local building_scrcpy=false
  if [[ -f "${INPUT_PATH_ABS}" && "$(basename "${INPUT_PATH_ABS}" .spec)" == "cuttlefish-scrcpy" ]]; then
    building_scrcpy=true
  elif [[ -d "${INPUT_PATH_ABS}/rpm" && -f "${INPUT_PATH_ABS}/rpm/cuttlefish-scrcpy.spec" ]]; then
    building_scrcpy=true
  fi

  if [[ "${building_scrcpy}" == "true" ]]; then
    # On aarch64, prefer a locally built scrcpy-server since the upstream prebuilt
    # causes protocol issues with the SDL3 client on Asahi. Fall back to the
    # upstream release artifact if the local toolchain is not available.
    if [[ "$(uname -m)" == "aarch64" && -x "${scrcpy_server_build_helper}" ]]; then
      echo "Building scrcpy-server locally for aarch64"
      if BUILD_DIR="${REPO_DIR}/out/build-scrcpy-server" "${scrcpy_server_build_helper}"; then
        install -m 0644 "${local_scrcpy_server}" "${scrcpy_server_dest}"
      else
        echo "Local scrcpy-server build failed; falling back to the upstream prebuilt"
      fi
    fi

    # Fetch scrcpy-server JAR if a local build did not provide one.
    # Version is read from the meson.build project declaration so it stays in sync.
    if [[ ! -f "${scrcpy_server_dest}" ]]; then
      local scrcpy_version
      scrcpy_version="$(grep -m1 "version:" "${REPO_DIR}/scrcpy/meson.build" \
                        | grep -oP "'\K[0-9]+\.[0-9]+\.[0-9]+")" || true
      if [[ -n "${scrcpy_version}" ]]; then
        echo "Fetching scrcpy-server v${scrcpy_version}"
        curl -fL --retry 3 \
          -o "${scrcpy_server_dest}" \
          "https://github.com/Genymobile/scrcpy/releases/download/v${scrcpy_version}/scrcpy-server-v${scrcpy_version}"
      fi
    fi
  fi

  build_source_manifest "${tmp_manifest}"

  if [[ -f "${SOURCE_TARBALL}" && -f "${SOURCE_MANIFEST}" ]] && cmp -s "${tmp_manifest}" "${SOURCE_MANIFEST}"; then
    echo "Reusing source tarball ${SOURCE_TARBALL}"
    return
  fi

  rm -rf "${SOURCE_STAGING_DIR}" "${SOURCE_TARBALL}"
  mkdir -p "${SOURCE_STAGING_DIR}"

  rsync -a \
    --exclude='.git/' \
    --exclude='.jj/' \
    --exclude='out/' \
    --exclude='base/cvd/bazel-out/' \
    --exclude='bazel-*/' \
    "${REPO_DIR}/" \
    "${SOURCE_STAGING_DIR}/"

  tar -czf "${SOURCE_TARBALL}" -C "${RPMBUILD_TOPDIR}/SOURCES" "${TAR_BASENAME}"
  mv "${tmp_manifest}" "${SOURCE_MANIFEST}"
  rm -rf "${SOURCE_STAGING_DIR}"
}

function cleanup_build_workdirs() {
  local workdir
  for workdir in "${build_workdirs[@]}"; do
    [[ -d "${workdir}" ]] || continue
    rm -rf "${workdir}" || true
  done
}

trap cleanup_build_workdirs EXIT

mkdir -p \
  "${RPMBUILD_TOPDIR}/BUILD" \
  "${RPMBUILD_TOPDIR}/BUILDROOT" \
  "${RPMBUILD_TOPDIR}/RPMS" \
  "${RPMBUILD_TOPDIR}/SOURCES" \
  "${RPMBUILD_TOPDIR}/SPECS" \
  "${RPMBUILD_WORK_ROOT}"

refresh_source_tarball_if_needed

declare -a specs
declare -a pushd_args

if [[ -f "${INPUT_PATH_ABS}" && "${INPUT_PATH_ABS}" == *.spec ]]; then
  if should_exclude_spec "${INPUT_PATH_ABS}"; then
    echo "Skipping excluded spec $(basename "${INPUT_PATH_ABS}")"
    exit 0
  fi
  specs=("${INPUT_PATH_ABS}")
  pushd_args=("$(dirname "${specs[0]}")")
elif [[ -d "${INPUT_PATH_ABS}/rpm" ]]; then
  specs=("${INPUT_PATH_ABS}"/rpm/*.spec)
  if [[ ${#specs[@]} -eq 0 ]]; then
    >&2 echo "no spec files found under ${INPUT_PATH_ABS}/rpm"
    exit 1
  fi
  if [[ ${#excluded_specs[@]} -gt 0 ]]; then
    declare -a filtered_specs=()
    for spec in "${specs[@]}"; do
      if should_exclude_spec "${spec}"; then
        echo "Skipping excluded spec $(basename "${spec}")"
        continue
      fi
      filtered_specs+=("${spec}")
    done
    specs=("${filtered_specs[@]}")
  fi
  if [[ ${#specs[@]} -eq 0 ]]; then
    echo "No RPM specs left to build under ${INPUT_PATH_ABS}/rpm after exclusions"
    exit 0
  fi
  pushd_args=("${INPUT_PATH_ABS}")
else
  >&2 echo "missing rpm directory under ${INPUT_PATH_ABS}, or input is not a .spec file"
  exit 1
fi

pushd "${pushd_args[0]}"
for spec in "${specs[@]}"; do
  spec_workdir="$(mktemp -d "${RPMBUILD_WORK_ROOT}/$(normalize_spec_name "${spec}").XXXXXX")"
  build_workdirs+=("${spec_workdir}")
  echo "Building RPM from ${spec}"
  rpmbuild \
    --define "_topdir ${RPMBUILD_TOPDIR}" \
    --define "_sourcedir ${RPMBUILD_TOPDIR}/SOURCES" \
    --define "_rpmdir ${RPMBUILD_TOPDIR}/RPMS" \
    --define "_builddir ${spec_workdir}/BUILD" \
    --define "_buildrootdir ${spec_workdir}/BUILDROOT" \
    -bb "${spec}"
done
popd

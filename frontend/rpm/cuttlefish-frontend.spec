# cuttlefish-frontend.spec — Fedora RPM port of frontend/debian/*
# Drop this file into frontend/rpm/ alongside the upstream frontend/debian/ directory.
# Build with: rpmbuild -bb --define "repo_root /path/to/android-cuttlefish" ...

%{!?pkg_version: %global pkg_version 1.48.0}
%{!?repo_root: %{error: repo_root must be defined}}

Name:           cuttlefish-user
Version:        %{pkg_version}
Release:        1%{?dist}
Summary:        Cuttlefish AVD operator and host orchestrator
License:        Apache-2.0
URL:            https://github.com/google/android-cuttlefish

BuildRequires:  golang >= 1.13
BuildRequires:  protobuf-devel
BuildRequires:  protobuf-compiler
BuildRequires:  curl
BuildRequires:  systemd-rpm-macros

# cuttlefish-user deps
Requires:       cuttlefish-base
Requires:       shadow-utils
Requires:       openssl

%description
Contains the host signaling server (operator) supporting multi-device
flows over WebRTC for Cuttlefish Android Virtual Devices.

%package -n cuttlefish-orchestration
Summary:        Cuttlefish AVD host orchestrator
Requires:       cuttlefish-user = %{version}-%{release}
Requires:       shadow-utils
Requires:       openssl
Requires:       nginx
Requires:       systemd-journal-remote

%description -n cuttlefish-orchestration
Contains the host orchestrator for Cuttlefish Android Virtual Devices.

# =========================================================================
%prep
# Nothing — sources come from repo_root via --define.

%build
GOUTIL="%{repo_root}/frontend/src/goutil"
ORCHESTRATOR_DIR="%{repo_root}/frontend/src/host_orchestrator"
OPERATOR_DIR="%{repo_root}/frontend/src/operator"

# Build Go binaries
"${GOUTIL}" "${ORCHESTRATOR_DIR}" build -v -buildmode=pie -ldflags="-w"
"${GOUTIL}" "${OPERATOR_DIR}" build -v -buildmode=pie -ldflags="-w"

# Build WebUI
pushd %{repo_root}/frontend
. ./setup-nodejs-env.sh
install_nodejs
package_version="$(head -1 debian/changelog | sed 's/.*(\(.*\)).*/\1/')"
last_commit="$( (git log -1 || echo dev) | head -1 | sed 's/commit //')"
echo "export const BUILD_VERSION = \"fedora-${package_version}-${last_commit}\";" \
  > src/operator/webui/src/environments/version.ts
(cd src/operator/webui/ && npm install && ./node_modules/.bin/ng build)
uninstall_nodejs
popd

%install
# --- cuttlefish-user ---
install -D -m 0755 %{repo_root}/frontend/src/operator/operator \
  %{buildroot}/usr/lib/cuttlefish-common/bin/operator
install -D -m 0755 %{repo_root}/frontend/src/host_orchestrator/host_orchestrator \
  %{buildroot}/usr/lib/cuttlefish-common/bin/host_orchestrator
# WebUI assets
install -d %{buildroot}/usr/share/cuttlefish-common/operator/static
cp -a %{repo_root}/frontend/src/operator/webui/dist/static/. \
  %{buildroot}/usr/share/cuttlefish-common/operator/static/
# intercept directory
cp -a %{repo_root}/frontend/src/operator/intercept \
  %{buildroot}/usr/share/cuttlefish-common/operator/intercept

# Operator systemd service
install -D -m 0644 /dev/stdin %{buildroot}%{_unitdir}/cuttlefish-operator.service << 'UNIT'
[Unit]
Description=Cuttlefish Operator (WebRTC signaling)
After=network-online.target cuttlefish-host-resources.service
Wants=network-online.target

[Service]
Type=simple
User=_cutf-operator
Group=cvdnetwork
EnvironmentFile=-/etc/sysconfig/cuttlefish-operator
ExecStartPre=/bin/bash -c '\
  D=${operator_tls_cert_dir:-/etc/cuttlefish-common/operator/cert}; \
  mkdir -p "$D"; \
  [ -f "$D/cert.pem" ] && [ -f "$D/key.pem" ] && exit 0; \
  openssl req -newkey rsa:4096 -x509 -sha256 -days 36000 -nodes \
    -out "$D/cert.pem" -keyout "$D/key.pem" -subj "/C=US"; \
  chown _cutf-operator:cvdnetwork "$D/cert.pem" "$D/key.pem"'
ExecStart=/usr/lib/cuttlefish-common/bin/operator \
  --socket_path=/run/cuttlefish/operator
RuntimeDirectory=cuttlefish
RuntimeDirectoryMode=0775

[Install]
WantedBy=multi-user.target
UNIT

# Operator sysconfig
install -D -m 0644 /dev/stdin %{buildroot}/etc/sysconfig/cuttlefish-operator << 'CONF'
# operator_http_port=1080
# operator_https_port=1443
# operator_tls_cert_dir=/etc/cuttlefish-common/operator/cert
# operator_listen_address=
# operator_webui_url=
CONF

# --- cuttlefish-orchestration ---
# Fedora nginx uses /etc/nginx/conf.d/ (not Debian's sites-available/sites-enabled)
install -D -m 0644 \
  %{repo_root}/frontend/host/packages/cuttlefish-orchestration/etc/nginx/sites-available/cuttlefish-orchestration.conf \
  %{buildroot}/etc/nginx/conf.d/cuttlefish-orchestration.conf

# Orchestrator systemd service
install -D -m 0644 /dev/stdin %{buildroot}%{_unitdir}/cuttlefish-host_orchestrator.service << 'UNIT'
[Unit]
Description=Cuttlefish Host Orchestrator
After=network-online.target cuttlefish-operator.service nginx.service
Wants=network-online.target systemd-journal-gatewayd.service

[Service]
Type=simple
User=httpcvd
EnvironmentFile=-/etc/sysconfig/cuttlefish-host_orchestrator
ExecStartPre=/bin/bash -c '\
  D=/etc/cuttlefish-orchestration/ssl/cert; \
  mkdir -p "$D"; \
  [ -f "$D/cert.pem" ] && [ -f "$D/key.pem" ] && exit 0; \
  openssl req -newkey rsa:4096 -x509 -sha256 -days 36000 -nodes \
    -out "$D/cert.pem" -keyout "$D/key.pem" -subj "/C=US"; \
  nginx -s reload 2>/dev/null || true'
ExecStartPre=/bin/bash -c 'mkdir -p /var/lib/cuttlefish-common && chown httpcvd: /var/lib/cuttlefish-common'
ExecStart=/usr/lib/cuttlefish-common/bin/host_orchestrator
WorkingDirectory=/usr/share/cuttlefish-common/operator
RuntimeDirectory=cuttlefish
RuntimeDirectoryMode=0775

[Install]
WantedBy=multi-user.target
UNIT

# Orchestrator sysconfig
install -D -m 0644 /dev/stdin %{buildroot}/etc/sysconfig/cuttlefish-host_orchestrator << 'CONF'
# orchestrator_http_port=2080
# orchestrator_cvd_artifacts_dir=/var/lib/cuttlefish-common
# orchestrator_listen_address=
CONF

# =========================================================================
%pre
# Create _cutf-operator user (from frontend/debian/cuttlefish-user.postinst)
getent passwd _cutf-operator >/dev/null 2>&1 || \
  useradd -r -s /sbin/nologin -d /var/empty -g cvdnetwork _cutf-operator

%post
%systemd_post cuttlefish-operator.service

%preun
%systemd_preun cuttlefish-operator.service

%postun
%systemd_postun_with_restart cuttlefish-operator.service

%pre -n cuttlefish-orchestration
getent passwd httpcvd >/dev/null 2>&1 || {
  useradd -r -s /sbin/nologin -d /var/empty -U httpcvd
  usermod -a -G cvdnetwork,kvm httpcvd
}

%post -n cuttlefish-orchestration
%systemd_post cuttlefish-host_orchestrator.service

%preun -n cuttlefish-orchestration
%systemd_preun cuttlefish-host_orchestrator.service

%postun -n cuttlefish-orchestration
%systemd_postun_with_restart cuttlefish-host_orchestrator.service

# =========================================================================
%files
/usr/lib/cuttlefish-common/bin/operator
/usr/lib/cuttlefish-common/bin/host_orchestrator
/usr/share/cuttlefish-common/operator/
/etc/sysconfig/cuttlefish-operator
%{_unitdir}/cuttlefish-operator.service

%files -n cuttlefish-orchestration
/etc/nginx/conf.d/cuttlefish-orchestration.conf
/etc/sysconfig/cuttlefish-host_orchestrator
%{_unitdir}/cuttlefish-host_orchestrator.service

%changelog
* Sat Mar 21 2026 Cuttlefish Team <cloud-android-ext@google.com>
- Fedora RPM port of cuttlefish-user/orchestration Debian packages

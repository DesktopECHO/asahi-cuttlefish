Name:           cuttlefish-lineageos
Version:        20260401
Release:        1%{?dist}
Summary:        LineageOS for Cuttlefish host
License:        Apache-2.0
URL:            https://github.com/google/android-cuttlefish
Source0:        android-cuttlefish-1.50.0.tar.gz
ExclusiveArch:  aarch64
%global debug_package %{nil}
%global __debug_install_post %{nil}
%undefine _debugsource_packages
AutoReqProv:    no

Requires:       cuttlefish-base

%description
Contains LineageOS 23 for use by this Cuttlefish workflow, installed under
/usr/share/cuttlefish-common/lineageos.

%prep
%autosetup -n android-cuttlefish-1.50.0

%install
rm -rf %{buildroot}

mkdir -p %{buildroot}/usr/share/cuttlefish-common
cp -a lineageos %{buildroot}/usr/share/cuttlefish-common/
find %{buildroot}/usr/share/cuttlefish-common/lineageos ! -type l -exec chmod u+w '{}' +
find %{buildroot}/usr/share/cuttlefish-common/lineageos ! -type l -exec chmod g=u '{}' +

%files
%license LICENSE
%defattr(-,root,kvm,-)
/usr/share/cuttlefish-common/lineageos

%post
cd /usr/share/cuttlefish-common/lineageos || exit 0
find etc usr -mindepth 1 | while read -r path; do
  target="/usr/lib/cuttlefish-common/${path}"
  if [ ! -e "${target}" ]; then
    mkdir -p "$(dirname "${target}")"
    ln -s "/usr/share/cuttlefish-common/lineageos/${path}" "${target}"
  fi
done

%changelog
* Tue Mar 31 2026 Daniel Milisic <dmilisic@desktopecho.com> - 20260401-1
- Package LineageOS as standalone RPM

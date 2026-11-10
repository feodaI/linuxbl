#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m py_compile shell/*.py
sh -n bin/feodal-panel bin/feodal-session bin/feodal-hardware bin/feodal-input bin/feodal-installer bin/feodal-lock bin/feodal-gaming
python3 -m py_compile bin/feodal-install-backend bin/feodal-antigravity
bash -n packaging/PKGBUILD scripts/build-iso.sh iso/overlay/airootfs/etc/mkinitcpio.conf.d/feodal.conf
sh -n scripts/setup-ui-tests.sh scripts/boot-vm.sh scripts/check-live-session.sh scripts/check-desktop-session.sh
python3 tests/test_desktop_defaults.py
python3 tests/test_memory_profile.py
python3 tests/test_input.py
python3 tests/test_wallpaper.py
python3 tests/test_installer_core.py
python3 tests/test_install_backend.py
python3 tests/test_gaming.py
python3 tests/test_antigravity.py
python3 tests/test_preferences.py
python3 tests/test_hardware.py
python3 tests/test_lock.py
python3 tests/test_session.py
python3 tests/test_live_readiness.py
python3 -c 'import xml.etree.ElementTree as E; E.parse("config/openbox.xml")'
xvfb-run -a -s '-screen 0 1366x768x24' dbus-run-session -- /usr/bin/python3 tests/test_shell.py
xvfb-run -a -s '-screen 0 1366x768x24' dbus-run-session -- /usr/bin/python3 tests/test_installer_gui.py

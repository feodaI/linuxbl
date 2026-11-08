#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m py_compile shell/feodal_panel.py
sh -n bin/feodal-panel bin/feodal-session
bash -n packaging/PKGBUILD scripts/build-iso.sh iso/overlay/airootfs/etc/mkinitcpio.conf.d/feodal.conf
sh -n scripts/setup-ui-tests.sh scripts/boot-vm.sh scripts/check-live-session.sh
python3 tests/test_memory_profile.py
python3 -c 'import xml.etree.ElementTree as E; E.parse("config/openbox.xml")'
xvfb-run -a -s '-screen 0 1366x768x24' dbus-run-session -- /usr/bin/python3 tests/test_shell.py

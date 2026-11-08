#!/bin/sh
set -eu
case "${1:-}" in
    ''|--with-vm) ;;
    *) printf 'Usage: %s [--with-vm]\n' "$0" >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'Run as root on Ubuntu/Debian to install UI test dependencies.' >&2
    exit 1
fi
apt-get update
apt-get install -y --no-install-recommends python3-gi python3-cairo python3-gi-cairo \
    gir1.2-gtk-3.0 gir1.2-wnck-3.0 openbox xvfb xauth xdotool xterm dbus-x11 libx11-6 x11-xkb-utils

if [ "${1:-}" = --with-vm ]; then
    apt-get install -y --no-install-recommends qemu-system-x86 qemu-utils libarchive-tools openssh-client curl
fi

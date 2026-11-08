#!/bin/sh
set -eu
[ "$(id -u)" -eq 0 ] || { printf '%s\n' 'Run inside the booted Feodal live VM as root.' >&2; exit 1; }
[ "$(cat /etc/hostname)" = feodal ]
user_id=$(id -u feodal)
[ "$user_id" -ne 0 ]
pgrep -u "$user_id" -f '/usr/lib/feodal/feodal_panel.py' >/dev/null
pgrep -u "$user_id" -x openbox >/dev/null
for service in NetworkManager systemd-resolved; do
    systemctl is-active --quiet "$service"
done
for unit in systemd-networkd.service systemd-networkd.socket systemd-networkd-wait-online.service iwd.service sshd.service; do
    [ "$(systemctl is-enabled "$unit" 2>/dev/null || true)" = masked ]
done
for unit in pipewire.socket pipewire-pulse.socket; do
    runuser -u feodal -- env XDG_RUNTIME_DIR="/run/user/$user_id" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$user_id/bus" \
        systemctl --user is-active --quiet "$unit"
done
swapon --noheadings --raw --show=NAME | grep -Fx /dev/zram0
zramctl --output NAME,DISKSIZE,ALGORITHM
getent ahostsv4 archlinux.org >/dev/null
printf '%s\n' 'PASS: unprivileged shell, network/DNS, service masks, audio sockets, zram.'

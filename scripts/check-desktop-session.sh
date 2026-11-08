#!/bin/sh
set -eu
[ "$(id -u)" -eq 0 ] || { printf '%s\n' 'Run inside the booted Feodal live VM as root.' >&2; exit 1; }
user_id=$(id -u feodal)
[ "$user_id" -ne 0 ]
for process in stalonetray nm-applet pasystray xfce4-power-manager dunst polkit-gnome-authentication-agent-1; do
    pgrep -u "$user_id" -f "(^|/)$process( |$)" >/dev/null || {
        printf 'Missing desktop helper: %s\n' "$process" >&2
        exit 1
    }
done
user_command() {
    runuser -u feodal -- env DISPLAY=:0 XAUTHORITY=/home/feodal/.Xauthority \
        XDG_RUNTIME_DIR="/run/user/$user_id" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$user_id/bus" "$@"
}
user_command feodal-input --status
user_command gdbus call --session --dest org.freedesktop.Notifications \
    --object-path /org/freedesktop/Notifications --method org.freedesktop.Notifications.GetServerInformation
printf '%s\n' 'PASS: desktop helpers, XKB status, notification service. Physical hardware is not checked.'

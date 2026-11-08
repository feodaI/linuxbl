if [ "${USER:-}" = feodal ] && [ -z "${DISPLAY:-}" ] && [ "$(tty 2>/dev/null)" = /dev/tty1 ]; then
    startx /usr/bin/feodal-session -- -keeptty vt1 || printf '%s\n' 'Feodal graphical session did not start; use startx /usr/bin/feodal-session from tty1 to retry.' >&2
fi

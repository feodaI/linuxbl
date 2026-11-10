import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / 'bin/feodal-session'
ACTIVATION_VARS = (
    'DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP '
    'XDG_SESSION_DESKTOP XDG_SESSION_TYPE'
)
DAEMONS = (
    'feodal-panel', 'nm-applet', 'pasystray', 'xfce4-power-manager', 'xss-lock',
    'dunst', 'stalonetray', 'polkit-gnome-authentication-agent-1',
)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bindir = self.directory / 'bin'
        self.bindir.mkdir()
        self.started_dir = self.directory / 'started'
        self.started_dir.mkdir()
        self.env = os.environ.copy()
        self.env.update({
            'PATH': str(self.bindir),
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/mock-session',
            'DISPLAY': ':42',
            'XAUTHORITY': '/tmp/mock-xauthority',
            'CALL_LOG': str(self.directory / 'calls'),
            'STARTED_DIR': str(self.started_dir),
            'EXPECTED_HELPERS': ' '.join(DAEMONS),
            'PANEL_STOP_FILE': str(self.directory / 'panel-stopped'),
            'FEODAL_POLKIT_AGENT': 'polkit-gnome-authentication-agent-1',
        })
        self.env.pop('DBUS_LOG', None)
        for daemon in DAEMONS:
            extra = ': > "$PANEL_STOP_FILE"' if daemon == 'feodal-panel' else ':'
            self.write_executable(daemon, f'''\
#!/bin/sh
printf 'started {daemon} %s\\n' "$*" >> "$CALL_LOG"
trap 'printf "stopped {daemon}\\n" >> "$CALL_LOG"; {extra}; exit 0' TERM INT
: > "$STARTED_DIR/{daemon}"
while :; do /bin/sleep 0.02; done
''')
        self.write_executable('feodal-input', '''\
#!/bin/sh
printf 'input %s\\n' "$*" >> "$CALL_LOG"
''')
        self.write_executable('openbox', '''\
#!/bin/sh
printf 'openbox %s\\n' "$*" >> "$CALL_LOG"
printf 'DISPLAY=%s\\nXAUTHORITY=%s\\nXDG_CURRENT_DESKTOP=%s\\nXDG_SESSION_DESKTOP=%s\\nXDG_SESSION_TYPE=%s\\n' \\
    "${DISPLAY-}" "${XAUTHORITY-}" "${XDG_CURRENT_DESKTOP-}" \\
    "${XDG_SESSION_DESKTOP-}" "${XDG_SESSION_TYPE-}" >> "$CALL_LOG"
for helper in $EXPECTED_HELPERS; do
    attempts=0
    while [ ! -f "$STARTED_DIR/$helper" ] && [ "$attempts" -lt 500 ]; do
        /bin/sleep 0.01
        attempts=$((attempts + 1))
    done
    [ -f "$STARTED_DIR/$helper" ] || exit 91
done
exit "${WM_STATUS:-0}"
''')
        self.write_executable('dbus-update-activation-environment', '''\
#!/bin/sh
printf 'updater %s\\n' "$*" >> "$CALL_LOG"
printf 'updater DISPLAY=%s\\nupdater XAUTHORITY=%s\\nupdater XDG_CURRENT_DESKTOP=%s\\nupdater XDG_SESSION_DESKTOP=%s\\nupdater XDG_SESSION_TYPE=%s\\n' \\
    "${DISPLAY-}" "${XAUTHORITY-}" "${XDG_CURRENT_DESKTOP-}" \\
    "${XDG_SESSION_DESKTOP-}" "${XDG_SESSION_TYPE-}" >> "$CALL_LOG"
exit "${UPDATER_STATUS:-0}"
''')

    def write_executable(self, name, content):
        path = self.bindir / name
        path.write_text(content)
        path.chmod(0o755)

    def run_session(self, env=None):
        return subprocess.run([str(SESSION)], env=env or self.env, text=True,
                              capture_output=True, timeout=10)

    def test_starts_optional_helpers_and_cleans_up_their_processes(self):
        result = self.run_session()
        log = Path(self.env['CALL_LOG']).read_text()

        self.assertEqual(result.returncode, 0, result.stderr)
        for daemon in DAEMONS:
            self.assertIn(f'started {daemon} ', log)
            self.assertIn(f'stopped {daemon}', log)
        self.assertIn('started xfce4-power-manager --no-daemon', log)
        self.assertIn('started xss-lock --transfer-sleep-lock -- feodal-lock', log)
        self.assertIn('started dunst -config /etc/xdg/feodal/dunstrc', log)
        self.assertIn('started stalonetray -c /etc/xdg/feodal/stalonetrayrc', log)
        self.assertIn('input --apply', log)
        self.assertLess(log.index('input --apply'), log.index('openbox '))

    def test_applies_dark_theme_and_xterm_resources(self):
        self.write_executable('feodal-input', '''\
#!/bin/sh
printf 'input GTK_THEME=%s XENVIRONMENT=%s\\n' "${GTK_THEME-}" "${XENVIRONMENT-}" >> "$CALL_LOG"
''')
        self.env.pop('GTK_THEME', None)
        self.env.pop('XENVIRONMENT', None)
        self.assertEqual(self.run_session().returncode, 0)
        log = Path(self.env['CALL_LOG']).read_text()
        self.assertIn('input GTK_THEME=Adwaita:dark XENVIRONMENT=/etc/xdg/feodal/Xresources', log)
        Path(self.env['CALL_LOG']).unlink()
        self.env.update({'GTK_THEME': 'Custom', 'XENVIRONMENT': '/custom'})
        self.assertEqual(self.run_session().returncode, 0)
        self.assertIn('input GTK_THEME=Custom XENVIRONMENT=/custom', Path(self.env['CALL_LOG']).read_text())

    def test_updates_only_requested_activation_environment_before_wm(self):
        result = self.run_session()
        log = Path(self.env['CALL_LOG']).read_text()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('updater --systemd ' + ACTIVATION_VARS, log)
        self.assertNotIn('--all', log)
        self.assertIn('openbox --config-file /etc/xdg/feodal/openbox.xml', log)
        self.assertIn('updater DISPLAY=:42', log)
        self.assertIn('updater XAUTHORITY=/tmp/mock-xauthority', log)
        for value in ('XDG_CURRENT_DESKTOP=Feodal', 'XDG_SESSION_DESKTOP=feodal',
                      'XDG_SESSION_TYPE=x11'):
            self.assertIn('updater ' + value, log)
            self.assertIn(value, log)
        self.assertLess(log.index('updater '), log.index('openbox '))

    def test_missing_dbus_address_starts_one_session(self):
        dbus_log = self.directory / 'dbus-calls'
        self.env['DBUS_LOG'] = str(dbus_log)
        self.write_executable('dbus-run-session', '''\
#!/bin/sh
printf 'called\\n' >> "$DBUS_LOG"
[ "$1" = -- ] || exit 90
shift
export DBUS_SESSION_BUS_ADDRESS=unix:path=/mock-started-session
exec "$@"
''')
        env = self.env.copy()
        env.pop('DBUS_SESSION_BUS_ADDRESS')

        result = self.run_session(env)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(dbus_log.read_text().splitlines(), ['called'])
        self.assertIn('openbox ', Path(self.env['CALL_LOG']).read_text())

    def test_activation_updater_failure_warns_but_wm_runs(self):
        self.env['UPDATER_STATUS'] = '17'

        result = self.run_session()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('warning:', result.stderr)
        self.assertIn('openbox ', Path(self.env['CALL_LOG']).read_text())

    def test_missing_optional_helpers_warn_but_wm_runs(self):
        optional = ('nm-applet', 'pasystray', 'xfce4-power-manager', 'dunst',
                    'stalonetray', 'polkit-gnome-authentication-agent-1',
                    'feodal-input')
        for helper in optional:
            (self.bindir / helper).unlink()
        self.env['EXPECTED_HELPERS'] = 'feodal-panel'

        result = self.run_session()

        self.assertEqual(result.returncode, 0, result.stderr)
        for helper in optional:
            self.assertIn(f'optional helper not found: {helper}', result.stderr)
        self.assertIn('openbox ', Path(self.env['CALL_LOG']).read_text())

    def test_wm_status_is_preserved_and_all_helpers_are_stopped(self):
        self.env['WM_STATUS'] = '23'

        result = self.run_session()
        log = Path(self.env['CALL_LOG']).read_text()

        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertTrue((self.directory / 'panel-stopped').exists(),
                        'session exit should stop the panel')
        for daemon in DAEMONS:
            self.assertIn(f'stopped {daemon}', log)


if __name__ == '__main__':
    unittest.main(verbosity=2)

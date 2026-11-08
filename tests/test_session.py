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


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bindir = self.directory / 'bin'
        self.bindir.mkdir()
        self.env = os.environ.copy()
        self.env.update({
            'PATH': str(self.bindir) + os.pathsep + self.env['PATH'],
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/mock-session',
            'DISPLAY': ':42',
            'XAUTHORITY': '/tmp/mock-xauthority',
            'CALL_LOG': str(self.directory / 'calls'),
            'PANEL_STOP_FILE': str(self.directory / 'panel-stopped'),
        })
        self.env.pop('DBUS_LOG', None)
        self.write_executable('feodal-panel', '''\
#!/bin/sh
trap 'printf stopped > "$PANEL_STOP_FILE"; exit 0' TERM INT
while :; do sleep 0.02; done
''')
        self.write_executable('openbox', '''\
#!/bin/sh
printf 'openbox %s\\n' "$*" >> "$CALL_LOG"
printf 'DISPLAY=%s\\nXAUTHORITY=%s\\nXDG_CURRENT_DESKTOP=%s\\nXDG_SESSION_DESKTOP=%s\\nXDG_SESSION_TYPE=%s\\n' \\
    "${DISPLAY-}" "${XAUTHORITY-}" "${XDG_CURRENT_DESKTOP-}" \\
    "${XDG_SESSION_DESKTOP-}" "${XDG_SESSION_TYPE-}" >> "$CALL_LOG"
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
                              capture_output=True, timeout=5)

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

    def test_wm_status_is_preserved_and_panel_is_stopped(self):
        self.env['WM_STATUS'] = '23'

        result = self.run_session()

        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertTrue((self.directory / 'panel-stopped').exists(),
                        'session exit should stop the panel')


if __name__ == '__main__':
    unittest.main(verbosity=2)

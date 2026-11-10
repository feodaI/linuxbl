import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'bin/feodal-lock'


class ScreenLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.bindir = self.directory / 'bin'
        self.bindir.mkdir()
        self.calls = self.directory / 'calls'
        self.env = os.environ.copy()
        self.env.update({'PATH': str(self.bindir), 'USER': 'feodal', 'LOCK_CALLS': str(self.calls)})
        self.write_executable('passwd', '''\
#!/bin/sh
printf '%s %s 2026-01-01 0 99999 7 -1\\n' "$1" "$LOCK_STATUS"
''')
        self.write_executable('i3lock', '''\
#!/bin/sh
printf '%s\\n' "$*" >> "$LOCK_CALLS"
''')

    def write_executable(self, name, content):
        path = self.bindir / name
        path.write_text(content)
        path.chmod(0o755)

    def run_lock(self, status=None, env_updates=None):
        env = self.env.copy()
        if status is not None:
            env['LOCK_STATUS'] = status
        if env_updates:
            env.update(env_updates)
        return subprocess.run([str(LOCK)], env=env, text=True, capture_output=True, timeout=5)

    def test_uses_foreground_i3lock_for_password_protected_account(self):
        result = self.run_lock('P')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().splitlines(), ['--nofork'])

    def test_skips_accounts_without_a_usable_password(self):
        for status in ('NP', 'L'):
            with self.subTest(status=status):
                result = self.run_lock(status)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('screen remains unlocked', result.stderr)
                self.assertFalse(self.calls.exists())

    def test_skips_when_password_status_cannot_be_checked(self):
        self.write_executable('passwd', '#!/bin/sh\nexit 1\n')

        result = self.run_lock()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('cannot verify', result.stderr)
        self.assertFalse(self.calls.exists())

    def test_requires_i3lock_for_password_protected_account(self):
        (self.bindir / 'i3lock').unlink()

        result = self.run_lock('P')

        self.assertEqual(result.returncode, 1)
        self.assertIn('i3lock is not installed', result.stderr)

    def test_super_l_is_bound_to_the_lock_helper(self):
        root = ET.parse(ROOT / 'config/openbox.xml').getroot()
        namespace = {'ob': 'http://openbox.org/3.4/rc'}
        binding = root.find(".//ob:keybind[@key='W-l']/ob:action/ob:command", namespace)

        self.assertIsNotNone(binding)
        self.assertEqual(binding.text, 'feodal-lock')


if __name__ == '__main__':
    unittest.main()

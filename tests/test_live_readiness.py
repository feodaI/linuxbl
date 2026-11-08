import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = (ROOT / 'scripts/check-live-session.sh').read_text().split('user_id=')[0]


class LiveReadinessTests(unittest.TestCase):
    def check_states(self, states):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            queue = base / 'states'
            queue.write_text('\n'.join(states) + '\n')
            commands = {
                'id': '#!/bin/sh\necho 0\n',
                'cat': '#!/bin/sh\necho feodal\n',
                'sleep': '#!/bin/sh\nexit 0\n',
                'systemctl': '''#!/usr/bin/env python3
import os
from pathlib import Path
path = Path(os.environ['STATE_FILE'])
lines = path.read_text().splitlines()
print(lines[0])
if len(lines) > 1:
    path.write_text('\\n'.join(lines[1:]) + '\\n')
''',
            }
            for name, source in commands.items():
                command = base / name
                command.write_text(source)
                command.chmod(0o755)
            env = {**os.environ, 'PATH': directory + os.pathsep + os.environ['PATH'],
                   'STATE_FILE': str(queue)}
            return subprocess.run(['sh', '-c', PREFIX], env=env, text=True,
                                  capture_output=True, timeout=10)

    def test_active_is_ready(self):
        self.assertEqual(self.check_states(['active']).returncode, 0)

    def test_pending_then_initializing_is_waited_for(self):
        result = self.check_states(['inactive', 'activating', 'active'])
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failure_is_not_treated_as_ready(self):
        result = self.check_states(['inactive', 'failed'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('failed', result.stderr)

    def test_wait_is_bounded(self):
        result = self.check_states(['inactive'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('timed out', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)

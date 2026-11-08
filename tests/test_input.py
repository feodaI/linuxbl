import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))

from feodal_input import (DEFAULT_LAYOUT, _XkbState, apply_layout, config_path,
                          current_group, load_layout, save_layout, toggle_group)


class FakeX11:
    def __init__(self, group=0, opened=True, get_state_status=0, lock_result=1):
        self.group = group
        self.opened = opened
        self.get_state_status = get_state_status
        self.lock_result = lock_result
        self.locked = []
        self.flushed = []
        self.closed = []

    def XOpenDisplay(self, _name):
        return 17 if self.opened else None

    def XkbGetState(self, _display, _device, state_pointer):
        if self.get_state_status == 0:
            state = state_pointer._obj
            state.group = self.group
        return self.get_state_status

    def XkbLockGroup(self, display, _device, group):
        self.locked.append((display, group))
        return self.lock_result

    def XFlush(self, display):
        self.flushed.append(display)

    def XCloseDisplay(self, display):
        self.closed.append(display)


class InputTests(unittest.TestCase):
    def test_default_and_atomic_owner_only_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'feodal/input.json'
            self.assertEqual(load_layout(path), DEFAULT_LAYOUT)
            save_layout('ua', path)
            self.assertEqual(load_layout(path), 'ua')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), {'layout': 'ua'})
            self.assertEqual(list(path.parent.glob('.input-*')), [])
            with self.assertRaises(ValueError):
                save_layout('us; touch /tmp/nope', path)

    def test_config_path_uses_only_absolute_xdg(self):
        with tempfile.TemporaryDirectory() as directory:
            with unittest.mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}):
                self.assertEqual(config_path(), Path(directory) / 'feodal/input.json')
            with unittest.mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
                self.assertEqual(config_path(), Path.home() / '.config/feodal/input.json')

    def test_malformed_or_unknown_config_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            for value in ('[', '{}', 'null', '{"layout":"bad"}'):
                path.write_text(value)
                self.assertEqual(load_layout(path), DEFAULT_LAYOUT)

    def test_apply_uses_argument_vector_and_timeout(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        apply_layout('us,ua', command_runner=runner,
                     which=lambda command: '/usr/bin/' + command, timeout=3)
        runner.assert_called_once_with(
            ['/usr/bin/setxkbmap', '-layout', 'us,ua', '-option', 'grp:alt_shift_toggle'],
            capture_output=True, text=True, timeout=3, check=False)
        runner.reset_mock()
        apply_layout('us', command_runner=runner,
                     which=lambda command: '/usr/bin/' + command)
        self.assertEqual(runner.call_args.args[0], ['/usr/bin/setxkbmap', '-layout', 'us'])

    def test_current_and_toggle_group_via_xkb(self):
        x11 = FakeX11(group=1)
        self.assertEqual(current_group('us,ua', x11=x11), 'UA')
        self.assertEqual(x11.closed, [17])
        self.assertEqual(toggle_group('us,ua', x11=x11), 'US')
        self.assertEqual(x11.locked[-1], (17, 0))
        self.assertEqual(x11.flushed, [17])
        self.assertEqual(x11.closed, [17, 17])

    def test_xkb_errors_close_display_and_single_layout_cannot_toggle(self):
        x11 = FakeX11(get_state_status=1)
        with self.assertRaisesRegex(RuntimeError, 'read'):
            current_group(x11=x11)
        self.assertEqual(x11.closed, [17])
        with self.assertRaisesRegex(RuntimeError, 'one keyboard'):
            toggle_group('us', x11=x11)
        with self.assertRaisesRegex(RuntimeError, 'X11 display'):
            current_group(x11=FakeX11(opened=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
from feodal_preferences import config_path, load_mode, save_mode, steam_command


class PreferenceTests(unittest.TestCase):
    def test_save_load_and_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'feodal/preferences.json'
            self.assertEqual(load_mode(path), 'auto')
            save_mode('nvidia', path)
            self.assertEqual(load_mode(path), 'nvidia')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            save_mode('auto', path)
            self.assertEqual(load_mode(path), 'auto')
            self.assertEqual(list(path.parent.glob('.preferences-*')), [])

    def test_invalid_config_and_untrusted_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'preferences.json'
            for data in ['[', '{}', '[]', 'null', '{"steam_gpu": "nvidia; touch /tmp/bad"}']:
                path.write_text(data)
                self.assertEqual(load_mode(path), 'auto')
            with self.assertRaises(ValueError):
                save_mode('other', path)

    def test_xdg_path(self):
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': '/tmp/feodal-test'}):
            self.assertEqual(config_path(), Path('/tmp/feodal-test/feodal/preferences.json'))
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': 'relative'}):
            self.assertEqual(config_path(), Path.home() / '.config/feodal/preferences.json')

    def test_explicit_steam_launch_modes(self):
        self.assertEqual(steam_command('auto', {'steam_available': True}), ['steam'])
        status = {'steam_available': True, 'nvidia_ready': True, 'prime_available': True}
        self.assertEqual(steam_command('nvidia', status), ['prime-run', 'steam'])
        for key in status:
            with self.subTest(key=key), self.assertRaises(ValueError):
                steam_command('nvidia', {**status, key: False})
        with self.assertRaises(ValueError):
            steam_command('unknown', status)


if __name__ == '__main__':
    unittest.main(verbosity=2)

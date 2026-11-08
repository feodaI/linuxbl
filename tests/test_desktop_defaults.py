import configparser
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class DesktopDefaultsTests(unittest.TestCase):
    def test_browser_policy_is_local_editable_and_minimal(self):
        policy = json.loads((ROOT / 'iso/overlay/airootfs/etc/firefox/policies/policies.json').read_text())
        self.assertEqual(policy, {'policies': {'Homepage': {
            'URL': 'file:///usr/share/feodal/browser/start.html',
            'Locked': False, 'StartPage': 'homepage'}}})
        self.assertTrue((ROOT / 'assets/browser/start.html').is_file())

    def test_desktop_defaults_preserve_upstream_application_ids(self):
        defaults = configparser.ConfigParser(interpolation=None)
        defaults.read(ROOT / 'config/feodal-mimeapps.list')
        for scheme in ('x-scheme-handler/http', 'x-scheme-handler/https', 'text/html'):
            self.assertEqual(defaults['Default Applications'][scheme], 'firefox.desktop')
        self.assertEqual(defaults['Default Applications']['text/plain'], 'org.xfce.mousepad.desktop')
        self.assertEqual(defaults['Default Applications']['video/mp4'], 'mpv.desktop')

    def test_browser_shortcut_and_live_package_selection(self):
        namespace = {'ob': 'http://openbox.org/3.4/rc'}
        config = ET.parse(ROOT / 'config/openbox.xml')
        self.assertEqual(config.find(".//ob:keybind[@key='W-b']/ob:action/ob:command", namespace).text,
                         'firefox')
        packages = (ROOT / 'iso/packages.desktop').read_text().splitlines()
        for package in ('firefox', 'firefox-i18n-uk', 'mousepad', 'xarchiver', 'mpv'):
            self.assertIn(package, packages)
        self.assertEqual(len(packages), len(set(packages)))
        self.assertIn('iso/packages.desktop', (ROOT / 'scripts/build-iso.sh').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)

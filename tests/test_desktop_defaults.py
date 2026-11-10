import configparser
from html.parser import HTMLParser
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
            'Locked': False, 'StartPage': 'homepage'}, 'OverrideFirstRunPage': ''}})
        self.assertTrue((ROOT / 'assets/browser/start.html').is_file())

    def test_start_page_has_no_automatic_network_resources(self):
        class Page(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, dict(attrs)))
        page = Page()
        page.feed((ROOT / 'assets/browser/start.html').read_text())
        for tag, attrs in page.tags:
            self.assertNotIn(tag, ('script', 'iframe', 'img', 'video', 'audio', 'link'))
            self.assertNotIn('src', attrs)
            self.assertNotIn('http-equiv', attrs)
        forms = [attrs for tag, attrs in page.tags if tag == 'form']
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]['action'], 'https://duckduckgo.com/')
        self.assertEqual(forms[0]['method'].lower(), 'get')
        self.assertTrue(any(tag == 'input' and attrs.get('name') == 'q' for tag, attrs in page.tags))
        css = (ROOT / 'assets/browser/start.html').read_text().split('<style>')[1].split('</style>')[0]
        self.assertNotIn('@import', css)
        self.assertNotIn('url(', css)

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

    def test_intel_gaming_stack_and_signed_multilib_are_in_iso(self):
        packages = (ROOT / 'iso/packages.desktop').read_text().splitlines()
        for package in ('steam', 'mesa', 'lib32-mesa', 'vulkan-intel', 'lib32-vulkan-intel',
                        'vulkan-icd-loader', 'lib32-vulkan-icd-loader', 'linux-headers', 'dkms'):
            self.assertIn(package, packages)
        self.assertNotIn('nvidia-open', packages)
        conf = (ROOT / 'iso/overlay/airootfs/etc/pacman.conf').read_text()
        self.assertIn('[multilib]\nInclude = /etc/pacman.d/mirrorlist', conf)
        self.assertIn('SigLevel = Required DatabaseOptional', conf)
        self.assertNotIn('TrustAll', conf)


if __name__ == '__main__':
    unittest.main(verbosity=2)

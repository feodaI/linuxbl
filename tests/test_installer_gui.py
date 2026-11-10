import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))
import feodal_installer as ui  # noqa: E402

Gtk = ui.Gtk
GB = 1000 ** 3
DISKS = [
    {'path': '/dev/sda', 'size': 32 * GB, 'model': 'USB Flash', 'transport': 'USB', 'removable': True,
     'partitions': ['ISO9660 1.8 ГБ «FEODAL»'], 'reason': 'Це носій, з якого запущено Feodal'},
    {'path': '/dev/nvme0n1', 'size': 512 * GB, 'model': 'NVMe SSD', 'transport': 'NVME', 'removable': False,
     'partitions': ['NTFS 511 ГБ «Windows»'], 'reason': None},
]


def pump(seconds=.2, until=None):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if until and until():
            return True
        time.sleep(.01)
    return bool(until and until())


class InstallerGuiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.received = self.dir / 'received.json'
        fake = self.dir / 'backend.py'
        fake.write_text(
            'import json, sys\n'
            f'open({str(self.received)!r}, "w").write(sys.stdin.read())\n'
            'for event in ({"type": "stage", "stage": "copy", "title": "Копіювання системи", "percent": 7},\n'
            '              {"type": "progress", "stage": "copy", "percent": 40},\n'
            '              {"type": "log", "text": "rsync ..."},\n'
            '              {"type": "done", "warnings": ["тест"]}):\n'
            '    print(json.dumps(event), flush=True)\n')
        os.environ['FEODAL_INSTALLER_BACKEND'] = f'{sys.executable} {fake}'
        self.window = ui.Installer(list_disks=lambda: [dict(d) for d in DISKS])
        self.addCleanup(self.window.destroy)

    def fill_user(self):
        values = {'fullname': 'Тарас Шевченко', 'password': 'kobzar1', 'password_confirm': 'kobzar1'}
        for key, value in values.items():
            self.window.entries[key].set_text(value)
        zone = self.window.timezone.get_active_id()
        self.assertTrue(zone)

    def test_wizard_flow_and_backend_payload(self):
        w = self.window
        self.assertFalse(w.back_button.get_visible())
        w.go(1)
        self.assertEqual(ui.PAGES[w.page], 'disk')
        self.assertFalse(w.next_button.get_sensitive())
        self.assertFalse(w.disk_buttons['/dev/sda'].get_sensitive())
        w.disk_buttons['/dev/nvme0n1'].set_active(True)
        self.assertEqual(w.config['disk'], '/dev/nvme0n1')
        self.assertTrue(w.next_button.get_sensitive())
        w.go(1)
        self.assertFalse(w.next_button.get_sensitive())
        self.fill_user()
        self.assertEqual(w.entries['username'].get_text(), 'taras')
        self.assertTrue(w.next_button.get_sensitive(), w.user_error.get_text())
        w.entries['password_confirm'].set_text('other')
        self.assertFalse(w.next_button.get_sensitive())
        self.assertIn('не збігаються', w.user_error.get_text())
        w.entries['password_confirm'].set_text('kobzar1')
        w.go(1)
        self.assertTrue(w.antigravity.get_active())
        w.go(1)
        self.assertEqual(ui.PAGES[w.page], 'summary')
        self.assertIn('Windows', w.erase_label.get_text())
        self.assertEqual(w.next_button.get_label(), 'Стерти диск і встановити')
        self.assertFalse(w.next_button.get_sensitive())
        w.confirm.set_active(True)
        self.assertTrue(w.next_button.get_sensitive())
        w.go(1)
        self.assertTrue(w.on_delete())  # cannot close mid-install
        self.assertTrue(pump(10, lambda: ui.PAGES[w.page] == 'finish'))
        self.assertTrue(w.finished)
        self.assertFalse(w.on_delete())
        self.assertEqual(w.next_button.get_label(), 'Перезавантажити')
        payload = json.loads(self.received.read_text())
        self.assertEqual(payload['disk'], '/dev/nvme0n1')
        self.assertEqual(payload['username'], 'taras')
        self.assertTrue(payload['antigravity'])
        self.assertNotIn('password_confirm', payload)

    def test_backend_crash_shows_error(self):
        os.environ['FEODAL_INSTALLER_BACKEND'] = f'{sys.executable} -c "import sys; sys.exit(126)"'
        w = self.window
        w.start_install()
        self.assertTrue(pump(10, lambda: ui.PAGES[w.page] == 'finish'))
        self.assertFalse(w.finished)
        self.assertIn('126', w.finish_text.get_text())

    def test_transliteration(self):
        self.assertEqual(ui.transliterate('щука юрій'), 'shchuka')


if __name__ == '__main__':
    unittest.main(verbosity=2)

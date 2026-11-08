import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
original_gdk_gl = os.environ.get('GDK_GL')
spec = importlib.util.spec_from_file_location('feodal_panel', ROOT / 'shell/feodal_panel.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Gtk, Wnck = module.Gtk, module.Wnck


def pump(seconds=.3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(.01)


class ShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wm = subprocess.Popen(['openbox', '--config-file', str(ROOT / 'config/openbox.xml')],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(.5)
        cls.shell = module.Shell()
        pump()

    @classmethod
    def tearDownClass(cls):
        if cls.shell.launcher:
            cls.shell.launcher.destroy()
        cls.shell.desktop.destroy()
        cls.shell.panel.destroy()
        cls.wm.terminate()
        cls.wm.wait(timeout=5)

    def test_gl_tuning_is_process_local(self):
        self.assertEqual(os.environ.get('GDK_GL'), original_gdk_gl)

    def test_application_search(self):
        app = module.Gio.AppInfo.create_from_commandline('xterm', 'Feodal Test Terminal', 0)
        self.assertTrue(module.matching(app, 'TEST terminal'))
        self.assertFalse(module.matching(app, 'unfindable string'))

    def test_launcher_toggle_escape(self):
        self.shell.toggle_launcher()
        pump()
        self.assertTrue(self.shell.launcher.get_visible())
        event = module.Gdk.Event.new(module.Gdk.EventType.KEY_PRESS)
        event.keyval = module.Gdk.KEY_Escape
        self.assertTrue(self.shell.launcher_key(self.shell.launcher, event))
        self.assertIsNone(self.shell.launcher)
        self.shell.toggle_launcher()
        self.shell.toggle_launcher()
        self.assertIsNone(self.shell.launcher)

    def test_real_app_launch_and_task_switch(self):
        self.shell.toggle_launcher()
        app = module.Gio.AppInfo.create_from_commandline('xterm -title FeodalSmoke -e sleep 30', 'Test', 0)
        item = type('Item', (), {'app': app})()
        self.shell.launch_app(None, item)
        pump(1)
        self.assertIsNone(self.shell.launcher)
        self.shell.screen.force_update()
        window = next((w for w in self.shell.screen.get_windows() if w.get_name() == 'FeodalSmoke'), None)
        self.assertIsNotNone(window, 'Launcher should start a real terminal: ' + repr([(w.get_name(), w.get_xid()) for w in self.shell.screen.get_windows()]))
        self.shell.refresh_tasks()
        self.assertTrue(any(b.get_label() == 'FeodalSmoke' for b in self.shell.tasks.get_children()))
        window.minimize()
        pump()
        self.shell.activate(window)
        pump()
        self.assertFalse(window.is_minimized())
        window.maximize()
        pump()
        x, y, width, height = window.get_geometry()
        self.assertLessEqual(y + height, self.shell.rect.height - 52)
        window.close(module.GdkX11.x11_get_server_time(self.shell.panel.get_window()))
        # Older libwnck cannot keep a window wrapper alive after its class group dies.
        del window
        pump()
        self.assertFalse(any(b.get_label() == 'FeodalSmoke' for b in self.shell.tasks.get_children()))

    def test_missing_program_reports_error(self):
        messages = []
        original = self.shell.error
        self.shell.error = messages.append
        try:
            self.shell.run(['feodal-nonexistent-command'])
        finally:
            self.shell.error = original
        self.assertEqual(messages, ['Програму не встановлено: feodal-nonexistent-command'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

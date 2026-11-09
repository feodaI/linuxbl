import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'shell'))
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
        if cls.shell.settings:
            cls.shell.settings.destroy()
        if cls.shell.launcher:
            cls.shell.launcher.destroy()
        cls.shell.desktop.destroy()
        cls.shell.panel.destroy()
        cls.wm.terminate()
        cls.wm.wait(timeout=5)

    def test_gl_tuning_is_process_local(self):
        self.assertEqual(os.environ.get('GDK_GL'), original_gdk_gl)

    def test_panel_browser_button_uses_official_firefox(self):
        row = self.shell.panel.get_child()
        buttons = [button for button in row.get_children()
                   if isinstance(button, Gtk.Button) and button.get_tooltip_text() == 'Firefox']
        self.assertEqual(len(buttons), 1)
        with patch.object(self.shell, 'run') as run:
            buttons[0].clicked()
            run.assert_called_once_with(['firefox'])

    def test_panel_leaves_screen_space_for_external_tray(self):
        self.shell.layout()
        self.assertEqual(self.shell.panel.get_size_request()[0], self.shell.rect.width - 166)

    def test_language_indicator_tracks_xkb_group(self):
        with patch.object(module, 'current_group', return_value=1), \
                patch.object(module, 'load_layout', return_value='us,ua'):
            self.shell.tick()
            self.assertEqual(self.shell.language.get_label(), 'UK')
        with patch.object(module, 'current_group', side_effect=RuntimeError('no display')):
            self.shell.tick()
            self.assertEqual(self.shell.language.get_label(), '—')

    def test_power_actions_require_confirmation_and_handle_denial(self):
        with patch.object(self.shell, 'confirm_power', return_value=False), \
                patch.object(module.subprocess, 'run') as run:
            self.shell.power_action('poweroff')
            self.shell.power_action('unknown')
            run.assert_not_called()
        with patch.object(self.shell, 'confirm_power', return_value=True), \
                patch.object(module.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as run, \
                patch.object(self.shell, 'error') as error:
            self.shell.power_action('reboot')
            pump()
            run.assert_called_once_with(['systemctl', 'reboot'], capture_output=True, text=True, timeout=15)
            error.assert_called_once()

    def test_application_search(self):
        app = module.Gio.AppInfo.create_from_commandline('xterm', 'Feodal Test Terminal', 0)
        self.assertTrue(module.matching(app, 'TEST terminal'))
        self.assertFalse(module.matching(app, 'unfindable string'))

    def test_launcher_closes_on_focus_loss_without_reopening(self):
        self.shell.toggle_launcher()
        pump()
        self.shell.launcher_unfocused()
        self.assertIsNone(self.shell.launcher)
        # The menu-button click that caused the focus loss must not reopen it.
        self.shell.toggle_launcher()
        self.assertIsNone(self.shell.launcher)
        self.shell.launcher_closed_at = 0

    def test_clock_shows_locale_independent_date(self):
        self.shell.tick()
        self.assertRegex(self.shell.clock.get_text(), r'^\d\d:\d\d$')
        day, rest = self.shell.date.get_text().split(', ')
        self.assertIn(day, module.WEEKDAYS)
        self.assertIn(rest.split()[1], module.MONTHS)

    def test_wallpaper_is_screen_sized_and_reloads(self):
        self.assertIsNotNone(self.shell.wallpaper)
        with patch.object(module, 'load_scaled', return_value=None):
            self.shell.reload_wallpaper()
        self.assertIsNone(self.shell.wallpaper)
        self.shell.reload_wallpaper()
        surface = self.shell.wallpaper
        self.assertGreaterEqual(surface.get_width(), self.shell.rect.width)
        self.assertGreaterEqual(surface.get_height(), self.shell.rect.height)

    def test_icon_button_falls_back_to_text(self):
        button = self.shell.icon_button('Текст', 'no-such-glyph', lambda _: None)
        self.assertEqual(button.get_label(), 'Текст')
        self.assertEqual(self.shell.icon_button('Живлення', 'power', lambda _: None).get_tooltip_text(),
                         'Живлення')

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
        self.assertLessEqual(y + height, self.shell.rect.height - module.PANEL_HEIGHT)
        window.close(module.GdkX11.x11_get_server_time(self.shell.panel.get_window()))
        # Older libwnck cannot keep a window wrapper alive after its class group dies.
        del window
        pump()
        self.assertFalse(any(b.get_label() == 'FeodalSmoke' for b in self.shell.tasks.get_children()))

    def test_diagnostics_callbacks_return_on_gtk_thread(self):
        import feodal_settings
        thread_id = threading.get_ident()
        for snapshot in ({'kernel': 'test'}, None):
            results = []
            def received(status, error):
                results.append((status, error, threading.get_ident()))
            if snapshot:
                mock = patch.object(feodal_settings, 'collect_status', return_value=snapshot)
            else:
                mock = patch.object(feodal_settings, 'collect_status', side_effect=OSError('test failure'))
            with mock:
                feodal_settings.diagnose_async(received)
                pump()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][2], thread_id)
            self.assertEqual(results[0][0], snapshot)
            self.assertEqual(bool(results[0][1]), snapshot is None)

    def test_control_center_lifecycle_and_preferences(self):
        from feodal_settings import status_text
        snapshot = {'kernel': 'test-kernel', 'memory_total_mib': 8192, 'memory_available_mib': 4096,
                    'gpus': [{'vendor': 'Intel', 'device': 'test', 'driver': 'i915'}],
                    'nvidia_ready': False, 'prime_available': False, 'steam_available': False,
                    'notes': ['Test hardware only']}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'XDG_CONFIG_HOME': directory}), \
                patch('feodal_settings.diagnose_async') as diagnose:
            self.shell.open_settings()
            center = self.shell.settings
            self.shell.open_settings()
            self.assertIs(self.shell.settings, center)
            self.assertTrue(center.busy)
            self.assertFalse(center.refresh_button.get_sensitive())
            diagnose.call_args.args[0](snapshot, None)
            self.assertIn('test-kernel', center.status_label.get_text())
            self.assertTrue(center.refresh_button.get_sensitive())
            self.assertIn('Test hardware only', status_text(snapshot))
            with patch('feodal_settings.apply_layout') as apply, patch('feodal_settings.save_layout') as save:
                center.keyboard.set_active_id('ua')
                center.apply_keyboard()
                pump()
                apply.assert_called_once_with('ua')
                save.assert_called_once_with('ua')
                self.assertIn('збережено', center.keyboard_note.get_text())
            with patch.object(self.shell, 'reload_wallpaper') as reload:
                center.apply_wallpaper(lambda: (_ for _ in ()).throw(ValueError()), 'ok')
                reload.assert_not_called()
                self.assertIn('Не вдалося', center.wallpaper_note.get_text())
                center.reset_wallpaper()
                reload.assert_called_once_with()
                self.assertIn('стандартні', center.wallpaper_note.get_text())
            center.mode.set_active_id('nvidia')
            self.assertEqual(module.load_mode(), 'nvidia')
            center.destroy()
            self.assertIsNone(self.shell.settings)
            center.received(snapshot, None)
            self.shell.open_settings()
            self.assertEqual(self.shell.settings.mode.get_active_id(), 'nvidia')
            self.shell.settings.destroy()
        pump()

    def test_steam_guard_and_async_launch(self):
        with patch.object(self.shell, 'run') as run, patch.object(self.shell, 'error') as error, \
                patch.object(module, 'load_mode', return_value='nvidia'), \
                patch.object(module, 'diagnose_async') as diagnose:
            self.shell.launch_steam()
            self.assertTrue(self.shell.steam_busy)
            self.shell.launch_steam()
            diagnose.assert_called_once()
            callback = diagnose.call_args.args[0]
            callback({'steam_available': True, 'prime_available': True, 'nvidia_ready': False}, None)
            self.assertFalse(self.shell.steam_busy)
            run.assert_not_called()
            error.assert_called_once()
            self.shell.launch_steam()
            diagnose.call_args.args[0]({'steam_available': True, 'prime_available': True, 'nvidia_ready': True}, None)
            run.assert_called_once_with(['prime-run', 'steam'])
        with patch.object(self.shell, 'run') as run, patch.object(module, 'load_mode', return_value='auto'), \
                patch.object(module.shutil, 'which', return_value='/usr/bin/steam'), \
                patch.object(module, 'diagnose_async') as diagnose:
            self.shell.launch_steam()
            run.assert_called_once_with(['steam'])
            diagnose.assert_not_called()

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

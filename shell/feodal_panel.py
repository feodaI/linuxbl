#!/usr/bin/env python3
"""Small X11 desktop shell; Openbox owns window management."""
import datetime
import os
import shutil
import subprocess
import sys
import threading

# This Cairo-only shell does not need a GL context; do not impose that on apps.
_previous_gdk_gl = os.environ.get('GDK_GL')
os.environ['GDK_GL'] = 'disable'

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
gi.require_version('Wnck', '3.0')
from gi.repository import Gdk, GdkX11, Gio, GLib, Gtk, Wnck

Gdk.init([])
if _previous_gdk_gl is None:
    os.environ.pop('GDK_GL', None)
else:
    os.environ['GDK_GL'] = _previous_gdk_gl

from feodal_preferences import load_mode, steam_command
from feodal_settings import ControlCenter, diagnose_async
from feodal_input import current_group, load_layout

STYLE = b'''
window { background: #101923; color: #e5edf5; font-family: Sans; }
button { background: #182633; color: #e5edf5; border: none; box-shadow: none;
         border-radius: 7px; padding: 8px 12px; }
button:hover { background: #294356; }
button.active { background: #27594f; color: #a6f5d5; }
entry { background: #182633; color: #e5edf5; border-color: #365164; padding: 9px; }
label.brand { color: #80dfba; font-weight: bold; }
label.muted { color: #9cabb9; }
menu, menuitem { background: #182633; color: #e5edf5; }
menuitem label { color: #e5edf5; }
menuitem:hover { background: #27594f; }
notebook, notebook > stack, viewport, scrolledwindow { background: #101923; color: #e5edf5; }
notebook > header { background: #182633; border: none; }
notebook > header > tabs > tab { background: #182633; color: #c6d3de; padding: 10px; }
notebook > header > tabs > tab:checked { background: #27594f; color: #a6f5d5; }
list, row { background: transparent; color: #e5edf5; }
row:selected, row:hover { background: #294356; }
'''


def application_list():
    return sorted((app for app in Gio.AppInfo.get_all() if app.should_show()),
                  key=lambda app: app.get_display_name().casefold())


def matching(app, query):
    return query.casefold() in (app.get_display_name() + ' ' + (app.get_description() or '')).casefold()


class Shell:
    def __init__(self):
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, 600)
        self.display = Gdk.Display.get_default()
        self.panel = Gtk.Window(title='Feodal Panel')
        self.panel.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.panel.set_decorated(False)
        self.panel.set_skip_taskbar_hint(True)
        self.panel.set_skip_pager_hint(True)
        self.panel.set_resizable(False)
        self.panel.connect('destroy', lambda _: Gio.Application.get_default().quit()
                           if Gio.Application.get_default() else None)
        row = Gtk.Box(spacing=7)
        row.set_border_width(5)
        self.panel.add(row)
        self.settings = None
        self.steam_busy = False
        self.menu_button = self.button('◈  FEODAL', self.toggle_launcher)
        row.pack_start(self.menu_button, False, False, 0)
        for label, command in [('Firefox', ['firefox']), ('Файли', ['thunar']), ('Термінал', ['xterm'])]:
            row.pack_start(self.button(label, lambda _, cmd=command: self.run(cmd)), False, False, 0)
        row.pack_start(self.button('Steam', lambda _: self.launch_steam()), False, False, 0)
        row.pack_start(self.button('Налаштування', self.open_settings), False, False, 0)
        self.tasks = Gtk.Box(spacing=4)
        task_scroll = Gtk.ScrolledWindow()
        task_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        task_scroll.add(self.tasks)
        row.pack_start(task_scroll, True, True, 4)
        self.clock = Gtk.Label()
        row.pack_end(self.button('Живлення', self.logout), False, False, 0)
        self.language = self.button('EN', self.toggle_language)
        self.language.set_tooltip_text('Перемкнути розкладку (Alt+Shift)')
        row.pack_end(self.language, False, False, 0)
        row.pack_end(self.clock, False, False, 8)
        self.launcher = None
        self.desktop = Gtk.Window(title='Feodal Desktop')
        self.desktop.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.desktop.set_decorated(False)
        self.desktop.set_skip_taskbar_hint(True)
        self.desktop.set_skip_pager_hint(True)
        canvas = Gtk.DrawingArea()
        canvas.connect('draw', self.draw_desktop)
        self.desktop.add(canvas)
        self.task_refresh_pending = False
        self.screen = Wnck.Screen.get_default()
        for signal in ['window-opened', 'window-closed', 'active-window-changed', 'active-workspace-changed']:
            self.screen.connect(signal, self.queue_tasks)
        self.screen.connect('window-opened', self.track_window)
        self.screen.force_update()
        for window in self.screen.get_windows():
            self.track_window(self.screen, window)
        self.display.connect('monitor-added', self.layout)
        self.display.connect('monitor-removed', self.layout)
        self.layout()
        self.desktop.show_all()
        self.panel.show_all()
        self.refresh_tasks()
        self.tick()
        GLib.timeout_add_seconds(1, self.tick)

    @staticmethod
    def button(label, callback):
        button = Gtk.Button(label=label)
        button.connect('clicked', callback)
        return button

    def layout(self, *_):
        monitor = self.display.get_primary_monitor() or self.display.get_monitor(0)
        rect = monitor.get_geometry()
        self.rect = rect
        self.desktop.move(rect.x, rect.y)
        self.desktop.resize(rect.width, rect.height)
        self.panel.move(rect.x, rect.y + rect.height - 52)
        # Keep the separate tray window outside this dock, independent of stacking order.
        self.panel.set_size_request(max(1, rect.width - 166), 52)

    @staticmethod
    def draw_desktop(widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        cr.set_source_rgb(.045, .075, .10)
        cr.paint()
        cr.set_source_rgba(.25, .65, .55, .08)
        for offset in range(0, width + height, 100):
            cr.move_to(offset, 0)
            cr.line_to(offset - height, height)
        cr.set_line_width(1)
        cr.stroke()
        cr.select_font_face('Sans', 0, 1)
        cr.set_font_size(62)
        cr.set_source_rgb(.50, .87, .73)
        cr.move_to(80, height * .43)
        cr.show_text('FEODAL')
        cr.set_font_size(17)
        cr.set_source_rgb(.62, .69, .74)
        cr.move_to(84, height * .43 + 38)
        cr.show_text('YOUR SPACE. LESS NOISE.')
        cr.set_font_size(13)
        cr.move_to(84, height * .43 + 74)
        cr.show_text('Super + Space  /  Apps     Super + Enter  /  Terminal')
        return False

    def error(self, message):
        dialog = Gtk.MessageDialog(transient_for=self.panel, modal=True,
                                   message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.CLOSE, text=message)
        dialog.run()
        dialog.destroy()

    def run(self, command):
        if not shutil.which(command[0]):
            self.error(f'Програму не встановлено: {command[0]}')
            return
        try:
            subprocess.Popen(command, start_new_session=True)
        except OSError as exc:
            self.error(str(exc))

    def open_settings(self, *_):
        if self.settings is None:
            self.settings = ControlCenter(self)
        self.settings.present()

    def launch_steam(self):
        if self.steam_busy:
            return
        self.steam_busy = True
        mode = load_mode()

        def ready(status, error):
            self.steam_busy = False
            if error:
                self.error(error)
                return
            try:
                command = steam_command(mode, status)
            except ValueError as exc:
                self.error(str(exc))
                return
            self.run(command)

        if mode == 'auto':
            ready({'steam_available': bool(shutil.which('steam'))}, None)
        else:
            diagnose_async(ready)

    def toggle_launcher(self, *_):
        if self.launcher:
            self.launcher.destroy()
            return
        self.launcher = Gtk.Window(title='Програми — Feodal')
        self.launcher.set_default_size(460, 460)
        self.launcher.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.launcher.set_skip_taskbar_hint(True)
        self.launcher.connect('destroy', self.launcher_closed)
        self.launcher.connect('key-press-event', self.launcher_key)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_border_width(18)
        self.launcher.add(box)
        title = Gtk.Label(label='Програми', xalign=0)
        title.get_style_context().add_class('brand')
        box.pack_start(title, False, False, 0)
        search = Gtk.SearchEntry(placeholder_text='Знайти програму…')
        box.pack_start(search, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box.pack_start(scroll, True, True, 0)
        listing = Gtk.ListBox()
        scroll.add(listing)
        for app in application_list():
            item = Gtk.ListBoxRow()
            item.app = app
            content = Gtk.Box(spacing=12)
            content.set_border_width(8)
            icon = app.get_icon()
            if icon:
                content.pack_start(Gtk.Image.new_from_gicon(icon, Gtk.IconSize.LARGE_TOOLBAR), False, False, 0)
            content.pack_start(Gtk.Label(label=app.get_display_name(), xalign=0), True, True, 0)
            item.add(content)
            listing.add(item)
        listing.set_filter_func(lambda item: matching(item.app, search.get_text()))
        search.connect('search-changed', lambda _: listing.invalidate_filter())
        listing.connect('row-activated', self.launch_app)
        search.connect('activate', lambda _: self.launch_first(listing))
        self.launcher.move(self.rect.x + 12, self.rect.y + max(0, self.rect.height - 540))
        self.launcher.show_all()
        self.launcher.present()
        search.grab_focus()

    def launch_first(self, listing):
        for item in listing.get_children():
            if item.get_child_visible():
                self.launch_app(listing, item)
                break

    def launch_app(self, _, item):
        try:
            context = self.display.get_app_launch_context()
            item.app.launch([], context)
            self.launcher.destroy()
        except GLib.Error as exc:
            self.error(str(exc))

    def launcher_closed(self, *_):
        self.launcher = None

    def launcher_key(self, _, event):
        if event.keyval == Gdk.KEY_Escape:
            self.launcher.destroy()
            return True
        return False

    def track_window(self, _, window):
        for signal in ['name-changed', 'state-changed', 'workspace-changed']:
            window.connect(signal, self.queue_tasks)

    def queue_tasks(self, *_):
        if not self.task_refresh_pending:
            self.task_refresh_pending = True
            GLib.idle_add(self.refresh_tasks)

    def refresh_tasks(self, *_):
        self.task_refresh_pending = False
        for child in self.tasks.get_children():
            child.destroy()
        active = self.screen.get_active_window()
        workspace = self.screen.get_active_workspace()
        for window in self.screen.get_windows():
            if window.is_skip_tasklist() or (workspace and not window.is_on_workspace(workspace)):
                continue
            name = window.get_name() or 'Вікно'
            xid = window.get_xid()
            button = self.button(name[:22], lambda _, target=xid: self.activate_id(target))
            button.set_tooltip_text(name)
            if window == active:
                button.get_style_context().add_class('active')
            self.tasks.pack_start(button, False, False, 0)
        self.tasks.show_all()

    def activate_id(self, xid):
        window = Wnck.Window.get(xid)
        if window:
            self.activate(window)

    def activate(self, window):
        timestamp = Gtk.get_current_event_time() or GdkX11.x11_get_server_time(self.panel.get_window())
        if window.is_active():
            window.minimize()
        else:
            window.activate(timestamp)

    def tick(self):
        now = datetime.datetime.now()
        self.clock.set_text(now.strftime('%H:%M'))
        self.clock.set_tooltip_text(now.strftime('%d.%m.%Y'))
        try:
            group = current_group()
            layouts = load_layout().split(',')
            layout = layouts[group] if group < len(layouts) else '?'
            self.language.set_label({'us': 'EN', 'ua': 'UK'}.get(layout, '—'))
        except (OSError, RuntimeError):
            self.language.set_label('—')
        return True

    def toggle_language(self, *_):
        from feodal_input import toggle_group
        try:
            toggle_group(load_layout())
            self.tick()
        except (OSError, RuntimeError, ValueError):
            self.error('Не вдалося перемкнути розкладку. Обери дві мови в налаштуваннях.')

    def confirm_power(self, action):
        labels = {'logout': 'Завершити сеанс', 'reboot': 'Перезавантажити', 'poweroff': 'Вимкнути'}
        dialog = Gtk.MessageDialog(transient_for=self.panel, modal=True,
                                   message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.OK_CANCEL,
                                   text=labels[action] + '? Збережи відкриті документи.')
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def power_action(self, action):
        commands = {'logout': ['openbox', '--exit'], 'reboot': ['systemctl', 'reboot'],
                    'poweroff': ['systemctl', 'poweroff']}
        if action not in commands or not self.confirm_power(action):
            return
        def work():
            try:
                result = subprocess.run(commands[action], capture_output=True, text=True, timeout=15)
                message = 'Дію відхилено системою. Перевір дозволи та відкриті програми.' if result.returncode else None
            except (OSError, subprocess.TimeoutExpired):
                message = 'Не вдалося виконати дію живлення.'
            if message:
                GLib.idle_add(lambda: (self.error(message), False)[1])
        threading.Thread(target=work, daemon=True, name='feodal-power').start()

    def logout(self, *_):
        menu = Gtk.Menu()
        for action, label in [('logout', 'Вийти із сеансу'), ('reboot', 'Перезавантажити'),
                              ('poweroff', 'Вимкнути комп’ютер')]:
            item = Gtk.MenuItem(label=label)
            item.connect('activate', lambda _, choice=action: self.power_action(choice))
            menu.append(item)
        menu.show_all()
        menu.popup_at_widget(self.panel, Gdk.Gravity.NORTH_EAST, Gdk.Gravity.SOUTH_EAST, None)


def main():
    if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        sys.exit('Feodal currently requires an X11 session.')
    # A per-user application instance also handles the global launcher shortcut.
    app = Gtk.Application(application_id='org.feodal.Shell', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    state = {}

    def command_line(application, invocation):
        if 'shell' not in state:
            state['shell'] = Shell()
            application.hold()
        if '--settings' in invocation.get_arguments():
            state['shell'].open_settings()
        if '--launcher' in invocation.get_arguments():
            state['shell'].toggle_launcher()
        return 0

    app.connect('command-line', command_line)
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())

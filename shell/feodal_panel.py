#!/usr/bin/env python3
"""Small X11 desktop shell; Openbox owns window management."""
import ctypes
import datetime
import os
import shutil
import subprocess
import sys
import threading

import cairo

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
from feodal_wallpaper import load_scaled

PANEL_HEIGHT = 40
TRAY_RESERVE = 166
# Shared with stalonetrayrc and the desktop strip behind the tray.
PANEL_RGB = (0x15 / 255, 0x18 / 255, 0x1d / 255)

STYLE = b'''
* { font-family: "Noto Sans", "DejaVu Sans", Sans; outline-color: alpha(#6fd3a8, .5); }
window { background: #111317; color: #e6e8eb; }
window.panel { background: #15181d; border-top: 1px solid #242930; }
window.popup { background: #15181d; border: 1px solid #2a3038; }
button { background: transparent; background-image: none; color: #d7dbe0; border: none;
         box-shadow: none; text-shadow: none; -gtk-icon-shadow: none;
         border-radius: 8px; padding: 6px 12px; min-height: 0; min-width: 0; }
button:hover { background: #22272e; }
button:active, button:checked { background: #2a3038; }
button:disabled { color: #5c636c; }
window.panel button { padding: 4px 9px; }
button.icon { padding: 4px 8px; color: #b9c0c8; }
button.icon:hover { color: #ffffff; }
button.menu { padding: 4px 12px; }
button.menu label { color: #6fd3a8; font-weight: bold; letter-spacing: 1px; }
button.task { color: #8f98a3; padding: 4px 10px; border-radius: 6px;
              border-bottom: 2px solid transparent; }
button.task:hover { color: #e6e8eb; }
button.task.active { color: #f2f4f6; background: #1f242b; border-bottom-color: #6fd3a8; }
button.pill { border: 1px solid #2c323b; padding: 2px 8px; font-size: 8.5pt; font-weight: bold; }
button.action { background: #1f242b; border: 1px solid #2a3038; }
button.action:hover { background: #262c34; border-color: #3a424c; }
label.clock { font-weight: bold; }
label.date, label.muted, label.hint { color: #8a939e; }
label.date { font-size: 8pt; }
label.brand { color: #6fd3a8; font-weight: bold; letter-spacing: 1px; }
label.title { font-size: 13pt; font-weight: bold; }
separator.panel-sep { background: #2a3038; min-width: 1px; margin: 9px 4px; }
entry { background: #1b1f25; color: #e6e8eb; border: 1px solid #2a3038; border-radius: 8px;
        box-shadow: none; padding: 8px 10px; caret-color: #6fd3a8; }
entry:focus { border-color: #6fd3a8; }
combobox button, combobox box { background: #1b1f25; border-radius: 8px; }
menu, .menu, .context-menu { background: #1b1f25; color: #e6e8eb; border: 1px solid #2a3038; padding: 4px; }
menuitem { padding: 7px 14px; border-radius: 6px; }
menuitem label { color: #e6e8eb; }
menuitem:hover { background: #262c34; }
tooltip, tooltip.background { background: #1b1f25; color: #e6e8eb; border: 1px solid #2a3038; }
notebook, notebook > stack, viewport, scrolledwindow { background: #111317; color: #e6e8eb; border: none; }
notebook > header { background: #111317; border: none; border-bottom: 1px solid #242930; }
notebook > header > tabs > tab { background: transparent; color: #8a939e; padding: 8px 14px;
                                 border: none; box-shadow: none; }
notebook > header > tabs > tab:hover { color: #e6e8eb; }
notebook > header > tabs > tab:checked { color: #f2f4f6; box-shadow: inset 0 -2px #6fd3a8; }
list, row { background: transparent; color: #e6e8eb; }
row { border-radius: 8px; }
row:hover { background: #1f242b; }
row:selected { background: #1d3830; }
notebook button { background: #1b1f25; border: 1px solid #2a3038; padding: 8px 12px; }
notebook button:hover { background: #242a32; border-color: #3a424c; }
scrollbar { background: transparent; border: none; }
scrollbar slider { background: #2f353e; border-radius: 4px; min-width: 4px; min-height: 4px; }
'''

# Panel glyphs are drawn with Cairo: loading the SVG icon theme costs ~17 MiB RSS.
def _glyph_browser(cr):
    cr.arc(9, 9, 6.5, 0, 6.2832)
    cr.move_to(2.5, 9)
    cr.line_to(15.5, 9)
    cr.move_to(9, 2.5)
    cr.curve_to(5.5, 6, 5.5, 12, 9, 15.5)
    cr.move_to(9, 2.5)
    cr.curve_to(12.5, 6, 12.5, 12, 9, 15.5)


def _glyph_files(cr):
    cr.move_to(2.5, 5)
    cr.line_to(7, 5)
    cr.line_to(8.5, 6.5)
    cr.line_to(15.5, 6.5)
    cr.line_to(15.5, 14)
    cr.line_to(2.5, 14)
    cr.close_path()


def _glyph_terminal(cr):
    cr.rectangle(2.5, 3.5, 13, 11)
    cr.move_to(5.5, 7)
    cr.line_to(7.5, 9)
    cr.line_to(5.5, 11)
    cr.move_to(9, 11)
    cr.line_to(12.5, 11)


def _glyph_games(cr):
    cr.move_to(5.5, 5.5)
    cr.line_to(12.5, 5.5)
    cr.curve_to(15.5, 5.5, 17, 13.5, 14.5, 13.5)
    cr.curve_to(12.5, 13.5, 12, 11, 9, 11)
    cr.curve_to(6, 11, 5.5, 13.5, 3.5, 13.5)
    cr.curve_to(1, 13.5, 2.5, 5.5, 5.5, 5.5)
    cr.close_path()
    cr.move_to(4.5, 8.5)
    cr.line_to(7.5, 8.5)
    cr.move_to(6, 7)
    cr.line_to(6, 10)
    cr.move_to(12.8, 8.5)
    cr.arc(12, 8.5, .8, 0, 6.2832)


def _glyph_settings(cr):
    for y, knob in ((5, 11.5), (9, 6), (13, 10)):
        cr.move_to(2.5, y)
        cr.line_to(15.5, y)
        cr.move_to(knob + 1.6, y)
        cr.arc(knob, y, 1.6, 0, 6.2832)


def _glyph_power(cr):
    cr.arc(9, 9.5, 6, -1.0, 4.14)
    cr.move_to(9, 2.5)
    cr.line_to(9, 8.5)


GLYPHS = {'browser': _glyph_browser, 'files': _glyph_files, 'terminal': _glyph_terminal,
          'games': _glyph_games, 'settings': _glyph_settings, 'power': _glyph_power}


def draw_glyph(widget, cr, name):
    width, height = widget.get_allocated_width(), widget.get_allocated_height()
    color = widget.get_style_context().get_color(widget.get_state_flags())
    cr.translate((width - 18) // 2, (height - 18) // 2)
    cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
    cr.set_line_width(1.5)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    GLYPHS[name](cr)
    cr.stroke()
    return False


def release_free_memory():
    """Return freed image-decoder heap to the OS (glibc only; no-op elsewhere)."""
    try:
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except (OSError, AttributeError):
        pass


# Independent of the live system's locale.
WEEKDAYS = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'нд')
MONTHS = ('січ', 'лют', 'бер', 'кві', 'тра', 'чер', 'лип', 'сер', 'вер', 'жов', 'лис', 'гру')


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
        self.panel.get_style_context().add_class('panel')
        row = Gtk.Box(spacing=2)
        row.set_border_width(4)
        self.panel.add(row)
        self.settings = None
        self.steam_busy = False
        self.launcher_closed_at = 0
        self.menu_button = self.button('feodal', self.toggle_launcher)
        self.menu_button.get_style_context().add_class('menu')
        self.menu_button.set_tooltip_text('Програми (Super+Space)')
        row.pack_start(self.menu_button, False, False, 0)
        row.pack_start(self.separator(), False, False, 0)
        for label, icon, command in [('Firefox', 'browser', ['firefox']), ('Файли', 'files', ['thunar']),
                                     ('Термінал', 'terminal', ['xterm'])]:
            row.pack_start(self.icon_button(label, icon, lambda _, cmd=command: self.run(cmd)), False, False, 0)
        row.pack_start(self.icon_button('Steam', 'games', lambda _: self.launch_steam()), False, False, 0)
        row.pack_start(self.separator(), False, False, 0)
        self.tasks = Gtk.Box(spacing=2)
        task_scroll = Gtk.ScrolledWindow()
        task_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        task_scroll.add(self.tasks)
        row.pack_start(task_scroll, True, True, 4)
        row.pack_end(self.icon_button('Живлення', 'power', self.logout), False, False, 0)
        row.pack_end(self.icon_button('Налаштування', 'settings', self.open_settings), False, False, 0)
        clock_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        clock_box.set_valign(Gtk.Align.CENTER)
        self.clock = Gtk.Label(xalign=1)
        self.clock.get_style_context().add_class('clock')
        self.date = Gtk.Label(xalign=1)
        self.date.get_style_context().add_class('date')
        clock_box.pack_start(self.clock, False, False, 0)
        clock_box.pack_start(self.date, False, False, 0)
        row.pack_end(clock_box, False, False, 10)
        self.language = self.button('EN', self.toggle_language)
        self.language.get_style_context().add_class('pill')
        self.language.set_valign(Gtk.Align.CENTER)
        self.language.set_tooltip_text('Перемкнути розкладку (Alt+Shift)')
        row.pack_end(self.language, False, False, 4)
        self.launcher = None
        self.desktop = Gtk.Window(title='Feodal Desktop')
        self.desktop.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.desktop.set_decorated(False)
        self.desktop.set_skip_taskbar_hint(True)
        self.desktop.set_skip_pager_hint(True)
        self.wallpaper = None
        self.wallpaper_size = None
        self.wallpaper_offset = (0, 0)
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

    @staticmethod
    def separator():
        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        separator.get_style_context().add_class('panel-sep')
        return separator

    @classmethod
    def icon_button(cls, label, icon, callback):
        if icon not in GLYPHS:
            return cls.button(label, callback)
        button = Gtk.Button()
        glyph = Gtk.DrawingArea()
        glyph.set_size_request(20, 22)
        glyph.connect('draw', draw_glyph, icon)
        button.add(glyph)
        button.set_tooltip_text(label)
        button.get_accessible().set_name(label)
        button.get_style_context().add_class('icon')
        button.connect('clicked', callback)
        return button

    def layout(self, *_):
        monitor = self.display.get_primary_monitor() or self.display.get_monitor(0)
        rect = monitor.get_geometry()
        self.rect = rect
        self.desktop.move(rect.x, rect.y)
        self.desktop.resize(rect.width, rect.height)
        self.panel.move(rect.x, rect.y + rect.height - PANEL_HEIGHT)
        # Keep the separate tray window outside this dock, independent of stacking order.
        self.panel.set_size_request(max(1, rect.width - TRAY_RESERVE), PANEL_HEIGHT)
        if (rect.width, rect.height) != self.wallpaper_size:
            self.reload_wallpaper()

    def reload_wallpaper(self):
        width, height = self.rect.width, self.rect.height
        self.wallpaper_size = (width, height)
        pixbuf = load_scaled(width, height)
        self.wallpaper, self.wallpaper_offset = None, (0, 0)
        if pixbuf:
            # Copy into a plain RGB24 surface and drop the pixbuf. Gdk.cairo_surface_create_from_pixbuf
            # measured ~66 MiB extra RSS on first use; this path costs about the image size.
            self.wallpaper = cairo.ImageSurface(cairo.FORMAT_RGB24, pixbuf.get_width(), pixbuf.get_height())
            cr = cairo.Context(self.wallpaper)
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
            cr.paint()
            self.wallpaper_offset = ((width - pixbuf.get_width()) / 2, (height - pixbuf.get_height()) / 2)
            del pixbuf, cr
            release_free_memory()
        self.desktop.queue_draw()

    def draw_desktop(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        if self.wallpaper:
            cr.set_source_surface(self.wallpaper, *self.wallpaper_offset)
        else:
            cr.set_source_rgb(.067, .075, .09)
        cr.paint()
        # Panel-coloured strip behind the external tray, so the bar reads as one piece.
        cr.set_source_rgb(*PANEL_RGB)
        cr.rectangle(0, height - PANEL_HEIGHT, width, PANEL_HEIGHT)
        cr.fill()
        cr.set_source_rgb(.141, .161, .188)
        cr.rectangle(0, height - PANEL_HEIGHT, width, 1)
        cr.fill()
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
        # Clicking the menu button first unfocuses (and closes) the popup; don't reopen it.
        if GLib.get_monotonic_time() - self.launcher_closed_at < 250000:
            return
        self.launcher = Gtk.Window(title='Програми — Feodal')
        self.launcher.set_default_size(420, 500)
        self.launcher.set_decorated(False)
        self.launcher.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.launcher.set_skip_taskbar_hint(True)
        self.launcher.set_skip_pager_hint(True)
        self.launcher.set_keep_above(True)
        self.launcher.get_style_context().add_class('popup')
        self.launcher.connect('destroy', self.launcher_closed)
        self.launcher.connect('key-press-event', self.launcher_key)
        self.launcher.connect('focus-out-event', self.launcher_unfocused)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(14)
        self.launcher.add(box)
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
            content.set_border_width(7)
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
        footer = Gtk.Box(spacing=6)
        hint = Gtk.Label(label='Enter — запуск   Esc — закрити', xalign=0)
        hint.get_style_context().add_class('hint')
        footer.pack_start(hint, True, True, 0)
        for label, icon, callback in [('Налаштування', 'settings', self.open_settings),
                                      ('Живлення', 'power', self.logout)]:
            footer.pack_end(self.icon_button(label, icon, lambda button, cb=callback: self.from_launcher(cb, button)),
                            False, False, 0)
        box.pack_end(footer, False, False, 0)
        self.launcher.move(self.rect.x + 6, self.rect.y + max(0, self.rect.height - PANEL_HEIGHT - 506))
        self.launcher.show_all()
        self.launcher.present()
        search.grab_focus()

    def from_launcher(self, callback, button):
        self.launcher.destroy()
        callback(button)

    def launcher_unfocused(self, *_):
        if self.launcher:
            self.launcher.destroy()
            self.launcher_closed_at = GLib.get_monotonic_time()
        return False

    def launch_first(self, listing):
        for item in listing.get_children():
            if item.get_child_visible():
                self.launch_app(listing, item)
                break

    def launch_app(self, _, item):
        try:
            context = self.display.get_app_launch_context()
            item.app.launch([], context)
            if self.launcher:
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
            button = self.button(name if len(name) <= 24 else name[:23] + '…',
                                 lambda _, target=xid: self.activate_id(target))
            button.set_tooltip_text(name)
            button.get_style_context().add_class('task')
            icon = window.get_mini_icon()
            if icon:
                button.set_image(Gtk.Image.new_from_pixbuf(icon))
                button.set_always_show_image(True)
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
        self.date.set_text(f'{WEEKDAYS[now.weekday()]}, {now.day} {MONTHS[now.month - 1]}')
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

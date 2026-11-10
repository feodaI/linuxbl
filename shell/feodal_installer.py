#!/usr/bin/env python3
"""Feodal graphical installer (runs as the live user; the root backend runs via pkexec)."""
import json
import os
import shlex
import subprocess
import sys
import threading

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk

import feodal_antigravity
import feodal_installer_core as core
from feodal_install_backend import STAGES
from feodal_style import STYLE

BACKEND = ['pkexec', '/usr/lib/feodal/feodal-install-backend']
PAGES = ('welcome', 'disk', 'user', 'apps', 'summary', 'progress', 'finish')
STEP_TITLES = ('Вітання', 'Диск', 'Користувач', 'Програми', 'Підтвердження', 'Встановлення', 'Готово')


def backend_command():
    override = os.environ.get('FEODAL_INSTALLER_BACKEND')
    return shlex.split(override) if override else BACKEND


def label(text, *classes, wrap=True, xalign=0):
    widget = Gtk.Label(label=text, xalign=xalign)
    widget.set_line_wrap(wrap)
    widget.set_max_width_chars(70)
    for name in classes:
        widget.get_style_context().add_class(name)
    return widget


def styled(widget, *classes):
    for name in classes:
        widget.get_style_context().add_class(name)
    return widget


class Installer(Gtk.Window):
    def __init__(self, list_disks=None):
        super().__init__(title='Встановлення Feodal')
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, 600)
        self.set_default_size(880, 580)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('delete-event', self.on_delete)
        self.list_disks = list_disks or (lambda: core.disk_choices(core.lsblk_tree(), core.live_boot_disk()))
        self.config = {'disk': None, 'antigravity': True, 'locale': 'uk_UA.UTF-8'}
        self.disks = []
        self.running = False
        self.finished = False
        self.username_edited = False
        self.page = 0
        self.process = None
        self.zones = core.timezones()

        root = Gtk.Box()
        self.add(root)
        sidebar = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2), 'sidebar')
        sidebar.set_size_request(200, -1)
        brand = label('feodal', 'brand')
        brand.set_margin_start(22)
        brand.set_margin_bottom(18)
        sidebar.pack_start(brand, False, False, 0)
        self.step_labels = []
        for title in STEP_TITLES:
            step = label(title, 'step', wrap=False)
            self.step_labels.append(step)
            sidebar.pack_start(step, False, False, 0)
        root.pack_start(sidebar, False, False, 0)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.pack_start(main, True, True, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
        main.pack_start(self.stack, True, True, 0)
        footer = Gtk.Box(spacing=8)
        footer.set_border_width(18)
        self.back_button = Gtk.Button(label='Назад')
        self.back_button.connect('clicked', lambda _: self.go(-1))
        self.next_button = styled(Gtk.Button(label='Далі'), 'primary')
        self.next_button.connect('clicked', lambda _: self.go(1))
        footer.pack_start(self.back_button, False, False, 0)
        footer.pack_end(self.next_button, False, False, 0)
        main.pack_end(footer, False, False, 0)

        for name in PAGES:
            builder = getattr(self, f'page_{name}')
            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
            page.set_border_width(30)
            builder(page)
            self.stack.add_named(page, name)
        self.page = 0
        self.show_all()
        self.show_page(0)

    # ---- pages ----------------------------------------------------------
    def heading(self, page, title, lead):
        page.pack_start(label(title, 'title'), False, False, 0)
        page.pack_start(label(lead, 'lead'), False, False, 0)

    def page_welcome(self, page):
        self.heading(page, 'Встановлення Feodal на диск',
                     'Feodal скопіює цю live-систему на внутрішній диск: темна панель, Firefox, файли, '
                     'термінал і центр керування — те саме, що ти бачиш зараз, але з твоїм обліковим записом '
                     'і збереженням файлів.')
        card = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), 'card')
        for line in ('Потрібно: диск від 20 ГБ, 64-бітний ПК (UEFI або BIOS), Secure Boot вимкнено.',
                     'Обраний диск буде стерто повністю — встановлення поруч із Windows поки не підтримується.',
                     'Інтернет потрібен лише для Google Antigravity; без нього система встановиться.',
                     'Тривалість: зазвичай 5–15 хвилин, залежно від швидкості флешки й диска.'):
            card.pack_start(label('•  ' + line), False, False, 0)
        page.pack_start(card, False, False, 0)
        self.live_note = label('', 'error')
        page.pack_start(self.live_note, False, False, 0)
        if not core.is_live() and not os.environ.get('FEODAL_INSTALLER_BACKEND'):
            self.live_note.set_text('Інсталятор працює лише із завантаженого live ISO Feodal.')

    def page_disk(self, page):
        self.heading(page, 'Куди встановити?',
                     'Обери диск. Усі розділи на ньому буде видалено й створено нові.')
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.disk_list = Gtk.ListBox()
        self.disk_list.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.add(self.disk_list)
        page.pack_start(scroll, True, True, 0)
        refresh = Gtk.Button(label='Оновити список')
        refresh.connect('clicked', lambda _: self.refresh_disks())
        refresh.set_halign(Gtk.Align.START)
        page.pack_start(refresh, False, False, 0)

    def refresh_disks(self):
        for child in self.disk_list.get_children():
            child.destroy()
        try:
            self.disks = self.list_disks()
        except (OSError, ValueError, subprocess.SubprocessError):
            self.disks = []
        group = None
        self.disk_buttons = {}
        for disk in self.disks:
            row = styled(Gtk.ListBoxRow(activatable=False), 'disk')
            box = Gtk.Box(spacing=12)
            box.set_border_width(8)
            radio = Gtk.RadioButton.new_from_widget(group)
            group = group or radio
            radio.set_sensitive(disk['reason'] is None)
            radio.connect('toggled', self.disk_toggled, disk['path'])
            self.disk_buttons[disk['path']] = radio
            box.pack_start(radio, False, False, 0)
            text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            kind = ' · '.join(filter(None, [disk['transport'], 'знімний' if disk['removable'] else '']))
            text.pack_start(label(f'{disk["model"]} — {core.human_size(disk["size"])}', 'clock'), False, False, 0)
            text.pack_start(label(f'{disk["path"]}' + (f'  ·  {kind}' if kind else ''), 'muted'), False, False, 0)
            parts = ', '.join(disk['partitions']) or 'порожній, без розділів'
            text.pack_start(label(f'Зараз: {parts}', 'muted'), False, False, 0)
            if disk['reason']:
                text.pack_start(label(disk['reason'], 'warning'), False, False, 0)
            box.pack_start(text, True, True, 0)
            row.add(box)
            self.disk_list.add(row)
        if not self.disks:
            self.disk_list.add(label('Дисків не знайдено.', 'warning'))
        # A radio group always has one active member; start with nothing chosen.
        self.config['disk'] = None
        if group:
            hidden = Gtk.RadioButton.new_from_widget(group)
            hidden.set_active(True)
            self.hidden_radio = hidden
        self.disk_list.show_all()
        self.update_buttons()

    def disk_toggled(self, button, path):
        if button.get_active():
            self.config['disk'] = path
        self.update_buttons()

    def page_user(self, page):
        self.heading(page, 'Твій обліковий запис',
                     'Цим логіном і паролем ти входитимеш у систему та підтверджуватимеш дії адміністратора.')
        grid = Gtk.Grid(column_spacing=14, row_spacing=10)
        self.entries = {}
        fields = (('fullname', 'Ім’я', 'Наприклад, Тарас', False),
                  ('username', 'Логін', 'малими латинськими, напр. taras', False),
                  ('password', 'Пароль', '', True),
                  ('password_confirm', 'Повтори пароль', '', True),
                  ('hostname', 'Назва комп’ютера', 'feodal', False))
        for row, (key, title, hint, secret) in enumerate(fields):
            grid.attach(label(title, 'lead', wrap=False, xalign=1), 0, row, 1, 1)
            entry = Gtk.Entry(placeholder_text=hint, visibility=not secret, hexpand=True)
            entry.connect('changed', self.user_changed)
            self.entries[key] = entry
            grid.attach(entry, 1, row, 1, 1)
        self.entries['hostname'].set_text('feodal')
        self.entries['fullname'].connect('changed', self.suggest_username)
        grid.attach(label('Часовий пояс', 'lead', wrap=False, xalign=1), 0, 5, 1, 1)
        self.timezone = Gtk.ComboBoxText()
        for zone in self.zones:
            self.timezone.append(zone, zone)
        self.timezone.set_active_id(core.default_timezone(self.zones))
        self.timezone.connect('changed', self.user_changed)
        grid.attach(self.timezone, 1, 5, 1, 1)
        grid.attach(label('Мова системи', 'lead', wrap=False, xalign=1), 0, 6, 1, 1)
        self.locale = Gtk.ComboBoxText()
        for value, title in core.LOCALES.items():
            self.locale.append(value, title)
        self.locale.set_active_id('uk_UA.UTF-8')
        self.locale.connect('changed', self.user_changed)
        grid.attach(self.locale, 1, 6, 1, 1)
        page.pack_start(grid, False, False, 0)
        self.user_error = label('', 'warning')
        page.pack_start(self.user_error, False, False, 0)

    def suggest_username(self, entry):
        if self.username_edited:
            return
        latin = ''.join(ch for ch in transliterate(entry.get_text().lower()) if ch.isascii() and ch.isalnum())[:20]
        if latin:
            self.entries['username'].set_text(latin if latin[0].isalpha() else 'u' + latin)

    def user_changed(self, widget=None):
        if widget is self.entries.get('username') and widget.has_focus():
            self.username_edited = True
        for key, entry in self.entries.items():
            self.config[key] = entry.get_text()
        self.config['timezone'] = self.timezone.get_active_id() if hasattr(self, 'timezone') else ''
        self.config['locale'] = self.locale.get_active_id() if hasattr(self, 'locale') else 'uk_UA.UTF-8'
        self.update_buttons()

    def user_problems(self):
        return core.validate_user(self.config)

    def page_apps(self, page):
        self.heading(page, 'Додаткові програми', 'Встановлюються одразу у твій обліковий запис.')
        card = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), 'card')
        self.antigravity = Gtk.CheckButton(label=f'Google Antigravity {feodal_antigravity.VERSION}')
        self.antigravity.set_active(True)
        self.antigravity.connect('toggled', lambda b: self.config.__setitem__('antigravity', b.get_active()))
        card.pack_start(self.antigravity, False, False, 0)
        card.pack_start(label(
            f'Агентне середовище розробки від Google. Завантажиться з офіційного сервера Google '
            f'(~{feodal_antigravity.SIZE // 1000000} МБ) і буде перевірене за контрольною сумою. '
            f'Це пропрієтарна програма Google; користуючись нею, ти приймаєш умови {feodal_antigravity.TERMS}. '
            'Вхід — через твій обліковий запис Google.', 'muted'), False, False, 0)
        page.pack_start(card, False, False, 0)
        self.network_note = label('', 'warning')
        page.pack_start(self.network_note, False, False, 0)
        page.pack_start(label('Firefox, файловий менеджер, термінал, редактор, архіватор і медіаплеєр '
                              'уже входять у систему.', 'muted'), False, False, 0)

    def page_summary(self, page):
        self.heading(page, 'Перевір і підтвердь', 'Після натискання кнопки скасувати вже не вийде.')
        self.summary = styled(Gtk.Grid(column_spacing=18, row_spacing=7), 'card')
        page.pack_start(self.summary, False, False, 0)
        notice = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), 'notice')
        self.erase_label = label('', 'error')
        notice.pack_start(self.erase_label, False, False, 0)
        self.confirm = Gtk.CheckButton(label='Я розумію, що всі дані на цьому диску буде безповоротно стерто')
        self.confirm.connect('toggled', lambda _: self.update_buttons())
        notice.pack_start(self.confirm, False, False, 0)
        page.pack_start(notice, False, False, 0)

    def fill_summary(self):
        for child in self.summary.get_children():
            child.destroy()
        disk = next((d for d in self.disks if d['path'] == self.config['disk']), None)
        rows = (('Диск', f'{disk["model"]}, {core.human_size(disk["size"])} ({disk["path"]})' if disk else '—'),
                ('Розмітка', 'GPT: EFI 512 МБ (FAT32) + система на решті диска (ext4)'),
                ('Завантажувач', 'GRUB для UEFI та BIOS'),
                ('Користувач', f'{self.config.get("fullname") or self.config.get("username")} '
                               f'({self.config.get("username")}), адміністратор через sudo'),
                ('Комп’ютер', self.config.get('hostname', '')),
                ('Мова / пояс', f'{core.LOCALES.get(self.config.get("locale"), "")} · {self.config.get("timezone")}'),
                ('Програми', f'Google Antigravity {feodal_antigravity.VERSION}' if self.config['antigravity']
                 else 'лише базові'))
        for row, (key, value) in enumerate(rows):
            self.summary.attach(label(key, 'muted', wrap=False), 0, row, 1, 1)
            self.summary.attach(label(value), 1, row, 1, 1)
        parts = ', '.join(disk['partitions']) if disk and disk['partitions'] else 'розділів немає'
        self.erase_label.set_text(f'Буде стерто весь диск {self.config["disk"]}: {parts}.')
        self.confirm.set_active(False)
        self.summary.show_all()

    def page_progress(self, page):
        self.heading(page, 'Встановлення…', 'Не вимикай комп’ютер і не виймай флешку.')
        self.stage_label = label('Підготовка', 'clock')
        page.pack_start(self.stage_label, False, False, 0)
        self.bar = Gtk.ProgressBar()
        page.pack_start(self.bar, False, False, 0)
        self.percent = label('0%', 'muted')
        page.pack_start(self.percent, False, False, 0)
        steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.stage_rows = {}
        for stage, title, _, _ in STAGES:
            row = label('○  ' + title, 'muted', wrap=False)
            self.stage_rows[stage] = (row, title)
            steps.pack_start(row, False, False, 0)
        page.pack_start(steps, False, False, 0)
        expander = Gtk.Expander(label='Журнал')
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(130)
        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        scroll.add(self.log_view)
        expander.add(scroll)
        page.pack_start(expander, True, True, 0)

    def page_finish(self, page):
        self.finish_title = label('', 'title')
        page.pack_start(self.finish_title, False, False, 0)
        self.finish_text = label('', 'lead')
        page.pack_start(self.finish_text, False, False, 0)
        self.finish_card = styled(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8), 'card')
        page.pack_start(self.finish_card, False, False, 0)

    # ---- navigation -----------------------------------------------------
    def show_page(self, index):
        self.page = index
        name = PAGES[index]
        self.stack.set_visible_child_name(name)
        for number, step in enumerate(self.step_labels):
            context = step.get_style_context()
            for state in ('current', 'done'):
                context.remove_class(state)
            if number == index:
                context.add_class('current')
            elif number < index:
                context.add_class('done')
        if name == 'disk' and not self.disks:
            self.refresh_disks()
        if name == 'apps':
            monitor = Gio.NetworkMonitor.get_default()
            self.network_note.set_text('' if monitor.get_network_available() else
                                       'Зараз немає мережі: Antigravity буде пропущено, його можна '
                                       'встановити пізніше командою feodal-antigravity install.')
        if name == 'summary':
            self.fill_summary()
        self.update_buttons()

    def update_buttons(self):
        if not hasattr(self, 'next_button'):
            return
        name = PAGES[self.page]
        self.back_button.set_visible(name not in ('welcome', 'progress', 'finish'))
        self.next_button.set_visible(name != 'progress')
        context = self.next_button.get_style_context()
        context.remove_class('danger')
        context.add_class('primary')
        label_text, sensitive = 'Далі', True
        if name == 'welcome':
            sensitive = not self.live_note.get_text()
        elif name == 'disk':
            sensitive = bool(self.config.get('disk'))
        elif name == 'user':
            problems = self.user_problems()
            shown = [message for field, message in problems if self.config.get(field) or field == 'password'
                     and self.config.get('password_confirm')]
            self.user_error.set_text(shown[0] if shown else '')
            sensitive = not problems
        elif name == 'summary':
            label_text, sensitive = 'Стерти диск і встановити', self.confirm.get_active()
            context.remove_class('primary')
            context.add_class('danger')
        elif name == 'finish':
            label_text = 'Перезавантажити' if self.finished else 'Закрити'
        self.next_button.set_label(label_text)
        self.next_button.set_sensitive(sensitive)

    def go(self, step):
        name = PAGES[self.page]
        if step > 0 and name == 'summary':
            self.start_install()
            return
        if step > 0 and name == 'finish':
            if self.finished:
                subprocess.Popen(['systemctl', 'reboot'])
            self.destroy()
            return
        self.show_page(max(0, min(len(PAGES) - 1, self.page + step)))

    def on_delete(self, *_):
        return self.running  # never close the window mid-install

    # ---- running the backend -------------------------------------------
    def start_install(self):
        self.running = True
        self.show_page(PAGES.index('progress'))
        payload = json.dumps({key: self.config.get(key) for key in (
            'disk', 'fullname', 'username', 'password', 'hostname', 'timezone', 'locale', 'antigravity')})
        try:
            self.process = subprocess.Popen(backend_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as exc:
            self.handle({'type': 'error', 'message': f'Не вдалося запустити встановлення: {exc}', 'log': ''})
            return
        threading.Thread(target=self.pump, args=(payload,), daemon=True, name='feodal-installer').start()

    def pump(self, payload):
        result = None
        try:
            self.process.stdin.write(payload)
            self.process.stdin.close()
            for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    event = {'type': 'log', 'text': line.rstrip()}
                if event.get('type') in ('done', 'error'):
                    result = event
                GLib.idle_add(self.handle, event)
        finally:
            self.process.stdout.close()
            code = self.process.wait()
            if result is None:
                GLib.idle_add(self.handle, {'type': 'error', 'log': '',
                                            'message': 'Встановлення перервано або доступ не надано '
                                                       f'(код {code}).'})

    def append_log(self, text):
        buffer = self.log_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), text + '\n')
        self.log_view.scroll_to_iter(buffer.get_end_iter(), 0, False, 0, 1)

    def handle(self, event):
        kind = event.get('type')
        if kind == 'log':
            self.append_log(event.get('text', ''))
        elif kind == 'stage':
            seen = True
            for stage, (row, title) in self.stage_rows.items():
                context = row.get_style_context()
                if stage == event['stage']:
                    row.set_text('●  ' + title)
                    context.remove_class('muted')
                    seen = False
                elif seen:
                    row.set_text('✓  ' + title)
                    context.remove_class('muted')
                    context.add_class('stage-done')
            self.stage_label.set_text(event.get('title', ''))
            self.set_percent(event.get('percent', 0))
        elif kind == 'progress':
            self.set_percent(event.get('percent', 0))
        elif kind in ('done', 'error'):
            self.running = False
            self.finished = kind == 'done'
            self.show_finish(event)
        return False

    def set_percent(self, value):
        self.bar.set_fraction(value / 100)
        self.percent.set_text(f'{value:.0f}%')

    def show_finish(self, event):
        for child in self.finish_card.get_children():
            child.destroy()
        if self.finished:
            self.finish_title.set_text('Feodal встановлено')
            self.finish_text.set_text('Перезавантаж комп’ютер і вийми флешку. Після запуску GRUB введи '
                                      f'логін {self.config.get("username")} і пароль — робочий стіл відкриється сам.')
            lines = ['Пароль адміністратора — це твій пароль (sudo).',
                     'Журнал встановлення: /var/log/feodal-installer.log']
            lines += ['Увага: ' + text for text in event.get('warnings', [])]
        else:
            self.finish_title.set_text('Встановлення не вдалося')
            self.finish_text.set_text(event.get('message', ''))
            lines = ['Диск міг бути частково змінений. Live-система працює як і раніше.']
            if event.get('log'):
                lines.append(f'Подробиці: {event["log"]}')
        for line in lines:
            self.finish_card.pack_start(label(line, 'warning' if line.startswith('Увага') else 'muted'),
                                        False, False, 0)
        self.finish_card.show_all()
        self.show_page(PAGES.index('finish'))


TABLE = str.maketrans({'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'ie',
                       'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'i', 'к': 'k', 'л': 'l',
                       'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
                       'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '',
                       'ю': 'iu', 'я': 'ia', '’': '', "'": ''})


def transliterate(text):
    return text.translate(TABLE).split(' ')[0]


def main():
    window = Installer()
    window.connect('destroy', Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == '__main__':
    sys.exit(main())

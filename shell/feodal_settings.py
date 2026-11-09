"""On-demand GTK control center; no resident background service."""
import threading

from gi.repository import GLib, Gtk

from feodal_hardware import collect_status
from feodal_preferences import load_mode, save_mode
from feodal_input import load_layout, apply_layout, save_layout
from feodal_wallpaper import reset_user_wallpaper, set_user_wallpaper

GUIDE = '''ДЛЯ MX330 / INTEL / 8 ГБ

MX330 належить до Pascal. nvidia-open для неї не підходить.
Для пропрієтарного драйвера потрібна сумісна legacy-гілка 580xx,
заголовки поточного ядра та відповідні 32-бітні бібліотеки.
Пакети AUR перевіряй і збирай вручну як звичайний користувач.
Цей центр не встановлює драйвери й не змінює конфігурацію Xorg.

STEAM

В Arch потрібен увімкнений multilib і 32-бітні графічні бібліотеки
для обраного драйвера. Steam встановлюється окремо через pacman.
Не змішуй бібліотеки різних гілок NVIDIA. Після встановлення
перезапусти діагностику, а перед зміною GPU повністю закрий Steam.
Налаштування тут діє лише на кнопку Steam у панелі й центрі керування,
а не на довільний запуск із меню програм чи автозапуск.

ІГРИ

Dota 2 має нативну Linux-версію. Для GTA V Legacy Story Mode
потрібен Proton. GTA Online має обмеження BattlEye під Linux.
Для конкретної гри в Steam можна окремо задати prime-run %command%
після налаштування драйвера та PRIME. Це не обхід античіта.

ПОЧАТКОВІ НАЛАШТУВАННЯ

Спробуй 1280×720 та низькі налаштування. Зменшення фонових
навантажень і zram не гарантують вищого FPS. Не замінюй основну ОС
цим live-прототипом без резервної копії та перевірки обладнання.'''


def diagnose_async(callback):
    def work():
        try:
            status, error = collect_status(), None
        except Exception:
            status, error = None, 'Не вдалося прочитати стан обладнання. Спробуй ще раз.'
        GLib.idle_add(deliver, status, error)

    def deliver(status, error):
        callback(status, error)
        return False

    threading.Thread(target=work, daemon=True, name='feodal-diagnostics').start()


def status_text(status):
    total = status['memory_total_mib']
    available = status['memory_available_mib']
    memory = f'{available} / {total} МіБ доступно' if total else 'недоступно'
    lines = [f"Ядро Linux: {status['kernel']}", f'Оперативна пам’ять: {memory}', '', 'Графічні пристрої:']
    vendors = {'0x8086': 'Intel', '0x10de': 'NVIDIA', '0x1002': 'AMD', '0x1234': 'QEMU'}
    for gpu in status['gpus']:
        gpu = {**gpu, 'vendor': vendors.get(gpu['vendor'].lower(), gpu['vendor'])}
        lines.append(f"  {gpu['vendor']} · {gpu['device']} · драйвер: {gpu['driver'] or 'не прив’язаний'}")
    if not status['gpus']:
        lines.append('  Не визначено. Це не підтвердження відсутності GPU.')
    for label, key in [('NVIDIA відповідає', 'nvidia_ready'), ('prime-run встановлено', 'prime_available'),
                       ('Steam встановлено', 'steam_available')]:
        lines.append(f"{label}: {'так' if status[key] else 'ні'}")
    lines += ['', 'Перевірка NVIDIA не є тестом Vulkan, PRIME або FPS.']
    lines += status['notes']
    return '\n'.join(lines)


class ControlCenter(Gtk.Window):
    def __init__(self, shell):
        super().__init__(title='Центр керування — Feodal')
        self.shell = shell
        self.closed = False
        self.busy = False
        self.set_default_size(720, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', self.on_destroy)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_border_width(18)
        self.add(outer)
        heading = Gtk.Label(label='Центр керування', xalign=0)
        heading.get_style_context().add_class('title')
        outer.pack_start(heading, False, False, 0)
        notebook = Gtk.Notebook()
        outer.pack_start(notebook, True, True, 0)
        self.status_label = Gtk.Label(xalign=0, yalign=0, selectable=True)
        self.status_label.set_line_wrap(True)
        self.status_label.set_max_width_chars(74)
        status_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        status_page.set_border_width(14)
        status_page.pack_start(self.scrolled(self.status_label), True, True, 0)
        self.refresh_button = shell.button('Перевірити обладнання', self.refresh)
        status_page.pack_end(self.refresh_button, False, False, 0)
        notebook.append_page(status_page, Gtk.Label(label='Система'))
        gaming = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        gaming.set_border_width(14)
        gaming.pack_start(self.label('Запуск Steam із панелі Feodal'), False, False, 0)
        self.mode = Gtk.ComboBoxText()
        self.mode.append('auto', 'Звичайний запуск — без примусового вибору GPU')
        self.mode.append('nvidia', 'NVIDIA / PRIME — лише з робочим драйвером')
        self.mode.set_active_id(load_mode())
        gaming.pack_start(self.mode, False, False, 0)
        self.saved = self.label('Не змінює драйвери, ядро чи глобальний режим графіки.')
        gaming.pack_start(self.saved, False, False, 0)
        self.mode.connect('changed', self.save)
        gaming.pack_start(shell.button('Запустити Steam', lambda _: shell.launch_steam()), False, False, 0)
        gaming.pack_start(self.label('Перед зміною GPU повністю закрий уже запущений Steam.\n'
                                    'Діагностика запускається лише на запит і може пробудити NVIDIA.'), False, False, 0)
        notebook.append_page(gaming, Gtk.Label(label='Ігри / GPU'))
        tools = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        tools.set_border_width(14)
        for title, command in [('Firefox', ['firefox']), ('Редактор текстів', ['mousepad']),
                               ('Архіви', ['xarchiver']), ('Медіаплеєр', ['mpv', '--player-operation-mode=pseudo-gui']),
                               ('Звук', ['pavucontrol']), ('Мережеві з’єднання', ['nm-connection-editor']),
                               ('Файли', ['thunar']), ('Термінал', ['xterm'])]:
            tools.pack_start(shell.button(title, lambda _, cmd=command: shell.run(cmd)), False, False, 0)
        notebook.append_page(self.scrolled(tools), Gtk.Label(label='Інструменти'))
        desktop = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        desktop.set_border_width(14)
        desktop.pack_start(self.label('Розкладка клавіатури'), False, False, 0)
        self.keyboard = Gtk.ComboBoxText()
        for value, title in [('us,ua', 'English + Українська — Alt+Shift'), ('us', 'English'), ('ua', 'Українська')]:
            self.keyboard.append(value, title)
        self.keyboard.set_active_id(load_layout())
        desktop.pack_start(self.keyboard, False, False, 0)
        self.apply_input_button = shell.button('Застосувати розкладку', self.apply_keyboard)
        desktop.pack_start(self.apply_input_button, False, False, 0)
        self.keyboard_note = self.label('Alt+Shift перемикає дві розкладки; налаштування зберігаються для користувача.')
        desktop.pack_start(self.keyboard_note, False, False, 0)
        for title, command in [('Екран і роздільність', ['arandr']),
                               ('Живлення, батарея та яскравість', ['xfce4-power-manager-settings']),
                               ('Знімок екрана', ['xfce4-screenshooter']),
                               ('Перевірити сповіщення', ['notify-send', 'Feodal', 'Сповіщення працюють.'])]:
            desktop.pack_start(shell.button(title, lambda _, cmd=command: shell.run(cmd)), False, False, 0)
        desktop.pack_start(self.label('Шпалери'), False, False, 0)
        wallpaper_row = Gtk.Box(spacing=8)
        wallpaper_row.pack_start(shell.button('Обрати зображення…', self.choose_wallpaper), True, True, 0)
        wallpaper_row.pack_start(shell.button('Стандартні', self.reset_wallpaper), True, True, 0)
        desktop.pack_start(wallpaper_row, False, False, 0)
        self.wallpaper_note = self.label('Стандартні: «Bridge medieval fantasy city», David Revoy / Blender '
                                         'Foundation, CC BY 3.0.')
        desktop.pack_start(self.wallpaper_note, False, False, 0)
        desktop.pack_start(self.label('Яскравість і батарея доступні лише за підтримки обладнання.\n'
                                     'Сон і закриття кришки потребують перевірки на ноутбуці.\n'
                                     'Блокування екрана ще не налаштоване — не вважай сон захистом.'), False, False, 0)
        notebook.append_page(self.scrolled(desktop), Gtk.Label(label='Робочий стіл'))
        guide = self.label(GUIDE)
        guide.set_selectable(True)
        guide.set_margin_start(14)
        guide.set_margin_end(14)
        guide.set_margin_top(14)
        notebook.append_page(self.scrolled(guide), Gtk.Label(label='Підготовка ігор'))
        outer.pack_end(shell.button('Закрити', lambda _: self.destroy()), False, False, 0)
        self.show_all()
        self.refresh()

    @staticmethod
    def label(text):
        label = Gtk.Label(label=text, xalign=0, yalign=0)
        label.set_line_wrap(True)
        label.set_max_width_chars(74)
        return label

    @staticmethod
    def scrolled(widget):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(widget)
        return scroll

    def apply_keyboard(self, *_):
        self.apply_input_button.set_sensitive(False)
        layout = self.keyboard.get_active_id()
        def done(message):
            if not self.closed:
                self.apply_input_button.set_sensitive(True)
                self.keyboard_note.set_text(message)
            return False
        def work():
            try:
                apply_layout(layout)
                save_layout(layout)
                message = 'Розкладку застосовано й збережено.'
            except (OSError, ValueError, RuntimeError):
                message = 'Не вдалося застосувати або зберегти розкладку. Перевір X11 та права доступу.'
            GLib.idle_add(done, message)
        threading.Thread(target=work, daemon=True, name='feodal-input').start()

    def choose_wallpaper(self, *_):
        dialog = Gtk.FileChooserDialog(title='Обрати шпалери', transient_for=self,
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons('Скасувати', Gtk.ResponseType.CANCEL, 'Обрати', Gtk.ResponseType.ACCEPT)
        images = Gtk.FileFilter()
        images.set_name('Зображення')
        images.add_pixbuf_formats()
        dialog.add_filter(images)
        path = dialog.get_filename() if dialog.run() == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if path:
            self.apply_wallpaper(lambda: set_user_wallpaper(path), 'Шпалери змінено.')

    def reset_wallpaper(self, *_):
        self.apply_wallpaper(reset_user_wallpaper, 'Повернено стандартні шпалери.')

    def apply_wallpaper(self, change, message):
        try:
            change()
        except (OSError, ValueError, GLib.Error):
            self.wallpaper_note.set_text('Не вдалося встановити зображення. Обери PNG або JPEG.')
            return
        self.shell.reload_wallpaper()
        self.wallpaper_note.set_text(message)

    def save(self, *_):
        try:
            save_mode(self.mode.get_active_id())
            self.saved.set_text('Збережено. Діє на наступний запуск Steam через Feodal.')
        except (OSError, ValueError):
            self.saved.set_text('Не вдалося зберегти. Перевір доступ до каталогу налаштувань.')

    def refresh(self, *_):
        if self.busy or self.closed:
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.status_label.set_text('Читаю стан системи…')
        diagnose_async(self.received)

    def received(self, status, error):
        self.busy = False
        if self.closed:
            return
        self.refresh_button.set_sensitive(True)
        self.status_label.set_text(error if error else status_text(status))

    def on_destroy(self, *_):
        self.closed = True
        self.shell.settings = None

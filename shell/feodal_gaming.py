#!/usr/bin/env python3
"""Safe Arch Linux gaming setup helper."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


OFFICIAL_PACKAGES = (
    'steam', 'mesa', 'lib32-mesa', 'vulkan-intel', 'lib32-vulkan-intel',
)
NVIDIA_PASCAL_PACKAGES = (
    'nvidia-580xx-dkms', 'nvidia-580xx-utils', 'lib32-nvidia-580xx-utils',
)


def multilib_enabled(pacman_conf='/etc/pacman.conf'):
    """Return whether an active multilib section includes its mirror list."""
    section = None
    has_include = False
    try:
        lines = Path(pacman_conf).read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError):
        return False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(('#', ';')):
            continue
        if stripped.startswith('[') and stripped.endswith(']'):
            if section == 'multilib' and has_include:
                return True
            section = stripped[1:-1].strip()
            has_include = False
        elif section == 'multilib' and stripped.startswith('Include'):
            key, separator, value = stripped.partition('=')
            has_include = bool(separator and key.strip() == 'Include' and value.strip())
    return section == 'multilib' and has_include


def graphics_devices(pci_path='/sys/bus/pci/devices'):
    """Return graphics-controller vendor/device IDs without probing the GPU."""
    devices = []
    try:
        entries = sorted(Path(pci_path).iterdir())
    except OSError:
        return devices
    for entry in entries:
        try:
            pci_class = int((entry / 'class').read_text(encoding='ascii').strip(), 16)
            vendor = (entry / 'vendor').read_text(encoding='ascii').strip().lower()
            device = (entry / 'device').read_text(encoding='ascii').strip().lower()
        except (OSError, UnicodeError, ValueError):
            continue
        if pci_class >> 16 == 0x03:
            devices.append({'vendor': vendor, 'device': device})
    return devices


def _status(pacman_conf, pci_path, which, output):
    devices = graphics_devices(pci_path)
    vendors = {device['vendor'].removeprefix('0x') for device in devices}
    output('Feodal — ігрова підготовка Arch Linux')
    output(f"Multilib: {'увімкнено' if multilib_enabled(pacman_conf) else 'не підтверджено'}")
    output(f"Steam: {'знайдено' if which('steam') else 'не встановлено'}")
    if '8086' in vendors:
        output('Intel GPU знайдено; рекомендовано залишити її основним GPU.')
    if '10de' in vendors:
        output('NVIDIA GPU знайдено; точну модель автоматично не визначено.')
        output('Для MX330/Pascal див. інструкцію: nvidia-open не підтримує Pascal.')
    if not devices:
        output('PCI GPU не знайдено або доступ до sysfs відсутній.')
    output('Для безпечного встановлення офіційного Steam/Intel набору: feodal-gaming install')
    return 0


def install_official(*, arch_linux, multilib, which=shutil.which,
                     runner=subprocess.run, confirm=input, output=print):
    """Install repository packages only, after environment checks and consent."""
    if not arch_linux:
        output('Ця команда призначена лише для Arch Linux.')
        return 2
    if not multilib:
        output('Спочатку вручну увімкніть [multilib] у /etc/pacman.conf та оновіть систему.')
        output('Інструкція: https://wiki.archlinux.org/title/Official_repositories#multilib')
        return 2
    if not which('pacman') or not which('sudo'):
        output('Потрібні pacman і sudo; жодних змін не виконано.')
        return 2
    output('Будуть встановлені лише офіційні пакети: ' + ' '.join(OFFICIAL_PACKAGES))
    output('AUR-драйвер NVIDIA не встановлюється і не змінюється.')
    try:
        answer = confirm('Продовжити повне оновлення та встановлення? [y/N] ')
    except (EOFError, OSError):
        answer = ''
    if answer.strip().lower() not in {'y', 'yes', 'т', 'так'}:
        output('Скасовано; система не змінена.')
        return 1
    try:
        result = runner(
            ['sudo', 'pacman', '-Syu', '--needed', *OFFICIAL_PACKAGES], check=False
        )
    except OSError as error:
        output(f'Не вдалося запустити pacman: {error}')
        return 1
    return result.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description='Безпечна підготовка Arch Linux до ігор')
    parser.add_argument('command', nargs='?', choices=('status', 'install'), default='status')
    args = parser.parse_args(argv)
    pacman_conf = '/etc/pacman.conf'
    if args.command == 'status':
        return _status(pacman_conf, '/sys/bus/pci/devices', shutil.which, print)
    return install_official(
        arch_linux=Path('/etc/arch-release').is_file(),
        multilib=multilib_enabled(pacman_conf),
    )


if __name__ == '__main__':
    sys.exit(main())

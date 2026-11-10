"""Install plan and disk logic for the Feodal installer. No GTK; safe to import anywhere."""
import json
import os
from pathlib import Path
import re
import subprocess

MIN_DISK_BYTES = 20 * 1000 ** 3
ISO_LABEL = 'FEODAL'
LIVE_MARKERS = (Path('/run/archiso/bootmnt'), Path('/run/archiso/airootfs'), Path('/run/archiso/sfs/airootfs'))
SOURCE_CANDIDATES = (Path('/run/archiso/airootfs'), Path('/run/archiso/sfs/airootfs'))
USERNAME = re.compile(r'^[a-z_][a-z0-9_-]{0,31}$')
HOSTNAME = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$')
RESERVED_USERS = {'root', 'bin', 'daemon', 'mail', 'ftp', 'http', 'nobody', 'dbus', 'polkitd', 'git',
                  'avahi', 'colord', 'rtkit', 'uuidd', 'systemd-network', 'systemd-resolve',
                  'systemd-timesync', 'systemd-journal-remote', 'systemd-coredump', 'systemd-oom',
                  'alpm', 'tss', 'usbmux', 'nm-openconnect', 'nm-openvpn', 'qemu', 'brltty', 'dnsmasq'}
LOCALES = {'uk_UA.UTF-8': 'Українська', 'en_US.UTF-8': 'English (US)'}


def is_live():
    return any(path.exists() for path in LIVE_MARKERS)


def live_source():
    for path in SOURCE_CANDIDATES:
        if (path / 'usr/bin/bash').exists() and (path / 'etc/os-release').exists():
            return path
    return None


def human_size(size):
    for unit in ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ'):
        if size < 1000 or unit == 'ТБ':
            return f'{size:.0f} {unit}' if unit == 'Б' else f'{size:.1f} {unit}'.replace('.0 ', ' ')
        size /= 1000


def partition_path(disk, number):
    # Kernel naming: nvme0n1 -> nvme0n1p2, mmcblk0 -> mmcblk0p2, sda -> sda2.
    return f'{disk}p{number}' if disk[-1].isdigit() else f'{disk}{number}'


def lsblk_tree(runner=subprocess.run):
    result = runner(['lsblk', '--json', '--bytes', '-o',
                     'NAME,PATH,SIZE,MODEL,TRAN,TYPE,RO,RM,FSTYPE,LABEL,MOUNTPOINTS'],
                    capture_output=True, text=True, check=True)
    return json.loads(result.stdout).get('blockdevices', [])


def _walk(device):
    yield device
    for child in device.get('children') or ():
        yield from _walk(child)


def _mountpoints(device):
    points = device.get('mountpoints')
    if points is None and device.get('mountpoint'):
        points = [device['mountpoint']]
    return [point for point in points or () if point]


def describe_partitions(device):
    parts = []
    for child in device.get('children') or ():
        label = child.get('label') or ''
        kind = (child.get('fstype') or 'невідомо').upper()
        size = human_size(int(child.get('size') or 0))
        parts.append(f'{kind} {size}' + (f' «{label}»' if label else ''))
    return parts


def disk_choices(tree, live_disk=None):
    """Whole disks with a reason string when they may not be used."""
    disks = []
    for device in tree:
        if device.get('type') != 'disk' or device['name'].startswith(('zram', 'loop', 'sr', 'fd')):
            continue
        size = int(device.get('size') or 0)
        nodes = list(_walk(device))
        reason = None
        if device.get('path') == live_disk or any(node.get('label') == ISO_LABEL for node in nodes):
            reason = 'Це носій, з якого запущено Feodal'
        elif str(device.get('ro')) in ('1', 'True', 'true'):
            reason = 'Диск лише для читання'
        elif size < MIN_DISK_BYTES:
            reason = f'Замалий: потрібно щонайменше {human_size(MIN_DISK_BYTES)}'
        elif any(_mountpoints(node) for node in nodes):
            reason = 'Розділи диска зараз змонтовані'
        disks.append({
            'path': device['path'],
            'size': size,
            'model': (device.get('model') or '').strip() or 'Диск',
            'transport': (device.get('tran') or '').upper(),
            'removable': str(device.get('rm')) in ('1', 'True', 'true'),
            'partitions': describe_partitions(device),
            'reason': reason,
        })
    return disks


def live_boot_disk(runner=subprocess.run):
    try:
        source = runner(['findmnt', '-no', 'SOURCE', '/run/archiso/bootmnt'],
                        capture_output=True, text=True).stdout.strip()
        if not source:
            return None
        parent = runner(['lsblk', '-no', 'PKNAME', source], capture_output=True, text=True).stdout.strip()
        return f'/dev/{parent}' if parent else source
    except OSError:
        return None


def validate_user(config):
    """Return a list of (field, message) problems; empty when valid."""
    if not isinstance(config, dict):
        return [('config', 'Некоректні налаштування користувача')]
    problems = []
    username = config.get('username', '')
    if not isinstance(username, str) or not USERNAME.fullmatch(username):
        problems.append(('username', 'Логін: малі латинські літери, цифри, _ або -, з літери'))
    elif username in RESERVED_USERS:
        problems.append(('username', 'Цей логін зайнятий системою'))
    password = config.get('password', '')
    if not isinstance(password, str) or len(password) < 4:
        problems.append(('password', 'Пароль має містити щонайменше 4 символи'))
    elif password != config.get('password_confirm', password):
        problems.append(('password', 'Паролі не збігаються'))
    elif any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in password):
        problems.append(('password', 'Пароль не може містити керівні символи'))
    hostname = config.get('hostname', '')
    if not isinstance(hostname, str) or not HOSTNAME.fullmatch(hostname):
        problems.append(('hostname', 'Назва комп’ютера: латинські літери, цифри та дефіс'))
    fullname = config.get('fullname', '')
    if not isinstance(fullname, str) or ':' in fullname or \
            any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in fullname):
        problems.append(('fullname', 'Ім’я не може містити керівні символи або двокрапку'))
    timezone = config.get('timezone', '')
    try:
        valid_timezone = isinstance(timezone, str) and timezone and '..' not in timezone and \
            not timezone.startswith('/') and (Path('/usr/share/zoneinfo') / timezone).is_file()
    except (OSError, ValueError):
        valid_timezone = False
    if not valid_timezone:
        problems.append(('timezone', 'Невідомий часовий пояс'))
    if config.get('locale') not in LOCALES:
        problems.append(('locale', 'Невідома мова системи'))
    return problems


def timezones():
    try:
        import zoneinfo
        zones = sorted(zone for zone in zoneinfo.available_timezones()
                       if '/' in zone and not zone.startswith(('Etc/', 'SystemV/', 'posix/', 'right/')))
    except Exception:
        zones = []
    return zones or ['Europe/Kyiv', 'UTC']


def default_timezone(zones):
    for zone in ('Europe/Kyiv', 'Europe/Kiev'):
        if zone in zones:
            return zone
    return zones[0]


def mounted_under(disk, runner=subprocess.run):
    tree = lsblk_tree(runner)
    for device in tree:
        if device.get('path') == disk:
            return [point for node in _walk(device) for point in _mountpoints(node)]
    raise ValueError(f'Диск не знайдено: {disk}')

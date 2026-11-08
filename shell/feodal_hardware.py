#!/usr/bin/env python3
"""Read-only hardware status snapshot for the Feodal settings center."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _read_memory(meminfo_path, notes):
    values = {'MemTotal': 0, 'MemAvailable': 0}
    found = set()
    try:
        lines = Path(meminfo_path).read_text(encoding='ascii').splitlines()
    except (OSError, UnicodeError):
        notes.append('Дані про оперативну пам’ять недоступні.')
        return values['MemTotal'], values['MemAvailable']

    for line in lines:
        key, separator, raw_value = line.partition(':')
        if not separator or key not in values:
            continue
        try:
            kib = int(raw_value.split()[0])
        except (IndexError, ValueError):
            continue
        values[key] = kib // 1024
        found.add(key)

    for key in values:
        if key not in found:
            notes.append(f'Значення {key} недоступне.')
    return values['MemTotal'], values['MemAvailable']


def _gpu_info(device_path):
    try:
        pci_class = (device_path / 'class').read_text(encoding='ascii').strip()
        vendor = (device_path / 'vendor').read_text(encoding='ascii').strip()
        device = (device_path / 'device').read_text(encoding='ascii').strip()
    except (OSError, UnicodeError):
        return None

    try:
        if int(pci_class, 16) >> 16 != 0x03:
            return None
    except ValueError:
        return None

    driver_link = device_path / 'driver'
    try:
        driver = driver_link.resolve().name if driver_link.is_symlink() else ''
    except OSError:
        driver = ''
    return {'vendor': vendor, 'device': device, 'driver': driver}


def _gpu_devices(drm_path, pci_path):
    devices = {}
    for root, pattern in ((pci_path, '*'), (drm_path, 'card[0-9]*')):
        try:
            entries = sorted(Path(root).glob(pattern))
        except OSError:
            continue
        for entry in entries:
            if pattern != '*' and (not entry.name.startswith('card') or
                                   not entry.name[4:].isdigit()):
                continue
            device_path = entry / 'device' if pattern != '*' else entry
            info = _gpu_info(device_path)
            if info is None:
                continue
            try:
                key = str(device_path.resolve())
            except OSError:
                key = str(device_path.absolute())
            devices.setdefault(key, info)
    return list(devices.values())


def _command_available(which, command):
    try:
        return bool(which(command))
    except (OSError, TypeError, ValueError):
        return False


def _nvidia_smi_works(which, command_runner, notes):
    executable = None
    try:
        executable = which('nvidia-smi')
    except (OSError, TypeError, ValueError):
        pass
    if not executable:
        notes.append('Команда nvidia-smi недоступна.')
        return False

    notes.append('Опитування NVIDIA може вивести GPU зі стану сну.')
    try:
        result = command_runner(
            [executable, '--query-gpu=name,driver_version', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.SubprocessError):
        notes.append('nvidia-smi не завершила перевірку успішно.')
        return False
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    if (result.returncode != 0 or not rows or
            any(len(row.split(',', 1)) != 2 or not all(part.strip() for part in row.split(',', 1))
                for row in rows)):
        notes.append('nvidia-smi не підтвердила роботу драйвера NVIDIA.')
        return False
    return True


def collect_status(meminfo_path='/proc/meminfo', drm_path='/sys/class/drm',
                   which=shutil.which, command_runner=subprocess.run,
                   pci_path='/sys/bus/pci/devices'):
    """Return a non-privileged snapshot of memory, display devices and launch tools."""
    notes = []
    memory_total, memory_available = _read_memory(meminfo_path, notes)
    gpus = _gpu_devices(drm_path, pci_path)
    if not gpus:
        notes.append('GPU не знайдено в DRM або PCI sysfs.')

    nvidia_devices = [gpu for gpu in gpus
                      if gpu['vendor'].lower().removeprefix('0x') == '10de']
    if any(gpu['device'].lower().removeprefix('0x') in {'1d16', '1d18'}
           for gpu in nvidia_devices):
        notes.append('Ця старіша відеокарта NVIDIA може потребувати драйвера гілки 580xx.')
    bound_nvidia = any(gpu['driver'] == 'nvidia' for gpu in nvidia_devices)
    if nvidia_devices and not bound_nvidia:
        notes.append('Драйвер NVIDIA не прив’язаний до пристрою; nvidia-smi не перевірялася.')
    nvidia_ready = (bound_nvidia and _nvidia_smi_works(which, command_runner, notes))
    prime_available = _command_available(which, 'prime-run')
    steam_available = _command_available(which, 'steam')

    return {
        'kernel': os.uname().release,
        'memory_total_mib': memory_total,
        'memory_available_mib': memory_available,
        'gpus': gpus,
        'nvidia_ready': nvidia_ready,
        'prime_available': prime_available,
        'steam_available': steam_available,
        'notes': notes,
    }


if __name__ == '__main__':
    json.dump(collect_status(), sys.stdout, indent=2)
    sys.stdout.write('\n')

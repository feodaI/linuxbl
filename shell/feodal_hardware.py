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
        notes.append('Memory information is unavailable.')
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
            notes.append(f'{key} memory value is unavailable.')
    return values['MemTotal'], values['MemAvailable']


def _gpu_devices(drm_path):
    devices = []
    try:
        cards = sorted(Path(drm_path).glob('card[0-9]*'))
    except OSError:
        return devices

    for card in cards:
        if not card.name.startswith('card') or not card.name[4:].isdigit():
            continue
        device_path = card / 'device'
        try:
            pci_class = (device_path / 'class').read_text(encoding='ascii').strip()
            vendor = (device_path / 'vendor').read_text(encoding='ascii').strip()
            device = (device_path / 'device').read_text(encoding='ascii').strip()
        except (OSError, UnicodeError):
            continue

        try:
            is_display_device = int(pci_class, 16) >> 16 == 0x03
        except ValueError:
            continue
        if not is_display_device:
            continue

        driver_link = device_path / 'driver'
        try:
            driver = driver_link.resolve().name if driver_link.is_symlink() else ''
        except OSError:
            driver = ''
        devices.append({'vendor': vendor, 'device': device, 'driver': driver})
    return devices


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
        notes.append('nvidia-smi is unavailable.')
        return False

    try:
        result = command_runner(
            [executable], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.SubprocessError):
        notes.append('nvidia-smi did not complete successfully.')
        return False
    if result.returncode != 0 or not result.stdout.strip():
        notes.append('nvidia-smi did not report a working NVIDIA driver.')
        return False
    return True


def collect_status(meminfo_path='/proc/meminfo', drm_path='/sys/class/drm',
                   which=shutil.which, command_runner=subprocess.run):
    """Return a non-privileged snapshot of memory, display devices and launch tools."""
    notes = []
    memory_total, memory_available = _read_memory(meminfo_path, notes)
    gpus = _gpu_devices(drm_path)
    if not gpus:
        notes.append('No GPU devices were found in DRM sysfs.')

    nvidia_devices = [gpu for gpu in gpus
                      if gpu['vendor'].lower().removeprefix('0x') == '10de']
    if any(gpu['device'].lower().removeprefix('0x') in {'1d16', '1d18'}
           for gpu in nvidia_devices):
        notes.append('This older NVIDIA GPU may require the legacy 580xx driver branch.')
    nvidia_ready = bool(nvidia_devices) and _nvidia_smi_works(which, command_runner, notes)
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

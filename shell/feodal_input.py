#!/usr/bin/env python3
"""Manage the user's X11 keyboard layout and query its active group."""
import argparse
import ctypes
import ctypes.util
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


DEFAULT_LAYOUT = 'us,ua'
LAYOUTS = {'us', 'ua', 'us,ua'}
SET_LAYOUTS = {'us', 'ua', 'us,ua'}
COMMAND_TIMEOUT = 5
XKB_USE_CORE_KBD = 0x0100


class _XkbState(ctypes.Structure):
    _fields_ = [
        ('group', ctypes.c_ubyte), ('locked_group', ctypes.c_ubyte),
        ('base_group', ctypes.c_ushort), ('latched_group', ctypes.c_ushort),
        ('mods', ctypes.c_ubyte), ('base_mods', ctypes.c_ubyte),
        ('latched_mods', ctypes.c_ubyte), ('locked_mods', ctypes.c_ubyte),
        ('compat_state', ctypes.c_ubyte), ('grab_mods', ctypes.c_ubyte),
        ('compat_grab_mods', ctypes.c_ubyte), ('lookup_mods', ctypes.c_ubyte),
        ('compat_lookup_mods', ctypes.c_ubyte), ('ptr_buttons', ctypes.c_ushort),
    ]


def config_path():
    """Return the input settings path, honoring only absolute XDG paths."""
    xdg = os.environ.get('XDG_CONFIG_HOME', '')
    base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / '.config'
    return base / 'feodal' / 'input.json'


def _valid_layout(value):
    return isinstance(value, str) and value in LAYOUTS


def load_layout(path=None):
    """Load a valid saved layout, falling back to the dual US/Ukrainian default."""
    try:
        data = json.loads(Path(path or config_path()).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return DEFAULT_LAYOUT
    if isinstance(data, dict) and _valid_layout(data.get('layout')):
        return data['layout']
    return DEFAULT_LAYOUT


def save_layout(layout, path=None):
    """Atomically save a supported layout with owner-only file permissions."""
    if not _valid_layout(layout):
        raise ValueError('layout must be one of: ' + ', '.join(sorted(LAYOUTS)))
    destination = Path(path or config_path())
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.input-', dir=destination.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'layout': layout}, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return destination


def apply_layout(layout, command_runner=None, which=None, timeout=COMMAND_TIMEOUT):
    """Apply a validated XKB layout without invoking a shell."""
    if not _valid_layout(layout):
        raise ValueError('unsupported keyboard layout')
    runner = command_runner or subprocess.run
    find_command = which or shutil.which
    executable = find_command('setxkbmap')
    if not executable:
        raise RuntimeError('setxkbmap is not installed')
    command = [executable, '-layout', layout]
    if ',' in layout:
        command.extend(['-option', 'grp:alt_shift_toggle'])
    try:
        result = runner(command, capture_output=True, text=True,
                        timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f'could not apply keyboard layout: {error}') from error
    if result.returncode:
        detail = (result.stderr or '').strip()
        raise RuntimeError(detail or 'setxkbmap failed')
    return result


@lru_cache(maxsize=1)
def _load_x11():
    library = ctypes.util.find_library('X11')
    if not library:
        raise RuntimeError('libX11 is not available')
    x11 = ctypes.CDLL(library)
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = ctypes.c_int
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XFlush.restype = ctypes.c_int
    x11.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                ctypes.POINTER(_XkbState)]
    x11.XkbGetState.restype = ctypes.c_int
    x11.XkbLockGroup.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    x11.XkbLockGroup.restype = ctypes.c_int
    return x11


def _open_x11(x11):
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError('cannot connect to the X11 display (is DISPLAY set?)')
    return display


def _read_group(x11, display):
    state = _XkbState()
    if x11.XkbGetState(display, XKB_USE_CORE_KBD, ctypes.byref(state)) != 0:
        raise RuntimeError('could not read the active XKB group')
    return int(state.group)


def _label(layout, group):
    groups = layout.split(',')
    name = groups[group % len(groups)]
    return {'us': 'EN', 'ua': 'UK'}[name]


def current_group(layout=DEFAULT_LAYOUT, x11=None):
    """Return the active XKB group number."""
    if not _valid_layout(layout):
        raise ValueError('unsupported keyboard layout')
    library = x11 or _load_x11()
    display = _open_x11(library)
    try:
        return _read_group(library, display)
    finally:
        library.XCloseDisplay(display)


def toggle_group(layout=DEFAULT_LAYOUT, x11=None):
    """Lock the other configured XKB group and return its language label."""
    if not _valid_layout(layout):
        raise ValueError('unsupported keyboard layout')
    groups = layout.split(',')
    if len(groups) < 2:
        raise RuntimeError('only one keyboard layout is configured')
    library = x11 or _load_x11()
    display = _open_x11(library)
    try:
        group = (_read_group(library, display) + 1) % len(groups)
        if not library.XkbLockGroup(display, XKB_USE_CORE_KBD, group):
            raise RuntimeError('could not change the active XKB group')
        library.XFlush(display)
        return _label(layout, group)
    finally:
        library.XCloseDisplay(display)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--apply', action='store_true', help='apply the saved layout')
    actions.add_argument('--toggle', action='store_true', help='switch the active XKB group')
    actions.add_argument('--status', action='store_true', help='print the active layout label')
    actions.add_argument('--set', choices=sorted(SET_LAYOUTS), metavar='LAYOUT',
                         help='save and apply us, ua or us,ua')
    args = parser.parse_args(argv)
    try:
        if args.set:
            apply_layout(args.set)
            save_layout(args.set)
        elif args.apply:
            apply_layout(load_layout())
        elif args.toggle:
            print(toggle_group(load_layout()))
        else:
            print(_label(load_layout(), current_group(load_layout())))
    except (OSError, RuntimeError, ValueError) as error:
        print(f'feodal-input: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

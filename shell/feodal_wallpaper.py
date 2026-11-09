"""Desktop wallpaper: per-user override, then the bundled image."""
import os
from pathlib import Path
import shutil
import tempfile

import gi

gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, GLib

BUNDLED = (Path('/usr/share/feodal/wallpapers/kingdom.jpg'),
           Path(__file__).resolve().parent.parent / 'assets/wallpaper/kingdom.jpg')


def user_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    if not base.is_absolute():
        base = Path.home() / '.config'
    return base / 'feodal' / 'wallpaper'


def candidates():
    return (user_path(),) + BUNDLED


def is_image(path):
    try:
        info = GdkPixbuf.Pixbuf.get_file_info(str(path))
    except GLib.Error:
        return False
    return bool(info and info[0] and info[1] > 0 and info[2] > 0)


def load_scaled(width, height):
    """Return a pixbuf covering width x height, or None.

    Decodes straight to screen size so the full-resolution image never stays in memory.
    """
    for path in candidates():
        try:
            info = GdkPixbuf.Pixbuf.get_file_info(str(path))
            if not info or not info[0]:
                continue
            scale = max(width / info[1], height / info[2])
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path), max(1, round(info[1] * scale)), max(1, round(info[2] * scale)), False)
        except (GLib.Error, OSError, ZeroDivisionError):
            continue
    return None


def set_user_wallpaper(source):
    if not is_image(source):
        raise ValueError('Not a supported image')
    target = user_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix='.wallpaper-')
    os.close(handle)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    except OSError:
        Path(temporary).unlink(missing_ok=True)
        raise


def reset_user_wallpaper():
    user_path().unlink(missing_ok=True)

"""Small, per-user gaming preferences; never modifies system graphics settings."""
import json
import os
from pathlib import Path
import tempfile

MODES = ('auto', 'nvidia')


def config_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    if not base.is_absolute():
        base = Path.home() / '.config'
    return base / 'feodal' / 'preferences.json'


def load_mode(path=None):
    try:
        data = json.loads((path or config_path()).read_text(encoding='utf-8'))
        mode = data.get('steam_gpu') if isinstance(data, dict) else None
        return mode if mode in MODES else 'auto'
    except (OSError, ValueError):
        return 'auto'


def save_mode(mode, path=None):
    if mode not in MODES:
        raise ValueError('Unknown GPU mode')
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.preferences-', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'steam_gpu': mode}, stream)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def steam_command(mode, status):
    if not status.get('steam_available'):
        raise ValueError('Steam не встановлений. Переглянь інструкцію в центрі керування.')
    if mode == 'auto':
        return ['steam']
    if mode != 'nvidia':
        raise ValueError('Невідомий режим GPU.')
    if not status.get('nvidia_ready'):
        raise ValueError('NVIDIA не готова: потрібен робочий драйвер. Відкрий діагностику.')
    return [
        'env', '__NV_PRIME_RENDER_OFFLOAD=1',
        '__GLX_VENDOR_LIBRARY_NAME=nvidia', '__VK_LAYER_NV_optimus=NVIDIA_only',
        'steam',
    ]

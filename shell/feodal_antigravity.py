"""Per-user Google Antigravity install from Google's official download.

The proprietary binary is never bundled with Feodal: it is fetched at install time
and checked against a pinned BLAKE2b digest (same digest as the Arch AUR package).
"""
import hashlib
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

VERSION = '2.29.1'
URL = ('https://storage.googleapis.com/antigravity-public/antigravity-hub/'
       '2.29.1-5241471524274176/linux-x64/Antigravity.tar.gz')
SIZE = 185057475
B2SUM = ('4c2b02dee239f4cce54a1b074f76cdcdb81f9e7443c9b379e79cbb54529d89db'
         'eccd9dd544acf4d91c1670e2ae9e584168a0941703bb43cc8edd7495a75b85ba')
TERMS = 'https://antigravity.google/terms'
DESKTOP = '''[Desktop Entry]
Type=Application
Name=Antigravity
GenericName=Agentic Platform
Comment=Google Antigravity
Exec="{binary}" --disable-gpu %U
Icon=applications-development
Categories=Development;
StartupWMClass=Antigravity
'''


class AntigravityError(Exception):
    pass


def paths(home):
    home = Path(home)
    return {
        'dir': home / '.local/opt/antigravity',
        'bin': home / '.local/bin/antigravity',
        'desktop': home / '.local/share/applications/antigravity.desktop',
    }


def installed(home):
    return (paths(home)['dir'] / 'antigravity').is_file()


def download(destination, progress=None, url=URL, opener=urllib.request.urlopen):
    digest = hashlib.blake2b()
    done = 0
    with opener(url, timeout=60) as response, open(destination, 'wb') as output:
        while True:
            chunk = response.read(1 << 20)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if done > SIZE * 2:
                raise AntigravityError('Завантаження більше за очікуване — перервано')
            if progress:
                progress(done, SIZE)
    if digest.hexdigest() != B2SUM:
        raise AntigravityError('Контрольна сума не збігається — файл відкинуто')


def _safe_extract(archive, target):
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        for member in members:
            name = Path(member.name)
            if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != 'Antigravity-x64':
                raise AntigravityError(f'Небезпечний шлях в архіві: {member.name}')
            if member.issym() or member.islnk() or member.isdev():
                raise AntigravityError(f'Неочікуваний тип файлу в архіві: {member.name}')
        tar.extractall(target, members=members, filter='data')


def install(home, progress=None, archive=None, url=URL, opener=urllib.request.urlopen, final_home=None):
    """Install into home; returns the launcher path. Replaces an older copy atomically.

    final_home is the same home as seen by the installed system (the installer writes via /mnt).
    """
    target = paths(home)
    for key in ('dir', 'bin', 'desktop'):
        target[key].parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.antigravity-', dir=target['dir'].parent))
    try:
        tarball = Path(archive) if archive else work / 'Antigravity.tar.gz'
        if archive is None:
            download(tarball, progress, url, opener)
        else:
            digest = hashlib.blake2b()
            with open(tarball, 'rb') as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b''):
                    digest.update(chunk)
            if digest.hexdigest() != B2SUM:
                raise AntigravityError('Контрольна сума не збігається — файл відкинуто')
        _safe_extract(tarball, work)
        new = work / 'Antigravity-x64'
        if not (new / 'antigravity').is_file():
            raise AntigravityError('В архіві немає програми antigravity')
        old = target['dir'].with_name('.antigravity-old')
        if old.exists():
            shutil.rmtree(old)
        if target['dir'].exists():
            target['dir'].rename(old)
        new.rename(target['dir'])
        if old.exists():
            shutil.rmtree(old)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    binary = paths(final_home or home)['dir'] / 'antigravity'
    if target['bin'].is_symlink() or target['bin'].exists():
        target['bin'].unlink()
    target['bin'].symlink_to(binary)
    target['desktop'].write_text(DESKTOP.format(binary=binary), encoding='utf-8')
    return binary


def uninstall(home):
    target = paths(home)
    shutil.rmtree(target['dir'], ignore_errors=True)
    for key in ('bin', 'desktop'):
        if target[key].is_symlink() or target[key].exists():
            target[key].unlink()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog='feodal-antigravity',
                                     description='Install Google Antigravity for the current user.')
    parser.add_argument('action', choices=('install', 'uninstall', 'status'))
    args = parser.parse_args(argv)
    home = Path.home()
    if os.geteuid() == 0:
        parser.error('run as your normal user, not root')
    if args.action == 'status':
        print(f'installed {VERSION}' if installed(home) else 'not installed')
        return 0
    if args.action == 'uninstall':
        uninstall(home)
        print('Antigravity removed.')
        return 0
    print(f'Google Antigravity {VERSION} — terms: {TERMS}')
    print(f'Downloading {SIZE // 1000000} MB from Google...')

    def show(done, total):
        print(f'\r{min(100, done * 100 // total):3d}%', end='', flush=True)
    try:
        binary = install(home, show)
    except (OSError, AntigravityError, tarfile.TarError) as exc:
        print(f'\nFailed: {exc}')
        return 1
    print(f'\nInstalled: {binary}')
    return 0

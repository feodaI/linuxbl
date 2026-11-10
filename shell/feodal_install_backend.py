"""Root side of the Feodal installer.

Reads a JSON config on stdin (so the password never appears in argv), writes JSON progress
lines to stdout and installs the running live image onto a whole disk:
GPT with a BIOS boot partition, a FAT32 ESP and an ext4 root; GRUB for BIOS and UEFI.
"""
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import feodal_installer_core as core

TARGET = Path('/mnt/feodal-target')
LOG = Path('/var/log/feodal-installer.log')
TOOLS = ('sgdisk', 'wipefs', 'partprobe', 'udevadm', 'mkfs.ext4', 'mkfs.fat', 'rsync', 'arch-chroot',
         'blkid', 'mount', 'umount', 'lsblk', 'findmnt')
# Files that only make sense on the live medium.
LIVE_FILES = (
    'etc/systemd/system/getty@tty1.service.d/autologin.conf',
    'etc/profile.d/feodal-live-session.sh',
    'etc/sysusers.d/feodal.conf',
    'etc/tmpfiles.d/feodal-home.conf',
    'etc/polkit-1/rules.d/49-feodal-live-installer.rules',
    'usr/share/applications/feodal-installer.desktop',
    'etc/systemd/system/etc-pacman.d-gnupg.mount',
    'etc/systemd/system/pacman-init.service',
    'etc/systemd/system/choose-mirror.service',
    'etc/systemd/system/livecd-talk.service',
    'etc/systemd/system/livecd-alsa-unmuter.service',
    'etc/systemd/journald.conf.d/volatile-storage.conf',
    'etc/systemd/logind.conf.d/do-not-suspend.conf',
    'etc/mkinitcpio.conf.d/archiso.conf',
    'etc/mkinitcpio.conf.d/feodal.conf',
    'etc/ssh/sshd_config.d/10-archiso.conf',
    'root/.automated_script.sh',
    'root/.zlogin',
    'root/.ssh/authorized_keys',
    'etc/motd',
)
LIVE_UNITS = {'pacman-init.service', 'choose-mirror.service', 'livecd-talk.service',
              'livecd-alsa-unmuter.service', 'etc-pacman.d-gnupg.mount', 'reflector.service',
              'cloud-init.service', 'cloud-init-local.service', 'cloud-init-main.service',
              'cloud-init-network.service', 'cloud-config.service', 'cloud-final.service',
              'cloud-init.target', 'cloud-init-hotplugd.socket', 'hv_fcopy_daemon.service',
              'hv_kvp_daemon.service', 'hv_vss_daemon.service', 'vboxservice.service', 'vmtoolsd.service',
              'vmware-vmblock-fuse.service'}
# Rescue/VM tooling from Arch releng that a desktop install does not need.
LIVE_PACKAGES = ('archinstall', 'mkinitcpio-archiso', 'cloud-init', 'clonezilla', 'open-vm-tools',
                 'virtualbox-guest-utils-nox', 'hyperv', 'livecd-sounds', 'espeakup')
PRESET = '''# Written by the Feodal installer.
ALL_kver="/boot/vmlinuz-linux"
PRESETS=('default' 'fallback')
default_image="/boot/initramfs-linux.img"
fallback_image="/boot/initramfs-linux-fallback.img"
fallback_options="-S autodetect"
'''
SESSION_PROFILE = '''# Start the Feodal desktop after a password login on tty1 (written by the installer).
if [ -z "${DISPLAY:-}" ] && [ "$(tty 2>/dev/null)" = /dev/tty1 ] && [ "$(id -u)" -ge 1000 ]; then
    startx /usr/bin/feodal-session -- -keeptty vt1 ||
        { printf '%s\\n' 'Feodal не запустився. Ctrl+Alt+F2 — текстова консоль.'; sleep 5; }
    exit
fi
'''
ISSUE = 'Feodal Linux \\r (\\l)\n\nУвійди своїм логіном — робочий стіл запуститься сам.\n\n'
GEO_MIRROR = 'Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch\n'
STAGES = (
    ('preflight', 'Перевірка', 0, 2),
    ('partition', 'Розмітка диска', 2, 5),
    ('format', 'Форматування', 5, 7),
    ('copy', 'Копіювання системи', 7, 72),
    ('configure', 'Налаштування системи', 72, 86),
    ('bootloader', 'Завантажувач GRUB', 86, 92),
    ('antigravity', 'Google Antigravity', 92, 99),
    ('finish', 'Завершення', 99, 100),
)


class InstallError(Exception):
    pass


class Installer:
    def __init__(self, config, emit, target=TARGET, source=None, log_path=LOG):
        self.config = config
        self.emit = emit
        self.target = Path(target)
        self.source = source
        self.log_path = Path(log_path)
        self.warnings = []
        self.stage = None
        self.disk = config.get('disk', '')

    # ---- plumbing -------------------------------------------------------
    def log(self, text):
        line = f'{datetime.datetime.now():%H:%M:%S} {text}'
        try:
            with open(self.log_path, 'a', encoding='utf-8') as handle:
                handle.write(line + '\n')
        except OSError:
            pass
        self.emit({'type': 'log', 'text': line})

    def warn(self, text):
        self.warnings.append(text)
        self.log('УВАГА: ' + text)

    def progress(self, fraction):
        _, _, start, end = next(stage for stage in STAGES if stage[0] == self.stage)
        self.emit({'type': 'progress', 'stage': self.stage,
                   'percent': round(start + (end - start) * max(0.0, min(1.0, fraction)), 1)})

    def run(self, command, stdin=None, check=True):
        self.log('$ ' + ' '.join(command))
        result = subprocess.run(command, input=stdin, capture_output=True, text=True)
        output = (result.stdout + result.stderr).strip()
        if output:
            for line in output.splitlines()[-15:]:
                self.log('  ' + line)
        if check and result.returncode:
            raise InstallError(f'Команда завершилася з помилкою ({result.returncode}): {command[0]}')
        return result

    def chroot(self, command, stdin=None, check=True):
        return self.run(['arch-chroot', str(self.target)] + command, stdin=stdin, check=check)

    def path(self, relative):
        return self.target / relative

    def require_target_mounts(self, esp=False):
        if not os.path.ismount(self.target):
            raise InstallError('Розділ системи більше не змонтовано')
        if esp and not os.path.ismount(self.path('boot/efi')):
            raise InstallError('Розділ EFI більше не змонтовано')

    def partition(self, number):
        return core.partition_path(self.disk, number)

    # ---- stages ---------------------------------------------------------
    def preflight(self):
        if os.geteuid() != 0:
            raise InstallError('Інсталятор має працювати від root')
        if not core.is_live():
            raise InstallError('Встановлення можливе лише з live-системи Feodal')
        self.source = self.source or core.live_source()
        if not self.source:
            raise InstallError('Не знайдено образ live-системи для копіювання')
        missing = [tool for tool in TOOLS if not shutil.which(tool)]
        if missing:
            raise InstallError('Бракує програм: ' + ', '.join(missing))
        problems = core.validate_user(self.config)
        if problems:
            raise InstallError(problems[0][1])
        _, chosen = self.check_target_disk()
        if self.target.is_symlink():
            raise InstallError(f'{self.target} не може бути символічним посиланням')
        if self.target.exists() and os.path.ismount(self.target):
            raise InstallError(f'{self.target} вже змонтовано')
        self.log(f'Диск: {self.disk} ({chosen["model"]}, {core.human_size(chosen["size"])}); '
                 f'джерело: {self.source}; UEFI: {Path("/sys/firmware/efi").exists()}')

    def check_target_disk(self):
        tree = core.lsblk_tree()
        choices = {disk['path']: disk for disk in core.disk_choices(tree, core.live_boot_disk())}
        chosen = choices.get(self.disk)
        if not chosen:
            raise InstallError(f'Диск не знайдено: {self.disk}')
        if chosen['reason']:
            raise InstallError(f'Диск {self.disk} не можна використати: {chosen["reason"]}')
        return tree, chosen

    def partition_disk(self):
        # Recheck immediately before the first destructive command; preflight may be stale.
        tree, _ = self.check_target_disk()
        for device in tree:
            if device.get('path') == self.disk:
                for child in device.get('children') or ():
                    self.run(['wipefs', '--all', '--force', child['path']], check=False)
        self.run(['wipefs', '--all', '--force', self.disk])
        self.run(['sgdisk', '--zap-all', self.disk])
        self.progress(.4)
        self.run(['sgdisk',
                  '-n', '1:0:+1M', '-t', '1:ef02', '-c', '1:BIOS boot',
                  '-n', '2:0:+512M', '-t', '2:ef00', '-c', '2:EFI',
                  '-n', '3:0:0', '-t', '3:8304', '-c', '3:Feodal',
                  self.disk])
        self.run(['partprobe', self.disk], check=False)
        self.run(['udevadm', 'settle'], check=False)
        for _ in range(50):
            if all(Path(self.partition(n)).exists() for n in (1, 2, 3)):
                return
            time.sleep(.2)
        raise InstallError('Нові розділи не з’явилися в системі')

    def format(self):
        self.run(['mkfs.fat', '-F', '32', '-n', 'FEODAL-EFI', self.partition(2)])
        self.progress(.3)
        self.run(['mkfs.ext4', '-F', '-q', '-L', 'feodal', self.partition(3)])
        self.target.mkdir(parents=True, exist_ok=True)
        self.run(['mount', self.partition(3), str(self.target)])
        self.path('boot/efi').mkdir(parents=True, exist_ok=True)
        self.run(['mount', self.partition(2), str(self.path('boot/efi'))])
        self.require_target_mounts(esp=True)

    def copy(self):
        self.require_target_mounts(esp=True)
        command = ['rsync', '-aAXH', '--numeric-ids', '--no-inc-recursive', '--info=progress2',
                   f'{self.source}/', f'{self.target}/']
        self.log('$ ' + ' '.join(command))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        buffer, last = b'', -1
        tail = []
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk
            parts = re.split(rb'[\r\n]', buffer)
            buffer = parts.pop()
            for part in parts:
                if part:
                    tail.append(part.decode(errors='replace'))
                    del tail[:-15]
                match = re.search(rb'\s(\d{1,3})%\s', part)
                if match and int(match.group(1)) != last:
                    last = int(match.group(1))
                    self.progress(last / 100)
        if buffer:
            tail.append(buffer.decode(errors='replace'))
        if process.wait():
            for line in tail[-15:]:
                self.log('  ' + line)
            raise InstallError('Не вдалося скопіювати систему на диск')

    def remove_live_files(self):
        for relative in LIVE_FILES:
            path = self.path(relative)
            if path.is_symlink() or path.exists():
                path.unlink()
                self.log(f'видалено /{relative}')
        systemd = self.path('etc/systemd/system')
        if systemd.is_dir():
            for link in systemd.glob('*.wants/*'):
                if link.name in LIVE_UNITS and link.is_symlink():
                    link.unlink()
                    self.log(f'вимкнено {link.name}')
        for directory in ('etc/systemd/system/getty@tty1.service.d',):
            path = self.path(directory)
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()

    def write(self, relative, text, mode=0o644):
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        path.chmod(mode)

    def configure(self):
        self.require_target_mounts(esp=True)
        self.remove_live_files()
        self.progress(.05)
        modules = sorted(path for path in self.path('usr/lib/modules').glob('*/vmlinuz')
                         if (path.parent / 'pkgbase').is_file()
                         and (path.parent / 'pkgbase').read_text().strip() == 'linux')
        if not modules:
            raise InstallError('Не знайдено ядро Linux у скопійованій системі')
        shutil.copy2(modules[-1], self.path('boot/vmlinuz-linux'))
        self.write('etc/mkinitcpio.d/linux.preset', PRESET)
        self.write('etc/mkinitcpio.conf.d/feodal.conf', 'COMPRESSION="zstd"\n')
        self.remove_live_packages()
        self.progress(.15)
        self.configure_system()
        self.progress(.35)
        self.chroot(['mkinitcpio', '-P'])
        self.progress(.7)
        self.chroot(['pacman-key', '--init'], check=False)
        if self.chroot(['pacman-key', '--populate', 'archlinux'], check=False).returncode:
            self.warn('Ключі pacman не ініціалізовано; виконай: sudo pacman-key --init && '
                      'sudo pacman-key --populate archlinux')

    def remove_live_packages(self):
        installed = set(self.chroot(['pacman', '-Qq'], check=False).stdout.split())
        removable = [name for name in LIVE_PACKAGES if name in installed]
        if not removable:
            return
        # Removing mkinitcpio-archiso fires the initramfs hook; mask it so the
        # image is built once, by the explicit mkinitcpio -P that follows.
        mask = self.path('etc/pacman.d/hooks/90-mkinitcpio-install.hook')
        masked = not (mask.exists() or mask.is_symlink())
        if masked:
            mask.parent.mkdir(parents=True, exist_ok=True)
            mask.symlink_to('/dev/null')
        try:
            if self.chroot(['pacman', '-Rns', '--noconfirm'] + removable, check=False).returncode:
                self.warn('Не вдалося прибрати частину live-пакетів; систему це не ламає')
        finally:
            if masked:
                mask.unlink()

    def configure_system(self):
        config = self.config
        root_uuid = self.run(['blkid', '-s', 'UUID', '-o', 'value', self.partition(3)]).stdout.strip()
        esp_uuid = self.run(['blkid', '-s', 'UUID', '-o', 'value', self.partition(2)]).stdout.strip()
        if not root_uuid or not esp_uuid:
            raise InstallError('Не вдалося визначити UUID розділів')
        self.write('etc/fstab', '# Written by the Feodal installer.\n'
                   f'UUID={root_uuid}  /          ext4  rw,relatime  0 1\n'
                   f'UUID={esp_uuid}  /boot/efi  vfat  rw,relatime,fmask=0077,dmask=0077,'
                   'codepage=437,iocharset=ascii,shortname=mixed,utf8,errors=remount-ro  0 2\n')
        hostname = config['hostname']
        self.write('etc/hostname', hostname + '\n')
        self.write('etc/hosts', '127.0.0.1 localhost\n::1 localhost\n'
                   f'127.0.1.1 {hostname}.localdomain {hostname}\n')
        locale_gen = self.path('etc/locale.gen')
        lines = locale_gen.read_text().splitlines() if locale_gen.exists() else []
        wanted = {'en_US.UTF-8 UTF-8', 'uk_UA.UTF-8 UTF-8'}
        lines = [line.lstrip('#').strip() if line.lstrip('#').strip() in wanted else line for line in lines]
        lines += sorted(wanted - set(lines))
        self.write('etc/locale.gen', '\n'.join(lines) + '\n')
        self.chroot(['locale-gen'])
        self.write('etc/locale.conf', f'LANG={config["locale"]}\n')
        self.write('etc/vconsole.conf', 'KEYMAP=us\nFONT=ter-v16n\n')
        localtime = self.path('etc/localtime')
        if localtime.is_symlink() or localtime.exists():
            localtime.unlink()
        localtime.symlink_to(f'/usr/share/zoneinfo/{config["timezone"]}')
        machine_id = self.path('etc/machine-id')
        machine_id.write_text('')
        self.chroot(['systemd-machine-id-setup'], check=False)
        passwd = self.path('etc/passwd').read_text()
        if re.search(r'^feodal:', passwd, re.M):
            self.chroot(['userdel', '--remove', 'feodal'], check=False)
        shutil.rmtree(self.path('home/feodal'), ignore_errors=True)
        if re.search(rf'^{re.escape(config["username"])}:', self.path('etc/passwd').read_text(), re.M):
            raise InstallError('Такий користувач уже існує в системі')
        self.chroot(['useradd', '--create-home', '--groups', 'wheel', '--shell', '/bin/bash',
                     '--comment', config.get('fullname') or config['username'], config['username']])
        self.chroot(['chpasswd'], stdin=f'{config["username"]}:{config["password"]}\n')
        self.chroot(['passwd', '--lock', 'root'], check=False)
        self.write('etc/sudoers.d/10-feodal-wheel', '%wheel ALL=(ALL:ALL) ALL\n', 0o440)
        self.write('etc/profile.d/feodal-session.sh', SESSION_PROFILE)
        self.write('etc/issue', ISSUE)
        mirrorlist = self.path('etc/pacman.d/mirrorlist')
        active = re.compile(r'^\s*Server\s*=', re.M)
        if not mirrorlist.exists() or not active.search(mirrorlist.read_text()):
            live = Path('/etc/pacman.d/mirrorlist')
            text = live.read_text() if live.exists() else ''
            self.write('etc/pacman.d/mirrorlist', text if active.search(text) else GEO_MIRROR)

    def bootloader(self):
        self.require_target_mounts(esp=True)
        default = self.path('etc/default/grub')
        text = default.read_text() if default.exists() else ''
        for key, value in (('GRUB_TIMEOUT', '3'), ('GRUB_DISTRIBUTOR', '"Feodal"'),
                           ('GRUB_CMDLINE_LINUX_DEFAULT', '"loglevel=3 quiet"')):
            line = f'{key}={value}'
            text, count = re.subn(rf'^#?\s*{key}=.*$', line, text, flags=re.M)
            if not count:
                text += line + '\n'
        self.write('etc/default/grub', text)
        self.chroot(['grub-install', '--target=i386-pc', '--recheck', self.disk])
        self.progress(.35)
        # Removable path (\EFI\BOOT\BOOTX64.EFI) boots even when firmware forgets NVRAM entries.
        self.chroot(['grub-install', '--target=x86_64-efi', '--efi-directory=/boot/efi', '--removable'])
        if Path('/sys/firmware/efi').exists():
            if self.chroot(['grub-install', '--target=x86_64-efi', '--efi-directory=/boot/efi',
                            '--bootloader-id=Feodal'], check=False).returncode:
                self.warn('Не вдалося додати запис Feodal у UEFI; диск усе одно завантажиться')
        self.progress(.7)
        self.chroot(['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

    def antigravity(self):
        if not self.config.get('antigravity'):
            self.log('Antigravity не обрано')
            return
        self.require_target_mounts()
        import feodal_antigravity
        username = self.config['username']
        home = self.path(f'home/{username}')
        self.log(f'Завантаження Google Antigravity {feodal_antigravity.VERSION} з {feodal_antigravity.URL}')
        try:
            feodal_antigravity.install(home, lambda done, total: self.progress(done / total * .95),
                                       final_home=Path('/home') / username)
            ids = self.chroot(['id', '-u', username]).stdout.strip(), self.chroot(['id', '-g', username]).stdout.strip()
            self.run(['chown', '-R', f'{ids[0]}:{ids[1]}', str(home / '.local')])
            self.log('Antigravity встановлено в ~/.local/opt/antigravity')
        except Exception as exc:  # optional extra: never fail the whole install
            self.warn(f'Antigravity не встановлено ({exc}). Пізніше: feodal-antigravity install')
            shutil.rmtree(home / '.local/opt/.antigravity-old', ignore_errors=True)

    def finish(self):
        self.require_target_mounts(esp=True)
        self.run(['sync'], check=False)
        try:
            shutil.copy2(self.log_path, self.path('var/log/feodal-installer.log'))
        except OSError:
            pass
        self.unmount(check=True)

    def unmount(self, check=False):
        efi = self.path('boot/efi')
        if self.target.exists() and (os.path.ismount(self.target) or os.path.ismount(efi)):
            result = self.run(['umount', '--recursive', str(self.target)], check=False)
            if result.returncode or os.path.ismount(self.target) or os.path.ismount(efi):
                message = f'Не вдалося відмонтувати {self.target}'
                if check:
                    raise InstallError(message)
                self.log('УВАГА: ' + message)

    def install(self):
        actions = {'preflight': self.preflight, 'partition': self.partition_disk, 'format': self.format,
                   'copy': self.copy, 'configure': self.configure, 'bootloader': self.bootloader,
                   'antigravity': self.antigravity, 'finish': self.finish}
        try:
            for stage, title, start, _ in STAGES:
                self.stage = stage
                self.emit({'type': 'stage', 'stage': stage, 'title': title, 'percent': start})
                actions[stage]()
                self.progress(1)
        except Exception as exc:
            message = str(exc) if isinstance(exc, InstallError) else f'Неочікувана помилка: {exc}'
            self.log('ПОМИЛКА: ' + message)
            try:
                self.unmount(check=False)
            except Exception as cleanup_error:
                self.log(f'Не вдалося очистити монтування: {cleanup_error}')
            self.emit({'type': 'error', 'stage': self.stage, 'message': message, 'log': str(self.log_path)})
            return 1
        self.emit({'type': 'done', 'warnings': self.warnings})
        return 0


def main():
    def emit(event):
        sys.stdout.write(json.dumps(event, ensure_ascii=False) + '\n')
        sys.stdout.flush()
    try:
        config = json.loads(sys.stdin.read())
        if not isinstance(config, dict):
            raise ValueError
    except ValueError:
        emit({'type': 'error', 'stage': 'preflight', 'message': 'Некоректні налаштування', 'log': ''})
        return 2
    return Installer(config, emit).install()


if __name__ == '__main__':
    sys.exit(main())

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))
import feodal_install_backend as backend  # noqa: E402

CONFIG = {'disk': '/dev/vda', 'fullname': 'Тарас', 'username': 'taras', 'password': 'pa55-secret',
          'password_confirm': 'pa55-secret', 'hostname': 'kingdom', 'timezone': 'Europe/Kyiv',
          'locale': 'uk_UA.UTF-8', 'antigravity': False}


class FakeInstaller(backend.Installer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands = []

    def run(self, command, stdin=None, check=True):
        self.commands.append((command, stdin))
        self.log('$ ' + ' '.join(command))
        out = ''
        if command[-1] == '-Qq' or command[-2:] == ['pacman', '-Qq']:
            out = 'base\narchinstall\ncloud-init\nfeodal-shell\n'
        elif command[0] == 'blkid':
            out = 'UUID-' + command[-1].rsplit('/', 1)[-1] + '\n'
        elif command[-3:-1] == ['id', '-u'] or command[-3:-1] == ['id', '-g']:
            out = '1000\n'
        return subprocess.CompletedProcess(command, 0, out, '')


def populate(target):
    files = {
        'etc/passwd': 'root:x:0:0:root:/root:/usr/bin/zsh\nfeodal:x:1000:1000::/home/feodal:/bin/bash\n',
        'etc/locale.gen': '#en_US.UTF-8 UTF-8  \n#uk_UA.UTF-8 UTF-8  \n#de_DE.UTF-8 UTF-8\n',
        'etc/default/grub': 'GRUB_DEFAULT=0\nGRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR="Arch"\n'
                            'GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet"\n',
        'etc/pacman.d/mirrorlist': '#Server = https://example.invalid/$repo\n',
        'usr/lib/modules/7.2.14-arch1-1/vmlinuz': 'kernel',
        'usr/lib/modules/7.2.14-arch1-1/pkgbase': 'linux\n',
        'home/feodal/.bashrc': '',
    }
    for relative in backend.LIVE_FILES:
        files.setdefault(relative, 'live')
    for relative, text in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    wants = target / 'etc/systemd/system/multi-user.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    for name in ('pacman-init.service', 'NetworkManager.service', 'vboxservice.service'):
        (wants / name).symlink_to(f'/usr/lib/systemd/system/{name}')
    (target / 'boot').mkdir()


class BackendTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.target = self.root / 'target'
        populate(self.target)
        self.events = []
        self.installer = FakeInstaller(dict(CONFIG), self.events.append, target=self.target,
                                       source=Path('/src'), log_path=self.root / 'install.log')
        self.installer.stage = 'configure'

    def text(self, relative):
        return (self.target / relative).read_text()

    def test_configure_turns_live_image_into_installed_system(self):
        with patch.object(Path, 'exists', lambda self: True if str(self) == '/etc/pacman.d/mirrorlist'
                          else os.path.lexists(self)), \
                patch.object(Path, 'read_text', lambda self, *a, **k: 'Server = https://live.mirror/$repo\n'
                             if str(self) == '/etc/pacman.d/mirrorlist' else open(self, encoding='utf-8').read()), \
                patch.object(backend.os.path, 'ismount', return_value=True):
            self.installer.configure()
        for relative in backend.LIVE_FILES:
            if relative == 'etc/mkinitcpio.conf.d/feodal.conf':
                # Rewritten without the archiso hooks.
                self.assertEqual(self.text(relative), 'COMPRESSION="zstd"\n')
                continue
            self.assertFalse((self.target / relative).exists(), relative)
        wants = self.target / 'etc/systemd/system/multi-user.target.wants'
        self.assertEqual(sorted(p.name for p in wants.iterdir()), ['NetworkManager.service'])
        self.assertEqual(self.text('boot/vmlinuz-linux'), 'kernel')
        self.assertIn("PRESETS=('default' 'fallback')", self.text('etc/mkinitcpio.d/linux.preset'))
        fstab = self.text('etc/fstab')
        self.assertIn('UUID=UUID-vda3  /          ext4', fstab)
        self.assertIn('UUID=UUID-vda2  /boot/efi  vfat', fstab)
        self.assertEqual(self.text('etc/hostname'), 'kingdom\n')
        self.assertIn('\nen_US.UTF-8 UTF-8\nuk_UA.UTF-8 UTF-8\n#de_DE', '\n' + self.text('etc/locale.gen'))
        self.assertEqual(self.text('etc/locale.conf'), 'LANG=uk_UA.UTF-8\n')
        self.assertEqual(os.readlink(self.target / 'etc/localtime'), '/usr/share/zoneinfo/Europe/Kyiv')
        self.assertFalse((self.target / 'home/feodal').exists())
        self.assertEqual(oct((self.target / 'etc/sudoers.d/10-feodal-wheel').stat().st_mode & 0o777), '0o440')
        self.assertIn('/dev/tty1', self.text('etc/profile.d/feodal-session.sh'))
        self.assertEqual(self.text('etc/pacman.d/mirrorlist'), 'Server = https://live.mirror/$repo\n')
        commands = [c for c, _ in self.installer.commands]
        chroot = [c[2:] for c in commands if c[:2] == ['arch-chroot', str(self.target)]]
        self.assertIn(['pacman', '-Rns', '--noconfirm', 'archinstall', 'cloud-init'], chroot)
        self.assertIn(['userdel', '--remove', 'feodal'], chroot)
        self.assertIn(['useradd', '--create-home', '--groups', 'wheel', '--shell', '/bin/bash',
                       '--comment', 'Тарас', 'taras'], chroot)
        self.assertIn(['passwd', '--lock', 'root'], chroot)
        self.assertLess(chroot.index(['locale-gen']), chroot.index(['mkinitcpio', '-P']))
        stdin = [s for c, s in self.installer.commands if c[-1] == 'chpasswd']
        self.assertEqual(stdin, ['taras:pa55-secret\n'])
        # The password must never reach argv, the log file or progress events.
        self.assertFalse(any('pa55-secret' in ' '.join(c) for c in commands))
        self.assertNotIn('pa55-secret', (self.root / 'install.log').read_text())
        self.assertNotIn('pa55-secret', json.dumps(self.events, ensure_ascii=False))

    def test_configure_refuses_to_write_when_target_is_unmounted(self):
        with patch.object(backend.os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(backend.InstallError, 'не змонтовано'):
                self.installer.configure()

    def test_live_package_removal_has_kernel_and_masked_initramfs_hook(self):
        hook = self.target / 'etc/pacman.d/hooks/90-mkinitcpio-install.hook'
        seen = []
        original = self.installer.run

        def run(command, stdin=None, check=True):
            if '-Rns' in command:
                seen.append((os.path.islink(hook) and os.readlink(hook),
                             (self.target / 'boot/vmlinuz-linux').is_file()))
            return original(command, stdin, check)

        self.installer.run = run
        with patch.object(backend.os.path, 'ismount', return_value=True):
            self.installer.configure()
        self.assertEqual(seen, [('/dev/null', True)])
        self.assertFalse(os.path.lexists(hook))

    def test_geo_mirror_when_no_server_available(self):
        with patch.object(backend, 'Path', wraps=Path) as wrapped:
            wrapped.side_effect = lambda *a: Path(*a) if a != ('/etc/pacman.d/mirrorlist',) \
                else self.root / 'missing'
            self.installer.configure_system()
        self.assertEqual(self.text('etc/pacman.d/mirrorlist'), backend.GEO_MIRROR)

    def test_bootloader_installs_bios_and_removable_uefi(self):
        self.installer.stage = 'bootloader'
        with patch.object(backend.Path, 'exists', lambda self: False if str(self) == '/sys/firmware/efi'
                          else os.path.lexists(self)), \
                patch.object(backend.os.path, 'ismount', return_value=True):
            self.installer.bootloader()
        grub = self.text('etc/default/grub')
        self.assertIn('GRUB_TIMEOUT=3', grub)
        self.assertIn('GRUB_DISTRIBUTOR="Feodal"', grub)
        chroot = [c[2:] for c, _ in self.installer.commands]
        self.assertEqual(chroot[0], ['grub-install', '--target=i386-pc', '--recheck', '/dev/vda'])
        self.assertIn('--removable', chroot[1])
        self.assertFalse(any('--bootloader-id=Feodal' in c for c in chroot))
        self.assertEqual(chroot[-1], ['grub-mkconfig', '-o', '/boot/grub/grub.cfg'])

    def test_partitioning_layout_and_nvme_names(self):
        self.installer.stage = 'partition'
        self.installer.disk = '/dev/nvme0n1'
        tree = [{'name': 'nvme0n1', 'path': '/dev/nvme0n1', 'size': 40 * 10 ** 9, 'type': 'disk'}]
        with patch.object(backend.core, 'lsblk_tree', return_value=tree), \
                patch.object(backend.core, 'live_boot_disk', return_value=None), \
                patch.object(backend.Path, 'exists', lambda self: True):
            self.installer.partition_disk()
        sgdisk = [c for c, _ in self.installer.commands if c[0] == 'sgdisk' and '-n' in c][0]
        self.assertEqual(sgdisk[-1], '/dev/nvme0n1')
        self.assertIn('2:ef00', sgdisk)
        self.assertIn('1:ef02', sgdisk)
        self.assertEqual(self.installer.partition(3), '/dev/nvme0n1p3')

    def test_partition_rechecks_disk_before_wiping(self):
        self.installer.stage = 'partition'
        tree = [{'name': 'vda', 'path': '/dev/vda', 'size': 40 * 10 ** 9, 'type': 'disk',
                 'children': [{'name': 'vda1', 'path': '/dev/vda1', 'mountpoints': ['/media/other']}]}]
        with patch.object(backend.core, 'lsblk_tree', return_value=tree), \
                patch.object(backend.core, 'live_boot_disk', return_value=None):
            with self.assertRaisesRegex(backend.InstallError, 'змонтовані'):
                self.installer.partition_disk()
        self.assertFalse(any(command[0] in ('wipefs', 'sgdisk') for command, _ in self.installer.commands))

    def test_preflight_refusals(self):
        self.installer.stage = 'preflight'
        with patch.object(backend.os, 'geteuid', return_value=1000):
            with self.assertRaisesRegex(backend.InstallError, 'root'):
                self.installer.preflight()
        with patch.object(backend.os, 'geteuid', return_value=0), \
                patch.object(backend.core, 'is_live', return_value=True), \
                patch.object(backend.shutil, 'which', return_value='/usr/bin/x'), \
                patch.object(backend.core, 'validate_user', return_value=[]), \
                patch.object(backend.core, 'live_boot_disk', return_value='/dev/vda'), \
                patch.object(backend.core, 'lsblk_tree', return_value=[
                    {'name': 'vda', 'path': '/dev/vda', 'size': 40 * 10 ** 9, 'type': 'disk'}]):
            with self.assertRaisesRegex(backend.InstallError, 'не можна'):
                self.installer.preflight()
            self.installer.disk = '/dev/sdz'
            with self.assertRaisesRegex(backend.InstallError, 'не знайдено'):
                self.installer.preflight()

    def test_failure_reports_error_and_unmounts(self):
        with patch.object(self.installer, 'preflight', side_effect=backend.InstallError('boom')), \
                patch.object(self.installer, 'unmount', side_effect=OSError('cleanup failed')) as unmount:
            self.assertEqual(self.installer.install(), 1)
        unmount.assert_called_once()
        self.assertEqual(self.events[-1]['type'], 'error')
        self.assertEqual(self.events[-1]['message'], 'boom')
        self.assertIn('cleanup failed', (self.root / 'install.log').read_text())

    def test_unmount_failure_is_fatal_when_finishing(self):
        result = subprocess.CompletedProcess(['umount'], 1, '', 'busy')
        with patch.object(backend.os.path, 'ismount', return_value=True), \
                patch.object(self.installer, 'run', return_value=result):
            with self.assertRaisesRegex(backend.InstallError, 'відмонтувати'):
                self.installer.unmount(check=True)

    def test_unmount_cleans_efi_even_if_root_mount_is_gone(self):
        result = subprocess.CompletedProcess(['umount'], 0, '', '')
        with patch.object(backend.os.path, 'ismount', side_effect=[False, True, False, False]), \
                patch.object(self.installer, 'run', return_value=result) as run:
            self.installer.unmount(check=True)
        run.assert_called_once_with(['umount', '--recursive', str(self.target)], check=False)

    def test_full_stage_order_and_progress(self):
        names = ('preflight', 'partition_disk', 'format', 'copy', 'configure', 'bootloader', 'finish')
        patches = [patch.object(self.installer, name) for name in names]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.assertEqual(self.installer.install(), 0)
        stages = [e['stage'] for e in self.events if e['type'] == 'stage']
        self.assertEqual(stages, [s[0] for s in backend.STAGES])
        percents = [e['percent'] for e in self.events if e['type'] in ('stage', 'progress')]
        self.assertEqual(percents, sorted(percents))
        self.assertEqual(self.events[-1], {'type': 'done', 'warnings': []})

    def test_antigravity_failure_is_only_a_warning(self):
        self.installer.config['antigravity'] = True
        self.installer.stage = 'antigravity'
        with patch.object(backend.os.path, 'ismount', return_value=True), \
                patch('feodal_antigravity.install', side_effect=OSError('offline')):
            self.installer.antigravity()
        self.assertIn('feodal-antigravity install', self.installer.warnings[0])

    def test_main_rejects_bad_json(self):
        result = subprocess.run([sys.executable, str(ROOT / 'shell/feodal_install_backend.py')],
                                input='not json', capture_output=True, text=True,
                                env={**os.environ, 'PYTHONPATH': str(ROOT / 'shell')})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['type'], 'error')


if __name__ == '__main__':
    unittest.main(verbosity=2)

import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))

from feodal_gaming import (  # noqa: E402
    OFFICIAL_PACKAGES,
    _status,
    graphics_devices,
    install_official,
    multilib_enabled,
)


class GamingHelperTests(unittest.TestCase):
    def test_multilib_requires_active_section_and_include(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'pacman.conf'
            config.write_text('# [multilib]\n[options]\nInclude = /mirror\n')
            self.assertFalse(multilib_enabled(config))
            config.write_text('[multilib]\n# Include = /mirror\n')
            self.assertFalse(multilib_enabled(config))
            config.write_text('[multilib]\nInclude = /etc/pacman.d/mirrorlist\n')
            self.assertTrue(multilib_enabled(config))

    def test_lists_only_display_class_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for address, vendor, device, pci_class in (
                ('0000:00:02.0', '0x8086', '0x1234', '0x030000'),
                ('0000:01:00.0', '0x10de', '0x1d16', '0x030200'),
                ('0000:02:00.0', '0x10de', '0xabcd', '0x020000'),
            ):
                path = root / address
                path.mkdir()
                (path / 'vendor').write_text(vendor)
                (path / 'device').write_text(device)
                (path / 'class').write_text(pci_class)
            self.assertEqual(graphics_devices(root), [
                {'vendor': '0x8086', 'device': '0x1234'},
                {'vendor': '0x10de', 'device': '0x1d16'},
            ])

    def test_status_identifies_mx330_and_keeps_aur_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nvidia = root / '0000:01:00.0'
            nvidia.mkdir()
            (nvidia / 'vendor').write_text('0x10de')
            (nvidia / 'device').write_text('0x1d16')
            (nvidia / 'class').write_text('0x030000')
            config = root / 'pacman.conf'
            config.write_text('[multilib]\nInclude = /mirror\n')
            lines = []
            self.assertEqual(_status(config, root, lambda _: None, lines.append), 0)
            self.assertTrue(any('GeForce MX330' in line for line in lines))
            self.assertTrue(any('лише вручну' in line for line in lines))

    def test_non_arch_or_missing_multilib_never_runs_pacman(self):
        runner = Mock()
        self.assertEqual(install_official(
            arch_linux=False, multilib=True, runner=runner, output=Mock()), 2)
        self.assertEqual(install_official(
            arch_linux=True, multilib=False, runner=runner, output=Mock()), 2)
        runner.assert_not_called()

    def test_decline_does_not_run_pacman(self):
        runner = Mock()
        result = install_official(
            arch_linux=True, multilib=True, which=lambda command: '/usr/bin/' + command,
            runner=runner, confirm=lambda _: 'n', output=Mock())
        self.assertEqual(result, 1)
        runner.assert_not_called()

    def test_confirmed_install_uses_fixed_official_package_list(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0))
        result = install_official(
            arch_linux=True, multilib=True, which=lambda command: '/usr/bin/' + command,
            runner=runner, confirm=lambda _: 'y', output=Mock())
        self.assertEqual(result, 0)
        runner.assert_called_once_with(
            ['sudo', 'pacman', '-Syu', '--needed', *OFFICIAL_PACKAGES], check=False)

    def test_pascal_package_names_are_documented_but_not_auto_installed(self):
        from feodal_gaming import NVIDIA_PASCAL_PACKAGES
        self.assertEqual(NVIDIA_PASCAL_PACKAGES, (
            'nvidia-580xx-dkms', 'nvidia-580xx-utils', 'lib32-nvidia-580xx-utils'))
        self.assertNotIn('nvidia-open', OFFICIAL_PACKAGES)
        self.assertFalse(any(package in OFFICIAL_PACKAGES for package in NVIDIA_PASCAL_PACKAGES))


if __name__ == '__main__':
    unittest.main(verbosity=2)

import subprocess
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shell.feodal_hardware import collect_status


class HardwareStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.meminfo = self.root / 'meminfo'
        self.drm = self.root / 'drm'
        self.drm.mkdir()
        self.pci = self.root / 'pci'
        self.pci.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def add_gpu(self, card, vendor='0x10de', device='0x1234',
                pci_class='0x030000', driver='nvidia'):
        device_path = self.drm / card / 'device'
        device_path.mkdir(parents=True)
        (device_path / 'class').write_text(pci_class)
        (device_path / 'vendor').write_text(vendor)
        (device_path / 'device').write_text(device)
        if driver:
            driver_path = self.root / 'drivers' / driver
            driver_path.mkdir(parents=True, exist_ok=True)
            (device_path / 'driver').symlink_to(driver_path)

    def add_pci_gpu(self, address, vendor='0x10de', device='0x1234',
                    pci_class='0x030000', driver=None):
        device_path = self.pci / address
        device_path.mkdir(parents=True)
        (device_path / 'class').write_text(pci_class)
        (device_path / 'vendor').write_text(vendor)
        (device_path / 'device').write_text(device)
        if driver:
            driver_path = self.root / 'drivers' / driver
            driver_path.mkdir(parents=True, exist_ok=True)
            (device_path / 'driver').symlink_to(driver_path)

    def fake_which(self, *available):
        commands = set(available)
        return lambda command: f'/usr/bin/{command}' if command in commands else None

    def test_reads_memory_and_intel_gpu_without_claiming_nvidia_ready(self):
        self.meminfo.write_text('MemTotal: 8192000 kB\nMemAvailable: 2048500 kB\n')
        self.add_gpu('card0', vendor='0x8086', device='0x1234', driver='i915')
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, 'NVIDIA, 550.00', ''))

        status = collect_status(self.meminfo, self.drm,
                                self.fake_which('nvidia-smi', 'prime-run', 'steam'), runner,
                                self.pci)

        self.assertEqual(status['memory_total_mib'], 8000)
        self.assertEqual(status['memory_available_mib'], 2000)
        self.assertEqual(status['gpus'], [
            {'vendor': '0x8086', 'device': '0x1234', 'driver': 'i915'}
        ])
        self.assertFalse(status['nvidia_ready'])
        self.assertTrue(status['prime_available'])
        self.assertTrue(status['steam_available'])
        runner.assert_not_called()

    def test_nvidia_ready_requires_sysfs_device_and_successful_bounded_command(self):
        self.meminfo.write_text('MemTotal: 4096000 kB\nMemAvailable: 1024000 kB\n')
        self.add_gpu('card1', device='0x1234')
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, 'NVIDIA, 550.00', ''))

        status = collect_status(self.meminfo, self.drm,
                                self.fake_which('nvidia-smi'), runner, self.pci)

        self.assertTrue(status['nvidia_ready'])
        runner.assert_called_once_with(
            ['/usr/bin/nvidia-smi', '--query-gpu=name,driver_version',
             '--format=csv,noheader'],
            capture_output=True, text=True, timeout=3, check=False
        )
        self.assertFalse(status['prime_available'])
        self.assertFalse(status['steam_available'])

    def test_installed_nvidia_smi_does_not_imply_a_device_or_readiness(self):
        self.meminfo.write_text('MemTotal: 1024 kB\nMemAvailable: 512 kB\n')
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, 'No devices', ''))

        status = collect_status(self.meminfo, self.drm,
                                self.fake_which('nvidia-smi'), runner, self.pci)

        self.assertFalse(status['nvidia_ready'])
        runner.assert_not_called()

    def test_broken_or_timed_out_nvidia_smi_is_not_ready(self):
        self.meminfo.write_text('MemTotal: 1024 kB\nMemAvailable: 512 kB\n')
        self.add_gpu('card0')
        runner = Mock(side_effect=subprocess.TimeoutExpired('nvidia-smi', 3))

        status = collect_status(self.meminfo, self.drm,
                                self.fake_which('nvidia-smi'), runner, self.pci)

        self.assertFalse(status['nvidia_ready'])
        self.assertTrue(any('не завершила' in note for note in status['notes']))

    def test_absent_proc_sysfs_and_commands_return_safe_defaults(self):
        status = collect_status(self.root / 'missing-meminfo', self.root / 'missing-drm',
                                self.fake_which(), Mock(), self.root / 'missing-pci')

        self.assertIsInstance(status['kernel'], str)
        self.assertEqual(status['memory_total_mib'], 0)
        self.assertEqual(status['memory_available_mib'], 0)
        self.assertEqual(status['gpus'], [])
        self.assertFalse(status['nvidia_ready'])
        self.assertFalse(status['prime_available'])
        self.assertFalse(status['steam_available'])
        self.assertTrue(status['notes'])

    def test_only_display_class_cards_are_reported_and_older_nvidia_is_noted(self):
        self.meminfo.write_text('MemTotal: 2048 kB\nMemAvailable: 1024 kB\n')
        self.add_gpu('card0', device='0x1d16')
        self.add_gpu('card1', pci_class='0x020000', driver='ethernet')
        (self.drm / 'card0-DP-1').mkdir()
        runner = Mock(return_value=subprocess.CompletedProcess([], 1, '', ''))

        status = collect_status(self.meminfo, self.drm,
                                self.fake_which('nvidia-smi'), runner, self.pci)

        self.assertEqual(len(status['gpus']), 1)
        self.assertFalse(status['nvidia_ready'])
        self.assertTrue(any('580xx' in note for note in status['notes']))

    def test_pci_enumeration_finds_unbound_gpu_without_a_drm_card(self):
        self.meminfo.write_text('MemTotal: 2048 kB\nMemAvailable: 1024 kB\n')
        self.add_pci_gpu('0000:01:00.0', driver=None)
        runner = Mock()

        status = collect_status(self.meminfo, self.drm,
                                self.fake_which('nvidia-smi'), runner, self.pci)

        self.assertEqual(status['gpus'], [
            {'vendor': '0x10de', 'device': '0x1234', 'driver': ''}
        ])
        self.assertFalse(status['nvidia_ready'])
        self.assertTrue(any('не прив’язаний' in note for note in status['notes']))
        runner.assert_not_called()

    def test_nvidia_smi_with_nouveau_bound_does_not_claim_nvidia_ready(self):
        self.meminfo.write_text('MemTotal: 2048 kB\nMemAvailable: 1024 kB\n')
        self.add_pci_gpu('0000:01:00.0', driver='nouveau')
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, 'NVIDIA, 550.00', ''))

        status = collect_status(self.meminfo, self.drm,
                                self.fake_which('nvidia-smi'), runner, self.pci)

        self.assertFalse(status['nvidia_ready'])
        runner.assert_not_called()

    def test_pci_and_drm_views_of_same_device_are_not_duplicated(self):
        self.meminfo.write_text('MemTotal: 2048 kB\nMemAvailable: 1024 kB\n')
        self.add_pci_gpu('0000:00:02.0', vendor='0x8086', device='0x1234', driver='i915')
        card = self.drm / 'card0'
        card.mkdir()
        (card / 'device').symlink_to(self.pci / '0000:00:02.0')

        status = collect_status(self.meminfo, self.drm, self.fake_which(), Mock(), self.pci)

        self.assertEqual(len(status['gpus']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)

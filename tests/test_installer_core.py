from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))
import feodal_installer_core as core  # noqa: E402

GB = 1000 ** 3


def disk(name, size, children=(), **extra):
    return {'name': name, 'path': f'/dev/{name}', 'size': size, 'type': 'disk', 'ro': False, 'rm': False,
            'model': 'Test Disk', 'tran': 'sata', 'children': list(children), **extra}


def part(name, size, fstype=None, label=None, mounts=()):
    return {'name': name, 'path': f'/dev/{name}', 'size': size, 'type': 'part', 'fstype': fstype,
            'label': label, 'mountpoints': list(mounts) or [None]}


class CoreTests(unittest.TestCase):
    def test_partition_names(self):
        self.assertEqual(core.partition_path('/dev/sda', 2), '/dev/sda2')
        self.assertEqual(core.partition_path('/dev/nvme0n1', 3), '/dev/nvme0n1p3')
        self.assertEqual(core.partition_path('/dev/mmcblk0', 1), '/dev/mmcblk0p1')

    def test_disk_choices_block_unsafe_targets(self):
        tree = [
            disk('nvme0n1', 512 * GB, [part('nvme0n1p1', 100_000_000, 'vfat', 'SYSTEM'),
                                       part('nvme0n1p3', 400 * GB, 'ntfs', 'Windows')], tran='nvme'),
            disk('sdb', 32 * GB, [part('sdb1', 2 * GB, 'iso9660', 'FEODAL', ['/run/archiso/bootmnt'])], rm=True),
            disk('sdc', 8 * GB),
            disk('sdd', 64 * GB, [part('sdd1', 64 * GB, 'ext4', None, ['/media/x'])]),
            disk('sde', 64 * GB, ro=True),
            disk('vda', 40 * GB),
            disk('zram0', 4 * GB), disk('fd0', 4096), disk('loop0', 2 * GB),
            {'name': 'sr0', 'path': '/dev/sr0', 'size': 2 * GB, 'type': 'rom'},
        ]
        choices = {d['path']: d for d in core.disk_choices(tree)}
        self.assertEqual(set(choices), {'/dev/nvme0n1', '/dev/sdb', '/dev/sdc', '/dev/sdd', '/dev/sde', '/dev/vda'})
        self.assertIsNone(choices['/dev/nvme0n1']['reason'])
        self.assertEqual(choices['/dev/nvme0n1']['transport'], 'NVME')
        self.assertIn('NTFS 400 ГБ «Windows»', choices['/dev/nvme0n1']['partitions'])
        self.assertIn('запущено', choices['/dev/sdb']['reason'])
        self.assertIn('Замалий', choices['/dev/sdc']['reason'])
        self.assertIn('змонтовані', choices['/dev/sdd']['reason'])
        self.assertIn('читання', choices['/dev/sde']['reason'])
        self.assertIsNone(choices['/dev/vda']['reason'])
        self.assertIn('запущено', core.disk_choices([disk('vdb', 40 * GB)], '/dev/vdb')[0]['reason'])

    def test_live_boot_disk_resolves_parent(self):
        outputs = iter(['/dev/sdb1\n', 'sdb\n'])

        def runner(*_, **__):
            return type('R', (), {'stdout': next(outputs)})()
        self.assertEqual(core.live_boot_disk(runner), '/dev/sdb')

    def test_user_validation(self):
        good = {'username': 'taras', 'password': 'secret1', 'password_confirm': 'secret1', 'hostname': 'feodal',
                'fullname': 'Тарас', 'timezone': 'Europe/Kyiv' if Path('/usr/share/zoneinfo/Europe/Kyiv').exists()
                else 'UTC', 'locale': 'uk_UA.UTF-8'}
        self.assertEqual(core.validate_user(good), [])
        for change, field in (({'username': 'Taras'}, 'username'), ({'username': 'root'}, 'username'),
                              ({'username': '1abc'}, 'username'), ({'password': 'abc', 'password_confirm': 'abc'},
                                                                   'password'),
                              ({'password_confirm': 'other'}, 'password'), ({'hostname': 'my host'}, 'hostname'),
                              ({'hostname': '-x'}, 'hostname'), ({'fullname': 'a:b'}, 'fullname'),
                              ({'password': 'secret\r1', 'password_confirm': 'secret\r1'}, 'password'),
                              ({'fullname': 'Тарас\x00'}, 'fullname'), ({'username': None}, 'username'),
                              ({'timezone': '\x00'}, 'timezone'),
                              ({'timezone': '../../etc/passwd'}, 'timezone'), ({'timezone': 'Mars/Base'}, 'timezone'),
                              ({'locale': 'xx_XX'}, 'locale')):
            problems = core.validate_user({**good, **change})
            self.assertIn(field, [name for name, _ in problems], change)
        self.assertIn('config', [name for name, _ in core.validate_user(None)])

    def test_sizes_and_timezones(self):
        self.assertEqual(core.human_size(512 * GB), '512 ГБ')
        self.assertEqual(core.human_size(int(1.5 * 1000 ** 4)), '1.5 ТБ')
        zones = core.timezones()
        self.assertIn(core.default_timezone(zones), zones)

    def test_live_detection(self):
        with patch.object(core, 'LIVE_MARKERS', (Path('/nonexistent-feodal'),)):
            self.assertFalse(core.is_live())


if __name__ == '__main__':
    unittest.main(verbosity=2)

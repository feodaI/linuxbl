import configparser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'iso/overlay/airootfs/etc/systemd/zram-generator.conf'


class MemoryProfileTests(unittest.TestCase):
    def test_zram_generator_profile(self):
        parser = configparser.ConfigParser(interpolation=None)
        self.assertTrue(parser.read(CONFIG), 'zram-generator config should be readable')
        self.assertEqual(parser.sections(), ['zram0'])
        self.assertEqual(parser['zram0']['zram-size'], 'min(ram / 2, 4096)')
        self.assertEqual(parser['zram0']['compression-algorithm'], 'zstd')
        self.assertEqual(parser['zram0'].getint('swap-priority'), 100)


if __name__ == '__main__':
    unittest.main(verbosity=2)

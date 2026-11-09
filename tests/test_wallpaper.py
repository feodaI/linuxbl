import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))
import feodal_wallpaper as wallpaper  # noqa: E402


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name)
        patcher = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.config)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_bundled_image_is_licensed_and_covers_screen(self):
        bundled = ROOT / 'assets/wallpaper/kingdom.jpg'
        self.assertTrue(wallpaper.is_image(bundled))
        credits = (ROOT / 'assets/wallpaper/CREDITS').read_text()
        self.assertIn('David Revoy', credits)
        self.assertIn('CC BY 3.0', credits)
        pixbuf = wallpaper.load_scaled(1366, 768)
        self.assertGreaterEqual(pixbuf.get_width(), 1366)
        self.assertGreaterEqual(pixbuf.get_height(), 768)
        # Cover scaling crops one axis only, never stretches.
        self.assertTrue(pixbuf.get_width() == 1366 or pixbuf.get_height() == 768)

    def test_user_wallpaper_overrides_and_resets(self):
        wallpaper.set_user_wallpaper(ROOT / 'assets/wallpaper/kingdom.jpg')
        self.assertEqual(wallpaper.user_path(), self.config / 'feodal/wallpaper')
        self.assertTrue(wallpaper.user_path().is_file())
        wallpaper.reset_user_wallpaper()
        self.assertFalse(wallpaper.user_path().exists())
        wallpaper.reset_user_wallpaper()

    def test_rejects_non_images_and_skips_broken_override(self):
        text = self.config / 'notes.txt'
        text.write_text('not an image')
        with self.assertRaises(ValueError):
            wallpaper.set_user_wallpaper(text)
        self.assertFalse(wallpaper.user_path().exists())
        wallpaper.user_path().parent.mkdir(parents=True)
        wallpaper.user_path().write_bytes(b'\xff\xd8broken')
        self.assertIsNotNone(wallpaper.load_scaled(800, 600))

    def test_missing_images_return_none(self):
        with patch.object(wallpaper, 'BUNDLED', (self.config / 'missing.jpg',)):
            self.assertIsNone(wallpaper.load_scaled(800, 600))


if __name__ == '__main__':
    unittest.main(verbosity=2)

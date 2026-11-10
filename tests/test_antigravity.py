import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))
import feodal_antigravity as ag  # noqa: E402


def make_archive(path, members):
    with tarfile.open(path, 'w:gz') as tar:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            if kind == 'dir':
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == 'link':
                info.type = tarfile.SYMTYPE
                info.linkname = data
                tar.addfile(info)
            else:
                info.size = len(data)
                info.mode = 0o755
                tar.addfile(info, io.BytesIO(data))
    return hashlib.blake2b(Path(path).read_bytes()).hexdigest()


class AntigravityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.home = self.dir / 'home'
        self.home.mkdir()

    def test_pinned_download_metadata(self):
        self.assertTrue(ag.URL.startswith('https://storage.googleapis.com/antigravity-public/'))
        self.assertIn(ag.VERSION, ag.URL)
        self.assertEqual(len(ag.B2SUM), 128)

    def test_installs_per_user_with_final_paths(self):
        archive = self.dir / 'a.tar.gz'
        digest = make_archive(archive, [('Antigravity-x64', b'', 'dir'),
                                        ('Antigravity-x64/antigravity', b'#!/bin/sh\n', 'file')])
        with patch.object(ag, 'B2SUM', digest):
            binary = ag.install(self.home, archive=archive, final_home=Path('/home/taras'))
            ag.install(self.home, archive=archive, final_home=Path('/home/taras'))  # reinstall replaces
        self.assertEqual(binary, Path('/home/taras/.local/opt/antigravity/antigravity'))
        self.assertTrue(ag.installed(self.home))
        self.assertEqual(Path(ag.paths(self.home)['bin']).readlink(), binary)
        self.assertIn('Exec="/home/taras/.local/opt/antigravity/antigravity"',
                      ag.paths(self.home)['desktop'].read_text())
        self.assertEqual(sorted(p.name for p in (self.home / '.local/opt').iterdir()), ['antigravity'])
        ag.uninstall(self.home)
        self.assertFalse(ag.installed(self.home))
        self.assertFalse(ag.paths(self.home)['desktop'].exists())

    def test_rejects_wrong_checksum_and_unsafe_archives(self):
        archive = self.dir / 'a.tar.gz'
        make_archive(archive, [('Antigravity-x64/antigravity', b'x', 'file')])
        with self.assertRaisesRegex(ag.AntigravityError, 'Контрольна сума'):
            ag.install(self.home, archive=archive)
        for members in ([('../evil', b'x', 'file')], [('Antigravity-x64/link', '/etc/passwd', 'link')],
                        [('Other/antigravity', b'x', 'file')]):
            digest = make_archive(archive, members)
            with patch.object(ag, 'B2SUM', digest), self.assertRaises(ag.AntigravityError):
                ag.install(self.home, archive=archive)
        self.assertFalse(ag.installed(self.home))
        self.assertFalse((self.dir / 'evil').exists())

    def test_download_verifies_stream(self):
        payload = b'antigravity-bytes'

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False
        seen = []
        with patch.object(ag, 'B2SUM', hashlib.blake2b(payload).hexdigest()):
            ag.download(self.dir / 'out', lambda d, t: seen.append(d), opener=lambda *_a, **_k: Response(payload))
        self.assertEqual((self.dir / 'out').read_bytes(), payload)
        self.assertEqual(seen[-1], len(payload))
        with self.assertRaises(ag.AntigravityError):
            ag.download(self.dir / 'out', opener=lambda *_a, **_k: Response(b'tampered'))


if __name__ == '__main__':
    unittest.main(verbosity=2)

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bb_launcher import boss_compiler as compiler
from bb_launcher.core import ValidationError


class BossCompilerTests(unittest.TestCase):
    def archive(self, extra=None):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('DarkScript3.exe', b'test compiler')
            archive.writestr('Resources/bb-common.emedf.json', b'test instruction metadata')
            if extra:
                archive.writestr(extra, b'bad')
        return stream.getvalue()

    def test_download_cache_reuse_and_resource_tamper(self):
        blob = self.archive()
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(compiler, 'ARCHIVE_SHA256', hashlib.sha256(blob).hexdigest()), \
                patch.object(compiler, 'EXECUTABLE_SHA256', hashlib.sha256(b'test compiler').hexdigest()), \
                patch.object(compiler.urllib.request, 'urlopen', return_value=io.BytesIO(blob)) as download:
            root = Path(temporary)
            executable = compiler.ensure_boss_compiler(root, lambda _: None)
            self.assertEqual(b'test compiler', executable.read_bytes())
            self.assertEqual(executable, compiler.ensure_boss_compiler(root, lambda _: None))
            download.assert_called_once()
            (executable.parent / 'Resources/bb-common.emedf.json').write_bytes(b'changed metadata')
            with self.assertRaisesRegex(ValidationError, 'resource changed'):
                compiler.ensure_boss_compiler(root, lambda _: None)
            self.assertEqual(1, download.call_count)

    def test_wrong_archive_is_never_published(self):
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(compiler.urllib.request, 'urlopen', return_value=io.BytesIO(b'wrong release')):
            with self.assertRaisesRegex(ValidationError, 'archive failed verification'):
                compiler.ensure_boss_compiler(Path(temporary), lambda _: None)
            self.assertTrue((Path(temporary) / 'tools').is_dir())
            self.assertFalse((Path(temporary) / 'tools' / ('DarkScript3-' + compiler.VERSION)).exists())

    def test_archive_paths_cannot_escape_installation(self):
        for name in ('../outside.exe', 'C:/outside.exe', 'Resources\\outside.exe'):
            with self.subTest(name=name), zipfile.ZipFile(io.BytesIO(self.archive())) as archive:
                # ZipInfo construction on Windows normalizes backslashes;
                # model an archive reader returning the original hostile name.
                entry = zipfile.ZipInfo('placeholder')
                entry.filename = name
                entries = archive.infolist() + [entry]
                with patch.object(archive, 'infolist', return_value=entries):
                    with self.assertRaisesRegex(ValidationError, 'invalid path'):
                        compiler._members(archive)

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.import_legacy_game import LEGACY, import_game


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'core.filemode', 'true')
        self.game = self.source / LEGACY
        self.game.mkdir(parents=True)
        (self.game / 'project.godot').write_text('config_version=5\n')
        (self.game / 'asset.bin').write_bytes(bytes(range(256)))
        executable = self.game / 'run.sh'
        executable.write_text('#!/bin/sh\n')
        executable.chmod(0o755)
        self.dest = self.root / 'destination' / 'game'
        self.commit = self.snapshot()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.source), *args]).decode().strip()

    def snapshot(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def test_pinned_snapshot_bytes_and_modes(self):
        (self.game / 'asset.bin').write_bytes(b'changed')
        self.snapshot()
        (self.game / 'untracked').touch()
        commit, tree, count = import_game(self.source, self.commit, self.dest)
        self.assertEqual(commit, self.commit)
        self.assertEqual(tree, self.git('rev-parse', f'{commit}:{LEGACY}'))
        self.assertEqual(count, 3)
        self.assertEqual((self.dest / 'asset.bin').read_bytes(), bytes(range(256)))
        self.assertEqual((self.dest / 'run.sh').stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.dest / 'asset.bin').stat().st_mode & 0o777, 0o644)
        self.assertFalse((self.dest / 'untracked').exists())

    def test_existing_destination_is_untouched(self):
        self.dest.mkdir(parents=True)
        marker = self.dest / 'keep'
        marker.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            import_game(self.source, self.commit, self.dest)
        self.assertEqual(marker.read_bytes(), b'keep')

    def test_symlink_in_source_is_rejected(self):
        (self.game / 'link').symlink_to('asset.bin')
        with self.assertRaisesRegex(ValueError, 'Unsupported tree entry'):
            import_game(self.source, self.snapshot(), self.dest)
        self.assertFalse(self.dest.exists())

    def test_missing_project_is_rejected(self):
        (self.game / 'project.godot').unlink()
        with self.assertRaisesRegex(ValueError, 'missing project.godot'):
            import_game(self.source, self.snapshot(), self.dest)
        self.assertFalse(self.dest.exists())

    def test_export_ignore_fails_closed(self):
        (self.game / '.gitattributes').write_text('asset.bin export-ignore\n')
        with self.assertRaisesRegex(ValueError, 'every tracked file'):
            import_game(self.source, self.snapshot(), self.dest)
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.dest.parent.iterdir()), [])

    def test_dangling_destination_symlink_is_rejected(self):
        self.dest.parent.mkdir(parents=True)
        self.dest.symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            import_game(self.source, self.commit, self.dest)
        self.assertTrue(self.dest.is_symlink())


if __name__ == '__main__':
    unittest.main()

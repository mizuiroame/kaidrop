import os
import tempfile
import unittest
from pathlib import Path

from kaidrop.foldertree import subfolders
from kaidrop.places import drive_label, file_icon, is_inside


class PlacesTest(unittest.TestCase):
    def test_drive_labels(self):
        self.assertEqual(drive_label("D:\\", "Datos"), "Datos (D:)")
        self.assertEqual(drive_label("C:\\", ""), "Local Disk (C:)")
        self.assertEqual(drive_label("E:\\", "", 2), "USB Drive (E:)")
        self.assertEqual(drive_label("G:\\", "", 4), "Network Drive (G:)")

    def test_file_icons(self):
        self.assertEqual(file_icon("01 Canción.FLAC"), "audio")
        self.assertEqual(file_icon("track.dsf"), "audio")
        self.assertEqual(file_icon("cover.jpg"), "image")
        self.assertEqual(file_icon("notes.txt"), "file")
        self.assertEqual(file_icon("README"), "file")

    def test_is_inside(self):
        music = Path.home() / "Music"
        self.assertTrue(is_inside(music, music))
        self.assertTrue(is_inside(music / "Album", music))
        self.assertFalse(is_inside(Path.home() / "Musicals", music))
        root = Path(Path.home().anchor)
        self.assertTrue(is_inside(music, root))
        if os.name == "nt":
            self.assertTrue(is_inside(Path(str(music).upper()), music))


class SubfoldersTest(unittest.TestCase):
    def test_folders_only_sorted_without_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("beta", "Alpha", "みずいろ", ".git", "$RECYCLE.BIN"):
                (base / name).mkdir()
            (base / "song.mp3").write_bytes(b"")
            self.assertEqual([p.name for p in subfolders(base)], ["Alpha", "beta", "みずいろ"])

    def test_missing_folder(self):
        self.assertEqual(subfolders(Path(tempfile.gettempdir()) / "kaidrop-missing-folder"), [])


if __name__ == "__main__":
    unittest.main()

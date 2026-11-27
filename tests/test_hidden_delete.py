"""Deleting a console folder that holds names the Switch 2 hides from its
listings (accents, Japanese): they can only be deleted by name, taken from
the folder on this computer they were sent from."""
import ftplib
import tempfile
import unittest
from pathlib import Path

from kaidrop.panes import same_name_folder
from kaidrop.remote import HiddenFiles, delete_tree


class Switch2Ftp:
    """A console's FTP: holds a set of paths (folders end with "/"), lists
    only ASCII names, deletes any name it's given, and refuses to remove a
    folder that still holds something."""

    def __init__(self, paths):
        self.paths = set(paths)

    def _children(self, folder):
        folder = folder.rstrip("/") + "/"
        out = set()
        for p in self.paths:
            if p != folder and p.startswith(folder):
                rest = p[len(folder):]
                name = rest.split("/", 1)[0]
                out.add((name, "/" in rest))
        return out

    def mlsd(self, path, facts=None):
        if path.rstrip("/") + "/" not in self.paths:
            raise ftplib.error_perm("550 No such folder")
        return iter([(name, {"type": "dir" if is_dir else "file", "size": "1"})
                     for name, is_dir in sorted(self._children(path)) if name.isascii()])

    def delete(self, path):
        if path not in self.paths:
            raise ftplib.error_perm("550 No such file")
        self.paths.remove(path)

    def rmd(self, path):
        folder = path.rstrip("/") + "/"
        if folder not in self.paths:
            raise ftplib.error_perm("550 No such folder")
        if self._children(path):
            raise ftplib.error_perm("550 Directory not empty")
        self.paths.remove(folder)


def make_local(root: Path, names):
    for name in names:
        p = root / name
        if name.endswith("/"):
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")


CONSOLE = ["/music/", "/music/Yoru/", "/music/Yoru/01 Minato.flac", "/music/Yoru/02 夜の港.flac",
           "/music/Yoru/Café/", "/music/Yoru/Café/03 灯り.flac", "/music/Yoru/Disc 2/",
           "/music/Yoru/Disc 2/04 港の歌.flac"]


class HiddenDeleteTest(unittest.TestCase):
    def test_without_a_local_folder_the_reason_is_clear(self):
        ftp = Switch2Ftp(CONSOLE)
        with self.assertRaises(HiddenFiles) as caught:
            delete_tree(ftp, "/music/Yoru", True)
        self.assertIn("/music/Yoru", str(caught.exception))
        self.assertIn("Japanese", str(caught.exception))
        self.assertIsInstance(caught.exception, ftplib.error_perm)  # Still caught as an FTP refusal.
        self.assertNotIn("/music/Yoru/01 Minato.flac", ftp.paths)  # What was listed went.

    def test_the_local_folder_gives_the_hidden_names(self):
        ftp = Switch2Ftp(CONSOLE)
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "Yoru"
            make_local(local, ["01 Minato.flac", "02 夜の港.flac", "Café/03 灯り.flac", "Disc 2/04 港の歌.flac",
                               "not on the console 音.flac"])
            delete_tree(ftp, "/music/Yoru", True, local=local)
            self.assertEqual(len(list(local.rglob("*"))), 7)  # Nothing on this computer was touched.
        self.assertEqual(ftp.paths, {"/music/"})

    def test_a_local_folder_missing_some_names_still_fails_clearly(self):
        ftp = Switch2Ftp(CONSOLE)
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "Yoru"
            make_local(local, ["02 夜の港.flac"])
            with self.assertRaises(HiddenFiles):
                delete_tree(ftp, "/music/Yoru", True, local=local)
        self.assertNotIn("/music/Yoru/02 夜の港.flac", ftp.paths)
        self.assertIn("/music/Yoru/Café/03 灯り.flac", ftp.paths)

    def test_names_that_would_climb_are_not_tried(self):
        ftp = Switch2Ftp(["/m/", "/m/曲.mp3", "/keep/", "/keep/曲.mp3"])
        with tempfile.TemporaryDirectory() as tmp:
            make_local(Path(tmp), ["曲.mp3"])
            delete_tree(ftp, "/m", True, local=Path(tmp))
        self.assertEqual(ftp.paths, {"/keep/", "/keep/曲.mp3"})


class SameNameFolderTest(unittest.TestCase):
    def test_found_inside_the_open_folder_or_as_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Yoru").mkdir()
            self.assertEqual(same_name_folder(root, "Yoru"), root / "Yoru")
            self.assertEqual(same_name_folder(root, "yoru"), root / "yoru")
            self.assertEqual(same_name_folder(root / "Yoru", "Yoru"), root / "Yoru")
            self.assertIsNone(same_name_folder(root, "Other"))
            self.assertIsNone(same_name_folder(None, "Yoru"))


if __name__ == "__main__":
    unittest.main()

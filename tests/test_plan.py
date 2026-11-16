import tempfile
import unittest
from pathlib import Path

from kaidrop.plan import build_plan


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        album = root / "Música" / "Disco Ñ"
        album.mkdir(parents=True)
        (album / "01 Canción.flac").write_bytes(b"abc")
        (album / "cover.jpg").write_bytes(b"x")
        (root / "Música" / "02 Plain.mp3").write_bytes(b"12345")
        (root / "single.ogg").write_bytes(b"z")
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_names_on_the_console(self):
        plan = build_plan([self.root / "Música", self.root / "single.ogg"], "/Music/")
        remotes = {item.remote for item in plan.items}
        self.assertEqual(remotes, {"/Music/Musica/Disco N/01 Cancion.flac", "/Music/Musica/Disco N/cover.jpg",
                                   "/Music/Musica/02 Plain.mp3", "/Music/single.ogg"})
        self.assertEqual(plan.total_bytes, 3 + 1 + 5 + 1)
        # Everything under a renamed folder counts as renamed; single.ogg doesn't.
        self.assertEqual(plan.renamed_count, 3)
        self.assertEqual(plan.folders[:3], ("/Music", "/Music/Musica", "/Music/Musica/Disco N"))

    def test_names_as_they_are(self):
        plan = build_plan([self.root / "Música"], "Music", plain=False)
        self.assertIn("/Music/Música/Disco Ñ/01 Canción.flac", {item.remote for item in plan.items})
        self.assertEqual(plan.renamed_count, 0)

    def test_root_folder(self):
        plan = build_plan([self.root / "single.ogg"], "")
        self.assertEqual(plan.items[0].remote, "/single.ogg")
        self.assertEqual(plan.folders, ())

    def test_local_files_untouched(self):
        build_plan([self.root / "Música"], "/Music")
        self.assertTrue((self.root / "Música" / "Disco Ñ" / "01 Canción.flac").exists())


if __name__ == "__main__":
    unittest.main()

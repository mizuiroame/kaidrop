import unittest

from kaidrop.names import ascii_name, folder_name, is_plain, unique_names


class NamesTest(unittest.TestCase):
    def test_accents_are_dropped(self):
        self.assertEqual(ascii_name("06 Canción.flac"), "06 Cancion.flac")
        self.assertEqual(ascii_name("Ñandú.mp3"), "Nandu.mp3")
        self.assertEqual(folder_name("Música Española"), "Musica Espanola")

    def test_typographic_punctuation(self):
        self.assertEqual(ascii_name("09 Why’d You Only Call Me.flac"), "09 Why'd You Only Call Me.flac")
        self.assertEqual(ascii_name("¿Qué? – Live.mp3"), "Que_ - Live.mp3")

    def test_unreadable_names(self):
        self.assertEqual(ascii_name("04 みずいろの雨.mp3"), "04 _.mp3")
        self.assertEqual(ascii_name("みずいろ.mp3"), "track.mp3")
        self.assertEqual(ascii_name(".mp3"), "track.mp3")
        self.assertEqual(folder_name("東京"), "untitled")

    def test_folders_keep_dots(self):
        self.assertEqual(folder_name("Vol. 1"), "Vol. 1")

    def test_is_plain(self):
        self.assertTrue(is_plain("01 Song (Live) & More.flac"))
        self.assertFalse(is_plain("Canción.flac"))
        self.assertFalse(is_plain("a:b.mp3"))

    def test_unique_names(self):
        names = unique_names(["Canción.mp3", "Cancion.mp3", "Vol. 1", "Vol. 1 "], {"Vol. 1", "Vol. 1 "})
        self.assertEqual(sorted(names.values(), key=str.lower),
                         sorted(["Cancion.mp3", "Cancion (2).mp3", "Vol. 1", "Vol. 1 (2)"], key=str.lower))
        # Case doesn't make names different on the console.
        same = unique_names(["a.mp3", "A.mp3"]).values()
        self.assertEqual({name.lower() for name in same}, {"a.mp3", "a (2).mp3"})

    def test_names_kept_without_plain(self):
        self.assertEqual(unique_names(["Canción.mp3"], plain=False), {"Canción.mp3": "Canción.mp3"})


if __name__ == "__main__":
    unittest.main()

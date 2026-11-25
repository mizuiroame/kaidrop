import unittest

from kaidrop.names import MAX_LENGTH, ascii_name, folder_name, is_plain, unique_names


class NamesTest(unittest.TestCase):
    def test_accents_are_dropped(self):
        self.assertEqual(ascii_name("06 Canción.flac"), "06 Cancion.flac")
        self.assertEqual(ascii_name("Ñandú.mp3"), "Nandu.mp3")
        self.assertEqual(folder_name("Música Española"), "Musica Espanola")

    def test_typographic_punctuation(self):
        self.assertEqual(ascii_name("09 Why’d You Only Call Me.flac"), "09 Why'd You Only Call Me.flac")
        self.assertEqual(ascii_name("¿Qué? – Live.mp3"), "Que_ - Live.mp3")

    def test_other_alphabets_in_latin_letters(self):
        self.assertEqual(ascii_name("04 みずいろの空.mp3"), "04 Mizuiro no Sora.mp3")
        self.assertEqual(ascii_name("水色.mp3"), "Mizuiro.mp3")
        self.assertEqual(folder_name("東京"), "Tokyo")
        self.assertEqual(folder_name("Москва"), "Moskva")

    def test_unreadable_names(self):
        self.assertEqual(ascii_name("04 ☂.mp3"), "04 _.mp3")
        self.assertEqual(ascii_name("☂☃.mp3"), "track.mp3")
        self.assertEqual(ascii_name(".mp3"), "track.mp3")
        self.assertEqual(folder_name("☂"), "untitled")

    def test_long_names_are_cut(self):
        name = ascii_name("水色" * 200 + ".flac")
        self.assertLessEqual(len(name), MAX_LENGTH)
        self.assertTrue(name.endswith("Mizuiro.flac") or name.endswith(".flac"))
        self.assertLessEqual(len(folder_name("東京" * 200)), MAX_LENGTH)

    def test_romanized_names_stay_unique(self):
        names = unique_names(["水色.mp3", "Mizuiro.mp3", "みずいろ.mp3"])
        self.assertEqual(sorted(names.values(), key=str.lower),
                         sorted(["Mizuiro.mp3", "Mizuiro (2).mp3", "Mizuiro (3).mp3"], key=str.lower))

    def test_the_folder_tells_japanese_from_chinese(self):
        self.assertEqual(ascii_name("雨.mp3", "C:\\Music\\みずいろ楽団"), "Ame.mp3")
        self.assertEqual(ascii_name("雨.mp3", "C:\\Music\\中国音乐"), "Yu.mp3")
        names = unique_names(["雨.mp3"], where="D:\\歌\\ひかり")
        self.assertEqual(names, {"雨.mp3": "Ame.mp3"})

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

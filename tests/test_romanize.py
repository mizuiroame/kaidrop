import unittest

from kaidrop import hangul, japanese, kana
from kaidrop.romanize import kanji_are_japanese, romanize


class KanaTest(unittest.TestCase):
    def test_hepburn(self):
        self.assertEqual(kana.romanize("しゃしん"), "shashin")
        self.assertEqual(kana.romanize("ちゃんと"), "chanto")
        self.assertEqual(kana.romanize("ふじ"), "fuji")
        self.assertEqual(kana.romanize("つき"), "tsuki")

    def test_small_tsu_doubles(self):
        self.assertEqual(kana.romanize("きって"), "kitte")
        self.assertEqual(kana.romanize("まっちゃ"), "matcha")
        self.assertEqual(kana.romanize("マッ"), "mat")  # Joins the next word: mat+te.

    def test_long_mark_and_n(self):
        self.assertEqual(kana.romanize("コーヒー"), "koohii")
        self.assertEqual(kana.romanize("けんいち"), "ken'ichi")
        self.assertEqual(kana.romanize("さんぽ"), "sanpo")

    def test_small_vowels_in_loanwords(self):
        self.assertEqual(kana.romanize("ファイティング"), "faitingu")
        self.assertEqual(kana.romanize("ヴァイオリン"), "vaiorin")
        self.assertEqual(kana.romanize("ウィンドウ"), "windou")
        self.assertEqual(kana.romanize("シェフ"), "shefu")

    def test_repeat_marks(self):
        self.assertEqual(kana.romanize("いすゞ"), "isuzu")
        self.assertEqual(kana.romanize("こゝろ"), "kokoro")


class HangulTest(unittest.TestCase):
    def test_revised_romanization(self):
        self.assertEqual(hangul.romanize("한국어"), "hangugeo")  # Carried over before a vowel.
        self.assertEqual(hangul.romanize("국물"), "gungmul")     # Nasal before ㅁ.
        self.assertEqual(hangul.romanize("신라"), "silla")       # ㄴ next to ㄹ.
        self.assertEqual(hangul.romanize("봄날"), "bomnal")
        self.assertEqual(hangul.romanize("좋다"), "jota")        # ㅎ aspirates ㄷ.
        self.assertEqual(hangul.romanize("서울"), "seoul")


class JapaneseTest(unittest.TestCase):
    def test_readings_by_word(self):
        self.assertEqual(japanese.romanize("水色"), "Mizuiro")  # Not "suishoku".
        self.assertEqual(japanese.romanize("水色の雨"), "Mizuiro no Ame")
        self.assertEqual(japanese.romanize("夜に駆ける"), "Yoru ni Kakeru")

    def test_endings_join_their_word(self):
        self.assertEqual(japanese.romanize("書いた手紙"), "Kaita Tegami")
        self.assertEqual(japanese.romanize("ちょっと待って"), "Chotto Matte")

    def test_particles_as_said(self):
        self.assertEqual(japanese.romanize("君の名は"), "Kimi no Na wa")
        self.assertEqual(japanese.romanize("街で君を想う"), "Machi de Kimi o Omou")

    def test_katakana_word(self):
        self.assertEqual(japanese.romanize("東京タワー"), "Toukyou Tawaa")

    def test_simplified_chinese_isnt_japanese(self):
        self.assertTrue(japanese.uses("門"))
        self.assertFalse(japanese.uses("门"))


class RomanizeTest(unittest.TestCase):
    def test_plain_names_unchanged(self):
        self.assertEqual(romanize("06 Cancion  (Live).flac"), "06 Cancion  (Live).flac")

    def test_chinese_pinyin_without_tones(self):
        self.assertEqual(romanize("我爱北京"), "Wo Ai Beijing")
        self.assertEqual(romanize("重庆"), "Chongqing")  # By the word, not 'zhong'.

    def test_korean(self):
        self.assertEqual(romanize("한국 노래.mp3"), "Hanguk Norae.mp3")

    def test_other_scripts(self):
        self.assertEqual(romanize("Москва"), "Moskva")
        self.assertEqual(romanize("Ελληνικά"), "Ellinika")
        self.assertEqual(romanize("Straße"), "Strasse")
        self.assertTrue(romanize("שלום").isascii())
        self.assertTrue(romanize("مرحبا").isascii())
        self.assertTrue(romanize("ภาษาไทย").isascii())

    def test_spaces_next_to_latin_letters(self):
        self.assertEqual(romanize("01 水色Remix.mp3"), "01 Mizuiro Remix.mp3")
        self.assertEqual(romanize("さくら（独唱）"), "Sakura (Dokushou)")

    def test_full_and_half_width(self):
        self.assertEqual(romanize("ＡＢＣ"), "ABC")
        self.assertEqual(romanize("ｶﾀｶﾅ"), "Katakana")

    def test_which_language_kanji_are(self):
        self.assertTrue(kanji_are_japanese("水色の雨"))            # Kana in the name.
        self.assertTrue(kanji_are_japanese("雨", "C:/Music/ひかり"))  # Kana in a folder above.
        self.assertFalse(kanji_are_japanese("我爱你"))             # 爱 is Chinese only.
        self.assertFalse(kanji_are_japanese("北京", "C:/中国音乐"))
        self.assertTrue(kanji_are_japanese("水色"))                # Nothing says Chinese.
        self.assertEqual(romanize("雨", "C:/中国音乐"), "Yu")
        self.assertEqual(romanize("雨"), "Ame")


if __name__ == "__main__":
    unittest.main()

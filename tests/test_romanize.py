import unittest

from kaidrop import hangul, japanese, kana
from kaidrop.romanize import AUTO, CHINESE, JAPANESE, kanji_are_japanese, romanize


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
        self.assertEqual(kana.romanize("コーヒー"), "kohi")  # Long vowels short, as plain Hepburn.
        self.assertEqual(kana.romanize("スーパー"), "supa")
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
        self.assertEqual(japanese.romanize("東京タワー"), "Tokyo Tawa")

    def test_long_vowels_short(self):
        self.assertEqual(japanese.romanize("東京"), "Tokyo")
        self.assertEqual(japanese.romanize("大阪"), "Osaka")
        self.assertEqual(japanese.romanize("京都"), "Kyoto")
        self.assertEqual(japanese.romanize("ありがとう"), "Arigato")
        self.assertEqual(japanese.romanize("先生"), "Sensei")  # ei stays, as plain Hepburn writes it.
        self.assertEqual(japanese.romanize("思う"), "Omou")    # Said as written: not a long vowel.
        self.assertEqual(japanese.romanize("君の名は"), "Kimi no Na wa")  # Particles as said.

    def test_kana_spelling_not_the_lemma(self):
        # UniDic files さよなら under さようなら: the kana written are read, not the lemma's.
        self.assertEqual(japanese.romanize("さよなら"), "Sayonara")
        self.assertEqual(japanese.romanize("さようなら"), "Sayonara")
        self.assertEqual(japanese.romanize("こんにちは"), "Konnichiwa")  # は said wa.

    def test_simplified_chinese_isnt_japanese(self):
        self.assertTrue(japanese.uses("門"))
        self.assertFalse(japanese.uses("门"))


class RomanizeTest(unittest.TestCase):
    def test_plain_names_unchanged(self):
        self.assertEqual(romanize("06 Cancion  (Live).flac"), "06 Cancion  (Live).flac")

    def test_chinese_pinyin_without_tones(self):
        self.assertEqual(romanize("我爱北京"), "Wo Ai Beijing")
        self.assertEqual(romanize("重庆"), "Chongqing")  # By the word, not 'zhong'.

    def test_chinese_syllables_joined_by_the_word(self):
        self.assertEqual(romanize("北京欢迎你"), "Beijing Huanying Ni")
        self.assertEqual(romanize("月亮代表", kanji=CHINESE), "Yueliang Daibiao")  # Auto reads it as Japanese.
        self.assertEqual(romanize("汉字", kanji=CHINESE), "Hanzi")
        self.assertEqual(romanize("月亮代表我的心.mp3", kanji=CHINESE), "Yueliang Daibiao Wo De Xin.mp3")
        self.assertEqual(romanize("我爱你"), "Wo Ai Ni")  # Not one set phrase (Woaini).
        self.assertEqual(romanize("01 后会无期 (Live).flac", kanji=CHINESE), "01 Houhui Wuqi (Live).flac")

    def test_chinese_word_list_is_bundled(self):
        from kaidrop import chinese
        self.assertTrue(chinese.DATA.is_file())
        self.assertEqual(chinese.words("北京欢迎你"), ["北京", "欢迎", "你"])

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
        self.assertEqual(romanize("さくら（独唱）"), "Sakura (Dokusho)")

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

    def test_the_name_and_nearest_folder_say_first(self):
        # A Chinese folder inside one with a Japanese name is still Chinese...
        self.assertFalse(kanji_are_japanese("华语音乐", "C:/テスト音楽"))
        self.assertFalse(kanji_are_japanese("月亮代表我的心", "C:/テスト音楽/华语音乐"))
        self.assertEqual(romanize("01 我爱你.mp3", "C:/テスト音楽/华语音乐"), "01 Wo Ai Ni.mp3")
        # ...and a Japanese folder inside a Chinese one is Japanese.
        self.assertTrue(kanji_are_japanese("雨", r"C:\中国音乐\ひかり"))

    def test_kanji_setting(self):
        # Japanese: kanji are always Japanese, even next to a Chinese-only letter.
        self.assertEqual(romanize("北京", "C:/中国音乐", JAPANESE), "Pekin")
        self.assertTrue(kanji_are_japanese("我爱你", "", JAPANESE))
        # Chinese: kanji are Chinese, even under a folder with kana...
        self.assertEqual(romanize("水色", "C:/みずいろ", CHINESE), "Shuise")  # 水色 is one word.
        self.assertEqual(romanize("北京", "", CHINESE), "Beijing")
        # ...but a name with kana is Japanese whatever the setting.
        self.assertEqual(romanize("水色の雨", "", CHINESE), "Mizuiro no Ame")
        # Automatic is the rule above.
        self.assertEqual(romanize("北京", "", AUTO), romanize("北京"))


if __name__ == "__main__":
    unittest.main()

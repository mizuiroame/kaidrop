import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kaidrop import settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"APPDATA": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_connection_fields_start_empty(self):
        s = settings.load()
        self.assertEqual((s.host, s.port, s.user), ("", "", ""))

    def test_remembers_what_was_typed(self):
        settings.save(settings.Settings("192.168.0.51", "1337", "", "/", True, ""))
        s = settings.load()
        self.assertEqual((s.host, s.port, s.user), ("192.168.0.51", "1337", ""))

    def test_kanji_setting(self):
        self.assertEqual(settings.load().kanji, "auto")  # The default.
        settings.save(settings.Settings("10.0.0.2", "5000", "", "/", True, "", "chinese"))
        self.assertEqual(settings.load().kanji, "chinese")
        path = Path(self.tmp.name) / "KaiDrop" / "settings.json"
        path.write_text(json.dumps({"kanji": "klingon"}), encoding="utf-8")
        self.assertEqual(settings.load().kanji, "auto")  # Anything else: the default.

    def test_reads_older_files_with_a_numeric_port(self):
        path = Path(self.tmp.name) / "KaiDrop" / "settings.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"host": "10.0.0.2", "port": 5000}), encoding="utf-8")
        s = settings.load()
        self.assertEqual((s.host, s.port, s.user), ("10.0.0.2", "5000", ""))


if __name__ == "__main__":
    unittest.main()

    def test_json_that_isnt_settings_gives_the_defaults(self):
        path = Path(self.tmp.name) / "KaiDrop" / "settings.json"
        path.parent.mkdir()
        for text in ("[]", "null", '"x"', "3"):
            path.write_text(text, encoding="utf-8")
            self.assertEqual(settings.load(), settings.Settings())

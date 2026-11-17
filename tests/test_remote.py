import unittest

from kaidrop.remote import RemoteEntry, parent, parse_list_line, sort_entries


class ListParsingTest(unittest.TestCase):
    def test_unix_lines(self):
        self.assertEqual(parse_list_line("drwxr-xr-x 1 owner group 0 Jan 01 12:00 Music"),
                         RemoteEntry("Music", True, 0))
        self.assertEqual(parse_list_line("-rw-r--r-- 1 0 0 8383563 Nov 15 2026 04 Mizuiro no Ame.mp3"),
                         RemoteEntry("04 Mizuiro no Ame.mp3", False, 8383563))
        self.assertEqual(parse_list_line("lrwxrwxrwx 1 o g 7 Jan 1 10:00 link -> target"),
                         RemoteEntry("link", False, 7))
        self.assertIsNone(parse_list_line("drwxr-xr-x 1 o g 0 Jan 01 12:00 .."))

    def test_dos_lines(self):
        self.assertEqual(parse_list_line("01-31-24  10:00AM       <DIR>          Albums"),
                         RemoteEntry("Albums", True, 0))
        self.assertEqual(parse_list_line("01-31-24  10:00PM            1234 song.flac"),
                         RemoteEntry("song.flac", False, 1234))

    def test_junk(self):
        self.assertIsNone(parse_list_line("total 12"))
        self.assertIsNone(parse_list_line(""))

    def test_order_and_parent(self):
        entries = sort_entries([RemoteEntry("b.mp3", False, 1), RemoteEntry("Zed", True, 0),
                                RemoteEntry("a.mp3", False, 1)])
        self.assertEqual([e.name for e in entries], ["Zed", "a.mp3", "b.mp3"])
        self.assertEqual(parent("/Music/Album/"), "/Music")
        self.assertEqual(parent("/Music"), "/")
        self.assertEqual(parent("/"), "/")


class ReasonTest(unittest.TestCase):
    def test_connection_errors_in_words(self):
        from kaidrop.remote import _reason

        self.assertIn("isn't running", _reason(ConnectionRefusedError(10061, "No se puede establecer")))
        self.assertIn("didn't answer", _reason(TimeoutError("timed out")))
        self.assertEqual(_reason(ConnectionResetError(10054, "x")), "the connection was cut")
        self.assertEqual(_reason(EOFError()), "the server closed the connection")
        self.assertEqual(_reason(OSError("550 No such file")), "550 No such file")


if __name__ == "__main__":
    unittest.main()

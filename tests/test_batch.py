import unittest
from pathlib import Path

from kaidrop.batch import Batch, leftover
from kaidrop.ftp import Status
from kaidrop.plan import Plan, UploadItem


def item(name: str) -> UploadItem:
    return UploadItem(Path(name), f"/Music/{name}", 10, False)


class LeftoverTest(unittest.TestCase):
    def setUp(self):
        self.batch = Batch("up", Plan((item("a"), item("b"), item("c"), item("d")), ("/Music",)),
                           ("4", "5", "6", "7"), "/Music")

    def test_keeps_what_did_not_end_well(self):
        ended = {"4": Status.SENT, "5": Status.FAILED}  # 5 failed when the connection went; 6 and 7 never started.
        rest = leftover(self.batch, ended)
        self.assertEqual([i.remote for i in rest.plan.items], ["/Music/b", "/Music/c", "/Music/d"])
        self.assertEqual(rest.rows, ("5", "6", "7"))
        self.assertEqual((rest.kind, rest.folder, rest.plan.folders), ("up", "/Music", ("/Music",)))

    def test_skipped_copied_and_cancelled_files_are_done(self):
        ended = {"4": Status.SKIPPED, "5": Status.COPY, "6": Status.CANCELLED}
        self.assertEqual(leftover(self.batch, ended).rows, ("7",))

    def test_nothing_left(self):
        ended = {row: Status.SENT for row in self.batch.rows}
        self.assertIsNone(leftover(self.batch, ended))


if __name__ == "__main__":
    unittest.main()

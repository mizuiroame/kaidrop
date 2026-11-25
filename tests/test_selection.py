"""Selecting several rows in a file pane, as in Explorer (needs a display; skipped without one)."""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace

from kaidrop.panes import CONTROL, FilePane

# In CI (GitHub sets CI=true) there is no desktop to click and focus in:
# these tests are skipped there and run on a PC.
_SKIP_REASON = "no display"
if os.environ.get("CI"):
    _root = None
    _SKIP_REASON = "GUI test: needs a desktop session, skipped in CI"
else:
    try:
        _root = tk.Tk()
        _root.withdraw()
    except tk.TclError:
        _root = None


@unittest.skipIf(_root is None, _SKIP_REASON)
class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.pane = FilePane(_root, "Test")
        self.pane.show([(f"song {i}.flac", False, 1000) for i in range(6)])
        self.tree = self.pane.tree
        self.addCleanup(self.pane.destroy)

    def pick(self, iid):
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        _root.update()  # <<TreeviewSelect>> sets the anchor.

    def test_shift_arrows_extend_from_the_anchor(self):
        self.pick("1")
        self.pane.extend_selection(1)
        self.pane.extend_selection(1)
        self.assertEqual(self.tree.selection(), ("1", "2", "3"))
        self.pane.extend_selection(-3)  # Past the anchor: the other way.
        self.assertEqual(self.tree.selection(), ("0", "1"))
        self.pane.extend_selection(99)  # Shift+End.
        self.assertEqual(self.tree.selection(), ("1", "2", "3", "4", "5"))

    def test_select_all(self):
        self.pane.select_all()
        self.assertEqual(len(self.pane.selected()), 6)

    def press(self, row, x=10, y=10, state=0):
        self.tree.identify_row = lambda _y: row
        event = SimpleNamespace(x=x, y=y, state=state)
        self.pane._press(event)
        self.tree.selection_set(row)  # What Tk's own binding does to a plain press.
        _root.update()
        return event

    def test_press_on_a_selection_keeps_it_for_a_drag(self):
        self.tree.selection_set(("1", "2", "3"))
        self.press("2")
        self.assertEqual(self.tree.selection(), ("1", "2", "3"))
        self.pane._release(SimpleNamespace(x=60, y=90, state=0))  # Dragged away: still all three.
        self.assertEqual(self.tree.selection(), ("1", "2", "3"))

    def test_click_without_drag_leaves_one(self):
        self.tree.selection_set(("1", "2", "3"))
        self.press("2")
        self.pane._release(SimpleNamespace(x=11, y=10, state=0))
        self.assertEqual(self.tree.selection(), ("2",))

    def test_ctrl_press_is_left_to_tk(self):
        self.tree.selection_set(("1", "2"))
        self.tree.identify_row = lambda _y: "2"
        self.pane._press(SimpleNamespace(x=10, y=10, state=CONTROL))
        self.assertIsNone(self.pane._held)

    def drag(self, start_row, rows_by_y, end_y, state=0):
        """Presses on start_row and drags to end_y; rows_by_y says which row is at a y."""
        self.press(start_row, y=10, state=state)
        self.tree.identify_row = lambda y: rows_by_y.get(y, "")
        return self.pane._band_motion(SimpleNamespace(x=10, y=end_y, state=state))

    def test_dragging_from_an_unselected_row_selects_the_rows_it_crosses(self):
        self.tree.selection_set("0")
        result = self.drag("1", {60: "4"}, 60)
        self.assertEqual(result, "break")  # Not a drag of files.
        self.assertEqual(self.tree.selection(), ("1", "2", "3", "4"))
        self.pane._band_motion(SimpleNamespace(x=10, y=30, state=0))  # Back up a little.
        self.tree.identify_row = lambda y: {30: "2"}.get(y, "")
        self.pane._band_motion(SimpleNamespace(x=10, y=30, state=0))
        self.assertEqual(self.tree.selection(), ("1", "2"))

    def test_ctrl_drag_adds_to_the_selection(self):
        self.tree.selection_set("5")
        self.tree.identify_row = lambda _y: "1"
        self.pane._press(SimpleNamespace(x=10, y=10, state=CONTROL))
        self.tree.identify_row = lambda y: {50: "2"}.get(y, "")
        self.pane._band_motion(SimpleNamespace(x=10, y=50, state=CONTROL))
        self.assertEqual(set(self.tree.selection()), {"5", "1", "2"})

    def test_a_small_wobble_is_still_a_click(self):
        self.tree.selection_set("0")
        self.drag("1", {12: "1"}, 12)
        self.assertEqual(self.tree.selection(), ("1",))

    def test_dragging_up_or_down_from_a_selected_row_selects_too(self):
        self.tree.selection_set(("1", "2"))
        self.drag("2", {80: "4"}, 80)
        self.assertEqual(self.tree.selection(), ("2", "3", "4"))

    def test_a_selection_of_several_stays_until_another_row_is_reached(self):
        self.tree.selection_set(("1", "3", "5"))
        self.drag("3", {20: "3"}, 20)  # Still on its own row: the three stay, to be dragged out.
        self.assertEqual(self.tree.selection(), ("1", "3", "5"))

    def test_leaving_the_list_sideways_hands_over_to_dragging_files(self):
        self.tree.selection_set(("1", "3", "5"))
        self.press("3")
        self.tree.identify_row = lambda _y: "3"
        self.assertIsNone(self.pane._band_motion(SimpleNamespace(x=-30, y=10, state=0)))
        self.assertIsNone(self.pane._band_motion(SimpleNamespace(x=-60, y=80, state=0)))
        self.assertEqual(self.tree.selection(), ("1", "3", "5"))  # All three go.


@unittest.skipIf(_root is None, _SKIP_REASON)
class HandOverTest(unittest.TestCase):
    """Up and down in a list selects; out of it sideways, the selection is
    dragged to the other pane and dropped there."""

    def setUp(self):
        from kaidrop.dragdrop import Drag, Target

        self.source, self.target = FilePane(_root, "Here"), FilePane(_root, "There")
        self.source.show([(f"file {i}", False, 1) for i in range(5)])
        self.target.show([("Folder", True, 0)])
        self.addCleanup(self.source.destroy)
        self.addCleanup(self.target.destroy)
        self.dropped = []
        self.drag = Drag(_root, self.source, [Target(self.target, "Send", lambda row: row or "/",
                                                     lambda row: self.dropped.append((self.source.selected(), row)))])
        self.drag._make_ghost = lambda: None  # No window needed for this.
        self.under = self.source.tree
        _root.winfo_containing = lambda x, y: self.under

    def tearDown(self):
        del _root.winfo_containing

    def event(self, x, y):
        return SimpleNamespace(x=x, y=y, x_root=x, y_root=y, state=0)

    def test_select_down_then_out_drops_the_selection(self):
        tree = self.source.tree
        tree.identify_row = lambda y: {10: "1", 40: "3"}.get(y, "")
        press = self.event(10, 10)
        self.source._press(press)
        self.drag._press(press)
        tree.selection_set("1")
        for e in (self.event(10, 40),):  # Down to file 3: selects 1-3; the drag waits.
            if self.source._band_motion(e) != "break":
                self.drag._motion(e)
        self.assertFalse(self.drag.dragging)
        self.assertEqual(tree.selection(), ("1", "2", "3"))
        out = self.event(-40, 40)  # Out sideways, over the other pane.
        self.under = self.target.tree
        self.target.tree.identify_row = lambda y: ""
        self.assertIsNone(self.source._band_motion(out))
        self.drag._motion(out)
        self.assertTrue(self.drag.dragging)
        self.drag._release(out)
        self.assertEqual(self.dropped, [([("file 1", False), ("file 2", False), ("file 3", False)], None)])


if __name__ == "__main__":
    unittest.main()

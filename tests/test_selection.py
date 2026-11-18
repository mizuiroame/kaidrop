"""Selecting several rows in a file pane, as in Explorer (needs a display; skipped without one)."""
import tkinter as tk
import unittest
from types import SimpleNamespace

from kaidrop.panes import CONTROL, FilePane

try:
    _root = tk.Tk()
    _root.withdraw()
except tk.TclError:
    _root = None


@unittest.skipIf(_root is None, "no display")
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

    def test_dragging_a_selected_row_moves_files_instead(self):
        self.tree.selection_set(("1", "2"))
        self.press("2")
        self.assertIsNone(self.pane._band_motion(SimpleNamespace(x=10, y=80, state=0)))


if __name__ == "__main__":
    unittest.main()

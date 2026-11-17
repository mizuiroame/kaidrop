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


if __name__ == "__main__":
    unittest.main()

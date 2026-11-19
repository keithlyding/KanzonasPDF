"""Count markers' groups, numbers and layers (counts.py; issue #107).

The Count tool's Properties: a Group to pick or type (New count starts the next group, whose
first marker is 1), Keep the numbers in order (on: deleting a marker, or moving it to another
group, numbers the rest 1, 2, 3... again across pages; off: the gap stays), and a Layer.
A selected marker's Properties: its group (it takes the next number there), its number (the
others make room), its layer. Right-click > Renumber group closes any gaps. Each is one undo
step.

cloydcc-dev, issue #107, 19 Nov 2026: "Is there a way to reset the count and set the layers
and labels like a properties box ... if I remove one count it will just continue from the
last (checkbox would be nice to turn on or off this behavior ...)". The owner, 19 Nov: the
renumbering an option, on by default; numbers changed in Properties, not the Markups list.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_count_groups
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations, counts, main_window, markup_layers  # noqa: E402

P = pymupdf.Point


def two_pages():
    d = pymupdf.open()
    d.new_page()
    d.new_page()
    path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
    d.save(path)
    return path


class Counting(unittest.TestCase):
    def setUp(self):
        saved = annotations.saved_tool_props("m_count")
        self.addCleanup(annotations.set_tool_props, "m_count", saved)
        annotations.reset_tool_props("m_count")
        w = self.w = main_window.MainWindow()
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w.show()
        w.open_file(two_pages())
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        w.set_tool("m_count")
        APP.processEvents()

    def place(self, *where):
        for page, x in where:
            self.v.place_count(page, P(x, 100))
        APP.processEvents()

    def numbers(self, group=counts.DEFAULT_GROUP):
        """{(page, x): n} of the group's markers."""
        return {(i, round(m["points"][0].x)): m["n"]
                for i, _x, m in counts.markers(self.v.doc, {group})}

    def select(self, page, x):
        for i, xref, m in counts.markers(self.v.doc):
            if i == page and round(m["points"][0].x) == x:
                self.v.select_xref(i, xref)
                APP.processEvents()
                return m
        raise AssertionError("no marker at %s" % ((page, x),))

    def change(self, **props):
        self.v.update_selected_props(dict(self.v.selected_model["props"], **props))
        APP.processEvents()


class KeepTheNumbersInOrder(Counting):
    def test_deleting_one_numbers_the_rest_again_across_pages(self):
        self.place((0, 100), (0, 150), (1, 100), (1, 150))
        self.select(0, 150)
        self.v.delete_selected()
        self.assertEqual(self.numbers(), {(0, 100): 1, (1, 100): 2, (1, 150): 3})
        self.v.undo()
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 150): 2, (1, 100): 3, (1, 150): 4})

    def test_the_next_marker_follows_on(self):
        self.place((0, 100), (0, 150), (0, 200))
        self.select(0, 150)
        self.v.delete_selected()
        self.place((0, 250))
        self.assertEqual(self.numbers()[(0, 250)], 3)

    def test_off_the_gap_stays_and_renumber_group_closes_it(self):
        self.place((0, 100), (0, 150), (0, 200))
        self.select(0, 100)
        self.change(order=False)
        self.assertFalse(any(m["props"]["order"] for _i, _x, m in counts.markers(self.v.doc)))
        self.select(0, 150)
        self.v.delete_selected()
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 200): 3})
        self.select(0, 200)
        self.v.renumber_selected_counts()
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 200): 2})

    def test_a_color_changed_renumbers_nothing(self):
        # (an older document: the order kept, and a gap from before 1.15.9)
        self.place((0, 100), (0, 150), (0, 200))
        m = self.select(0, 200)
        gap = annotations.copy(m)
        gap["n"] = 5
        self.v.commit_models(0, [(self.v.selection[1], gap)])
        self.select(0, 200)
        self.change(stroke="#ff0000")
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 150): 2, (0, 200): 5})
        self.assertTrue(all(m["props"]["order"] for _i, _x, m in counts.markers(self.v.doc)))

    def test_on_by_default(self):
        self.assertTrue(annotations.tool_props("m_count")["order"])

    def test_the_eraser_closes_the_gap_too(self):
        self.place((0, 100), (0, 150), (0, 200))
        self.v.apply_point_tool(0, "eraser", P(150, 100))
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 200): 2})

    def test_other_groups_are_left_alone(self):
        self.place((0, 100), (0, 150))
        self.w._new_count_group()
        self.place((1, 100), (1, 150))
        self.select(0, 100)
        self.v.delete_selected()
        self.assertEqual(self.numbers("Count 2"), {(1, 100): 1, (1, 150): 2})


class GroupAndNumber(Counting):
    def test_new_count_starts_the_next_group_at_1(self):
        self.place((0, 100), (0, 150))
        self.w._new_count_group()
        self.assertEqual(annotations.tool_props("m_count")["group"], "Count 2")
        self.place((1, 100))
        self.assertEqual(self.numbers("Count 2"), {(1, 100): 1})
        self.w._new_count_group()
        self.assertEqual(annotations.tool_props("m_count")["group"], "Count 3")

    def test_a_group_typed_in_properties(self):
        self.w.props.group.setCurrentText("Smoke detectors")
        self.w.props._emit()
        self.place((0, 100), (0, 150))
        self.assertEqual(self.numbers("Smoke detectors"), {(0, 100): 1, (0, 150): 2})

    def test_a_placed_marker_isnt_selected_and_the_next_number_follows(self):
        self.place((0, 100), (0, 150))
        self.assertIsNone(self.v.selection)
        self.assertIn("Count 1 #3", self.w.props.hint.text())
        self.assertTrue(self.w.props.new_group.isVisible())

    def test_properties_shows_the_next_number(self):
        self.place((0, 100), (0, 150))
        self.v.clear_selection()
        self.w._refresh_props()
        self.assertIn("#3", self.w.props.hint.text())

    def test_a_selected_markers_number_and_the_others_make_room(self):
        self.place((0, 100), (0, 150), (0, 200), (0, 250))
        self.select(0, 250)
        self.assertEqual(self.w.props.number.value(), 4)
        self.assertTrue(self.w.props.rows["n"][1].isVisible())
        self.change(n=2)
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 250): 2, (0, 150): 3, (0, 200): 4})
        self.v.undo()
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 150): 2, (0, 200): 3, (0, 250): 4})

    def test_a_number_fixed_by_hand_with_the_order_off(self):
        self.place((0, 100), (0, 150), (0, 200))
        self.select(0, 100)
        self.change(order=False)
        self.select(0, 150)
        self.v.delete_selected()
        self.select(0, 200)
        self.change(n=2)
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 200): 2})

    def test_moved_to_another_group_it_takes_its_next_number(self):
        self.place((0, 100), (0, 150), (0, 200))
        self.w._new_count_group()
        self.place((1, 100))
        self.select(0, 150)
        self.change(group="Count 2")
        self.assertEqual(self.numbers("Count 2"), {(1, 100): 1, (0, 150): 2})
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 200): 2})     # (no gap left)

    def test_the_groups_of_the_document_are_offered(self):
        self.place((0, 100))
        self.w._new_count_group()
        self.place((0, 150))
        self.select(0, 100)
        items = [self.w.props.group.itemText(k) for k in range(self.w.props.group.count())]
        self.assertEqual(items, ["Count 1", "Count 2"])
        self.assertFalse(self.w.props.new_group.isVisible())       # (for the tool only)

    def test_copies_still_take_the_next_number(self):
        self.place((0, 100), (0, 150))
        self.select(0, 150)
        self.v.duplicate_selected()
        self.assertEqual(sorted(self.numbers().values()), [1, 2, 3])


class Colors(Counting):
    """New count takes a color no group of the document has yet; picking a group again gives
    the next markers its markers' color, text size and opacity (the owner, 19 Nov)."""

    def tool(self, key):
        return annotations.tool_props("m_count")[key]

    def pick(self, group):
        self.w.props.group.setCurrentText(group)
        self.w.props._emit()
        APP.processEvents()

    def test_each_new_count_gets_its_own_color(self):
        self.place((0, 100))
        first = self.tool("stroke")
        self.w._new_count_group()
        second = self.tool("stroke")
        self.place((0, 150))
        self.w._new_count_group()
        third = self.tool("stroke")
        self.assertEqual(len({first.lower(), second.lower(), third.lower()}), 3)
        self.assertIn(second, counts.COLORS)

    def test_a_group_picked_again_looks_like_its_markers(self):
        self.w.props.fontsize.setValue(14)
        self.place((0, 100))
        blue = self.tool("stroke")
        self.w._new_count_group()
        self.w.props.fontsize.setValue(9)
        self.place((0, 150))
        self.pick(counts.DEFAULT_GROUP)
        self.assertEqual(self.tool("stroke"), blue)
        self.assertEqual(self.tool("fontsize"), 14)
        self.place((0, 200))
        m = self.select(0, 200)
        self.assertEqual((m["n"], m["props"]["stroke"]), (2, blue))

    def test_a_new_name_keeps_the_color_chosen(self):
        self.w.props.stroke.set_color("#123456")
        self.w.props._emit()
        self.pick("Speakers")
        self.assertEqual(self.tool("stroke"), "#123456")

    def test_when_all_the_colors_are_used_it_goes_round(self):
        found = [(0, k, {"props": {"stroke": c, "group": "G%d" % k}, "n": 1})
                 for k, c in enumerate(counts.COLORS)]
        self.assertEqual(counts.next_color(found, counts.COLORS[2]), counts.COLORS[3])


class GapsAreShown(Counting):
    """Properties says when a group's numbers have gaps or repeats, with Renumber beside it;
    nothing when they're clean."""

    def shown(self):
        self.w._refresh_props()
        lab, row = self.w.props.rows["gaps"]
        return self.w.props.gaps.text() if row.isVisible() else ""

    def gap(self):
        """1, 3: the second deleted with the order off."""
        self.place((0, 100), (0, 150), (0, 200))
        self.select(0, 100)
        self.change(order=False)
        self.select(0, 150)
        self.v.delete_selected()
        self.v.clear_selection()

    def test_nothing_when_the_numbers_are_clean(self):
        self.place((0, 100), (0, 150))
        self.assertEqual(self.shown(), "")

    def test_a_gap_is_named_for_the_tool(self):
        self.gap()
        self.assertIn("missing: 2", self.shown())

    def test_and_for_a_selected_marker(self):
        self.gap()
        self.select(0, 200)
        self.assertIn("missing: 2", self.shown())

    def test_a_number_used_twice(self):
        self.place((0, 100), (0, 150), (0, 200))
        self.select(0, 100)
        self.change(order=False)
        self.select(0, 200)
        self.change(n=2)
        self.v.clear_selection()
        text = self.shown()
        self.assertIn("used more than once: 2", text)
        self.assertNotIn("missing", text)          # (1, 2, 2: nothing above 2 to miss)

    def test_renumber_fixes_it_and_the_line_goes(self):
        self.gap()
        self.shown()
        self.w.props.renumber.click()
        APP.processEvents()
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 200): 2})
        self.assertEqual(self.shown(), "")
        self.v.undo()
        self.assertEqual(self.numbers(), {(0, 100): 1, (0, 200): 3})

    def test_a_long_list_is_cut_short(self):
        self.assertEqual(counts.problem_text("Count 1", list(range(1, 20)), []),
                         "Count 1 numbers missing: 1, 2, 3, 4, 5, 6, 7, 8, ...")


class WithAToolChestEntry(Counting):
    """A Tool Chest entry of the Count tool keeps its group and color, in every document (it's
    the tool's whole style); New count and the group picked work on it too."""

    def use(self, **props):
        self.w.chest.use.emit("m_count", dict(annotations.DEFAULTS["m_count"], **props))
        APP.processEvents()
        self.addCleanup(lambda: annotations.OVERRIDE.update({"tool": None, "props": None}))

    def test_its_group_and_color(self):
        self.use(group="Smoke detectors", stroke="#ff0000")
        self.place((0, 100), (0, 150))
        self.assertEqual(self.numbers("Smoke detectors"), {(0, 100): 1, (0, 150): 2})
        self.assertTrue(all(m["props"]["stroke"] == "#ff0000"
                            for _i, _x, m in counts.markers(self.v.doc)))

    def test_new_count_with_it(self):
        self.use(group="Smoke detectors")
        self.place((0, 100))
        self.w._new_count_group()
        self.assertEqual(annotations.tool_props("m_count")["group"], "Count 1")
        self.place((0, 150))
        self.assertEqual(self.numbers(), {(0, 150): 1})

    def test_picking_a_group_with_it_picks_its_layer(self):
        x = self.v.new_markup_layer("Fire alarm")
        self.use(group="Smoke detectors")
        self.w._count_layer_picked(x)
        self.place((0, 100))
        self.w._new_count_group()
        self.w.props.group.setCurrentText("Smoke detectors")
        self.w.props._emit()
        self.assertEqual(self.v.count_layer, x)


class Layers(Counting):
    def test_new_markers_go_on_the_layer_picked(self):
        x = self.v.new_markup_layer("Fire alarm")
        self.w._count_layer_picked(x)
        self.place((0, 100))
        (_i, xref, _m), = counts.markers(self.v.doc)
        self.assertEqual(markup_layers.layer_of(self.v.doc, xref), x)

    def test_as_the_layers_tab_says_by_default(self):
        x = self.v.new_markup_layer("Markups")
        self.v.set_markup_layer(x)
        self.place((0, 100))
        (_i, xref, _m), = counts.markers(self.v.doc)
        self.assertEqual(markup_layers.layer_of(self.v.doc, xref), x)

    def test_a_new_layer_from_properties(self):
        with mock.patch.object(QInputDialog, "getText", return_value=("Speakers", True)):
            self.w._count_layer_picked("new")
        self.place((0, 100))
        (_i, xref, _m), = counts.markers(self.v.doc)
        names = {x: n for x, n, _on in markup_layers.layers(self.v.doc)}
        self.assertEqual(names[markup_layers.layer_of(self.v.doc, xref)], "Speakers")

    def test_a_selected_marker_moves_to_the_layer(self):
        x = self.v.new_markup_layer("Fire alarm")
        self.place((0, 100))
        self.select(0, 100)
        self.w._count_layer_picked(x)
        (_i, xref, _m), = counts.markers(self.v.doc)
        self.assertEqual(markup_layers.layer_of(self.v.doc, xref), x)

    def test_picking_a_group_again_picks_its_layer(self):
        x = self.v.new_markup_layer("Fire alarm")
        self.w._count_layer_picked(x)
        self.place((0, 100))
        self.w._new_count_group()
        self.assertIsNone(self.v.count_layer)
        self.w.props.group.setCurrentText(counts.DEFAULT_GROUP)
        self.w.props._emit()
        self.assertEqual(self.v.count_layer, x)


if __name__ == "__main__":
    unittest.main()

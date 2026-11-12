"""Spaces (1.12, the owner, 11 Nov, from the Bluebeam comparison: Revu's Spaces): a named
area drawn with the Space tool (a see-through polygon, its name its text), the markups whose
middle is inside it in it (the smallest one when spaces overlap), shown in the Markups list's
Space column and filter, renamed in one undo step, kept through restyling and saving.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_spaces
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A  # noqa: E402
from kanzonas import spaces  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.markups_panel import ALL_SPACES, COLUMNS, MarkupsPanel, collect  # noqa: E402

R = pymupdf.Rect
P = pymupdf.Point


def view(rotation=0):
    d = pymupdf.open()
    pg = d.new_page(width=612, height=792)
    if rotation:
        pg.set_rotation(rotation)
    path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
    d.save(path)
    return DocumentView(path)


class Spaces(unittest.TestCase):
    def setUp(self):
        self.v = view()
        self.addCleanup(self.v.close_doc)
        self.names = []
        self.v.ask_space_name = lambda default, title=None: \
            self.names.pop(0) if self.names else default

    def space(self, pts, name=None):
        if name:
            self.names.append(name)
        before = {a.xref for a in self.v.doc[0].annots()}
        self.v.apply_poly(0, "space", [P(*p) for p in pts])
        made = [a.xref for a in self.v.doc[0].annots() if a.xref not in before]
        self.assertEqual(len(made), 1)
        return made[0]

    def box(self, rect):
        return self.v._create(0, {"kind": "rect", "rect": R(rect), "text": "",
                                  "props": dict(A.DEFAULTS["rect"])})

    def rows(self):
        return {r[1]: r for r in collect(self.v.doc)}

    def test_a_space_and_the_markups_in_it(self):
        room = self.space([(50, 50), (300, 50), (300, 300), (50, 300)], "Room 101")
        self.assertTrue(spaces.is_space(self.v.doc, room))
        inside = self.box((100, 100, 140, 140))
        outside = self.box((400, 400, 440, 440))
        rows = self.rows()
        self.assertEqual(COLUMNS[-1], "Space")
        self.assertEqual(rows[inside][12], "Room 101")
        self.assertEqual(rows[outside][12], "")
        self.assertEqual(rows[room][12], "")                    # (a space is in none)
        self.assertEqual(rows[room][2], "Space")
        self.assertEqual(rows[room][3], "Room 101")
        # its look: see-through, filled; a polygon to every other program
        page = self.v.doc[0]
        a = page.load_annot(room)
        self.assertEqual(a.type[0], pymupdf.PDF_ANNOT_POLYGON)
        self.assertLess(a.opacity, 1)
        self.assertIsNotNone(a.colors.get("fill"))

    def test_picked_by_its_outline_only(self):
        # (a press inside a room draws or selects what's in it, as with an unfilled shape)
        room = self.space([(50, 50), (300, 50), (300, 300), (50, 300)], "Room")
        self.assertIsNone(self.v.annot_at(0, P(170, 170)))
        self.assertEqual(self.v.annot_at(0, P(51, 170)), room)
        x = self.box((100, 100, 140, 140))
        self.assertEqual(self.v.annot_at(0, P(120, 101)), x)
        # a filled polygon that isn't a space: picked anywhere inside, as before
        props = dict(A.DEFAULTS["polygon"], fill="#00ff00")
        poly = self.v._create(0, {"kind": "polygon", "props": props, "rect": R(), "text": "",
                                  "points": [P(350, 350), P(500, 350), P(500, 500)]})
        self.assertEqual(self.v.annot_at(0, P(470, 400)), poly)

    def test_moved_in_and_out(self):
        self.space([(50, 50), (300, 50), (300, 300), (50, 300)], "Kitchen")
        x = self.box((400, 400, 440, 440))
        self.assertEqual(self.rows()[x][12], "")
        self.v.select_xref(0, x)
        self.v.nudge(-1, 0, 300)
        self.v.nudge(0, -1, 300)
        x = self.v.selection[1]
        self.assertEqual(self.rows()[x][12], "Kitchen")

    def test_the_smallest_of_overlapping_spaces_and_an_l_shape(self):
        self.space([(0, 0), (600, 0), (600, 700), (0, 700)], "Level 2")
        self.space([(100, 100), (200, 100), (200, 200), (100, 200)], "Closet")
        # an L: its middle (the corners' average) isn't inside it
        ell = self.space([(300, 300), (500, 300), (500, 340), (340, 340), (340, 500),
                          (300, 500)], "Hall")
        a = self.box((140, 140, 160, 160))
        b = self.box((400, 600, 420, 620))
        c = self.box((305, 450, 325, 470))
        rows = self.rows()
        self.assertEqual(rows[a][12], "Closet")
        self.assertEqual(rows[b][12], "Level 2")
        self.assertEqual(rows[c][12], "Hall")
        # each name written inside its space
        page = self.v.doc[0]
        labels = dict(self.v.space_labels(0))
        self.assertEqual(set(labels), {"Level 2", "Closet", "Hall"})
        hall = [p for x, _n, p in spaces.on_page(self.v.doc, page) if x == ell][0]
        at = labels["Hall"] * ~page.transformation_matrix     # (back to PDF space)
        self.assertTrue(spaces.inside(hall, at.x, at.y))

    def test_names_numbered_rename_one_undo_step_and_cancel(self):
        first = self.space([(50, 50), (100, 50), (100, 100)])
        second = self.space([(150, 50), (200, 50), (200, 100)])
        self.assertEqual(spaces._name(self.v.doc, first), "Space 1")
        self.assertEqual(spaces._name(self.v.doc, second), "Space 2")
        self.v.select_xref(0, first)
        self.assertEqual(self.v.selected_space(), first)
        self.assertTrue(self.v.rename_space(name="Lobby"))
        self.assertEqual(spaces._name(self.v.doc, first), "Lobby")
        self.assertEqual(dict(self.v.space_labels(0)).keys(), {"Lobby", "Space 2"})
        self.v.undo()
        self.assertEqual(spaces._name(self.v.doc, first), "Space 1")
        # cancelled when asked for its name: no space
        self.v.ask_space_name = lambda default, title=None: None
        n = len(list(self.v.doc[0].annots()))
        self.v.apply_poly(0, "space", [P(300, 300), P(350, 300), P(350, 350)])
        self.assertEqual(len(list(self.v.doc[0].annots())), n)

    def test_kept_through_restyle_copy_and_save(self):
        room = self.space([(50, 50), (300, 50), (300, 300), (50, 300)], "Office")
        self.v.select_xref(0, room)
        self.v.update_selected_props({"width": 3.0})
        room = self.v.selection[1]
        self.assertTrue(spaces.is_space(self.v.doc, room))
        self.assertEqual(spaces._name(self.v.doc, room), "Office")
        from kanzonas import tool_chest
        self.assertEqual(tool_chest.tool_for(self.v.selected_model), "space")
        out = os.path.join(tempfile.mkdtemp(), "out.pdf")
        self.v.doc.save(out)
        d = pymupdf.open(out)
        self.assertEqual([n for _x, n, _p in spaces.on_page(d, d[0])], ["Office"])
        # a plain polygon isn't a space
        self.v.apply_poly(0, "polygon", [P(400, 400), P(450, 400), P(450, 450)])
        self.assertEqual(len(spaces.on_page(self.v.doc, self.v.doc[0])), 1)

    def test_rotated_page(self):
        self.v = view(90)
        self.addCleanup(self.v.close_doc)
        self.v.ask_space_name = lambda default, title=None: "Room"
        self.space([(50, 50), (300, 50), (300, 300), (50, 300)])
        x = self.box((100, 100, 140, 140))
        self.assertEqual(self.rows()[x][12], "Room")

    def test_markups_list_space_filter(self):
        self.space([(50, 50), (300, 50), (300, 300), (50, 300)], "Room A")
        self.space([(320, 50), (600, 50), (600, 300), (320, 300)], "Room B")
        a = self.box((100, 100, 140, 140))
        b = self.box((400, 100, 440, 140))
        panel = MarkupsPanel()
        self.addCleanup(panel.deleteLater)
        panel.refresh(self.v.doc)
        APP.processEvents()
        self.assertTrue(panel.space_filter.isVisibleTo(panel))
        self.assertEqual([panel.space_filter.itemText(i)
                          for i in range(panel.space_filter.count())],
                         [ALL_SPACES, "Room A", "Room B"])
        panel.space_filter.setCurrentText("Room B")
        shown = [panel.table.item(r, 0).data(0x0100)[1] for r in range(panel.table.rowCount())
                 if not panel.table.isRowHidden(r)]
        self.assertEqual(shown, [b])
        self.assertEqual(panel.count.text(), "1 of 4")
        self.assertNotIn(a, shown)

    def test_no_spaces_no_filter(self):
        self.box((100, 100, 140, 140))
        panel = MarkupsPanel()
        self.addCleanup(panel.deleteLater)
        panel.refresh(self.v.doc)
        self.assertFalse(panel.space_filter.isVisibleTo(panel))


if __name__ == "__main__":
    unittest.main()

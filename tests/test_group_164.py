"""1.16.4: Arrange > Group on big CAD sheets (the owner, 23 Nov 2026: grouping the drawing's
own objects "must work across layers, show as one group, and be fast").

- Objects on different layers make one group: inside it each keeps its own layer (its
  /OC /name BDC ... EMC, the layer copied into the group's resources) and the group is placed
  outside the layers they don't share, so turning a layer off still hides just its own
  objects. Clips that cut out the same area count as one (CAD programs set the sheet's frame
  as the clip again for each layer); a different clip, or different parts of a tagged page,
  still can't be one group, and Group says why.
- A selected group shows one box, its own outline, and Properties calls it
  "Group (n objects)".
- Grouping works from the page's objects as read (no second read of the drawing), a group
  moved again is written over where it is (the rest of the drawing stays as read: its
  objects are the same ones), and CAD mode's idle preparation waits while a mouse button is
  held (a slice of it between two mouse moves made each move of a drag wait).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_group_164
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QTimer, Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import page_objects as P  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from tests.test_interaction_112 import Window, pump  # noqa: E402

FRAME = b"q 20 20 m 772 20 l 772 592 l 20 592 l 20 20 l W n\n"


def sheet(extra=b""):
    """A sheet like the owner's (forklift.pdf): turned 270 degrees, each layer drawn under
    the sheet's frame set as the clip again, a ladder on its own layer with each line in its
    own  q <color, width> ... Q , and lines of two other layers next to it. Returns (path,
    the layers' xrefs by name)."""
    d = pymupdf.open()
    pg = d.new_page(width=792, height=612)
    ocs = {name: d.add_ocg(name, on=True) for name in ("ladder", "0", "Building")}
    ladder = b"".join(b"0 w\nq\n1 0 0 RG 2 w\n%d 110 m %d 150 l S\nQ\n" % (100 + 6 * i, 100 + 6 * i)
                      for i in range(8))
    content = b"\n".join([
        FRAME + b"/OC /Lb BDC 0 0 1 RG 1.5 w 96 104 m 150 104 l S 96 156 m 150 156 l S EMC Q",
        FRAME + b"/OC /L0 BDC 0 0.6 0 RG 96 100 m 150 100 l S 300 300 m 340 300 l S EMC Q",
        FRAME + b"/OC /L0 BDC 0 0.6 0 RG 96 160 m 150 160 l S EMC Q",
        FRAME + b"/OC /Ll BDC\n" + ladder + b"300 320 m 340 320 l S EMC Q",
        extra])
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, content)
    pg.set_contents(x)
    d.xref_set_key(pg.xref, "Resources", "<</Properties<</Ll %d 0 R/L0 %d 0 R/Lb %d 0 R>>>>" % (
        ocs["ladder"], ocs["0"], ocs["Building"]))
    pg.set_rotation(270)
    path = os.path.join(tempfile.mkdtemp(), "sheet.pdf")
    d.save(path)
    return path, ocs


def looks(v, ocs):
    """The page drawn with every layer on, then with each one off in turn."""
    d = pymupdf.open("pdf", v._snapshot())
    out = []
    for off in (None,) + tuple(ocs.values()):
        d.set_layer(-1, on=[x for x in ocs.values() if x != off], off=[off] if off else [])
        out.append(d[0].get_pixmap(dpi=100).samples)
    return out


def same_objects(test, a, b):
    """Objects a (worked out after an edit) are what a fresh read b gives."""
    test.assertEqual(len(a.found), len(b.found))
    for x, y in zip(a.found, b.found):
        test.assertEqual(set(x), set(y))
        for k in x:
            if k == "ctm":
                test.assertTrue(all(abs(p - q) < 1e-6 for p, q in zip(x[k], y[k])))
            else:
                test.assertEqual(x[k], y[k], k)
    test.assertEqual([(it["n"], it["kind"], tuple(it["rect"])) for it in a.items],
                     [(it["n"], it["kind"], tuple(it["rect"])) for it in b.items])


class View(unittest.TestCase):
    def setUp(self):
        for name in ("information", "warning", "critical"):
            p = mock.patch.object(QMessageBox, name, return_value=None)
            p.start()
            self.addCleanup(p.stop)

    def view(self, extra=b""):
        path, self.ocs = sheet(extra)
        v = DocumentView(path)
        self.addCleanup(v.close_doc)
        self.objs = v.content_objects(0)
        return v

    def ladder_and_strays(self):
        """The ladder's lines and the four lines of the other layers beside it (not the ones
        far off)."""
        return [it for it in self.objs.items if it["obj"]["box"][0] < 200]


class AcrossLayers(View):
    def test_objects_on_different_layers_make_one_group(self):
        v = self.view()
        items = self.ladder_and_strays()
        self.assertEqual(len(items), 12)
        self.assertEqual(len({it["obj"]["ctx"][0] for it in items}), 3)     # (3 layers,
        self.assertEqual(len({it["obj"]["ctx"] for it in items}), 4)        # 4 clips)
        v.select_objects(0, items)
        self.assertIsNone(v.group_problem())
        before = looks(v, self.ocs)
        self.assertTrue(v.group_selection())
        self.assertEqual([it["kind"] for it in v.obj_sel[1]], ["group"])
        g = v.obj_sel[1][0]
        # drawn the same, and each layer turned off hides just its own lines, as before
        self.assertEqual(looks(v, self.ocs), before)
        props = v.doc.xref_get_key(g["xref"], "Resources/Properties")[1]
        for name in ("Ll", "L0", "Lb"):
            self.assertIn("/" + name, props)
        self.assertEqual(P.group_size(v.doc, g["xref"]), 12)
        # what the view keeps is what reading the page again gives
        same_objects(self, v.content_objects(0), P.Objects(v.doc[0]))
        # the page's layers stay nested properly (no layer closed inside a  q ... Q )
        depth, marks = 0, []
        for op, _a, _s, _e in P._tokens(P._contents(v.doc[0])):
            if op == b"q":
                depth += 1
            elif op == b"Q":
                depth -= 1
            elif op in (b"BDC", b"BMC"):
                marks.append(depth)
            elif op == b"EMC":
                self.assertEqual(marks.pop(), depth)
        # Ungroup gives the lines back, each on its own layer
        v.select_objects(0, [g])
        v.ungroup_selection()
        self.assertEqual(len(v.obj_sel[1]), 12)
        self.assertEqual(looks(v, self.ocs), before)

    def test_a_different_clip_still_says_why(self):
        v = self.view(b"q 0 0 300 300 re W n 0 0 1 RG 120 130 m 140 130 l S Q")
        items = self.ladder_and_strays()
        self.assertEqual(items[-1]["obj"]["box"], (120, 130, 140, 130))
        v.select_objects(0, items)
        self.assertIn("clipping", v.group_problem())
        v.select_objects(0, items[:-1])     # (the one under the other clip left out)
        self.assertIsNone(v.group_problem())

    def test_parts_of_a_tagged_page_stay_apart(self):
        v = self.view(b"/P <</MCID 0>> BDC 120 130 m 140 130 l S EMC "
                      b"/P <</MCID 1>> BDC 120 134 m 140 134 l S EMC")
        tagged = [it for it in self.objs.items if it["obj"]["box"][0] == 120]
        self.assertEqual(len(tagged), 2)
        v.select_objects(0, tagged)
        self.assertIn("tagged", v.group_problem())


class Speed(View):
    def test_grouping_does_not_read_the_drawing_again(self):
        v = self.view()
        items = self.ladder_and_strays()
        v.select_objects(0, items)
        with mock.patch.object(P, "scan_steps", side_effect=AssertionError("read again")), \
                mock.patch.object(P, "scan", side_effect=AssertionError("read again")):
            self.assertTrue(v.group_selection())
            objs = v.content_objects(0)
        self.assertEqual([it["kind"] for it in v.obj_sel[1]], ["group"])
        same_objects(self, objs, P.Objects(v.doc[0]))

    def test_a_group_moved_again_is_written_over_in_place(self):
        v = self.view()
        v.select_objects(0, self.ladder_and_strays())
        v.group_selection()
        page = v.doc[0]
        objs = v.content_objects(0)
        g = v.obj_sel[1][0]
        size = len(P._contents(page))
        for k in range(3):
            new = P.transform(page, [g["n"]], pymupdf.Matrix(1, 0, 0, 1, 3 + k, -2), objs)
            same_objects(self, new, P.Objects(page))
            # the length of the drawing stays: everything else is where it was, the same
            # objects as read (only the group's own made anew)
            self.assertEqual(len(P._contents(page)), size)
            for a, b in zip(objs.items, new.items):
                self.assertTrue(a is b or a["n"] == g["n"])
            for a, b in zip(objs.found, new.found):
                self.assertTrue(a is b or a is objs.found[g["n"]])
            objs = new

    def test_idle_preparation_waits_while_a_button_is_held(self):
        v = self.view()
        v.cad_select = True
        v._prep_timer = QTimer(v)
        v._prep_timer.setSingleShot(True)

        def unread():
            return sum(1 for it in self.objs.items if it["kind"] == "shape" and "lines" not in it)
        todo = unread()
        self.assertGreater(todo, 0)
        with mock.patch.object(QApplication, "mouseButtons", return_value=Qt.LeftButton):
            for _ in range(5):
                v._cad_prepare_step()
            self.assertEqual(unread(), todo)
            self.assertTrue(v._prep_timer.isActive())       # (it tries again later)
        for _ in range(5):
            v._cad_prepare_step()
        self.assertEqual(unread(), 0)

    def test_idle_preparation_waits_while_a_grip_is_hot(self):
        # (1.17: CAD mode moves by click, move, click, no button held: the pointer's moves
        # mustn't wait for a slice of it either)
        from kanzonas import cad_grips
        v = self.view()
        v.cad_select = True
        v._prep_timer = QTimer(v)
        v._prep_timer.setSingleShot(True)

        def unread():
            return sum(1 for it in self.objs.items if it["kind"] == "shape" and "lines" not in it)
        todo = unread()
        self.assertGreater(todo, 0)
        with mock.patch.object(cad_grips, "owner", return_value=v.pages[0]):
            for _ in range(5):
                v._cad_prepare_step()
            self.assertEqual(unread(), todo)
            self.assertTrue(v._prep_timer.isActive())
        for _ in range(5):
            v._cad_prepare_step()
        self.assertEqual(unread(), 0)


class OneBox(Window):
    def test_a_group_shows_one_box_and_says_what_it_holds(self):
        w, v = self.open()
        w.set_tool("editobjects")
        pump()
        shapes = [it for it in v.content_objects(0).items if it["kind"] == "shape"]
        self.assertEqual(len(shapes), 2)
        v.select_objects(0, shapes)
        w.a_group.trigger()
        pump()
        self.assertEqual([it["kind"] for it in v.obj_sel[1]], ["group"])
        self.assertEqual(w.props.title.text(), "Selected: Group (2 objects)")
        # one box: the group's own outline, no second box just outside it
        pw = v.pages[0]
        img = pw.grab().toImage()
        r = pw.to_screen(v.selected_objects_rect()).adjusted(-2, -2, 2, 2)
        y = round(r.top())

        def bluish(x, y):
            c = QColor(img.pixel(x, y))
            return c.blue() - c.red() > 60
        xs = range(round(r.left()) + 15, round(r.center().x()) - 15)
        self.assertEqual([x for x in xs if bluish(x, y) or bluish(x, y - 1)], [])
        inner = [x for x in xs if any(bluish(x, y + k) for k in (1, 2, 3))]
        self.assertTrue(inner)                              # (its outline is drawn)


if __name__ == "__main__":
    unittest.main()

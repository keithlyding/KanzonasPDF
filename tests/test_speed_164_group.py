"""1.16.4: Group, a drag and its release on a big CAD sheet, timed (the owner, 23 Nov 2026:
on his 174,000-object sheet with 92 layers, grouping a fork truck's 216 shapes took 4.6 s,
each mouse move of a drag 41 ms and the release 0.7 to 1 s).

The sheet is made here, like his: about 170,000 objects in layers, the sheet's frame set as
the clip again for each run of layers, many lines each in its own  q ... Q , labels, the
page turned 270 degrees, and a fork truck of 216 shapes on a layer of its own.

- Group works from the objects as read (it read the 5.8 MB drawing three times).
- A drag's mouse moves don't wait for CAD mode's idle preparation (a slice of it ran
  between two moves).
- The release writes the moved group over where it is and keeps the rest of the objects
  as read, and the sheet's scale note isn't read again when the text didn't change.

Grouping and the release are timed against one read of the sheet's objects, so a slower
machine doesn't fail them (on the machine where these were written: a read 1.1 s, Group
0.25 s in the view, a release 0.1 s, a mouse move 5 ms; before: 4.6 s and 0.45 s, and the
moves 40 ms and more while the preparation ran). A mouse move has its own budget: the
preparation's slice alone took 30 ms.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_speed_164_group
"""
import os
import random
import statistics
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import page_objects as P  # noqa: E402

FRAME = b"q\n648 0 m\n5951 0 l\n5951 10199 l\n648 10199 l\n648 0 l W n\n"
LAYERS = 40


def big_sheet(n=170000, seed=7):
    """The sheet (see the module's text) saved to a file: (path, the fork truck's layer)."""
    rnd = random.Random(seed)
    d = pymupdf.open()
    pg = d.new_page(width=792, height=1224)
    ocs = [d.add_ocg("Layer %d" % k, on=True) for k in range(LAYERS)]
    fork = d.add_ocg("FORKTRUCK", on=True)
    out = [b"0.12 0 0 0.12 0 0 cm"]
    per = n // 8
    made = 0
    for block in range(8):
        out.append(FRAME + b"0.5 0.5 0.5 RG /GS0 gs 1 j 1 J")
        for k in range(per // 1000):
            out.append(b"/OC /oc%d BDC" % rnd.randrange(LAYERS))
            for i in range(1000):
                x, y = rnd.uniform(700, 5900), rnd.uniform(0, 7000)
                if i % 3 == 0:
                    out.append(b"0 w\nq\n0 1 0 RG\n%d %d m %d %d l S\nQ" %
                               (x, y, x + rnd.uniform(-60, 60), y + rnd.uniform(-60, 60)))
                else:
                    out.append(b"%d %d m\n%d %d l\nS" % (x, y, x + rnd.uniform(-60, 60), y))
            made += 1000
            out.append(b"EMC")
        if block == 3:
            # labels
            out.append(b"/OC /oc0 BDC 0 g BT /F1 40 Tf")
            for i in range(300):
                out.append(b"1 0 0 1 %d %d Tm (ROOM %d) Tj" % (rnd.uniform(700, 5800),
                                                                rnd.uniform(0, 7000), i))
            out.append(b"ET EMC")
        if block == 6:
            # the fork truck: 216 shapes, by itself above the rest
            out.append(b"/OC /Fork BDC 0 0 1 RG")
            for i in range(216):
                x, y = 3000 + (i % 18) * 20, 8000 + (i // 18) * 30
                out.append(b"%d %d m %d %d l %d %d l S" % (x, y, x + 15, y, x + 15, y + 25))
            out.append(b"EMC")
        out.append(b"Q")
    x = d.get_new_xref()
    d.update_object(x, "<<>>")
    d.update_stream(x, b"\n".join(out))
    pg.set_contents(x)
    props = "".join("/oc%d %d 0 R" % (k, oc) for k, oc in enumerate(ocs)) + "/Fork %d 0 R" % fork
    font = d.get_new_xref()
    d.update_object(font, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    d.xref_set_key(pg.xref, "Resources",
                   "<</Properties<<%s>>/ExtGState<</GS0<</CA 1>>>>/Font<</F1 %d 0 R>>>>"
                   % (props, font))
    pg.set_rotation(270)
    path = os.path.join(tempfile.mkdtemp(), "big sheet.pdf")
    d.save(path)
    return path, made + 216


class BigSheet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path, cls.count = big_sheet()

    def setUp(self):
        from kanzonas.main_window import MainWindow
        self.w = w = MainWindow()
        w.settings.setValue("ask_beside", "false")
        w.resize(1400, 1000)
        w.show()
        w.open_file(self.path)
        APP.processEvents()
        self.v = v = w.view()
        self.addCleanup(self.close)
        w.set_tool("editobjects")
        self.mode = v.mouse_mode
        w.set_mouse_mode("cad")
        self.snap = w.a_snap_objects.isChecked()
        if self.snap:
            w.a_snap_objects.trigger()  # (its points are another matter: off)
        v.fit_page()
        APP.processEvents()

    def close(self):
        w = self.w
        w.set_mouse_mode(self.mode)
        if w.a_snap_objects.isChecked() != self.snap:
            w.a_snap_objects.trigger()
        self.v.dirty = False
        w._close_confirmed = True
        w.close()
        APP.processEvents()

    def fork(self):
        objs = self.v.content_objects(0)
        return [it for it in objs.items if it["obj"]["ctx"][0] == (b"/OC /Fork BDC",)]

    def test_group_drag_and_release(self):
        w, v = self.w, self.v
        t = time.perf_counter()
        objs = P.Objects(v.doc[0])
        read = time.perf_counter() - t
        self.assertGreater(len(objs.items), 160000)
        # Group, the fastest of three tries (each from the objects as read: an undo, and
        # the objects read again)
        tries = []
        for k in range(3):
            items = self.fork()
            self.assertEqual(len(items), 216)
            v.select_objects(0, items)
            w._update_ui()
            self.assertTrue(w.a_group.isEnabled())
            t = time.perf_counter()
            w.a_group.trigger()
            tries.append(time.perf_counter() - t)
            self.assertEqual([it["kind"] for it in v.obj_sel[1]], ["group"])
            if k < 2:
                w.a_undo.trigger()
                APP.processEvents()
        group = min(tries)
        # drags of the group and their releases. In the first, right after grouping, CAD
        # mode's idle preparation has all the sheet's outlines still to read: its first
        # mouse moves are timed (the preparation, run between them, read them in half a
        # second). The fastest of three releases
        pw = v.pages[0]
        releases = []
        for k in range(3):
            g = v.obj_sel[1][0]
            self.assertEqual(g["kind"], "group")
            c = pw.to_screen_pt((g["quad"].ul + g["quad"].lr) / 2).toPoint()
            if k == 0:
                self.assertTrue(any("lines" not in it for it in v.content_objects(0).items))
                v._prep_timer.start(0)
                APP.processEvents()
            QTest.mousePress(pw, Qt.LeftButton, Qt.NoModifier, c)
            APP.processEvents()
            each = []
            for i in range(1, 9):
                t = time.perf_counter()
                QTest.mouseMove(pw, c + QPoint(i * 5, i * 3))
                APP.processEvents()
                APP.processEvents()
                each.append(time.perf_counter() - t)
            if k == 0:
                first, move = each, statistics.median(each)
            t = time.perf_counter()
            QTest.mouseRelease(pw, Qt.LeftButton, Qt.NoModifier, c + QPoint(40, 24))
            releases.append(time.perf_counter() - t)
            APP.processEvents()
            self.assertEqual([it["kind"] for it in v.obj_sel[1]], ["group"])
            now = v.obj_sel[1][0]["rect"]
            self.assertGreater(abs(now.x0 - g["rect"].x0) + abs(now.y0 - g["rect"].y0), 5)
        release = min(releases)
        self.assertLess(group, 0.6 * read, (tries, read))
        self.assertLess(move, 0.030, first)
        self.assertLess(release, 0.2 * read, (releases, read))

if __name__ == "__main__":
    unittest.main()

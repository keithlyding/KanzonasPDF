"""Measure > Find similar (as Bluebeam's VisualSearch; visual_search.py): drag a box around one
symbol, choose where to look (this page or every page), the Count group, the sensitivity and
whether to find it turned too; the matching symbols are placed as Count markers of that group,
numbered on from its highest, in one undo step, for the user to check (delete any that aren't;
Ctrl+Z takes them all back). A symbol the group has a marker on already isn't counted again.
The search draws each page without its markups and runs a page at a time from the event loop
(no thread touches the document), with a window that can stop it.

The owner, 23 Nov 2026 (takeoff and quantity surveying, the seventh of seven): "Pick one symbol
on a sheet, find the matching ones (on the page or the whole set), and place them as Count
markers in a group, for the user to check before keeping. ... it must stay fast on big sheets
(no worker threads touching the document, per AGENTS.md)."

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_find_similar
"""
import os
import random
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import annotations as A, counts, main_window, visual_search as VS  # noqa: E402

P = pymupdf.Point


def symbol(page, c, kind="fixture"):
    s = page.new_shape()
    if kind == "fixture":                   # (a circle with a cross)
        s.draw_circle(c, 8)
        s.draw_line(c + (-8, 0), c + (8, 0))
        s.draw_line(c + (0, -8), c + (0, 8))
    elif kind == "other":                   # (a square with a diagonal)
        s.draw_rect(pymupdf.Rect(c.x - 8, c.y - 8, c.x + 8, c.y + 8))
        s.draw_line(c + (-8, -8), c + (8, 8))
    else:                                   # (an L and a dot, turned by kind quarters)
        m = pymupdf.Matrix(90 * kind)
        pts = [P(-8, -8) * m + c, P(-8, 8) * m + c, P(8, 8) * m + c]
        s.draw_polyline(pts)
        s.draw_circle(P(4, -4) * m + c, 2)
    s.finish(width=1, color=(0, 0, 0))
    s.commit()


FIXTURES = [P(80 + (i % 6) * 90, 100 + (i // 6) * 150) for i in range(12)]


def plan(pages=2, lines=300):
    d = pymupdf.open()
    random.seed(7)
    for k in range(pages):
        p = d.new_page(width=612, height=792)
        sh = p.new_shape()
        for _ in range(lines):
            x, y = random.uniform(0, 612), random.uniform(0, 792)
            sh.draw_line((x, y), (x + random.uniform(-30, 30), y + random.uniform(-30, 30)))
            sh.finish(width=0.4, color=(0.4, 0.4, 0.4))
        sh.commit()
        for c in FIXTURES[: 12 - 4 * k]:
            symbol(p, c)
        for i in range(5):
            symbol(p, P(130 + i * 90, 700), "other")
    path = os.path.join(tempfile.mkdtemp(), "plan.pdf")
    d.save(path)
    return path


class Window(unittest.TestCase):
    pages = 2

    def setUp(self):
        self.addCleanup(lambda: [setattr(x, "_close_confirmed", True) or x.close()
                                 for x in main_window.windows()])
        w = self.w = main_window.MainWindow()
        w.resize(1200, 900)
        w.show()
        w.open_file(plan(self.pages))
        APP.processEvents()
        v = self.v = w.view()
        self.addCleanup(lambda: setattr(v, "dirty", False))
        self.opts = {"scope": "page", "group": "Fixtures", "sensitivity": 0.8, "turned": False}
        v.ask_find_similar = lambda groups, default: dict(self.opts)
        self.said = []
        v.statusMessage.connect(self.said.append)

    def find(self, index=0, at=FIXTURES[0], half=11):
        self.w.set_tool("findsimilar")
        APP.processEvents()
        self.v.apply_drag_tool(index, "findsimilar", at - (half, half), at + (half, half), False)
        end = time.monotonic() + 30
        while self.v._find_job is not None and time.monotonic() < end:
            APP.processEvents()
        APP.processEvents()

    def markers(self):
        return [(i, m) for i, _x, m in counts.markers(self.v.doc)]


class FindSimilar(Window):
    def test_this_page_its_symbols_become_count_markers(self):
        self.find()
        got = self.markers()
        self.assertEqual(len(got), 12)                       # (the 12, not the 5 others)
        self.assertEqual({i for i, _m in got}, {0})
        self.assertEqual({counts.group_of(m) for _i, m in got}, {"Fixtures"})
        self.assertEqual(sorted(m["n"] for _i, m in got), list(range(1, 13)))
        for c in FIXTURES:
            self.assertTrue(any(abs(m["points"][0] - c) < 3 for _i, m in got), c)
        self.assertTrue(any("Found 12 similar symbols" in s for s in self.said))
        self.v.undo()                                        # (all of them at once)
        APP.processEvents()
        self.assertEqual(self.markers(), [])

    def test_every_page_and_not_counted_twice(self):
        self.opts["scope"] = "all"
        self.find()
        got = self.markers()
        self.assertEqual(sorted(i for i, _m in got).count(0), 12)
        self.assertEqual(sorted(i for i, _m in got).count(1), 8)
        self.find()                                          # (again: nothing new)
        self.assertEqual(len(self.markers()), 20)
        self.assertTrue(any("nothing new" in s for s in self.said))

    def test_a_blank_box_finds_nothing(self):
        rev = self.v.revision
        self.find(at=P(590, 20), half=5)
        self.assertEqual(self.v.revision, rev)
        self.assertTrue(any("nothing in that box" in s for s in self.said))

    def test_cancelled_dialog_does_nothing(self):
        self.v.ask_find_similar = lambda groups, default: None
        rev = self.v.revision
        self.find()
        self.assertEqual(self.v.revision, rev)

    def test_stopped_nothing_is_placed(self):
        from unittest import mock
        self.opts["scope"] = "all"
        real = VS.search_page

        def first_then_stop(*a, **k):
            self.v._find_job["bar"].canceled.emit()      # (Stop pressed during page 1)
            return real(*a, **k)
        rev = self.v.revision
        with mock.patch.object(VS, "search_page", first_then_stop):
            self.find()
        self.assertEqual(self.v.revision, rev)
        self.assertTrue(any("stopped" in s for s in self.said))

    def test_numbered_on_from_the_group_and_its_look(self):
        pg = self.v.doc[0]
        self.v.modify(lambda: A.write(pg, {"kind": "m_count", "rect": pymupdf.Rect(),
                                           "props": dict(A.DEFAULTS["m_count"], group="Fixtures",
                                                         stroke="#ff8800"),
                                           "points": [P(500, 600)], "n": 7}), [0])
        self.find()
        got = [m for _i, m in self.markers() if m["n"] != 7]
        self.assertEqual(sorted(m["n"] for m in got), list(range(8, 20)))
        self.assertEqual({m["props"]["stroke"] for m in got}, {"#ff8800"})


class Turned(unittest.TestCase):
    def test_turned_by_quarters(self):
        d = pymupdf.open()
        p = d.new_page(width=612, height=792)
        for k, c in enumerate([P(100, 100), P(200, 100), P(300, 100), P(400, 100)]):
            symbol(p, c, k)
        z = VS.zoom_for(p, pymupdf.Rect(89, 89, 111, 111))
        t = VS.template(p, pymupdf.Rect(89, 89, 111, 111), z)
        self.assertEqual(len(VS.search_page(p, t, z, 0.8)), 1)
        self.assertEqual(len(VS.search_page(p, t, z, 0.8, turned=True)), 4)


class OnABigSheet(unittest.TestCase):
    def test_a_36_by_24_sheet_with_20000_lines(self):
        d = pymupdf.open()
        p = d.new_page(width=36 * 72, height=24 * 72)
        random.seed(3)
        sh = p.new_shape()
        for _ in range(20000):
            x, y = random.uniform(0, 2592), random.uniform(0, 1728)
            sh.draw_line((x, y), (x + random.uniform(-40, 40), y + random.uniform(-40, 40)))
            sh.finish(width=0.3, color=(0.5, 0.5, 0.5))
        sh.commit()
        spots = [P(150 + (i % 15) * 160, 150 + (i // 15) * 400) for i in range(60)]
        for c in spots:
            symbol(p, c)
        r = pymupdf.Rect(spots[0] - (11, 11), spots[0] + (11, 11))
        z = VS.zoom_for(p, r)
        t0 = time.perf_counter()
        got = VS.search_page(p, VS.template(p, r, z), z, 0.75)
        took = time.perf_counter() - t0
        centers = [(g.tl + g.br) / 2 for g, _s in got]
        found = sum(1 for c in spots if any(abs(c - q) < 4 for q in centers))
        self.assertGreaterEqual(found, 57)                  # (at 0.75: nearly all of them)
        self.assertLess(len(got) - found, 4)                # (and hardly anything else)
        self.assertLess(took, 8.0)                          # (about 1.5 s here)


if __name__ == "__main__":
    unittest.main()

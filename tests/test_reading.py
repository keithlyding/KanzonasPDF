"""Reading comfort (View menu): Full screen, Presentation, Page layout (single page,
continuous, two pages, with the cover page on its own), Reading view (the text reflowed in
reading order), Read aloud (with a stand-in for QTextToSpeech) and Auto scroll.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_reading
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, Signal  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import read_aloud, reading, reading_text  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402

LEFT = ("The left column starts here. It goes on for a while! Does it end? "
        "Yes, at the bottom of the column. ") * 2
RIGHT = "The right column comes second. It is read after the left one. " * 3


def two_column_pdf(path, pages=3, size=(612, 792)):
    doc = pymupdf.open()
    for i in range(pages):
        pg = doc.new_page(width=size[0], height=size[1])
        pg.insert_text((72, 70), "Chapter %d" % (i + 1), fontsize=26)
        pg.insert_textbox(pymupdf.Rect(72, 110, 296, 330), LEFT, fontsize=11)
        pg.insert_textbox(pymupdf.Rect(316, 110, 540, 330), RIGHT, fontsize=11)
        # both columns have a gap at the same height: still read column by column
        pg.insert_textbox(pymupdf.Rect(72, 350, 296, 420), "Left second paragraph.", fontsize=11)
        pg.insert_textbox(pymupdf.Rect(316, 350, 540, 420), "Right second paragraph.",
                          fontsize=11)
        pg.insert_textbox(pymupdf.Rect(72, 460, 540, 520), "A footnote across the page.",
                          fontsize=9)
    doc.save(path)


class _Base(unittest.TestCase):
    pages = 3
    size = (612, 792)

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kz-reading-")
        self.path = os.path.join(self.dir, "book.pdf")
        two_column_pdf(self.path, self.pages, self.size)
        self.w = MainWindow()
        self.w._close_confirmed = True
        self.w.resize(1200, 900)
        self.w.show()
        self.w.open_file(self.path)
        for _ in range(3):
            APP.processEvents()
        self.v = self.w.view()

    def tearDown(self):
        reading.window_closing(self.w)
        self.w.settings.remove("file_states")
        self.w.close()
        self.w.deleteLater()
        APP.processEvents()


class FullScreen(_Base):
    def test_enter_and_leave(self):
        w = self.w
        self.assertTrue(w.menuBar().isVisible())
        w.a_full_screen.trigger()
        APP.processEvents()
        self.assertTrue(w.isFullScreen())
        self.assertTrue(w.a_full_screen.isChecked())
        self.assertFalse(w.menuBar().isVisible())
        self.assertFalse(w.statusBar().isVisible())
        self.assertFalse(w.tabs.tabBar().isVisible())
        self.assertFalse(w.dock.isVisible())
        self.assertTrue(self.v.isVisible())
        # Escape on the page (nothing selected, the default tool): out of full screen
        self.v.setFocus()
        QTest.keyClick(self.v, Qt.Key_Escape)
        APP.processEvents()
        self.assertFalse(w.isFullScreen())
        self.assertFalse(w.a_full_screen.isChecked())
        self.assertTrue(w.menuBar().isVisible())
        self.assertTrue(w.statusBar().isVisible())
        self.assertTrue(w.dock.isVisible())

    def test_escape_puts_the_tool_down_first(self):
        w = self.w
        reading.enter_full_screen(w)
        w.set_tool("rect")
        QTest.keyClick(self.v, Qt.Key_Escape)
        APP.processEvents()
        self.assertTrue(w.isFullScreen())           # the tool was put down
        self.assertEqual(w.tool, w.default_tool())
        QTest.keyClick(self.v, Qt.Key_Escape)
        APP.processEvents()
        self.assertFalse(w.isFullScreen())

    def test_top_edge_shows_the_slim_bar(self):
        w = self.w
        w.a_full_screen.trigger()
        APP.processEvents()
        full = w._full
        bar = w._fs_bar
        self.assertFalse(bar.isVisible())

        def move(y):
            at = w.mapToGlobal(QPoint(200, y))
            with mock.patch.object(reading.QCursor, "pos", return_value=at), \
                    mock.patch.object(w, "isActiveWindow", return_value=True):
                ev = QMouseEvent(QEvent.MouseMove, QPointF(200, y), QPointF(at),
                                 Qt.NoButton, Qt.NoButton, Qt.NoModifier)
                full.eventFilter(self.v.viewport(), ev)
        move(1)
        self.assertTrue(bar.isVisible())
        self.assertEqual(bar.y(), 0)
        move(400)
        self.assertFalse(bar.isVisible())
        w.a_full_screen.trigger()                   # Ctrl+Shift+L again: back
        APP.processEvents()
        self.assertFalse(w.isFullScreen())
        self.assertFalse(bar.isVisible())

    def test_shortcuts(self):
        self.assertEqual(self.w.a_full_screen.shortcut().toString(), "Ctrl+Shift+L")
        self.assertEqual(self.w.a_present.shortcut().toString(), "F5")
        self.assertEqual(self.w.a_cad_mouse.shortcut().toString(), "F11")    # (unchanged)
        self.assertEqual(self.w.a_lock.shortcut().toString(), "Ctrl+L")


class Presentation(_Base):
    pages = 6

    def test_keys(self):
        self.v.goto_page(1)
        p = reading.start_presentation(self.w)
        APP.processEvents()
        self.assertTrue(p.isFullScreen())
        self.assertEqual(p.page, 1)
        for key, want in ((Qt.Key_Space, 2), (Qt.Key_Right, 3), (Qt.Key_PageDown, 4),
                          (Qt.Key_Left, 3), (Qt.Key_Backspace, 2), (Qt.Key_PageUp, 1),
                          (Qt.Key_End, 5), (Qt.Key_Down, 5), (Qt.Key_Home, 0),
                          (Qt.Key_Up, 0)):
            QTest.keyClick(p, key)
            self.assertEqual(p.page, want, key)
        QTest.keyClicks(p, "4")
        QTest.keyClick(p, Qt.Key_Return)
        self.assertEqual(p.page, 3)                 # a page number and Enter
        QTest.mouseClick(p, Qt.LeftButton)
        self.assertEqual(p.page, 4)
        QTest.mouseClick(p, Qt.RightButton)
        self.assertEqual(p.page, 3)
        # B: a black screen, W: white; any other key brings the page back (and is used up)
        QTest.keyClick(p, Qt.Key_B)
        self.assertEqual(p.blank, "black")
        QTest.keyClick(p, Qt.Key_W)
        self.assertEqual(p.blank, "white")
        QTest.keyClick(p, Qt.Key_Space)
        self.assertIsNone(p.blank)
        self.assertEqual(p.page, 3)
        QTest.keyClick(p, Qt.Key_L)
        self.assertTrue(p.laser)
        p.repaint()                                 # (draws the page and the pointer)
        QTest.keyClick(p, Qt.Key_L)
        self.assertFalse(p.laser)
        img = p.grab().toImage()
        self.assertFalse(img.isNull())
        QTest.keyClick(p, Qt.Key_Escape)
        APP.processEvents()
        self.assertIsNone(self.w._presentation)
        self.assertEqual(self.v.current_page(), 3)  # back at the page shown last

    def test_page_drawn_fitted(self):
        p = reading.start_presentation(self.w)
        APP.processEvents()
        pm = p._pixmap(0)
        dpr = pm.devicePixelRatio()
        w, h = pm.width() / dpr, pm.height() / dpr
        self.assertTrue(abs(w - p.width()) <= 2 or abs(h - p.height()) <= 2)
        self.assertLessEqual(w, p.width() + 1)
        self.assertLessEqual(h, p.height() + 1)
        p.close()


class PageLayouts(_Base):
    pages = 7
    size = (300, 400)

    def place(self, i):
        g = self.v.pages[i].geometry()
        return g.x(), g.y(), g.width()

    def test_two_pages_continuous_with_cover(self):
        v = self.v
        self.w.layout_actions["two_continuous"].trigger()
        APP.processEvents()
        self.assertEqual(v.page_layout, "two_continuous")
        # without the cover page: 1|2, 3|4, ... (0-based 0|1, 2|3)
        x0, y0, w0 = self.place(0)
        x1, y1, _ = self.place(1)
        self.assertEqual(y0, y1)
        self.assertGreater(x1, x0)
        self.assertLessEqual(x1 - (x0 + w0), 12)        # the spread's pages meet in the middle
        self.assertGreater(self.place(2)[1], y0)
        self.w.a_cover.trigger()                         # cover page on its own
        APP.processEvents()
        self.assertTrue(v.cover_page)
        x0, y0, _ = self.place(0)
        x1, y1, _ = self.place(1)
        x2, y2, _ = self.place(2)
        self.assertGreater(y1, y0)                       # the cover alone in the first row
        self.assertEqual(y1, y2)                         # then 2|3 (book spreads)
        self.assertLess(x1, x2)
        self.assertEqual(x0, x2)                         # the cover on the right
        self.assertEqual([v.spread(i) for i in range(4)], [[0], [1, 2], [1, 2], [3, 4]])
        # every page shown
        self.assertTrue(all(not w.isHidden() for w in v.pages))
        # a text drag from page 2 across to page 3 beside it ends on page 3
        right = v.pages[2]
        pos = v.pages[1].mapFromGlobal(right.mapToGlobal(QPoint(right.width() // 2, 30)))
        self.assertEqual(v.page_point_from(v.pages[1], QPointF(pos))[0], 2)
        pos = v.pages[1].mapFromGlobal(right.mapToGlobal(QPoint(-5, 30)))   # (in the gap)
        self.assertEqual(v.page_point_from(v.pages[1], QPointF(pos))[0], 1)

    def test_two_pages_one_spread_at_a_time(self):
        v = self.v
        self.w.layout_actions["two"].trigger()
        APP.processEvents()
        shown = [i for i, w in enumerate(v.pages) if not w.isHidden()]
        self.assertEqual(shown, [0, 1])
        v.setFocus()
        QTest.keyClick(v, Qt.Key_Right)                  # the next spread
        self.assertEqual(v.current_page(), 2)
        self.assertEqual([i for i, w in enumerate(v.pages) if not w.isHidden()], [2, 3])
        self.w.a_next_page.trigger()
        self.assertEqual(v.current_page(), 4)
        self.w.a_last_page.trigger()
        self.assertEqual(v.current_page(), 6)
        self.assertEqual([i for i, w in enumerate(v.pages) if not w.isHidden()], [6])
        QTest.keyClick(v, Qt.Key_Left)
        self.assertEqual(v.current_page(), 4)
        # fit width: the spread across the window
        v.fit_width()
        APP.processEvents()
        both = v.pages[5].geometry().right() - v.pages[4].geometry().left()
        self.assertLessEqual(both, v.viewport().width())
        self.assertGreater(both, v.viewport().width() * 0.8)

    def test_single_page_turns_at_the_edge(self):
        v = self.v
        self.w.layout_actions["single"].trigger()
        APP.processEvents()
        v.set_zoom(3.0)
        APP.processEvents()
        self.assertEqual([i for i, w in enumerate(v.pages) if not w.isHidden()], [0])
        bar = v.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        v.setFocus()
        QTest.keyClick(v, Qt.Key_PageDown)               # scrolls within the page first
        self.assertEqual(v.current_page(), 0)
        page = v.pages[0]
        bar.setValue(page.y() + page.height() - v.viewport().height() + 20)
        QTest.keyClick(v, Qt.Key_PageDown)               # its end in view: the next page
        self.assertEqual(v.current_page(), 1)
        self.assertEqual(bar.value(), v.pages[1].y() - 12)      # at its top
        QTest.keyClick(v, Qt.Key_PageUp)                 # back up: the bottom of page 1
        self.assertEqual(v.current_page(), 0)
        page = v.pages[0]
        self.assertGreaterEqual(bar.value() + v.viewport().height(), page.y() + page.height())
        self.assertLess(bar.value(), page.y() + page.height())
        # the thumbnails and Go to still reach any page
        v.goto_page(5)
        self.assertEqual(v.current_page(), 5)
        self.assertEqual([i for i, w in enumerate(v.pages) if not w.isHidden()], [5])
        self.w.layout_actions["continuous"].trigger()
        APP.processEvents()
        self.assertTrue(all(not w.isHidden() for w in v.pages))
        self.assertEqual(v.current_page(), 5)

    def test_remembered_per_document(self):
        self.w.layout_actions["two"].trigger()
        self.w.a_cover.trigger()
        self.w.close_tab(self.w.tabs.currentIndex())
        APP.processEvents()
        self.w.open_file(self.path)
        for _ in range(3):
            APP.processEvents()
        v = self.w.view()
        self.assertEqual((v.page_layout, v.cover_page), ("two", True))
        self.assertTrue(self.w.layout_actions["two"].isChecked())
        self.assertTrue(self.w.a_cover.isChecked())


class ReadingOrder(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kz-reading-")
        self.path = os.path.join(self.dir, "cols.pdf")
        two_column_pdf(self.path, 1)

    def test_two_columns_in_order(self):
        doc = pymupdf.open(self.path)
        blocks = reading_text.read_page(doc[0])
        texts = [b.text() for b in blocks]
        self.assertEqual(texts[0], "Chapter 1")
        self.assertTrue(texts[1].startswith("The left column starts here."))
        self.assertEqual(texts[2], "Left second paragraph.")
        self.assertTrue(texts[3].startswith("The right column comes second."))
        self.assertEqual(texts[4], "Right second paragraph.")
        self.assertEqual(texts[5], "A footnote across the page.")
        html = reading_text.page_html(blocks, 16)
        self.assertIn("<h1", html)              # the title, bigger than the text
        self.assertLess(html.index("left column"), html.index("right column"))
        doc.close()

    def test_column_beside_a_picture_stays_in_its_column(self):
        # the right column is empty beside a picture (pictures aren't read): the left
        # column's text there still belongs between its paragraphs above and below
        B = reading_text.Block

        def blk(x0, y0, x1, y1, text):
            return B((x0, y0, x1, y1), [[(text, (x0, y0, x1, y1))]], 10, False)
        blocks = [blk(72, 40, 540, 60, "Title"),
                  blk(72, 100, 290, 200, "L1"), blk(320, 100, 540, 200, "R1"),
                  blk(72, 220, 290, 300, "L2"),                       # (a picture at the right)
                  blk(72, 320, 290, 400, "L3"), blk(320, 320, 540, 400, "R3"),
                  blk(72, 450, 540, 470, "Footer")]
        order = [b.lines[0][0][0] for b in reading_text.order_blocks(blocks)]
        self.assertEqual(order, ["Title", "L1", "L2", "L3", "R1", "R3", "Footer"])

    def test_a_turned_page_in_the_order_it_is_shown(self):
        doc = pymupdf.open(self.path)
        doc[0].set_rotation(90)
        texts = [b.text() for b in reading_text.read_page(doc[0])]
        self.assertEqual(texts[0], "Chapter 1")
        self.assertEqual(len(texts), 6)
        doc.close()
        # text written sideways (bottom to top): read from its first line on
        doc = pymupdf.open()
        pg = doc.new_page()
        for k, word in reversed(list(enumerate(("First", "Second", "Third")))):
            pg.insert_text((100 + 30 * k, 500), word + " line", fontsize=12, rotate=90)
        texts = [b.text() for b in reading_text.read_page(pg)]
        self.assertEqual(texts, ["First line", "Second line", "Third line"])

    def test_hyphen_at_a_line_end_joined(self):
        self.assertEqual(reading_text.join_lines(["We are read-", "ing it. Well-", "Known"]),
                         "We are reading it. Well- Known")

    def test_sentences_with_places(self):
        doc = pymupdf.open(self.path)
        blocks = reading_text.read_page(doc[0])
        ss = reading_text.sentences(blocks, 0)
        self.assertEqual(ss[0].text, "Chapter 1")
        self.assertEqual(ss[1].text, "The left column starts here.")
        self.assertEqual(ss[2].text, "It goes on for a while!")
        self.assertEqual(ss[3].text, "Does it end?")
        for s in ss:
            for start, end, rects in s.words:
                self.assertTrue(rects)
                self.assertNotIn(" ", s.text[start:end])
        # from a point: the sentence starts at the nearest word
        x0, y0, x1, y1 = ss[3].words[0][2][0]
        later = reading_text.sentences(blocks, 0, start=((x0 + x1) / 2, (y0 + y1) / 2))
        self.assertEqual(later[0].text, "Does it end?")
        doc.close()


class _FakeTTS(QObject):
    """A stand-in for QTextToSpeech: say() starts a sentence; the test says each word and
    finishes it."""
    stateChanged = Signal(object)
    sayingWord = Signal(str, int, int, int)

    class State:
        Ready, Speaking, Paused, Error = range(4)

    made = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = self.State.Ready
        self.said = []
        self.rate = None
        self.voice = None
        _FakeTTS.made.append(self)

    @staticmethod
    def availableEngines():
        return ["fake"]

    def availableVoices(self):
        return [_Voice("Anne"), _Voice("Bob")]

    def state(self):
        return self._state

    def setRate(self, r):
        self.rate = r

    def setVoice(self, v):
        self.voice = v.name()

    def say(self, text):
        self.said.append(text)
        self._state = self.State.Speaking
        self.stateChanged.emit(self._state)

    def finish(self, words=True):
        text = self.said[-1]
        pos = 0
        if words:
            for word in text.split(" "):
                self.sayingWord.emit(word, 0, pos, len(word))
                pos += len(word) + 1
        self._state = self.State.Ready
        self.stateChanged.emit(self._state)
        APP.processEvents()                 # (the next sentence starts on the event loop)

    def stop(self):
        self._state = self.State.Ready
        self.stateChanged.emit(self._state)

    def pause(self):
        self._state = self.State.Paused

    def resume(self):
        self._state = self.State.Speaking


class _Voice:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class ReadAloud(_Base):
    def setUp(self):
        super().setUp()
        _FakeTTS.made = []
        p = mock.patch.object(read_aloud, "_engine_class", _FakeTTS)
        p.start()
        self.addCleanup(p.stop)

    def test_sentences_in_order_highlight_follows_and_stop(self):
        w, v = self.w, self.v
        w.settings.setValue("read_rate", 5)
        w.settings.setValue("read_voice", "Bob")
        w.a_read_page.trigger()
        r = w._reader
        eng = _FakeTTS.made[-1]
        self.assertEqual((eng.rate, eng.voice), (0.5, "Bob"))     # Preferences' choices
        self.assertEqual(eng.said, ["Chapter 1"])
        self.assertEqual(r.state, "speaking")
        self.assertTrue(w.a_read_stop.isEnabled())
        self.assertEqual(v.read_mark[0], 0)
        eng.finish()
        self.assertEqual(eng.said[-1], "The left column starts here.")
        # the word being said is marked, and moves on with the voice
        eng.sayingWord.emit("left", 0, 4, 4)
        word = v.read_mark[2]
        self.assertEqual(len(word), 1)
        eng.sayingWord.emit("column", 0, 9, 6)
        self.assertNotEqual(v.read_mark[2], word)
        self.assertGreater(v.read_mark[2][0][0], word[0][0])
        v.pages[0].repaint()                    # (paints the marks)
        eng.finish()
        eng.finish()
        self.assertEqual(eng.said[1:], ["The left column starts here.",
                                        "It goes on for a while!", "Does it end?"])
        w.a_read_pause.trigger()
        self.assertEqual(r.state, "paused")
        w.a_read_pause.trigger()
        self.assertEqual(r.state, "speaking")
        w.a_read_stop.trigger()
        self.assertEqual(r.state, "stopped")
        self.assertIsNone(v.read_mark)
        self.assertFalse(w.a_read_stop.isEnabled())
        n = len(eng.said)
        eng.finish()                            # (a late "ready" from the engine: nothing more)
        self.assertEqual(len(eng.said), n)

    def test_a_late_ready_from_a_stop_skips_nothing(self):
        w = self.w
        w.a_read_page.trigger()
        eng = _FakeTTS.made[-1]
        eng.say = lambda text: eng.said.append(text)     # (begins speaking only later)
        w.a_read_page.trigger()                 # again: the first reading is stopped
        eng.stateChanged.emit(eng.State.Ready)  # the engine's late answer to that stop
        APP.processEvents()
        self.assertEqual(eng.said[-1], "Chapter 1")
        self.assertEqual(w._reader.current.text, "Chapter 1")
        w.a_read_stop.trigger()

    def test_the_page_then_stops_and_the_document_goes_on(self):
        w = self.w
        w.a_read_page.trigger()
        eng = _FakeTTS.made[-1]
        for _ in range(40):
            if w._reader.state == "stopped":
                break
            eng.finish(words=False)
        self.assertEqual(w._reader.state, "stopped")
        self.assertEqual(eng.said[-1], "A footnote across the page.")
        self.assertNotIn("Chapter 2", eng.said)
        eng.said.clear()
        w.a_read_doc.trigger()                  # from the first page, on to the next ones
        for _ in range(40):
            if "Chapter 2" in eng.said:
                break
            eng.finish(words=False)
        self.assertEqual(eng.said[0], "Chapter 1")
        self.assertIn("Chapter 2", eng.said)
        self.assertEqual(self.v.read_mark[0], 1)
        self.assertEqual(self.v.current_page(), 1)      # the view followed
        w.a_read_stop.trigger()

    def test_from_selected_text(self):
        w, v = self.w, self.v
        blocks = v.reading_blocks(0)
        s = reading_text.sentences(blocks, 0)[3]          # "Does it end?"
        x0, y0, x1, y1 = s.words[0][2][0]
        unit = (x0, y0, x0 + 3, y1, "D", 1, 0, 0)
        v.text_sel = [(0, [unit])]
        w.a_read_from.trigger()
        eng = _FakeTTS.made[-1]
        self.assertEqual(eng.said, ["Does it end?"])
        w.a_read_stop.trigger()

    def test_voice_and_speed_in_preferences(self):
        from kanzonas.preferences import PreferencesDialog
        w = self.w
        w.settings.setValue("read_voice", "")
        d = PreferencesDialog(w)
        self.addCleanup(d.close)
        self.assertEqual(d.voice.count(), 1)            # (the voices: only when opened)
        d.voice.showPopup()
        d.voice.hidePopup()
        self.assertEqual([d.voice.itemText(i) for i in range(1, d.voice.count())],
                         ["Anne", "Bob"])
        d.voice.setCurrentIndex(d.voice.findData("Bob"))
        d.rate.setValue(-4)
        d.scroll_speed.setValue(120)
        d._apply()
        self.assertEqual(w.settings.value("read_voice"), "Bob")
        self.assertEqual(int(w.settings.value("read_rate")), -4)
        self.assertEqual(int(w.settings.value("autoscroll_speed")), 120)
        eng = _FakeTTS.made[-1]
        self.assertEqual((eng.voice, eng.rate), ("Bob", -0.4))     # (applied at once)
        d2 = PreferencesDialog(w)                       # remembered
        self.addCleanup(d2.close)
        self.assertEqual(d2.voice.currentData(), "Bob")
        self.assertEqual(d2.rate.value(), -4)

    def test_no_speech(self):
        with mock.patch.object(read_aloud, "_engine_class", None), \
                mock.patch.object(read_aloud, "tts_class", return_value=None), \
                mock.patch.object(reading.QMessageBox, "information") as box:
            self.assertFalse(reading.read(self.w, "page"))
        box.assert_called_once()

    def test_qt_mock_engine(self):
        """Qt's own test voice ("mock", in the PySide6 wheel) through the real class."""
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
        except ImportError:
            self.skipTest("no QtTextToSpeech")
        if "mock" not in QTextToSpeech.availableEngines():
            self.skipTest("no mock speech engine")
        with mock.patch.object(read_aloud, "_engine_class",
                               lambda parent: QTextToSpeech("mock", parent)):
            self.w._reader = None
            self.w.a_read_page.trigger()
            r = self.w._reader
            words = []
            r.engine.sayingWord.connect(lambda word, *_: words.append(word))
            for _ in range(200):
                QTest.qWait(20)
                if len(words) >= 3:
                    break
            self.assertEqual(words[:2], ["Chapter", "1"])
            r.stop()
            self.assertIsNone(self.v.read_mark)


class ReadingView(_Base):
    def test_pane_follows_the_page_and_sizes(self):
        w = self.w
        w.a_reflow.trigger()
        APP.processEvents()
        pane = w.reading_pane
        self.assertTrue(w.reading_dock.isVisible())
        self.assertTrue(w.a_reflow.isChecked())
        text = pane.text.toPlainText()
        self.assertTrue(text.startswith("Page 1 of 3") or "Chapter 1" in text)
        self.assertIn("Chapter 1", text)
        self.assertLess(text.index("left column"), text.index("right column"))
        self.view_page(1)
        self.assertIn("Chapter 2", pane.text.toPlainText())
        size = pane.size
        pane.bigger(1)
        self.assertGreater(pane.size, size)
        self.assertEqual(int(w.settings.value("reflow_size")), pane.size)
        w.a_reflow.trigger()
        self.assertFalse(w.reading_dock.isVisible())

    def view_page(self, i):
        self.v.goto_page(i)
        APP.processEvents()


class AutoScroll(_Base):
    def test_scrolls_speeds_up_and_stops(self):
        w, v = self.w, self.v
        w.settings.setValue("autoscroll_speed", 400)
        w._autoscroll = None
        bar = v.verticalScrollBar()
        bar.setValue(0)
        w.a_autoscroll.trigger()
        a = w._autoscroll
        self.assertTrue(a.active)
        self.assertTrue(w.a_autoscroll.isChecked())
        for _ in range(5):
            a._tick()
        self.assertGreater(bar.value(), 0)
        QTest.keyClick(v, Qt.Key_Down)
        self.assertEqual(a.speed, 500)
        self.assertEqual(int(w.settings.value("autoscroll_speed")), 500)
        QTest.keyClick(v, Qt.Key_Escape)
        self.assertFalse(a.active)
        self.assertFalse(w.a_autoscroll.isChecked())


class Menus(_Base):
    def test_in_the_view_menu_and_the_manual(self):
        from kanzonas import manual
        names = [a.text() for a in self.w.view_menu.actions()]
        for n in ("Full screen", "Presentation", "Page layout", "Reading view", "Read aloud",
                  "Auto scroll"):
            self.assertIn(n, names)
        self.assertEqual(manual.missing_from_manual(self.w), [])

    def test_speech_not_loaded_at_start_up(self):
        code = ("import os, sys; from PySide6.QtCore import QSettings\n"
                "for f in (QSettings.NativeFormat, QSettings.IniFormat):\n"
                "    QSettings.setPath(f, QSettings.UserScope, os.environ['KZ_SETTINGS'])\n"
                "from PySide6.QtWidgets import QApplication; app = QApplication([])\n"
                "from kanzonas.main_window import MainWindow; w = MainWindow()\n"
                "print('QtTextToSpeech' in ' '.join(sys.modules))\n"
                "sys.stdout.flush(); os._exit(0)\n")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", KANZONAS_LANG="en",
                   KZ_SETTINGS=tempfile.mkdtemp(prefix="kz-reading-settings-"))
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "False", out.stderr)


if __name__ == "__main__":
    unittest.main()

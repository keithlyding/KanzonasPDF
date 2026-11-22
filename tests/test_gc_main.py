"""Python's garbage collector runs only on the main thread (kanzonas/gc_main.py). It used to
run on whichever thread was making objects when a collection was due: on a worker thread it
deleted closed windows (and their timers) off their own thread, "Timers cannot be stopped
from another thread", and a crash (the Scan window, 1.15.14; the scan stress test on the Mac
and Windows builds).

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_gc_main
"""
import gc
import os
import sys
import threading
import time
import unittest
import weakref
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QTimer, qInstallMessageHandler  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas import gc_main  # noqa: E402


class Cycle:
    pass


def make_cycles(n):
    for _ in range(n):
        a = Cycle()
        a.me = a


def spin(until, seconds=5.0):
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        APP.processEvents()
        time.sleep(0.01)


class Collector(unittest.TestCase):
    def setUp(self):
        self.c = gc_main.install()
        self.assertIsNotNone(self.c)
        self.main = threading.get_ident()
        self.where = []

        def seen(phase, info):
            if phase == "start":
                self.where.append(threading.get_ident())
        gc.callbacks.append(seen)
        self.addCleanup(gc.callbacks.remove, seen)

    def test_the_automatic_collector_is_off_and_the_main_thread_collects(self):
        self.assertTrue(gc_main.installed())
        self.assertFalse(gc.isenabled())
        self.assertTrue(self.c.timer.isActive())

    def test_installing_again_keeps_the_one_collector(self):
        self.assertIs(gc_main.install(), self.c)

    def test_a_worker_making_cycles_runs_no_collection(self):
        t = threading.Thread(target=make_cycles, args=(200_000,))
        t.start()
        t.join()
        self.assertEqual([w for w in self.where if w != self.main], [])

    def test_the_main_thread_collects_them(self):
        gone = []
        a = Cycle()
        a.me = a
        weakref.finalize(a, lambda: gone.append(threading.get_ident()))
        del a
        make_cycles(5_000)                  # (past the first generation's threshold)
        spin(lambda: gone)
        self.assertEqual(gone, [self.main])
        self.assertTrue(self.where)
        self.assertTrue(all(w == self.main for w in self.where))

    def test_a_closed_qt_object_with_a_timer_is_freed_on_the_main_thread(self):
        """What crashed: a QObject owning a running timer, left in a reference cycle, freed
        by a collection on a worker thread."""
        warnings, gone = [], []
        old = qInstallMessageHandler(lambda mode, ctx, msg: warnings.append(msg))
        self.addCleanup(qInstallMessageHandler, old)
        o = QObject()
        o.timer = QTimer(o)
        o.timer.start(1000)
        o.me = o                            # (a cycle: only the collector frees it)
        weakref.finalize(o, lambda: gone.append(threading.get_ident()))
        del o
        workers = [threading.Thread(target=make_cycles, args=(100_000,)) for _ in range(4)]
        for t in workers:
            t.start()
        for t in workers:
            t.join()
        self.assertEqual(gone, [])          # (no worker freed it)
        spin(lambda: gone)
        self.assertEqual(gone, [self.main])
        self.assertFalse([m for m in warnings if "another thread" in m], warnings)

    def test_turned_back_on_it_is_turned_off_again(self):
        gc.enable()
        spin(lambda: not gc.isenabled(), 2.0)
        self.assertFalse(gc.isenabled())

    def test_a_pause_of_the_collector_leaves_it_off(self):
        from kanzonas import page_objects

        @page_objects._gc_paused
        def work():
            return gc.isenabled()
        self.assertFalse(work())
        self.assertFalse(gc.isenabled())


class WhatIsCollected(unittest.TestCase):
    """A tick collects what Python would have: the youngest generation past its threshold,
    the middle one every so many of those, the oldest only when enough was added to it."""

    def setUp(self):
        self.c = gc_main.install()
        self.ran = []
        patcher = mock.patch.object(gc_main.gc, "collect",
                                    side_effect=lambda g=2: self.ran.append(g) or 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tick(self, counts, threshold=(700, 10, 10)):
        with mock.patch.object(gc_main.gc, "get_count", return_value=counts), \
                mock.patch.object(gc_main.gc, "get_threshold", return_value=threshold):
            self.c.tick()

    def test_nothing_below_the_threshold(self):
        self.tick((500, 0, 0))
        self.assertEqual(self.ran, [])

    def test_the_youngest(self):
        self.tick((800, 3, 0))
        self.assertEqual(self.ran, [0])

    def test_the_middle(self):
        self.tick((800, 11, 3))
        self.assertEqual(self.ran, [1])

    def test_the_oldest_only_when_enough_was_added_to_it(self):
        self.c.long_lived, self.c.pending = 100_000, 1_000
        self.tick((800, 11, 11))
        self.assertEqual(self.ran, [1])     # (a quarter wasn't added: the middle one)
        self.c.pending = 30_000
        self.tick((800, 11, 11))
        self.assertEqual(self.ran, [1, 2])
        self.assertEqual(self.c.pending, 0)

    def test_collection_switched_off(self):
        self.tick((10 ** 6, 99, 99), threshold=(0, 10, 10))
        self.assertEqual(self.ran, [])


class ScanErrors(unittest.TestCase):
    """The scan's COM helper lets go of its objects without a collection on its thread: an
    error's tracebacks (and those of the errors it was raised while handling) are dropped."""

    def test_tracebacks_are_dropped_along_the_chain(self):
        from kanzonas import scan_local
        try:
            try:
                raise OSError("driver")
            except OSError:
                raise scan_local.ScanError("no scanner")
        except scan_local.ScanError as ex:
            err = ex
        self.assertIsNotNone(err.__traceback__)
        self.assertIsNotNone(err.__context__.__traceback__)
        scan_local._without_tracebacks(err)
        self.assertIsNone(err.__traceback__)
        self.assertIsNone(err.__context__.__traceback__)

    def test_no_collection_in_the_helper(self):
        import inspect
        from kanzonas import scan_local
        src = inspect.getsource(scan_local.com_call)
        self.assertNotIn("gc.collect()\n", src)


if __name__ == "__main__":
    unittest.main()

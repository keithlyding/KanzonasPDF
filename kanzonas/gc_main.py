"""Python's garbage collector runs only on the app's main thread, the one Qt's windows live on.

Python collects reference cycles in whichever thread happens to make an object when a
collection is due. A Qt object freed in a cycle is deleted right there, with the timers and
children it owns, so a collection in a worker thread (a scan, finding scanners, OCR, an
export) deleted windows that had been closed off their own thread: Qt warned "Timers cannot
be stopped from another thread" and the app could crash (the Scan window, 1.15.14).

So the automatic collector is switched off, and a timer on the main thread does its work.
Each generation is collected when Python would have collected it (Python's own thresholds),
and the oldest one only after the objects added to it since the last full pass come to a
quarter of what it held then (Python's rule for full passes, which keeps them rare in a long
session). install() is called at start-up (and by each window, for the self test and tests).
What a pause of the collector restores (page_objects._gc_paused, the theme change) is
"off", so nothing turns it back on; if something does, the next tick turns it off again."""
import gc
import threading

TICK_MS = 250               # how often the main thread looks whether a collection is due

_collector = None


class _Collector:
    def __init__(self, app):
        from PySide6.QtCore import QTimer
        self.thread = threading.get_ident()
        self.pending = 0                        # added to the oldest generation since a full pass
        self.long_lived = len(gc.get_objects(2))
        self.passes = [0, 0, 0]                 # (collections run here, per generation)
        self.timer = QTimer(app)                # (the application's: it lives on its thread)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.tick)
        gc.disable()
        self.timer.start()

    def tick(self):
        if gc.isenabled():
            gc.disable()
        if threading.get_ident() != self.thread:
            return
        t0, t1, t2 = gc.get_threshold()
        if t0 <= 0:
            return                              # (collection switched off: gc.set_threshold(0))
        c0, c1, c2 = gc.get_count()
        if c0 <= t0:
            return
        if c2 > t2 and self.pending >= self.long_lived // 4:
            self.full()
        elif c1 > t1:
            young = len(gc.get_objects(0)) + len(gc.get_objects(1))
            found = gc.collect(1)
            self.pending += max(0, young - found)   # (what's left moved to the oldest)
            self.passes[1] += 1
        else:
            gc.collect(0)
            self.passes[0] += 1

    def full(self):
        gc.collect(2)
        self.pending = 0
        self.long_lived = len(gc.get_objects(2))
        self.passes[2] += 1


def install():
    """Switches the automatic collector off and has the main thread collect instead. Called on
    the main thread once the QApplication exists; again, it does nothing."""
    global _collector
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance()
    if app is None or threading.current_thread() is not threading.main_thread():
        return None
    if _collector is not None and _collector.timer.parent() is app:
        if not _collector.timer.isActive():
            _collector.timer.start()
        gc.disable()
        return _collector
    _collector = _Collector(app)
    return _collector


def installed():
    """Whether the main thread collects (and the automatic collector is off)."""
    try:
        return (_collector is not None and _collector.timer.isActive()
                and not gc.isenabled())
    except RuntimeError:
        return False                            # (its timer went with an earlier QApplication)


def selftest_check():
    """For the self test: the collector is the main thread's, a worker thread making
    thousands of cycles runs no collection, and the main thread collects them."""
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    c = install()
    assert c is not None and installed(), "the main thread doesn't collect"
    where = []

    def seen(phase, info):
        if phase == "start":
            where.append(threading.get_ident())
    gc.callbacks.append(seen)
    try:
        class Cycle:
            pass

        def make():
            for _ in range(50_000):
                a = Cycle()
                a.me = a
        t = threading.Thread(target=make, name="kanzonas-gc-check")
        t.start()
        t.join()
        off_thread = [w for w in where if w != c.thread]
        assert not off_thread, "a collection ran in a worker thread"
        clock = QElapsedTimer()
        clock.start()
        while not where and clock.elapsed() < 5000:
            QCoreApplication.processEvents()
        assert where, "the main thread didn't collect"
        assert all(w == c.thread for w in where), "a collection ran in a worker thread"
    finally:
        gc.callbacks.remove(seen)
    return "(collected on the main thread)"

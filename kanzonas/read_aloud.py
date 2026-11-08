"""View > Read aloud: the system's own speech (Qt's QTextToSpeech: SAPI / Windows voices on
Windows, AVSpeechSynthesizer on macOS, Speech Dispatcher on Linux) reads the page, from the
selected text, or the whole document, a sentence at a time in reading order (reading_text).
The sentence being read is shaded on the page and the word being spoken (when the voice says
which) shaded darker; the page scrolls to follow.

QtTextToSpeech is imported only when reading starts (or when Preferences lists the voices):
nothing of it is loaded at start-up."""

import os
import re
import sys
import time

import shiboken6
from PySide6.QtCore import QObject, QTimer, Signal

from .i18n import tr

_engine_class = None        # tests put a stand-in for QTextToSpeech here


def tts_class():
    """QTextToSpeech, or None when this PySide6 has no QtTextToSpeech."""
    if _engine_class is not None:
        return _engine_class
    try:
        from PySide6.QtTextToSpeech import QTextToSpeech
    except ImportError:
        return None
    return QTextToSpeech


def engines():
    cls = tts_class()
    if cls is None:
        return []
    try:
        return [e for e in cls.availableEngines() if e != "mock"]
    except Exception:
        return []


# the system's own engines, the best first (never Qt's silent test engine, "mock", which is in
# the PySide6 wheel and the app's folder too)
PREFERRED = ("winrt", "sapi", "darwin", "speechd")


def pick_engine(names):
    """The engine to read with, of the engines names."""
    pick = [n for n in PREFERRED if n in names]
    return (pick or list(names) or [None])[0]


def platform_engines():
    """The engines the build must have on this system."""
    if sys.platform == "win32":
        return ("winrt", "sapi")
    if sys.platform == "darwin":
        return ("darwin",)
    return ("speechd",)


def no_speech_message():
    if sys.platform.startswith("linux"):
        return tr("No speech is available on this computer. Install Speech Dispatcher "
                  "(the speech-dispatcher package, with a voice such as espeak-ng) and try "
                  "again.")
    return tr("No speech is available on this computer: the system's text-to-speech "
              "couldn't be started.")


def rate_from(settings):
    """The speed set in Preferences, -10 (slow) to 10 (fast); 0 is the voice's normal."""
    from . import paths
    return paths.stored_int(settings, "read_rate", 0, -10, 10)


def voice_name(settings):
    from . import paths
    return paths.stored_str(settings, "read_voice", "")


class Reader(QObject):
    """Reads sentences of one document view aloud. stateChanged: speaking, paused or
    stopped."""
    stateChanged = Signal(str)
    message = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.engine = None
        self.view = None
        self.state = "stopped"
        self.queue = []             # sentences of the page being read still to say
        self.current = None         # the sentence being said
        self.next_page = None       # the page after the queue (None: stop after it)
        self.last_page = None
        self._word = None
        self._spoke = False         # the engine has begun saying the current sentence
        self._said_at = 0.0

    # ---- the speech engine --------------------------------------------------------
    def _make_engine(self):
        cls = tts_class()
        if cls is None:
            return None
        try:
            names = engines() if _engine_class is None else []
            if names:
                eng = cls(pick_engine(names), self)
            else:
                eng = cls(self)
        except Exception:
            return None
        if hasattr(cls, "State") and eng.state() == cls.State.Error:
            return None
        eng.stateChanged.connect(self._engine_state)
        if hasattr(eng, "sayingWord"):
            eng.sayingWord.connect(self._saying_word)
        return eng

    def apply_settings(self):
        """The voice and speed set in Preferences (again after they changed)."""
        eng = self.engine
        if eng is None:
            return
        try:
            eng.setRate(rate_from(self.settings) / 10.0)
            name = voice_name(self.settings)
            if name:
                for v in eng.availableVoices():
                    if v.name() == name:
                        eng.setVoice(v)
                        break
        except Exception:
            pass

    def _ready(self):
        if self.engine is None:
            if not engines() and _engine_class is None:
                self.message.emit(no_speech_message())
                return False
            self.engine = self._make_engine()
            if self.engine is None:
                self.message.emit(no_speech_message())
                return False
            self.apply_settings()
        return True

    # ---- reading ------------------------------------------------------------------
    def start(self, view, page, start=None, to_end=False):
        """Read page `page` of view (from the word nearest to start, a point on the page),
        and the pages after it when to_end."""
        self.stop()
        if view is None or not self._ready():
            return False
        self.view = view
        view.destroyed.connect(self._view_gone)
        self.last_page = view.page_count() - 1 if to_end else page
        self.queue = self._sentences(page, start)
        self.next_page = page + 1
        self._set_state("speaking")
        if not self.queue:
            self._skip_empty_pages(page)
        else:
            self._say_next()
        return True

    def _sentences(self, page, start=None):
        from . import reading_text
        try:
            return reading_text.sentences(self.view.reading_blocks(page), page, start)
        except Exception:
            return []

    def _skip_empty_pages(self, page):
        """Pages without text are passed over, one per turn of the event loop (a long
        scanned document doesn't freeze the window)."""
        if self.state != "speaking":
            return
        if self.next_page is None or self.next_page > self.last_page:
            if self.current is None:
                self.message.emit(tr("There's no text to read on this page. A scanned page "
                                     "needs Recognize text (OCR) first.") if
                                  page == self.last_page else tr("Finished reading."))
            self.stop()
            return
        p = self.next_page
        self.next_page = p + 1
        self.queue = self._sentences(p)
        if self.queue:
            self._say_next()
        else:
            QTimer.singleShot(0, lambda: self._skip_empty_pages(page))

    def _say_next(self):
        if self.state != "speaking" or self.engine is None:
            return
        if not self.queue:
            if self.next_page is not None and self.next_page <= self.last_page:
                self._skip_empty_pages(self.next_page - 1)
            else:
                self.stop()
                self.message.emit(tr("Finished reading."))
            return
        self.current = self.queue.pop(0)
        self._word = None
        self._spoke = False
        self._said_at = time.monotonic()
        self._mark()
        self.engine.say(self.current.text)

    def _engine_state(self, st):
        cls = type(self.engine) if self.engine is not None else None
        S = getattr(cls, "State", None)
        if S is None or self.state == "stopped":
            return
        if st == S.Speaking:
            self._spoke = True
        elif st == S.Ready and self.state == "speaking" and self.current is not None and (
                self._spoke or time.monotonic() - self._said_at > 0.5):
            # the sentence is said: the next one (after the event loop turns, so the engine
            # has finished its own work). (A Ready before this sentence was begun is the
            # engine's answer to an earlier stop: it doesn't end this one.)
            self.current = None
            QTimer.singleShot(0, self._say_next)
        elif st == S.Error:
            self.message.emit(tr("The speech stopped with an error."))
            self.stop()

    def _saying_word(self, word, _id=None, start=0, length=0):
        s = self.current
        if s is None:
            return
        w = s.word_at(start)
        if w is not None and w is not self._word:
            self._word = w
            self._mark()

    # ---- what's shown -------------------------------------------------------------
    def _mark(self):
        v = self.view
        if v is None or not shiboken6.isValid(v):
            return
        old = v.read_mark
        s = self.current
        new = None
        if s is not None:
            new = (s.page, s.rects(), list(self._word[2]) if self._word else [])
        v.read_mark = new
        for mark in (old, new):
            if mark is not None and mark[0] < len(v.pages):
                _repaint(v, mark)
        if new is not None:
            follow(v, new[0], (new[2] or new[1] or [None])[0])

    def pause(self):
        if self.state == "speaking" and self.engine is not None:
            self.engine.pause()
            self._set_state("paused")

    def resume(self):
        if self.state == "paused" and self.engine is not None:
            self._set_state("speaking")
            self.engine.resume()

    def toggle_pause(self):
        if self.state == "paused":
            self.resume()
        else:
            self.pause()

    def stop(self):
        was = self.state
        self.state = "stopped"
        self.queue = []
        self.current = None
        self._word = None
        if self.engine is not None and was != "stopped":
            try:
                self.engine.stop()
            except Exception:
                pass
        v = self.view
        if v is not None and shiboken6.isValid(v):
            try:
                v.destroyed.disconnect(self._view_gone)
            except (RuntimeError, TypeError):
                pass
            if v.read_mark is not None:
                old, v.read_mark = v.read_mark, None
                if old[0] < len(v.pages):
                    _repaint(v, old)
        self.view = None
        if was != "stopped":
            self.stateChanged.emit("stopped")

    def _view_gone(self, *_):
        self.view = None
        self.stop()

    def _set_state(self, st):
        if st != self.state:
            self.state = st
            self.stateChanged.emit(st)

    def say_sample(self):
        """Preferences: a sentence in the chosen voice and speed."""
        self.stop()
        if self._ready():
            self.apply_settings()
            self.engine.say(tr("This is how KanzonasPDF reads to you."))


def _repaint(view, mark):
    """Repaint where a read mark is (or was) on its page, not the whole page."""
    w = view.pages[mark[0]]
    if w.isHidden():
        return
    page = view.doc[mark[0]]
    for r in list(mark[1]) + list(mark[2]):
        w.update(w.to_screen(r, page).toAlignedRect().adjusted(-3, -3, 3, 3))


def follow(view, index, rect):
    """Scroll so rect (on page index) is in view, a third of the way down the window."""
    if rect is None or index >= len(view.pages):
        return
    view._show_index(index)
    w = view.pages[index]
    r = w.to_screen(rect)
    top = w.y() + r.y()
    vbar = view.verticalScrollBar()
    vh = view.viewport().height()
    if not (vbar.value() + 30 <= top <= vbar.value() + vh - r.height() - 40):
        vbar.setValue(int(top - vh / 3))
    left = w.x() + r.x()
    hbar = view.horizontalScrollBar()
    if not (hbar.value() <= left <= hbar.value() + view.viewport().width() - r.width()):
        hbar.setValue(int(left - 40))
    view._on_scroll()


# ---- the self-test ---------------------------------------------------------------------------
# the FFmpeg libraries, as each platform names them (packaging/trim_build.py takes them out)
FFMPEG = re.compile(r"^(lib)?(avcodec|avformat|avutil|avdevice|avfilter|swresample|swscale|"
                    r"postproc)([-.]\d+)*(\.dll|\.so(\.\d+)*|\.dylib)$", re.I)


def selftest_check():
    """Self-test "read aloud (speech)": the system's speech engine is in the build and starts
    (Windows: WinRT or SAPI, macOS: AVSpeechSynthesizer); on Linux Qt's Speech Dispatcher
    plugin is in it and loads, or fails for want of the computer's own libspeechd alone; and
    the audio output text-to-speech plays through works without Qt's multimedia backends."""
    from PySide6.QtCore import QLibraryInfo, QPluginLoader
    from PySide6.QtTextToSpeech import QTextToSpeech
    names = engines()
    have = [n for n in platform_engines() if n in names]
    assert have, "none of this system's speech engines (%s) in the build; found %s" % (
        ", ".join(platform_engines()), QTextToSpeech.availableEngines())
    notes = []
    if sys.platform.startswith("linux"):
        path = os.path.join(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath),
                            "texttospeech", "libqtexttospeech_speechd.so")
        assert os.path.isfile(path), "no Speech Dispatcher plugin at " + path
        loader = QPluginLoader(path)
        if loader.load():
            notes.append("speechd plugin loads")
        else:
            err = loader.errorString()
            # (everything else it needs is in the build; libspeechd comes with the
            # computer's speech-dispatcher, which Read aloud asks for when it's missing)
            assert "libspeechd" in err, err
            import ctypes
            try:
                ctypes.CDLL("libspeechd.so.2")
            except OSError:
                pass
            else:
                raise AssertionError("the computer has libspeechd, yet: " + err)
            notes.append("speechd plugin bundled; no libspeechd on this computer")
    else:
        name = pick_engine(names)
        eng = QTextToSpeech(name)
        assert eng.state() != QTextToSpeech.State.Error, "%s: %s" % (name, eng.errorString())
        notes.append("%s starts, %d voices" % (name, len(eng.availableVoices())))
        eng.deleteLater()
    # (WinRT's voices play through QAudioSink: part of the QtMultimedia library, not of the
    # backends the build leaves out)
    from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
    fmt = QAudioFormat()
    fmt.setSampleRate(22050)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    out = QMediaDevices.defaultAudioOutput()
    if out.isNull():
        notes.append("no sound device on this computer")
    else:
        sink = QAudioSink(out, fmt)
        assert sink.format().sampleRate() == 22050, "no audio output: %s" % sink.error()
        notes.append("plays through " + out.description())
        sink.deleteLater()
    return "(%s; %s)" % (", ".join(have), "; ".join(notes))


def build_media_check():
    """Self-test "no FFmpeg in the build": the built app holds no multimedia backend (Qt's
    media plugins and PySide6's FFmpeg, ~20-30 MB that nothing uses; packaging/trim_build.py).
    Outside a build there's nothing to check."""
    top = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or not top:
        return "(not a build)"
    found = []
    for d, dirs, files in os.walk(top):
        if "PySide6" not in d.replace(os.sep, "/").split("/"):
            continue
        if os.path.basename(d) == "plugins" and "multimedia" in dirs:
            found.append(os.path.join(d, "multimedia"))
        found += [os.path.join(d, n) for n in files if FFMPEG.match(n)]
    assert not found, "multimedia backends in the build: %s" % ", ".join(
        os.path.relpath(p, top) for p in found[:6])
    return ""

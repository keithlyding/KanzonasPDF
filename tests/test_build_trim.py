"""packaging/trim_build.py: what the built app never uses (Qt's multimedia backends and
PySide6's FFmpeg, which QtTextToSpeech's QtMultimedia brings along) leaves the Windows exe
folder, the Linux app folder and the macOS app, in each one's own layout; OpenCV's FFmpeg and
the text-to-speech plugins stay; every build job runs it right after PyInstaller; and the
self-test's "no FFmpeg in the build" finds what's left.

    python -m unittest tests.test_build_trim
"""
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packaging"))

import trim_build  # noqa: E402

WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-windows.yml")

# each platform's PyInstaller layout (a trailing "->" is a link to the path after it)
LAYOUTS = {
    "windows": [
        "KanzonasPDF.exe",
        "_internal/PySide6/avcodec-61.dll", "_internal/PySide6/avformat-61.dll",
        "_internal/PySide6/avutil-59.dll", "_internal/PySide6/swresample-5.dll",
        "_internal/PySide6/swscale-8.dll",
        "_internal/PySide6/Qt6Multimedia.dll", "_internal/PySide6/Qt6TextToSpeech.dll",
        "_internal/PySide6/plugins/multimedia/ffmpegmediaplugin.dll",
        "_internal/PySide6/plugins/multimedia/windowsmediaplugin.dll",
        "_internal/PySide6/plugins/texttospeech/qtexttospeech_sapi.dll",
        "_internal/PySide6/plugins/texttospeech/qtexttospeech_winrt.dll",
        "_internal/cv2/opencv_videoio_ffmpeg4110_64.dll",
    ],
    "linux": [
        "KanzonasPDF",
        "_internal/PySide6/Qt/lib/libavcodec.so.63", "_internal/PySide6/Qt/lib/libswscale.so.10",
        "_internal/PySide6/Qt/lib/libQt6Multimedia.so.6",
        "_internal/PySide6/Qt/plugins/multimedia/libffmpegmediaplugin.so",
        "_internal/PySide6/Qt/plugins/texttospeech/libqtexttospeech_speechd.so",
        "_internal/libavcodec.so.63 -> PySide6/Qt/lib/libavcodec.so.63",
        "_internal/libQt6Multimedia.so.6 -> PySide6/Qt/lib/libQt6Multimedia.so.6",
        "_internal/opencv_python_headless.libs/libavcodec-c4204469.so.62.28.101",
    ],
    "macos": [
        "Contents/MacOS/KanzonasPDF",
        "Contents/Frameworks/PySide6/Qt/lib/libavcodec.62.dylib",
        "Contents/Frameworks/PySide6/Qt/lib/QtMultimedia.framework/QtMultimedia",
        "Contents/Frameworks/PySide6/Qt/plugins/multimedia/libffmpegmediaplugin.dylib",
        "Contents/Frameworks/PySide6/Qt/plugins/multimedia/libdarwinmediaplugin.dylib",
        "Contents/Frameworks/PySide6/Qt/plugins/texttospeech/libqtexttospeech_darwin.dylib",
        "Contents/Frameworks/libavcodec.62.dylib -> PySide6/Qt/lib/libavcodec.62.dylib",
        "Contents/Resources/PySide6/Qt/plugins/multimedia -> "
        "../../../../Frameworks/PySide6/Qt/plugins/multimedia",
        "Contents/Frameworks/cv2/.dylibs/libavcodec.61.19.100.dylib",
    ],
}
GONE = {
    "windows": ["_internal/PySide6/avcodec-61.dll", "_internal/PySide6/avformat-61.dll",
                "_internal/PySide6/avutil-59.dll", "_internal/PySide6/swresample-5.dll",
                "_internal/PySide6/swscale-8.dll", "_internal/PySide6/plugins/multimedia"],
    "linux": ["_internal/PySide6/Qt/lib/libavcodec.so.63",
              "_internal/PySide6/Qt/lib/libswscale.so.10",
              "_internal/PySide6/Qt/plugins/multimedia", "_internal/libavcodec.so.63"],
    "macos": ["Contents/Frameworks/PySide6/Qt/lib/libavcodec.62.dylib",
              "Contents/Frameworks/PySide6/Qt/plugins/multimedia",
              "Contents/Frameworks/libavcodec.62.dylib",
              "Contents/Resources/PySide6/Qt/plugins/multimedia"],
}


def make(top, entries):
    for e in entries:
        path, _, target = e.partition(" -> ")
        full = os.path.join(top, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if target:
            os.symlink(target, full)
        else:
            with open(full, "wb") as f:
                f.write(b"x" * 1000)


def listed(top):
    out = set()
    for d, dirs, files in os.walk(top):
        for n in files + dirs:
            out.add(os.path.relpath(os.path.join(d, n), top).replace(os.sep, "/"))
    return out


@unittest.skipIf(sys.platform == "win32", "makes symbolic links")
class Trim(unittest.TestCase):
    def check(self, kind):
        top = tempfile.mkdtemp(prefix="kz-trim-")
        make(top, LAYOUTS[kind])
        before = listed(top)
        freed = trim_build.trim(top, log=lambda *_: None)
        after = listed(top)
        for p in GONE[kind]:
            self.assertIn(p, before)
            self.assertNotIn(p, after)
        kept = {e.partition(" -> ")[0] for e in LAYOUTS[kind]} - set(GONE[kind])
        kept -= {p for p in kept if p.startswith(tuple(g + "/" for g in GONE[kind]))}
        for p in kept:
            self.assertIn(p, after)             # (OpenCV's FFmpeg, speech, QtMultimedia)
        self.assertGreater(freed, 0)
        self.assertFalse(trim_build.dangling(top))
        return top

    def test_windows(self):
        self.check("windows")

    def test_linux(self):
        self.check("linux")

    def test_macos_app(self):
        self.check("macos")

    def test_the_speech_plugins_must_be_there(self):
        top = tempfile.mkdtemp(prefix="kz-trim-")
        make(top, [e for e in LAYOUTS["linux"] if "texttospeech" not in e])
        with self.assertRaises(SystemExit):
            trim_build.trim(top, log=lambda *_: None)

    def test_not_a_build(self):
        with self.assertRaises(SystemExit):
            trim_build.trim(tempfile.mkdtemp(), log=lambda *_: None)

    def test_the_self_test_finds_what_is_left(self):
        from kanzonas import read_aloud
        for kind in ("linux", "macos"):
            top = tempfile.mkdtemp(prefix="kz-trim-")
            make(top, LAYOUTS[kind])
            internal = os.path.join(top, "_internal" if kind == "linux" else
                                    "Contents/Frameworks")
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "_MEIPASS", internal, create=True):
                with self.assertRaises(AssertionError):
                    read_aloud.build_media_check()
                trim_build.trim(top, log=lambda *_: None)
                self.assertEqual(read_aloud.build_media_check(), "")
        self.assertEqual(read_aloud.build_media_check(), "(not a build)")


class Workflow(unittest.TestCase):
    def test_every_build_job_trims_right_after_pyinstaller(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            text = f.read()
        jobs = re.split(r"\n  (?=[a-z]+:\n)", text)
        found = {}
        for job in jobs:
            name = job.split(":", 1)[0].strip()
            steps = job.split("\n      - ")
            for i, step in enumerate(steps):
                if "python -m PyInstaller" in step:
                    found[name] = steps[i + 1]
        self.assertEqual(set(found), {"build", "linux", "macos"})
        self.assertIn(r"packaging/trim_build.py dist\KanzonasPDF", found["build"])
        self.assertIn("packaging/trim_build.py dist/KanzonasPDF\n", found["linux"])
        self.assertIn("packaging/trim_build.py dist/KanzonasPDF.app", found["macos"])

    def test_the_patterns_agree(self):
        from kanzonas import read_aloud
        self.assertEqual(read_aloud.FFMPEG.pattern, trim_build.FFMPEG.pattern)
        for name in ("avcodec-61.dll", "libavcodec.so.63", "libavcodec.62.dylib",
                     "swscale-8.dll", "libswresample.so.7"):
            self.assertTrue(trim_build.FFMPEG.match(name), name)
        for name in ("libavif.so.16", "Qt6Multimedia.dll", "libavahi-client.so.3",
                     "opencv_videoio_ffmpeg4110_64.dll"):
            self.assertFalse(trim_build.FFMPEG.match(name), name)


if __name__ == "__main__":
    unittest.main()

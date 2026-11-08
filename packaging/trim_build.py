"""Takes out of the PyInstaller build what KanzonasPDF never uses, before it is packed (each job
of .github/workflows/build-windows.yml runs it right after PyInstaller: the Windows exe folder,
the Linux AppImage's app folder, the macOS app).

    python packaging/trim_build.py dist/KanzonasPDF          (Windows, Linux)
    python packaging/trim_build.py dist/KanzonasPDF.app      (macOS)

What goes: Qt's multimedia backends (the FFmpeg plugin, and Windows' and the Mac's own media
plugins) and the FFmpeg libraries PySide6 ships for them, about 20-30 MB on each platform.
View > Read aloud needs QtTextToSpeech, which needs the QtMultimedia library itself (its audio
formats, and the audio output the WinRT voices play through: built into that library, not a
plugin), so PyInstaller brings the media plugins along; nothing in the app plays or records
video or sound files. Without a backend Qt says "No QtMultimedia backends found" once and keeps
QMediaDevices, QAudioSink and QSoundEffect working, which is all text-to-speech uses. The
self-test checks "read aloud (speech)" (the system's engine starts in the built app) and "no
FFmpeg in the build".

Only PySide6's own copies go: OpenCV's FFmpeg (opencv_python*.libs, used by OCR) stays. Links
left pointing at nothing (PyInstaller's links to the libraries on Linux and macOS) go too.
Exits with 1 when the folder isn't a PyInstaller build, or the text-to-speech plugins aren't in
it (they must be, for Read aloud).
"""
import os
import re
import shutil
import sys

# under PySide6's folder: Qt plugin folders that go entirely
PLUGIN_DIRS = ("multimedia",)
# the FFmpeg libraries, as each platform names them: avcodec-61.dll (Windows),
# libavcodec.so.61 (Linux), libavcodec.61.dylib (macOS)
FFMPEG = re.compile(r"^(lib)?(avcodec|avformat|avutil|avdevice|avfilter|swresample|swscale|"
                    r"postproc)([-.]\d+)*(\.dll|\.so(\.\d+)*|\.dylib)$", re.I)
# what text-to-speech needs, which must still be there
SPEECH_PLUGINS = "texttospeech"


def _is_pyside(path, top):
    rel = os.path.relpath(path, top).replace(os.sep, "/").split("/")
    return "PySide6" in rel


def unused(top):
    """[(path, is a folder)] of what goes, inside top."""
    out = []
    for d, dirs, files in os.walk(top):
        if os.path.basename(d) == "plugins" and _is_pyside(d, top):
            for name in [n for n in dirs if n in PLUGIN_DIRS]:
                out.append((os.path.join(d, name), True))
                dirs.remove(name)
        # (a link to a folder is listed with the folders)
        for name in files + [n for n in dirs if os.path.islink(os.path.join(d, n))]:
            p = os.path.join(d, name)
            if FFMPEG.match(name) and _is_pyside(p, top):
                out.append((p, False))
    return out


def dangling(top):
    """Links inside top that point at nothing."""
    out = []
    for d, dirs, files in os.walk(top):
        for name in files + dirs:
            p = os.path.join(d, name)
            if os.path.islink(p) and not os.path.exists(p):
                out.append(p)
    return out


def size(path):
    if os.path.islink(path):
        return 0
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for d, _dirs, files in os.walk(path):
        for n in files:
            p = os.path.join(d, n)
            if not os.path.islink(p):
                total += os.path.getsize(p)
    return total


def speech_plugins(top):
    """The text-to-speech plugin files in the build."""
    found = []
    for d, _dirs, files in os.walk(top):
        if os.path.basename(d) == SPEECH_PLUGINS:
            found += [os.path.join(d, n) for n in files if not os.path.islink(os.path.join(d, n))]
    return found


def trim(top, log=print):
    """Removes what goes; returns the bytes freed."""
    if not os.path.isdir(top):
        raise SystemExit("ERROR: %s isn't a folder" % top)
    if not any("PySide6" in dirs for _d, dirs, _f in os.walk(top)):
        raise SystemExit("ERROR: no PySide6 in %s: not a PyInstaller build of KanzonasPDF" % top)
    freed = 0
    for p, is_dir in unused(top):
        n = size(p)
        freed += n
        log("  removed %s (%.1f MB)" % (os.path.relpath(p, top), n / 1e6))
        if is_dir and not os.path.islink(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
    # (twice: a link to a link)
    for _ in range(2):
        for p in dangling(top):
            os.remove(p)
    if not speech_plugins(top):
        raise SystemExit("ERROR: no text-to-speech plugins in %s (View > Read aloud needs "
                         "them)" % top)
    log("%s: %.1f MB of multimedia backends taken out" % (top, freed / 1e6))
    return freed


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    trim(argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())

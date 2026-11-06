"""File > Scan through the computer's own scanner drivers, and watching a folder.

- Windows: WIA (Windows Image Acquisition), through its scripting objects (WIA.DeviceManager)
  over COM with comtypes (imported only here, only on Windows), so USB scanners, vendor WIA
  drivers and the network scanners Windows has already added all work.
- Linux: SANE, through the `scanimage` command when it's installed (the sane-utils package).
- macOS: neither yet (eSCL and WSD work there).
- Any system: a folder a printer scans into (Scan to Network Folder, FTP, a USB stick copied
  over): new PDFs and pictures that appear in it are taken as scanned pages.

scanimage runs with fixed arguments (no shell); the files WIA and scanimage write are checked
like anything from the network (scan_net.check_image).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading

from . import scan_net as net
from .i18n import tr
from .scan_net import Caps, Device, ScanError, SourceCaps

LIST_TIMEOUT = 25           # seconds to list the scanners
WATCH_EXTS = (".pdf", ".jpg", ".jpeg", ".tif", ".tiff", ".png")
MAX_WATCHED_FILE = net.MAX_IMAGE


def _popen_kw(**over):
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    kw.update(over)
    if sys.platform == "win32":
        kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW: no console flashes up
    return kw


def run(cmd, timeout):
    """(exit code, stdout, stderr) of a command (UTF-8 text)."""
    try:
        p = subprocess.run(cmd, timeout=timeout, **_popen_kw())
    except FileNotFoundError:
        raise ScanError(tr("{program} isn't installed.").format(program=cmd[0]))
    except subprocess.TimeoutExpired:
        raise ScanError(tr("{program} didn't answer in time.").format(
            program=os.path.basename(cmd[0])))
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8",
                                                                              "replace")


class _Proc:
    """A running command whose output is read line by line; kill() stops it (Cancel), and it is
    stopped when nothing comes for `quiet` seconds."""

    def __init__(self, cmd, quiet, **streams):
        try:
            self.p = subprocess.Popen(cmd, **_popen_kw(**streams))
        except FileNotFoundError:
            raise ScanError(tr("{program} isn't installed.").format(program=cmd[0]))
        self.quiet = quiet
        self.timed_out = False
        self._timer = None
        self._arm()

    def _arm(self):
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(self.quiet, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def _expire(self):
        self.timed_out = True
        self.kill()

    def kill(self):
        try:
            self.p.kill()
        except OSError:
            pass

    def lines(self, stream):
        for raw in iter(stream.readline, b""):
            self._arm()
            yield raw.decode("utf-8", "replace").rstrip("\r\n")

    def finish(self):
        if self._timer:
            self._timer.cancel()
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.kill()
        return self.p.returncode


def _read_page(path, dpi):
    try:
        if os.path.getsize(path) > net.MAX_IMAGE:
            raise ScanError(tr("A scanned page was too large ({mb} MB).").format(
                mb=os.path.getsize(path) // (1024 * 1024)))
        with open(path, "rb") as f:
            data = f.read()
    except OSError as ex:
        raise ScanError(tr("Couldn't read the scanned page."), str(ex))
    return net.check_image(data, dpi)


# ---- Windows: WIA ---------------------------------------------------------------------------
# WIA's scripting objects (WIA.DeviceManager, the ones VBScript and PowerShell use) through COM
# with comtypes, late-bound (IDispatch: nothing is generated or written to disk). COM is set up
# per thread: each call below starts and ends it in the worker thread it runs in, and lets go
# of every WIA object before ending it.
WIA_FORMATS = {"jpeg": "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}",
               "png": "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}",
               "bmp": "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"}
WIA_INTENT = {"color": 1, "gray": 2, "bw": 4}      # WIA_IPS_CUR_INTENT
WIA_DATATYPE = {"color": 3, "gray": 2, "bw": 0}    # WIA_IPA_DATATYPE
WIA_HANDLING = {"platen": 2, "feeder": 1, "duplex": 5}     # WIA_DPS_DOCUMENT_HANDLING_SELECT
WIA_PAPER_EMPTY = "80210003"
WIA_ERRORS = {
    "80210003": "empty", "80210002": "jam", "80210004": "jam", "80210016": "open",
    "80210005": "offline", "8021000A": "offline", "80210015": "offline", "80210006": "busy",
    "80210007": "warming", "80210008": "attention",
}
SCANNER_DEVICE = 1                                 # WiaDeviceType.ScannerDeviceType
P_HANDLING_CAPS, P_HANDLING, P_PAGES = 3086, 3088, 3096
P_INTENT, P_DATATYPE, P_XRES, P_YRES = 6146, 4103, 6147, 6148
P_XPOS, P_YPOS, P_WIDTH, P_HEIGHT = 6149, 6150, 6151, 6152


def _comtypes():
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        raise ScanError(tr("Scanning through Windows (WIA) needs the comtypes package, which "
                           "is missing from this copy of KanzonasPDF."))
    return comtypes


def hresult(ex):
    """A COM error's code as 8 hex digits ("80210003"), or ""."""
    args = getattr(ex, "hresult", None), *getattr(ex, "args", ())
    for a in args:
        if isinstance(a, int):
            return "%08X" % (a & 0xFFFFFFFF)
    return ""


def com_call(fn):
    """fn(comtypes) with COM set up in this thread; COM errors become ScanErrors. Every WIA
    object is let go of (and an error's traceback with them) before COM is shut down."""
    ct = _comtypes()
    ct.CoInitializeEx(ct.COINIT_APARTMENTTHREADED)
    result, err = None, None
    try:
        result = fn(ct)
    except ScanError as ex:
        err = ex.with_traceback(None)
    except Exception as ex:                 # COMError, or a WIA object missing a member
        code = hresult(ex)
        text = (getattr(ex, "text", None) or (ex.args[1] if len(ex.args) > 1 else "") or
                str(ex))
        err = ScanError(wia_message(code, text), "WIA %s: %s" % (code, text))
    finally:
        import gc
        gc.collect()
        ct.CoUninitialize()
    if err is not None:
        raise err
    return result


def _manager(ct):
    return ct.client.CreateObject("WIA.DeviceManager", dynamic=True)


def _items(collection):
    return [collection.Item(i) for i in range(1, int(collection.Count) + 1)]


def _prop(props, pid):
    return next((p for p in _items(props) if int(p.PropertyID) == pid), None)


def _set(props, pid, value):
    """Set a WIA property; a value the driver refuses is left as the driver has it."""
    p = _prop(props, pid)
    if p is not None:
        try:
            p.Value = value
        except Exception:
            pass


def _connect(ct, device_id):
    for info in _items(_manager(ct).DeviceInfos):
        if str(info.DeviceID) == device_id:
            return info.Connect()
    raise ScanError(wia_message("NOTFOUND", ""), "WIA device %s not listed" % device_id)


def wia_devices(log=None):
    def find(ct):
        out = []
        for info in _items(_manager(ct).DeviceInfos):
            if int(info.Type) != SCANNER_DEVICE:
                continue
            name = ""
            try:
                name = str(info.Properties.Item("Name").Value)
            except Exception:
                pass
            out.append(Device(name or tr("Scanner"), "wia", str(info.DeviceID)))
        return out
    try:
        devices = com_call(find)
    except ScanError as ex:
        if log is not None:
            log.append("WIA: %s" % (ex.details or ex.message))
        return []
    if log is not None:
        log.append("WIA: %d scanner(s)" % len(devices))
    return devices


def wia_message(code, message, pages=0):
    k = WIA_ERRORS.get(code)
    if k == "empty":
        return tr("The document feeder is empty: put the pages in it, or choose the flatbed "
                  "(glass).")
    if k == "jam":
        return tr("Paper is jammed in the document feeder: clear it (see the printer's panel) "
                  "and try again.")
    if k == "open":
        return tr("A cover of the scanner is open: close it and try again.")
    if k == "offline":
        return tr("The scanner is off or not connected: turn it on, check its cable or "
                  "network, and try again.")
    if k in ("busy", "warming"):
        return tr("The scanner is busy or warming up: wait a moment and try again.")
    if k == "attention":
        return tr("The scanner needs attention: check the message on its panel.")
    if code == "NOTFOUND":
        return tr("Windows no longer lists this scanner: click Refresh.")
    return tr("Windows couldn't scan ({code}): {message}").format(code=code or "?",
                                                                 message=message)


class WiaScanner:
    protocol = "wia"

    def __init__(self, device):
        self.device = device
        self.trail = []
        self.canceled = False

    def capabilities(self):
        """What the driver says: feeder and duplex (WIA_DPS_DOCUMENT_HANDLING_CAPABILITIES)
        and the resolutions; values every scanner takes when it says nothing."""
        def ask(ct):
            dev = _connect(ct, self.device.address)
            p = _prop(dev.Properties, P_HANDLING_CAPS)
            handling = int(p.Value) if p is not None else 0
            dpis = []
            x = _prop(dev.Items.Item(1).Properties, P_XRES)
            if x is not None:
                kind = int(x.SubType)
                if kind == 2:                       # a list
                    dpis = [int(v) for v in _items(x.SubTypeValues)]
                elif kind == 1:                     # a range
                    lo, hi = int(x.SubTypeMin), int(x.SubTypeMax)
                    dpis = [v for v in net.COMMON_DPI if lo <= v <= hi]
            return handling, dpis
        handling, dpis = com_call(ask)
        self.trail.append("WIA capabilities: handling %s, resolutions %s" % (handling, dpis))
        src = SourceCaps(resolutions=sorted(v for v in dpis if 0 < v <= 4800) or
                         [75, 100, 150, 200, 300, 600])
        sources = {}
        if handling & 2 or not handling & 1:
            sources["platen"] = src
        if handling & 1:
            sources["feeder"] = src
        if handling & 1 and handling & 4:
            sources["duplex"] = src
        return Caps(sources, self.device.name,
                    "WIA document handling %s, resolutions %s" % (handling, dpis))

    def abort(self):
        # (a page the driver is transferring can't be interrupted: the scan stops after it)
        self.canceled = True

    def _transfer(self, ct, settings, folder, report):
        w_in, h_in = net.region(settings, SourceCaps(max_w=8.5, max_h=14.0))
        dpi = int(settings.dpi)
        dev = _connect(ct, self.device.address)
        _set(dev.Properties, P_HANDLING, WIA_HANDLING[settings.source])
        _set(dev.Properties, P_PAGES, 1 if settings.source == "platen" else 0)
        item = dev.Items.Item(1)
        for pid, value in ((P_INTENT, WIA_INTENT[settings.color]),
                           (P_DATATYPE, WIA_DATATYPE[settings.color]), (P_XRES, dpi),
                           (P_YRES, dpi), (P_XPOS, 0), (P_YPOS, 0),
                           (P_WIDTH, round(w_in * dpi)), (P_HEIGHT, round(h_in * dpi))):
            _set(item.Properties, pid, value)
        fmt = WIA_FORMATS["png" if settings.color == "bw" else "jpeg"]
        paths = []
        while len(paths) < net.MAX_PAGES and not self.canceled:
            report(tr("Scanning page {n}...").format(n=len(paths) + 1))
            try:
                img = item.Transfer(fmt)
            except Exception as ex:
                code = hresult(ex)
                if paths and code == WIA_PAPER_EMPTY:
                    break                           # (the feeder is done)
                if paths or code == WIA_PAPER_EMPTY:
                    raise
                img = item.Transfer()               # (a driver without that format)
            path = os.path.join(folder, "page%04d.%s" % (len(paths) + 1,
                                                         str(img.FileExtension or "bmp")))
            img.SaveFile(path)
            img = None
            paths.append(path)
            if settings.source == "platen":
                break
        return paths

    def scan(self, settings, report=lambda _t: None):
        self.canceled = False
        folder = tempfile.mkdtemp(prefix="kanzonas-scan-")
        try:
            report(tr("Starting the scan..."))
            paths = com_call(lambda ct: self._transfer(ct, settings, folder, report))
            if self.canceled and not paths:
                raise net.Canceled()
            if not paths:
                raise ScanError(tr("The scanner finished without sending a page."))
            for path in paths:
                yield _read_page(path, settings.dpi)
            if self.canceled:
                raise net.Canceled()
        finally:
            shutil.rmtree(folder, ignore_errors=True)


# ---- Linux: SANE ----------------------------------------------------------------------------
def scanimage():
    return shutil.which("scanimage")


def sane_devices(log=None):
    exe = scanimage()
    if not exe:
        if log is not None:
            log.append("SANE: scanimage isn't installed")
        return []
    code, out, err = run([exe, "-f", "%d\t%v\t%m\t%t%n"], LIST_TIMEOUT)
    devices = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0]:
            name = " ".join(p for p in parts[1:3] if p) or parts[0]
            devices.append(Device(name, "sane", parts[0]))
    if log is not None:
        log.append("SANE: %d scanner(s)%s" % (len(devices), "" if code == 0 else
                                              " (exit %s: %s)" % (code, err.strip()[:200])))
    return devices


SANE_COLORS = {"color": "color", "gray": "gray", "grayscale": "gray", "lineart": "bw",
               "binary": "bw", "black & white": "bw", "black and white": "bw", "halftone": "bw"}


def sane_source_kind(name):
    n = name.lower()
    if "duplex" in n:
        return "duplex"
    if "adf" in n or "feeder" in n:
        return "feeder"
    if "flatbed" in n or "platen" in n or "normal" in n or "glass" in n:
        return "platen"
    return None


def parse_sane_options(text):
    """{"sources": {kind: name}, "modes": {color: name}, "resolutions": [...], "x": mm, "y":
    mm} from `scanimage -A`."""
    out = {"sources": {}, "modes": {}, "resolutions": [], "x": None, "y": None}

    def values(line):
        m = re.match(r"\s*--?[\w-]+\s+(.*?)\s*(\[.*\])?\s*$", line)
        return m.group(1) if m else ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("--source "):
            for v in values(line).split("|"):
                k = sane_source_kind(v)
                if k and k not in out["sources"]:
                    out["sources"][k] = v.strip()
        elif s.startswith("--mode "):
            for v in values(line).split("|"):
                c = SANE_COLORS.get(v.strip().lower())
                if c and c not in out["modes"]:
                    out["modes"][c] = v.strip()
        elif s.startswith("--resolution "):
            v = values(line).replace("dpi", "")
            rng = re.match(r"\s*(\d+)\.\.(\d+)", v)
            if rng:
                lo, hi = int(rng.group(1)), int(rng.group(2))
                out["resolutions"] = [r for r in net.COMMON_DPI if lo <= r <= hi]
            else:
                out["resolutions"] = sorted(int(x) for x in re.findall(r"\d+", v.split("(")[0]))
        elif re.match(r"-[xy] ", s):
            m = re.match(r"-([xy])\s+[\d.]+\.\.([\d.]+)mm", s)
            if m:
                out[m.group(1)] = float(m.group(2))
    return out


class SaneScanner:
    protocol = "sane"

    def __init__(self, device):
        self.device = device
        self.proc = None
        self.opts = None
        self.trail = []
        self.canceled = False

    def capabilities(self):
        exe = scanimage()
        if not exe:
            raise ScanError(tr("scanimage isn't installed (the sane-utils package)."))
        code, out, err = run([exe, "-d", self.device.address, "-A"], LIST_TIMEOUT)
        self.opts = parse_sane_options(out)
        self.trail.append("scanimage -A (exit %s): %s" % (code, (out + err)[:4000]))
        src = SourceCaps(colors=[c for c in ("color", "gray", "bw") if c in self.opts["modes"]]
                         or ["color"], resolutions=self.opts["resolutions"] or [300])
        if self.opts["x"]:
            src.max_w = self.opts["x"] / 25.4
        if self.opts["y"]:
            src.max_h = self.opts["y"] / 25.4
        kinds = list(self.opts["sources"]) or ["platen"]
        return Caps({k: src for k in ("platen", "feeder", "duplex") if k in kinds},
                    self.device.name, out[:20000])

    def abort(self):
        self.canceled = True
        if self.proc:
            self.proc.kill()

    def command(self, settings, folder):
        if self.opts is None:
            self.capabilities()
        o = self.opts
        dpi = net.nearest(o["resolutions"] or [settings.dpi], settings.dpi)
        cmd = [scanimage() or "scanimage", "-d", self.device.address, "--format=png",
               "--resolution", str(dpi)]
        if settings.color in o["modes"]:
            cmd += ["--mode", o["modes"][settings.color]]
        if settings.source in o["sources"]:
            cmd += ["--source", o["sources"][settings.source]]
        w_in, h_in = net.region(settings, SourceCaps(max_w=(o["x"] or 1e9) / 25.4,
                                                     max_h=(o["y"] or 1e9) / 25.4))
        if o["x"]:
            cmd += ["-x", "%.1f" % (w_in * 25.4)]
        if o["y"]:
            cmd += ["-y", "%.1f" % (h_in * 25.4)]
        cmd += ["--batch=" + os.path.join(folder, "page%04d.png")]
        if settings.source == "platen":
            cmd += ["--batch-count=1"]
        return cmd, dpi

    def scan(self, settings, report=lambda _t: None):
        self.canceled = False
        folder = tempfile.mkdtemp(prefix="kanzonas-scan-")
        try:
            cmd, dpi = self.command(settings, folder)
            report(tr("Starting the scan..."))
            self.proc = _Proc(cmd, net.PAGE_TIMEOUT, stdout=subprocess.DEVNULL)
            done, said = 0, []
            for line in self.proc.lines(self.proc.p.stderr):
                said.append(line)
                m = re.search(r"Scanned page (\d+)", line)
                if m:
                    path = os.path.join(folder, "page%04d.png" % int(m.group(1)))
                    if os.path.isfile(path):
                        done += 1
                        yield _read_page(path, dpi)
                        report(tr("Scanning page {n}...").format(n=done + 1))
            code = self.proc.finish()
            if self.canceled:
                raise net.Canceled()
            for name in sorted(os.listdir(folder))[done:]:
                if name.endswith(".png"):
                    done += 1
                    yield _read_page(os.path.join(folder, name), dpi)
            text = "\n".join(said[-20:])
            if not done:
                raise ScanError(sane_message(text), "scanimage exit %s: %s" % (code, text))
        finally:
            if self.proc:
                self.proc.kill()
            shutil.rmtree(folder, ignore_errors=True)


def sane_message(text):
    t = text.lower()
    if "out of documents" in t or "no more documents" in t:
        return tr("The document feeder is empty: put the pages in it, or choose the flatbed "
                  "(glass).")
    if "jam" in t:
        return tr("Paper is jammed in the document feeder: clear it (see the printer's panel) "
                  "and try again.")
    if "cover" in t and "open" in t:
        return tr("A cover of the scanner is open: close it and try again.")
    if "busy" in t:
        return tr("The scanner is busy or warming up: wait a moment and try again.")
    return tr("The scanner finished without sending a page.")


# ---- a folder the printer scans into ------------------------------------------------------
WATCH_GIVE_UP = 60.0        # seconds a file that looks unfinished is waited for


def _tail(path, n):
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - n))
        return f.read()


def looks_complete(path):
    """False when a file that arrived is visibly unfinished (the printer or the FTP upload
    is still writing it, or stopped): a JPEG without its end marker, a PNG without its last
    chunk, a PDF without %%EOF near its end. True when it can't be told (TIFF)."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
        tail = _tail(path, 2048)
    except OSError:
        return True                 # (read_watched says what's wrong)
    return _complete(head, tail)


def _complete(head, tail):
    kind = net.image_kind(head)
    if kind == "jpeg":
        return tail.rstrip(b"\0\r\n ").endswith(b"\xff\xd9")
    if kind == "png":
        return tail.endswith(b"IEND\xaeB`\x82")
    if kind == "pdf":
        return b"%%EOF" in tail
    return True


class FolderWatch:
    """New PDFs and pictures in a folder. Files already there when watching starts are left
    alone; a new file is taken once its size and time have stayed the same between two
    looks and it doesn't look unfinished (the printer may still be writing it, an FTP
    upload may pause), or once it hasn't changed for WATCH_GIVE_UP seconds (read_watched
    then says it's incomplete). Links to other files, and anything that isn't a plain file,
    are left alone (a share others write into could link to a file of this computer)."""

    def __init__(self, folder, clock=None):
        import time
        self.folder = folder
        self.clock = clock or time.monotonic
        self.known = set(self._names())
        self.sizes = {}             # name -> ((size, time), when that was first seen)

    def _names(self):
        try:
            with os.scandir(self.folder) as it:
                return [e.name for _i, e in zip(range(20000), it)
                        if e.is_file(follow_symlinks=False) and not e.is_symlink()
                        and os.path.splitext(e.name)[1].lower() in WATCH_EXTS]
        except OSError:
            return []

    def poll(self):
        """Paths of the files that have arrived complete since the last look."""
        ready = []
        now = self.clock()
        for name in self._names():
            if name in self.known:
                continue
            path = os.path.join(self.folder, name)
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError:
                continue
            stamp = (st.st_size, st.st_mtime_ns)
            seen = self.sizes.get(name)
            if st.st_size > 0 and seen is not None and seen[0] == stamp and (
                    looks_complete(path) or now - seen[1] >= WATCH_GIVE_UP):
                self.known.add(name)
                self.sizes.pop(name, None)
                ready.append(path)
            elif seen is None or seen[0] != stamp:
                self.sizes[name] = (stamp, now)
        return sorted(ready)


def _read_plain_file(path, limit):
    """The bytes of path, a plain file (not a link, a pipe or a device: opening a pipe would
    wait for a writer forever), of at most limit bytes."""
    import stat
    name = os.path.basename(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | \
        getattr(os, "O_NONBLOCK", 0)
    try:
        if os.path.islink(path):
            raise ScanError(tr("{name} is a link to another file: it's left alone.").format(
                name=name))
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode):
                raise ScanError(tr("{name} isn't a file.").format(name=name))
            if st.st_size > limit:
                raise ScanError(tr("{name} is too large.").format(name=name))
            data = f.read(limit + 1)
    except OSError as ex:
        raise ScanError(tr("Couldn't read {name}.").format(name=name), str(ex))
    if len(data) > limit:
        raise ScanError(tr("{name} is too large.").format(name=name))
    return data


def read_watched(path):
    """A Page of a file that arrived in the watched folder (its own size: dpi 0)."""
    data = _read_plain_file(path, MAX_WATCHED_FILE)
    if not _complete(data[:8], data[-2048:]):
        raise ScanError(tr("{name} is incomplete (the printer may have stopped sending "
                           "it).").format(name=os.path.basename(path)))
    if os.path.splitext(path)[1].lower() == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ScanError(tr("{name} isn't a PDF.").format(name=os.path.basename(path)))
        return net.Page(data, "pdf", 0, [])
    return net.check_image(data, 0)

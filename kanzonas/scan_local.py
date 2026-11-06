"""File > Scan through the computer's own scanner drivers, and watching a folder.

- Windows: WIA (Windows Image Acquisition), through its scripting objects (WIA.DeviceManager)
  in a Windows PowerShell process, so USB scanners, vendor WIA drivers and the network scanners
  Windows has already added all work, with nothing to install.
- Linux: SANE, through the `scanimage` command when it's installed (the sane-utils package).
- macOS: neither yet (eSCL and WSD work there).
- Any system: a folder a printer scans into (Scan to Network Folder, FTP, a USB stick copied
  over): new PDFs and pictures that appear in it are taken as scanned pages.

The commands run with fixed arguments (no shell); what they print and the files they write are
checked like anything from the network (scan_net.check_image).
"""

import base64
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
WIA_FORMATS = {"jpeg": "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}",
               "png": "{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}",
               "bmp": "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"}
WIA_INTENT = {"color": 1, "gray": 2, "bw": 4}      # WIA_IPS_CUR_INTENT
WIA_DATATYPE = {"color": 3, "gray": 2, "bw": 0}    # WIA_IPA_DATATYPE
WIA_HANDLING = {"platen": 2, "feeder": 1, "duplex": 5}     # WIA_DPS_DOCUMENT_HANDLING_SELECT
WIA_ERRORS = {
    "80210003": "empty", "80210002": "jam", "80210004": "jam", "80210016": "open",
    "80210005": "offline", "8021000A": "offline", "80210015": "offline", "80210006": "busy",
    "80210007": "warming", "80210008": "attention",
}

_PS_HEAD = ("$ErrorActionPreference = 'Stop'\n"
            "[Console]::OutputEncoding = [Text.Encoding]::UTF8\n"
            "function Hex($e) { '{0:X8}' -f $e.Exception.HResult }\n")

PS_LIST = _PS_HEAD + """
$m = New-Object -ComObject WIA.DeviceManager
foreach ($i in $m.DeviceInfos) {
  if ($i.Type -eq 1) {
    $n = ''
    try { $n = $i.Properties.Item('Name').Value } catch {}
    Write-Output ("DEVICE`t" + $i.DeviceID + "`t" + $n)
  }
}
"""

PS_SCAN = _PS_HEAD + """
function SetProp($props, $id, $value) {
  foreach ($p in $props) { if ($p.PropertyID -eq $id) { try { $p.Value = $value } catch {}; return } }
}
try {
  $m = New-Object -ComObject WIA.DeviceManager
  $info = $null
  foreach ($i in $m.DeviceInfos) { if ($i.DeviceID -eq '@ID@') { $info = $i } }
  if ($info -eq $null) { Write-Output "ERROR`tNOTFOUND`t"; exit 3 }
  $dev = $info.Connect()
  SetProp $dev.Properties 3088 @HANDLING@
  SetProp $dev.Properties 3096 @PAGES@
  $item = $dev.Items.Item(1)
  SetProp $item.Properties 6146 @INTENT@
  SetProp $item.Properties 4103 @DATATYPE@
  SetProp $item.Properties 6147 @DPI@
  SetProp $item.Properties 6148 @DPI@
  SetProp $item.Properties 6149 0
  SetProp $item.Properties 6150 0
  SetProp $item.Properties 6151 @WIDTH@
  SetProp $item.Properties 6152 @HEIGHT@
  $n = 0
  while ($n -lt @MAX@) {
    try { $img = $item.Transfer('@FORMAT@') }
    catch {
      $code = Hex $_
      if ($n -gt 0 -and $code -eq '80210003') { break }
      if ($n -eq 0 -and $code -ne '80210003') {
        try { $img = $item.Transfer() } catch { Write-Output ("ERROR`t" + (Hex $_) + "`t" + $_.Exception.Message); exit 2 }
      } else { Write-Output ("ERROR`t" + $code + "`t" + $_.Exception.Message); exit 2 }
    }
    $n++
    $path = Join-Path '@DIR@' ('page{0:D4}.{1}' -f $n, $img.FileExtension)
    $img.SaveFile($path)
    Write-Output ("PAGE`t" + $path)
    if (@ONE@) { break }
  }
  Write-Output "DONE"
} catch { Write-Output ("ERROR`t" + (Hex $_) + "`t" + $_.Exception.Message); exit 2 }
"""


def powershell():
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return exe if os.path.isfile(exe) else (shutil.which("powershell") or "powershell.exe")


def ps_command(script):
    """The command line that runs a PowerShell script (passed encoded: no quoting issues)."""
    return [powershell(), "-NoProfile", "-NonInteractive", "-Sta", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode("ascii")]


def _ps_quote(s):
    return str(s).replace("'", "''")


def wia_devices(log=None):
    code, out, err = run(ps_command(PS_LIST), LIST_TIMEOUT)
    devices = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] == "DEVICE" and parts[1]:
            devices.append(Device(parts[2] or tr("Scanner"), "wia", parts[1]))
    if log is not None:
        log.append("WIA: %d scanner(s)%s" % (len(devices), "" if code == 0 else
                                             " (exit %s: %s)" % (code, err.strip()[:200])))
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
    return tr("Windows couldn't scan ({code}): {message}").format(code=code, message=message)


class WiaScanner:
    protocol = "wia"

    def __init__(self, device):
        self.device = device
        self.proc = None
        self.trail = []
        self.canceled = False

    def capabilities(self):
        # WIA's own settings vary by driver; these are what nearly every scanner takes (the
        # driver adjusts a value it can't do exactly)
        src = SourceCaps(resolutions=[75, 100, 150, 200, 300, 600])
        return Caps({"platen": src, "feeder": src, "duplex": src}, self.device.name)

    def abort(self):
        self.canceled = True
        if self.proc:
            self.proc.kill()

    def script(self, settings, folder):
        w_in, h_in = net.region(settings, SourceCaps(max_w=8.5, max_h=14.0))
        fmt = "png" if settings.color == "bw" else "jpeg"
        values = {"ID": _ps_quote(self.device.address), "DIR": _ps_quote(folder),
                  "HANDLING": WIA_HANDLING[settings.source],
                  "PAGES": 1 if settings.source == "platen" else 0,
                  "INTENT": WIA_INTENT[settings.color], "DATATYPE": WIA_DATATYPE[settings.color],
                  "DPI": int(settings.dpi), "WIDTH": round(w_in * settings.dpi),
                  "HEIGHT": round(h_in * settings.dpi), "FORMAT": WIA_FORMATS[fmt],
                  "MAX": net.MAX_PAGES, "ONE": "$true" if settings.source == "platen" else "$false"}
        return re.sub(r"@([A-Z]+)@", lambda m: str(values[m.group(1)]), PS_SCAN)

    def scan(self, settings, report=lambda _t: None):
        folder = tempfile.mkdtemp(prefix="kanzonas-scan-")
        try:
            report(tr("Starting the scan..."))
            self.proc = _Proc(ps_command(self.script(settings, folder)), net.PAGE_TIMEOUT,
                              stderr=subprocess.STDOUT)
            pages, error = 0, None
            for line in self.proc.lines(self.proc.p.stdout):
                kind, _t, rest = line.partition("\t")
                if kind == "PAGE":
                    path = os.path.join(folder, os.path.basename(rest))
                    pages += 1
                    yield _read_page(path, settings.dpi)
                    report(tr("Scanning page {n}...").format(n=pages + 1))
                elif kind == "ERROR":
                    code, _t, msg = rest.partition("\t")
                    error = ScanError(wia_message(code, msg, pages), "WIA %s: %s" % (code, msg))
            self.proc.finish()
            if self.canceled:
                raise net.Canceled()
            if self.proc.timed_out:
                raise ScanError(tr("The scanner stopped answering."))
            if error:
                raise error
            if not pages:
                raise ScanError(tr("The scanner finished without sending a page."))
        finally:
            if self.proc:
                self.proc.kill()
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
class FolderWatch:
    """New PDFs and pictures in a folder. Files already there when watching starts are left
    alone; a new file is taken once its size has stayed the same between two looks (the
    printer may still be writing it)."""

    def __init__(self, folder):
        self.folder = folder
        self.known = set(self._names())
        self.sizes = {}

    def _names(self):
        try:
            with os.scandir(self.folder) as it:
                return [e.name for _i, e in zip(range(20000), it)
                        if e.is_file() and os.path.splitext(e.name)[1].lower() in WATCH_EXTS]
        except OSError:
            return []

    def poll(self):
        """Paths of the files that have arrived complete since the last look."""
        ready = []
        for name in self._names():
            if name in self.known:
                continue
            path = os.path.join(self.folder, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > 0 and self.sizes.get(name) == size:
                self.known.add(name)
                self.sizes.pop(name, None)
                ready.append(path)
            else:
                self.sizes[name] = size
        return sorted(ready)


def read_watched(path):
    """A Page of a file that arrived in the watched folder (its own size: dpi 0)."""
    if os.path.splitext(path)[1].lower() == ".pdf":
        try:
            if os.path.getsize(path) > MAX_WATCHED_FILE:
                raise ScanError(tr("{name} is too large.").format(name=os.path.basename(path)))
            with open(path, "rb") as f:
                data = f.read()
        except OSError as ex:
            raise ScanError(tr("Couldn't read {name}.").format(name=os.path.basename(path)),
                            str(ex))
        if not data.startswith(b"%PDF-"):
            raise ScanError(tr("{name} isn't a PDF.").format(name=os.path.basename(path)))
        return net.Page(data, "pdf", 0, [])
    return _read_page(path, 0)

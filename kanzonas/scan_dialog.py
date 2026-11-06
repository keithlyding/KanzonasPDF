"""File > Scan...: the Scan window.

The scanners found (and how each is reached: eSCL, WSD, WIA, SANE), Refresh, Add by
address..., Watch a folder...; the source, color, resolution and page size the chosen scanner
offers; Scan (with progress and Cancel), then Scan more pages or Done. Done puts the pages in a
new document or into the current one after the current page (one undo step), and can make them
searchable with OCR.

Talking to the scanner runs in a worker thread (scanners.py and the protocol modules have no
Qt and no PyMuPDF in them); the pages come back to the Qt main thread through a signal, and
only there are they made into PDF pages (PyMuPDF isn't thread-safe).
"""

import json
import os
import sys
import threading

import pymupdf
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
                               QPushButton, QRadioButton, QVBoxLayout)

from . import paths
from . import scan_net as net
from .i18n import tr
from .scan_net import Device, ScanError, ScanSettings

WATCH_INTERVAL = 2000           # ms between looks at a watched folder


def source_labels():
    return {"platen": tr("Flatbed (glass)"), "feeder": tr("Document feeder"),
            "duplex": tr("Document feeder, both sides")}


def color_labels():
    return {"color": tr("Color"), "gray": tr("Grayscale"), "bw": tr("Black and white")}


def size_labels():
    return {"letter": tr("Letter (8.5 x 11 in)"), "legal": tr("Legal (8.5 x 14 in)"),
            "a4": tr("A4 (210 x 297 mm)"), "max": tr("Largest the scanner allows")}


def default_size():
    from PySide6.QtCore import QLocale
    return "letter" if QLocale().measurementSystem() == QLocale.ImperialUSSystem else "a4"


def build_pdf(pages):
    """A new PDF of scanned pages (main thread only). A picture page is its scanned size (its
    pixels at the resolution it was scanned at; a file from a watched folder keeps its own
    size); JPEG pictures stay JPEG inside (no quality loss). A PDF's pages come without
    their links, form fields and comments."""
    out = pymupdf.open()
    try:
        for p in pages:
            if p.kind == "pdf":
                src = pymupdf.open(stream=p.data, filetype="pdf")
                with src:
                    if src.needs_pass:
                        raise ScanError(tr("A scanned PDF is password-protected."))
                    if src.page_count > net.MAX_PAGES or \
                            out.page_count + src.page_count > 5 * net.MAX_PAGES:
                        raise ScanError(tr("Too many pages in one scan (more than {n}).").format(
                            n=net.MAX_PAGES))
                    # (its pages' drawing only: a PDF from the network or a shared folder
                    # can carry links that run a script or a program, form fields and
                    # comments, which a scanned page has no business bringing in)
                    out.insert_pdf(src, links=False, annots=False, widgets=False)
                continue
            img = pymupdf.open(stream=p.data, filetype=p.kind)
            pdf = pymupdf.open("pdf", img.convert_to_pdf())
            img.close()
            with pdf:
                for i in range(pdf.page_count):
                    r = pdf[i].rect
                    w, h = r.width, r.height
                    if p.dpi and i < len(p.sizes):
                        w, h = p.sizes[i][0] * 72.0 / p.dpi, p.sizes[i][1] * 72.0 / p.dpi
                        if (w > h) != (r.width > r.height) and abs(r.width - r.height) > 1:
                            w, h = h, w           # (turned by the picture's own orientation)
                    page = out.new_page(width=w, height=h)
                    page.show_pdf_page(page.rect, pdf, i)
        return out
    except Exception:
        out.close()
        raise


class _Bridge(QObject):
    event = Signal(object)


class ScanDialog(QDialog):
    """File > Scan. discover / open_scanner / add_by_address default to scanners.py's (tests
    pass stand-ins)."""

    def __init__(self, window, discover=None, open_scanner=None, add_by_address=None):
        super().__init__(window)
        from . import scanners
        self.win = window
        self.settings = window.settings
        self._discover = discover or scanners.discover
        self._open = open_scanner or scanners.open_scanner
        self._add = add_by_address or scanners.add_by_address
        self.devices, self.printers, self.log = [], [], []
        self.caps = {}                  # device key -> Caps
        self.pages = []
        self.scanner = None             # the protocol object scanning now
        self.error = None
        self.trail = []
        self.watch = None
        self.link = None                # the WSD printer this computer is listed on (panel)
        self._gen = {}
        self._busy = set()
        self._bridge = _Bridge(self)
        self._bridge.event.connect(self._on_event)
        self._watch_timer = QTimer(self)
        self._watch_timer.timeout.connect(self._poll_folder)
        self.setWindowTitle(tr("Scan"))
        self._build()
        self._restore()
        self.refresh()

    # ---- the window -------------------------------------------------------------------------
    def _build(self):
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Scanners and printers found:")))
        self.list = QListWidget()
        self.list.setMinimumWidth(460)
        self.list.setMinimumHeight(110)
        self.list.currentRowChanged.connect(lambda _r: self._device_changed())
        lay.addWidget(self.list)
        row = QHBoxLayout()
        self.b_refresh = QPushButton(tr("Refresh"))
        self.b_refresh.setToolTip(tr("Look for scanners again"))
        self.b_refresh.clicked.connect(self.refresh)
        self.b_add = QPushButton(tr("Add by address..."))
        self.b_add.setToolTip(tr("Type the printer's IP address when it isn't found (Wi-Fi "
                                 "and some routers block discovery)"))
        self.b_add.clicked.connect(self.add_address)
        self.b_watch = QPushButton(tr("Watch a folder..."))
        self.b_watch.setToolTip(tr("For a printer that scans to a network folder or FTP: new "
                                   "PDFs and pictures that arrive in the folder are taken as "
                                   "scanned pages"))
        self.b_watch.clicked.connect(self.watch_folder)
        for b in (self.b_refresh, self.b_add, self.b_watch):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        form = QFormLayout()
        self.source = QComboBox()
        self.color = QComboBox()
        self.dpi = QComboBox()
        self.page_size = QComboBox()
        for k, label in size_labels().items():
            self.page_size.addItem(label, k)
        form.addRow(tr("Source:"), self.source)
        form.addRow(tr("Color:"), self.color)
        form.addRow(tr("Resolution:"), self.dpi)
        form.addRow(tr("Page size:"), self.page_size)
        self.source.currentIndexChanged.connect(lambda _i: self._source_changed())
        into = QHBoxLayout()
        self.rb_new = QRadioButton(tr("A new document"))
        self.rb_current = QRadioButton(tr("This document, after the current page"))
        group = QButtonGroup(self)
        group.addButton(self.rb_new)
        group.addButton(self.rb_current)
        into.addWidget(self.rb_new)
        into.addWidget(self.rb_current)
        into.addStretch(1)
        form.addRow(tr("Put the pages in:"), into)
        self.ocr = QCheckBox(tr("Make the pages searchable (recognize text, OCR)"))
        form.addRow("", self.ocr)
        lay.addLayout(form)
        # (plain text: device names, faults and file names come from the network, and a
        # label would otherwise take "<b>" or "<img ...>" in them for formatting)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status.setMinimumHeight(48)
        lay.addWidget(self.status)
        self.panel_note = QLabel()
        self.panel_note.setTextFormat(Qt.PlainText)
        self.panel_note.setWordWrap(True)
        self.panel_note.setStyleSheet("color: gray;")
        self.panel_note.setVisible(False)
        lay.addWidget(self.panel_note)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)
        self.count = QLabel()
        lay.addWidget(self.count)
        row = QHBoxLayout()
        self.b_details = QPushButton(tr("Copy details"))
        self.b_details.setToolTip(tr("Copy what was found and the scanner's own answers, to send "
                                     "if your scanner doesn't work (nothing personal is "
                                     "included)"))
        self.b_details.clicked.connect(self.copy_details)
        self.b_scan = QPushButton(tr("Scan"))
        self.b_scan.setDefault(True)
        self.b_scan.clicked.connect(self.scan)
        self.b_cancel = QPushButton(tr("Cancel"))
        self.b_cancel.clicked.connect(self.cancel_scan)
        self.b_done = QPushButton(tr("Done"))
        self.b_done.setToolTip(tr("Put the scanned pages in the document"))
        self.b_done.clicked.connect(self.finish)
        self.b_close = QPushButton(tr("Close"))
        self.b_close.clicked.connect(self.reject)
        row.addWidget(self.b_details)
        row.addStretch(1)
        for b in (self.b_scan, self.b_cancel, self.b_done, self.b_close):
            row.addWidget(b)
        lay.addLayout(row)
        self._update()

    def _restore(self):
        s = self.settings
        self.page_size.setCurrentIndex(max(0, self.page_size.findData(paths.stored_str(
            s, "scan_size", default_size(), tuple(net.PAGE_SIZES)))))
        has_doc = self.win.view() is not None
        self.rb_current.setEnabled(has_doc)
        into = paths.stored_str(s, "scan_into", "new", ("new", "current"))
        (self.rb_current if into == "current" and has_doc else self.rb_new).setChecked(True)
        self.ocr.setChecked(paths.stored_str(s, "scan_ocr", "false") == "true")
        try:
            d = Device.from_dict(json.loads(paths.stored_str(s, "scan_device", "") or "null"))
        except ValueError:
            d = None
        if d is not None:
            self.devices.append(d)
            self._fill_list(select=d.key())

    def _remember(self):
        s = self.settings
        d = self.device()
        if d is not None:
            s.setValue("scan_device", json.dumps(d.to_dict()))
        for key, combo in (("scan_source", self.source), ("scan_color", self.color),
                           ("scan_dpi", self.dpi), ("scan_size", self.page_size)):
            if combo.currentData() is not None:
                s.setValue(key, str(combo.currentData()))
        s.setValue("scan_into", "current" if self.rb_current.isChecked() else "new")
        s.setValue("scan_ocr", "true" if self.ocr.isChecked() else "false")

    def _say(self, text):
        self.status.setText(text)

    def _update(self):
        scanning = "scan" in self._busy
        d = self.device()
        ready = d is not None and d.key() in self.caps and not scanning
        self.b_scan.setEnabled(ready)
        self.b_scan.setText(tr("Scan more pages") if self.pages else tr("Scan"))
        self.b_cancel.setEnabled(scanning or "add" in self._busy)
        self.b_done.setEnabled(bool(self.pages) and not scanning)
        self.b_refresh.setEnabled("find" not in self._busy and not scanning)
        self.b_add.setEnabled("add" not in self._busy and not scanning)
        self.list.setEnabled(not scanning)
        for w in (self.source, self.color, self.dpi, self.page_size):
            w.setEnabled(not scanning)
        self.progress.setVisible(bool(self._busy - {"watch"}))
        n = len(self.pages)
        self.count.setText(tr("{n} page(s) scanned").format(n=n) if n else "")

    # ---- worker threads ---------------------------------------------------------------------
    def _start(self, kind, fn, *extra):
        """Run fn() in a worker thread; its result (or exception) comes back as an event."""
        gen = self._gen[kind] = self._gen.get(kind, 0) + 1
        self._busy.add(kind)
        bridge = self._bridge

        def emit(ev):
            try:
                bridge.event.emit(ev)
            except RuntimeError:        # (the window is gone)
                pass

        def run():
            try:
                result = fn(lambda *a: emit((kind, gen, "progress") + a))
                emit((kind, gen, "ok", result) + extra)
            except Exception as ex:          # (shown to the user in plain words)
                emit((kind, gen, "error", ex) + extra)
        t = threading.Thread(target=run, daemon=True, name="kanzonas-scan-" + kind)
        t.start()
        self._update()
        return t

    def _on_event(self, ev):
        kind, gen, what = ev[0], ev[1], ev[2]
        if gen != self._gen.get(kind):
            return                      # (from a search or scan that was replaced)
        if what != "progress":
            self._busy.discard(kind)
        getattr(self, "_got_" + kind)(what, *ev[3:])
        self._update()

    # ---- finding scanners ------------------------------------------------------------------
    def refresh(self):
        self.log = []
        self._say(tr("Looking for scanners..."))
        log, cancel = self.log, lambda: False
        self._start("find", lambda _p: self._discover(cancel=cancel, log=log))

    def _got_find(self, what, result):
        if what == "error":
            self.error = result
            self._say(getattr(result, "message", str(result)))
            return
        found, printers = result
        self.printers = printers
        keep = self.device()
        known = {d.key() for d in found}
        named = {(d.protocol, d.name) for d in found}
        # the remembered or added scanner stays listed even when discovery misses it (unless
        # it was found again, at a new address)
        extra = [d for d in self.devices if d.key() not in known and
                 (d.protocol, d.name) not in named]
        if keep is not None and keep.key() not in known and (keep.protocol, keep.name) in named:
            keep = next(d for d in found if (d.protocol, d.name) == (keep.protocol, keep.name))
        self.devices = found + extra
        self._fill_list(select=keep.key() if keep else None)
        if found:
            self._say(tr("Found {n} scanner(s): pick one, then click Scan.").format(n=len(found)))
        elif printers:
            p = printers[0]
            self._say(tr("{names} answered but offer no scanning over the network: open the "
                         "printer's web page (http://{ip}) and set WSD to Enable, then click "
                         "Refresh; or try Add by address...").format(
                             names=", ".join(x.name for x in printers[:3]), ip=p.host))
        else:
            from . import scanners
            self._say(tr("No scanners found on this network. Tried: {tried}. Try Add by "
                         "address... with the printer's IP address (on its panel or its network "
                         "report), or Watch a folder... if the printer scans to a folder.")
                      .format(tried="; ".join(scanners.tried_list())))

    def _fill_list(self, select=None):
        self.list.blockSignals(True)
        self.list.clear()
        for d in self.devices:
            it = QListWidgetItem(d.label())
            it.setToolTip(d.address)
            it.setData(Qt.UserRole, d.key())
            self.list.addItem(it)
        self.list.blockSignals(False)
        keys = [d.key() for d in self.devices]
        row = keys.index(select) if select in keys else (0 if keys else -1)
        self.list.setCurrentRow(row)
        if row >= 0 and self.list.currentRow() == row:
            self._device_changed()

    def device(self):
        row = self.list.currentRow()
        return self.devices[row] if 0 <= row < len(self.devices) else None

    def add_address(self):
        text, ok = QInputDialog.getText(
            self, tr("Add by address"),
            tr("The printer's IP address or name (on its panel, or in its network report), "
               "for example 192.168.1.20:"),
            text=paths.stored_str(self.settings, "scan_address", ""))
        if not ok or not text.strip():
            return
        self.settings.setValue("scan_address", text.strip())
        self._say(tr("Asking {address} (eSCL, then WSD)...").format(address=text.strip()))
        log = self.log
        self._start("add", lambda _p: self._add(text, log=log))

    def _got_add(self, what, result):
        if what == "error":
            self.error = result
            self._say(getattr(result, "message", str(result)))
            return
        d = result
        self.devices = [x for x in self.devices if x.key() != d.key()] + [d]
        self._fill_list(select=d.key())

    # ---- the chosen scanner's options -------------------------------------------------------
    def _device_changed(self):
        d = self.device()
        if d is None or "scan" in self._busy:
            self._update()
            return
        if self.link is not None and self.link.device.key() != d.key():
            self._unlink()
        if d.key() in self.caps:
            self._fill_options(self.caps[d.key()])
            return
        if "caps" in self._busy and getattr(self, "_asking", None) == d.key():
            return                      # (already being asked)
        self._asking = d.key()
        self._say(tr("Asking {name} what it can do...").format(name=d.name))
        scanner = self._open(d)
        self._start("caps", lambda _p: scanner.capabilities(), d.key(), scanner)

    def _got_caps(self, what, result, key, scanner):
        self.trail = getattr(scanner, "trail", [])
        if what == "error":
            self.error = result
            self._say(getattr(result, "message", str(result)))
            return
        self.caps[key] = result
        self._scanners = getattr(self, "_scanners", {})
        self._scanners[key] = scanner
        d = self.device()
        if d is not None and d.key() == key:
            self._fill_options(result)
            self._say(tr("Ready: put the pages on the glass or in the feeder, then click Scan."))
            if d.protocol == "wsd" and self.link is None:
                self._link(d)

    def _fill_options(self, caps):
        s = self.settings
        want = self.source.currentData() or paths.stored_str(s, "scan_source", "platen")
        self.source.blockSignals(True)
        self.source.clear()
        for k, label in source_labels().items():
            if k in caps.sources:
                self.source.addItem(label, k)
        self.source.setCurrentIndex(max(0, self.source.findData(want)))
        self.source.blockSignals(False)
        self._source_changed()

    def _source_changed(self):
        d = self.device()
        caps = self.caps.get(d.key()) if d else None
        if caps is None or self.source.currentData() not in caps.sources:
            return
        src = caps.sources[self.source.currentData()]
        s = self.settings
        want_c = self.color.currentData() or paths.stored_str(s, "scan_color", "color")
        try:
            want_d = int(self.dpi.currentData() or paths.stored_str(s, "scan_dpi", "300"))
        except ValueError:
            want_d = 300
        self.color.clear()
        for k, label in color_labels().items():
            if k in src.colors:
                self.color.addItem(label, k)
        self.color.setCurrentIndex(max(0, self.color.findData(want_c)))
        self.dpi.clear()
        for v in src.resolutions:
            self.dpi.addItem(tr("{dpi} dpi").format(dpi=v), v)
        self.dpi.setCurrentIndex(max(0, self.dpi.findData(net.nearest(src.resolutions, want_d))))

    def current_settings(self):
        return ScanSettings(source=self.source.currentData() or "platen",
                            color=self.color.currentData() or "color",
                            dpi=int(self.dpi.currentData() or 300),
                            size=self.page_size.currentData() or "letter")

    # ---- scanning --------------------------------------------------------------------------
    def scan(self, panel=None):
        """Scan with the window's settings. panel: (ScanIdentifier, DestinationToken) of a
        scan started on the printer's panel."""
        d = self.device()
        if d is None or d.key() not in self.caps:
            return
        scanner = getattr(self, "_scanners", {}).get(d.key()) or self._open(d)
        scanner.caps = getattr(scanner, "caps", None) or self.caps[d.key()]
        self.scanner = scanner
        settings = self.current_settings()
        self._remember()
        self._say(tr("Starting the scan..."))

        extra = {"scan_id": panel[0], "dest_token": panel[1]} if panel else {}

        def job(progress):
            n = 0
            for page in scanner.scan(settings, lambda t: progress("status", t), **extra):
                progress("page", page)
                n += 1
            return n
        self._start("scan", job)

    def _got_scan(self, what, *args):
        if what == "progress":
            if args[0] == "status":
                self._say(args[1])
            elif args[0] == "page":
                self.pages.append(args[1])
            return
        self.trail = getattr(self.scanner, "trail", [])
        self.scanner = None
        if what == "error":
            ex = args[0]
            if not isinstance(ex, net.Canceled):
                self.error = ex
            self._say(getattr(ex, "message", str(ex)) if not isinstance(ex, net.Canceled) else
                      tr("Canceled.") + (" " + tr("The pages scanned before are kept.")
                                         if self.pages else ""))
            return
        self._say(tr("Scanned {n} page(s). Scan more pages, or click Done to put them in a "
                     "document.").format(n=len(self.pages)))

    def cancel_scan(self):
        if self.scanner is not None:
            self.scanner.abort()
        if "add" in self._busy:
            self._gen["add"] = self._gen.get("add", 0) + 1     # (its answer is ignored)
            self._busy.discard("add")
            self._say(tr("Canceled."))
        self._update()

    # ---- scans started on the printer's panel (WSD, scan_events.py) ----------------------
    def _link(self, device):
        from .scan_events import PanelLink
        gen = self._gen["panel"] = self._gen.get("panel", 0) + 1
        bridge = self._bridge

        def emit(*ev):
            try:
                bridge.event.emit(("panel", gen) + ev)
            except RuntimeError:        # (the window is gone)
                pass
        self.link = PanelLink(device, lambda sid, token: emit("scan", sid, token),
                              lambda ok, err: emit("state", ok, err))
        self.panel_note.setText(tr("Letting the printer list this computer on its panel..."))
        self.panel_note.setVisible(True)
        self.link.start()

    def _unlink(self):
        if self.link is not None:
            self.link.stop()
            self.link = None
            self._gen["panel"] = self._gen.get("panel", 0) + 1
        self.panel_note.setVisible(False)

    def _got_panel(self, what, *args):
        if what == "state":
            ok, err = args
            if ok:
                note = tr("You can also start the scan on the printer: choose Scan to Computer "
                          "(WSD) on its panel and pick \"{name}\"; the pages come here, with the "
                          "settings above.").format(name=self.link.name if self.link else "")
                if sys.platform == "win32":
                    note += " " + tr("If Windows asks whether to allow KanzonasPDF on private "
                                     "networks, allow it: that's how the printer reaches this "
                                     "window.")
            else:
                note = tr("Scans started on the printer's panel can't come here: {error}").format(
                    error=getattr(err, "message", err))
            self.panel_note.setText(note)
            return
        if what == "scan":
            if "scan" in self._busy:
                self._say(tr("The printer started a scan, but another one is still running "
                             "here."))
                return
            self._say(tr("The printer started a scan: receiving the pages..."))
            self.scan(panel=args)

    # ---- a watched folder -------------------------------------------------------------------
    def watch_folder(self):
        from .scan_local import FolderWatch
        folder = QFileDialog.getExistingDirectory(
            self, tr("Watch a folder"), paths.stored_str(self.settings, "scan_folder", ""))
        if not folder:
            return
        self.settings.setValue("scan_folder", folder)
        self.watch = FolderWatch(folder)
        self._watch_timer.start(WATCH_INTERVAL)
        self._say(tr("Watching {folder}: scan into it from the printer (Scan to Network Folder "
                     "or FTP); each new PDF or picture is added here as it arrives. Click Done "
                     "when they're all in.").format(folder=folder))

    def _poll_folder(self):
        """Look at the watched folder in a worker thread (a slow network share mustn't make
        the window stutter); only making the finished files into pages happens here."""
        from .scan_local import read_watched
        if self.watch is None or "watch" in self._busy:
            return
        watch = self.watch

        def look(_progress):
            out = []
            for path in watch.poll():
                try:
                    out.append((path, read_watched(path), None))
                except Exception as ex:
                    out.append((path, None, ex))
            return out
        self._start("watch", look)

    def _got_watch(self, what, result):
        if what == "error":
            self._say(getattr(result, "message", str(result)))
            return
        for path, page, err in result:
            if page is not None:
                try:
                    build_pdf([page]).close()    # (it opens: checked before it's added)
                except Exception as ex:
                    err = ex
            if err is not None:
                self._say(tr("Couldn't use {name}: {error}").format(
                    name=os.path.basename(path), error=getattr(err, "message", err)))
                continue
            self.pages.append(page)
            self._say(tr("Added {name} from the folder.").format(name=os.path.basename(path)))

    # ---- Done: the pages into a document -------------------------------------------------
    def finish(self):
        if not self.pages or "scan" in self._busy:
            return
        self._remember()
        try:
            doc = build_pdf(self.pages)
        except Exception as ex:
            QMessageBox.warning(self, tr("Scan"), tr("Couldn't make the scanned pages into a "
                                                     "PDF: {error}").format(
                                                         error=getattr(ex, "message", ex)))
            return
        n = doc.page_count
        v = self.win.view() if self.rb_current.isChecked() else None
        if v is not None:
            if not self.win._pages_unlocked():
                doc.close()
                return
            at = v.current_page() + 1
            try:
                ok = v.modify(lambda: v.doc.insert_pdf(doc, start_at=at), structural=True,
                              changed=[])
            finally:
                doc.close()
            if not ok:
                return
            v.goto_page(at)
            new = list(range(at, at + n))
        else:
            v = self.win._open_untitled(doc)
            v.dirty = True              # closing it asks whether to save
            new = list(range(n))
        self.pages = []
        self._watch_timer.stop()
        self.win.statusBar().showMessage(tr("{n} scanned page(s) added").format(n=n), 5000)
        self.accept()
        if self.ocr.isChecked():
            v.run_ocr(new, paths.stored_str(self.settings, "ocr_accuracy", "auto"))

    # ---- Copy details ------------------------------------------------------------------------
    def details(self):
        from . import scanners
        d = self.device()
        caps = self.caps.get(d.key()) if d else None
        trail = list(self.trail)
        if self.link is not None:
            trail += ["panel: " + x for x in self.link.log + (
                self.link.listener.log if self.link.listener else [])]
        return scanners.details_report(self.devices, self.printers, self.log, d, caps,
                                       self.error, trail)

    def copy_details(self):
        QApplication.clipboard().setText(self.details())
        self._say(tr("Copied the details: paste them into an email or a GitHub issue to the "
                     "KanzonasPDF project."))

    # ---- closing -------------------------------------------------------------------------------
    def reject(self):
        if self.pages:
            r = QMessageBox.question(self, tr("Scan"), tr("Discard the {n} scanned page(s)?")
                                     .format(n=len(self.pages)))
            if r != QMessageBox.Yes:
                return
        self._stop()
        super().reject()

    def done(self, result):
        self._stop()                    # (accepted or rejected: stop listening, unsubscribe)
        super().done(result)

    def _stop(self):
        self._watch_timer.stop()
        self._unlink()
        if self.scanner is not None:
            self.scanner.abort()
        for k in list(self._gen):
            self._gen[k] += 1           # (answers still coming are ignored)
        self._busy.clear()

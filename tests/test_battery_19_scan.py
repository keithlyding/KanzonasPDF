"""What the 1.9 break-it battery found in File > Scan, fixed:

- a page cut short (the device or the Wi-Fi dropped the connection mid-page) was taken as a
  scanned page, half a picture: http.client doesn't say a Content-Length wasn't met;
- a job whose address (the device's Location) had a space in it failed ("Couldn't reach
  ...: URL can't contain control characters": http.client refuses such a path);
- Cancel while a page was arriving added the half that had come before it stopped;
- the listener for scans started on the printer's panel read and parsed a request from any
  computer on the network before refusing it, a thread for each (a host opening many slow
  connections piled threads up), and a chunk size of -1 read the request until the sender
  stopped, however much it sent;
- a PDF that a scanner sent or that arrived in the watched folder brought its links (a
  javascript: address, a link starting a program), form fields and comments into the
  document;
- a multi-page TIFF had a size cap for each picture but none for all of them: 500
  pictures of 200 megapixels each (a small file when compressed) were all decoded on the
  main thread; and a file from the watched folder had its pictures decoded twice (checked
  when it arrived, made into pages again at Done);
- the Scan window's messages took a device's name (or a fault, or a file name from the
  watched folder) with "<b>" or "<img ...>" in it for formatting;
- the watched folder took a file that a printer or an FTP upload paused writing for two
  seconds (half a page), followed links to files elsewhere on this computer (a share others
  write into could bring in any file the user can read), and a pipe put there in place of a
  file made the folder's reading wait forever.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_battery_19_scan
"""
import io
import os
import socket
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_scanning import (APP, ESCL_CAPS, Escl, FakeScanner,  # noqa: E402,F401
                                 ServerCase, picture, wait_for)
from kanzonas import scan_escl, scan_events, scan_local, scan_net as net  # noqa: E402
from kanzonas.scan_net import Device, ScanError, ScanSettings  # noqa: E402


class CutShort(Escl):
    """An eSCL scanner whose page stops halfway: the connection closed (or, with hang, left
    open a while first, as a device that stalls)."""

    def do_GET(self):
        st = self.server.st
        if "NextDocument" not in self.path or not st["pages"]:
            return Escl.do_GET(self)
        body = st["pages"].pop(0)
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body[:len(body) // 2])
        self.wfile.flush()
        if st.get("hang"):
            time.sleep(st["hang"])
        self.close_connection = True


class Pages(ServerCase):
    def scanner(self, **state):
        srv, port = self.server(CutShort, **state)
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        s.caps = scan_escl.parse_capabilities(ESCL_CAPS)
        return srv, s

    def test_a_page_cut_short_is_not_taken(self):
        srv, s = self.scanner(pages=[picture(400, 400)])
        got = []
        with self.assertRaises(net.NetError) as cm:
            for page in s.scan(ScanSettings()):
                got.append(page)
        self.assertEqual(got, [])
        self.assertIn("was cut", cm.exception.message)
        self.assertEqual(srv.st["deletes"], ["/eSCL/ScanJobs/123"])     # the job is cleaned up

    def test_cancel_while_a_page_arrives_keeps_no_half_page(self):
        _srv, s = self.scanner(pages=[picture(400, 400)], hang=3)
        got = []
        threading.Timer(0.6, s.abort).start()
        t0 = time.time()
        with self.assertRaises(net.Canceled):
            for page in s.scan(ScanSettings()):
                got.append(page)
        self.assertEqual(got, [])
        self.assertLess(time.time() - t0, 2.5)


class OddLocation(Escl):
    """A device whose job address has a space in it."""

    def do_POST(self):
        self.server.st["posts"].append((self.path, self.body().decode()))
        self.send(201, headers=[("Location", "/eSCL/Scan Jobs/123")])

    def do_GET(self):
        st = self.server.st
        if self.path == "/eSCL/Scan%20Jobs/123/NextDocument":
            if st["pages"]:
                return self.send(200, st["pages"].pop(0), "image/jpeg")
            return self.send(404)
        return Escl.do_GET(self)


class Addresses(ServerCase):
    def test_a_job_address_with_a_space(self):
        srv, port = self.server(OddLocation, pages=[picture(50, 50)])
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        self.assertEqual(len(list(s.scan(ScanSettings()))), 1)
        self.assertEqual(srv.st["deletes"], ["/eSCL/Scan%20Jobs/123"])


class PanelListener(unittest.TestCase):
    def test_another_computer_is_turned_away_before_anything_is_read(self):
        lst = scan_events.EventListener("10.9.9.9", lambda *a: None, "127.0.0.1")
        lst.start()
        self.addCleanup(lst.stop)
        _s, host, port, _path = net.split_url(lst.url)
        s = socket.create_connection((host, port), timeout=5)
        self.addCleanup(s.close)
        s.settimeout(2)
        t0 = time.time()
        try:
            got = s.recv(100)            # (sending nothing: the listener used to wait 10 s)
        except ConnectionResetError:
            got = b""
        self.assertEqual(got, b"")
        self.assertLess(time.time() - t0, 1.5)
        self.assertIn("127.0.0.1 refused", lst.log)

    def test_a_negative_chunk_size(self):
        body = io.BytesIO(b"-1\r\n" + b"x" * 300000 + b"\r\n0\r\n\r\n")
        with self.assertRaises(ValueError):
            scan_events._read_chunked(body, scan_events.MAX_EVENT)
        self.assertLess(body.tell(), 1000)          # (nothing read past the size)
        # (and what a printer really sends still reads)
        ok = io.BytesIO(b"4;ext=1\r\n<a/>\r\n0\r\n\r\n")
        self.assertEqual(scan_events._read_chunked(ok, scan_events.MAX_EVENT), b"<a/>")


class WatchedFolder(unittest.TestCase):
    def folder(self):
        d = tempfile.mkdtemp()
        return d, scan_local.FolderWatch(d, clock=lambda: self.now)

    now = 0.0

    def test_a_file_paused_while_written_waits(self):
        jpg = picture(300, 300)
        for name, data, cut in (("scan1.jpg", jpg, len(jpg) // 2),
                                ("scan2.pdf", b"%PDF-1.4\n" + b"1 0 obj\n<<>>\nendobj\n" * 50 +
                                 b"trailer\n<<>>\n%%EOF\n", 200),
                                ("scan3.png", picture(300, 300, "PNG"), 100)):
            with self.subTest(name=name):
                d, w = self.folder()
                path = os.path.join(d, name)
                with open(path, "wb") as f:
                    f.write(data[:cut])
                self.assertEqual(w.poll(), [])
                self.now += 2
                self.assertEqual(w.poll(), [])          # (the same size: but it's unfinished)
                with open(path, "ab") as f:
                    f.write(data[cut:])
                self.now += 2
                self.assertEqual(w.poll(), [])
                self.now += 2
                self.assertEqual(w.poll(), [path])
                self.assertEqual(scan_local.read_watched(path).data, data)

    def test_a_file_never_finished_is_said_to_be_incomplete(self):
        d, w = self.folder()
        path = os.path.join(d, "scan.jpg")
        with open(path, "wb") as f:
            f.write(picture(300, 300)[:500])
        self.assertEqual(w.poll(), [])
        self.now += 2
        self.assertEqual(w.poll(), [])
        self.now += scan_local.WATCH_GIVE_UP
        self.assertEqual(w.poll(), [path])
        with self.assertRaises(ScanError) as cm:
            scan_local.read_watched(path)
        self.assertIn("incomplete", cm.exception.message)

    @unittest.skipUnless(hasattr(os, "symlink"), "no links here")
    def test_a_link_to_a_file_elsewhere_is_left_alone(self):
        private = os.path.join(tempfile.mkdtemp(), "private.pdf")
        with open(private, "wb") as f:
            f.write(b"%PDF-1.4\nthe user's own file\n%%EOF\n")
        d, w = self.folder()
        link = os.path.join(d, "scan.pdf")
        try:
            os.symlink(private, link)
        except OSError:
            self.skipTest("can't make links here")
        for _ in range(3):
            self.now += 2
            self.assertEqual(w.poll(), [])
        with self.assertRaises(ScanError):
            scan_local.read_watched(link)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no pipes here")
    def test_a_pipe_in_place_of_a_file_doesnt_wait_forever(self):
        d, _w = self.folder()
        pipe = os.path.join(d, "scan.pdf")
        os.mkfifo(pipe)
        out = []

        def read():
            try:
                scan_local.read_watched(pipe)
            except ScanError as ex:
                out.append(ex)
        t = threading.Thread(target=read, daemon=True)
        t.start()
        t.join(3)
        if t.is_alive():                # (let the reader go: open the pipe's other end)
            fd = os.open(pipe, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
        self.assertFalse(t.is_alive())
        self.assertEqual(len(out), 1)


class ScannedPdf(unittest.TestCase):
    def test_only_the_pages_drawing_comes_in(self):
        import pymupdf
        from kanzonas.scan_dialog import build_pdf
        d = pymupdf.open()
        p = d.new_page()
        p.insert_text((50, 50), "The scanned words")
        p.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(10, 10, 50, 50),
                       "uri": "javascript:alert('LINKJS')"})
        p.insert_link({"kind": pymupdf.LINK_LAUNCH, "from": pymupdf.Rect(60, 10, 90, 50),
                       "file": "LAUNCHME.exe"})
        p.add_text_annot((100, 100), "NOTEFROMSCANNER")
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.field_name = "FIELDFROMSCANNER"
        w.rect = pymupdf.Rect(100, 200, 200, 220)
        p.add_widget(w)
        out = build_pdf([net.Page(d.tobytes(), "pdf", 0, [])])
        self.addCleanup(out.close)
        data = out.tobytes(garbage=1, expand=255)
        for word in (b"LINKJS", b"LAUNCHME", b"NOTEFROMSCANNER", b"FIELDFROMSCANNER"):
            self.assertNotIn(word, data)
        self.assertEqual(out[0].get_text().strip(), "The scanned words")


def tiff_header(sizes):
    """A TIFF whose pictures (one IFD each) claim sizes: only what's read before decoding."""
    import struct
    out = bytearray(b"II*\x00" + struct.pack("<I", 8))
    for k, (w, h) in enumerate(sizes):
        nxt = 8 + (k + 1) * (2 + 2 * 12 + 4) if k + 1 < len(sizes) else 0
        out += struct.pack("<H", 2)
        out += struct.pack("<HHII", 256, 4, 1, w) + struct.pack("<HHII", 257, 4, 1, h)
        out += struct.pack("<I", nxt)
    return bytes(out)


class AllPixels(unittest.TestCase):
    def test_a_multi_page_tiff_too_large_in_all(self):
        # (each picture under the cap of one: 195 megapixels)
        data = tiff_header([(15000, 13000)] * 40)
        with self.assertRaises(ScanError) as cm:
            net.check_image(data, 600)
        self.assertIn("megapixels in all", cm.exception.message)
        # a 100-page job of Letter pages at 600 dpi, in color, is fine
        page = net.check_image(tiff_header([(5100, 6600)] * 100), 600)
        self.assertEqual(len(page.sizes), 100)

    def test_build_pdf_refuses_before_decoding(self):
        from unittest import mock
        from kanzonas import scan_dialog
        page = net.Page(tiff_header([(15000, 13000)] * 40), "tiff", 600,
                        [(15000, 13000)] * 40)
        with mock.patch.object(scan_dialog.pymupdf, "open", wraps=scan_dialog.pymupdf.open) \
                as opened:
            with self.assertRaises(ScanError):
                scan_dialog.build_pdf([page])
        self.assertEqual([c for c in opened.call_args_list if c.kwargs.get("filetype")], [])


class Window(unittest.TestCase):
    def test_a_devices_name_is_shown_as_it_is(self):
        from PySide6.QtCore import Qt
        from kanzonas import scan_dialog
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.settings.remove("scan_device")
        dev = Device('<b>Big</b><img src="x.png">', "escl", "http://10.0.0.9/eSCL", "10.0.0.9")
        fake = FakeScanner(dev, [])
        dlg = scan_dialog.ScanDialog(w, discover=lambda cancel=None, log=None: ([], []),
                                     open_scanner=lambda d: fake)
        self.addCleanup(lambda: (dlg._stop(), dlg.deleteLater()))
        wait_for(lambda: "find" not in dlg._busy)
        dlg._say("Asking %s what it can do..." % dev.name)
        for label in (dlg.status, dlg.panel_note):
            self.assertEqual(label.textFormat(), Qt.PlainText)
        self.assertIn("<b>Big</b>", dlg.status.text())

    def test_a_watched_files_pictures_are_decoded_once(self):
        from unittest import mock
        from kanzonas import scan_dialog
        from kanzonas.main_window import MainWindow
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.settings.remove("scan_device")
        dlg = scan_dialog.ScanDialog(w, discover=lambda cancel=None, log=None: ([], []))
        self.addCleanup(lambda: (dlg._stop(), dlg.deleteLater()))
        wait_for(lambda: "find" not in dlg._busy)
        path = os.path.join(tempfile.mkdtemp(), "scan.png")
        with open(path, "wb") as f:
            f.write(picture(300, 400, "PNG"))
        decoded = []
        real = scan_dialog.pymupdf.open

        def opening(*a, **k):
            if k.get("filetype") not in (None, "pdf"):
                decoded.append(k["filetype"])
            return real(*a, **k)
        with mock.patch.object(scan_dialog.pymupdf, "open", opening):
            dlg._got_watch("ok", [(path, scan_local.read_watched(path), None)])
            self.assertEqual(decoded, ["png"])
            dlg.rb_new.setChecked(True)
            dlg.finish()
        self.assertEqual(decoded, ["png"])              # (not again at Done)
        doc = w.view().doc
        self.addCleanup(lambda: setattr(w.view(), "dirty", False))
        with scan_dialog.build_pdf([scan_local.read_watched(path)]) as want:   # (its own size)
            self.assertEqual([p.rect for p in doc], [p.rect for p in want])
            self.assertEqual(len(doc[0].get_images()), 1)


if __name__ == "__main__":
    unittest.main()

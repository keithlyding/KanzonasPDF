"""What the 1.9 break-it battery found in File > Scan, fixed:

- a page cut short (the device or the Wi-Fi dropped the connection mid-page) was taken as a
  scanned page, half a picture: http.client doesn't say a Content-Length wasn't met;
- Cancel while a page was arriving added the half that had come before it stopped;
- the listener for scans started on the printer's panel read and parsed a request from any
  computer on the network before refusing it, a thread for each (a host opening many slow
  connections piled threads up), and a chunk size of -1 read the request until the sender
  stopped, however much it sent;
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

from tests.test_scanning import (APP, ESCL_CAPS, Escl, ServerCase, picture,  # noqa: E402,F401
                                 serve)
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


if __name__ == "__main__":
    unittest.main()

"""TEMPORARY diagnostic (branch claude/mac-udp-probe only, never merged): the discovery test's
own path, timed. Always passes; prints what happened."""
import os
import select
import socket
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kanzonas import scan_escl, scan_net as net  # noqa: E402


class Probe2(unittest.TestCase):
    def test_print_discovery_trace(self):
        ev = []
        t0 = time.monotonic()

        def mark(what):
            ev.append("%.3f %s" % (time.monotonic() - t0, what))

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        s.settimeout(5)
        port = s.getsockname()[1]

        def run():
            try:
                for _ in range(2):
                    data, src = s.recvfrom(65535)
                    mark("responder got %d bytes from %s" % (len(data), src))
                    s.sendto(b"\x00" * 12, src)
            except OSError as e:
                mark("responder %r" % e)
        threading.Thread(target=run, daemon=True).start()

        real_select, real_sendto = select.select, socket.socket.sendto

        def sel(r, w, x, t=None):
            out = real_select(r, w, x, t)
            mark("select(%d socks, %.3f) -> %d ready" % (len(r), t or 0, len(out[0])))
            return out

        def sendto(self_, data, *a):
            n = real_sendto(self_, data, *a)
            mark("sendto %s from %s -> %s" % (a[-1], self_.getsockname(), n))
            return n
        log = []
        with mock.patch.object(select, "select", sel), \
                mock.patch.object(socket.socket, "sendto", sendto), \
                mock.patch.object(scan_escl, "MDNS", ("127.0.0.1", port)):
            mark("browse starts")
            found = scan_escl.browse(window=0.8, target="127.0.0.1", log=log)
            mark("browse returns %d, log %s" % (len(found), log))
        time.sleep(1.0)
        mark("after 1 s")
        print("\nDISCOVERY TRACE on %s\n  " % sys.platform + "\n  ".join(ev[:80]),
              file=sys.stderr, flush=True)

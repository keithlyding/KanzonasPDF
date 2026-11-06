"""File > Scan: scans started on the printer's own panel ("Scan to Computer", WSD).

Many WSD printers (the Dell E525w among them, probably) also, or only, scan when the scan is
started on the printer. For that the computer must be a destination on the printer's panel:

1. While the Scan window shows a WSD scanner, KanzonasPDF subscribes to the scanner's
   ScanAvailableEvent (WS-Eventing Subscribe, with a destination named "KanzonasPDF - <this
   computer's name>", for an hour, renewed at half time; Unsubscribe when the window closes).
2. A small HTTP listener waits for the printer's event on a free port of the network address
   that faces the printer.
3. The user picks that destination on the printer's panel and presses Scan: the printer sends
   ScanAvailableEvent, and the Scan window then scans as if Scan had been clicked, with the
   event's ScanIdentifier and the subscription's DestinationToken (scan_wsd.WsdScanner.scan).

The listener is as strict as everything else from the network: only POSTs from the printer's
own address, to a random path of this subscription, with its identifier when the printer
echoes it; at most 64 KB, parsed by scan_net.parse_xml (no DTDs, no entities). It only ever
reacts by asking that same printer for the pages.
"""

import secrets
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import scan_net as net
from . import scan_wsd
from .i18n import tr
from .scan_net import ScanError, child, descendants, text

MAX_EVENT = 65536
RENEW_MIN, RENEW_MAX = 60, 1800           # seconds between renewals


def local_ip_facing(ip):
    """This computer's address on the network that reaches ip (a UDP connect sends nothing)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, 9))
        return s.getsockname()[0]
    except OSError:
        raise ScanError(tr("This computer has no network that reaches {ip}.").format(ip=ip))
    finally:
        s.close()


def display_name():
    """The name the printer shows for this computer on its panel."""
    name = (socket.gethostname() or "").split(".")[0][:24]
    return "KanzonasPDF - " + name if name else "KanzonasPDF"


def _read_chunked(rfile, limit):
    out = b""
    for _ in range(10000):
        line = rfile.readline(100)
        size = line.split(b";")[0].strip() or b"0"
        # (only hex digits: int() also takes "-1", and read(-1) reads until the sender
        # stops, however much it sends)
        if size.strip(b"0123456789abcdefABCDEF"):
            raise ValueError("bad chunk size")
        size = int(size, 16)
        if size == 0:
            rfile.readline(100)
            return out
        if len(out) + size > limit:
            raise ValueError("too large")
        out += rfile.read(size)
        rfile.readline(10)
    raise ValueError("too many chunks")


class EventListener:
    """An HTTP server for one printer's events (WS-Eventing pushes them with POST)."""

    def __init__(self, printer_ip, on_message, bind_ip=None):
        self.printer_ip = printer_ip
        self.on_message = on_message
        self.path = "/kanzonas-scan/" + secrets.token_hex(16)
        self.identifier = "urn:uuid:" + str(uuid.uuid4())
        self.log = []
        listener = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 10                     # (a client that sends nothing is dropped)

            def log_message(self, *_a):
                pass

            def _reply(self, code):
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()

            def do_POST(self):
                code, message = listener.accept(self)
                listener.log.append("%s %s -> %d" % (self.client_address[0], self.path[:40],
                                                     code))
                try:
                    self._reply(code)
                except OSError:
                    pass
                if message is not None:
                    listener.on_message(*message)

            def _refuse(self):
                self._reply(405)
            do_GET = do_PUT = do_DELETE = do_HEAD = _refuse

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def verify_request(self, _request, client_address):
                # anyone else is turned away before anything is read, and before a thread
                # is started for them (the listener is on the network: a host sending
                # nothing, or slowly, on many connections mustn't pile threads up here)
                if client_address[0] == listener.printer_ip:
                    return True
                if len(listener.log) < 500:
                    listener.log.append("%s refused" % client_address[0])
                return False

        self.server = Server((bind_ip or local_ip_facing(printer_ip), 0), Handler)
        self._thread = None

    @property
    def url(self):
        host, port = self.server.server_address[:2]
        return net.make_url("http", host, port, self.path)

    def accept(self, h):
        """(HTTP status, (action, root) or None) for one POST."""
        if h.client_address[0] != self.printer_ip:
            return 403, None
        if h.path != self.path:
            return 404, None
        try:
            if "chunked" in (h.headers.get("Transfer-Encoding") or "").lower():
                body = _read_chunked(h.rfile, MAX_EVENT)
            else:
                size = h.headers.get("Content-Length") or ""
                if not size.isdigit():
                    return 411, None
                if int(size) > MAX_EVENT:
                    return 413, None
                body = h.rfile.read(int(size))
        except (ValueError, OSError):
            return 413, None
        try:
            root = net.parse_xml(body, limit=MAX_EVENT)
        except ScanError:
            return 400, None
        header = child(root, "Header")
        ident = text(header, "Identifier")
        if ident and ident != self.identifier:
            return 403, None
        return 202, (text(header, "Action").rsplit("/", 1)[-1], root)

    def start(self):
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True,
                                        name="kanzonas-scan-events")
        self._thread.start()

    def stop(self):
        if self._thread is not None:
            self.server.shutdown()
        self.server.server_close()


class PanelLink:
    """Keeps this computer listed on one WSD printer's panel while the Scan window is open.
    on_scan(scan_identifier, destination_token) and on_state(ok, error or None) are called
    from worker threads."""

    def __init__(self, device, on_scan, on_state, name=None, bind_ip=None):
        self.device = device
        self.host = device.host or net.split_url(device.address)[1]
        self.context = "kanzonas-" + secrets.token_hex(6)
        self.name = name or display_name()
        self.on_scan, self.on_state = on_scan, on_state
        self.bind_ip = bind_ip
        self.listener = None
        self.sub = None
        self.log = []
        self._timer = None
        self._lock = threading.Lock()
        self._stopped = False
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._start, daemon=True,
                                        name="kanzonas-scan-panel")
        self._thread.start()

    def _start(self):
        try:
            ip = net.resolve_host(self.host)
            listener = EventListener(ip, self._message, self.bind_ip)
            listener.start()
            with self._lock:
                stopped = self._stopped
                if not stopped:
                    self.listener = listener
            if stopped:
                listener.stop()
                return
            self._subscribe()
        except ScanError as ex:
            self.log.append("subscribe: %s" % (ex.details or ex.message))
            if not self._stopped:
                self.on_state(False, ex)
            self._close_listener()
            return
        except OSError as ex:
            err = ScanError(tr("Couldn't wait for the printer's scans: {error}").format(
                error=ex), repr(ex))
            self.log.append("listener: %r" % ex)
            if not self._stopped:
                self.on_state(False, err)
            return
        if not self._stopped:
            self.on_state(True, None)

    def _subscribe(self):
        sub = scan_wsd.subscribe(self.device.address, self.listener.url,
                                 self.listener.identifier, self.name, self.context)
        self.log.append("subscribed: notify %s, expires in %d s, manager %s" % (
            self.listener.url.split("/kanzonas-scan/")[0], sub["expires"], sub["manager"]))
        with self._lock:
            stopped = self._stopped
            if not stopped:
                self.sub = sub
        if stopped:                     # (the window closed meanwhile: don't stay listed)
            try:
                scan_wsd.unsubscribe(self.device.address, sub)
            except ScanError:
                pass
            return
        self._schedule(sub["expires"])

    def _schedule(self, secs):
        with self._lock:
            if self._stopped:
                return
            self._timer = threading.Timer(max(RENEW_MIN, min(RENEW_MAX, secs / 2)), self.renew)
            self._timer.daemon = True
            self._timer.start()

    def renew(self):
        if self._stopped:
            return
        try:
            if self.sub is None:
                raise ScanError("no subscription")
            self._schedule(scan_wsd.renew(self.device.address, self.sub))
            self.log.append("renewed")
        except ScanError:
            try:
                self._subscribe()               # (the printer forgot it: subscribe again)
            except ScanError as ex:
                self.log.append("subscribe again: %s" % (ex.details or ex.message))
                if not self._stopped:
                    self.on_state(False, ex)

    def _message(self, action, root):
        if self._stopped:
            return
        if action == "ScanAvailableEvent":
            ev = descendants(root, "ScanAvailableEvent")
            ctx = text(ev[0], "ClientContext") if ev else ""
            sid = text(ev[0], "ScanIdentifier") if ev else ""
            self.log.append("ScanAvailableEvent (%s)" % ("ours" if ctx == self.context
                                                         else "another context"))
            if ev and ctx == self.context and sid and self.sub is not None:
                self.on_scan(sid, self.sub["token"])
        elif action == "SubscriptionEnd":
            self.log.append("SubscriptionEnd")
            with self._lock:
                self.sub = None
            threading.Thread(target=self.renew, daemon=True).start()

    def _close_listener(self):
        with self._lock:
            listener, self.listener = self.listener, None
        if listener is not None:
            listener.stop()

    def stop(self, wait=False):
        """Unsubscribe and stop listening (in the background unless wait)."""
        with self._lock:
            self._stopped = True
            if self._timer is not None:
                self._timer.cancel()
            sub, self.sub = self.sub, None

        def end():
            if self._thread is not None:
                self._thread.join(15)
            if sub is not None:
                try:
                    scan_wsd.unsubscribe(self.device.address, sub)
                except ScanError:
                    pass
            self._close_listener()
        if wait:
            end()
        else:
            threading.Thread(target=end, daemon=True).start()

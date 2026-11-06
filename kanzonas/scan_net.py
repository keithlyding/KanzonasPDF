"""File > Scan: what the network scanners (eSCL in scan_escl.py, WSD in scan_wsd.py) share.

Everything that comes from the network is untrusted:
- XML is parsed with expat directly, refusing any DOCTYPE (so no entity declarations, no
  external entities, no entity expansion), with caps on its size, depth and element count.
- HTTP goes through http.client to the one device the user picked (no proxy, no cookies),
  every request with a time limit and a cap on the answer's size; a redirect is followed only
  to the same host, and a device's self-signed HTTPS certificate is accepted only for it.
- A picture's size is read from its header before anything decodes it, and refused when too
  large; pages per job are capped.
- Discovery sends one query from a port of our own and only reads answers to it, for a short
  window (see udp_exchange).

No Qt and no PyMuPDF here: this runs in a worker thread (scan_dialog.py), and the pages are
turned into PDF pages on the main thread.
"""

import http.client
import socket
import ssl
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit
from xml.sax.saxutils import escape

from .i18n import tr

CONNECT_TIMEOUT = 5.0          # seconds to reach a device
READ_TIMEOUT = 30.0            # seconds for an answer
PAGE_TIMEOUT = 180.0           # seconds for a page to be scanned and sent
MAX_XML = 2 * 1024 * 1024      # bytes of one XML answer
MAX_XML_DEPTH = 64
MAX_XML_ELEMENTS = 100_000
MAX_IMAGE = 300 * 1024 * 1024  # bytes of one scanned page (uncompressed TIFF at 600 dpi: ~100 MB)
MAX_PIXELS = 200_000_000       # a Letter page at 1200 dpi is 135 megapixels
MAX_SIDE = 40_000              # pixels
MAX_PAGES = 500                # pages in one job
# pixels of all the pictures in one file (a multi-page TIFF: each picture is checked against
# MAX_PIXELS, and 500 of them could each be that large, decoded on the main thread, a tiny
# file when compressed): a 100-page job of Letter pages at 600 dpi (5,100 x 6,600 pixels
# each) is 3.4 billion; 6 billion leaves room above it
MAX_TOTAL_PIXELS = 6_000_000_000
MAX_REDIRECTS = 3

PROTOCOLS = {"escl": "eSCL (AirScan)", "wsd": "WSD", "wia": "WIA", "sane": "SANE"}

# page sizes, inches (width, height); "max" is the whole area the scanner offers
PAGE_SIZES = {"letter": (8.5, 11.0), "legal": (8.5, 14.0), "a4": (210 / 25.4, 297 / 25.4),
              "max": None}
COMMON_DPI = (75, 100, 150, 200, 240, 300, 400, 600, 1200)


class ScanError(Exception):
    """A failure with a message for the user (plain words, what to do) and technical details
    for Copy details."""

    def __init__(self, message, details=""):
        super().__init__(message)
        self.message = message
        self.details = details


class Canceled(ScanError):
    def __init__(self):
        super().__init__(tr("Canceled."))


class NetError(ScanError):
    """Couldn't talk to the device. kind: refused | timeout | unreachable | tls | http."""

    def __init__(self, message, kind, details="", status=None):
        super().__init__(message, details)
        self.kind = kind
        self.status = status


class XmlRefused(ScanError):
    pass


# ---- the data passed around ----------------------------------------------------------------
@dataclass
class Device:
    name: str
    protocol: str                 # escl | wsd | wia | sane
    address: str                  # URL (escl: the eSCL root, wsd: the scan service) or device id
    host: str = ""                # what the list shows after the name (an IP address)
    alt: list = field(default_factory=list)    # other URLs of the same service (http / https)
    info: dict = field(default_factory=dict)   # what discovery found, for Copy details

    def key(self):
        return self.protocol + " " + self.address

    def label(self):
        how = PROTOCOLS.get(self.protocol, self.protocol)
        return "%s  (%s%s)" % (self.name, how, ", " + self.host if self.host else "")

    def to_dict(self):
        return {"name": self.name, "protocol": self.protocol, "address": self.address,
                "host": self.host, "alt": list(self.alt)}

    @classmethod
    def from_dict(cls, d):
        if not isinstance(d, dict) or d.get("protocol") not in PROTOCOLS or not d.get("address"):
            return None
        return cls(str(d.get("name") or d["address"]), d["protocol"], str(d["address"]),
                   str(d.get("host") or ""), [str(a) for a in d.get("alt") or []])


@dataclass
class SourceCaps:
    colors: list = field(default_factory=lambda: ["color", "gray", "bw"])
    resolutions: list = field(default_factory=lambda: [75, 150, 200, 300, 600])
    max_w: float = 8.5            # inches
    max_h: float = 11.69
    formats: list = field(default_factory=list)   # the protocol's own names
    extra: dict = field(default_factory=dict)     # anything else the protocol needs


@dataclass
class Caps:
    sources: dict = field(default_factory=dict)   # platen | feeder | duplex -> SourceCaps
    model: str = ""
    raw: str = ""                 # the device's own answer (for Copy details)


@dataclass
class ScanSettings:
    source: str = "platen"        # platen | feeder | duplex
    color: str = "color"          # color | gray | bw
    dpi: int = 300
    size: str = "letter"          # a PAGE_SIZES key


@dataclass
class Page:
    data: bytes
    kind: str                     # jpeg | png | tiff | bmp | pdf
    dpi: int
    sizes: list = field(default_factory=list)     # (width, height) pixels of each picture


def region(settings, src):
    """(width, height) in inches to scan: the page size, never more than the scanner offers."""
    size = PAGE_SIZES.get(settings.size)
    if size is None:
        return src.max_w, src.max_h
    return min(size[0], src.max_w), min(size[1], src.max_h)


def nearest(values, wanted):
    values = sorted(set(int(v) for v in values if v))
    if not values:
        return wanted
    return min(values, key=lambda v: (abs(v - wanted), -v))


# ---- XML, safely ----------------------------------------------------------------------------
def parse_xml(data, limit=MAX_XML):
    """An ElementTree element of untrusted XML. Tags are "{namespace}name". Refuses a DOCTYPE
    (and with it every entity declaration and external entity), more than MAX_XML_DEPTH
    levels or MAX_XML_ELEMENTS elements, and more than limit bytes."""
    import xml.parsers.expat as expat
    from xml.etree.ElementTree import Element
    if isinstance(data, str):
        data = data.encode("utf-8")
    if len(data) > limit:
        raise XmlRefused(tr("The scanner's answer was too large."),
                         "XML of %d bytes (limit %d)" % (len(data), limit))
    p = expat.ParserCreate(namespace_separator="}")
    p.buffer_text = True
    try:
        p.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    except AttributeError:
        pass
    root, stack, count = [], [], [0]

    def refuse(*_args):
        raise XmlRefused(tr("The scanner sent an answer KanzonasPDF won't read (it declares "
                            "entities)."), "DOCTYPE or entity declaration in XML")

    def qn(name):
        return "{" + name if "}" in name else name

    def start(name, attrs):
        count[0] += 1
        if count[0] > MAX_XML_ELEMENTS or len(stack) >= MAX_XML_DEPTH:
            raise XmlRefused(tr("The scanner's answer was too large."),
                             "XML too deep or too many elements")
        el = Element(qn(name), {qn(k): v for k, v in attrs.items()})
        if stack:
            stack[-1].append(el)
        elif root:
            raise XmlRefused(tr("The scanner's answer isn't valid XML."), "two root elements")
        else:
            root.append(el)
        stack.append(el)

    def end(_name):
        stack.pop()

    def chars(text):
        if not stack:
            return
        el = stack[-1]
        if len(el):
            el[-1].tail = (el[-1].tail or "") + text
        else:
            el.text = (el.text or "") + text

    p.StartDoctypeDeclHandler = refuse
    p.EntityDeclHandler = refuse
    p.UnparsedEntityDeclHandler = refuse
    p.NotationDeclHandler = refuse
    p.ExternalEntityRefHandler = refuse
    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chars
    try:
        p.Parse(data, True)
    except expat.ExpatError as ex:
        raise ScanError(tr("The scanner's answer isn't valid XML."), "XML: %s" % ex)
    if not root:
        raise ScanError(tr("The scanner's answer isn't valid XML."), "XML: no element")
    return root[0]


def local(tag):
    """A tag's name without its namespace (devices disagree on namespaces: match by name)."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def child(el, *path):
    """The first element down path (names without namespaces), or None."""
    for name in path:
        if el is None:
            return None
        el = next((c for c in el if local(c.tag) == name), None)
    return el


def children(el, name):
    return [] if el is None else [c for c in el if local(c.tag) == name]


def descendants(el, name):
    return [] if el is None else [c for c in el.iter() if local(c.tag) == name]


def text(el, *path, default=""):
    el = child(el, *path) if path else el
    if el is None or el.text is None:
        return default
    return el.text.strip()


def xml_escape(s):
    return escape(str(s), {'"': "&quot;"})


# ---- HTTP to one device -------------------------------------------------------------------
@dataclass
class Response:
    status: int
    headers: dict                  # lower-case names
    body: bytes
    url: str


def split_url(url):
    """(scheme, host, port, path) of an http(s) URL; ScanError for anything else."""
    try:
        p = urlsplit(url.strip())
        port = p.port
    except ValueError:
        raise ScanError(tr("{url} isn't a valid address.").format(url=url))
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ScanError(tr("{url} isn't a valid address.").format(url=url))
    port = port or (443 if p.scheme == "https" else 80)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    return p.scheme, p.hostname, port, path


def host_port(host, port, scheme):
    h = "[%s]" % host if ":" in host else host
    return h + ":%d" % port


def make_url(scheme, host, port, path):
    return "%s://%s%s" % (scheme, host_port(host, port, scheme), path if path.startswith("/")
                          else "/" + path)


class Http:
    """Requests to one device. Only its host is ever contacted: a full URL naming another
    host (a Location header, an address inside an answer) is taken for its path on this host,
    and a redirect elsewhere is refused. abort() (from another thread) stops a request."""

    def __init__(self, base_url):
        self.scheme, self.host, self.port, self.base_path = split_url(base_url)
        self._sock = None
        self._lock = threading.Lock()
        self.canceled = False
        self.log = []               # (method, url, status) of each request, for Copy details

    @property
    def base(self):
        return make_url(self.scheme, self.host, self.port, self.base_path)

    def url(self, path):
        """path (relative to the base, absolute, or a full URL) as a URL on this device."""
        if "://" in path:
            scheme, host, port, p = split_url(path)
            if scheme != self.scheme or host.lower() != self.host.lower():
                port = self.port        # (another host named: this device, as it was reached)
            return make_url(self.scheme, self.host, port, p)
        if path.startswith("/"):
            return make_url(self.scheme, self.host, self.port, path)
        base = self.base_path if self.base_path.endswith("/") else self.base_path + "/"
        return make_url(self.scheme, self.host, self.port, base + path)

    def abort(self):
        with self._lock:
            self.canceled = True
            sock = self._sock
        if sock is not None:
            try:
                # (the socket itself: http.client lets go of it once the answer's headers
                # are in, while the answer is still read from it; and under TLS the plain
                # shutdown, which a read in another thread then returns from)
                socket.socket.shutdown(sock, socket.SHUT_RDWR)
            except OSError:
                pass

    def request(self, method, path, body=None, headers=None, limit=MAX_XML,
                timeout=READ_TIMEOUT):
        url = self.url(path)
        for _hop in range(MAX_REDIRECTS + 1):
            r = self._once(method, url, body, headers, limit, timeout)
            if r.status in (301, 302, 303, 307, 308) and r.headers.get("location"):
                loc = r.headers["location"]
                if "://" in loc:
                    scheme, host, port, p = split_url(loc)
                    if host.lower() != self.host.lower():
                        raise NetError(tr("{host} sent KanzonasPDF to another address "
                                          "({other}); for safety it doesn't follow.").format(
                                              host=self.host, other=host), "http",
                                       "redirect to %s" % loc, r.status)
                    url = make_url(scheme, self.host, port, p)
                    self.scheme, self.port = scheme, port     # (http -> https on the device)
                else:
                    url = self.url(loc)
                if r.status == 303:
                    method, body = "GET", None
                continue
            return r
        raise NetError(tr("{host} kept redirecting.").format(host=self.host), "http")

    def _once(self, method, url, body, headers, limit, timeout):
        scheme, host, port, path = split_url(url)
        # (a path from the device, a job's Location say, with a space or a character beyond
        # ASCII in it: sent percent-encoded, as http.client refuses it as it is)
        path = quote(path, safe="/?&=%:@!$'()*+,;~-._[]")
        if self.canceled:
            raise Canceled()
        if scheme == "https":
            # Scanners use self-signed certificates; this connection only ever goes to the
            # device the user picked (or typed), so its certificate is accepted as it is.
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(host, port, timeout=CONNECT_TIMEOUT, context=ctx)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=CONNECT_TIMEOUT)
        hdrs = {"Host": host_port(host, port, scheme),      # (some devices want the port)
                "User-Agent": "KanzonasPDF", "Accept": "*/*", "Connection": "close"}
        hdrs.update(headers or {})
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            try:
                conn.connect()
                conn.sock.settimeout(timeout)
                with self._lock:
                    self._sock = conn.sock
                if self.canceled:
                    raise Canceled()
                conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
                for k, v in hdrs.items():
                    conn.putheader(k, v)
                if body is not None:
                    conn.putheader("Content-Length", str(len(body)))
                conn.endheaders(body)
                resp = conn.getresponse()
                rh = {k.lower(): v for k, v in resp.getheaders()}
                size = rh.get("content-length", "")
                if size.isdigit() and int(size) > limit:
                    raise ScanError(tr("The scanner's answer was too large."),
                                    "%s: Content-Length %s > %d" % (url, size, limit))
                chunks, got = [], 0
                while True:
                    part = resp.read(65536)
                    if not part:
                        break
                    got += len(part)
                    if got > limit:
                        raise ScanError(tr("The scanner's answer was too large."),
                                        "%s: more than %d bytes" % (url, limit))
                    chunks.append(part)
                # (Cancel shuts the connection down, which reads as the end of the answer;
                # a device that drops the connection mid-page reads the same: http.client
                # doesn't say a Content-Length was cut short, and half a picture opens)
                if self.canceled:
                    raise Canceled()
                if size.isdigit() and got < int(size):
                    raise NetError(tr("The connection to {host} was cut before the scanner's "
                                      "answer was complete.").format(host=host), "unreachable",
                                   "%s %s: %d of %s bytes" % (method, url, got, size))
                self.log.append((method, url, resp.status))
                return Response(resp.status, rh, b"".join(chunks), url)
            except ScanError:
                raise
            except (OSError, http.client.HTTPException) as ex:
                if self.canceled:           # (whatever a connection shut down gives)
                    raise Canceled()
                if isinstance(ex, ConnectionRefusedError):
                    raise NetError(tr("{host} refused the connection on port {port}.").format(
                        host=host, port=port), "refused", "%s %s: %s" % (method, url, ex))
                if isinstance(ex, (socket.timeout, TimeoutError)):
                    raise NetError(tr("{host} didn't answer in time.").format(host=host),
                                   "timeout", "%s %s: %s" % (method, url, ex))
                if isinstance(ex, ssl.SSLError):
                    raise NetError(tr("A secure connection to {host} failed.").format(
                        host=host), "tls", "%s %s: %s" % (method, url, ex))
                raise NetError(tr("Couldn't reach {host}: {error}").format(host=host, error=ex),
                               "unreachable", "%s %s: %r" % (method, url, ex))
        finally:
            with self._lock:
                self._sock = None
            conn.close()


# ---- pictures: their size from the header, before anything decodes them ------------------
def image_kind(data):
    head = bytes(data[:8])
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head.startswith(b"BM"):
        return "bmp"
    if head.startswith(b"%PDF-"):
        return "pdf"
    return None


def _jpeg_size(d):
    i, n = 2, len(d)
    for _ in range(10000):
        while i < n and d[i] != 0xFF:
            i += 1
        while i < n and d[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = d[i]
        i += 1
        if marker in (0x01,) or 0xD0 <= marker <= 0xD9:
            continue
        if i + 2 > n:
            break
        length = struct.unpack(">H", d[i:i + 2])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE,
                      0xCF) and i + 7 <= n:
            h, w = struct.unpack(">HH", d[i + 3:i + 7])
            return [(w, h)]
        i += length
    return []


def _tiff_sizes(d):
    end = "<" if d[:2] == b"II" else ">"
    out, seen = [], set()
    off = struct.unpack(end + "I", d[4:8])[0]
    while off and off not in seen and len(out) <= MAX_PAGES:
        seen.add(off)
        if off + 2 > len(d):
            break
        count = struct.unpack(end + "H", d[off:off + 2])[0]
        w = h = 0
        for k in range(count):
            e = off + 2 + 12 * k
            if e + 12 > len(d):
                break
            tag, typ = struct.unpack(end + "HH", d[e:e + 4])
            if tag in (256, 257):
                val = struct.unpack(end + ("H" if typ == 3 else "I"),
                                    d[e + 8:e + 10] if typ == 3 else d[e + 8:e + 12])[0]
                if tag == 256:
                    w = val
                else:
                    h = val
        out.append((w, h))
        nxt = off + 2 + 12 * count
        if nxt + 4 > len(d):
            break
        off = struct.unpack(end + "I", d[nxt:nxt + 4])[0]
    return out


def image_sizes(data, kind):
    """[(width, height)] in pixels of each picture in data (several for a multi-page TIFF);
    [] when the header can't be read (a PDF has none)."""
    d = memoryview(data).tobytes() if not isinstance(data, bytes) else data
    try:
        if kind == "jpeg":
            return _jpeg_size(d)
        if kind == "png" and len(d) >= 24:
            return [struct.unpack(">II", d[16:24])]
        if kind == "tiff":
            return _tiff_sizes(d)
        if kind == "bmp" and len(d) >= 26:
            w, h = struct.unpack("<ii", d[18:26])
            return [(abs(w), abs(h))]
    except struct.error:
        pass
    return []


def bare_dib_to_bmp(data):
    """WSD's "dib" format can be a bitmap without its file header: add one."""
    if data[:2] == b"BM" or len(data) < 40:
        return data
    hdr = struct.unpack("<I", data[:4])[0]
    if hdr not in (40, 52, 56, 108, 124):
        return data
    bits = struct.unpack("<H", data[14:16])[0]
    compression = struct.unpack("<I", data[16:20])[0]
    used = struct.unpack("<I", data[32:36])[0]
    colors = used or (1 << bits if bits <= 8 else 0)
    masks = 12 if hdr == 40 and compression == 3 else 0
    offset = 14 + hdr + masks + 4 * colors
    return b"BM" + struct.pack("<IHHI", 14 + len(data), 0, 0, offset) + data


def check_image(data, dpi):
    """A Page of a scanned picture, its size read from its header and checked: ScanError when
    it isn't a picture KanzonasPDF reads (JPEG, PNG, TIFF, BMP, PDF) or is too large."""
    if len(data) > MAX_IMAGE:
        raise ScanError(tr("A scanned page was too large ({mb} MB).").format(
            mb=len(data) // (1024 * 1024)))
    if data[:2] != b"BM" and image_kind(data) is None:
        data = bare_dib_to_bmp(data)
    kind = image_kind(data)
    if kind is None:
        raise ScanError(tr("The scanner sent a page in a format KanzonasPDF doesn't read."),
                        "first bytes: %r" % bytes(data[:16]))
    sizes = image_sizes(data, kind)
    if kind != "pdf":
        if not sizes or any(w <= 0 or h <= 0 for w, h in sizes):
            raise ScanError(tr("A scanned page couldn't be read."), "%s without a size" % kind)
        if len(sizes) > MAX_PAGES:
            raise ScanError(tr("Too many pages in one scan (more than {n}).").format(n=MAX_PAGES))
        for w, h in sizes:
            if w > MAX_SIDE or h > MAX_SIDE or w * h > MAX_PIXELS:
                raise ScanError(tr("A scanned page was too large ({w} x {h} pixels): choose a "
                                   "lower resolution.").format(w=w, h=h))
        check_total(sizes)
    return Page(bytes(data), kind, int(dpi or 0), sizes)


def check_total(sizes):
    """ScanError when the pictures of one file [(width, height)] have more than
    MAX_TOTAL_PIXELS pixels in all."""
    total = sum(int(w) * int(h) for w, h in sizes)
    if total > MAX_TOTAL_PIXELS:
        raise ScanError(tr("The scanned file is too large: its {n} pages have {mp} "
                           "megapixels in all (at most {most}). Scan fewer pages at a time, "
                           "or at a lower resolution.").format(
                               n=len(sizes), mp=total // 1_000_000,
                               most=MAX_TOTAL_PIXELS // 1_000_000),
                        "%d pixels in %d pictures" % (total, len(sizes)))


# ---- discovery over UDP --------------------------------------------------------------------
def local_ipv4():
    """This computer's IPv4 addresses (not loopback), to send discovery out of each network."""
    addrs = set()
    if sys.platform.startswith("linux"):
        try:
            import fcntl
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                for _i, name in socket.if_nameindex():
                    try:
                        r = fcntl.ioctl(s.fileno(), 0x8915,       # SIOCGIFADDR
                                        struct.pack("256s", name[:15].encode()))
                        addrs.add(socket.inet_ntoa(r[20:24]))
                    except OSError:
                        pass
            finally:
                s.close()
        except (ImportError, OSError):
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    try:
        # the address of the default route (a UDP connect sends nothing)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("192.0.2.1", 9))
            addrs.add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127.") and a != "0.0.0.0")


def udp_exchange(sends, window, multicast_ttl=1, interfaces=None, max_packets=512,
                 cancel=None):
    """Send each (payload, (address, port), delay seconds) from a port of our own on every local
    network (multicast) or once (a unicast address), then read the answers that come back to
    that port for `window` seconds. [(data, sender IP)]. Nothing listens on a well-known port,
    so only answers to these queries arrive."""
    socks = []
    ifaces = interfaces if interfaces is not None else (local_ipv4() or ["0.0.0.0"])
    multicast = any(_is_multicast(dest[0]) for _p, dest, _d in sends)
    for addr in (ifaces if multicast else ["0.0.0.0"]):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setblocking(False)
            s.bind((addr, 0))
            if addr != "0.0.0.0":
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(addr))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, multicast_ttl)
            socks.append(s)
        except OSError:
            continue
    out = []
    try:
        if not socks:
            return out
        import select
        start = time.monotonic()
        pending = sorted(sends, key=lambda s: s[2])
        while True:
            now = time.monotonic() - start
            while pending and pending[0][2] <= now:
                payload, dest, _d = pending.pop(0)
                for s in socks:
                    try:
                        s.sendto(payload, dest)
                    except OSError:
                        pass
            if now >= window or len(out) >= max_packets or (cancel and cancel()):
                break
            wait = min(window - now, (pending[0][2] - now) if pending else 0.2, 0.2)
            ready, _w, _x = select.select(socks, [], [], max(0.0, wait))
            for s in ready:
                try:
                    data, src = s.recvfrom(65535)
                except OSError:
                    continue
                out.append((data, src[0]))
    finally:
        for s in socks:
            s.close()
    return out


def _is_multicast(addr):
    try:
        return 224 <= int(addr.split(".")[0]) <= 239
    except ValueError:
        return False


def resolve_host(name):
    """The IPv4 address of a host name (or the address itself)."""
    try:
        socket.inet_aton(name)
        if name.count(".") == 3:
            return name
    except OSError:
        pass
    try:
        return socket.getaddrinfo(name, None, socket.AF_INET)[0][4][0]
    except (OSError, IndexError):
        raise ScanError(tr("Couldn't find the address of {host}: check the name, or type the "
                           "printer's IP address (on its panel or network report).").format(
                               host=name))

"""File > Scan: WSD, Microsoft's Web Services on Devices: WS-Discovery to find the device,
WS-MetadataExchange to find its scan service, then WS-Scan (SOAP 1.2 over HTTP).

- WS-Discovery: a Probe (SOAP over UDP to 239.255.255.250:3702, or straight to a typed address)
  from a port of our own; ProbeMatches come back to that port. Only answers whose RelatesTo is
  one of our probes are read. A device that doesn't answer UDP can still be asked over HTTP at
  its "stable" discovery address (a directed probe).
- Metadata: a WS-Transfer Get to the device's address (XAddrs) lists the services it hosts;
  the one with ScannerServiceType is the scanner.
- WS-Scan: GetScannerElements (capabilities, status), CreateScanJob (a ScanTicket), then
  RetrieveImage per page (the picture comes as an MTOM/XOP attachment, a multipart/related
  answer) until the ClientErrorNoImagesAvailable fault, and CancelJob to stop.

Written from Microsoft's "Scan Service (WS-Scan) Schema" reference
(https://learn.microsoft.com/windows-hardware/drivers/image/wsd-scan-service-schema) and the
real devices' habits documented by sane-airscan (https://github.com/alexpevzner/sane-airscan,
read as a reference, no code taken): JobInformation filled in (some Canons need it), one
picture asked from the glass and "all" from the feeder, sizes some Kyoceras send turned,
ServerErrorNotAcceptingJobs from devices that only scan from their own panel.

Every address a device names is used only on the device that answered: its host is replaced
by the address the answer came from.
"""

import time
import uuid
from urllib.parse import unquote

from . import scan_net as net
from .i18n import tr
from .scan_net import (Caps, Device, ScanError, SourceCaps, child, children, descendants,
                       parse_xml, text, xml_escape)

NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"
NS_WSA = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
NS_WSD = "http://schemas.xmlsoap.org/ws/2005/04/discovery"
NS_WSDP = "http://schemas.xmlsoap.org/ws/2006/02/devprof"
NS_SCAN = "http://schemas.microsoft.com/windows/2006/08/wdp/scan"
NS_WSE = "http://schemas.xmlsoap.org/ws/2004/08/eventing"
ANONYMOUS = "http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous"
PROBE = "http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe"
TRANSFER_GET = "http://schemas.xmlsoap.org/ws/2004/09/transfer/Get"
DISCOVERY_TO = "urn:schemas-xmlsoap-org:ws:2005:04:discovery"
MULTICAST = ("239.255.255.250", 3702)
STABLE_PATH = "/StableWSDiscoveryEndpoint/schemas-xmlsoap-org_ws_2005_04_discovery"
SOAP_TYPE = "application/soap+xml; charset=utf-8"

COLORS = {"color": "RGB24", "gray": "Grayscale8", "bw": "BlackAndWhite1"}
ENTRY_COLORS = {"RGB24": "color", "RGB48": "color", "Grayscale8": "gray", "Grayscale16": "gray",
                "BlackAndWhite1": "bw"}
FORMATS = {"color": ("jfif", "exif", "png", "tiff-single-uncompressed", "dib", "pdf-a"),
           "gray": ("jfif", "exif", "png", "tiff-single-uncompressed", "dib", "pdf-a"),
           "bw": ("png", "tiff-single-g4", "tiff-single-g3mh", "tiff-single-uncompressed", "dib",
                  "jfif", "exif", "pdf-a")}
SOURCES = {"platen": "Platen", "feeder": "ADF", "duplex": "ADFDuplex"}
MAX_PARTS = 16


def _id():
    return "urn:uuid:" + str(uuid.uuid4())


def envelope(action, to, body, msg_id=None, extra_ns="", headers=""):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<soap:Envelope xmlns:soap="%s" xmlns:wsa="%s" xmlns:wscn="%s" xmlns:wse="%s"%s>'
            "<soap:Header><wsa:To>%s</wsa:To><wsa:Action>%s</wsa:Action>"
            "<wsa:MessageID>%s</wsa:MessageID><wsa:ReplyTo><wsa:Address>%s</wsa:Address>"
            "</wsa:ReplyTo>%s</soap:Header><soap:Body>%s</soap:Body></soap:Envelope>" % (
                NS_SOAP, NS_WSA, NS_SCAN, NS_WSE, extra_ns, xml_escape(to), xml_escape(action),
                msg_id or _id(), ANONYMOUS, headers, body))


def probe_xml(msg_id, types):
    return envelope(PROBE, DISCOVERY_TO, "<wsd:Probe><wsd:Types>%s</wsd:Types></wsd:Probe>"
                    % types, msg_id, ' xmlns:wsd="%s" xmlns:wsdp="%s"' % (NS_WSD, NS_WSDP))


def parse_probe_matches(data, ids):
    """[{address, types, xaddrs}] from a ProbeMatches answer to one of our probes (ids)."""
    try:
        root = parse_xml(data, limit=65536)
    except ScanError:
        return []
    header = child(root, "Header")
    relates = text(header, "RelatesTo")
    if relates and relates not in ids:
        return []
    out = []
    for m in descendants(child(root, "Body"), "ProbeMatch")[:32]:
        out.append({"address": text(m, "EndpointReference", "Address"),
                    "types": text(m, "Types"),
                    "xaddrs": text(m, "XAddrs").split()[:8]})
    return out


def on_host(url, host):
    """url with its host replaced by host (the address that answered)."""
    scheme, _h, port, path = net.split_url(url)
    return net.make_url(scheme, host, port, path)


def _xaddr(xaddrs, host):
    urls = [u for u in xaddrs if u.lower().startswith(("http://", "https://"))]
    if not urls:
        return None
    try:
        best = next((u for u in urls if net.split_url(u)[1] == host), urls[0])
        return on_host(best, host)
    except ScanError:
        return None


def metadata(url, endpoint, timeout=6.0):
    """What a device's metadata says: {model, manufacturer, name, scan: [service URLs],
    printer: bool, raw}. The service URLs are on the device's own host."""
    h = net.Http(url)
    r = h.request("POST", url, envelope(TRANSFER_GET, endpoint or url, ""),
                  {"Content-Type": SOAP_TYPE}, timeout=timeout)
    if r.status != 200:
        raise net.NetError(tr("{host} answered the device question with an error (HTTP "
                              "{status}).").format(host=h.host, status=r.status), "http",
                           "metadata %s: HTTP %d" % (url, r.status), r.status)
    root = parse_xml(r.body)
    out = {"model": text(descendants(root, "ModelName")[0]) if descendants(root, "ModelName")
           else "",
           "manufacturer": text(descendants(root, "Manufacturer")[0])
           if descendants(root, "Manufacturer") else "",
           "name": text(descendants(root, "FriendlyName")[0])
           if descendants(root, "FriendlyName") else "",
           "scan": [], "printer": False, "raw": r.body.decode("utf-8", "replace")}
    for hosted in descendants(root, "Hosted")[:16]:
        types = text(hosted, "Types")
        if "PrintDeviceType" in types or "PrinterServiceType" in types:
            out["printer"] = True
        if "ScannerServiceType" not in types:
            continue
        for ref in children(hosted, "EndpointReference"):
            addr = text(ref, "Address")
            if addr.lower().startswith(("http://", "https://")):
                try:
                    out["scan"].append(on_host(addr, h.host))
                except ScanError:
                    pass
    return out


def _device_name(meta, fallback):
    maker, model = meta.get("manufacturer") or "", meta.get("model") or ""
    if maker and model.lower().startswith(maker.lower()):
        maker = ""                  # ("Dell" and "Dell Color MFP E525w")
    name = meta.get("name") or " ".join(x for x in (maker, model) if x)
    return (name or fallback)[:120]


def discover(window=3.0, cancel=None, target=None, log=None, interfaces=None):
    """(WSD scanners, printers that answered without a scan service) on the local network, or
    only at `target` (an IP address, asked directly)."""
    ids = [_id(), _id()]
    dest = (target, MULTICAST[1]) if target else MULTICAST
    scan_probe = probe_xml(ids[0], "wscn:ScanDeviceType").encode()
    any_probe = probe_xml(ids[1], "wsdp:Device").encode()
    sends = [(scan_probe, dest, 0.0), (any_probe, dest, 0.15), (scan_probe, dest, 0.5)]
    got = net.udp_exchange(sends, window, multicast_ttl=1, cancel=cancel, interfaces=interfaces,
                           log=log)
    matches = {}
    for data, src in got:
        for m in parse_probe_matches(data, ids):
            key = (m["address"] or src, src)
            if key not in matches:
                matches[key] = dict(m, host=src)
    if log is not None:
        log.append("WS-Discovery %s: %d answer(s) from %d device(s)%s" % (
            target or "multicast", len(got), len(matches),
            "".join(" [%s %s]" % (m["host"], m["types"]) for m in list(matches.values())[:20])))
    return from_matches(list(matches.values()), log, cancel, any_type=bool(target))


def from_matches(matches, log=None, cancel=None, any_type=False):
    """Devices from ProbeMatches ({address, types, xaddrs, host}): asks each one that may scan
    for its metadata (several at once)."""
    wanted = [m for m in matches if any_type or "ScanDeviceType" in m["types"]
              or "PrintDeviceType" in m["types"]][:32]
    if not wanted:
        return [], []
    from concurrent.futures import ThreadPoolExecutor

    def ask(m):
        url = _xaddr(m["xaddrs"], m["host"])
        if url is None:
            return m, None, "no XAddrs"
        if cancel and cancel():
            return m, None, "canceled"
        try:
            return m, metadata(url, m["address"]), url
        except ScanError as ex:
            return m, None, "%s: %s" % (url, ex.details or ex.message)
    scanners, printers = [], []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for m, meta, note in pool.map(ask, wanted):
            if meta is None:
                if log is not None:
                    log.append("WSD %s: metadata failed: %s" % (m["host"], note))
                if "ScanDeviceType" in m["types"]:
                    # a scanner that didn't give its metadata: its own address may serve
                    url = _xaddr(m["xaddrs"], m["host"])
                    if url:
                        scanners.append(Device(m["host"], "wsd", url, m["host"], [],
                                               {"endpoint": m["address"], "types": m["types"],
                                                "metadata": note}))
                continue
            name = _device_name(meta, m["host"])
            if log is not None:
                log.append("WSD %s: %s; scan service: %s" % (
                    m["host"], name, ", ".join(meta["scan"]) or "none"))
            if meta["scan"]:
                scanners.append(Device(name, "wsd", meta["scan"][0], m["host"], meta["scan"][1:],
                                       {"endpoint": m["address"], "types": m["types"],
                                        "model": meta["model"],
                                        "manufacturer": meta["manufacturer"],
                                        "metadata": meta["raw"][:20000]}))
            else:
                printers.append(Device(name, "wsd", note, m["host"], [],
                                       {"types": m["types"], "model": meta["model"]}))
    return scanners, printers


def directed_probe(host, log=None, timeout=4.0):
    """Ask a device for its WSD address over HTTP (when UDP doesn't get through)."""
    ids = [_id()]
    out = []
    for port in (80, 5357):
        url = net.make_url("http", host, port, STABLE_PATH)
        try:
            r = net.Http(url).request("POST", STABLE_PATH, probe_xml(ids[0], "wsdp:Device"),
                                      {"Content-Type": SOAP_TYPE}, limit=65536, timeout=timeout)
        except ScanError as ex:
            if log is not None:
                log.append("WSD directed probe %s: %s" % (url, ex.details or ex.message))
            continue
        if log is not None:
            log.append("WSD directed probe %s: HTTP %d" % (url, r.status))
        if r.status == 200:
            out = [dict(m, host=host) for m in parse_probe_matches(r.body, ids)]
            if out:
                break
    return out


# ---- MTOM (the picture attached to RetrieveImage's answer) --------------------------------
def _params(ctype):
    out = {}
    for item in ctype.split(";")[1:]:
        k, _eq, v = item.strip().partition("=")
        if k:
            out[k.strip().lower()] = v.strip().strip('"')
    return out


def _cid(value):
    return unquote(value.strip().strip("<>").strip()).lower()


def parse_multipart(body, ctype):
    """(SOAP root element, attachment bytes or None) of a multipart/related (MTOM) answer."""
    params = _params(ctype)
    boundary = params.get("boundary")
    if not boundary:
        raise ScanError(tr("The scanner's answer couldn't be read."), "multipart without boundary")
    delim = b"--" + boundary.encode("latin-1")
    pieces = body.split(delim)
    parts = []
    for raw in pieces[1:]:
        if raw.startswith(b"--"):
            break
        if len(parts) >= MAX_PARTS:
            raise ScanError(tr("The scanner's answer couldn't be read."), "too many MIME parts")
        raw = raw[2:] if raw.startswith(b"\r\n") else raw[1:] if raw.startswith(b"\n") else raw
        cut, gap = raw.find(b"\r\n\r\n"), 4
        if cut < 0:
            cut, gap = raw.find(b"\n\n"), 2
        if cut < 0:
            continue
        headers = {}
        for line in raw[:cut].decode("latin-1").splitlines():
            k, _c, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
        content = raw[cut + gap:]
        if content.endswith(b"\r\n"):
            content = content[:-2]
        elif content.endswith(b"\n"):
            content = content[:-1]
        parts.append((headers, content))
    if not parts:
        raise ScanError(tr("The scanner's answer couldn't be read."), "no MIME parts")
    start = _cid(params.get("start", ""))
    root_i = next((i for i, (h, _c) in enumerate(parts)
                   if start and _cid(h.get("content-id", "")) == start), 0)
    root = parse_xml(parts[root_i][1])
    others = [(h, c) for i, (h, c) in enumerate(parts) if i != root_i]
    att = None
    for inc in descendants(root, "Include"):
        href = inc.get("href", "")
        if href.lower().startswith("cid:"):
            want = _cid(href[4:])
            att = next((c for h, c in others if _cid(h.get("content-id", "")) == want), None)
            if att is not None:
                break
    if att is None and others:
        att = others[0][1]
    return root, att


class WsdFault(ScanError):
    def __init__(self, code, reason, status=None):
        super().__init__(fault_message(code), "SOAP fault %s (%s), HTTP %s" % (
            code, reason, status))
        self.code = code


def fault_of(root):
    """(subcode, reason) of a SOAP fault ("ClientErrorNoImagesAvailable"), or None."""
    fault = descendants(root, "Fault")
    if not fault:
        return None
    f = fault[0]
    code = ""
    values = descendants(child(f, "Code"), "Value")
    if values:
        code = text(values[-1])
    code = code or text(f, "faultcode")
    return code.rsplit(":", 1)[-1], (text(descendants(f, "Text")[0]) if descendants(f, "Text")
                                     else text(f, "faultstring"))


def fault_message(code, reasons=()):
    reasons = set(reasons)
    if reasons & {"CoverOpen", "InterlockOpen"}:
        return tr("A cover of the scanner is open: close it and try again.")
    if reasons & {"MediaJam", "MultipleFeedError"}:
        return tr("Paper is jammed in the document feeder: clear it (see the printer's panel) "
                  "and try again.")
    if "AttentionRequired" in reasons:
        return tr("The scanner needs attention: check the message on its panel.")
    if code in ("ServerErrorNotAcceptingJobs", "ClientErrorInvalidScanIdentifier",
                "ClientErrorInvalidDestinationToken"):
        return tr("The scanner isn't taking a scan from the computer right now. Check that it "
                  "isn't busy or showing a message. Some printers only take a WSD scan started on "
                  "their own panel: choose Scan, then to Computer (WSD), then click Scan here.")
    if code in ("ClientErrorNoImagesAvailable", "ServerErrorNoImagesAvailable"):
        return tr("The scanner had no page to send: put the page on the glass or in the "
                  "feeder and try again.")
    if code in ("ClientErrorFormatNotSupported", "ClientErrorInvalidArgs", "InvalidArgs",
                "ClientErrorConflictingRequiredParameters", "ClientErrorInvalidScanTicket"):
        return tr("The scanner refused these settings: try another resolution, color or "
                  "source.")
    if code in ("ClientErrorJobCancelled",):
        return tr("The scan was canceled on the scanner.")
    return tr("The scanner reported an error ({code}).").format(code=code or "?")


def _sizes(el, prefix):
    def wh(name):
        w, h = text(el, name, "Width"), text(el, name, "Height")
        return (int(w), int(h)) if w.isdigit() and h.isdigit() else None
    return wh(prefix + "MinimumSize"), wh(prefix + "MaximumSize")


def _source(el, prefix, formats):
    if el is None:
        return None
    res = child(el, prefix + "Resolutions")
    ws = {int(text(w)) for w in descendants(child(res, "Widths"), "Width") if text(w).isdigit()}
    hs = {int(text(h)) for h in descendants(child(res, "Heights"), "Height") if text(h).isdigit()}
    dpis = sorted(v for v in (ws & hs if hs else ws) if 0 < v <= 4800)
    colors = []
    for e in descendants(child(el, prefix + "Color"), "ColorEntry"):
        c = ENTRY_COLORS.get(text(e))
        if c and c not in colors:
            colors.append(c)
    src = SourceCaps(colors=[c for c in ("color", "gray", "bw") if c in colors] or ["color"],
                     resolutions=dpis or [300], formats=list(formats) or ["jfif"])
    _lo, hi = _sizes(el, prefix)
    if hi and hi[0] > 0 and hi[1] > 0:
        w, h = hi
        if w > h:              # (some devices send them the other way around)
            w, h = h, w
        src.max_w, src.max_h = w / 1000.0, h / 1000.0
    return src


def parse_elements(root, raw=""):
    """Caps (and the status) from a GetScannerElements answer."""
    config = descendants(root, "ScannerConfiguration")
    if not config:
        raise ScanError(tr("The scanner didn't describe what it can do."),
                        "no ScannerConfiguration in GetScannerElementsResponse")
    config = config[0]
    formats = [text(f) for f in descendants(child(config, "DeviceSettings"), "FormatValue")]
    caps = Caps(raw=raw)
    names = descendants(root, "ScannerName")
    caps.model = text(names[0]) if names else ""
    platen = _source(child(config, "Platen"), "Platen", formats)
    if platen:
        caps.sources["platen"] = platen
    adf = child(config, "ADF")
    front = _source(child(adf, "ADFFront"), "ADF", formats)
    if front:
        caps.sources["feeder"] = front
        if text(adf, "ADFSupportsDuplex").lower() in ("true", "1"):
            caps.sources["duplex"] = front
    if not caps.sources:
        raise ScanError(tr("The scanner didn't say what it can scan from."),
                        "no Platen or ADFFront in ScannerConfiguration")
    return caps


def parse_status(root):
    """(ScannerState, [ScannerStateReason])."""
    st = descendants(root, "ScannerStatus")
    if not st:
        return "", []
    return text(st[0], "ScannerState"), [text(r) for r in descendants(st[0],
                                                                      "ScannerStateReason")]


def ticket_xml(source, color, dpi, width, height, fmt, images, scan_id=None, dest_token=None):
    """A CreateScanJobRequest; width and height in 1/1000 inch. No MustHonor: the device may
    adjust what it can't do exactly. scan_id and dest_token: for a scan started on the
    printer's panel (its ScanAvailableEvent and our subscription's DestinationToken)."""
    panel = ""
    if scan_id:
        panel = ("<wscn:ScanIdentifier>%s</wscn:ScanIdentifier>" % xml_escape(scan_id) +
                 ("<wscn:DestinationToken>%s</wscn:DestinationToken>" % xml_escape(dest_token)
                  if dest_token else ""))
    side = ("<wscn:ColorProcessing>%s</wscn:ColorProcessing>"
            "<wscn:Resolution><wscn:Width>%d</wscn:Width><wscn:Height>%d</wscn:Height>"
            "</wscn:Resolution><wscn:ScanRegion><wscn:ScanRegionXOffset>0"
            "</wscn:ScanRegionXOffset><wscn:ScanRegionYOffset>0</wscn:ScanRegionYOffset>"
            "<wscn:ScanRegionWidth>%d</wscn:ScanRegionWidth><wscn:ScanRegionHeight>%d"
            "</wscn:ScanRegionHeight></wscn:ScanRegion>" % (color, dpi, dpi, width, height))
    sides = "<wscn:MediaFront>%s</wscn:MediaFront>" % side
    if source == "ADFDuplex":
        sides += "<wscn:MediaBack>%s</wscn:MediaBack>" % side
    return ("<wscn:CreateScanJobRequest>%s<wscn:ScanTicket><wscn:JobDescription>"
            "<wscn:JobName>KanzonasPDF scan</wscn:JobName>"
            "<wscn:JobOriginatingUserName>KanzonasPDF</wscn:JobOriginatingUserName>"
            "<wscn:JobInformation>KanzonasPDF</wscn:JobInformation></wscn:JobDescription>"
            "<wscn:DocumentParameters><wscn:Format>%s</wscn:Format>"
            "<wscn:ImagesToTransfer>%d</wscn:ImagesToTransfer>"
            "<wscn:InputSize><wscn:InputMediaSize><wscn:Width>%d</wscn:Width>"
            "<wscn:Height>%d</wscn:Height></wscn:InputMediaSize></wscn:InputSize>"
            "<wscn:InputSource>%s</wscn:InputSource><wscn:MediaSides>%s</wscn:MediaSides>"
            "</wscn:DocumentParameters></wscn:ScanTicket></wscn:CreateScanJobRequest>" % (
                panel, xml_escape(fmt), images, width, height, source, sides))


class WsdScanner:
    """One WS-Scan service (the device the user picked)."""

    protocol = "wsd"

    def __init__(self, device, sleep=time.sleep):
        self.device = device
        self.http = net.Http(device.address)
        self.caps = None
        self.sleep = sleep
        self.trail = []

    def abort(self):
        self.http.abort()

    def call(self, action, body, http=None, limit=net.MAX_XML, timeout=net.READ_TIMEOUT):
        """(answer's root element, attachment or None); WsdFault for a SOAP fault."""
        h = http or self.http
        r = h.request("POST", h.base_path, envelope(NS_SCAN + "/" + action, h.base, body),
                      {"Content-Type": SOAP_TYPE, "Cache-Control": "no-cache"},
                      limit=limit, timeout=timeout)
        ctype = r.headers.get("content-type", "")
        att = None
        if "multipart/" in ctype.lower():
            root, att = parse_multipart(r.body, ctype)
        elif r.body.strip():
            try:
                root = parse_xml(r.body)
            except ScanError:
                if r.status >= 400:
                    raise net.NetError(tr("The scanner answered with an error (HTTP {status})."
                                          ).format(status=r.status), "http",
                                       "%s: HTTP %d" % (action, r.status), r.status)
                raise
        else:
            root = None
        fault = fault_of(root) if root is not None else None
        if fault:
            raise WsdFault(fault[0], fault[1], r.status)
        if r.status >= 400 or root is None:
            raise net.NetError(tr("The scanner answered with an error (HTTP {status}).").format(
                status=r.status), "http", "%s: HTTP %d" % (action, r.status), r.status)
        return root, att

    def capabilities(self):
        names = ("ScannerDescription", "ScannerConfiguration", "ScannerStatus",
                 "DefaultScanTicket")
        for asked in (names, names[:2]):
            body = ("<wscn:GetScannerElementsRequest><wscn:RequestedElements>%s"
                    "</wscn:RequestedElements></wscn:GetScannerElementsRequest>" % "".join(
                        "<wscn:Name>wscn:%s</wscn:Name>" % n for n in asked))
            try:
                root, _a = self.call("GetScannerElements", body)
                break
            except WsdFault:
                if asked is not names:
                    raise
        from xml.etree.ElementTree import tostring
        self.caps = parse_elements(root, tostring(root, encoding="unicode"))
        return self.caps

    def status(self):
        body = ("<wscn:GetScannerElementsRequest><wscn:RequestedElements><wscn:Name>"
                "wscn:ScannerStatus</wscn:Name></wscn:RequestedElements>"
                "</wscn:GetScannerElementsRequest>")
        try:
            root, _a = self.call("GetScannerElements", body, http=net.Http(self.http.base),
                                 timeout=10)
        except ScanError:
            return "", []
        return parse_status(root)

    def scan(self, settings, report=lambda _t: None, scan_id=None, dest_token=None):
        """Scan with ScanSettings; yields each Page as it arrives. scan_id, dest_token: a
        scan the user started on the printer's panel (scan_events.py)."""
        self.http.canceled = False      # (a scan canceled before doesn't stop this one)
        caps = self.caps or self.capabilities()
        key = settings.source if settings.source in caps.sources else next(iter(caps.sources))
        src = caps.sources[key]
        color = settings.color if settings.color in src.colors else src.colors[0]
        fmt = next((f for f in FORMATS[color] if f in src.formats), src.formats[0])
        mode = COLORS[color]
        if color == "bw" and fmt in ("jfif", "exif"):
            mode = COLORS["gray"]       # (no 1-bit JPEG: gray instead)
        dpi = net.nearest(src.resolutions, settings.dpi)
        w_in, h_in = net.region(settings, src)
        body = ticket_xml(SOURCES[key], mode, dpi, round(w_in * 1000), round(h_in * 1000), fmt,
                          1 if key == "platen" else 0, scan_id, dest_token)
        self.trail.append("CreateScanJob: " + body)
        report(tr("Starting the scan..."))
        for attempt in range(6):
            try:
                root, _a = self.call("CreateScanJob", body)
                break
            except WsdFault as f:
                state, reasons = self.status()
                f.details += "; ScannerState %s, reasons %s" % (state, ",".join(reasons))
                if {"Calibrating", "LampWarming"} & set(reasons) and attempt < 5:
                    report(tr("The scanner is getting ready..."))
                    self.sleep(2)
                    continue
                if key != "platen" and f.code == "ServerErrorNotAcceptingJobs" and \
                        state == "Idle" and not reasons:
                    raise ScanError(tr("The document feeder is empty: put the pages in it, or "
                                       "choose the flatbed (glass)."), f.details)
                if reasons:
                    raise ScanError(fault_message(f.code, reasons), f.details)
                raise
        job_id = text(descendants(root, "JobId")[0]) if descendants(root, "JobId") else ""
        token = text(descendants(root, "JobToken")[0]) if descendants(root, "JobToken") else ""
        if not job_id:
            raise ScanError(tr("The scanner didn't start the scan."), "no JobId in "
                            "CreateScanJobResponse")
        pages = retries = 0
        done = False
        try:
            while True:
                if pages >= net.MAX_PAGES:
                    raise ScanError(tr("Too many pages in one scan (more than {n}).").format(
                        n=net.MAX_PAGES))
                report(tr("Scanning page {n}...").format(n=pages + 1))
                req = ("<wscn:RetrieveImageRequest><wscn:DocumentDescription><wscn:DocumentName>"
                       "IMAGE%03d</wscn:DocumentName></wscn:DocumentDescription>"
                       "<wscn:JobId>%s</wscn:JobId><wscn:JobToken>%s</wscn:JobToken>"
                       "</wscn:RetrieveImageRequest>" % (pages + 1, xml_escape(job_id),
                                                         xml_escape(token)))
                try:
                    _root, att = self.call("RetrieveImage", req, limit=net.MAX_IMAGE + 65536,
                                           timeout=net.PAGE_TIMEOUT)
                except WsdFault as f:
                    if pages and f.code in ("ClientErrorNoImagesAvailable",
                                            "ClientErrorJobIdNotFound"):
                        break
                    if f.code == "ServerErrorTemporaryError" and retries < 30:
                        retries += 1
                        self.sleep(1)
                        continue
                    state, reasons = self.status()
                    if key != "platen" and not pages and f.code in (
                            "ClientErrorNoImagesAvailable", "ClientErrorJobIdNotFound"):
                        raise ScanError(tr("The document feeder is empty: put the pages in it, "
                                           "or choose the flatbed (glass)."), f.details)
                    raise ScanError(fault_message(f.code, reasons), "%s; ScannerState %s, "
                                    "reasons %s" % (f.details, state, ",".join(reasons)))
                if not att:
                    raise ScanError(tr("The scanner's answer had no picture in it."),
                                    "RetrieveImage without an attachment")
                page = net.check_image(att, dpi)
                pages += 1
                retries = 0
                yield page
                if key == "platen":
                    break
            done = True
        finally:
            if not done:
                try:
                    self.call("CancelJob", "<wscn:CancelJobRequest><wscn:JobId>%s</wscn:JobId>"
                              "</wscn:CancelJobRequest>" % xml_escape(job_id),
                              http=net.Http(self.http.base), timeout=3)
                except ScanError:
                    pass


# ---- WS-Eventing: scans started on the printer's panel (see scan_events.py) ---------------
SUBSCRIBE = NS_WSE + "/Subscribe"
RENEW = NS_WSE + "/Renew"
UNSUBSCRIBE = NS_WSE + "/Unsubscribe"
SCAN_AVAILABLE = NS_SCAN + "/ScanAvailableEvent"
ACTION_DIALECT = "http://schemas.xmlsoap.org/ws/2006/02/devprof/Action"
PUSH_MODE = NS_WSE + "/DeliveryModes/Push"
EXPIRES = "PT1H"


def subscribe_xml(notify_url, identifier, display_name, context, expires=EXPIRES):
    """The body of a Subscribe to ScanAvailableEvent: the printer lists display_name as a scan
    destination on its panel, and sends the event to notify_url."""
    return ('<wse:Subscribe><wse:Delivery Mode="%s"><wse:NotifyTo><wsa:Address>%s</wsa:Address>'
            "<wsa:ReferenceParameters><wse:Identifier>%s</wse:Identifier>"
            "</wsa:ReferenceParameters></wse:NotifyTo></wse:Delivery>"
            "<wse:Expires>%s</wse:Expires>"
            '<wse:Filter Dialect="%s">%s</wse:Filter>'
            "<wscn:ScanDestinations><wscn:ScanDestination>"
            "<wscn:ClientDisplayName>%s</wscn:ClientDisplayName>"
            "<wscn:ClientContext>%s</wscn:ClientContext>"
            "</wscn:ScanDestination></wscn:ScanDestinations></wse:Subscribe>" % (
                PUSH_MODE, xml_escape(notify_url), xml_escape(identifier), expires,
                ACTION_DIALECT, SCAN_AVAILABLE, xml_escape(display_name), xml_escape(context)))


def seconds(value, default=3600):
    """Seconds of an xs:duration ("PT1H", "P0Y0M0DT30H0M0S") or until an xs:dateTime."""
    import re
    v = (value or "").strip()
    m = re.match(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?"
                 r"(?:(\d+(?:\.\d+)?)S)?)?$", v)
    if m and v not in ("P", "PT"):
        y, mo, d, h, mi, sec = (float(x or 0) for x in m.groups())
        return int(((y * 365 + mo * 30 + d) * 24 + h) * 3600 + mi * 60 + sec)
    try:
        from datetime import datetime, timezone
        when = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        left = (when - datetime.now(timezone.utc)).total_seconds()
        return int(left) if left > 0 else default
    except ValueError:
        return default


def _soap(service_url, action, to, body, headers="", timeout=net.READ_TIMEOUT):
    """POST one SOAP message to the scan service's device: its root element, WsdFault for a
    fault. (A To naming another host is still sent only to this device.)"""
    h = net.Http(service_url)
    target = to if to.lower().startswith(("http://", "https://")) else service_url
    r = h.request("POST", target, envelope(action, to, body, headers=headers),
                  {"Content-Type": SOAP_TYPE}, timeout=timeout)
    root = parse_xml(r.body) if r.body.strip() else None
    fault = fault_of(root) if root is not None else None
    if fault:
        raise WsdFault(fault[0], fault[1], r.status)
    if r.status >= 400 or (root is None and r.status != 202 and action == SUBSCRIBE):
        raise net.NetError(tr("The scanner answered with an error (HTTP {status}).").format(
            status=r.status), "http", "%s: HTTP %d" % (action.rsplit("/", 1)[-1], r.status),
            r.status)
    return root


def subscribe(service_url, notify_url, identifier, display_name, context, timeout=10):
    """Subscribe to ScanAvailableEvent: {manager, params, expires, token}."""
    from xml.etree.ElementTree import tostring
    root = _soap(service_url, SUBSCRIBE, service_url,
                 subscribe_xml(notify_url, identifier, display_name, context), timeout=timeout)
    resp = descendants(root, "SubscribeResponse")
    if not resp:
        raise ScanError(tr("The scanner didn't accept the subscription."),
                        "no SubscribeResponse")
    resp = resp[0]
    mgr = child(resp, "SubscriptionManager")
    params = child(mgr, "ReferenceParameters")
    echo = "".join(tostring(p, encoding="unicode") for p in (params if params is not None
                                                             else []))[:4096]
    token = ""
    for d in descendants(resp, "DestinationResponse"):
        if text(d, "ClientContext") == context or not token:
            token = text(d, "DestinationToken")
    return {"manager": text(mgr, "Address") or service_url, "params": echo,
            "expires": seconds(text(resp, "Expires")), "token": token}


def renew(service_url, sub, timeout=10):
    """Renew a subscription: seconds until it expires."""
    root = _soap(service_url, RENEW, sub["manager"],
                 "<wse:Renew><wse:Expires>%s</wse:Expires></wse:Renew>" % EXPIRES,
                 sub["params"], timeout=timeout)
    return seconds(text(descendants(root, "Expires")[0]) if root is not None and
                   descendants(root, "Expires") else "")


def unsubscribe(service_url, sub, timeout=3):
    _soap(service_url, UNSUBSCRIBE, sub["manager"], "<wse:Unsubscribe/>", sub["params"],
          timeout=timeout)

"""File > Scan: eSCL ("AirScan", Mopria and Apple's driverless scanning), and finding eSCL
scanners with multicast DNS (DNS-SD services _uscan._tcp and _uscans._tcp).

eSCL is plain HTTP(S) with XML: GET <root>/ScannerCapabilities, POST <root>/ScanJobs with
ScanSettings (the answer's Location is the job), GET <job>/NextDocument for each page until
404, then DELETE <job>. 503 means "not ready yet, ask again". Written from the Mopria eSCL
specification's published schema and the behavior of real devices documented by sane-airscan
(https://github.com/alexpevzner/sane-airscan, read as a reference, no code taken).

Multicast DNS (RFC 6762) is asked as a "one-shot" query from a port of our own: responders
answer such a query straight back to that port (legacy unicast), so nothing here listens on
port 5353 or joins a multicast group; answers with another query ID are ignored.
"""

import random
import struct
import time

from . import scan_net as net
from .i18n import tr
from .scan_net import (Caps, Device, ScanError, SourceCaps, child, descendants,
                       local, parse_xml, text, xml_escape)

SERVICES = ("_uscan._tcp.local", "_uscans._tcp.local")
MDNS = ("224.0.0.251", 5353)
T_A, T_PTR, T_TXT, T_SRV = 1, 12, 16, 33

NS_SCAN = "http://schemas.hp.com/imaging/escl/2011/05/03"
NS_PWG = "http://www.pwg.org/schemas/2010/12/sm"
COLOR_MODES = {"color": "RGB24", "gray": "Grayscale8", "bw": "BlackAndWhite1"}
MODE_COLORS = {"RGB24": "color", "RGB48": "color", "Grayscale8": "gray", "Grayscale16": "gray",
               "BlackAndWhite1": "bw"}
FORMATS = {"color": ("image/jpeg", "image/png", "image/tiff", "application/pdf"),
           "gray": ("image/jpeg", "image/png", "image/tiff", "application/pdf"),
           "bw": ("image/png", "image/tiff", "image/jpeg", "application/pdf")}
LOAD_RETRIES = 30           # NextDocument answered 503 (the page isn't ready): 1 s apart
JOB_RETRIES = 10            # ScanJobs answered 503


# ---- multicast DNS --------------------------------------------------------------------------
def build_query(qid, questions):
    """A DNS query: questions [(name, type)], class IN."""
    out = struct.pack(">HHHHHH", qid, 0, len(questions), 0, 0, 0)
    for name, qtype in questions:
        for label in name.strip(".").split("."):
            raw = label.encode("utf-8")[:63]
            out += bytes([len(raw)]) + raw
        out += b"\x00" + struct.pack(">HH", qtype, 1)
    return out


def _read_name(d, off):
    labels, end, jumps = [], None, 0
    while True:
        if off >= len(d):
            raise ValueError("name past the end")
        n = d[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            if off + 1 >= len(d):
                raise ValueError("bad pointer")
            if end is None:
                end = off + 2
            jumps += 1
            if jumps > 32:
                raise ValueError("pointer loop")
            off = ((n & 0x3F) << 8) | d[off + 1]
            continue
        if n & 0xC0:
            raise ValueError("bad label")
        labels.append(d[off + 1:off + 1 + n].decode("utf-8", "replace"))
        off += 1 + n
        if len(labels) > 128:
            raise ValueError("name too long")
    return ".".join(labels), (end if end is not None else off)


def parse_message(d):
    """(query id, is a response, [(name, type, data)]) of a DNS message; data is the name
    (PTR), (port, target) (SRV), {key: value} (TXT) or an address (A)."""
    if len(d) < 12:
        raise ValueError("short")
    qid, flags, qd, an, ns, ar = struct.unpack(">HHHHHH", d[:12])
    off = 12
    for _ in range(qd):
        _n, off = _read_name(d, off)
        off += 4
    records = []
    for _ in range(min(an + ns + ar, 500)):
        name, off = _read_name(d, off)
        if off + 10 > len(d):
            raise ValueError("short record")
        rtype, _cls, _ttl, size = struct.unpack(">HHIH", d[off:off + 10])
        off += 10
        rd = d[off:off + size]
        if len(rd) < size:
            raise ValueError("short data")
        if rtype == T_PTR:
            records.append((name.lower(), rtype, _read_name(d, off)[0]))
        elif rtype == T_SRV and size >= 7:
            port = struct.unpack(">H", rd[4:6])[0]
            records.append((name.lower(), rtype, (port, _read_name(d, off + 6)[0])))
        elif rtype == T_TXT:
            txt, i = {}, 0
            while i < len(rd):
                n = rd[i]
                item = rd[i + 1:i + 1 + n].decode("utf-8", "replace")
                i += 1 + n
                k, _eq, v = item.partition("=")
                if k:
                    txt.setdefault(k.lower(), v)
            records.append((name.lower(), rtype, txt))
        elif rtype == T_A and size == 4:
            records.append((name.lower(), rtype, ".".join(str(b) for b in rd)))
        off += size
    return qid, bool(flags & 0x8000), records


def _ask(questions, dest, window, cancel=None, interfaces=None, log=None):
    """[(sender IP, records)] of the answers to one query (sent twice, 0.4 s apart)."""
    qid = random.randrange(1, 0xFFFF)
    q = build_query(qid, questions)
    got = net.udp_exchange([(q, dest, 0.0), (q, dest, 0.4)], window, multicast_ttl=255,
                           cancel=cancel, interfaces=interfaces, log=log)
    out = []
    for data, src in got:
        try:
            rid, response, records = parse_message(data)
        except (ValueError, IndexError, struct.error):
            continue
        if rid == qid and response:
            out.append((src, records))
    return out


def browse(window=2.5, cancel=None, target=None, log=None, interfaces=None):
    """eSCL scanners answering on the local network (or only `target`, an IP address, asked
    directly). Devices; what was heard goes into log (a list of lines)."""
    dest = (target, MDNS[1]) if target else MDNS
    answers = _ask([(s, T_PTR) for s in SERVICES], dest, window, cancel, interfaces, log)
    if log is not None:
        log.append("mDNS %s: %d answer(s)%s" % (
            target or "multicast", len(answers),
            "".join(" from %s" % src for src, _r in answers[:20])))
    found = devices_from_records(answers)
    # instances whose address or details weren't in the first answer: ask their sender
    missing = {}
    for src, records in answers:
        for name, rtype, data in records:
            if rtype == T_PTR and name in SERVICES and not any(
                    d.info.get("instance") == data.lower() for d in found):
                missing.setdefault(src, []).append(data)
    for src, names in list(missing.items())[:10]:
        if cancel and cancel():
            break
        qs = [(n, T_SRV) for n in names[:4]] + [(n, T_TXT) for n in names[:4]]
        more = _ask(qs, (src, MDNS[1]), 1.0, cancel)
        joined = [(src, [r for s, recs in answers if s == src for r in recs]
                   + [r for _s, recs in more for r in recs])]
        found += [d for d in devices_from_records(joined)
                  if not any(d.key() == f.key() for f in found)]
    return merge(found)


def devices_from_records(answers):
    """Devices from mDNS answers [(sender IP, records)]. A device is reached at the address
    that answered (never an address a record names), on the port its SRV record gives."""
    out = []
    for src, records in answers:
        ptrs = [(n, d) for n, t, d in records if t == T_PTR and n in SERVICES]
        for service, instance in ptrs:
            inst = instance.lower()
            srv = next((d for n, t, d in records if t == T_SRV and n == inst), None)
            txt = next((d for n, t, d in records if t == T_TXT and n == inst), None)
            if srv is None:
                continue
            txt = txt or {}
            https = service.startswith("_uscans")
            rs = (txt.get("rs") or "eSCL").strip("/")
            port = srv[0] or (443 if https else 80)
            url = net.make_url("https" if https else "http", src, port, "/" + rs)
            name = txt.get("ty") or instance.split("._")[0]
            info = {"instance": inst, "service": service, "port": port,
                    "txt": {k: v for k, v in txt.items()
                            if k in ("rs", "ty", "uuid", "cs", "is", "duplex", "pdl", "vers",
                                     "note", "adminurl", "representation")}}
            out.append(Device(name[:120], "escl", url, src, [], info))
    return out


def merge(devices):
    """One device per scanner: its http and https services together (http first)."""
    out = []
    for d in sorted(devices, key=lambda d: d.address.startswith("https")):
        uuid = (d.info.get("txt") or {}).get("uuid", "").lower()
        same = next((o for o in out if o.host == d.host and
                     (not uuid or (o.info.get("txt") or {}).get("uuid", "").lower() == uuid)),
                    None)
        if same is None:
            out.append(d)
        elif d.address not in same.alt and d.address != same.address:
            same.alt.append(d.address)
    return out


# ---- eSCL -----------------------------------------------------------------------------------
def _resolutions(caps_el):
    out = set()
    for r in descendants(caps_el, "DiscreteResolution"):
        x, y = text(r, "XResolution"), text(r, "YResolution")
        if x.isdigit() and (not y or y == x):
            out.add(int(x))
    for r in descendants(caps_el, "XResolutionRange"):
        lo, hi = text(r, "Min"), text(r, "Max")
        if lo.isdigit() and hi.isdigit():
            out.update(v for v in net.COMMON_DPI if int(lo) <= v <= int(hi))
    return sorted(v for v in out if 0 < v <= 4800)


def _input_caps(el):
    colors, formats, ext = [], [], False
    for m in descendants(el, "ColorMode"):
        c = MODE_COLORS.get(text(m))
        if c and c not in colors:
            colors.append(c)
    for f in descendants(el, "DocumentFormat") + descendants(el, "DocumentFormatExt"):
        ext = ext or local(f.tag) == "DocumentFormatExt"
        if text(f) and text(f) not in formats:
            formats.append(text(f))
    src = SourceCaps(colors=[c for c in ("color", "gray", "bw") if c in colors] or ["color"],
                     resolutions=_resolutions(el) or [300], formats=formats or ["image/jpeg"])
    src.extra["format_ext"] = ext
    for name, attr in (("MaxWidth", "max_w"), ("MaxHeight", "max_h")):
        v = text(el, name)
        if v.isdigit() and int(v) > 0:
            setattr(src, attr, int(v) / 300.0)
    return src


def parse_capabilities(data):
    root = parse_xml(data)
    if local(root.tag) != "ScannerCapabilities":
        raise ScanError(tr("The device's answer isn't an eSCL scanner description."),
                        "root element %s" % root.tag)
    caps = Caps(model=text(root, "MakeAndModel"), raw=data.decode("utf-8", "replace"))
    platen = child(root, "Platen", "PlatenInputCaps")
    if platen is not None:
        caps.sources["platen"] = _input_caps(platen)
    adf = child(root, "Adf")
    if adf is not None:
        simplex = child(adf, "AdfSimplexInputCaps")
        duplex = child(adf, "AdfDuplexInputCaps")
        if simplex is not None:
            caps.sources["feeder"] = _input_caps(simplex)
        if duplex is not None:
            caps.sources["duplex"] = _input_caps(duplex)
        elif simplex is not None and any(text(o) == "Duplex" for o in
                                         descendants(child(adf, "AdfOptions"), "AdfOption")):
            caps.sources["duplex"] = _input_caps(simplex)
    if not caps.sources:
        raise ScanError(tr("The scanner didn't say what it can scan from."),
                        "no Platen or Adf in ScannerCapabilities")
    return caps


def parse_status(data):
    """(state, feeder state) from ScannerStatus: ("Idle", "ScannerAdfLoaded")."""
    try:
        root = parse_xml(data)
    except ScanError:
        return "", ""
    return text(root, "State"), text(root, "AdfState")


ADF_MESSAGES = {
    "ScannerAdfEmpty": "empty", "ScannerAdfJam": "jam", "ScannerAdfMispick": "jam",
    "ScannerAdfDoorOpen": "open", "ScannerAdfHopperError": "jam", "ScannerAdfMultipickDetected":
    "jam", "ScannerAdfOutputFull": "full", "ScannerAdfInputTrayFailed": "jam",
}


def problem_message(state, adf):
    """A plain-word message for what ScannerStatus reports, or None."""
    k = ADF_MESSAGES.get(adf)
    if k == "empty":
        return tr("The document feeder is empty: put the pages in it, or choose the flatbed "
                  "(glass).")
    if k == "jam":
        return tr("Paper is jammed in the document feeder: clear it (see the printer's panel) "
                  "and try again.")
    if k == "open":
        return tr("The document feeder's cover is open: close it and try again.")
    if k == "full":
        return tr("The document feeder's output tray is full: empty it and try again.")
    if state in ("Down", "Stopped"):
        return tr("The scanner isn't ready (it reports \"{state}\"): check its panel for a "
                  "message.").format(state=state)
    return None


def settings_xml(source, duplex, mode, dpi, width, height, fmt, ext):
    """eSCL ScanSettings; width and height in 1/300 inch. (The order of the elements is the one
    real devices are known to accept.)"""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<scan:ScanSettings xmlns:scan="%s" xmlns:pwg="%s">' % (NS_SCAN, NS_PWG),
             "<pwg:Version>2.0</pwg:Version>",
             "<pwg:ScanRegions>", "<pwg:ScanRegion>",
             "<pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>",
             "<pwg:XOffset>0</pwg:XOffset>", "<pwg:YOffset>0</pwg:YOffset>",
             "<pwg:Width>%d</pwg:Width>" % width, "<pwg:Height>%d</pwg:Height>" % height,
             "</pwg:ScanRegion>", "</pwg:ScanRegions>",
             "<pwg:InputSource>%s</pwg:InputSource>" % xml_escape(source),
             "<scan:ColorMode>%s</scan:ColorMode>" % xml_escape(mode),
             "<pwg:DocumentFormat>%s</pwg:DocumentFormat>" % xml_escape(fmt)]
    if ext:
        parts.append("<scan:DocumentFormatExt>%s</scan:DocumentFormatExt>" % xml_escape(fmt))
    parts += ["<scan:XResolution>%d</scan:XResolution>" % dpi,
              "<scan:YResolution>%d</scan:YResolution>" % dpi]
    if source == "Feeder":
        parts.append("<scan:Duplex>%s</scan:Duplex>" % ("true" if duplex else "false"))
    parts.append("</scan:ScanSettings>")
    return "".join(parts)


class EsclScanner:
    """One eSCL scanner (the device the user picked)."""

    protocol = "escl"

    def __init__(self, device, sleep=time.sleep):
        self.device = device
        self.http = net.Http(device.address)
        self.caps = None
        self.sleep = sleep
        self.trail = []

    def abort(self):
        self.http.abort()

    def _get(self, path, **kw):
        """GET, trying the device's other address (https / http) when the first can't be
        reached at all."""
        try:
            return self.http.request("GET", path, **kw)
        except net.NetError as ex:
            if ex.kind not in ("refused", "tls", "unreachable") or not self.device.alt:
                raise
            self.trail.append("%s: %s" % (self.http.base, ex.details or ex.message))
            for alt in self.device.alt:
                h = net.Http(alt)
                try:
                    r = h.request("GET", path, **kw)
                except net.NetError as ex2:
                    self.trail.append("%s: %s" % (alt, ex2.details or ex2.message))
                    continue
                self.http = h
                return r
            raise

    def capabilities(self):
        r = self._get("ScannerCapabilities")
        if r.status != 200:
            raise ScanError(tr("The scanner answered but not as an eSCL scanner (HTTP {status})."
                               ).format(status=r.status), "%s: HTTP %d" % (r.url, r.status))
        self.caps = parse_capabilities(r.body)
        return self.caps

    def status(self):
        try:
            r = self.http.request("GET", "ScannerStatus", timeout=10)
        except ScanError:
            return "", ""
        return parse_status(r.body) if r.status == 200 else ("", "")

    def scan(self, settings, report=lambda _t: None):
        """Scan with ScanSettings; yields each Page as it arrives."""
        self.http.canceled = False      # (a scan canceled before doesn't stop this one)
        caps = self.caps or self.capabilities()
        key = settings.source if settings.source in caps.sources else next(iter(caps.sources))
        src = caps.sources[key]
        color = settings.color if settings.color in src.colors else src.colors[0]
        fmt = next((f for f in FORMATS[color] if f in src.formats), src.formats[0])
        mode = COLOR_MODES[color]
        if color == "bw" and fmt == "image/jpeg":
            mode = COLOR_MODES["gray"]       # (no 1-bit JPEG: gray instead)
        dpi = net.nearest(src.resolutions, settings.dpi)
        w_in, h_in = net.region(settings, src)
        body = settings_xml("Platen" if key == "platen" else "Feeder", key == "duplex", mode,
                            dpi, round(w_in * 300), round(h_in * 300), fmt,
                            src.extra.get("format_ext"))
        self.trail.append("ScanSettings: " + body)
        report(tr("Starting the scan..."))
        for attempt in range(JOB_RETRIES + 1):
            r = self.http.request("POST", "ScanJobs", body,
                                  {"Content-Type": "text/xml; charset=utf-8"})
            if r.status != 503 or attempt == JOB_RETRIES:
                break
            report(tr("The scanner is getting ready..."))
            self.sleep(1)
        if r.status not in (200, 201) or not r.headers.get("location"):
            raise self._job_error(r)
        job = self.http.url(r.headers["location"]).rstrip("/")
        pages = retries = 0
        done = False
        try:
            while True:
                if pages >= net.MAX_PAGES:
                    raise ScanError(tr("Too many pages in one scan (more than {n}).").format(
                        n=net.MAX_PAGES))
                report(tr("Scanning page {n}...").format(n=pages + 1))
                r = self.http.request("GET", job + "/NextDocument", limit=net.MAX_IMAGE,
                                      timeout=net.PAGE_TIMEOUT)
                if r.status == 200:
                    page = net.check_image(r.body, dpi)
                    pages += 1
                    retries = 0
                    yield page
                    continue
                if r.status == 503 and retries < LOAD_RETRIES:
                    retries += 1
                    self.sleep(1)
                    continue
                if r.status in (404, 410) and pages:
                    break
                state, adf = self.status()
                msg = problem_message(state, adf)
                if r.status in (404, 410) and msg is None:
                    msg = tr("The scanner finished without sending a page.")
                raise ScanError(msg or tr("The scanner stopped with an error (HTTP {status})."
                                          ).format(status=r.status),
                                "NextDocument: HTTP %d; State %s, AdfState %s" % (
                                    r.status, state, adf))
            done = True
        finally:
            # the job is deleted when it's done, canceled or failed (some devices keep a
            # finished job until then); a fresh connection, as abort() closes the other one
            try:
                h = net.Http(self.http.base)
                h.request("DELETE", job, timeout=5 if done else 3)
            except ScanError:
                pass  # (the scanner already dropped the job)

    def _job_error(self, r):
        state, adf = self.status()
        msg = problem_message(state, adf)
        details = "ScanJobs: HTTP %d; State %s, AdfState %s; %s" % (
            r.status, state, adf, r.body[:300].decode("utf-8", "replace"))
        if msg:
            return ScanError(msg, details)
        if r.status in (409, 503):
            return ScanError(tr("The scanner is busy (scanning, copying, or waiting for "
                                "something on its panel): finish that, then try again."), details)
        return ScanError(tr("The scanner refused these settings (HTTP {status}): try another "
                            "resolution, color or source.").format(status=r.status), details)

"""File > Scan: finding scanners every way at once, adding one by its address, opening the
right protocol for a device, and the "Copy details" report.

Network discovery (eSCL by multicast DNS, WSD by WS-Discovery) and the system's own scanners
(WIA on Windows, SANE on Linux) are asked side by side, in worker threads; nothing here
touches Qt or a document.
"""

import os
import re
import sys
import time

from . import scan_net as net
from .i18n import tr
from .scan_net import Device, ScanError

ESCL_PORTS = (("http", 80), ("https", 443), ("http", 8080), ("http", 9095), ("https", 9096))
WEB_PORTS = (("http", 80), ("https", 443))


def system_kind():
    """The system's own scanner support: "wia", "sane" or None."""
    if sys.platform == "win32":
        return "wia"
    if sys.platform.startswith("linux"):
        return "sane"
    return None


def tried_list():
    """What discovery tries here, in words."""
    out = [tr("eSCL (AirScan) and WSD on the network")]
    kind = system_kind()
    if kind == "wia":
        out.append(tr("Windows' own scanners (WIA)"))
    elif kind == "sane":
        from . import scan_local
        out.append(tr("SANE (scanimage)") if scan_local.scanimage() else
                   tr("SANE isn't installed (the sane-utils package)"))
    return out


def discover(cancel=None, log=None, window=2.5):
    """(scanners, printers that answered WSD without a scanner) found every way at once."""
    from concurrent.futures import ThreadPoolExecutor
    from . import scan_escl, scan_wsd, scan_local
    log = log if log is not None else []
    log.append("Discovery on %s, local IPv4: %s" % (sys.platform,
                                                     ", ".join(net.local_ipv4()) or "none"))
    jobs = {"escl": lambda: (scan_escl.browse(window, cancel, log=log), []),
            "wsd": lambda: scan_wsd.discover(window + 0.5, cancel, log=log)}
    kind = system_kind()
    if kind == "wia":
        jobs["wia"] = lambda: (scan_local.wia_devices(log), [])
    elif kind == "sane":
        jobs["sane"] = lambda: (scan_local.sane_devices(log), [])
    scanners, printers = [], []
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {k: pool.submit(f) for k, f in jobs.items()}
        for k, fut in futures.items():
            try:
                found, other = fut.result()
            except Exception as ex:          # one way failing never hides the others
                log.append("%s failed: %r" % (k, ex))
                continue
            scanners += found
            printers += other
    # a printer found by eSCL and WSD is listed both ways (if one doesn't work, the other may)
    seen, out = set(), []
    for d in scanners:
        if d.key() not in seen:
            seen.add(d.key())
            out.append(d)
    printers = [p for p in printers if not any(s.host == p.host for s in out)]
    return out, printers


def parse_address(text):
    """(host, eSCL URL typed or None) of what was typed: an IP address, a host name, or a
    URL."""
    t = text.strip()
    if not t:
        raise ScanError(tr("Type the printer's IP address, for example 192.168.1.20."))
    if "://" in t:
        scheme, host, port, path = net.split_url(t)
        return host, (net.make_url(scheme, host, port, path) if path not in ("", "/") else None)
    host = t.split("/")[0]
    if host.count(":") == 1:
        host = host.split(":")[0]
    host = host.strip("[]")
    if not re.match(r"^[A-Za-z0-9.\-:]+$", host):
        raise ScanError(tr("{url} isn't a valid address.").format(url=t))
    return host, None


def add_by_address(text, cancel=None, log=None):
    """The scanner at a typed address: eSCL first (asked by multicast DNS straight at the
    address, and at the usual ports), then WSD (a WS-Discovery probe straight at it, then over
    HTTP). ScanError in plain words when nothing scans there."""
    from concurrent.futures import ThreadPoolExecutor
    from . import scan_escl, scan_wsd
    log = log if log is not None else []
    host, typed = parse_address(text)
    ip = net.resolve_host(host)
    log.append("Add by address: %s -> %s" % (host, ip))

    def escl_at(url):
        d = Device(ip, "escl", url, ip)
        s = scan_escl.EsclScanner(d)
        try:
            caps = s.capabilities()
        except ScanError as ex:
            log.append("eSCL %s: %s" % (url, ex.details or ex.message))
            return None
        d.name = caps.model or ip
        log.append("eSCL %s: %s" % (url, d.name))
        return d
    urls = ([typed] if typed else []) + [net.make_url(s, ip, p, "/eSCL") for s, p in ESCL_PORTS]
    with ThreadPoolExecutor(max_workers=8) as pool:
        mdns = pool.submit(scan_escl.browse, 1.5, cancel, ip, log)
        tries = [pool.submit(escl_at, u) for u in urls]
        wsd = pool.submit(scan_wsd.discover, 2.0, cancel, ip, log)
        try:
            from_mdns = [d for d in mdns.result() if d.host == ip]
        except Exception as ex:
            log.append("mDNS %s failed: %r" % (ip, ex))
            from_mdns = []
        found = [f.result() for f in tries]
        try:
            wsd_scanners, wsd_printers = wsd.result()
        except Exception as ex:
            log.append("WSD %s failed: %r" % (ip, ex))
            wsd_scanners, wsd_printers = [], []
    escl = [d for d in found if d]
    if from_mdns:
        # its own advertisement says where eSCL is (path and port): check it answers
        d = escl_at(from_mdns[0].address) if not any(
            e.address == from_mdns[0].address for e in escl) else None
        if d:
            d.name = from_mdns[0].name or d.name
            d.alt = from_mdns[0].alt
            escl.insert(0, d)
    if escl:
        return escl[0]
    if cancel and cancel():
        raise net.Canceled()
    if not wsd_scanners and not wsd_printers:
        matches = scan_wsd.directed_probe(ip, log)
        if matches:
            wsd_scanners, wsd_printers = scan_wsd.from_matches(matches, log, cancel, any_type=True)
    if wsd_scanners:
        return wsd_scanners[0]
    web = "http://%s" % ip
    if wsd_printers:
        raise ScanError(tr("The printer at {ip} answered over WSD, but offers no scanning that "
                           "way: WSD scanning is turned off. Open its web page ({web}), set WSD "
                           "(or WSD Scan) to Enable, then try again.").format(ip=ip, web=web))
    if _web_page(ip, log):
        raise ScanError(tr("The printer answered but WSD scanning is turned off: open its web "
                           "page ({web}) and set WSD to Enable (often under Network or Protocol "
                           "settings), then try again. If it has no such setting, use Watch a "
                           "folder... with its Scan to Network Folder.").format(web=web))
    raise ScanError(tr("Nothing answered at {ip}. Check the address (it's on the printer's "
                       "panel or its network report), that the printer is on, and that this "
                       "computer is on the same network.").format(ip=ip))


def _web_page(ip, log):
    for scheme, port in WEB_PORTS:
        try:
            r = net.Http(net.make_url(scheme, ip, port, "/")).request("GET", "/", limit=65536,
                                                                      timeout=4)
        except ScanError as ex:
            log.append("web page %s://%s: %s" % (scheme, ip, ex.details or ex.message))
            continue
        log.append("web page %s://%s: HTTP %d" % (scheme, ip, r.status))
        return True
    return False


def open_scanner(device):
    """The protocol's scanner object for a Device."""
    if device.protocol == "escl":
        from .scan_escl import EsclScanner
        return EsclScanner(device)
    if device.protocol == "wsd":
        from .scan_wsd import WsdScanner
        return WsdScanner(device)
    if device.protocol == "wia":
        from .scan_local import WiaScanner
        return WiaScanner(device)
    if device.protocol == "sane":
        from .scan_local import SaneScanner
        return SaneScanner(device)
    raise ScanError(tr("Unknown kind of scanner."))


# ---- Copy details ---------------------------------------------------------------------------
def _scrub(s):
    """Serial numbers out, and this computer's user folder (a temporary file's path)."""
    s = re.sub(r"(<[\w:]*SerialNumber[^>]*>)[^<]*(<)", r"\1(removed)\2", s)
    home = os.path.expanduser("~")
    if home and len(home) > 3:
        s = s.replace(home, "~")
    return s


def details_report(devices, printers, log, device=None, caps=None, error=None, trail=None):
    """Plain text for the owner to send when a scanner doesn't work: what discovery found
    and the device's own answers. Nothing personal (no user or computer name, no files)."""
    from . import __version__
    lines = ["KanzonasPDF %s scanning details (%s)" % (__version__, sys.platform),
             time.strftime("%Y-%m-%d %H:%M"), "", "Discovery:"]
    lines += ["  " + x for x in log[-80:]] or ["  (nothing yet)"]
    lines += ["", "Scanners found:"]
    for d in devices:
        lines.append("  %s | %s | %s%s" % (d.name, d.protocol, d.address,
                                            " | also " + ", ".join(d.alt) if d.alt else ""))
        info = {k: v for k, v in d.info.items() if k != "metadata"}
        if info:
            lines.append("    %s" % info)
    if not devices:
        lines.append("  none")
    if printers:
        lines += ["", "Printers that answered WSD without a scanner:"]
        lines += ["  %s | %s | %s" % (p.name, p.host, p.info) for p in printers]
    if device is not None:
        lines += ["", "Selected: %s | %s | %s" % (device.name, device.protocol, device.address)]
        meta = device.info.get("metadata")
        if meta:
            lines += ["", "Device metadata:", meta[:20000]]
    if trail:
        lines += ["", "Requests:"] + ["  " + str(t)[:3000] for t in trail[-40:]]
    if caps is not None:
        lines += ["", "Capabilities (%s):" % caps.model]
        for k, src in caps.sources.items():
            lines.append("  %s: colors %s, dpi %s, max %.2f x %.2f in, formats %s" % (
                k, src.colors, src.resolutions, src.max_w, src.max_h, src.formats))
        if caps.raw:
            lines += ["", "Raw capabilities:", caps.raw[:60000]]
    if error is not None:
        lines += ["", "Last error: %s" % getattr(error, "message", error)]
        if getattr(error, "details", ""):
            lines.append("  " + error.details[:3000])
    return _scrub("\n".join(lines))

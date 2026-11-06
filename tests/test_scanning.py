"""File > Scan, tested against fake devices on this computer (nobody here has a real scanner):
a fake eSCL scanner (HTTP), a fake WS-Scan scanner (SOAP with MTOM pictures), fake
WS-Discovery and multicast DNS answers, Add by address, the errors (WSD turned off, time-outs,
broken or hostile XML, oversized pictures), the Scan window driven with stand-ins (a new
document, insert into the current one as one undo step), the watched folder, and WIA and SANE
with their commands stood in for.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_scanning
"""
import io
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

import pymupdf  # noqa: E402

from kanzonas import scan_escl, scan_local, scan_net as net, scan_wsd, scanners  # noqa: E402
from kanzonas.scan_net import Caps, Device, ScanError, ScanSettings, SourceCaps  # noqa: E402


def picture(w, h, fmt="JPG", color=(30, 120, 200)):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(*color))
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, fmt)
    return bytes(data)


def wait_for(cond, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    raise AssertionError("timed out waiting")


# ---- a fake eSCL scanner --------------------------------------------------------------------
NS = ('xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" '
      'xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm"')
RES = "".join("<scan:DiscreteResolution><scan:XResolution>%d</scan:XResolution>"
              "<scan:YResolution>%d</scan:YResolution></scan:DiscreteResolution>" % (r, r)
              for r in (75, 100, 150, 200, 300, 600))
PROFILE = ("<scan:SettingProfiles><scan:SettingProfile><scan:ColorModes>"
           "<scan:ColorMode>BlackAndWhite1</scan:ColorMode><scan:ColorMode>Grayscale8"
           "</scan:ColorMode><scan:ColorMode>RGB24</scan:ColorMode></scan:ColorModes>"
           "<scan:DocumentFormats><pwg:DocumentFormat>application/pdf</pwg:DocumentFormat>"
           "<pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat><scan:DocumentFormatExt>"
           "image/jpeg</scan:DocumentFormatExt></scan:DocumentFormats><scan:SupportedResolutions>"
           "<scan:DiscreteResolutions>%s</scan:DiscreteResolutions></scan:SupportedResolutions>"
           "</scan:SettingProfile></scan:SettingProfiles>" % RES)


def input_caps(tag, height):
    return ("<scan:%s><scan:MinWidth>16</scan:MinWidth><scan:MaxWidth>2550</scan:MaxWidth>"
            "<scan:MinHeight>16</scan:MinHeight><scan:MaxHeight>%d</scan:MaxHeight>"
            "<scan:MaxScanRegions>1</scan:MaxScanRegions>%s<scan:SupportedIntents>"
            "<scan:Intent>Document</scan:Intent><scan:Intent>Photo</scan:Intent>"
            "</scan:SupportedIntents></scan:%s>" % (tag, height, PROFILE, tag))


ESCL_CAPS = ('<?xml version="1.0" encoding="UTF-8"?><scan:ScannerCapabilities %s>'
             "<pwg:Version>2.63</pwg:Version><pwg:MakeAndModel>Dell Color MFP E525w"
             "</pwg:MakeAndModel><pwg:SerialNumber>CN0SECRET1234</pwg:SerialNumber>"
             "<scan:UUID>4509a320-00a0-008f-00b6-002507510eca</scan:UUID>"
             "<scan:Platen>%s</scan:Platen><scan:Adf>%s%s<scan:FeederCapacity>15"
             "</scan:FeederCapacity><scan:AdfOptions><scan:AdfOption>DetectPaperLoaded"
             "</scan:AdfOption><scan:AdfOption>Duplex</scan:AdfOption></scan:AdfOptions>"
             "</scan:Adf></scan:ScannerCapabilities>" % (
                 NS, input_caps("PlatenInputCaps", 3508), input_caps("AdfSimplexInputCaps", 4200),
                 input_caps("AdfDuplexInputCaps", 4200))).encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def send(self, code, body=b"", ctype="text/xml", headers=()):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass                        # (the client gave up: the time-out test)

    def body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))


class Escl(Handler):
    def do_GET(self):
        st = self.server.st
        st["requests"].append(("GET", self.path, self.headers.get("Host")))
        if st.get("stall"):
            time.sleep(st["stall"])
        if self.path == "/eSCL/ScannerCapabilities":
            return self.send(200, st["caps"])
        if self.path == "/eSCL/ScannerStatus":
            return self.send(200, ("<scan:ScannerStatus %s><pwg:Version>2.63</pwg:Version>"
                                   "<pwg:State>Idle</pwg:State><scan:AdfState>%s</scan:AdfState>"
                                   "</scan:ScannerStatus>" % (NS, st["adf"])).encode())
        if self.path == "/eSCL/ScanJobs/123/NextDocument":
            if st["busy"]:
                st["busy"] -= 1
                return self.send(503)
            if st["pages"]:
                return self.send(200, st["pages"].pop(0), "image/jpeg")
            return self.send(404)
        if self.path == "/":
            return self.send(200, b"<html>printer</html>", "text/html")
        self.send(404)

    def do_POST(self):
        st = self.server.st
        st["posts"].append((self.path, self.body().decode()))
        if self.path != "/eSCL/ScanJobs":
            return self.send(404)
        if st["job"] != 201:
            return self.send(st["job"])
        # (Location names another host: the client must stay on the device it reached)
        self.send(201, headers=[("Location", "http://192.0.2.99/eSCL/ScanJobs/123")])

    def do_DELETE(self):
        self.server.st["deletes"].append(self.path)
        self.send(200)


def serve(handler, **state):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    srv.st = dict(requests=[], posts=[], deletes=[], busy=0, pages=[], job=201,
                  adf="ScannerAdfLoaded", caps=ESCL_CAPS)
    srv.st.update(state)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class ServerCase(unittest.TestCase):
    def server(self, handler=None, **state):
        srv = serve(handler or Escl, **state)
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return srv, srv.server_address[1]


def closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class EsclScanning(ServerCase):
    def test_capabilities_like_a_real_device(self):
        _srv, port = self.server()
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        caps = s.capabilities()
        self.assertEqual(caps.model, "Dell Color MFP E525w")
        self.assertEqual(sorted(caps.sources), ["duplex", "feeder", "platen"])
        p = caps.sources["platen"]
        self.assertEqual(p.colors, ["color", "gray", "bw"])
        self.assertEqual(p.resolutions, [75, 100, 150, 200, 300, 600])
        self.assertAlmostEqual(p.max_w, 8.5)
        self.assertAlmostEqual(p.max_h, 3508 / 300)
        self.assertTrue(p.extra["format_ext"])

    def test_two_page_feeder_job(self):
        jpg = [picture(850, 1100), picture(850, 1100, color=(200, 0, 0))]
        srv, port = self.server(pages=list(jpg), busy=1)
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port),
                                  sleep=lambda _s: None)
        said = []
        pages = list(s.scan(ScanSettings("feeder", "color", 100, "letter"), said.append))
        self.assertEqual([p.data for p in pages], jpg)
        self.assertEqual([(p.kind, p.dpi, p.sizes) for p in pages], [("jpeg", 100, [(850, 1100)])] * 2)
        path, body = srv.st["posts"][0]
        self.assertEqual(path, "/eSCL/ScanJobs")
        for part in ("<pwg:InputSource>Feeder</pwg:InputSource>", "<scan:Duplex>false</scan:Duplex>",
                     "<scan:ColorMode>RGB24</scan:ColorMode>", "<scan:XResolution>100<",
                     "<pwg:Width>2550</pwg:Width>", "<pwg:Height>3300</pwg:Height>",
                     "<pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>",
                     "<scan:DocumentFormatExt>image/jpeg</scan:DocumentFormatExt>"):
            self.assertIn(part, body)
        # NextDocument asked of the device that was reached (not the Location's host), until 404
        gets = [r for r in srv.st["requests"] if "NextDocument" in r[1]]
        self.assertEqual(len(gets), 4)                  # 503, page, page, 404
        self.assertTrue(all(h == "127.0.0.1:%d" % port for _m, _p, h in gets))
        self.assertEqual(srv.st["deletes"], ["/eSCL/ScanJobs/123"])
        self.assertIn("Scanning page 2...", said)

    def test_duplex_and_gray_settings(self):
        srv, port = self.server(pages=[picture(100, 100)])
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        list(s.scan(ScanSettings("duplex", "gray", 300, "a4")))
        body = srv.st["posts"][0][1]
        self.assertIn("<scan:Duplex>true</scan:Duplex>", body)
        self.assertIn("<scan:ColorMode>Grayscale8</scan:ColorMode>", body)
        self.assertIn("<pwg:Height>3508</pwg:Height>", body)        # A4, 1/300 in

    def test_empty_feeder_in_plain_words(self):
        srv, port = self.server(adf="ScannerAdfEmpty")
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        with self.assertRaises(ScanError) as cm:
            list(s.scan(ScanSettings("feeder")))
        self.assertIn("feeder is empty", cm.exception.message)
        self.assertEqual(srv.st["deletes"], ["/eSCL/ScanJobs/123"])

    def test_busy_device(self):
        _srv, port = self.server(job=409)
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        with self.assertRaises(ScanError) as cm:
            list(s.scan(ScanSettings()))
        self.assertIn("busy", cm.exception.message)

    def test_oversized_page_refused(self):
        huge = bytearray(picture(10, 10, "PNG"))
        huge[16:24] = struct.pack(">II", 60000, 60000)          # the header claims 60000 x 60000
        srv, port = self.server(pages=[bytes(huge)])
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        with self.assertRaises(ScanError) as cm:
            list(s.scan(ScanSettings()))
        self.assertIn("too large", cm.exception.message)
        self.assertEqual(srv.st["deletes"], ["/eSCL/ScanJobs/123"])   # the job is cleaned up

    def test_cancel_while_the_page_is_coming(self):
        srv, port = self.server(stall=3)
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        s.caps = scan_escl.parse_capabilities(ESCL_CAPS)
        threading.Timer(0.4, s.abort).start()
        t0 = time.time()
        with self.assertRaises(net.Canceled):
            list(s.scan(ScanSettings()))
        self.assertLess(time.time() - t0, 2.5)
        self.assertEqual(srv.st["deletes"], ["/eSCL/ScanJobs/123"])      # the job is deleted
        srv.st["stall"] = 0
        srv.st["pages"] = [picture(20, 20)]
        self.assertEqual(len(list(s.scan(ScanSettings()))), 1)          # and the next one works

    def test_other_address_tried_when_the_first_is_refused(self):
        _srv, port = self.server()
        d = Device("x", "escl", "http://127.0.0.1:%d/eSCL" % closed_port(), "127.0.0.1",
                   ["http://127.0.0.1:%d/eSCL" % port])
        s = scan_escl.EsclScanner(d)
        self.assertEqual(s.capabilities().model, "Dell Color MFP E525w")


# ---- untrusted answers ------------------------------------------------------------------
class Hostile(ServerCase):
    def test_entity_expansion_refused(self):
        laughs = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
                  b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]><a>&lol2;</a>')
        with self.assertRaises(net.XmlRefused):
            net.parse_xml(laughs)
        external = (b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                    b"<a>&x;</a>")
        with self.assertRaises(net.XmlRefused):
            net.parse_xml(external)
        _srv, port = self.server(caps=laughs)
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        with self.assertRaises(ScanError):
            s.capabilities()

    def test_malformed_xml(self):
        _srv, port = self.server(caps=b"<scan:ScannerCapabilities><oops")
        s = scan_escl.EsclScanner(Device("x", "escl", "http://127.0.0.1:%d/eSCL" % port))
        with self.assertRaises(ScanError) as cm:
            s.capabilities()
        self.assertIn("isn't valid XML", cm.exception.message)
        with self.assertRaises(ScanError):
            net.parse_xml(b"<a/><b/>")
        with self.assertRaises(net.XmlRefused):
            net.parse_xml(b"<a>" * 100 + b"</a>" * 100)               # too deep

    def test_answer_too_large(self):
        _srv, port = self.server(caps=b"<a>" + b"x" * 5000 + b"</a>")
        h = net.Http("http://127.0.0.1:%d/eSCL" % port)
        with self.assertRaises(ScanError) as cm:
            h.request("GET", "ScannerCapabilities", limit=1000)
        self.assertIn("too large", cm.exception.message)

    def test_timeout(self):
        _srv, port = self.server(stall=2)
        h = net.Http("http://127.0.0.1:%d/eSCL" % port)
        t0 = time.time()
        with self.assertRaises(net.NetError) as cm:
            h.request("GET", "ScannerCapabilities", timeout=0.3)
        self.assertEqual(cm.exception.kind, "timeout")
        self.assertIn("didn't answer in time", cm.exception.message)
        self.assertLess(time.time() - t0, 1.5)

    def test_refused(self):
        h = net.Http("http://127.0.0.1:%d/" % closed_port())
        with self.assertRaises(net.NetError) as cm:
            h.request("GET", "/")
        self.assertEqual(cm.exception.kind, "refused")

    def test_no_redirect_to_another_host(self):
        class Redirect(Handler):
            def do_GET(self):
                self.send(302, headers=[("Location", "http://192.0.2.7/elsewhere")])
        _srv, port = self.server(Redirect)
        with self.assertRaises(net.NetError) as cm:
            net.Http("http://127.0.0.1:%d/" % port).request("GET", "/")
        self.assertIn("another address", cm.exception.message)

    def test_picture_headers(self):
        self.assertEqual(net.check_image(picture(40, 30), 300).sizes, [(40, 30)])
        self.assertEqual(net.check_image(picture(40, 30, "PNG"), 300).sizes, [(40, 30)])
        self.assertEqual(net.check_image(picture(40, 30, "TIFF"), 300).sizes, [(40, 30)])
        bmp = picture(40, 30, "BMP")
        self.assertEqual(net.check_image(bmp, 300).kind, "bmp")
        self.assertEqual(net.check_image(bmp[14:], 300).kind, "bmp")    # a bare DIB (WSD "dib")
        with self.assertRaises(ScanError):
            net.check_image(b"GIF89a....", 300)
        tiff = bytearray(picture(10, 10, "TIFF"))
        self.assertEqual(net.image_sizes(bytes(tiff), "tiff"), [(10, 10)])


# ---- a fake WS-Scan scanner -------------------------------------------------------------------
SOAP_NS = ('xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
           'xmlns:wse="http://schemas.xmlsoap.org/ws/2004/08/eventing" '
           'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
           'xmlns:wscn="http://schemas.microsoft.com/windows/2006/08/wdp/scan" '
           'xmlns:wsdp="http://schemas.xmlsoap.org/ws/2006/02/devprof" '
           'xmlns:mex="http://schemas.xmlsoap.org/ws/2004/09/mex" '
           'xmlns:xop="http://www.w3.org/2004/08/xop/include"')


def soap(body, action="x"):
    return ('<?xml version="1.0" encoding="UTF-8"?><soap:Envelope %s><soap:Header>'
            "<wsa:Action>%s</wsa:Action></soap:Header><soap:Body>%s</soap:Body>"
            "</soap:Envelope>" % (SOAP_NS, action, body)).encode()


def fault(code):
    return soap("<soap:Fault><soap:Code><soap:Value>soap:Sender</soap:Value><soap:Subcode>"
                "<soap:Value>wscn:%s</soap:Value></soap:Subcode></soap:Code><soap:Reason>"
                '<soap:Text xml:lang="en">%s</soap:Text></soap:Reason></soap:Fault>' % (code, code),
                "http://schemas.xmlsoap.org/ws/2004/08/addressing/fault")


def wsd_source(prefix):
    return ("<wscn:%sOpticalResolution><wscn:Width>600</wscn:Width><wscn:Height>600</wscn:Height>"
            "</wscn:%sOpticalResolution><wscn:%sResolutions><wscn:Widths><wscn:Width>100"
            "</wscn:Width><wscn:Width>200</wscn:Width><wscn:Width>300</wscn:Width><wscn:Width>600"
            "</wscn:Width></wscn:Widths><wscn:Heights><wscn:Height>100</wscn:Height><wscn:Height>"
            "200</wscn:Height><wscn:Height>300</wscn:Height><wscn:Height>600</wscn:Height>"
            "</wscn:Heights></wscn:%sResolutions><wscn:%sColor><wscn:ColorEntry>BlackAndWhite1"
            "</wscn:ColorEntry><wscn:ColorEntry>Grayscale8</wscn:ColorEntry><wscn:ColorEntry>RGB24"
            "</wscn:ColorEntry></wscn:%sColor><wscn:%sMinimumSize><wscn:Width>100</wscn:Width>"
            "<wscn:Height>100</wscn:Height></wscn:%sMinimumSize><wscn:%sMaximumSize><wscn:Width>"
            "8500</wscn:Width><wscn:Height>11690</wscn:Height></wscn:%sMaximumSize>"
            % ((prefix,) * 10))


WSD_ELEMENTS = soap(
    "<wscn:GetScannerElementsResponse><wscn:ScannerElements>"
    '<wscn:ElementData Name="wscn:ScannerDescription" Valid="true"><wscn:ScannerDescription>'
    "<wscn:ScannerName>Dell E525w Scanner</wscn:ScannerName></wscn:ScannerDescription>"
    "</wscn:ElementData>"
    '<wscn:ElementData Name="wscn:ScannerConfiguration" Valid="true"><wscn:ScannerConfiguration>'
    "<wscn:DeviceSettings><wscn:FormatsSupported><wscn:FormatValue>jfif</wscn:FormatValue>"
    "<wscn:FormatValue>pdf-a</wscn:FormatValue></wscn:FormatsSupported></wscn:DeviceSettings>"
    "<wscn:Platen>%s</wscn:Platen><wscn:ADF><wscn:ADFSupportsDuplex>true</wscn:ADFSupportsDuplex>"
    "<wscn:ADFFront>%s</wscn:ADFFront></wscn:ADF></wscn:ScannerConfiguration></wscn:ElementData>"
    '<wscn:ElementData Name="wscn:ScannerStatus" Valid="true"><wscn:ScannerStatus>'
    "<wscn:ScannerState>Idle</wscn:ScannerState></wscn:ScannerStatus></wscn:ElementData>"
    "</wscn:ScannerElements></wscn:GetScannerElementsResponse>" % (wsd_source("Platen"),
                                                                    wsd_source("ADF")))


def metadata(port, scanner=True):
    hosted = ("<wsdp:Hosted><wsa:EndpointReference><wsa:Address>http://192.0.2.77:%d/WDP/SCAN"
              "</wsa:Address></wsa:EndpointReference><wsdp:Types>wscn:ScannerServiceType"
              "</wsdp:Types><wsdp:ServiceId>uri:scan</wsdp:ServiceId></wsdp:Hosted>" % port
              if scanner else "")
    return soap("<mex:Metadata><mex:MetadataSection Dialect=\"http://schemas.xmlsoap.org/ws/2006/"
                "02/devprof/ThisModel\"><wsdp:ThisModel><wsdp:Manufacturer>Dell</wsdp:Manufacturer>"
                "<wsdp:ModelName>Dell Color MFP E525w</wsdp:ModelName></wsdp:ThisModel>"
                "</mex:MetadataSection><mex:MetadataSection Dialect=\"http://schemas.xmlsoap.org/ws/"
                "2006/02/devprof/Relationship\"><wsdp:Relationship Type=\"http://schemas.xmlsoap.org"
                "/ws/2006/02/devprof/host\"><wsdp:Hosted><wsa:EndpointReference><wsa:Address>"
                "http://192.0.2.77:%d/WDP/PRINT</wsa:Address></wsa:EndpointReference><wsdp:Types>"
                "wprt:PrinterServiceType</wsdp:Types></wsdp:Hosted>%s</wsdp:Relationship>"
                "</mex:MetadataSection></mex:Metadata>" % (port, hosted))


def mtom(jpeg):
    root = soap('<wscn:RetrieveImageResponse><wscn:ScanData><xop:Include href="cid:img1%40kz"/>'
                "</wscn:ScanData></wscn:RetrieveImageResponse>")
    b = b"MIMEBoundaryurn_uuid_4aa7d814"
    body = (b"--" + b + b"\r\nContent-Type: application/xop+xml; type=\"application/soap+xml\"; "
            b"charset=UTF-8\r\nContent-Transfer-Encoding: binary\r\nContent-ID: <root@kz>\r\n\r\n"
            + root + b"\r\n--" + b + b"\r\nContent-Type: image/jpeg\r\nContent-Transfer-Encoding: "
            b"binary\r\nContent-ID: <img1@kz >\r\n\r\n" + jpeg + b"\r\n--" + b + b"--\r\n")
    ctype = ('multipart/related; type="application/xop+xml"; boundary="%s"; start="<root@kz>"; '
             'start-info="application/soap+xml"' % b.decode())
    return body, ctype


class Wsd(Handler):
    def do_POST(self):
        st = self.server.st
        body = self.body().decode()
        action = re.search(r"<wsa:Action>(.*?)</wsa:Action>", body).group(1).rsplit("/", 1)[-1]
        st["requests"].append((self.path, action, body))
        port = self.server.server_address[1]
        if self.path == "/dev" and action == "Get":
            return self.send(200, metadata(port, st.get("scan_service", True)),
                             "application/soap+xml")
        if self.path == "/StableWSDiscoveryEndpoint/schemas-xmlsoap-org_ws_2005_04_discovery":
            mid = re.search(r"<wsa:MessageID>(.*?)</wsa:MessageID>", body).group(1)
            return self.send(200, probe_matches(mid, "http://127.0.0.1:%d/dev" % port))
        if action == "Subscribe" and self.path == "/WDP/SCAN":
            st["subscribe"] = body
            ctx = re.search(r"<wscn:ClientContext>(.*?)</wscn:ClientContext>", body).group(1)
            # (the manager named on another host: the client must stay on this device)
            return self.send(200, soap(
                "<wse:SubscribeResponse><wse:SubscriptionManager><wsa:Address>"
                "http://192.0.2.77:%d/WDP/SCAN/sub</wsa:Address><wsa:ReferenceParameters>"
                "<wse:Identifier>urn:uuid:sub-1</wse:Identifier></wsa:ReferenceParameters>"
                "</wse:SubscriptionManager><wse:Expires>PT1H</wse:Expires>"
                "<wscn:DestinationResponses><wscn:DestinationResponse><wscn:ClientContext>%s"
                "</wscn:ClientContext><wscn:DestinationToken>dest-77</wscn:DestinationToken>"
                "</wscn:DestinationResponse></wscn:DestinationResponses></wse:SubscribeResponse>"
                % (port, ctx)), "application/soap+xml")
        if action in ("Renew", "Unsubscribe") and self.path == "/WDP/SCAN/sub":
            st.setdefault("eventing", []).append((action, body))
            return self.send(200, soap("<wse:RenewResponse><wse:Expires>PT30M</wse:Expires>"
                                       "</wse:RenewResponse>" if action == "Renew" else ""))
        if self.path != "/WDP/SCAN":
            return self.send(404)
        if action == "GetScannerElements":
            return self.send(200, WSD_ELEMENTS, "application/soap+xml")
        if action == "CreateScanJob":
            if st.get("refuse"):
                return self.send(500, fault("ServerErrorNotAcceptingJobs"))
            return self.send(200, soap("<wscn:CreateScanJobResponse><wscn:JobId>7</wscn:JobId>"
                                       "<wscn:JobToken>tok-7</wscn:JobToken>"
                                       "</wscn:CreateScanJobResponse>"), "application/soap+xml")
        if action == "RetrieveImage":
            if st["pages"]:
                data, ctype = mtom(st["pages"].pop(0))
                return self.send(200, data, ctype)
            return self.send(400, fault("ClientErrorNoImagesAvailable"), "application/soap+xml")
        if action == "CancelJob":
            st["deletes"].append("cancel")
            return self.send(200, soap("<wscn:CancelJobResponse/>"))
        self.send(400, fault("ClientErrorInvalidArgs"))


def probe_matches(relates, xaddr, types="wsdp:Device wscn:ScanDeviceType wprt:PrintDeviceType"):
    return ('<?xml version="1.0" encoding="UTF-8"?><soap:Envelope %s '
            'xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"><soap:Header>'
            "<wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>"
            "<wsa:RelatesTo>%s</wsa:RelatesTo></soap:Header><soap:Body><wsd:ProbeMatches>"
            "<wsd:ProbeMatch><wsa:EndpointReference><wsa:Address>urn:uuid:dell-e525w"
            "</wsa:Address></wsa:EndpointReference><wsd:Types>%s</wsd:Types>"
            "<wsd:XAddrs>%s</wsd:XAddrs><wsd:MetadataVersion>1</wsd:MetadataVersion>"
            "</wsd:ProbeMatch></wsd:ProbeMatches></soap:Body></soap:Envelope>"
            % (SOAP_NS, relates, types, xaddr)).encode()


class WsdScanning(ServerCase):
    def scanner(self, **state):
        srv, port = self.server(Wsd, **state)
        return srv, scan_wsd.WsdScanner(Device("x", "wsd", "http://127.0.0.1:%d/WDP/SCAN" % port),
                                        sleep=lambda _s: None)

    def test_capabilities(self):
        _srv, s = self.scanner()
        caps = s.capabilities()
        self.assertEqual(caps.model, "Dell E525w Scanner")
        self.assertEqual(sorted(caps.sources), ["duplex", "feeder", "platen"])
        p = caps.sources["platen"]
        self.assertEqual(p.resolutions, [100, 200, 300, 600])
        self.assertEqual(p.colors, ["color", "gray", "bw"])
        self.assertEqual((p.max_w, p.max_h), (8.5, 11.69))
        self.assertEqual(p.formats, ["jfif", "pdf-a"])

    def test_two_page_feeder_job_with_mtom(self):
        jpg = [picture(300, 400), picture(300, 400, color=(0, 150, 0))]
        srv, s = self.scanner(pages=list(jpg))
        pages = list(s.scan(ScanSettings("feeder", "color", 300, "letter")))
        self.assertEqual([p.data for p in pages], jpg)
        actions = [a for _p, a, _b in srv.st["requests"]]
        self.assertEqual(actions, ["GetScannerElements", "CreateScanJob", "RetrieveImage",
                                   "RetrieveImage", "RetrieveImage"])
        ticket = srv.st["requests"][1][2]
        for part in ("<wscn:InputSource>ADF</wscn:InputSource>",
                     "<wscn:ImagesToTransfer>0</wscn:ImagesToTransfer>",
                     "<wscn:Format>jfif</wscn:Format>", "<wscn:ColorProcessing>RGB24<",
                     "<wscn:ScanRegionWidth>8500<", "<wscn:ScanRegionHeight>11000<",
                     "<wscn:JobInformation>KanzonasPDF</wscn:JobInformation>"):
            self.assertIn(part, ticket)
        self.assertIn("<wscn:JobId>7</wscn:JobId><wscn:JobToken>tok-7</wscn:JobToken>",
                      srv.st["requests"][2][2])
        self.assertIn("<wsa:To>http://127.0.0.1:", srv.st["requests"][2][2])
        self.assertEqual(srv.st["deletes"], [])          # finished: nothing to cancel

    def test_platen_takes_one_picture(self):
        srv, s = self.scanner(pages=[picture(50, 50), picture(50, 50)])
        self.assertEqual(len(list(s.scan(ScanSettings("platen")))), 1)
        self.assertIn("<wscn:ImagesToTransfer>1</wscn:ImagesToTransfer>", srv.st["requests"][1][2])

    def test_duplex_ticket_has_both_sides(self):
        srv, s = self.scanner(pages=[picture(50, 50)])
        list(s.scan(ScanSettings("duplex")))
        t = srv.st["requests"][1][2]
        self.assertIn("ADFDuplex", t)
        self.assertIn("<wscn:MediaBack>", t)

    def test_empty_feeder_and_refusal(self):
        _srv, s = self.scanner()
        with self.assertRaises(ScanError) as cm:
            list(s.scan(ScanSettings("feeder")))
        self.assertIn("feeder is empty", cm.exception.message)
        srv, s = self.scanner(refuse=True)
        with self.assertRaises(ScanError) as cm:
            list(s.scan(ScanSettings("platen")))
        self.assertIn("own panel", cm.exception.message)

    def test_mtom_like_microsofts_example(self):
        jpg = picture(20, 20)
        body, ctype = mtom(jpg)
        root, att = scan_wsd.parse_multipart(body, ctype)
        self.assertEqual(att, jpg)
        self.assertEqual(net.local(root.tag), "Envelope")
        # without a start parameter or a matching cid: the first part is the message
        root, att = scan_wsd.parse_multipart(body.replace(b"cid:img1", b"cid:nope"),
                                             ctype.replace('start="<root@kz>"; ', ""))
        self.assertEqual(att, jpg)

    def test_metadata_finds_the_scan_service_on_the_device_that_answered(self):
        _srv, port = self.server(Wsd)
        meta = scan_wsd.metadata("http://127.0.0.1:%d/dev" % port, "urn:uuid:dell-e525w")
        self.assertEqual(meta["scan"], ["http://127.0.0.1:%d/WDP/SCAN" % port])
        self.assertEqual(meta["model"], "Dell Color MFP E525w")
        self.assertTrue(meta["printer"])


# ---- discovery over UDP --------------------------------------------------------------------
def udp_responder(answer, count=1):
    """A UDP socket on 127.0.0.1 answering each datagram with answer(datagram) (a list)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    s.settimeout(5)

    def run():
        try:
            for _ in range(count):
                data, src = s.recvfrom(65535)
                for reply in answer(data):
                    s.sendto(reply, src)
        except OSError:
            pass
        finally:
            s.close()
    threading.Thread(target=run, daemon=True).start()
    return s.getsockname()[1]


def dns_name(name):
    out = b""
    for label in name.split("."):
        out += bytes([len(label)]) + label.encode()
    return out + b"\x00"


def rr(name, rtype, data):
    return dns_name(name) + struct.pack(">HHIH", rtype, 0x8001, 120, len(data)) + data


def mdns_answer(qid, port):
    inst = "Dell E525w._uscan._tcp.local"
    txt = b"".join(bytes([len(x)]) + x for x in (b"txtvers=1", b"ty=Dell Color MFP E525w",
                                                 b"rs=eSCL", b"UUID=4509a320", b"is=platen,adf",
                                                 b"duplex=T", b"cs=color,grayscale,binary"))
    records = [rr("_uscan._tcp.local", 12, dns_name(inst)),
               rr(inst, 33, struct.pack(">HHH", 0, 0, port) + dns_name("dell-e525w.local")),
               rr(inst, 16, txt), rr("dell-e525w.local", 1, bytes([10, 0, 0, 99]))]
    return struct.pack(">HHHHHH", qid, 0x8400, 0, 1, 0, 3) + b"".join(records)


class Discovery(ServerCase):
    def test_mdns_answer_becomes_an_escl_device(self):
        def answer(data):
            qid = struct.unpack(">H", data[:2])[0]
            return [mdns_answer(qid ^ 1, 1234),      # (an answer to someone else's query)
                    mdns_answer(qid, 8080)]
        port = udp_responder(answer, count=2)
        with mock.patch.object(scan_escl, "MDNS", ("127.0.0.1", port)):
            found = scan_escl.browse(window=0.8, target="127.0.0.1")
        self.assertEqual(len(found), 1)
        d = found[0]
        self.assertEqual((d.name, d.protocol, d.host), ("Dell Color MFP E525w", "escl", "127.0.0.1"))
        # reached at the address that answered, not the address the record names
        self.assertEqual(d.address, "http://127.0.0.1:8080/eSCL")
        self.assertEqual(d.info["txt"]["duplex"], "T")

    def test_dns_parser_survives_garbage(self):
        for junk in (b"", b"\x00" * 11, b"\x00\x01\x84\x00\x00\x00\x00\x01\x00\x00\x00\x00\xc0\x0c",
                     os.urandom(300)):
            try:
                scan_escl.parse_message(junk)
            except (ValueError, IndexError, struct.error):
                pass

    def test_ws_discovery_probe_matches_become_a_wsd_device(self):
        _srv, http_port = self.server(Wsd)
        seen = []

        def answer(data):
            text = data.decode()
            seen.append(text)
            mid = re.search(r"<wsa:MessageID>(.*?)</wsa:MessageID>", text).group(1)
            return [probe_matches("urn:uuid:not-ours", "http://192.0.2.1/x"),
                    # XAddrs naming another host: the device that answered is asked instead
                    probe_matches(mid, "http://192.0.2.50:%d/dev" % http_port)]
        port = udp_responder(answer, count=3)
        with mock.patch.object(scan_wsd, "MULTICAST", ("127.0.0.1", port)):
            scanners_, printers = scan_wsd.discover(window=0.8, target="127.0.0.1")
        self.assertIn("<wsd:Types>wscn:ScanDeviceType</wsd:Types>", seen[0])
        self.assertEqual(printers, [])
        self.assertEqual(len(scanners_), 1)
        d = scanners_[0]
        self.assertEqual((d.name, d.protocol), ("Dell Color MFP E525w", "wsd"))
        self.assertEqual(d.address, "http://127.0.0.1:%d/WDP/SCAN" % http_port)

    def test_printer_without_scan_service(self):
        _srv, http_port = self.server(Wsd, scan_service=False)
        matches = [{"address": "urn:uuid:x", "types": "wprt:PrintDeviceType", "host": "127.0.0.1",
                    "xaddrs": ["http://127.0.0.1:%d/dev" % http_port]}]
        found, printers = scan_wsd.from_matches(matches)
        self.assertEqual(found, [])
        self.assertEqual([p.name for p in printers], ["Dell Color MFP E525w"])

    def test_discover_everything_keeps_going_when_one_way_fails(self):
        d = Device("A", "escl", "http://10.0.0.5/eSCL", "10.0.0.5")
        with mock.patch.object(scan_escl, "browse", lambda *a, **k: [d]), \
                mock.patch.object(scan_wsd, "discover", mock.Mock(side_effect=OSError("no"))), \
                mock.patch.object(scanners, "system_kind", lambda: None):
            log = []
            found, printers = scanners.discover(log=log)
        self.assertEqual(found, [d])
        self.assertTrue(any("wsd failed" in line for line in log))


class AddByAddress(ServerCase):
    def fakes(self, wsd=([], []), mdns=()):
        return [mock.patch.object(scan_escl, "browse", lambda *a, **k: list(mdns)),
                mock.patch.object(scan_wsd, "discover", lambda *a, **k: wsd)]

    def run_with(self, patches, text="127.0.0.1"):
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        log = []
        return scanners.add_by_address(text, log=log), log

    def test_escl_first(self):
        _srv, port = self.server()
        _w, wport = self.server(Wsd)
        wsd_dev = Device("W", "wsd", "http://127.0.0.1:%d/WDP/SCAN" % wport, "127.0.0.1")
        d, log = self.run_with(self.fakes(wsd=([wsd_dev], [])) + [
            mock.patch.object(scanners, "ESCL_PORTS", (("http", closed_port()), ("http", port)))])
        self.assertEqual((d.protocol, d.name), ("escl", "Dell Color MFP E525w"))
        self.assertEqual(d.address, "http://127.0.0.1:%d/eSCL" % port)
        self.assertTrue(any("refused" in line for line in log))

    def test_then_wsd_by_directed_probe(self):
        _srv, wport = self.server(Wsd)
        directed = [{"address": "urn:uuid:x", "types": "wscn:ScanDeviceType", "host": "127.0.0.1",
                     "xaddrs": ["http://127.0.0.1:%d/dev" % wport]}]
        d, _log = self.run_with(self.fakes() + [
            mock.patch.object(scanners, "ESCL_PORTS", (("http", closed_port()),)),
            mock.patch.object(scan_wsd, "directed_probe", lambda *a, **k: directed)])
        self.assertEqual(d.protocol, "wsd")
        self.assertEqual(d.address, "http://127.0.0.1:%d/WDP/SCAN" % wport)

    def test_wsd_directed_probe_over_http(self):
        _srv, wport = self.server(Wsd)
        with mock.patch.object(scan_wsd, "STABLE_PATH", scan_wsd.STABLE_PATH), \
                mock.patch.object(net, "make_url", side_effect=lambda s, h, p, path:
                                  "%s://%s:%d%s" % (s, h, wport if p in (80, 5357) else p, path)):
            m = scan_wsd.directed_probe("127.0.0.1")
        self.assertEqual(m[0]["xaddrs"], ["http://127.0.0.1:%d/dev" % wport])

    def test_web_page_but_no_scanning_says_turn_wsd_on(self):
        _srv, port = self.server()
        with self.assertRaises(ScanError) as cm:
            self.run_with(self.fakes() + [
                mock.patch.object(scanners, "ESCL_PORTS", (("http", closed_port()),)),
                mock.patch.object(scanners, "WEB_PORTS", (("http", port),)),
                mock.patch.object(scan_wsd, "directed_probe", lambda *a, **k: [])])
        msg = cm.exception.message
        self.assertIn("WSD scanning is turned off", msg)
        self.assertIn("http://127.0.0.1", msg)
        self.assertIn("set WSD to Enable", msg)

    def test_printer_only_over_wsd(self):
        p = Device("Dell", "wsd", "http://127.0.0.1/dev", "127.0.0.1")
        with self.assertRaises(ScanError) as cm:
            self.run_with(self.fakes(wsd=([], [p])) + [
                mock.patch.object(scanners, "ESCL_PORTS", (("http", closed_port()),))])
        self.assertIn("set WSD (or WSD Scan) to Enable", cm.exception.message)

    def test_nothing_there(self):
        with self.assertRaises(ScanError) as cm:
            self.run_with(self.fakes() + [
                mock.patch.object(scanners, "ESCL_PORTS", (("http", closed_port()),)),
                mock.patch.object(scanners, "WEB_PORTS", (("http", closed_port()),)),
                mock.patch.object(scan_wsd, "directed_probe", lambda *a, **k: [])])
        self.assertIn("Nothing answered at 127.0.0.1", cm.exception.message)

    def test_typed_addresses(self):
        self.assertEqual(scanners.parse_address(" 192.168.1.20 "), ("192.168.1.20", None))
        self.assertEqual(scanners.parse_address("192.168.1.20:80"), ("192.168.1.20", None))
        self.assertEqual(scanners.parse_address("http://10.0.0.2:8080/eSCL"),
                         ("10.0.0.2", "http://10.0.0.2:8080/eSCL"))
        for bad in ("", "a b; rm", "ftp://x"):
            with self.assertRaises(ScanError):
                scanners.parse_address(bad)


# ---- WIA and SANE, their commands stood in for ----------------------------------------------
class FakeProc:
    def __init__(self, stdout=b"", stderr=b""):
        self.stdout, self.stderr, self.returncode = io.BytesIO(stdout), io.BytesIO(stderr), 0

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


# a stand-in for comtypes and WIA's scripting objects (as comtypes' late binding shows them)
class Coll:
    def __init__(self, items):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        if isinstance(i, str):
            return next(x for x in self.items if x.Name == i)
        return self.items[i - 1]


class Prop:
    def __init__(self, pid, value=0, name="", subtype=0, values=(), lo=0, hi=0):
        self.PropertyID, self.Value, self.Name, self.SubType = pid, value, name, subtype
        self.SubTypeValues, self.SubTypeMin, self.SubTypeMax = Coll(values), lo, hi


class ComError(Exception):
    def __init__(self, hresult, text):
        super().__init__(hresult, text, None)
        self.hresult, self.text = hresult, text


class Picture:
    def __init__(self, data, ext="png"):
        self.data, self.FileExtension = data, ext

    def SaveFile(self, path):
        with open(path, "wb") as f:
            f.write(self.data)


class WiaItem:
    def __init__(self, results, dpi_prop):
        self.results, self.formats = list(results), []
        self.Properties = Coll([Prop(p) for p in (6146, 4103, 6148, 6149, 6150, 6151, 6152)]
                               + [dpi_prop])

    def Transfer(self, fmt=None):
        self.formats.append(fmt)
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class WiaDevice:
    def __init__(self, handling, item):
        self.Properties = Coll([Prop(3086, handling), Prop(3088), Prop(3096)])
        self.Items = Coll([item])


class WiaInfo:
    def __init__(self, dev_id, kind, name, device=None):
        self.DeviceID, self.Type, self.device = dev_id, kind, device
        self.Properties = Coll([Prop(7, name, "Name")])

    def Connect(self):
        return self.device


def fake_comtypes(infos, calls):
    import types
    ct = types.ModuleType("comtypes")
    client = types.ModuleType("comtypes.client")
    ct.COINIT_APARTMENTTHREADED = 2
    ct.COMError = ComError
    ct.CoInitializeEx = lambda flags: calls.append(("init", flags, threading.get_ident()))
    ct.CoUninitialize = lambda: calls.append(("uninit", threading.get_ident()))

    def create(progid, dynamic=False):
        calls.append(("create", progid, dynamic))
        m = types.SimpleNamespace(DeviceInfos=Coll(infos))
        return m
    client.CreateObject = create
    ct.client = client
    return mock.patch.dict(sys.modules, {"comtypes": ct, "comtypes.client": client})


EMPTY = ComError(-2145320957, "There are no documents in the document feeder.")  # 0x80210003


class Wia(unittest.TestCase):
    def setup(self, results=(), handling=7, dpi=None):
        self.calls = []
        dpi = dpi or Prop(6147, 300, subtype=2, values=[100, 200, 300, 600])
        self.item = WiaItem(results, dpi)
        self.dev = WiaDevice(handling, self.item)
        infos = [WiaInfo("{CAM}\\0001", 2, "A camera"),
                 WiaInfo("{6BDD}\\0002", 1, "Dell E525w (WSD)", self.dev)]
        p = fake_comtypes(infos, self.calls)
        p.start()
        self.addCleanup(p.stop)
        return Device("Dell E525w (WSD)", "wia", "{6BDD}\\0002")

    def balanced(self):
        inits = [c for c in self.calls if c[0] == "init"]
        self.assertEqual(len(inits), len([c for c in self.calls if c[0] == "uninit"]))
        self.assertTrue(all(c[1] == 2 for c in inits))                  # single-threaded COM
        self.assertTrue(all(c[2] for c in self.calls if c[0] == "create"))   # late-bound

    def test_listing(self):
        self.setup()
        found = scan_local.wia_devices()
        self.assertEqual([(d.name, d.protocol, d.address) for d in found],
                         [("Dell E525w (WSD)", "wia", "{6BDD}\\0002")])
        self.balanced()

    def test_no_comtypes_is_a_plain_message(self):
        with mock.patch.dict(sys.modules, {"comtypes": None}):
            log = []
            self.assertEqual(scan_local.wia_devices(log), [])
            self.assertIn("comtypes", log[0])

    def test_capabilities_from_the_driver(self):
        d = self.setup(handling=7)
        caps = scan_local.WiaScanner(d).capabilities()
        self.assertEqual(sorted(caps.sources), ["duplex", "feeder", "platen"])
        self.assertEqual(caps.sources["platen"].resolutions, [100, 200, 300, 600])
        d = self.setup(handling=0, dpi=Prop(6147, 300, subtype=1, lo=50, hi=300))
        caps = scan_local.WiaScanner(d).capabilities()
        self.assertEqual(list(caps.sources), ["platen"])                  # a flatbed only
        self.assertEqual(caps.sources["platen"].resolutions, [75, 100, 150, 200, 240, 300])
        self.balanced()

    def test_feeder_scan(self):
        pngs = [picture(255, 330, "PNG"), picture(255, 330, "PNG")]
        d = self.setup([Picture(pngs[0]), Picture(pngs[1]), EMPTY])
        pages = list(scan_local.WiaScanner(d).scan(ScanSettings("feeder", "gray", 150)))
        self.assertEqual([p.data for p in pages], pngs)
        dev, item = self.dev.Properties, self.item.Properties
        self.assertEqual((dev.items[1].Value, dev.items[2].Value), (1, 0))   # feeder, all pages
        values = {p.PropertyID: p.Value for p in item.items}
        self.assertEqual((values[6146], values[4103], values[6147], values[6148], values[6151],
                          values[6152]), (2, 2, 150, 150, 1275, 1650))
        self.assertEqual(self.item.formats, ["{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"] * 3)
        self.balanced()

    def test_glass_takes_one_page_and_falls_back_to_the_drivers_format(self):
        bmp = picture(40, 50, "BMP")
        d = self.setup([ComError(-2147024809, "bad format"), Picture(bmp, "bmp"),
                        Picture(bmp, "bmp")])
        pages = list(scan_local.WiaScanner(d).scan(ScanSettings("platen", "bw", 300)))
        self.assertEqual([p.kind for p in pages], ["bmp"])
        self.assertEqual(self.item.formats, ["{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}", None])

    def test_empty_feeder_message(self):
        d = self.setup([EMPTY])
        with self.assertRaises(ScanError) as cm:
            list(scan_local.WiaScanner(d).scan(ScanSettings("feeder")))
        self.assertIn("feeder is empty", cm.exception.message)
        self.assertIn("80210003", cm.exception.details)
        self.balanced()


SANE_OPTIONS = """
Options specific to device `airscan:e0:Dell E525w':
  Standard:
    --resolution 75|100|150|300|600dpi [300]
        Sets the resolution of the scanned image.
    --mode Color|Gray|Lineart [Color]
        Selects the scan mode.
    --source Flatbed|ADF|ADF Duplex [Flatbed]
        Selects the scan source.
  Geometry:
    -l 0..215.9mm [0]
    -t 0..297.011mm [0]
    -x 0..215.9mm [215.9]
    -y 0..297.011mm [297.011]
"""


class Sane(unittest.TestCase):
    def test_listing_and_options(self):
        with mock.patch.object(scan_local, "scanimage", lambda: "/usr/bin/scanimage"), \
                mock.patch.object(scan_local, "run", lambda cmd, t: (
                    0, "airscan:e0:Dell E525w\tDell\tE525w\teSCL network scanner\n", "")):
            found = scan_local.sane_devices()
        self.assertEqual([(d.name, d.address) for d in found],
                         [("Dell E525w", "airscan:e0:Dell E525w")])
        o = scan_local.parse_sane_options(SANE_OPTIONS)
        self.assertEqual(o["sources"], {"platen": "Flatbed", "feeder": "ADF", "duplex": "ADF Duplex"})
        self.assertEqual(o["modes"], {"color": "Color", "gray": "Gray", "bw": "Lineart"})
        self.assertEqual(o["resolutions"], [75, 100, 150, 300, 600])
        self.assertEqual((o["x"], o["y"]), (215.9, 297.011))
        rng = scan_local.parse_sane_options("    --resolution 50..1200dpi (in steps of 1) [300]")
        self.assertEqual(rng["resolutions"], [75, 100, 150, 200, 240, 300, 400, 600, 1200])

    def test_duplex_scan_command(self):
        pngs = [picture(80, 100, "PNG"), picture(80, 100, "PNG")]
        seen = {}

        def popen(cmd, **kw):
            seen["cmd"], seen["kw"] = cmd, kw
            batch = next(a for a in cmd if a.startswith("--batch="))[8:]
            err = ""
            for i, data in enumerate(pngs, 1):
                with open(batch % i, "wb") as f:
                    f.write(data)
                err += "Scanning page %d\nScanned page %d. (scanner status = 5)\n" % (i, i)
            return FakeProc(stderr=(err + "Batch terminated, 2 pages scanned\n").encode())
        dev = Device("Dell", "sane", "airscan:e0:Dell E525w")
        with mock.patch.object(scan_local, "scanimage", lambda: "/usr/bin/scanimage"), \
                mock.patch.object(scan_local, "run", lambda cmd, t: (0, SANE_OPTIONS, "")), \
                mock.patch.object(scan_local.subprocess, "Popen", popen):
            s = scan_local.SaneScanner(dev)
            caps = s.capabilities()
            self.assertEqual(sorted(caps.sources), ["duplex", "feeder", "platen"])
            pages = list(s.scan(ScanSettings("duplex", "bw", 300, "letter")))
        self.assertEqual([p.data for p in pages], pngs)
        cmd = seen["cmd"]
        self.assertEqual(cmd[:6], ["/usr/bin/scanimage", "-d", "airscan:e0:Dell E525w",
                                   "--format=png", "--resolution", "300"])
        self.assertEqual(cmd[6:14], ["--mode", "Lineart", "--source", "ADF Duplex", "-x", "215.9",
                                     "-y", "279.4"])
        self.assertTrue(cmd[14].startswith("--batch=") and cmd[14].endswith("page%04d.png"))
        self.assertNotIn("--batch-count=1", cmd)

    def test_empty_feeder(self):
        with mock.patch.object(scan_local, "scanimage", lambda: "/usr/bin/scanimage"), \
                mock.patch.object(scan_local, "run", lambda cmd, t: (0, SANE_OPTIONS, "")), \
                mock.patch.object(scan_local.subprocess, "Popen", lambda cmd, **kw: FakeProc(
                    stderr=b"scanimage: sane_start: Document feeder out of documents\n")):
            with self.assertRaises(ScanError) as cm:
                list(scan_local.SaneScanner(Device("D", "sane", "x")).scan(ScanSettings("feeder")))
        self.assertIn("feeder is empty", cm.exception.message)


# ---- the watched folder ---------------------------------------------------------------------
class Watch(unittest.TestCase):
    def test_new_files_are_taken_once_complete(self):
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "old.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 old")
        w = scan_local.FolderWatch(folder)
        self.assertEqual(w.poll(), [])
        path = os.path.join(folder, "scan0001.jpg")
        with open(path, "wb") as f:
            f.write(picture(50, 60))
        with open(os.path.join(folder, "notes.txt"), "w") as f:
            f.write("not a scan")
        self.assertEqual(w.poll(), [])          # first seen: maybe still being written
        self.assertEqual(w.poll(), [path])
        self.assertEqual(w.poll(), [])
        page = scan_local.read_watched(path)
        self.assertEqual((page.kind, page.sizes, page.dpi), ("jpeg", [(50, 60)], 0))


# ---- the Scan window -----------------------------------------------------------------------
from kanzonas import scan_dialog  # noqa: E402
from kanzonas.document_view import DocumentView  # noqa: E402
from kanzonas.main_window import MainWindow  # noqa: E402


class FakeScanner:
    protocol = "escl"

    def __init__(self, device, batches):
        self.device, self.batches, self.caps, self.trail = device, batches, None, ["GET caps"]
        self.settings = []

    def capabilities(self):
        src = SourceCaps(resolutions=[100, 300], max_w=8.5, max_h=14)
        return Caps({"platen": src, "feeder": src}, "Fake MFP",
                    "<caps><SerialNumber>SECRET</SerialNumber></caps>")

    def scan(self, settings, report):
        self.settings.append(settings)
        report("Scanning page 1...")
        for data in self.batches.pop(0):
            yield net.check_image(data, settings.dpi)

    def abort(self):
        pass


class ScanWindow(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow()
        self.w.show()
        self.addCleanup(lambda: (setattr(self.w, "_close_confirmed", True), self.w.close()))
        s = self.w.settings
        for k in ("scan_device", "scan_into", "scan_ocr", "scan_source"):
            s.remove(k)
        s.setValue("scan_dpi", "100")
        s.setValue("scan_size", "letter")
        self.dev = Device("Fake MFP", "escl", "http://10.0.0.9/eSCL", "10.0.0.9")
        self.batches = [[picture(850, 1100), picture(850, 1400)], [picture(850, 1100)]]
        self.fake = FakeScanner(self.dev, self.batches)

    def dialog(self, devices=None):
        devices = [self.dev] if devices is None else devices
        if not devices and not self.w.settings.value("scan_device"):
            dlg = scan_dialog.ScanDialog(self.w, discover=lambda cancel=None, log=None: ([], []),
                                         open_scanner=lambda d: self.fake)
            self.addCleanup(lambda: (dlg._stop(), dlg.deleteLater()))
            wait_for(lambda: "find" not in dlg._busy)
            return dlg
        dlg = scan_dialog.ScanDialog(self.w, discover=lambda cancel=None, log=None: (devices, []),
                                     open_scanner=lambda d: self.fake)
        self.addCleanup(lambda: (dlg._stop(), dlg.deleteLater()))
        wait_for(lambda: "find" not in dlg._busy and "caps" not in dlg._busy and
                 dlg.b_scan.isEnabled())
        return dlg

    def scan_once(self, dlg):
        n = len(dlg.pages)
        dlg.b_scan.click()
        wait_for(lambda: "scan" not in dlg._busy)
        self.assertGreater(len(dlg.pages), n)

    def test_scanned_pages_become_a_new_document(self):
        dlg = self.dialog()
        self.assertEqual(dlg.list.count(), 1)
        self.assertIn("eSCL", dlg.list.item(0).text())
        self.assertEqual([dlg.source.itemData(i) for i in range(dlg.source.count())],
                         ["platen", "feeder"])
        self.assertEqual(dlg.dpi.currentData(), 100)          # remembered
        dlg.source.setCurrentIndex(dlg.source.findData("feeder"))
        self.scan_once(dlg)
        self.assertEqual(dlg.b_scan.text(), "Scan more pages")
        self.assertTrue(dlg.b_done.isEnabled())
        self.scan_once(dlg)                                   # Scan more pages
        self.assertEqual(len(dlg.pages), 3)
        self.assertEqual(self.fake.settings[0], ScanSettings("feeder", "color", 100, "letter"))
        dlg.rb_new.setChecked(True)
        dlg.b_done.click()
        v = self.w.view()
        self.assertTrue(v.untitled)
        self.assertTrue(v.dirty)
        self.assertEqual([(round(p.rect.width), round(p.rect.height)) for p in v.doc],
                         [(612, 792), (612, 1008), (612, 792)])          # 100 dpi: 8.5 x 11 in
        img = v.doc[0].get_images(full=True)
        self.assertEqual(len(img), 1)
        self.assertEqual(v.doc.extract_image(img[0][0])["ext"], "jpeg")  # not recompressed
        # remembered for next time
        self.assertEqual(json.loads(self.w.settings.value("scan_device"))["address"],
                         self.dev.address)
        self.assertEqual(self.w.settings.value("scan_source"), "feeder")

    def test_insert_into_current_document_is_one_undo_step(self):
        doc = pymupdf.open()
        for _ in range(3):
            doc.new_page(width=612, height=792)
        v = self.w._open_untitled(doc)
        v.goto_page(0)
        dlg = self.dialog()
        self.assertTrue(dlg.rb_current.isEnabled())
        dlg.rb_current.setChecked(True)
        self.scan_once(dlg)
        with mock.patch.object(self.w, "_pages_unlocked", lambda: True), \
                mock.patch.object(DocumentView, "run_ocr") as ocr:
            dlg.ocr.setChecked(True)
            dlg.b_done.click()
        self.assertEqual(v.doc.page_count, 5)
        self.assertEqual([round(p.rect.height) for p in v.doc], [792, 792, 1008, 792, 792])
        self.assertEqual(len(v.doc[1].get_images()), 1)
        self.assertEqual(ocr.call_args[0][0], [1, 2])           # the new pages made searchable
        v.undo()
        self.assertEqual(v.doc.page_count, 3)
        self.assertEqual(sum(len(p.get_images()) for p in v.doc), 0)
        v.redo()
        self.assertEqual(v.doc.page_count, 5)

    def test_errors_in_plain_words_and_details(self):
        def broken(settings, report):
            raise ScanError("The document feeder is empty: put the pages in it.", "AdfEmpty")
            yield
        self.fake.scan = broken
        dlg = self.dialog()
        dlg.b_scan.click()
        wait_for(lambda: "scan" not in dlg._busy)
        self.assertIn("feeder is empty", dlg.status.text())
        self.assertFalse(dlg.b_done.isEnabled())
        text = dlg.details()
        self.assertIn("Fake MFP", text)
        self.assertIn("AdfEmpty", text)
        self.assertIn("(removed)", text)                     # serial numbers left out
        self.assertNotIn("SECRET", text)
        dlg.copy_details()
        self.assertEqual(QApplication.clipboard().text(), text)

    def test_nothing_found_says_what_was_tried(self):
        dlg = scan_dialog.ScanDialog(self.w, discover=lambda cancel=None, log=None: ([], []),
                                     open_scanner=lambda d: self.fake)
        self.addCleanup(lambda: (dlg._stop(), dlg.deleteLater()))
        wait_for(lambda: "find" not in dlg._busy)
        t = dlg.status.text()
        self.assertIn("No scanners found on this network", t)
        self.assertIn("eSCL (AirScan) and WSD", t)
        self.assertIn("Add by address", t)
        self.assertFalse(dlg.b_scan.isEnabled())

    def test_remembered_scanner_is_listed_before_discovery_finds_it(self):
        self.w.settings.setValue("scan_device", json.dumps(self.dev.to_dict()))
        dlg = self.dialog(devices=[])
        self.assertEqual(dlg.device().key(), self.dev.key())

    def test_remembered_scanner_found_at_a_new_address_is_replaced(self):
        self.w.settings.setValue("scan_device", json.dumps(self.dev.to_dict()))
        moved = Device("Fake MFP", "escl", "http://10.0.0.77/eSCL", "10.0.0.77")
        dlg = self.dialog(devices=[moved])
        self.assertEqual([d.address for d in dlg.devices], [moved.address])
        self.assertEqual(dlg.device().address, moved.address)

    def test_add_by_address_in_the_window(self):
        dlg = self.dialog(devices=[])
        added = Device("Added", "escl", "http://10.0.0.3/eSCL", "10.0.0.3")
        dlg._add = lambda text, log=None: added
        with mock.patch.object(scan_dialog.QInputDialog, "getText",
                               lambda *a, **k: ("10.0.0.3", True)):
            dlg.b_add.click()
        wait_for(lambda: "add" not in dlg._busy and "caps" not in dlg._busy)
        self.assertEqual(dlg.device().name, "Added")

    def test_watched_folder_pages(self):
        folder = tempfile.mkdtemp()
        dlg = self.dialog(devices=[])
        with mock.patch.object(scan_dialog.QFileDialog, "getExistingDirectory",
                               lambda *a, **k: folder):
            dlg.b_watch.click()
        src = pymupdf.open()
        src.new_page(width=300, height=400)
        src.save(os.path.join(folder, "Scan_0001.pdf"))
        main = threading.get_ident()
        looked = []
        real = scan_local.FolderWatch.poll

        def poll(watch):
            looked.append(threading.get_ident())
            return real(watch)
        with mock.patch.object(scan_local.FolderWatch, "poll", poll):
            for _ in range(2):
                dlg._poll_folder()
                wait_for(lambda: "watch" not in dlg._busy)
        self.assertEqual(len(looked), 2)
        self.assertNotIn(main, looked)                 # the folder is read in a worker thread
        self.assertEqual(len(dlg.pages), 1)
        self.assertTrue(dlg.b_done.isEnabled())
        dlg.b_done.click()
        self.assertEqual([(round(p.rect.width), round(p.rect.height)) for p in self.w.view().doc],
                         [(300, 400)])

    def test_closing_with_pages_asks(self):
        dlg = self.dialog()
        self.scan_once(dlg)
        with mock.patch.object(QMessageBox, "question", lambda *a, **k: QMessageBox.No):
            dlg.reject()
        self.assertTrue(dlg.isVisible() or dlg.result() == 0)
        self.assertTrue(dlg.pages)

    def test_menu_and_ribbon(self):
        self.assertIn(self.w.a_scan, self.w.menuBar().actions()[0].menu().actions())
        self.assertEqual(self.w.a_scan.iconText(), "Scan")


# ---- scans started on the printer's panel (WS-Eventing) ------------------------------------
def send_event(srv, sid="scan-id-1", identifier=None, context=None, path=None, body=None):
    """The fake printer sends ScanAvailableEvent to the address KanzonasPDF subscribed with."""
    import http.client
    sub = srv.st["subscribe"]
    url = re.search(r"<wse:NotifyTo><wsa:Address>(.*?)</wsa:Address>", sub).group(1)
    ident = identifier or re.search(r"<wse:Identifier>(.*?)</wse:Identifier>", sub).group(1)
    ctx = context or re.search(r"<wscn:ClientContext>(.*?)</wscn:ClientContext>", sub).group(1)
    _scheme, host, port, upath = net.split_url(url)
    body = body if body is not None else soap(
        "<wscn:ScanAvailableEvent><wscn:ClientContext>%s</wscn:ClientContext>"
        "<wscn:ScanIdentifier>%s</wscn:ScanIdentifier></wscn:ScanAvailableEvent>" % (ctx, sid),
        "http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScanAvailableEvent").replace(
        b"</soap:Header>", b"<wse:Identifier>" + ident.encode() + b"</wse:Identifier>"
        b"</soap:Header>")
    c = http.client.HTTPConnection(host, port, timeout=5)
    c.request("POST", path or upath, body, {"Content-Type": "application/soap+xml"})
    status = c.getresponse().status
    c.close()
    return status


class PanelScans(ServerCase):
    def link(self):
        from kanzonas import scan_events
        srv, port = self.server(Wsd, pages=[picture(100, 100)])
        d = Device("Dell", "wsd", "http://127.0.0.1:%d/WDP/SCAN" % port, "127.0.0.1")
        scans, states = [], []
        link = scan_events.PanelLink(d, lambda sid, token: scans.append((sid, token)),
                                     lambda ok, err: states.append((ok, err)),
                                     name="KanzonasPDF - TESTPC")
        link.start()
        self.addCleanup(lambda: link.stop(wait=True))
        wait_for(lambda: states)
        self.assertEqual(states, [(True, None)])
        return srv, link, scans

    def test_subscribe_event_renew_unsubscribe(self):
        srv, link, scans = self.link()
        sub = srv.st["subscribe"]
        for part in ("<wscn:ClientDisplayName>KanzonasPDF - TESTPC</wscn:ClientDisplayName>",
                     '<wse:Filter Dialect="http://schemas.xmlsoap.org/ws/2006/02/devprof/Action">'
                     "http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScanAvailableEvent<",
                     "<wse:Expires>PT1H</wse:Expires>", "<wsa:Address>http://127.0.0.1:"):
            self.assertIn(part, sub)
        self.assertEqual(send_event(srv), 202)
        wait_for(lambda: scans)
        self.assertEqual(scans, [("scan-id-1", "dest-77")])
        link.renew()
        action, body = srv.st["eventing"][0]
        self.assertEqual(action, "Renew")
        self.assertIn("urn:uuid:sub-1</", body)                 # its reference parameters
        self.assertIn("<wsa:To>http://192.0.2.77:", body)
        link.stop(wait=True)
        self.assertEqual([a for a, _b in srv.st["eventing"]], ["Renew", "Unsubscribe"])
        self.assertIn("urn:uuid:sub-1</", srv.st["eventing"][1][1])

    def test_listener_refuses_what_isnt_the_printers_event(self):
        srv, link, scans = self.link()
        self.assertEqual(send_event(srv, path="/kanzonas-scan/guess"), 404)
        self.assertEqual(send_event(srv, identifier="urn:uuid:someone-else"), 403)
        self.assertEqual(send_event(srv, body=b"<a>" + b"x" * 70000 + b"</a>"), 413)
        self.assertEqual(send_event(srv, body=b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x '
                                              b'"y">]><a>&x;</a>'), 400)
        self.assertEqual(send_event(srv, context="not-ours"), 202)
        time.sleep(0.2)
        self.assertEqual(scans, [])
        # from another address than the printer's
        from kanzonas import scan_events
        other = scan_events.EventListener("10.9.9.9", lambda *a: scans.append(a), "127.0.0.1")
        other.start()
        self.addCleanup(other.stop)
        import http.client
        _s, host, port, path = net.split_url(other.url)
        c = http.client.HTTPConnection(host, port, timeout=5)
        c.request("POST", path, b"<a/>")
        self.assertEqual(c.getresponse().status, 403)
        c.close()
        self.assertEqual(scans, [])

    def test_window_scans_when_the_printer_starts_it(self):
        srv, port = self.server(Wsd, pages=[picture(850, 1100)])
        dev = Device("Dell E525w", "wsd", "http://127.0.0.1:%d/WDP/SCAN" % port, "127.0.0.1")
        w = MainWindow()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        w.settings.setValue("scan_dpi", "100")
        w.settings.remove("scan_device")
        w.settings.setValue("scan_source", "platen")
        dlg = scan_dialog.ScanDialog(w, discover=lambda cancel=None, log=None: ([dev], []))
        self.addCleanup(lambda: (dlg._stop(), dlg.deleteLater()))
        wait_for(lambda: "subscribe" in srv.st and "can also start" in dlg.panel_note.text())
        self.assertIn("Scan to Computer (WSD)", dlg.panel_note.text())
        self.assertEqual(send_event(srv, "panel-42"), 202)
        wait_for(lambda: dlg.pages and "scan" not in dlg._busy)
        create = next(b for _p, a, b in srv.st["requests"] if a == "CreateScanJob")
        self.assertIn("<wscn:CreateScanJobRequest><wscn:ScanIdentifier>panel-42</wscn:"
                      "ScanIdentifier><wscn:DestinationToken>dest-77</wscn:DestinationToken>"
                      "<wscn:ScanTicket>", create)
        self.assertIn("panel: subscribed", dlg.details())
        dlg.b_done.click()
        self.assertEqual([(round(p.rect.width), round(p.rect.height)) for p in w.view().doc],
                         [(612, 792)])
        wait_for(lambda: [a for a, _b in srv.st.get("eventing", [])] == ["Unsubscribe"])


class SelfTest(unittest.TestCase):
    def test_the_built_apps_check(self):
        with mock.patch.object(scan_local, "wia_devices", lambda log=None: []):
            detail = scanners.selftest_check()
        self.assertIn("XML guard", detail)


class Startup(unittest.TestCase):
    def test_nothing_of_scanning_loads_at_start(self):
        code = ("import os, sys, tempfile\nsys.path.insert(0, %r)\n"
                "from PySide6.QtCore import QSettings\n"
                "d = tempfile.mkdtemp()\n"
                "for f in (QSettings.NativeFormat, QSettings.IniFormat):\n"
                "    QSettings.setPath(f, QSettings.UserScope, d)\n"
                "from PySide6.QtWidgets import QApplication\napp = QApplication([])\n"
                "from kanzonas.main_window import MainWindow\nw = MainWindow()\n"
                "print('LOADED', sorted(m for m in sys.modules if (m.startswith('kanzonas.scan')"
                " and m != 'kanzonas.scan_text') or m.startswith('comtypes')))\nsys.stdout.flush()\nos._exit(0)\n" % ROOT)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             timeout=120, env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        line = next(x for x in out.stdout.splitlines() if x.startswith("LOADED"))
        self.assertEqual(line, "LOADED []")


if __name__ == "__main__":
    unittest.main()

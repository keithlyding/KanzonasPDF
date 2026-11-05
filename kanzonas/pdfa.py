"""PDF/A: File > Save as PDF/A writes an archival copy (PDF/A-2b, ISO 19005-2 level B; PDF/A-3b,
ISO 19005-3, when the document has attached files that aren't PDF/A themselves), and
File > Check PDF/A lists what keeps a document from being PDF/A.

Level B ("basic") is about the look of the pages: everything needed to show them is in the
file (fonts embedded, colors defined by an ICC profile), nothing depends on the viewer
(scripts, actions that launch things, encryption), and the file says it is PDF/A in its XMP
metadata. The requirements followed are veraPDF's published rules for PDF/A-2 and -3
(https://github.com/veraPDF/veraPDF-validation-profiles/wiki/PDFA-Parts-2-and-3-rules);
what this module does about each is in the comments where it's done. It checks and fixes
what is common and what can be fixed without changing how the pages look; it's not a formal
validator (veraPDF is: free, from the PDF Association).

No Qt here: pdfa_ui.py has the windows. Everything works on a document of its own (convert
opens the bytes it's given), never on the one being edited, so undo and the journal are
untouched; check() only reads.

What can't be fixed without changing the pages (a font that isn't embedded and that
KanzonasPDF has no copy of, a page larger than 200 inches, a PostScript drawing...) is listed
in the check after saving, page by page.
"""

import datetime
import mimetypes
import os
import re
import struct
import uuid
from xml.sax.saxutils import escape

import pymupdf

from .i18n import tr

m = pymupdf.mupdf

# ---- what PDF/A allows ---------------------------------------------------------------------
# 6.5.1: the actions allowed (Launch, Sound, Movie, ResetForm, ImportData, Hide, SetOCGState,
# Rendition, Trans, GoTo3DView, JavaScript, SetState and NOP aren't) and the named actions
ALLOWED_ACTIONS = {"GoTo", "GoToR", "GoToE", "Thread", "URI", "Named", "SubmitForm"}
ALLOWED_NAMED = {"NextPage", "PrevPage", "FirstPage", "LastPage"}
# 6.3.1: annotation types defined in ISO 32000-1, less 3D, Sound, Screen and Movie
ALLOWED_ANNOTS = {"Text", "Link", "FreeText", "Line", "Square", "Circle", "Polygon", "PolyLine",
                  "Highlight", "Underline", "Squiggly", "StrikeOut", "Stamp", "Caret", "Ink",
                  "Popup", "FileAttachment", "Widget", "PrinterMark", "TrapNet", "Watermark",
                  "Redact"}
# 6.2.10: the blend modes of ISO 32000-1
BLEND_MODES = {"Normal", "Compatible", "Multiply", "Screen", "Overlay", "Darken", "Lighten",
               "ColorDodge", "ColorBurn", "HardLight", "SoftLight", "Difference", "Exclusion",
               "Hue", "Saturation", "Color", "Luminosity"}
# 6.2.6
INTENTS = {"RelativeColorimetric", "AbsoluteColorimetric", "Perceptual", "Saturation"}
# 6.1.7.2: the standard filters, less LZWDecode (Crypt only with the Identity crypt filter)
FILTERS = {"ASCIIHexDecode", "ASCII85Decode", "FlateDecode", "RunLengthDecode",
           "CCITTFaxDecode", "JBIG2Decode", "DCTDecode", "JPXDecode"}
# filters MuPDF decodes to the plain data (an LZW stream with only these is re-compressed)
_PLAIN_FILTERS = {"LZWDecode", "FlateDecode", "ASCIIHexDecode", "ASCII85Decode",
                  "RunLengthDecode"}
# 6.2.11.3.3: the CMaps a font may use without embedding them (ISO 32000-1, Table 118)
PREDEFINED_CMAPS = set("""Identity-H Identity-V GB-EUC-H GB-EUC-V GBpc-EUC-H GBpc-EUC-V GBK-EUC-H
GBK-EUC-V GBKp-EUC-H GBKp-EUC-V GBK2K-H GBK2K-V UniGB-UCS2-H UniGB-UCS2-V UniGB-UTF16-H
UniGB-UTF16-V B5pc-H B5pc-V HKscs-B5-H HKscs-B5-V ETen-B5-H ETen-B5-V ETenms-B5-H ETenms-B5-V
CNS-EUC-H CNS-EUC-V UniCNS-UCS2-H UniCNS-UCS2-V UniCNS-UTF16-H UniCNS-UTF16-V 83pv-RKSJ-H
90ms-RKSJ-H 90ms-RKSJ-V 90msp-RKSJ-H 90msp-RKSJ-V 90pv-RKSJ-H Add-RKSJ-H Add-RKSJ-V EUC-H EUC-V
Ext-RKSJ-H Ext-RKSJ-V H V UniJIS-UCS2-H UniJIS-UCS2-V UniJIS-UCS2-HW-H UniJIS-UCS2-HW-V
UniJIS-UTF16-H UniJIS-UTF16-V KSC-EUC-H KSC-EUC-V KSCms-UHC-H KSCms-UHC-V KSCms-UHC-HW-H
KSCms-UHC-HW-V KSCpc-EUC-H UniKS-UCS2-H UniKS-UCS2-V UniKS-UTF16-H UniKS-UTF16-V""".split())

# annotation flags (ISO 32000-1, 12.5.3)
F_INVISIBLE, F_HIDDEN, F_PRINT, F_NOVIEW, F_TOGGLENOVIEW = 1, 2, 4, 32, 256

# ---- the standard 14 fonts, embedded from MuPDF's own copies -----------------------------
# MuPDF draws a font that isn't embedded with its URW base-35 fonts (Nimbus Sans, Nimbus Roman,
# Nimbus Mono PS, Standard Symbols PS, D050000L), which have the metrics of Adobe's standard 14
# fonts. Embedding those very programs keeps every page looking exactly as it does here.
# name -> (MuPDF's font, Flags, ItalicAngle, CapHeight, StemV)
STANDARD_14 = {
    "Helvetica": ("helv", 32, 0, 718, 88), "Helvetica-Bold": ("hebo", 32, 0, 718, 140),
    "Helvetica-Oblique": ("heit", 96, -12, 718, 88),
    "Helvetica-BoldOblique": ("hebi", 96, -12, 718, 140),
    "Times-Roman": ("tiro", 34, 0, 662, 84), "Times-Bold": ("tibo", 34, 0, 676, 139),
    "Times-Italic": ("tiit", 98, -15.5, 653, 76), "Times-BoldItalic": ("tibi", 98, -15, 669, 121),
    "Courier": ("cour", 35, 0, 562, 51), "Courier-Bold": ("cobo", 35, 0, 562, 106),
    "Courier-Oblique": ("coit", 99, -12, 562, 51),
    "Courier-BoldOblique": ("cobi", 99, -12, 562, 106),
    "Symbol": ("symb", 4, 0, 673, 85), "ZapfDingbats": ("zadb", 4, 0, 692, 90),
}
_FAMILIES = {"Helvetica": "Helvetica", "Arial": "Helvetica", "ArialMT": "Helvetica",
             "Times": "Times", "TimesNewRoman": "Times", "TimesNewRomanPS": "Times",
             "TimesNewRomanPSMT": "Times", "Courier": "Courier", "CourierNew": "Courier",
             "CourierNewPS": "Courier", "CourierNewPSMT": "Courier"}
_STYLES = {"": "", "Roman": "", "Regular": "", "Bold": "B", "Italic": "I", "Oblique": "I",
           "BoldItalic": "BI", "BoldOblique": "BI"}
_NAMES = {("Helvetica", ""): "Helvetica", ("Helvetica", "B"): "Helvetica-Bold",
          ("Helvetica", "I"): "Helvetica-Oblique", ("Helvetica", "BI"): "Helvetica-BoldOblique",
          ("Times", ""): "Times-Roman", ("Times", "B"): "Times-Bold",
          ("Times", "I"): "Times-Italic", ("Times", "BI"): "Times-BoldItalic",
          ("Courier", ""): "Courier", ("Courier", "B"): "Courier-Bold",
          ("Courier", "I"): "Courier-Oblique", ("Courier", "BI"): "Courier-BoldOblique"}


def standard_font(name):
    """The standard 14 font a font of this name is drawn with when it isn't embedded
    (Helvetica for Helvetica, Arial, ArialMT, Arial,Bold...), or None."""
    name = re.sub(r"^[A-Z]{6}\+", "", name or "").replace(" ", "")
    if name in STANDARD_14:
        return name
    if name == "Times":
        return "Times-Roman"
    parts = re.split(r"[,-]", name, maxsplit=1)
    family = _FAMILIES.get(parts[0])
    style = parts[1] if len(parts) > 1 else ""
    style = re.sub(r"(PS)?MT$", "", style)
    if family is None or style not in _STYLES:
        return None
    return _NAMES[(family, _STYLES[style])]


# the base encodings' glyph names (ISO 32000-1, Annex D), from code 32 on ('-': none)
_STANDARD = (
    "space exclam quotedbl numbersign dollar percent ampersand quoteright parenleft "
    "parenright asterisk plus comma hyphen period slash zero one two three four five six "
    "seven eight nine colon semicolon less equal greater question at A B C D E F G H I J K L "
    "M N O P Q R S T U V W X Y Z bracketleft backslash bracketright asciicircum underscore "
    "quoteleft a b c d e f g h i j k l m n o p q r s t u v w x y z braceleft bar braceright "
    "asciitilde" + " -" * 34 + " exclamdown cent sterling fraction yen florin section "
    "currency quotesingle quotedblleft guillemotleft guilsinglleft guilsinglright fi fl - "
    "endash dagger daggerdbl periodcentered - paragraph bullet quotesinglbase quotedblbase "
    "quotedblright guillemotright ellipsis perthousand - questiondown - grave acute "
    "circumflex tilde macron breve dotaccent dieresis - ring cedilla - hungarumlaut ogonek "
    "caron emdash" + " -" * 16 + " AE - ordfeminine - - - - Lslash Oslash OE ordmasculine "
    "- - - - - ae - - - dotlessi - - lslash oslash oe germandbls - - - -").split()
_WIN_HIGH = (
    "Euro - quotesinglbase florin quotedblbase ellipsis dagger daggerdbl circumflex "
    "perthousand Scaron guilsinglleft OE - Zcaron - - quoteleft quoteright quotedblleft "
    "quotedblright bullet endash emdash tilde trademark scaron guilsinglright oe - zcaron "
    "Ydieresis space exclamdown cent sterling currency yen brokenbar section dieresis "
    "copyright ordfeminine guillemotleft logicalnot hyphen registered macron degree "
    "plusminus twosuperior threesuperior acute mu paragraph periodcentered cedilla "
    "onesuperior ordmasculine guillemotright onequarter onehalf threequarters questiondown "
    "Agrave Aacute Acircumflex Atilde Adieresis Aring AE Ccedilla Egrave Eacute Ecircumflex "
    "Edieresis Igrave Iacute Icircumflex Idieresis Eth Ntilde Ograve Oacute Ocircumflex "
    "Otilde Odieresis multiply Oslash Ugrave Uacute Ucircumflex Udieresis Yacute Thorn "
    "germandbls agrave aacute acircumflex atilde adieresis aring ae ccedilla egrave eacute "
    "ecircumflex edieresis igrave iacute icircumflex idieresis eth ntilde ograve oacute "
    "ocircumflex otilde odieresis divide oslash ugrave uacute ucircumflex udieresis yacute "
    "thorn ydieresis").split()
_MAC_HIGH = (
    "Adieresis Aring Ccedilla Eacute Ntilde Odieresis Udieresis aacute agrave acircumflex "
    "adieresis atilde aring ccedilla eacute egrave ecircumflex edieresis iacute igrave "
    "icircumflex idieresis ntilde oacute ograve ocircumflex odieresis otilde uacute ugrave "
    "ucircumflex udieresis dagger degree cent sterling section bullet paragraph germandbls "
    "registered copyright trademark acute dieresis - AE Oslash - plusminus - - yen mu - - - "
    "- - ordfeminine ordmasculine - ae oslash questiondown exclamdown logicalnot - florin - "
    "- guillemotleft guillemotright ellipsis space Agrave Atilde Otilde OE oe endash emdash "
    "quotedblleft quotedblright quoteleft quoteright divide - ydieresis Ydieresis fraction "
    "currency guilsinglleft guilsinglright fi fl daggerdbl periodcentered quotesinglbase "
    "quotedblbase perthousand Acircumflex Ecircumflex Aacute Edieresis Egrave Iacute "
    "Icircumflex Idieresis Igrave Oacute Ocircumflex - Ograve Uacute Ucircumflex Ugrave "
    "dotlessi circumflex tilde macron breve dotaccent ring cedilla hungarumlaut ogonek "
    "caron").split()


def base_encoding(name):
    """{code: glyph name} of StandardEncoding, WinAnsiEncoding or MacRomanEncoding; None for
    any other name."""
    std = {32 + i: n for i, n in enumerate(_STANDARD) if n != "-"}
    if name == "StandardEncoding":
        return std
    low = {c: n for c, n in std.items() if c < 127}
    low[39], low[96] = "quotesingle", "grave"
    if name == "WinAnsiEncoding":
        high = _WIN_HIGH
    elif name == "MacRomanEncoding":
        high = _MAC_HIGH
    else:
        return None
    low.update({128 + i: n for i, n in enumerate(high) if n != "-"})
    return low


def cff_builtin_encoding(data):
    """{code: glyph index} of a CFF font program's own encoding ("Standard" when it uses the
    predefined StandardEncoding, None when it can't be read)."""
    try:
        def index(pos):
            count = struct.unpack_from(">H", data, pos)[0]
            if count == 0:
                return [], pos + 2
            size = data[pos + 2]
            offs = [int.from_bytes(data[pos + 3 + i * size:pos + 3 + (i + 1) * size], "big")
                    for i in range(count + 1)]
            base = pos + 3 + (count + 1) * size - 1
            return [data[base + offs[i]:base + offs[i + 1]] for i in range(count)], \
                base + offs[-1]
        _names, pos = index(data[2])
        tops, pos = index(pos)
        top = {}
        d, i, operands = tops[0], 0, []
        while i < len(d):
            b = d[i]
            if b <= 21:
                op = b
                if b == 12:
                    i += 1
                    op = 1200 + d[i]
                top[op] = operands
                operands = []
                i += 1
            elif b == 28:
                operands.append(struct.unpack_from(">h", d, i + 1)[0])
                i += 3
            elif b == 29:
                operands.append(struct.unpack_from(">i", d, i + 1)[0])
                i += 5
            elif b == 30:
                i += 1
                while i < len(d) and (d[i] & 0x0F) != 0x0F and (d[i] >> 4) != 0x0F:
                    i += 1
                i += 1
                operands.append(0)
            elif 32 <= b <= 246:
                operands.append(b - 139)
                i += 1
            elif 247 <= b <= 250:
                operands.append((b - 247) * 256 + d[i + 1] + 108)
                i += 2
            elif 251 <= b <= 254:
                operands.append(-(b - 251) * 256 - d[i + 1] - 108)
                i += 2
            else:
                i += 1
        enc = top.get(16, [0])[0]
        if enc in (0, 1):
            return "Standard" if enc == 0 else None
        fmt = data[enc]
        out = {}
        if fmt & 0x7F == 0:
            n = data[enc + 1]
            for g in range(n):
                out[data[enc + 2 + g]] = g + 1
            pos = enc + 2 + n
        else:
            n = data[enc + 1]
            g, pos = 1, enc + 2
            for _r in range(n):
                first, left = data[pos], data[pos + 1]
                for c in range(first, first + left + 1):
                    out[c] = g
                    g += 1
                pos += 2
        if fmt & 0x80:
            # supplements: codes for glyphs given by name (SID); rare, and the glyph is
            # found through the charset
            charstrings, _ = index(top[17][0])
            charset = _cff_charset(data, top.get(15, [0])[0], len(charstrings))
            for k in range(data[pos]):
                code, sid = struct.unpack_from(">BH", data, pos + 1 + k * 3)
                if sid in charset:
                    out[code] = charset[sid]
        return out
    except (IndexError, struct.error, KeyError):
        return None


def _cff_charset(data, offset, glyphs):
    """{SID: glyph index} of a CFF charset."""
    out = {}
    if offset < 3:
        return out
    fmt, pos, g = data[offset], offset + 1, 1
    while g < glyphs:
        if fmt == 0:
            out[struct.unpack_from(">H", data, pos)[0]] = g
            g += 1
            pos += 2
        else:
            first = struct.unpack_from(">H", data, pos)[0]
            left = data[pos + 2] if fmt == 1 else struct.unpack_from(">H", data, pos + 2)[0]
            for k in range(left + 1):
                out[first + k] = g
                g += 1
            pos += 3 if fmt == 1 else 4
    return out


# ---- the ICC profiles ----------------------------------------------------------------------
_profiles = {}


def icc_profile(kind):
    """The ICC profile MuPDF draws with ("rgb": Artifex's sRGB profile; "cmyk": Artifex's CMYK
    SWOP profile), as bytes. They're the profiles built into MuPDF (AGPL, as all of it):
    the copy keeps the colors exactly as KanzonasPDF shows them. See NOTICE.md."""
    if kind not in _profiles:
        icc_was_on = m.fz_colorspace_is_icc(m.fz_device_rgb())
        if not icc_was_on:
            m.fz_enable_icc()
        try:
            doc = pymupdf.open()
            pdf = pymupdf._as_pdf_document(doc)
            cs = m.fz_device_rgb() if kind == "rgb" else m.fz_device_cmyk()
            arr = m.pdf_resolve_indirect(m.pdf_add_colorspace(pdf, cs))
            stream = m.pdf_array_get(arr, 1)
            _profiles[kind] = _data(stream)
            doc.close()
        finally:
            if not icc_was_on:
                m.fz_disable_icc()
    return _profiles[kind]


def _icc_info(data):
    """(device class, color space, major version) of an ICC profile's header."""
    if len(data) < 128 or data[36:40] != b"acsp":
        return None
    return data[12:16].decode("latin-1"), data[16:20].decode("latin-1"), data[8]


# ---- small helpers on MuPDF objects --------------------------------------------------------
def _name(obj):
    """The name in obj (resolved), or None."""
    obj = m.pdf_resolve_indirect(obj)
    return m.pdf_to_name(obj) if m.pdf_is_name(obj) else None


def _get(obj, key):
    """obj[key] resolved (a null object when missing)."""
    return m.pdf_resolve_indirect(m.pdf_dict_gets(obj, key))


def _has(obj, key):
    return m.pdf_dict_gets(obj, key).m_internal is not None and \
        not m.pdf_is_null(m.pdf_dict_gets(obj, key))


def _stream_of(obj, key):
    """obj[key] when it is a stream (as the reference MuPDF needs for reading it), else
    None."""
    raw = m.pdf_dict_gets(obj, key)
    return raw if m.pdf_is_stream(raw) else None


def _data(stream):
    """The decoded bytes of a stream (a reference)."""
    return bytes(m.fz_buffer_extract_copy(m.pdf_load_stream(stream)))


def _items(obj):
    for i in range(m.pdf_dict_len(obj)):
        yield m.pdf_to_name(m.pdf_dict_get_key(obj, i)), m.pdf_dict_get_val(obj, i)


def _text(obj):
    obj = m.pdf_resolve_indirect(obj)
    if m.pdf_is_string(obj):
        return m.pdf_to_text_string(obj)
    if m.pdf_is_name(obj):
        return m.pdf_to_name(obj)
    return ""


def _new_name(pdf, name):
    return m.pdf_new_name(name)


def _ref(pdf, xref):
    return m.pdf_new_indirect(pdf, xref, 0)


def _filters(obj):
    f = _get(obj, "Filter")
    if m.pdf_is_name(f):
        return [m.pdf_to_name(f)]
    if m.pdf_is_array(f):
        return [_name(m.pdf_array_get(f, i)) or "" for i in range(m.pdf_array_len(f))]
    return []


def _is_cmyk_name(obj):
    return _name(obj) == "DeviceCMYK"


# the k / K operators or a DeviceCMYK color space (also an inline picture's /CMYK) in a
# content stream; the RGB ones (rg / RG, DeviceRGB, inline /RGB)
_CMYK_OPS = re.compile(rb"(?:^|[\s\]>)])[kK](?=[\s/\[(<%]|$)|/DeviceCMYK\b|/CMYK\b")
_RGB_OPS = re.compile(rb"(?:^|[\s\]>)])(?:rg|RG)(?=[\s/\[(<%]|$)|/DeviceRGB\b|/RGB\b")


# ---- problems ------------------------------------------------------------------------------
class Problem:
    """One thing that keeps the document from being PDF/A: kind (see kind_labels), page
    (0-based, None for the whole document), text, and whether Save as PDF/A fixes it."""
    __slots__ = ("kind", "page", "text", "fixable")

    def __init__(self, kind, page, text, fixable):
        self.kind, self.page, self.text, self.fixable = kind, page, text, fixable

    def __repr__(self):
        return "Problem(%r, %r, %r, %r)" % (self.kind, self.page, self.text, self.fixable)


KINDS = ("file", "metadata", "color", "fonts", "annots", "forms", "actions", "graphics",
         "attachments", "signatures", "layers", "pages")


def kind_labels():
    return {"file": tr("The file"), "metadata": tr("Metadata and PDF/A identification"),
            "color": tr("Colors"), "fonts": tr("Fonts"),
            "annots": tr("Comments, markups and links"), "forms": tr("Form fields"),
            "actions": tr("Scripts and actions"),
            "graphics": tr("Pictures, drawings and transparency"),
            "attachments": tr("Attached files"), "signatures": tr("Digital signatures"),
            "layers": tr("Layers"), "pages": tr("Pages")}


# ---- the work ------------------------------------------------------------------------------
class _Pass:
    """One walk over a document: records problems; with fix=True also fixes what it can
    (notes say what was changed, for the summary after saving)."""

    def __init__(self, doc, fix, step=None):
        self.doc = doc
        self.pdf = pymupdf._as_pdf_document(doc)
        self.fix = fix
        self.step = step
        self.problems = []
        self.notes = []
        self._seen = set()
        self.part = 2
        self.cmyk_ref = None            # the ICCBased CMYK color space (fixing)
        self.page_of = {}
        self.uses_cmyk = False
        self.uses_rgb = False
        self.intent_cs = None           # the color space of the PDF/A output intent there was
        self.claimed = None             # (part, conformance) the file says it is

    # problems and notes
    def problem(self, kind, page, text, fixable=True):
        key = (kind, page, text)
        if key in self._seen:
            return
        self._seen.add(key)
        self.problems.append(Problem(kind, page, text, fixable))

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)

    def _tick(self):
        if self.step is not None and self.step() is False:
            raise _Stopped()

    # -- the walk
    def run(self):
        doc = self.doc
        if doc.is_encrypted or (doc.metadata or {}).get("encryption"):
            # 6.1.3-2 (Save as PDF/A refuses such a document before getting here)
            self.problem("file", None, tr(
                "The file is protected with a password (encrypted), which PDF/A doesn't allow. "
                "Remove its security first (Protect > Remove security)."), False)
            if doc.is_encrypted:
                return self
        self.catalog = m.pdf_resolve_indirect(m.pdf_dict_gets(m.pdf_trailer(self.pdf), "Root"))
        self.catalog_xref = doc.pdf_catalog()
        self._page_map()
        self._identification()
        self._output_intent()
        self._document_level()
        self._pages()
        self._objects()
        self._colors()
        self._attachments()
        if self.fix:
            self._finish()
        return self

    def _page_map(self):
        """page_of: xref -> the first page that uses it (through its resources, contents,
        annotations), for telling which page a problem is on."""
        pdf = self.pdf
        pages = {self.doc[i].xref: i for i in range(self.doc.page_count)} \
            if self.doc.page_count else {}
        self.page_xrefs = pages
        for xref, i in sorted(pages.items(), key=lambda t: t[1]):
            todo = [m.pdf_load_object(pdf, xref)]
            self.page_of.setdefault(xref, i)
            while todo:
                obj = todo.pop()
                if m.pdf_is_dict(obj):
                    children = [v for k, v in _items(obj) if k not in ("Parent", "P", "Dest",
                                                                         "D", "Popup")]
                elif m.pdf_is_array(obj):
                    children = [m.pdf_array_get(obj, k) for k in range(m.pdf_array_len(obj))]
                else:
                    continue
                for v in children:
                    if m.pdf_is_indirect(v):
                        num = m.pdf_to_num(v)
                        if num in pages or num in self.page_of:
                            continue
                        self.page_of[num] = i
                        todo.append(m.pdf_resolve_indirect(v))
                    elif m.pdf_is_dict(v) or m.pdf_is_array(v):
                        todo.append(v)

    # -- metadata (6.6)
    def _identification(self):
        meta = _stream_of(self.catalog, "Metadata")
        xml = ""
        if meta is not None:
            try:
                xml = _data(meta).decode("utf-8")
            except (UnicodeDecodeError, RuntimeError):
                xml = ""
        part = re.search(r"pdfaid:part(?:>|\s*=\s*[\"'])\s*(\d)", xml)
        conf = re.search(r"pdfaid:conformance(?:>|\s*=\s*[\"'])\s*([A-Za-z])", xml)
        if part:
            self.claimed = (int(part.group(1)), (conf.group(1) if conf else "").upper())
        if not self.claimed or self.claimed[0] not in (2, 3) or self.claimed[1] not in "ABU" \
                or not self.claimed[1]:
            self.problem("metadata", None, tr(
                "The file isn't marked as PDF/A (its metadata has no PDF/A identification)."))
        elif re.search(r"<\?xpacket[^>]*\b(bytes|encoding)\s*=", xml) or \
                not _info_matches_xmp(self.doc, xml):
            self.problem("metadata", None, tr(
                "Its metadata (XMP) doesn't match the document properties."))

    # -- output intent (6.2.3)
    def _output_intent(self):
        intents = _get(self.catalog, "OutputIntents")
        found = None
        profiles = set()
        if m.pdf_is_array(intents):
            for i in range(m.pdf_array_len(intents)):
                oi = m.pdf_resolve_indirect(m.pdf_array_get(intents, i))
                raw = m.pdf_dict_gets(oi, "DestOutputProfile")
                if m.pdf_is_indirect(raw):
                    profiles.add(m.pdf_to_num(raw))
                if _name(m.pdf_dict_gets(oi, "S")) != "GTS_PDFA1":
                    continue
                info = None
                if m.pdf_is_stream(raw):
                    info = _icc_info(_data(raw)[:128])
                found = info or ("", "", 9)
        good = found is not None and found[0] in ("mntr", "prtr") and \
            found[1] in ("RGB ", "CMYK", "GRAY") and found[2] < 5 and len(profiles) <= 1
        if found is None:
            self.problem("color", None, tr(
                "There's no output intent (the color profile PDF/A requires for the colors "
                "the pages use)."))
        elif not good:
            self.problem("color", None, tr(
                "The output intent's color profile isn't one PDF/A allows."))
        else:
            self.intent_cs = found[1].strip()
        if self.fix:
            # one PDF/A output intent with an sRGB profile (it replaces any others: PDF/A
            # wants every output intent to use the same profile)
            prof = self.doc.get_new_xref()
            self.doc.update_object(prof, "<< /N 3 >>")
            self.doc.update_stream(prof, icc_profile("rgb"), compress=True)
            oi = self.doc.get_new_xref()
            self.doc.update_object(oi, "<< /Type /OutputIntent /S /GTS_PDFA1 "
                                       "/OutputConditionIdentifier (sRGB IEC61966-2.1) "
                                       "/Info (sRGB IEC61966-2.1) "
                                       "/RegistryName (http://www.color.org) "
                                       "/DestOutputProfile %d 0 R >>" % prof)
            self.doc.xref_set_key(self.doc.pdf_catalog(), "OutputIntents", "[%d 0 R]" % oi)
            self.catalog = m.pdf_resolve_indirect(
                m.pdf_dict_gets(m.pdf_trailer(self.pdf), "Root"))

    # -- document-wide entries (6.1, 6.4, 6.5, 6.9, 6.10, 6.11)
    def _document_level(self):
        cat = self.catalog
        version = self.pdf.m_internal.version
        if version > 17:
            self.problem("file", None, tr(
                "The file is PDF {version}; PDF/A-2 is based on PDF 1.7.").format(
                version="%d.%d" % divmod(version, 10)))
            if self.fix:
                self.pdf.m_internal.version = 17
        v = _name(m.pdf_dict_gets(cat, "Version"))
        if v and v > "1.7":
            if self.fix:
                m.pdf_dict_dels(cat, "Version")
            else:
                self.problem("file", None, tr(
                    "The file is PDF {version}; PDF/A-2 is based on PDF 1.7.").format(version=v))
        trailer_id = m.pdf_dict_gets(m.pdf_trailer(self.pdf), "ID")
        if not m.pdf_is_array(m.pdf_resolve_indirect(trailer_id)):
            # 6.1.3-1 (every save writes one)
            self.problem("file", None, tr("The file has no identifier (ID)."))
        for key, text in (("Requirements", tr("The document lists viewer features it requires "
                                              "(Requirements), which PDF/A doesn't allow.")),
                          ("NeedsRendering", tr("The document asks the viewer to build its "
                                                "pages (an XFA form)."))):
            if _has(cat, key):
                self.problem("file" if key == "Requirements" else "forms", None, text)
                if self.fix:
                    m.pdf_dict_dels(cat, key)
        names = _get(cat, "Names")
        if m.pdf_is_dict(names):
            if _has(names, "JavaScript"):
                self.problem("actions", None, tr("The document contains JavaScript."))
                if self.fix:
                    m.pdf_dict_dels(names, "JavaScript")
                    self.note(tr("Removed the document's JavaScript."))
            if _has(names, "AlternatePresentations"):
                self.problem("pages", None, tr("The document has an alternate presentation "
                                               "(a slide show), which PDF/A doesn't allow."))
                if self.fix:
                    m.pdf_dict_dels(names, "AlternatePresentations")
        form = _get(cat, "AcroForm")
        self.acroform = form if m.pdf_is_dict(form) else None
        if self.acroform is not None:
            if _has(form, "XFA"):
                self.problem("forms", None, tr("The form is an XFA form; its dynamic part "
                                               "isn't allowed (the fields themselves stay)."))
                if self.fix:
                    m.pdf_dict_dels(form, "XFA")
            self.need_appearances = m.pdf_to_bool(_get(form, "NeedAppearances"))
            if self.need_appearances:
                self.problem("forms", None, tr("The form leaves drawing its fields to the "
                                               "viewer (NeedAppearances)."))
                if self.fix:
                    # (every field gets its appearance drawn here instead: _make_appearances)
                    m.pdf_dict_dels(form, "NeedAppearances")
        else:
            self.need_appearances = False
        if _has(cat, "Perms"):
            # 6.1.12: only UR3 and DocMDP; both are signatures, which the copy can't keep
            if self.fix:
                m.pdf_dict_dels(cat, "Perms")
        self._optional_content()

    def _optional_content(self):
        """6.9: each layer configuration has a unique Name, no AS (automatic switching), and
        an Order, when there is one, that lists every layer."""
        ocp = _get(self.catalog, "OCProperties")
        if not m.pdf_is_dict(ocp):
            return
        ocgs = _get(ocp, "OCGs")
        all_ocgs = []
        if m.pdf_is_array(ocgs):
            for i in range(m.pdf_array_len(ocgs)):
                o = m.pdf_array_get(ocgs, i)
                if m.pdf_is_indirect(o):
                    all_ocgs.append(m.pdf_to_num(o))
        configs = []
        d = _get(ocp, "D")
        if m.pdf_is_dict(d):
            configs.append(d)
        more = _get(ocp, "Configs")
        if m.pdf_is_array(more):
            for i in range(m.pdf_array_len(more)):
                c = m.pdf_resolve_indirect(m.pdf_array_get(more, i))
                if m.pdf_is_dict(c):
                    configs.append(c)
        names = set()
        bad = False
        for n, c in enumerate(configs):
            name = _text(m.pdf_dict_gets(c, "Name"))
            if not name or name in names:
                bad = True
                if self.fix:
                    name = tr("Default") if n == 0 and tr("Default") not in names else \
                        "%s %d" % (tr("Configuration"), n + 1)
                    m.pdf_dict_puts(c, "Name", m.pdf_new_text_string(name))
            names.add(name)
            if _has(c, "AS"):
                bad = True
                if self.fix:
                    m.pdf_dict_dels(c, "AS")
            order = _get(c, "Order")
            if m.pdf_is_array(order):
                listed = set()
                todo = [order]
                while todo:
                    a = todo.pop()
                    for i in range(m.pdf_array_len(a)):
                        o = m.pdf_array_get(a, i)
                        if m.pdf_is_indirect(o):
                            listed.add(m.pdf_to_num(o))
                        r = m.pdf_resolve_indirect(o)
                        if m.pdf_is_array(r):
                            todo.append(r)
                missing = [x for x in all_ocgs if x not in listed]
                if missing:
                    bad = True
                    if self.fix:
                        for x in missing:
                            m.pdf_array_push(order, _ref(self.pdf, x))
        if bad:
            self.problem("layers", None, tr(
                "The layer settings lack a name, don't list every layer, or switch layers "
                "automatically."))

    # -- pages (6.1.13, 6.2.2, 6.3, 6.5.2, 6.10)
    def _pages(self):
        doc = self.doc
        for i in range(doc.page_count):
            self._tick()
            page = doc[i]
            obj = m.pdf_load_object(self.pdf, page.xref)
            for key in ("MediaBox", "CropBox", "BleedBox", "TrimBox", "ArtBox"):
                box = m.pdf_resolve_indirect(m.pdf_dict_get_inheritable(obj, m.pdf_new_name(key)))
                if m.pdf_is_array(box) and m.pdf_array_len(box) == 4:
                    v = [m.pdf_to_real(m.pdf_array_get(box, k)) for k in range(4)]
                    w, h = abs(v[2] - v[0]), abs(v[3] - v[1])
                    if not (3 <= w <= 14400 and 3 <= h <= 14400):
                        self.problem("pages", i, tr(
                            "The page is smaller than 3 points or larger than 14,400 points "
                            "(200 inches) on a side."), False)
            if _has(obj, "PresSteps"):
                self.problem("pages", i, tr("The page has presentation steps (PresSteps)."))
                if self.fix:
                    m.pdf_dict_dels(obj, "PresSteps")
            if not _has(obj, "Resources"):
                inherited = m.pdf_dict_get_inheritable(obj, m.pdf_new_name("Resources"))
                if not m.pdf_is_null(inherited):
                    # 6.2.2-2: a content stream's resources are its own, not inherited
                    self.problem("pages", i, tr("The page takes its resources (fonts, "
                                                "pictures) from the page tree."))
                    if self.fix:
                        m.pdf_dict_puts(obj, "Resources", inherited)
            if self.fix:
                self._forms_without_resources(obj)
            self._annotations(i, page)

    def _forms_without_resources(self, page_obj):
        """6.2.2-2: a drawing group (form XObject) the page places that has no resources of its
        own (an old way to share the page's) gets the page's."""
        res = _get(page_obj, "Resources")
        xobjs = _get(res, "XObject") if m.pdf_is_dict(res) else None
        if xobjs is None or not m.pdf_is_dict(xobjs):
            return
        for _k, v in _items(xobjs):
            x = m.pdf_resolve_indirect(v)
            if m.pdf_is_stream(v) and _name(m.pdf_dict_gets(x, "Subtype")) == "Form" and \
                    not _has(x, "Resources"):
                m.pdf_dict_puts(x, "Resources", m.pdf_dict_gets(page_obj, "Resources"))

    def _annotations(self, i, page):
        pdf = self.pdf
        obj = m.pdf_load_object(pdf, page.xref)
        annots = _get(obj, "Annots")
        if not m.pdf_is_array(annots):
            return
        drop, drop_widgets, need_ap, widgets_ap = [], [], [], []
        for k in range(m.pdf_array_len(annots)):
            raw = m.pdf_array_get(annots, k)
            a = m.pdf_resolve_indirect(raw)
            if not m.pdf_is_dict(a):
                continue
            xref = m.pdf_to_num(raw) if m.pdf_is_indirect(raw) else 0
            sub = _name(m.pdf_dict_gets(a, "Subtype")) or "?"
            label = sub
            if sub not in ALLOWED_ANNOTS:
                self.problem("annots", i, tr(
                    "A {kind} annotation, a kind PDF/A doesn't allow (3D, sound, movie or "
                    "multimedia); it's removed.").format(kind=label))
                drop.append(k)
                continue
            f = _get(a, "F")
            flags = m.pdf_to_int(f) if m.pdf_is_number(f) else None
            if flags is not None and flags & (F_HIDDEN | F_NOVIEW) and sub != "Popup":
                # 6.3.2: every annotation shows and prints; one that is hidden would appear,
                # changing the page, so it goes
                self.problem("annots", i, tr(
                    "A hidden {kind} annotation; PDF/A shows every annotation, so it's "
                    "removed.").format(kind=label))
                (drop_widgets if sub == "Widget" else drop).append(k if sub != "Widget" else xref)
                continue
            want = ((flags or 0) | F_PRINT) & ~(F_INVISIBLE | F_HIDDEN | F_NOVIEW | F_TOGGLENOVIEW)
            if (flags is None and sub != "Popup") or (flags is not None and flags != want):
                if flags is None or not flags & F_PRINT:
                    self.problem("annots", i, tr("A {kind} annotation isn't set to "
                                                 "print.").format(kind=label))
                if self.fix:
                    m.pdf_dict_puts(a, "F", m.pdf_new_int(want))
            self._annotation_appearance(i, a, sub, xref, need_ap, widgets_ap)
        if self.fix:
            self._drop_annotations(page, annots, drop, drop_widgets)
            self._make_appearances(i, page, need_ap, widgets_ap)

    def _annotation_appearance(self, i, a, sub, xref, need_ap, widgets_ap):
        """6.3.3: an appearance (only N) for every annotation but popups, links and those
        with an empty Rect; for a check box or option button a set of states."""
        rect = _get(a, "Rect")
        empty = False
        if m.pdf_is_array(rect) and m.pdf_array_len(rect) == 4:
            v = [m.pdf_to_real(m.pdf_array_get(rect, k)) for k in range(4)]
            empty = v[0] == v[2] and v[1] == v[3]
        ap = _get(a, "AP")
        field_type = _name(_inheritable(a, "FT"))
        if sub == "Widget" and field_type == "Sig" and \
                not m.pdf_is_null(_inheritable(a, "V")):
            self._signature(i, a, xref)
            ap = _get(a, "AP")
        if m.pdf_is_dict(ap):
            if _has(ap, "D") or _has(ap, "R"):
                self.problem("annots", i, tr(
                    "A {kind} annotation has rollover or pressed appearances, which PDF/A "
                    "doesn't allow.").format(kind=sub))
                if self.fix:
                    m.pdf_dict_dels(ap, "D")
                    m.pdf_dict_dels(ap, "R")
            n = _get(ap, "N")
            n_stream = _stream_of(ap, "N") is not None
            if sub == "Widget" and field_type == "Btn":
                if n_stream:
                    # a push button's single appearance, as the one state of a set
                    self.problem("forms", i, tr("A button's appearance isn't stored as PDF/A "
                                                "requires."))
                    if self.fix:
                        states = m.pdf_new_dict(self.pdf, 1)
                        m.pdf_dict_puts(states, "Default", m.pdf_dict_gets(ap, "N"))
                        m.pdf_dict_puts(ap, "N", states)
                        m.pdf_dict_puts(a, "AS", m.pdf_new_name("Default"))
                    return
                if m.pdf_is_dict(n) and m.pdf_dict_len(n):
                    return
            elif n_stream:
                return
            elif m.pdf_is_dict(n) and sub == "Widget":
                # a field (not a button) with a set of states: the state shown becomes its
                # appearance
                state = _get(a, "AS")
                pick = _stream_of(n, m.pdf_to_name(state)) if m.pdf_is_name(state) else None
                self.problem("forms", i, tr("A field's appearance isn't stored as PDF/A "
                                            "requires."), pick is not None)
                if self.fix and pick is not None:
                    m.pdf_dict_puts(ap, "N", pick)
                return
        if sub in ("Popup", "Link") or empty:
            return
        if sub == "Widget":
            self.problem("forms", i, tr("A form field has no appearance."))
            widgets_ap.append(xref)
        else:
            self.problem("annots", i, tr("A {kind} annotation has no appearance.").format(
                kind=sub), sub in _PYMUPDF_APPEARANCES)
            need_ap.append(xref)

    def _signature(self, i, a, xref):
        """A signed signature field: the copy is a new file, in which the signature
        couldn't be valid (6.4.3: it would have to cover the whole file). The value goes,
        the field stays, empty (as Protect > Clear all digital signatures does)."""
        self.problem("signatures", i, tr(
            "The document is digitally signed. A PDF/A copy is a new file, in which the "
            "signature wouldn't be valid: it's removed (sign the PDF/A copy if it needs a "
            "signature)."))
        if not self.fix:
            return
        holder = a
        while not _has(holder, "V") and _has(holder, "Parent"):
            holder = _get(holder, "Parent")
        m.pdf_dict_dels(holder, "V")
        rect = _get(a, "Rect")
        v = [m.pdf_to_real(m.pdf_array_get(rect, k)) for k in range(4)] \
            if m.pdf_is_array(rect) and m.pdf_array_len(rect) == 4 else [0, 0, 0, 0]
        blank = self.doc.get_new_xref()
        self.doc.update_object(blank, "<< /Type /XObject /Subtype /Form /BBox [0 0 %g %g] "
                                      "/Resources << >> >>" % (abs(v[2] - v[0]),
                                                               abs(v[3] - v[1])))
        self.doc.update_stream(blank, b" ")
        ap = m.pdf_new_dict(self.pdf, 1)
        m.pdf_dict_puts(ap, "N", _ref(self.pdf, blank))
        m.pdf_dict_puts(a, "AP", ap)
        self.note(tr("Removed the digital signatures (they wouldn't be valid in the new "
                     "file)."))

    def _drop_annotations(self, page, annots, drop, drop_widgets):
        if drop:
            popups = set()
            for k in drop:
                a = m.pdf_resolve_indirect(m.pdf_array_get(annots, k))
                p = m.pdf_dict_gets(a, "Popup")
                if m.pdf_is_indirect(p):
                    popups.add(m.pdf_to_num(p))
            for k in range(m.pdf_array_len(annots)):
                o = m.pdf_array_get(annots, k)
                if m.pdf_is_indirect(o) and m.pdf_to_num(o) in popups and k not in drop:
                    drop.append(k)
            for k in sorted(set(drop), reverse=True):
                m.pdf_array_delete(annots, k)
            self.note(tr("Removed annotations that were hidden or of kinds PDF/A doesn't "
                         "allow."))
        if drop_widgets:
            for w in list(page.widgets()):
                if w.xref in drop_widgets:
                    page.delete_widget(w)
            self.note(tr("Removed annotations that were hidden or of kinds PDF/A doesn't "
                         "allow."))

    def _make_appearances(self, i, page, need_ap, widgets_ap):
        if self.need_appearances:
            widgets_ap = [w.xref for w in page.widgets()]
        for xref in need_ap:
            try:
                annot = page.load_annot(xref)
                if annot is not None:
                    annot.update()
            except Exception:
                pass
        if widgets_ap:
            for w in page.widgets():
                if w.xref in widgets_ap:
                    try:
                        w.update()
                    except Exception:
                        pass

    # -- every object (6.1.7, 6.2.4 to 6.2.11, 6.4.1, 6.5)
    def _objects(self):
        doc, pdf = self.doc, self.pdf
        self.font_jobs = []
        self.content_streams = []
        for xref in range(1, doc.xref_length()):
            if xref % 200 == 0:
                self._tick()
            try:
                obj = m.pdf_load_object(pdf, xref)
            except Exception:
                continue
            page = self.page_of.get(xref)
            stream = m.pdf_is_stream(m.pdf_new_indirect(pdf, xref, 0))
            if stream:
                self._stream(xref, obj, page)
            todo = [obj]
            while todo:
                o = todo.pop()
                if m.pdf_is_dict(o):
                    self._dict(xref, o, page, o is obj)
                    todo.extend(v for _k, v in _items(o)
                                if not m.pdf_is_indirect(v) and (m.pdf_is_dict(v) or
                                                                 m.pdf_is_array(v)))
                elif m.pdf_is_array(o):
                    self._array(o, page)
                    for k in range(m.pdf_array_len(o)):
                        v = m.pdf_array_get(o, k)
                        if not m.pdf_is_indirect(v) and (m.pdf_is_dict(v) or m.pdf_is_array(v)):
                            todo.append(v)
        for job in self.font_jobs:
            job()

    def _stream(self, xref, obj, page):
        filters = _filters(obj)
        for key in ("F", "FFilter", "FDecodeParms"):
            if _has(obj, key) and _name(m.pdf_dict_gets(obj, "Type")) != "EmbeddedFile":
                self.problem("file", page, tr("Part of the file is kept in another file "
                                              "(an external stream)."), False)
        if "LZWDecode" in filters:
            plain = all(f in _PLAIN_FILTERS for f in filters)
            self.problem("file", page, tr("Part of the file uses LZW compression, which PDF/A "
                                          "doesn't allow."), plain)
            if self.fix and plain:
                data = self.doc.xref_stream(xref)
                m.pdf_dict_dels(obj, "DecodeParms")
                self.doc.update_stream(xref, data, compress=True)
        for f in filters:
            if f not in FILTERS and f != "LZWDecode":
                self.problem("file", page, tr("Part of the file uses a compression PDF/A "
                                              "doesn't allow ({name}).").format(name=f), False)
        sub = _name(m.pdf_dict_gets(obj, "Subtype"))
        typ = _name(m.pdf_dict_gets(obj, "Type"))
        if sub == "Form" or _has(obj, "PatternType"):
            self.content_streams.append((xref, page, obj))
        if sub == "Image":
            self._image(xref, obj, page)
        elif sub == "Form":
            for key in ("OPI", "PS", "Ref"):
                if _has(obj, key):
                    # 6.2.9: no OPI, PostScript or reference to another file in a drawing
                    # group; the drawing itself stays
                    self.problem("graphics", page, tr(
                        "A drawing refers to another file or holds PostScript code (OPI, "
                        "PS or Ref)."))
                    if self.fix:
                        m.pdf_dict_dels(obj, key)
            if _name(m.pdf_dict_gets(obj, "Subtype2")) == "PS":
                self.problem("graphics", page, tr("A PostScript drawing (PDF/A doesn't allow "
                                                  "PostScript)."), False)
        elif sub == "PS" and typ == "XObject":
            self.problem("graphics", page, tr("A PostScript drawing (PDF/A doesn't allow "
                                              "PostScript)."), False)

    def _content_xrefs(self):
        if not hasattr(self, "_contents"):
            self._contents = set()
            for i in range(self.doc.page_count):
                for x in self.doc[i].get_contents():
                    self._contents.add(x)
                    self.content_streams.append(
                        (x, i, m.pdf_load_object(self.pdf, self.doc[i].xref)))
        return self._contents

    def _image(self, xref, obj, page):
        """6.2.8: no Alternates or OPI, no smoothing (Interpolate), 1, 2, 4, 8 or 16 bits."""
        for key in ("Alternates", "OPI"):
            if _has(obj, key):
                self.problem("graphics", page, tr("A picture has alternate versions or OPI "
                                                  "links."))
                if self.fix:
                    m.pdf_dict_dels(obj, key)
        if m.pdf_to_bool(_get(obj, "Interpolate")):
            self.problem("graphics", page, tr("A picture is set to be smoothed when enlarged "
                                              "(Interpolate)."))
            if self.fix:
                self.doc.xref_set_key(xref, "Interpolate", "false")
        bpc = _get(obj, "BitsPerComponent")
        if m.pdf_is_number(bpc):
            mask = m.pdf_to_bool(_get(obj, "ImageMask"))
            if (mask and m.pdf_to_int(bpc) != 1) or \
                    (not mask and m.pdf_to_int(bpc) not in (1, 2, 4, 8, 16)):
                self.problem("graphics", page, tr("A picture has a number of bits per color "
                                                  "PDF/A doesn't allow."), False)
        intent = _name(m.pdf_dict_gets(obj, "Intent"))
        if intent and intent not in INTENTS:
            self.problem("color", page, tr("A rendering intent PDF/A doesn't allow "
                                           "({name}).").format(name=intent))
            if self.fix:
                m.pdf_dict_dels(obj, "Intent")

    def _dict(self, xref, d, page, top):
        if _has(d, "AA"):
            # 6.5.2, 6.4.1: no additional actions (on opening, closing, printing, on pages,
            # fields...); they are nearly always JavaScript
            self.problem("actions", page, tr("Actions that run on their own (when the "
                                             "document opens, closes or prints, or on a page "
                                             "or a field)."))
            if self.fix:
                m.pdf_dict_dels(d, "AA")
        sub = _name(m.pdf_dict_gets(d, "Subtype"))
        if sub == "Widget" and _has(d, "A"):
            # 6.4.1-1: a field's widget has no action (a button's "submit" or script)
            self.problem("actions", page, tr("A form field runs an action when clicked, "
                                             "which PDF/A doesn't allow."))
            if self.fix:
                m.pdf_dict_dels(d, "A")
        for key in ("A", "OpenAction", "Next"):
            v = _get(d, key)
            if key == "Next" and m.pdf_is_array(v):
                bad = any(self._bad_action(m.pdf_resolve_indirect(m.pdf_array_get(v, k)))
                          for k in range(m.pdf_array_len(v)))
            else:
                bad = m.pdf_is_dict(v) and self._bad_action(v)
            if bad:
                what = bad if isinstance(bad, str) else "?"
                if what == "JavaScript":
                    self.problem("actions", page, tr("The document contains JavaScript."))
                else:
                    self.problem("actions", page, tr("An action PDF/A doesn't allow "
                                                     "({action}).").format(action=what))
                if self.fix:
                    m.pdf_dict_dels(d, key)
                    self.note(tr("Removed scripts and actions PDF/A doesn't allow."))
        if _name(m.pdf_dict_gets(d, "Type")) == "Font":
            self._font(xref, d, page)
            return
        if self.fix and _has(d, "Metadata") and not (top and xref == self.catalog_xref):
            # metadata of pages, pictures, fonts...: PDF/A checks every XMP packet for
            # properties it knows (or extension schemas describing the others); these come
            # from the programs that made the pictures and seldom follow that, so they go
            m.pdf_dict_dels(d, "Metadata")
        # extended graphics states (6.2.5, 6.2.6, 6.2.10)
        for key in ("TR", "TR2", "HTP", "HT"):
            if not _has(d, key):
                continue
            if key == "TR2" and _name(m.pdf_dict_gets(d, key)) == "Default":
                continue
            if key == "HT" and not self._bad_halftone(_get(d, "HT")):
                continue
            self.problem("color", page, tr("Printing settings PDF/A doesn't allow (transfer "
                                           "functions or halftones)."))
            if self.fix:
                m.pdf_dict_dels(d, key)
        bm = m.pdf_resolve_indirect(m.pdf_dict_gets(d, "BM"))
        bms = [bm] if m.pdf_is_name(bm) else \
            [m.pdf_array_get(bm, k) for k in range(m.pdf_array_len(bm))] if m.pdf_is_array(bm) \
            else []
        for b in bms:
            name = _name(b)
            if name and name not in BLEND_MODES:
                self.problem("graphics", page, tr("A blend mode PDF/A doesn't allow "
                                                  "({name}).").format(name=name))
                if self.fix:
                    m.pdf_dict_puts(d, "BM", m.pdf_new_name("Normal"))
                break
        ri = _name(m.pdf_dict_gets(d, "RI"))
        if ri and ri not in INTENTS:
            self.problem("color", page, tr("A rendering intent PDF/A doesn't allow "
                                           "({name}).").format(name=ri))
            if self.fix:
                m.pdf_dict_dels(d, "RI")
        # color spaces: DeviceCMYK where it's named (pictures, shadings, transparency groups,
        # color space resources)
        for key in ("ColorSpace", "CS"):
            v = m.pdf_dict_gets(d, key)
            if key == "CS" and _name(m.pdf_dict_gets(d, "S")) != "Transparency":
                continue
            if _is_cmyk_name(v):
                self._cmyk_used(page)
                if self.fix:
                    m.pdf_dict_puts(d, key, self._cmyk())
            elif _name(v) == "DeviceRGB":
                self.uses_rgb_on(page)
            r = m.pdf_resolve_indirect(v)
            if key == "ColorSpace" and m.pdf_is_dict(r):
                for name, cs in list(_items(r)):
                    if name.startswith("Default"):
                        continue
                    if _is_cmyk_name(cs):
                        self._cmyk_used(page)
                        if self.fix:
                            m.pdf_dict_puts(r, name, self._cmyk())
                    elif _name(cs) == "DeviceRGB":
                        self.uses_rgb_on(page)

    def _array(self, a, page):
        """Color space arrays naming DeviceCMYK ([/Separation /Spot /DeviceCMYK fn],
        [/Indexed /DeviceCMYK ...], [/DeviceN ...], [/Pattern /DeviceCMYK])."""
        n = m.pdf_array_len(a)
        if not n or _name(m.pdf_array_get(a, 0)) not in ("Separation", "DeviceN", "Indexed",
                                                        "Pattern", "NChannel"):
            return
        for k in range(1, n):
            v = m.pdf_array_get(a, k)
            if m.pdf_is_name(v) and m.pdf_to_name(v) == "DeviceCMYK":
                self._cmyk_used(page)
                if self.fix:
                    m.pdf_array_put(a, k, self._cmyk())
            elif m.pdf_is_name(v) and m.pdf_to_name(v) == "DeviceRGB":
                self.uses_rgb_on(page)

    def _bad_action(self, act):
        """The kind of action act is if PDF/A doesn't allow it (6.5.1), else False."""
        if not m.pdf_is_dict(act):
            return False
        s = _name(m.pdf_dict_gets(act, "S"))
        if s is None:
            return False
        if s not in ALLOWED_ACTIONS:
            return s
        if s == "Named" and _name(m.pdf_dict_gets(act, "N")) not in ALLOWED_NAMED:
            return "Named"
        nxt = _get(act, "Next")
        if m.pdf_is_dict(nxt):
            return self._bad_action(nxt)
        if m.pdf_is_array(nxt):
            for k in range(m.pdf_array_len(nxt)):
                bad = self._bad_action(m.pdf_resolve_indirect(m.pdf_array_get(nxt, k)))
                if bad:
                    return bad
        return False

    @staticmethod
    def _bad_halftone(ht):
        """6.2.5: halftones of type 1 or 5, without HalftoneName (and TransferFunction only
        where ISO 32000-1 needs it: left to the check, it's rare)."""
        if m.pdf_is_name(ht):
            return False        # /Default
        if not m.pdf_is_dict(ht):
            return True
        return m.pdf_to_int(_get(ht, "HalftoneType")) not in (1, 5) or _has(ht, "HalftoneName")

    # -- fonts (6.2.11)
    def _font(self, xref, d, page):
        sub = _name(m.pdf_dict_gets(d, "Subtype"))
        name = _name(m.pdf_dict_gets(d, "BaseFont")) or "?"
        shown = re.sub(r"^[A-Z]{6}\+", "", name)
        if sub == "Type3":
            return
        if sub == "Type0":
            desc = _get(d, "DescendantFonts")
            cid = m.pdf_resolve_indirect(m.pdf_array_get(desc, 0)) \
                if m.pdf_is_array(desc) and m.pdf_array_len(desc) else None
            enc = m.pdf_resolve_indirect(m.pdf_dict_gets(d, "Encoding"))
            if m.pdf_is_name(enc) and m.pdf_to_name(enc) not in PREDEFINED_CMAPS:
                self.problem("fonts", page, tr("Font {font} uses a character map (CMap) that "
                                               "isn't embedded ({cmap}).").format(
                    font=shown, cmap=m.pdf_to_name(enc)), False)
            if cid is None or not m.pdf_is_dict(cid):
                return
            fd = _get(cid, "FontDescriptor")
            embedded = m.pdf_is_dict(fd) and any(_has(fd, k) for k in ("FontFile", "FontFile2",
                                                                       "FontFile3"))
            if not embedded:
                self.problem("fonts", page, tr("Font {font} isn't embedded, and KanzonasPDF has "
                                               "no copy of it to embed.").format(font=shown),
                             False)
                return
            if _name(m.pdf_dict_gets(cid, "Subtype")) == "CIDFontType2" and \
                    not _has(cid, "CIDToGIDMap"):
                self.problem("fonts", page, tr("Font {font} lacks its CIDToGIDMap.").format(
                    font=shown))
                if self.fix:
                    m.pdf_dict_puts(cid, "CIDToGIDMap", m.pdf_new_name("Identity"))
            self._font_descriptor(fd, page, shown)
            return
        if sub not in ("Type1", "MMType1", "TrueType"):
            if sub is not None:
                self.problem("fonts", page, tr("Font {font} is of a kind PDF/A doesn't "
                                               "allow.").format(font=shown), False)
            return
        fd = _get(d, "FontDescriptor")
        embedded = m.pdf_is_dict(fd) and any(_has(fd, k) for k in ("FontFile", "FontFile2",
                                                                   "FontFile3"))
        if embedded:
            self._font_descriptor(fd, page, shown)
            if not _has(d, "Widths") or not _has(d, "FirstChar"):
                self.problem("fonts", page, tr("Font {font} has no character widths.").format(
                    font=shown), False)
            return
        std = standard_font(name)
        if std is None or (sub == "TrueType" and std in ("Symbol", "ZapfDingbats")):
            self.problem("fonts", page, tr("Font {font} isn't embedded, and KanzonasPDF has no "
                                           "copy of it to embed.").format(font=shown), False)
            return
        plan = _embed_plan(d, std, sub)
        if plan is None:
            self.problem("fonts", page, tr("Font {font} isn't embedded, and the standard font "
                                           "that could replace it has other character widths "
                                           "or encoding.").format(font=shown), False)
            return
        self.problem("fonts", page, tr("Font {font} isn't embedded.").format(font=shown))
        if self.fix:
            self.font_jobs.append(lambda: self._embed(d, std, plan))

    def _font_descriptor(self, fd, page, shown):
        if not m.pdf_is_dict(fd):
            return
        ff3 = _get(fd, "FontFile3")
        if _stream_of(fd, "FontFile3") is not None:
            sub = _name(m.pdf_dict_gets(ff3, "Subtype"))
            if sub not in (None, "Type1C", "CIDFontType0C", "OpenType"):
                self.problem("fonts", page, tr("Font {font} is of a kind PDF/A doesn't "
                                               "allow.").format(font=shown), False)
        if self.fix:
            # 6.2.11.4.2: CharSet and CIDSet, when present, must list every glyph of the
            # font program exactly; both are optional, so they go rather than being trusted
            m.pdf_dict_dels(fd, "CharSet")
            m.pdf_dict_dels(fd, "CIDSet")

    def _embed(self, d, std, plan):
        """Embed MuPDF's program of the standard font std in font dictionary d (a simple
        font), with widths read from that program (6.2.11.4.1, 6.2.11.5)."""
        if not hasattr(self, "_font_files"):
            self._font_files = {}
        mu_name, flags, angle, cap, stemv = STANDARD_14[std]
        font = pymupdf.Font(mu_name)
        if std not in self._font_files:
            data = font.buffer
            ff = self.doc.get_new_xref()
            self.doc.update_object(ff, "<< /Subtype /Type1C >>")
            self.doc.update_stream(ff, data, compress=True)
            bbox = font.bbox
            desc = self.doc.get_new_xref()
            self.doc.update_object(desc, (
                "<< /Type /FontDescriptor /FontName /%s /Flags %d /FontBBox [%d %d %d %d] "
                "/ItalicAngle %g /Ascent %d /Descent %d /CapHeight %d /StemV %d "
                "/FontFile3 %d 0 R >>") % (std, flags, round(bbox.x0 * 1000),
                                           round(bbox.y0 * 1000), round(bbox.x1 * 1000),
                                           round(bbox.y1 * 1000), angle,
                                           round(font.ascender * 1000),
                                           round(font.descender * 1000), cap, stemv, ff))
            self._font_files[std] = desc
        desc = self._font_files[std]
        m.pdf_dict_puts(d, "Subtype", m.pdf_new_name("Type1"))
        m.pdf_dict_puts(d, "BaseFont", m.pdf_new_name(std))
        m.pdf_dict_puts(d, "FontDescriptor", _ref(self.pdf, desc))
        if std in ("Symbol", "ZapfDingbats"):
            # a symbolic font is drawn with its own encoding (as MuPDF shows it): a named base
            # encoding (some programs write WinAnsiEncoding) would, once the font is
            # embedded, send other readers looking for Latin letters it doesn't have
            enc = m.pdf_resolve_indirect(m.pdf_dict_gets(d, "Encoding"))
            if m.pdf_is_name(enc):
                m.pdf_dict_dels(d, "Encoding")
            elif m.pdf_is_dict(enc):
                m.pdf_dict_dels(enc, "BaseEncoding")
        widths = plan
        if widths is not True:
            first, last = min(widths), max(widths)
            arr = m.pdf_new_array(self.pdf, last - first + 1)
            for c in range(first, last + 1):
                m.pdf_array_push(arr, m.pdf_new_int(widths.get(c, 0)))
            m.pdf_dict_puts(d, "FirstChar", m.pdf_new_int(first))
            m.pdf_dict_puts(d, "LastChar", m.pdf_new_int(last))
            m.pdf_dict_puts(d, "Widths", arr)
        self.note(tr("Embedded the standard fonts (Helvetica, Times, Courier...) from "
                     "KanzonasPDF's own copies."))

    # -- colors (6.2.4.3)
    def _cmyk(self):
        if self.cmyk_ref is None:
            prof = self.doc.get_new_xref()
            self.doc.update_object(prof, "<< /N 4 >>")
            self.doc.update_stream(prof, icc_profile("cmyk"), compress=True)
            arr = self.doc.get_new_xref()
            self.doc.update_object(arr, "[/ICCBased %d 0 R]" % prof)
            self.cmyk_ref = arr
        return _ref(self.pdf, self.cmyk_ref)

    def _cmyk_used(self, page):
        self.uses_cmyk = True
        if self.intent_cs != "CMYK":
            self.problem("color", page, tr("CMYK colors are used without a CMYK color profile."))

    def uses_rgb_on(self, page):
        self.uses_rgb = True
        if self.intent_cs not in (None, "RGB"):
            self.problem("color", page, tr("RGB colors are used with a CMYK output intent."))

    def _colors(self):
        """DeviceCMYK set by the content itself (k, K, cs with /DeviceCMYK, inline pictures):
        a DefaultCMYK color space (the CMYK profile MuPDF draws with) in every resource
        dictionary takes care of those (6.2.4.3: "a device independent DefaultCMYK colour
        space has been set")."""
        self._content_xrefs()
        cmyk_somewhere = False
        for xref, page, holder in self.content_streams:
            self._tick()
            try:
                data = self.doc.xref_stream(xref)
            except Exception:
                continue
            if not data:
                continue
            if _CMYK_OPS.search(data):
                res = m.pdf_resolve_indirect(
                    m.pdf_dict_get_inheritable(holder, m.pdf_new_name("Resources")))
                if m.pdf_is_dict(res) and \
                        not m.pdf_is_null(m.pdf_dict_getp(res, "ColorSpace/DefaultCMYK")):
                    continue
                cmyk_somewhere = True
                self._cmyk_used(page)
            if self.intent_cs not in (None, "RGB") and _RGB_OPS.search(data):
                self.uses_rgb_on(page)
        if not (self.fix and cmyk_somewhere):
            return
        pdf = self.pdf
        holders = [m.pdf_load_object(pdf, self.doc[i].xref) for i in range(self.doc.page_count)]
        for xref in range(1, self.doc.xref_length()):
            try:
                obj = m.pdf_load_object(pdf, xref)
            except Exception:
                continue
            if m.pdf_is_dict(obj) and (_name(m.pdf_dict_gets(obj, "Subtype")) == "Form" or
                                       _has(obj, "PatternType") or
                                       _name(m.pdf_dict_gets(obj, "Subtype")) == "Type3"):
                holders.append(obj)
        for obj in holders:
            res = _get(obj, "Resources")
            if not m.pdf_is_dict(res):
                continue
            cs = _get(res, "ColorSpace")
            if not m.pdf_is_dict(cs):
                cs = m.pdf_new_dict(pdf, 1)
                m.pdf_dict_puts(res, "ColorSpace", cs)
                cs = _get(res, "ColorSpace")
            if not _has(cs, "DefaultCMYK"):
                m.pdf_dict_puts(cs, "DefaultCMYK", self._cmyk())

    # -- attached files (6.8)
    def _attachments(self):
        """PDF/A-2 allows attachments only when they are PDF/A themselves (-1 or -2); PDF/A-3
        allows any, each with its kind (MIME type), its relationship to the document
        (AFRelationship) and listed among the document's associated files (AF). Both want
        the file name in both forms (F and UF)."""
        doc, pdf = self.doc, self.pdf
        specs = []          # [file spec, page, put(ref): make the holder point to ref]
        tree = m.pdf_resolve_indirect(m.pdf_dict_getp(self.catalog, "Names/EmbeddedFiles"))
        for holder, k in _name_tree_entries(tree):
            raw = m.pdf_array_get(holder, k)
            specs.append((raw, None, lambda ref, h=holder, k=k: m.pdf_array_put(h, k, ref)))
        for i in range(doc.page_count):
            obj = m.pdf_load_object(pdf, doc[i].xref)
            annots = _get(obj, "Annots")
            if not m.pdf_is_array(annots):
                continue
            for k in range(m.pdf_array_len(annots)):
                a = m.pdf_resolve_indirect(m.pdf_array_get(annots, k))
                if _name(m.pdf_dict_gets(a, "Subtype")) == "FileAttachment" and \
                        m.pdf_is_dict(_get(a, "FS")):
                    specs.append((m.pdf_dict_gets(a, "FS"), i,
                                  lambda ref, a=a: m.pdf_dict_puts(a, "FS", ref)))
        found = []
        for raw, page, put in specs:
            spec = m.pdf_resolve_indirect(raw)
            ef = _get(spec, "EF")
            stream = None
            for key in ("F", "UF"):
                if stream is None and m.pdf_is_dict(ef):
                    stream = _stream_of(ef, key)
            if stream is None:
                continue
            label = _text(m.pdf_dict_gets(spec, "UF")) or _text(m.pdf_dict_gets(spec, "F")) or "?"
            try:
                data = _data(stream)
            except Exception:
                data = b""
            found.append((raw, spec, stream, page, put, label, pdfa_part_of(data) in (1, 2)))
            if not (_has(spec, "F") and _has(spec, "UF")):
                self.problem("attachments", page, tr("Attached file {name} lacks its file name "
                                                     "in one of the two forms.").format(
                    name=label))
                if self.fix:
                    for key in ("F", "UF"):
                        if not _has(spec, key):
                            m.pdf_dict_puts(spec, key, m.pdf_new_text_string(label))
        claims3 = self.claimed is not None and self.claimed[0] == 3
        others = [f for f in found if not f[6]]
        for raw, spec, stream, page, put, label, _ok in found if claims3 else others:
            if claims3:
                if not _has(spec, "AFRelationship") or not _has(stream, "Subtype"):
                    self.problem("attachments", page, tr(
                        "Attached file {name} lacks what PDF/A-3 requires (its kind and its "
                        "relationship to the document).").format(name=label))
            else:
                self.problem("attachments", page, tr(
                    "Attached file {name} isn't PDF/A. PDF/A-2 allows only PDF/A attachments; "
                    "Save as PDF/A saves such a document as PDF/A-3b, which allows any "
                    "attachment.").format(name=label))
        if not (self.fix and others):
            return
        self.part = 3
        af = m.pdf_new_array(pdf, len(found))
        for raw, spec, stream, page, put, label, _ok in found:
            if not _has(spec, "AFRelationship"):
                m.pdf_dict_puts(spec, "AFRelationship", m.pdf_new_name("Unspecified"))
            if not _has(stream, "Subtype"):
                mime = mimetypes.guess_type(label)[0] or "application/octet-stream"
                m.pdf_dict_puts(stream, "Subtype", m.pdf_new_name(mime))
            if m.pdf_is_indirect(raw):
                ref = _ref(pdf, m.pdf_to_num(raw))
            else:
                # (a file spec written inside its holder: made an object of its own, so the
                # list of associated files names the same one)
                ref = m.pdf_add_object(pdf, spec)
                put(ref)
            m.pdf_array_push(af, ref)
        m.pdf_dict_puts(self.catalog, "AF", af)
        self.note(tr("The document has attached files that aren't PDF/A, so it was saved as "
                     "PDF/A-3b, the part of the standard that allows any attached file "
                     "(PDF/A-2b allows only PDF/A attachments)."))

    # -- the metadata (6.6), written last
    def _finish(self):
        doc = self.doc
        info = dict(doc.metadata or {})
        now = datetime.datetime.now().astimezone()
        from . import __version__
        props = {
            "title": info.get("title") or "", "author": info.get("author") or "",
            "subject": info.get("subject") or "", "keywords": info.get("keywords") or "",
            "creator": info.get("creator") or "",
            "producer": "KanzonasPDF %s" % __version__,
            "creationDate": info.get("creationDate") or "",
            "modDate": pdf_date(now), "trapped": "",
        }
        if props["creationDate"] and _xmp_date(props["creationDate"]) is None:
            props["creationDate"] = ""          # (one that can't be read: dropped from both)
        doc.set_metadata(props)
        doc.set_xml_metadata(xmp_packet(props, self.part, now))


class _Stopped(Exception):
    pass


_PYMUPDF_APPEARANCES = {"Text", "FreeText", "Line", "Square", "Circle", "Polygon", "PolyLine",
                        "Highlight", "Underline", "Squiggly", "StrikeOut", "Stamp", "Caret",
                        "Ink", "FileAttachment", "Redact"}


def _inheritable(obj, key):
    """A field's key, from it or the fields above it."""
    seen = 0
    while m.pdf_is_dict(obj) and seen < 50:
        v = m.pdf_dict_gets(obj, key)
        if not m.pdf_is_null(v):
            return m.pdf_resolve_indirect(v)
        obj = _get(obj, "Parent")
        seen += 1
    return m.PdfObj()


def _name_tree_entries(tree):
    """[(Names array, index of a value in it)] of a name tree."""
    out = []
    todo = [tree] if m.pdf_is_dict(tree) else []
    while todo:
        node = todo.pop()
        names = _get(node, "Names")
        if m.pdf_is_array(names):
            for k in range(1, m.pdf_array_len(names), 2):
                if m.pdf_is_dict(m.pdf_resolve_indirect(m.pdf_array_get(names, k))):
                    out.append((names, k))
        kids = _get(node, "Kids")
        if m.pdf_is_array(kids):
            todo.extend(m.pdf_resolve_indirect(m.pdf_array_get(kids, k))
                        for k in range(m.pdf_array_len(kids)))
    return out


def _font_encoding(d, std, font):
    """{code: glyph index in MuPDF's program of std} for simple font d, following its
    Encoding as a PDF reader does (ISO 32000-1, 9.6.6); None when it can't be followed."""
    enc = m.pdf_resolve_indirect(m.pdf_dict_gets(d, "Encoding"))
    symbolic = std in ("Symbol", "ZapfDingbats")
    base, diffs = None, None
    if m.pdf_is_name(enc):
        base = m.pdf_to_name(enc)
    elif m.pdf_is_dict(enc):
        base = _name(m.pdf_dict_gets(enc, "BaseEncoding"))
        diffs = _get(enc, "Differences")
    elif not m.pdf_is_null(enc):
        return None
    out = {}
    if base and not symbolic:
        names = base_encoding(base)
        if names is None:
            return None
        for code, gname in names.items():
            out[code] = m.fz_encode_character_by_glyph_name(font.this, gname)
    else:
        builtin = cff_builtin_encoding(font.buffer)
        if builtin is None:
            return None
        if builtin == "Standard":
            for code, gname in base_encoding("StandardEncoding").items():
                out[code] = m.fz_encode_character_by_glyph_name(font.this, gname)
        else:
            out.update(builtin)
    if diffs is not None and m.pdf_is_array(diffs):
        code = 0
        for k in range(m.pdf_array_len(diffs)):
            v = m.pdf_resolve_indirect(m.pdf_array_get(diffs, k))
            if m.pdf_is_number(v):
                code = m.pdf_to_int(v)
            elif m.pdf_is_name(v):
                out[code] = m.fz_encode_character_by_glyph_name(font.this, m.pdf_to_name(v))
                code += 1
    return {c: g for c, g in out.items() if 0 <= c <= 255}


def _embed_plan(d, std, sub):
    """How to embed std in font dictionary d: True (its widths already match the program),
    {code: width} (no widths there: these to add), or None (it can't be done without
    changing the text: other widths or an encoding that can't be followed)."""
    if sub == "TrueType":
        # a TrueType font (Arial, Times New Roman...) becomes a Type 1 font: only with an
        # encoding a Type 1 font reads the same way
        enc = m.pdf_resolve_indirect(m.pdf_dict_gets(d, "Encoding"))
        base = m.pdf_to_name(enc) if m.pdf_is_name(enc) else \
            _name(m.pdf_dict_gets(enc, "BaseEncoding")) if m.pdf_is_dict(enc) else None
        if base not in ("WinAnsiEncoding", "MacRomanEncoding", "StandardEncoding"):
            return None
    font = pymupdf.Font(STANDARD_14[std][0])
    codes = _font_encoding(d, std, font)
    if codes is None:
        return None
    program = {c: round(m.fz_advance_glyph(font.this, g, 0) * 1000)
               for c, g in codes.items() if g > 0}
    widths = _get(d, "Widths")
    if not m.pdf_is_array(widths):
        if not program:
            return None
        return program
    first = m.pdf_to_int(_get(d, "FirstChar"))
    for k in range(m.pdf_array_len(widths)):
        c = first + k
        w = m.pdf_to_real(m.pdf_resolve_indirect(m.pdf_array_get(widths, k)))
        if c in program and abs(program[c] - w) > 1 and w != 0:
            return None
    return True


# ---- metadata ------------------------------------------------------------------------------
def pdf_date(dt):
    """A PDF date string (D:YYYYMMDDHHmmSS+HH'mm') of an aware datetime."""
    off = dt.utcoffset() or datetime.timedelta(0)
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return "D:%s%s%02d'%02d'" % (dt.strftime("%Y%m%d%H%M%S"), sign, minutes // 60, minutes % 60)


def _xmp_date(pdfdate):
    """The XMP (ISO 8601) form of a PDF date string, or None when it can't be read."""
    s = (pdfdate or "").strip()
    mo = re.match(r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?"
                  r"(?:(Z)|([+-])(\d{2})'?(\d{2})?'?)?", s)
    if not mo:
        return None
    y, mon, day, hh, mm, ss, z, sign, th, tm = mo.groups()
    try:
        datetime.datetime(int(y), int(mon or 1), int(day or 1), int(hh or 0), int(mm or 0),
                          int(ss or 0))
    except ValueError:
        return None
    out = "%s-%s-%sT%s:%s:%s" % (y, mon or "01", day or "01", hh or "00", mm or "00", ss or "00")
    if z:
        out += "Z"
    elif sign:
        out += "%s%s:%s" % (sign, th, tm or "00")
    return out


def _xml(text):
    """text fit for XML 1.0 (no control characters), escaped."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]", "", text or "")
    return escape(text, {'"': "&quot;"})


def xmp_packet(props, part, now=None):
    """The document's XMP metadata for PDF/A: the PDF/A identification (part, level B) and
    the document properties, the same as in the document information dictionary."""
    now = now or datetime.datetime.now().astimezone()
    lines = ['<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>',
             '<x:xmpmeta xmlns:x="adobe:ns:meta/">',
             '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
             '<rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">',
             '<pdfaid:part>%d</pdfaid:part>' % part,
             '<pdfaid:conformance>B</pdfaid:conformance>',
             '</rdf:Description>',
             '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">',
             '<dc:format>application/pdf</dc:format>']
    if props.get("title"):
        lines.append('<dc:title><rdf:Alt><rdf:li xml:lang="x-default">%s</rdf:li></rdf:Alt>'
                     '</dc:title>' % _xml(props["title"]))
    if props.get("author"):
        lines.append('<dc:creator><rdf:Seq><rdf:li>%s</rdf:li></rdf:Seq></dc:creator>'
                     % _xml(props["author"]))
    if props.get("subject"):
        lines.append('<dc:description><rdf:Alt><rdf:li xml:lang="x-default">%s</rdf:li>'
                     '</rdf:Alt></dc:description>' % _xml(props["subject"]))
    lines += ['</rdf:Description>',
              '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">']
    if props.get("creator"):
        lines.append('<xmp:CreatorTool>%s</xmp:CreatorTool>' % _xml(props["creator"]))
    created = _xmp_date(props.get("creationDate"))
    if created:
        lines.append('<xmp:CreateDate>%s</xmp:CreateDate>' % created)
    modified = _xmp_date(props.get("modDate"))
    if modified:
        lines.append('<xmp:ModifyDate>%s</xmp:ModifyDate>' % modified)
        lines.append('<xmp:MetadataDate>%s</xmp:MetadataDate>' % modified)
    lines += ['</rdf:Description>',
              '<rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">']
    if props.get("producer"):
        lines.append('<pdf:Producer>%s</pdf:Producer>' % _xml(props["producer"]))
    if props.get("keywords"):
        lines.append('<pdf:Keywords>%s</pdf:Keywords>' % _xml(props["keywords"]))
    lines += ['</rdf:Description>',
              '<rdf:Description rdf:about="" xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/">',
              '<xmpMM:DocumentID>uuid:%s</xmpMM:DocumentID>' % uuid.uuid4(),
              '<xmpMM:InstanceID>uuid:%s</xmpMM:InstanceID>' % uuid.uuid4(),
              '</rdf:Description>', '</rdf:RDF>', '</x:xmpmeta>']
    padding = "\n".join([" " * 99] * 20)
    return "\n".join(lines) + "\n" + padding + '\n<?xpacket end="w"?>'


def _info_matches_xmp(doc, xml):
    """Whether the document information (title, author, subject, keywords, creator,
    producer) is also in the XMP metadata, the same."""
    info = doc.metadata or {}
    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
        value = (info.get(key) or "").strip()
        if value and _xml(value) not in xml and value not in xml:
            return False
    return True


def pdfa_part_of(data):
    """The PDF/A part (1, 2, 3...) a PDF in data says it conforms to, or None (not a PDF, or
    not PDF/A)."""
    if not data[:1024].lstrip().startswith(b"%PDF"):
        return None
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return None
    try:
        xml = doc.get_xml_metadata() or ""
    finally:
        doc.close()
    mo = re.search(r"pdfaid:part(?:>|\s*=\s*[\"'])\s*(\d)", xml)
    return int(mo.group(1)) if mo else None


# ---- the commands --------------------------------------------------------------------------
def check(doc, step=None):
    """What keeps doc from being PDF/A-2b (or PDF/A-3b, when it says it is): [Problem].
    Only reads doc. step(): called now and then; False stops (None is returned)."""
    try:
        return _Pass(doc, fix=False, step=step).run().problems
    except _Stopped:
        return None


def convert(data, path, step=None):
    """Write a PDF/A copy of the PDF in data (bytes, not encrypted) to path. Returns
    {"part": 2 or 3, "notes": [what was changed], "remaining": [Problem]: what the copy
    still has that PDF/A doesn't allow (the check of the file written)}; None if step()
    said stop (nothing is written then)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise ValueError(tr("This document is protected with a password. PDF/A doesn't "
                                "allow encryption: remove its security first."))
        try:
            work = _Pass(doc, fix=True, step=step).run()
        except _Stopped:
            return None
        tmp = path + ".kanzonas-tmp"
        try:
            doc.save(tmp, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    finally:
        doc.close()
    out = pymupdf.open(path)
    try:
        remaining = _Pass(out, fix=False).run().problems
    finally:
        out.close()
    return {"part": work.part, "notes": work.notes, "remaining": remaining}

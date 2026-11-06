"""Comments exchanged without the PDF: markups with their replies and review statuses
exported to XFDF (the XML form Acrobat and others read and write: Adobe's XFDF Specification
3.0, standardized as ISO 19444-1, https://www.iso.org/standard/74272.html) or FDF (the same
annotations in PDF syntax, ISO 32000-1 12.7.8), and imported into another copy of the
document.

Each markup goes as a record: its page (0 = the first), its PDF subtype and its keys, read
as plain values (numbers, text, names), never as raw PDF text: a file from someone else
can't slip references to other objects of the document into it. Positions are PDF user
space, as the file has them (XFDF's own), so they come back exactly.
KanzonasPDF's own markups also carry their style (/KZProps, in XFDF as kz:props in their own
namespace, which other programs leave alone): imported, they are drawn again as KanzonasPDF
draws them (annotations.write). Markups from other programs get an appearance from MuPDF.

Importing matches markups by name (/NM): one already in the document is replaced when the
imported one differs and skipped when it's the same, so comments sent back and forth don't
pile up. Markups for pages the document doesn't have are skipped and reported; pictures and
attached files aren't exchanged (their contents aren't part of a comment file).
"""

import json
import re
import uuid
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

import pymupdf

from . import annotations as A
from . import review
from .i18n import tr

NS = "http://ns.adobe.com/xfdf/"
KZ_NS = "https://kanzonas.com/ns/xfdf/1"
_SKIP = (pymupdf.PDF_ANNOT_POPUP, pymupdf.PDF_ANNOT_WIDGET, pymupdf.PDF_ANNOT_LINK)

# PDF subtype -> XFDF element
ELEMENTS = {"Text": "text", "FreeText": "freetext", "Line": "line", "Square": "square",
            "Circle": "circle", "Polygon": "polygon", "PolyLine": "polyline",
            "Highlight": "highlight", "Underline": "underline", "Squiggly": "squiggly",
            "StrikeOut": "strikeout", "Stamp": "stamp", "Caret": "caret", "Ink": "ink",
            "Redact": "redact"}
SUBTYPES = {v: k for k, v in ELEMENTS.items()}
FLAG_NAMES = ["invisible", "hidden", "print", "nozoom", "norotate", "noview", "readonly",
              "locked", "togglenoview", "lockedcontents"]
STYLES = {"S": "solid", "D": "dash", "B": "bevelled", "I": "inset", "U": "underline"}
_NAME = re.compile(r"^[A-Za-z0-9#._+-]{1,64}$")
_REF = re.compile(r"\d+\s+\d+\s+R")

# the keys carried, by kind of value
STRINGS = ("T", "Contents", "Subj", "M", "CreationDate", "NM", "State", "StateModel", "DA",
           "DS", A.KZ_KEY)
NUMBERS = ("F", "CA", "Rotate", "Q", "LL", "LLE", "LLO")
NAMES = ("Name", "IT", "RT")
ARRAYS = ("Rect", "C", "IC", "QuadPoints", "Vertices", "L", "RD", "CL")
BOOLS = ("Open", "Cap")


# ---- numbers -----------------------------------------------------------------------------------
def _num(v):
    s = ("%.4f" % float(v)).rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def _nums(text):
    """'[1 2.5 3]' or '1,2.5;3' -> [1.0, 2.5, 3.0]."""
    out = []
    for t in re.split(r"[\s,;\[\]]+", text or ""):
        if t:
            out.append(float(t))
    return out


def _hex(c):
    if not c:
        return None
    if len(c) == 1:
        c = [c[0]] * 3
    elif len(c) == 4:
        k = c[3]
        c = [(1 - c[0]) * (1 - k), (1 - c[1]) * (1 - k), (1 - c[2]) * (1 - k)]
    elif len(c) != 3:
        return None
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v * 255))) for v in c)


def _rgb(h):
    h = (h or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", h):
        return None
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


# ---- reading a document's markups as records -------------------------------------------------
def _read_keys(doc, x):
    """The carried keys of annotation (or FDF object) x as plain values."""
    keys = {}
    for k in STRINGS:
        kind, val = doc.xref_get_key(x, k)
        if kind == "string":
            keys[k] = val
    for k in NUMBERS:
        kind, val = doc.xref_get_key(x, k)
        if kind in ("int", "float"):
            keys[k] = float(val)
    for k in NAMES:
        kind, val = doc.xref_get_key(x, k)
        if kind == "name" and _NAME.match(val.lstrip("/")):
            keys[k] = val.lstrip("/")
    for k in BOOLS:
        kind, val = doc.xref_get_key(x, k)
        if kind == "bool":
            keys[k] = val == "true"
    for k in ARRAYS:
        kind, val = doc.xref_get_key(x, k)
        if kind == "array" and not _REF.search(val):
            try:
                keys[k] = _nums(val)
            except ValueError:
                pass
    kind, val = doc.xref_get_key(x, "InkList")
    if kind == "array" and not _REF.search(val):
        try:
            keys["InkList"] = [_nums(s) for s in re.findall(r"\[([^\[\]]*)\]", val)]
        except ValueError:
            pass
    kind, val = doc.xref_get_key(x, "LE")
    if kind == "array":
        ends = [n for n in re.findall(r"/([A-Za-z]+)", val)]
        if len(ends) == 2:
            keys["LE"] = ends
    bs = {}
    kind, val = doc.xref_get_key(x, "BS/W")
    if kind in ("int", "float"):
        bs["W"] = float(val)
    kind, val = doc.xref_get_key(x, "BS/S")
    if kind == "name" and val.lstrip("/") in STYLES and val != "/S":
        bs["S"] = val.lstrip("/")           # (solid, the default, left out)
    kind, val = doc.xref_get_key(x, "BS/D")
    if kind == "array" and not _REF.search(val):
        bs["D"] = _nums(val)
    if not bs:
        kind, val = doc.xref_get_key(x, "Border")
        if kind == "array" and not _REF.search(val):
            nums = _nums(re.sub(r"\[[^\[\]]*\]", " ", val.strip()[1:-1]))
            if len(nums) >= 3:
                bs["W"] = nums[2]
    if bs:
        keys["BS"] = bs
    kind, val = doc.xref_get_key(x, "BE/S")
    if kind == "name" and val == "/C":
        kind, val = doc.xref_get_key(x, "BE/I")
        keys["BE"] = {"S": "C", "I": float(val) if kind in ("int", "float") else 1.0}
    return keys


def _skipped_kind(doc, x, subtype, keys):
    """Why this markup isn't exchanged (a picture, an attached file...), or ""."""
    if subtype not in ELEMENTS:
        return subtype or "?"
    if doc.xref_get_key(x, "KZImage")[0] != "null":
        return "Image"
    try:
        kind = json.loads(keys.get(A.KZ_KEY) or "{}").get("kind")
    except ValueError:
        kind = None
    if kind in ("image", "attach"):
        return kind
    return ""


def records(doc, only=None):
    """(records, skipped) for the document's markups: all of them, or only those in
    only {page index: [xref]} with their replies and statuses. skipped: {what: count}."""
    out, skipped = [], {}
    names = {}                                  # xref -> name, made up where one is missing
    pages = range(doc.page_count) if only is None else sorted(only)
    for i in pages:
        if not 0 <= i < doc.page_count:
            continue
        page = doc[i]
        threads = review.Threads(page)
        if only is None:
            wanted = None
        else:
            picked = [x for x in only[i]]
            wanted = set(picked) | set(threads.descendants(picked))
        for x, typ, nm in page.annot_xrefs():
            if typ in _SKIP or (wanted is not None and x not in wanted):
                continue
            kind, sub = doc.xref_get_key(x, "Subtype")
            sub = sub.lstrip("/")
            keys = _read_keys(doc, x)
            why = _skipped_kind(doc, x, sub, keys)
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            names[x] = keys.get("NM") or nm or "kz-" + str(uuid.uuid4())
            keys["NM"] = names[x]
            rec = {"page": i, "subtype": sub, "keys": keys, "xref": x}
            ln = threads.links.get(x)
            if ln is not None:
                rec["irt"] = ln.parent
            kind, val = doc.xref_get_key(x, "Popup")
            if kind == "xref":
                p = int(val.split()[0])
                pk, pv = doc.xref_get_key(p, "Rect")
                ok, ov = doc.xref_get_key(p, "Open")
                if pk == "array" and not _REF.search(pv):
                    rec["popup"] = {"rect": _nums(pv), "open": ov == "true"}
            out.append(rec)
    for rec in out:
        if "irt" in rec:
            rec["irt"] = names.get(rec["irt"])
            if rec["irt"] is None:
                del rec["irt"]
        rec.pop("xref", None)
    return out, skipped


# ---- XFDF ------------------------------------------------------------------------------------
def _attrs(rec):
    k = rec["keys"]
    at = [("page", str(rec["page"]))]
    if "Rect" in k:
        at.append(("rect", ",".join(_num(v) for v in k["Rect"])))
    for key, name in (("NM", "name"), ("T", "title"), ("Subj", "subject"), ("M", "date"),
                      ("CreationDate", "creationdate"), ("State", "state"),
                      ("StateModel", "statemodel")):
        if k.get(key):
            at.append((name, k[key]))
    if _hex(k.get("C")):
        at.append(("color", _hex(k["C"])))
    if _hex(k.get("IC")):
        at.append(("interior-color", _hex(k["IC"])))
    if "CA" in k:
        at.append(("opacity", _num(k["CA"])))
    if "F" in k:
        f = int(k["F"])
        at.append(("flags", ",".join(n for b, n in enumerate(FLAG_NAMES) if f & (1 << b))))
    if rec.get("irt"):
        at.append(("inreplyto", rec["irt"]))
        at.append(("replyType", "group" if k.get("RT") == "Group" else "reply"))
    if "IT" in k:
        at.append(("intent", k["IT"]))
    if "Name" in k:
        at.append(("icon", k["Name"]))
    if "Rotate" in k:
        at.append(("rotation", _num(k["Rotate"])))
    if "Q" in k:
        at.append(("justification", ("left", "centered", "right")[int(k["Q"]) % 3]))
    bs = k.get("BS") or {}
    if "W" in bs:
        at.append(("width", _num(bs["W"])))
    if k.get("BE", {}).get("S") == "C":
        at.append(("style", "cloudy"))
        at.append(("intensity", _num(k["BE"].get("I", 1))))
    elif bs.get("S") in STYLES:
        at.append(("style", STYLES[bs["S"]]))
    if bs.get("D"):
        at.append(("dashes", ",".join(_num(v) for v in bs["D"])))
    if "QuadPoints" in k:
        at.append(("coords", ",".join(_num(v) for v in k["QuadPoints"])))
    if len(k.get("L") or ()) == 4:
        at.append(("start", ",".join(_num(v) for v in k["L"][:2])))
        at.append(("end", ",".join(_num(v) for v in k["L"][2:])))
    if "LE" in k:
        if rec["subtype"] == "FreeText":
            at.append(("head", k["LE"][0]))
        else:
            at += [("head", k["LE"][0]), ("tail", k["LE"][1])]
    for key, name in (("LL", "leaderLength"), ("LLE", "leaderExtend"), ("LLO", "leaderOffset")):
        if key in k:
            at.append((name, _num(k[key])))
    if "Cap" in k:
        at.append(("caption", "yes" if k["Cap"] else "no"))
    if "Open" in k:
        at.append(("open", "yes" if k["Open"] else "no"))
    if k.get("RD"):
        at.append(("fringe", ",".join(_num(v) for v in k["RD"])))
    if k.get("CL"):
        at.append(("callout", ",".join(_num(v) for v in k["CL"])))
    if k.get(A.KZ_KEY):
        at.append(("kz:props", k[A.KZ_KEY]))
    return at


def _pairs(nums):
    return ";".join("%s,%s" % (_num(nums[i]), _num(nums[i + 1]))
                    for i in range(0, len(nums) - 1, 2))


def to_xfdf(recs, filename=""):
    """The records as an XFDF document (bytes, UTF-8)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<xfdf xmlns="%s" xmlns:kz="%s" xml:space="preserve">' % (NS, KZ_NS), "<annots>"]
    for rec in recs:
        tag = ELEMENTS[rec["subtype"]]
        k = rec["keys"]
        head = "<%s %s" % (tag, " ".join("%s=%s" % (n, quoteattr(v)) for n, v in _attrs(rec)))
        body = []
        if k.get("Contents"):
            body.append("<contents>%s</contents>" % escape(k["Contents"]))
        if k.get("DA"):
            body.append("<defaultappearance>%s</defaultappearance>" % escape(k["DA"]))
        if k.get("DS"):
            body.append("<defaultstyle>%s</defaultstyle>" % escape(k["DS"]))
        if k.get("Vertices"):
            body.append("<vertices>%s</vertices>" % _pairs(k["Vertices"]))
        if k.get("InkList"):
            body.append("<inklist>%s</inklist>" % "".join(
                "<gesture>%s</gesture>" % _pairs(g) for g in k["InkList"]))
        if rec.get("popup"):
            p = rec["popup"]
            body.append('<popup page="%d" rect="%s" open="%s" flags="print,nozoom,norotate"/>'
                        % (rec["page"], ",".join(_num(v) for v in p["rect"]),
                           "yes" if p.get("open") else "no"))
        lines.append(head + (">" + "".join(body) + "</%s>" % tag if body else "/>"))
    lines.append("</annots>")
    if filename:
        lines.append("<f href=%s/>" % quoteattr(filename))
    lines.append("</xfdf>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _local(tag):
    return tag.split("}", 1)[-1]


def from_xfdf(data):
    """The records in an XFDF document (bytes). Raises ValueError for a file that isn't
    XFDF."""
    if re.search(rb"<!(DOCTYPE|ENTITY)", data[:4096] if isinstance(data, bytes) else b""):
        raise ValueError(tr("This XFDF file declares a DTD or entities, which aren't allowed."))
    try:
        root = ET.fromstring(data)
    except ET.ParseError as ex:
        raise ValueError(tr("This isn't a readable XFDF file: {error}").format(error=ex))
    if _local(root.tag) != "xfdf":
        raise ValueError(tr("This isn't an XFDF file."))
    out = []
    for annots in root:
        if _local(annots.tag) != "annots":
            continue
        for el in annots:
            rec = _xfdf_record(el)
            if rec is not None:
                out.append(rec)
    return out


def _xfdf_record(el):
    tag = _local(el.tag)
    sub = SUBTYPES.get(tag)
    at = {_local(k) if not k.startswith("{" + KZ_NS) else "kz:" + _local(k): v
          for k, v in el.attrib.items()}
    if sub is None:
        return {"subtype": tag, "page": -1, "keys": {}, "unknown": True}
    try:
        page = int(at.get("page", "0"))
    except ValueError:
        page = -1
    k = {}
    try:
        if "rect" in at:
            k["Rect"] = _nums(at["rect"])[:4]
        for key, name in (("NM", "name"), ("T", "title"), ("Subj", "subject"),
                          ("M", "date"), ("CreationDate", "creationdate"),
                          ("State", "state"), ("StateModel", "statemodel"),
                          (A.KZ_KEY, "kz:props")):
            if name in at:
                k[key] = at[name]
        for key, name in (("C", "color"), ("IC", "interior-color")):
            if _rgb(at.get(name)):
                k[key] = _rgb(at[name])
        if "opacity" in at:
            k["CA"] = max(0.0, min(1.0, float(at["opacity"])))
        if "flags" in at:
            k["F"] = float(sum(1 << FLAG_NAMES.index(n.strip().lower())
                               for n in at["flags"].split(",")
                               if n.strip().lower() in FLAG_NAMES))
        if "intent" in at and _NAME.match(at["intent"]):
            k["IT"] = at["intent"]
        if "icon" in at and _NAME.match(at["icon"]):
            k["Name"] = at["icon"]
        if "rotation" in at:
            k["Rotate"] = float(at["rotation"])
        if "justification" in at:
            k["Q"] = float({"centered": 1, "right": 2}.get(at["justification"], 0))
        bs = {}
        if "width" in at:
            bs["W"] = float(at["width"])
        style = at.get("style", "")
        if style == "cloudy":
            k["BE"] = {"S": "C", "I": float(at.get("intensity", 1))}
        elif style in STYLES.values() and style != "solid":
            bs["S"] = next(s for s, n in STYLES.items() if n == style)
        if "dashes" in at:
            bs["D"] = _nums(at["dashes"])
        if bs:
            k["BS"] = bs
        if "coords" in at:
            k["QuadPoints"] = _nums(at["coords"])
        if "start" in at and "end" in at:
            k["L"] = _nums(at["start"])[:2] + _nums(at["end"])[:2]
        heads = [at.get("head"), at.get("tail")]
        if sub == "FreeText" and heads[0]:
            k["LE"] = [heads[0], "None"]
        elif any(heads):
            k["LE"] = [h if h and _NAME.match(h) else "None" for h in heads]
        for key, name in (("LL", "leaderLength"), ("LLE", "leaderExtend"),
                          ("LLO", "leaderOffset")):
            if name in at:
                k[key] = float(at[name])
        if "caption" in at:
            k["Cap"] = at["caption"] == "yes"
        if "open" in at:
            k["Open"] = at["open"] == "yes"
        if "fringe" in at:
            k["RD"] = _nums(at["fringe"])
        if "callout" in at:
            k["CL"] = _nums(at["callout"])
        if at.get("inreplyto"):
            k["RT"] = "Group" if at.get("replyType") == "group" else "R"
    except ValueError:
        return {"subtype": sub, "page": -1, "keys": {}, "unknown": True}
    rec = {"page": page, "subtype": sub, "keys": k}
    if at.get("inreplyto"):
        rec["irt"] = at["inreplyto"]
    for child in el:
        name = _local(child.tag)
        text = child.text or ""
        try:
            if name == "contents":
                k["Contents"] = "".join(child.itertext())
            elif name == "defaultappearance":
                k["DA"] = text
            elif name == "defaultstyle":
                k["DS"] = text
            elif name == "vertices":
                k["Vertices"] = _nums(text)
            elif name == "inklist":
                k["InkList"] = [_nums(g.text or "") for g in child if _local(g.tag) == "gesture"]
            elif name == "popup":
                rect = _nums(child.attrib.get("rect", ""))
                if len(rect) == 4:
                    rec["popup"] = {"rect": rect, "open": child.attrib.get("open") == "yes"}
        except ValueError:
            pass
    return rec


# ---- FDF -------------------------------------------------------------------------------------
def _pdf_dict(rec, page_key):
    """The record's keys as the inside of a PDF dictionary."""
    k = rec["keys"]
    parts = ["/Type/Annot/Subtype/" + rec["subtype"], page_key]
    for key in STRINGS:
        if key in k:
            parts.append("/%s%s" % (key, pymupdf.get_pdf_str(str(k[key]))))
    for key in NUMBERS:
        if key in k:
            v = k[key]
            parts.append("/%s %s" % (key, int(v) if key in ("F", "Q", "Rotate") else _num(v)))
    for key in NAMES:
        if key in k and _NAME.match(k[key]):
            parts.append("/%s/%s" % (key, k[key]))
    for key in BOOLS:
        if key in k:
            parts.append("/%s %s" % (key, "true" if k[key] else "false"))
    for key in ARRAYS:
        if key in k:
            parts.append("/%s[%s]" % (key, " ".join(_num(v) for v in k[key])))
    if k.get("InkList"):
        parts.append("/InkList[%s]" % "".join("[%s]" % " ".join(_num(v) for v in g)
                                              for g in k["InkList"]))
    if k.get("LE"):
        parts.append("/LE[/%s/%s]" % tuple(e if _NAME.match(e) else "None" for e in k["LE"]))
    bs = k.get("BS") or {}
    if bs:
        parts.append("/BS<<%s%s%s>>" % (
            "/W %s" % _num(bs["W"]) if "W" in bs else "",
            "/S/%s" % bs["S"] if bs.get("S") in STYLES else "",
            "/D[%s]" % " ".join(_num(v) for v in bs["D"]) if bs.get("D") else ""))
    if k.get("BE"):
        parts.append("/BE<</S/C/I %s>>" % _num(k["BE"].get("I", 1)))
    return "".join(parts)


def to_fdf(recs, filename=""):
    """The records as an FDF file (bytes)."""
    objs = {}
    num = {}
    n = 2
    for rec in recs:
        num[rec["keys"]["NM"]] = n
        n += 2 if rec.get("popup") else 1
    annots = []
    for rec in recs:
        x = num[rec["keys"]["NM"]]
        body = _pdf_dict(rec, "/Page %d" % rec["page"])
        if rec.get("irt") in num:
            body += "/IRT %d 0 R" % num[rec["irt"]]
        if rec.get("popup"):
            p = rec["popup"]
            body += "/Popup %d 0 R" % (x + 1)
            objs[x + 1] = "<</Type/Annot/Subtype/Popup/Rect[%s]/Open %s/Parent %d 0 R/F 28>>" % (
                " ".join(_num(v) for v in p["rect"]), "true" if p.get("open") else "false", x)
        objs[x] = "<<" + body + ">>"
        annots.append(x)
    objs[1] = "<</FDF<<%s/Annots[%s]>>>>" % (
        "/F%s" % pymupdf.get_pdf_str(filename) if filename else "",
        " ".join("%d 0 R" % x for x in annots))
    out = ["%FDF-1.2", "%\xe2\xe3\xcf\xd3"]
    for x in sorted(objs):
        out.append("%d 0 obj\n%s\nendobj" % (x, objs[x]))
    out.append("trailer\n<</Root 1 0 R>>\n%%EOF\n")
    return "\n".join(out).encode("latin-1")


def from_fdf(data):
    """The records in an FDF file (bytes). Raises ValueError for a file that isn't FDF."""
    if not data.lstrip()[:8].startswith(b"%FDF"):
        raise ValueError(tr("This isn't an FDF file."))
    try:
        fdf = pymupdf.open("pdf", data)
    except Exception as ex:
        raise ValueError(tr("This isn't a readable FDF file: {error}").format(error=ex))
    try:
        kind, root = fdf.xref_get_key(-1, "Root")
        if kind != "xref":
            raise ValueError(tr("This isn't an FDF file."))
        rx = int(root.split()[0])
        kind, val = fdf.xref_get_key(rx, "FDF/Annots")
        if kind == "xref":
            val = fdf.xref_object(int(val.split()[0]), compressed=True)
        xs = [int(a) for a in re.findall(r"(\d+)\s+0\s+R", val or "")]
        out, names = [], {}
        for x in xs:
            kind, sub = fdf.xref_get_key(x, "Subtype")
            sub = sub.lstrip("/")
            if sub not in ELEMENTS:
                out.append({"subtype": sub, "page": -1, "keys": {}, "unknown": True})
                continue
            keys = _read_keys(fdf, x)
            keys.setdefault("NM", "kz-" + str(uuid.uuid4()))
            names[x] = keys["NM"]
            pk, pv = fdf.xref_get_key(x, "Page")
            rec = {"page": int(pv) if pk == "int" else -1, "subtype": sub, "keys": keys}
            kind, irt = fdf.xref_get_key(x, "IRT")
            if kind == "xref":
                rec["irt"] = int(irt.split()[0])
            kind, pop = fdf.xref_get_key(x, "Popup")
            if kind == "xref":
                p = int(pop.split()[0])
                rk, rv = fdf.xref_get_key(p, "Rect")
                ok, ov = fdf.xref_get_key(p, "Open")
                if rk == "array" and not _REF.search(rv):
                    rec["popup"] = {"rect": _nums(rv), "open": ov == "true"}
            out.append(rec)
        for rec in out:
            if isinstance(rec.get("irt"), int):
                rec["irt"] = names.get(rec["irt"])
                if rec["irt"] is None:
                    del rec["irt"]
        return out
    finally:
        fdf.close()


# ---- importing records into a document -------------------------------------------------------
class Report:
    """What an import did: added, replaced, unchanged, skipped ({why: count})."""

    def __init__(self):
        self.added = self.replaced = self.unchanged = 0
        self.skipped = {}
        self.pages = set()

    def skip(self, why, n=1):
        self.skipped[why] = self.skipped.get(why, 0) + n

    def text(self):
        parts = [tr("{n} comments added").format(n=self.added)]
        if self.replaced:
            parts.append(tr("{n} updated").format(n=self.replaced))
        if self.unchanged:
            parts.append(tr("{n} already in the document").format(n=self.unchanged))
        out = ", ".join(parts) + "."
        for why, n in sorted(self.skipped.items()):
            out += "\n" + tr("Skipped: {n} ({why})").format(n=n, why=why)
        return out


def _same_record(doc, x, rec):
    """Annotation x already holds what rec says (the dates and text and places alike)."""
    have = _read_keys(doc, x)
    want = rec["keys"]
    for key in set(have) | set(want):
        a, b = have.get(key), want.get(key)
        if key in ("Rect",) and rec["subtype"] in ("Text", "Highlight", "Underline",
                                                   "StrikeOut", "Squiggly", "Line", "Ink"):
            continue                    # (worked out again by MuPDF from its geometry)
        if not A._same(a, b, tol=0.01):
            return False
    return True


def import_records(doc, recs):
    """Add the records' markups to doc (inside one DocumentView.modify: one undo step).
    Returns a Report. Records are matched by name (/NM) to markups already there."""
    rep = Report()
    by_page = {}
    for rec in recs:
        if rec.get("unknown"):
            rep.skip(tr("not a kind of comment KanzonasPDF exchanges") + ": " + rec["subtype"])
            continue
        if not 0 <= rec["page"] < doc.page_count:
            rep.skip(tr("page {n} isn't in this document").format(n=rec["page"] + 1))
            continue
        if len(rec["keys"].get("Rect") or ()) != 4:
            rep.skip(tr("no position"))
            continue
        rec["keys"].setdefault("NM", "kz-" + str(uuid.uuid4()))
        by_page.setdefault(rec["page"], []).append(rec)
    made = {}                                   # name -> new xref (across pages)
    existing = {}                               # name -> (page index, xref)
    named = {}                                  # xref -> name
    for i in by_page:
        for x, typ, nm in doc[i].annot_xrefs():
            if nm:
                existing[nm] = (i, x)
                named[x] = nm
    replies, redraws = [], []
    for i, page_recs in sorted(by_page.items()):
        page = doc[i]
        new, replace, redraw = [], [], []
        for rec in page_recs:
            name = rec["keys"]["NM"]
            old = existing.get(name)
            if old is not None and old[0] == i and _same_record(doc, old[1], rec):
                made[name] = old[1]
                rep.unchanged += 1
                continue
            if old is not None and old[0] == i:
                replace.append(old[1])
            x = doc.get_new_xref()
            body = _pdf_dict(rec, "/P %d 0 R" % page.xref)
            doc.update_object(x, "<<" + body + ">>")
            new.append(x)
            if rec.get("popup"):
                p = doc.get_new_xref()
                doc.update_object(p, "<</Type/Annot/Subtype/Popup/Rect[%s]/Open %s/Parent %d 0 R"
                                     "/F 28/P %d 0 R>>" % (
                                         " ".join(_num(v) for v in rec["popup"]["rect"]),
                                         "true" if rec["popup"].get("open") else "false", x,
                                         page.xref))
                doc.xref_set_key(x, "Popup", "%d 0 R" % p)
                new.append(p)
            made[name] = x
            rep.pages.add(i)
            if old is not None and old[0] == i:
                rep.replaced += 1
            else:
                rep.added += 1
            if rec.get("irt"):
                replies.append((x, rec))
            redraw.append((x, rec))
        if replace:
            from . import pdf_speed
            # (replies already there that answer one replaced answer the new one)
            threads = review.Threads(page)
            olds = set(replace)
            for x in replace:
                for c in threads.children.get(x, ()):
                    if c not in olds and named.get(x) in made:
                        doc.xref_set_key(c, "IRT", "%d 0 R" % made[named[x]])
            pdf_speed.delete_many(page, replace, keep_replies=True)
        if new:
            review._append_annots(page, new)
        redraws.append((i, redraw))
    for x, rec in replies:
        parent = made.get(rec["irt"])
        if parent is None and rec["irt"] in existing:
            parent = existing[rec["irt"]][1]
        if parent is not None and parent != x:
            doc.xref_set_key(x, "IRT", "%d 0 R" % parent)
            if rec["keys"].get("RT") != "Group":
                doc.xref_set_key(x, "RT", "/R")
    for i, redraw in redraws:
        _appearances(doc[i], redraw)
    return rep


def _appearances(page, redraw):
    """Draw the new markups: KanzonasPDF's own as it draws them, replies empty, statuses not
    at all (hidden), the rest as MuPDF draws them."""
    if not redraw:
        return
    doc = page.parent
    m = pymupdf.mupdf
    ours, theirs = [], []
    for x, rec in redraw:
        k = rec["keys"]
        if rec.get("irt") and rec["subtype"] == "Text" and k.get("RT") != "Group":
            if not k.get("State"):
                doc.xref_set_key(x, "AP", "<</N %d 0 R>>" % review._empty_appearance(doc))
            continue
        (ours if k.get(A.KZ_KEY) else theirs).append((x, rec))
    if theirs:
        loaded = A.load_annots(page, [x for x, _r in theirs])
        for x, _rec in theirs:
            a = loaded.get(x)
            if a is not None:
                try:
                    m.pdf_dirty_annot(a.this)
                    m.pdf_update_annot(a.this)
                except Exception:
                    pass
        loaded.clear()
    if not ours:
        return
    loaded = A.load_annots(page, [x for x, _r in ours])
    models = {}
    for x, _rec in ours:
        a = loaded.get(x)
        try:
            models[x] = A.read(a) if a is not None else None
        except Exception:
            models[x] = None
    loaded.clear()
    order = A.annot_order(page)
    fresh = {}
    from . import pdf_speed
    for x, rec in ours:
        model = models.get(x)
        if model is None:
            continue
        try:
            fresh[x] = A.write(page, model).xref
        except Exception:
            fresh.pop(x, None)          # (kept as it came: MuPDF draws it)
    if fresh:
        # the written one takes the imported one's place, its name, dates and flags
        threads = review.Threads(page)
        for old, new in fresh.items():
            for c in threads.children.get(old, ()):
                doc.xref_set_key(c, "IRT", "%d 0 R" % new)
            for key in ("NM", "M", "CreationDate", "T", "Subj"):
                kind, val = doc.xref_get_key(old, key)
                if kind == "string":
                    doc.xref_set_key(new, key, pymupdf.get_pdf_str(val))
            kind, val = doc.xref_get_key(old, "F")
            if kind == "int":
                doc.xref_set_key(new, "F", val)
        pdf_speed.delete_many(page, list(fresh), keep_replies=True)
        now = A.annot_order(page)
        kept = set(now)
        final = [fresh.get(x, x) for x in order if fresh.get(x, x) in kept]
        placed = set(final)
        final += [x for x in now if x not in placed]     # (pop-up notes write() added)
        if final != now:
            A.set_annot_order(page, final)
    for x, rec in ours:
        if x not in fresh:
            a = A.load_annots(page, [x]).get(x)
            if a is not None:
                try:
                    m.pdf_dirty_annot(a.this)
                    m.pdf_update_annot(a.this)
                except Exception:
                    pass
            del a

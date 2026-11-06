"""Smart forms: calculated fields, number / date / phone formats, range checks and required
fields, stored the way Acrobat stores them so every PDF reader that runs form scripts does the
same, and worked out here by KanzonasPDF itself.

KanzonasPDF never runs a PDF's JavaScript. A field's scripts are only *read*, by a strict
parser that recognizes the standard calls Acrobat writes (AFSimple_Calculate, the "simplified
field notation" formula between /** BVCALC and EVCALC **/, AFNumber_Format, AFPercent_Format,
AFDate_FormatEx, AFSpecial_Format, AFRange_Validate and their keystroke twins). Anything else is
a custom script: it's kept in the file, shown as "custom calculation (not run)", and never run.

Formulas ("Price * Qty + Shipping") are parsed by a small recursive-descent parser of our own
(+ - * / parentheses, numbers and field names); nothing is ever passed to eval.

Where it lives in the PDF (ISO 32000, 12.7 and 12.6.3):
- the field's /AA (additional actions): /K keystroke, /F format, /V validate, /C calculate,
  each a JavaScript action << /S /JavaScript /JS (...) >>;
- /AcroForm /CO: the calculated fields in the order a reader calculates them;
- /Ff bit 2: required; /TU: the tooltip (the field's description).
"""

import math
import re
from datetime import date

# ---- formulas: our own small, safe parser ------------------------------------------------
OPS = ("SUM", "PRD", "AVG", "MIN", "MAX")


class FormulaError(ValueError):
    pass


_NAME_START = re.compile(r"[A-Za-z_\u00c0-\uffff\\]")
_NAME_CHAR = re.compile(r"[A-Za-z0-9_.\u00c0-\uffff]")


def _tokens(text):
    """Tokens of a formula: ("num", float), ("name", str), ("op", ch). Field names are
    letters, digits, _ and . (a.b is field b under a); any other character in a name is
    written with a backslash before it (Acrobat's simplified field notation: Item\\ 1)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "+-*/()":
            out.append(("op", c))
            i += 1
        elif c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = re.compile(r"\d*\.?\d*(?:[eE][+-]?\d+)?").match(text, i)
            s = m.group(0)
            try:
                out.append(("num", float(s)))
            except ValueError:
                raise FormulaError("bad number %r" % s)
            i = m.end()
            if i < n and _NAME_START.match(text[i]) and text[i] != "\\":
                raise FormulaError("a name can't start with a digit: %r" % text[m.start():i + 1])
        elif _NAME_START.match(c):
            name = []
            while i < n:
                c = text[i]
                if c == "\\":
                    if i + 1 >= n:
                        raise FormulaError("a backslash ends the formula")
                    name.append(text[i + 1])
                    i += 2
                elif _NAME_CHAR.match(c):
                    name.append(c)
                    i += 1
                else:
                    break
            out.append(("name", "".join(name)))
        else:
            raise FormulaError("unexpected %r" % c)
    return out


def parse_formula(text):
    """A formula's tree: ("num", x) | ("field", name) | ("neg", a) | (op, a, b)."""
    toks = _tokens(text)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else (None, None)

    def take():
        t = peek()
        pos[0] += 1
        return t

    def expr():
        a = term()
        while peek() in (("op", "+"), ("op", "-")):
            a = (take()[1], a, term())
        return a

    def term():
        a = unary()
        while peek() in (("op", "*"), ("op", "/")):
            a = (take()[1], a, unary())
        return a

    def unary():
        if peek() in (("op", "-"), ("op", "+")):
            sign = take()[1]
            a = unary()
            return ("neg", a) if sign == "-" else a
        return primary()

    def primary():
        kind, val = take()
        if kind == "num":
            return ("num", val)
        if kind == "name":
            return ("field", val)
        if (kind, val) == ("op", "("):
            a = expr()
            if take() != ("op", ")"):
                raise FormulaError("a ( is not closed")
            return a
        raise FormulaError("the formula ends too soon" if kind is None else
                           "unexpected %r" % val)

    if not toks:
        raise FormulaError("empty formula")
    tree = expr()
    if pos[0] != len(toks):
        raise FormulaError("unexpected %r" % (toks[pos[0]][1],))
    return tree


def formula_fields(tree):
    """The field names a formula uses, in order, each once."""
    out = []

    def walk(t):
        if t[0] == "field":
            if t[1] not in out:
                out.append(t[1])
        elif t[0] != "num":
            for a in t[1:]:
                walk(a)
    walk(tree)
    return out


def eval_formula(tree, get):
    """The formula's value, get(name) giving each field's number (0 for an empty one).
    Raises ZeroDivisionError on a division by zero."""
    k = tree[0]
    if k == "num":
        return tree[1]
    if k == "field":
        return get(tree[1])
    if k == "neg":
        return -eval_formula(tree[1], get)
    a, b = eval_formula(tree[1], get), eval_formula(tree[2], get)
    if k == "+":
        return a + b
    if k == "-":
        return a - b
    if k == "*":
        return a * b
    if b == 0:
        raise ZeroDivisionError
    return a / b


_PREC = {"+": 1, "-": 1, "*": 2, "/": 2}


def _escape_name(name):
    return re.sub(r"([^A-Za-z0-9_.\u00c0-\uffff])", r"\\\1", name)


def _js_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _num(x):
    return number_text(x)


def formula_text(tree, parent=0, right=False):
    """The formula written out again (field names escaped, only the parentheses needed)."""
    k = tree[0]
    if k == "num":
        return _num(tree[1])
    if k == "field":
        return _escape_name(tree[1])
    if k == "neg":
        return "-" + formula_text(tree[1], 3)
    p = _PREC[k]
    s = "%s %s %s" % (formula_text(tree[1], p), k, formula_text(tree[2], p, True))
    return "(%s)" % s if p < parent or (right and p == parent) else s


def formula_js(tree, parent=0, right=False):
    """The JavaScript Acrobat writes for a simplified-field-notation formula."""
    k = tree[0]
    if k == "num":
        return _num(tree[1])
    if k == "field":
        return "AFMakeNumber(getField(%s).value)" % _js_str(tree[1])
    if k == "neg":
        return "-" + formula_js(tree[1], 3)
    p = _PREC[k]
    s = "%s %s %s" % (formula_js(tree[1], p), k, formula_js(tree[2], p, True))
    return "(%s)" % s if p < parent or (right and p == parent) else s


# ---- reading a field's scripts: a strict parser of the standard calls only -------------
_JS_TOKEN = re.compile(r"""\s*(?:
    (?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
  | (?P<num>-?\d+(?:\.\d*)?|-?\.\d+)
  | (?P<id>[A-Za-z_$][A-Za-z0-9_$]*)
  | (?P<p>[(),;\[\]])
)""", re.X)
_JS_ESC = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def _js_unquote(s):
    def one(m):
        c = m.group(1)
        if c[0] == "u":
            return chr(int(c[1:], 16))
        if c[0] == "x":
            return chr(int(c[1:], 16))
        return _JS_ESC.get(c, c)
    return re.sub(r"\\(u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2}|.)", one, s[1:-1])


def parse_call(js):
    """(name, [args]) when js is exactly one call of a function with literal arguments
    (strings, numbers, true / false, and arrays of those as [..] or new Array(..)), with an
    optional ';'; None for anything else. Nothing is ever run."""
    if not js:
        return None
    s = js.strip()
    toks, i = [], 0
    while i < len(s):
        m = _JS_TOKEN.match(s, i)
        if not m or m.end() == i:
            if s[i:].strip() == "":
                break
            return None
        i = m.end()
        kind = m.lastgroup
        toks.append((kind, m.group(kind)))
    pos = [0]

    def peek(k=0):
        return toks[pos[0] + k] if pos[0] + k < len(toks) else (None, None)

    def take(kind=None, val=None):
        t = peek()
        if (kind and t[0] != kind) or (val is not None and t[1] != val):
            raise ValueError
        pos[0] += 1
        return t

    def literal():
        kind, val = peek()
        if kind == "str":
            take()
            return _js_unquote(val)
        if kind == "num":
            take()
            return float(val)
        if kind == "id" and val in ("true", "false"):
            take()
            return val == "true"
        if (kind, val) == ("p", "["):
            take()
            return items("]")
        if (kind, val) == ("id", "new") and peek(1) == ("id", "Array"):
            take()
            take()
            take("p", "(")
            return items(")")
        raise ValueError

    def items(close):
        out = []
        if peek() == ("p", close):
            take()
            return out
        while True:
            out.append(literal())
            if peek() == ("p", close):
                take()
                return out
            take("p", ",")

    try:
        name = take("id")[1]
        take("p", "(")
        args = items(")")
        if peek() == ("p", ";"):
            take()
        if pos[0] != len(toks):
            return None
        return name, args
    except (ValueError, IndexError):
        return None


_SFN = re.compile(r"^\s*/\*\*\s*BVCALC\s(.*?)\sEVCALC\s*\*\*/", re.S)


def split_names(value):
    """A list of field names given as a list or as one string 'a, b, c' (AFMakeArrayFromList)."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def read_calc(js):
    """A calculate script as {"op", "fields"} | {"formula"} | {"custom"}; None for none."""
    if not js or not js.strip():
        return None
    m = _SFN.match(js)
    if m:
        try:
            tree = parse_formula(m.group(1).strip())
            return {"formula": formula_text(tree)}
        except FormulaError:
            return {"custom": js}
    call = parse_call(js)
    if call and call[0] == "AFSimple_Calculate" and len(call[1]) == 2 and \
            str(call[1][0]).upper() in OPS and isinstance(call[1][1], (list, str)):
        fields = split_names(call[1][1])
        if fields:
            return {"op": str(call[1][0]).upper(), "fields": fields}
    return {"custom": js}


def calc_js(calc):
    """The JavaScript for a calculation, as Acrobat writes it."""
    if not calc:
        return None
    if "custom" in calc:
        return calc["custom"]
    if "formula" in calc:
        tree = parse_formula(calc["formula"])
        return "/** BVCALC %s EVCALC **/ event.value = %s;" % (formula_text(tree),
                                                               formula_js(tree))
    return 'AFSimple_Calculate("%s", new Array (%s));' % (
        calc["op"], ", ".join(_js_str(f) for f in calc["fields"]))


def calc_inputs(calc):
    """The field names a calculation reads (custom ones: none we know of)."""
    if not calc or "custom" in calc:
        return []
    if "formula" in calc:
        try:
            return formula_fields(parse_formula(calc["formula"]))
        except FormulaError:
            return []
    return list(calc["fields"])


# Acrobat's AFDate_Format(n) list of formats
_DATE_FORMATS = ["m/d", "m/d/yy", "mm/dd/yy", "mm/yy", "d-mmm", "d-mmm-yy", "dd-mmm-yy",
                 "yy-mm-dd", "mmm-yy", "mmmm-yy", "mmm d, yyyy", "mmmm d, yyyy"]
DATE_PRESETS = ["mm/dd/yyyy", "m/d/yyyy", "mm/dd/yy", "dd/mm/yyyy", "yyyy-mm-dd",
                "d-mmm-yyyy", "mmmm d, yyyy", "dd.mm.yyyy"]


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def read_format(js_f, js_k=None):
    """A format script (with its keystroke twin) as one of
    {"kind": "number", "decimals", "sep", "neg", "currency", "prepend"},
    {"kind": "percent", "decimals", "sep"}, {"kind": "date", "pattern"},
    {"kind": "special", "which"} (0 ZIP, 1 ZIP+4, 2 phone, 3 SSN), {"custom": js}; or None."""
    if not js_f or not js_f.strip():
        if js_k and js_k.strip():
            return {"custom": js_f or "", "keystroke": js_k}
        return None
    call = parse_call(js_f)
    if call:
        name, a = call
        if name == "AFNumber_Format" and len(a) >= 4:
            return {"kind": "number", "decimals": max(0, min(10, _int(a[0], 2))),
                    "sep": _int(a[1]) if _int(a[1]) in range(5) else 0,
                    "neg": _int(a[2]) if _int(a[2]) in range(4) else 0,
                    "currency": str(a[4]) if len(a) > 4 and isinstance(a[4], str) else "",
                    "prepend": bool(a[5]) if len(a) > 5 else True}
        if name == "AFPercent_Format" and len(a) >= 1:
            return {"kind": "percent", "decimals": max(0, min(10, _int(a[0], 2))),
                    "sep": _int(a[1]) if len(a) > 1 and _int(a[1]) in range(5) else 0}
        if name in ("AFDate_FormatEx", "AFDate_Format") and len(a) == 1:
            pat = a[0] if isinstance(a[0], str) else (
                _DATE_FORMATS[_int(a[0])] if 0 <= _int(a[0], -1) < len(_DATE_FORMATS) else None)
            if pat and date_pattern_ok(pat):
                return {"kind": "date", "pattern": pat}
        if name == "AFSpecial_Format" and len(a) == 1 and _int(a[0], -1) in range(4):
            return {"kind": "special", "which": _int(a[0])}
    out = {"custom": js_f}
    if js_k:
        out["keystroke"] = js_k
    return out


def format_js(fmt):
    """(format script, keystroke script) for a format, as Acrobat writes them."""
    if not fmt:
        return None, None
    if "custom" in fmt:
        return fmt["custom"] or None, fmt.get("keystroke")
    k = fmt["kind"]
    if k == "number":
        args = '%d, %d, %d, 0, %s, %s' % (fmt.get("decimals", 2), fmt.get("sep", 0),
                                          fmt.get("neg", 0), _js_str(fmt.get("currency", "")),
                                          "true" if fmt.get("prepend", True) else "false")
        return "AFNumber_Format(%s);" % args, "AFNumber_Keystroke(%s);" % args
    if k == "percent":
        args = "%d, %d" % (fmt.get("decimals", 2), fmt.get("sep", 0))
        return "AFPercent_Format(%s);" % args, "AFPercent_Keystroke(%s);" % args
    if k == "date":
        p = _js_str(fmt["pattern"])
        return "AFDate_FormatEx(%s);" % p, "AFDate_KeystrokeEx(%s);" % p
    if k == "special":
        return ("AFSpecial_Format(%d);" % fmt["which"],
                "AFSpecial_Keystroke(%d);" % fmt["which"])
    return None, None


def read_validate(js):
    """A validate script as {"min", "max"} (either may be None) | {"custom"} | None."""
    if not js or not js.strip():
        return None
    call = parse_call(js)
    if call and call[0] == "AFRange_Validate" and len(call[1]) == 4:
        a = call[1]
        try:
            lo = float(a[1]) if a[0] is True else None
            hi = float(a[3]) if a[2] is True else None
        except (TypeError, ValueError):
            return {"custom": js}
        if lo is not None or hi is not None:
            return {"min": lo, "max": hi}
    return {"custom": js}


def validate_js(rng):
    if not rng:
        return None
    if "custom" in rng:
        return rng["custom"]
    lo, hi = rng.get("min"), rng.get("max")
    if lo is None and hi is None:
        return None
    return "AFRange_Validate(%s, %s, %s, %s);" % (
        "true" if lo is not None else "false", _num(lo or 0),
        "true" if hi is not None else "false", _num(hi or 0))


# ---- numbers ---------------------------------------------------------------------------
def number_text(x):
    """A number as a field value: no float noise (0.1 + 0.2 is 0.3), no '.0' on a whole one."""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return ""
    s = "%.12g" % round(float(x), 10)
    if "e" in s:
        s = ("%.10f" % x).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def to_number(value):
    """A field value as a number the way Acrobat's AFMakeNumber reads it (None: not one).
    Accepts a decimal comma, thousands separators, a currency sign, a % sign (25% is 0.25)
    and (1,234) for a negative."""
    if value is None or value is False:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1].strip()
    pct = s.endswith("%")
    s = s.rstrip("%").strip()
    s = re.sub(r"^[^\d\-+.,]+|[^\d.,]+$", "", s)          # a currency sign before or after
    if s.startswith("-"):
        neg, s = not neg, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    s = s.replace(" ", "").replace("'", "").replace("\u00a0", "")
    if not s or not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        # the last one is the decimal point: 1,234.56 or 1.234,56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        # 1,234 / 1,234,567: thousands; 12,5 / 0,25: a decimal comma
        if len(parts) > 2 or (len(parts[1]) == 3 and parts[0] not in ("", "0")):
            s = s.replace(",", "") if all(len(p) == 3 for p in parts[1:]) else None
        else:
            s = s.replace(",", ".")
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts) if all(len(p) == 3 for p in parts[1:]) else None
    if s is None:
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    if pct:
        x /= 100.0
    return -x if neg else x


_SEPS = {0: (",", "."), 1: ("", "."), 2: (".", ","), 3: ("", ","), 4: ("'", ".")}


def _group(x, decimals, sep):
    thousands, point = _SEPS.get(sep, _SEPS[0])
    s = "%.*f" % (decimals, abs(x))
    whole, _, frac = s.partition(".")
    if thousands:
        whole = "{:,}".format(int(whole)).replace(",", thousands)
    return whole + (point + frac if frac else "")


def format_value(fmt, raw):
    """What a field shows for its value raw, with its format (raw itself when there's none,
    it isn't a number where one is expected, or the format is a custom script)."""
    if not fmt or "custom" in fmt or raw is None or raw == "":
        return raw
    k = fmt.get("kind")
    if k in ("number", "percent"):
        x = to_number(raw)
        if x is None:
            return raw
        if k == "percent":
            body = _group(x * 100.0, fmt.get("decimals", 2), fmt.get("sep", 0)) + "%"
            return "-" + body if round(x * 100.0, fmt.get("decimals", 2)) < 0 else body
        dec = fmt.get("decimals", 2)
        x = round(x, dec)
        body = _group(x, dec, fmt.get("sep", 0))
        cur = fmt.get("currency", "")
        if cur:
            body = cur + body if fmt.get("prepend", True) else body + cur
        if x < 0:
            # (1 and 3 are Acrobat's red styles: shown with a minus / in parentheses here)
            return "(" + body + ")" if fmt.get("neg", 0) in (2, 3) else "-" + body
        return body
    if k == "date":
        d = parse_date(raw, fmt["pattern"])
        return format_date(d, fmt["pattern"]) if d else raw
    if k == "special":
        digits = re.sub(r"\D", "", str(raw))
        w = fmt.get("which", 0)
        if w == 0 and len(digits) == 5:
            return digits
        if w == 1 and len(digits) == 9:
            return digits[:5] + "-" + digits[5:]
        if w == 2 and len(digits) == 10:
            return "(%s) %s-%s" % (digits[:3], digits[3:6], digits[6:])
        if w == 2 and len(digits) == 7:
            return digits[:3] + "-" + digits[3:]
        if w == 3 and len(digits) == 9:
            return "%s-%s-%s" % (digits[:3], digits[3:5], digits[5:])
        return raw
    return raw


# ---- dates -----------------------------------------------------------------------------
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
_MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
              "septiembre", "octubre", "noviembre", "diciembre"]
_DATE_TOKEN = re.compile(r"yyyy|yy|mmmm|mmm|mm|m|dddd|ddd|dd|d")


def date_pattern_ok(pattern):
    """A date format made of day, month and year parts (time parts aren't handled here)."""
    if not pattern or re.search(r"[HhMstT]", pattern):
        return False
    return bool(_DATE_TOKEN.search(pattern))


def format_date(d, pattern):
    def one(m):
        t = m.group(0)
        return {"yyyy": "%04d" % d.year, "yy": "%02d" % (d.year % 100),
                "mmmm": MONTHS[d.month - 1], "mmm": MONTHS[d.month - 1][:3],
                "mm": "%02d" % d.month, "m": str(d.month),
                "dddd": d.strftime("%A"), "ddd": d.strftime("%a"),
                "dd": "%02d" % d.day, "d": str(d.day)}[t]
    return _DATE_TOKEN.sub(one, pattern)


def _month_of(word):
    w = word.lower().rstrip(".")
    if len(w) < 3:
        return None
    for names in (MONTHS, _MONTHS_ES):
        for k, name in enumerate(names):
            if name.lower().startswith(w) or w == name.lower()[:3]:
                return k + 1
    return None


def parse_date(text, pattern):
    """The date typed in text, read in the order of the pattern's parts (11/6/26 with
    mm/dd/yyyy is November 6, 2026); a 4-digit first number is year-month-day. None if it
    isn't a date that exists."""
    if not text:
        return None
    s = str(text).strip()
    nums = re.findall(r"\d+", s)
    words = [w for w in re.findall(r"[^\W\d_]+", s)]
    month_word = next((_month_of(w) for w in words if _month_of(w)), None)
    order = [t[0] for t in _DATE_TOKEN.findall(pattern) if t[0] in "dmy"]
    seen = []
    for o in order:
        if o not in seen:
            seen.append(o)
    order = seen
    y = m = d = None
    try:
        if nums and len(nums[0]) == 4 and len(nums) >= 3 and month_word is None:
            y, m, d = int(nums[0]), int(nums[1]), int(nums[2])
        elif month_word is not None:
            m = month_word
            rest = [o for o in order if o != "m"]
            vals = list(nums)
            if len(vals) == 1 and "y" in rest and "d" in rest:
                return None
            for o in rest:
                if not vals:
                    break
                v = int(vals.pop(0))
                if o == "y":
                    y = v
                else:
                    d = v
            if len(nums) == 2 and d is not None and y is not None and d > 31 >= y:
                d, y = y, d
        else:
            if len(nums) == 1 and len(nums[0]) in (6, 8):
                n = nums[0]
                cut = []
                for o in order:
                    k = (4 if len(n) == 8 else 2) if o == "y" else 2
                    cut.append(n[:k])
                    n = n[k:]
                nums = cut
            if len(nums) < len(order):
                return None
            for o, v in zip(order, nums):
                if o == "y":
                    y = int(v)
                elif o == "m":
                    m = int(v)
                else:
                    d = int(v)
        if d is None and "d" not in order:
            d = 1
        if y is None and "y" not in order:
            y = date.today().year
        if None in (y, m, d):
            return None
        if y < 100:
            y += 2000 if y < 50 else 1900
        return date(y, m, d)
    except (ValueError, TypeError):
        return None


# ---- checking what's typed -------------------------------------------------------------
SPECIAL_DIGITS = {0: (5,), 1: (9,), 2: (7, 10), 3: (9,)}


def keystroke_pattern(fmt):
    """A regular expression for the characters a field with this format takes while typing
    (None: anything)."""
    if not fmt or "custom" in fmt:
        return None
    k = fmt.get("kind")
    if k in ("number", "percent"):
        return r"[\d\s.,'()+\-%" + re.escape(fmt.get("currency", "") or "$") + r"]*"
    if k == "special":
        return r"[\d\s()+\-.]*"
    return None


def check_input(text, fmt=None, rng=None):
    """(ok, value to store, message) for what someone typed into a field with this format
    and range. The value stored is the plain one (1234.5, 5551234567, a date in the field's
    format); the field shows it formatted (format_value)."""
    from .i18n import tr
    s = (text or "").strip() if fmt and "custom" not in fmt else (text or "")
    if s == "":
        return True, "", ""
    k = fmt.get("kind") if fmt and "custom" not in fmt else None
    value = s if k else text
    num = None
    if k in ("number", "percent"):
        num = to_number(s)
        if num is None:
            return False, None, tr("Type a number.")
        value = number_text(num)
    elif k == "date":
        d = parse_date(s, fmt["pattern"])
        if d is None:
            return False, None, tr("Type a date that exists, as {format}.").format(
                format=fmt["pattern"])
        value = format_date(d, fmt["pattern"])
    elif k == "special":
        digits = re.sub(r"\D", "", s)
        w = fmt.get("which", 0)
        if len(digits) not in SPECIAL_DIGITS[w] or re.search(r"[^\d\s()+\-.]", s):
            return False, None, [tr("Type a 5-digit ZIP code."),
                                 tr("Type a ZIP+4 code (9 digits)."),
                                 tr("Type a phone number (7 or 10 digits)."),
                                 tr("Type a Social Security number (9 digits).")][w]
        value = digits
    if rng and "custom" not in rng and (rng.get("min") is not None or
                                        rng.get("max") is not None):
        if num is None:
            num = to_number(s)
        if num is None:
            return False, None, tr("Type a number.")
        lo, hi = rng.get("min"), rng.get("max")
        if (lo is not None and num < lo) or (hi is not None and num > hi):
            if lo is not None and hi is not None:
                msg = tr("The value must be between {min} and {max}.")
            elif lo is not None:
                msg = tr("The value must be at least {min}.")
            else:
                msg = tr("The value must be at most {max}.")
            return False, None, msg.format(min=number_text(lo), max=number_text(hi))
        if not k:
            value = s
    return True, value, ""


# ---- the form's fields, read straight from the PDF --------------------------------------
class Field:
    __slots__ = ("name", "fx", "ft", "ff", "widgets", "calc", "fmt", "rng", "tu", "kids")

    def __init__(self, name, fx):
        self.name, self.fx = name, fx
        self.ft, self.ff, self.widgets = None, 0, []
        self.calc = self.fmt = self.rng = None
        self.tu = ""
        self.kids = False


class Form:
    """A form's fields by full name, their pages, calculations, formats and checks, and the
    calculation order (/AcroForm /CO). Read once and kept until the document changes other
    than by a value being filled in (DocumentView._smart_form)."""

    def __init__(self):
        self.fields = {}            # full name -> Field
        self.by_widget = {}         # widget xref -> full name
        self.widget_page = {}       # widget xref -> page index
        self.groups = {}            # a parent's full name -> its terminal fields' names
        self.co = []                # full names in /CO order

    def names(self):
        return list(self.fields)

    def calculated(self):
        return [n for n, f in self.fields.items() if f.calc and "custom" not in f.calc]

    def expand(self, name):
        """The terminal fields a name stands for (a parent stands for all its fields)."""
        if name in self.fields:
            return [name]
        return list(self.groups.get(name, []))


def _m():
    import pymupdf
    return pymupdf.mupdf, pymupdf


def _text(m, obj):
    """A PDF string or stream object's text."""
    if m.pdf_is_string(obj):
        return m.pdf_to_text_string(obj)
    if m.pdf_is_stream(obj):
        buf = m.pdf_load_stream(obj)
        try:
            data = bytes(m.fz_buffer_extract_copy(buf))
        except Exception:
            data = b""
        for enc in ("utf-8", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                pass
    return ""


def _js_of(m, field, key):
    aa = m.pdf_dict_gets(field, "AA")
    if not m.pdf_is_dict(aa):
        return ""
    act = m.pdf_dict_gets(aa, key)
    if not m.pdf_is_dict(act):
        return ""
    if m.pdf_to_name(m.pdf_dict_gets(act, "S")) != "JavaScript":
        return ""
    return _text(m, m.pdf_dict_gets(act, "JS"))


def read_form(doc):
    """The document's Form (empty when it has none)."""
    m, pymupdf = _m()
    form = Form()
    pdf = pymupdf._as_pdf_document(doc)
    acro = m.pdf_dict_getp(m.pdf_trailer(pdf), "Root/AcroForm")
    if not m.pdf_is_dict(acro):
        return form
    page_of = {}
    for i in range(doc.page_count):
        try:
            annots = m.pdf_dict_gets(m.pdf_lookup_page_obj(pdf, i), "Annots")
        except Exception:
            continue
        if m.pdf_is_array(annots):
            for k in range(m.pdf_array_len(annots)):
                num = m.pdf_to_num(m.pdf_array_get(annots, k))
                if num:
                    page_of.setdefault(num, i)
    seen = set()

    def walk(arr, prefix, inherited):
        for k in range(m.pdf_array_len(arr)):
            node = m.pdf_array_get(arr, k)
            num = m.pdf_to_num(node)
            if not num or num in seen or not m.pdf_is_dict(node):
                continue
            seen.add(num)
            t = m.pdf_dict_gets(node, "T")
            part = m.pdf_to_text_string(t) if m.pdf_is_string(t) else None
            name = prefix if part is None else (prefix + "." + part if prefix else part)
            inh = dict(inherited)
            ft = m.pdf_dict_gets(node, "FT")
            if m.pdf_is_name(ft):
                inh["ft"] = m.pdf_to_name(ft)
            ff = m.pdf_dict_gets(node, "Ff")
            if m.pdf_is_int(ff) or m.pdf_is_real(ff):
                inh["ff"] = m.pdf_to_int(ff)
            kids = m.pdf_dict_gets(node, "Kids")
            named_kids = []
            if m.pdf_is_array(kids):
                for j in range(m.pdf_array_len(kids)):
                    kid = m.pdf_array_get(kids, j)
                    if m.pdf_is_string(m.pdf_dict_gets(kid, "T")):
                        named_kids.append(kid)
            if part is None and prefix in form.fields:
                # a widget of the field above (no name of its own)
                f = form.fields[prefix]
                f.widgets.append(num)
                continue
            if named_kids:
                walk(kids, name, inh)
                # (a parent's own widgets, if any, are ignored: a parent is a group)
                form.groups[name] = [n for n in form.fields if n.startswith(name + ".")]
                continue
            if not name:
                continue
            f = form.fields.get(name)
            if f is None:
                f = form.fields[name] = Field(name, num)
                f.ft, f.ff = inh.get("ft"), inh.get("ff", 0)
                tu = m.pdf_dict_gets(node, "TU")
                f.tu = m.pdf_to_text_string(tu) if m.pdf_is_string(tu) else ""
                # field-level actions; some makers put them on the (only) widget
                src = node
                if not m.pdf_is_dict(m.pdf_dict_gets(node, "AA")) and m.pdf_is_array(kids) \
                        and m.pdf_array_len(kids):
                    src = m.pdf_array_get(kids, 0)
                f.calc = read_calc(_js_of(m, src, "C"))
                f.fmt = read_format(_js_of(m, src, "F"), _js_of(m, src, "K"))
                f.rng = read_validate(_js_of(m, src, "V"))
            if m.pdf_name_eq(m.pdf_dict_gets(node, "Subtype"), m.pdf_new_name("Widget")):
                f.widgets.append(num)
            if m.pdf_is_array(kids):
                f.kids = True
                for j in range(m.pdf_array_len(kids)):
                    kn = m.pdf_to_num(m.pdf_array_get(kids, j))
                    if kn and kn not in seen:
                        seen.add(kn)
                        f.widgets.append(kn)

    fields = m.pdf_dict_gets(acro, "Fields")
    if m.pdf_is_array(fields):
        walk(fields, "", {})
    for name, f in form.fields.items():
        for w in f.widgets:
            form.by_widget[w] = name
            if w in page_of:
                form.widget_page[w] = page_of[w]
    co = m.pdf_dict_gets(acro, "CO")
    if m.pdf_is_array(co):
        by_fx = {f.fx: n for n, f in form.fields.items()}
        for k in range(m.pdf_array_len(co)):
            n = by_fx.get(m.pdf_to_num(m.pdf_array_get(co, k)))
            if n and n not in form.co:
                form.co.append(n)
    return form


def has_calculations(doc):
    """Cheap: does the form list calculated fields (/AcroForm /CO)?"""
    m, pymupdf = _m()
    try:
        co = m.pdf_dict_getp(m.pdf_trailer(pymupdf._as_pdf_document(doc)), "Root/AcroForm/CO")
        return m.pdf_is_array(co) and m.pdf_array_len(co) > 0
    except Exception:
        return False


def field_value(doc, fx):
    """A field's value (/V, inherited from its parents) as text: a name for a checkbox."""
    m, pymupdf = _m()
    obj = m.pdf_new_indirect(pymupdf._as_pdf_document(doc), fx, 0)
    for _ in range(32):
        v = m.pdf_dict_gets(obj, "V")
        if not m.pdf_is_null(v):
            if m.pdf_is_name(v):
                return m.pdf_to_name(v)
            if m.pdf_is_string(v) or m.pdf_is_stream(v):
                return _text(m, v)
            if m.pdf_is_array(v) and m.pdf_array_len(v):
                return _text(m, m.pdf_array_get(v, 0))
            if m.pdf_is_number(v):
                return number_text(m.pdf_to_real(v))
            return ""
        obj = m.pdf_dict_gets(obj, "Parent")
        if not m.pdf_is_dict(obj):
            break
    return ""


def calc_order(form):
    """The calculated fields in an order where each comes after the fields it reads:
    /CO's order wherever that already works, a field moved after its inputs where not.
    Returns (order, looped): fields reading themselves in a loop are left out (looped)."""
    calc = form.calculated()
    rank = {n: k for k, n in enumerate(form.co)}
    calc.sort(key=lambda n: rank.get(n, len(rank)))
    deps = {}
    for n in calc:
        ins = set()
        for name in calc_inputs(form.fields[n].calc):
            ins.update(form.expand(name))
        deps[n] = {d for d in ins if d in deps or d in calc}
    order, done, looped = [], set(), []
    state = {}

    def visit(n, path):
        if n in done:
            return True
        if state.get(n) == "busy":
            return False
        state[n] = "busy"
        ok = True
        for d in sorted(deps.get(n, ()), key=lambda x: rank.get(x, len(rank))):
            if d != n and d in deps and not visit(d, path + [n]):
                ok = False
        if n in deps.get(n, ()):
            ok = False
        state[n] = "done"
        if ok:
            done.add(n)
            order.append(n)
        else:
            looped.append(n)
        return ok
    for n in calc:
        visit(n, [])
    return order, looped


def calculate(calc, number_of):
    """A calculation's result (a float, or None: no result, e.g. a division by zero).
    number_of(name) gives a field's number (0 for an empty or non-numeric one)."""
    if not calc or "custom" in calc:
        return None
    try:
        if "formula" in calc:
            x = eval_formula(parse_formula(calc["formula"]), number_of)
        else:
            vals = [number_of(n) for n in calc["fields"]]
            vals = [v for vs in vals for v in (vs if isinstance(vs, list) else [vs])]
            if not vals:
                return None
            op = calc["op"]
            if op == "SUM":
                x = math.fsum(vals)
            elif op == "PRD":
                x = 1.0
                for v in vals:
                    x *= v
            elif op == "AVG":
                x = math.fsum(vals) / len(vals)
            elif op == "MIN":
                x = min(vals)
            else:
                x = max(vals)
    except (ZeroDivisionError, OverflowError, FormulaError):
        return None
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def recalculate(doc, form, changed=None):
    """{field name: new value} for every calculated field whose value changes, in order,
    after the values in changed ({name: value}) were filled in."""
    values = dict(changed or {})
    out = {}
    order, _looped = calc_order(form)

    def value(n):
        if n in values:
            return values[n]
        f = form.fields.get(n)
        values[n] = field_value(doc, f.fx) if f is not None else ""
        return values[n]

    def number(n):
        names = form.expand(n)
        if not names:
            return 0.0
        nums = []
        for nn in names:
            f = form.fields[nn]
            v = value(nn)
            if f.ft == "Btn" and v in ("Off", ""):
                x = 0.0
            else:
                x = to_number(v)
            nums.append(x if x is not None else 0.0)
        return nums[0] if len(nums) == 1 and n in form.fields else nums

    def number_of_formula(n):
        x = number(n)
        return math.fsum(x) if isinstance(x, list) else x

    for n in order:
        f = form.fields[n]
        if "formula" in f.calc:
            x = calculate(f.calc, number_of_formula)
        else:
            x = calculate(f.calc, number)
        new = number_text(x) if x is not None else ""
        if new != value(n):
            values[n] = new
            out[n] = new
    return out


# ---- writing a field's properties --------------------------------------------------------
def _js_action(m, pdf, js):
    act = m.pdf_new_dict(pdf, 2)
    m.pdf_dict_puts(act, "S", m.pdf_new_name("JavaScript"))
    m.pdf_dict_puts(act, "JS", m.pdf_new_text_string(js))
    return act


def write_actions(doc, fx, widgets, calc, fmt, rng):
    """Put the field's keystroke, format, validate and calculate actions in its /AA
    (other actions in it stay); the same keys are taken off its widgets so they can't hide
    the field's own."""
    m, pymupdf = _m()
    pdf = pymupdf._as_pdf_document(doc)
    field = m.pdf_new_indirect(pdf, fx, 0)
    f_js, k_js = format_js(fmt)
    want = {"K": k_js, "F": f_js, "V": validate_js(rng), "C": calc_js(calc)}
    aa = m.pdf_dict_gets(field, "AA")
    if not m.pdf_is_dict(aa):
        if not any(want.values()):
            return
        aa = m.pdf_dict_puts_dict(field, "AA", 4)
    for key, js in want.items():
        if js:
            if _js_of(m, field, key) != js:
                m.pdf_dict_puts(aa, key, _js_action(m, pdf, js))
        elif not m.pdf_is_null(m.pdf_dict_gets(aa, key)):
            m.pdf_dict_dels(aa, key)
    if not m.pdf_dict_len(aa):
        m.pdf_dict_dels(field, "AA")
    for w in widgets:
        if w == fx:
            continue
        wobj = m.pdf_new_indirect(pdf, w, 0)
        waa = m.pdf_dict_gets(wobj, "AA")
        if m.pdf_is_dict(waa):
            for key in want:
                if not m.pdf_is_null(m.pdf_dict_gets(waa, key)):
                    m.pdf_dict_dels(waa, key)
            if not m.pdf_dict_len(waa):
                m.pdf_dict_dels(wobj, "AA")


def write_co(doc, fxs):
    """Set /AcroForm /CO to these fields (in this order); remove it when there are none."""
    m, pymupdf = _m()
    pdf = pymupdf._as_pdf_document(doc)
    acro = m.pdf_dict_getp(m.pdf_trailer(pdf), "Root/AcroForm")
    if not m.pdf_is_dict(acro):
        return
    old = m.pdf_dict_gets(acro, "CO")
    have = [m.pdf_to_num(m.pdf_array_get(old, k)) for k in range(m.pdf_array_len(old))] \
        if m.pdf_is_array(old) else None
    if have == list(fxs) or (have is None and not fxs):
        return
    if not fxs:
        m.pdf_dict_dels(acro, "CO")
        return
    arr = m.pdf_new_array(pdf, len(fxs))
    for x in fxs:
        m.pdf_array_push(arr, m.pdf_new_indirect(pdf, x, 0))
    m.pdf_dict_puts(acro, "CO", arr)


def set_flags(doc, fx, widgets, required=None, readonly=None):
    """Turn a field's Required (bit 2) / Read-only (bit 1) flag on or off (None: as is), on the
    field and on any widget that carries its own copy of the flags."""
    for x in [fx] + [w for w in widgets if w != fx]:
        typ, val = doc.xref_get_key(x, "Ff")
        if x != fx and typ == "null":
            continue
        try:
            ff = int(float(val)) if typ in ("int", "float") else 0
        except ValueError:
            ff = 0
        new = ff
        if required is not None:
            new = new | 2 if required else new & ~2
        if readonly is not None:
            new = new | 1 if readonly else new & ~1
        if new != ff or (typ == "null" and x == fx and new):
            doc.xref_set_key(x, "Ff", str(new))


def set_tooltip(doc, fx, text):
    import pymupdf
    if text:
        doc.xref_set_key(fx, "TU", pymupdf.get_pdf_str(text))
    elif doc.xref_get_key(fx, "TU")[0] != "null":
        doc.xref_set_key(fx, "TU", "null")


def field_scripts(doc, fx, wx=None):
    """(calc, fmt, rng) of one field, read from its dictionary (or its widget wx when the
    field has no actions of its own), without reading the whole form."""
    m, pymupdf = _m()
    pdf = pymupdf._as_pdf_document(doc)
    src = m.pdf_new_indirect(pdf, fx, 0)
    if not m.pdf_is_dict(m.pdf_dict_gets(src, "AA")) and wx and wx != fx:
        src = m.pdf_new_indirect(pdf, wx, 0)
    if not m.pdf_is_dict(m.pdf_dict_gets(src, "AA")):
        return None, None, None
    return (read_calc(_js_of(m, src, "C")), read_format(_js_of(m, src, "F"), _js_of(m, src, "K")),
            read_validate(_js_of(m, src, "V")))


def co_order(form, old_co=None):
    """The /CO list for a form: the calculated fields KanzonasPDF works out, each after the
    ones it reads, in the places /CO had calculated fields; custom ones keep their place."""
    calc = [n for n, f in form.fields.items() if f.calc]
    seq = [n for n in (old_co if old_co is not None else form.co) if n in calc]
    seq += [n for n in calc if n not in seq]
    order, looped = calc_order(form)
    mine = iter(order + looped)
    return [next(mine) if "custom" not in form.fields[n].calc else n for n in seq]

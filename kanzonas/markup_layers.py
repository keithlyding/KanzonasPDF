"""Markups on layers (1.12, the owner, 11 Nov, from the Bluebeam comparison; issue #82 asked
for it too): a markup is put on a layer with the PDF's own optional content (its /OC, an
optional content group, the same kind of layer a CAD plot's drawing has), so every PDF program
that shows layers shows and hides it with its layer.

The Layers panel shows and hides layers (as before); new markups go on the layer chosen there
("New markups go on"), a markup's right-click menu moves it to another layer (or none), and the
Markups list shows and filters by layer. A markup on a hidden layer isn't drawn (MuPDF leaves
it out) nor picked."""

from .i18n import tr


def layers(doc):
    """[(xref, name, on)] of the document's layers, by name."""
    try:
        found = doc.get_ocgs() or {}
    except Exception:
        return []
    return sorted(((x, o.get("name") or tr("(unnamed)"), bool(o.get("on", True)))
                   for x, o in found.items()), key=lambda t: (t[1].lower(), t[0]))


def names(doc):
    return {x: name for x, name, _on in layers(doc)}


def hidden(doc):
    """The xrefs of the layers turned off now."""
    return {x for x, _name, on in layers(doc) if not on}


def layer_of(doc, xref):
    """The layer (OCG xref) markup xref is on, or None (also for a layer membership dictionary,
    /OCMD: shown here as no layer)."""
    try:
        kind, val = doc.xref_get_key(xref, "OC")
        if kind != "xref":
            return None
        oc = int(val.split()[0])
        return oc if doc.xref_get_key(oc, "Type") == ("name", "/OCG") else None
    except Exception:
        return None


def put(doc, xrefs, layer):
    """Put the markups on layer (an OCG xref), or on none (None)."""
    for x in xrefs:
        doc.xref_set_key(x, "OC", f"{layer} 0 R" if layer else "null")


def new_layer(doc, name):
    """A new layer, shown. MuPDF lists a document's layers once (the Layers panel's list):
    they're read again, each staying shown or hidden as it was. Returns its xref."""
    from . import undo_journal
    hidden_now = hidden(doc)
    x = doc.add_ocg(name, on=True)
    undo_journal.reload_layers(doc)
    if hidden_now:
        for number, oc in ui_layers(doc):
            if oc in hidden_now:
                doc.set_layer_ui_config(number, 2)
    return x


def ui_layers(doc):
    """[(number in layer_ui_configs, OCG xref)] for the panel's layers: its check boxes follow
    the order of the layers in /OCProperties /D /Order. Empty when they can't be paired."""
    try:
        configs = [c for c in doc.layer_ui_configs() if c.get("type") == "checkbox"]
        kind, order = doc.xref_get_key(doc.pdf_catalog(), "OCProperties/D/Order")
    except Exception:
        return []
    if kind != "array":
        return []
    import re
    refs = [int(n) for n in re.findall(r"(\d+) 0 R", order)]
    ocgs = set(doc.get_ocgs() or {})
    refs = [r for r in refs if r in ocgs]
    if len(refs) != len(configs):
        return []
    return [(c["number"], r) for c, r in zip(configs, refs)]

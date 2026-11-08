"""Every ribbon tab fits a 1366 x 768 screen, in English and in Spanish, without scrolling
sideways (the owner: "Let's fit Spanish stuff on a 1366 pixel screen"); the layout is the same
in both languages; and no command has left the tab it was on.

Measured at Windows' own interface font, Segoe UI 9 pt at 100% scaling. Where Segoe UI isn't
installed, a font of the same width stands in: Liberation Sans or Arimo (made with Arial's
widths) or Arial itself; Arial's average letter at 9 pt is 7 pixels, as Segoe UI's is (the
"dialog units" Windows lays dialogs out with), so a tab measures within a few pixels of what
Windows shows. The default font of a test machine (DejaVu Sans, Inter...) is wider and would
measure tabs that fit as too wide.

Each language runs in its own process (the language and the application's font are set once
per process, before any window), with settings in a fresh folder.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_ribbon_fits
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCREEN = 1366
FRAME = 16                  # a window's left and right borders on Windows 10 and 11
LIMIT = SCREEN - FRAME      # the widest a tab may be: a full-width window that isn't maximized
FONTS = ("Segoe UI", "Liberation Sans", "Arimo", "Arial")

# What each tab had on it before the tabs were made to fit (1.9), and each tab added since, on
# a button, under a button's arrow or under a group's arrow: none of it may leave its tab.
ON_TABS = {
    "Home": "a_actual a_cad_mouse a_fit_page a_fit_width a_mouse_hand a_mouse_standard a_zoom_in "
            "a_zoom_out t:addtext t:attach t:capture t:comment t:editobjects t:edittext "
            "t:erasecontent t:highlight t:image t:initials t:link t:note t:signature t:stamp "
            "t:strikeout t:textbox t:underline",
    "Markup": "a_chest a_props t:arc t:arrow t:attach t:callout t:circle t:cloud t:comment "
              "t:curve t:ellipse t:eraser t:highlight t:ink t:legend t:line t:mask t:note "
              "t:polygon t:polyline t:rect t:stamp t:strikeout t:textbox t:underline",
    "Measure": "a_grid a_grid_settings a_measure_summary a_scale_bar a_sheet_scales a_snap_grid "
               "a_snap_objects a_snap_page t:m_angle t:m_area t:m_calibrate t:m_count t:m_dim "
               "t:m_length t:m_perimeter t:m_poly t:m_radius t:m_volume",
    "Arrange": "A:al_bottom A:al_hcenter A:al_left A:al_right A:al_top A:al_vmiddle A:dist_h "
               "A:dist_v A:z_back A:z_backward A:z_forward A:z_front a_grid a_grid_settings "
               "a_lock a_snap_grid a_snap_objects a_snap_page a_unlock_all",
    "Review": "a_cards a_delete_markups a_flatten_markups a_markups a_next_markup a_prev_markup "
              "a_show_markups t:comment t:note",
    "Protect": "a_apply_placeholders a_apply_redact a_apply_sel_redact a_clear_sigs a_digisign "
               "a_multi_sign a_remove_security a_sanitize a_search_redact a_security "
               "a_sig_details a_timestamp a_unlock t:date t:initials t:placeholder t:redact "
               "t:signature",
    "Forms": "a_hl_fields t:f_check t:f_combo t:f_initials t:f_radio t:f_sign t:f_text",
    "Pages": "a_attachments a_background a_bookmarks a_combine a_compare a_compress a_del_page "
             "a_extract a_flatten a_from_images a_header a_insert_blank a_insert_pdf "
             "a_move_down a_move_up a_new a_ocr a_replace_pages a_rot_l a_rot_r a_scan "
             "a_sheet_links a_uncrop a_watermark t:crop",
    "Print": "a_fix_hairlines a_page_boxes a_print a_print_check a_show_boxes a_uncrop t:crop",
    "View": "a_chest a_collapse a_free_pan a_grid a_grid_settings a_group_names a_hl_fields "
            "a_manual a_markups a_menu_bar a_night a_palette a_props a_ribbon a_shortcuts "
            "a_show_markups a_sidebar a_snap_grid a_snap_objects a_snap_page a_split",
    # (1.10: a tab of its own)
    "Reading": "L:continuous L:single L:two L:two_continuous a_autoscroll a_cover "
               "a_full_screen a_present a_read_doc a_read_from a_read_page a_read_pause "
               "a_read_stop a_reflow",
    "CAD": "A:al_bottom A:al_hcenter A:al_left A:al_right A:al_top A:al_vmiddle A:dist_h "
           "A:dist_v A:z_back A:z_backward A:z_forward A:z_front a_snap_grid a_snap_objects "
           "a_snap_page c:align c:array c:copy c:delete c:mirror c:move c:rotate c:scale "
           "c:trim t:addtext t:arc t:arrow t:callout t:circle t:cloud t:curve t:editobjects "
           "t:edittext t:erasecontent t:image t:ink t:legend t:line t:m_angle t:m_area "
           "t:m_calibrate t:m_count t:m_dim t:m_length t:m_perimeter t:m_poly t:m_radius "
           "t:m_volume t:mask t:polygon t:polyline t:rect t:select t:stamp t:textbox",
}

# Builds the main window in one language with the stand-in font, shows it as wide as the
# limit and reports each tab: its width, whether it scrolls, its groups (the commands on each
# button, by name in the code, so both languages compare) and every command it reaches.
CHILD = r"""
import json, os, sys
sys.path.insert(0, os.environ["KZ_ROOT"])
from PySide6.QtCore import QSettings
for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
    QSettings.setPath(fmt, QSettings.UserScope, os.environ["KZ_SETTINGS"])
from PySide6.QtWidgets import QApplication, QToolButton, QComboBox, QFrame
from PySide6.QtGui import QAction, QFont, QFontDatabase, QFontInfo
app = QApplication([])
have = set(QFontDatabase.families())
font = next((f for f in json.loads(os.environ["KZ_FONTS"]) if f in have), None)
out = {"font": font}
if font is not None:
    app.setFont(QFont(font, 9))
    out["font_used"] = QFontInfo(app.font()).family()
    out["pixels"] = QFontInfo(app.font()).pixelSize()
    from kanzonas import i18n
    from kanzonas.main_window import MainWindow
    w = MainWindow()
    w.set_mouse_mode("cad")                     # (the CAD tab shows only in CAD mode)
    limit = int(os.environ["KZ_LIMIT"])
    w.resize(limit, 740)
    w.show()
    app.processEvents()
    names = {}
    for k, a in w.tool_actions.items():
        names[id(a)] = "t:" + k
    for k, a in w.arrange_actions.items():
        names.setdefault(id(a), "A:" + k)
    for k, a in w.cad_actions.items():
        names.setdefault(id(a), "c:" + k)
    for k, a in w.layout_actions.items():
        names.setdefault(id(a), "L:" + k)
    for k, v in vars(w).items():
        if isinstance(v, QAction):
            names.setdefault(id(v), k)
    name = lambda a: names.get(id(a), "?" + a.text())
    r = w.ribbon
    tabs = []
    for i in range(r.count()):
        r.setCurrentIndex(i)
        app.processEvents()
        strip = r.widget(i)
        page = strip.widget()
        groups, reach = [], set()
        lay = page.layout()
        for k in range(lay.count()):
            g = lay.itemAt(k).widget()
            if g is None or isinstance(g, QFrame):
                continue
            items = []
            for b in g.findChildren(QToolButton):
                acts = ([b.defaultAction()] if b.defaultAction() is not None else []) + \
                       (b.menu().actions() if b.menu() is not None else [])
                reach.update(name(a) for a in acts)
                items.append([type(b).__name__, b.toolButtonStyle().value] +
                             [name(a) for a in acts])
            items += [[type(c).__name__] for c in g.findChildren(QComboBox)]
            groups.append(items)
        tabs.append({"title": r.tabText(i), "width": page.sizeHint().width(),
                     "scrolls": strip.horizontalScrollBar().maximum() > 0,
                     "viewport": strip.viewport().width(),
                     "groups": groups, "reach": sorted(reach)})
    out.update(lang=i18n.language(), window=w.width(), tabs=tabs)
sys.stdout.write("RESULT " + json.dumps(out) + "\n")
sys.stdout.flush()
os._exit(0)
"""


def run_both():
    procs = {}
    for lang in ("en", "es"):
        env = dict(os.environ, KANZONAS_LANG=lang, QT_QPA_PLATFORM="offscreen", KZ_ROOT=ROOT,
                   KZ_LIMIT=str(LIMIT), KZ_FONTS=json.dumps(FONTS),
                   KZ_SETTINGS=tempfile.mkdtemp(prefix="kanzonas-test-ribbon-"))
        procs[lang] = subprocess.Popen([sys.executable, "-c", CHILD], env=env, cwd=ROOT,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out = {}
    for lang, p in procs.items():
        stdout, stderr = p.communicate(timeout=300)
        line = [ln for ln in stdout.splitlines() if ln.startswith("RESULT ")]
        if not line:
            raise AssertionError("the %s run failed:\n%s%s" % (lang, stdout, stderr))
        out[lang] = json.loads(line[-1][len("RESULT "):])
    return out


class RibbonFits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_both()
        if cls.result["en"]["font"] is None:
            raise unittest.SkipTest("none of %s is installed to measure with" % (FONTS,))

    def widths(self, lang):
        return ", ".join("%s %d" % (t["title"], t["width"]) for t in self.result[lang]["tabs"])

    def test_measured_with_a_font_as_wide_as_segoe_ui(self):
        for lang in ("en", "es"):
            r = self.result[lang]
            self.assertEqual(r["lang"], lang)
            self.assertEqual(r["font_used"], r["font"])
            self.assertEqual(r["pixels"], 12)           # 9 pt at 96 dots per inch (100%)

    def test_every_tab_fits_in_english_and_spanish(self):
        for lang in ("en", "es"):
            r = self.result[lang]
            self.assertLessEqual(r["window"], LIMIT)
            for t in r["tabs"]:
                self.assertLessEqual(t["width"], LIMIT, "%s, %s tab (font %s): %s" % (
                    lang, t["title"], r["font"], self.widths(lang)))
                self.assertFalse(t["scrolls"], "%s, %s tab scrolls" % (lang, t["title"]))

    def test_the_same_layout_in_both_languages(self):
        en, es = self.result["en"]["tabs"], self.result["es"]["tabs"]
        self.assertEqual(len(en), len(es))
        for a, b in zip(en, es):
            self.assertEqual(a["groups"], b["groups"], "%s / %s" % (a["title"], b["title"]))

    def test_no_command_left_its_tab(self):
        tabs = {t["title"]: t for t in self.result["en"]["tabs"]}
        self.assertEqual(set(tabs), set(ON_TABS))
        for title, wanted in ON_TABS.items():
            missing = set(wanted.split()) - set(tabs[title]["reach"])
            self.assertEqual(missing, set(), "gone from the %s tab" % title)

    def test_the_most_used_stay_large_on_the_home_tab(self):
        home = self.result["en"]["tabs"][0]
        large = [item[2] for group in home["groups"] for item in item_list(group)
                 if item[1] == 3]                           # Qt.ToolButtonTextUnderIcon
        for k in ("a_mouse_standard", "a_mouse_hand", "a_cad_mouse", "t:edittext",
                  "t:addtext", "t:editobjects", "t:stamp", "t:image", "t:signature"):
            self.assertIn(k, large)


def item_list(group):
    return [item for item in group if len(item) > 2]


if __name__ == "__main__":
    unittest.main()

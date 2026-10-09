"""Run: QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p test_audit_regressions.py"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pymupdf as F
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PySide6.QtGui import QGuiApplication
from kanzonas.document_view import DocumentView
from kanzonas import annotations as A, autosave, export, measure
app = QApplication.instance() or QApplication([])

class AuditRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup); self.addCleanup(patch.stopall)
        self.views = []; self.addCleanup(lambda: [v.close_doc() for v in self.views])
        self.password = 'user'
        patch.object(QInputDialog, 'getText', side_effect=lambda *a, **k: (self.password, True)).start()
        for n in ('information', 'warning', 'critical'):
            patch.object(QMessageBox, n, return_value=None).start()
        (self.root / 'backups').mkdir()
        patch.object(autosave, 'folder', return_value=str(self.root / 'backups')).start()

    def document(self, name='input', permissions=None):
        p = self.root / (name + '.pdf'); d = F.open()
        for i in range(3):
            pg = d.new_page(); pg.insert_text((72, 72), 'PAGE %d SECRET' % i)
        pg = d[0]
        pg.insert_link({'kind': F.LINK_GOTO, 'from': F.Rect(50, 150, 150, 180), 'page': 2})
        w = F.Widget(); w.field_name = 'test'; w.field_type = F.PDF_WIDGET_TYPE_TEXT
        w.field_value = 'original'; w.rect = F.Rect(50, 250, 200, 280); pg.add_widget(w)
        d.set_page_labels([{'startpage': 0, 'prefix': 'EL-', 'style': 'D', 'firstpagenum': 1}])
        if permissions is None: d.save(p)
        else: d.save(p, encryption=F.PDF_ENCRYPT_AES_256, user_pw='user', owner_pw='owner', permissions=permissions)
        d.close(); v = DocumentView(str(p)); self.views.append(v); return v

    def assert_original_protection(self, out, perms):
        d = F.open(out)
        self.assertTrue(d.needs_pass)
        self.assertEqual(d.authenticate('user'), 2); d.close()
        d = F.open(out); self.assertEqual(d.authenticate('owner'), 4); d.close()
        d = F.open(out); d.authenticate('user')
        self.assertEqual(d.permissions & perms, perms); d.close()

    def test_owner_authority(self):
        # saving edits keeps the file's own encryption: both original passwords still work
        # and no password is invented (an invented owner password locks the owner out)
        perms = F.PDF_PERM_MODIFY | F.PDF_PERM_ANNOTATE
        v = self.document(permissions=perms)
        v.rotate_page(0, 90); out = self.root / 'protected.pdf'
        asked = QInputDialog.getText.call_count
        v.save(str(out))
        self.assertEqual(QInputDialog.getText.call_count, asked, "asked for a password to save")
        self.assert_original_protection(out, perms)

    def test_owner_only_open_requires_original_user_password(self):
        self.password = 'owner'
        perms = F.PDF_PERM_MODIFY | F.PDF_PERM_ANNOTATE
        v = self.document('owner-login', perms)
        v.rotate_page(0, 90); out = self.root / 'owner-save.pdf'
        v.save(str(out))
        self.assert_original_protection(out, perms)

    def test_fill_owner_only_form_and_save(self):
        # a form with only a permissions password (common for official forms) can be filled
        # in and saved without knowing that password, and stays protected
        p = self.root / 'gov.pdf'; d = F.open(); pg = d.new_page()
        w = F.Widget(); w.field_name = 'Name'; w.field_type = F.PDF_WIDGET_TYPE_TEXT
        w.rect = F.Rect(50, 50, 250, 70); pg.add_widget(w)
        perms = F.PDF_PERM_FORM | F.PDF_PERM_PRINT
        d.save(p, encryption=F.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='', permissions=perms)
        d.close(); v = DocumentView(str(p)); self.views.append(v)
        pg = v.doc[0]; v._set_field(0, next(pg.widgets()).xref, 'Jane')
        asked = QInputDialog.getText.call_count
        out = self.root / 'gov-filled.pdf'; v.save(str(out))
        self.assertEqual(QInputDialog.getText.call_count, asked)
        d = F.open(out); pg = d[0]
        self.assertEqual(next(pg.widgets()).field_value, 'Jane')
        self.assertFalse(d.permissions & F.PDF_PERM_MODIFY)
        self.assertEqual(d.authenticate('owner'), 4); d.close()

    def test_undo_then_save_keeps_protection(self):
        perms = F.PDF_PERM_MODIFY | F.PDF_PERM_ANNOTATE
        v = self.document('undo-save', perms)
        v.rotate_page(0, 90); v.rotate_page(1, 90); v.undo()
        out = self.root / 'undo-save-out.pdf'; v.save(str(out))
        self.assert_original_protection(out, perms)

    def test_search_redaction_keeps_unrelated_markups(self):
        # a term that only appears in KanzonasPDF's structure data ("rect") must not delete
        # a rectangle markup
        v = self.document(); pg = v.doc[0]
        A.write(pg, {'kind': 'rect', 'rect': F.Rect(300, 300, 400, 400),
                     'props': dict(A.DEFAULTS['rect'])})
        v._scrub_terms({'rect'})
        pg = v.doc[0]; self.assertEqual(len(list(pg.annots())), 1)

    def test_flatten_keeps_link_position_on_rotated_page(self):
        v = self.document(); v.doc[0].set_rotation(90)
        before = [ln['from'] for ln in v.doc[0].get_links()]
        v.flatten([0])
        self.assertEqual([ln['from'] for ln in v.doc[0].get_links()], before)

    def test_protected_backup(self):
        v = self.document(); a = autosave.Autosaver(None, 0); a.backup(v); old = v._backup_path
        self.assertTrue(Path(old).exists()); v.set_security('new-user', 'new-owner')
        self.assertFalse(Path(old).exists()); a.views = lambda: [v]; a.tick()
        self.assertIsNone(v._backup_path); v.save(str(self.root / 'protected.pdf'))
        v.rotate_page(0, 90); a.tick(); self.assertIsNone(v._backup_path)

    def test_recovery_identity(self):
        a = autosave.Autosaver(None, 0); x = self.document('first'); y = self.document('second')
        x.path = '/a/same.pdf'; y.path = '/b/same.pdf'
        with patch('kanzonas.autosave.time.strftime', return_value='fixed'):
            a.backup(x); a.backup(y)
        self.assertNotEqual(x._backup_path, y._backup_path)
        a.discard(x); self.assertTrue(Path(y._backup_path).exists())

    def test_flatten_semantics(self):
        v = self.document(); v.set_page_scale([0], measure.scale_from_preset(48), 'ft', '1:48')
        v.flatten([0]); out = self.root / 'flattened.pdf'; v.save(str(out)); d = F.open(out)
        self.assertEqual(d[0].get_links()[0]['page'], 2)
        self.assertEqual([p.get_label() for p in d], ['EL-1', 'EL-2', 'EL-3'])
        self.assertTrue(measure.get_scale(d[0])[3]); d.close()

    def test_crossing_vector_redaction(self):
        v = self.document(); v.doc[0].draw_line((50, 100), (550, 100), width=4)
        v.mark_redactions(0, [F.Rect(200, 80, 300, 120)]); v.apply_redactions(scrub=True)
        out = self.root / 'redacted.pdf'; v.save(str(out)); d = F.open(out)
        self.assertFalse(any(i[0] == 'l' and i[1].x == 50 and i[2].x == 550
                             for path in d[0].get_drawings() for i in path['items'])); d.close()

    def test_stamp_private_data_redaction(self):
        v = self.document(); pg = v.doc[0]; props = dict(A.DEFAULTS['stamp']); props['label'] = 'SECRET'
        A.write(pg, {'kind': 'stamp', 'rect': F.Rect(50, 400, 250, 460), 'props': props, 'detail': 'SECRET'})
        v.search_redact('SECRET'); v.apply_redactions(scrub=True)
        out = self.root / 'scrubbed.pdf'; v.save(str(out)); d = F.open(out)
        self.assertFalse(any('SECRET' in d.xref_object(i) for i in range(1, d.xref_length()))); d.close()

    def test_granular_permissions(self):
        v = self.document('fill', F.PDF_PERM_FORM); pg = v.doc[0]; x = next(pg.widgets()).xref
        v._set_field(0, x, 'filled'); pg = v.doc[0]
        self.assertEqual(next(pg.widgets()).field_value, 'filled'); self.assertFalse(v.allowed(F.PDF_PERM_MODIFY))
        v = self.document('annotate', F.PDF_PERM_ANNOTATE)
        v.apply_drag_tool(0, 'rect', F.Point(100, 400), F.Point(200, 450), False)
        pg = v.doc[0]; self.assertEqual(len(list(pg.annots())), 1)

    def test_undo_keeps_original_restrictions(self):
        v = self.document('undo-form', F.PDF_PERM_FORM)
        pg = v.doc[0]; x = next(pg.widgets()).xref
        v._set_field(0, x, 'filled'); v.undo()
        self.assertFalse(v.allowed(F.PDF_PERM_MODIFY))
        self.assertFalse(v.allowed(F.PDF_PERM_COPY))
        self.assertTrue(v.allowed(F.PDF_PERM_FORM))

    def test_restricted_copy(self):
        v = self.document('restricted', 0); QGuiApplication.clipboard().setText('sentinel')
        v.select_all_text(); self.assertIsNone(v.copy())
        self.assertEqual(QGuiApplication.clipboard().text(), 'sentinel'); self.assertFalse(v.allowed(F.PDF_PERM_PRINT))
        with self.assertRaises(PermissionError): v.extract_pages(0, 0, str(self.root / 'copy.pdf'))

    def test_print_entrypoint_refuses_forbidden_document(self):
        from kanzonas.main_window import MainWindow
        v = self.document('no-print', 0)
        class Window:
            def view(self): return v
        with patch('kanzonas.main_window.QPrintDialog') as dialog:
            MainWindow.print_doc(Window())
            dialog.assert_not_called()

    def test_signed_readonly_still_allows_copy_and_print(self):
        v = self.document('signed-policy')
        v.sig_results = [{'intact': True}]; v.read_only = True
        self.assertTrue(v.allowed(F.PDF_PERM_COPY))
        self.assertTrue(v.allowed(F.PDF_PERM_PRINT))
        self.assertFalse(v.allowed(F.PDF_PERM_MODIFY))
        self.assertFalse(v.allowed(F.PDF_PERM_ANNOTATE))

    def test_ocr_disables_telemetry_before_engine(self):
        import sys
        import types
        from kanzonas import ocr
        events = []
        runtime = types.SimpleNamespace(disable_telemetry_events=lambda: events.append('disable'))
        recognizer = types.SimpleNamespace(RapidOCR=lambda: events.append('engine') or object())
        with patch.object(ocr, '_engine', None), patch.dict(sys.modules, {'onnxruntime': runtime, 'rapidocr_onnxruntime': recognizer}):
            ocr._get_engine()
        self.assertEqual(events, ['disable', 'engine'])

    def test_excel_literal(self):
        from openpyxl import load_workbook
        d = F.open(); pg = d.new_page(); pg.insert_text((72, 72), '=1+1'); out = self.root / 'text.xlsx'
        export.to_excel(d.tobytes(), str(out)); d.close(); wb = load_workbook(out)
        self.assertEqual(wb.active['A1'].value, '=1+1'); self.assertEqual(wb.active['A1'].data_type, 's'); wb.close()

if __name__ == '__main__': unittest.main()

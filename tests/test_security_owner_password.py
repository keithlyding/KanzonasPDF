"""An encrypted PDF whose permissions allow editing but that has a permissions (owner)
password: Security properties and Remove security ask for that password instead of failing
silently (set_security raised PermissionError out of the menu command), and Unlock with
password accepts it although the document isn't read-only."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox  # noqa: E402

APP = QApplication.instance() or QApplication([])

from kanzonas.main_window import MainWindow  # noqa: E402


def encrypted_pdf(perms=-1):
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "secret-ish")
    p = os.path.join(tempfile.mkdtemp(), "e.pdf")
    d.save(p, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", permissions=perms)
    return p


class OwnerPassword(unittest.TestCase):
    def window(self, path):
        w = MainWindow()
        w.show()
        w.open_file(path)
        APP.processEvents()
        self.addCleanup(lambda: (setattr(w, "_close_confirmed", True), w.close()))
        return w, w.view()

    def test_editing_allowed_but_security_locked(self):
        w, v = self.window(encrypted_pdf())
        self.assertFalse(v.read_only)
        self.assertFalse(v.owner_authorized())
        with self.assertRaises(PermissionError):
            v.set_security("", "x", -1)

    def test_security_properties_asks_for_the_password_first(self):
        w, v = self.window(encrypted_pdf())
        asked = []

        def get_text(*a, **k):
            asked.append(a[1:3])
            return "owner", True
        with mock.patch.object(QInputDialog, "getText", get_text), \
                mock.patch.object(QDialog, "exec", lambda self: QDialog.Rejected):
            w.security_properties()         # no PermissionError escapes
        self.assertEqual(len(asked), 1)
        self.assertTrue(v.owner_authorized())

    def test_cancel_at_the_password_changes_nothing(self):
        w, v = self.window(encrypted_pdf())
        with mock.patch.object(QInputDialog, "getText", lambda *a, **k: ("", False)), \
                mock.patch.object(QDialog, "exec", lambda self: QDialog.Accepted):
            w.security_properties()
            w.remove_security()
        self.assertFalse(v.owner_authorized())
        self.assertIsNone(v.security)

    def test_remove_security_with_the_password(self):
        w, v = self.window(encrypted_pdf())
        with mock.patch.object(QInputDialog, "getText", lambda *a, **k: ("owner", True)):
            w.remove_security()
        self.assertEqual(v.security, {"open_pw": "", "owner_pw": "", "perms": -1})

    def test_unlock_command_accepts_the_password_when_not_read_only(self):
        w, v = self.window(encrypted_pdf())
        shown = []
        with mock.patch.object(QInputDialog, "getText", lambda *a, **k: ("owner", True)), \
                mock.patch.object(QMessageBox, "information", lambda *a, **k: shown.append(a)):
            w.unlock_doc()
        self.assertTrue(v.owner_authorized())
        self.assertEqual(shown, [], "no 'isn't protected' message for a protected file")
        with mock.patch.object(QMessageBox, "information", lambda *a, **k: shown.append(a)):
            w.unlock_doc()                  # now it really is unlocked
        self.assertEqual(len(shown), 1)

    def test_unencrypted_file_needs_no_password(self):
        d = pymupdf.open()
        d.new_page()
        p = os.path.join(tempfile.mkdtemp(), "plain.pdf")
        d.save(p)
        w, v = self.window(p)
        self.assertTrue(v.owner_authorized())
        with mock.patch.object(QInputDialog, "getText", lambda *a, **k: self.fail("asked")), \
                mock.patch.object(QDialog, "exec", lambda self: QDialog.Rejected):
            w.security_properties()


if __name__ == "__main__":
    unittest.main()

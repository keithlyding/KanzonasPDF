"""Trust fixes. Run: QT_QPA_PLATFORM=offscreen python -m unittest tests.test_trust_fixes"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf as F
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog

from kanzonas import digisign, updates
from kanzonas.document_view import DocumentView

app = QApplication.instance() or QApplication([])


class CertificateTests(unittest.TestCase):
    def test_created_certificate_is_not_a_ca(self):
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import pkcs12
        folder = tempfile.mkdtemp()
        path = digisign.create_certificate(
            "Test", "t@example.com", "Kanzonas", "pw",
            path=os.path.join(folder, "me.p12"))
        _key, cert, _extra = pkcs12.load_key_and_certificates(open(path, "rb").read(), b"pw")
        usage = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        self.assertFalse(usage.key_cert_sign)
        basic = cert.extensions.get_extension_for_class(x509.BasicConstraints)
        self.assertTrue(basic.critical)
        self.assertFalse(basic.value.ca)


class UpdaterTests(unittest.TestCase):
    def test_refuses_non_github_host_and_missing_digest(self):
        release = {"assets": [{
            "name": updates.PORTABLE_ZIP,
            "browser_download_url": "https://evil.example/KanzonasPDF-portable.zip",
            "digest": "sha256:" + "ab" * 32,
        }]}
        self.assertIsNone(updates.asset_url(release))
        release["assets"][0]["browser_download_url"] = (
            "https://github.com/keithlyding/KanzonasPDF/releases/download/v0.84/"
            "KanzonasPDF-portable.zip")
        release["assets"][0].pop("digest")
        self.assertIsNone(updates.asset_url(release))
        release["assets"][0]["digest"] = "sha256:" + "cd" * 32
        self.assertTrue(updates.asset_url(release).startswith("https://github.com/"))
        self.assertEqual(updates.asset_digest(release), "cd" * 32)


class RedactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        patch.object(QInputDialog, "getText", return_value=("", True)).start()
        patch.object(QMessageBox, "warning", return_value=None).start()
        self.addCleanup(patch.stopall)
        self.views = []
        self.addCleanup(lambda: [v.close_doc() for v in self.views])

    def test_apply_redactions_scrubs_metadata_by_default(self):
        path = self.root / "secret.pdf"
        doc = F.open()
        page = doc.new_page()
        page.insert_text((72, 72), "SECRET-TOKEN")
        doc.set_metadata({"title": "SECRET-TOKEN"})
        page.add_redact_annot(F.Rect(70, 60, 220, 90))
        doc.save(path)
        doc.close()
        view = DocumentView(str(path))
        self.views.append(view)
        view.apply_redactions()
        raw = view.doc.tobytes()
        self.assertNotIn(b"SECRET-TOKEN", raw)

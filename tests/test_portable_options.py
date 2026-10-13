"""portable.txt settings used by the PortableApps.com package: data=... puts the data folder
elsewhere, updates=off leaves updating to the PortableApps.com Platform. A plain portable.txt
(the portable zip) keeps working as before.

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_portable_options
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kanzonas import paths, updates  # noqa: E402


class PortableOptions(unittest.TestCase):
    def folder(self, marker):
        root = tempfile.mkdtemp()
        app = os.path.join(root, "App", "KanzonasPDF")
        os.makedirs(app)
        if marker is not None:
            with open(os.path.join(app, paths.MARKER), "w") as f:
                f.write(marker)
        p = mock.patch.object(paths, "app_dir", lambda: app)
        p.start()
        self.addCleanup(p.stop)
        return root, app

    def test_plain_portable_zip_unchanged(self):
        _root, app = self.folder("KanzonasPDF portable\nBecause this file is here, settings = here.\n")
        self.assertEqual(paths.portable_options(), {})
        self.assertEqual(paths.data_dir(), os.path.join(app, "data"))
        self.assertFalse(paths.platform_updates())

    def test_portableapps_package(self):
        root, _app = self.folder("PortableApps.com\ndata=../../Data\nupdates=off\n")
        self.assertEqual(paths.data_dir(), os.path.normpath(os.path.join(root, "Data")))
        self.assertTrue(paths.platform_updates())
        with mock.patch.object(os, "name", "nt"), mock.patch.object(sys, "frozen", True,
                                                                     create=True):
            self.assertFalse(updates.can_self_update())

        class Settings:
            def value(self, _k, default=None):
                return default
        self.assertFalse(updates.UpdateChecker(Settings()).enabled())   # off by default

    def test_installed_copy(self):
        self.folder(None)
        self.assertFalse(paths.is_portable())
        self.assertFalse(paths.platform_updates())


if __name__ == "__main__":
    unittest.main()


class DriveLetterMoves(unittest.TestCase):
    """PortableApps.com Format: the app must keep working, recent files included, when the
    stick's drive letter changes between PCs."""

    def test_follows_the_stick_to_its_new_letter(self):
        import ntpath
        files = {"F:\\Docs\\plan.pdf"}
        exists = files.__contains__
        with mock.patch.object(paths, "is_portable", lambda: True), \
                mock.patch.object(paths, "app_dir", lambda: "F:\\PortableApps\\KanzonasPDFPortable\\App\\KanzonasPDF"):
            f = lambda p: paths.follow_drive(p, exists, ntpath.splitdrive)
            self.assertEqual(f("E:\\Docs\\plan.pdf"), "F:\\Docs\\plan.pdf")
            self.assertEqual(f("C:\\Users\\me\\gone.pdf"), "C:\\Users\\me\\gone.pdf")  # not on stick
            self.assertEqual(f("F:\\Docs\\plan.pdf"), "F:\\Docs\\plan.pdf")
        with mock.patch.object(paths, "is_portable", lambda: False):
            self.assertEqual(paths.follow_drive("E:\\Docs\\plan.pdf", exists, ntpath.splitdrive),
                             "E:\\Docs\\plan.pdf")                               # installed: as is

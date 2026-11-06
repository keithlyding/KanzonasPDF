"""Only one OpenCV ships: rapidocr asks for opencv-python and pdf2docx for
opencv-python-headless, and both install into the same cv2 folder, so which one won depended
on install order (an outside audit found a broken mix). Both builds remove both and install
the headless one at the version pinned in constraints.txt.

    python -m unittest tests.test_opencv_pin
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class OneOpenCV(unittest.TestCase):
    def test_the_headless_one_is_pinned_at_the_same_version(self):
        text = read("constraints.txt")
        gui = re.search(r"^opencv-python==([0-9.]+)", text, re.M)
        headless = re.search(r"^opencv-python-headless==([0-9.]+)", text, re.M)
        self.assertIsNotNone(headless, "opencv-python-headless isn't pinned")
        self.assertEqual(gui.group(1), headless.group(1))

    def test_every_build_keeps_only_the_headless_one(self):
        wf = read(".github", "workflows", "build-windows.yml")
        # (each job removes both, then installs the pinned headless one without dependencies:
        # Windows, Linux and macOS, whose one job builds both kinds of Mac)
        jobs = 3
        self.assertEqual(wf.count("pip uninstall -y opencv-python opencv-python-headless"), jobs)
        self.assertEqual(len(re.findall(r'pip install --no-deps "opencv-python-headless==\$v"',
                                        wf)), jobs)
        self.assertEqual(wf.count("^opencv-python-headless=="), jobs)


if __name__ == "__main__":
    unittest.main()

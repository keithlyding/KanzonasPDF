"""The search for slop (tools/slop_check.py; the owner, 13 Nov 2026: "please add a search for
slop in future testing"): its hard rules hold on every build (no leftovers such as TODO or
"here's the updated code", no AI model names in the program or its texts, no print() in the
program, nothing the guides name that isn't there), and each rule still catches what it's for.
Its soft report is read before a release: python tools/slop_check.py

    python -m unittest tests.test_slop
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import slop_check as S  # noqa: E402


class NoSlop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = S._Code()

    def test_no_leftovers(self):
        self.assertEqual(S.leftovers(), [])

    def test_no_ai_model_names(self):
        self.assertEqual(S.models(), [])

    def test_no_print_in_the_program(self):
        self.assertEqual(S.prints(), [])

    def test_what_the_guides_name_is_there(self):
        self.assertEqual(S.references(), [])


class TheRulesCatchSlop(unittest.TestCase):
    """Each rule on made-up slop, so a rule that stops matching is noticed."""

    @classmethod
    def setUpClass(cls):
        cls.code = S._Code()

    def test_leftovers(self):
        for text in ("# TODO: handle this", "x = 1  # FIXME", "As an AI, I can't",
                     "Here's the updated code:", "Lorem ipsum dolor", "key = 'YOUR_API_KEY'",
                     "<insert your name here>"):
            self.assertTrue(S._MARKER.search(text) or S._LEFTOVER.search(text), text)
        for text in ("Seleccionar todo", "the todo list", "XXXL", "Here's the page"):
            self.assertFalse(S._MARKER.search(text) or S._LEFTOVER.search(text), text)
        self.assertTrue(S._FENCE.match("```python"))

    def test_model_names(self):
        for text in ("written by ChatGPT", "claude-opus-5-5", "gpt-4o", "Gemini 2"):
            self.assertTrue(S._MODEL.search(text), text)
        for text in ("see CLAUDE.md", "the claude/ branches", "Gemini constellation"):
            self.assertFalse(S._MODEL.search(text), text)

    def test_references(self):
        missing = lambda ref: S._missing(ref, self.code)
        # what's there
        for ref in ("kanzonas/manual.py", "tests/__init__.py", "annotations.shift_in_place",
                    "DocumentView.modify", "DocumentView._content_key", "_POSITION_KEYS",
                    "undo_journal.detached", "hit_index.py", "Page.get_textpage",
                    "~/.config/KanzonasPDF", "claude/review-<handle>-pr<N>", "brand/"):
            self.assertIsNone(missing(ref), ref)
        # what isn't (made up)
        for ref in ("kanzonas/smart_cache.py", "tests/test_nothing_here.py",
                    "annotations.shift_everything", "DocumentView.modify_all",
                    "_NO_SUCH_TABLE", "made_up_helper()", "tools/fix_all.py"):
            self.assertIsNotNone(missing(ref), ref)

    def test_wording_and_emoji(self):
        for text in ("Seamlessly edit PDFs", "a robust, cutting-edge editor", "Let's delve in",
                     "It's important to note that", "Unleash your PDFs"):
            self.assertTrue(S._WORDING.search(text), text)
        for text in ("Unlock the PDF", "Trim to the cutting edge", "Edit text"):
            self.assertFalse(S._WORDING.search(text), text)
        self.assertTrue(S._EMOJI.search("Done 🚀"))
        self.assertFalse(S._EMOJI.search("⌘S, ✓ Done, ✕"))     # (the Mac's keys, marks)

    def test_narrating_and_commented(self):
        self.assertTrue(S._NARRATING.search("# Updated to use the new cache"))
        self.assertTrue(S._NARRATING.search("# Fixed: the crash"))
        self.assertFalse(S._NARRATING.search("# fixed-size icons are moved"))
        self.assertTrue(S._CODE_LIKE.match("# x = compute(page)"))


if __name__ == "__main__":
    unittest.main()

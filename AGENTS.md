# KanzonasPDF: rules for every change (all AI agents and people)

This file is read by every coding agent working on this repo (Claude, ChatGPT/Codex, Grok...)
and by people. `CLAUDE.md` just points here. Read all of it before editing.

A free Windows PDF reader/editor in Python (PySide6 + PyMuPDF), built into an .exe by
`.github/workflows/build-windows.yml`, which runs `KanzonasPDF.exe --selftest`.

## Branches and merging (several agents work here at once)
- Start every task from the latest `main`, on a new branch of your own named
  `<agent>/<task>` (for example `chatgpt/fix-print-dialog`, `grok/stamp-sizes`).
  One branch per task.
- Never push to `main`, and never to another agent's branch (`initial-editor` belongs to
  Claude). A push to `main` publishes a release.
- Merge only through a pull request to `main`, and only once the Windows build on your branch
  is green. Never skip, disable or weaken a test to get green.
- **Take the version number at merge time, not at the start.** Just before merging, merge
  the latest `main` into your branch, then set `__version__` to the next number after the one
  on `main` and add your CHANGELOG row above the newest one. Two branches with the same
  version conflict, and the second won't be released.
- **Version numbers (from 0.90 on; 1.0 since 22 Oct 2026):** a bug-fix release bumps the last
  number (1.0 -> 1.0.1 -> 1.0.2 ... 1.0.10); a release with a new feature bumps the middle one
  (1.1, then 1.1.1 for its fixes). Plain numbers only (1.0, not 1.00). A 1.x release is a normal
  release on GitHub (only 0.x ones were marked pre-release).
- Every push to any branch runs the full Windows build (~12 minutes). Push when a piece of
  work is done, not after every small edit.

## Every user-facing change must update, in the same commit:
1. **The user manual** `kanzonas/manual.py` (Help > User manual, F1). Describe new or changed
   tools, menu commands, shortcuts and behavior, and correct anything the change made untrue
   (including the keyboard shortcut table). Name menu commands exactly as the menu shows them.
   The self-test check "user manual covers every command" fails the Windows build if a menu
   command is missing from the manual, but it cannot catch wording that has become wrong.
2. **The version**: bump `__version__` in `kanzonas/__init__.py` (see "Take the version
   number at merge time" above).
3. **CHANGELOG.md**: add a row for the new version (and fill in the previous row's commit).
4. **RELEASE_NOTES.md**: a few plain-language lines under `## <version>` (New / Fixed) and their
   Spanish translation under `## <version> (es)`. They go into the GitHub release and the app's
   update box shows them to people updating; the build fails without them.

## Before pushing
- `QT_QPA_PLATFORM=offscreen python -m kanzonas --selftest selftest.log` must exit 0.
- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p "test_*.py" -t .` must pass
  (`-t .` loads `tests/__init__.py`, which tears Qt down in order at exit; without it the
  process can crash after reporting OK).
- For CAD-related changes: `python tests/cad_samples.py DIR` then `python tests/cad_battery.py DIR`.
- New dependencies: add the minimum to `requirements.txt` and the exact version and license
  to `constraints.txt`; heavy ones must be imported lazily (see Performance).

## Security updates
- `.github/workflows/security-check.yml` runs every Monday (and by hand): pip-audit on
  `constraints.txt`, and `tools/check_dependencies.py` for newer PyMuPDF and PySide6 releases
  (they read untrusted PDFs and pictures; MuPDF fixes often have no PyPI advisory). It reports
  in one open issue labeled `security`. Act on it promptly: bump the pin in `constraints.txt` on
  a branch, read the release notes, and release when the Windows build is green.

## Conventions
- American spelling in all user-visible text.
- Annotations: keep a Page object alive while using an Annot from it ("not bound to page").
- PyMuPDF is not thread-safe: no worker threads touching a document; split long work into
  short slices on the Qt event loop (see Find in `document_view.py`).
## Performance (keep it fast and light, like PDF-XChange)
- Start-up must not import heavy libraries (OCR/onnxruntime, pdf2docx, ezdxf, openpyxl,
  python-pptx, python-docx, pyHanko, aiohttp, OpenCV, qtawesome, pyspellchecker): import them inside the function
  that needs them. Toolbar icons are drawn straight from the MDI font file (theme.py), not
  through qtawesome. The self-test check "performance budget" fails the build if one is loaded.
- Budget (checked in the Windows build): start-up < 5 s, open + draw a 60,000-line sheet
  < 5 s, zoom to 400% < 5 s, peak memory < 800 MB. Typical today: ~0.3 s / 0.9 s / 0.6 s / 170 MB.
- Editing budget (checked in the Windows build, self-test "editing speed budget"): on a 20,000-line
  page, 1,000 markups added < 2 s, moved < 2 s, deleted < 1.5 s; a sheet's 400 labels moved
  with its lines < 4 s; the live CAD highlight's longest step < 0.25 s; a repaint not reading
  the selection again. Typical today: 0.4 / 0.5 / 0.3 / 1.0 s, 0.03 s.
- Everyday budget (self-test "everyday speed budget"): a text-selection drag < 10 ms per move,
  hover over 2,000 markups < 10 ms, Edit objects hover < 5 ms, night mode on 8 megapixels
  < 0.5 s, a 15,000-piece command preview < 80 ms, Tab on a form < 20 ms, inserting 100 pages
  into a shown 300-page document < 2.5 s, deleting 10 pages < 2.5 s. Per-move work goes
  through cached per-page indexes (`hit_index.py`, `_hit_cache`), never a Python loop over
  every character, markup or object; many pieces are drawn as one QPainterPath.
- A markup that is only moved is moved where it is (`annotations.shift_in_place`: its box and
  positions shifted, its drawing reused), never deleted and written anew; keep it that way
  for any new markup kind (a key holding positions goes in `_POSITION_KEYS`, a position kept in
  KZProps in its geom list). tests/test_move_in_place.py checks every kind pixel for pixel.
- Edit in bulk: one redaction, one write, one walk of the page's markups for many items, not
  one per item (PyMuPDF's per-call steps read the whole page or all its markups each time).
- Heavy drawing budget (self-test "heavy drawing speed budget"), on a 60,000-shape sheet:
  reading it for CAD < 2.5 s, its outlines < 2 s, a markup added and the page drawn again
  < 0.3 s, that undone < 0.3 s, a wheel zoom shown < 0.15 s. "performance budget" times the
  400% zoom until the page is sharp.
- `kanzonas/pdf_speed.py` replaces two PyMuPDF steps that slow down steeply with many markups
  (naming a new markup; deleting many), and skips PyMuPDF's hidden-text search in scrub
  (Apply redactions, Sanitize) only on pages with no character and no ActualText. The
  self-test check "PyMuPDF speed fixes" fails if a PyMuPDF update renames what they replace
  or the shortcut stops applying: then read the new PyMuPDF code and update them. Redaction
  is a security feature: never skip work there unless it provably can't change the output.
- Undo goes through MuPDF's journal (`kanzonas/undo_journal.py`), not a copy per edit. Every
  change to a document goes through `DocumentView.modify` (a change made outside one folds
  into the latest edit). MuPDF drops every step to redo at the first change of any kind, so
  nothing may change the document between an undo and a redo except a new edit: a step
  that changes and restores (PyMuPDF turning a rotated page upright to read it) runs inside
  `undo_journal.detached`, and Save and page copies work on a copy while there are steps
  to redo. It patches PyMuPDF and finds MuPDF's resource tables with ctypes; the self-test
  check "undo through MuPDF's journal" fails if that stops working (the app would silently
  fall back to a copy per edit). After a PyMuPDF update, run tests/test_undo_journal.py and
  tests/test_battery_17_undo.py.
- Text is read through `Page.get_textpage`, which `text_guard.py` wraps: MuPDF 1.28 crashes
  on nested ActualText, and such pages are read with TEXT_IGNORE_ACTUALTEXT. Read text through
  PyMuPDF's page methods (or ask `text_guard.flags_for`), never with MuPDF's stext calls
  directly; the self-test check "text reading guard" fails if the guard is off.
- Page content is rendered without markups and kept by a content key (`render_layers.py`,
  `DocumentView._content_key`): any content change must go through `modify` with its pages
  (or `_clear_caches()`), or the old content render stays on screen.
- Never redo expensive work on every mouse move or paint: cache per page and clear the cache
  in `DocumentView._clear_caches()` (see display lists, tiles, snap indexes).
- Big pages render in tiles from a cached display list; keep it that way.

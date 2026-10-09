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

## Before pushing
- `QT_QPA_PLATFORM=offscreen python -m kanzonas --selftest selftest.log` must exit 0.
- `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p "test_*.py"` must pass.
- For CAD-related changes: `python tests/cad_samples.py DIR` then `python tests/cad_battery.py DIR`.
- New dependencies: add the minimum to `requirements.txt` and the exact version and license
  to `constraints.txt`; heavy ones must be imported lazily (see Performance).

## Conventions
- American spelling in all user-visible text.
- Annotations: keep a Page object alive while using an Annot from it ("not bound to page").
- PyMuPDF is not thread-safe: no worker threads touching a document; split long work into
  short slices on the Qt event loop (see Find in `document_view.py`).
## Performance (keep it fast and light, like PDF-XChange)
- Start-up must not import heavy libraries (OCR/onnxruntime, pdf2docx, ezdxf, openpyxl,
  python-pptx, python-docx, pyHanko, aiohttp, OpenCV, qtawesome): import them inside the function
  that needs them. Toolbar icons are drawn straight from the MDI font file (theme.py), not
  through qtawesome. The self-test check "performance budget" fails the build if one is loaded.
- Budget (checked in the Windows build): start-up < 5 s, open + draw a 60,000-line sheet
  < 5 s, zoom to 400% < 5 s, peak memory < 800 MB. Typical today: ~0.3 s / 0.9 s / 0.6 s / 170 MB.
- Never redo expensive work on every mouse move or paint: cache per page and clear the cache
  in `DocumentView._clear_caches()` (see display lists, tiles, snap indexes).
- Big pages render in tiles from a cached display list; keep it that way.

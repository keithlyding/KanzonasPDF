# KanzonasPDF: rules for every change

A free Windows PDF reader/editor in Python (PySide6 + PyMuPDF), built into an .exe by
`.github/workflows/build-windows.yml`, which runs `KanzonasPDF.exe --selftest`.

## Every user-facing change must update, in the same commit:
1. **The user manual** `kanzonas/manual.py` (Help > User manual, F1). Describe new or changed
   tools, menu commands, shortcuts and behavior, and correct anything the change made untrue
   (including the keyboard shortcut table). Name menu commands exactly as the menu shows them.
   The self-test check "user manual covers every command" fails the Windows build if a menu
   command is missing from the manual, but it cannot catch wording that has become wrong.
2. **The version**: bump `__version__` in `kanzonas/__init__.py`.
3. **CHANGELOG.md**: add a row for the new version (and fill in the previous row's commit).

## Before pushing
- `QT_QPA_PLATFORM=offscreen python -m kanzonas --selftest selftest.log` must exit 0.
- For CAD-related changes: `python tests/cad_samples.py DIR` then `python tests/cad_battery.py DIR`.

## Conventions
- American spelling in all user-visible text.
- Annotations: keep a Page object alive while using an Annot from it ("not bound to page").

## Performance (keep it fast and light, like PDF-XChange)
- Start-up must not import heavy libraries (OCR/onnxruntime, pdf2docx, ezdxf, openpyxl,
  python-pptx, python-docx, pyHanko, aiohttp, OpenCV): import them inside the function that
  needs them. The self-test check "performance budget" fails the build if one is loaded.
- Budget (checked in the Windows build): start-up < 5 s, open + draw a 60,000-line sheet
  < 5 s, zoom to 400% < 5 s, peak memory < 800 MB. Typical today: ~0.3 s / 0.9 s / 0.6 s / 170 MB.
- Never redo expensive work on every mouse move or paint: cache per page and clear the cache
  in `DocumentView._clear_caches()` (see display lists, tiles, snap indexes).
- Big pages render in tiles from a cached display list; keep it that way.

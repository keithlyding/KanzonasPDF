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

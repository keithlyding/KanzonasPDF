@echo off
REM Builds a standalone Windows app into dist\KanzonasPDF\KanzonasPDF.exe
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --windowed --name KanzonasPDF run.py
echo.
echo Done. Run dist\KanzonasPDF\KanzonasPDF.exe

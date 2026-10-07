@echo off
REM Builds a standalone Windows app into dist\KanzonasPDF\KanzonasPDF.exe
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --windowed --collect-all rapidocr_onnxruntime --collect-all docx --collect-all pptx --collect-all pdf2docx --collect-all ezdxf --collect-all openpyxl --name KanzonasPDF run.py
echo.
echo Done. Run dist\KanzonasPDF\KanzonasPDF.exe

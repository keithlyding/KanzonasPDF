@echo off
REM Builds a standalone Windows app into dist\KanzonasPDF\KanzonasPDF.exe
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --windowed --collect-all rapidocr_onnxruntime --collect-all docx --collect-all pptx --collect-all pdf2docx --collect-all ezdxf --collect-all openpyxl --collect-all pyhanko --collect-all pyhanko_certvalidator --collect-all qtawesome --collect-all aiohttp --icon assets/kanzonas.ico --name KanzonasPDF run.py
echo.
echo Done. Run dist\KanzonasPDF\KanzonasPDF.exe

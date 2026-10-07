@echo off
REM Double-click this file to run KanzonasPDF from source.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)

REM Install the libraries the first time (or after an update adds new ones).
python -c "import pymupdf, PySide6, rapidocr_onnxruntime, pdf2docx, ezdxf, openpyxl, pptx, pyhanko, qtawesome" >nul 2>nul
if errorlevel 1 (
    echo First run: installing required libraries, this takes a minute...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installing libraries failed. See the messages above.
        pause
        exit /b 1
    )
)

REM pythonw runs the app without leaving a console window open.
start "" pythonw run.py %*

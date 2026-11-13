# Builds KanzonasPDFShell.dll (Explorer's thumbnails and Preview pane for PDFs) and its test,
# kzshell_test.exe, with the Visual C++ compiler, against the MuPDF that PyMuPDF ships
# (pymupdf\mupdf-devel: its headers and mupdfcpp64.lib; the DLL loads PyMuPDF's
# mupdfcpp64.dll from the program's _internal\pymupdf folder at first use).
#
#   powershell -File shell_ext\build.ps1 -Out shell_ext\out
param([Parameter(Mandatory = $true)][string]$Out)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pym = python -c "import os, pymupdf; print(os.path.dirname(pymupdf.__file__))"
$inc = Join-Path $pym "mupdf-devel\include"
$lib = Join-Path $pym "mupdf-devel\lib\mupdfcpp64.lib"
if (-not (Test-Path (Join-Path $inc "mupdf\functions.h"))) { throw "PyMuPDF's MuPDF headers aren't in $inc" }
if (-not (Test-Path $lib)) { throw "PyMuPDF's mupdfcpp64.lib isn't at $lib" }
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw "Visual C++ isn't installed" }
$vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$out = (Resolve-Path $Out).Path
# /MT: the static C++ runtime (Explorer's helper processes load the DLL before anything of
# ours could put a runtime on their path); /EHsc: MuPDF's C++ functions throw on errors
$flags = "/nologo /O2 /EHsc /MT /std:c++17 /W3 /DUNICODE /D_UNICODE /I`"$inc`" /I`"$here`""
$libs = "shlwapi.lib ole32.lib user32.lib gdi32.lib uuid.lib"
$dll = "cl $flags /LD `"$here\kzshell.cpp`" /Fo`"$out\\`" /Fe`"$out\KanzonasPDFShell.dll`" /link /DEF:`"$here\kzshell.def`" `"$lib`" delayimp.lib /DELAYLOAD:mupdfcpp64.dll $libs"
$test = "cl $flags `"$here\kzshell_test.cpp`" /Fo`"$out\\`" /Fe`"$out\kzshell_test.exe`" /link $libs"
cmd /s /c "`"$vcvars`" >nul && $dll && $test"
if ($LASTEXITCODE -ne 0) { throw "the build failed ($LASTEXITCODE)" }
Get-Item "$out\KanzonasPDFShell.dll", "$out\kzshell_test.exe" | Format-Table Name, Length

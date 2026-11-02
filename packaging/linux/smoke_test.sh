#!/bin/bash
# Smoke test of the Linux app: it starts on an X display, opens a PDF (its window shows the
# file's name) and is still running 15 s later.
#   packaging/linux/smoke_test.sh ./KanzonasPDF-x86_64.AppImage --appimage-extract-and-run
# Needs Xvfb and xdotool, and Python with PyMuPDF (to make the PDF).
set -u
work=$(mktemp -d)
python -c "import pymupdf, sys; d = pymupdf.open(); d.new_page().insert_text((72, 72), 'smoke'); d.save(sys.argv[1])" "$work/kz-smoke-test.pdf" || exit 1

Xvfb :97 -screen 0 1600x1000x24 -nolisten tcp > "$work/xvfb.log" 2>&1 &
xvfb=$!
export DISPLAY=:97
sleep 2
QT_QPA_PLATFORM=xcb "$@" "$work/kz-smoke-test.pdf" > "$work/app.log" 2>&1 &
app=$!

result=1
for i in $(seq 1 60); do
  if ! kill -0 $app 2>/dev/null; then
    wait $app; echo "The app exited early with code $?"; break
  fi
  if xdotool search --name "kz-smoke-test" > /dev/null 2>&1; then
    echo "Window open with the PDF after ${i} s: $(xdotool search --name kz-smoke-test getwindowname | head -1)"
    sleep 15
    if kill -0 $app 2>/dev/null; then result=0; else echo "The app exited within 15 s of opening the PDF"; fi
    break
  fi
  sleep 1
done
if [ $result -ne 0 ] && [ "$i" -eq 60 ]; then echo "No window showing the PDF after 60 s"; fi

# (with --appimage-extract-and-run the app is a child of the AppImage runtime, which removes
# the unpacked files when it ends)
pkill -TERM -P $app 2>/dev/null; kill $app 2>/dev/null
sleep 3
pkill -KILL -P $app 2>/dev/null; kill -9 $app 2>/dev/null
kill $xvfb 2>/dev/null
echo "--- app output"; grep -v "^\[INFO\]" "$work/app.log" | tail -40
rm -rf "$work"
exit $result

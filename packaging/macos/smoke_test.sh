#!/bin/bash
# Smoke test of the macOS app, on the Mac's real display (not offscreen):
#   1. a PDF opened as Finder opens it (LaunchServices starts the app and hands it the file as
#      an Apple event, a QFileOpenEvent in the app) opens;
#   2. a second PDF opened the same way while it runs goes to the same, running app;
#   3. the program started a second time with a PDF (as from a terminal) hands it over to
#      the running one and ends;
#   4. it's still running 15 s later, with one window or more.
# "Opened" is read from the recent files list the app keeps in its settings (macOS keeps
# them for it in cfprefsd, readable with `defaults` while it runs); the window titles are
# checked too when macOS lets this script read them (they need Screen Recording permission).
#   packaging/macos/smoke_test.sh dist/KanzonasPDF.app [screenshot.png]
# Needs Python with PyMuPDF (to make the PDFs). When something fails, a screenshot is saved
# where the second argument says (when macOS lets this script take one).
set -u
app="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
exe="$app/Contents/MacOS/KanzonasPDF"
id=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$app/Contents/Info.plist")
work=$(mktemp -d)
work=$(cd "$work" && pwd -P)              # (/var is a link to /private/var)
for n in kz-smoke-first kz-smoke-second kz-smoke-third; do
  python -c "import pymupdf, sys; d = pymupdf.open(); d.new_page().insert_text((72, 72), 'smoke'); d.save(sys.argv[1])" "$work/$n.pdf" || exit 1
done
unset QT_QPA_PLATFORM

domain() {      # the app's settings (QSettings keeps them under its organization's domain)
  defaults domains 2>/dev/null | tr ',' '\n' | sed 's/^ *//' | grep -i '^com\.kanzonaspdf\.' | head -1
}
d=$(domain)
if [ -n "$d" ]; then defaults delete "$d" recent > /dev/null 2>&1; fi

running() { pgrep -f "$exe" | wc -l | tr -d ' '; }

opened() {      # wait up to $2 s for $1 in the recent files
  for _ in $(seq 1 "$2"); do
    d=$(domain)
    if [ -n "$d" ] && defaults read "$d" recent 2>/dev/null | grep -q "$1"; then return 0; fi
    sleep 1
  done
  return 1
}

windows() {     # the app's window titles, one per line ("" when they can't be read)
  osascript -l JavaScript -e '
    ObjC.import("CoreGraphics");
    const all = ObjC.deepUnwrap(ObjC.castRefToObject(
      $.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, $.kCGNullWindowID)));
    all.filter(w => w.kCGWindowOwnerName === "KanzonasPDF" && w.kCGWindowLayer === 0)
       .map(w => "[" + (w.kCGWindowName || "") + "]").join("\n")' 2>/dev/null
}

result=0
fail() { echo "FAIL: $*"; result=1; }

echo "--- 1. opened from Finder (LaunchServices, an Apple event)"
# (the first start of a new app can be slow: macOS checks it)
open --stdout "$work/app.out" --stderr "$work/app.err" -a "$app" "$work/kz-smoke-first.pdf" \
  || fail "open couldn't start the app"
if opened kz-smoke-first.pdf 180; then echo "opened kz-smoke-first.pdf"; else fail "kz-smoke-first.pdf didn't open"; fi
[ "$(running)" -ge 1 ] || fail "the app isn't running"
pid=$(pgrep -f "$exe" | head -1)

echo "--- 2. a second PDF while it runs (Apple event to the running app)"
open -a "$app" "$work/kz-smoke-second.pdf" || fail "open failed"
if opened kz-smoke-second.pdf 30; then echo "opened kz-smoke-second.pdf"; else fail "kz-smoke-second.pdf didn't open"; fi
[ "$(running)" = 1 ] || fail "$(running) copies of the app are running (one expected)"

echo "--- 3. the program started again with a PDF hands it over and ends"
"$exe" "$work/kz-smoke-third.pdf" > "$work/second.log" 2>&1 &
second=$!
for _ in $(seq 1 30); do kill -0 $second 2>/dev/null || break; sleep 1; done
if kill -0 $second 2>/dev/null; then
  fail "the second copy is still running"; kill $second 2>/dev/null
else
  wait $second || fail "the second copy ended with code $?"
fi
if opened kz-smoke-third.pdf 30; then echo "opened kz-smoke-third.pdf"; else fail "kz-smoke-third.pdf didn't reach the running app"; fi
[ "$(pgrep -f "$exe" | head -1)" = "$pid" ] || fail "the first copy isn't the one running"

echo "--- 4. still running 15 s later"
sleep 15
[ "$(running)" = 1 ] || fail "the app ended"
w=$(windows)
echo "windows: $(echo "$w" | tr '\n' ' ')"
if [ -z "$w" ]; then
  echo "::warning::couldn't list the app's windows (osascript)"
elif echo "$w" | grep -q '\[kz-smoke'; then
  echo "the window shows a smoke-test PDF"
elif echo "$w" | grep -q '\[.\+\]'; then
  fail "no window shows a smoke-test PDF"
else
  echo "(window titles not readable here: no Screen Recording permission; the recent files say what opened)"
fi
d=$(domain)
echo "settings domain: $d"; defaults read "$d" recent 2>/dev/null

if [ $result -ne 0 ]; then
  echo "--- the app"; ps -o pid,etime,time,stat,command -p "$(pgrep -f "$exe" | head -1)" 2>/dev/null
  if [ $# -ge 2 ]; then screencapture -x "$2" 2>/dev/null && echo "screenshot: $2"; fi
fi
pkill -TERM -f "$exe"; sleep 3; pkill -KILL -f "$exe" 2>/dev/null
echo "--- the app's output"; tail -40 "$work/app.err" "$work/app.out" 2>/dev/null
echo "--- second copy's output"; tail -20 "$work/second.log"
rm -rf "$work"
exit $result

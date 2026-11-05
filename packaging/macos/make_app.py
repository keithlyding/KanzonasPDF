"""Finishes the macOS app that PyInstaller made, checks it, and packs it in a disk image (the
macos job of .github/workflows/build-windows.yml runs it; the checks run on any computer).

    python packaging/macos/make_app.py finish dist/KanzonasPDF.app --version 1.9 --arch arm64 \
        [--min-macos 14.4] [--licenses DIR] [--adhoc-sign]
    python packaging/macos/make_app.py dmg dist/KanzonasPDF.app KanzonasPDF-macos-arm64.dmg

1. Info.plist: the bundle id, name and version, the icon, the oldest macOS it runs on, dark
   mode, and PDF as a document type, so Finder offers KanzonasPDF in Open With and it can be
   made the app for every PDF (Get Info > Change All).
2. The icon: KanzonasPDF.icns made from assets/kanzonas-icon-source.png (the small sizes from
   kanzonas-icon-small-source.png, drawn for them), with macOS's iconutil when it's there.
3. The license files (LICENSE.txt, NOTICE.txt, LICENSE-AGPL-3.0.txt) in Contents/Resources.
4. Checks every program and library in the app (Mach-O files): each one has code for the
   Mac it's for (--arch: arm64 for Apple silicon, x86_64 for Intel; a universal file has
   both) and none needs a newer macOS than --min-macos (the build machine is newer than
   the oldest supported Mac, so its own self test alone wouldn't show it).
5. --adhoc-sign: signs the app again without an identity ("ad hoc", as PyInstaller did:
   changing Info.plist broke that signature, and an Apple silicon Mac runs no unsigned
   code). A Developer ID signature, when there is one, replaces it (see the workflow).
6. dmg: a compressed disk image holding the app and a link to /Applications to drag it to.
Exits with 1 (and says why) when a check fails.
"""
import argparse
import os
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
APP = "KanzonasPDF"
BUNDLE_ID = "io.github.keithlyding.kanzonaspdf"
ICON = "KanzonasPDF.icns"
LICENSES = ("LICENSE.txt", "NOTICE.txt", "LICENSE-AGPL-3.0.txt")
ICON_SIZES = (16, 32, 64, 128, 256, 512, 1024)
SMALL_ICON_UP_TO = 64           # sizes drawn from the small icon source (as on Windows)

# Mach-O (macOS programs and libraries)
CPU = {"x86_64": 0x01000007, "arm64": 0x0100000C}
CPU_NAMES = {v: k for k, v in CPU.items()}
MH_MAGIC_64, MH_MAGIC = 0xFEEDFACF, 0xFEEDFACE
FAT_MAGIC, FAT_MAGIC_64 = 0xCAFEBABE, 0xCAFEBABF
LC_VERSION_MIN_MACOSX, LC_BUILD_VERSION = 0x24, 0x32
PLATFORM_MACOS = 1


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


# ---- Info.plist ------------------------------------------------------------------------------

def info_plist(info, version, min_macos):
    """info (the dict PyInstaller wrote) with KanzonasPDF's own entries."""
    info = dict(info)
    info.update({
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": APP,
        "CFBundleDisplayName": APP,
        "CFBundleExecutable": info.get("CFBundleExecutable", APP),
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "CFBundleIconFile": ICON,
        "CFBundleDevelopmentRegion": "en",
        "CFBundleLocalizations": ["en", "es"],
        "LSMinimumSystemVersion": min_macos,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,       # follows Light / Dark
        "NSSupportsAutomaticGraphicsSwitching": True,
        "NSHumanReadableCopyright": "Free software under the GNU AGPL-3.0",
        # PDF files: listed in Finder's Open With, and can be made the app for all of them
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "PDF document",
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Default",
            "LSItemContentTypes": ["com.adobe.pdf"],
            "CFBundleTypeExtensions": ["pdf"],
            "CFBundleTypeMIMETypes": ["application/pdf"],
            "CFBundleTypeIconSystemGenerated": True,
        }],
    })
    return info


def write_info_plist(app, version, min_macos):
    path = os.path.join(app, "Contents", "Info.plist")
    try:
        with open(path, "rb") as f:
            info = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException) as e:
        fail(f"can't read {path}: {e}")
    old_icon = info.get("CFBundleIconFile")
    info = info_plist(info, version, min_macos)
    with open(path, "wb") as f:
        plistlib.dump(info, f)
    return info, old_icon


# ---- the icon --------------------------------------------------------------------------------

def icon_images(big, small):
    """{size: RGBA image} for the .icns, the small sizes from the small source."""
    from PIL import Image
    out = {}
    with Image.open(big) as b, Image.open(small) as s:
        b, s = b.convert("RGBA"), s.convert("RGBA")
        for size in ICON_SIZES:
            src = s if size <= SMALL_ICON_UP_TO else b
            out[size] = src.resize((size, size), Image.LANCZOS)
    return out


def make_icns(out, big=None, small=None):
    """Write the app icon to out: with iconutil (macOS) from an .iconset folder, else with
    Pillow."""
    big = big or os.path.join(ROOT, "assets", "kanzonas-icon-source.png")
    small = small or os.path.join(ROOT, "assets", "kanzonas-icon-small-source.png")
    images = icon_images(big, small)
    iconutil = shutil.which("iconutil")
    if iconutil:
        with tempfile.TemporaryDirectory() as tmp:
            iconset = os.path.join(tmp, "KanzonasPDF.iconset")
            os.mkdir(iconset)
            for size in ICON_SIZES[:-1]:            # 16 ... 512, each also at twice the size
                images[size].save(os.path.join(iconset, f"icon_{size}x{size}.png"))
                images[size * 2].save(os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
            subprocess.run([iconutil, "-c", "icns", "-o", out, iconset], check=True)
    else:
        images[1024].save(out, format="ICNS",
                          append_images=[images[s] for s in ICON_SIZES[:-1]])
    with open(out, "rb") as f:
        if f.read(4) != b"icns":
            fail(f"{out} isn't an icon file")


# ---- Mach-O checks ---------------------------------------------------------------------------

def _version(v):
    """A Mach-O version number (xxxx.yy.zz in nibbles) as (major, minor, patch)."""
    return (v >> 16, (v >> 8) & 0xFF, v & 0xFF)


def _slice_info(data, off):
    """(cpu type, oldest macOS (major, minor, patch) or None) of the thin Mach-O at off."""
    magic = struct.unpack_from("<I", data, off)[0]
    if magic not in (MH_MAGIC_64, MH_MAGIC):
        return None, None
    cputype, _sub, _ft, ncmds, _size = struct.unpack_from("<iiiII", data, off + 4)
    p = off + (32 if magic == MH_MAGIC_64 else 28)
    minos = None
    for _ in range(ncmds):
        if p + 8 > len(data):
            break
        cmd, cmdsize = struct.unpack_from("<II", data, p)
        if cmd == LC_BUILD_VERSION:
            platform, v = struct.unpack_from("<II", data, p + 8)
            if platform == PLATFORM_MACOS:
                minos = _version(v)
        elif cmd == LC_VERSION_MIN_MACOSX:
            minos = _version(struct.unpack_from("<I", data, p + 8)[0])
        if cmdsize < 8:
            break
        p += cmdsize
    return cputype & 0xFFFFFFFF, minos


def macho_info(path):
    """{architecture name: oldest macOS (major, minor, patch) or None} of the Mach-O file at
    path (one entry, or one per slice of a universal file); None when it isn't one."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if len(head) < 8:
                return None
            be = struct.unpack(">I", head[:4])[0]
            le = struct.unpack("<I", head[:4])[0]
            if le not in (MH_MAGIC_64, MH_MAGIC) and be not in (FAT_MAGIC, FAT_MAGIC_64):
                return None
            if be in (FAT_MAGIC, FAT_MAGIC_64):
                nfat = struct.unpack(">I", head[4:8])[0]
                if not 0 < nfat < 30:          # (a Java class file starts with CAFEBABE too)
                    return None
            f.seek(0)
            data = f.read()
    except OSError:
        return None
    out = {}
    if le in (MH_MAGIC_64, MH_MAGIC):
        cpu, minos = _slice_info(data, 0)
        out[CPU_NAMES.get(cpu, hex(cpu))] = minos
        return out
    nfat = struct.unpack_from(">I", data, 4)[0]
    wide = be == FAT_MAGIC_64
    p = 8
    for _ in range(nfat):
        if wide:
            cpu, _sub, offset, _size, _align, _r = struct.unpack_from(">iiQQII", data, p)
            p += 32
        else:
            cpu, _sub, offset, _size, _align = struct.unpack_from(">iiIII", data, p)
            p += 20
        _cpu, minos = _slice_info(data, offset)
        out[CPU_NAMES.get(cpu & 0xFFFFFFFF, hex(cpu & 0xFFFFFFFF))] = minos
    return out


def macho_files(top):
    for d, _dirs, files in os.walk(top):
        for n in files:
            p = os.path.join(d, n)
            if os.path.islink(p):
                continue
            info = macho_info(p)
            if info:
                yield p, info


# Qt for Python's own modules (PySide6 6.12.0: the Python bindings, libshiboken and
# libpyside, not Qt itself) name the macOS of the SDK they were built with (26.0) as their
# oldest. A library's oldest macOS isn't enforced when it's loaded, and they run on older
# ones: the builds' tests and self-test run them on macOS 15. Qt's own libraries are checked.
SDK_AS_MINIMUM = re.compile(r"^Contents/Frameworks/(PySide6|shiboken6)/[^/]+\.(so|dylib)$")


def check_binaries(app, arch, min_macos):
    """Problems (text lines) with the app's programs and libraries: code missing for arch,
    or needing a macOS newer than min_macos. Also returns how many were checked and the
    newest macOS one needs."""
    want = tuple(int(x) for x in min_macos.split("."))
    want = want + (0,) * (3 - len(want))
    problems, n, newest = [], 0, (0, 0, 0)
    for path, info in macho_files(app):
        n += 1
        rel = os.path.relpath(path, app).replace(os.sep, "/")
        if arch not in info:
            problems.append(f"{rel}: no {arch} code (has {', '.join(sorted(info))})")
            continue
        minos = info[arch]
        if minos and minos > want and SDK_AS_MINIMUM.match(rel):
            print(f"(not checked: {rel} names macOS {'.'.join(map(str, minos))}, its SDK's)")
            continue
        if minos:
            newest = max(newest, minos)
            if minos > want:
                problems.append(f"{rel}: needs macOS {'.'.join(map(str, minos))} "
                                f"(the app says it runs on {min_macos})")
    return problems, n, newest


# ---- the app ---------------------------------------------------------------------------------

def finish(app, version, arch, min_macos, licenses=None, sign=False):
    if not os.path.isdir(os.path.join(app, "Contents", "MacOS")):
        fail(f"{app} isn't an app bundle")
    resources = os.path.join(app, "Contents", "Resources")
    os.makedirs(resources, exist_ok=True)
    info, old_icon = write_info_plist(app, version, min_macos)
    exe = os.path.join(app, "Contents", "MacOS", info["CFBundleExecutable"])
    if not os.path.isfile(exe):
        fail(f"the program {exe} named in Info.plist isn't there")
    if old_icon and old_icon != ICON:
        for name in (old_icon, old_icon + ".icns"):     # (PyInstaller's, made from the .ico)
            p = os.path.join(resources, name)
            if os.path.isfile(p):
                os.remove(p)
    make_icns(os.path.join(resources, ICON))
    if licenses:
        for name in LICENSES:
            src = os.path.join(licenses, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(resources, name))
    for name in LICENSES[:2]:                           # (the AGPL text download may fail)
        if not os.path.isfile(os.path.join(resources, name)):
            fail(f"{name} is missing from the app (pass --licenses)")
    problems, n, newest = check_binaries(app, arch, min_macos)
    print(f"Checked {n} programs and libraries for {arch}: the newest macOS one needs is "
          f"{'.'.join(map(str, newest))}")
    if not n:
        fail("no programs or libraries found in the app")
    if problems:
        fail("the app won't run on every Mac it says it runs on:\n  " + "\n  ".join(problems))
    if sign:
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app],
                       check=True)


def make_dmg(app, out, volume=APP):
    """A compressed disk image with the app and a link to /Applications."""
    with tempfile.TemporaryDirectory() as tmp:
        stage = os.path.join(tmp, volume)
        os.mkdir(stage)
        # (ditto keeps the app's links, permissions and signature exactly)
        subprocess.run(["ditto", app, os.path.join(stage, os.path.basename(app))], check=True)
        os.symlink("/Applications", os.path.join(stage, "Applications"))
        if os.path.exists(out):
            os.remove(out)
        subprocess.run(["hdiutil", "create", "-volname", volume, "-srcfolder", stage,
                        "-fs", "HFS+", "-format", "UDZO", "-imagekey", "zlib-level=9",
                        "-ov", out], check=True)
    subprocess.run(["hdiutil", "verify", out], check=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Finish, check and pack the macOS app.")
    sub = ap.add_subparsers(dest="step", required=True)
    f = sub.add_parser("finish", help="Info.plist, icon, licenses, checks (and ad hoc signing)")
    f.add_argument("app", help="the .app PyInstaller made (dist/KanzonasPDF.app)")
    f.add_argument("--version", required=True)
    f.add_argument("--arch", required=True, choices=sorted(CPU))
    f.add_argument("--min-macos", default="14.4")
    f.add_argument("--licenses", help="folder with LICENSE.txt, NOTICE.txt, LICENSE-AGPL-3.0.txt")
    f.add_argument("--adhoc-sign", action="store_true")
    d = sub.add_parser("dmg", help="pack the (finished, signed) app in a disk image")
    d.add_argument("app")
    d.add_argument("dmg")
    a = ap.parse_args(argv)
    if a.step == "finish":
        finish(os.path.abspath(a.app), a.version, a.arch, a.min_macos, a.licenses, a.adhoc_sign)
    else:
        make_dmg(os.path.abspath(a.app), a.dmg)
        print(f"{a.dmg}: {os.path.getsize(a.dmg) // 1000000} MB")


if __name__ == "__main__":
    main()

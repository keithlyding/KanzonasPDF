"""Makes the Linux AppImage from the PyInstaller folder (the Linux job of
.github/workflows/build-windows.yml runs it; it runs the same way on any Linux machine).

    python packaging/linux/make_appimage.py dist/KanzonasPDF AppDir --version 1.7 \
        [--max-glibc 2.35 --max-glibcxx 3.4.30] \
        [--appimagetool appimagetool-x86_64.AppImage --runtime-file runtime-x86_64 \
         --output KanzonasPDF-x86_64.AppImage]

1. Copies the PyInstaller folder to AppDir/usr/lib/KanzonasPDF and adds AppRun, the desktop
   file, the icon, the AppStream metadata and the license files.
2. Removes the libraries in packaging/linux/excludelist (the computer's own are used).
3. Checks the bundle: the desktop file and AppStream metadata, no excluded library left,
   every library a bundled file needs is in the bundle or on this machine, and (with
   --max-glibc / --max-glibcxx / --max-cxxabi / --max-libgcc) that nothing needs a newer
   glibc, C++ runtime (libstdc++ and its C++ ABI) or libgcc_s than the oldest system the
   AppImage supports. Lists what it takes from the computer.
4. With --appimagetool, packs AppDir into the AppImage.
Exits with 1 (and says why) when a check fails.
"""
import argparse
import datetime
import os
import re
import shutil
import stat
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
APP = "KanzonasPDF"
ID = "kanzonaspdf"                      # desktop file and icon name
# AppStream metadata: named after its reverse-DNS id, as AppStream wants (appimagetool would
# look for kanzonaspdf.appdata.xml; it's told not to, and the metadata is checked here)
METAINFO = "io.github.keithlyding.kanzonaspdf.metainfo.xml"
LICENSES = ("LICENSE.txt", "NOTICE.txt", "LICENSE-AGPL-3.0.txt")
# plugins Qt loads only when asked for (embedded displays, VNC, Vulkan displays): a library
# they need that's missing on a desktop is not an error
# (and Read aloud's Speech Dispatcher plugin: it needs the computer's own libspeechd, which
# comes with its speech-dispatcher service; without it Read aloud says how to install it)
OPTIONAL_PLUGINS = ("platforms/libqeglfs.so", "platforms/libqminimalegl.so",
                    "platforms/libqvkkhrdisplay.so", "platforms/libqlinuxfb.so",
                    "platforms/libqvnc.so", "egldeviceintegrations/",
                    "texttospeech/libqtexttospeech_speechd.so")
# the versioned libraries left to the computer (excludelist): every kind of version name
# they define, so that a need for a newer one than the oldest supported system has is
# caught (GCC 14 code needs CXXABI_1.3.15 even when it needs no newer GLIBCXX version)
VERSIONED = ("GLIBC", "GLIBCXX", "CXXABI", "GCC")
VERSION_NEED = re.compile(r"\b(%s)_(\d+(?:\.\d+)+)\b" % "|".join(VERSIONED))
# version names without a number, and the glibc that brought them (-z pack-relative-relocs)
NAMED_VERSIONS = {"GLIBC_ABI_DT_RELR": ("GLIBC", "2.36")}


def fail(msg):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def excluded_names():
    with open(os.path.join(HERE, "excludelist"), encoding="utf-8") as f:
        return {ln.split("#")[0].strip() for ln in f} - {""}


def is_elf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def elf_files(top):
    for d, _dirs, files in os.walk(top):
        for n in files:
            p = os.path.join(d, n)
            if not os.path.islink(p) and is_elf(p):
                yield p


def version_key(v):
    return tuple(int(x) for x in v.split("."))


def make_appdir(dist, appdir, version):
    if not os.path.isfile(os.path.join(dist, APP)):
        fail("%s isn't a PyInstaller folder (no %s in it)" % (dist, APP))
    missing = [n for n in LICENSES[:2] if not os.path.isfile(os.path.join(dist, n))]
    if missing:
        fail("license files missing from %s: %s (the license step runs first)"
             % (dist, ", ".join(missing)))
    if os.path.exists(appdir):
        shutil.rmtree(appdir)
    lib = os.path.join(appdir, "usr", "lib", APP)
    shutil.copytree(dist, lib, symlinks=True)

    shutil.copy2(os.path.join(HERE, "AppRun"), os.path.join(appdir, "AppRun"))
    os.chmod(os.path.join(appdir, "AppRun"), 0o755)
    share = os.path.join(appdir, "usr", "share")
    for d in ("applications", "icons/hicolor/256x256/apps", "metainfo", "doc/" + ID):
        os.makedirs(os.path.join(share, d), exist_ok=True)
    desktop = os.path.join(HERE, ID + ".desktop")
    shutil.copy2(desktop, os.path.join(appdir, ID + ".desktop"))
    shutil.copy2(desktop, os.path.join(share, "applications", ID + ".desktop"))
    icon = os.path.join(ROOT, "assets", "kanzonas.png")          # 256 x 256
    shutil.copy2(icon, os.path.join(appdir, ID + ".png"))
    shutil.copy2(icon, os.path.join(share, "icons/hicolor/256x256/apps", ID + ".png"))
    os.symlink(ID + ".png", os.path.join(appdir, ".DirIcon"))
    with open(os.path.join(HERE, METAINFO), encoding="utf-8") as f:
        meta = f.read()
    meta = meta.replace("@VERSION@", version).replace(
        "@DATE@", datetime.date.today().isoformat())
    with open(os.path.join(share, "metainfo", METAINFO), "w", encoding="utf-8") as f:
        f.write(meta)
    for n in LICENSES:                  # also where Linux users look for them
        if os.path.isfile(os.path.join(lib, n)):
            shutil.copy2(os.path.join(lib, n), os.path.join(share, "doc", ID, n))
    return lib


def prune(lib):
    names = excluded_names()
    removed = []
    for d, _dirs, files in os.walk(lib):
        for n in files:
            if n in names:
                os.remove(os.path.join(d, n))
                removed.append(os.path.relpath(os.path.join(d, n), lib))
    print("Removed %d libraries the computer provides: %s" % (len(removed), ", ".join(sorted(removed))))


def check(lib, max_glibc=None, max_glibcxx=None, max_cxxabi=None, max_libgcc=None):
    problems, host, need = [], set(), {k: {} for k in VERSIONED}
    internal = os.path.join(lib, "_internal")
    names = excluded_names()
    env = dict(os.environ, LD_LIBRARY_PATH=internal)     # as the PyInstaller program runs
    for f in elf_files(lib):
        rel = os.path.relpath(f, lib)
        if os.path.basename(f) in names:
            problems.append("excluded library still in the bundle: " + rel)
        out = subprocess.run(["objdump", "-p", f], capture_output=True, text=True).stdout
        found = VERSION_NEED.findall(out)
        for name, (kind, v) in NAMED_VERSIONS.items():
            if re.search(r"\b%s\b" % name, out):
                found.append((kind, v))
                print("%s needs %s (%s %s)" % (rel, name, kind, v))
        for kind, v in found:
            if version_key(v) > version_key(need[kind].get("max", "0")):
                need[kind]["max"], need[kind]["by"] = v, rel
        if not re.search(r"^\s+NEEDED\s", out, re.M):
            continue
        r = subprocess.run(["ldd", f], capture_output=True, text=True, env=env)
        for line in r.stdout.splitlines():
            m = re.match(r"\s*(\S+) => (.*?)(?: \(0x[0-9a-f]+\))?$", line)
            if not m:
                continue
            soname, where = m.groups()
            if where == "not found":
                optional = any(o in rel for o in OPTIONAL_PLUGINS)
                (print if optional else problems.append)(
                    "%s needs %s, which is neither in the bundle nor on this machine%s"
                    % (rel, soname, " (optional plugin: ignored)" if optional else ""))
            elif not os.path.realpath(where).startswith(os.path.realpath(lib) + os.sep):
                host.add(soname)
    print("From the computer it uses: " + ", ".join(sorted(host)))
    appdir = os.path.dirname(os.path.dirname(os.path.dirname(lib)))
    if shutil.which("appstreamcli"):
        r = subprocess.run(["appstreamcli", "validate-tree", "--no-net", appdir],
                           capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            problems.append("AppStream metadata or desktop file not valid (appstreamcli)")
    else:
        print("(appstreamcli isn't installed: AppStream metadata not checked)")
    if shutil.which("desktop-file-validate"):
        r = subprocess.run(["desktop-file-validate", os.path.join(appdir, ID + ".desktop")],
                           capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode != 0:
            problems.append("desktop file not valid (desktop-file-validate)")
    for kind, limit in (("GLIBC", max_glibc), ("GLIBCXX", max_glibcxx),
                        ("CXXABI", max_cxxabi), ("GCC", max_libgcc)):
        top = need[kind].get("max")
        if top:
            print("Newest %s needed: %s (by %s)" % (kind, top, need[kind]["by"]))
            if limit and version_key(top) > version_key(limit):
                problems.append("%s needs %s_%s, newer than the oldest supported system's %s"
                                % (need[kind]["by"], kind, top, limit))
    for p in problems:
        print("ERROR: " + p, file=sys.stderr)
    if problems:
        sys.exit(1)


def du(path):
    total = 0
    for d, _dirs, files in os.walk(path):
        for n in files:
            p = os.path.join(d, n)
            if not os.path.islink(p):
                total += os.path.getsize(p)
    return total


def pack(appdir, tool, runtime, output):
    st = os.stat(tool)
    os.chmod(tool, st.st_mode | stat.S_IXUSR)
    cmd = [tool, "--no-appstream"] + (["--runtime-file", runtime] if runtime else []) + \
        [appdir, output]
    # appimagetool is itself an AppImage: without FUSE (CI machines, containers) it unpacks
    # itself and runs
    env = dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    print("+ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, env=env)
    if r.returncode != 0 or not os.path.isfile(output):
        fail("appimagetool failed (%d)" % r.returncode)
    os.chmod(output, 0o755)
    print("%s: %.1f MB" % (output, os.path.getsize(output) / 1e6))


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    a.add_argument("dist", help="the PyInstaller folder (dist/KanzonasPDF)")
    a.add_argument("appdir", help="AppDir to make (replaced if it exists)")
    a.add_argument("--version", required=True)
    a.add_argument("--max-glibc", help="fail if a bundled file needs a newer glibc")
    a.add_argument("--max-glibcxx", help="fail if a bundled file needs a newer libstdc++")
    a.add_argument("--max-cxxabi", help="fail if a bundled file needs a newer C++ ABI "
                   "(libstdc++'s CXXABI_ versions)")
    a.add_argument("--max-libgcc", help="fail if a bundled file needs a newer libgcc_s "
                   "(GCC_ versions)")
    a.add_argument("--appimagetool", help="appimagetool AppImage; without it, stop at the AppDir")
    a.add_argument("--runtime-file", help="AppImage runtime (else appimagetool downloads one)")
    a.add_argument("--output", default=APP + "-x86_64.AppImage")
    args = a.parse_args(argv)
    lib = make_appdir(args.dist, args.appdir, args.version)
    prune(lib)
    check(lib, args.max_glibc, args.max_glibcxx, args.max_cxxabi, args.max_libgcc)
    print("AppDir: %.0f MB" % (du(args.appdir) / 1e6))
    if args.appimagetool:
        pack(args.appdir, args.appimagetool, args.runtime_file, args.output)


if __name__ == "__main__":
    main()

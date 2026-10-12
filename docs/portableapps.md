# KanzonasPDF on PortableApps.com

Every Windows build makes `KanzonasPDFPortable-layout.zip` (a build artifact, not a release
download): KanzonasPDF in the PortableApps.com Format, tested in the build (it runs, keeps its
settings in the package's `Data` folder, leaves the registry alone, and its own updater is off
because the PortableApps.com Platform updates it).

Two steps need PortableApps.com's own Windows tools, so they are done by hand:

1. Unzip `KanzonasPDFPortable-layout.zip`.
2. Run the **PortableApps.com Launcher Generator** on the `KanzonasPDFPortable` folder. It makes
   `KanzonasPDFPortable.exe` from `App\AppInfo\Launcher\KanzonasPDFPortable.ini`.
3. Run the **PortableApps.com Installer** on the folder. It makes
   `KanzonasPDFPortable_<version>.paf.exe`.
4. Try it (install it into the PortableApps.com Platform, open a PDF, change a setting, close
   and reopen it), then post it in the portableapps.com forum's Development Test section.

Check the current rules first: https://portableapps.com/development and
https://portableapps.com/development/portableapps.com_format. The `appinfo.ini` format
version (3.8) and the launcher settings were written from memory; correct them in
`tools/make_portableapps.py` if the format page says otherwise.

How the package points the program at `Data`: `App\KanzonasPDF\portable.txt` contains
`data=..\..\Data` and `updates=off` (see `kanzonas/paths.py`).

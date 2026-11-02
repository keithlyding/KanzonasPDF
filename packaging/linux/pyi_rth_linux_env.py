# PyInstaller runtime hook for the Linux build (runs before KanzonasPDF's own code).
#
# The PyInstaller program starts with LD_LIBRARY_PATH pointing at its own libraries. The
# dynamic loader reads that variable once, when the process starts, so changing it now
# doesn't change which libraries KanzonasPDF itself loads; but every program KanzonasPDF
# starts inherits it: a browser or file manager opened for a link (xdg-open) would load our
# bundled, older libraries instead of its own and fail. Give children the variable the user
# had (PyInstaller keeps it in LD_LIBRARY_PATH_ORIG).
import os

_orig = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
if _orig:
    os.environ["LD_LIBRARY_PATH"] = _orig
else:
    os.environ.pop("LD_LIBRARY_PATH", None)
del _orig

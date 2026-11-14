# PyInstaller spec for Tagwave (one-folder build: fast start-up).
# Build with:  pyinstaller packaging/tagwave.spec --noconfirm
import os
import shutil

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
FFMPEG_DIR = os.environ.get("FFMPEG_DIR") or os.path.dirname(shutil.which("ffmpeg") or "")
if not os.path.isfile(os.path.join(FFMPEG_DIR, "ffmpeg.exe")):
    raise SystemExit("FFmpeg not found. Set FFMPEG_DIR to the folder containing ffmpeg.exe and ffprobe.exe.")
UI_DIST = os.path.join(ROOT, "ui", "dist")
if not os.path.isfile(os.path.join(UI_DIST, "index.html")):
    raise SystemExit("UI not built. Run `npm run build` in ui/ first.")

datas = [
    (UI_DIST, "ui"),
    (os.path.join(ROOT, "assets", "tagwave.ico"), "assets"),
    (os.path.join(ROOT, "packaging", "THIRD_PARTY_NOTICES.txt"), "."),
]
binaries = [
    (os.path.join(FFMPEG_DIR, "ffmpeg.exe"), "bin"),
    (os.path.join(FFMPEG_DIR, "ffprobe.exe"), "bin"),
]
hiddenimports = collect_submodules("tagwave") + ["clr", "clr_loader"]

for pkg in ("jpeglib", "webview", "mutagen"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# jpeglib loads its libjpeg builds with ctypes (cjpeglib_<version>.pyd), so
# PyInstaller doesn't see them as imports: bundle them explicitly.
import glob
import jpeglib as _jpeglib
_cj = os.path.join(os.path.dirname(_jpeglib.__file__), "cjpeglib")
binaries += [(p, "jpeglib/cjpeglib") for p in glob.glob(os.path.join(_cj, "cjpeglib_*.pyd"))]
datas = [d for d in datas if not d[0].endswith((".lib", ".exp"))]

a = Analysis(
    [os.path.join(ROOT, "packaging", "run_tagwave.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "_tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "cefpython3",
              "IPython", "matplotlib", "pytest", "webview.platforms.qt", "webview.platforms.gtk",
              "webview.platforms.cocoa", "webview.platforms.android", "webview.platforms.cef"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Tagwave",
    icon=os.path.join(ROOT, "assets", "tagwave.ico"),
    version=os.path.join(ROOT, "packaging", "version_info.txt"),
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Tagwave", upx=False)

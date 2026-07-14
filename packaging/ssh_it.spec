"""Cross-platform PyInstaller one-folder bundle for SSH It."""

from pathlib import Path

from PyInstaller.compat import is_darwin
from PyInstaller.utils.hooks import collect_data_files

project_root = Path(SPEC).resolve().parent.parent
data_files = collect_data_files(
    "ssh_it",
    includes=["resources/**/*.json"],
)

analysis = Analysis(
    [str(project_root / "src" / "ssh_it" / "__main__.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=data_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
# The application does not decode TIFF images. Dropping this optional plug-in avoids shipping a
# binary with an unavailable libtiff ABI on otherwise-supported Linux distributions.
analysis.binaries = [
    item
    for item in analysis.binaries
    if Path(item[0]).name.casefold() not in {"libqtiff.dylib", "libqtiff.so", "qtiff.dll"}
]
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SSH It",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SSH It",
)

if is_darwin:
    bundle = BUNDLE(
        bundle,
        name="SSH It.app",
        icon=None,
        bundle_identifier="local.ssh-it.desktop",
    )

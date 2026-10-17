# -*- mode: python ; coding: utf-8 -*-
# 돋보기 데스크톱 앱 빌드 설정. 실행: python packaging/build.py  (결과: dist/Dotbogi/Dotbogi.exe)
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "dotbogi"
VERSION = "1.0.0"

datas = [(str(PKG / "static"), "dotbogi/static")]
datas += collect_data_files("webview")
hiddenimports = collect_submodules("dotbogi") + collect_submodules("webview.platforms")

a = Analysis(
    [str(ROOT / "packaging" / "dotbogi_app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "jupyter", "notebook", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "webview.platforms.gtk", "webview.platforms.qt", "webview.platforms.cocoa", "webview.platforms.android"],
    noarchive=False,
)
# C++ 런타임: PyInstaller가 최상위에 옛 MSVCP140.dll(14.29)을 넣는 경우가 있다. 최신 MSVC로 빌드한 LightGBM이
# 이걸 먼저 잡으면 'access violation reading 0x0'으로 멈추므로(VS 2022 17.10 std::mutex 문제), 묶음 안의 최신판으로 바꾼다.
import sklearn  # noqa: E402

NEW_MSVCP = Path(sklearn.__file__).parent / ".libs" / "msvcp140.dll"
if NEW_MSVCP.exists():
    a.binaries = [(name, str(NEW_MSVCP) if name.lower() == "msvcp140.dll" else src, kind) for name, src, kind in a.binaries]
else:
    print("경고: 최신 msvcp140.dll을 찾지 못했습니다. LightGBM이 멈출 수 있습니다.")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dotbogi",
    icon=str(PKG / "static" / "img" / "dotbogi.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Dotbogi", upx=False)

# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：pyinstaller build.spec   ->  dist/智能缓存清理器.exe
import os

from PyInstaller.utils.hooks import collect_all

datas = [(os.path.join(SPECPATH, 'web'), 'web'), (os.path.join(SPECPATH, 'assets'), 'assets')]
binaries = []
hiddenimports = ['webview.platforms.winforms', 'webview.platforms.egl']

for pkg in ('webview', 'clr_loader'):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]


a = Analysis(
    [os.path.join(SPECPATH, 'app.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='智能缓存清理器',
    icon=os.path.join(SPECPATH, 'assets', 'icon.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

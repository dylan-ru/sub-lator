# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (r'C:\Users\blodon\Documents\Projects\sub-lator\.venv311\Lib\site-packages\lightning_fabric\version.info', 'lightning_fabric'),
        ('src/icons', 'src/icons'),
        ('src/icons/down_arrow.svg', '.'),
        ('src/icons/down_arrow_dark.svg', '.'),
        ('src/icons/down_arrow_white.svg', '.'),
        ('src/icons/icon.png', '.'),
        ('src/icons/moon_icon.png', '.'),
        ('src/icons/white_moon.png', '.'),
        ('src/icons/down_arrow.svg', 'src/icons'),
        ('src/icons/down_arrow_dark.svg', 'src/icons'),
        ('src/icons/down_arrow_white.svg', 'src/icons'),
        (r'C:\Users\blodon\Documents\Projects\sub-lator\.venv311\Lib\site-packages\speechbrain', 'speechbrain')
    ],
    hiddenimports=[],
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
    name='main',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['translate.ico'],
)

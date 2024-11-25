# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import site
import tkinterdnd2

# Get tkdnd package location
tkinterdnd2_path = os.path.dirname(tkinterdnd2.__file__)

block_cipher = None

a = Analysis(
    ['sequence-to-video.py'],
    pathex=[],
    binaries=[
        ('C:\\Users\\green\\OneDrive\\Documents\\ffmpeg-master-latest-win64-gpl\\bin\\ffmpeg.exe', '.')
    ],
    datas=[
        (tkinterdnd2_path, 'tkinterdnd2'),
        (os.path.join(tkinterdnd2_path, 'tkdnd'), 'tkdnd')
    ],
    hiddenimports=['tkinterdnd2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sequence-to-video',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
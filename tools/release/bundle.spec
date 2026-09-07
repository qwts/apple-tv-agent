# PyInstaller onedir build; native builds avoid cross-compiling libraries.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parents[1]
datas, binaries, hiddenimports = [], [], []
for package in ('pyatv', 'keyring', 'PIL', 'apple_tv_agent'):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
datas += copy_metadata('apple-tv-agent', recursive=True)
datas += copy_metadata('Pillow', recursive=True)
for schema in (root / 'schemas').glob('*.json'):
    datas.append((str(schema), 'apple_tv_agent'))
for guide in (root / 'docs').glob('*.md'):
    datas.append((str(guide), 'apple_tv_agent/docs'))
datas.append((str(root / 'skills/apple-tv-control'), 'apple_tv_agent/skills/apple-tv-control'))
if sys.platform == 'linux':
    hiddenimports += ['secretstorage', 'jeepney', 'keyring.backends.SecretService']
a = Analysis([str(root / 'tools/release/entrypoint.py')], pathex=[str(root / 'src')],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=['pytest', 'ruff', 'uv', 'build', 'PyInstaller'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='apple-tv-agent',
          console=True, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='apple-tv-agent', strip=False, upx=False)

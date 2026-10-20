"""Build a single-file Windows x64 receiver with the vendored driver client."""
from pathlib import Path
import os
import platform
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
if sys.platform != 'win32' or platform.architecture()[0] != '64bit':
    raise SystemExit('Use Windows with 64-bit Python.')
pc = root / 'pc'
command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
           '--windowed', '--name', 'PhoneGamepadReceiver',
           '--distpath', str(root / 'dist'), '--workpath', str(root / 'build'),
           '--specpath', str(root / 'build'), '--paths', str(pc / 'vendor'),
           '--hidden-import', 'vgamepad', '--collect-all', 'vgamepad',
           '--add-data', str(pc / 'InstallDriver.ps1') + os.pathsep + '.',
           '--add-data', str(root / 'LICENSE') + os.pathsep + '.',
           '--add-data', str(root / 'THIRD_PARTY.md') + os.pathsep + '.']
for notice in (pc / 'vendor').glob('*LICENSE.txt'):
    command += ['--add-data', str(notice) + os.pathsep + 'licenses']
command += [str(pc / 'receiver.py')]
env = dict(os.environ)
env['PYTHONPATH'] = str(pc / 'vendor') + os.pathsep + env.get('PYTHONPATH', '')
subprocess.run(command, cwd=root, env=env, check=True)
print(root / 'dist/PhoneGamepadReceiver.exe')

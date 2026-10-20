"""Build with Android SDK build-tools 35+ and JDK 17; no Gradle downloads."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import zipfile
import ctypes
import shutil

args = argparse.ArgumentParser()
args.add_argument('--sdk', default=os.environ.get('ANDROID_SDK_ROOT', r'D:\Android\Sdk'))
args.add_argument('--jdk', default=os.environ.get('JAVA_HOME', r'D:\Java\MicrosoftJDK17'))
args.add_argument('--work', required=True, help='Intermediate build and persistent signing key directory')
args.add_argument('--output', default=str(Path(__file__).resolve().parents[1] / 'phone-gamepad.apk'))
options = args.parse_args()
base = Path(__file__).resolve().parent
sdk, jdk, work = Path(options.sdk), Path(options.jdk), Path(options.work).resolve()
work.mkdir(parents=True, exist_ok=True)
def native_path(path):
    if os.name != 'nt':
        return path
    buffer = ctypes.create_unicode_buffer(32768)
    if ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)):
        return Path(buffer.value)
    return path

base, work = native_path(base), native_path(work)
tools = sdk / 'build-tools' / '35.0.0'
android = sdk / 'platforms' / 'android-35' / 'android.jar'
env = dict(os.environ, JAVA_HOME=str(jdk), PATH=str(jdk / 'bin') + os.pathsep + os.environ['PATH'])


def run(*command):
    values = []
    for item in command:
        value = str(item)
        # Some Windows SDK executables mishandle non-ASCII absolute paths.
        if Path(value).is_absolute() and any(ord(ch) > 127 for ch in value):
            value = os.path.relpath(value, work)
        values.append(value)
    subprocess.run(values, cwd=work, env=env, check=True)


generated, classes, dex = (work / name for name in ('generated', 'classes', 'dex'))
for folder in (generated, classes, dex):
    if folder.exists():
        resolved = folder.resolve()
        if resolved.parent != work.resolve() or folder.name not in ('generated', 'classes', 'dex'):
            raise RuntimeError('Refusing to clean a build path outside the chosen work directory')
        shutil.rmtree(resolved)
    folder.mkdir(exist_ok=True)
run(tools / 'aapt2.exe', 'compile', '--dir', base / 'res', '-o', work / 'resources.zip')
run(tools / 'aapt2.exe', 'link', '-I', android, '--manifest', base / 'AndroidManifest.xml',
    '--java', generated, '--min-sdk-version', '26', '--target-sdk-version', '35',
    '-o', work / 'resources.apk', work / 'resources.zip')
sources = list((base / 'src').rglob('*.java')) + list(generated.rglob('*.java'))
run(jdk / 'bin' / 'javac.exe', '-encoding', 'UTF-8', '-source', '8', '-target', '8',
    '-classpath', android, '-d', classes, *sources)
run(tools / 'd8.bat', '--release', '--min-api', '26', '--lib', android, '--output', dex,
    *classes.rglob('*.class'))
with zipfile.ZipFile(work / 'resources.apk') as source, zipfile.ZipFile(work / 'unsigned.apk', 'w') as target:
    for item in source.infolist():
        target.writestr(item, source.read(item.filename))
    target.write(dex / 'classes.dex', 'classes.dex', compress_type=zipfile.ZIP_DEFLATED)
run(tools / 'zipalign.exe', '-f', '4', work / 'unsigned.apk', work / 'aligned.apk')
keyfile = work / 'signing.json'
if keyfile.exists():
    signing = json.loads(keyfile.read_text())
else:
    signing = {'password': secrets.token_urlsafe(24)}
    keyfile.write_text(json.dumps(signing), encoding='utf-8')
keystore = work / 'phonepad.jks'
if not keystore.exists():
    run(jdk / 'bin' / 'keytool.exe', '-genkeypair', '-keystore', keystore,
        '-alias', 'phonepad', '-storepass', signing['password'], '-keypass', signing['password'],
        '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000', '-dname', 'CN=Local Coop Phone Gamepad')
output = Path(options.output).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
output = native_path(output.parent) / output.name
# Use environment options, avoiding printing signing passwords in normal tool output.
env['PHONEPAD_SIGN_PASSWORD'] = signing['password']
run(tools / 'apksigner.bat', 'sign', '--ks', keystore, '--ks-key-alias', 'phonepad',
    '--ks-pass', 'env:PHONEPAD_SIGN_PASSWORD', '--key-pass', 'env:PHONEPAD_SIGN_PASSWORD',
    '--out', output, work / 'aligned.apk')
run(tools / 'apksigner.bat', 'verify', '--verbose', output)
print('APK ready:', output)

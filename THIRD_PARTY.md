# Third-party notices

The root MIT license applies to original project code only.

- **vgamepad 0.1.0 (MIT)** — https://github.com/yannbouteiller/vgamepad ; vendored Python package and ViGEmClient DLLs in `pc/vendor/` and `keyboard/vendor/`. Original source distribution SHA256: `57f6bd01aec0c172947517fb782d150ef9b285f7f4d524c317374fa5c24a89de`. License: `vendor/VGAMEPAD_LICENSE.txt` in each component. Upstream setup.py and its old driver installer are not included/executed.
- **ViGEmClient (MIT)** — https://github.com/nefarius/ViGEmClient ; license: each `vendor/VIGEMCLIENT_LICENSE.txt`.
- **ViGEmBus (BSD 3-Clause)** — https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0 ; driver installer downloaded from the official release by `InstallDriver.ps1`. The script verifies its Windows signature and Nefarius publisher. License: each `vendor/VIGEM_LICENSE.txt`. The installer is not committed to this repository.
- **Python, Tcl/Tk, PyInstaller** — the standalone EXE bundles their runtimes/bootloader under their upstream licenses; the full Windows ZIP contains copies from the build environment. PyInstaller's bootloader exception permits distributing the bundled application under its own license.

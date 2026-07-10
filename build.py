#!/usr/bin/env python3
"""One-shot build for A.T.L.A.S.

    python build.py [--version X.Y.Z]

Steps:
  1. optional version bump in src/core/config.py
  2. icon.png → assets/atlas.ico (all standard sizes, high-quality, alpha)
  3. PyInstaller → dist/ATLAS.exe (icon embedded via atlas.spec)
  4. Inno Setup (iscc.exe) → ATLAS-Setup-v<version>.exe
  5. SHA-256 checksums
  6. everything staged in dist/release/ ready for a GitHub Release

Designed to run on Windows for a full build; on other platforms it still does
the icon + PyInstaller steps and skips Inno with a warning (so CI/dev on Linux
doesn't hard-fail). Missing icon.png → a generated placeholder + warning.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ICON_PNG = ROOT / "icon.png"
ICON_ICO = ASSETS / "atlas.ico"
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
CONFIG = ROOT / "src" / "core" / "config.py"


def read_version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', CONFIG.read_text(encoding="utf-8"))
    if not m:
        sys.exit("Could not find __version__ in config.py")
    return m.group(1)


def bump_version(new: str) -> None:
    text = CONFIG.read_text(encoding="utf-8")
    text = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{new}"', text)
    CONFIG.write_text(text, encoding="utf-8")
    print(f"[version] set to {new}")


def make_icon() -> None:
    """icon.png → assets/atlas.ico with every standard size. High-quality
    LANCZOS downscale, transparency preserved. Falls back to a generated
    placeholder if icon.png is missing — never fails the build."""
    from PIL import Image, ImageDraw

    ASSETS.mkdir(exist_ok=True)
    if ICON_PNG.exists():
        src = Image.open(ICON_PNG).convert("RGBA")
        print(f"[icon] using {ICON_PNG.name} ({src.width}x{src.height})")
    else:
        print("WARNING: icon.png not found — generating a placeholder orb icon.")
        src = _placeholder_icon()

    # square-pad so non-square art isn't distorted
    side = max(src.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(src, ((side - src.width) // 2, (side - src.height) // 2))
    frames = [canvas.resize((s, s), Image.LANCZOS) for s in ICON_SIZES]
    frames[-1].save(ICON_ICO, format="ICO",
                    sizes=[(s, s) for s in ICON_SIZES], append_images=frames[:-1])
    print(f"[icon] wrote {ICON_ICO} with sizes {ICON_SIZES}")


def _placeholder_icon():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 240, 240), outline=(109, 40, 217, 255), width=10)
    d.ellipse((56, 56, 200, 200), outline=(168, 85, 247, 255), width=14)
    d.ellipse((104, 104, 152, 152), fill=(216, 180, 254, 255))
    return img


def run_pyinstaller() -> Path:
    print("[build] PyInstaller (onedir)…")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "atlas.spec"], cwd=ROOT, check=True)
    exe = ROOT / "dist" / "ATLAS" / "ATLAS.exe"   # onedir: dist/ATLAS/ATLAS.exe
    if not exe.exists():
        sys.exit("PyInstaller did not produce dist/ATLAS/ATLAS.exe")
    folder_mb = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file()) // (1 << 20)
    print(f"[build] {exe.parent} ({folder_mb} MB folder)")
    return exe


def run_inno(version: str) -> Path | None:
    iscc = shutil.which("iscc") or shutil.which("ISCC") or \
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if sys.platform != "win32" or not Path(iscc).exists():
        print("WARNING: Inno Setup (iscc) not available — skipping installer.")
        return None
    print("[build] Inno Setup…")
    subprocess.run([iscc, f"/DMyAppVersion={version}", "installer/atlas.iss"],
                   cwd=ROOT, check=True)
    setup = ROOT / "dist" / f"ATLAS-Setup-v{version}.exe"
    if not setup.exists():
        sys.exit(f"Inno did not produce {setup}")
    print(f"[build] {setup} ({setup.stat().st_size // 1024} KB)")
    return setup


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stage_release(version: str, exe: Path, setup: Path | None) -> None:
    out = ROOT / "dist" / "release"
    out.mkdir(parents=True, exist_ok=True)
    artifacts = [setup] if setup else [exe]   # prefer the installer as the asset
    for art in artifacts:
        dst = out / art.name
        shutil.copy2(art, dst)
        digest = sha256(dst)
        (out / f"{art.name}.sha256").write_text(f"{digest}  {art.name}\n",
                                                encoding="ascii")
        print(f"[release] {dst.name}  sha256={digest}")
    print(f"[release] staged in {out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="set __version__ before building")
    args = ap.parse_args()
    if args.version:
        bump_version(args.version)
    version = read_version()
    print(f"=== Building A.T.L.A.S. v{version} ===")
    make_icon()
    exe = run_pyinstaller()
    setup = run_inno(version)
    stage_release(version, exe, setup)
    print("=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

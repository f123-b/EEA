"""Build the backend as a self-contained executable for the desktop bundle."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = [
    ROOT / "adapters" / "src",
    ROOT / "application" / "src",
    ROOT / "apps" / "backend" / "src",
    ROOT / "apps" / "cli" / "src",
    ROOT / "core" / "src",
    ROOT / "ports" / "src",
    ROOT,
]


def build(output: Path) -> Path:
    """Build and copy the platform-native PyInstaller executable."""

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    work_path = ROOT / "build" / "backend-sidecar"
    spec_path = ROOT / "build" / "backend-sidecar-spec"
    if work_path.exists():
        shutil.rmtree(work_path)
    if spec_path.exists():
        shutil.rmtree(spec_path)
    work_path.mkdir(parents=True, exist_ok=True)
    spec_path.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "eea-api",
        "--distpath",
        str(output.parent),
        "--workpath",
        str(work_path),
        "--specpath",
        str(spec_path),
        "--hidden-import",
        "eea_backend.main",
        "--hidden-import",
        "plugins.builtin.motor_control",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "IPython",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "jupyter",
        "--exclude-module",
        "PySide6",
        "--exclude-module",
        "tkinter",
    ]
    for source_root in SOURCE_ROOTS:
        command.extend(["--paths", str(source_root)])
    command.append(str(ROOT / "apps" / "backend" / "src" / "eea_backend" / "__main__.py"))
    subprocess.run(command, cwd=ROOT, check=True, env=os.environ.copy())

    generated = output.parent / ("eea-api.exe" if os.name == "nt" else "eea-api")
    if not generated.exists():
        raise RuntimeError(f"PyInstaller did not produce {generated}")
    if generated != output:
        if output.exists():
            output.unlink()
        shutil.move(str(generated), str(output))
    if not output.exists():
        raise RuntimeError(f"backend sidecar was not copied to {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_name = "eea-api.exe" if os.name == "nt" else "eea-api"
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "apps" / "desktop" / "src-tauri" / "resources" / default_name,
    )
    args = parser.parse_args()
    built = build(args.output)
    print(f"Built backend sidecar: {built}")


if __name__ == "__main__":
    main()

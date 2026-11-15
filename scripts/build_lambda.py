"""Build build/lambda/lambda.zip for the Python 3.13 x86_64 Lambda runtime.

Run with: uv run python scripts/build_lambda.py
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "lambda"
PKG = OUT / "pkg"
REQS = OUT / "requirements.txt"
ZIP = OUT / "lambda.zip"
SRC = ROOT / "src" / "telco_ops_agent"
LAMBDA_UNZIPPED_LIMIT_MB = 250


def run(*cmd: str) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def dir_size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1024**2


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1. Pin the exact locked dependencies (no dev deps, no hashes, not our own project).
    run("uv", "export", "--no-dev", "--no-hashes", "--no-emit-project", "-o", str(REQS))

    # 2. Install Linux x86_64 wheels into a clean folder (no source builds).
    if PKG.exists():
        shutil.rmtree(PKG)
    run(
        "uv", "pip", "install",
        "-r", str(REQS),
        "--target", str(PKG),
        "--python-platform", "x86_64-manylinux_2_28",
        "--python-version", "3.13",
        "--only-binary", ":all:",
    )

    # 3. Add our own code at the zip root.
    shutil.copytree(SRC, PKG / "telco_ops_agent", ignore=shutil.ignore_patterns("__pycache__"))

    # 4. Zip with forward-slash paths (Lambda runs on Linux).
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PKG.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(path, path.relative_to(PKG).as_posix())

    # 5. Report sizes.
    unzipped = dir_size_mb(PKG)
    zipped = ZIP.stat().st_size / 1024**2
    print(f"Unzipped: {unzipped:.1f} MB")
    print(f"Zip:      {zipped:.1f} MB  ->  {ZIP.relative_to(ROOT).as_posix()}")
    if unzipped > LAMBDA_UNZIPPED_LIMIT_MB:
        print(f"WARNING: over Lambda's {LAMBDA_UNZIPPED_LIMIT_MB} MB unzipped limit")


if __name__ == "__main__":
    main()

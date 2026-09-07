"""Portable launcher: ``python run.py [Streamlit options]``."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("The Shortlist requires Python 3.10 or newer.", file=sys.stderr)
        return 1

    root = Path(__file__).resolve().parent
    if importlib.util.find_spec("streamlit") is None:
        print(
            "Streamlit is not installed. Run:\n"
            f'  "{sys.executable}" -m pip install -r "{root / "requirements.txt"}"',
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(root / "app.py"),
        *(sys.argv[1:] if argv is None else argv),
    ]
    try:
        return subprocess.run(command, cwd=root, check=False).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

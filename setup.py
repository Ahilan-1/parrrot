"""
setup.py — Installs the parrrot package without requiring admin rights.

Fixes: "No module named 'parrrot'" for first-time users.

Just run:
    python setup.py

That's it. Do NOT run `python setup.py install` — that old command is
deprecated and requires admin access on Windows.

Development vs production:
  - Development (you are editing the source):  installs as editable (-e)
    so changes in this folder take effect immediately without reinstalling.
  - Production (deploying / shipping to another machine): installs normally
    so the package is self-contained and does not depend on this folder.

To force a mode:
    python setup.py dev    ← editable install (development)
    python setup.py prod   ← regular install  (production)
"""

import subprocess
import sys
import os


def _is_inside_venv() -> bool:
    return (
        hasattr(sys, "real_prefix")                          # virtualenv
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)  # venv
    )


def main(mode: str = "auto") -> None:
    if sys.version_info < (3, 11):
        print(
            f"ERROR: Parrrot requires Python 3.11 or newer.\n"
            f"You are running Python {sys.version_info.major}.{sys.version_info.minor}.\n"
            f"Download a newer version at: https://www.python.org/downloads/"
        )
        sys.exit(1)

    project_dir = os.path.dirname(os.path.abspath(__file__))

    # Decide editable vs regular install
    if mode == "dev":
        editable = True
    elif mode == "prod":
        editable = False
    else:
        # auto: editable inside a venv (dev workflow), regular otherwise (production)
        editable = _is_inside_venv()

    if editable:
        print("Development install (editable) — changes in source take effect immediately.\n")
        cmd = [sys.executable, "-m", "pip", "install", "--user", "-e", "."]
    else:
        print("Production install — package is copied into site-packages, self-contained.\n")
        cmd = [sys.executable, "-m", "pip", "install", "--user", "."]

    result = subprocess.run(cmd, cwd=project_dir)

    if result.returncode == 0:
        print("\nInstalled successfully!")
        print("You can now run:  parrrot")
        print("Or import it:     import parrrot")
        if not editable:
            print("\nNote: this folder can now be moved or deleted — the install is self-contained.")
    else:
        print("\nInstall failed. Try running manually:")
        if editable:
            print("    pip install --user -e .")
        else:
            print("    pip install --user .")

    sys.exit(result.returncode)


if __name__ == "__main__":
    # Intercept `python setup.py install` (old deprecated style)
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        print("NOTE: `python setup.py install` is deprecated and needs admin rights.")
        print("Running the correct install instead...\n")
        main(mode="auto")
    elif len(sys.argv) > 1 and sys.argv[1] == "dev":
        main(mode="dev")
    elif len(sys.argv) > 1 and sys.argv[1] == "prod":
        main(mode="prod")
    else:
        main(mode="auto")

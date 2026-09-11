#!/usr/bin/env python3
"""NEOX file-manager integration helper.

The helper configures default folder handling, opens common user directories and
provides small convenience actions used by the shell/search modules.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import run_command, run_detached, setup_logging, which

LOGGER = setup_logging("neox-file-manager-integration")

DEFAULT_FILE_MANAGERS = ["org.gnome.Nautilus.desktop", "org.kde.dolphin.desktop", "thunar.desktop", "pcmanfm.desktop"]


def find_file_manager() -> str:
    """Return a desktop id or executable for the preferred file manager."""

    configured = os.environ.get("FILE_MANAGER")
    if configured:
        return configured
    for desktop_id in DEFAULT_FILE_MANAGERS:
        if (pathlib.Path("/usr/share/applications") / desktop_id).exists():
            return desktop_id
    for executable in ("nautilus", "dolphin", "thunar", "pcmanfm"):
        if which(executable):
            return executable
    return "xdg-open"


def configure_default() -> int:
    """Set a sensible default file manager for inode/directory."""

    manager = find_file_manager()
    if manager.endswith(".desktop") and which("xdg-mime"):
        result = run_command(["xdg-mime", "default", manager, "inode/directory"], timeout=2, logger=LOGGER)
        return result.returncode
    LOGGER.info("Default file manager executable: %s", manager)
    return 0


def open_path(path: pathlib.Path) -> bool:
    """Open a path in the user's file manager."""

    manager = find_file_manager()
    target = str(path.expanduser())
    if manager.endswith(".desktop") and which("gtk-launch"):
        return run_detached(["gtk-launch", manager, target], logger=LOGGER)
    return run_detached([manager, target], logger=LOGGER)


def reveal(path: pathlib.Path) -> bool:
    """Reveal a path using xdg-open on its parent directory."""

    target = path.expanduser()
    parent = target if target.is_dir() else target.parent
    return open_path(parent)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX file manager integration")
    parser.add_argument("path", nargs="?", default=str(pathlib.Path.home()), help="path to open")
    parser.add_argument("--configure", action="store_true", help="configure default folder handler")
    parser.add_argument("--reveal", action="store_true", help="open parent folder of path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.configure:
        return configure_default()
    ok = reveal(pathlib.Path(args.path)) if args.reveal else open_path(pathlib.Path(args.path))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

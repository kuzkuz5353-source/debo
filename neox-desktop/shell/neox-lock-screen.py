#!/usr/bin/env python3
"""NEOX lock screen wrapper.

For security, NEOX delegates actual authentication to swaylock when available.
This helper prepares a blurred wallpaper/screenshot background, launches swaylock
with a mobile-inspired style, and integrates with DPMS through Hyprland keybinds.
"""

from __future__ import annotations

import argparse
import getpass
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import NEOX_RUNTIME_DIR, run_command, setup_logging, temporary_png, which

LOGGER = setup_logging("neox-lock-screen")


def create_blurred_background() -> pathlib.Path | None:
    """Capture and blur the current screen, returning a PNG path."""

    if not which("grim"):
        LOGGER.warning("grim is required to capture lock-screen background")
        return None
    screenshot = temporary_png("lock-raw")
    blurred = NEOX_RUNTIME_DIR / "neox-lock-background.png"
    result = run_command(["grim", str(screenshot)], timeout=3, logger=LOGGER)
    if result.returncode != 0:
        return None
    if which("magick"):
        run_command(["magick", str(screenshot), "-blur", "0x16", "-brightness-contrast", "-18x-5", str(blurred)], timeout=10, logger=LOGGER)
    elif which("convert"):
        run_command(["convert", str(screenshot), "-blur", "0x16", "-brightness-contrast", "-18x-5", str(blurred)], timeout=10, logger=LOGGER)
    else:
        blurred = screenshot
    return blurred if blurred.exists() else screenshot


def swaylock_args(background: pathlib.Path | None) -> list[str]:
    """Build styled swaylock command-line arguments."""

    args = [
        "swaylock",
        "--daemonize",
        "--indicator",
        "--clock",
        "--timestr", "%H:%M",
        "--datestr", "%A, %d %B",
        "--font", "Inter",
        "--font-size", "34",
        "--indicator-radius", "120",
        "--indicator-thickness", "8",
        "--inside-color", "111827cc",
        "--inside-ver-color", "3b82f6cc",
        "--inside-wrong-color", "ef4444cc",
        "--ring-color", "60a5faff",
        "--ring-ver-color", "93c5fdff",
        "--ring-wrong-color", "f87171ff",
        "--key-hl-color", "bfdbfeff",
        "--line-color", "00000000",
        "--separator-color", "00000000",
        "--text-color", "ffffffff",
        "--text-ver-color", "ffffffff",
        "--text-wrong-color", "ffffffff",
        "--fade-in", "0.25",
    ]
    if background is not None:
        args.extend(["--image", str(background), "--scaling", "fill"])
    else:
        args.extend(["--color", "0b1020"])
    return args


def lock_with_swaylock() -> int:
    """Execute swaylock with NEOX styling."""

    if not which("swaylock"):
        LOGGER.error("swaylock is not installed; secure lock screen unavailable")
        return 1
    background = create_blurred_background()
    args = swaylock_args(background)
    LOGGER.info("Locking screen for user %s", getpass.getuser())
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    except Exception as exc:
        LOGGER.exception("Cannot start swaylock: %s", exc)
        return 1
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX lock screen")
    parser.add_argument("--dpms-off", action="store_true", help="turn displays off after locking")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    code = lock_with_swaylock()
    if code == 0 and args.dpms_off:
        time.sleep(1)
        run_command(["hyprctl", "dispatch", "dpms", "off"], timeout=2, logger=LOGGER)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

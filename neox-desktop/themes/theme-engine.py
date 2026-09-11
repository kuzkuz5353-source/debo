#!/usr/bin/env python3
"""NEOX theme engine.

Applies CSS themes, maintains ``~/.config/neox/current.css``, optionally writes
GTK settings, and supports a small automatic day/night scheduler.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "shell"))

from neox_common import NEOX_CONFIG_DIR, JsonLineClient, read_json, setup_logging, write_json

LOGGER = setup_logging("neox-theme-engine")
THEME_DIRS = [pathlib.Path(__file__).resolve().parent, pathlib.Path("/usr/share/neox/themes"), NEOX_CONFIG_DIR / "themes"]
STATE_PATH = NEOX_CONFIG_DIR / "theme.json"


def available_themes() -> dict[str, pathlib.Path]:
    """Return available CSS themes by stem name."""

    themes: dict[str, pathlib.Path] = {}
    for directory in THEME_DIRS:
        if directory.exists():
            for path in directory.glob("neox-*.css"):
                themes[path.stem] = path
    return themes


def apply_theme(name: str, accent: str | None = None) -> bool:
    """Copy a theme to current.css and persist selection."""

    themes = available_themes()
    path = themes.get(name)
    if path is None:
        LOGGER.error("Theme not found: %s", name)
        return False
    NEOX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    css = path.read_text(encoding="utf-8")
    if accent and re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        css = re.sub(r"--neox-accent:\s*#[0-9a-fA-F]{6};", f"--neox-accent: {accent};", css)
    (NEOX_CONFIG_DIR / "current.css").write_text(css, encoding="utf-8")
    write_json(STATE_PATH, {"theme": name, "accent": accent or "", "updated_at": time.time()})
    _write_gtk_settings(name)
    JsonLineClient(logger=LOGGER).send("theme-changed", {"theme": name, "accent": accent or ""})
    LOGGER.info("Applied theme %s", name)
    return True


def _write_gtk_settings(name: str) -> None:
    """Write GTK settings.ini using dark preference when appropriate."""

    settings_dir = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / "gtk-4.0"
    settings_dir.mkdir(parents=True, exist_ok=True)
    prefer_dark = "1" if name in {"neox-dark", "neox-nord"} else "0"
    settings = f"[Settings]\ngtk-application-prefer-dark-theme={prefer_dark}\ngtk-theme-name=Adwaita\ngtk-icon-theme-name=Adwaita\n"
    (settings_dir / "settings.ini").write_text(settings, encoding="utf-8")


def auto_theme(day: str = "neox-light", night: str = "neox-dark") -> None:
    """Switch theme according to local hour; intended for autostart."""

    hour = time.localtime().tm_hour
    apply_theme(day if 7 <= hour < 19 else night)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX theme engine")
    parser.add_argument("theme", nargs="?", help="theme name, e.g. neox-dark")
    parser.add_argument("--accent", help="override accent color, e.g. #3b82f6")
    parser.add_argument("--list", action="store_true", help="list themes")
    parser.add_argument("--auto", action="store_true", help="apply light/dark by local time")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.list:
        for name in sorted(available_themes()):
            print(name)
        return 0
    if args.auto:
        auto_theme()
        return 0
    if not args.theme:
        state = read_json(STATE_PATH, {"theme": "neox-hd"})
        print(state.get("theme", "neox-hd"))
        return 0
    return 0 if apply_theme(args.theme, args.accent) else 1


if __name__ == "__main__":
    raise SystemExit(main())

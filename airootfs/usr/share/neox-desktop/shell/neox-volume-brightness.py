#!/usr/bin/env python3
"""NEOX volume and brightness on-screen display."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import SingletonLock, run_command, setup_logging, which

LOGGER = setup_logging("neox-volume-brightness")

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk

    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell
    except (ImportError, ValueError):
        LayerShell = None  # type: ignore[assignment]
except (ImportError, ValueError) as exc:
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    GLib = None  # type: ignore[assignment]
    LayerShell = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


def get_volume() -> tuple[int, bool]:
    """Return current PipeWire volume percent and mute state."""

    if not which("wpctl"):
        return (0, False)
    text = run_command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], timeout=1, logger=LOGGER).stdout
    match = re.search(r"([0-9.]+)", text)
    percent = int(float(match.group(1)) * 100) if match else 0
    return (percent, "MUTED" in text)


def change_volume(action: str) -> tuple[int, bool]:
    """Apply a volume action and return the new state."""

    if which("wpctl"):
        if action == "up":
            run_command(["wpctl", "set-volume", "-l", "1.5", "@DEFAULT_AUDIO_SINK@", "5%+"], timeout=1, logger=LOGGER)
        elif action == "down":
            run_command(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"], timeout=1, logger=LOGGER)
        elif action == "mute":
            run_command(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], timeout=1, logger=LOGGER)
    return get_volume()


def get_brightness() -> int:
    """Return current backlight brightness percent."""

    if not which("brightnessctl"):
        return 0
    text = run_command(["brightnessctl", "-m"], timeout=1, logger=LOGGER).stdout
    match = re.search(r",(\d+)%", text)
    return int(match.group(1)) if match else 0


def change_brightness(action: str) -> int:
    """Apply a brightness action and return the new percent."""

    if which("brightnessctl"):
        if action == "up":
            run_command(["brightnessctl", "set", "+5%"], timeout=1, logger=LOGGER)
        elif action == "down":
            run_command(["brightnessctl", "set", "5%-"], timeout=1, logger=LOGGER)
    return get_brightness()


class OSD(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """Transient layer-shell OSD for volume/brightness."""

    def __init__(self, kind: str, value: int, muted: bool = False) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.OSD")
        self.kind = kind
        self.value = max(0, min(150, value))
        self.muted = muted

    def do_activate(self) -> None:
        """Build the OSD window and auto-hide after two seconds."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX OSD")
        window.set_decorated(False)
        window.set_default_size(360, 86)
        if LayerShell is not None:
            LayerShell.init_for_window(window)
            LayerShell.set_namespace(window, "neox-osd")
            LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
            LayerShell.set_anchor(window, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_margin(window, LayerShell.Edge.BOTTOM, 96)
            LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.NONE)
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        root.add_css_class("osd")
        root.set_margin_top(14)
        root.set_margin_bottom(14)
        root.set_margin_start(18)
        root.set_margin_end(18)
        icon = Gtk.Label(label=self._icon())
        icon.add_css_class("icon")
        root.append(icon)
        scale = Gtk.LevelBar.new_for_interval(0, 100)
        scale.set_value(min(100, self.value))
        scale.set_hexpand(True)
        root.append(scale)
        label = Gtk.Label(label="Muted" if self.muted else f"{self.value}%")
        label.add_css_class("value")
        root.append(label)
        window.set_child(root)
        window.present()
        GLib.timeout_add_seconds(2, lambda: (self.quit(), False)[1])

    def _icon(self) -> str:
        """Return text icon for current OSD type."""

        if self.kind == "brightness":
            return "☀"
        if self.muted or self.value == 0:
            return "🔇"
        if self.value < 35:
            return "🔈"
        if self.value < 75:
            return "🔉"
        return "🔊"

    def _install_css(self) -> None:
        """Install OSD CSS."""

        css = """
        .osd { border-radius: 28px; background: rgba(20,20,24,0.92); color: white; border: 1px solid rgba(255,255,255,0.10); box-shadow: 0 18px 44px rgba(0,0,0,0.38); }
        .icon { font-size: 30px; }
        .value { font-weight: 900; min-width: 58px; }
        levelbar trough { min-height: 12px; border-radius: 999px; background: rgba(255,255,255,0.10); }
        levelbar block.filled { background: #60a5fa; border-radius: 999px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI args."""

    parser = argparse.ArgumentParser(description="NEOX volume/brightness OSD")
    parser.add_argument("kind", nargs="?", choices=["volume", "brightness"], help="OSD kind")
    parser.add_argument("action", nargs="?", choices=["up", "down", "mute"], help="change action")
    parser.add_argument("--daemon", action="store_true", help="keep a tiny placeholder daemon for systemd integration")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.daemon:
        LOGGER.info("OSD daemon placeholder running; keybind invocations show transient OSDs")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    if not args.kind:
        return 0
    if args.kind == "volume":
        value, muted = change_volume(args.action or "")
    else:
        value = change_brightness(args.action or "")
        muted = False
    if Gtk is None:
        print(f"{args.kind}: {'muted' if muted else str(value) + '%'}")
        return 0
    # Do not enforce singleton: repeated hardware key presses should restart the
    # short-lived OSD animation naturally.
    return OSD(args.kind, value, muted).run([])


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""NEOX logout / power menu overlay."""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import SingletonLock, run_command, setup_logging

LOGGER = setup_logging("neox-logout-screen")

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gtk

    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell
    except (ImportError, ValueError):
        LayerShell = None  # type: ignore[assignment]
except (ImportError, ValueError) as exc:
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    LayerShell = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


class LogoutScreen(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """Fullscreen mobile-style power menu."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.LogoutScreen")

    def do_activate(self) -> None:
        """Build the overlay."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX Logout")
        window.set_decorated(False)
        window.set_default_size(900, 600)
        if LayerShell is not None:
            LayerShell.init_for_window(window)
            LayerShell.set_namespace(window, "neox-logout-screen")
            LayerShell.set_layer(window, LayerShell.Layer.OVERLAY)
            for edge in (LayerShell.Edge.TOP, LayerShell.Edge.RIGHT, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT):
                LayerShell.set_anchor(window, edge, True)
            LayerShell.set_keyboard_mode(window, LayerShell.KeyboardMode.EXCLUSIVE)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        root.add_css_class("root")
        root.set_valign(Gtk.Align.CENTER)
        root.set_halign(Gtk.Align.CENTER)
        window.set_child(root)
        title = Gtk.Label(label="NEOX oturumunu yönet")
        title.add_css_class("title")
        root.append(title)
        grid = Gtk.Grid()
        grid.set_column_spacing(18)
        grid.set_row_spacing(18)
        root.append(grid)
        actions: list[tuple[str, str, Callable[[], None]]] = [
            ("Kilitle", "lock", lambda: self._run(["neox-lock-screen"])),
            ("Oturumu Kapat", "logout", lambda: self._run(["hyprctl", "dispatch", "exit"])),
            ("Uyut", "suspend", lambda: self._run(["systemctl", "suspend"])),
            ("Yeniden Başlat", "restart", lambda: self._run(["systemctl", "reboot"])),
            ("Kapat", "power", lambda: self._run(["systemctl", "poweroff"])),
            ("İptal", "cancel", self.quit),
        ]
        for index, (label, css_class, callback) in enumerate(actions):
            button = Gtk.Button(label=label)
            button.add_css_class("power-button")
            button.add_css_class(css_class)
            button.connect("clicked", lambda _button, cb=callback: cb())
            grid.attach(button, index % 3, index // 3, 1, 1)
        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", lambda _c, keyval, _kc, _st: self._escape(keyval))
        window.add_controller(key)
        window.present()

    def _escape(self, keyval: int) -> bool:
        """Close on Escape."""

        if keyval == Gdk.KEY_Escape:
            self.quit()
            return True
        return False

    def _run(self, args: list[str]) -> None:
        """Run a power/session command and close overlay."""

        LOGGER.info("Running logout action: %s", args)
        run_command(args, timeout=2, logger=LOGGER)
        self.quit()

    def _install_css(self) -> None:
        """Install logout screen CSS."""

        css = """
        .root { background: rgba(8,10,16,0.70); color: white; }
        .title { font-size: 32px; font-weight: 900; text-shadow: 0 2px 12px rgba(0,0,0,0.6); }
        .power-button { min-width: 170px; min-height: 110px; border-radius: 30px; background: rgba(255,255,255,0.10); color: white; font-size: 18px; font-weight: 800; border: 1px solid rgba(255,255,255,0.10); }
        .power-button:hover { background: rgba(59,130,246,0.30); transform: scale(1.04); }
        .power-button.power { background: rgba(239,68,68,0.28); }
        .power-button.restart { background: rgba(245,158,11,0.22); }
        .power-button.suspend { background: rgba(99,102,241,0.24); }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI args."""

    parser = argparse.ArgumentParser(description="NEOX logout screen")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    parse_args(argv or sys.argv[1:])
    if Gtk is None:
        LOGGER.error("GTK4/PyGObject is not available: %s", GTK_IMPORT_ERROR)
        return 1
    lock = SingletonLock("neox-logout-screen")
    if not lock.acquire():
        return 0
    try:
        return LogoutScreen().run([])
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

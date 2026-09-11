#!/usr/bin/env python3
"""NEOX clock widget."""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "shell"))
from neox_common import setup_logging

LOGGER = setup_logging("neox-clock-widget")

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk
except (ImportError, ValueError) as exc:
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    GLib = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


class ClockWidget(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """Small desktop clock popover."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.ClockWidget")
        self.time_label: Gtk.Label | None = None
        self.date_label: Gtk.Label | None = None

    def do_activate(self) -> None:
        """Build UI."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX Clock")
        window.set_default_size(360, 220)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.add_css_class("root")
        root.set_margin_top(24)
        root.set_margin_bottom(24)
        root.set_margin_start(24)
        root.set_margin_end(24)
        window.set_child(root)
        self.time_label = Gtk.Label(label="")
        self.time_label.add_css_class("time")
        self.date_label = Gtk.Label(label="")
        self.date_label.add_css_class("date")
        root.append(self.time_label)
        root.append(self.date_label)
        GLib.timeout_add_seconds(1, self.tick)
        self.tick()
        window.present()

    def tick(self) -> bool:
        """Refresh displayed date/time."""

        now = time.localtime()
        if self.time_label is not None:
            self.time_label.set_label(time.strftime("%H:%M:%S", now))
        if self.date_label is not None:
            self.date_label.set_label(time.strftime("%A, %d %B %Y", now))
        return True

    def _install_css(self) -> None:
        """Install CSS."""

        css = ".root{background:#111827;color:white;border-radius:24px}.time{font-size:56px;font-weight:900}.date{font-size:18px;color:rgba(255,255,255,.72)}"
        provider = Gtk.CssProvider(); provider.load_from_data(css.encode())
        display = Gdk.Display.get_default()
        if display: Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def main() -> int:
    """Entry point."""

    if Gtk is None:
        LOGGER.error("GTK unavailable: %s", GTK_IMPORT_ERROR)
        return 1
    return ClockWidget().run([])


if __name__ == "__main__":
    raise SystemExit(main())

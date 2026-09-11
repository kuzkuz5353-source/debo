#!/usr/bin/env python3
"""NEOX calendar widget."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "shell"))
from neox_common import setup_logging

LOGGER = setup_logging("neox-calendar-widget")

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gtk
except (ImportError, ValueError) as exc:
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


class CalendarWidget(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """Calendar popover with GTK Calendar."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.CalendarWidget")

    def do_activate(self) -> None:
        """Build UI."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX Calendar")
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.add_css_class("root")
        root.set_margin_top(18); root.set_margin_bottom(18); root.set_margin_start(18); root.set_margin_end(18)
        title = Gtk.Label(label="Takvim")
        title.add_css_class("title")
        calendar = Gtk.Calendar()
        root.append(title); root.append(calendar)
        window.set_child(root)
        window.present()

    def _install_css(self) -> None:
        """Install CSS."""

        css = ".root{background:#111827;color:white;border-radius:24px}.title{font-size:24px;font-weight:900} calendar{padding:10px}"
        provider = Gtk.CssProvider(); provider.load_from_data(css.encode())
        display = Gdk.Display.get_default()
        if display: Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def main() -> int:
    """Entry point."""

    if Gtk is None:
        LOGGER.error("GTK unavailable: %s", GTK_IMPORT_ERROR)
        return 1
    return CalendarWidget().run([])


if __name__ == "__main__":
    raise SystemExit(main())

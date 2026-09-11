#!/usr/bin/env python3
"""NEOX MPRIS media player widget powered by playerctl."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "shell"))
from neox_common import run_command, setup_logging, which

LOGGER = setup_logging("neox-media-player-widget")

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


class MediaPlayerWidget(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """Small media controls widget."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.MediaPlayerWidget")
        self.label: Gtk.Label | None = None

    def do_activate(self) -> None:
        """Build UI."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX Media")
        window.set_default_size(440, 220)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.add_css_class("root")
        root.set_margin_top(22); root.set_margin_bottom(22); root.set_margin_start(22); root.set_margin_end(22)
        self.label = Gtk.Label(label="Medya yok")
        self.label.add_css_class("title")
        root.append(self.label)
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls.set_halign(Gtk.Align.CENTER)
        for text, cmd in (("⏮", "previous"), ("⏯", "play-pause"), ("⏭", "next")):
            button = Gtk.Button(label=text); button.connect("clicked", lambda _b, c=cmd: self.playerctl(c)); controls.append(button)
        root.append(controls)
        window.set_child(root)
        GLib.timeout_add_seconds(2, self.tick)
        self.tick(); window.present()

    def playerctl(self, command: str) -> None:
        """Run playerctl command."""

        if which("playerctl"):
            run_command(["playerctl", command], timeout=2, logger=LOGGER)
            self.tick()

    def tick(self) -> bool:
        """Refresh metadata."""

        if self.label is not None and which("playerctl"):
            result = run_command(["playerctl", "metadata", "--format", "{{artist}}\n{{title}}"], timeout=1, logger=LOGGER)
            self.label.set_label(result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "Medya yok")
        return True

    def _install_css(self) -> None:
        """Install CSS."""

        css = ".root{background:#111827;color:white;border-radius:24px}.title{font-size:22px;font-weight:900} button{border-radius:999px;min-width:58px;min-height:46px;background:rgba(255,255,255,.1);color:white}"
        provider = Gtk.CssProvider(); provider.load_from_data(css.encode())
        display = Gdk.Display.get_default()
        if display: Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def main() -> int:
    """Entry point."""

    if Gtk is None:
        LOGGER.error("GTK unavailable: %s", GTK_IMPORT_ERROR)
        return 1
    return MediaPlayerWidget().run([])


if __name__ == "__main__":
    raise SystemExit(main())

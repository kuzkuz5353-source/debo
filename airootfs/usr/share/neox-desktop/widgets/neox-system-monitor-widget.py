#!/usr/bin/env python3
"""NEOX system monitor widget."""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "shell"))
from neox_common import run_command, setup_logging, which

LOGGER = setup_logging("neox-system-monitor-widget")

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

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


class SystemMonitorWidget(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """CPU/RAM/disk monitor widget."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.SystemMonitorWidget")
        self.cpu = None; self.mem = None; self.disk = None

    def do_activate(self) -> None:
        """Build UI."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX System Monitor")
        window.set_default_size(420, 260)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        root.add_css_class("root")
        root.set_margin_top(22); root.set_margin_bottom(22); root.set_margin_start(22); root.set_margin_end(22)
        title = Gtk.Label(label="Sistem Monitörü"); title.add_css_class("title"); root.append(title)
        self.cpu = self._bar("CPU", root)
        self.mem = self._bar("Bellek", root)
        self.disk = self._bar("Disk", root)
        window.set_child(root)
        GLib.timeout_add_seconds(1, self.tick)
        self.tick(); window.present()

    def _bar(self, label: str, root: Gtk.Box) -> Gtk.LevelBar:
        """Add a label+level bar."""

        root.append(Gtk.Label(label=label))
        bar = Gtk.LevelBar.new_for_interval(0, 100); bar.set_value(0); root.append(bar); return bar

    def tick(self) -> bool:
        """Refresh metrics."""

        try:
            if psutil is not None:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
                disk = psutil.disk_usage(str(pathlib.Path.home())).percent
            else:
                cpu = float(run_command(["bash", "-lc", "awk '{u=$2+$4; t=$2+$4+$5} END{print int(u*100/t)}' /proc/stat"], timeout=1, logger=LOGGER).stdout or 0)
                meminfo = pathlib.Path("/proc/meminfo").read_text().splitlines()
                values = {line.split(':')[0]: int(line.split()[1]) for line in meminfo if line}
                mem = (1 - values.get("MemAvailable", 0) / max(1, values.get("MemTotal", 1))) * 100
                disk = 0.0
            for bar, value in ((self.cpu, cpu), (self.mem, mem), (self.disk, disk)):
                if bar is not None: bar.set_value(float(value))
        except Exception as exc:
            LOGGER.debug("Metric refresh failed: %s", exc)
        return True

    def _install_css(self) -> None:
        """Install CSS."""

        css = ".root{background:#111827;color:white;border-radius:24px}.title{font-size:24px;font-weight:900} levelbar block.filled{background:#60a5fa}"
        provider = Gtk.CssProvider(); provider.load_from_data(css.encode())
        display = Gdk.Display.get_default()
        if display: Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def main() -> int:
    """Entry point."""

    if Gtk is None:
        LOGGER.error("GTK unavailable: %s", GTK_IMPORT_ERROR)
        return 1
    return SystemMonitorWidget().run([])


if __name__ == "__main__":
    raise SystemExit(main())

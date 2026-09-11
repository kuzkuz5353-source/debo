#!/usr/bin/env python3
"""NEOX weather widget using wttr.in JSON when network is available."""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "shell"))
from neox_common import ConfigManager, setup_logging

LOGGER = setup_logging("neox-weather-widget")

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


class WeatherWidget(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """Weather card widget."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.WeatherWidget")
        self.config = ConfigManager()
        self.label: Gtk.Label | None = None

    def do_activate(self) -> None:
        """Build UI and start network fetch."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX Weather")
        window.set_default_size(380, 220)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.add_css_class("root")
        root.set_margin_top(22); root.set_margin_bottom(22); root.set_margin_start(22); root.set_margin_end(22)
        title = Gtk.Label(label="Hava Durumu")
        title.add_css_class("title")
        self.label = Gtk.Label(label="Yükleniyor…")
        self.label.add_css_class("weather")
        root.append(title); root.append(self.label)
        window.set_child(root)
        window.present()
        threading.Thread(target=self.fetch, daemon=True).start()

    def fetch(self) -> None:
        """Fetch weather data in a background thread."""

        location = self.config.get("widgets", "weather_location", "Istanbul")
        url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            current = payload["current_condition"][0]
            text = f"{location}\n{current['temp_C']}°C · {current['weatherDesc'][0]['value']}\nNem {current['humidity']}% · Rüzgar {current['windspeedKmph']} km/s"
        except Exception as exc:
            LOGGER.warning("Weather fetch failed: %s", exc)
            text = "Hava durumu alınamadı"
        GLib.idle_add(lambda: (self.label.set_label(text) if self.label else None, False)[1])

    def _install_css(self) -> None:
        """Install CSS."""

        css = ".root{background:#111827;color:white;border-radius:24px}.title{font-size:24px;font-weight:900}.weather{font-size:18px;color:rgba(255,255,255,.78)}"
        provider = Gtk.CssProvider(); provider.load_from_data(css.encode())
        display = Gdk.Display.get_default()
        if display: Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def main() -> int:
    """Entry point."""

    if Gtk is None:
        LOGGER.error("GTK unavailable: %s", GTK_IMPORT_ERROR)
        return 1
    return WeatherWidget().run([])


if __name__ == "__main__":
    raise SystemExit(main())

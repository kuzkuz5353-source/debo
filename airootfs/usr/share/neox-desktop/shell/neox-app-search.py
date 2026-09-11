#!/usr/bin/env python3
"""Standalone NEOX application search overlay.

This helper shares the desktop-entry index with the Dynamic Island and can run as
a compact layer-shell search UI or as a CLI fallback when GTK is unavailable.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import DesktopAppScanner, DesktopEntry, SingletonLock, run_command, safe_eval_math, setup_logging, which

LOGGER = setup_logging("neox-app-search")

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk, Pango

    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell
    except (ImportError, ValueError):
        LayerShell = None  # type: ignore[assignment]
except (ImportError, ValueError) as exc:  # pragma: no cover - GUI dependency.
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    GLib = None  # type: ignore[assignment]
    Pango = None  # type: ignore[assignment]
    LayerShell = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


@dataclass(slots=True)
class Result:
    """Search result model."""

    title: str
    subtitle: str
    icon: str
    action: Callable[[], None]


class SearchOverlay(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK search overlay shown below the Dynamic Island area."""

    def __init__(self, initial_query: str = "") -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.Search")
        self.initial_query = initial_query
        self.scanner = DesktopAppScanner(logger=LOGGER)
        self.results: list[Result] = []
        self.selected = 0
        self.window: Gtk.ApplicationWindow | None = None
        self.entry: Gtk.SearchEntry | None = None
        self.result_box: Gtk.Box | None = None

    def do_activate(self) -> None:
        """Build the overlay and focus the search entry."""

        self._install_css()
        self.scanner.scan(force=False)
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX Search")
        self.window.set_decorated(False)
        self.window.set_default_size(900, 520)
        if LayerShell is not None:
            LayerShell.init_for_window(self.window)
            LayerShell.set_namespace(self.window, "neox-search")
            LayerShell.set_layer(self.window, LayerShell.Layer.TOP)
            LayerShell.set_anchor(self.window, LayerShell.Edge.TOP, True)
            LayerShell.set_margin(self.window, LayerShell.Edge.TOP, 78)
            LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.EXCLUSIVE)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_top(18)
        outer.set_margin_bottom(18)
        outer.set_margin_start(18)
        outer.set_margin_end(18)
        outer.add_css_class("neox-search-window")
        self.window.set_child(outer)

        self.entry = Gtk.SearchEntry()
        self.entry.set_placeholder_text("Uygulama, anahtar kelime, hesaplama veya web ara…")
        self.entry.connect("search-changed", lambda entry: self.update(entry.get_text()))
        self.entry.connect("activate", lambda _entry: self.activate_selected())
        outer.append(self.entry)

        self.result_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.append(self.result_box)

        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self.on_key)
        self.window.add_controller(key)
        self.window.present()
        self.entry.set_text(self.initial_query)
        self.entry.grab_focus()
        self.update(self.initial_query)

    def build_results(self, query: str) -> list[Result]:
        """Return calculator, app and web results for query."""

        query = query.strip()
        results: list[Result] = []
        value = safe_eval_math(query) if query else None
        if value is not None:
            text = str(int(value) if value.is_integer() else round(value, 8))
            results.append(Result(text, "Hesap makinesi sonucu", "accessories-calculator-symbolic", lambda: self.copy(text)))
        for app in self.scanner.fuzzy_search(query, limit=8):
            results.append(Result(app.name, app.comment or app.exec, app.icon or "application-x-executable-symbolic", lambda item=app: self.launch(item)))
        if query:
            results.append(Result(f"Web'de ara: {query}", "Varsayılan tarayıcı", "web-browser-symbolic", lambda: self.web(query)))
        return results[:8]

    def update(self, query: str) -> None:
        """Update result rows."""

        self.results = self.build_results(query)
        self.selected = 0
        if self.result_box is None:
            return
        while child := self.result_box.get_first_child():
            self.result_box.remove(child)
        for index, result in enumerate(self.results):
            button = Gtk.Button()
            button.add_css_class("neox-search-row")
            button.connect("clicked", lambda _button, i=index: self.activate(i))
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_top(9)
            row.set_margin_bottom(9)
            row.set_margin_start(12)
            row.set_margin_end(12)
            icon = Gtk.Image.new_from_file(result.icon) if pathlib.Path(result.icon).exists() else Gtk.Image.new_from_icon_name(result.icon)
            icon.set_pixel_size(32)
            row.append(icon)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            title = Gtk.Label(label=result.title)
            title.set_xalign(0)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.add_css_class("title")
            subtitle = Gtk.Label(label=result.subtitle)
            subtitle.set_xalign(0)
            subtitle.set_ellipsize(Pango.EllipsizeMode.END)
            subtitle.add_css_class("subtitle")
            labels.append(title)
            labels.append(subtitle)
            row.append(labels)
            button.set_child(row)
            self.result_box.append(button)
        self.highlight()

    def highlight(self) -> None:
        """Highlight selected row."""

        if self.result_box is None:
            return
        child = self.result_box.get_first_child()
        index = 0
        while child is not None:
            if index == self.selected:
                child.add_css_class("selected")
            else:
                child.remove_css_class("selected")
            child = child.get_next_sibling()
            index += 1

    def on_key(self, _controller: Gtk.EventControllerKey, keyval: int, _keycode: int, _state: int) -> bool:
        """Keyboard result navigation."""

        if keyval == Gdk.KEY_Escape:
            self.quit()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self.selected = min(len(self.results) - 1, self.selected + 1)
            self.highlight()
            return True
        if keyval == Gdk.KEY_Up:
            self.selected = max(0, self.selected - 1)
            self.highlight()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate_selected()
            return True
        return False

    def activate_selected(self) -> None:
        """Activate selected result."""

        self.activate(self.selected)

    def activate(self, index: int) -> None:
        """Run a result action and exit."""

        if 0 <= index < len(self.results):
            self.results[index].action()
        self.quit()

    def launch(self, app: DesktopEntry) -> None:
        """Launch an application."""

        app.launch(LOGGER)

    def copy(self, text: str) -> None:
        """Copy calculator result to clipboard."""

        if which("wl-copy"):
            run_command(["wl-copy"], input_text=text, logger=LOGGER)

    def web(self, query: str) -> None:
        """Search the web."""

        os.spawnlp(os.P_NOWAIT, "xdg-open", "xdg-open", f"https://www.google.com/search?q={query.replace(' ', '+')}")

    def _install_css(self) -> None:
        """Install CSS for search overlay."""

        css = """
        .neox-search-window {
            border-radius: 30px;
            background: rgba(16,18,24,0.94);
            color: white;
            box-shadow: 0 24px 60px rgba(0,0,0,0.45);
            border: 1px solid rgba(255,255,255,0.08);
        }
        searchentry, entry { min-height: 46px; border-radius: 24px; padding: 0 16px; background: rgba(255,255,255,0.10); color: white; }
        .neox-search-row { border-radius: 18px; background: transparent; color: white; border: 0; }
        .neox-search-row:hover, .neox-search-row.selected { background: rgba(59,130,246,0.24); }
        .title { font-weight: 800; color: white; }
        .subtitle { font-size: 12px; color: rgba(255,255,255,0.62); }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def run_cli(query: str) -> int:
    """Fallback CLI mode useful over SSH or while GTK dependencies are missing."""

    scanner = DesktopAppScanner(logger=LOGGER)
    scanner.scan(force=False)
    for index, app in enumerate(scanner.fuzzy_search(query, limit=10), start=1):
        print(f"{index:2d}. {app.name} — {app.comment}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI args."""

    parser = argparse.ArgumentParser(description="NEOX application search")
    parser.add_argument("query", nargs="*", help="initial search query")
    parser.add_argument("--cli", action="store_true", help="print results instead of opening GTK UI")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    query = " ".join(args.query)
    if args.cli or Gtk is None:
        if Gtk is None:
            LOGGER.warning("GTK UI unavailable, using CLI: %s", GTK_IMPORT_ERROR)
        return run_cli(query)
    lock = SingletonLock("neox-app-search")
    if not lock.acquire():
        return 0
    try:
        return SearchOverlay(query).run([])
    except Exception as exc:
        LOGGER.exception("Search crashed: %s", exc)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""NEOX Dynamic Island panel.

The panel is a GTK4 layer-shell surface anchored at the top center of the screen.
It provides clock/date, active window title, app search, media controls, basic
status indicators and notification previews with mobile-style expansion.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import (  # noqa: E402
    ConfigManager,
    DesktopAppScanner,
    DesktopEntry,
    HyprlandIPC,
    JsonLineClient,
    SingletonLock,
    run_command,
    safe_eval_math,
    setup_logging,
    which,
)
from neox_hd_ui import load_hd_css  # noqa: E402

LOGGER = setup_logging("neox-panel")

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
class SearchResult:
    """Result row rendered by the Dynamic Island search dropdown."""

    title: str
    subtitle: str
    icon: str
    action: Callable[[], None]


class DynamicIsland(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK application implementing the top Dynamic Island."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.Panel")
        self.config = ConfigManager()
        self.hyprland = HyprlandIPC(LOGGER)
        self.scanner = DesktopAppScanner(logger=LOGGER)
        self.bus = JsonLineClient(logger=LOGGER)
        self.compact_width = self.config.getint("panel", "width", 400)
        self.compact_height = self.config.getint("panel", "height", 40)
        self.expanded_width_percent = self.config.getint("panel", "expanded_width_percent", 70)
        self.current_width = self.compact_width
        self.current_height = self.compact_height
        self.mode = "compact"
        self.selected_result = 0
        self.results: list[SearchResult] = []
        self.window: Gtk.ApplicationWindow | None = None
        self.island: Gtk.Box | None = None
        self.compact_box: Gtk.Box | None = None
        self.search_box: Gtk.Box | None = None
        self.media_box: Gtk.Box | None = None
        self.result_box: Gtk.Box | None = None
        self.search_entry: Gtk.SearchEntry | None = None
        self.clock_label: Gtk.Label | None = None
        self.date_label: Gtk.Label | None = None
        self.center_label: Gtk.Label | None = None
        self.status_label: Gtk.Label | None = None
        self.media_title: Gtk.Label | None = None
        self.notification_revealer: Gtk.Revealer | None = None
        self.notification_label: Gtk.Label | None = None

    def do_activate(self) -> None:
        """Build UI and start periodic status refresh timers."""

        self._install_css()
        self.scanner.scan(force=False)
        self.scanner.watch(lambda apps: GLib.idle_add(self._apps_changed, apps))
        self._build_window()
        GLib.timeout_add_seconds(1, self._tick_clock)
        GLib.timeout_add_seconds(1, self._tick_active_window)
        GLib.timeout_add_seconds(3, self._tick_status)
        GLib.timeout_add_seconds(3, self._tick_media)

    def _build_window(self) -> None:
        """Create the top-center layer-shell surface."""

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX Dynamic Island")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_default_size(self.compact_width, 140)

        if LayerShell is not None:
            LayerShell.init_for_window(self.window)
            LayerShell.set_namespace(self.window, "neox-panel")
            LayerShell.set_layer(self.window, LayerShell.Layer.TOP)
            LayerShell.set_anchor(self.window, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self.window, LayerShell.Edge.LEFT, False)
            LayerShell.set_anchor(self.window, LayerShell.Edge.RIGHT, False)
            LayerShell.set_margin(self.window, LayerShell.Edge.TOP, 10)
            LayerShell.set_exclusive_zone(self.window, 0)
            LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.ON_DEMAND)
        else:
            LOGGER.warning("gtk4-layer-shell not available; panel is a normal window")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_valign(Gtk.Align.START)
        outer.add_css_class("neox-panel-outer")
        self.window.set_child(outer)

        self.island = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.island.add_css_class("neox-island")
        self.island.set_size_request(self.compact_width, self.compact_height)
        outer.append(self.island)

        self.compact_box = self._build_compact_box()
        self.search_box = self._build_search_box()
        self.media_box = self._build_media_box()
        self.island.append(self.compact_box)
        self.island.append(self.search_box)
        self.island.append(self.media_box)
        self.search_box.set_visible(False)
        self.media_box.set_visible(False)

        self.notification_revealer = Gtk.Revealer()
        self.notification_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.notification_revealer.set_transition_duration(300)
        self.notification_label = Gtk.Label(label="")
        self.notification_label.add_css_class("neox-notification-preview")
        self.notification_revealer.set_child(self.notification_label)
        outer.append(self.notification_revealer)

        self.result_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.result_box.add_css_class("neox-search-results")
        self.result_box.set_visible(False)
        outer.append(self.result_box)

        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self._on_key_pressed)
        self.window.add_controller(key)

        self._tick_clock()
        self._tick_status()
        self.window.present()

    def _build_compact_box(self) -> Gtk.Box:
        """Build the normal 400x40 compact island layout."""

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_start(14)
        row.set_margin_end(14)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        row.set_valign(Gtk.Align.CENTER)

        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        left.set_hexpand(True)
        self.clock_label = Gtk.Label(label="--:--")
        self.clock_label.add_css_class("neox-clock")
        self.date_label = Gtk.Label(label="--")
        self.date_label.add_css_class("neox-date")
        clock_click = Gtk.GestureClick.new()
        clock_click.connect("pressed", lambda *_args: self._launch_widget("neox-calendar-widget"))
        left.add_controller(clock_click)
        left.append(self.clock_label)
        left.append(self.date_label)
        row.append(left)

        search_button = Gtk.Button(label="⌕")
        search_button.set_tooltip_text("Ara")
        search_button.add_css_class("neox-panel-button")
        search_button.connect("clicked", lambda _button: self.enter_search_mode())
        row.append(search_button)

        self.center_label = Gtk.Label(label="NEOX")
        self.center_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.center_label.set_max_width_chars(22)
        self.center_label.add_css_class("neox-active-title")
        self.center_label.set_hexpand(True)
        row.append(self.center_label)

        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        right.set_hexpand(True)
        right.set_halign(Gtk.Align.END)
        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("neox-status")
        right.append(self.status_label)
        bell = Gtk.Button(label="◌")
        bell.add_css_class("neox-panel-button")
        bell.set_tooltip_text("Bildirim merkezi")
        bell.connect("clicked", lambda _button: self._launch_helper("neox-notification-center"))
        right.append(bell)
        row.append(right)
        return row

    def _build_search_box(self) -> Gtk.Box:
        """Build the expanded search input row."""

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_start(18)
        row.set_margin_end(18)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        icon = Gtk.Label(label="⌕")
        icon.add_css_class("neox-search-icon")
        row.append(icon)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Uygulama, dosya, hesaplama veya web ara…")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("activate", lambda _entry: self._activate_selected_result())
        row.append(self.search_entry)
        close_button = Gtk.Button(label="×")
        close_button.add_css_class("neox-panel-button")
        close_button.connect("clicked", lambda _button: self.leave_search_mode())
        row.append(close_button)
        return row

    def _build_media_box(self) -> Gtk.Box:
        """Build media playback expansion row."""

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_start(16)
        row.set_margin_end(16)
        row.set_margin_top(6)
        row.set_margin_bottom(6)
        art = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        art.set_pixel_size(36)
        row.append(art)
        self.media_title = Gtk.Label(label="")
        self.media_title.set_ellipsize(Pango.EllipsizeMode.END)
        self.media_title.set_hexpand(True)
        self.media_title.add_css_class("neox-media-title")
        row.append(self.media_title)
        for label, command in (("⏮", "previous"), ("⏯", "play-pause"), ("⏭", "next")):
            button = Gtk.Button(label=label)
            button.add_css_class("neox-panel-button")
            button.connect("clicked", lambda _button, cmd=command: self._playerctl(cmd))
            row.append(button)
        return row

    def enter_search_mode(self) -> None:
        """Expand into search mode and focus the input."""

        if self.mode == "search":
            return
        self.mode = "search"
        if self.compact_box is not None:
            self.compact_box.set_visible(False)
        if self.media_box is not None:
            self.media_box.set_visible(False)
        if self.search_box is not None:
            self.search_box.set_visible(True)
        if self.search_entry is not None:
            self.search_entry.set_text("")
            self.search_entry.grab_focus()
        self._animate_to(self._expanded_width(), 60)
        self._update_results("")

    def leave_search_mode(self) -> None:
        """Return to the compact island state."""

        self.mode = "compact"
        if self.result_box is not None:
            self.result_box.set_visible(False)
        if self.search_box is not None:
            self.search_box.set_visible(False)
        if self.media_box is not None:
            self.media_box.set_visible(False)
        if self.compact_box is not None:
            self.compact_box.set_visible(True)
        self._animate_to(self.compact_width, self.compact_height)

    def enter_media_mode(self, title: str) -> None:
        """Temporarily expand for media playback metadata."""

        if self.mode == "search":
            return
        self.mode = "media"
        if self.compact_box is not None:
            self.compact_box.set_visible(False)
        if self.search_box is not None:
            self.search_box.set_visible(False)
        if self.media_box is not None:
            self.media_box.set_visible(True)
        if self.media_title is not None:
            self.media_title.set_label(title)
        self._animate_to(min(self._expanded_width(), 620), 50)

    def show_notification_preview(self, title: str, body: str, critical: bool = False) -> None:
        """Show a notification preview below the island for three seconds."""

        if self.notification_label is not None:
            self.notification_label.set_label(f"{title}\n{body}")
            if critical:
                self.notification_label.add_css_class("critical")
            else:
                self.notification_label.remove_css_class("critical")
        if self.notification_revealer is not None:
            self.notification_revealer.set_reveal_child(True)
            GLib.timeout_add_seconds(3, self._hide_notification_preview)

    def _hide_notification_preview(self) -> bool:
        """Hide the notification preview revealer."""

        if self.notification_revealer is not None:
            self.notification_revealer.set_reveal_child(False)
        return False

    def _expanded_width(self) -> int:
        """Return 70% of monitor width, with a safe fallback."""

        display = Gdk.Display.get_default()
        if display is None:
            return 900
        monitors = display.get_monitors()
        monitor = monitors.get_item(0) if monitors.get_n_items() else None
        if monitor is None:
            return 900
        geometry = monitor.get_geometry()
        return int(geometry.width * self.expanded_width_percent / 100)

    def _animate_to(self, target_width: int, target_height: int) -> None:
        """Animate island size over 300 ms using an ease-out curve."""

        if self.island is None:
            return
        start_width = self.current_width
        start_height = self.current_height
        started = time.monotonic()
        duration = 0.30

        def ease(t: float) -> float:
            return 1 - pow(1 - t, 3)

        def frame() -> bool:
            elapsed = time.monotonic() - started
            progress = min(1.0, elapsed / duration)
            amount = ease(progress)
            width = int(start_width + (target_width - start_width) * amount)
            height = int(start_height + (target_height - start_height) * amount)
            if self.island is not None:
                self.island.set_size_request(width, height)
            self.current_width = width
            self.current_height = height
            return progress < 1.0

        GLib.timeout_add(16, frame)

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Update result dropdown as the user types."""

        self._update_results(entry.get_text())

    def _update_results(self, query: str) -> None:
        """Populate search result widgets."""

        self.results = self._build_results(query)
        self.selected_result = 0
        if self.result_box is None:
            return
        while child := self.result_box.get_first_child():
            self.result_box.remove(child)
        for index, result in enumerate(self.results[:8]):
            row = self._result_row(index, result)
            self.result_box.append(row)
        self.result_box.set_visible(bool(self.results))
        self._highlight_selected_result()

    def _build_results(self, query: str) -> list[SearchResult]:
        """Build app, calculator and web search results."""

        query = query.strip()
        results: list[SearchResult] = []
        if query:
            value = safe_eval_math(query)
            if value is not None and re.search(r"\d", query):
                display = int(value) if value.is_integer() else round(value, 8)
                results.append(
                    SearchResult(
                        title=str(display),
                        subtitle="Hesap makinesi sonucu — Enter ile panoya kopyala",
                        icon="accessories-calculator-symbolic",
                        action=lambda text=str(display): self._copy_text(text),
                    )
                )
        apps = self.scanner.fuzzy_search(query, limit=8 if query else 5)
        for app in apps:
            results.append(
                SearchResult(
                    title=app.name,
                    subtitle=app.comment or app.exec,
                    icon=app.icon or "application-x-executable-symbolic",
                    action=lambda desktop_app=app: self._launch_app(desktop_app),
                )
            )
        if query:
            results.append(
                SearchResult(
                    title=f"Web'de ara: {query}",
                    subtitle="Varsayılan tarayıcıda arama yap",
                    icon="web-browser-symbolic",
                    action=lambda text=query: self._web_search(text),
                )
            )
        return results[:8]

    def _result_row(self, index: int, result: SearchResult) -> Gtk.Button:
        """Create a clickable result row."""

        button = Gtk.Button()
        button.add_css_class("neox-result-row")
        button.connect("clicked", lambda _button: self._activate_result(index))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_start(12)
        row.set_margin_end(12)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        icon = Gtk.Image.new_from_file(result.icon) if pathlib.Path(result.icon).exists() else Gtk.Image.new_from_icon_name(result.icon)
        icon.set_pixel_size(28)
        row.append(icon)
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=result.title)
        title.set_xalign(0.0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.add_css_class("neox-result-title")
        subtitle = Gtk.Label(label=result.subtitle)
        subtitle.set_xalign(0.0)
        subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        subtitle.add_css_class("neox-result-subtitle")
        text_box.append(title)
        text_box.append(subtitle)
        row.append(text_box)
        button.set_child(row)
        return button

    def _highlight_selected_result(self) -> None:
        """Apply selected CSS class to the current result row."""

        if self.result_box is None:
            return
        child = self.result_box.get_first_child()
        index = 0
        while child is not None:
            if isinstance(child, Gtk.Widget):
                if index == self.selected_result:
                    child.add_css_class("selected")
                else:
                    child.remove_css_class("selected")
            child = child.get_next_sibling()
            index += 1

    def _activate_selected_result(self) -> None:
        """Activate the currently highlighted result."""

        self._activate_result(self.selected_result)

    def _activate_result(self, index: int) -> None:
        """Run a result action and collapse the island."""

        if 0 <= index < len(self.results):
            try:
                self.results[index].action()
            except Exception as exc:
                LOGGER.exception("Search result action failed: %s", exc)
        self.leave_search_mode()

    def _launch_app(self, app: DesktopEntry) -> None:
        """Launch an app from search results."""

        if not app.launch(LOGGER):
            self.show_notification_preview("NEOX", f"{app.name} başlatılamadı")

    def _copy_text(self, text: str) -> None:
        """Copy text to the Wayland clipboard."""

        if which("wl-copy"):
            run_command(["wl-copy"], input_text=text, timeout=2, logger=LOGGER)
        else:
            self.show_notification_preview("NEOX", text)

    def _web_search(self, query: str) -> None:
        """Open the default browser with a web search."""

        encoded = query.replace(" ", "+")
        os.spawnlp(os.P_NOWAIT, "xdg-open", "xdg-open", f"https://www.google.com/search?q={encoded}")

    def _on_key_pressed(self, _controller: Gtk.EventControllerKey, keyval: int, _keycode: int, _state: int) -> bool:
        """Handle search navigation keys and panel shortcuts."""

        if keyval == Gdk.KEY_Escape and self.mode == "search":
            self.leave_search_mode()
            return True
        if self.mode == "search" and keyval in (Gdk.KEY_Down, Gdk.KEY_Tab):
            self.selected_result = min(len(self.results) - 1, self.selected_result + 1)
            self._highlight_selected_result()
            return True
        if self.mode == "search" and keyval == Gdk.KEY_Up:
            self.selected_result = max(0, self.selected_result - 1)
            self._highlight_selected_result()
            return True
        if self.mode == "search" and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._activate_selected_result()
            return True
        return False

    def _tick_clock(self) -> bool:
        """Refresh the clock once per second."""

        now = time.localtime()
        if self.clock_label is not None:
            self.clock_label.set_label(time.strftime("%H:%M", now))
        if self.date_label is not None:
            self.date_label.set_label(time.strftime("%d %b", now))
        return True

    def _tick_active_window(self) -> bool:
        """Refresh active window title from Hyprland IPC."""

        if self.mode != "compact" or self.center_label is None:
            return True
        active = self.hyprland.active_window()
        title = str(active.get("title") or active.get("class") or "NEOX")
        self.center_label.set_label(title[:80])
        return True

    def _tick_status(self) -> bool:
        """Refresh network, audio and battery indicators."""

        if self.status_label is None:
            return True
        parts: list[str] = []
        network = self._network_icon()
        if network:
            parts.append(network)
        volume = self._volume_icon()
        if volume:
            parts.append(volume)
        battery = self._battery_icon()
        if battery:
            parts.append(battery)
        self.status_label.set_label("  ".join(parts))
        return True

    def _tick_media(self) -> bool:
        """Show media information when an MPRIS player is active."""

        if not which("playerctl") or self.mode == "search":
            return True
        result = run_command(
            ["playerctl", "metadata", "--format", "{{artist}} — {{title}}"],
            timeout=1.5,
            logger=LOGGER,
        )
        text = result.stdout.strip()
        status = run_command(["playerctl", "status"], timeout=1.0, logger=LOGGER).stdout.strip()
        if result.returncode == 0 and text and status == "Playing":
            self.enter_media_mode(text)
        elif self.mode == "media":
            self.leave_search_mode()
        return True

    def _network_icon(self) -> str:
        """Return a text icon for NetworkManager state."""

        if not which("nmcli"):
            return ""
        result = run_command(["nmcli", "-t", "-f", "TYPE,STATE", "device"], timeout=1, logger=LOGGER)
        if "wifi:connected" in result.stdout:
            return "Wi‑Fi"
        if "ethernet:connected" in result.stdout:
            return "ETH"
        return "Offline"

    def _volume_icon(self) -> str:
        """Return a text icon for PipeWire volume."""

        if not which("wpctl"):
            return ""
        result = run_command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], timeout=1, logger=LOGGER)
        text = result.stdout.strip()
        match = re.search(r"([0-9.]+)", text)
        if not match:
            return ""
        percent = int(float(match.group(1)) * 100)
        if "MUTED" in text:
            return "Muted"
        return f"Vol {percent}%"

    def _battery_icon(self) -> str:
        """Return a compact battery label if a battery is present."""

        power_root = pathlib.Path("/sys/class/power_supply")
        for battery in power_root.glob("BAT*"):
            try:
                capacity = (battery / "capacity").read_text(encoding="utf-8").strip()
                status = (battery / "status").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            symbol = "⚡" if status == "Charging" else "Bat"
            return f"{symbol} {capacity}%"
        return ""

    def _playerctl(self, command: str) -> None:
        """Run a playerctl command."""

        if which("playerctl"):
            run_command(["playerctl", command], timeout=2, logger=LOGGER)

    def _launch_helper(self, helper: str) -> None:
        """Launch another NEOX helper."""

        os.spawnlp(os.P_NOWAIT, helper, helper)

    def _launch_widget(self, helper: str) -> None:
        """Launch a widget helper, trying source-tree path if not installed."""

        path = pathlib.Path(__file__).resolve().parent.parent / "widgets" / f"{helper}.py"
        if path.exists():
            os.spawnlp(os.P_NOWAIT, sys.executable, sys.executable, str(path))
        else:
            os.spawnlp(os.P_NOWAIT, helper, helper)

    def _apps_changed(self, apps: list[DesktopEntry]) -> bool:
        """Update scanner cache when the app list changes."""

        LOGGER.info("Panel search index updated: %d apps", len(apps))
        return False

    def _install_css(self) -> None:
        """Install component CSS for the Dynamic Island."""

        load_hd_css(Gtk, Gdk, profile="panel")
        css = """
        .neox-panel-outer { background: transparent; }
        .neox-island {
            background: rgba(20, 20, 20, 0.86);
            color: white;
            border-radius: 22px;
            box-shadow: 0 18px 44px rgba(0,0,0,0.38);
            border: 1px solid rgba(255,255,255,0.08);
            transition: all 300ms cubic-bezier(0.4, 0, 0.2, 1);
        }
        .neox-clock { font-weight: 800; font-size: 14px; }
        .neox-date, .neox-status, .neox-active-title { color: rgba(255,255,255,0.74); font-size: 12px; }
        .neox-panel-button {
            border: 0;
            border-radius: 999px;
            min-width: 28px;
            min-height: 28px;
            padding: 2px 8px;
            background: rgba(255,255,255,0.10);
            color: rgba(255,255,255,0.92);
        }
        .neox-panel-button:hover { background: rgba(255,255,255,0.20); }
        .neox-search-icon { font-size: 22px; color: #60a5fa; }
        searchentry, entry {
            border-radius: 18px;
            min-height: 38px;
            padding: 0 12px;
            background: rgba(255,255,255,0.10);
            color: white;
            border: 1px solid rgba(255,255,255,0.10);
        }
        .neox-search-results {
            min-width: 640px;
            padding: 8px;
            border-radius: 24px;
            background: rgba(18, 18, 22, 0.92);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 22px 52px rgba(0,0,0,0.42);
        }
        .neox-result-row {
            border-radius: 16px;
            background: transparent;
            color: white;
            border: 0;
        }
        .neox-result-row:hover, .neox-result-row.selected { background: rgba(96,165,250,0.22); }
        .neox-result-title { font-weight: 700; color: white; }
        .neox-result-subtitle { font-size: 12px; color: rgba(255,255,255,0.64); }
        .neox-media-title { color: white; font-weight: 700; }
        .neox-notification-preview {
            padding: 14px 18px;
            border-radius: 22px;
            background: rgba(20,20,24,0.94);
            color: white;
            box-shadow: 0 18px 44px rgba(0,0,0,0.35);
        }
        .neox-notification-preview.critical { background: rgba(185,28,28,0.94); }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX Dynamic Island panel")
    parser.add_argument("--search", action="store_true", help="start directly in search mode")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the panel."""

    args = parse_args(argv or sys.argv[1:])
    if Gtk is None:
        LOGGER.error("GTK4/PyGObject is not available: %s", GTK_IMPORT_ERROR)
        return 1
    lock = SingletonLock("neox-panel")
    if not lock.acquire():
        if args.search:
            JsonLineClient(logger=LOGGER).send("open-search")
        return 0
    try:
        app = DynamicIsland()
        if args.search:
            GLib.timeout_add(500, lambda: (app.enter_search_mode(), False)[1])
        return app.run([])
    except Exception as exc:
        LOGGER.exception("Panel crashed: %s", exc)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

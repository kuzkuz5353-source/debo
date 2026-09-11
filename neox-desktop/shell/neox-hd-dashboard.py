#!/usr/bin/env python3
"""NEOX HD Dashboard.

This is the high-definition home surface for NEOX: a polished overview that
combines a hero clock, search, favorite applications, system metrics, workspaces,
media status and quick actions.  It complements the mobile app grid and can be
opened with ``Super+H``.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import (  # noqa: E402
    DesktopAppScanner,
    DesktopEntry,
    HyprlandIPC,
    NEOX_CONFIG_DIR,
    SingletonLock,
    category_label,
    read_json,
    run_command,
    setup_logging,
    which,
)
from neox_hd_ui import format_percent, load_hd_css, make_header, make_metric_card, read_system_metrics  # noqa: E402

LOGGER = setup_logging("neox-hd-dashboard")

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
class QuickTile:
    """Quick action shown on the dashboard."""

    title: str
    subtitle: str
    icon: str
    action: Callable[[], object]
    dangerous: bool = False


class HDDashboard(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK layer-shell high-definition overview."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.HDDashboard")
        self.scanner = DesktopAppScanner(logger=LOGGER)
        self.hyprland = HyprlandIPC(LOGGER)
        self.apps: list[DesktopEntry] = []
        self.window: Gtk.ApplicationWindow | None = None
        self.time_label: Gtk.Label | None = None
        self.date_label: Gtk.Label | None = None
        self.metric_grid: Gtk.Grid | None = None
        self.media_label: Gtk.Label | None = None
        self.workspace_box: Gtk.Box | None = None
        self.favorite_flow: Gtk.FlowBox | None = None
        self.search: Gtk.SearchEntry | None = None

    def do_activate(self) -> None:
        """Create and present the dashboard."""

        self.apps = self.scanner.scan(force=False)
        self._install_css()
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX HD Dashboard")
        self.window.set_decorated(False)
        self.window.set_default_size(1360, 860)
        if LayerShell is not None:
            LayerShell.init_for_window(self.window)
            LayerShell.set_namespace(self.window, "neox-hd-dashboard")
            LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
            for edge in (LayerShell.Edge.TOP, LayerShell.Edge.RIGHT, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT):
                LayerShell.set_anchor(self.window, edge, True)
            LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.EXCLUSIVE)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        root.add_css_class("neox-hd-root")
        root.add_css_class("dashboard-root")
        root.set_margin_top(42)
        root.set_margin_bottom(42)
        root.set_margin_start(54)
        root.set_margin_end(54)
        self.window.set_child(root)

        root.append(self._hero())
        body = Gtk.Grid()
        body.set_column_spacing(18)
        body.set_row_spacing(18)
        body.set_column_homogeneous(False)
        body.set_vexpand(True)
        root.append(body)

        favorites = self._favorites_panel()
        body.attach(favorites, 0, 0, 2, 2)
        body.attach(self._metrics_panel(), 2, 0, 1, 1)
        body.attach(self._workspace_panel(), 2, 1, 1, 1)
        body.attach(self._quick_actions_panel(), 0, 2, 3, 1)

        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self._on_key)
        self.window.add_controller(key)
        self.window.present()
        if self.search is not None:
            self.search.grab_focus()
        GLib.timeout_add_seconds(1, self._tick_clock)
        GLib.timeout_add_seconds(3, self._tick_metrics)
        GLib.timeout_add_seconds(4, self._tick_media)
        GLib.timeout_add_seconds(4, self._tick_workspaces)
        self._tick_clock()
        self._tick_metrics()
        self._tick_media()
        self._tick_workspaces()

    def _hero(self) -> Gtk.Widget:
        """Build hero clock and global search."""

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        hero.add_css_class("dashboard-hero")
        hero.add_css_class("neox-hd-glass")
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left.set_hexpand(True)
        self.time_label = Gtk.Label(label="--:--")
        self.time_label.set_xalign(0)
        self.time_label.add_css_class("neox-hd-hero-title")
        self.date_label = Gtk.Label(label="")
        self.date_label.set_xalign(0)
        self.date_label.add_css_class("neox-hd-hero-subtitle")
        left.append(self.time_label)
        left.append(self.date_label)
        hero.append(left)
        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        search_box.set_size_request(480, -1)
        search_title = Gtk.Label(label="Akıllı arama")
        search_title.set_xalign(0)
        search_title.add_css_class("neox-hd-subtitle")
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Uygulama başlat, web ara veya hesapla…")
        self.search.connect("activate", self._activate_search)
        search_box.append(search_title)
        search_box.append(self.search)
        hero.append(search_box)
        return hero

    def _favorites_panel(self) -> Gtk.Widget:
        """Build favorite application panel."""

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.add_css_class("neox-hd-card")
        panel.append(make_header(Gtk, "Favori Programlar", "Desktop Grid ve Program Center favorileri"))
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.favorite_flow = Gtk.FlowBox()
        self.favorite_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.favorite_flow.set_max_children_per_line(5)
        self.favorite_flow.set_min_children_per_line(3)
        self.favorite_flow.set_column_spacing(12)
        self.favorite_flow.set_row_spacing(12)
        scrolled.set_child(self.favorite_flow)
        panel.append(scrolled)
        self._refresh_favorites()
        return panel

    def _metrics_panel(self) -> Gtk.Widget:
        """Build system metrics panel."""

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.add_css_class("neox-hd-card")
        panel.append(make_header(Gtk, "Sistem", "Canlı durum"))
        self.metric_grid = Gtk.Grid()
        self.metric_grid.set_column_spacing(10)
        self.metric_grid.set_row_spacing(10)
        self.metric_grid.set_column_homogeneous(True)
        panel.append(self.metric_grid)
        self.media_label = Gtk.Label(label="Medya: —")
        self.media_label.set_xalign(0)
        self.media_label.add_css_class("neox-hd-subtitle")
        panel.append(self.media_label)
        return panel

    def _workspace_panel(self) -> Gtk.Widget:
        """Build workspace overview panel."""

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.add_css_class("neox-hd-card")
        panel.append(make_header(Gtk, "Workspace", "Açık pencereler"))
        self.workspace_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panel.append(self.workspace_box)
        return panel

    def _quick_actions_panel(self) -> Gtk.Widget:
        """Build quick action tile strip."""

        panel = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        panel.add_css_class("dashboard-actions")
        actions = [
            QuickTile("Kontrol", "Ayarlar", "preferences-system-symbolic", lambda: self._helper("neox-control-center")),
            QuickTile("Programlar", "Yönet", "view-grid-symbolic", lambda: self._helper("neox-program-center")),
            QuickTile("Duvar", "HD arka plan", "preferences-desktop-wallpaper-symbolic", lambda: self._helper("neox-wallpaper-manager")),
            QuickTile("Bildirim", "Merkez", "preferences-system-notifications-symbolic", lambda: self._helper("neox-notification-center")),
            QuickTile("Launcher", "Izgara", "open-menu-symbolic", lambda: self._helper("neox-desktop-grid")),
            QuickTile("Kilitle", "Güvenli", "system-lock-screen-symbolic", lambda: self._helper("neox-lock-screen")),
            QuickTile("Güç", "Oturum", "system-shutdown-symbolic", lambda: self._helper("neox-logout-screen"), True),
        ]
        for tile in actions:
            panel.append(self._quick_tile(tile))
        return panel

    def _quick_tile(self, tile: QuickTile) -> Gtk.Widget:
        """Render one quick action tile."""

        button = Gtk.Button()
        button.add_css_class("quick-tile")
        if tile.dangerous:
            button.add_css_class("danger")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        icon = Gtk.Image.new_from_icon_name(tile.icon)
        icon.set_pixel_size(30)
        icon.set_halign(Gtk.Align.START)
        title = Gtk.Label(label=tile.title)
        title.set_xalign(0)
        title.add_css_class("quick-title")
        subtitle = Gtk.Label(label=tile.subtitle)
        subtitle.set_xalign(0)
        subtitle.add_css_class("neox-hd-subtitle")
        box.append(icon)
        box.append(title)
        box.append(subtitle)
        button.set_child(box)
        button.connect("clicked", lambda _button: tile.action())
        return button

    def _refresh_favorites(self) -> None:
        """Load favorites from shared state and render cards."""

        if self.favorite_flow is None:
            return
        while child := self.favorite_flow.get_first_child():
            self.favorite_flow.remove(child)
        favorite_ids = set(read_json(NEOX_CONFIG_DIR / "desktop-grid.json", {"favorites": []}).get("favorites", []))
        apps = [app for app in self.apps if app.id in favorite_ids]
        if not apps:
            apps = self.apps[:10]
        for app in apps[:15]:
            self.favorite_flow.append(self._favorite_card(app))

    def _favorite_card(self, app: DesktopEntry) -> Gtk.Widget:
        """Create a favorite app card."""

        button = Gtk.Button()
        button.add_css_class("favorite-card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_file(app.icon) if pathlib.Path(app.icon).exists() else Gtk.Image.new_from_icon_name(app.icon or "application-x-executable-symbolic")
        icon.set_pixel_size(64)
        label = Gtk.Label(label=app.name)
        label.set_wrap(True)
        label.set_lines(2)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.add_css_class("favorite-label")
        category = Gtk.Label(label=category_label(app.categories))
        category.add_css_class("neox-hd-subtitle")
        box.append(icon)
        box.append(label)
        box.append(category)
        button.set_child(box)
        button.connect("clicked", lambda _button: app.launch(LOGGER))
        return button

    def _tick_clock(self) -> bool:
        """Refresh hero clock/date."""

        now = time.localtime()
        if self.time_label is not None:
            self.time_label.set_label(time.strftime("%H:%M", now))
        if self.date_label is not None:
            self.date_label.set_label(time.strftime("%A, %d %B %Y", now))
        return True

    def _tick_metrics(self) -> bool:
        """Refresh system metric cards."""

        if self.metric_grid is None:
            return True
        while child := self.metric_grid.get_first_child():
            self.metric_grid.remove(child)
        metrics = read_system_metrics()
        cards = [
            make_metric_card(Gtk, "CPU", format_percent(metrics.cpu_percent), "işlemci", "neox-hd-accent"),
            make_metric_card(Gtk, "Bellek", format_percent(metrics.memory_percent), "RAM", "neox-hd-warning" if metrics.memory_percent > 80 else ""),
            make_metric_card(Gtk, "Disk", format_percent(metrics.disk_percent), "home", "neox-hd-warning" if metrics.disk_percent > 85 else ""),
            make_metric_card(Gtk, "Ses", "Muted" if metrics.muted else format_percent(metrics.volume_percent), metrics.network, ""),
        ]
        if metrics.battery_percent is not None:
            cards.append(make_metric_card(Gtk, "Batarya", format_percent(metrics.battery_percent), "şarj oluyor" if metrics.battery_charging else "pil", "neox-hd-success" if metrics.battery_charging else ""))
        for index, card in enumerate(cards):
            self.metric_grid.attach(card, index % 2, index // 2, 1, 1)
        return True

    def _tick_media(self) -> bool:
        """Refresh MPRIS media summary."""

        if self.media_label is None:
            return True
        if not which("playerctl"):
            self.media_label.set_label("Medya: playerctl yok")
            return True
        result = run_command(["playerctl", "metadata", "--format", "{{status}} · {{artist}} — {{title}}"], timeout=1, logger=LOGGER)
        self.media_label.set_label("Medya: " + (result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "—"))
        return True

    def _tick_workspaces(self) -> bool:
        """Refresh workspace window counts."""

        if self.workspace_box is None:
            return True
        while child := self.workspace_box.get_first_child():
            self.workspace_box.remove(child)
        counts: dict[int, int] = {}
        for client in self.hyprland.clients():
            workspace = client.get("workspace") or {}
            workspace_id = int(workspace.get("id") or 0)
            counts[workspace_id] = counts.get(workspace_id, 0) + 1
        if not counts:
            label = Gtk.Label(label="Açık pencere yok")
            label.set_xalign(0)
            label.add_css_class("neox-hd-subtitle")
            self.workspace_box.append(label)
            return True
        for workspace_id in sorted(counts):
            button = Gtk.Button(label=f"Workspace {workspace_id} · {counts[workspace_id]} pencere")
            button.add_css_class("neox-hd-chip")
            button.connect("clicked", lambda _button, ws=workspace_id: self.hyprland.dispatch("workspace", str(ws)))
            self.workspace_box.append(button)
        return True

    def _activate_search(self, entry: Gtk.SearchEntry) -> None:
        """Launch best matching app or forward query to standalone search."""

        query = entry.get_text().strip()
        if not query:
            self._helper("neox-app-search")
            return
        matches = self.scanner.fuzzy_search(query, limit=1)
        if matches:
            matches[0].launch(LOGGER)
            self.quit()
            return
        self._helper("neox-app-search", query)

    def _helper(self, name: str, *args: str) -> None:
        """Launch a NEOX helper from PATH or source tree."""

        source = pathlib.Path(__file__).resolve().parent / f"{name}.py"
        if source.exists():
            command = [sys.executable, str(source), *args]
        else:
            command = [name, *args]
        LOGGER.info("Launching helper: %s", command)
        try:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        except Exception as exc:
            LOGGER.warning("Cannot launch %s: %s", name, exc)

    def _on_key(self, _controller: Gtk.EventControllerKey, keyval: int, _keycode: int, _state: int) -> bool:
        """Close dashboard on Escape and open task switcher on Tab."""

        if keyval == Gdk.KEY_Escape:
            self.quit()
            return True
        if keyval == Gdk.KEY_Tab:
            self._helper("neox-task-switcher")
            self.quit()
            return True
        return False

    def _install_css(self) -> None:
        """Install dashboard-specific CSS."""

        scale = load_hd_css(Gtk, Gdk, profile="dashboard")
        css = f"""
        .dashboard-root {{ background: rgba(5,8,22,0.64); }}
        .dashboard-hero {{ padding: {scale.px(22)}px {scale.px(26)}px; }}
        .dashboard-actions {{ padding: {scale.px(4)}px; }}
        .quick-tile {{ min-width: {scale.px(144)}px; min-height: {scale.px(112)}px; border-radius: {scale.radius}px; padding: {scale.px(14)}px; background: rgba(255,255,255,0.075); color: white; border: 1px solid rgba(255,255,255,0.09); }}
        .quick-tile:hover {{ background: rgba(96,165,250,0.22); border-color: rgba(96,165,250,0.44); }}
        .quick-tile.danger:hover {{ background: rgba(251,113,133,0.24); border-color: rgba(251,113,133,0.48); }}
        .quick-title {{ font-weight: 900; font-size: {scale.px(15)}px; }}
        .favorite-card {{ min-width: {scale.px(130)}px; min-height: {scale.px(152)}px; border-radius: {scale.radius}px; padding: {scale.px(12)}px; background: rgba(255,255,255,0.065); color: white; border: 1px solid rgba(255,255,255,0.08); }}
        .favorite-card:hover {{ background: rgba(96,165,250,0.20); border-color: rgba(96,165,250,0.42); }}
        .favorite-label {{ font-weight: 850; font-size: {scale.px(13)}px; }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def run_cli() -> int:
    """Headless dashboard summary."""

    metrics = read_system_metrics()
    print("NEOX HD Dashboard")
    print(f"CPU: {format_percent(metrics.cpu_percent)}")
    print(f"Memory: {format_percent(metrics.memory_percent)}")
    print(f"Disk: {format_percent(metrics.disk_percent)}")
    print(f"Network: {metrics.network}")
    print(f"Volume: {'Muted' if metrics.muted else format_percent(metrics.volume_percent)}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX HD Dashboard")
    parser.add_argument("--cli", action="store_true", help="print dashboard summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.cli or Gtk is None:
        if Gtk is None:
            LOGGER.warning("GTK unavailable, using CLI fallback: %s", GTK_IMPORT_ERROR)
        return run_cli()
    lock = SingletonLock("neox-hd-dashboard")
    if not lock.acquire():
        return 0
    try:
        return HDDashboard().run([])
    except Exception as exc:
        LOGGER.exception("HD Dashboard crashed: %s", exc)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

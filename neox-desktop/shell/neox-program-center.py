#!/usr/bin/env python3
"""NEOX Program Center.

The Program Center is the advanced application-management companion to the
mobile desktop grid.  It scans all freedesktop applications, groups them by
category, provides HD cards and a detail inspector, launches apps, marks
favorites, opens source .desktop files, detects Flatpak/Snap uninstall commands
and reports distribution package updates.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import (  # noqa: E402
    DesktopAppScanner,
    DesktopEntry,
    JsonLineClient,
    NEOX_CONFIG_DIR,
    SingletonLock,
    category_label,
    read_json,
    run_command,
    setup_logging,
    which,
    write_json,
)
from neox_hd_ui import format_percent, load_hd_css, make_header  # noqa: E402

LOGGER = setup_logging("neox-program-center")
FAVORITES_PATH = NEOX_CONFIG_DIR / "desktop-grid.json"

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, Gtk, Pango
except (ImportError, ValueError) as exc:  # pragma: no cover - GUI dependency.
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    GLib = None  # type: ignore[assignment]
    Pango = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


@dataclass(slots=True)
class PackageUpdates:
    """Distribution package update snapshot."""

    manager: str
    count: int
    detail: str


class FavoritesStore:
    """Shared favorite-app state used by Program Center and Desktop Grid."""

    def __init__(self, path: pathlib.Path = FAVORITES_PATH) -> None:
        self.path = path
        self.payload = read_json(path, {"items": [], "favorites": []})
        self.favorites: set[str] = set(self.payload.get("favorites", []))

    def toggle(self, app_id: str) -> bool:
        """Toggle favorite state and return the new state."""

        if app_id in self.favorites:
            self.favorites.remove(app_id)
            active = False
        else:
            self.favorites.add(app_id)
            active = True
        self.payload["favorites"] = sorted(self.favorites)
        write_json(self.path, self.payload)
        return active

    def contains(self, app_id: str) -> bool:
        """Return whether an app is a favorite."""

        return app_id in self.favorites


class ProgramCenter(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK HD app-management window."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.ProgramCenter")
        self.scanner = DesktopAppScanner(logger=LOGGER)
        self.bus = JsonLineClient(logger=LOGGER)
        self.favorites = FavoritesStore()
        self.apps: list[DesktopEntry] = []
        self.category = "Tümü"
        self.query = ""
        self.window: Gtk.ApplicationWindow | None = None
        self.category_box: Gtk.Box | None = None
        self.flow: Gtk.FlowBox | None = None
        self.detail: Gtk.Box | None = None
        self.update_label: Gtk.Label | None = None
        self.search: Gtk.SearchEntry | None = None

    def do_activate(self) -> None:
        """Build the UI and start background scans."""

        self.apps = self.scanner.scan(force=False)
        self._install_css()
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX Program Center")
        self.window.set_default_size(1180, 760)
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.add_css_class("program-root")
        root.add_css_class("neox-hd-root")
        self.window.set_child(root)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar.add_css_class("program-sidebar")
        sidebar.set_size_request(230, -1)
        root.append(sidebar)
        sidebar.append(make_header(Gtk, "Programlar", "Kurulu uygulamalar"))
        self.update_label = Gtk.Label(label="Güncellemeler kontrol ediliyor…")
        self.update_label.set_xalign(0)
        self.update_label.add_css_class("neox-hd-subtitle")
        sidebar.append(self.update_label)
        self.category_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar.append(self.category_box)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        main.set_hexpand(True)
        main.set_margin_top(20)
        main.set_margin_bottom(20)
        main.set_margin_start(20)
        main.set_margin_end(20)
        root.append(main)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        toolbar.add_css_class("neox-hd-toolbar")
        toolbar.set_margin_bottom(4)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Uygulama, kategori, açıklama veya anahtar kelime ara…")
        self.search.set_hexpand(True)
        self.search.connect("search-changed", self._search_changed)
        toolbar.append(self.search)
        refresh = Gtk.Button(label="Yenile")
        refresh.add_css_class("neox-hd-button")
        refresh.connect("clicked", lambda _button: self._rescan())
        toolbar.append(refresh)
        updates = Gtk.Button(label="Güncellemeler")
        updates.add_css_class("neox-hd-button")
        updates.connect("clicked", lambda _button: self._show_update_detail())
        toolbar.append(updates)
        main.append(toolbar)

        content = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        content.set_wide_handle(True)
        main.append(content)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_max_children_per_line(4)
        self.flow.set_min_children_per_line(2)
        self.flow.set_column_spacing(14)
        self.flow.set_row_spacing(14)
        scrolled.set_child(self.flow)
        content.set_start_child(scrolled)

        self.detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.detail.add_css_class("detail-panel")
        self.detail.set_size_request(330, -1)
        content.set_end_child(self.detail)
        content.set_resize_start_child(True)
        content.set_shrink_start_child(False)
        content.set_resize_end_child(False)

        self._refresh_categories()
        self._refresh_grid()
        self._empty_detail()
        self.window.present()
        threading.Thread(target=self._check_updates_worker, name="neox-program-updates", daemon=True).start()

    def _install_css(self) -> None:
        """Install Program Center specific HD CSS."""

        scale = load_hd_css(Gtk, Gdk, profile="program-center")
        css = f"""
        .program-root {{ background: #050816; color: white; }}
        .program-sidebar {{ padding: {scale.px(18)}px; background: rgba(255,255,255,0.045); border-right: 1px solid rgba(255,255,255,0.08); }}
        .program-category {{ min-height: {scale.px(42)}px; border-radius: 16px; padding: 0 12px; background: transparent; color: rgba(255,255,255,0.76); border: 0; font-weight: 800; }}
        .program-category:hover, .program-category.active {{ background: rgba(96,165,250,0.22); color: white; }}
        .program-card {{ min-width: {scale.px(210)}px; min-height: {scale.px(182)}px; border-radius: {scale.radius}px; padding: {scale.px(14)}px; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.10); color: white; }}
        .program-card:hover {{ background: rgba(30,41,59,0.86); border-color: rgba(96,165,250,0.52); }}
        .program-icon {{ margin-bottom: 8px; }}
        .program-name {{ font-size: {scale.px(15)}px; font-weight: 900; }}
        .program-meta {{ font-size: {scale.px(12)}px; color: rgba(255,255,255,0.58); }}
        .detail-panel {{ padding: {scale.px(18)}px; border-radius: {scale.radius}px; background: rgba(15,23,42,0.72); border: 1px solid rgba(255,255,255,0.10); }}
        .detail-name {{ font-size: {scale.px(24)}px; font-weight: 950; }}
        .detail-comment {{ color: rgba(255,255,255,0.70); }}
        .detail-path {{ font-family: monospace; font-size: {scale.px(11)}px; color: rgba(255,255,255,0.48); }}
        .favorite-active {{ background: rgba(251,191,36,0.26); border-color: rgba(251,191,36,0.48); }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _refresh_categories(self) -> None:
        """Refresh category buttons."""

        if self.category_box is None:
            return
        while child := self.category_box.get_first_child():
            self.category_box.remove(child)
        labels = ["Tümü", "Favoriler"] + sorted({category_label(app.categories) for app in self.apps})
        for label in labels:
            button = Gtk.Button(label=label)
            button.add_css_class("program-category")
            if label == self.category:
                button.add_css_class("active")
            button.connect("clicked", lambda _button, value=label: self._set_category(value))
            self.category_box.append(button)

    def _set_category(self, category: str) -> None:
        """Select a category and refresh grid."""

        self.category = category
        self._refresh_categories()
        self._refresh_grid()

    def _search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Update query from search entry."""

        self.query = entry.get_text().strip().lower()
        self._refresh_grid()

    def _filtered_apps(self) -> list[DesktopEntry]:
        """Return apps matching category and query."""

        apps = self.apps
        if self.category == "Favoriler":
            apps = [app for app in apps if self.favorites.contains(app.id)]
        elif self.category != "Tümü":
            apps = [app for app in apps if category_label(app.categories) == self.category]
        if self.query:
            apps = [app for app in apps if self.query in app.searchable_text or self.query in app.name.lower()]
        return sorted(apps, key=lambda app: app.name.casefold())

    def _refresh_grid(self) -> None:
        """Refresh application cards."""

        if self.flow is None:
            return
        while child := self.flow.get_first_child():
            self.flow.remove(child)
        for app in self._filtered_apps():
            self.flow.append(self._app_card(app))

    def _app_card(self, app: DesktopEntry) -> Gtk.Widget:
        """Create an HD card for an application."""

        button = Gtk.Button()
        button.add_css_class("program-card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_halign(Gtk.Align.START)
        icon = Gtk.Image.new_from_file(app.icon) if pathlib.Path(app.icon).exists() else Gtk.Image.new_from_icon_name(app.icon or "application-x-executable-symbolic")
        icon.set_pixel_size(58)
        icon.add_css_class("program-icon")
        box.append(icon)
        name = Gtk.Label(label=app.name)
        name.set_xalign(0)
        name.set_wrap(True)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.add_css_class("program-name")
        box.append(name)
        meta = Gtk.Label(label=category_label(app.categories))
        meta.set_xalign(0)
        meta.add_css_class("program-meta")
        box.append(meta)
        comment = Gtk.Label(label=app.comment or app.exec)
        comment.set_xalign(0)
        comment.set_wrap(True)
        comment.set_lines(2)
        comment.set_ellipsize(Pango.EllipsizeMode.END)
        comment.add_css_class("program-meta")
        box.append(comment)
        button.set_child(box)
        button.connect("clicked", lambda _button: self._select_app(app))
        return button

    def _empty_detail(self) -> None:
        """Show default inspector text."""

        if self.detail is None:
            return
        while child := self.detail.get_first_child():
            self.detail.remove(child)
        self.detail.append(make_header(Gtk, "Uygulama seç", "Bir kart seçerek ayrıntıları ve yönetim seçeneklerini gör."))

    def _select_app(self, app: DesktopEntry) -> None:
        """Populate the detail inspector for an application."""

        if self.detail is None:
            return
        while child := self.detail.get_first_child():
            self.detail.remove(child)
        icon = Gtk.Image.new_from_file(app.icon) if pathlib.Path(app.icon).exists() else Gtk.Image.new_from_icon_name(app.icon or "application-x-executable-symbolic")
        icon.set_pixel_size(86)
        icon.set_halign(Gtk.Align.START)
        self.detail.append(icon)
        name = Gtk.Label(label=app.name)
        name.set_xalign(0)
        name.set_wrap(True)
        name.add_css_class("detail-name")
        self.detail.append(name)
        comment = Gtk.Label(label=app.comment or "Açıklama yok")
        comment.set_xalign(0)
        comment.set_wrap(True)
        comment.add_css_class("detail-comment")
        self.detail.append(comment)
        self.detail.append(self._detail_line("Kategori", ", ".join(app.categories) or "Diğer"))
        self.detail.append(self._detail_line("Komut", app.exec))
        path = Gtk.Label(label=app.path)
        path.set_xalign(0)
        path.set_wrap(True)
        path.add_css_class("detail-path")
        self.detail.append(path)
        self.detail.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        launch = self._action_button("Başlat", lambda: app.launch(LOGGER))
        favorite = self._action_button("Favori" if not self.favorites.contains(app.id) else "Favoriden çıkar", lambda: self._toggle_favorite(app))
        if self.favorites.contains(app.id):
            favorite.add_css_class("favorite-active")
        reveal = self._action_button(".desktop dosyasını aç", lambda: self._open_parent(app.path))
        uninstall = self._action_button("Kaldır", lambda: self._uninstall(app))
        uninstall.add_css_class("neox-hd-danger")
        for button in (launch, favorite, reveal, uninstall):
            self.detail.append(button)

    def _detail_line(self, key: str, value: str) -> Gtk.Widget:
        """Create one key/value detail line."""

        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        label = Gtk.Label(label=key)
        label.set_xalign(0)
        label.add_css_class("neox-hd-subtitle")
        text = Gtk.Label(label=value or "—")
        text.set_xalign(0)
        text.set_wrap(True)
        row.append(label)
        row.append(text)
        return row

    def _action_button(self, title: str, callback: Any) -> Gtk.Button:
        """Create an inspector action button."""

        button = Gtk.Button(label=title)
        button.add_css_class("neox-hd-button")
        button.connect("clicked", lambda _button: callback())
        return button

    def _toggle_favorite(self, app: DesktopEntry) -> None:
        """Toggle favorite state and notify other components."""

        active = self.favorites.toggle(app.id)
        self.bus.send("reload-apps")
        self.bus.send("notification", {"title": "NEOX", "body": f"{app.name} {'favorilere eklendi' if active else 'favorilerden çıkarıldı'}"})
        self._select_app(app)

    def _open_parent(self, path: str) -> None:
        """Open the parent directory of a desktop-entry file."""

        parent = str(pathlib.Path(path).parent)
        if which("xdg-open"):
            subprocess.Popen(["xdg-open", parent], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _uninstall(self, app: DesktopEntry) -> None:
        """Start Flatpak/Snap uninstall when detectable, otherwise explain."""

        path = app.path
        if "/flatpak/" in path and which("flatpak"):
            app_id = pathlib.Path(path).stem
            subprocess.Popen(["flatpak", "uninstall", app_id])
            return
        if "/snapd/" in path and which("snap"):
            snap_name = pathlib.Path(path).stem.split("_")[0]
            subprocess.Popen(["snap", "remove", snap_name])
            return
        self.bus.send("notification", {"title": "NEOX Program Center", "body": "Sistem paketleri dağıtım paket yöneticisiyle kaldırılmalıdır."})

    def _rescan(self) -> None:
        """Force an application rescan."""

        self.apps = self.scanner.scan(force=True)
        self._refresh_categories()
        self._refresh_grid()

    def _show_update_detail(self) -> None:
        """Launch a terminal with the distro's update command if possible."""

        terminal = os.environ.get("TERMINAL", "foot")
        if which("checkupdates"):
            command = "checkupdates; read -rp 'Devam etmek için Enter...'"
        elif which("apt"):
            command = "apt list --upgradable; read -rp 'Devam etmek için Enter...'"
        elif which("dnf"):
            command = "dnf check-update; read -rp 'Devam etmek için Enter...'"
        else:
            self.bus.send("notification", {"title": "NEOX", "body": "Desteklenen paket yöneticisi bulunamadı."})
            return
        subprocess.Popen([terminal, "bash", "-lc", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _check_updates_worker(self) -> None:
        """Check pending distro updates off the UI thread."""

        updates = check_updates()
        GLib.idle_add(self._set_updates, updates)

    def _set_updates(self, updates: PackageUpdates) -> bool:
        """Set updates label from background result."""

        if self.update_label is not None:
            if updates.count >= 0:
                self.update_label.set_label(f"{updates.manager}: {updates.count} güncelleme")
            else:
                self.update_label.set_label("Güncelleme bilgisi yok")
        return False


def check_updates() -> PackageUpdates:
    """Check updates for pacman/apt/dnf systems."""

    if which("checkupdates"):
        result = run_command(["checkupdates"], timeout=20, logger=LOGGER)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        return PackageUpdates("pacman", len(lines), result.stdout)
    if which("apt"):
        result = run_command(["bash", "-lc", "apt list --upgradable 2>/dev/null | tail -n +2"], timeout=20, logger=LOGGER)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        return PackageUpdates("apt", len(lines), result.stdout)
    if which("dnf"):
        result = run_command(["bash", "-lc", "dnf -q check-update | awk 'NF>=3 {print}'"], timeout=30, logger=LOGGER)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        return PackageUpdates("dnf", len(lines), result.stdout)
    return PackageUpdates("unknown", -1, "")


def run_cli(args: argparse.Namespace) -> int:
    """Program Center CLI fallback."""

    scanner = DesktopAppScanner(logger=LOGGER)
    apps = scanner.scan(force=args.rescan)
    if args.updates:
        updates = check_updates()
        print(f"{updates.manager}: {updates.count} updates")
        if updates.detail:
            print(updates.detail)
        return 0
    if args.launch:
        for app in apps:
            if app.id == args.launch or app.name.lower() == args.launch.lower():
                return 0 if app.launch(LOGGER) else 1
        LOGGER.error("Application not found: %s", args.launch)
        return 1
    for app in apps:
        if args.category and category_label(app.categories).lower() != args.category.lower():
            continue
        print(f"{app.id}\t{category_label(app.categories)}\t{app.name}\t{app.comment}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="NEOX Program Center")
    parser.add_argument("--cli", action="store_true", help="use CLI mode")
    parser.add_argument("--rescan", action="store_true", help="force app rescan")
    parser.add_argument("--launch", help="launch an app by desktop id or name")
    parser.add_argument("--category", help="filter CLI listing by NEOX category")
    parser.add_argument("--updates", action="store_true", help="print package update count")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.cli or Gtk is None or args.launch or args.updates:
        if Gtk is None:
            LOGGER.warning("GTK unavailable, using CLI fallback: %s", GTK_IMPORT_ERROR)
        return run_cli(args)
    lock = SingletonLock("neox-program-center")
    if not lock.acquire():
        return 0
    try:
        return ProgramCenter().run([])
    except Exception as exc:
        LOGGER.exception("Program Center crashed: %s", exc)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Mobile-style NEOX desktop application grid.

The grid scans freedesktop ``.desktop`` files, caches them, watches for changes,
renders a full-screen translucent launcher, supports pagination, search-friendly
metadata, right-click menus, drag/drop reordering and basic folder creation.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, cast

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import (  # noqa: E402
    ConfigManager,
    DesktopAppScanner,
    DesktopEntry,
    JsonLineClient,
    NEOX_CONFIG_DIR,
    SingletonLock,
    category_label,
    chunked,
    icon_is_file,
    read_json,
    setup_logging,
    write_json,
)
from neox_hd_ui import load_hd_css  # noqa: E402

LOGGER = setup_logging("neox-desktop-grid")
STATE_PATH = NEOX_CONFIG_DIR / "desktop-grid.json"

try:  # GTK is optional at import time so tests can import the module headlessly.
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango

    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell
    except (ImportError, ValueError):
        LayerShell = None  # type: ignore[assignment]
except (ImportError, ValueError) as exc:  # pragma: no cover - depends on host GUI.
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    Gio = None  # type: ignore[assignment]
    GLib = None  # type: ignore[assignment]
    GObject = None  # type: ignore[assignment]
    Pango = None  # type: ignore[assignment]
    LayerShell = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


@dataclass(slots=True)
class GridSettings:
    """User-adjustable grid layout settings."""

    columns: int = 8
    rows: int = 5
    icon_size: int = 72
    category_mode: bool = False

    @property
    def page_size(self) -> int:
        """Return the maximum number of applications per normal page."""

        return max(1, self.columns * self.rows)


class GridState:
    """Persistent launcher arrangement state.

    Items are stored as dictionaries for forwards compatibility:
    ``{"type": "app", "id": "firefox.desktop"}`` or
    ``{"type": "folder", "name": "Folder", "items": ["a.desktop", "b.desktop"]}``.
    """

    def __init__(self, path: pathlib.Path = STATE_PATH) -> None:
        self.path = path
        payload = read_json(path, {"items": [], "favorites": []})
        self.items: list[dict[str, Any]] = list(payload.get("items", []))
        self.favorites: set[str] = set(payload.get("favorites", []))

    def merge_apps(self, apps: list[DesktopEntry]) -> None:
        """Add newly installed apps and remove stale references."""

        valid_ids = {app.id for app in apps}
        seen: set[str] = set()
        cleaned: list[dict[str, Any]] = []
        for item in self.items:
            if item.get("type") == "app":
                app_id = str(item.get("id", ""))
                if app_id in valid_ids and app_id not in seen:
                    cleaned.append({"type": "app", "id": app_id})
                    seen.add(app_id)
            elif item.get("type") == "folder":
                folder_items = [app_id for app_id in item.get("items", []) if app_id in valid_ids]
                for app_id in folder_items:
                    seen.add(app_id)
                if folder_items:
                    cleaned.append(
                        {
                            "type": "folder",
                            "name": str(item.get("name", "Klasör")),
                            "items": folder_items,
                        }
                    )
        for app in apps:
            if app.id not in seen:
                cleaned.append({"type": "app", "id": app.id})
        self.items = cleaned
        self.favorites.intersection_update(valid_ids)

    def save(self) -> None:
        """Persist the state atomically."""

        write_json(self.path, {"items": self.items, "favorites": sorted(self.favorites)})

    def find_index(self, app_id: str) -> int | None:
        """Return the top-level index that contains ``app_id``."""

        for index, item in enumerate(self.items):
            if item.get("type") == "app" and item.get("id") == app_id:
                return index
            if item.get("type") == "folder" and app_id in item.get("items", []):
                return index
        return None

    def remove_app_reference(self, app_id: str) -> None:
        """Remove ``app_id`` from the top-level list or from any folder."""

        new_items: list[dict[str, Any]] = []
        for item in self.items:
            if item.get("type") == "app" and item.get("id") == app_id:
                continue
            if item.get("type") == "folder":
                folder_items = [value for value in item.get("items", []) if value != app_id]
                if folder_items:
                    item = dict(item)
                    item["items"] = folder_items
                    new_items.append(item)
                continue
            new_items.append(item)
        self.items = new_items

    def create_or_extend_folder(self, source_id: str, target_id: str) -> None:
        """Drop ``source_id`` onto ``target_id`` and create/extend a folder."""

        if source_id == target_id:
            return
        target_index = self.find_index(target_id)
        if target_index is None:
            return
        target_item = dict(self.items[target_index])
        self.remove_app_reference(source_id)
        # Recalculate target index after removing the source entry.
        target_index = self.find_index(target_id)
        if target_index is None:
            return
        target_item = dict(self.items[target_index])
        if target_item.get("type") == "folder":
            items = list(target_item.get("items", []))
            if source_id not in items:
                items.append(source_id)
            target_item["items"] = items
            self.items[target_index] = target_item
            return
        if target_item.get("type") == "app":
            self.items[target_index] = {
                "type": "folder",
                "name": "Klasör",
                "items": [str(target_item.get("id")), source_id],
            }

    def move_before(self, source_id: str, target_id: str) -> None:
        """Move an app before another app without creating a folder."""

        if source_id == target_id:
            return
        source_item: dict[str, Any] | None = None
        for item in self.items:
            if item.get("type") == "app" and item.get("id") == source_id:
                source_item = dict(item)
                break
        if source_item is None:
            return
        self.remove_app_reference(source_id)
        target_index = self.find_index(target_id)
        if target_index is None:
            self.items.append(source_item)
        else:
            self.items.insert(target_index, source_item)


class NeoxDesktopGrid(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK application implementing the full-screen launcher."""

    def __init__(self, toggle: bool = False) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.DesktopGrid")
        self.toggle = toggle
        self.config = ConfigManager()
        self.settings = GridSettings(
            columns=max(1, self.config.getint("desktop_grid", "columns", 8)),
            rows=max(1, self.config.getint("desktop_grid", "rows", 5)),
            icon_size=max(32, self.config.getint("desktop_grid", "icon_size", 72)),
            category_mode=self.config.getbool("desktop_grid", "category_mode", False),
        )
        self.scanner = DesktopAppScanner(logger=LOGGER)
        self.state = GridState()
        self.apps: dict[str, DesktopEntry] = {}
        self.pages: list[list[dict[str, Any]]] = []
        self.current_page = 0
        self.window: Gtk.ApplicationWindow | None = None
        self.stack: Gtk.Stack | None = None
        self.indicators: Gtk.Box | None = None
        self.header_label: Gtk.Label | None = None
        self.folder_popover: Gtk.Popover | None = None
        self.bus = JsonLineClient(logger=LOGGER)

    def do_activate(self) -> None:
        """GTK activation callback."""

        self._install_css()
        self.reload_apps(force=False)
        self._build_window()
        self.scanner.watch(lambda apps: GLib.idle_add(self._on_apps_changed, apps))

    def reload_apps(self, *, force: bool) -> None:
        """Reload desktop applications and rebuild pagination."""

        apps = self.scanner.scan(force=force)
        self.apps = {app.id: app for app in apps}
        self.state.merge_apps(apps)
        self.state.save()
        self._paginate()

    def _on_apps_changed(self, apps: list[DesktopEntry]) -> bool:
        """Handle scanner updates on the GTK main thread."""

        self.apps = {app.id: app for app in apps}
        self.state.merge_apps(apps)
        self.state.save()
        self._paginate()
        self._refresh_pages()
        return False

    def _paginate(self) -> None:
        """Split launcher items into pages according to settings."""

        if self.settings.category_mode:
            # Category mode is rendered as a single scrollable page so headings do
            # not compete with the fixed mobile grid page size.
            self.pages = [self.state.items]
            return
        self.pages = chunked(self.state.items, self.settings.page_size)
        self.current_page = min(self.current_page, max(0, len(self.pages) - 1))

    def _build_window(self) -> None:
        """Create the layer-shell window and all child widgets."""

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX Desktop Grid")
        self.window.set_decorated(False)
        self.window.set_resizable(True)
        self.window.set_default_size(1280, 800)

        if LayerShell is not None:
            LayerShell.init_for_window(self.window)
            LayerShell.set_namespace(self.window, "neox-desktop-grid")
            LayerShell.set_layer(self.window, LayerShell.Layer.BACKGROUND)
            for edge in (LayerShell.Edge.TOP, LayerShell.Edge.RIGHT, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT):
                LayerShell.set_anchor(self.window, edge, True)
            LayerShell.set_exclusive_zone(self.window, -1)
        else:
            LOGGER.warning("gtk4-layer-shell not available; desktop grid runs as a normal window")

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        root.add_css_class("neox-grid-root")
        root.set_margin_top(72)
        root.set_margin_bottom(32)
        root.set_margin_start(48)
        root.set_margin_end(48)
        self.window.set_child(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.set_halign(Gtk.Align.CENTER)
        self.header_label = Gtk.Label(label="NEOX")
        self.header_label.add_css_class("neox-grid-title")
        header.append(self.header_label)
        search_button = Gtk.Button(label="⌕")
        search_button.set_tooltip_text("Arama aç (Super+Space)")
        search_button.add_css_class("neox-round-button")
        search_button.connect("clicked", lambda _button: self.bus.send("open-search"))
        header.append(search_button)
        root.append(header)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)
        self.stack.set_vexpand(True)
        root.append(self.stack)

        self.indicators = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.indicators.set_halign(Gtk.Align.CENTER)
        self.indicators.add_css_class("neox-page-indicators")
        root.append(self.indicators)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_scroll)
        self.window.add_controller(scroll)

        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self._on_key_pressed)
        self.window.add_controller(key)

        self._refresh_pages()
        self.window.present()

    def _refresh_pages(self) -> None:
        """Recreate page widgets from the current state."""

        if self.stack is None or self.indicators is None:
            return
        while child := self.stack.get_first_child():
            self.stack.remove(child)
        while child := self.indicators.get_first_child():
            self.indicators.remove(child)

        if self.settings.category_mode:
            page = self._build_category_page()
            self.stack.add_named(page, "page-0")
        else:
            for index, items in enumerate(self.pages):
                page = self._build_grid_page(items)
                self.stack.add_named(page, f"page-{index}")

        for index in range(max(1, len(self.pages))):
            button = Gtk.Button(label="●" if index == self.current_page else "○")
            button.add_css_class("neox-page-dot")
            button.connect("clicked", self._indicator_clicked, index)
            self.indicators.append(button)

        self._show_page(self.current_page)

    def _build_grid_page(self, items: list[dict[str, Any]]) -> Gtk.Widget:
        """Build one fixed-size mobile launcher page."""

        page = Gtk.Grid()
        page.set_column_homogeneous(True)
        page.set_row_homogeneous(True)
        page.set_column_spacing(14)
        page.set_row_spacing(18)
        page.set_valign(Gtk.Align.CENTER)
        page.set_halign(Gtk.Align.CENTER)
        page.add_css_class("neox-grid-page")

        for index, item in enumerate(items):
            row = index // self.settings.columns
            col = index % self.settings.columns
            if item.get("type") == "folder":
                widget = self._folder_cell(item)
            else:
                app = self.apps.get(str(item.get("id", "")))
                widget = self._app_cell(app) if app else Gtk.Box()
            page.attach(widget, col, row, 1, 1)
        return page

    def _build_category_page(self) -> Gtk.Widget:
        """Build the optional grouped-by-category view."""

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        outer.set_margin_start(32)
        outer.set_margin_end(32)
        outer.set_margin_bottom(32)
        groups: dict[str, list[DesktopEntry]] = {}
        for app in self.apps.values():
            groups.setdefault(category_label(app.categories), []).append(app)
        for label in sorted(groups):
            heading = Gtk.Label(label=label)
            heading.set_xalign(0.0)
            heading.add_css_class("neox-category-heading")
            outer.append(heading)
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_max_children_per_line(self.settings.columns)
            flow.set_min_children_per_line(min(4, self.settings.columns))
            flow.set_column_spacing(14)
            flow.set_row_spacing(18)
            for app in sorted(groups[label], key=lambda item: item.name.casefold()):
                flow.append(self._app_cell(app))
            outer.append(flow)
        scrolled.set_child(outer)
        return scrolled

    def _app_cell(self, app: DesktopEntry) -> Gtk.Widget:
        """Create a launcher cell for an application."""

        button = Gtk.Button()
        button.add_css_class("neox-app-cell")
        button.set_tooltip_text(app.comment or app.name)
        button.connect("clicked", self._launch_app, app)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        image = self._icon_widget(app.icon)
        image.set_pixel_size(self.settings.icon_size)
        label = Gtk.Label(label=app.name)
        label.add_css_class("neox-app-label")
        label.set_justify(Gtk.Justification.CENTER)
        label.set_max_width_chars(14)
        label.set_lines(2)
        label.set_wrap(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(image)
        box.append(label)
        button.set_child(box)

        right_click = Gtk.GestureClick.new()
        right_click.set_button(3)
        right_click.connect("pressed", self._show_context_menu, app)
        button.add_controller(right_click)

        drag = Gtk.DragSource.new()
        drag.set_actions(Gdk.DragAction.MOVE)
        drag.connect("prepare", self._drag_prepare, app.id)
        button.add_controller(drag)

        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect("drop", self._drop_on_app, app.id)
        button.add_controller(drop)
        return button

    def _folder_cell(self, item: dict[str, Any]) -> Gtk.Widget:
        """Create a launcher cell representing a folder."""

        name = str(item.get("name", "Klasör"))
        button = Gtk.Button()
        button.add_css_class("neox-app-cell")
        button.add_css_class("neox-folder-cell")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_halign(Gtk.Align.CENTER)
        image = Gtk.Image.new_from_icon_name("folder-symbolic")
        image.set_pixel_size(self.settings.icon_size)
        label = Gtk.Label(label=name)
        label.add_css_class("neox-app-label")
        label.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(image)
        box.append(label)
        button.set_child(box)
        button.connect("clicked", self._open_folder, item)

        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        first_id = str(item.get("items", [""])[0])
        drop.connect("drop", self._drop_on_app, first_id)
        button.add_controller(drop)
        return button

    def _icon_widget(self, icon: str) -> Gtk.Image:
        """Create a GTK image from an absolute icon path or icon theme name."""

        if icon_is_file(icon):
            return Gtk.Image.new_from_file(os.path.expanduser(icon))
        if icon:
            return Gtk.Image.new_from_icon_name(icon)
        return Gtk.Image.new_from_icon_name("application-x-executable-symbolic")

    def _launch_app(self, _button: Gtk.Button, app: DesktopEntry) -> None:
        """Launch an app and keep the desktop grid in the background."""

        LOGGER.info("Launching app from grid: %s", app.name)
        if not app.launch(LOGGER):
            self.bus.send("notification", {"title": "NEOX", "body": f"{app.name} başlatılamadı"})

    def _show_context_menu(self, gesture: Gtk.GestureClick, _n_press: int, x: float, y: float, app: DesktopEntry) -> None:
        """Show right-click actions for an app cell."""

        widget = cast(Gtk.Widget, gesture.get_widget())
        popover = Gtk.Popover()
        popover.set_parent(widget)
        popover.set_has_arrow(False)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        menu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        menu.add_css_class("neox-context-menu")
        favorite_text = "Favorilerden çıkar" if app.id in self.state.favorites else "Favorilere ekle"
        for label, callback in (
            (favorite_text, lambda _btn: self._toggle_favorite(app, popover)),
            ("Bilgi", lambda _btn: self._show_app_info(app, popover)),
            ("Kaldır", lambda _btn: self._uninstall_app(app, popover)),
        ):
            button = Gtk.Button(label=label)
            button.add_css_class("neox-context-button")
            button.connect("clicked", callback)
            menu.append(button)
        popover.set_child(menu)
        popover.popup()

    def _toggle_favorite(self, app: DesktopEntry, popover: Gtk.Popover) -> None:
        """Toggle an app's favorite state."""

        if app.id in self.state.favorites:
            self.state.favorites.remove(app.id)
        else:
            self.state.favorites.add(app.id)
        self.state.save()
        popover.popdown()

    def _show_app_info(self, app: DesktopEntry, popover: Gtk.Popover) -> None:
        """Display basic desktop-entry information in a dialog."""

        dialog = Gtk.AlertDialog(
            modal=True,
            message=app.name,
            detail=f"{app.comment}\n\nKomut: {app.exec}\nKategori: {', '.join(app.categories)}\nDosya: {app.path}",
        )
        if self.window is not None:
            dialog.show(self.window)
        popover.popdown()

    def _uninstall_app(self, app: DesktopEntry, popover: Gtk.Popover) -> None:
        """Try to open the proper uninstaller for Flatpak/Snap apps."""

        popover.popdown()
        path = app.path
        if "/flatpak/" in path:
            app_id = pathlib.Path(path).stem
            os.spawnlp(os.P_NOWAIT, "flatpak", "flatpak", "uninstall", app_id)
        elif "/snapd/" in path:
            snap_name = pathlib.Path(path).stem.split("_")[0]
            os.spawnlp(os.P_NOWAIT, "snap", "snap", "remove", snap_name)
        else:
            self.bus.send(
                "notification",
                {
                    "title": "NEOX",
                    "body": "Bu uygulama sistem paket yöneticisiyle kaldırılmalıdır.",
                },
            )

    def _drag_prepare(self, _source: Gtk.DragSource, _x: float, _y: float, app_id: str) -> Gdk.ContentProvider:
        """Provide the dragged application id as UTF-8 text."""

        return Gdk.ContentProvider.new_for_value(app_id)

    def _drop_on_app(self, _target: Gtk.DropTarget, value: str, _x: float, _y: float, target_id: str) -> bool:
        """Handle dropping one icon onto another.

        Holding Shift reorders before the target; a plain drop creates or extends
        a folder to match mobile launcher behavior.
        """

        source_id = str(value)
        if not source_id or source_id == target_id:
            return False
        modifiers = 0
        display = Gdk.Display.get_default()
        if display is not None:
            seat = display.get_default_seat()
            keyboard = seat.get_keyboard() if seat is not None else None
            # Some GDK backends do not expose current modifier state here; in
            # that case the default mobile behavior is folder creation.
            if keyboard is not None and hasattr(keyboard, "get_modifier_state"):
                try:
                    modifiers = int(keyboard.get_modifier_state())
                except Exception:
                    modifiers = 0
        if modifiers & Gdk.ModifierType.SHIFT_MASK:
            self.state.move_before(source_id, target_id)
        else:
            self.state.create_or_extend_folder(source_id, target_id)
        self.state.save()
        self._paginate()
        self._refresh_pages()
        return True

    def _open_folder(self, button: Gtk.Button, item: dict[str, Any]) -> None:
        """Open a folder popover with the contained applications."""

        if self.folder_popover is not None:
            self.folder_popover.popdown()
        popover = Gtk.Popover()
        popover.set_parent(button)
        popover.set_has_arrow(False)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_top(14)
        outer.set_margin_bottom(14)
        outer.set_margin_start(14)
        outer.set_margin_end(14)
        title = Gtk.Label(label=str(item.get("name", "Klasör")))
        title.add_css_class("neox-folder-title")
        outer.append(title)
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(4)
        for app_id in item.get("items", []):
            app = self.apps.get(str(app_id))
            if app is not None:
                flow.append(self._app_cell(app))
        outer.append(flow)
        popover.set_child(outer)
        self.folder_popover = popover
        popover.popup()

    def _indicator_clicked(self, _button: Gtk.Button, index: int) -> None:
        """Switch to a page when its dot is clicked."""

        self._show_page(index)

    def _show_page(self, index: int) -> None:
        """Show one launcher page and update the iOS-style indicators."""

        if self.stack is None or self.indicators is None:
            return
        self.current_page = max(0, min(index, max(0, len(self.pages) - 1)))
        self.stack.set_visible_child_name(f"page-{self.current_page}")
        child = self.indicators.get_first_child()
        idx = 0
        while child is not None:
            if isinstance(child, Gtk.Button):
                child.set_label("●" if idx == self.current_page else "○")
            child = child.get_next_sibling()
            idx += 1
        if self.header_label is not None:
            self.header_label.set_label(f"NEOX  ·  Sayfa {self.current_page + 1}/{max(1, len(self.pages))}")

    def _on_scroll(self, _controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        """Change pages with horizontal or vertical wheel gestures."""

        amount = dx if abs(dx) > abs(dy) else dy
        if amount > 0:
            self._show_page(self.current_page + 1)
        elif amount < 0:
            self._show_page(self.current_page - 1)
        return True

    def _on_key_pressed(self, _controller: Gtk.EventControllerKey, keyval: int, _keycode: int, _state: int) -> bool:
        """Keyboard navigation: arrows change pages, Escape hides/exits."""

        if keyval in (Gdk.KEY_Escape, Gdk.KEY_BackSpace):
            if self.toggle and self.window is not None:
                self.window.set_visible(not self.window.get_visible())
            else:
                self.quit()
            return True
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self._show_page(self.current_page + 1)
            return True
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self._show_page(self.current_page - 1)
            return True
        if keyval == Gdk.KEY_space:
            self.bus.send("open-search")
            return True
        return False

    def _install_css(self) -> None:
        """Install component-local CSS. Theme files can override these classes."""

        load_hd_css(Gtk, Gdk, profile="desktop-grid")
        css = f"""
        .neox-grid-root {{
            background: rgba(8, 12, 20, 0.34);
            color: white;
            font-family: Inter, Cantarell, sans-serif;
        }}
        .neox-grid-title {{
            font-size: 24px;
            font-weight: 700;
            text-shadow: 0 2px 8px rgba(0,0,0,0.45);
        }}
        .neox-grid-page {{
            padding: 18px;
        }}
        .neox-app-cell {{
            min-width: {self.settings.icon_size + 44}px;
            min-height: {self.settings.icon_size + 62}px;
            padding: 10px;
            border-radius: 24px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            transition: all 300ms cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .neox-app-cell:hover {{
            background: rgba(255,255,255,0.14);
            border-color: rgba(255,255,255,0.22);
            box-shadow: 0 12px 28px rgba(0,0,0,0.25);
            transform: scale(1.08);
        }}
        .neox-app-cell:active {{
            transform: scale(0.94);
        }}
        .neox-folder-cell {{
            background: rgba(59,130,246,0.15);
        }}
        .neox-app-label {{
            color: rgba(255,255,255,0.94);
            font-size: 13px;
            font-weight: 600;
            text-shadow: 0 1px 4px rgba(0,0,0,0.55);
        }}
        .neox-page-dot {{
            background: transparent;
            border: 0;
            color: rgba(255,255,255,0.78);
            font-size: 18px;
            padding: 2px 4px;
        }}
        .neox-round-button {{
            border-radius: 999px;
            min-width: 42px;
            min-height: 42px;
            background: rgba(255,255,255,0.12);
            color: white;
            font-size: 22px;
        }}
        .neox-context-menu, .neox-folder-title {{
            padding: 10px;
            border-radius: 18px;
            background: rgba(20,20,24,0.94);
            color: white;
        }}
        .neox-context-button {{
            border-radius: 12px;
            padding: 8px 12px;
        }}
        .neox-category-heading {{
            color: rgba(255,255,255,0.86);
            font-size: 18px;
            font-weight: 700;
            margin-top: 10px;
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="NEOX mobile-style desktop grid")
    parser.add_argument("--toggle", action="store_true", help="hide on Escape instead of exiting")
    parser.add_argument("--rescan", action="store_true", help="rescan applications and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Application entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.rescan:
        DesktopAppScanner(logger=LOGGER).scan(force=True)
        return 0
    if Gtk is None:
        LOGGER.error("GTK4/PyGObject is not available: %s", GTK_IMPORT_ERROR)
        return 1
    lock = SingletonLock("neox-desktop-grid")
    if not lock.acquire():
        # A second invocation from the key binding politely asks the daemon to open
        # the grid instead of creating a duplicate background layer.
        JsonLineClient(logger=LOGGER).send("open-desktop-grid")
        return 0
    try:
        return NeoxDesktopGrid(toggle=args.toggle).run([])
    except Exception as exc:
        LOGGER.exception("Desktop grid crashed: %s", exc)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

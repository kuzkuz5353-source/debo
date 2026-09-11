#!/usr/bin/env python3
"""NEOX Super-key task switcher.

The task switcher uses Hyprland IPC to list windows and focus/close/move them.
It renders a paged overlay with at most ten live window cards per page, keyboard
navigation, search filtering, close buttons and workspace drop targets.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import sys
import threading
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import (  # noqa: E402
    ConfigManager,
    HyprlandIPC,
    NEOX_RUNTIME_DIR,
    SingletonLock,
    chunked,
    run_command,
    setup_logging,
    temporary_png,
    which,
)
from neox_hd_ui import load_hd_css  # noqa: E402

LOGGER = setup_logging("neox-task-switcher")

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, GLib, GObject, Gtk, Pango

    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell
    except (ImportError, ValueError):
        LayerShell = None  # type: ignore[assignment]
except (ImportError, ValueError) as exc:  # pragma: no cover - GUI dependency.
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    GLib = None  # type: ignore[assignment]
    GObject = None  # type: ignore[assignment]
    Pango = None  # type: ignore[assignment]
    LayerShell = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


@dataclass(slots=True)
class WindowInfo:
    """Hyprland client information rendered as a switcher card."""

    address: str
    title: str
    app_class: str
    workspace: int
    workspace_name: str
    at: tuple[int, int]
    size: tuple[int, int]
    floating: bool = False

    @classmethod
    def from_hypr(cls, payload: dict[str, Any]) -> "WindowInfo":
        """Create a WindowInfo from ``hyprctl clients -j`` payload."""

        workspace = payload.get("workspace") or {}
        at = payload.get("at") or [0, 0]
        size = payload.get("size") or [800, 500]
        return cls(
            address=str(payload.get("address", "")),
            title=str(payload.get("title") or payload.get("class") or "Untitled"),
            app_class=str(payload.get("class") or "Application"),
            workspace=int(workspace.get("id", 0) or 0),
            workspace_name=str(workspace.get("name") or workspace.get("id") or ""),
            at=(int(at[0]), int(at[1])),
            size=(max(1, int(size[0])), max(1, int(size[1]))),
            floating=bool(payload.get("floating", False)),
        )

    @property
    def haystack(self) -> str:
        """Lowercase text used for filtering."""

        return f"{self.title} {self.app_class} {self.workspace_name}".lower()


class TaskSwitcher(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK overlay for switching among Hyprland windows."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.TaskSwitcher")
        self.config = ConfigManager()
        self.hyprland = HyprlandIPC(LOGGER)
        self.focus_mode = self.config.get("task_switcher", "focus_mode", "focus")
        self.max_per_page = max(1, self.config.getint("task_switcher", "max_per_page", 10))
        self.windows: list[WindowInfo] = []
        self.filtered: list[WindowInfo] = []
        self.pages: list[list[WindowInfo]] = []
        self.current_page = 0
        self.selected_index = 0
        self.window: Gtk.ApplicationWindow | None = None
        self.stack: Gtk.Stack | None = None
        self.indicators: Gtk.Label | None = None
        self.search_entry: Gtk.SearchEntry | None = None
        self.workspace_box: Gtk.Box | None = None

    def do_activate(self) -> None:
        """Build overlay and load current Hyprland clients."""

        self._install_css()
        self.reload_windows()
        self._build_window()

    def reload_windows(self) -> None:
        """Fetch and filter Hyprland clients."""

        clients = self.hyprland.clients()
        self.windows = [WindowInfo.from_hypr(client) for client in clients if client.get("mapped", True)]
        self.filtered = list(self.windows)
        self._paginate()

    def _paginate(self) -> None:
        """Split windows into max-ten pages."""

        self.pages = chunked(self.filtered, self.max_per_page)
        self.current_page = min(self.current_page, max(0, len(self.pages) - 1))
        self.selected_index = min(self.selected_index, max(0, len(self.filtered) - 1))

    def _build_window(self) -> None:
        """Create the fullscreen layer-shell overlay."""

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX Task Switcher")
        self.window.set_decorated(False)
        self.window.set_default_size(1280, 800)
        if LayerShell is not None:
            LayerShell.init_for_window(self.window)
            LayerShell.set_namespace(self.window, "neox-task-switcher")
            LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
            for edge in (LayerShell.Edge.TOP, LayerShell.Edge.RIGHT, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT):
                LayerShell.set_anchor(self.window, edge, True)
            LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.EXCLUSIVE)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.add_css_class("neox-switcher-root")
        outer.set_margin_top(36)
        outer.set_margin_bottom(36)
        outer.set_margin_start(46)
        outer.set_margin_end(46)
        self.window.set_child(outer)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title = Gtk.Label(label="Açık Pencereler")
        title.add_css_class("neox-switcher-title")
        title.set_hexpand(True)
        title.set_xalign(0.0)
        top.append(title)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Pencere ara…")
        self.search_entry.set_width_chars(28)
        self.search_entry.connect("search-changed", self._filter_changed)
        top.append(self.search_entry)
        close_all = Gtk.Button(label="Tümünü Kapat")
        close_all.add_css_class("danger")
        close_all.connect("clicked", lambda _button: self._close_all())
        top.append(close_all)
        outer.append(top)

        self.workspace_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.workspace_box.add_css_class("neox-workspaces")
        outer.append(self.workspace_box)

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)
        outer.append(self.stack)

        self.indicators = Gtk.Label(label="")
        self.indicators.add_css_class("neox-switcher-indicators")
        outer.append(self.indicators)

        key = Gtk.EventControllerKey.new()
        key.connect("key-pressed", self._on_key)
        self.window.add_controller(key)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._on_scroll)
        self.window.add_controller(scroll)

        self._refresh()
        self.window.present()
        if self.search_entry is not None:
            self.search_entry.grab_focus()
        self._capture_thumbnails_async()

    def _refresh(self) -> None:
        """Refresh page stack, indicators and workspace chips."""

        if self.stack is None:
            return
        while child := self.stack.get_first_child():
            self.stack.remove(child)
        for page_index, page in enumerate(self.pages):
            self.stack.add_named(self._build_page(page), f"page-{page_index}")
        self._refresh_workspaces()
        self._show_page(self.current_page)

    def _build_page(self, windows: list[WindowInfo]) -> Gtk.Widget:
        """Build a page with a dynamic grid based on window count."""

        count = max(1, len(windows))
        cols, rows = self._grid_dimensions(count)
        grid = Gtk.Grid()
        grid.set_column_homogeneous(True)
        grid.set_row_homogeneous(True)
        grid.set_column_spacing(18)
        grid.set_row_spacing(18)
        grid.set_valign(Gtk.Align.CENTER)
        grid.set_halign(Gtk.Align.CENTER)
        for index, info in enumerate(windows):
            card = self._window_card(info)
            grid.attach(card, index % cols, index // cols, 1, 1)
        return grid

    def _grid_dimensions(self, count: int) -> tuple[int, int]:
        """Return requested dynamic grid dimensions for count 1-10."""

        if count <= 1:
            return (1, 1)
        if count == 2:
            return (2, 1)
        if count == 3:
            return (3, 1)
        if count == 4:
            return (2, 2)
        if count <= 6:
            return (3, 2)
        if count <= 8:
            return (4, 2)
        return (5, 2)

    def _window_card(self, info: WindowInfo) -> Gtk.Widget:
        """Create a switcher card with thumbnail, title, icon and close button."""

        overlay = Gtk.Overlay()
        overlay.add_css_class("neox-window-card")
        button = Gtk.Button()
        button.add_css_class("neox-window-button")
        button.connect("clicked", lambda _button: self._focus(info))
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        content.set_margin_start(10)
        content.set_margin_end(10)

        thumb = self._thumbnail_widget(info)
        thumb.set_vexpand(True)
        content.append(thumb)
        label = Gtk.Label(label=info.title)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.add_css_class("neox-window-title")
        content.append(label)
        meta = Gtk.Label(label=f"{info.app_class} · Workspace {info.workspace_name}")
        meta.set_ellipsize(Pango.EllipsizeMode.END)
        meta.add_css_class("neox-window-meta")
        content.append(meta)
        button.set_child(content)
        overlay.set_child(button)

        icon = Gtk.Label(label=info.app_class[:2].upper())
        icon.add_css_class("neox-card-icon")
        icon.set_halign(Gtk.Align.START)
        icon.set_valign(Gtk.Align.START)
        icon.set_margin_start(14)
        icon.set_margin_top(14)
        overlay.add_overlay(icon)

        close = Gtk.Button(label="×")
        close.add_css_class("neox-card-close")
        close.set_halign(Gtk.Align.END)
        close.set_valign(Gtk.Align.START)
        close.set_margin_end(14)
        close.set_margin_top(14)
        close.connect("clicked", lambda _button: self._close(info))
        overlay.add_overlay(close)

        drag = Gtk.DragSource.new()
        drag.set_actions(Gdk.DragAction.MOVE)
        drag.connect("prepare", lambda _source, _x, _y: Gdk.ContentProvider.new_for_value(info.address))
        overlay.add_controller(drag)
        return overlay

    def _thumbnail_widget(self, info: WindowInfo) -> Gtk.Widget:
        """Return a screenshot thumbnail if present, otherwise a styled placeholder."""

        path = self._thumbnail_path(info)
        if path.exists():
            image = Gtk.Picture.new_for_filename(str(path))
            image.set_content_fit(Gtk.ContentFit.COVER)
            image.add_css_class("neox-thumbnail")
            return image
        placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        placeholder.add_css_class("neox-thumbnail-placeholder")
        placeholder.set_size_request(260 if len(self.filtered) > 1 else 720, 170 if len(self.filtered) > 1 else 420)
        big = Gtk.Label(label=info.app_class[:1].upper() or "•")
        big.add_css_class("neox-placeholder-letter")
        placeholder.append(big)
        text = Gtk.Label(label=info.title)
        text.set_ellipsize(Pango.EllipsizeMode.END)
        placeholder.append(text)
        return placeholder

    def _thumbnail_path(self, info: WindowInfo) -> pathlib.Path:
        """Return cache path for a window thumbnail."""

        safe = info.address.replace("0x", "").replace(":", "_")
        return NEOX_RUNTIME_DIR / f"thumb-{safe}.png"

    def _capture_thumbnails_async(self) -> None:
        """Capture current window rectangles with grim on a background thread."""

        if not which("grim"):
            return

        def worker() -> None:
            changed = False
            for info in self.filtered[: self.max_per_page]:
                path = self._thumbnail_path(info)
                geometry = f"{info.at[0]},{info.at[1]} {info.size[0]}x{info.size[1]}"
                result = run_command(["grim", "-g", geometry, str(path)], timeout=1.5, logger=LOGGER)
                changed = changed or result.returncode == 0
            if changed:
                GLib.idle_add(self._refresh)

        threading.Thread(target=worker, name="neox-thumbnail-capture", daemon=True).start()

    def _refresh_workspaces(self) -> None:
        """Render workspace counts and drop targets."""

        if self.workspace_box is None:
            return
        while child := self.workspace_box.get_first_child():
            self.workspace_box.remove(child)
        counts: dict[int, int] = {}
        for info in self.windows:
            counts[info.workspace] = counts.get(info.workspace, 0) + 1
        for workspace in sorted(counts):
            chip = Gtk.Label(label=f"{workspace}: {counts[workspace]}")
            chip.add_css_class("neox-workspace-chip")
            drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
            drop.connect("drop", self._drop_on_workspace, workspace)
            chip.add_controller(drop)
            self.workspace_box.append(chip)

    def _show_page(self, index: int) -> None:
        """Show one page and update page indicator text."""

        self.current_page = max(0, min(index, max(0, len(self.pages) - 1)))
        if self.stack is not None:
            self.stack.set_visible_child_name(f"page-{self.current_page}")
        if self.indicators is not None:
            dots = " ".join("●" if idx == self.current_page else "○" for idx in range(max(1, len(self.pages))))
            self.indicators.set_label(f"{dots}   Sayfa {self.current_page + 1}/{max(1, len(self.pages))}")

    def _filter_changed(self, entry: Gtk.SearchEntry) -> None:
        """Filter windows by title/class/workspace."""

        query = entry.get_text().strip().lower()
        self.filtered = [info for info in self.windows if query in info.haystack] if query else list(self.windows)
        self._paginate()
        self._refresh()

    def _focus(self, info: WindowInfo) -> None:
        """Focus the selected window and optionally fullscreen it."""

        LOGGER.info("Focusing window %s %s", info.address, info.title)
        self.hyprland.dispatch("focuswindow", f"address:{info.address}")
        if self.focus_mode == "fullscreen":
            self.hyprland.dispatch("fullscreen", "1")
        self.quit()

    def _close(self, info: WindowInfo) -> None:
        """Close one window and refresh the switcher."""

        self.hyprland.dispatch("closewindow", f"address:{info.address}")
        GLib.timeout_add(200, lambda: (self.reload_windows(), self._refresh(), False)[2])

    def _close_all(self) -> None:
        """Close all visible filtered windows after a user click."""

        for info in list(self.filtered):
            self.hyprland.dispatch("closewindow", f"address:{info.address}")
        self.quit()

    def _drop_on_workspace(self, _target: Gtk.DropTarget, address: str, _x: float, _y: float, workspace: int) -> bool:
        """Move a dragged window to another workspace."""

        if not address:
            return False
        self.hyprland.dispatch("movetoworkspacesilent", f"{workspace},address:{address}")
        GLib.timeout_add(200, lambda: (self.reload_windows(), self._refresh(), False)[2])
        return True

    def _on_scroll(self, _controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        """Mouse wheel page navigation."""

        amount = dx if abs(dx) > abs(dy) else dy
        if amount > 0:
            self._show_page(self.current_page + 1)
        elif amount < 0:
            self._show_page(self.current_page - 1)
        return True

    def _on_key(self, _controller: Gtk.EventControllerKey, keyval: int, _keycode: int, _state: int) -> bool:
        """Keyboard controls for page/window navigation."""

        if keyval == Gdk.KEY_Escape:
            self.quit()
            return True
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self._show_page(self.current_page + 1)
            return True
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self._show_page(self.current_page - 1)
            return True
        if keyval == Gdk.KEY_Tab:
            if self.filtered:
                self.selected_index = (self.selected_index + 1) % len(self.filtered)
                self._show_page(self.selected_index // self.max_per_page)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.filtered:
                self._focus(self.filtered[self.selected_index])
            return True
        return False

    def _install_css(self) -> None:
        """Install task switcher CSS."""

        load_hd_css(Gtk, Gdk, profile="task-switcher")
        css = """
        .neox-switcher-root {
            background: rgba(8,10,16,0.58);
            color: white;
            font-family: Inter, Cantarell, sans-serif;
        }
        .neox-switcher-title { font-size: 28px; font-weight: 900; text-shadow: 0 2px 10px rgba(0,0,0,0.55); }
        searchentry, entry { border-radius: 22px; padding: 0 14px; min-height: 42px; background: rgba(255,255,255,0.10); color: white; }
        button { border-radius: 16px; }
        button.danger { background: rgba(239,68,68,0.20); color: white; border: 1px solid rgba(239,68,68,0.35); }
        .neox-window-card {
            min-width: 260px;
            min-height: 230px;
            border-radius: 28px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.10);
            box-shadow: 0 18px 44px rgba(0,0,0,0.35);
            transition: all 300ms cubic-bezier(0.4, 0, 0.2, 1);
        }
        .neox-window-card:hover {
            background: rgba(255,255,255,0.12);
            border-color: rgba(96,165,250,0.85);
            transform: scale(1.035);
        }
        .neox-window-button { background: transparent; border: 0; color: white; }
        .neox-thumbnail, .neox-thumbnail-placeholder { border-radius: 20px; background: linear-gradient(135deg, #172033, #0f172a); }
        .neox-thumbnail-placeholder { padding: 24px; color: rgba(255,255,255,0.74); }
        .neox-placeholder-letter { font-size: 52px; font-weight: 900; color: #60a5fa; }
        .neox-window-title { font-weight: 800; color: white; }
        .neox-window-meta { font-size: 12px; color: rgba(255,255,255,0.60); }
        .neox-card-icon { padding: 6px 8px; border-radius: 12px; background: rgba(15,23,42,0.80); color: #bfdbfe; font-weight: 900; }
        .neox-card-close { opacity: 0.72; min-width: 30px; min-height: 30px; border-radius: 999px; background: rgba(239,68,68,0.70); color: white; }
        .neox-workspaces { padding: 4px; }
        .neox-workspace-chip { padding: 7px 12px; border-radius: 999px; background: rgba(255,255,255,0.09); color: rgba(255,255,255,0.84); }
        .neox-switcher-indicators { font-size: 15px; color: rgba(255,255,255,0.82); }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX Hyprland task switcher")
    parser.add_argument("--list", action="store_true", help="print Hyprland clients and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.list:
        for item in HyprlandIPC(LOGGER).clients():
            info = WindowInfo.from_hypr(item)
            print(f"{info.address}  ws={info.workspace}  {info.app_class}: {info.title}")
        return 0
    if Gtk is None:
        LOGGER.error("GTK4/PyGObject is not available: %s", GTK_IMPORT_ERROR)
        return 1
    lock = SingletonLock("neox-task-switcher")
    if not lock.acquire():
        return 0
    try:
        return TaskSwitcher().run([])
    except Exception as exc:
        LOGGER.exception("Task switcher crashed: %s", exc)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""NEOX wallpaper manager.

Supports static wallpapers via hyprpaper/swaybg, slideshow mode, per-monitor
assignment, optional live wallpapers via mpvpaper and accent-color extraction.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import threading
import time
from dataclasses import dataclass
from typing import Iterable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import ConfigManager, HyprlandIPC, JsonLineClient, NEOX_CONFIG_DIR, SingletonLock, read_json, run_command, setup_logging, which, write_json

LOGGER = setup_logging("neox-wallpaper-manager")
STATE_PATH = NEOX_CONFIG_DIR / "wallpapers.json"
SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency.
    Image = None  # type: ignore[assignment]

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


@dataclass(slots=True)
class WallpaperState:
    """Persistent wallpaper settings."""

    current: str = ""
    monitor_map: dict[str, str] | None = None
    slideshow_dir: str = ""
    slideshow_interval: int = 900
    live: bool = False


class WallpaperManager:
    """Non-UI wallpaper manager API."""

    def __init__(self) -> None:
        self.config = ConfigManager()
        payload = read_json(STATE_PATH, {})
        self.state = WallpaperState(
            current=str(payload.get("current", "")),
            monitor_map=dict(payload.get("monitor_map", {})),
            slideshow_dir=str(payload.get("slideshow_dir", "")),
            slideshow_interval=int(payload.get("slideshow_interval", 900)),
            live=bool(payload.get("live", False)),
        )
        self.bus = JsonLineClient(logger=LOGGER)
        self.hyprland = HyprlandIPC(LOGGER)

    def save(self) -> None:
        """Persist wallpaper state."""

        write_json(STATE_PATH, self.state.__dict__)

    def set_wallpaper(self, path: pathlib.Path, monitor: str = "") -> bool:
        """Apply a static wallpaper to one monitor or all monitors."""

        path = path.expanduser().resolve()
        if not path.exists() or path.suffix.lower() not in SUPPORTED:
            LOGGER.error("Unsupported wallpaper: %s", path)
            return False
        applied = False
        if which("hyprctl") and which("hyprpaper"):
            run_command(["hyprctl", "hyprpaper", "preload", str(path)], timeout=3, logger=LOGGER)
            target = monitor or ""
            result = run_command(["hyprctl", "hyprpaper", "wallpaper", f"{target},{path}"], timeout=3, logger=LOGGER)
            applied = result.returncode == 0
        if not applied and which("swaybg"):
            os.system("pkill -x swaybg >/dev/null 2>&1")
            os.spawnlp(os.P_NOWAIT, "swaybg", "swaybg", "-m", "fill", "-i", str(path))
            applied = True
        if applied:
            self.state.current = str(path)
            if monitor:
                assert self.state.monitor_map is not None
                self.state.monitor_map[monitor] = str(path)
            self.state.live = False
            self.save()
            accent = self.extract_accent(path)
            self.bus.send("wallpaper-changed", {"path": str(path), "monitor": monitor, "accent": accent})
        return applied

    def set_live_wallpaper(self, path: pathlib.Path, monitor: str = "*") -> bool:
        """Apply a video/live wallpaper through mpvpaper."""

        if not which("mpvpaper"):
            LOGGER.error("mpvpaper is required for live wallpapers")
            return False
        path = path.expanduser().resolve()
        if not path.exists():
            return False
        os.system("pkill -x mpvpaper >/dev/null 2>&1")
        os.spawnlp(os.P_NOWAIT, "mpvpaper", "mpvpaper", monitor, str(path))
        self.state.current = str(path)
        self.state.live = True
        self.save()
        self.bus.send("wallpaper-changed", {"path": str(path), "live": True})
        return True

    def gallery(self, directories: Iterable[pathlib.Path] | None = None) -> list[pathlib.Path]:
        """Return wallpaper files from common directories."""

        dirs = list(directories or []) or [
            NEOX_CONFIG_DIR / "wallpapers",
            pathlib.Path.home() / "Pictures" / "Wallpapers",
            pathlib.Path("/usr/share/neox/assets/wallpapers"),
            pathlib.Path(__file__).resolve().parent.parent / "assets" / "wallpapers",
        ]
        files: list[pathlib.Path] = []
        for directory in dirs:
            if not directory.exists():
                continue
            for file_path in sorted(directory.iterdir()):
                if file_path.suffix.lower() in SUPPORTED:
                    files.append(file_path)
        return files

    def extract_accent(self, path: pathlib.Path) -> str:
        """Extract a bright average accent color from a wallpaper."""

        if Image is None:
            return self.config.get("appearance", "accent", "#3b82f6")
        try:
            image = Image.open(path).convert("RGB")
            image.thumbnail((64, 64))
            pixels = list(image.getdata())
        except Exception as exc:
            LOGGER.debug("Cannot extract wallpaper color: %s", exc)
            return "#3b82f6"
        # Prefer saturated and bright pixels for a pleasant accent.
        def weight(pixel: tuple[int, int, int]) -> float:
            r, g, b = pixel
            return (max(pixel) - min(pixel)) * 1.5 + (r + g + b) / 3
        selected = sorted(pixels, key=weight, reverse=True)[: max(1, len(pixels) // 8)]
        r = sum(pixel[0] for pixel in selected) // len(selected)
        g = sum(pixel[1] for pixel in selected) // len(selected)
        b = sum(pixel[2] for pixel in selected) // len(selected)
        return f"#{r:02x}{g:02x}{b:02x}"

    def run_slideshow(self, directory: pathlib.Path, interval: int) -> None:
        """Run a blocking wallpaper slideshow loop."""

        images = self.gallery([directory])
        if not images:
            LOGGER.error("No wallpapers found in %s", directory)
            return
        index = 0
        while True:
            self.set_wallpaper(images[index % len(images)])
            index += 1
            time.sleep(max(30, interval))


class WallpaperWindow(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK wallpaper gallery."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.WallpaperManager")
        self.manager = WallpaperManager()

    def do_activate(self) -> None:
        """Build gallery UI."""

        self._install_css()
        window = Gtk.ApplicationWindow(application=self)
        window.set_title("NEOX Wallpaper Manager")
        window.set_default_size(900, 620)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)
        root.add_css_class("root")
        window.set_child(root)
        header = Gtk.Label(label="Duvar Kağıtları")
        header.set_xalign(0)
        header.add_css_class("title")
        root.append(header)
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(4)
        flow.set_column_spacing(12)
        flow.set_row_spacing(12)
        for path in self.manager.gallery():
            flow.append(self._wallpaper_card(path))
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(flow)
        root.append(scrolled)
        window.present()

    def _wallpaper_card(self, path: pathlib.Path) -> Gtk.Widget:
        """Create one clickable wallpaper preview."""

        button = Gtk.Button()
        button.add_css_class("card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        picture = Gtk.Picture.new_for_filename(str(path))
        picture.set_size_request(180, 110)
        picture.set_content_fit(Gtk.ContentFit.COVER)
        label = Gtk.Label(label=path.name)
        box.append(picture)
        box.append(label)
        button.set_child(box)
        button.connect("clicked", lambda _button: self.manager.set_wallpaper(path))
        return button

    def _install_css(self) -> None:
        """Install gallery CSS."""

        css = """
        .root { background: #111827; color: white; }
        .title { font-size: 28px; font-weight: 900; }
        .card { border-radius: 22px; padding: 10px; background: rgba(255,255,255,0.08); color: white; }
        .card:hover { background: rgba(59,130,246,0.24); }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI args."""

    parser = argparse.ArgumentParser(description="NEOX wallpaper manager")
    parser.add_argument("--set", dest="wallpaper", help="set static wallpaper")
    parser.add_argument("--monitor", default="", help="target monitor name for --set")
    parser.add_argument("--live", help="set live wallpaper with mpvpaper")
    parser.add_argument("--daemon", action="store_true", help="run saved slideshow if configured")
    parser.add_argument("--slideshow", help="directory for slideshow")
    parser.add_argument("--interval", type=int, default=900, help="slideshow interval seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    manager = WallpaperManager()
    if args.wallpaper:
        return 0 if manager.set_wallpaper(pathlib.Path(args.wallpaper), args.monitor) else 1
    if args.live:
        return 0 if manager.set_live_wallpaper(pathlib.Path(args.live), args.monitor or "*") else 1
    if args.slideshow:
        manager.run_slideshow(pathlib.Path(args.slideshow), args.interval)
        return 0
    if args.daemon:
        if manager.state.slideshow_dir:
            manager.run_slideshow(pathlib.Path(manager.state.slideshow_dir), manager.state.slideshow_interval)
        return 0
    if Gtk is None:
        LOGGER.error("GTK4/PyGObject is not available: %s", GTK_IMPORT_ERROR)
        return 1
    lock = SingletonLock("neox-wallpaper-manager")
    if not lock.acquire():
        return 0
    try:
        return WallpaperWindow().run([])
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

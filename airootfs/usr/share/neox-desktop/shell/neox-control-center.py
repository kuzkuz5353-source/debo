#!/usr/bin/env python3
"""NEOX control center and settings application."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from typing import Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import ConfigManager, JsonLineClient, SingletonLock, run_command, setup_logging, which
from neox_hd_ui import load_hd_css

LOGGER = setup_logging("neox-control-center")

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gtk

    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LayerShell
    except (ImportError, ValueError):
        LayerShell = None  # type: ignore[assignment]
except (ImportError, ValueError) as exc:
    Gtk = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    LayerShell = None  # type: ignore[assignment]
    GTK_IMPORT_ERROR = exc
else:
    GTK_IMPORT_ERROR = None


class ControlCenter(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK control center with quick toggles and full settings pages."""

    def __init__(self, quick: bool = False) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.ControlCenter")
        self.quick = quick
        self.config = ConfigManager()
        self.bus = JsonLineClient(logger=LOGGER)
        self.window: Gtk.ApplicationWindow | None = None
        self.stack: Gtk.Stack | None = None

    def do_activate(self) -> None:
        """Build control center window."""

        self._install_css()
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX Control Center")
        self.window.set_default_size(920, 640)
        if self.quick and LayerShell is not None:
            self.window.set_decorated(False)
            LayerShell.init_for_window(self.window)
            LayerShell.set_namespace(self.window, "neox-control-center")
            LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
            LayerShell.set_anchor(self.window, LayerShell.Edge.TOP, True)
            LayerShell.set_margin(self.window, LayerShell.Edge.TOP, 72)
            LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.ON_DEMAND)
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.add_css_class("root")
        self.window.set_child(root)

        nav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        nav.add_css_class("sidebar")
        nav.set_size_request(220, -1)
        root.append(nav)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_hexpand(True)
        root.append(self.stack)

        pages = [
            ("quick", "Hızlı Ayarlar", self._quick_settings()),
            ("appearance", "Görünüm", self._appearance_page()),
            ("display", "Ekran", self._display_page()),
            ("sound", "Ses", self._sound_page()),
            ("network", "Ağ", self._network_page()),
            ("bluetooth", "Bluetooth", self._bluetooth_page()),
            ("power", "Güç", self._power_page()),
            ("users", "Kullanıcılar", self._simple_page("Kullanıcılar", ["Hesap adı", os.environ.get("USER", "user"), "Avatar", "~/.face"])),
            ("locale", "Dil ve Bölge", self._simple_page("Dil ve Bölge", ["Klavye", "tr,us", "Saat dilimi", "Europe/Istanbul"])),
            ("accessibility", "Erişilebilirlik", self._accessibility_page()),
            ("about", "Hakkında", self._about_page()),
        ]
        for name, label, page in pages:
            self.stack.add_titled(page, name, label)
            button = Gtk.Button(label=label)
            button.add_css_class("nav-button")
            button.connect("clicked", lambda _button, target=name: self.stack.set_visible_child_name(target))
            nav.append(button)
        self.stack.set_visible_child_name("quick" if self.quick else "appearance")
        self.window.present()

    def _quick_settings(self) -> Gtk.Widget:
        """Build quick toggle and slider panel."""

        page = self._page("Hızlı Ayarlar")
        grid = Gtk.Grid()
        grid.set_column_homogeneous(True)
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        page.append(grid)
        toggles = [
            ("Wi‑Fi", self._wifi_state, self._toggle_wifi),
            ("Bluetooth", self._bluetooth_state, self._toggle_bluetooth),
            ("Gece Işığı", lambda: False, lambda active: self._night_light(active)),
            ("Rahatsız Etme", lambda: False, lambda active: self.bus.send("dnd", {"enabled": active})),
            ("Döndürme Kilidi", lambda: False, lambda active: LOGGER.info("Rotation lock: %s", active)),
            ("Uçak Modu", lambda: False, lambda active: self._airplane(active)),
            ("Ekran Paylaşımı", lambda: False, lambda active: LOGGER.info("Screen share toggle: %s", active)),
        ]
        for index, (label, state, callback) in enumerate(toggles):
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("tile")
            button.set_active(bool(state()))
            button.connect("toggled", lambda widget, cb=callback: cb(widget.get_active()))
            grid.attach(button, index % 2, index // 2, 1, 1)
        page.append(self._slider("Ses", self._get_volume(), self._set_volume))
        page.append(self._slider("Parlaklık", self._get_brightness(), self._set_brightness))
        return page

    def _appearance_page(self) -> Gtk.Widget:
        """Build appearance settings."""

        page = self._page("Görünüm")
        for label, command in (
            ("Koyu Tema", "neox-theme-engine neox-dark"),
            ("Açık Tema", "neox-theme-engine neox-light"),
            ("Nord Tema", "neox-theme-engine neox-nord"),
            ("Duvar Kağıdı Yöneticisi", "neox-wallpaper-manager"),
        ):
            page.append(self._action_row(label, lambda cmd=command: os.system(f"{cmd} &")))
        page.append(self._info_row("Köşe yuvarlatma", self.config.get("appearance", "corner_radius", "12")))
        page.append(self._info_row("İkon boyutu", self.config.get("desktop_grid", "icon_size", "72")))
        return page

    def _display_page(self) -> Gtk.Widget:
        """Build display page using hyprctl monitors."""

        page = self._page("Ekran")
        result = run_command(["hyprctl", "monitors"], timeout=2, logger=LOGGER)
        page.append(self._multiline(result.stdout or "Hyprland monitör bilgisi alınamadı."))
        return page

    def _sound_page(self) -> Gtk.Widget:
        """Build sound page."""

        page = self._page("Ses")
        page.append(self._slider("Çıkış Ses Seviyesi", self._get_volume(), self._set_volume))
        result = run_command(["wpctl", "status"], timeout=2, logger=LOGGER) if which("wpctl") else None
        page.append(self._multiline(result.stdout if result else "wpctl bulunamadı."))
        return page

    def _network_page(self) -> Gtk.Widget:
        """Build network page."""

        page = self._page("Ağ")
        page.append(self._action_row("Wi‑Fi Yenile", lambda: self._refresh_network_page(page)))
        result = run_command(["nmcli", "device", "wifi", "list"], timeout=5, logger=LOGGER) if which("nmcli") else None
        page.append(self._multiline(result.stdout if result else "NetworkManager bulunamadı."))
        return page

    def _bluetooth_page(self) -> Gtk.Widget:
        """Build Bluetooth page."""

        page = self._page("Bluetooth")
        page.append(self._action_row("Taramayı Başlat", lambda: run_command(["bluetoothctl", "scan", "on"], timeout=2, logger=LOGGER)))
        result = run_command(["bluetoothctl", "devices"], timeout=3, logger=LOGGER) if which("bluetoothctl") else None
        page.append(self._multiline(result.stdout if result else "BlueZ bluetoothctl bulunamadı."))
        return page

    def _power_page(self) -> Gtk.Widget:
        """Build power settings."""

        page = self._page("Güç")
        for label, command in (("Uyut", "systemctl suspend"), ("Yeniden Başlat", "systemctl reboot"), ("Kapat", "systemctl poweroff")):
            page.append(self._action_row(label, lambda cmd=command: os.system(cmd)))
        result = run_command(["powerprofilesctl", "get"], timeout=2, logger=LOGGER) if which("powerprofilesctl") else None
        page.append(self._info_row("Performans Profili", result.stdout.strip() if result else "powerprofilesctl yok"))
        return page

    def _accessibility_page(self) -> Gtk.Widget:
        """Build accessibility toggles."""

        page = self._page("Erişilebilirlik")
        for label in ("Büyük metin", "Yüksek kontrast", "Renk körlüğü filtresi", "Ekran büyüteci"):
            toggle = Gtk.ToggleButton(label=label)
            toggle.add_css_class("tile")
            toggle.connect("toggled", lambda button, name=label: LOGGER.info("Accessibility %s=%s", name, button.get_active()))
            page.append(toggle)
        return page

    def _about_page(self) -> Gtk.Widget:
        """Build about page."""

        page = self._page("Hakkında")
        uname = run_command(["uname", "-a"], timeout=2, logger=LOGGER).stdout.strip()
        page.append(self._info_row("NEOX Sürümü", "0.1.0"))
        page.append(self._info_row("Oturum", os.environ.get("XDG_CURRENT_DESKTOP", "NEOX")))
        page.append(self._multiline(uname))
        return page

    def _page(self, title: str) -> Gtk.Box:
        """Create a standard settings page."""

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(22)
        page.set_margin_bottom(22)
        page.set_margin_start(24)
        page.set_margin_end(24)
        heading = Gtk.Label(label=title)
        heading.set_xalign(0)
        heading.add_css_class("heading")
        page.append(heading)
        return page

    def _simple_page(self, title: str, values: list[str]) -> Gtk.Widget:
        """Build a simple key/value page."""

        page = self._page(title)
        for index in range(0, len(values), 2):
            page.append(self._info_row(values[index], values[index + 1] if index + 1 < len(values) else ""))
        return page

    def _info_row(self, label: str, value: str) -> Gtk.Widget:
        """Create an information row."""

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("row")
        left = Gtk.Label(label=label)
        left.set_xalign(0)
        left.set_hexpand(True)
        right = Gtk.Label(label=value)
        right.add_css_class("muted")
        row.append(left)
        row.append(right)
        return row

    def _action_row(self, label: str, action: Callable[[], object]) -> Gtk.Widget:
        """Create a clickable action row."""

        button = Gtk.Button(label=label)
        button.add_css_class("row-button")
        button.connect("clicked", lambda _button: action())
        return button

    def _multiline(self, text: str) -> Gtk.Widget:
        """Create a scrollable monospace text label."""

        label = Gtk.Label(label=text or "—")
        label.set_xalign(0)
        label.set_yalign(0)
        label.set_wrap(True)
        label.add_css_class("monospace")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(180)
        scrolled.set_child(label)
        return scrolled

    def _slider(self, label: str, initial: int, callback: Callable[[int], None]) -> Gtk.Widget:
        """Create a labeled percentage slider."""

        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title = Gtk.Label(label=f"{label}: {initial}%")
        title.set_xalign(0)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        scale.set_value(initial)
        scale.connect("value-changed", lambda widget: (title.set_label(f"{label}: {int(widget.get_value())}%"), callback(int(widget.get_value()))))
        row.append(title)
        row.append(scale)
        return row

    def _wifi_state(self) -> bool:
        """Return NetworkManager Wi-Fi radio state."""

        if not which("nmcli"):
            return False
        return "enabled" in run_command(["nmcli", "radio", "wifi"], timeout=1, logger=LOGGER).stdout

    def _toggle_wifi(self, active: bool) -> None:
        """Toggle Wi-Fi radio."""

        if which("nmcli"):
            run_command(["nmcli", "radio", "wifi", "on" if active else "off"], timeout=3, logger=LOGGER)

    def _bluetooth_state(self) -> bool:
        """Return Bluetooth rfkill state."""

        if not which("rfkill"):
            return False
        return "yes" not in run_command(["rfkill", "list", "bluetooth"], timeout=1, logger=LOGGER).stdout.lower()

    def _toggle_bluetooth(self, active: bool) -> None:
        """Toggle Bluetooth via rfkill."""

        if which("rfkill"):
            run_command(["rfkill", "unblock" if active else "block", "bluetooth"], timeout=2, logger=LOGGER)

    def _night_light(self, active: bool) -> None:
        """Toggle night light using gammastep if available."""

        if active and which("gammastep"):
            os.spawnlp(os.P_NOWAIT, "gammastep", "gammastep", "-O", "4200")
        else:
            os.system("pkill gammastep >/dev/null 2>&1")

    def _airplane(self, active: bool) -> None:
        """Toggle airplane mode by blocking radios."""

        if which("nmcli"):
            run_command(["nmcli", "radio", "all", "off" if active else "on"], timeout=3, logger=LOGGER)
        if which("rfkill"):
            run_command(["rfkill", "block" if active else "unblock", "bluetooth"], timeout=2, logger=LOGGER)

    def _get_volume(self) -> int:
        """Return PipeWire volume percent."""

        if not which("wpctl"):
            return 0
        text = run_command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], timeout=1, logger=LOGGER).stdout
        match = re.search(r"([0-9.]+)", text)
        return int(float(match.group(1)) * 100) if match else 0

    def _set_volume(self, value: int) -> None:
        """Set PipeWire volume percent."""

        if which("wpctl"):
            run_command(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{value}%"], timeout=1, logger=LOGGER)

    def _get_brightness(self) -> int:
        """Return display brightness percent."""

        if not which("brightnessctl"):
            return 0
        text = run_command(["brightnessctl", "-m"], timeout=1, logger=LOGGER).stdout
        match = re.search(r",(\d+)%", text)
        return int(match.group(1)) if match else 0

    def _set_brightness(self, value: int) -> None:
        """Set brightness percent."""

        if which("brightnessctl"):
            run_command(["brightnessctl", "set", f"{value}%"], timeout=1, logger=LOGGER)

    def _refresh_network_page(self, _page: Gtk.Box) -> None:
        """Refresh network list by rebuilding the application."""

        if self.stack is not None:
            self.stack.remove(self.stack.get_child_by_name("network"))
            self.stack.add_titled(self._network_page(), "network", "Ağ")
            self.stack.set_visible_child_name("network")

    def _install_css(self) -> None:
        """Install control-center CSS."""

        load_hd_css(Gtk, Gdk, profile="control-center")
        css = """
        .root { background: rgba(18,20,28,0.96); color: white; border-radius: 28px; }
        .sidebar { padding: 18px; background: rgba(255,255,255,0.04); }
        .nav-button, .row-button, button { border-radius: 16px; padding: 10px 12px; background: rgba(255,255,255,0.08); color: white; }
        .nav-button:hover, .row-button:hover, button:hover { background: rgba(59,130,246,0.22); }
        .heading { font-size: 28px; font-weight: 900; margin-bottom: 10px; }
        .tile { min-height: 74px; border-radius: 22px; background: rgba(255,255,255,0.08); font-weight: 800; }
        .tile:checked { background: rgba(59,130,246,0.40); }
        .row { padding: 12px; border-radius: 18px; background: rgba(255,255,255,0.06); }
        .muted { color: rgba(255,255,255,0.62); }
        .monospace { font-family: monospace; color: rgba(255,255,255,0.78); }
        scale trough { min-height: 8px; border-radius: 999px; }
        scale highlight { background: #60a5fa; border-radius: 999px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX control center")
    parser.add_argument("--quick", action="store_true", help="open as a layer-shell quick settings popover")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    args = parse_args(argv or sys.argv[1:])
    if Gtk is None:
        LOGGER.error("GTK4/PyGObject is not available: %s", GTK_IMPORT_ERROR)
        return 1
    lock = SingletonLock("neox-control-center")
    if not lock.acquire():
        return 0
    try:
        return ControlCenter(quick=args.quick).run([])
    except Exception as exc:
        LOGGER.exception("Control center crashed: %s", exc)
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())

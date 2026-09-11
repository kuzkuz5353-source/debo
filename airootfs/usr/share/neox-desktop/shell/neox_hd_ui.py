#!/usr/bin/env python3
"""NEOX HD user-interface toolkit.

This module upgrades NEOX from a prototype-looking shell into a more coherent
high-density interface system.  It provides adaptive scale detection, shared
visual tokens, GTK CSS loading, responsive sizing helpers, system metrics and
small factories used by the advanced dashboard/program-center applications.

The module deliberately keeps GTK imports optional: command-line fallback modes
and unit checks can import it on machines without a Wayland/GTK stack.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import re
import time
from typing import Any, Callable, Mapping

from neox_common import run_command, setup_logging, which

LOGGER = setup_logging("neox-hd-ui")


@dataclasses.dataclass(frozen=True, slots=True)
class HDScale:
    """Resolved scale profile for high-density screens."""

    name: str
    factor: float
    icon: int
    touch: int
    radius: int
    blur: int
    shadow: int

    def px(self, value: int | float) -> int:
        """Scale a pixel value and return an integer suitable for GTK sizes."""

        return max(1, int(round(float(value) * self.factor)))


@dataclasses.dataclass(frozen=True, slots=True)
class HDPalette:
    """Color tokens used by NEOX HD CSS."""

    bg0: str = "#050816"
    bg1: str = "#0b1020"
    bg2: str = "#111827"
    glass: str = "rgba(17, 24, 39, 0.74)"
    glass_strong: str = "rgba(15, 23, 42, 0.90)"
    text: str = "#f8fafc"
    text_muted: str = "rgba(248, 250, 252, 0.68)"
    accent: str = "#60a5fa"
    accent_2: str = "#a78bfa"
    success: str = "#34d399"
    warning: str = "#fbbf24"
    danger: str = "#fb7185"
    border: str = "rgba(255, 255, 255, 0.12)"
    border_hot: str = "rgba(96, 165, 250, 0.54)"
    shadow: str = "rgba(0, 0, 0, 0.48)"


@dataclasses.dataclass(slots=True)
class SystemMetrics:
    """Small system metric snapshot used by HD widgets."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float
    battery_percent: int | None
    battery_charging: bool
    volume_percent: int | None
    muted: bool
    network: str
    updated_at: float = dataclasses.field(default_factory=time.time)


@dataclasses.dataclass(frozen=True, slots=True)
class HDAction:
    """Action descriptor rendered as a button/card by HD applications."""

    title: str
    subtitle: str
    icon: str
    callback: Callable[[], object]
    destructive: bool = False


def detect_scale(gdk_display: Any | None = None) -> HDScale:
    """Detect a comfortable NEOX HD scale profile.

    Detection order:
    1. ``NEOX_SCALE`` explicit value.
    2. ``GDK_SCALE`` integer value.
    3. Primary monitor width if a GDK display is passed.
    4. 1.0 laptop/desktop fallback.
    """

    explicit = os.environ.get("NEOX_SCALE") or os.environ.get("GDK_SCALE")
    if explicit and explicit.lower() not in {"auto", "detect", "default"}:
        try:
            factor = max(0.85, min(2.5, float(explicit)))
            return _profile_for_factor(factor)
        except ValueError:
            LOGGER.debug("Invalid scale value: %s", explicit)

    width = 0
    if gdk_display is not None:
        try:
            monitors = gdk_display.get_monitors()
            monitor = monitors.get_item(0) if monitors.get_n_items() else None
            if monitor is not None:
                width = int(monitor.get_geometry().width)
                scale_factor = int(getattr(monitor, "get_scale_factor", lambda: 1)())
                if scale_factor > 1:
                    return _profile_for_factor(float(scale_factor))
        except Exception as exc:  # pragma: no cover - depends on GDK backend.
            LOGGER.debug("Cannot inspect monitor scale: %s", exc)
    if width >= 3200:
        return _profile_for_factor(1.35)
    if width >= 2500:
        return _profile_for_factor(1.20)
    if width >= 1900:
        return _profile_for_factor(1.08)
    return _profile_for_factor(1.0)


def _profile_for_factor(factor: float) -> HDScale:
    """Create a named HD profile from a scale factor."""

    name = "4K" if factor >= 1.3 else "QHD" if factor >= 1.15 else "FHD"
    return HDScale(
        name=name,
        factor=factor,
        icon=max(72, int(round(86 * factor))),
        touch=max(46, int(round(52 * factor))),
        radius=max(22, int(round(26 * factor))),
        blur=max(14, int(round(18 * factor))),
        shadow=max(24, int(round(36 * factor))),
    )


def is_dark_color(hex_color: str) -> bool:
    """Return whether a ``#rrggbb`` color is perceived as dark."""

    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", hex_color.strip())
    if not match:
        return True
    value = match.group(1)
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return luminance < 0.52


def hd_css(scale: HDScale | None = None, palette: HDPalette | None = None, profile: str = "global") -> str:
    """Return shared GTK CSS for NEOX HD interfaces."""

    scale = scale or detect_scale()
    palette = palette or HDPalette()
    return f"""
    * {{
        -gtk-icon-style: symbolic;
        outline-color: transparent;
    }}
    window, .neox-hd-root, .neox-hd-card, .neox-hd-toolbar {{
        font-family: Inter, SF Pro Display, Cantarell, system-ui, sans-serif;
        color: {palette.text};
    }}
    .neox-hd-root {{
        background:
            radial-gradient(circle at 16% 12%, rgba(96,165,250,0.26), transparent 34%),
            radial-gradient(circle at 82% 72%, rgba(167,139,250,0.22), transparent 38%),
            linear-gradient(135deg, rgba(5,8,22,0.92), rgba(11,16,32,0.86));
    }}
    .neox-hd-glass, .neox-hd-card, .neox-hd-toolbar {{
        background: {palette.glass};
        border: 1px solid {palette.border};
        border-radius: {scale.radius}px;
        box-shadow: 0 {scale.px(18)}px {scale.shadow}px {palette.shadow};
    }}
    .neox-hd-card {{
        padding: {scale.px(16)}px;
        transition: all 220ms cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .neox-hd-card:hover {{
        background: rgba(30, 41, 59, 0.84);
        border-color: {palette.border_hot};
        box-shadow: 0 {scale.px(22)}px {scale.px(54)}px rgba(0,0,0,0.52);
    }}
    .neox-hd-title {{
        font-size: {scale.px(28)}px;
        font-weight: 900;
        letter-spacing: -0.03em;
    }}
    .neox-hd-subtitle {{
        font-size: {scale.px(13)}px;
        color: {palette.text_muted};
    }}
    .neox-hd-hero-title {{
        font-size: {scale.px(56)}px;
        font-weight: 950;
        letter-spacing: -0.055em;
        text-shadow: 0 4px 24px rgba(0,0,0,0.42);
    }}
    .neox-hd-hero-subtitle {{
        font-size: {scale.px(18)}px;
        color: {palette.text_muted};
    }}
    .neox-hd-chip {{
        min-height: {scale.touch}px;
        padding: 0 {scale.px(14)}px;
        border-radius: 999px;
        background: rgba(255,255,255,0.08);
        color: {palette.text};
        border: 1px solid rgba(255,255,255,0.08);
        font-weight: 800;
    }}
    .neox-hd-chip:hover {{
        background: rgba(96,165,250,0.22);
        border-color: rgba(96,165,250,0.42);
    }}
    .neox-hd-accent {{ color: {palette.accent}; }}
    .neox-hd-danger {{ color: {palette.danger}; }}
    .neox-hd-warning {{ color: {palette.warning}; }}
    .neox-hd-success {{ color: {palette.success}; }}
    button.neox-hd-button, .neox-hd-button {{
        min-height: {scale.touch}px;
        border-radius: {max(16, scale.radius - 8)}px;
        padding: {scale.px(9)}px {scale.px(14)}px;
        background: rgba(255,255,255,0.08);
        color: {palette.text};
        border: 1px solid rgba(255,255,255,0.08);
        font-weight: 800;
    }}
    button.neox-hd-button:hover, .neox-hd-button:hover {{
        background: rgba(96,165,250,0.22);
        border-color: rgba(96,165,250,0.44);
    }}
    button.neox-hd-button:active, .neox-hd-button:active {{
        transform: scale(0.97);
    }}
    entry, searchentry {{
        min-height: {scale.touch}px;
        border-radius: 999px;
        padding: 0 {scale.px(18)}px;
        background: rgba(255,255,255,0.10);
        color: {palette.text};
        border: 1px solid rgba(255,255,255,0.10);
        caret-color: {palette.accent};
    }}
    levelbar trough, scale trough {{
        min-height: {scale.px(10)}px;
        border-radius: 999px;
        background: rgba(255,255,255,0.10);
    }}
    levelbar block.filled, scale highlight {{
        border-radius: 999px;
        background: linear-gradient(90deg, {palette.accent}, {palette.accent_2});
    }}
    .neox-hd-icon-tile {{
        min-width: {scale.px(72)}px;
        min-height: {scale.px(72)}px;
        border-radius: {scale.radius}px;
        background: linear-gradient(135deg, rgba(96,165,250,0.22), rgba(167,139,250,0.16));
        border: 1px solid rgba(255,255,255,0.10);
    }}
    .neox-hd-separator {{
        min-height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.16), transparent);
    }}
    """


def load_hd_css(Gtk: Any, Gdk: Any, *, profile: str = "global", priority: int | None = None) -> HDScale:
    """Load the shared HD CSS into a GTK application and return the scale."""

    display = Gdk.Display.get_default() if Gdk is not None else None
    scale = detect_scale(display)
    provider = Gtk.CssProvider()
    provider.load_from_data(hd_css(scale=scale, profile=profile).encode("utf-8"))
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            priority if priority is not None else Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
    return scale


def make_header(Gtk: Any, title: str, subtitle: str = "") -> Any:
    """Create a reusable title/subtitle header box."""

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    title_label = Gtk.Label(label=title)
    title_label.set_xalign(0)
    title_label.add_css_class("neox-hd-title")
    box.append(title_label)
    if subtitle:
        subtitle_label = Gtk.Label(label=subtitle)
        subtitle_label.set_xalign(0)
        subtitle_label.add_css_class("neox-hd-subtitle")
        box.append(subtitle_label)
    return box


def make_metric_card(Gtk: Any, title: str, value: str, subtitle: str = "", accent_class: str = "") -> Any:
    """Create a small HD metric card."""

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    card.add_css_class("neox-hd-card")
    label = Gtk.Label(label=title)
    label.set_xalign(0)
    label.add_css_class("neox-hd-subtitle")
    number = Gtk.Label(label=value)
    number.set_xalign(0)
    number.add_css_class("neox-hd-title")
    if accent_class:
        number.add_css_class(accent_class)
    card.append(label)
    card.append(number)
    if subtitle:
        sub = Gtk.Label(label=subtitle)
        sub.set_xalign(0)
        sub.add_css_class("neox-hd-subtitle")
        card.append(sub)
    return card


def format_percent(value: float | int | None, fallback: str = "—") -> str:
    """Format a number as percentage for UI labels."""

    if value is None:
        return fallback
    return f"{int(round(float(value)))}%"


def read_system_metrics() -> SystemMetrics:
    """Read CPU, memory, disk, battery, volume and network metrics."""

    cpu = _read_cpu_percent()
    memory = _read_memory_percent()
    disk = _read_disk_percent()
    battery_percent, charging = _read_battery()
    volume, muted = _read_volume()
    network = _read_network()
    return SystemMetrics(cpu, memory, disk, battery_percent, charging, volume, muted, network)


def _read_cpu_percent() -> float:
    """Read CPU percent using psutil when installed or /proc/stat fallback."""

    try:
        import psutil  # type: ignore

        return float(psutil.cpu_percent(interval=None))
    except Exception:
        pass
    try:
        first = _proc_cpu_times()
        time.sleep(0.05)
        second = _proc_cpu_times()
        idle_delta = second[3] - first[3]
        total_delta = sum(second) - sum(first)
        return max(0.0, min(100.0, 100.0 * (1 - idle_delta / max(1, total_delta))))
    except Exception:
        return 0.0


def _proc_cpu_times() -> list[int]:
    """Return first /proc/stat CPU line as integers."""

    parts = pathlib.Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
    return [int(part) for part in parts]


def _read_memory_percent() -> float:
    """Read memory use percent."""

    try:
        import psutil  # type: ignore

        return float(psutil.virtual_memory().percent)
    except Exception:
        pass
    try:
        values: dict[str, int] = {}
        for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            values[key] = int(raw.split()[0])
        total = max(1, values.get("MemTotal", 1))
        available = values.get("MemAvailable", 0)
        return max(0.0, min(100.0, (1 - available / total) * 100))
    except Exception:
        return 0.0


def _read_disk_percent() -> float:
    """Read home filesystem usage percent."""

    try:
        import psutil  # type: ignore

        return float(psutil.disk_usage(str(pathlib.Path.home())).percent)
    except Exception:
        pass
    try:
        stat = os.statvfs(str(pathlib.Path.home()))
        total = stat.f_blocks * stat.f_frsize
        free = stat.f_bavail * stat.f_frsize
        return max(0.0, min(100.0, (1 - free / max(1, total)) * 100))
    except Exception:
        return 0.0


def _read_battery() -> tuple[int | None, bool]:
    """Read battery percentage and charging state from sysfs."""

    for battery in pathlib.Path("/sys/class/power_supply").glob("BAT*"):
        try:
            percent = int((battery / "capacity").read_text(encoding="utf-8").strip())
            status = (battery / "status").read_text(encoding="utf-8").strip().lower()
            return percent, status in {"charging", "full"}
        except Exception:
            continue
    return None, False


def _read_volume() -> tuple[int | None, bool]:
    """Read PipeWire default sink volume."""

    if not which("wpctl"):
        return None, False
    result = run_command(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], timeout=1, logger=LOGGER)
    match = re.search(r"([0-9.]+)", result.stdout)
    volume = int(float(match.group(1)) * 100) if match else None
    return volume, "MUTED" in result.stdout


def _read_network() -> str:
    """Return a compact NetworkManager state label."""

    if not which("nmcli"):
        return "Ağ bilinmiyor"
    result = run_command(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"], timeout=1, logger=LOGGER)
    for line in result.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == "wifi" and parts[1] == "connected":
            return f"Wi‑Fi · {parts[2] if len(parts) > 2 and parts[2] else 'bağlı'}"
        if len(parts) >= 2 and parts[0] == "ethernet" and parts[1] == "connected":
            return "Ethernet · bağlı"
    return "Çevrimdışı"


__all__ = [
    "HDAction",
    "HDPalette",
    "HDScale",
    "SystemMetrics",
    "detect_scale",
    "format_percent",
    "hd_css",
    "is_dark_color",
    "load_hd_css",
    "make_header",
    "make_metric_card",
    "read_system_metrics",
]

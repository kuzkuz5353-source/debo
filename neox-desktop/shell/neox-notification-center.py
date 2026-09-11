#!/usr/bin/env python3
"""NEOX notification daemon and notification-center UI.

The daemon implements ``org.freedesktop.Notifications`` via D-Bus when the
``dbus-next`` package is available.  Notifications are persisted to a small JSON
history, previewed through the NEOX event bus, and shown in a grouped GTK center.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import JsonLineClient, NEOX_CONFIG_DIR, SingletonLock, read_json, setup_logging, write_json

LOGGER = setup_logging("neox-notification-center")
HISTORY_PATH = NEOX_CONFIG_DIR / "notifications.json"

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, dbus_property, method, signal
    from dbus_next import Variant
except ImportError as exc:  # pragma: no cover - optional runtime dependency.
    MessageBus = None  # type: ignore[assignment]
    ServiceInterface = object  # type: ignore[assignment]
    Variant = Any  # type: ignore[assignment]
    DBUS_IMPORT_ERROR = exc
else:
    DBUS_IMPORT_ERROR = None

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
class Notification:
    """Stored notification item."""

    id: int
    app_name: str
    summary: str
    body: str
    icon: str = ""
    actions: list[str] = field(default_factory=list)
    urgency: int = 1
    created_at: float = field(default_factory=time.time)


class NotificationStore:
    """Persistent notification history and DND state."""

    def __init__(self, path: pathlib.Path = HISTORY_PATH) -> None:
        self.path = path
        payload = read_json(path, {"notifications": [], "dnd": False, "next_id": 1})
        self.notifications: list[Notification] = [Notification(**item) for item in payload.get("notifications", [])]
        self.dnd = bool(payload.get("dnd", False))
        self.next_id = int(payload.get("next_id", 1))

    def add(self, app_name: str, summary: str, body: str, icon: str, actions: list[str], urgency: int) -> Notification:
        """Add and persist one notification."""

        item = Notification(self.next_id, app_name, summary, body, icon, actions, urgency)
        self.next_id += 1
        self.notifications.insert(0, item)
        self.notifications = self.notifications[:200]
        self.save()
        return item

    def close(self, notification_id: int) -> None:
        """Remove a notification by id."""

        self.notifications = [item for item in self.notifications if item.id != notification_id]
        self.save()

    def clear(self) -> None:
        """Clear history."""

        self.notifications = []
        self.save()

    def save(self) -> None:
        """Persist state."""

        write_json(
            self.path,
            {
                "dnd": self.dnd,
                "next_id": self.next_id,
                "notifications": [asdict(item) for item in self.notifications],
            },
        )


if MessageBus is not None:

    class NotificationsInterface(ServiceInterface):
        """D-Bus implementation of org.freedesktop.Notifications."""

        def __init__(self, store: NotificationStore) -> None:
            super().__init__("org.freedesktop.Notifications")
            self.store = store
            self.bus_client = JsonLineClient(logger=LOGGER)

        @method()
        def GetCapabilities(self) -> "as":
            """Return supported desktop-notification capabilities."""

            return ["actions", "body", "body-markup", "persistence", "sound", "action-icons"]

        @method()
        def GetServerInformation(self) -> "ssss":
            """Return notification server identity."""

            return ("NEOX Notification Center", "NEOX", "0.1.0", "1.2")

        @method()
        def Notify(
            self,
            app_name: "s",
            replaces_id: "u",
            app_icon: "s",
            summary: "s",
            body: "s",
            actions: "as",
            hints: "a{sv}",
            expire_timeout: "i",
        ) -> "u":
            """Receive a notification from a client application."""

            urgency = 1
            raw_urgency = hints.get("urgency") if isinstance(hints, dict) else None
            if raw_urgency is not None:
                try:
                    urgency = int(raw_urgency.value if hasattr(raw_urgency, "value") else raw_urgency)
                except (TypeError, ValueError):
                    urgency = 1
            if replaces_id:
                self.store.close(int(replaces_id))
            item = self.store.add(app_name, summary, body, app_icon, list(actions), urgency)
            LOGGER.info("Notification %s from %s: %s", item.id, app_name, summary)
            if not self.store.dnd or urgency >= 2:
                self.bus_client.send(
                    "notification",
                    {"id": item.id, "title": summary, "body": body, "app": app_name, "critical": urgency >= 2},
                )
            return item.id

        @method()
        def CloseNotification(self, notification_id: "u") -> "":
            """Close a notification by id."""

            self.store.close(int(notification_id))
            self.NotificationClosed(int(notification_id), 2)

        @signal()
        def NotificationClosed(self, notification_id: "u", reason: "u") -> "uu":
            """Signal emitted when a notification is closed."""

            return (notification_id, reason)

        @signal()
        def ActionInvoked(self, notification_id: "u", action_key: "s") -> "us":
            """Signal emitted when a notification action is invoked."""

            return (notification_id, action_key)


class NotificationCenter(Gtk.Application if Gtk else object):  # type: ignore[misc,valid-type]
    """GTK notification history center."""

    def __init__(self) -> None:
        if Gtk is None:
            raise RuntimeError(f"GTK4 is required: {GTK_IMPORT_ERROR}")
        super().__init__(application_id="org.neox.NotificationCenter")
        self.store = NotificationStore()
        self.window: Gtk.ApplicationWindow | None = None
        self.list_box: Gtk.Box | None = None

    def do_activate(self) -> None:
        """Build and present the center."""

        self._install_css()
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("NEOX Notifications")
        self.window.set_decorated(False)
        self.window.set_default_size(430, 720)
        if LayerShell is not None:
            LayerShell.init_for_window(self.window)
            LayerShell.set_namespace(self.window, "neox-notification-center")
            LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
            LayerShell.set_anchor(self.window, LayerShell.Edge.TOP, True)
            LayerShell.set_anchor(self.window, LayerShell.Edge.RIGHT, True)
            LayerShell.set_anchor(self.window, LayerShell.Edge.BOTTOM, True)
            LayerShell.set_margin(self.window, LayerShell.Edge.RIGHT, 12)
            LayerShell.set_margin(self.window, LayerShell.Edge.TOP, 12)
            LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.ON_DEMAND)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)
        root.add_css_class("neox-notifications-root")
        self.window.set_child(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title = Gtk.Label(label="Bildirimler")
        title.add_css_class("title")
        title.set_xalign(0)
        title.set_hexpand(True)
        header.append(title)
        dnd = Gtk.ToggleButton(label="DND")
        dnd.set_active(self.store.dnd)
        dnd.connect("toggled", self._toggle_dnd)
        header.append(dnd)
        clear = Gtk.Button(label="Temizle")
        clear.connect("clicked", lambda _button: self._clear())
        header.append(clear)
        root.append(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        scrolled.set_child(self.list_box)
        root.append(scrolled)
        self._populate()
        self.window.present()

    def _populate(self) -> None:
        """Populate grouped notification rows."""

        if self.list_box is None:
            return
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        groups: dict[str, list[Notification]] = {}
        for item in self.store.notifications:
            groups.setdefault(item.app_name or "Uygulama", []).append(item)
        if not groups:
            empty = Gtk.Label(label="Henüz bildirim yok")
            empty.add_css_class("empty")
            self.list_box.append(empty)
            return
        for app_name, items in groups.items():
            heading = Gtk.Label(label=app_name)
            heading.set_xalign(0)
            heading.add_css_class("group")
            self.list_box.append(heading)
            for item in items:
                self.list_box.append(self._row(item))

    def _row(self, item: Notification) -> Gtk.Widget:
        """Create one notification history row."""

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.add_css_class("notification-row")
        row.set_margin_bottom(4)
        icon = Gtk.Image.new_from_file(item.icon) if pathlib.Path(item.icon).exists() else Gtk.Image.new_from_icon_name(item.icon or "dialog-information-symbolic")
        icon.set_pixel_size(36)
        row.append(icon)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        texts.set_hexpand(True)
        summary = Gtk.Label(label=item.summary)
        summary.set_xalign(0)
        summary.set_ellipsize(Pango.EllipsizeMode.END)
        summary.add_css_class("summary")
        body = Gtk.Label(label=item.body)
        body.set_xalign(0)
        body.set_wrap(True)
        body.add_css_class("body")
        stamp = Gtk.Label(label=time.strftime("%H:%M", time.localtime(item.created_at)))
        stamp.set_xalign(0)
        stamp.add_css_class("time")
        texts.append(summary)
        texts.append(body)
        texts.append(stamp)
        row.append(texts)
        close = Gtk.Button(label="×")
        close.connect("clicked", lambda _button: self._close(item.id))
        row.append(close)
        if item.urgency >= 2:
            row.add_css_class("critical")
        return row

    def _toggle_dnd(self, button: Gtk.ToggleButton) -> None:
        """Enable/disable do-not-disturb mode."""

        self.store.dnd = button.get_active()
        self.store.save()

    def _clear(self) -> None:
        """Clear all notifications."""

        self.store.clear()
        self._populate()

    def _close(self, notification_id: int) -> None:
        """Close one notification row."""

        self.store.close(notification_id)
        self._populate()

    def _install_css(self) -> None:
        """Install notification-center CSS."""

        css = """
        .neox-notifications-root { background: rgba(18,20,28,0.94); color: white; border-radius: 28px; border: 1px solid rgba(255,255,255,0.08); }
        .title { font-size: 24px; font-weight: 900; }
        .group { color: rgba(255,255,255,0.72); font-weight: 800; margin-top: 10px; }
        .notification-row { padding: 12px; border-radius: 20px; background: rgba(255,255,255,0.07); }
        .notification-row.critical { background: rgba(185,28,28,0.34); }
        .summary { font-weight: 800; color: white; }
        .body { color: rgba(255,255,255,0.72); }
        .time, .empty { color: rgba(255,255,255,0.48); font-size: 12px; }
        button { border-radius: 14px; background: rgba(255,255,255,0.10); color: white; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


async def run_daemon() -> int:
    """Run the freedesktop notification D-Bus service."""

    if MessageBus is None:
        LOGGER.error("dbus-next is required for notification daemon: %s", DBUS_IMPORT_ERROR)
        return 1
    store = NotificationStore()
    bus = await MessageBus().connect()
    interface = NotificationsInterface(store)  # type: ignore[name-defined]
    bus.export("/org/freedesktop/Notifications", interface)
    await bus.request_name("org.freedesktop.Notifications")
    LOGGER.info("NEOX notification daemon is running")
    await asyncio.Future()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX notification center")
    parser.add_argument("--daemon", action="store_true", help="run D-Bus notification service")
    parser.add_argument("--clear", action="store_true", help="clear notification history and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for daemon or UI mode."""

    args = parse_args(argv or sys.argv[1:])
    if args.clear:
        NotificationStore().clear()
        return 0
    if args.daemon:
        lock = SingletonLock("neox-notifications-daemon")
        if not lock.acquire():
            return 0
        try:
            return asyncio.run(run_daemon())
        except KeyboardInterrupt:
            return 0
        finally:
            lock.release()
    if Gtk is None:
        LOGGER.error("GTK4/PyGObject is not available: %s", GTK_IMPORT_ERROR)
        return 1
    return NotificationCenter().run([])


if __name__ == "__main__":
    raise SystemExit(main())

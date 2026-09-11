#!/usr/bin/env python3
"""D-Bus bridge for NEOX shell actions."""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "shell"))

from neox_common import DesktopAppScanner, JsonLineClient, setup_logging

LOGGER = setup_logging("neox-dbus-service")

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, signal
except ImportError as exc:
    MessageBus = None  # type: ignore[assignment]
    ServiceInterface = object  # type: ignore[assignment]
    DBUS_IMPORT_ERROR = exc
else:
    DBUS_IMPORT_ERROR = None


if MessageBus is not None:

    class ShellInterface(ServiceInterface):
        """D-Bus API exposed as org.neox.Shell."""

        def __init__(self) -> None:
            super().__init__("org.neox.Shell")
            self.client = JsonLineClient(logger=LOGGER)

        @method()
        def OpenSearch(self) -> "":
            """Open the application search overlay."""

            self.client.send("open-search")

        @method()
        def OpenControlCenter(self) -> "":
            """Open the control center."""

            self.client.send("open-control-center")

        @method()
        def OpenNotificationCenter(self) -> "":
            """Open notification center."""

            self.client.send("open-notifications")

        @method()
        def OpenTaskSwitcher(self) -> "":
            """Open the task switcher."""

            self.client.send("open-task-switcher")

        @method()
        def ReloadApplications(self) -> "u":
            """Refresh desktop-entry cache and return app count."""

            apps = DesktopAppScanner(logger=LOGGER).scan(force=True)
            self.ApplicationsChanged(len(apps))
            return len(apps)

        @method()
        def NotifyPreview(self, title: "s", body: "s") -> "":
            """Show a notification preview through the shell event bus."""

            self.client.send("notification", {"title": title, "body": body})

        @signal()
        def ApplicationsChanged(self, count: "u") -> "u":
            """Signal emitted when app cache is refreshed."""

            return count


async def run_service() -> int:
    """Run D-Bus service until interrupted."""

    if MessageBus is None:
        LOGGER.error("dbus-next is required: %s", DBUS_IMPORT_ERROR)
        return 1
    bus = await MessageBus().connect()
    bus.export("/org/neox/Shell", ShellInterface())  # type: ignore[name-defined]
    await bus.request_name("org.neox.Shell")
    LOGGER.info("org.neox.Shell D-Bus service is running")
    await asyncio.Future()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="NEOX D-Bus service")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point."""

    parse_args(argv or sys.argv[1:])
    try:
        return asyncio.run(run_service())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

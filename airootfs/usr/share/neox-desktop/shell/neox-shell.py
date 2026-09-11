#!/usr/bin/env python3
"""NEOX shell daemon.

The daemon owns the lightweight JSON-lines event bus, supervises optional shell
components, mirrors Hyprland events, performs background update checks and runs
user autostart commands.  It intentionally avoids drawing UI; separate GTK
layer-shell programs provide the panel, grid, task switcher and OSD.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import queue
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# Allow running from the source tree without installation.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from neox_common import (  # noqa: E402
    ConfigManager,
    DesktopAppScanner,
    HyprlandIPC,
    JsonLineServer,
    NEOX_CONFIG_DIR,
    NEOX_RUNTIME_DIR,
    SingletonLock,
    ensure_runtime_dirs,
    install_signal_handlers,
    run_command,
    run_detached,
    setup_logging,
    which,
)

LOGGER = setup_logging("neox-shell")


@dataclass(slots=True)
class ManagedProcess:
    """A supervised subprocess definition."""

    name: str
    command: list[str]
    restart: bool = True
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    last_start: float = 0.0
    crash_count: int = 0

    def alive(self) -> bool:
        """Return ``True`` when the subprocess is running."""

        return self.process is not None and self.process.poll() is None


class ShellDaemon:
    """Singleton manager for the NEOX user session."""

    def __init__(self, manage_components: bool = False) -> None:
        ensure_runtime_dirs()
        self.config = ConfigManager()
        self.hyprland = HyprlandIPC(LOGGER)
        self.bus = JsonLineServer(logger=LOGGER)
        self.scanner = DesktopAppScanner(logger=LOGGER)
        self.stop_event = threading.Event()
        self.manage_components = manage_components
        self.processes: dict[str, ManagedProcess] = {}
        self.hypr_event_queue: "queue.Queue[str]" = queue.Queue()
        self._register_bus_handlers()

    def _register_bus_handlers(self) -> None:
        """Install event-bus handlers used by other NEOX components."""

        self.bus.subscribe("open-search", lambda _payload: self.exec_helper("neox-app-search"))
        self.bus.subscribe("open-control-center", lambda _payload: self.exec_helper("neox-control-center"))
        self.bus.subscribe("open-notifications", lambda _payload: self.exec_helper("neox-notification-center"))
        self.bus.subscribe("open-task-switcher", lambda _payload: self.exec_helper("neox-task-switcher"))
        self.bus.subscribe("reload-apps", lambda _payload: self.scanner.scan(force=True))
        self.bus.subscribe("wallpaper-changed", self._handle_wallpaper_changed)
        self.bus.subscribe("notification", self._handle_notification)
        self.bus.subscribe("shutdown", lambda _payload: self.stop())

    def start(self) -> None:
        """Start the daemon and block until shutdown."""

        LOGGER.info("Starting NEOX shell daemon")
        install_signal_handlers(self.stop)
        self.bus.start()
        self.scanner.scan(force=False)
        self.scanner.watch(lambda apps: LOGGER.info("Application index updated: %d apps", len(apps)))
        self.run_user_autostart()
        if self.manage_components:
            self._create_managed_processes()
            self._start_managed_processes()
        threading.Thread(target=self._hyprland_event_loop, name="neox-hypr-events", daemon=True).start()
        threading.Thread(target=self._update_checker_loop, name="neox-update-checker", daemon=True).start()
        self._main_loop()

    def stop(self) -> None:
        """Request a graceful daemon shutdown."""

        if self.stop_event.is_set():
            return
        LOGGER.info("Stopping NEOX shell daemon")
        self.stop_event.set()
        self.scanner.stop_watching()
        self.bus.stop()
        for managed in self.processes.values():
            if managed.alive() and managed.process is not None:
                with contextlib.suppress(Exception):
                    managed.process.terminate()

    def exec_helper(self, helper: str, *args: str) -> bool:
        """Execute a NEOX helper from PATH with robust logging."""

        command = [helper, *args]
        return run_detached(command, logger=LOGGER)

    def _create_managed_processes(self) -> None:
        """Define optional components the shell can supervise."""

        names = [
            "neox-panel",
            "neox-desktop-grid",
            "neox-notification-center --daemon",
            "neox-volume-brightness --daemon",
            "neox-wallpaper-manager --daemon",
        ]
        for item in names:
            argv = shlex.split(item)
            self.processes[argv[0]] = ManagedProcess(argv[0], argv)

    def _start_managed_processes(self) -> None:
        """Start every managed process that is not already running."""

        for managed in self.processes.values():
            self._start_process(managed)

    def _start_process(self, managed: ManagedProcess) -> None:
        """Start one managed subprocess."""

        if managed.alive():
            return
        try:
            managed.process = subprocess.Popen(
                managed.command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            managed.last_start = time.time()
            LOGGER.info("Started component %s pid=%s", managed.name, managed.process.pid)
        except FileNotFoundError:
            LOGGER.warning("Managed component missing: %s", managed.command[0])
        except Exception as exc:
            LOGGER.exception("Cannot start %s: %s", managed.name, exc)

    def _main_loop(self) -> None:
        """Supervise processes and dispatch queued Hyprland events."""

        while not self.stop_event.wait(1.0):
            self._supervise_processes()
            self._drain_hyprland_events()

    def _supervise_processes(self) -> None:
        """Restart crashed managed components with basic backoff."""

        if not self.manage_components:
            return
        for managed in self.processes.values():
            if managed.alive() or not managed.restart:
                continue
            if managed.process is not None:
                code = managed.process.poll()
                managed.crash_count += 1
                LOGGER.warning("Component %s exited with %s", managed.name, code)
            # Back off after repeated crashes to avoid CPU loops.
            if managed.crash_count > 5 and time.time() - managed.last_start < 60:
                LOGGER.error("Component %s crashed too often; not restarting yet", managed.name)
                continue
            self._start_process(managed)

    def run_user_autostart(self) -> None:
        """Run commands from ``~/.config/neox/autostart.conf``."""

        autostart = NEOX_CONFIG_DIR / "autostart.conf"
        if not autostart.exists():
            return
        try:
            lines = autostart.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            LOGGER.warning("Cannot read autostart file: %s", exc)
            return
        for raw_line in lines:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            run_detached(["bash", "-lc", line], logger=LOGGER)

    def _hyprland_event_socket(self) -> pathlib.Path | None:
        """Return the Hyprland event socket path for the active instance."""

        signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if not signature or not runtime:
            return None
        path = pathlib.Path(runtime) / "hypr" / signature / ".socket2.sock"
        return path if path.exists() else None

    def _hyprland_event_loop(self) -> None:
        """Mirror Hyprland IPC events into the NEOX internal event queue."""

        while not self.stop_event.is_set():
            path = self._hyprland_event_socket()
            if path is None:
                self.stop_event.wait(2.0)
                continue
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.connect(str(path))
                    LOGGER.info("Connected to Hyprland event socket: %s", path)
                    fileobj = sock.makefile("r", encoding="utf-8", errors="replace")
                    for line in fileobj:
                        if self.stop_event.is_set():
                            break
                        self.hypr_event_queue.put(line.strip())
            except OSError as exc:
                LOGGER.debug("Hyprland event socket disconnected: %s", exc)
                self.stop_event.wait(1.0)

    def _drain_hyprland_events(self) -> None:
        """Process pending Hyprland events."""

        while True:
            try:
                event = self.hypr_event_queue.get_nowait()
            except queue.Empty:
                return
            LOGGER.debug("Hyprland event: %s", event)
            if event.startswith("openwindow") or event.startswith("closewindow"):
                # Task switcher previews use hyprctl directly; this event nudges
                # panels that subscribe through the bus in future revisions.
                pass

    def _handle_wallpaper_changed(self, payload: dict[str, Any]) -> None:
        """React to wallpaper palette changes."""

        LOGGER.info("Wallpaper changed: %s", payload.get("path", "unknown"))
        accent = payload.get("accent")
        if accent:
            LOGGER.info("New wallpaper accent color: %s", accent)

    def _handle_notification(self, payload: dict[str, Any]) -> None:
        """Forward notification preview events to libnotify when available."""

        title = str(payload.get("title", "NEOX"))
        body = str(payload.get("body", ""))
        if which("notify-send"):
            run_command(["notify-send", title, body], timeout=2, logger=LOGGER)
        else:
            LOGGER.info("Notification: %s - %s", title, body)

    def _update_checker_loop(self) -> None:
        """Check package updates in the background every six hours."""

        while not self.stop_event.wait(30.0):
            count = self._check_updates_once()
            if count > 0:
                self.bus.handlers.get("notification", [])
                self._handle_notification({"title": "NEOX", "body": f"{count} sistem güncellemesi mevcut"})
            # Sleep in small chunks so stop remains responsive.
            for _ in range(6 * 60 * 60):
                if self.stop_event.wait(1.0):
                    return

    def _check_updates_once(self) -> int:
        """Return an approximate pending update count for common distros."""

        try:
            if which("checkupdates"):
                result = run_command(["checkupdates"], timeout=20, logger=LOGGER)
                return len([line for line in result.stdout.splitlines() if line.strip()])
            if which("apt"):
                result = run_command(["bash", "-lc", "apt list --upgradable 2>/dev/null | tail -n +2"], timeout=20, logger=LOGGER)
                return len([line for line in result.stdout.splitlines() if line.strip()])
            if which("dnf"):
                result = run_command(["bash", "-lc", "dnf -q check-update | awk 'NF>=3 {print}'"], timeout=30, logger=LOGGER)
                return len([line for line in result.stdout.splitlines() if line.strip()])
        except Exception as exc:
            LOGGER.debug("Update check failed: %s", exc)
        return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="NEOX shell daemon")
    parser.add_argument("--manage-components", action="store_true", help="supervise panel/grid/helpers from the shell")
    parser.add_argument("--reload-apps", action="store_true", help="refresh the application cache and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""

    args = parse_args(argv or sys.argv[1:])
    if args.reload_apps:
        DesktopAppScanner(logger=LOGGER).scan(force=True)
        return 0
    lock = SingletonLock("neox-shell")
    if not lock.acquire():
        LOGGER.warning("neox-shell is already running")
        return 0
    daemon = ShellDaemon(manage_components=args.manage_components)
    try:
        daemon.start()
    except Exception as exc:
        LOGGER.exception("Fatal shell error: %s", exc)
        return 1
    finally:
        daemon.stop()
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

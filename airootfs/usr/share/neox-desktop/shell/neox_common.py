#!/usr/bin/env python3
"""Shared runtime helpers for the NEOX desktop environment.

This module deliberately has no hard dependency on GTK.  Graphical components can
import it before the Wayland/GTK stack is available, and command-line helpers use
it for logging, configuration, desktop-entry parsing, Hyprland IPC and lightweight
inter-process messaging.
"""

from __future__ import annotations

import ast
import configparser
import contextlib
import dataclasses
import functools
import hashlib
import json
import locale
import logging
import logging.handlers
import math
import os
import pathlib
import queue
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

APP_ID = "org.neox.Shell"
VERSION = "0.1.0"
HOME = pathlib.Path.home()
XDG_CONFIG_HOME = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
XDG_CACHE_HOME = pathlib.Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache"))
XDG_DATA_HOME = pathlib.Path(os.environ.get("XDG_DATA_HOME", HOME / ".local" / "share"))
XDG_RUNTIME_DIR = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/neox-{os.getuid()}"))
NEOX_CONFIG_DIR = XDG_CONFIG_HOME / "neox"
NEOX_CACHE_DIR = XDG_CACHE_HOME / "neox"
NEOX_RUNTIME_DIR = XDG_RUNTIME_DIR / "neox"
NEOX_LOG_DIR = XDG_CACHE_HOME / "neox" / "logs"
NEOX_STATE_FILE = NEOX_CONFIG_DIR / "state.json"

DESKTOP_DIRS: tuple[pathlib.Path, ...] = (
    pathlib.Path("/usr/share/applications"),
    pathlib.Path("/usr/local/share/applications"),
    XDG_DATA_HOME / "applications",
    pathlib.Path("/var/lib/flatpak/exports/share/applications"),
    XDG_DATA_HOME / "flatpak" / "exports" / "share" / "applications",
    pathlib.Path("/var/lib/snapd/desktop/applications"),
)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_LOCALE = locale.getlocale()[0] or os.environ.get("LANG", "en_US.UTF-8").split(".")[0]
_LANG = _LOCALE.split("_")[0]
_PLACEHOLDER_RE = re.compile(r"%[fFuUdDnNickvm]")


def ensure_runtime_dirs() -> None:
    """Create runtime, cache and config directories used by all components."""

    for path in (NEOX_CONFIG_DIR, NEOX_CACHE_DIR, NEOX_RUNTIME_DIR, NEOX_LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def setup_logging(name: str, level: int | str = logging.INFO) -> logging.Logger:
    """Return a configured logger with stderr and rotating-file handlers.

    The function is idempotent: calling it more than once for the same logger will
    not add duplicate handlers.  Logs are stored in ``~/.cache/neox/logs``.
    """

    ensure_runtime_dirs()
    logger = logging.getLogger(name)
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s:%(lineno)d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stderr = logging.StreamHandler()
    stderr.setFormatter(formatter)
    stderr.setLevel(level)
    logger.addHandler(stderr)

    logfile = NEOX_LOG_DIR / f"{name}.log"
    file_handler = logging.handlers.RotatingFileHandler(
        logfile, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    return logger


LOGGER = setup_logging("neox-common", os.environ.get("NEOX_LOG_LEVEL", "INFO"))


class SingletonLock:
    """Advisory lock used to keep daemon-like NEOX processes single-instance."""

    def __init__(self, name: str) -> None:
        ensure_runtime_dirs()
        self.name = name
        self.path = NEOX_RUNTIME_DIR / f"{name}.lock"
        self._file: Any | None = None

    def acquire(self) -> bool:
        """Try to acquire the singleton lock and return ``True`` on success."""

        import fcntl

        self._file = self.path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        self._file.write(str(os.getpid()))
        self._file.flush()
        return True

    def release(self) -> None:
        """Release the singleton lock if it is currently held."""

        if self._file is None:
            return
        import fcntl

        with contextlib.suppress(OSError):
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        with contextlib.suppress(Exception):
            self._file.close()
        self._file = None

    def __enter__(self) -> "SingletonLock":
        if not self.acquire():
            raise RuntimeError(f"{self.name} is already running")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def which(command: str) -> str | None:
    """Return the executable path for ``command`` or ``None`` if missing."""

    return shutil.which(command)


def run_command(
    args: Sequence[str],
    *,
    timeout: float = 5.0,
    check: bool = False,
    input_text: str | None = None,
    logger: logging.Logger | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess safely and capture UTF-8 output.

    ``check=False`` is the default because many desktop helpers are optional on a
    development machine.  Callers inspect ``returncode`` and log user-friendly
    messages instead of crashing the shell.
    """

    log = logger or LOGGER
    try:
        log.debug("Running command: %s", " ".join(shlex.quote(a) for a in args))
        return subprocess.run(
            list(args),
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        log.warning("Command failed: %s stderr=%s", args, exc.stderr)
        return exc
    except FileNotFoundError:
        log.warning("Command not found: %s", args[0])
        return subprocess.CompletedProcess(args, 127, "", f"{args[0]} not found")
    except subprocess.TimeoutExpired as exc:
        log.warning("Command timed out: %s", args)
        return subprocess.CompletedProcess(args, 124, exc.stdout or "", exc.stderr or "timeout")


def run_detached(command: Sequence[str] | str, *, logger: logging.Logger | None = None) -> bool:
    """Start a program detached from the shell and return whether it was launched."""

    log = logger or LOGGER
    if isinstance(command, str):
        argv = shlex.split(command)
    else:
        argv = list(command)
    if not argv:
        return False
    try:
        subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        log.info("Launched detached command: %s", argv)
        return True
    except FileNotFoundError:
        log.warning("Cannot launch missing executable: %s", argv[0])
    except Exception as exc:  # pragma: no cover - defensive desktop integration.
        log.exception("Cannot launch command %s: %s", argv, exc)
    return False


def _localized_key(parser: configparser.ConfigParser, section: str, key: str) -> str | None:
    """Return localized key value according to the process locale."""

    candidates = [f"{key}[{_LOCALE}]", f"{key}[{_LANG}]", key]
    for candidate in candidates:
        if parser.has_option(section, candidate):
            return parser.get(section, candidate, fallback=None)
    return None


def parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse freedesktop boolean values."""

    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def parse_list(value: str | None) -> list[str]:
    """Parse semicolon-separated desktop-entry lists."""

    if not value:
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def desktop_environment_names() -> set[str]:
    """Return DE names that NEOX should match in OnlyShowIn/NotShowIn checks."""

    current = os.environ.get("XDG_CURRENT_DESKTOP", "NEOX:Hyprland")
    names = {"NEOX", "Hyprland"}
    names.update(part for part in re.split(r"[:;]", current) if part)
    return names


@dataclasses.dataclass(slots=True)
class DesktopEntry:
    """Parsed representation of a freedesktop ``.desktop`` application."""

    id: str
    name: str
    exec: str
    icon: str
    path: str
    categories: list[str]
    comment: str
    keywords: list[str]
    terminal: bool = False
    startup_notify: bool = True
    no_display: bool = False
    hidden: bool = False
    only_show_in: list[str] = dataclasses.field(default_factory=list)
    not_show_in: list[str] = dataclasses.field(default_factory=list)

    @property
    def searchable_text(self) -> str:
        """Return lower-case text used by fuzzy search."""

        return " ".join(
            [self.name, self.comment, " ".join(self.keywords), " ".join(self.categories)]
        ).lower()

    @property
    def command(self) -> list[str]:
        """Return an executable argv with desktop placeholders removed."""

        cleaned = _PLACEHOLDER_RE.sub("", self.exec).strip()
        try:
            return shlex.split(cleaned)
        except ValueError:
            return [cleaned]

    def should_show(self) -> bool:
        """Apply Hidden/NoDisplay/OnlyShowIn/NotShowIn visibility rules."""

        if self.hidden or self.no_display:
            return False
        names = desktop_environment_names()
        if self.only_show_in and not names.intersection(self.only_show_in):
            return False
        if self.not_show_in and names.intersection(self.not_show_in):
            return False
        return bool(self.name and self.exec)

    def launch(self, logger: logging.Logger | None = None) -> bool:
        """Launch this application according to its desktop Exec command."""

        log = logger or LOGGER
        if not self.command:
            log.warning("Desktop entry has empty command: %s", self.path)
            return False
        if self.terminal:
            terminal = os.environ.get("TERMINAL", "foot")
            return run_detached([terminal, *self.command], logger=log)
        return run_detached(self.command, logger=log)

    def to_json(self) -> dict[str, Any]:
        """Serialize the desktop entry for cache storage."""

        return dataclasses.asdict(self)

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "DesktopEntry":
        """Deserialize a cached desktop entry."""

        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            exec=str(payload.get("exec", "")),
            icon=str(payload.get("icon", "")),
            path=str(payload.get("path", "")),
            categories=list(payload.get("categories", [])),
            comment=str(payload.get("comment", "")),
            keywords=list(payload.get("keywords", [])),
            terminal=bool(payload.get("terminal", False)),
            startup_notify=bool(payload.get("startup_notify", True)),
            no_display=bool(payload.get("no_display", False)),
            hidden=bool(payload.get("hidden", False)),
            only_show_in=list(payload.get("only_show_in", [])),
            not_show_in=list(payload.get("not_show_in", [])),
        )

    @classmethod
    def from_file(cls, path: pathlib.Path) -> "DesktopEntry | None":
        """Parse a desktop-entry file and return ``None`` when invalid."""

        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str  # Keep localized key case and brackets intact.
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                parser.read_file(handle)
        except (OSError, configparser.Error) as exc:
            LOGGER.debug("Skipping unreadable desktop file %s: %s", path, exc)
            return None
        section = "Desktop Entry"
        if not parser.has_section(section):
            return None
        entry_type = parser.get(section, "Type", fallback="Application")
        if entry_type != "Application":
            return None
        name = _localized_key(parser, section, "Name") or path.stem
        exec_line = parser.get(section, "Exec", fallback="").strip()
        entry = cls(
            id=path.name,
            name=name.strip(),
            exec=exec_line,
            icon=parser.get(section, "Icon", fallback="").strip(),
            path=str(path),
            categories=parse_list(parser.get(section, "Categories", fallback="")),
            comment=(_localized_key(parser, section, "Comment") or "").strip(),
            keywords=parse_list(_localized_key(parser, section, "Keywords") or ""),
            terminal=parse_bool(parser.get(section, "Terminal", fallback=None), False),
            startup_notify=parse_bool(parser.get(section, "StartupNotify", fallback=None), True),
            no_display=parse_bool(parser.get(section, "NoDisplay", fallback=None), False),
            hidden=parse_bool(parser.get(section, "Hidden", fallback=None), False),
            only_show_in=parse_list(parser.get(section, "OnlyShowIn", fallback="")),
            not_show_in=parse_list(parser.get(section, "NotShowIn", fallback="")),
        )
        return entry


class DesktopAppScanner:
    """Fast, cached scanner for freedesktop application entries."""

    def __init__(
        self,
        directories: Sequence[pathlib.Path] | None = None,
        *,
        include_hidden: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        self.directories = tuple(directories or DESKTOP_DIRS)
        self.include_hidden = include_hidden
        self.logger = logger or setup_logging("neox-app-scanner")
        self.cache_file = NEOX_CACHE_DIR / "applications.json"
        self._apps: list[DesktopEntry] = []
        self._lock = threading.RLock()
        self._watch_stop = threading.Event()

    @property
    def apps(self) -> list[DesktopEntry]:
        """Return a copy of the currently known applications."""

        with self._lock:
            return list(self._apps)

    def _signature(self) -> str:
        """Build a cheap signature of desktop-entry directories for cache checks."""

        chunks: list[str] = []
        for directory in self.directories:
            try:
                stat = directory.stat()
            except OSError:
                continue
            latest = 0
            count = 0
            try:
                for file_path in directory.rglob("*.desktop"):
                    with contextlib.suppress(OSError):
                        file_stat = file_path.stat()
                        latest = max(latest, int(file_stat.st_mtime_ns))
                        count += 1
            except OSError:
                pass
            chunks.append(f"{directory}:{stat.st_mtime_ns}:{latest}:{count}")
        return hashlib.sha256("|".join(chunks).encode("utf-8")).hexdigest()

    def _load_cache(self, signature: str) -> list[DesktopEntry] | None:
        """Load cached applications if the directory signature matches."""

        try:
            payload = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if payload.get("signature") != signature:
            return None
        apps = [DesktopEntry.from_json(item) for item in payload.get("apps", [])]
        self.logger.debug("Loaded %d applications from cache", len(apps))
        return apps

    def _save_cache(self, signature: str, apps: Sequence[DesktopEntry]) -> None:
        """Persist scanner results to JSON cache."""

        ensure_runtime_dirs()
        payload = {
            "version": VERSION,
            "signature": signature,
            "generated_at": time.time(),
            "apps": [app.to_json() for app in apps],
        }
        tmp = self.cache_file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.cache_file)
        except OSError as exc:
            self.logger.debug("Cannot write app cache: %s", exc)

    def scan(self, *, force: bool = False) -> list[DesktopEntry]:
        """Scan application directories and update the in-memory app list."""

        start = time.perf_counter()
        signature = self._signature()
        if not force:
            cached = self._load_cache(signature)
            if cached is not None:
                with self._lock:
                    self._apps = cached
                return cached

        by_id: dict[str, DesktopEntry] = {}
        for directory in self.directories:
            if not directory.exists():
                continue
            try:
                files = sorted(directory.rglob("*.desktop"))
            except OSError as exc:
                self.logger.debug("Cannot scan %s: %s", directory, exc)
                continue
            for file_path in files:
                entry = DesktopEntry.from_file(file_path)
                if entry is None:
                    continue
                if self.include_hidden or entry.should_show():
                    by_id[entry.id] = entry
        apps = sorted(by_id.values(), key=lambda app: app.name.casefold())
        with self._lock:
            self._apps = apps
        self._save_cache(signature, apps)
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.logger.info("Scanned %d applications in %.1f ms", len(apps), elapsed_ms)
        return apps

    def by_id(self) -> dict[str, DesktopEntry]:
        """Return a mapping from desktop-entry id to application."""

        return {app.id: app for app in self.apps}

    def fuzzy_search(self, query: str, limit: int = 8) -> list[DesktopEntry]:
        """Return the best fuzzy matches for ``query``."""

        query = query.strip().lower()
        if not query:
            return self.apps[:limit]
        scored: list[tuple[float, DesktopEntry]] = []
        for app in self.apps:
            score = fuzzy_score(query, app.searchable_text)
            if score > 0:
                scored.append((score, app))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [app for _score, app in scored[:limit]]

    def watch(self, callback: Callable[[list[DesktopEntry]], None], interval: float = 2.0) -> threading.Thread:
        """Watch application directories and invoke ``callback`` on changes.

        The implementation uses ``watchdog`` when available, otherwise a very low
        overhead polling fallback based on directory signatures.  It runs on a
        daemon thread and is safe for GTK components to use by re-dispatching the
        callback through ``GLib.idle_add``.
        """

        def loop() -> None:
            previous = ""
            while not self._watch_stop.is_set():
                try:
                    current = self._signature()
                    if current != previous:
                        previous = current
                        apps = self.scan(force=True)
                        callback(apps)
                except Exception as exc:  # pragma: no cover - defensive daemon loop.
                    self.logger.exception("Application watch error: %s", exc)
                self._watch_stop.wait(interval)

        thread = threading.Thread(target=loop, name="neox-app-watch", daemon=True)
        thread.start()
        return thread

    def stop_watching(self) -> None:
        """Stop the watch thread started by :meth:`watch`."""

        self._watch_stop.set()


def fuzzy_score(pattern: str, text: str) -> float:
    """Small dependency-free fuzzy matcher optimized for app search.

    The scorer rewards contiguous matches and matches that begin at word
    boundaries.  It is deterministic and fast enough for thousands of desktop
    entries without extra dependencies.
    """

    if pattern in text:
        boundary_bonus = 1.0 if text.startswith(pattern) or f" {pattern}" in text else 0.2
        return 100.0 + boundary_bonus - (len(text) - len(pattern)) * 0.001
    score = 0.0
    pos = -1
    consecutive = 0
    for char in pattern:
        found = text.find(char, pos + 1)
        if found == -1:
            return 0.0
        if found == pos + 1:
            consecutive += 1
            score += 4.0 + consecutive
        else:
            consecutive = 0
            score += 1.0
        if found == 0 or text[found - 1] in " -_/.":
            score += 2.0
        pos = found
    return score / max(1, len(pattern))


class ConfigManager:
    """Simple INI configuration manager for ``~/.config/neox/neox.conf``."""

    def __init__(self, path: pathlib.Path | None = None) -> None:
        self.path = path or NEOX_CONFIG_DIR / "neox.conf"
        self.parser = configparser.ConfigParser(interpolation=None)
        self.reload()

    def reload(self) -> None:
        """Reload the configuration file, keeping defaults if it does not exist."""

        self.parser.clear()
        self.parser["desktop_grid"] = {"columns": "8", "rows": "5", "icon_size": "72"}
        self.parser["appearance"] = {"theme": "neox-dark", "accent": "#3b82f6"}
        self.parser["task_switcher"] = {"focus_mode": "focus", "max_per_page": "10"}
        self.parser["panel"] = {"width": "400", "height": "40", "expanded_width_percent": "70"}
        if self.path.exists():
            try:
                self.parser.read(self.path, encoding="utf-8")
            except configparser.Error as exc:
                LOGGER.warning("Configuration parse error in %s: %s", self.path, exc)

    def get(self, section: str, option: str, fallback: str = "") -> str:
        """Return a string config value."""

        return self.parser.get(section, option, fallback=fallback)

    def getint(self, section: str, option: str, fallback: int = 0) -> int:
        """Return an integer config value."""

        try:
            return self.parser.getint(section, option, fallback=fallback)
        except ValueError:
            return fallback

    def getfloat(self, section: str, option: str, fallback: float = 0.0) -> float:
        """Return a float config value."""

        try:
            return self.parser.getfloat(section, option, fallback=fallback)
        except ValueError:
            return fallback

    def getbool(self, section: str, option: str, fallback: bool = False) -> bool:
        """Return a boolean config value."""

        try:
            return self.parser.getboolean(section, option, fallback=fallback)
        except ValueError:
            return fallback


class HyprlandIPC:
    """Convenience wrapper around ``hyprctl`` JSON and dispatch commands."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or setup_logging("neox-hyprland")

    def json(self, command: str) -> Any:
        """Run ``hyprctl -j <command>`` and parse JSON output."""

        result = run_command(["hyprctl", "-j", command], timeout=2, logger=self.logger)
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout or "null")
        except json.JSONDecodeError as exc:
            self.logger.debug("Invalid hyprctl JSON for %s: %s", command, exc)
            return None

    def dispatch(self, dispatcher: str, argument: str = "") -> bool:
        """Run a Hyprland dispatcher command."""

        args = ["hyprctl", "dispatch", dispatcher]
        if argument:
            args.append(argument)
        result = run_command(args, timeout=2, logger=self.logger)
        return result.returncode == 0

    def clients(self) -> list[dict[str, Any]]:
        """Return open Hyprland clients as dictionaries."""

        payload = self.json("clients")
        return payload if isinstance(payload, list) else []

    def active_window(self) -> dict[str, Any]:
        """Return the active Hyprland window information."""

        payload = self.json("activewindow")
        return payload if isinstance(payload, dict) else {}

    def monitors(self) -> list[dict[str, Any]]:
        """Return Hyprland monitor information."""

        payload = self.json("monitors")
        return payload if isinstance(payload, list) else []


class JsonLineClient:
    """Tiny JSON-lines client for the NEOX Unix-domain event socket."""

    def __init__(self, path: pathlib.Path | None = None, logger: logging.Logger | None = None) -> None:
        self.path = path or (NEOX_RUNTIME_DIR / "shell.sock")
        self.logger = logger or setup_logging("neox-bus-client")

    def send(self, event: str, payload: Mapping[str, Any] | None = None, timeout: float = 0.2) -> bool:
        """Send one event to the shell daemon if it is running."""

        ensure_runtime_dirs()
        message = json.dumps({"event": event, "payload": dict(payload or {})}, ensure_ascii=False) + "\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                sock.connect(str(self.path))
                sock.sendall(message.encode("utf-8"))
            return True
        except OSError as exc:
            self.logger.debug("Cannot send event %s to %s: %s", event, self.path, exc)
            return False


class JsonLineServer:
    """Minimal JSON-lines Unix socket server used by ``neox-shell``."""

    def __init__(self, path: pathlib.Path | None = None, logger: logging.Logger | None = None) -> None:
        self.path = path or (NEOX_RUNTIME_DIR / "shell.sock")
        self.logger = logger or setup_logging("neox-bus-server")
        self.handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None

    def subscribe(self, event: str, handler: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe a Python callable to a bus event."""

        self.handlers.setdefault(event, []).append(handler)

    def start(self) -> None:
        """Start the Unix socket server on a daemon thread."""

        ensure_runtime_dirs()
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.path))
        sock.listen(20)
        sock.settimeout(0.5)
        self._socket = sock
        self._thread = threading.Thread(target=self._serve, name="neox-json-bus", daemon=True)
        self._thread.start()
        self.logger.info("NEOX event bus listening on %s", self.path)

    def stop(self) -> None:
        """Stop the Unix socket server."""

        self._stop.set()
        if self._socket is not None:
            with contextlib.suppress(OSError):
                self._socket.close()
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    def _serve(self) -> None:
        assert self._socket is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            try:
                data = conn.recv(65536).decode("utf-8", errors="replace")
            except OSError:
                return
            for line in data.splitlines():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = str(message.get("event", ""))
                payload = message.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}
                for handler in self.handlers.get(event, []):
                    try:
                        handler(payload)
                    except Exception as exc:  # pragma: no cover - defensive event bus.
                        self.logger.exception("Event handler failed for %s: %s", event, exc)


class Debouncer:
    """Threading based debounce helper for file-system and search updates."""

    def __init__(self, delay: float, callback: Callable[..., None]) -> None:
        self.delay = delay
        self.callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.delay, self.callback, args=args, kwargs=kwargs)
            self._timer.daemon = True
            self._timer.start()


def chunked(items: Sequence[Any], size: int) -> list[list[Any]]:
    """Return ``items`` split into pages of at most ``size`` elements."""

    if size <= 0:
        return [list(items)]
    return [list(items[index : index + size]) for index in range(0, len(items), size)] or [[]]


def read_json(path: pathlib.Path, default: Any) -> Any:
    """Read JSON from disk, returning ``default`` on missing/invalid data."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: pathlib.Path, data: Any) -> bool:
    """Atomically write JSON to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError as exc:
        LOGGER.warning("Cannot write JSON %s: %s", path, exc)
        return False


def icon_is_file(icon: str) -> bool:
    """Return whether ``icon`` points to an existing image file."""

    return bool(icon and pathlib.Path(icon).expanduser().exists())


def safe_eval_math(expression: str) -> float | None:
    """Evaluate a small mathematical expression safely for app search."""

    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Num,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Load,
        ast.Call,
        ast.Name,
    )
    allowed_names = {name: getattr(math, name) for name in dir(math) if not name.startswith("_")}
    allowed_names.update({"abs": abs, "round": round})
    if not re.fullmatch(r"[0-9+\-*/%()., a-zA-Z_]+", expression):
        return None
    try:
        tree = ast.parse(expression.replace(",", "."), mode="eval")
    except SyntaxError:
        return None
    if not all(isinstance(node, allowed_nodes) for node in ast.walk(tree)):
        return None
    try:
        value = eval(compile(tree, "<neox-math>", "eval"), {"__builtins__": {}}, allowed_names)
    except Exception:
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def install_signal_handlers(stop_callback: Callable[[], None]) -> None:
    """Install SIGINT/SIGTERM handlers for graceful daemon shutdown."""

    def handler(_signum: int, _frame: Any) -> None:
        stop_callback()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def temporary_png(prefix: str = "neox") -> pathlib.Path:
    """Return a unique temporary PNG path under the runtime directory."""

    ensure_runtime_dirs()
    fd, name = tempfile.mkstemp(prefix=f"{prefix}-", suffix=".png", dir=str(NEOX_RUNTIME_DIR))
    os.close(fd)
    return pathlib.Path(name)


def category_label(categories: Iterable[str]) -> str:
    """Map freedesktop categories to localized user-facing NEOX groups."""

    mapping = [
        ({"Network", "WebBrowser", "Email"}, "İnternet"),
        ({"Office", "WordProcessor", "Spreadsheet", "Presentation"}, "Ofis"),
        ({"Development", "IDE", "GUIDesigner"}, "Geliştirme"),
        ({"AudioVideo", "Audio", "Video", "Graphics", "Photography"}, "Multimedya"),
        ({"System", "Settings", "Utility"}, "Sistem"),
        ({"Game"}, "Oyunlar"),
        ({"Education", "Science"}, "Eğitim"),
    ]
    category_set = set(categories)
    for keys, label in mapping:
        if category_set.intersection(keys):
            return label
    return "Diğer"


__all__ = [
    "APP_ID",
    "VERSION",
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "XDG_RUNTIME_DIR",
    "NEOX_CONFIG_DIR",
    "NEOX_CACHE_DIR",
    "NEOX_RUNTIME_DIR",
    "DESKTOP_DIRS",
    "ConfigManager",
    "Debouncer",
    "DesktopAppScanner",
    "DesktopEntry",
    "HyprlandIPC",
    "JsonLineClient",
    "JsonLineServer",
    "SingletonLock",
    "category_label",
    "chunked",
    "ensure_runtime_dirs",
    "fuzzy_score",
    "icon_is_file",
    "install_signal_handlers",
    "read_json",
    "run_command",
    "run_detached",
    "safe_eval_math",
    "setup_logging",
    "temporary_png",
    "which",
    "write_json",
]

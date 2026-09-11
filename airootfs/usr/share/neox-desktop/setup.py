#!/usr/bin/env python3
"""setuptools installer for NEOX desktop helper scripts."""

from __future__ import annotations

from pathlib import Path
from setuptools import setup

ROOT = Path(__file__).parent
SHELL_SCRIPTS = [str(path) for path in (ROOT / "shell").glob("neox-*.py")]
WIDGET_SCRIPTS = [str(path) for path in (ROOT / "widgets").glob("neox-*.py")]

setup(
    name="neox-desktop",
    version="0.1.0",
    description="Mobile-inspired desktop environment shell for Hyprland",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="NEOX Desktop Contributors",
    license="GPL-3.0-or-later",
    python_requires=">=3.11",
    py_modules=["neox_common", "neox_hd_ui"],
    package_dir={"": "shell"},
    scripts=SHELL_SCRIPTS + WIDGET_SCRIPTS + [str(ROOT / "themes" / "theme-engine.py"), str(ROOT / "dbus" / "neox-dbus-service.py")],
    data_files=[
        ("share/wayland-sessions", [str(ROOT / "session" / "neox.desktop")]),
        ("share/neox", [str(ROOT / "session" / "neox-session.session"), str(ROOT / "compositor" / "hyprland.conf")]),
        ("share/neox/themes", [str(path) for path in (ROOT / "themes").glob("*.css")]),
        ("share/doc/neox-desktop", [str(ROOT / "README.md"), str(ROOT / "LICENSE")]),
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: X11 Applications :: GTK",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python :: 3.11",
        "Topic :: Desktop Environment",
    ],
)

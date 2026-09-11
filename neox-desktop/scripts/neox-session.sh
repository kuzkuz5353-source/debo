#!/usr/bin/env bash
# Start a full NEOX session. Display managers execute this file through
# /usr/bin/neox-session, and developers may run it from a TTY.
set -Eeuo pipefail

export XDG_CURRENT_DESKTOP="NEOX:Hyprland"
export XDG_SESSION_DESKTOP="neox"
export XDG_SESSION_TYPE="wayland"
export QT_QPA_PLATFORM="wayland;xcb"
export GDK_BACKEND="wayland,x11"
export MOZ_ENABLE_WAYLAND="1"
export NEOX_CONFIG_HOME="${NEOX_CONFIG_HOME:-$HOME/.config/neox}"

# Update DBus/systemd activation environments so portals and user units see the
# correct Wayland display once Hyprland starts.
dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE NEOX_CONFIG_HOME 2>/dev/null || true
systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE NEOX_CONFIG_HOME 2>/dev/null || true

CONFIG="$HOME/.config/hypr/hyprland.conf"
if [[ ! -f "$CONFIG" && -f "/usr/share/neox/hyprland.conf" ]]; then
    mkdir -p "$HOME/.config/hypr"
    cp "/usr/share/neox/hyprland.conf" "$CONFIG"
fi

exec Hyprland -c "$CONFIG"
